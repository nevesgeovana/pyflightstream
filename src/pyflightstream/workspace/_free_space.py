"""The recipe runner of ``pyfs-matrix free-space`` and the file helpers it shares with storage.

Pipeline role: the steps of a storage recipe (``inputs/management/m<id>.toml``)
run in order by :func:`pyflightstream.workspace.storage.free_space`, which
reads and checks the recipe, holds the ``runs.json`` lease and records the
call: ``prune_step_exports``, ``compact_sims``, ``delete_extensions`` and
``post_archives``. The file helpers below it (walking a tree without following
a link, the files a recipe never removes) are the ones every storage command
reads, so storage imports them from here. The simulation selection and the
compaction raise the storage command's own refusal and stay in storage; the
runner takes them from its caller.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import zipfile
from collections.abc import Callable, Iterable, Iterator
from importlib import metadata
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
import pyflightstream.workspace._batch_life as batch_life
import pyflightstream.workspace._step_prune as step_prune
from pyflightstream._progress import tracked
from pyflightstream.workspace import CampaignWorkspace, RunStatus, WorkspaceError
from pyflightstream.workspace._links import _is_link, _make_dir_link, is_reparse
from pyflightstream.workspace.naming import ARCHIVE_DIR

COMPACTED_SUFFIX = ".zip"
_PROTECTED_SUFFIXES = (".fsm",)
#: The recipe mode that deletes an unsteady point's per-step exports, all but
#: the last step of each export.
PRUNE_MODE = "prune_step_exports"

#: A step's simulation selection: ``(spec, records, present) -> sim ids``.
_Select = Callable[[dict[str, Any], dict[str, list[dict[str, Any]]], Iterable[str]], list[str]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _version() -> str:
    try:
        return metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        # Same fallback as pyflightstream/__init__.py's own __version__: a
        # source tree imported without an installation has no distribution
        # metadata, so the version is honestly unknown rather than stale.
        return "0.0.0+uninstalled"


def _walk_files(root: Path) -> Iterator[Path]:
    """Every regular file below ``root``, without following a link or junction."""
    if not root.is_dir() or is_reparse(root):
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
            if is_reparse(path):
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


def _zip_path(workspace: CampaignWorkspace, sim_id: str) -> Path:
    folder = workspace.sim_dir(sim_id)
    return folder.with_name(folder.name + COMPACTED_SUFFIX)


def _both_refusal(folder: Path, archive: Path) -> str:
    """Refuse a simulation held both as a folder and as a compacted archive, in words."""
    return (
        f"{folder} and {archive} both exist: the simulation was compacted, and a run or a "
        "sync then wrote a folder beside the archive. Neither is read or changed; merge the "
        "archive's files into the folder (or move one of the two aside), then run again."
    )


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
        # Staged input digests name files beneath inputs/, also after a run moves.
        names += [str(Path("inputs") / name) for name in (row.get("inputs_sha256") or {})]
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
            # A log by the one log-name rule, or a job script (PFS-2087.002).
            or batch_life.is_kept_name(lowered)
        ):
            keep.add(path.resolve())
    return keep


def _sim_folder(sim: str) -> str:
    """Return a simulation's folder as a progress line names it."""
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
    spec: dict[str, Any],
    apply: bool,
    deleted: set[Path],
) -> list[dict[str, Any]]:
    """Delete one simulation's per-step exports the table's ``spec`` selects (preview by default).

    ``spec`` is a ``[[prune_step_exports]]`` table: without ``keep_last`` or
    ``delete_steps`` every step but the last of each export goes.

    Returns one entry per point folder that has a step to delete: the runs it
    belongs to, the steps deleted, every file deleted with its step and size,
    the files kept (the last step of each export unless ``spec`` says otherwise)
    and those a record protects.
    ``deleted`` receives each deleted file's resolved path.
    """
    sim_dir = workspace.sim_dir(sim)
    keep = _protected(workspace, sim, rows)
    points: list[dict[str, Any]] = []
    groups = step_prune.step_export_groups(sim_dir, _walk_files(sim_dir))
    for folder, exports in sorted(groups.items()):
        files: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        protected: list[str] = []
        for _export, by_step in sorted(exports.items()):
            keeping, doomed = step_prune.split_steps(spec, by_step)
            kept += step_prune.kept_entries(by_step, keeping, workspace.root)
            for step in doomed:
                path = by_step[step]
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
        # A manifest of the wrong shape is skipped like an unreadable one: it
        # must not fail after the exports were already unlinked.
        if not isinstance(document, dict) or not isinstance(document.get("products", {}), dict):
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
        _textio.write_text(temporary, json.dumps(document, indent=1) + "\n")
        temporary.replace(manifest)
        changed[manifest.relative_to(workspace.root).as_posix()] = len(gone)
    return changed


