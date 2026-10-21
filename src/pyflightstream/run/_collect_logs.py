"""How collect reads a point's solver log: the scheduler's own, and a job that ended without it.

Pipeline role: the half of :mod:`pyflightstream.run.collect` that resolves the
log a point is judged by before the sweep observes its outputs. A machine
whose build aborts at ``EXPORT_LOG`` writes its own log under the HPC
profile's ``native_log`` (:func:`native_log`); a job whose end-of-job files
(``job_end_files``) exist while its log does not ended without it
(:func:`job_ended_without_log`, FR-311); and the sweep observes the
scheduler's file in the place of the declared log (:func:`observed_paths`).
The collect stage supplies the point folder name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace._batches import job_of
from pyflightstream.workspace.inputs import resolve_hpc_profile

__all__ = [
    "JOB_END_TAIL_LINES",
    "LOG_SUFFIX",
    "NativeLog",
    "job_ended_without_log",
    "native_log",
    "observed_paths",
]


#: The suffix every solver log this package names carries, from EXPORT_KINDS.
LOG_SUFFIX = "_log.txt"


def _tail_lines(path: Path, count: int) -> list[str]:
    """Return the last ``count`` lines of ``path``, reading from its end (F-1255)."""
    size = path.stat().st_size
    chunk = 65536
    with path.open("rb") as handle:
        while True:
            start = max(0, size - chunk)
            handle.seek(start)
            data = handle.read(size - start)
            # A window cut mid-line holds one more line than it shows whole.
            if start == 0 or data.count(b"\n") > count:
                break
            chunk *= 4
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0:
        lines = lines[1:]
    return lines[-count:]


def _glob_values(record: RunRecord, point: str) -> dict[str, object]:
    """Return what a profile glob of this record is formatted with (PFS-2095.026).

    ``{sim}`` and ``{point}``, the record's own; a point of a grouped job also
    offers its job's values (``batch``, ``sims``, ...), which the grouped
    collect formats the same globs with, so a glob naming one of them is no
    crash here.
    """
    job = job_of(record)
    values = job.get("values") if job is not None else None
    # FR-730: {sim} is the FIRST simulation of the job, so the job's own value is not overwritten.
    return {"sim": record.sim_id, **(values if isinstance(values, Mapping) else {}), "point": point}


def _profile_glob(key: str, pattern: str, values: Mapping[str, object]) -> tuple[str | None, str]:
    """Return the glob ``pattern`` formats to, or None and the refusal naming what it lacks."""
    try:
        return pattern.format(**values), ""
    except KeyError as error:
        lacking = f"{{{error.args[0]}}}"
    except (IndexError, ValueError, AttributeError, TypeError) as error:
        lacking = f"a placeholder it cannot read ({error})"
    return None, (
        f"the HPC profile's {key} ({pattern!r}) names {lacking}, which this point does not "
        f"fill; it fills {', '.join('{' + name + '}' for name in values)}. Correct the "
        "pattern in the profile."
    )


@dataclass(frozen=True)
class NativeLog:
    """What the HPC profile's ``native_log`` resolved to for one record."""

    #: The sentence of a refusal, or None.
    refusal: str | None = None
    #: The file the scheduler is writing, or None when there is none to read.
    source: Path | None = None
    #: The declared name the row's log is read under.
    target: Path | None = None


def native_log(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    work_dir: Path,
    *,
    point: str,
) -> NativeLog:
    """Find the log the SCHEDULER wrote, and the declared name it is read under.

    Some machines abort at
    ``EXPORT_LOG``: the job runs, every other export lands, and the log the
    package judges the run by never arrives, so `collect` waits for a file
    nothing will ever write. Such a machine writes its own log beside the run,
    and its HPC profile names it (``native_log = "FTS{sim}.l*"``); this copies
    that file to the declared name, so everything downstream reads one log
    whatever the scheduler called it.

    NOTHING IS COPIED HERE. Observing a copy would falsely establish settling
    while the scheduler continues writing its source. The source
    is what is OBSERVED (:func:`pyflightstream.run.collect.collect_once`), and it
    is copied once it has settled (collect's ``_copy_native_log``), over whatever
    an earlier sweep left.

    The answer carries a refusal; or the scheduler's file and the declared
    name; or neither, when there is nothing to say: no profile, no
    ``native_log``, or the scheduler's file not written yet, which is a WAIT
    and not a failure.
    """
    profile = resolve_hpc_profile(workspace.inputs_dir)
    pattern = getattr(profile, "native_log", None)
    if not pattern:
        return NativeLog()
    declared = [name for name in names if str(name).endswith(LOG_SUFFIX)]
    if not declared:
        return NativeLog(
            f"the HPC profile names a native log ({pattern!r}) and this point declares no "
            f"output ending in {LOG_SUFFIX!r}, so there is no name to copy it to. The row "
            "declares its log among its outputs, which is how it is collected and how the "
            f"run is judged; its outputs are {', '.join(Path(n).name for n in names)}."
        )
    target = work_dir / declared[0]
    # Resolve {point} to the record's output folder through the shared rule,
    # including records without point_name that name their submitted working
    # directory (FIX-0211).
    glob, refusal = _profile_glob("native_log", pattern, _glob_values(record, point))
    if glob is None:
        return NativeLog(refusal)
    found = sorted(path for path in work_dir.glob(glob) if path.is_file())
    if len(found) > 1:
        return NativeLog(
            f"the HPC profile's native_log ({pattern!r}) matches {len(found)} files in "
            f"{work_dir}: {', '.join(path.name for path in found)}. Which of them is this "
            "run's log is not a guess this package makes, because the log is what the run "
            "is judged by. Narrow the pattern, or clear the ones that are not this run's."
        )
    return NativeLog(source=found[0] if found else None, target=target)


