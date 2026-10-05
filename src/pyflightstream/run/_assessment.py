"""Judging solver quality from the outputs of a run.

Private to :mod:`pyflightstream.run`, which re-exports every public name
of it. :class:`OutcomeAssessor` is the protocol the campaign loop takes;
:class:`LoadsAssessor` is its standard implementation on the anchor-based
parsers of :mod:`pyflightstream.results`, with the residual and the
clocking judgments of a quasi-steady rotor beside it, and
:func:`worse_of` orders two run statuses by severity.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pyflightstream.cases import (
    SimCase,
    point_name,
)
from pyflightstream.cases.qsteady import (
    QsteadyClocking,
    QsteadyRecordError,
    read_qsteady_record,
)
from pyflightstream.cases.qsteady import record_file_name as qsteady_record_file_name
from pyflightstream.cases.workflows import (
    QSTEADY_ROTOR,
)
from pyflightstream.results import (
    SOLVER_MODES,
    IncompleteOutputError,
    LoadsReport,
    ResidualSample,
    classify_solver_mode,
    frozen_time_steps,
    parse_loads,
    parse_log_times,
    parse_residual_history,
    parse_residual_solves,
)
from pyflightstream.results.conditions import ConditionBinding, bind_conditions
from pyflightstream.run._executors import (
    ExecutionResult,
)
from pyflightstream.run._wake_edge_verdict import (
    reads_as_residual_history,
)
from pyflightstream.versions import FsVersion
from pyflightstream.workspace import (
    LEGACY_SIM_OUTPUTS_DIR,
    SIM_DATAPOINTS_DIR,
    SIM_OUTPUTS_DIR,
    RunStatus,
    datapoint_dir_name,
)
from pyflightstream.workspace.naming import (
    PointName,
)


@dataclass(frozen=True)
class Assessment:
    """Judgment of one successfully executed point.

    Attributes
    ----------
    status : RunStatus
        ``CONVERGED``, ``COMPLETED_MAX_ITER``, or ``FAILED_DIVERGED``;
        execution and completeness failures are decided by the loop
        before the assessor runs.
    iterations : int, optional
        Solver iterations reached, when the assessor parsed them.
    residual : float, optional
        Final residual, when parsed.
    error : str, optional
        Explanation for a diverged judgment.
    fs_version_reported : str, optional
        Version string printed in the assessed output, verbatim
        (FR-18).
    fs_build : str, optional
        Build number printed in the assessed output.
    conditions : list of dict, optional
        The operating-point binding, one entry per requested axis the
        export prints back: ``axis``, ``requested``, ``reported``,
        ``deviation``, ``tolerance``, ``unit`` and ``within``
        (REV010-001). Empty when the assessor had no case to compare
        against; ``None`` when the assessor does not perform the
        comparison at all. Recorded on EVERY outcome rather than only
        on a refusal, because "checked and agreed" and "never checked"
        are different claims about a result and a later reader cannot
        otherwise tell them apart.
    log_file_used : str, optional
        Name of the solver log the residual verdict was read from, or
        None where none was read and the judgment fell to the iteration
        count. Recorded because the two are DIFFERENT CLAIMS about a
        result: an unsteady point with no log is recorded
        ``COMPLETED_MAX_ITER`` whatever the solver did, and a later
        reader of the manifest cannot otherwise tell that from a point
        whose residuals were actually read and missed the threshold.

        IT REACHES THE MANIFEST, which is the whole point of it and was
        not true of the first version: the field was populated on the
        assessment and dropped at the RunRecord boundary, so the reader
        it names still could not tell the two apart.
    residual_note : str, optional
        Where a final residual did not fit its printed field and was read
        from an earlier iteration instead, which column, which iteration
        and what value; None where every final residual was printed.
    solver_run_time_s, solver_initialization_s, time_steps : optional
        The solver's own run time and initialization time in seconds and the
        time steps of an unsteady run, read from the log the verdict read;
        None where no log was read or it prints no such line.
    clocking_verdicts : list of dict, optional
        A quasi-steady rotor wheel solved at several clockings (0.30.0): one
        entry per clocking, in the order the run solved them, with its
        ``index``, ``clocking_deg``, ``status``, ``iterations``, ``residual``
        and, where it has one, ``note`` or ``error``, each judged from that
        clocking's own solve in the one log the run exports. The point's
        ``status``, ``residual`` and ``iterations`` are then the worst case:
        the worst status, the largest final residual, and the iterations of
        clocking 0, the solve its loads export is of. None on every other
        point.
    warnings : list of str, optional
        What the judgment could not use and did without, for the point's
        record's ``warnings`` (0.31.0): a quasi-steady point whose record
        cannot be read (:class:`~pyflightstream.cases.qsteady.QsteadyRecordError`)
        has its solver log judged as one solve, and says so here. None where
        there is nothing to say.
    """

    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    error: str | None = None
    fs_version_reported: str | None = None
    fs_build: str | None = None
    conditions: list[dict] | None = None
    log_file_used: str | None = None
    residual_note: str | None = None
    solver_run_time_s: float | None = None
    solver_initialization_s: float | None = None
    time_steps: int | None = None
    clocking_verdicts: list[dict[str, object]] | None = None
    warnings: list[str] | None = None


def _bind_case_conditions(case: SimCase | None, report: LoadsReport) -> ConditionBinding:
    """Compare the point a case requested against the one an export printed.

    Parameters
    ----------
    case : SimCase or None
        The requested point. None means there is nothing to compare
        against, which the campaign loop never produces: it fills
        :attr:`SimCase.point` before the assessor runs. It reaches here
        only when :class:`LoadsAssessor` is called directly on a file,
        and the empty binding that results is recorded as empty rather
        than as agreement.
    report : LoadsReport
        The parsed export.

    Returns
    -------
    ConditionBinding
        Every comparable field with its deviation and decision.

    Notes
    -----
    WHICH SUPPLIED VELOCITY WINS, stated here because this is the one
    function that applies the rule and it was previously written nowhere
    (OPS-2009.01.04). Free-stream velocity can arrive from two places at
    once and the order is:

    1. ``case.point["velocity"]``, the value of THIS point, wins;
    2. :attr:`~pyflightstream.cases.SimCase.velocity`, the case default,
       fills in when the point supplies none;
    3. neither: nothing is requested, which is not the same as zero, and
       the binding records the axis as unasked rather than as agreed.

    ``setdefault`` is what encodes 1 over 2. A plain assignment reads
    identically at the call site and reverses the order, and nothing
    else in the package would notice: the campaign would run at one
    speed and the record would claim another.

    TWO SUPPLY POINTS ARE DELIBERATELY OUTSIDE THIS RULE. A sweep cannot
    emit a velocity at all today: :meth:`SweepAxis.points` yields alpha,
    beta and advance_ratio only, so step 1 is reachable only by a caller
    that fills ``point`` itself, and a test pins that reading rather
    than presenting the branch as campaign-reachable. And
    :attr:`~pyflightstream.cases.ReferenceData.velocity` is the
    COEFFICIENT reference velocity, read by no library code and passed
    to the solver only by a user recipe through
    :func:`pyflightstream.script.helpers.solver_settings`; the library
    holds no precedence over it and states none.
    """
    if case is None:
        return ConditionBinding()
    requested: dict[str, float] = {
        axis: value for axis, value in case.point.items() if value is not None
    }
    if case.velocity is not None:
        requested.setdefault("velocity", case.velocity)
    return bind_conditions(requested, reported=report)


class OutcomeAssessor(Protocol):
    """Judges solver quality from the outputs of one executed point.

    The campaign loop already handled execution failure and missing
    declared outputs; the assessor inspects the collected outputs (in
    ``sim_dir / "outputs"``, and in ``sim_dir / "raw"`` where a workspace
    written before 0.16.0 holds one, FR-84) and decides between
    converged, iteration limited, and diverged. The standard
    implementation lands with the results parsers.
    """

    def __call__(self, case: SimCase, execution: ExecutionResult, sim_dir: Path) -> Assessment:
        """Return the judgment of one executed point."""
        ...


def _read_loads(path: Path, requested_version: str | FsVersion | None):
    """Parse one collected file as a loads table, or say why not."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return parse_loads(text, requested_version=requested_version), None
    except (OSError, IncompleteOutputError, ValueError) as error:
        return None, str(error)