def _would_compact(
    workspace: CampaignWorkspace,
    spec: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
    present: list[str],
    *,
    select: _Select,
) -> set[str]:
    """Return the simulations one ``[[compact_sims]]`` step compacts, as its loop decides."""
    return {
        sim
        for sim in select(spec, records, present)
        if not any(row.get("status") == RunStatus.SUBMITTED.value for row in records.get(sim, []))
        and not _zip_path(workspace, sim).exists()
        and _older_than(workspace.sim_dir(sim), spec.get("older_than_days"))
    }


def _check_selections(
    workspace: CampaignWorkspace,
    document: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
    present: list[str],
    *,
    select: _Select,
) -> None:
    """Make every step's selection before any step runs, against what earlier steps leave.

    A ``[[delete_extensions]]`` naming a simulation an earlier ``[[compact_sims]]``
    compacts is refused here, in the preview as in the apply, and before
    anything is changed (PFS-2096.027).
    """
    left = list(present)
    for spec in document.get(PRUNE_MODE, []):
        select(spec, records, left)
    for spec in document.get("compact_sims", []):
        gone = _would_compact(workspace, spec, records, left, select=select)
        left = [sim for sim in left if sim not in gone]
    for spec in document.get("delete_extensions", []):
        select(spec, records, left)


def _run_recipe(
    workspace: CampaignWorkspace,
    document: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
    present: list[str],
    *,
    apply: bool,
    steps: list[dict[str, Any]],
    select: _Select,
    compact: Callable[[CampaignWorkspace, str], dict[str, Any]],
) -> int:
    """Run a checked recipe's steps in order, appending each to ``steps``; return bytes freed.

    ``select`` chooses a step's simulations and ``compact`` compacts one, both
    the caller's (:mod:`pyflightstream.workspace.storage`), which owns their refusals.
    """
    root = workspace.root
    freed = 0
    # PRUNE FIRST, so a recipe that prunes and then compacts prunes
    # folders that are still folders: a compacted simulation is not read here.
    for spec in document.get(PRUNE_MODE, []):
        step: dict[str, Any] = {
            "mode": PRUNE_MODE,
            "points": [],
            "refused": {},
            **step_prune.selection_record(spec),
        }
        steps.append(step)
        deleted: set[Path] = set()
        selected = select(spec, records, present)
        for sim in tracked(f"free-space: {PRUNE_MODE}", selected, label=_sim_folder):
            rows = records.get(sim, [])
            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):
                step["refused"][sim] = "a run is still SUBMITTED; every step is kept"
                continue
            step["points"] += _prune_step_exports(
                workspace, sim, rows, spec=spec, apply=apply, deleted=deleted
            )
        if apply:
            freed += sum(item["bytes"] for point in step["points"] for item in point["files"])
            step["products_json"] = _forget_pruned_listings(workspace, deleted)
    for spec in document.get("compact_sims", []):
        step = {"mode": "compact_sims", "sims": [], "refused": {}}
        steps.append(step)
        selected = select(spec, records, present)
        for sim in tracked("free-space: compact_sims", selected, label=_sim_folder):
            rows = records.get(sim, [])
            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):
                step["refused"][sim] = "a run is still SUBMITTED"
                continue
            folder = workspace.sim_dir(sim)
            if _zip_path(workspace, sim).exists():
                step["refused"][sim] = _both_refusal(folder, _zip_path(workspace, sim))
                continue
            if not _older_than(folder, spec.get("older_than_days")):
                continue
            if apply:
                done = compact(workspace, sim)
                freed += done["bytes_before"] - done["bytes_after"]
                step["sims"].append(done)
            else:
                step["sims"].append(
                    {"sim_id": sim, "bytes": sum(_size(p) for p in _walk_files(folder))}
                )
        # What this step compacted, or would in the preview, is no longer a
        # folder a later step can select: the preview refuses what the apply would.
        compacted = {str(item["sim_id"]) for item in step["sims"]}
        present = [sim for sim in present if sim not in compacted]
    listed: set[Path] = set()  # a file an earlier step lists is not listed again (preview = apply)
    for spec in document.get("delete_extensions", []):
        extensions = [str(e).lower() for e in spec.get("extensions", [])]
        step = {
            "mode": "delete_extensions",
            "extensions": extensions,
            "files": [],
            "kept": [],
            "refused": {},
        }
        steps.append(step)
        selected = select(spec, records, present)
        for sim in tracked("free-space: delete_extensions", selected, label=_sim_folder):
            rows = records.get(sim, [])
            if any(row.get("status") == RunStatus.SUBMITTED.value for row in rows):
                # Recorded as the other two modes record it (PFS-2093.006).
                step["refused"][sim] = "a run is still SUBMITTED; its files are kept"
                continue
            keep = _protected(workspace, sim, rows)
            for file in _walk_files(workspace.sim_dir(sim)):
                if file.suffix.lower() not in extensions:
                    continue
                relative = file.relative_to(workspace.root).as_posix()
                if file.resolve() in listed:
                    continue
                if file.resolve() in keep:
                    step["kept"].append(relative)
                    continue
                size = _size(file)
                listed.add(file.resolve())
                step["files"].append({"path": relative, "bytes": size})
                if apply:
                    file.unlink()
                    freed += size
    for spec in document.get("post_archives", []):
        action = spec.get("action", "delete")
        keep_latest = int(spec.get("keep_latest", 0))
        step = {"mode": "post_archives", "action": action, "archives": []}
        steps.append(step)
        post_root = workspace.root / "post"
        roots = sorted(post_root.rglob(ARCHIVE_DIR)) if post_root.is_dir() else []
        for archive_root in tracked("free-space: post_archives", roots, label=_relative_to(root)):
            # An `archive` folder inside another archive is part of that
            # archive's stamp, handled (or already removed) with it.
            inner = ARCHIVE_DIR in archive_root.relative_to(post_root).parts[:-1]
            if inner or not archive_root.is_dir() or is_reparse(archive_root):
                continue
            stamps = sorted(
                (p for p in archive_root.iterdir() if p.is_dir() and not is_reparse(p)),
                key=lambda p: p.name,
            )
            chosen = stamps[: max(len(stamps) - keep_latest, 0)]
            for stamp_dir in chosen:
                if not _older_than(stamp_dir, spec.get("older_than_days")):
                    continue
                entry, released = _post_archive(stamp_dir, workspace.root, action, apply)
                freed += released
                step["archives"].append(entry)
    return freed


