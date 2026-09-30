"""Workspace storage management and synchronisation (0.30.0).

Five commands of ``pyfs-matrix`` live here, and every one of them writes one
entry to ``storage_management.json`` at the workspace root, the provenance of
every storage call ever made in that workspace:

- ``space-in-use`` reports the sizes on disk, by top-level folder, by
  ``sims/sim_*`` and by extension, in that order;
- ``free-space <m<id>>`` runs a recipe from ``inputs/management/m<id>.toml``:
  ``prune_step_exports`` (an unsteady point's per-step exports, all but the
  last step of each), ``compact_sims`` (a simulation folder becomes
  ``sims/sim_<id>.zip``),
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

0.32.0 (package B2). ``sync`` names every ``sims/sim_*`` folder of both sides,
recorded or not, and with ``restore`` (off by default) rebuilds the records of
the folders no record carries through :func:`pyflightstream.run.records.rebuild`;
it copies each file to a temporary name and renames it in place, skips every
folder named ``archive`` unless ``include_archives``, and holds the
``runs.json`` lease for the whole of its merge and copy (RST-6). A matrix is
read from the root or ``inputs/matrices/``, one stem in both homes once when
the bytes are identical and refused naming both when they differ (RST-1).
``sync``, ``free-space`` and ``delete-sims`` take ``runs``, the manifest
:func:`pyflightstream.run.records.resolve_manifest` names.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import tomllib
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pyflightstream._errors import PyflightstreamError
from pyflightstream._progress import stage_progress, tracked
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunStatus,
    WorkspaceError,
    matrix_by_stem,
    matrix_files,
    planned_points_without_record,
    post_stages,
)
from pyflightstream.workspace._links import (
    _is_link,
    _is_reparse,
    _make_dir_link,
    _remove_link,
)
from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP, archive_previous

__all__ = [
    "COMPACTED_SUFFIX",
    "DELETED_SIM_KEY",
    "MANAGEMENT_DIR",
    "MATRIX_PRODUCT_CHOICES",
    "PRUNE_MODE",
    "STEP_EXPORTS_PRUNED",
    "STORAGE_FILE",
    "STORAGE_SCHEMA",
    "SYNC_CONFIG",
    "SYNC_LEVELS",
    "StorageError",
    "delete_sims",
    "disk_estimate",
    "ensure_sim_expanded",
    "free_space",
    "pruned_step_refusal",
    "read_storage_calls",
    "record_storage_call",
    "space_in_use",
    "sync_summary_lines",
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
#: The recipe mode that deletes an unsteady point's per-step exports, all but
#: the last step of each export (0.30.0).
PRUNE_MODE = "prune_step_exports"
_RECIPE_TABLES = (PRUNE_MODE, "compact_sims", "delete_extensions", "post_archives")
#: A per-step export: the solver stamps ``_iteration=<step>`` before the
#: extension of every file an unsteady action exports at a step (RPT-041), the
#: pattern :func:`pyflightstream.post.series.stamped_exports` reads them by.
_STEP_EXPORT = re.compile(r"^(?P<stem>.+)_iteration=(?P<step>\d+)\.(?P<ext>txt|dat|vtk|csv)$")
#: What a post's refusal opens with when a step it needs was deleted by
#: ``prune_step_exports``; the post stage keeps the product a previous post
#: made under that refusal, where it would otherwise retire it.
STEP_EXPORTS_PRUNED = "Refused, per-step exports deleted by free-space: "
#: The suffix of the temporary name a sync copies a file to before renaming it
#: in place (P0320-SYNC-ATOMIC); a file left under it by a killed sync is never
#: brought by another.
_SYNC_TEMPORARY = ".pyfs-sync.tmp"


class StorageError(WorkspaceError):
    """A storage command refused: the message names what and why."""


# --------------------------------------------------------------------------- helpers


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _stamp() -> str:
    return _now().strftime(ARCHIVE_STAMP)


def _version() -> str:
    from importlib import metadata

    try:
        return metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        # Same fallback as pyflightstream/__init__.py's own __version__: a
        # source tree imported without an installation has no distribution
        # metadata, so the version is honestly unknown rather than stale.
        return "0.0.0+uninstalled"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            "root that holds runs.json as workspace (CLI: --workspace)"
        )
    return CampaignWorkspace(root)


def _manifest_of(root: Path, runs: str | None) -> Path:
    """Return the manifest ``runs`` names in ``root``; ``runs.json`` when None.

    Resolved by :func:`pyflightstream.run.records.resolve_manifest`, the one
    rule for a manifest name, which refuses a name that is not a JSON file
    directly in the root. The run row shares this row (ARCHITECTURE section
    3); the import is deferred only because ``run`` imports this module while
    it loads.
    """
    from pyflightstream.run import records as run_records

    return run_records.resolve_manifest(root, runs)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    """Return the rows of a manifest as written; empty when the file does not exist."""
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise StorageError(f"{path} is not a list of run records")
    return rows


def _replace_rows(workspace: CampaignWorkspace, path: Path, rows: list[dict[str, Any]]) -> None:
    """Replace a manifest atomically; ``runs.json`` through the workspace's own writer."""
    if path == workspace.manifest_path:
        workspace._replace_manifest(rows)
        return
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _archive_rows(workspace: CampaignWorkspace, path: Path, stamp: str) -> str:
    """Copy a manifest to ``archive/<stem>-<stamp>.json``; return that path, relative."""
    (workspace.root / ARCHIVE_DIR).mkdir(exist_ok=True)
    archived = f"{ARCHIVE_DIR}/{path.stem}-{stamp}.json"
    shutil.copy2(path, workspace.root / archived)
    return archived


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
        archive_previous(workspace.root, path)
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
    never delete the mesh it was linked to (fixed rule, 2026-09-28).
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