class LoadsAssessor:
    """The standard solver-quality judgment, built on the run outputs.

    Reads the collected loads spreadsheet and, when available, the
    exported solver log. It produces four of the six terminal statuses:
    CONVERGED, COMPLETED_MAX_ITER and FAILED_DIVERGED when it can judge
    the run, and FAILED_INCOMPLETE_OUTPUT when it cannot. The Notes
    below list every case in the last group and say why they share one
    status.

    - NaN or infinite Total coefficients: FAILED_DIVERGED.
    - A native log with consecutive frozen time steps: FAILED_DIVERGED.
    - With a log: the final velocity and pressure residuals against
      the run's convergence limit (SRC-003 p.200). A NaN or infinite
      residual in EITHER column is a divergence, judged before the two
      are combined: reducing them first cannot preserve the invalidity
      of one of them.
    - Without a log, steady mode: an iteration counter below the
      requested limit means the threshold stopped the solver
      (CONVERGED); reaching the limit means COMPLETED_MAX_ITER. Unless
      the run forced all iterations, which disables that threshold: an
      early stop is then a refusal, because the one mechanism that
      could have ended the loop legitimately was off (PYFS-008).
    - Without a log, unsteady mode: the time loop always runs to its
      prescribed end, so completion is recorded as
      COMPLETED_MAX_ITER. EXPORTING a log is what changes that; naming
      it is not required, because a collected file that parses as a
      residual history is found by content.

    Parameters
    ----------
    loads_file : str, optional
        Name of the loads spreadsheet among the collected outputs, by
        file name (any directory part of the declared name is dropped
        by collection). None, the default, finds the collected output
        that parses as a loads table, the same rule
        :func:`pyflightstream.results.tables.parse_run_loads` uses on the
        manifest: a swept case names its outputs per point
        (``loads_{point}.txt``), so no single literal could name them
        all, and the content is what identifies the file anyway.
    log_file : str, optional
        Name of the exported solver log (EXPORT_LOG). None, the default,
        finds the collected output that parses as a residual history,
        the same rule ``loads_file`` follows and for the same reason: a
        swept case names its outputs per point, so no single literal
        could name them all.

        NAMING IT IS STRICTER, not weaker: a named file that was not
        collected is a refusal, while the default falls back to the
        iteration-count judgment when nothing parses. Name it when the
        run must not be judged without residuals.
    requested_version : str or FsVersion, optional
        Version the campaign requested; enables the FR-18 cross-check
        against the version printed in the loads footer.

    Notes
    -----
    Every refusal carries ``FAILED_INCOMPLETE_OUTPUT``, and that is a
    constrained choice rather than the right name for each of them. The
    terminal set is closed at six values, and it was resolved on
    2026-08-03 that it stays closed: FR-46 holds and FR-37 closes as
    covered, so there is no seventh value meaning "the solver ran and
    this package cannot judge the result".

    The reason this one is chosen is asymmetric rather than aesthetic.
    Every other available status describes an outcome the solver
    reached, so any of them would make a point nobody judged
    indistinguishable from a point that passed. Over-reporting
    incompleteness costs a re-run; under-reporting it publishes a
    number.

    Read ``COMPLETED_MAX_ITER`` with the same care. It is not a success
    value here: it says the solver reached its iteration cap, which is
    one of the two ways of not converging. The other, a non-finite
    residual, is ``FAILED_DIVERGED``. ``CONVERGED`` is the only status
    this assessor gives to a run that met its threshold.

    The refusals, in the order they are tested:

    1. The file named by ``loads_file`` is not among the collected
       outputs. The error lists what was collected, because the usual
       cause is a swept case whose recipe names its outputs per point.
    2. No ``loads_file`` was named and no single collected output reads
       as a loads table, either because none parses or because several
       do. Choosing one would be a guess about which point ran.
    3. The loads spreadsheet is unparseable or truncated.
    4. The export is evidence of a different operating point from the
       one the case requested, beyond tolerance (REV010-001).
    5. The loads footer prints a solver mode this package has not been
       taught (REV010-002).
    6. The file named by ``log_file`` is not among the collected
       outputs; or ``log_file`` was not named and SEVERAL collected
       outputs parse as a residual history, because choosing one would
       be a guess about which is this point's. Zero candidates is not a
       refusal: it is the iteration-count judgment, which is what every
       campaign that exports no log has always received.
    7. The solver log is present but no residual history can be read
       from it.
    8. Steady mode with all iterations forced, and the solver stopped
       early (PYFS-008), as described above.

    Items 4 and 5 are new at v0.4.0 and both replace a path that used
    to end in a SUCCESS, which is what makes them worth stating here
    rather than only in the changelog. Item 4 ran as CONVERGED on a
    valid export belonging to another case: nothing about such a file
    is malformed, so no parser guard could ever have seen it. Item 5
    fell through to the unsteady branch and returned
    COMPLETED_MAX_ITER with no error, so a mode this package had never
    seen became a successful terminal state.

    Item 4 is also tested BEFORE divergence, deliberately. Divergence
    is a physical outcome, and attributing one to a case that never
    produced the file is a worse error than reporting that the evidence
    could not be matched to the case.

    Examples
    --------
    The assessor is built once per campaign and handed to the loop, which
    calls it for each executed point; building it reads nothing:

    >>> from pyflightstream.run import LoadsAssessor
    >>> assess = LoadsAssessor(log_file="solver_log.txt")
    >>> (assess.loads_file, assess.log_file, assess.requested_version)
    (None, 'solver_log.txt', None)
    """

    def __init__(
        self,
        loads_file: str | None = None,
        *,
        log_file: str | None = None,
        requested_version: str | FsVersion | None = None,
    ):
        self.loads_file = loads_file
        self.log_file = log_file
        self.requested_version = requested_version

    def __call__(self, case: SimCase, execution: ExecutionResult, sim_dir: Path) -> Assessment:
        """Judge one executed point from its collected outputs."""
        judgment = _LoadsJudgment(assessor=self, case=case, sim_dir=sim_dir)
        if (assessment := _find_assessment_outputs(judgment)) is not None:
            return assessment
        if (assessment := _read_assessment_loads(judgment)) is not None:
            return assessment
        if (assessment := _validate_assessment_loads(judgment)) is not None:
            return assessment
        if (assessment := _find_assessment_log(judgment)) is not None:
            return assessment
        if (assessment := _judge_assessment_log(judgment)) is not None:
            return assessment
        return _judge_assessment_iterations(judgment)


