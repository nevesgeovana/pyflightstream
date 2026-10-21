"""Workspace storage management and synchronisation.

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

package B2: ``sync`` names every ``sims/sim_*`` folder of both sides,
recorded or not, and with ``restore`` (off by default) rebuilds the records of
the folders no record carries through :func:`pyflightstream.run.records.rebuild`,
which the run layer registers here (:func:`register_records_rebuild`);
it copies each file to a temporary name and renames it in place, skips every
folder named ``archive`` unless ``include_archives``, and holds the
``runs.json`` lease for the whole of its merge and copy (RST-6). A matrix is
read from the root or ``inputs/matrices/``, one stem in both homes once when
the bytes are identical and refused naming both when they differ (RST-1).
``sync``, ``free-space`` and ``delete-sims`` take ``runs``, the manifest
:func:`pyflightstream.workspace.naming.resolve_manifest` names (the
function :mod:`pyflightstream.run.records` re-exports).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import time
import tomllib
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pyflightstream._textio as _textio
import pyflightstream.workspace._batch_life as batch_life
import pyflightstream.workspace._step_prune as step_prune
from pyflightstream._errors import PyflightstreamWarning, warn
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
from pyflightstream.workspace._free_space import (
    _PROTECTED_SUFFIXES,
    _both_refusal,
    _check_selections,
    _check_step_values,
    _library_target,
    _now,
    _relink_inputs,
    _run_recipe,
    _sha256,
    _sim_folder,
    _size,
    _version,
    _walk_files,
    _zip_path,
)
from pyflightstream.workspace._free_space import COMPACTED_SUFFIX as COMPACTED_SUFFIX
from pyflightstream.workspace._free_space import PRUNE_MODE as PRUNE_MODE
from pyflightstream.workspace._free_space import human_bytes as human_bytes
from pyflightstream.workspace._links import _is_link, _make_dir_link, _remove_link, is_reparse
from pyflightstream.workspace._verdicts import DELETED_SIM_KEY as DELETED_SIM_KEY
from pyflightstream.workspace._verdicts import merge_runs as _merge_runs
from pyflightstream.workspace.manifest import (
    MANIFEST_LOCK_POLL_S,
    MANIFEST_LOCK_RENEW_S,
    MANIFEST_LOCK_STALE_S,
    manifest_lock,
)
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR,
    ARCHIVE_STAMP,
    archive_previous,
    free_root_archive,
    resolve_manifest,
)

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
    "kept_phrase",
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
_COMPACT_META = "_pyfs_compacted.json"
_RECIPE_TABLES = (PRUNE_MODE, "compact_sims", "delete_extensions", "post_archives")
#: What a post's refusal opens with when a step it needs was deleted by
#: ``prune_step_exports``; the post stage keeps the product a previous post
#: made under that refusal, where it would otherwise retire it.
STEP_EXPORTS_PRUNED = "Refused, per-step exports deleted by free-space: "
#: What a recorded ``prune_step_exports`` step kept, in words (FR-416).
kept_phrase = step_prune.kept_phrase
#: The suffix of the temporary name a sync copies a file to before renaming it
#: in place (P0320-SYNC-ATOMIC); a file left under it by a killed sync is never
#: brought by another.
_SYNC_TEMPORARY = ".pyfs-sync.tmp"


class StorageError(WorkspaceError):
    """A storage command refused: the message names what and why."""


# --------------------------------------------------------------------------- helpers


def _stamp() -> str:
    # THE PACKAGE'S ONE ARCHIVE CLOCK, local time (PFS-2096.026): every other
    # writer of archive/<stem>-<stamp>.json stamps its copy in local time, and
    # restore takes the newest by stamp, so a UTC stamp here sorted a storage
    # copy hours away from the copies made beside it.
    return _dt.datetime.now().strftime(ARCHIVE_STAMP)


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


def _read_rows(path: Path) -> list[dict[str, Any]]:
    """Return the rows of a manifest as written; empty when the file does not exist."""
    from pyflightstream.workspace.record_document import read_rows

    if path.name != "additional.json":
        return read_rows(path)
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise StorageError(f"{path} is not a list of run records")
    return rows


def _replace_rows(workspace: CampaignWorkspace, path: Path, rows: list[dict[str, Any]]) -> None:
    """Replace a manifest atomically; ``runs.json`` through the workspace's own writer."""
    from pyflightstream.workspace.record_document import encode_rows

    if path == workspace.manifest_path:
        workspace._replace_manifest(rows)
        return
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    document = rows if path.name == "additional.json" else encode_rows(rows)
    _textio.write_text(temporary, json.dumps(document, indent=2) + "\n")
    temporary.replace(path)


#: How long a storage command waits for the ``runs.json`` lease before it says a
#: run is in progress: long enough for the lease's brief arbitration, never for a run.
_LEASE_WAIT_S = 1.0


@contextmanager
def _runs_lease(workspace: CampaignWorkspace, refusal: str) -> Iterator[None]:
    """Hold the ``runs.json`` lease, refusing with ``refusal`` while a live writer holds it.

    The lease's own rules decide whether a ``runs.json.lock`` is held
    (PFS-2094.047): a lock left by a process that died on this host, or one
    whose heartbeat stopped for :data:`MANIFEST_LOCK_STALE_S`, is recovered,
    so a killed run does not stop every storage command for good; and the
    command holds the lease while it changes files, so no run or collect
    starts writing beside it.
    """
    stack = ExitStack()
    try:
        stack.enter_context(
            manifest_lock(
                workspace.manifest_path,
                root=workspace.root,
                timeout_s=_LEASE_WAIT_S,
                renew_s=MANIFEST_LOCK_RENEW_S,
                stale_s=MANIFEST_LOCK_STALE_S,
                poll_s=MANIFEST_LOCK_POLL_S,
            )
        )
    except WorkspaceError as error:
        raise StorageError(refusal) from error
    with stack:
        yield