def _post_archive(stamp: Path, root: Path, action: str, apply: bool) -> tuple[dict[str, Any], int]:
    """Preview or remove one post stamp, preserving any existing compacted evidence."""
    size = sum(_size(path) for path in _walk_files(stamp))
    entry: dict[str, Any] = {"path": stamp.relative_to(root).as_posix(), "bytes": size}
    archive = stamp.with_name(stamp.name + COMPACTED_SUFFIX)
    refusal = (
        f"Cannot compact {stamp}: {archive} already exists or is a link. "
        "Move the existing archive aside before compacting this folder."
    )
    if action == "compact" and (archive.exists() or is_reparse(archive)):
        raise WorkspaceError(refusal)
    if not apply:
        return entry, 0
    if action == "compact":
        try:
            handle = archive.open("xb")
        except FileExistsError as error:
            raise WorkspaceError(refusal) from error
        try:
            with handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for folder, dirs, files in os.walk(stamp, followlinks=False):
                    here = Path(folder)
                    dirs[:] = [name for name in dirs if not is_reparse(here / name)]
                    for name in sorted([*dirs, *files]):
                        path = here / name
                        if not is_reparse(path) and (path.is_dir() or path.is_file()):
                            bundle.write(path, path.relative_to(stamp))
        except BaseException:
            archive.unlink(missing_ok=True)
            raise
        entry["archive"] = archive.relative_to(root).as_posix()
        size -= _size(archive)
    shutil.rmtree(stamp)
    return entry, size