@dataclass(kw_only=True)
class _LoadsJudgment:
    """Inputs and phase results of one ordered execution."""

    assessor: LoadsAssessor
    case: SimCase
    sim_dir: Path
    collected: list[Path] = field(init=False)
    report_path: Path = field(init=False)
    report: LoadsReport = field(init=False)
    stamp: dict[str, Any] = field(init=False)
    mode: str | None = field(init=False)
    stopped_early: bool = field(init=False)
    log_path: Path | None = field(init=False)
    clockings: tuple[QsteadyClocking, ...] | None = field(init=False)


def _find_assessment_outputs(job: _LoadsJudgment) -> Assessment | None:
    """Find assessment outputs."""
    # THE POINT'S OWN FOLDER, OR THE TWO A CAMPAIGN WROTE INTO BEFORE
    # 0.16.0, AND NEVER BOTH (FR-92). A point collects into
    # `datapoints/DP-<point>/` since this release, so what is there is
    # that point's evidence and nothing else; `outputs/` held every
    # point of the simulation at once, and `raw/` was its name before
    # 0.16.0. A workspace recorded under an older layout must keep
    # every one of its points, so both are still read -- but ONLY
    # where the point has no folder of its own. Mixing them would put
    # a sweep's shared folder back beside the point's own, which is
    # what this layout exists to prevent.
    #
    # The `break` below therefore ranks nothing on the first branch,
    # which holds one folder; it ranks `outputs/` before `raw/` on the
    # legacy branch, where a workspace can hold both.
    # `case` is None where a caller judges a folder directly rather
    # than a point, which the unit tests do and which is why this
    # reads through getattr like the declared-outputs narrowing below.
    point = getattr(job.case, "point", None)
    # `if point` and not `is not None`: an EMPTY mapping has no folder to
    # be judged from, and it cannot reach here carrying evidence anyway,
    # because `collect_outputs` refuses it before anything is moved.
    # 0.21.0: a record carried across as a case names its folder by the name
    # the run recorded; a real case is named by `point_name`.
    recorded_name = getattr(job.case, "datapoint_name", None)
    if recorded_name:
        own_name: str | None = datapoint_dir_name(PointName(recorded_name))
    elif point and hasattr(job.case, "condition_order"):
        # A REAL CASE, asked by what only a case has, and not by whether a
        # name happened to be recorded. 0.21.1: a record carried across as a
        # case can reach here with NO recorded name -- a 0.20.x swept row
        # carries neither a point name nor a working directory, because the
        # whole sweep was one job in the simulation folder -- and it then
        # fell into this branch and raised AttributeError on
        # `condition_order`. That is not a WorkspaceError, so the collecting
        # sweep does not catch it and one such record aborts the collection
        # of every other point in the workspace (the qa lens, FIX-0211).
        own_name = datapoint_dir_name(PointName(point_name(job.case, point)))
    else:
        # No name recorded and nothing that can compute one: the point is
        # judged from the simulation folder, as it was before 0.21.0.
        own_name = None
    own = None if own_name is None else Path(job.sim_dir) / SIM_DATAPOINTS_DIR / own_name
    # THE PREDICATE IS EXISTENCE AND NOT EMPTINESS, and the difference
    # is a wrong answer (the architecture and verification lenses,
    # 2026-09-11). A point whose folder EXISTS is judged from that
    # folder whatever is in it: an empty one earns this point's own
    # refusal. Falling through to the shared folder because the
    # point's own was empty is how a point whose collection failed
    # got judged on ANOTHER point's export.
    #
    # MEASURED, because on an alpha sweep the operating-point binding
    # below hides it: a loads export prints alpha, beta and velocity
    # and NEVER prints the advance ratio, so on a J sweep the binding
    # cannot tell two points apart, and the point at J=1.7 was
    # recorded CONVERGED on the export of J=1.3 in silence. That is
    # the defect REV010-001 exists against, re-entered by a new door.
    folders = (
        [f"{SIM_DATAPOINTS_DIR}/{own_name}"]
        if own is not None and own.is_dir()
        else [SIM_OUTPUTS_DIR, LEGACY_SIM_OUTPUTS_DIR]
    )
    job.collected = []
    for folder in folders:
        found = sorted(
            (path for path in (Path(job.sim_dir) / folder).glob("*") if path.is_file()),
            key=lambda path: path.name,
        )
        if found:
            job.collected = found
            break
    # THE POINT'S OWN OUTPUTS, when the case declares them. This
    # narrowed a SHARED folder to the files this point declared, and
    # it is kept for the older layouts above, where the folder is
    # still shared. In a datapoint folder it selects everything and
    # changes nothing. A case that declares no outputs is judged over
    # the whole folder.
    declared = {Path(name).name for name in getattr(job.case, "outputs", None) or ()}
    if declared:
        own_outputs = [path for path in job.collected if path.name in declared]
        if own_outputs:
            job.collected = own_outputs
    return None