def observed_paths(
    record: RunRecord, names: Sequence[str], work_dir: Path, native: NativeLog
) -> tuple[list[str], list[Path]]:
    """Return the declared names a sweep waits for, and the paths it observes for them.

    G45: A TECPLOT THE PACKAGE WRITES IS NOT WAITED FOR. The solver writes its
    VTK and never the .dat, which is written from it once the job is settled;
    waiting for it was waiting forever. THE SCHEDULER'S FILE STANDS IN FOR THE
    DECLARED LOG while the two observations are taken, because it is the one the
    job is writing. Where the scheduler has written nothing yet the declared
    name is observed as it always was, and reads as missing.
    """
    written_here = {
        str(translation.get("dat"))
        for translation in record.surface_translations or []
        if isinstance(translation, Mapping)
    }
    waited = [name for name in names if name not in written_here]
    paths = [
        native.source
        if native.source is not None and work_dir / name == native.target
        else work_dir / name
        for name in waited
    ]
    return waited, paths


#: The lines of each end-of-job file a FAILED_EXECUTION record carries (FR-526).
JOB_END_TAIL_LINES = 20


def job_ended_without_log(
    workspace: CampaignWorkspace,
    record: RunRecord,
    names: Sequence[str],
    work_dir: Path,
    *,
    native: NativeLog,
    point: str,
) -> RunRecord | None:
    """Record FAILED_EXECUTION for a job whose end-of-job files exist and whose log does not.

    FR-311. The HPC profile's ``job_end_files`` lists the files the scheduler
    writes when a job ends; nothing of one scheduler is written here. When
    every pattern matches a file and the solver log does not exist (the
    ``native_log`` match, or else the declared log), the job ended without
    it: the record is written FAILED_EXECUTION and returned, carrying the last
    :data:`JOB_END_TAIL_LINES` lines of each matched file, read as bytes and
    decoded with replacement. None, and the sweep goes on as before, when the
    profile lists none, when a pattern matches nothing, when the point
    declares no log, or when the log exists. A heuristic (FR-529): a log delayed
    on a shared file system, or a requeued job, can be misjudged.
    """
    profile = resolve_hpc_profile(workspace.inputs_dir)
    patterns = tuple(getattr(profile, "job_end_files", ()) or ())
    logs = [work_dir / name for name in names if str(name).endswith(LOG_SUFFIX)]
    if not patterns or not logs or native.source is not None or any(p.exists() for p in logs):
        return None
    matched: list[Path] = []
    for pattern in patterns:
        # A pattern this point cannot fill matches nothing, as a pattern with no file does.
        glob, _ = _profile_glob("job_end_files", pattern, _glob_values(record, point))
        found = sorted(work_dir.glob(glob)) if glob is not None else []
        if not any(path.is_file() for path in found):
            return None
        matched += [path for path in found if path.is_file()]
    tails = [
        f"--- last {JOB_END_TAIL_LINES} lines of {path.name} ---\n"
        + "\n".join(_tail_lines(path, JOB_END_TAIL_LINES))
        for path in matched
    ]
    error = (
        f"the job ended without its solver log: {', '.join(p.name for p in matched)} exist "
        f"(job_end_files of the HPC profile) and {', '.join(p.name for p in logs)} does not "
        "(FR-311).\n" + "\n".join(tails)
    )
    failed = record.model_copy(update={"status": RunStatus.FAILED_EXECUTION, "error": error})
    workspace.complete_submitted_record(failed)
    return failed
