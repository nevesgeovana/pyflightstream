"""What the other commands do about a grouped job's folders while it runs (0.35.0).

Pipeline role: the workspace-layer half of FR-372 (P0350-BATCH-TRANSPARENT). A
batch's sims live in ``sims/batch/<matrix>_b<ID>/sim_<id>/`` until its job ends
and ``collect`` moves them, so the commands that enumerate ``sims/sim_<id>``
(``delete-sims``, ``sync``, ``free-space``, ``post --from-sims``) would miss them
or, worse, damage a job that is still writing. This module holds the rules those
commands share and nothing that launches a solver: which batches are still
running (read from the files the job leaves, never from the scheduler), where a
simulation's folders are, what a sync brings from the batch tree, and which
file names are job scripts and not loads exports.

"Running" is a batch folder whose job has not ended: the job entry of a record
names it, and none of the end evidence is there (the local end record
``<stem>.end.json``, the job's final log ``<stem>.job-log.txt``, every
``job_end_files`` glob of the HPC profile). ``run`` reads the same evidence in
``run._batch_collect.job_ended`` and adds a settling watch; a command that only
refuses to touch a folder takes the files as they are.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.workflows import (
    BATCH_STEM_PREFIX,
    FULL_POLAR_STEM,
    JOB_END_SUFFIX,
    JOB_LOG_SUFFIX,
)
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace._batches import batch_dirs, batch_sim_dirs

if TYPE_CHECKING:
    from pyflightstream.workspace import CampaignWorkspace

__all__ = [
    "batch_files",
    "batch_report",
    "is_kept_name",
    "mark_running",
    "remove_sim_folders",
    "running_batches",
    "running_sims",
    "submitted_sims",
]

_SUBMITTED = "SUBMITTED"
_KEPT_NAMES = ("fs_runtime_output.txt", "flightstreamlog.txt")
_LOG_ENDINGS = ("log.txt", ".log")


def is_job_script(name: str) -> bool:
    """Say whether a file name is a grouped job's script, not a loads export.

    Parameters
    ----------
    name : str
        A file name.

    Returns
    -------
    bool
        True for ``FULL-POLAR.txt`` and ``BATCH-<first>-<last>.txt``.
    """
    lowered = name.lower()
    return lowered == f"{FULL_POLAR_STEM}.txt".lower() or (
        lowered.startswith(BATCH_STEM_PREFIX.lower()) and lowered.endswith(".txt")
    )


def is_kept_name(name: str) -> bool:
    """Say whether ``free-space`` keeps a file by its name: a runtime log or a job script.

    Parameters
    ----------
    name : str
        A file name.

    Returns
    -------
    bool
        True for the solver's runtime logs and the job scripts.
    """
    return name.lower() in _KEPT_NAMES or is_job_script(name)


def _field(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)


def _job_of(row: Any) -> Mapping[str, Any] | None:
    submission = _field(row, "submission")
    job = submission.get("job") if isinstance(submission, Mapping) else None
    return job if isinstance(job, Mapping) else None


def _end_globs(root: Path) -> tuple[str, ...]:
    """Return the profile's ``job_end_files`` globs; none without a readable profile."""
    from pyflightstream.workspace.hpc import resolve_hpc_profile

    try:
        profile = resolve_hpc_profile(root / "inputs")
    except (PyflightstreamError, OSError, ValueError):
        return ()
    return tuple(getattr(profile, "job_end_files", ()) or ())


def _ended(root: Path, job: Mapping[str, Any], globs: Sequence[str]) -> bool:
    folder = root / str(job["dir"])
    stem = PurePosixPath(str(job["script"])).stem
    if (folder / f"{stem}{JOB_END_SUFFIX}").is_file() or (
        folder / f"{stem}{JOB_LOG_SUFFIX}"
    ).is_file():
        return True
    values = job.get("values") or {}
    for pattern in globs:
        try:
            found = [p for p in folder.glob(pattern.format(**values)) if p.is_file()]
        except (KeyError, IndexError, ValueError):
            return False
        if not found:
            return False
    return bool(globs)