def _read_assessment_loads(job: _LoadsJudgment) -> Assessment | None:
    """Read assessment loads."""
    if job.assessor.loads_file is not None:
        wanted = Path(job.assessor.loads_file).name
        found = [path for path in job.collected if path.name == wanted]
        if not found:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                error=(
                    f"no collected output named {wanted!r} to judge; collected: "
                    f"{', '.join(path.name for path in job.collected) or 'nothing'}. The "
                    "name must match the file the recipe exported, or leave "
                    "LoadsAssessor() unnamed to judge whichever output parses as a "
                    "loads table"
                ),
            )
        job.report_path = found[0]
        job.report, error = _read_loads(found[0], job.assessor.requested_version)
        if job.report is None:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                error=f"loads spreadsheet {wanted!r} unusable: {error}",
            )
    else:
        usable = [
            (path, report)
            for path, (report, _) in (
                (path, _read_loads(path, job.assessor.requested_version)) for path in job.collected
            )
            if report
        ]
        if len(usable) > 1:
            # A WORKSPACE RECORDED BEFORE 0.16.0 SHARES ONE FOLDER
            # between the points of a case, so from the second point
            # onward every earlier point's export is still sitting
            # there and parses just as well. Points collected under
            # this release each have their own folder (FR-92) and
            # never reach here. Ask REV010-001's binding,
            # thirty lines below, which of them the solver actually ran at
            # THIS point's conditions: a loads export prints the alpha,
            # the sideslip and the velocity it ran, so the file that
            # belongs to this point identifies itassessor.
            #
            # THIS IS NOT A RELAXATION. Where the binding does not settle
            # it -- none match, or several do -- the refusal below stands
            # exactly as it was, because attributing another point's
            # result to this one is the defect REV010-001 exists against
            # and it is worse than refusing. Naming the file cannot fix
            # this and never could: the message used to offer that, forty
            # lines under the sentence saying no literal names them all on
            # a swept case.
            mine = [
                (path, report)
                for path, report in usable
                if not _bind_case_conditions(job.case, report).mismatches
            ]
            if len(mine) == 1:
                usable = mine
        if len(usable) != 1:
            names = ", ".join(path.name for path in job.collected) or "nothing"
            reason = "none of them parses" if not usable else "several of them parse"
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                error=(
                    f"no single collected output reads as a loads table ({reason}); "
                    f"collected: {names}. Each point collects into its own "
                    f"{SIM_DATAPOINTS_DIR}/ folder since 0.16.0, so this folder "
                    "should hold one point's exports: either the point exported "
                    "no loads spreadsheet, or it exported several. A workspace "
                    "recorded before 0.16.0 shares one folder between the points "
                    "of a case, and there this assessor keeps the export whose "
                    "printed conditions match the point it is judging; reaching "
                    "here means none of them did, or more than one did. Naming a "
                    "file is not offered as a remedy: a swept case names its "
                    "outputs per point, so no single literal names them all. "
                    "Check what this point exported, or judge the row from Python "
                    "with an assessor that knows which file is which"
                ),
            )
        job.report_path = usable[0][0]
        job.report = usable[0][1]
    # REV010-001, the check whose absence let a converged result for one
    # flight condition be recorded as the evidence of another. The
    # assessor received `case` and never read it, so a valid, complete,
    # genuinely converged export printing alpha=2 deg was accepted as
    # CONVERGED for a point requesting alpha=0 deg. Nothing about that
    # file is malformed, which is exactly why no parser guard could see
    # it. The tabular layer already had the comparison and the manifest
    # never consults it, so the status was authorized long before
    # anything disagreed.
    #
    # It runs FIRST, before divergence and before the mode, because
    # those two judge a file that is assumed to be this run's evidence.
    # Calling a result diverged when it belongs to another point
    # attributes a physical outcome to a case that never produced it.
    # The binding rides in `stamp` so every outcome below carries it:
    # what was requested, what was printed, by how much they differ, and
    # whether that was accepted (REV010-001's closure asks for the
    # decision to be persisted, not just acted on).
    return None


