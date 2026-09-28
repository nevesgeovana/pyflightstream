"""Workspace storage management and synchronisation (0.30.0).

Five commands of ``pyfs-matrix`` live here, and every one of them writes one
entry to ``storage_management.json`` at the workspace root, the provenance of
every storage call ever made in that workspace:

- ``space-in-use`` reports the sizes on disk, by top-level folder, by
  ``sims/sim_*`` and by extension, in that order;
- ``free-space <m<id>>`` runs a recipe from ``inputs/management/m<id>.toml``:
  ``compact_sims`` (a simulation folder becomes ``sims/sim_<id>.zip``),
  ``delete_extensions`` (files of named extensions under ``sims/``) and
  ``post_archives`` (the ``archive/<stamp>/`` folders the post writes when it
  supersedes a product, compacted or deleted);
- ``delete-sims <ids>`` deletes simulations: the folder, their post products
  and their records, leaving a note in ``runs.json`` and the full mention here;
- ``sync <level>`` brings runs and results from the other workspaces named in
  ``inputs/sync-workspaces.toml`` into the main one.

THE RULES EVERY COMMAND KEEPS. A command that changes files previews by
default and changes them only with ``apply=True``. A recipe touches ``sims/``
and the post archives only, never ``inputs/``, a matrix, a saved ``.fsm``, a
script, a log, or a file a run record names or hashes: those are what a later
``post`` needs to extract the post-processing again. A compacted simulation is
restored in place, automatically, by ``post``, ``collect`` and a continuation
(:func:`ensure_sim_expanded`). ``storage_management.json`` has the schema
``pyfs-storage/1`` that the standalone ``fts_sync.py`` script started, and a
file that script began is continued, never rewritten.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import stat
import tomllib
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyflightstream.workspace import (
    CampaignWorkspace,
    RunStatus,
    WorkspaceError,
    _is_link,
    _make_dir_link,
    _remove_link,
    planned_points_without_record,
    post_stages,
)
from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP

__all__ = [
    "COMPACTED_SUFFIX",
    "DELETED_SIM_KEY",
    "MANAGEMENT_DIR",
    "MATRIX_PRODUCT_CHOICES",
    "STORAGE_FILE",
    "STORAGE_SCHEMA",
    "SYNC_CONFIG",
    "SYNC_LEVELS",
    "StorageError",
    "delete_sims",
    "disk_estimate",
    "ensure_sim_expanded",
    "free_space",
    "read_storage_calls",
    "record_storage_call",
    "space_in_use",
    "sync_workspaces",
]

STORAGE_FILE = "storage_management.json"
STORAGE_SCHEMA = "pyfs-storage/1"
TOOL = "pyfs-matrix"
MANAGEMENT_DIR = Path("inputs") / "management"
SYNC_CONFIG = Path("inputs") / "sync-workspaces.toml"
SYNC_LEVELS = ("runs", "post", "fsm", "all")
MATRIX_PRODUCT_CHOICES = ("points-only", "regenerate")
COMPACTED_SUFFIX = ".zip"
#: The key of a ``runs.json`` row that is a note, not a record: the id it names
#: belonged to a simulation that ``delete-sims`` deleted. ``read_manifest``
#: passes such a row over; the raw manifest carries it as evidence.
DELETED_SIM_KEY = "deleted_sim"
_COMPACT_META = "_pyfs_compacted.json"
_PROTECTED_SUFFIXES = (".fsm",)
_RECIPE_TABLES = ("compact_sims", "delete_extensions", "post_archives")


class StorageError(WorkspaceError):
    """A storage command refused: the message names what and why."""


# --------------------------------------------------------------------------- helpers


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _stamp() -> str:
    return _now().strftime(ARCHIVE_STAMP)


def _version() -> str:
    from pyflightstream import __version__

    return __version__


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    """Say whether ``path`` is a symbolic link or a Windows junction (never followed)."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _walk_files(root: Path) -> Iterator[Path]:
    """Every regular file below ``root``, without following a link or junction."""
    if not root.is_dir() or _is_reparse(root):
        return
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if _is_reparse(path):
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
            elif entry.is_file(follow_symlinks=False):
                yield path


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def human_bytes(count: float) -> str:
    """``1536`` -> ``1.5 KB``; binary multiples, one decimal."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(count) < 1024 or unit == "TB":
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} TB"  # pragma: no cover - the loop returns


def _workspace(root: str | Path) -> CampaignWorkspace:
    root = Path(root).resolve()
    if not root.is_dir():
        raise StorageError(f"{root}: not a folder")
    # A FOLDER THAT IS NOT A WORKSPACE IS REFUSED, so a storage record is never
    # written into a parent folder that holds several workspaces (measured: a
    # smoke run from the wrong directory wrote one there).
    if not ((root / "runs.json").is_file() or (root / "inputs").is_dir()):
        raise StorageError(
            f"{root} is not a pyfs-matrix workspace (no runs.json, no inputs/); name the "
            "workspace root with --workspace"
        )
    return CampaignWorkspace(root)


# --------------------------------------------------------------------------- the record


def read_storage_calls(root: str | Path) -> list[dict[str, Any]]:
    """Every call recorded in ``storage_management.json``, oldest first."""
    path = Path(root) / STORAGE_FILE
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != STORAGE_SCHEMA or not isinstance(document.get("calls"), list):
        raise StorageError(
            f"{path} is not a {STORAGE_SCHEMA} file; it is left untouched. Move it aside to "
            "start a new storage record."
        )
    return list(document["calls"])


def record_storage_call(root: str | Path, entry: dict[str, Any]) -> int:
    """Append one call to ``storage_management.json``; return its index.

    The write is atomic and serialised by the workspace's own manifest lock on
    the storage file, so two commands cannot interleave their entries.
    """
    workspace = _workspace(root)
    path = workspace.root / STORAGE_FILE
    full = {"at": _now().isoformat(), "tool": TOOL, "tool_version": _version(), **entry}
    with workspace._manifest_lock(path):
        calls = read_storage_calls(workspace.root)
        calls.append(full)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps({"schema": STORAGE_SCHEMA, "calls": calls}, indent=1, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    return len(calls) - 1


# --------------------------------------------------------------------------- space in use


@dataclass
class SpaceReport:
    """The sizes of one workspace, in the three groupings ``space-in-use`` prints."""

    root: Path
    total: int = 0
    files: int = 0
    by_folder: dict[str, int] = field(default_factory=dict)
    by_sim: dict[str, int] = field(default_factory=dict)
    by_extension: dict[str, int] = field(default_factory=dict)
    compacted: list[str] = field(default_factory=list)
    free: int = 0

    def lines(self, *, top: int = 15) -> list[str]:
        """Render the report: folders, then simulations, then extensions."""
        out = [
            f"space in use: {self.root}",
            f"  total {human_bytes(self.total)} in {self.files} files; "
            f"free on this disk {human_bytes(self.free)}",
            "",
            "by top-level folder:",
        ]
        out += _table(self.by_folder, self.total, top=None)
        out += ["", f"by simulation (sims/sim_*; {len(self.by_sim)} total):"]
        out += _table(self.by_sim, self.total, top=top)
        if self.compacted:
            out.append(f"  compacted: {', '.join(self.compacted)}")
        out += ["", "by extension:"]
        out += _table(self.by_extension, self.total, top=top)
        return out


def _table(sizes: dict[str, int], total: int, *, top: int | None) -> list[str]:
    ranked = sorted(sizes.items(), key=lambda item: (-item[1], item[0]))
    shown = ranked if top is None else ranked[:top]
    rows = [
        f"  {name:<40} {human_bytes(size):>10} {100.0 * size / total if total else 0.0:6.1f} %"
        for name, size in shown
    ]
    if top is not None and len(ranked) > top:
        rest = sum(size for _, size in ranked[top:])
        rows.append(f"  ... {len(ranked) - top} more{'':<30} {human_bytes(rest):>10}")
    return rows


def _measure(root: Path) -> SpaceReport:
    report = SpaceReport(root=root, free=shutil.disk_usage(root).free)
    for path in _walk_files(root):
        size = _size(path)
        relative = path.relative_to(root)
        parts = relative.parts
        folder = parts[0] + ("/" if len(parts) > 1 else "")
        report.by_folder[folder] = report.by_folder.get(folder, 0) + size
        if len(parts) > 1 and parts[0] == "sims":
            name = parts[1]
            if name.startswith("sim_"):
                report.by_sim[name] = report.by_sim.get(name, 0) + size
                if len(parts) == 2 and name.endswith(COMPACTED_SUFFIX):
                    report.compacted.append(name)
        extension = path.suffix.lower() or "(none)"
        report.by_extension[extension] = report.by_extension.get(extension, 0) + size
        report.total += size
        report.files += 1
    report.compacted.sort()
    return report


def space_in_use(root: str | Path) -> SpaceReport:
    """Measure the workspace and record the call (the report changes no file)."""
    workspace = _workspace(root)
    report = _measure(workspace.root)
    record_storage_call(
        workspace.root,
        {
            "action": "space-in-use",
            "applied": False,
            "total_bytes": report.total,
            "files": report.files,
            "free_bytes": report.free,
            "by_folder": report.by_folder,
            "by_extension": report.by_extension,
            "sims": len(report.by_sim),
            "compacted": report.compacted,
        },
    )
    return report


# --------------------------------------------------------------------------- compaction


def _remove_sim_folder(folder: Path) -> list[str]:
    """Remove a simulation folder WITHOUT ever deleting what a link points at.

    Every link or junction below the folder (its ``inputs`` into the geometry
    library first of all) is undone before the folder is removed, and the
    removal is refused if one is still there: deleting a simulation must
    never delete the mesh it was linked to (the owner's rule, 2026-09-28).
    Returns the links undone, relative to the folder.
    """
    undone: list[str] = []
    stack = [folder]
    while stack:
        current = stack.pop()
        for entry in list(os.scandir(current)):
            path = Path(entry.path)
            if _is_reparse(path):
                if _is_link(path) or path.is_dir():
                    _remove_link(path)
                else:
                    path.unlink()
                undone.append(path.relative_to(folder).as_posix())
            elif entry.is_dir(follow_symlinks=False):
                stack.append(path)
    left = [p for p in folder.rglob("*") if _is_reparse(p)]
    if left:
        raise StorageError(
            f"{folder}: a link is still inside ({left[0]}); the folder was not removed, so "
            "nothing it points at can be deleted"
        )
    shutil.rmtree(folder)
    return undone


def _relink_inputs(main: CampaignWorkspace, other: Path, sim_name: str) -> str | None:
    """Make main's ``sims/<sim>/inputs`` a link into MAIN's geometry library.

    The other workspace's simulation links its ``inputs`` into ITS library;
    the same geometry folder (the library itself or one geometry's folder
    under it) is linked in main, so a synced simulation reads main's mesh and
    no copy of it is made. Returns what happened, or None when there was
    nothing to do.
    """
    target_inputs = main.root / "sims" / sim_name / "inputs"
    if not target_inputs.parent.is_dir() or _is_link(target_inputs):
        return None
    if target_inputs.is_dir() and any(target_inputs.iterdir()):
        return None
    source_inputs = other / "sims" / sim_name / "inputs"
    if not _is_reparse(source_inputs):
        return (
            "not linked: the other workspace staged a copy of its inputs, which sync never copies"
        )
    library = (main.inputs_dir / "geometries").resolve()
    pointed = Path(os.path.realpath(source_inputs))
    try:
        relative = pointed.relative_to((other / "inputs" / "geometries").resolve())
    except ValueError:
        # A link read through a share may not resolve on this machine: take
        # the geometry folder by name, the one component the layout allows.
        relative = Path(pointed.name) if (library / pointed.name).is_dir() else Path(".")
    wanted = (library / relative).resolve()
    if not wanted.is_dir() or (wanted != library and wanted.parent != library):
        return f"not linked: {relative.as_posix()} is not in main's inputs/geometries"
    if target_inputs.is_dir():
        target_inputs.rmdir()
    _make_dir_link(wanted, target_inputs)
    return f"linked to inputs/geometries/{relative.as_posix()}".rstrip("/.")


def _zip_path(workspace: CampaignWorkspace, sim_id: str) -> Path:
    folder = workspace.sim_dir(sim_id)
    return folder.with_name(folder.name + COMPACTED_SUFFIX)


def _compact_sim(workspace: CampaignWorkspace, sim_id: str) -> dict[str, Any]:
    """Zip one simulation folder, verify every member, then remove the folder."""
    folder = workspace.sim_dir(sim_id)
    archive = _zip_path(workspace, sim_id)
    inputs = folder / "inputs"
    link_target = os.path.realpath(inputs) if _is_link(inputs) else None
    members: dict[str, str] = {}
    temporary = archive.with_name(archive.name + f".{os.getpid()}.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for path in sorted(_walk_files(folder)):
            name = path.relative_to(folder).as_posix()
            zf.write(path, name)
            members[name] = _sha256(path)
        zf.writestr(
            _COMPACT_META,
            json.dumps({"sim_id": sim_id, "inputs_link": link_target, "members": members}),
        )
    with zipfile.ZipFile(temporary) as zf:
        for name, digest in members.items():
            if hashlib.sha256(zf.read(name)).hexdigest() != digest:
                temporary.unlink()
                raise StorageError(
                    f"sim {sim_id}: the compacted copy of {name} does not match the file; "
                    "nothing was removed"
                )
    temporary.replace(archive)
    before = sum(_size(folder / name) for name in members)
    _remove_sim_folder(folder)
    return {
        "sim_id": sim_id,
        "archive": archive.relative_to(workspace.root).as_posix(),
        "files": len(members),
        "bytes_before": before,
        "bytes_after": _size(archive),
        "inputs_link": link_target,
    }


def ensure_sim_expanded(workspace: CampaignWorkspace, sim_id: str, *, reason: str) -> bool:
    """Restore ``sims/sim_<id>.zip`` in place when its folder is absent.

    Called by ``post``, ``collect`` and a continuation before they read a
    simulation, so a compacted simulation is read as if it had never been
    compacted. Returns True when a restore happened; the restore is recorded
    in ``storage_management.json`` and the folder stays expanded.
    """
    folder = workspace.sim_dir(sim_id)
    archive = _zip_path(workspace, sim_id)
    if folder.exists() or not archive.is_file():
        return False
    temporary = folder.with_name(folder.name + f".{os.getpid()}.restoring")
    if temporary.exists():
        shutil.rmtree(temporary)
    with zipfile.ZipFile(archive) as zf:
        meta = json.loads(zf.read(_COMPACT_META)) if _COMPACT_META in zf.namelist() else {}
        for info in zf.infolist():
            if info.filename == _COMPACT_META:
                continue
            target = (temporary / info.filename).resolve()
            if temporary.resolve() not in target.parents:
                raise StorageError(f"{archive}: member {info.filename} leaves the folder")
            zf.extract(info, temporary)
    for name, digest in dict(meta.get("members", {})).items():
        if _sha256(temporary / name) != digest:
            shutil.rmtree(temporary)
            raise StorageError(f"{archive}: {name} does not match its recorded hash; not restored")
    temporary.replace(folder)
    link = meta.get("inputs_link")
    if link and not (folder / "inputs").exists():
        try:
            _make_dir_link(Path(link), folder / "inputs")
        except OSError:
            (folder / "inputs").mkdir()
    archive.unlink()
    record_storage_call(
        workspace.root,
        {"action": "restore", "applied": True, "sim_id": sim_id, "reason": reason},
    )
    return True


def compacted_sim_ids(workspace: CampaignWorkspace) -> list[str]:
    """Return the simulations stored as ``sims/sim_<id>.zip``."""
    sims = workspace.root / "sims"
    if not sims.is_dir():
        return []
    return sorted(
        path.name[len("sim_") : -len(COMPACTED_SUFFIX)]
        for path in sims.glob(f"sim_*{COMPACTED_SUFFIX}")
        if path.is_file()
    )


# --------------------------------------------------------------------------- recipes


def _records_by_sim(workspace: CampaignWorkspace) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in workspace.read_raw_manifest():
        if row.get(DELETED_SIM_KEY) is not None:
            continue
        out.setdefault(str(row.get("sim_id")), []).append(row)
    return out


def _protected(workspace: CampaignWorkspace, sim_id: str, rows: list[dict[str, Any]]) -> set[Path]:
    """Return the files of one simulation a recipe may never remove.

    A saved simulation, every script, every log, and every file a record names
    or hashes (outputs, staged inputs, the script): what a later ``post``
    reads to extract the post-processing again.
    """
    folder = workspace.sim_dir(sim_id)
    keep: set[Path] = set()
    for row in rows:
        names: list[str] = list(row.get("outputs") or [])
        names += list((row.get("inputs_sha256") or {}).keys())
        names += list((row.get("output_digests") or row.get("outputs_sha256") or {}).keys())
        if row.get("script_path"):
            names.append(str(row["script_path"]))
        for name in names:
            candidate = (folder / name).resolve()
            keep.add(candidate)
            cwd = row.get("cwd")
            if cwd:
                keep.add((Path(cwd) / name).resolve())
    for path in _walk_files(folder):
        lowered = path.name.lower()
        if (
            path.suffix.lower() in _PROTECTED_SUFFIXES
            or "scripts" in path.relative_to(folder).parts
            or lowered.endswith(("_log.txt", ".log"))
            or lowered in ("fs_runtime_output.txt", "flightstreamlog.txt")
        ):
            keep.add(path.resolve())
    return keep


def _select_sims(
    spec: dict[str, Any], records: dict[str, list[dict[str, Any]]], present: Iterable[str]
) -> list[str]:
    wanted = spec.get("sims", "all")
    candidates = sorted(present)
    if wanted != "all":
        if not isinstance(wanted, list):
            raise StorageError("'sims' is \"all\" or a list of simulation ids")
        named = {str(item) for item in wanted}
        missing = named.difference(candidates)
        if missing:
            raise StorageError(f"no simulation folder for sims {sorted(missing)}")
        candidates = [sim for sim in candidates if sim in named]
    statuses = spec.get("status")
    if statuses is not None:
        allowed = {str(item).upper() for item in statuses}
        unknown = allowed.difference(status.value for status in RunStatus)
        if unknown:
            raise StorageError(f"unknown run status {sorted(unknown)}")
        candidates = [
            sim
            for sim in candidates
            if records.get(sim)
            and all(str(row.get("status")) in allowed for row in records.get(sim, []))
        ]
    return candidates


def _older_than(path: Path, days: float | None) -> bool:
    if days is None:
        return True
    age = _now().timestamp() - path.stat().st_mtime
    return age >= float(days) * 86400.0


def read_recipe(root: Path, recipe: str) -> tuple[Path, dict[str, Any]]:
    """Read ``inputs/management/<recipe>.toml`` and check its tables."""
    name = recipe[:-5] if recipe.endswith(".toml") else recipe
    if not name.startswith("m") or "/" in name or "\\" in name:
        raise StorageError(f"{recipe}: a storage recipe is named m<id>, in {MANAGEMENT_DIR}")
    path = root / MANAGEMENT_DIR / f"{name}.toml"
    if not path.is_file():
        raise StorageError(f"{path}: no such recipe")
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    unknown = set(document).difference(_RECIPE_TABLES + ("description",))
    if unknown:
        raise StorageError(
            f"{path}: unknown table(s) {sorted(unknown)}; a recipe holds "
            f"{', '.join(f'[[{t}]]' for t in _RECIPE_TABLES)}"
        )
    for table in _RECIPE_TABLES:
        entries = document.get(table, [])
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise StorageError(f"{path}: {table} is written [[{table}]], one table per step")
    return path, document


def free_space(root: str | Path, recipe: str, *, apply: bool = False) -> dict[str, Any]:
    """Run a storage recipe: preview by default, change files only with ``apply``.

    Returns the entry recorded in ``storage_management.json``.
    """
    workspace = _workspace(root)
    if workspace.manifest_path.with_name("runs.json.lock").exists():
        raise StorageError(f"{workspace.root}: runs.json.lock present, a run is in progress")
    path, document = read_recipe(workspace.root, recipe)
    records = _records_by_sim(workspace)
    sims_root = workspace.root / "sims"
    present = [
        p.name[len("sim_") :]
        for p in (sims_root.iterdir() if sims_root.is_dir() else [])
        if p.is_dir() and p.name.startswith("sim_") and not _is_reparse(p)
    ]
    steps: list[dict[str, Any]] = []
    freed = 0
    for spec in document.get("compact_sims", []):
        step: dict[str, Any] = {"mode": "compact_sims", "sims": [], "refused": {}}
        for sim in _select_sims(spec, records, present):
            rows = records.get(sim, [])
            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):
                step["refused"][sim] = "a run is still SUBMITTED"
                continue
            folder = workspace.sim_dir(sim)
            if not _older_than(folder, spec.get("older_than_days")):
                continue
            if apply:
                done = _compact_sim(workspace, sim)
                freed += done["bytes_before"] - done["bytes_after"]
                step["sims"].append(done)
            else:
                step["sims"].append(
                    {"sim_id": sim, "bytes": sum(_size(p) for p in _walk_files(folder))}
                )
        present = [sim for sim in present if workspace.sim_dir(sim).is_dir()]
        steps.append(step)
    for spec in document.get("delete_extensions", []):
        extensions = [str(e).lower() for e in spec.get("extensions", [])]
        if not extensions or not all(e.startswith(".") for e in extensions):
            raise StorageError(f'{path}: delete_extensions needs extensions = [".vtk", ...]')
        refused_ext = sorted(set(extensions).intersection(_PROTECTED_SUFFIXES))
        if refused_ext:
            raise StorageError(
                f"{path}: {refused_ext} is never deleted by a recipe: the saved simulation "
                "is what a later post or continuation reopens"
            )
        step = {"mode": "delete_extensions", "extensions": extensions, "files": [], "kept": []}
        for sim in _select_sims(spec, records, present):
            rows = records.get(sim, [])
            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):
                continue
            keep = _protected(workspace, sim, rows)
            for file in _walk_files(workspace.sim_dir(sim)):
                if file.suffix.lower() not in extensions:
                    continue
                relative = file.relative_to(workspace.root).as_posix()
                if file.resolve() in keep:
                    step["kept"].append(relative)
                    continue
                size = _size(file)
                step["files"].append({"path": relative, "bytes": size})
                if apply:
                    file.unlink()
                    freed += size
        steps.append(step)
    for spec in document.get("post_archives", []):
        action = spec.get("action", "delete")
        if action not in ("compact", "delete"):
            raise StorageError(f'{path}: post_archives action is "compact" or "delete"')
        keep_latest = int(spec.get("keep_latest", 0))
        step = {"mode": "post_archives", "action": action, "archives": []}
        post_root = workspace.root / "post"
        roots = sorted(post_root.rglob(ARCHIVE_DIR)) if post_root.is_dir() else []
        for archive_root in roots:
            # An `archive` folder inside another archive is part of that
            # archive's stamp, handled (or already removed) with it.
            inner = ARCHIVE_DIR in archive_root.relative_to(post_root).parts[:-1]
            if inner or not archive_root.is_dir() or _is_reparse(archive_root):
                continue
            stamps = sorted(
                (p for p in archive_root.iterdir() if p.is_dir() and not _is_reparse(p)),
                key=lambda p: p.name,
            )
            chosen = stamps[: max(len(stamps) - keep_latest, 0)]
            for stamp_dir in chosen:
                if not _older_than(stamp_dir, spec.get("older_than_days")):
                    continue
                size = sum(_size(p) for p in _walk_files(stamp_dir))
                entry = {
                    "path": stamp_dir.relative_to(workspace.root).as_posix(),
                    "bytes": size,
                }
                if apply:
                    if action == "compact":
                        zipped = shutil.make_archive(str(stamp_dir), "zip", stamp_dir)
                        entry["archive"] = Path(zipped).relative_to(workspace.root).as_posix()
                        freed += size - _size(Path(zipped))
                    else:
                        freed += size
                    shutil.rmtree(stamp_dir)
                step["archives"].append(entry)
        steps.append(step)
    entry = {
        "action": "free-space",
        "applied": apply,
        "recipe": path.relative_to(workspace.root).as_posix(),
        "recipe_sha256": _sha256(path),
        "steps": steps,
        "bytes_freed": freed,
    }
    record_storage_call(workspace.root, entry)
    return entry


# --------------------------------------------------------------------------- delete sims


def _products_of(workspace: CampaignWorkspace, sim_ids: set[str], run_ids: set[str]):
    """Per matrix: the post files that belong to the sims, and the shared ones."""
    found: dict[str, dict[str, list[str]]] = {}
    post = workspace.root / "post"
    for manifest in sorted(post.rglob("products.json")) if post.is_dir() else []:
        if ARCHIVE_DIR in manifest.relative_to(post).parts:
            continue
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        folder = manifest.parent
        own: list[str] = []
        shared: list[str] = []
        for name, entry in dict(document.get("products", {})).items():
            if not isinstance(entry, dict):
                continue
            runs = {str(run) for run in entry.get("runs", []) or []}
            if str(entry.get("sim_id")) in sim_ids:
                own.append(name)
            elif runs & run_ids:
                shared.append(name)
        for run_id, value in dict(document.get("provenance", {})).items():
            if run_id in run_ids and isinstance(value, str):
                own.append(value)
        if own or shared:
            found[folder.relative_to(workspace.root).as_posix()] = {
                "own": sorted(set(own)),
                "shared": sorted(set(shared)),
            }
    return found


def _forget_products(
    manifest: Path, item: dict[str, list[str]], run_ids: set[str], *, sims: list[str], stamp: str
) -> None:
    """Take the deleted files out of ``products.json`` and say which products are stale.

    The products manifest never claims a file that is not on disk
    (ARCHITECTURE invariant 3), so the deleted entries leave it; the shared
    products that still hold the deleted points are named under
    ``deleted_by_storage`` until a post rebuilds the manifest.
    """
    document = json.loads(manifest.read_text(encoding="utf-8"))
    products = dict(document.get("products", {}))
    for name in item["own"]:
        products.pop(name, None)
    document["products"] = products
    provenance = document.get("provenance")
    if isinstance(provenance, dict):
        document["provenance"] = {k: v for k, v in provenance.items() if k not in run_ids}
    notes = list(document.get("deleted_by_storage", []))
    notes.append({"at": _now().isoformat(), "stamp": stamp, "sims": sims, "stale": item["shared"]})
    document["deleted_by_storage"] = notes
    temporary = manifest.with_name(f"{manifest.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest)


def delete_sims(
    root: str | Path,
    sim_ids: Sequence[str],
    *,
    matrix_products: str | None = None,
    apply: bool = False,
    caller: str | None = None,
) -> dict[str, Any]:
    """Delete simulations, their post products and their records.

    Preview by default. With ``apply``, ``matrix_products`` must say what
    happens to a product that mixes the deleted simulation with others:
    ``points-only`` leaves it (marked stale), ``regenerate`` reruns the post
    of that matrix without the deleted points. The records leave
    ``runs.json`` (archived first); one note row per simulation stays there,
    and the full mention is the returned entry, recorded in
    ``storage_management.json``.
    """
    workspace = _workspace(root)
    if matrix_products is not None and matrix_products not in MATRIX_PRODUCT_CHOICES:
        raise StorageError(f"--matrix-products is one of {', '.join(MATRIX_PRODUCT_CHOICES)}")
    if workspace.manifest_path.with_name("runs.json.lock").exists():
        raise StorageError(f"{workspace.root}: runs.json.lock present, a run is in progress")
    ids = [str(sim).strip() for sim in sim_ids if str(sim).strip()]
    if not ids:
        raise StorageError("name at least one simulation id")
    records = _records_by_sim(workspace)
    unknown = [
        sim
        for sim in ids
        if sim not in records
        and not workspace.sim_dir(sim).exists()
        and not _zip_path(workspace, sim).exists()
    ]
    if unknown:
        raise StorageError(f"no record and no folder for sims {unknown}")
    submitted = [
        sim
        for sim in ids
        if any(row.get("status") == RunStatus.SUBMITTED.value for row in records.get(sim, []))
    ]
    if submitted:
        raise StorageError(f"sims {submitted} have a run still SUBMITTED; collect it first")
    run_ids = {str(row.get("run_id")) for sim in ids for row in records.get(sim, [])}
    products = _products_of(workspace, set(ids), run_ids)
    shared = {folder: item["shared"] for folder, item in products.items() if item["shared"]}
    sims_entry = []
    for sim in ids:
        folder, archive = workspace.sim_dir(sim), _zip_path(workspace, sim)
        rows = records.get(sim, [])
        sims_entry.append(
            {
                "sim_id": sim,
                "run_ids": sorted(str(row.get("run_id")) for row in rows),
                "matrix": sorted({str(row.get("matrix_stem")) for row in rows}),
                "statuses": sorted({str(row.get("status")) for row in rows}),
                "dates": sorted(
                    {str(row.get("started_at") or row.get("ended_at")) for row in rows}
                ),
                "bytes": sum(_size(p) for p in _walk_files(folder)) + _size(archive),
                "outputs_sha256": {
                    str(row.get("run_id")): row.get("output_digests") or row.get("outputs_sha256")
                    for row in rows
                },
            }
        )
    entry: dict[str, Any] = {
        "action": "delete-sims",
        "applied": False,
        "caller": caller or os.environ.get("USERNAME") or os.environ.get("USER"),
        "matrix_products": matrix_products,
        "sims": sims_entry,
        "post": products,
        "stale": shared,
    }
    if apply and shared and matrix_products is None:
        raise StorageError(
            "these matrix products also hold the deleted points: "
            + "; ".join(f"{folder}: {', '.join(names)}" for folder, names in shared.items())
            + ". Say --matrix-products points-only (leave them, marked stale) or "
            "--matrix-products regenerate (rerun their post without the deleted points)."
        )
    if not apply:
        record_storage_call(workspace.root, entry)
        return entry
    stamp = _stamp()
    # THE FOLDERS GO FIRST, links undone before anything is removed: a
    # refusal there leaves the records, the products and the mesh as they were.
    links_undone: dict[str, list[str]] = {}
    for sim in ids:
        folder = workspace.sim_dir(sim)
        if folder.exists():
            links_undone[sim] = _remove_sim_folder(folder)
        archive = _zip_path(workspace, sim)
        if archive.is_file():
            archive.unlink()
    entry["links_undone"] = links_undone
    for folder_rel, item in products.items():
        folder = workspace.root / folder_rel
        for name in item["own"]:
            target = folder / name
            if target.is_file() and not _is_reparse(target):
                target.unlink()
        _forget_products(folder / "products.json", item, run_ids, sims=ids, stamp=stamp)
    with workspace._manifest_lock():
        raw = workspace.read_raw_manifest()
        archive_dir = workspace.root / ARCHIVE_DIR
        archive_dir.mkdir(exist_ok=True)
        if workspace.manifest_path.is_file():
            shutil.copy2(workspace.manifest_path, archive_dir / f"runs-{stamp}.json")
        kept = [row for row in raw if str(row.get("run_id")) not in run_ids]
        index = len(read_storage_calls(workspace.root))
        for item in sims_entry:
            kept.append(
                {
                    "run_id": f"deleted/sim_{item['sim_id']}/{stamp}",
                    DELETED_SIM_KEY: item["sim_id"],
                    "deleted_at": _now().isoformat(),
                    "deleted_run_ids": item["run_ids"],
                    "note": (
                        "this simulation id belonged to a simulation deleted by pyfs-matrix "
                        f"delete-sims; the full entry is call {index} of {STORAGE_FILE}"
                    ),
                    "storage_entry": index,
                }
            )
        workspace._replace_manifest(kept)
    entry["applied"] = True
    entry["runs_archived_as"] = f"{ARCHIVE_DIR}/runs-{stamp}.json"
    if matrix_products == "regenerate" and shared:
        regenerated: list[str | None] = []
        stems = {None if name == "None" else name for item in sims_entry for name in item["matrix"]}
        for folder_rel in shared:
            folder = (workspace.root / folder_rel).resolve()
            matching = [s for s in stems if workspace.products_dir(s).resolve() == folder]
            if not matching:
                entry.setdefault("not_regenerated", []).append(folder_rel)
                continue
            for stage in post_stages():
                stage(workspace, overwrite=True, archive=True, matrix_stem=matching[0])
            regenerated.append(matching[0])
        entry["regenerated"] = regenerated
    record_storage_call(workspace.root, entry)
    return entry


# --------------------------------------------------------------------------- sync


def read_sync_config(root: Path) -> tuple[str, dict[str, Path]]:
    """``inputs/sync-workspaces.toml``: the main name and every workspace's path."""
    path = root / SYNC_CONFIG
    if not path.is_file():
        raise StorageError(
            f'{path} not found: name the workspaces there, main = "<name>" and one '
            '[workspaces.<name>] table with path = "..." per workspace'
        )
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    main, table = document.get("main"), document.get("workspaces")
    if not isinstance(table, dict) or not table:
        raise StorageError(f"{path}: no [workspaces.<name>] table")
    spaces: dict[str, Path] = {}
    for name, item in table.items():
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise StorageError(f'{path}: [workspaces.{name}] needs path = "..."')
        spaces[name] = Path(item["path"]).expanduser()
    if main not in spaces:
        raise StorageError(f"{path}: main = {main!r} is not one of {sorted(spaces)}")
    if spaces[main].resolve() != root.resolve():
        raise StorageError(
            f"{path}: main {main!r} is {spaces[main]}, but the workspace is {root}; sync is run "
            "on the main workspace"
        )
    return str(main), spaces


def read_matrix_owners(root: Path) -> dict[str, str]:
    """Each matrix stem and the ONE workspace that owns it, from ``sync-workspaces.toml``.

    A workspace declares ``matrices = ["matriz", ...]`` in its table. A
    matrix belongs to one workspace and one only; a workspace may own several
    (the owner's rule, 2026-09-28). A stem declared twice is refused, naming
    both workspaces.
    """
    path = root / SYNC_CONFIG
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    owners: dict[str, str] = {}
    for name, item in dict(document.get("workspaces", {})).items():
        declared = item.get("matrices", []) if isinstance(item, dict) else []
        if not isinstance(declared, list) or not all(isinstance(s, str) for s in declared):
            raise StorageError(f'{path}: [workspaces.{name}] matrices = ["<stem>", ...]')
        for stem in declared:
            stem = stem[:-3] if stem.endswith(".fs") else stem
            if stem in owners and owners[stem] != name:
                raise StorageError(
                    f"{path}: matrix {stem!r} is declared by {owners[stem]!r} and by {name!r}; "
                    "a matrix belongs to one workspace only"
                )
            owners[stem] = name
    return owners


def _matrix_files(ws: Path) -> dict[str, Path]:
    """Find a workspace's matrices: ``<root>/<stem>.fs`` or ``inputs/matrices/<stem>.fs``."""
    found: dict[str, Path] = {}
    for folder in (ws, ws / "inputs" / "matrices"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.fs")):
            if not path.is_file() or _is_reparse(path):
                continue
            if path.stem in found:
                raise StorageError(
                    f"{ws}: matrix {path.stem!r} is in two places ({found[path.stem]} and "
                    f"{path.relative_to(ws)}); keep one"
                )
            found[path.stem] = path.relative_to(ws)
    return found


def _sync_matrices(
    main: CampaignWorkspace,
    name: str,
    other: Path,
    owners: dict[str, str],
    *,
    apply: bool,
    stamp: str,
) -> dict[str, Any]:
    """Bring matrices across: every difference is a MERGE CONFLICT, and the owner wins.

    A matrix present on both sides and different is reported as a conflict
    every time; the owning workspace's copy is the one main keeps (main's
    own copy is archived first when the other workspace owns it). A matrix
    only in the other workspace is copied when that workspace owns it.
    """
    mine, theirs = _matrix_files(main.root), _matrix_files(other)
    result: dict[str, Any] = {"conflicts": [], "copied": [], "identical": 0, "not_copied": []}
    for stem in sorted(set(mine) | set(theirs)):
        owner = owners[stem]
        here, there = mine.get(stem), theirs.get(stem)
        if there is None:
            continue
        source = other / there
        if here is not None and _sha256(main.root / here) == _sha256(source):
            result["identical"] += 1
            continue
        if here is not None:
            result["conflicts"].append(
                {
                    "matrix": stem,
                    "main": here.as_posix(),
                    "other": there.as_posix(),
                    "owner": owner,
                    "kept": name if owner == name else "main",
                }
            )
        if owner != name:
            if here is None:
                result["not_copied"].append(
                    {"matrix": stem, "reason": f"owned by {owner!r}, not by {name!r}"}
                )
            continue
        target = main.root / (here if here is not None else there)
        if apply:
            if here is not None:
                keep = main.root / ARCHIVE_DIR / f"sync-{stamp}" / here
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(keep))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if _sha256(target) != _sha256(source):
                raise StorageError(f"the copy of matrix {stem} does not match its source; stopped")
        result["copied"].append(
            {
                "matrix": stem,
                "path": target.relative_to(main.root).as_posix(),
                "sha256": _sha256(source),
                "replaced_main": here is not None,
            }
        )
    return result


def _refuse_undeclared_matrices(
    main_root: Path, others: dict[str, Path], owners: dict[str, str]
) -> None:
    undeclared = []
    for label, root in {"main": main_root, **others}.items():
        if not root.is_dir():
            continue
        for stem, relative in _matrix_files(root).items():
            if stem not in owners:
                undeclared.append(f"{relative.as_posix()} ({label})")
    if undeclared:
        raise StorageError(
            "every matrix must be declared by the ONE workspace it belongs to, in "
            f'{SYNC_CONFIG}: matrices = ["<stem>", ...]; undeclared: ' + ", ".join(undeclared)
        )


def _sync_files(ws: Path, level: str, skip_sims: set[str]) -> list[Path]:
    rank = SYNC_LEVELS.index(level)
    out: set[Path] = set()
    sims = ws / "sims"
    for sim in sorted(sims.glob("sim_*")) if sims.is_dir() else []:
        if _is_reparse(sim) or sim.name[len("sim_") :] in skip_sims:
            continue
        if sim.is_file():
            if rank >= 3 and sim.name.endswith(COMPACTED_SUFFIX):
                out.add(sim)
            continue
        out.update(_walk_files(sim / "scripts"))
        for file in _walk_files(sim / "datapoints"):
            if file.name == "FS_runtime_output.txt" or file.name.endswith("_log.txt"):
                out.add(file)
            elif rank >= 2 and file.suffix.lower() == ".fsm":
                out.add(file)
        if rank >= 3:
            for file in _walk_files(sim):
                parts = file.relative_to(sim).parts
                if parts and parts[0] == "inputs":
                    continue
                out.add(file)
    if rank >= 1:
        out.update(_walk_files(ws / "post"))
    return sorted(path.relative_to(ws) for path in out)


def _merge_runs(
    main_rows: list[dict[str, Any]], other_rows: list[dict[str, Any]], prefer_other: bool
):
    deleted = {
        str(run)
        for row in main_rows
        if row.get(DELETED_SIM_KEY) is not None
        for run in row.get("deleted_run_ids", [])
    }
    index = {row.get("run_id"): i for i, row in enumerate(main_rows)}
    merged = [dict(row) for row in main_rows]
    added: list[str] = []
    replaced: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for row in other_rows:
        run_id = row.get("run_id")
        if not run_id:
            conflicts.append({"run_id": None, "reason": "a record without run_id"})
            continue
        if str(run_id) in deleted:
            conflicts.append({"run_id": run_id, "reason": "deleted in main by delete-sims"})
            continue
        if run_id not in index:
            index[run_id] = len(merged)
            merged.append(row)
            added.append(str(run_id))
            continue
        mine = merged[index[run_id]]
        if mine == row:
            continue
        if mine.get("status") == RunStatus.SUBMITTED.value or prefer_other:
            merged[index[run_id]] = row
            replaced.append(
                {
                    "run_id": run_id,
                    "from": mine.get("status"),
                    "to": row.get("status"),
                    "forced": mine.get("status") != RunStatus.SUBMITTED.value,
                }
            )
        else:
            conflicts.append(
                {
                    "run_id": run_id,
                    "main_status": mine.get("status"),
                    "other_status": row.get("status"),
                }
            )
    return merged, added, replaced, conflicts


def _plan_points_without_record(
    other: Path, rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Per matrix, the points the OTHER workspace planned that no merged record carries.

    0.30.0. Each ``post/<stem>/plan.json`` of the other workspace lists the
    points its plan called for; a point that no record of the merged
    ``runs.json`` carries (:func:`planned_points_without_record`) was never
    attempted there, or its record never reached main. A row of ten planned
    points once recorded six on an HPC workspace and nothing said so; a sync
    is where the two workspaces meet, so it says it here. A plan that cannot
    be read is named with why.
    """
    found: dict[str, dict[str, Any]] = {}
    post = other / "post"
    for plan in sorted(post.glob("*/plan.json")) if post.is_dir() else []:
        stem = plan.parent.name
        try:
            payload = json.loads(plan.read_text(encoding="utf-8"))
            points = payload["points"]
            planned = [str(point["run_id"]) for point in points]
        except (OSError, ValueError, KeyError, TypeError) as error:
            found[stem] = {"error": f"{plan} could not be read: {error}"}
            continue
        found[stem] = {
            "planned": len(planned),
            "without_record": planned_points_without_record(planned, rows),
        }
    return found


def _sync_one(
    main: CampaignWorkspace,
    name: str,
    other: Path,
    level: str,
    *,
    apply: bool,
    prefer_other: bool,
    overwrite: bool,
    owners: dict[str, str],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": "sync",
        "level": level,
        "applied": apply,
        "source_name": name,
        "source": str(other),
        "main": str(main.root),
        "options": {"prefer_other": prefer_other, "overwrite": overwrite},
    }
    if not ((other / "runs.json").exists() or (other / "inputs").is_dir()):
        entry["skipped"] = "not a pyfs-matrix workspace (no runs.json, no inputs/)"
        record_storage_call(main.root, entry)
        return entry
    if (other / "runs.json.lock").exists():
        entry["skipped"] = "runs.json.lock present there: a run is in progress"
        record_storage_call(main.root, entry)
        return entry
    stamp = _stamp()
    other_rows = (
        json.loads((other / "runs.json").read_text(encoding="utf-8"))
        if (other / "runs.json").is_file()
        else []
    )
    if not isinstance(other_rows, list):
        raise StorageError(f"{other / 'runs.json'} is not a list of run records")
    submitted = {
        str(row.get("sim_id"))
        for row in other_rows
        if row.get("status") == RunStatus.SUBMITTED.value
    }
    plan: list[tuple[str, Path]] = []
    file_conflicts: list[str] = []
    identical = 0
    for relative in _sync_files(other, level, submitted):
        source, target = other / relative, main.root / relative
        if not target.exists():
            plan.append(("copy", relative))
        elif _size(source) == _size(target) and _sha256(source) == _sha256(target):
            identical += 1
        elif overwrite:
            plan.append(("overwrite", relative))
        else:
            file_conflicts.append(relative.as_posix())
    copied: list[dict[str, Any]] = []
    overwritten: list[dict[str, Any]] = []
    with main._manifest_lock():
        main_rows = main.read_raw_manifest()
        merged, added, replaced, run_conflicts = _merge_runs(main_rows, other_rows, prefer_other)
        archived_as = None
        if apply and (added or replaced):
            if main.manifest_path.is_file():
                (main.root / ARCHIVE_DIR).mkdir(exist_ok=True)
                archived_as = f"{ARCHIVE_DIR}/runs-{stamp}.json"
                shutil.copy2(main.manifest_path, main.root / archived_as)
            main._replace_manifest(merged)
    if apply:
        for kind, relative in plan:
            source, target = other / relative, main.root / relative
            if kind == "overwrite":
                keep = main.root / ARCHIVE_DIR / f"sync-{stamp}" / relative
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(keep))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            digest = _sha256(target)
            if digest != _sha256(source):
                raise StorageError(f"the copy of {relative} does not match its source; stopped")
            item = {"path": relative.as_posix(), "bytes": _size(target), "sha256": digest}
            (overwritten if kind == "overwrite" else copied).append(item)
    # THE MESH IS LINKED, NEVER COPIED (the owner's rule, 2026-09-28): each
    # simulation folder sync brought gets its `inputs` link into main's own
    # geometry library, the way the other workspace's simulation had it.
    inputs_links: dict[str, str] = {}
    other_sims = other / "sims"
    for sim in sorted(other_sims.glob("sim_*")) if other_sims.is_dir() else []:
        if not sim.is_dir() or _is_reparse(sim):
            continue
        if apply:
            done = _relink_inputs(main, other, sim.name)
            if done:
                inputs_links[sim.name] = done
        elif not (main.root / "sims" / sim.name / "inputs").exists():
            inputs_links[sim.name] = "to link when applied"
    entry["inputs_links"] = inputs_links
    # MATRICES (the owner's rule, 2026-09-28): every difference is reported as
    # a merge conflict, and the workspace that owns the matrix wins.
    entry["matrices"] = _sync_matrices(main, name, other, owners, apply=apply, stamp=stamp)
    # 0.30.0: what the other workspace planned and no merged record carries.
    entry["plan_points_without_record"] = _plan_points_without_record(other, merged)
    entry.update(
        {
            "runs": {
                "added": added,
                "replaced": replaced,
                "conflicts": run_conflicts,
                "submitted_sims_record_only": sorted(submitted),
                "archived_as": archived_as,
                "records_before": len(main_rows),
                "records_after": len(merged),
            },
            "files": {
                "to_copy": sum(kind == "copy" for kind, _ in plan),
                "to_overwrite": sum(kind == "overwrite" for kind, _ in plan),
                "copied": copied,
                "overwritten": overwritten,
                "conflicts": file_conflicts,
                "identical": identical,
                "archived_in": f"{ARCHIVE_DIR}/sync-{stamp}" if overwritten else None,
            },
            "bytes_copied": sum(item["bytes"] for item in copied + overwritten),
        }
    )
    record_storage_call(main.root, entry)
    return entry


def sync_workspaces(
    root: str | Path,
    level: str,
    *,
    source: str | None = None,
    apply: bool = False,
    prefer_other: bool = False,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """Bring runs and results from the other workspaces into the main one.

    ``level`` is cumulative: ``runs`` (runs.json and run provenance: each
    simulation's ``scripts/`` and datapoint logs), ``post`` (+ ``post/``),
    ``fsm`` (+ the datapoints' saved simulations), ``all`` (+ everything else
    under ``sims/``; an ``inputs`` junction is never followed). Nothing in
    main is deleted, and ``inputs/`` is never touched except a declared
    matrix under ``inputs/matrices/``. MATRICES, at every level: each one is
    declared in ``sync-workspaces.toml`` by the ONE workspace that owns it
    (an undeclared matrix refuses the sync); a difference is always reported
    as a merge conflict and the owner's copy is the one main keeps. Returns
    one recorded entry per source workspace.
    """
    if level not in SYNC_LEVELS:
        raise StorageError(f"sync level is one of {', '.join(SYNC_LEVELS)}")
    main = _workspace(root)
    main_name, spaces = read_sync_config(main.root)
    if main.manifest_path.with_name("runs.json.lock").exists():
        raise StorageError(f"{main.root}: runs.json.lock present, a run is in progress here")
    names = [source] if source else [name for name in spaces if name != main_name]
    for name in names:
        if name not in spaces:
            raise StorageError(f"--from {name!r} is not in {SYNC_CONFIG} ({sorted(spaces)})")
        if name == main_name:
            raise StorageError(f"--from {name!r} is the main workspace itself")
    owners = read_matrix_owners(main.root)
    unknown = sorted(set(owners.values()).difference(spaces))
    if unknown:
        raise StorageError(f"{SYNC_CONFIG}: matrices declared by unknown workspaces {unknown}")
    _refuse_undeclared_matrices(main.root, {name: spaces[name].resolve() for name in names}, owners)
    return [
        _sync_one(
            main,
            name,
            spaces[name].resolve(),
            level,
            apply=apply,
            prefer_other=prefer_other,
            overwrite=overwrite,
            owners=owners,
        )
        for name in names
    ]


# --------------------------------------------------------------------------- plan check


def disk_estimate(
    workspace: CampaignWorkspace, pending_points: int, *, margin: float = 0.10
) -> tuple[str, bool]:
    """Say whether ``pending_points`` more points fit on the workspace's disk.

    The estimate is the mean size of a recorded datapoint folder in this
    workspace times the number of points the plan will run; the answer is
    False when that, plus a margin of the disk's free space, exceeds it.
    """
    free = shutil.disk_usage(workspace.root).free
    sizes = []
    sims = workspace.root / "sims"
    for datapoint in sims.glob("sim_*/datapoints/DP-*") if sims.is_dir() else []:
        if datapoint.is_dir() and not _is_reparse(datapoint):
            sizes.append(sum(_size(p) for p in _walk_files(datapoint)))
    if not sizes:
        return (
            f"{pending_points} point(s) to run; {human_bytes(free)} free on the workspace disk; "
            "no recorded point in this workspace to estimate their size from",
            True,
        )
    mean = sum(sizes) / len(sizes)
    need = mean * pending_points
    fits = need <= free * (1.0 - margin)
    line = (
        f"{pending_points} point(s) to run, about {human_bytes(need)} at "
        f"{human_bytes(mean)} per recorded point ({len(sizes)} measured); "
        f"{human_bytes(free)} free on the workspace disk"
    )
    return line, fits
