"""Small steps of the collect of a submitted job: its log note, its refused points, its clock.

Pipeline role: the private helpers :mod:`pyflightstream.run.collect` calls
while it completes a job or a sweep of points. Each is one named step with no
state of its own, kept apart so the collect module stays readable. The last three
things in it read a recorded point as the case the assessor judges: the outputs a
submission declared, the datapoint folder a record names, and the shim that carries
both to :class:`~pyflightstream.run.LoadsAssessor`.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run._step_exports import untranslated_surfaces

from ..workspace import MissingOutputsError, RunRecord, RunStatus
from ..workspace.naming import datapoint_name_of


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
    """Null a point's wall time where its solver log is absent, and say why (FR-861).

    The solver clock is the log's, and a time is never estimated. The basis
    says so too (PFS-2103.007): it still named the clock file the nulled time
    had been measured from.
    """
    update["wall_time_s"] = None
    submission = update.get("submission")
    job = submission.get("job") if isinstance(submission, dict) else None
    if isinstance(job, dict):
        job["wall_time_basis"] = (
            "not recorded: the solver log is absent (FR-861), and the solver "
            "clock is the log's; a time is never estimated"
        )


def limit_for_its_word(update: dict[str, object]) -> None:
    """Keep ``iterations_requested`` only where the FINAL status is MAX_ITER_REACHED (FR-974).

    The assessor stamps the limit with its own verdict; the log verdicts and the
    walltime stop that may replace that verdict come after it, so the field is
    settled on the status the record is written with.
    """
    if update.get("status") != RunStatus.MAX_ITER_REACHED:
        update["iterations_requested"] = None


def _declared_outputs(record: RunRecord) -> list[str]:
    """Return the output names the submitted point was built to write.

    THEY COME OFF THE RECORD AND NOT OFF THE MATRIX, deliberately. A
    collector that re-read the matrix would read whatever the matrix says
    NOW, and a matrix edited between the submission and the collection is
    exactly the shape that made a recorded REmi of 11.7716754 read back as
    99.0 in a regenerated product (GEO-039-F02). The submission block
    carries what was declared at the moment the job was handed over.
    """
    submission = record.submission or {}
    declared = submission.get("declared_outputs")
    if isinstance(declared, (list, tuple)):
        return [str(name) for name in declared]
    return []


def _datapoint_of(record: RunRecord) -> str | None:
    """Return the datapoint folder's NAME for this record's outputs, or None.

    The name the run RECORDED when it has one. When it does not -- every record
    written before 0.21.0 -- the folder the record's own submission block says
    the job ran in, which is read rather than recomputed: a name recomputed now
    would file the outputs where no record of them points, and that is the thing
    to avoid. None when the record names neither, which is a point submitted
    before 0.18.1, whose job ran in the simulation folder.

    ONE HOME, because the two callers must not disagree. `_recorded_name`
    refuses when this is None and the assessor's shim carries the None through,
    and when they disagreed the shim fell into the branch written for a real
    case and asked it for a field only a case has.
    """
    if record.point_name:
        return record.point_name
    # THE FOLDER NAME IS READ BY THE MODULE THAT WRITES IT, which answers None
    # for anything that is not a point's folder rather than raising an error
    # this sweep's handler does not catch (the architect lens, FIX-0211).
    #
    # WHAT THIS DOES NOT CHECK, stated because the same field is read twice in
    # this module with two different trust models: `_working_dir` resolves
    # `working_dir` and REFUSES one that is not a direct child of this record's
    # own `datapoints/`, and it runs before this on the collecting path. This
    # reads the name only and is not itself that check.
    ran_in = datapoint_name_of(Path(str((record.submission or {}).get("working_dir") or "")).name)
    if ran_in is None:
        return None
    # AND IT IS THIS RECORD'S FOLDER, not merely a datapoint folder of this
    # simulation. `_working_dir` checks the second and not the first, so an
    # edited `working_dir` naming ANOTHER point's folder was refused for a
    # record that carries a point name and accepted for one that does not --
    # this release's own records (the qa lens, FIX-0211). A 0.20.x record ends
    # its `run_id` in the tag, so the record carries its own cross-check.
    tail = str(record.run_id).rsplit("/", 1)[-1]
    return str(ran_in) if tail in ("", str(ran_in)) else None


class _RecordAsCase:
    """The two fields the standard assessor reads, taken off the run record.

    NOT A SimCase AND NOT PRETENDING TO BE ONE. :class:`LoadsAssessor` reads
    exactly three things from its first argument: ``point``, ``outputs``, and
    the flight condition it binds the export against, and both of the first
    two are recorded on the row at submission from the case that produced it.
    So the values here are the RUN'S OWN, carried across, and nothing is
    invented.

    The assessor accepts ``None`` in this position and documents what happens
    then: the condition binding is recorded as EMPTY rather than as agreement.
    Passing the record's real point instead is what makes the binding a
    comparison rather than a blank, which is the whole reason this exists
    rather than a bare ``None``.
    """

    __slots__ = ("point", "outputs", "velocity", "datapoint_name", "recipe")

    def __init__(self, record: RunRecord, *, velocity_is_the_point_s: bool = True) -> None:
        self.point = dict(record.point or {})
        # 0.21.0: the folder the assessor judges is named by the name the run
        # RECORDED, never recomputed from a record that is not a case. 0.21.1:
        # a record written before 0.21.0 recorded no name and names its folder
        # in its submission block instead, and reading it here is what keeps
        # the assessor out of the branch that would ask this shim for a field
        # only a real case has.
        self.datapoint_name = _datapoint_of(record)
        self.outputs = list(record.outputs or _declared_outputs(record))
        # THE VELOCITY THE RUN REQUESTED, which the record has carried since
        # OPS-2009.01.13 and which this read as None until 0.24.0, calling None
        # the honest answer. It was not: a local point whose export printed
        # 30 m/s against a requested 80 is FAILED_INCOMPLETE_OUTPUT, and the
        # same files collected from a cluster were CONVERGED, because nothing
        # here asked. The two paths claim one judgement and now make it.
        #
        # None still, in the one place the record cannot answer: a POINT OF A
        # JOB that sweeps a flow variable. The job's record carries the row's
        # velocity and not that point's, and holding a point to another
        # point's speed would refuse a correct export. Unasked is recorded as
        # unasked there, which rule 3 of `_bind_case_conditions` exists for.
        self.velocity = record.velocity_requested_m_s if velocity_is_the_point_s else None
        # 0.31.0: the run type the record states, which the assessor reads to
        # know a quasi-steady point (its record is judged per clocking).
        self.recipe = record.recipe