def _validate_assessment_loads(job: _LoadsJudgment) -> Assessment | None:
    """Validate assessment loads."""
    binding = _bind_case_conditions(job.case, job.report)
    # A keyword bag for Assessment: values differ by key and the record
    # checks each one when it is built, hence ``Any``.
    job.stamp = {
        "fs_version_reported": job.report.fs_version_reported,
        "fs_build": job.report.fs_build,
        "conditions": binding.as_records(),
    }
    if binding.mismatches:
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            iterations=job.report.current_iteration,
            error=(
                "the collected export is evidence of a different operating "
                f"point than this run requested: {binding.describe()}. A loads "
                "export prints the conditions the solver actually ran, so this "
                "file is a valid result of another case rather than a bad "
                "result of this one. Each point collects into its own "
                "folder, so a later sweep point no longer overwrites a same "
                "named export there; give each point a uniquely named output "
                "anyway, because the post-processing products of a point are "
                "named after it and two points sharing it collide in the "
                "product tree"
            ),
            **job.stamp,
        )
    diverged = job.report.diverged_columns()
    if diverged:
        return Assessment(
            status=RunStatus.FAILED_DIVERGED,
            iterations=job.report.current_iteration,
            error=f"non-finite Total coefficients: {', '.join(diverged)}",
            **job.stamp,
        )
    # REV010-002. The mode decides WHICH judgment rule applies, so an
    # unrecognized one is checked before any rule is chosen, including
    # the residual path below. The old code tested for "steady" and let
    # everything else fall through to the unsteady branch, which returns
    # COMPLETED_MAX_ITER with error=None: a solver mode this package has
    # never seen became a successful terminal state, indistinguishable
    # from a genuine unsteady run. Failing closed here is the difference
    # between "we judged this" and "we did not recognize it".
    job.mode = classify_solver_mode(job.report.solver_mode)
    if job.mode is None:
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            iterations=job.report.current_iteration,
            error=(
                f"the loads footer prints solver mode {job.report.solver_mode.strip()!r}, "
                f"which is not one this package knows ({', '.join(SOLVER_MODES)}). The "
                "mode selects the judgment rule, so an unrecognized one means the "
                "export cannot be assessed rather than that it completed. Either the "
                "solver version prints a mode this package has not been taught, or "
                "the footer is malformed"
            ),
            **job.stamp,
        )
    job.stopped_early = (
        job.mode == "steady" and job.report.current_iteration < job.report.requested_iterations
    )
    # PYFS-008. The iteration-count judgment below reads an early stop
    # as "the convergence threshold stopped the solver", and that
    # inference holds only while the threshold is what can stop it.
    # SOLVER_SET_FORCED_ITERATIONS turns the threshold off: the solver
    # is told to run the full budget whatever the residual does. So
    # under forced iterations an early stop means the opposite of
    # convergence, because the one mechanism that could legitimately
    # end the loop early was disabled. The field was parsed
    # (LoadsReport.forced_iterations) and never consulted, so a run
    # that stopped at 312 of a forced 500 was published CONVERGED,
    # indistinguishable from one that met the threshold at 312.
    #
    # BEFORE THE LOG, since 0.24.0. This check sat below the log branch,
    # which returns, so a collected log turned the refusal into
    # COMPLETED_MAX_ITER or CONVERGED: a residual says how far the
    # iteration it was printed at had come, and says nothing about the
    # iterations a run that was told to do all of them never did.
    # Completeness is established first and the residual judged after.
    if job.stopped_early and job.report.forced_iterations:
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            iterations=job.report.current_iteration,
            error=(
                f"the solver stopped at iteration {job.report.current_iteration} of "
                f"{job.report.requested_iterations} with forced iterations enabled, "
                "so the convergence threshold was not what ended the loop: it "
                "was disabled. The loads file describes an unfinished solve. "
                "A solver log, which is found by content and does not have to be "
                "named, does not change this: a residual cannot stand in for "
                "iterations that were required and not run. Find why the solver "
                "stopped"
            ),
            **job.stamp,
        )
    return None


def _find_assessment_log(job: _LoadsJudgment) -> Assessment | None:
    """Find assessment log."""
    job.log_path = None
    # A QUASI-STEADY WHEEL SOLVED AT k CLOCKINGS exports ONE log holding its
    # k solves in sequence, each counter starting at 1 (L1 of 0.30.0,
    # RPT-091): the run's own record beside the loads export says so, and
    # the log is then read and judged solve by solve.
    job.clockings, record_warning = _wheel_clockings(
        job.report_path, quasi_steady=None if job.case is None else job.case.recipe == QSTEADY_ROTOR
    )
    if record_warning is not None:
        # 0.31.0: THE RECORD'S ONE REFUSAL, decided here: the log is judged
        # as one solve, and the point's record says why.
        job.stamp["warnings"] = [record_warning]
    solves = 1 if job.clockings is None else len(job.clockings)
    if job.assessor.log_file is None:
        # AUTO-DETECTION BY CONTENT, on the same ground the loads
        # table is found by content: a swept case names its outputs
        # per point, so no literal could name them all, and a file
        # collected from THIS run's folder that parses as a residual
        # history is this run's solver log.
        #
        # WHAT THIS CHANGES, said plainly because it changes a
        # published status. Until now an unsteady run was recorded
        # COMPLETED_MAX_ITER unconditionally, since the time loop
        # always reaches its prescribed end and the iteration
        # counter therefore says nothing. That is a statement about
        # this package's evidence and it reads as a statement about
        # the solver: a run that converged at every time step and a
        # run that never converged at any came out with the same
        # word. A collected log settles it, and a run that exports
        # one should not have to be asked twice for permission to
        # use it. Nothing is auto-detected when no collected file
        # parses as a history, so a campaign that exports no log is
        # judged exactly as it was.
        #
        # Several candidates are NOT resolved by choosing: that
        # would be a guess about which is the log of this point.
        candidates = [
            path
            for path in job.collected
            if path != job.report_path and reads_as_residual_history(path, solves=solves)
        ]
        if len(candidates) == 1:
            job.log_path = candidates[0]
        elif len(candidates) > 1:
            # SEVERAL IS A REFUSAL, exactly as it is for the loads
            # table one branch up, and for the same reason: choosing
            # one would be a guess about which is the log of THIS
            # point. The first version fell through silently to the
            # iteration-count judgment, which is the verdict this
            # whole path exists to replace, so a campaign that had
            # gone to the trouble of exporting a log got the old
            # answer and no way to tell.
            names = ", ".join(path.name for path in candidates)
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                iterations=job.report.current_iteration,
                error=(
                    f"{len(candidates)} collected outputs read as a solver log "
                    f"({names}), so which one carries this point's residuals is a "
                    "guess. Name it with LoadsAssessor(log_file='<name>'), or give "
                    "each point a uniquely named log"
                ),
                **job.stamp,
            )
    if job.assessor.log_file is not None:
        wanted_log = Path(job.assessor.log_file).name
        matches = [path for path in job.collected if path.name == wanted_log]
        if not matches:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                error=(
                    f"no collected output named {wanted_log!r} to read residuals "
                    f"from; collected: "
                    f"{', '.join(path.name for path in job.collected) or 'nothing'}. A "
                    "solver log of a swept case carries the point in its name, so "
                    "name it as the recipe exported it, or drop log_file and accept "
                    "the iteration-count judgment"
                ),
                **job.stamp,
            )
        job.log_path = matches[0]
    return None


