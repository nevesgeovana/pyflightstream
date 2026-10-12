"""The run record read as the case the assessor judges: its point, outputs and datapoint name.

Pipeline role: a private module of :mod:`pyflightstream.run`, below
:mod:`pyflightstream.run.collect` and :mod:`pyflightstream.run._assemble`, which
both judge a recorded point with :class:`~pyflightstream.run.LoadsAssessor`.
It holds the three things that reading needs and neither stage may import
from the other: the outputs a submission declared, the datapoint folder a
record names, and the shim that carries both to the assessor.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream.workspace import RunRecord
from pyflightstream.workspace.naming import datapoint_name_of


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
    # its `run_id` in the tag, which is what `pyfs-matrix rename` reads it by,
    # so the record carries its own cross-check and only had to be asked.
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