def _lease_live_in(root: Path) -> bool:
    """Whether another workspace's ``runs.json.lock`` is a live lease, read without writing there.

    The lease renews its lock's time stamp every few seconds, so a lock no
    heartbeat touched for :data:`MANIFEST_LOCK_STALE_S` is left by a process
    that ended, not a run in progress (PFS-2094.047).
    """
    lock = root / "runs.json.lock"
    try:
        return time.time() - lock.stat().st_mtime <= MANIFEST_LOCK_STALE_S
    except OSError:
        return False


def _archive_manifest(workspace: CampaignWorkspace, path: Path, stamp: str) -> str:
    """Copy a manifest to its free ``archive/<stem>-<stamp>.json``; return that path, relative.

    Through :func:`free_root_archive`, the one spelling ``restore`` reads, so a
    second copy within one stamp is numbered and never overwrites the first
    (PFS-2096.026). A copy that fails raises: the rows are not rewritten
    without it.
    """
    kept = free_root_archive(workspace.root, path.name, stamp)
    kept.parent.mkdir(exist_ok=True)
    shutil.copy2(path, kept)
    return kept.relative_to(workspace.root).as_posix()


# --------------------------------------------------------------------------- the record


def read_storage_calls(root: str | Path) -> list[dict[str, Any]]:
    """Every call recorded in ``storage_management.json``, oldest first.

    Parameters
    ----------
    root : str or Path
        The workspace root.

    Returns
    -------
    list of dict
        The recorded calls, oldest first; empty when the file does not exist.

    Raises
    ------
    StorageError
        If the file is not a storage record.
    """
    path = Path(root) / STORAGE_FILE
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema") != STORAGE_SCHEMA
        or not isinstance(document.get("calls"), list)
        or not all(isinstance(call, dict) for call in document["calls"])
    ):
        raise StorageError(
            f"{path} is not a {STORAGE_SCHEMA} file; it is left untouched. Move it aside to "
            "start a new storage record."
        )
    return list(document["calls"])