def _judge_assessment_log(job: _LoadsJudgment) -> Assessment | None:
    """Judge assessment log."""
    if job.log_path is not None:
        job.stamp["log_file_used"] = job.log_path.name
        log_text = job.log_path.read_text(encoding="utf-8", errors="replace")
        # 0.21.0: the times the log prints ride on every verdict read from it.
        times = parse_log_times(log_text)
        job.stamp["solver_run_time_s"] = times.solver_run_time_s
        job.stamp["solver_initialization_s"] = times.solver_initialization_s
        job.stamp["time_steps"] = times.time_steps
        if job.clockings is not None:
            return _judge_the_clockings(
                log_text, job.log_path, job.report, job.report_path, job.clockings, job.stamp
            )
        try:
            history = parse_residual_history(log_text)
            final = history[-1]
        except (IncompleteOutputError, ValueError) as exc:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                error=f"solver log unusable: {exc}",
                **job.stamp,
            )
        # THE LOG AND THE EXPORT END AT ONE ITERATION, OR THE LOG IS NOT
        # THIS EXPORT'S. A log is found by content or by name, and neither
        # says it belongs to the loads file beside it: an export of
        # iteration 312 was judged CONVERGED on the residual a log printed
        # at iteration 1575. Both files print the solver's own counter, and
        # the recorded pair of one run agrees on it, so a disagreement means
        # the residual describes a state the coefficients were not read at.
        if final.iteration != job.report.current_iteration:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                iterations=job.report.current_iteration,
                error=(
                    f"the solver log {job.log_path.name} ends at iteration "
                    f"{final.iteration} and the loads export {job.report_path.name} was "
                    f"written at iteration {job.report.current_iteration}, so the residual "
                    "is not the residual of the exported coefficients and no "
                    "convergence judgment is made from it. The log is of another "
                    "run or another point, or one of the two files was written "
                    "before the solve ended; export both at the end of the same solve"
                ),
                **job.stamp,
            )
        try:
            frozen = frozen_time_steps(log_text)
        except IncompleteOutputError as exc:
            # A residual block the solver stopped under is unusable
            # evidence at assessment time, the same verdict the residual
            # history gives above; it escaped as an exception once the
            # reader learned to call a cut a cut (0.26.0).
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                iterations=final.iteration,
                error=f"solver log unusable: {exc}",
                **job.stamp,
            )
        if frozen is not None:
            return Assessment(
                status=RunStatus.FAILED_DIVERGED,
                iterations=final.iteration,
                error=frozen.reason,
                **job.stamp,
            )
        judged = _judge_final_residuals(history, job.report.convergence_limit)
        if judged.note:
            job.stamp["residual_note"] = judged.note
        return Assessment(
            status=judged.status,
            iterations=final.iteration,
            residual=judged.residual,
            error=judged.error,
            **job.stamp,
        )
    return None


def _judge_assessment_iterations(job: _LoadsJudgment) -> Assessment:
    """Judge assessment iterations."""
    if job.mode == "steady":
        # forced_iterations is None when the loads footer does not print
        # the line; the count judgment then stands, because nothing says
        # the threshold was off. Stated rather than left implicit: the
        # falsy branch covers False and None, and they mean different
        # things.
        return Assessment(
            status=RunStatus.CONVERGED if job.stopped_early else RunStatus.COMPLETED_MAX_ITER,
            iterations=job.report.current_iteration,
            **job.stamp,
        )
    return Assessment(
        status=RunStatus.COMPLETED_MAX_ITER,
        iterations=job.report.current_iteration,
        error=None,
        **job.stamp,
    )


@dataclass(frozen=True)
class _ResidualJudgment:
    """The verdict one residual history's final row gives, with what it read."""

    status: RunStatus
    residual: float | None
    note: str | None
    error: str | None