def _records_by_sim(
    workspace: CampaignWorkspace, *manifests: Path
) -> dict[str, list[dict[str, Any]]]:
    """Return the records by simulation id, of ``runs.json`` or of each manifest named."""
    out: dict[str, list[dict[str, Any]]] = {}
    rows = (
        [row for path in manifests for row in _read_rows(path)]
        if manifests
        else workspace.read_raw_manifest()
    )
    for row in rows:
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


def _sim_folder(sim: str) -> str:
    """Return a simulation's folder as a progress line names it (0.32.0)."""
    return f"sims/sim_{sim}"


def _relative_to(root: str | Path):
    """Return the progress label of a path under ``root``: relative where it can be."""

    def label(path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return str(path)

    return label


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


def _step_export_groups(folder: Path) -> dict[Path, dict[tuple[str, str], dict[int, Path]]]:
    """Every per-step export below a simulation folder, by its folder, then export, then step.

    An export is its stem (the ``_cp``, ``_sloads`` or ``_probes`` suffix
    included) and its extension, so the loads, the sectional loads, the probes
    and each surface of one point are separate exports, each with its own last
    step. Nothing under the simulation's ``inputs`` or ``scripts`` is read,
    and no link or junction is followed.
    """
    groups: dict[Path, dict[tuple[str, str], dict[int, Path]]] = {}
    for path in _walk_files(folder):
        if path.relative_to(folder).parts[0] in ("inputs", "scripts"):
            continue
        matched = _STEP_EXPORT.match(path.name)
        if matched is None:
            continue
        export = (matched.group("stem"), matched.group("ext"))
        by_step = groups.setdefault(path.parent, {}).setdefault(export, {})
        by_step[int(matched.group("step"))] = path
    return groups


def _runs_of_folder(sim_dir: Path, rows: list[dict[str, Any]], folder: Path) -> list[str]:
    """Return the runs whose per-step exports a folder holds, as the post looks for them.

    The post reads a point's stamped files in the simulation folder and in the
    folders its declared outputs are in (``post.series.write_point_series``),
    so a datapoint folder belongs to the runs that filed an output there, and
    the simulation folder itself to every run of the simulation.
    """
    wanted = folder.resolve()
    runs = set()
    for row in rows:
        folders = {sim_dir.resolve()}
        folders.update((sim_dir / Path(str(o)).parent).resolve() for o in row.get("outputs") or [])
        if wanted in folders:
            runs.add(str(row.get("run_id")))
    return sorted(runs)


def _prune_step_exports(
    workspace: CampaignWorkspace,
    sim: str,
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    deleted: set[Path],
) -> list[dict[str, Any]]:
    """Delete one simulation's per-step exports but the last step of each (preview by default).

    Returns one entry per point folder that has a step to delete: the runs it
    belongs to, the steps deleted, every file deleted with its step and size,
    the files kept (each export's last step) and those a record protects.
    ``deleted`` receives each deleted file's resolved path.
    """
    sim_dir = workspace.sim_dir(sim)
    keep = _protected(workspace, sim, rows)
    points: list[dict[str, Any]] = []
    for folder, exports in sorted(_step_export_groups(sim_dir).items()):
        files: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        protected: list[str] = []
        for _export, by_step in sorted(exports.items()):
            last = max(by_step)
            relative_last = by_step[last].relative_to(workspace.root).as_posix()
            kept.append({"path": relative_last, "step": last})
            for step, path in sorted(by_step.items()):
                if step == last:
                    continue
                relative = path.relative_to(workspace.root).as_posix()
                if path.resolve() in keep:
                    protected.append(relative)
                    continue
                files.append({"path": relative, "step": step, "bytes": _size(path)})
                if apply:
                    deleted.add(path.resolve())
                    path.unlink()
        if not files and not protected:
            continue
        points.append(
            {
                "folder": folder.relative_to(workspace.root).as_posix(),
                "run_ids": _runs_of_folder(sim_dir, rows, folder),
                "deleted_steps": sorted({int(item["step"]) for item in files}),
                "files": files,
                "kept": kept,
                "protected": protected,
            }
        )
    return points


def _forget_pruned_listings(workspace: CampaignWorkspace, deleted: set[Path]) -> dict[str, int]:
    """Take the deleted per-step files out of every ``products.json`` that lists one.

    The post lists a point's native per-step exports (Tecplot, VTK, CSV) in
    ``products.json`` as the solver wrote them; the manifest never claims a
    file that is not on disk (ARCHITECTURE invariant 3), so those entries
    leave it, and a ``pruned_by_storage`` note names them and says when. The
    products made from those files, and their entries, stay.
    """
    changed: dict[str, int] = {}
    post = workspace.root / "post"
    for manifest in sorted(post.rglob("products.json")) if post.is_dir() and deleted else []:
        if ARCHIVE_DIR in manifest.relative_to(post).parts:
            continue
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        products = dict(document.get("products", {}))
        gone = [name for name in products if (manifest.parent / name).resolve() in deleted]
        if not gone:
            continue
        for name in gone:
            products.pop(name)
        document["products"] = products
        notes = list(document.get("pruned_by_storage", []))
        notes.append({"at": _now().isoformat(), "mode": PRUNE_MODE, "listings_removed": gone})
        document["pruned_by_storage"] = notes
        temporary = manifest.with_name(f"{manifest.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
        temporary.replace(manifest)
        changed[manifest.relative_to(workspace.root).as_posix()] = len(gone)
    return changed


def _pruned_files(root: Path, run_id: str) -> dict[str, tuple[int, str]]:
    """Each per-step file ``prune_step_exports`` deleted for a run: its call and recipe.

    Keyed by the file's resolved path, case-folded where the file system folds
    case. A storage record this package cannot read names nothing.
    """
    try:
        calls = read_storage_calls(root)
    except (StorageError, OSError, ValueError):
        return {}
    found: dict[str, tuple[int, str]] = {}
    for index, call in enumerate(calls):
        if call.get("action") != "free-space" or not call.get("applied"):
            continue
        for step in call.get("steps") or []:
            if not isinstance(step, dict) or step.get("mode") != PRUNE_MODE:
                continue
            for point in step.get("points") or []:
                if run_id not in (point.get("run_ids") or []):
                    continue
                for item in point.get("files") or []:
                    key = os.path.normcase(str((root / str(item["path"])).resolve()))
                    found[key] = (index, str(call.get("recipe")))
    return found


def pruned_step_refusal(
    sim_dir: Path,
    run_id: str,
    expected: Mapping[int, Sequence[Path]],
    *,
    product: str,
    window: tuple[int, int],
) -> str | None:
    """Say why a product that needs a pruned step is refused, or None.

    The post calls this with the steps of a window it did not find and, for
    each, the files it looked for. When ``free-space`` deleted one of them
    (mode ``prune_step_exports``, applied, for this run), the answer names
    the missing steps, the first file and the recorded call, and opens with
    :data:`STEP_EXPORTS_PRUNED`: a product is never written from the steps
    that remain. A step no storage call deleted is left to the caller's own
    rule for a step that was never exported.

    Parameters
    ----------
    sim_dir : Path
        The simulation folder, ``<workspace>/sims/sim_<id>``.
    run_id : str
        The point's run, as its record states it.
    expected : mapping of int to sequence of Path
        Each missing step and the files the product looked for at that step.
    product : str
        The product's name, as the refusal says it.
    window : tuple of int
        The inclusive ``(first_step, last_step)`` the product needs.

    Returns
    -------
    str or None
        The refusal, or None when no missing step was deleted by a storage call.
    """
    root = sim_dir.parent.parent
    if not expected or not (root / STORAGE_FILE).is_file():
        return None
    pruned = _pruned_files(root, run_id)
    hits: dict[int, tuple[Path, tuple[int, str]]] = {}
    for step, paths in sorted(expected.items()):
        for path in paths:
            found = pruned.get(os.path.normcase(str(path.resolve())))
            if found is not None:
                hits[step] = (path, found)
                break
    if not hits:
        return None
    steps = sorted(hits)
    shown = ", ".join(str(step) for step in steps[:8])
    if len(steps) > 8:
        shown += f", ..., {steps[-1]} ({len(steps)} steps)"
    path, (index, recipe) = hits[steps[0]]
    return (
        f"{STEP_EXPORTS_PRUNED}{product} needs step(s) {shown} of the window {window[0]} to "
        f"{window[1]}, and their per-step exports ({path.name} the first) were deleted by "
        f"free-space {recipe} ({PRUNE_MODE}, call {index} of {STORAGE_FILE}), which kept "
        "the last step of each export only. The product is not written from the steps that "
        "remain; a product made before that call stays as it was."
    )


def free_space(
    root: str | Path, recipe: str, *, apply: bool = False, runs: str | None = None
) -> dict[str, Any]:
    """Run a storage recipe: preview by default, change files only with ``apply``.

    ``runs`` names another manifest in the root (CLI: ``--runs NAME``), such
    as a rebuilt one, whose records the recipe reads IN ADDITION to
    ``runs.json``'s: a file either names is protected, and a simulation
    SUBMITTED in either is left alone, so naming a manifest never protects
    less than the default (P0320-RUNS-NAME). Returns the entry recorded in
    ``storage_management.json``.
    """
    workspace = _workspace(root)
    manifest = _manifest_of(workspace.root, runs)
    if workspace.manifest_path.with_name("runs.json.lock").exists():
        raise StorageError(f"{workspace.root}: runs.json.lock present, a run is in progress")
    path, document = read_recipe(workspace.root, recipe)
    records = _records_by_sim(workspace, *dict.fromkeys((workspace.manifest_path, manifest)))
    sims_root = workspace.root / "sims"
    present = [
        p.name[len("sim_") :]
        for p in (sims_root.iterdir() if sims_root.is_dir() else [])
        if p.is_dir() and p.name.startswith("sim_") and not _is_reparse(p)
    ]
    steps: list[dict[str, Any]] = []
    freed = 0
    # PRUNE FIRST (0.30.0), so a recipe that prunes and then compacts prunes
    # folders that are still folders: a compacted simulation is not read here.
    for spec in document.get(PRUNE_MODE, []):
        step: dict[str, Any] = {"mode": PRUNE_MODE, "points": [], "refused": {}}
        deleted: set[Path] = set()
        selected = _select_sims(spec, records, present)
        for sim in tracked(f"free-space: {PRUNE_MODE}", selected, label=_sim_folder):
            rows = records.get(sim, [])
            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):
                step["refused"][sim] = "a run is still SUBMITTED; every step is kept"
                continue
            step["points"] += _prune_step_exports(
                workspace, sim, rows, apply=apply, deleted=deleted
            )
        if apply:
            freed += sum(item["bytes"] for point in step["points"] for item in point["files"])
            step["products_json"] = _forget_pruned_listings(workspace, deleted)
        steps.append(step)
    for spec in document.get("compact_sims", []):
        step = {"mode": "compact_sims", "sims": [], "refused": {}}
        selected = _select_sims(spec, records, present)
        for sim in tracked("free-space: compact_sims", selected, label=_sim_folder):
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
        selected = _select_sims(spec, records, present)
        for sim in tracked("free-space: delete_extensions", selected, label=_sim_folder):
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
        for archive_root in tracked("free-space: post_archives", roots, label=_relative_to(root)):
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
    runs: str | None = None,
) -> dict[str, Any]:
    """Delete simulations, their post products and their records.

    Preview by default. With ``apply``, ``matrix_products`` must say what
    happens to a product that mixes the deleted simulation with others:
    ``points-only`` leaves it (marked stale), ``regenerate`` reruns the post
    of that matrix without the deleted points. The records leave
    ``runs.json`` (archived first); one note row per simulation stays there,
    and the full mention is the returned entry, recorded in
    ``storage_management.json``.

    ``runs`` names another manifest in the root (CLI: ``--runs NAME``): the
    records are read from it and leave it, archived first as
    ``archive/<stem>-<stamp>.json``, and ``runs.json`` is not touched
    (P0320-RUNS-NAME). ``regenerate`` is refused with it, because the post it
    reruns reads ``runs.json``.
    """
    workspace = _workspace(root)
    manifest = _manifest_of(workspace.root, runs)
    if matrix_products is not None and matrix_products not in MATRIX_PRODUCT_CHOICES:
        raise StorageError(
            "matrix_products (CLI: --matrix-products) is one of "
            f"{', '.join(MATRIX_PRODUCT_CHOICES)}"
        )
    if matrix_products == "regenerate" and manifest != workspace.manifest_path:
        raise StorageError(
            f"matrix_products (CLI: --matrix-products) 'regenerate' is refused with runs "
            f"(CLI: --runs) {manifest.name}: the post it reruns reads runs.json. Delete with "
            "'points-only', then post that manifest (pyfs-matrix post --runs)."
        )
    if workspace.manifest_path.with_name("runs.json.lock").exists():
        raise StorageError(f"{workspace.root}: runs.json.lock present, a run is in progress")
    ids = [str(sim).strip() for sim in sim_ids if str(sim).strip()]
    if not ids:
        raise StorageError("name at least one simulation id")
    records = _records_by_sim(workspace, manifest)
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
    measured: dict[str, int] = {}
    for sim in tracked("delete-sims: measure", ids, label=_sim_folder):
        folder, archive = workspace.sim_dir(sim), _zip_path(workspace, sim)
        rows = records.get(sim, [])
        measured[sim] = sum(_size(p) for p in _walk_files(folder)) + _size(archive)
        sims_entry.append(
            {
                "sim_id": sim,
                "run_ids": sorted(str(row.get("run_id")) for row in rows),
                "matrix": sorted({str(row.get("matrix_stem")) for row in rows}),
                "statuses": sorted({str(row.get("status")) for row in rows}),
                "dates": sorted(
                    {str(row.get("started_at") or row.get("ended_at")) for row in rows}
                ),
                "bytes": measured[sim],
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
        "manifest": manifest.name,
        "sims": sims_entry,
        "post": products,
        "stale": shared,
    }
    if apply and shared and matrix_products is None:
        raise StorageError(
            "these matrix products also hold the deleted points: "
            + "; ".join(f"{folder}: {', '.join(names)}" for folder, names in shared.items())
            + ". Say matrix_products (CLI: --matrix-products) 'points-only' (leave them, "
            "marked stale) or 'regenerate' (rerun their post without the deleted points)."
        )
    if not apply:
        record_storage_call(workspace.root, entry)
        return entry
    stamp = _stamp()
    # THE FOLDERS GO FIRST, links undone before anything is removed: a
    # refusal there leaves the records, the products and the mesh as they were.
    links_undone: dict[str, list[str]] = {}
    for sim in tracked("delete-sims: remove", ids, label=_sim_folder, size=measured.__getitem__):
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
    archived_as = f"{ARCHIVE_DIR}/{manifest.stem}-{stamp}.json"
    with workspace._manifest_lock():
        raw = _read_rows(manifest)
        (workspace.root / ARCHIVE_DIR).mkdir(exist_ok=True)
        if manifest.is_file():
            _archive_rows(workspace, manifest, stamp)
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
        _replace_rows(workspace, manifest, kept)
    entry["applied"] = True
    entry["runs_archived_as"] = archived_as
    if matrix_products == "regenerate" and shared:
        regenerated: list[str | None] = []
        stems = {
            None if name == "None" else name
            for item in sims_entry
            for name in cast(list[str], item["matrix"])
        }
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
    (fixed rule, 2026-09-28). A stem declared twice is refused, naming
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
    """Return a workspace's matrices, one per stem, from the root or ``inputs/matrices/``.

    0.32.0 (P0320-MATRICES-HOME, RST-1): the two homes are equal, so a stem
    held in both is read once when the two files hold the same bytes, and
    refused, naming both paths, when they differ (:func:`matrix_by_stem`).
    """
    try:
        found = matrix_by_stem(ws)
    except WorkspaceError as error:
        raise StorageError(str(error)) from error
    return {stem: path.relative_to(ws) for stem, path in found.items()}


def _atomic_copy(source: Path, target: Path, *, keep: Path | None = None) -> str:
    """Copy ``source`` over ``target`` through a temporary name; return the digest.

    P0320-SYNC-ATOMIC. The bytes go to a temporary file in the target's own
    folder, are checked against the source, and only then take the target's
    name in one rename, so an interrupted copy never leaves a partial file
    under the target's name, and an overwritten file stays in place until
    its replacement is whole. ``keep``, when given and the target exists,
    receives a copy of the target first (the sync's ``archive/sync-<stamp>/``).
    A failure removes the temporary file and leaves the target as it was.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}{_SYNC_TEMPORARY}")
    try:
        shutil.copy2(source, temporary)
        digest = _sha256(temporary)
        if digest != _sha256(source):
            raise StorageError(
                f"the copy of {source} does not match its source; stopped, {target} unchanged"
            )
        if keep is not None and target.exists():
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, keep)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return digest


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
    only in the other workspace is copied when that workspace owns it. Main
    may hold one stem in both homes with the same bytes (RST-1); the owning
    workspace's copy then replaces both, so the two stay one.
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
        copies = [path for path in matrix_files(main.root) if path.stem == stem] or [target]
        if apply:
            for copy in copies:
                keep = main.root / ARCHIVE_DIR / f"sync-{stamp}" / copy.relative_to(main.root)
                _atomic_copy(source, copy, keep=keep)
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


def _sync_files(
    ws: Path, level: str, skip_sims: set[str], *, include_archives: bool = False
) -> tuple[list[Path], list[Path]]:
    """Return the files a sync of ``level`` brings from ``ws``, and the archive files skipped.

    P0320-SYNC-SKIP-ARCHIVES: a file under any folder named ``archive`` (the
    ``post/<matrix>/**/archive/<stamp>/`` a post leaves, an ``archive/`` inside
    a simulation) is set apart unless ``include_archives``. A file a killed
    sync left under its temporary name is never brought.
    """
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
    brought: list[Path] = []
    archived: list[Path] = []
    for relative in sorted(path.relative_to(ws) for path in out):
        if relative.name.endswith(_SYNC_TEMPORARY):
            continue
        if not include_archives and ARCHIVE_DIR in relative.parts[:-1]:
            archived.append(relative)
        else:
            brought.append(relative)
    return brought, archived


def _sim_ids(ws: Path) -> set[str]:
    """Every simulation id with a folder, or a compacted zip, under ``ws/sims/``."""
    found: set[str] = set()
    sims = ws / "sims"
    for path in sims.glob("sim_*") if sims.is_dir() else []:
        if _is_reparse(path):
            continue
        if path.is_dir():
            found.add(path.name[len("sim_") :])
        elif path.is_file() and path.name.endswith(COMPACTED_SUFFIX):
            found.add(path.name[len("sim_") : -len(COMPACTED_SUFFIX)])
    return found


def _brought_sim_ids(files: list[Path]) -> set[str]:
    """Return the simulation ids with a file among ``files``, the paths a sync brings."""
    found: set[str] = set()
    for relative in files:
        parts = relative.parts
        if len(parts) < 2 or parts[0] != "sims" or not parts[1].startswith("sim_"):
            continue
        name = parts[1]
        if len(parts) == 2 and name.endswith(COMPACTED_SUFFIX):
            name = name[: -len(COMPACTED_SUFFIX)]
        found.add(name[len("sim_") :])
    return found


def _sim_folders(
    main_ids: set[str], other_ids: set[str], brought: set[str], rows: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """P0320-SYNC-ALL-FOLDERS: the simulation folders of both sides, compared.

    ``without_record`` names every folder main holds, or holds once the sync is
    applied (``brought``: the other's simulations with a file the level
    copies), that no record of the merged manifest carries; a folder a
    ``delete-sims`` note names is accounted for by that note and left out. A
    simulation of the other workspace the level does not bring (a compacted
    one below ``all``, a folder holding nothing the level copies) is in
    ``other`` and never in ``without_record``, because the restore rebuilds in
    main.
    """
    recorded = {
        str(row.get("sim_id"))
        for row in rows
        if row.get(DELETED_SIM_KEY) is None and row.get("sim_id") is not None
    }
    noted = {str(row.get(DELETED_SIM_KEY)) for row in rows if row.get(DELETED_SIM_KEY) is not None}
    return {
        "main": sorted(main_ids),
        "other": sorted(other_ids),
        "only_main": sorted(main_ids - other_ids),
        "only_other": sorted(other_ids - main_ids),
        "both": sorted(main_ids & other_ids),
        "without_record": sorted((main_ids | (other_ids & brought)) - recorded - noted),
    }


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


def sync_summary_lines(entry: Mapping[str, Any]) -> list[str]:
    """Return the lines ``pyfs-matrix sync`` prints for what 0.32.0 added to an entry.

    The archive files and bytes skipped (P0320-SYNC-SKIP-ARCHIVES), the
    simulation folders of both sides and those no record carries
    (P0320-SYNC-ALL-FOLDERS), and what the restore did or would do
    (P0320-SYNC-RESTORE-OPTIN). An entry written before 0.32.0 gives none.
    """
    lines: list[str] = []
    skipped = entry.get("files", {}).get("archives_skipped")
    if skipped and skipped["files"]:
        lines.append(
            f"  archive: {skipped['files']} file(s), {human_bytes(skipped['bytes'])} skipped "
            "(--include-archives brings them)"
        )
    sims = entry.get("sims")
    if not sims:
        return lines
    lines.append(
        f"  sims/: {len(sims['main'])} in main, {len(sims['other'])} in other, "
        f"{len(sims['both'])} in both"
    )
    orphans = sims["without_record"]
    if not orphans:
        return lines
    lines.append(f"    without a record: {', '.join(orphans)}")
    restore = entry.get("restore") or {}
    if not restore.get("asked"):
        lines.append("    run again with --restore --apply to rebuild their records")
    elif restore.get("error"):
        lines.append(f"    restore refused: {restore['error']}")
    elif restore.get("result") is None:
        lines.append("    their records are rebuilt when applied (--restore --apply)")
    else:
        result = restore["result"]
        rebuilt, refused = result.get("rebuilt") or [], result.get("refused") or {}
        lines.append(
            f"    restore: {len(rebuilt)} record(s) rebuilt, {len(refused)} sim(s) refused"
        )
        for sim, why in dict(refused).items():
            lines.append(f"      refused sim {sim}: {why}")
    return lines


def _restore_orphans(root: Path, sims: list[str]) -> dict[str, Any]:
    """Rebuild the records of ``sims`` through :func:`pyflightstream.run.records.rebuild`.

    P0320-SYNC-RESTORE-OPTIN. Called by an applying sync that was asked to
    restore, AFTER it released the ``runs.json`` lease, which the rebuild takes
    itself. The rebuild appends the records whose run ids ``runs.json`` does
    not hold (the B1 contract). A refusal is the entry's ``error``, not the
    sync's: the files it copied stand. The rebuilt records themselves are in
    ``runs.json`` and are not repeated in the storage record.
    """
    from pyflightstream.run import records as run_records

    outcome: dict[str, Any] = {"asked": True, "sims": sims, "result": None, "error": None}
    try:
        result = run_records.rebuild(root, sims=sims, apply=True)
    except (PyflightstreamError, OSError) as error:
        outcome["error"] = str(error)
        return outcome
    kept = {key: value for key, value in result.items() if key != "records"}
    outcome["result"] = json.loads(json.dumps(kept, default=str))
    return outcome


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
    manifest: Path,
    restore: bool,
    include_archives: bool,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": "sync",
        "level": level,
        "applied": apply,
        "source_name": name,
        "source": str(other),
        "main": str(main.root),
        "options": {
            "prefer_other": prefer_other,
            "overwrite": overwrite,
            "restore": restore,
            "include_archives": include_archives,
            "runs": manifest.name,
        },
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
    # THE OTHER WORKSPACE'S OWN MANIFEST is the source: `runs` names the
    # manifest of main the records merge into (P0320-RUNS-NAME).
    other_rows = _read_rows(other / "runs.json")
    submitted = {
        str(row.get("sim_id"))
        for row in other_rows
        if row.get("status") == RunStatus.SUBMITTED.value
    }
    files, archived = _sync_files(other, level, submitted, include_archives=include_archives)
    plan: list[tuple[str, Path]] = []
    file_conflicts: list[str] = []
    identical = 0
    with stage_progress("sync hash", total_files=len(files)) as progress:
        for relative in files:
            source, target = other / relative, main.root / relative
            if not target.exists():
                plan.append(("copy", relative))
            elif _size(source) == _size(target) and _sha256(source) == _sha256(target):
                identical += 1
            elif overwrite:
                plan.append(("overwrite", relative))
            else:
                file_conflicts.append(relative.as_posix())
            progress.advance(files=1, bytes=_size(source), current=relative.as_posix())
    main_ids, other_ids = _sim_ids(main.root), _sim_ids(other)
    copied: list[dict[str, Any]] = []
    overwritten: list[dict[str, Any]] = []
    inputs_links: dict[str, str] = {}
    # RST-6: THE LEASE ON runs.json IS HELD FOR THE WHOLE OF THE MERGE AND THE
    # COPY, so a restore (which refuses while runs.json.lock is present), a
    # run, a collect or a second sync never writes into the workspace while
    # this one does. It was held around the merge only.
    with main._manifest_lock():
        with stage_progress("sync merge", total_files=len(other_rows)) as progress:
            main_rows = _read_rows(manifest)
            merged, added, replaced, run_conflicts = _merge_runs(
                main_rows, other_rows, prefer_other
            )
            archived_as = None
            if apply and (added or replaced):
                if manifest.is_file():
                    archived_as = _archive_rows(main, manifest, stamp)
                _replace_rows(main, manifest, merged)
            progress.advance(files=len(other_rows))
        total = sum(_size(other / relative) for _, relative in plan)
        with stage_progress("sync copy", total_files=len(plan), total_bytes=total) as progress:
            for kind, relative in plan if apply else []:
                source, target = other / relative, main.root / relative
                keep = None
                if kind == "overwrite":
                    keep = main.root / ARCHIVE_DIR / f"sync-{stamp}" / relative
                digest = _atomic_copy(source, target, keep=keep)
                size = _size(target)
                item = {"path": relative.as_posix(), "bytes": size, "sha256": digest}
                (overwritten if kind == "overwrite" else copied).append(item)
                progress.advance(files=1, bytes=size, current=relative.as_posix())
        # THE MESH IS LINKED, NEVER COPIED (fixed rule, 2026-09-28): each
        # simulation folder sync brought gets its `inputs` link into main's own
        # geometry library, the way the other workspace's simulation had it.
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
        # MATRICES (fixed rule, 2026-09-28): every difference is reported as
        # a merge conflict, and the workspace that owns the matrix wins.
        entry["matrices"] = _sync_matrices(main, name, other, owners, apply=apply, stamp=stamp)
    entry["inputs_links"] = inputs_links
    # P0320-SYNC-ALL-FOLDERS: every simulation folder of both sides, recorded
    # or not; P0320-SYNC-RESTORE-OPTIN: their records rebuilt only when asked.
    entry["sims"] = _sim_folders(main_ids, other_ids, _brought_sim_ids(files), merged)
    orphans = entry["sims"]["without_record"]
    entry["restore"] = {"asked": restore, "sims": [], "result": None, "error": None}
    if restore:
        entry["restore"]["sims"] = orphans
        if apply and orphans:
            entry["restore"] = _restore_orphans(main.root, orphans)
    # 0.30.0: what the other workspace planned and no merged record carries.
    entry["plan_points_without_record"] = _plan_points_without_record(other, merged)
    entry.update(
        {
            "runs": {
                "manifest": manifest.name,
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
                "archives_skipped": {
                    "files": len(archived),
                    "bytes": sum(_size(other / relative) for relative in archived),
                },
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
    restore: bool = False,
    include_archives: bool = False,
    runs: str | None = None,
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
    as a merge conflict and the owning workspace's copy is the one main
    keeps. Returns one recorded entry per source workspace.

    0.32.0. Every ``sims/sim_*`` folder of both sides is compared, recorded or
    not, and each entry's ``sims`` names the folders no record carries.
    ``restore`` (CLI: ``--restore``), off by default, rebuilds their records
    through :func:`pyflightstream.run.records.rebuild` once an applying sync
    has released the ``runs.json`` lease it holds for the whole of its merge
    and copy. Every file is copied to a temporary name and renamed in place.
    A folder named ``archive`` is skipped unless ``include_archives`` (CLI:
    ``--include-archives``), and ``files.archives_skipped`` counts what was.
    ``runs`` (CLI: ``--runs NAME``) names the manifest of main the records
    merge into; the other workspace's ``runs.json`` is the source.

    Raises
    ------
    RunsManifestError
        ``runs`` is not a JSON file directly in the root.
    StorageError
        An unknown level or source; ``runs.json.lock`` present in main (a run,
        a collect, a restore or another sync is writing); ``restore`` with a
        manifest other than ``runs.json``; a matrix no workspace declares, or
        one stem held in both homes of a workspace with different bytes.
    """
    if level not in SYNC_LEVELS:
        raise StorageError(f"sync level is one of {', '.join(SYNC_LEVELS)}")
    main = _workspace(root)
    manifest = _manifest_of(main.root, runs)
    if restore and manifest != main.manifest_path:
        raise StorageError(
            f"restore (CLI: --restore) rebuilds records into runs.json only; with runs (CLI: "
            f"--runs) {manifest.name} it is refused. Rebuild into another manifest with "
            "pyflightstream.run.records.rebuild and its out (CLI: --out) (the command "
            "pyfs-matrix rebuild)."
        )
    main_name, spaces = read_sync_config(main.root)
    if main.manifest_path.with_name("runs.json.lock").exists():
        raise StorageError(
            f"{main.root}: runs.json.lock present, a run, a collect, a restore or another sync "
            "is writing here; the sync is refused until it ends"
        )
    names = [source] if source else [name for name in spaces if name != main_name]
    for name in names:
        if name not in spaces:
            raise StorageError(
                f"from (CLI: --from) {name!r} is not in {SYNC_CONFIG} ({sorted(spaces)})"
            )
        if name == main_name:
            raise StorageError(f"from (CLI: --from) {name!r} is the main workspace itself")
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
            manifest=manifest,
            restore=restore,
            include_archives=include_archives,
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