def record_storage_call(root: str | Path, entry: dict[str, Any]) -> int:
    """Append one call to ``storage_management.json``; return its index.

    The write is atomic and serialised by the workspace's own manifest lock on
    the storage file, so two commands cannot interleave their entries.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    entry : dict of str to object
        The call's entry.

    Returns
    -------
    int
        The entry's index in the file.
    """
    workspace = _workspace(root)
    path = workspace.root / STORAGE_FILE
    full = {"at": _now().isoformat(), "tool": TOOL, "tool_version": _version(), **entry}
    with workspace._manifest_lock(path):
        calls = read_storage_calls(workspace.root)
        calls.append(full)
        archive_previous(workspace.root, path)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        _textio.write_text(
            temporary,
            json.dumps({"schema": STORAGE_SCHEMA, "calls": calls}, indent=1, ensure_ascii=False)
            + "\n",
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
    """Measure the workspace and record the call (the report changes no file).

    Parameters
    ----------
    root : str or Path
        The workspace root.

    Returns
    -------
    SpaceReport
        The space each part of the workspace uses.
    """
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
    never delete the mesh it was linked to.
    Returns the links undone, relative to the folder.
    """
    undone: list[str] = []
    stack = [folder]
    while stack:
        current = stack.pop()
        for entry in list(os.scandir(current)):
            path = Path(entry.path)
            if is_reparse(path):
                if _is_link(path) or path.is_dir():
                    _remove_link(path)
                else:
                    path.unlink()
                undone.append(path.relative_to(folder).as_posix())
            elif entry.is_dir(follow_symlinks=False):
                stack.append(path)
    left = [p for p in folder.rglob("*") if is_reparse(p)]
    if left:
        raise StorageError(
            f"{folder}: a link is still inside ({left[0]}); the folder was not removed, so "
            "nothing it points at can be deleted"
        )
    shutil.rmtree(folder)
    return undone


def _compact_sim(workspace: CampaignWorkspace, sim_id: str) -> dict[str, Any]:
    """Zip one simulation folder, verify every member, then remove the folder."""
    folder = workspace.sim_dir(sim_id)
    archive = _zip_path(workspace, sim_id)
    if archive.exists():
        # NEVER OVER AN EARLIER ARCHIVE (PFS-2096.014): a folder beside the zip
        # is a run or a sync that wrote into a compacted simulation, often part
        # of it, and zipping it over the archive would lose the rest.
        raise StorageError(_both_refusal(folder, archive))
    inputs = folder / "inputs"
    link_target = os.path.realpath(inputs) if _is_link(inputs) else None
    members: dict[str, str] = {}
    temporary = archive.with_name(archive.name + f".{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as zf:
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
                # Streamed, as every other hash here: a member can be a large .fsm.
                check = hashlib.sha256()
                with zf.open(name) as member:
                    for chunk in iter(lambda: member.read(1 << 20), b""):
                        check.update(chunk)
                if check.hexdigest() != digest:
                    raise StorageError(
                        f"sim {sim_id}: the compacted copy of {name} does not match the file; "
                        "nothing was removed"
                    )
    except BaseException:
        # A failed write (a file another process holds open) or a mismatch
        # leaves no partial zip, which space-in-use would count as a simulation.
        temporary.unlink(missing_ok=True)
        raise
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

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace.
    sim_id : str
        The simulation.
    reason : str
        The command asking, recorded with the restore.

    Returns
    -------
    bool
        True when a restore happened.

    Raises
    ------
    StorageError
        If a member of the archive leaves the folder or does not match its recorded hash,
        or the folder and the archive both exist.
    """
    folder = workspace.sim_dir(sim_id)
    archive = _zip_path(workspace, sim_id)
    if not archive.is_file():
        return False
    # ONE RESTORER AT A TIME (PFS-2096.016), under the storage record's own
    # lease, including the coexistence check: publishing the restored folder
    # precedes unlinking the archive, so that transient state must wait too.
    with workspace._manifest_lock(workspace.root / STORAGE_FILE):
        restored = _expand_archive(workspace, folder, archive)
    if restored is None:
        return False
    record_storage_call(
        workspace.root,
        {"action": "restore", "applied": True, "sim_id": sim_id, "reason": reason, **restored},
    )
    return True


def _extract_verified(archive: Path, temporary: Path) -> dict[str, Any]:
    """Extract a compacted simulation into ``temporary`` and return its recorded meta.

    A member that leaves the folder, or whose hash differs from the recorded
    one, refuses the restore (the second after removing the extracted copy).
    """
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
    return meta


def _expand_archive(
    workspace: CampaignWorkspace, folder: Path, archive: Path
) -> dict[str, Any] | None:
    """Extract, verify and put a compacted simulation in place; None when another restored it.

    Returns what the restore entry records about the ``inputs`` link: whether
    it was made again, and where it points, or the recorded target it could
    not reach when only an empty folder could be made (PFS-2085.011).
    """
    if not archive.is_file():
        return None
    if folder.exists():
        raise StorageError(_both_refusal(folder, archive))
    temporary = folder.with_name(folder.name + f".{os.getpid()}.restoring")
    if _is_link(temporary):
        # A planted link would make the containment check below accept the folder it
        # points at: it is unlinked, never followed.
        _remove_link(temporary)
    shutil.rmtree(temporary, ignore_errors=True)
    if temporary.exists() or temporary.is_symlink():
        raise StorageError(
            f"{temporary} is in the way of restoring {archive} and cannot be removed; "
            "remove it by hand, then restore again"
        )
    meta = _extract_verified(archive, temporary)
    try:
        temporary.replace(folder)
    except OSError:
        # The folder appeared while extracting: the copy is discarded, and a
        # folder beside the archive is the state refused above.
        shutil.rmtree(temporary, ignore_errors=True)
        if folder.exists():
            raise StorageError(_both_refusal(folder, archive)) from None
        raise
    restored = _restore_inputs_link(workspace, folder, meta)
    archive.unlink()
    return restored


def _restore_inputs_link(
    workspace: CampaignWorkspace, folder: Path, meta: dict[str, Any]
) -> dict[str, Any]:
    """Link a restored simulation's ``inputs`` again, into this workspace's library."""
    link = meta.get("inputs_link")
    if link and not (folder / "inputs").exists():
        wanted = _library_target(workspace, str(link))
        try:
            if wanted is None:
                raise OSError(f"no folder of {workspace.inputs_dir / 'geometries'} matches it")
            _make_dir_link(wanted, folder / "inputs")
        except OSError as error:
            (folder / "inputs").mkdir()
            warn(
                f"{folder}: the compacted simulation linked its inputs to {link}, and that "
                f"link could not be made again in this workspace ({error}); inputs/ is an "
                "empty folder. Stage the geometry under inputs/geometries and link it.",
                PyflightstreamWarning,
            )
            return {"inputs_link_restored": False, "inputs_link_target": str(link)}
        return {"inputs_link_restored": True, "inputs_link_target": str(wanted)}
    return {}


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


def _select_sims(
    spec: dict[str, Any], records: dict[str, list[dict[str, Any]]], present: Iterable[str]
) -> list[str]:
    wanted = spec.get("sims", "all")
    candidates = sorted(present)
    # The shapes of sims and status, and the status names, are read_recipe's (PFS-2096.028).
    if wanted != "all":
        named = {str(item) for item in wanted}
        missing = named.difference(candidates)
        if missing:
            raise StorageError(f"no simulation folder for sims {sorted(missing)}")
        candidates = [sim for sim in candidates if sim in named]
    statuses = spec.get("status")
    if statuses is not None:
        allowed = {str(item).upper() for item in statuses}
        candidates = [
            sim
            for sim in candidates
            if records.get(sim)
            and all(str(row.get("status")) in allowed for row in records.get(sim, []))
        ]
    return candidates


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
    step_prune.check_prune_tables(path, document.get(PRUNE_MODE, []), StorageError)
    for table in _RECIPE_TABLES:
        for spec in document.get(table, []):
            if (problem := step_prune.table_problem(table, spec, _PROTECTED_SUFFIXES)) is not None:
                raise StorageError(f"{path}: [[{table}]] {problem}")
    _check_step_values(path, document, StorageError)
    return path, document


def _pruned_files(root: Path, run_id: str) -> dict[str, tuple[int, str, str]]:
    """Each per-step file ``prune_step_exports`` deleted for a run: call, recipe, what it kept.

    Keyed by the file's resolved path, case-folded where the file system folds
    case. A storage record this package cannot read names nothing.
    """
    try:
        calls = read_storage_calls(root)
    except (StorageError, OSError, ValueError):
        return {}
    found: dict[str, tuple[int, str, str]] = {}
    for index, call in enumerate(calls):
        if call.get("action") != "free-space" or not call.get("applied"):
            continue
        for step in call.get("steps") or []:
            if not isinstance(step, dict) or step.get("mode") != PRUNE_MODE:
                continue
            kept = step_prune.kept_phrase(step, exclusive=True)
            for point in step.get("points") or []:
                if run_id not in (point.get("run_ids") or []):
                    continue
                for item in point.get("files") or []:
                    key = os.path.normcase(str((root / str(item["path"])).resolve()))
                    found[key] = (index, str(call.get("recipe")), kept)
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
    hits: dict[int, tuple[Path, tuple[int, str, str]]] = {}
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
    path, (index, recipe, kept) = hits[steps[0]]
    return (
        f"{STEP_EXPORTS_PRUNED}{product} needs step(s) {shown} of the window {window[0]} to "
        f"{window[1]}, and their per-step exports ({path.name} the first) were deleted by "
        f"free-space {recipe} ({PRUNE_MODE}, call {index} of {STORAGE_FILE}), which kept "
        f"{kept}. The product is not written from the steps that "
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

    Parameters
    ----------
    root : str or Path
        The workspace root.
    recipe : str
        The recipe's name, ``m<id>``, under ``inputs/management/``.
    apply : bool, optional
        Write the files; without it nothing is written and the same refusals fire.
    runs : str, optional
        Another manifest in the root whose records are read as well as ``runs.json``'s.

    Returns
    -------
    dict of str to object
        The entry recorded in ``storage_management.json``.

    Raises
    ------
    StorageError
        If the recipe is invalid, would delete a saved simulation, or a run is in progress.
    """
    workspace = _workspace(root)
    manifest = resolve_manifest(workspace.root, runs)
    with _runs_lease(workspace, f"{workspace.root}: runs.json.lock present, a run is in progress"):
        path, document = read_recipe(workspace.root, recipe)
        records = batch_life.mark_running(
            _records_by_sim(workspace, *dict.fromkeys((workspace.manifest_path, manifest))),
            workspace.root,
        )
        sims_root = workspace.root / "sims"
        present = [
            p.name[len("sim_") :]
            for p in (sims_root.iterdir() if sims_root.is_dir() else [])
            if p.is_dir() and p.name.startswith("sim_") and not is_reparse(p)
        ]
        _check_selections(workspace, document, records, present, select=_select_sims)
        entry: dict[str, Any] = {
            "action": "free-space",
            "applied": apply,
            "recipe": path.relative_to(workspace.root).as_posix(),
            "recipe_sha256": _sha256(path),
            "steps": [],
            "bytes_freed": 0,
        }
        try:
            entry["bytes_freed"] = _run_recipe(
                workspace,
                document,
                records,
                present,
                apply=apply,
                steps=entry["steps"],
                select=_select_sims,
                compact=_compact_sim,
            )
        except BaseException as error:
            # WHAT AN APPLIED RECIPE DID IS ALWAYS RECORDED (PFS-2096.027), the
            # steps done so far and the error that stopped the rest.
            if apply:
                entry["bytes_freed"] = None
                entry["interrupted"] = f"{type(error).__name__}: {error}"
                record_storage_call(workspace.root, entry)
            raise
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
        except (OSError, ValueError) as error:
            # NEVER SKIPPED (PFS-2086.006): an unread manifest hides the products
            # that hold the deleted points, and the shared-product refusal with them.
            raise StorageError(
                f"{manifest} cannot be read ({error}); delete-sims reads it to find the "
                "products that hold the deleted points, so nothing is deleted. Restore it "
                "(pyfs-matrix restore products) or rebuild it with a post, then run again."
            ) from error
        folder = manifest.parent
        own: list[str] = []
        shared: list[str] = []
        for name, entry in dict(document.get("products", {})).items():
            if not isinstance(entry, dict):
                continue
            runs = {str(run) for run in entry.get("runs", []) or []}
            if str(entry.get("sim_id")) in sim_ids:
                _refuse_outside(folder, name, manifest)
                own.append(name)
            elif runs & run_ids:
                shared.append(name)
        for run_id, value in dict(document.get("provenance", {})).items():
            if run_id in run_ids and isinstance(value, str):
                _refuse_outside(folder, value, manifest)
                own.append(value)
        if own or shared:
            found[folder.relative_to(workspace.root).as_posix()] = {
                "own": sorted(set(own)),
                "shared": sorted(set(shared)),
            }
    return found


def _refuse_outside(folder: Path, name: str, manifest: Path) -> None:
    """Refuse a product path that leaves its post folder: delete-sims unlinks what it names.

    The folder it lands in is resolved: a linked folder leaves it as surely as ``..`` does.
    """
    named = folder / name
    if ".." in Path(name).parts or not named.parent.resolve().is_relative_to(folder.resolve()):
        raise StorageError(
            f"{manifest} names the product {name!r}, which is not inside {folder}; "
            "delete-sims removes only files of the post folder, so nothing is deleted. "
            "Correct the entry (pyfs-matrix restore products) or rebuild it with a post."
        )


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
    _textio.write_text(temporary, json.dumps(document, indent=2) + "\n")
    temporary.replace(manifest)


def delete_sims(
    root: str | Path,
    sim_ids: Sequence[str],
    *,
    matrix_products: str | None = None,
    apply: bool = False,
    caller: str | None = None,
    runs: str | None = None,
    force: bool = False,
    archive: bool = False,
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

    A simulation with a record still SUBMITTED is refused unless ``force``
    (CLI: ``--force``), which deletes it whatever the status of its records
    (FR-306); the entry then states ``force`` and each simulation's statuses.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    sim_ids : sequence of str
        The simulations to delete.
    matrix_products : str, optional
        What happens to a product shared with other simulations, ``points-only`` or ``regenerate``;
        required with ``apply`` when one is.
    archive : bool, optional
        Keep replaced matrix products during regeneration. False overwrites in place (FR-397).
    apply : bool, optional
        Write the files; without it nothing is written and the same refusals fire.
    caller : str, optional
        Who asked, recorded in the entry; the operating-system user when None.
    runs : str, optional
        Another manifest in the root, by name; ``runs.json`` when None.
    force : bool, optional
        Delete a simulation with a record still SUBMITTED.

    Returns
    -------
    dict of str to object
        The entry recorded in ``storage_management.json``.

    Raises
    ------
    StorageError
        If no simulation is named, one is unknown or still SUBMITTED without ``force``,
        ``matrix_products`` is missing or unknown where a product is shared, or ``regenerate`` is
        asked with ``runs``.
    """
    workspace = _workspace(root)
    manifest = resolve_manifest(workspace.root, runs)
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
    with _runs_lease(workspace, f"{workspace.root}: runs.json.lock present, a run is in progress"):
        entry = _delete_sims_held(
            workspace,
            manifest,
            sim_ids,
            matrix_products=matrix_products,
            apply=apply,
            caller=caller,
            force=force,
        )
    with _recorded_if_interrupted(workspace.root, entry, apply, {}):
        shared = cast(dict[str, list[str]], entry["stale"])
        if entry["applied"] and matrix_products == "regenerate" and shared:
            regenerated: list[str | None] = []
            entry["regenerated"] = regenerated
            stems = {
                None if name == "None" else name
                for item in entry["sims"]
                for name in cast(list[str], item["matrix"])
            }
            for folder_rel in shared:
                folder = (workspace.root / folder_rel).resolve()
                matching = [s for s in stems if workspace.products_dir(s).resolve() == folder]
                if not matching:
                    entry.setdefault("not_regenerated", []).append(folder_rel)
                    continue
                for stage in post_stages():
                    stage(workspace, overwrite=True, archive=archive, matrix_stem=matching[0])
                regenerated.append(matching[0])
    record_storage_call(workspace.root, entry)
    return entry


def _delete_sims_held(
    workspace: CampaignWorkspace,
    manifest: Path,
    sim_ids: Sequence[str],
    *,
    matrix_products: str | None,
    apply: bool,
    caller: str | None,
    force: bool,
) -> dict[str, Any]:
    """Check and measure under the ``runs.json`` lease, and with ``apply`` delete."""
    # ONE ENTRY PER SIMULATION, in the order named (PFS-2103.041): a repeated
    # id wrote two tombstones with one run_id.
    if isinstance(sim_ids, str):
        # One bare id is one simulation, never its characters.
        sim_ids = [sim_ids]
    ids = list(dict.fromkeys(str(sim).strip() for sim in sim_ids if str(sim).strip()))
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
    submitted = batch_life.submitted_sims(workspace.root, ids, records, force=force)
    if submitted and not force:
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
        "force": force,
        "forced_submitted": submitted if force else [],
        "manifest": manifest.name,
        "sims": sims_entry,
        "post": products,
        "stale": shared,
        **batch_life.batch_report(workspace.root, ids),
    }
    if apply and shared and matrix_products is None:
        raise StorageError(
            "these matrix products also hold the deleted points: "
            + "; ".join(f"{folder}: {', '.join(names)}" for folder, names in shared.items())
            + ". Say matrix_products (CLI: --matrix-products) 'points-only' (leave them, "
            "marked stale) or 'regenerate' (rerun their post without the deleted points)."
        )
    if not apply:
        return entry
    # THE INTENT IS RECORDED BEFORE ANYTHING IS REMOVED (PFS-2086.005), so a
    # delete that stops part way is visible, and the same delete-sims run again
    # finishes it: its records are still in the manifest until the last step.
    record_storage_call(
        workspace.root,
        {
            **entry,
            "intent": (
                "delete-sims started; the entry after this one records what it removed. "
                "With none after it, the delete stopped part way: run the same delete-sims "
                "again to finish it."
            ),
        },
    )
    try:
        _delete_applied(
            workspace, manifest, entry, products=products, run_ids=run_ids, measured=measured
        )
    except BaseException as error:
        entry["applied"] = True
        entry["interrupted"] = f"{type(error).__name__}: {error}"
        record_storage_call(workspace.root, entry)
        raise
    return entry


def _delete_applied(
    workspace: CampaignWorkspace,
    manifest: Path,
    entry: dict[str, Any],
    *,
    products: dict[str, dict[str, list[str]]],
    run_ids: set[str],
    measured: dict[str, int],
) -> None:
    """Remove the checked simulations, their own products and their records; fill ``entry``."""
    ids = [str(item["sim_id"]) for item in entry["sims"]]
    stamp = _stamp()
    # THE FOLDERS GO FIRST, links undone before anything is removed: a
    # refusal there leaves the records, the products and the mesh as they were.
    links_undone: dict[str, list[str]] = {}
    entry["links_undone"] = links_undone
    for sim in tracked("delete-sims: remove", ids, label=_sim_folder, size=measured.__getitem__):
        links_undone[sim] = batch_life.remove_sim_folders(workspace, sim, _remove_sim_folder)
        archive = _zip_path(workspace, sim)
        if archive.is_file():
            archive.unlink()
    for folder_rel, item in products.items():
        folder = workspace.root / folder_rel
        for name in item["own"]:
            target = folder / name
            if target.is_file() and not is_reparse(target):
                target.unlink()
        _forget_products(folder / "products.json", item, run_ids, sims=ids, stamp=stamp)
    # The runs.json lease is already held by delete_sims for all of this.
    raw = _read_rows(manifest)
    archived_as = _archive_manifest(workspace, manifest, stamp) if manifest.is_file() else None
    kept = [row for row in raw if str(row.get("run_id")) not in run_ids]
    index = len(read_storage_calls(workspace.root))
    for item in entry["sims"]:
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
        # A relative path is the workspace root's (PFS-2094.049), so the
        # documented path = "." names main wherever the command is run from.
        written = Path(item["path"]).expanduser()
        spaces[name] = written if written.is_absolute() else root / written
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
    matrix belongs to one workspace and one only; a workspace may own several.
    A stem declared twice is refused, naming
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

    P0320-MATRICES-HOME, RST-1: the two homes are equal, so a stem
    held in both is read once when the two files hold the same bytes, and
    refused, naming both paths, when they differ (:func:`matrix_by_stem`).
    """
    try:
        found = matrix_by_stem(ws)
    except WorkspaceError as error:
        raise StorageError(str(error)) from error
    return {stem: path.relative_to(ws) for stem, path in found.items()}


def _refuse_linked_folders(root: Path, target: Path) -> None:
    """Refuse a destination whose folders under ``root`` include a link."""
    try:
        relative = target.parent.relative_to(root)
    except ValueError:
        return
    folder = root
    for part in relative.parts:
        folder = folder / part
        if folder.exists() and is_reparse(folder):
            raise StorageError(
                f"{folder} is a link; sync never writes through a link, so {target} was not "
                "written. Replace the link by a folder or remove it."
            )


def _atomic_copy(
    source: Path, target: Path, *, keep: Path | None = None, root: Path | None = None
) -> str:
    """Copy ``source`` over ``target`` through a temporary name; return the digest.

    P0320-SYNC-ATOMIC. The bytes go to a temporary file in the target's own
    folder, are checked against the source, and only then take the target's
    name in one rename, so an interrupted copy never leaves a partial file
    under the target's name, and an overwritten file stays in place until
    its replacement is whole. ``keep``, when given and the target exists,
    receives a copy of the target first (the sync's ``archive/sync-<stamp>/``).
    A failure removes the temporary file and leaves the target as it was.
    With ``root``, no folder between it and the target may be a link, and a
    file already at the temporary name is removed (the link itself, not what
    it points at) before the copy, so nothing outside the workspace is written.
    """
    if root is not None:
        _refuse_linked_folders(root, target)
        if keep is not None:
            _refuse_linked_folders(root, keep)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}{_SYNC_TEMPORARY}")
    temporary.unlink(missing_ok=True)
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
                _atomic_copy(source, copy, keep=keep, root=main.root)
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
        if is_reparse(sim) or sim.name[len("sim_") :] in skip_sims:
            continue
        if sim.is_file():
            if rank >= 3 and sim.name.endswith(COMPACTED_SUFFIX):
                out.add(sim)
            continue
        # The one per-simulation rule, which a batch's sim_<id> follows too (PFS-2087.002).
        out |= batch_life.sim_sync_files(sim, rank)
    out |= batch_life.batch_files(ws, rank, skip_sims)
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
        if is_reparse(path):
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


def _plan_points_without_record(
    other: Path, rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Per matrix, the points the OTHER workspace planned that no merged record carries.

    Each ``post/<stem>/plan.json`` of the other workspace lists the
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
    """Return the lines ``pyfs-matrix sync`` prints for a synchronization entry.

    The archive files and bytes skipped (P0320-SYNC-SKIP-ARCHIVES), the
    simulation folders of both sides and those no record carries
    (P0320-SYNC-ALL-FOLDERS), and what the restore did or would do
    (P0320-SYNC-RESTORE-OPTIN). An entry written in legacy releases gives none.

    Parameters
    ----------
    entry : mapping of str to object
        One entry :func:`sync_workspaces` returned.

    Returns
    -------
    list of str
        The lines; none for an entry written in legacy releases.
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


#: The rebuild of the records of simulation folders no record carries, which
#: an applying ``sync --restore`` asks for (P0320-SYNC-RESTORE-OPTIN): the
#: run records (:mod:`pyflightstream.run.records`), ABOVE this layer since
#: AD-09: register it here when they load, the way the post
#: registers its stages in :mod:`pyflightstream.workspace`, and the package
#: root loads them. No import of this module points up at the run.
_Rebuild = Callable[[Path, list[str]], dict[str, Any]]
_REBUILDS: list[_Rebuild] = []


def register_records_rebuild(rebuild: _Rebuild) -> _Rebuild:
    """Register the rebuild a restoring sync calls with ``(root, sims)``; return the held one.

    The rebuild returns the entry's ``restore`` block (``asked``, ``sims``,
    ``result``, ``error``) and never raises for a refusal, which it writes in
    ``error``: the files the sync copied stand.

    The registry holds exactly one rebuild. The first registered is held; a
    rebuild of the same module replaces it (a reload of
    :mod:`pyflightstream.run.records`), and a rebuild of another module is
    not taken: a copy of the records executed under another name, as a
    mutation test does, never displaces the package's own. The return is the
    rebuild the registry holds afterwards, so a registrant that was not taken
    sees it. A module that loads this file by path, apart from the package,
    holds an empty registry of its own until it registers: its restoring sync
    then names that in the ``error`` of its restore block.
    """
    # Held rebuilds of another module stay; none held, or one of this module: take it.
    _REBUILDS[:] = [h for h in _REBUILDS if h.__module__ != rebuild.__module__] or [rebuild]
    return _REBUILDS[0]


def _restore_orphans(root: Path, sims: list[str]) -> dict[str, Any]:
    """Rebuild the records of ``sims`` through the registered records rebuild.

    P0320-SYNC-RESTORE-OPTIN. Called by an applying sync that was asked to
    restore, AFTER it released the ``runs.json`` lease, which the rebuild takes
    itself. The rebuild appends the records whose run ids ``runs.json`` does
    not hold (the B1 contract). A refusal is the entry's ``error``, not the
    sync's: the files it copied stand. The rebuilt records themselves are in
    ``runs.json`` and are not repeated in the storage record.
    """
    if _REBUILDS:
        return _REBUILDS[0](root, sims)
    error = "no records rebuild is registered: import pyflightstream, which registers it"
    return {"asked": True, "sims": sims, "result": None, "error": error}


@contextmanager
def _recorded_if_interrupted(
    root: Path, entry: dict[str, Any], apply: bool, done: dict[str, Any]
) -> Iterator[None]:
    """Record ``entry`` and what was ``done`` when an applied command stops part way.

    PFS-2096.027: the error is recorded with the entry, so a sync that merged
    the records and then failed a copy leaves a record of both.
    """
    try:
        yield
    except BaseException as error:
        if apply:
            entry.update(done, interrupted=f"{type(error).__name__}: {error}")
            record_storage_call(root, entry)
        raise


def _expand_compacted(
    main: CampaignWorkspace,
    files: Iterable[Path],
    *,
    source: str,
    apply: bool,
    expanded: list[str],
) -> list[str]:
    """Restore, with ``apply``, the compacted simulations of main that ``files`` write into.

    Returns their ids: what main holds only as ``sims/sim_<id>.zip``.
    """
    found: set[str] = set()
    for relative in files:
        parts = relative.parts
        if len(parts) < 2 or parts[0] != "sims" or not parts[1].startswith("sim_"):
            continue
        incoming_archive = len(parts) == 2 and relative.suffix == COMPACTED_SUFFIX
        sim_id = parts[1][len("sim_") :]
        if incoming_archive:
            sim_id = sim_id[: -len(COMPACTED_SUFFIX)]
        folder, archive = main.sim_dir(sim_id), _zip_path(main, sim_id)
        if folder.exists() and (incoming_archive or archive.is_file()):
            raise StorageError(
                f"sync from {source}: {folder} conflicts with {archive}; "
                "expand and reconcile the compacted simulation before syncing"
            )
        if not incoming_archive and len(parts) > 2 and archive.is_file():
            found.add(sim_id)
    for sim_id in sorted(found):
        if apply:
            ensure_sim_expanded(main, sim_id, reason=f"sync from {source}")
        expanded.append(sim_id)
    return sorted(found)


def _sync_existing(main: CampaignWorkspace, relative: Path, source: Path) -> tuple[bool, bool]:
    """Whether main has a file and the same bytes, including a compacted preview."""
    target = main.root / relative
    if target.exists():
        return True, _size(source) == _size(target) and _sha256(source) == _sha256(target)
    parts = relative.parts
    if len(parts) > 2 and parts[0] == "sims" and parts[1].startswith("sim_"):
        archive = _zip_path(main, parts[1][len("sim_") :])
        if archive.is_file():
            with zipfile.ZipFile(archive) as zf:
                name = Path(*parts[2:]).as_posix()
                try:
                    info = zf.getinfo(name)
                except KeyError:
                    return False, False
                if info.file_size != _size(source):
                    return True, False
                digest = hashlib.sha256()
                with zf.open(info) as member:
                    for chunk in iter(lambda: member.read(1 << 20), b""):
                        digest.update(chunk)
                return True, digest.hexdigest() == _sha256(source)
    return False, False


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
    copied: list[dict[str, Any]] = []
    overwritten: list[dict[str, Any]] = []
    with _recorded_if_interrupted(
        main.root, entry, apply, {"files": {"copied": copied, "overwritten": overwritten}}
    ):
        if not ((other / "runs.json").exists() or (other / "inputs").is_dir()):
            entry["skipped"] = "not a pyfs-matrix workspace (no runs.json, no inputs/)"
            record_storage_call(main.root, entry)
            return entry
        if _lease_live_in(other):
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
        with main._manifest_lock():
            # A SIMULATION MAIN HOLDS COMPACTED IS RESTORED BEFORE ANYTHING IS COPIED
            # INTO IT (PFS-2096.014): the copy made a partial folder beside the
            # archive, which the next compaction then zipped over the complete one.
            _expand_compacted(
                main, files, source=name, apply=apply, expanded=entry.setdefault("expanded", [])
            )
            plan: list[tuple[str, Path]] = []
            file_conflicts: list[str] = []
            identical = 0
            with stage_progress("sync hash", total_files=len(files)) as progress:
                for relative in files:
                    exists, same = _sync_existing(main, relative, other / relative)
                    if not exists:
                        plan.append(("copy", relative))
                    elif same:
                        identical += 1
                    elif overwrite:
                        plan.append(("overwrite", relative))
                    else:
                        file_conflicts.append(relative.as_posix())
                    progress.advance(
                        files=1, bytes=_size(other / relative), current=relative.as_posix()
                    )
            main_ids, other_ids = _sim_ids(main.root), _sim_ids(other)
            inputs_links: dict[str, str] = {}
            # RST-6: THE LEASE ON runs.json IS HELD FOR THE WHOLE OF THE MERGE AND THE
            # COPY, so a restore (which refuses while runs.json.lock is present), a
            # run, a collect or a second sync never writes into the workspace while
            # this one does. A copy that fails
            # after the records were merged is recorded with what was done (PFS-2096.027).
            with stage_progress("sync merge", total_files=len(other_rows)) as progress:
                main_rows = _read_rows(manifest)
                merged, added, replaced, run_conflicts = _merge_runs(
                    main_rows, other_rows, prefer_other
                )
                archived_as = (
                    _archive_manifest(main, manifest, stamp)
                    if apply and (added or replaced) and manifest.is_file()
                    else None
                )
                if apply and (added or replaced):
                    _replace_rows(main, manifest, merged)
                entry["runs"] = {
                    "manifest": manifest.name,
                    "added": added,
                    "replaced": replaced,
                    "conflicts": run_conflicts,
                    "submitted_sims_record_only": sorted(submitted),
                    "archived_as": archived_as,
                    "records_before": len(main_rows),
                    "records_after": len(merged),
                }
                progress.advance(files=len(other_rows))
            with stage_progress(
                "sync copy",
                total_files=len(plan),
                total_bytes=sum(_size(other / relative) for _, relative in plan),
            ) as progress:
                for kind, relative in plan if apply else []:
                    source, target = other / relative, main.root / relative
                    keep = None
                    if kind == "overwrite":
                        keep = main.root / ARCHIVE_DIR / f"sync-{stamp}" / relative
                    digest = _atomic_copy(source, target, keep=keep, root=main.root)
                    size = _size(target)
                    item = {"path": relative.as_posix(), "bytes": size, "sha256": digest}
                    (overwritten if kind == "overwrite" else copied).append(item)
                    progress.advance(files=1, bytes=size, current=relative.as_posix())
            # THE MESH IS LINKED, NEVER COPIED: each
            # simulation folder sync brought gets its `inputs` link into main's own
            # geometry library, the way the other workspace's simulation had it.
            other_sims = other / "sims"
            for sim in sorted(other_sims.glob("sim_*")) if other_sims.is_dir() else []:
                if not sim.is_dir() or is_reparse(sim) or sim.name[len("sim_") :] in submitted:
                    continue
                if apply:
                    done = _relink_inputs(main, other, sim.name)
                    if done:
                        inputs_links[sim.name] = done
                elif not (main.root / "sims" / sim.name / "inputs").exists():
                    inputs_links[sim.name] = "to link when applied"
            # MATRICES: every difference is reported as
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
        # What the other workspace planned and no merged record carries.
        entry["plan_points_without_record"] = _plan_points_without_record(other, merged)
        entry.update(
            {
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

    Every ``sims/sim_*`` folder of both sides is compared, recorded or
    not, and each entry's ``sims`` names the folders no record carries.
    ``restore`` (CLI: ``--restore``), off by default, rebuilds their records
    through :func:`pyflightstream.run.records.rebuild` once an applying sync
    has released the ``runs.json`` lease it holds for the whole of its merge
    and copy. Every file is copied to a temporary name and renamed in place.
    A folder named ``archive`` is skipped unless ``include_archives`` (CLI:
    ``--include-archives``), and ``files.archives_skipped`` counts what was.
    ``runs`` (CLI: ``--runs NAME``) names the manifest of main the records
    merge into; the other workspace's ``runs.json`` is the source.

    Parameters
    ----------
    root : str or Path
        The main workspace.
    level : str
        ``runs``, ``post``, ``fsm`` or ``all``.
    source : str, optional
        The one workspace of ``sync-workspaces.toml`` to bring from; every other one when None.
    apply : bool, optional
        Write the files; without it nothing is written and the same refusals fire.
    prefer_other : bool, optional
        Where a record differs, keep the other workspace's; main's is kept otherwise, unless it is
        SUBMITTED.
    overwrite : bool, optional
        Replace a file of main that differs from the other workspace's instead of reporting a
        conflict.
    restore : bool, optional
        Rebuild the records of the simulation folders no record carries.
    include_archives : bool, optional
        Copy the folders named ``archive`` too.
    runs : str, optional
        The manifest of main the records merge into; ``runs.json`` when None.

    Returns
    -------
    list of dict
        One recorded entry per source workspace.

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
    manifest = resolve_manifest(main.root, runs)
    if restore and manifest != main.manifest_path:
        raise StorageError(
            f"restore (CLI: --restore) rebuilds records into runs.json only; with runs (CLI: "
            f"--runs) {manifest.name} it is refused. Rebuild into another manifest with "
            "pyflightstream.run.records.rebuild and its out (CLI: --out) (the command "
            "pyfs-matrix rebuild)."
        )
    main_name, spaces = read_sync_config(main.root)
    with _runs_lease(
        main,
        f"{main.root}: runs.json.lock present, a run, a collect, a restore or another sync "
        "is writing here; the sync is refused until it ends",
    ):
        pass  # only asked here: the lease's own rules say whether a writer holds it
    names = [source] if source else [name for name in spaces if name != main_name]
    for name in names:
        if name not in spaces:
            raise StorageError(
                f"source (CLI: --from) {name!r} is not in {SYNC_CONFIG} ({sorted(spaces)})"
            )
        if name == main_name:
            raise StorageError(f"source (CLI: --from) {name!r} is the main workspace itself")
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

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace.
    pending_points : int
        The points the plan will run.
    margin : float, optional
        The share of the free space held back.

    Returns
    -------
    tuple of (str, bool)
        The line the plan prints, and whether the points fit.
    """
    free = shutil.disk_usage(workspace.root).free
    sizes = []
    sims = workspace.root / "sims"
    for datapoint in sims.glob("sim_*/datapoints/DP-*") if sims.is_dir() else []:
        if datapoint.is_dir() and not is_reparse(datapoint):
            size = sum(_size(p) for p in _walk_files(datapoint))
            if size > 0:  # an empty folder is no completed sample
                sizes.append(size)
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