def _judge_final_residuals(history: Sequence[ResidualSample], limit: float) -> _ResidualJudgment:
    """Judge one solve's final residuals against the convergence limit.

    CONVERGED within the limit, COMPLETED_MAX_ITER above it, FAILED_DIVERGED
    for a residual that is NaN or infinite; an overflowed field is read from
    its last printed value where that is within the limit, and the note says
    so.
    """
    final = history[-1]
    # PYFS-007. Every component is judged BEFORE they are combined,
    # and that order is the fix rather than a detail of it.
    #
    # This was `max(velocity, pressure)` followed by a NaN test on the
    # result. Python's max returns the first argument when the
    # comparison is False, and every comparison against NaN is False,
    # so max(9.6e-8, nan) is 9.6e-08: a NaN in the SECOND position was
    # swallowed and the test below it never fired. The point was then
    # published CONVERGED, carrying a residual that is not the residual
    # that decided it. The guard only ever worked when the NaN happened
    # to land in the velocity column.
    #
    # Infinity is the same class and was also wrong: inf <= limit is
    # False, so an infinite residual read as COMPLETED_MAX_ITER, which
    # says the solver ran out of iterations. It did not; it diverged.
    #
    # Reducing a set of numbers cannot be trusted to preserve the
    # invalidity of one of them, so validity is established first.
    components = {
        "velocity": final.velocity_residual,
        "pressure": final.pressure_residual,
    }
    # A FIELD TOO NARROW IS NOT A DIVERGENCE. The solver prints a run
    # of asterisks when a number does not fit its column, and on the
    # LAST row that turned a converged run into FAILED_DIVERGED: a
    # 26.100 rotor printed `*************` in the pressure column at
    # its final iteration, 1.15e-9 on the row before. The overflowed
    # column is read from its last printed value, and ONLY when that
    # value is already within the limit: a column that overflowed from
    # above the limit may have overflowed because it grew, so it stays
    # unjudged. What was read, and from which iteration, is recorded.
    notes: list[str] = []
    for name in sorted(final.overflowed):
        earlier = next(
            (
                (sample.iteration, getattr(sample, f"{name}_residual"))
                for sample in reversed(history[:-1])
                if name not in sample.overflowed
                and math.isfinite(getattr(sample, f"{name}_residual"))
            ),
            None,
        )
        if earlier is not None and earlier[1] <= limit:
            components[name] = earlier[1]
            notes.append(
                f"the {name} residual of iteration {final.iteration} did not fit its "
                f"printed field; read from iteration {earlier[0]}, {earlier[1]:.4g}"
            )
    nonfinite = [
        f"{name}={value!r}"
        for name, value in components.items()
        if value is None or not math.isfinite(value)
    ]
    if nonfinite:
        overflow = (
            f" The solver printed {', '.join(sorted(final.overflowed))} as a field "
            "of asterisks, and the last printed value of that column is not within "
            "the limit, so it may have overflowed because it grew."
            if final.overflowed
            else ""
        )
        return _ResidualJudgment(
            status=RunStatus.FAILED_DIVERGED,
            residual=None,
            note="; ".join(notes) or None,
            error=(
                "non-finite final residual(s): "
                f"{', '.join(nonfinite)}. A residual that is NaN or "
                "infinite is not a small number, so no convergence "
                "judgment can be made from it; the solver diverged or "
                "the log is corrupt at that iteration." + overflow
            ),
        )
    residual = max(components.values())
    converged = residual <= limit
    return _ResidualJudgment(
        status=RunStatus.CONVERGED if converged else RunStatus.COMPLETED_MAX_ITER,
        residual=residual,
        note="; ".join(notes) or None,
        error=None,
    )


#: The order of badness of a clocking's verdict, worst last: the worst of a
#: wheel's clockings is its point's status.
_CLOCKING_SEVERITY = (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER, RunStatus.FAILED_DIVERGED)


def _wheel_clockings(
    loads_path: Path, *, quasi_steady: bool | None
) -> tuple[tuple[QsteadyClocking, ...] | None, str | None]:
    """Return a quasi-steady wheel's clockings in the order its run solved them, and a warning.

    Read from the point's quasi-steady record, which the run writes beside the
    loads export (``<loads stem>_qsteady.json``), by its one reader
    (:func:`pyflightstream.cases.qsteady.read_qsteady_record`): clockings 1 to
    k - 1 are solved first and clocking 0 last, with the point's full exports
    (:meth:`~pyflightstream.cases.qsteady.QsteadyRecord.solve_order`). The
    clockings are None for every point that is not a wheel of two clockings
    or more, and the point's log is then judged as one solve, which refuses a
    log of several.

    THE RECORD'S REFUSAL IS DECIDED HERE (0.31.0). A point of the
    ``qsteady_rotor`` run type (``quasi_steady`` True) whose record is
    missing, unreadable or of another schema has its log judged as one solve,
    and the returned warning says so for the point's record. A point of
    another run type (``quasi_steady`` False) has no record to read: only the
    quasi-steady builder writes one, and only its run type is a steady solve
    repeated. Where the run type is not known (``quasi_steady`` None, a folder
    judged without its case), a record on disk is read and one that is absent
    says nothing.
    """
    if quasi_steady is False:
        return None, None
    path = loads_path.with_name(Path(qsteady_record_file_name(loads_path.name)).name)
    if quasi_steady is None and not path.is_file():
        return None, None
    try:
        record = read_qsteady_record(loads_path)
    except QsteadyRecordError as error:
        return None, (
            f"{error}; its solver log is judged as one solve, so a log holding the solves "
            "of several clockings is refused. Re-run the point so that its run writes the "
            "record again"
        )
    if record.case != "wheel" or len(record.positions) < 2:
        return None, None
    return record.solve_order(), None