def running_batches(root: str | Path, rows: Iterable[Any]) -> dict[str, set[str]]:
    """Map every batch whose job has not ended to the simulations it holds.

    Parameters
    ----------
    root : str or Path
        The campaign workspace root.
    rows : iterable
        The run records, as mappings or as ``RunRecord`` objects.

    Returns
    -------
    dict of str to set of str
        Batch label (``<matrix>_b<ID>``) to its simulation ids; empty when no
        batch is running.
    """
    base = Path(root)
    globs: tuple[str, ...] | None = None
    jobs: dict[str, tuple[Mapping[str, Any], set[str]]] = {}
    for row in rows:
        job = _job_of(row)
        if job is None or job.get("kind") != "batch" or not (base / str(job["dir"])).is_dir():
            continue
        sims = jobs.setdefault(str(job["label"]), (job, set()))[1]
        sims.add(str(_field(row, "sim_id")))
    running: dict[str, set[str]] = {}
    for label, (job, sims) in jobs.items():
        globs = _end_globs(base) if globs is None else globs
        if not _ended(base, job, globs):
            folder = base / str(job["dir"])
            inside = {
                sim
                for sim, folders in batch_sim_dirs(base).items()
                if any(item.parent == folder for item in folders)
            }
            running[label] = sims | inside
    return running


def running_sims(root: str | Path, rows: Iterable[Any]) -> dict[str, str]:
    """Map every simulation of a running batch to that batch's label.

    Parameters
    ----------
    root : str or Path
        The campaign workspace root.
    rows : iterable
        The run records, as mappings or as ``RunRecord`` objects.

    Returns
    -------
    dict of str to str
        Simulation id to the label of its running batch.
    """
    return {
        sim: label for label, sims in running_batches(root, rows).items() for sim in sorted(sims)
    }


def submitted_sims(
    root: str | Path,
    ids: Sequence[str],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    force: bool,
) -> list[str]:
    """Return the simulations ``delete-sims`` treats as still in flight.

    A simulation with a record still SUBMITTED, or one that belongs to a batch
    whose job has not ended (its collected points keep the job entry), is in
    flight. The second kind is refused here, naming the batch, unless ``force``.

    Parameters
    ----------
    root : str or Path
        The campaign workspace root.
    ids : sequence of str
        The simulations asked for.
    records : mapping
        The records by simulation id.
    force : bool
        Delete whatever the status (CLI: ``--force``).

    Returns
    -------
    list of str
        The ids with a SUBMITTED record, then those of a running batch.

    Raises
    ------
    WorkspaceError
        If a named simulation belongs to a running batch and ``force`` is not set.
    """
    flat = [row for rows in records.values() for row in rows]
    running = running_sims(root, flat)
    batched = [sim for sim in ids if sim in running]
    if batched and not force:
        names = sorted({running[sim] for sim in batched})
        raise WorkspaceError(
            f"sims (CLI: --sims) {batched} belong to batch {', '.join(names)}, whose job has "
            "not ended: deleting them now removes folders the job is writing and leaves the "
            "other points of the batch SUBMITTED against a script that names them. Wait for "
            "the batch to end and collect it, or say force (CLI: --force)."
        )
    submitted = [
        sim for sim in ids if any(row.get("status") == _SUBMITTED for row in records.get(sim, []))
    ]
    return submitted + [sim for sim in batched if sim not in submitted]


def mark_running(
    records: dict[str, list[dict[str, Any]]], root: str | Path
) -> dict[str, list[dict[str, Any]]]:
    """Add a SUBMITTED stand-in to every simulation of a running batch.

    ``free-space`` skips a simulation with a SUBMITTED record; a batch point
    already collected while its job runs has none, so its simulation would be
    freed under the job. The stand-ins are read only by that rule.

    Parameters
    ----------
    records : dict
        The records by simulation id, as ``free-space`` reads them.
    root : str or Path
        The campaign workspace root.

    Returns
    -------
    dict
        ``records`` with the stand-ins added.
    """
    flat = [row for rows in records.values() for row in rows]
    for sim, label in running_sims(root, flat).items():
        records.setdefault(sim, []).append(
            {"run_id": f"batch/{label}", "status": _SUBMITTED, "sim_id": sim}
        )
    return records


