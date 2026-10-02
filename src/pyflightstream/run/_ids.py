"""Names shared by every module of the run package: ids, job shape, the failure.

Private to :mod:`pyflightstream.run`. The run id and the point names of a
case, whether a row runs as one job and whether a point starts cold, the
one line the loop says, and :class:`CampaignErrors`, which every module
may raise and the root re-exports. It sits at the bottom of the package
order and imports no module of the package.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from pyflightstream._errors import (
    PyflightstreamError,
)
from pyflightstream._progress import (
    record_activity,
    say_line,
)
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    SimCase,
    point_name,
)
from pyflightstream.cases.acoustics import (
    with_acoustic_signals,
)
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import (
    COLD_START_VARIABLE,
    carries_singularity_strength,
    disc_speed_moves_with_the_point,
    with_tecplot_source,
)
from pyflightstream.workspace import JOB_TAG as _WORKSPACE_JOB_TAG
from pyflightstream.workspace import (
    CampaignWorkspace,
    RunRecord,
    WorkspaceError,
)
from pyflightstream.workspace.matrix import ResolvedMatrix


class CampaignErrors(PyflightstreamError, RuntimeError):  # noqa: N818 (the SAD Section 7 name)
    """One or more campaign points failed; raised after the loop.

    Every failed point is listed with its status and error text, and
    all points, failed or not, are already in the manifest: the
    exception reports, it never hides.

    Attributes
    ----------
    failures : list of RunRecord
        The manifest records of the failed points.
    records : list of RunRecord
        Every record the call wrote, failed or not, in the order it wrote
        them; the failures alone when the raiser did not pass them.
    """

    def __init__(self, failures: list[RunRecord], records: list[RunRecord] | None = None):
        self.failures = failures
        self.records = list(failures) if records is None else list(records)
        lines = "\n".join(
            f"  {record.run_id}: {record.status} ({record.error or 'no error text'})"
            for record in failures
        )
        super().__init__(
            f"{len(failures)} campaign point(s) failed; every point is recorded in "
            f"the manifest:\n{lines}"
        )


def _run_id(campaign: Campaign, case: SimCase, point: dict[str, float]) -> str:
    """Compose the fixed manifest identity of one campaign point.

    The scheme ``<campaign>/sim_<sim_id>/<point name>`` is identity (0.21.0),
    not presentation: it never goes through the naming template, so
    renaming outputs can never fork or collide run identities.
    """
    return f"{campaign.name}/sim_{case.sim_id}/{point_name(case, point)}"


def _point_names(
    campaign: Campaign,
    case: SimCase,
    point: dict[str, float],
    workspace: CampaignWorkspace,
) -> tuple[str, list[str]]:
    """Render the human-readable names of one point, output only.

    Returns the script file stem and the declared output names with
    their placeholders rendered; the recipe sees the rendered names in
    :attr:`SimCase.outputs`, so what it exports is what the loop
    collects. The default template reproduces the historical names.
    """
    ratio = _advance_ratio_of(case)
    name = point_name(case, point)
    stem = workspace.naming.render_point(
        campaign=campaign.name,
        sim=case.sim_id,
        point=point,
        mach=case.mach,
        advance_ratio=ratio,
        name=name,
    )
    outputs = [
        workspace.naming.render_output(
            declared,
            campaign=campaign.name,
            sim=case.sim_id,
            point=point,
            mach=case.mach,
            advance_ratio=ratio,
            stem=stem,
            point_name=name,
        )
        for declared in case.outputs
    ]
    # G45: the VTK a Tecplot surface is written from is an output of the point,
    # and the native Tecplot only where the pproc asks for the strength (SS1).
    # 0.32.0 (E2): the acoustic export of a row that declares observers, last.
    return stem, with_acoustic_signals(
        with_tecplot_source(outputs, singularity_strength=carries_singularity_strength(case)),
        case,
        stem,
    )


def _unplaced(translation: Mapping[str, object]) -> bool:
    """Whether a recorded translation states no placement for its loads frame (G45)."""
    frame = translation.get("frame")
    return (
        not isinstance(frame, Mapping) or frame.get("origin") is None or frame.get("axes") is None
    )


def _advance_ratio_of(case: SimCase) -> float | None:
    """Return the advance ratio a case states or resolves, for its name; None without one.

    A row stating ADVANCE_RATIO names it directly; a row stating RPM with
    a velocity and a rotor diameter resolves it the way the rotor
    speed does (PFS-2029.19.01, the J field of the standard convention). A case
    that cannot resolve one is a case without a J field, not a refusal:
    the name is presentation, and the run type's own refusals still say
    what a rotor row lacks.
    """
    from pyflightstream.cases.workflows import ADVANCE_RATIO_VARIABLE, RPM_VARIABLE, rotor_speed

    stated = case.variables.get(ADVANCE_RATIO_VARIABLE)
    if stated is not None:
        try:
            return float(stated)
        except (TypeError, ValueError):
            return None
    if case.variables.get(RPM_VARIABLE) is None:
        return None
    try:
        return rotor_speed(case).advance_ratio
    except PyflightstreamError:
        return None


def _say(message: str, *, quiet: bool = False) -> None:
    """Print one progress line to stderr, immediately.

    FR-78. STDERR is decided before the first line was written: everything this
    run prints that a caller CONSUMES is on stdout, so a progress line there
    would break a pipeline reading records.

    THE STREAM IS RESOLVED AT CALL TIME, not bound at import. Binding it once
    at module level captured the interpreter's ORIGINAL stderr, so anything
    that replaces `sys.stderr` afterwards -- a test harness, a caller
    redirecting output, a notebook -- saw nothing at all while the lines went
    somewhere else. The first version did that and its own test caught it.

    `flush=True` is the requirement and not a precaution: a stream that is not
    a terminal is block-buffered, so a campaign redirected to a file would
    print its first line when the last point was done, which is the silence
    this requirement exists to end.
    """
    # Guarded: a log that cannot be written is said, never raised, so it
    # cannot abort a campaign (GOAL-034 Q8 CXQ8-1).
    record_activity("progress", "message", message)
    if quiet:
        return
    # Guarded too: a closed or broken stderr drops the line, never the stage
    # (GOAL-034 Q8 QA3-1).
    say_line(message)


#: The tag a JOB's run id ends with, where a point's run id ends with its
#: point tag; its home is the workspace layer since 0.30.0, beside the record
#: it names, and it is stated here under the name this module has always had.
JOB_TAG = _WORKSPACE_JOB_TAG


def _job_run_id(campaign: Campaign, case: SimCase) -> str:
    """Return the run id of a JOB, which no one point's tag may end.

    The point tag is run IDENTITY and it ends every ``run_id`` in every
    existing manifest; the rule is enforced at the sweep and carries its
    own incident history. A record covering three points cannot borrow one
    of their tags, so it ends with :data:`JOB_TAG` instead.
    """
    return f"{campaign.name}/sim_{case.sim_id}/{JOB_TAG}"


def _points_the_recorded_job_ran(
    campaign: Campaign, case: SimCase, manifest: Mapping[str, RunRecord]
) -> tuple[str, ...] | None:
    """Return the point names the recorded job of this row ran, in order, or None.

    A STEADY ROW OF A MATRIX IS ONE JOB, recorded under the row's id and not
    under its points' (FR-95), so a point the job ran is recorded although no
    record carries the point's own id. None where the row is not one job or no
    job of it is recorded. ``run_campaign`` skips these points on resume and
    ``plan_campaign`` reports them ALREADY_RECORDED, both from here: the plan
    read the points' own ids and called every point of a recorded job READY,
    while resume ran none of them.
    """
    if not _is_one_job(campaign, case):
        return None
    job = manifest.get(_job_run_id(campaign, case))
    if job is None:
        return None
    return tuple(str(entry.get("tag") or "") for entry in job.points_ran or [])


#: The run type whose points are ONE job since 0.17.0.
ONE_JOB_RECIPE = "steady"


def runs_as_one_job(campaign: Campaign, case: SimCase) -> bool:
    """Return whether the pending points of this case run together as one warm job.

    The public face of the rule :func:`_is_one_job` states, for a caller that must
    say how many jobs a run spends before it runs them (``force_rerun_all``, G44):
    a steady matrix row whose points differ in attitude alone is one job however
    its points were recorded.

    Parameters
    ----------
    campaign : Campaign
        The campaign the case belongs to.
    case : SimCase
        The row.

    Returns
    -------
    bool
        True when two or more pending points of the row run as one job.
    """
    return _is_one_job(campaign, case)


def _is_one_job(campaign: Campaign, case: SimCase) -> bool:
    """Whether this case's points run as one job rather than one each.

    A STEADY ROW OF A MATRIX, and only that. Three conditions, each for
    its own reason:

    * the recipe is the steady run type. A LEGACY row is built by its own
      recipe, which builds one point and knows nothing of a sweep; an
      unsteady point marches in time from its own initial state, so two of
      them in one process would make the second continue the first's clock.
    * the campaign came from a MATRIX. This convention applies to matrix
      rows, and a campaign authored in Python is a
      different surface with a contract of its own: thirty-one tier-1 tests
      state that a Python campaign records one point at a time, and widening
      that convention onto them would be a change nobody asked for, made
      silently, to an interface the decision was not about.
    * there is more than one point. One point is one job either way, and
      routing it here would give it a job's run id for no gain and break
      every resume that expects its point tag.

    THE INCONSISTENCY THIS LEAVES IS REAL AND IS RECORDED RATHER THAN
    HIDDEN: the same steady sweep is one job through a matrix and one job
    per point through the Python API. Whether the Python surface should
    follow is a question for the author, and answering it unasked is what
    the second condition exists to prevent.

    A FOURTH CONDITION SINCE 0.21.0: the points differ in ATTITUDE alone. A
    row may now sweep a flow variable, and one warm job cannot run such a
    sweep: the air state is a SETUP command, the solver takes it before it is
    initialised, and the phase guard refuses it after. So a row sweeping MACH,
    REmi, an altitude or any other flow variable is one job per point, each
    with its own fluid block, and the warm sweep stays what the predecessor's
    recipe was: one setup, one initialisation, many angles.

    A FIFTH SINCE 0.28.0: the row's disc takes a different speed at each
    point. A disc that derives its speed from a swept advance ratio (G20) is
    set once in a warm job, so every point after the first would turn at the
    first point's speed; such a row is one job per point, as a flow sweep is.

    A SIXTH SINCE 0.30.0: the row couples a fixed wing (FSI-G). A steady
    coupled script ends at ``EXECUTE_AEROELASTIC_ANALYSIS`` and its process
    is stopped once the analysis ends, so one script holds one point.
    """
    if not (case.recipe == ONE_JOB_RECIPE and bool(getattr(campaign, "matrix_stem", None))):
        return False
    if case.fsi is not None:
        return False
    return not (_sweeps_the_flow(case) or disc_speed_moves_with_the_point(case))


def _sweeps_the_flow(case: SimCase) -> bool:
    """Whether this case's sweep moves the air state rather than the attitude.

    Read from the RESOLVED points rather than from the axis name: a row that
    sweeps a flow variable carries one state per point, and a row that sweeps
    an angle carries none. That way a variable that becomes sweepable later
    needs no second list to be added to.
    """
    states = list(case.point_states.values())
    return any(
        state.fluid != states[0].fluid or state.velocity != states[0].velocity
        for state in states[1:]
    )


def _is_cold_start(case: SimCase) -> bool:
    """Select the R13 cold default; an explicit false value opts into warm starts."""
    stated = case.variables.get(COLD_START_VARIABLE)
    if stated is None or str(stated).strip() == "":
        return True
    value = str(stated).strip().upper()
    if value in {"TRUE", "ENABLE", "YES", "1"}:
        return True
    if value in {"FALSE", "DISABLE", "NO", "0"}:
        return False
    raise CampaignConfigError(
        f"case {case.sim_id!r}: COLD_START must be true or false; got {stated!r}. "
        "Cold is the default; false explicitly opts into warm steady starts."
    )


# FR-327 (0.34.0, P0340-RUN-AGAIN): the refusal of a second run counts what continuing does.
class _AlreadyRecordedError(WorkspaceError):
    """A point of the matrix is already in the manifest and no way to continue was chosen.

    Attributes
    ----------
    recorded : int
        The points of the campaign the manifest already carries.
    would_run : int
        The points of the campaign no record carries, which ``--resume`` would run.
    """

    def __init__(self, message: str, *, recorded: int, would_run: int) -> None:
        super().__init__(message)
        self.recorded = recorded
        self.would_run = would_run


def _recorded_and_new(campaign: Campaign, manifest: Mapping[str, RunRecord]) -> tuple[int, int]:
    """Count the points of the campaign the manifest carries and the points it does not."""
    recorded = new = 0
    for case in campaign.sims:
        ran = _points_the_recorded_job_ran(campaign, case, manifest)
        for point in case.sweep.points():
            if ran is not None:
                # A steady row is one job: its points are recorded under the job's id.
                is_recorded = point_name(case, point) in ran
            else:
                is_recorded = _run_id(campaign, case, point) in manifest
            recorded += is_recorded
            new += not is_recorded
    return recorded, new


def already_recorded_error(
    campaign: Campaign, manifest: Mapping[str, RunRecord], run_id: str, root: object
) -> _AlreadyRecordedError:
    """Return the refusal of a run whose point ``run_id`` is already in the manifest.

    Parameters
    ----------
    campaign : Campaign
        The campaign about to run, after any selection.
    manifest : mapping of str to RunRecord
        The records of the workspace, keyed by run id.
    run_id : str
        The first recorded run id the run met.
    root : object
        The workspace root, named in the message.

    Returns
    -------
    _AlreadyRecordedError
        The error to raise: nothing was staged or run, and it counts the recorded points and
        the points ``--resume`` would run.
    """
    recorded, new = _recorded_and_new(campaign, manifest)
    return _AlreadyRecordedError(
        f"run_id {run_id!r} is already in the manifest of {root}; re-running a "
        f"recorded point would fork the run identity. {recorded} point(s) of this run are "
        f"recorded and {new} would run with resume=True (CLI: --resume), which SKIPS the "
        "recorded ones and does not re-run this one. To REDO it instead, name it: "
        f"force_rerun=[{run_id!r}] (CLI: --force-rerun {run_id}), which archives that "
        "record and that point's collected outputs and then runs it, leaving every point "
        "it does not name alone.",
        recorded=recorded,
        would_run=new,
    )


# FR-326 (0.34.0, P0340-RUN-ONE-POINT): a selection of the matrix, planned or run alone.
def _names_of(case: SimCase) -> list[str]:
    """Return the point names of one case, in sweep order, as the plan prints them."""
    return [point_name(case, point) for point in case.sweep.points()]


def _only_these_points(case: SimCase, wanted: set[str]) -> SimCase | None:
    """Return the case reduced to the points ``wanted`` names, or None where it has none."""
    kept = [
        value
        for value, name in zip(case.sweep.values, _names_of(case), strict=True)
        if name in wanted
    ]
    if not kept:
        return None
    return case.model_copy(update={"sweep": case.sweep.model_copy(update={"values": kept})})


def narrow_to_selection(
    resolved: ResolvedMatrix,
    sims: Sequence[str] | None,
    points: Sequence[str] | None,
    *,
    redoing: bool = False,
) -> ResolvedMatrix:
    """Return the matrix reduced to the simulations ``sims`` and the points ``points`` name.

    Parameters
    ----------
    resolved : ResolvedMatrix
        The matrix bound to the workspace.
    sims : sequence of str, optional
        The simulation ids as the matrix spells them; None or empty selects every one.
    points : sequence of str, optional
        Point names, accepted only with ``sims``: only those points of the selected
        simulations remain, and a simulation carrying none of them is left out.
    redoing : bool
        True under ``force_rerun_all``, which redoes recorded points by simulation and
        refuses a point selection (``--force-rerun`` names points to redo).

    Returns
    -------
    ResolvedMatrix
        The same object when nothing is selected, otherwise a copy whose campaign carries
        the selected simulations and points, with ``row_builds`` kept in step.

    Raises
    ------
    MatrixError
        When ``points`` comes without ``sims`` or with ``redoing``, or names a simulation
        or a point the matrix does not carry; raised before anything runs.
    """
    if not sims:
        if points:
            raise MatrixError(
                "points (CLI: --points) name points of the simulations sims (CLI: --sims) "
                "names; give --sims too, or leave --points out. Nothing was run."
            )
        return resolved
    if points and redoing:
        raise MatrixError(
            "points (CLI: --points) cannot be combined with force_rerun_all (CLI: "
            "--force-rerun-all), which redoes whole simulations; name the recorded point "
            "to redo with force_rerun (CLI: --force-rerun). Nothing was run."
        )
    campaign = resolved.campaign
    carried = [case.sim_id for case in campaign.sims]
    unknown = [sim for sim in sims if sim not in carried]
    if unknown:
        raise MatrixError(
            f"sims names {', '.join(unknown)}, which this matrix does not carry; it "
            f"carries {', '.join(carried)}. Nothing was run."
        )
    chosen = [case for case in campaign.sims if case.sim_id in set(sims)]
    if points:
        existing = [name for case in chosen for name in _names_of(case)]
        missing = [name for name in points if name not in existing]
        if missing:
            raise MatrixError(
                f"points names {', '.join(missing)}, which simulation(s) {', '.join(sims)} "
                f"do not carry; they carry {', '.join(existing)}. Nothing was run."
            )
        reduced = [_only_these_points(case, set(points)) for case in chosen]
        chosen = [case for case in reduced if case is not None]
    keep = [case.sim_id in {c.sim_id for c in chosen} for case in campaign.sims]
    by_id = {case.sim_id: case for case in chosen}
    return replace(
        resolved,
        campaign=campaign.model_copy(
            update={"sims": [by_id[sim] for sim in carried if sim in by_id]}
        ),
        row_builds=tuple(b for b, kept in zip(resolved.row_builds, keep, strict=True) if kept),
    )