def _judge_the_clockings(
    log_text: str,
    log_path: Path,
    report: LoadsReport,
    report_path: Path,
    clockings: Sequence[QsteadyClocking],
    stamp: dict[str, Any],
) -> Assessment:
    """Judge a quasi-steady wheel from the one log holding every clocking's solve.

    Each solve is judged as a point's one solve is
    (:func:`_judge_final_residuals`); the point carries each verdict in
    ``clocking_verdicts`` and the worst case in its status and residual. The
    log's last solve is clocking 0's, whose loads export is the point's, so
    it must end at the iteration that export was written at; each earlier
    clocking's own loads export is held to its solve the same way where it
    was collected.
    """
    try:
        solves = parse_residual_solves(log_text)
    except (IncompleteOutputError, ValueError) as exc:
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            error=f"solver log unusable: {exc}",
            **stamp,
        )
    if len(solves) != len(clockings):
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            iterations=report.current_iteration,
            error=(
                f"the solver log {log_path.name} holds {len(solves)} solve(s) and the point "
                f"was solved at {len(clockings)} clockings, one solve each, so which solve "
                "is which clocking's cannot be told and no convergence judgment is made "
                "from it. The log is of another run, or the run stopped before its last "
                "clocking"
            ),
            **stamp,
        )
    final = solves[-1][-1]
    if final.iteration != report.current_iteration:
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            iterations=report.current_iteration,
            error=(
                f"the last solve of the solver log {log_path.name}, clocking 0's, ends at "
                f"iteration {final.iteration} and the loads export {report_path.name} was "
                f"written at iteration {report.current_iteration}, so the residual is not "
                "the residual of the exported coefficients and no convergence judgment is "
                "made from it"
            ),
            **stamp,
        )
    try:
        frozen = frozen_time_steps(log_text)
    except IncompleteOutputError as exc:
        return Assessment(
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            iterations=final.iteration,
            error=f"solver log unusable: {exc}",
            **stamp,
        )
    if frozen is not None:
        return Assessment(
            status=RunStatus.FAILED_DIVERGED,
            iterations=final.iteration,
            error=frozen.reason,
            **stamp,
        )
    verdicts: list[dict[str, object]] = []
    statuses: list[RunStatus] = []
    residuals: list[float | None] = []
    notes: list[str] = []
    errors: list[str] = []
    for clocking, history in zip(clockings, solves, strict=True):
        index = clocking.index
        judged = _judge_final_residuals(history, report.convergence_limit)
        status, error = judged.status, judged.error
        loads = clocking.loads
        if index != 0:
            # EACH CLOCKING'S LOADS EXPORT IS OF ITS OWN SOLVE, held to it as
            # the point's own export is held to the last one.
            exported = report_path.with_name(Path(loads).name)
            own = _read_loads(exported, None)[0] if exported.is_file() else None
            if own is None:
                status = RunStatus.FAILED_INCOMPLETE_OUTPUT
                error = (
                    f"no readable loads export {exported.name} for this clocking, so its "
                    "solve's residual describes no exported coefficients"
                )
            elif own.current_iteration != history[-1].iteration:
                status = RunStatus.FAILED_INCOMPLETE_OUTPUT
                error = (
                    f"its solve ends at iteration {history[-1].iteration} and its loads "
                    f"export {exported.name} was written at iteration "
                    f"{own.current_iteration}, so the residual is not that export's"
                )
        verdict: dict[str, object] = {
            "index": index,
            "clocking_deg": clocking.clocking_deg,
            "status": str(status),
            "iterations": history[-1].iteration,
            "residual": judged.residual,
        }
        if judged.note:
            verdict["note"] = judged.note
            notes.append(f"clocking {index}: {judged.note}")
        if error:
            verdict["error"] = error
            errors.append(f"clocking {index}: {error}")
        verdicts.append(verdict)
        statuses.append(status)
        residuals.append(judged.residual)
    stamp["clocking_verdicts"] = verdicts
    if notes:
        stamp["residual_note"] = "; ".join(notes)
    if RunStatus.FAILED_INCOMPLETE_OUTPUT in statuses:
        worst = RunStatus.FAILED_INCOMPLETE_OUTPUT
    else:
        worst = max(statuses, key=_CLOCKING_SEVERITY.index)
    judged_residuals = [value for value in residuals if value is not None]
    return Assessment(
        status=worst,
        iterations=final.iteration,
        # THE LARGEST, the worst case, and only where every clocking has one:
        # a clocking that diverged has none, and the largest of the others
        # would read as the point's.
        residual=max(judged_residuals) if len(judged_residuals) == len(residuals) else None,
        error="; ".join(errors) or None,
        **stamp,
    )


#: FR-95. How bad a point's outcome is, worst LAST, for folding the points
#: of one job into the job's own status.
#:
#: IT IS A STATED ORDER AND NOT A PREFERENCE ABOUT WORDS. A job's headline
#: is what a reader triages by, so it has to name the most serious thing
#: that happened rather than the most recent. The order is: converged, then
#: the two that produced numbers and did not reach the answer, then the
#: four failures with the ones that produced nothing usable last. A status
#: missing from this tuple sorts as worse than everything in it, which is
#: the safe direction: a state nobody has classified is not quietly the
#: best one.
_STATUS_SEVERITY: tuple[RunStatus, ...] = (
    RunStatus.CONVERGED,
    RunStatus.SUBMITTED,
    RunStatus.COMPLETED_MAX_ITER,
    RunStatus.WALLTIME_REACHED,
    # FR-413: the outputs are present and the log is not; no verdict either way.
    RunStatus.RAN_MISSING_LOG,
    RunStatus.FAILED_SCRIPT,
    RunStatus.FAILED_EXECUTION,
    RunStatus.FAILED_INCOMPLETE_OUTPUT,
    RunStatus.FAILED_DIVERGED,
    # FR-309: the person's verdict outranks any outcome the run reached.
    RunStatus.FAILED_MARKED,
)


def worse_of(left: RunStatus, right: RunStatus) -> RunStatus:
    """Return the more serious of two point outcomes, by :data:`_STATUS_SEVERITY`."""

    def rank(status: RunStatus) -> int:
        try:
            return _STATUS_SEVERITY.index(status)
        except ValueError:
            return len(_STATUS_SEVERITY)

    return right if rank(right) > rank(left) else left


#: PUBLIC SINCE 0.24.0, because `run.collect` folds a swept job's points with the
#: same rule and reaching into a sibling for an underscore name is the boundary
#: the digest guard refuses. The private spelling stays for what already reads it.
_worse_of = worse_of