def _check_step_values(path: Path, document: dict[str, Any], error: type[Exception]) -> None:
    """Refuse a step's values before any step runs (PFS-2096.027).

    A refusal met in the middle of an applied recipe came after the earlier
    steps had changed files. ``error`` is the storage command's refusal.
    """
    for spec in document.get("delete_extensions", []):
        extensions = [str(e).lower() for e in spec.get("extensions", [])]
        if not extensions or not all(e.startswith(".") for e in extensions):
            raise error(f'{path}: delete_extensions needs extensions = [".vtk", ...]')
        refused_ext = sorted(set(extensions).intersection(_PROTECTED_SUFFIXES))
        if refused_ext:
            raise error(
                f"{path}: {refused_ext} is never deleted by a recipe: the saved simulation "
                "is what a later post or continuation reopens"
            )
    for spec in document.get("post_archives", []):
        if spec.get("action", "delete") not in ("compact", "delete"):
            raise error(f'{path}: post_archives action is "compact" or "delete"')
        keep_latest = spec.get("keep_latest", 0)
        if isinstance(keep_latest, bool) or not isinstance(keep_latest, int) or keep_latest < 0:
            # PFS-2096.017: a negative count chose every archive, the latest included.
            raise error(
                f"{path}: post_archives keep_latest = {keep_latest!r}; write how many of the "
                "newest archives to keep, a whole number 0 or more"
            )


def human_bytes(count: float) -> str:
    """``1536`` -> ``1.5 KB``; binary multiples, one decimal."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(count) < 1024 or unit == "TB":
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} TB"  # pragma: no cover - the loop returns


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
    if not is_reparse(source_inputs):
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


def _library_target(workspace: CampaignWorkspace, recorded: str) -> Path | None:
    """Map a compacted simulation's recorded ``inputs`` link onto THIS workspace's library.

    The record is an absolute path on the machine that compacted it, possibly
    into another workspace's library when the archive came by sync
    (PFS-2096.015). The part after ``inputs/geometries`` names the geometry
    folder, as :func:`_relink_inputs` takes it; None when this library has
    no such folder.
    """
    library = (workspace.inputs_dir / "geometries").resolve()
    parts = Path(recorded).parts
    relative: Path | None = None
    for index in range(len(parts) - 1, 0, -1):
        if (parts[index - 1].lower(), parts[index].lower()) == ("inputs", "geometries"):
            relative = Path(*parts[index + 1 :]) if index + 1 < len(parts) else Path(".")
            break
    if relative is None:
        name = Path(recorded).name
        relative = Path(name) if name and (library / name).is_dir() else None
    if relative is not None:
        wanted = (library / relative).resolve()
        if wanted.is_dir() and (wanted == library or wanted.parent == library):
            return wanted
    # A link outside any geometry library is kept only inside this workspace.
    own = Path(recorded)
    if own.is_dir() and workspace.root.resolve() in own.resolve().parents:
        return own
    return None
