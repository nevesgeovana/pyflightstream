"""Small steps of the collect of a submitted job: its log note, its refused points, its clock.

Pipeline role: the private helpers :mod:`pyflightstream.run.collect` calls
while it completes a job or a sweep of points. Each is one named step with no
state of its own, kept apart so the collect module stays readable.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run._step_exports import untranslated_surfaces

from ..workspace import MissingOutputsError, RunRecord, RunStatus


def job_log_note(job_log: Path | None, sim_dir: Path) -> tuple[str | None, str | None]:
    """Return the note and the text of the job's one log, both None without a job log."""
    job_note: str | None = None
    job_log_text: str | None = None
    if job_log is not None:
        where = (
            job_log.relative_to(sim_dir).as_posix() if job_log.is_relative_to(sim_dir) else job_log
        )
        job_note = (
            "no solver log of its own: this machine's HPC profile states export_log = false, so "
            f"the job's one log is the scheduler's, filed as {where} in the simulation folder, "
            "where the job ran; each point is judged from its loads export"
        )
        if job_log.is_file():
            job_log_text = job_log.read_text(encoding="utf-8", errors="replace")
    return job_note, job_log_text


def note_untranslated(
    tag: str,
    error: MissingOutputsError,
    owned: Sequence[Any],
    record: RunRecord,
    *,
    job_warnings: list[str],
    refused: dict[str, str],
) -> None:
    """Refuse the point, or warn when all it misses is the package's own translation."""
    owned_names = {str(name) for name in owned}
    untranslated = untranslated_surfaces(
        [
            entry
            for entry in record.surface_translations or []
            if isinstance(entry, Mapping) and str(entry.get("dat")) in owned_names
        ],
        error.missing,
        error.collected,
    )
    if untranslated is None:
        refused[tag] = str(error)
    else:
        for line in untranslated:
            if f"{tag}: {line}" not in job_warnings:
                job_warnings.append(f"{tag}: {line}")
            warnings.warn(f"{tag}: {line}", PyflightstreamWarning, stacklevel=3)


def refused_entry(tag: str, point: dict, outputs: list[str] | None) -> dict[str, object]:
    """Return the ``points_ran`` entry of a point of a job whose outputs were refused."""
    entry: dict[str, object] = {
        "tag": tag,
        "point": point,
        "status": str(RunStatus.FAILED_INCOMPLETE_OUTPUT),
    }
    if outputs:
        entry["outputs"] = list(outputs)
    return entry


def is_a_sweep_job(record: RunRecord) -> bool:
    """Whether the record carries a job's per-point mapping, even for one point."""
    by_point = (record.submission or {}).get("declared_by_point")
    return isinstance(by_point, Mapping) and bool(by_point)


def no_time_without_the_log(update: dict[str, object]) -> None:
    """Null a point's wall time where its solver log is absent, and say why (FR-413 R2).

    The solver clock is the log's, and a time is never estimated. The basis
    says so too (PFS-2103.007): it still named the clock file the nulled time
    had been measured from.
    """
    update["wall_time_s"] = None
    submission = update.get("submission")
    job = submission.get("job") if isinstance(submission, dict) else None
    if isinstance(job, dict):
        job["wall_time_basis"] = (
            "not recorded: the solver log is absent (FR-413 R2), and the solver "
            "clock is the log's; a time is never estimated"
        )


def limit_for_its_word(update: dict[str, object]) -> None:
    """Keep ``iterations_requested`` only where the FINAL status is MAX_ITER_REACHED (FR-434 R1).

    The assessor stamps the limit with its own verdict; the log verdicts and the
    walltime stop that may replace that verdict come after it, so the field is
    settled on the status the record is written with.
    """
    if update.get("status") != RunStatus.MAX_ITER_REACHED:
        update["iterations_requested"] = None