def remove_sim_folders(
    workspace: CampaignWorkspace, sim: str, remove: Callable[[Path], list[str]]
) -> list[str]:
    """Remove a simulation's folder and every copy of it inside a batch folder.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign workspace.
    sim : str
        The simulation id; ``sims/sim_<id>`` may not exist when it lives only in a batch.
    remove : callable
        The link-safe folder remover of ``workspace.storage``; it returns the
        links it undid, relative to the folder it was given.

    Returns
    -------
    list of str
        The links undone, relative to ``sims/sim_<id>`` or, for a batch copy,
        prefixed with its path under the workspace.
    """
    base, folder = workspace.root, workspace.sim_dir(sim)
    undone = remove(folder) if folder.exists() else []
    for inside in batch_sim_dirs(base).get(sim, []):
        prefix = inside.relative_to(base).as_posix()
        undone += [f"{prefix}/{link}" for link in remove(inside)]
    return undone


def batch_report(root: str | Path, ids: Iterable[str]) -> dict[str, list[str]]:
    """Name the batch folders that would be left holding no simulation.

    Parameters
    ----------
    root : str or Path
        The campaign workspace root.
    ids : iterable of str
        The simulations being deleted.

    Returns
    -------
    dict of str to list of str
        ``batches_left_without_sim``: the batch folders, relative to the root,
        whose every simulation is among ``ids``. Nothing is deleted with them.
    """
    base, gone = Path(root), set(ids)
    held = batch_sim_dirs(base)
    left = [
        folder.relative_to(base).as_posix() + "/"
        for folder in batch_dirs(base)
        if (inside := {s for s, found in held.items() if any(f.parent == folder for f in found)})
        and inside <= gone
    ]
    return {"batches_left_without_sim": left}


def _files(folder: Path) -> Iterable[Path]:
    """Every regular file below ``folder``, never through a link or a junction."""
    for here, children, names in os.walk(folder):
        children[:] = [
            child
            for child in children
            if not os.path.islink(os.path.join(here, child))
            and not os.path.isjunction(os.path.join(here, child))
        ]
        for name in names:
            yield Path(here) / name


def _sim_files(sim: Path, rank: int) -> set[Path]:
    """Return what a sync of level ``rank`` brings from one simulation folder."""
    out = set(_files(sim / "scripts"))
    for file in _files(sim / "datapoints"):
        if file.name == "FS_runtime_output.txt" or file.name.endswith("_log.txt"):
            out.add(file)
        elif rank >= 2 and file.suffix.lower() == ".fsm":
            out.add(file)
    if rank >= 3:
        out.update(
            file
            for file in _files(sim)
            if file.relative_to(sim).parts and file.relative_to(sim).parts[0] != "inputs"
        )
    return out


def batch_files(ws: Path, rank: int, skip_sims: set[str]) -> set[Path]:
    """Return the files a sync of level ``rank`` brings from ``sims/batch/``.

    The job's scripts and logs travel at every level, as a simulation's do; the
    rest of the job folder (descriptors, end records) at ``all``; each
    simulation inside a batch folder follows the rules of ``sims/sim_<id>``.

    Parameters
    ----------
    ws : Path
        The workspace root.
    rank : int
        The index of the sync level in the ordered levels (3 is ``all``).
    skip_sims : set of str
        Simulations the sync leaves out.

    Returns
    -------
    set of Path
        Absolute paths of the files to bring.
    """
    out: set[Path] = set()
    for folder in batch_dirs(ws):
        for entry in sorted(folder.iterdir()):
            if entry.is_dir() and entry.name.startswith("sim_"):
                if entry.name[len("sim_") :] not in skip_sims and not os.path.islink(entry):
                    out |= _sim_files(entry, rank)
            elif entry.is_file() and (
                rank >= 3 or is_job_script(entry.name) or entry.name.endswith(_LOG_ENDINGS)
            ):
                out.add(entry)
    return out
