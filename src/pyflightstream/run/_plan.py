"""The campaign plan: pre-flight of every point, its cost, and its receipt.

Private to :mod:`pyflightstream.run`, which re-exports every public name
of it. :func:`plan_campaign` resolves every recipe, allocates the managed
folders and builds every script in dry run, returning one
:class:`PointPlan` per point and writing the plan summary into the
campaign root. The cost table (:func:`estimate_point_cost`,
:func:`point_costs`, :func:`format_cost_table`) and the plan receipt the
run refuses without (:func:`plan_receipt_error`) live here too, with the
collision checks the run repeats before anything executes.
"""

from __future__ import annotations

import enum
import json
import warnings
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import pyflightstream
import pyflightstream._textio as _textio
import pyflightstream.cases.workflows as workflows
import pyflightstream.run._ids as _ids
from pyflightstream._digest import (
    file_sha256,
)
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._tokens import NOT_APPLICABLE
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    case_at_point,
    check_recipe,
    point_name,
    resolve_recipe,
)
from pyflightstream.cases._skipped_families import (
    noting_the_families_rows_lack,
    noting_the_study_skips,
    saying_the_study_skips,
)
from pyflightstream.cases.qsteady import summarise as summarise_validity
from pyflightstream.cases.qsteady import (
    summarise_inflow_harmonics,
)
from pyflightstream.cases.windows import RESTART_STEP_OFFSET_VARIABLE
from pyflightstream.cases.workflows import (
    ACTUATOR_VARIABLE,
    PROFILE_VARIABLE,
    RAW_MESH_FORMATS,
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    STEADY_RUN_TYPES,
    actuator_records,
    effective_fsi_config,
    qsteady_validity,
    rotor_machs,
    streamline_count,
)
from pyflightstream.cases.workflows._farfield import plan_record as farfield_plan_record
from pyflightstream.cases.workflows._freestream import (
    WakeTermination,
    planned_run_wake,
    planned_wake,
    wake_warnings,
)
from pyflightstream.run._alias import PLANNED_ORDER_KEY
from pyflightstream.run._continuation import (
    _refuse_an_import_count_nothing_logs,
    resolve_continuation,
)
from pyflightstream.run._continuation_frame import (
    point_verdict,
)
from pyflightstream.run._executors import (
    SolverBuild,
)
from pyflightstream.run._identity import (
    _build_groups,
    _build_label,
    _case_build,
    _file_digest,
)
from pyflightstream.run._ids import (
    _point_names,
    _points_the_recorded_job_ran,
    _run_id,
)
from pyflightstream.script import MarchStrategy, Script
from pyflightstream.versions import resolve
from pyflightstream.workspace import (
    SIM_DATAPOINTS_DIR,
    CampaignWorkspace,
    NamingTemplateError,
    RunRecord,
    WorkspaceError,
    collection_name,
    datapoint_dir_name,
    structural_assessment,
)
from pyflightstream.workspace._batches import GroupingReceipt
from pyflightstream.workspace._settings_file import (
    ENTRY_ACCEPTANCE_SOURCE,
    TYPED_ACCEPTANCE_SOURCE,
    invocation_sources,
)
from pyflightstream.workspace.costs import priced_rows
from pyflightstream.workspace.manifest import COST_EXCLUDED_STATUSES
from pyflightstream.workspace.naming import (
    PointName,
    archive_previous,
)


class PlanStatus(enum.StrEnum):
    """Pre-flight status of one campaign point (no execution involved).

    READY: the recipe resolved, the geometry exists, and the script
    built and rendered in dry run. BLOCKED: something failed before any
    solver could run; the plan carries the error text.
    ALREADY_RECORDED: the manifest already holds this ``run_id``, so
    ``run_campaign(..., resume=True)`` would skip it.

    Examples
    --------
    >>> from pyflightstream.run import PlanStatus
    >>> [status.value for status in PlanStatus]
    ['READY', 'BLOCKED', 'ALREADY_RECORDED']
    >>> PlanStatus.READY == "READY"
    True
    """

    READY = "READY"
    BLOCKED = "BLOCKED"
    ALREADY_RECORDED = "ALREADY_RECORDED"


@dataclass(frozen=True)
class PointPlan:
    """Pre-flight judgment of one campaign point.

    Attributes
    ----------
    run_id : str
        Manifest identity the point would run under.
    sim_id : str
        Simulation identity of the case.
    point : dict of str to float
        Sweep point coordinates (alpha and beta in deg, advance_ratio
        dimensionless).
    script_name : str or None
        File name the generated script would take (from the naming
        template); None when the name itself could not be rendered.
    status : PlanStatus
        The pre-flight status.
    error : str or None
        What blocks the point, for BLOCKED entries.
    waived_commands : tuple of str
        Commands the point's script emits under an ``allow_broken``
        waiver. Known at plan time, because the dry run builds the same
        script, and reported here so an operator learns the campaign
        leans on a command a probe measured broken BEFORE spending
        solver time rather than from the manifest afterwards. The deprecated
        alias ``broken_commands`` still reads, warning from the deprecation
        ledger (PFS-2022.01.05). ``plan.json`` uses ``waived_commands``.
    raw : bool
        Whether the point's script used the ``raw()`` escape hatch.
        Same reason.
    march_strategy : str or None
        How the point's unsteady run is marched on its build, ``"actions"``
        or ``"single_march"`` (GOAL-023); None for a steady point or one
        that is BLOCKED.
    rotor_mach : dict of str to dict
        On a point of an ``unsteady_rotor`` row, a ``steady`` row stating
        ``RPM`` or a row naming an actuator disc, each rotor's and disc's tip
        and helical Mach numbers keyed by its alias or disc name, as
        :meth:`pyflightstream.cases.workflows.RotorMach.record` states them,
        with a ``note`` naming the row where they are not known (M1).
        Empty on every other point.
    qsteady_validity : dict of str to object
        On a point of a ``qsteady_rotor`` WHEEL, the 1P reduced frequency of
        its blade: the per cent of the span with k above 0.1,
        ``k_min``, ``k_max`` and ``k_mean``, as
        :func:`pyflightstream.cases.workflows.qsteady_validity` states them,
        or a ``note`` saying why the chord is not known at plan time. Empty on
        every other point.
    continuation : str or None
        On a point of a row stating ``RESTART`` (FR-96), what the
        continuation does (``continuing a CONVERGED unsteady run, <run id>, by
        1 revolution(s)``) or why the request cannot continue the point; None
        on every other point and where the resolver's refusal is the error.
    wake_termination : dict of str to object
        On a point of an ``unsteady_rotor`` row that is not a continuation, the
        wake termination its script emits (FR-584): the key that
        stated it (``default`` for the 4R default), the length asked in rotor
        radii, the steps, the rule that gave V_ax and V_ax in m/s, as
        :meth:`pyflightstream.cases.workflows._freestream.WakeTermination.record`
        states them. Empty on every other point.
    run_wake_length : dict of str to object
        On a point of an ``unsteady_rotor`` row stating ``RUN_WAKE_LENGTH_R``
        (FR-906), the run length resolved from it: the length asked
        in rotor radii, the rule and V_ax, the resulting ``time_iterations`` and
        the revolutions they turn. Empty on every other point, and then left
        out of ``plan.json``.
    streamlines : int
        The off-body streamlines the point's pproc traces (FR-1079):
        every seed line's count and every tube's ``radial * circular``. 0, and
        left out of ``plan.json``, where it traces none.
    """

    run_id: str
    sim_id: str
    point: dict[str, float]
    script_name: str | None
    status: PlanStatus
    error: str | None = None
    waived_commands: tuple[str, ...] = ()
    raw: bool = False
    march_strategy: MarchStrategy | None = None
    rotor_mach: dict[str, dict[str, object]] = field(default_factory=dict)
    qsteady_validity: dict[str, object] = field(default_factory=dict)
    continuation: str | None = None
    wake_termination: dict[str, object] = field(default_factory=dict)
    run_wake_length: dict[str, object] = field(default_factory=dict)
    streamlines: int = 0
    farfield: dict[str, object] = field(default_factory=dict)
    fsi: dict[str, object] = field(default_factory=dict)
    inflow_harmonics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlannedPointCost:
    """What one point is expected to cost, and what that expectation rests on.

    Named for the point that has not run. In contrast,
    :class:`pyflightstream.qa.cost.PointCost` represents one point measured
    on two solver builds and is exported from `pyflightstream.qa`.

    FR-82. Every field but `seconds` and `samples` is READ from the row, the
    mesh and the setup: they are measurements of the thing about to be run. The
    two that are not are marked as such, because the difference between a
    figure a reader can check and a figure fitted from history is the whole
    question when someone is deciding whether to spend a seat.

    Attributes
    ----------
    run_id : str
        The point this row is about.
    panels : int or None
        Mesh size: the ELEMENT COUNT the geometry's mesh block states, which
        one campaign geometry overstates by about a percent (`_mesh_size`
        carries the measurement). None where the geometry states none or
        could not be read. This is an element count, not a boundary count.
    trailing_edges : int or None
        How many of the families the row marks for vorticity drag the
        opened geometry actually carries. ZERO is a measured none; None
        means the geometry could not be read, so the intersection this
        column promises could not be performed at all.
    farfield_layers : int or None
        The farfield layer setting, None when the setup states none.
    viscous_coupling : bool
        Whether viscous coupling is on.
    unsteady : bool
        Steady or unsteady, which is the single largest term in the cost.
    time_iterations : int or None
        Time steps for an unsteady row; None for a steady one.
    processors : int or None
        `SET_MAX_PARALLEL_THREADS`, the number of processors set.
    seconds : float or None
        EXPECTED wall time. None where no comparable run has been recorded.
    samples : int
        How many recorded runs the estimate was fitted from. ZERO means the
        estimate is absent rather than uncertain, and the table prints
        `unknown` rather than a number.
    basis : str
        One sentence naming what the estimate rests on, carried into the
        report so the figure is never read without it.
    """

    run_id: str
    panels: int | None
    trailing_edges: int | None
    farfield_layers: int | None
    viscous_coupling: bool
    unsteady: bool
    time_iterations: int | None
    processors: int | None
    seconds: float | None
    samples: int
    basis: str


def _mesh_size(geometry) -> int | None:
    """Return the element count the geometry's mesh block states, or None (FR-82).

    FR-82's "tamanho da malha", read by the layer that owns the `.fsm`
    format rather than parsed a second time here. What the number is, and
    the percent it can be off by, is documented at
    :func:`pyflightstream._fsm.element_count`; nothing does arithmetic on it.
    """
    from pyflightstream._fsm import element_count

    return element_count(geometry)


def _marked_trailing_edges(case) -> int | None:
    """How many boundaries the row marks for vorticity drag (FR-82).

    Read from the row's own statement and the geometry's inventory rather
    than from a rendered script, because the plan must not build a script
    twice to fill a column of a table; the two agree because they read the
    same two things the builder does.

    THE SELECTION IS `solver.vorticity_drag_families`, family NAMES, and
    the builder leaves out the families the opened geometry does not carry
    (PFS-2030.03.03).

    A row marking none answers 0, which is then a measurement.

    A RAW MESH IS READ FROM ITS DECLARED INVENTORY (G01, G03). An ``.obj``
    or ``.stl`` carries no mesh block, so its names are the sidecar's
    ``boundaries`` as the import's renames leave them, which is exactly
    what the builder declares.
    """
    families = getattr(getattr(case, "solver", None), "vorticity_drag_families", None)
    if not families:
        return 0  # a measured none: the row marks no family
    inventory: Sequence[str] | None = None
    if case.geometry is not None and Path(str(case.geometry)).suffix.lower() in RAW_MESH_FORMATS:
        declared = tuple(case.inventory or ())
        spec = case.mesh_import
        inventory = declared if spec is None else spec.names_after_renames(declared)
    elif case.geometry is not None:
        try:
            from pyflightstream._fsm import boundary_names

            inventory = boundary_names(case.geometry)
        except Exception:
            inventory = None
    if not inventory:
        # An unreadable geometry leaves the intersection unknown. The row's
        # family count alone cannot establish which trailing edges the geometry has.
        return None
    carried = {name.casefold() for name in inventory}
    return len([name for name in families if str(name).casefold() in carried])


def _recorded_is_unsteady(record: dict, *, steps: int | None = None) -> bool:
    """Whether a recorded run was unsteady, by the fact it states (FR-82).

    The record's own `recipe` answers, and it is the same key the planned
    point is classified by. A record from an older manifest schema states
    none, and only then does this fall back to a proxy: a run carrying a
    reduction block reduced, and only an unsteady run reduces. That fallback
    cannot identify an unsteady run without a planned reduction.
    """
    recipe = record.get("recipe")
    if recipe in (*STEADY_RUN_TYPES, "unsteady", "unsteady_rotor"):
        # The quasi-steady rotor is steady at every solve.
        return recipe not in STEADY_RUN_TYPES
    return steps is not None or bool(record.get("reductions"))


#: The statuses whose wall time is no sample of what a point costs (PFS-2094.014):
#: a failure ended early or never ran, WALLTIME_REACHED would teach the estimate
#: that a point costs exactly the clock it was given, SUBMITTED has not run here,
#: and RAN_MISSING_LOG is no verdict. The set of qa/cost.py's _EXCLUDED_STATUSES,
#: which run/ cannot import (qa imports run).
_NOT_A_COST_SAMPLE = COST_EXCLUDED_STATUSES


def _recorded_costs(workspace) -> list[dict]:
    """Every recorded point that carries a wall time and ran to an end, as plain mappings.

    The model's whole training set. A workspace that has run nothing produces
    an empty list, and every estimate below then reports `samples = 0`, which
    the table prints as `unknown` rather than as a number. A record in a status
    of :data:`_NOT_A_COST_SAMPLE` is left out, as restore-and-rebuild.md says
    of FAILED_MARKED.
    """
    # Use the workspace's manifest reader. Only a missing file means no
    # recorded runs; other failures must remain visible to the estimator.
    if not workspace.manifest_path.is_file():
        return []
    records = workspace.read_manifest()
    out = []
    for record in records:
        data = record if isinstance(record, dict) else record.model_dump(mode="json")
        seconds = data.get("wall_time_s")
        if str(data.get("status")) in _NOT_A_COST_SAMPLE:
            continue
        if isinstance(seconds, (int, float)) and seconds > 0:
            out.append(data)
    return out


def estimate_point_cost(
    case,
    *,
    run_id: str,
    recorded: list[dict],
    steps_by_run: dict[str, int | None] | None = None,
) -> PlannedPointCost:
    """Table one point's cost, and fit its time from comparable recorded runs.

    FR-82. EVERY FIGURE BUT THE TIME IS A MEASUREMENT of the row, the mesh and
    the setup. The time is an extrapolation and the row says so, carrying the
    number of samples it was fitted from and one sentence naming the basis.

    COMPARABLE MEANS THE SAME RUN TYPE, because steady and unsteady differ by
    more than any other term: an unsteady point runs its solve once per time
    step. Within a run type the fit is linear in the work the point asks for,
    which is the time steps for an unsteady row and one solve for a steady one.

    There is no processor term. The processor count is read and printed for
    comparison across rows; it is not multiplied into anything. The fit is
    linear in the time steps and in nothing else.

    IT IS DELIBERATELY A CRUDE MODEL and the docstring says so rather than
    the code implying otherwise. A fuller scalability study is planned and
    will calibrate it; until then the instruction is to estimate from
    whatever the workspace already holds, so a reader gets a number with
    its sample size attached, or no number at all.

    Parameters
    ----------
    case : SimCase
        The point's case, specialized to the point; supplies the run type,
        the geometry, the solver settings and the time steps.
    run_id : str
        Manifest identity of the point, carried into the row.
    recorded : list of dict
        The workspace's recorded runs, as manifest rows; those of the same
        run type that state a wall time (``wall_time_s``, seconds) are the
        samples.
    steps_by_run : dict of str to int or None, optional
        Time steps of each run id the plan holds, used to scale an unsteady
        sample; a run id mapped to None, or absent, is left out of the fit.

    Returns
    -------
    PlannedPointCost
        The point's row: the measured figures, the expected time in seconds
        (None when no comparable run exists), the number of samples and the
        sentence naming the basis.
    """
    solver = getattr(case, "solver", None)
    from pyflightstream.cases.workflows import time_steps_of

    iterations = time_steps_of(case)
    # A custom LEGACY recipe is not an unsteady declaration. Its physical
    # clock is the available evidence, while registered unsteady workflows
    # remain unsteady even if an invalid clock prevents a step count.
    unsteady = case.recipe in ("unsteady", "unsteady_rotor") or (
        case.recipe not in STEADY_RUN_TYPES and iterations is not None
    )

    # Resolve row NCPUS before setup max_threads, using the same resolver
    # as the emitted script and descriptor (PFS-2094.038).
    from pyflightstream.cases.workflows import row_ncpus

    from_setup = getattr(solver, "max_threads", None)
    processors = row_ncpus(case, from_setup if isinstance(from_setup, int) else None)
    if not isinstance(processors, int):
        processors = None

    # MESH SIZE, and this column read the BOUNDARY COUNT until it was checked
    # against a real geometry: `boundary_names` returns names, so a wing-body
    # read 2 and a rotor sector 3. The mesh block states its size on the line
    # right after `$MESH_START$`, which is 14266 for that same wing-body.
    panels = _mesh_size(case.geometry) if case.geometry else None

    # TRAILING EDGES: counted from the script the plan already builds, because
    # the marked edges are the boundaries of `SET_VORTICITY_DRAG_BOUNDARIES`
    # and no row carries them as a variable. Counting a key nobody writes
    # reported zero for every point, which reads as a measurement of none.
    trailing = _marked_trailing_edges(case)

    # Fit comparable records of the same run type against time steps, or one
    # solve for a steady row. Read the record's recipe just as for the planned
    # point: a reduction block alone cannot identify an unsteady run whose
    # reductions were not planned.
    same = [
        r
        for r in recorded
        if _recorded_is_unsteady(r, steps=(steps_by_run or {}).get(r.get("run_id", ""))) == unsteady
    ]
    seconds = None
    basis = (
        "no recorded run of this run type in this workspace, so no estimate is "
        "offered rather than one with no basis"
    )
    rates = []
    unknown = 0
    for record in same:
        if unsteady:
            # THE SAMPLE'S OWN WORK, and it is NOT read off the manifest's
            # reductions: a recorded run whose reductions were skipped
            # carries a null step count there, and reading that as ONE
            # SOLVE made the rate 36 times too large on the reference rotor point.
            # The plan resolved the step count of every point it holds, and
            # a recorded run of a point still in the matrix is that point,
            # so the map answers; a record of a point that has left the
            # matrix stays unknown.
            recorded_id = record.get("run_id")
            steps = (steps_by_run or {}).get(recorded_id) if isinstance(recorded_id, str) else None
            if not isinstance(steps, int) or steps <= 0:
                unknown += 1
                continue
            work = float(steps)
        else:
            # A STEADY JOB RECORD IS ITS POINTS' SOLVES IN ONE PROCESS
            # (PFS-2094.015): its wall time is the whole job's, so it is
            # one solve per point it ran, not one solve.
            work = float(len(record.get("points_ran") or []) or 1)
        rates.append(float(record["wall_time_s"]) / work)
    samples = len(rates)
    if rates and unsteady and not iterations:
        # THE POINT'S OWN WORK IS UNKNOWN (PFS-2094.016): priced at one
        # time step, the per-step rate was shown as its expected time.
        basis = (
            "this point's step count is unknown (its row states none this reader "
            "can step), so no estimate is offered rather than one priced at a "
            "single time step"
        )
    elif rates:
        rate = sum(rates) / len(rates)
        work = float(iterations) if unsteady and iterations else 1.0
        seconds = round(rate * work, 1)
        dropped = (
            ""
            if not unknown
            else (
                f" {unknown} further recorded run(s) state no step count and were "
                "left out rather than counted as one step."
            )
        )
        # THE MECHANISM NAMED IS THE ONE THAT ACTED. Both run types were
        # told "linear in the time steps the point asks for", and a steady
        # row asks for none: its work is one solve, fixed. An operator
        # message that names a mechanism which did not act is the defect
        # this estate treats as worst, because it reads as current.
        how = (
            "linear in the time steps the point asks for"
            if unsteady
            else "one solve per recorded run, which is what a steady row asks for"
        )
        basis = (
            f"fitted from {samples} recorded "
            f"{'unsteady' if unsteady else 'steady'} run(s) of this workspace, "
            f"{how}. It is a crude model "
            "pending a scalability study and is not a measurement of "
            f"this point.{dropped}"
        )
    elif same:
        basis = (
            f"the {len(same)} recorded "
            f"{'unsteady' if unsteady else 'steady'} run(s) of this workspace state "
            "no step count, so none of them calibrates a per-step rate and no "
            "estimate is offered rather than one fitted to a guess"
        )
    return PlannedPointCost(
        run_id=run_id,
        panels=panels,
        trailing_edges=trailing,
        farfield_layers=getattr(solver, "farfield_layers", None),
        viscous_coupling=bool(getattr(solver, "viscous_coupling", False)),
        unsteady=unsteady,
        time_iterations=iterations,
        processors=processors,
        seconds=seconds,
        # THE SAMPLES THAT ACTUALLY ENTERED THE FIT, never the comparable
        # runs found: a row reporting `unknown` beside a sample count is a
        # row whose reader cannot tell which of the two numbers to believe.
        samples=samples,
        basis=basis,
    )


def point_costs(
    plan: CampaignPlan, cases_by_sim_id: Mapping[str, SimCase], workspace
) -> list[PlannedPointCost]:
    """One cost row per planned point (FR-82).

    Parameters
    ----------
    plan : CampaignPlan
        The plan whose points are to be tabled.
    cases_by_sim_id : mapping
        The resolved case, KEYED ON THE SIMULATION ID and not on the run id.
        The name carries the key because choosing the other one produces an
        empty result and no refusal. A point whose simulation is absent gets
        no row rather than a row of blanks.
    workspace : CampaignWorkspace
        Where the recorded wall times are read from.

    Returns
    -------
    list of PlannedPointCost
        In plan order.

    Notes
    -----
    THE POINT IS FILLED IN, exactly as the campaign loop fills it before it
    builds a script. A swept row states ``ADVANCE_RATIO: sweep`` and the
    VALUE is the point's, so the un-filled row names no rotor speed and its
    clock reported a blank; the column that was asked for is the per-POINT
    cost, and a row is not a point.

    THE STEP COUNT OF EVERY POINT IS RESOLVED ONCE and handed to the fit, so
    a RECORDED run of one of these points can be weighed by the work it did.
    Read off the manifest instead, it is null for every run whose reductions
    were skipped, and the rate comes out by the factor of the steps: the
    reference rotor point was tabled at 7013.5s against a recorded run of
    194.8s of that same point.
    """
    from pyflightstream.cases.workflows import time_steps_of

    recorded = _recorded_costs(workspace)
    filled = {
        entry.run_id: case_at_point(cases_by_sim_id[entry.sim_id], entry.point)
        for entry in plan.points
        if entry.sim_id in cases_by_sim_id
    }
    steps_by_run = {run_id: time_steps_of(case) for run_id, case in filled.items()}
    return priced_rows(
        [
            estimate_point_cost(case, run_id=run_id, recorded=recorded, steps_by_run=steps_by_run)
            for run_id, case in filled.items()
        ],
        filled,
        getattr(workspace, "inputs_dir", None),
    )


#: What `_elide` puts in place of the characters it drops.
MARKER = "..."


def _elide(text: str, width: int) -> str:
    """Shorten a run id to `width`, keeping its END and marking the cut.

    FROM THE LEFT, because the left of a run id is the campaign and the
    simulation, which every row of one table shares, and the right is the
    point, which distinguishes rows. Preserve that suffix and mark truncation
    so long campaign names cannot make distinct points appear identical.
    """
    if len(text) <= width:
        return text
    # Keep the result within the requested width, including widths too small
    # for both the truncation marker and a suffix.
    if width <= len(MARKER):
        return text[-width:] if width > 0 else ""
    return MARKER + text[-(width - len(MARKER)) :]


def format_cost_table(costs: list[PlannedPointCost]) -> str:
    """Render the cost table FR-82 asks for, with its basis under it.

    Parameters
    ----------
    costs : list of PlannedPointCost
        One row per point, as :func:`estimate_point_cost` returns them.

    Returns
    -------
    str
        The fixed-width table, one line per point, followed by one basis
        line per distinct run type; an empty list gives the header alone.
    """
    header = (
        f"{'point':38} {'mesh':>8} {'TEs':>5} {'layers':>7} {'visc':>5} "
        f"{'type':>9} {'steps':>7} {'procs':>6} {'expected':>10} {'samples':>8}"
    )
    rows = [header, "-" * len(header)]
    for cost in costs:
        expected = "unknown" if cost.seconds is None else f"{cost.seconds:.1f}s"
        rows.append(
            f"{_elide(cost.run_id, 38):38} "
            f"{NOT_APPLICABLE if cost.panels is None else cost.panels:>8} "
            f"{NOT_APPLICABLE if cost.trailing_edges is None else cost.trailing_edges:>5} "
            f"{NOT_APPLICABLE if cost.farfield_layers is None else cost.farfield_layers:>7} "
            f"{'yes' if cost.viscous_coupling else 'no':>5} "
            f"{'unsteady' if cost.unsteady else 'steady':>9} "
            f"{NOT_APPLICABLE if cost.time_iterations is None else cost.time_iterations:>7} "
            f"{NOT_APPLICABLE if cost.processors is None else cost.processors:>6} "
            f"{expected:>10} {cost.samples:>8}"
        )
    if costs:
        rows.append("")
        rows.append("EXPECTED TIME IS AN EXTRAPOLATION AND NOT A MEASUREMENT:")
        # Print each distinct basis in row order, so a mixed steady and unsteady
        # table states the evidence supporting each estimate.
        seen: list[tuple[bool, str]] = []
        for cost in costs:
            key = (cost.unsteady, cost.basis)
            if key not in seen:
                seen.append(key)
        for unsteady, basis in seen:
            rows.append(f"  {'unsteady' if unsteady else 'steady'} rows: {basis}")
    return "\n".join(rows)


@dataclass(frozen=True)
class CampaignPlan:
    """The pre-flight plan of one campaign: statuses per point, no execution.

    Attributes
    ----------
    campaign : str
        Campaign name.
    fs_version : str
        Canonical FlightStream version the scripts were validated
        against.
    points : list of PointPlan
        One entry per campaign point, in campaign order.
    plan_file : Path or None
        Where the JSON summary was written: ``post/<matrix>/plan.json``
        for a campaign converted from a run matrix, ``plan.json`` in the
        campaign root otherwise (PFS-2031.04); None when writing was
        disabled.
    build_groups : dict of str to list of str
        Which cases run on which solver installation, keyed by
        :attr:`~pyflightstream.cases.SimCase.fs_build` with the empty
        string standing for the campaign's own. Reported here because
        how many installations a study actually spans is usually a
        surprise, and the pre-flight is the one place it can be learned
        without spending a licensed seat (PFS-2009.09.01).
    """

    campaign: str
    fs_version: str
    points: list[PointPlan] = field(default_factory=list)
    #: Where the campaign name came from, ``directory`` or ``option`` (PFS-2029.03.01).
    campaign_name_from: str | None = None
    plan_file: Path | None = None
    build_groups: dict[str, list[str]] = field(default_factory=dict)
    #: FR-82. One row per point when the caller asks for the cost table, empty
    #: otherwise. Filled by point_costs from the resolved cases held by this plan.
    #: Keep this field last so the public constructor retains its defaults.
    costs: list[PlannedPointCost] = field(default_factory=list)
    #: The generated input guides this plan wrote or rewrote, under
    #: ``inputs/pproc``; empty when they already said what they would say.
    guides: list[Path] = field(default_factory=list)
    #: Resolved row setup details, shared by plan's summary and inspect-setups.
    setup_inspections: list[dict[str, object]] = field(default_factory=list)
    #: The grouping a ``plan --batch`` or ``--polar-sweep`` decided (FR-365); None for single
    #: points. LAST, for the reason of ``costs``.
    grouping: GroupingReceipt | None = None
    #: Each simulation's WHOLE sweep, point names in sweep order (FR-395): what an
    #: alias is numbered against, also for a plan of a ``--sims``/``--points`` selection,
    #: whose ``points`` list only the selection. LAST, for the reason of ``costs``.
    planned_order: dict[str, list[str]] = field(default_factory=dict)

    @property
    def blocked(self) -> list[PointPlan]:
        """The points that cannot run as planned."""
        return [entry for entry in self.points if entry.status is PlanStatus.BLOCKED]

    @property
    def ready(self) -> list[PointPlan]:
        """The points that built cleanly in dry run."""
        return [entry for entry in self.points if entry.status is PlanStatus.READY]

    @property
    def already_recorded(self) -> list[PointPlan]:
        """The points the manifest already holds (resume would skip them)."""
        return [entry for entry in self.points if entry.status is PlanStatus.ALREADY_RECORDED]

    @staticmethod
    def installation_label(key: str) -> str:
        """Name one of :attr:`build_groups` the way a message should say it."""
        return _build_label(key)

    def summary(self) -> str:
        """Return the one-paragraph human summary of the plan."""
        lines = [
            f"campaign {self.campaign!r} on FlightStream {self.fs_version}: "
            f"{len(self.ready)} ready, {len(self.blocked)} blocked, "
            f"{len(self.already_recorded)} already recorded"
        ]
        # The grouping comes FIRST, before any per-point line, because it
        # is the thing an operator has to decide on before starting: one
        # line per installation, whatever the row count.
        if self.build_groups:
            lines.append(f"  {len(self.build_groups)} solver installation(s):")
            for key, sims in self.build_groups.items():
                lines.append(f"    {_build_label(key)}: {len(sims)} case(s) ({', '.join(sims)})")
        for entry in self.blocked:
            lines.append(f"  {entry.run_id}: {entry.error}")
        # A point that waives a broken command, or uses the raw escape
        # hatch, plans READY and is otherwise indistinguishable from a
        # clean one. The operator should learn that here rather than
        # from the manifest, after the solver time is spent.
        waiving = [entry for entry in self.points if entry.waived_commands]
        if waiving:
            commands = sorted({name for entry in waiving for name in entry.waived_commands})
            lines.append(
                f"  {len(waiving)} point(s) waive a command recorded broken: {', '.join(commands)}"
            )
        unvalidated = [entry for entry in self.points if entry.raw]
        if unvalidated:
            lines.append(f"  {len(unvalidated)} point(s) use the raw() escape hatch")
        lines.extend(_point_lines(self.points))
        return "\n".join(lines)


def _point_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the per-point lines of the plan's summary in display order."""
    lines: list[str] = []
    # M1: every unsteady rotor point states its rotors' tip and
    # helical Mach numbers, or why they are not known.
    for entry in points:
        for alias, mach in entry.rotor_mach.items():
            lines.append(f"  {entry.run_id}: {rotor_mach_line(alias, mach)}")
    # Every quasi-steady wheel point states the four values of its
    # blade's 1P reduced frequency, or why the chord is not known.
    for entry in points:
        if entry.qsteady_validity:
            lines.append(f"  {entry.run_id}: {qsteady_validity_line(entry.qsteady_validity)}")
            harmonics = entry.qsteady_validity.get("inflow_fft")
            if isinstance(harmonics, Mapping):
                lines.append(f"  {entry.run_id}: {inflow_harmonics_line(harmonics)}")
    # FR-584: every rotor point states the wake its termination keeps.
    for entry in points:
        if entry.wake_termination:
            lines.append(f"  {entry.run_id}: {wake_termination_line(entry.wake_termination)}")
    # FR-906: a run length stated as a wake length states its count.
    for entry in points:
        if entry.run_wake_length:
            lines.append(f"  {entry.run_id}: {run_wake_length_line(entry.run_wake_length)}")
    return lines + _streamline_lines(points) + _farfield_lines(points)


def _streamline_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return the plan's line per point that seeds off-body streamlines (FR-1079)."""
    return [
        f"  {entry.run_id}: {entry.streamlines} off-body streamlines traced "
        "(the [streamlines] lines and tubes of its pproc)"
        for entry in points
        if entry.streamlines
    ]


def _farfield_lines(points: Sequence[PointPlan]) -> list[str]:
    """Return one line per far-field input a plan adds or cannot serve (FR-1047)."""
    lines: list[str] = []
    for entry in points:
        inputs = entry.farfield.get("inputs", ()) if entry.farfield else ()
        for item in cast(Sequence[Mapping[str, object]], inputs):
            if item.get("state") in ("added", "not_applicable", "refused"):
                lines.append(f"  {entry.run_id}: far field {farfield_line(item)}")
    return lines


def farfield_line(item: Mapping[str, object]) -> str:
    """Return one far-field input of the plan as its console line (FR-1047)."""
    what = item.get("source") or item.get("reason") or ""
    return f"{item.get('analysis')} {item.get('input')} {item.get('state')}: {what}".rstrip(": ")


def run_wake_length_line(run: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's run length from a wake length (FR-422).

    ``run`` is one :attr:`PointPlan.run_wake_length`: the length asked, the
    resolved step count and the revolutions it turns, and the V_ax with the
    rule that gave it. The length is nominal (FR-908), so the revolutions are
    what a user checks near hover.
    """
    return (
        f"run length RUN_WAKE_LENGTH_R = {run.get('length_r'):g} R: "
        f"{run.get('time_iterations')} steps, {run.get('revolutions'):.4g} revolution(s), "
        f"V_ax {run.get('v_ax_m_s'):.4g} m/s ({run.get('rule')})"
    )


def wake_termination_line(wake: Mapping[str, object]) -> str:
    """Return the words the plan prints for one rotor point's wake termination (FR-584).

    ``wake`` is one :attr:`PointPlan.wake_termination`: the L asked, the V_ax
    used with the rule that gave it, and the steps emitted; a count states
    itself, its steps and the length it keeps over the run (FR-601).
    """
    steps, length, speed = wake.get("steps"), wake.get("length_r"), wake.get("v_ax_m_s")
    if not isinstance(length, int | float):
        kept = WakeTermination(**cast(dict[str, Any], wake)).count_kept_r()
        keeps = "an unknown length" if kept is None else f"about {kept:.3g} R"
        return f"wake termination {wake.get('stated_as')}: {steps} steps, keeping {keeps} of wake"
    if steps is None:
        return (
            f"wake termination L = {length:g} R ({wake.get('stated_as')}) not converted: "
            "no rotor radius is known, so no termination line is written"
        )
    used = f"{speed:.4g} m/s" if isinstance(speed, int | float) else "none"
    return (
        f"wake termination L = {length:g} R ({wake.get('stated_as')}), V_ax {used} "
        f"({wake.get('rule')}), {steps} steps"
    )


def qsteady_validity_line(validity: Mapping[str, object]) -> str:
    """Return the words the plan prints for one quasi-steady wheel point.

    ``validity`` is one :attr:`PointPlan.qsteady_validity`.
    """
    note = validity.get("note")
    if note:
        root, tip = validity.get("k_per_chord_m_root"), validity.get("k_per_chord_m_tip")
        known = (
            f"; k per metre of chord {root:.4f} at the root, {tip:.4f} at the tip"
            if isinstance(root, int | float) and isinstance(tip, int | float)
            else ""
        )
        return f"quasi-steady validity not computed: {note}{known}"
    return f"quasi-steady validity (1P reduced frequency): {summarise_validity(validity)}"


def inflow_harmonics_line(harmonics: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's ``--inflow-fft`` record.

    nP is counted on ONE BLADE (how many times it meets the perturbation per
    revolution), not the blade-passing N P of a fixed surface nor the rotor
    total (:mod:`pyflightstream.cases.qsteady`).
    """
    note = harmonics.get("note")
    if harmonics.get("n_max") is None:
        return f"inflow harmonics not computed: {note}"
    words = summarise_inflow_harmonics(harmonics)
    return f"{words}; {note}" if note else words


def rotor_mach_line(alias: str, mach: Mapping[str, object]) -> str:
    """Return the words the plan prints for one rotor of one point (M1).

    ``mach`` is one entry of :attr:`PointPlan.rotor_mach`.
    """
    tip, helical = mach.get("mach_tip"), mach.get("mach_helical")
    kind = mach.get("kind") or "rotor"
    if isinstance(tip, int | float) and isinstance(helical, int | float):
        line = f"{kind} {alias} M_tip {tip:.3f}, M_hel {helical:.3f}"
        advancing = mach.get("mach_advancing")
        if isinstance(advancing, int | float):
            line += f", M_adv {advancing:.3f}"
            if mach.get("mach_advancing_bound") == "edgewise":
                line += " (rotor axis not resolved: the edgewise bound)"
        return line
    return f"{kind} {alias} M_tip and M_hel not computed: {mach.get('note')}"


#: FR-97: plan is mandatory before run. It pre-flights points and writes
#: the receipt required by run; describe only those operations here.
PLAN_REQUIRED_MESSAGE = (
    "no plan for this matrix, and a run needs one. Run "
    "`pyfs-matrix plan <matrix>` first: it pre-flights every point without "
    "spending any solver time, reports which are blocked and which are already "
    "recorded, and writes the receipt this refusal is asking for. Add --cost for "
    "what the run is expected to cost."
)


def plan_receipt_error(
    workspace: CampaignWorkspace, matrix_path: str | Path | None, matrix_stem: str | None
) -> str | None:
    """Return why this run may not proceed on the plan it has, or None.

    THREE ANSWERS, and the third is the one the pin exists for:

    * no matrix: a campaign authored in Python is not planned through a
      file and this gate does not apply to it.
    * no plan file: refused, naming the command that writes one.
    * a plan whose ``matrix_sha256`` is not the matrix on disk: refused,
      because the plan measured a different study. A plan that predates
      the pin carries None and is refused the same way, which is right:
      it cannot say what it read.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign root whose plan folder is searched for ``plan.json``.
    matrix_path : str or Path, optional
        The matrix file the run reads; None for a campaign authored in
        Python.
    matrix_stem : str, optional
        The matrix file name without extension, which names the plan
        folder under ``post/``.

    Returns
    -------
    str or None
        The refusal text, or None when the run may proceed.
    """
    if matrix_path is None:
        return None
    plan_file = workspace.plan_dir(matrix_stem) / "plan.json"
    if not plan_file.is_file():
        return f"{PLAN_REQUIRED_MESSAGE} Expected it at {plan_file}."
    try:
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return f"the plan at {plan_file} cannot be read: {error}. {PLAN_REQUIRED_MESSAGE}"
    planned = payload.get("matrix_sha256")
    current = _file_digest(matrix_path)
    if planned is None:
        return (
            f"the plan at {plan_file} does not say which matrix it measured, so it "
            f"cannot be shown to be about this one. {PLAN_REQUIRED_MESSAGE}"
        )
    if planned != current:
        return (
            f"the matrix changed since it was planned: the plan at {plan_file} measured "
            f"{planned[:12]} and {Path(matrix_path).name} is {str(current)[:12]} now. "
            "Plan it again; a plan that measured another study is not a plan for this "
            "one."
        )
    return None


@noting_the_families_rows_lack()  # FR-320: each family a row lacks, said once
@noting_the_study_skips()  # FR-435: each name a study holds and a row's model lacks, said once
def plan_campaign(
    campaign: Campaign,
    workspace: CampaignWorkspace,
    *,
    recipes: dict[str, ScriptRecipe] | None = None,
    write_plan: bool = True,
    name_from: str | None = None,
    builds: Mapping[str, SolverBuild] | None = None,
    versions: Mapping[str, str] | None = None,
    matrix_path: str | Path | None = None,
    accept_unregistered_build: bool = False,
    setup_inspections: Sequence[dict[str, object]] | None = None,
    inflow_fft: bool = False,
    accepted_builds: Collection[str] = (),
    planned_order: Mapping[str, Sequence[str]] | None = None,
) -> CampaignPlan:
    """Pre-flight a campaign: validate every point without executing any.

    ``inflow_fft`` (``pyfs-matrix plan --inflow-fft``) adds to each
    quasi-steady wheel point in a custom inflow the harmonic content of that
    inflow as one blade meets it
    (:func:`pyflightstream.cases.workflows.qsteady_inflow_fft`).

    Per case, in order: allocate the managed simulation folders,
    resolve the recipe, and verify the geometry file exists; per
    point: render the output names through the naming template and
    build the whole script in dry run (the builder validates phase,
    version, and entity references without a solver, and the dry-run
    script is not written to ``scripts/``, so the files of a later
    real run stay the only scripts on disk). Points whose ``run_id``
    is already in the manifest, and the points a recorded job of their
    steady row ran, are marked ALREADY_RECORDED, which is exactly what
    ``run_campaign(..., resume=True)`` would skip; this pairing is what
    lets a sweep grow points and re-run safely. The new points of a row
    whose job is recorded are READY, and resume runs them one each.

    Nothing is executed and nothing is appended to the manifest: a
    broken recipe or a missing geometry surfaces here, before any
    solver time is spent, instead of as a FAILED_SCRIPT record inside
    the campaign loop.

    Parameters
    ----------
    campaign : Campaign
        What would run; its ``fs_version`` is resolved to canonical
        and every dry-run script is validated against it.
    workspace : CampaignWorkspace
        The managed campaign root; folders are allocated, the
        manifest is read, nothing else is touched.
    recipes : dict of str to ScriptRecipe, optional
        Named recipe registry, as in :func:`run_campaign`.
    write_plan : bool
        Write the JSON summary as ``plan.json``, under ``post/<matrix>/``
        for a campaign converted from a run matrix and in the campaign
        root otherwise (overwritten on each call; a convenience report,
        never an identity source). Default True.
    name_from : str, optional
        Where the campaign name came from, ``option`` or ``directory``,
        recorded in the plan; None when the caller does not say.
    builds : mapping of str to SolverBuild, optional
        As in :func:`run_campaign`, and pre-flighting is where it earns
        its keep: a case sent to a second build has its dry-run script
        validated against THAT build's version, so a command the second
        installation does not carry blocks the point here rather than
        failing after the first one has already run. A case naming a
        build the mapping does not carry is refused, exactly as the
        campaign loop refuses it, so the pre-flight cannot pass a
        configuration the run will reject.
    versions : mapping of str to str, optional
        Per simulation id, the version its scripts are emitted under,
        for a pre-flight that binds no executable: ``plan_matrix`` and
        ``run_matrix`` both read it off the build registry for the build
        each row named (``_row_versions``), so a row naming a second build
        has its dry-run script validated against that build's grammar
        away from the licensed machine (PFS-2009.05). A row on 26.123 in a
        matrix defaulting to 26.120 is checked against 26.123's grammar,
        including commands absent from 26.120.
        ``builds`` wins where both name a build.
    matrix_path : str or Path, optional
        The matrix file the campaign was converted from. Its SHA-256 is
        written into ``plan.json`` so ``run`` can refuse a plan that
        measured a different study; None for a campaign authored in Python.
    accept_unregistered_build : bool
        Recorded in ``plan.json`` so the plan rehearses the command line
        ``run`` executes; no solver is launched here, so no check changes.
        Default False.
    setup_inspections : sequence of dict, optional
        The setup inspections to carry into the plan and its
        ``plan.json``; None for none.
    inflow_fft : bool
        With True, each quasi-steady wheel point in a custom inflow also
        carries the harmonic content of that inflow. Default False.
    accepted_builds : collection of str
        The installations whose own entry of ``inputs/executables.local.toml``
        accepts their installed build (FR-998), a build id or ``""`` for
        the campaign's own. ``plan.json`` then states the acceptance, the
        builds it holds for and its file, as the run's records will. Default
        empty.
    planned_order : mapping of str to sequence of str, optional
        Per simulation id, the point names of its WHOLE sweep in sweep order,
        for a campaign narrowed to a ``--sims``/``--points`` selection before
        planning (FR-326): run id aliases are numbered against the whole sweep,
        as ``run`` numbers them (FR-395). None reads it off ``campaign``, which
        is the whole sweep when nothing was selected. Written into ``plan.json``
        as ``planned_order`` and onto :attr:`CampaignPlan.planned_order`.

    Returns
    -------
    CampaignPlan
        One :class:`PointPlan` per point; inspect ``blocked`` before
        running, or print ``summary()``.

    Raises
    ------
    ExecutorConfigurationError
        When a case names an ``fs_build`` that ``builds`` does not
        carry.
    WorkspaceError
        When :meth:`CampaignWorkspace.read_manifest` refuses a recorded
        row, for example a surface averaging window that does not
        validate.

    Warns
    -----
    PyflightstreamWarning
        A row whose actuator disc is RELAXED and names a loading profile
        (FR-332, :func:`_warn_on_relaxed_discs_naming_a_profile`); the
        point plans as it would without the warning.
    PyflightstreamWarning
        A rotor point whose wake may not reach the length it asks, or whose
        wake end plane is the solver's default or sits before it (FR-325,
        :func:`_warn_on_short_wakes`); the plan is what it would be without it.
    PyflightstreamWarning
        Once per artifact, key and name, a name a row's setup or pproc cites
        that its reference's study holds and its model lacks, naming every
        such row (FR-987); the plan status is what it would be without it.
    """
    canonical = resolve(campaign.fs_version).canonical
    # Before the first folder is allocated, for the reason run_campaign
    # states: a missing build is knowable up front, and discovering it
    # halfway leaves a plan that describes part of a campaign.
    case_builds = [_case_build(case, builds) for case in campaign.sims]
    manifest = {record.run_id: record for record in workspace.read_manifest()}
    recorded = set(manifest)
    points: list[PointPlan] = []
    shared = _names_two_cases_share(campaign, workspace)
    for case, build in zip(campaign.sims, case_builds, strict=True):
        # The row's build decides, then the version read for the row, then the campaign's.
        case_version = (versions or {}).get(case.sim_id, campaign.fs_version)
        if build is not None:
            case_version = build.fs_version
        workspace.create_sim(case.sim_id)
        case_error = _plan_case_error(campaign, case, workspace, recipes) or shared.get(case.sim_id)
        recipe: ScriptRecipe | None = None
        if case_error is None:
            # `resolve_recipe` returns the imported function as a plain Callable; it
            # is a ScriptRecipe, whose named parameters a Callable type cannot state.
            # FR-987: the build notes what the row's model lacks and its study holds.
            recipe = saying_the_study_skips(
                recipes[case.recipe]
                if recipes and case.recipe in recipes
                else cast(ScriptRecipe, resolve_recipe(case.recipe))
            )
        if case_error is None:
            case_error = _one_job_error(campaign, case, workspace, case_version)
        # A POINT A RECORDED JOB OF ITS ROW RAN IS RECORDED, although no record
        # carries the point's own id: the question `run_campaign` asks before a
        # resume, asked here of the same helper, so READY is what resume runs.
        case_points = list(case.sweep.points())
        recorded_here = recorded
        ran = _points_the_recorded_job_ran(campaign, case, manifest)
        if ran is not None:
            recorded_here = recorded | {
                _run_id(campaign, case, point)
                for point in case_points
                if point_name(case, point) in ran
            }
        for point in case_points:
            points.append(
                _plan_point(
                    campaign,
                    case,
                    point,
                    workspace,
                    recipe,
                    case_error,
                    recorded_here,
                    fs_version=case_version,
                    inflow_fft=inflow_fft,
                    write_products=write_plan,
                )
            )
    _warn_on_relaxed_discs_naming_a_profile(campaign.sims)
    _warn_on_short_wakes(points)
    groups = _build_groups(campaign)
    order = _planned_order(campaign, planned_order)
    plan_file = None
    if write_plan:
        plan_file = workspace.plan_dir(campaign.matrix_stem) / "plan.json"
        payload = {
            "campaign": campaign.name,
            "campaign_name_from": name_from,
            "fs_version": canonical,
            "package_version": pyflightstream.__version__,
            "build_groups": groups,
            "setup_inspections": list(setup_inspections or ()),
            "points": [_point_record(entry) for entry in points],
            # FR-395: the whole sweep, the order an alias is numbered against.
            PLANNED_ORDER_KEY: order,
            # FR-97: WHICH MATRIX THIS PLAN MEASURED. A
            # mandatory plan that does not say is satisfied by a stale one,
            # and then "plan, edit the matrix, run" passes a gate that read
            # a different study. None when the campaign was authored in
            # Python and has no matrix to pin to; `run` asks for a plan
            # only where a matrix exists.
            "matrix_sha256": _file_digest(matrix_path) if matrix_path else None,
            # Plan launches no solver, so the flag changes no check here;
            # it is recorded so the plan rehearses the command line run executes.
            "accept_unregistered_build": accept_unregistered_build,
            # FR-998, FR-999: what the workspace files gave this plan, and where
            # from; nothing where no file gave anything.
            **_settings_provenance(campaign, accept_unregistered_build, accepted_builds),
        }
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        if campaign.matrix_stem:
            # P0320-RESTORE-ARCHIVE: the plan this one replaces, for `restore plan`.
            archive_previous(workspace.root, plan_file, matrix=campaign.matrix_stem)
        _textio.write_text(plan_file, json.dumps(payload, indent=2) + "\n")
    return CampaignPlan(
        campaign=campaign.name,
        fs_version=canonical,
        campaign_name_from=name_from,
        points=points,
        plan_file=plan_file,
        build_groups=groups,
        setup_inspections=list(setup_inspections or ()),
        planned_order=order,
    )


def _one_job_error(
    campaign: Campaign, case: SimCase, workspace: CampaignWorkspace, version: str
) -> str | None:
    """Rehearse the shared steady script in addition to each point's recipe."""
    if not _ids._is_one_job(campaign, case):
        return None
    try:
        point_cases = [
            case_at_point(case, point, outputs=_point_names(campaign, case, point, workspace)[1])
            for point in case.sweep.points()
        ]
        script = Script(version=version)
        script.working_dir = str(workspace.sim_dir(case.sim_id))
        workflows.build_steady_sweep(point_cases, script, cold=_ids._is_cold_start(case))
        script.render()
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    return None


def _planned_order(
    campaign: Campaign, given: Mapping[str, Sequence[str]] | None
) -> dict[str, list[str]]:
    """Return each simulation's whole sweep: ``given`` where it names one, else the campaign's."""
    order = {
        case.sim_id: [point_name(case, point) for point in case.sweep.points()]
        for case in campaign.sims
    }
    for sim, names in (given or {}).items():
        order[sim] = list(names)
    return order


def _settings_provenance(
    campaign: Campaign, accepted: bool, accepted_builds: Collection[str]
) -> dict[str, object]:
    """Return what ``plan.json`` adds where a workspace file stated a value (FR-998, FR-999).

    ``settings_sources`` names each value this invocation took from ``pyfs.toml``
    or ``pyfs.local.toml`` and its file; an acceptance stated on a build's own
    entry makes ``accept_unregistered_build`` true, lists the builds it holds
    for under ``accepted_builds`` and names ``executables.local.toml``; an
    acceptance typed is named ``typed`` beside another value taken from a file.
    Empty where no file stated anything, so such a plan is written as before.
    """
    sources = invocation_sources()
    extra: dict[str, object] = {}
    if accepted and sources and "accept_unregistered_build" not in sources:
        sources["accept_unregistered_build"] = TYPED_ACCEPTANCE_SOURCE
    if accepted_builds and not accepted:
        extra["accept_unregistered_build"] = True
        extra["accepted_builds"] = sorted(key or campaign.fs_version for key in accepted_builds)
        sources["accept_unregistered_build"] = ENTRY_ACCEPTANCE_SOURCE
    if sources:
        extra["settings_sources"] = sources
    return extra


def _plan_case_error(
    campaign: Campaign,
    case: SimCase,
    workspace: CampaignWorkspace,
    recipes: dict[str, ScriptRecipe] | None,
) -> str | None:
    """Return what blocks a whole case (recipe, outputs, geometry), or None."""
    try:
        if recipes and case.recipe in recipes:
            check_recipe(case.recipe, recipes[case.recipe])
        else:
            resolve_recipe(case.recipe)
    except ValueError as error:
        return str(error)
    collision = _output_collision(campaign, case, workspace)
    if collision is not None:
        return collision
    if case.geometry is not None and not Path(case.geometry).is_file():
        return (
            f"geometry file {case.geometry} does not exist; the campaign loop "
            "stages it into the managed inputs/ folder before execution, so the "
            "authored path must point at a real file (check the path, or resolve "
            "it from the workspace geometry library)."
        )
    return None


def _discs_naming_a_profile(case: SimCase) -> list[tuple[str, str]]:
    """Return ``(disc, profile stem)`` for every disc of the row that names a profile.

    The flat form (``ACTUATOR: <block> / PROFILE: <stem>``) and the brace
    records alike. A row the builder would refuse yields nothing here: the
    point is reported BLOCKED with the builder's own reason.
    """
    try:
        records = actuator_records(case)
    except CampaignConfigError:
        return []
    if not records:
        records = [
            {key: str(case.variables.get(key, "")) for key in (ACTUATOR_VARIABLE, PROFILE_VARIABLE)}
        ]
    return [
        (record[ACTUATOR_VARIABLE].strip(), record[PROFILE_VARIABLE].strip())
        for record in records
        if record.get(ACTUATOR_VARIABLE, "").strip() and record.get(PROFILE_VARIABLE, "").strip()
    ]


def _warn_on_relaxed_discs_naming_a_profile(cases: Sequence[SimCase]) -> None:
    """Warn, and never refuse, on a RELAXED disc whose row names a loading profile (FR-646).

    Measured on 26.124 (RPT-137): a disc of wake type RELAXED gave the same
    wake for every loading profile and for the native ELLIPTICAL model, and
    carried about half of the thrust asked, so the profile the row names
    does not reach the wake. The warning names the row, the disc and the
    report; the plan, its statuses and its file are what they would be
    without it. A RIGID disc naming a profile, and a RELAXED disc loaded by
    its net thrust, are not warned about.
    """
    for case in cases:
        for name, profile in _discs_naming_a_profile(case):
            block = case.actuators.get(name)
            if block is None or block.wake_type != "RELAXED":
                continue
            warnings.warn(
                f"row {case.sim_id!r}: the actuator disc {name!r} has wake_type RELAXED and "
                f"names the loading profile {profile!r}. Measured on 26.124 (RPT-137), a "
                "RELAXED disc ignored a custom loading profile and carried about half of the "
                "thrust asked; the run goes ahead as planned. A RIGID disc reads the profile.",
                PyflightstreamWarning,
                stacklevel=3,
            )


def _point_record(entry: PointPlan) -> dict[str, Any]:
    """Return one point as ``plan.json`` writes it.

    The run length of FR-422 is written only where the row states it, so a
    plan omits its keys for rows without that setting.
    """
    record = {**asdict(entry), "status": str(entry.status)}
    if not entry.run_wake_length:
        del record["run_wake_length"]
    if not entry.streamlines:
        del record["streamlines"]
    # FR-1047: the far-field resolution, on a row with [farfield] only.
    if not entry.farfield:
        del record["farfield"]
    for key in ("fsi", "inflow_harmonics"):
        if not record[key]:
            del record[key]
    return record


def _point_facts(
    point_case: SimCase, *, inflow_fft: bool, fs_version: str | None = None
) -> dict[str, Any]:
    """Return what a point's plan states about its rotors, wheel and wake, READY or not.

    The rotors' tip and helical Mach numbers (M1), a quasi-steady
    wheel's 1P reduced frequency and, on a rotor point, the wake its
    termination keeps (FR-584).
    """
    wake = planned_wake(point_case)
    run = planned_run_wake(point_case)
    return {
        "rotor_mach": {mach.alias: mach.record() for mach in rotor_machs(point_case)},
        "qsteady_validity": qsteady_validity(point_case, inflow_fft=inflow_fft) or {},
        "wake_termination": {} if wake is None else wake.record(),
        "run_wake_length": {} if run is None else run.record(),
        "streamlines": streamline_count(point_case),
        "farfield": {} if fs_version is None else farfield_plan_record(point_case, fs_version),
    }


def _warn_on_short_wakes(points: Sequence[PointPlan]) -> None:
    """Warn, and never refuse, on every READY rotor point whose wake may fall short (FR-325).

    The plan warns always: when the run
    has fewer revolutions than the length asked needs, at the 4R default and at
    any larger length; when a step or revolution count keeps less than the 4R
    recommendation; when a stated wake end plane sits before the length; and
    on the solver's DEFAULT plane, whose position the plan cannot know. Each
    warning names the row and the point. Computed from the plan's own records:
    no solver call and no file read, and the plan's statuses and file are what
    they would be without it (FR-605).
    """
    for entry in points:
        if entry.status is not PlanStatus.READY or not entry.wake_termination:
            continue
        wake = WakeTermination(**cast(dict[str, Any], entry.wake_termination))
        for message in wake_warnings(f"row {entry.sim_id!r} ({entry.run_id})", wake):
            warnings.warn(message, PyflightstreamWarning, stacklevel=3)


def _plan_point(
    campaign: Campaign,
    case: SimCase,
    point: dict[str, float],
    workspace: CampaignWorkspace,
    recipe: ScriptRecipe | None,
    case_error: str | None,
    recorded: set[str],
    *,
    fs_version: str,
    inflow_fft: bool = False,
    write_products: bool = True,
) -> PointPlan:
    """Judge one point in dry run: names, script build, manifest state.

    ``fs_version`` is the version the dry-run script is built against,
    which is the campaign's unless the case named its own build; it is
    keyword-only and has no default, so a caller cannot silently fall
    back to the campaign's version for a case that runs elsewhere.
    """
    run_id = _run_id(campaign, case, point)
    # A keyword bag for PointPlan: values differ by key, hence ``Any``.
    base: dict[str, Any] = {"run_id": run_id, "sim_id": case.sim_id, "point": dict(point)}
    if recipe is None:
        return PointPlan(
            **base,
            script_name=None,
            status=PlanStatus.BLOCKED,
            error=case_error or "recipe resolution failed",
        )
    try:
        stem, outputs = _point_names(campaign, case, point, workspace)
    except NamingTemplateError as error:
        return PointPlan(**base, script_name=None, status=PlanStatus.BLOCKED, error=str(error))
    script_name = f"{stem}.txt"
    point_case = case_at_point(case, point, outputs=outputs)
    # M1: record tip and helical Mach numbers even for blocked points; their
    # rotors may still reach the speed of sound. Likewise record a quasi-steady
    # wheel's blade 1P reduced frequency and a rotor point's wake.
    base.update(_point_facts(point_case, inflow_fft=inflow_fft, fs_version=fs_version))
    if case_error is not None:
        return PointPlan(
            **base, script_name=script_name, status=PlanStatus.BLOCKED, error=case_error
        )
    # Resolve a continuation exactly as run does: its saved file and step count
    # come from the previous record, not the RESTART row. The builder needs
    # those resolved inputs to rehearse the script.
    #
    # Do not archive during pre-flight. Only run replaces existing outputs.
    #
    # A point its request cannot continue is RECORDED and explained (FR-96): a
    # completed continuation of the same request, FINISH_PENDING on CONVERGED,
    # a steady run or a queued one. A failed latest run goes to the resolver,
    # which refuses it by name, so plan reports BLOCKED with that reason.
    restarting = (verdict := point_verdict(workspace, case, point)) is not None
    base["continuation"] = verdict.said if verdict else None
    if verdict is not None and not verdict.pending:
        return PointPlan(**base, script_name=script_name, status=PlanStatus.ALREADY_RECORDED)
    try:
        # An unreadable COLD_START is refused here, where the plan reports it
        # BLOCKED, and not first inside run_campaign's loop after earlier
        # rows have spent the seat.
        _ids._is_cold_start(case)
        rehearsed = resolve_continuation(
            workspace, case, point, run_id=run_id, recipe=recipe, fs_version=fs_version
        )
    except (WorkspaceError, CampaignConfigError) as error:
        return PointPlan(
            **base, script_name=script_name, status=PlanStatus.BLOCKED, error=str(error)
        )
    if rehearsed is not None:
        point_case = point_case.model_copy(
            update={
                "variables": {
                    **point_case.variables,
                    # Where the file is NOW, absolutely: the rehearsal archives
                    # nothing, so the run's archived path does not exist yet.
                    RESTART_FROM_VARIABLE: str(
                        (workspace.sim_dir(case.sim_id) / str(rehearsed["saved"])).resolve()
                    ),
                    RESTART_ITERATIONS_VARIABLE: str(rehearsed["iterations"]),
                    RESTART_STEP_OFFSET_VARIABLE: str(rehearsed["step_offset"]),
                }
            }
        )
    script = Script(version=fs_version)
    try:
        recipe(point_case, script)
        base.update(_structural_facts(point_case))
        # G02: the plan knows no machine, so a log export the row turned off
        # is refused here, before any run can spend a seat on it.
        _refuse_an_import_count_nothing_logs(point_case, script, None)
        script.render()
        _inflow_plan_products(
            base,
            point_case,
            workspace,
            campaign.matrix_stem,
            stem,
            inflow_fft=inflow_fft,
            write_products=write_products,
        )
    except Exception as error:  # recipes are user code; any failure blocks the point
        return PointPlan(
            **base,
            script_name=script_name,
            status=PlanStatus.BLOCKED,
            error=f"{type(error).__name__}: {error}",
        )
    # FR-1047 (PFS-2081.56): the far-field probes this dry-run script
    # chose, reused or added, which are the ones the run lays and records.
    if base.get("farfield"):
        base["farfield"] = farfield_plan_record(point_case, fs_version, script)
    # This dry run built the point recipe; one-job rows also rehearse the
    # shared sweep in _one_job_error. These provenance flags describe the
    # point recipe. Neither rehearsal promises the run's exact bytes,
    # and the difference is one argument: the plan runs before
    # anything is staged, so a case naming a geometry renders `OPEN
    # <library path>` here and `OPEN <staged copy>` at run time. A raw mesh
    # on the trailing-edge file route, and an actuator disc loaded by a
    # profile, differ in a second: the script is given no working folder here,
    # so the node file and the profile's copy are named by their bare names
    # (G02, G06, `Script.working_dir`). Nothing
    # depends on that today (the plan checks the library file exists, the
    # builder judges only the suffix, and plan.json carries no script
    # text), and it is written down so a later reader does not reuse this
    # render AS the run's. Two things make that reuse wrong even for a
    # case naming no geometry: `write_script` writes in text mode, so on
    # this Windows-primary machine the bytes the solver reads and
    # `script_sha256` hashes carry CRLF while `render()` returns LF; and
    # a RECIPE is user code that may read `case.geometry` in more than one
    # place, or branch on it, so the one-argument difference is a property
    # of the two shipped builders rather than of the mechanism.
    # Reported at plan time
    # rather than only in the manifest: an operator who learns from the
    # manifest that a point leaned on a broken command has already spent
    # the solver time (PYFS-002, and the pre-flight promise of FR-14).
    waived = tuple(use.command for use in script.waived_commands)
    if run_id in recorded and not restarting:
        return PointPlan(
            **base,
            script_name=script_name,
            status=PlanStatus.ALREADY_RECORDED,
            waived_commands=waived,
            raw=script.raw_flag,
            march_strategy=script.march_strategy,
        )
    return PointPlan(
        **base,
        script_name=script_name,
        status=PlanStatus.READY,
        waived_commands=waived,
        raw=script.raw_flag,
        march_strategy=script.march_strategy,
    )


def _inflow_plan_products(
    base, case, workspace, matrix_stem, stem, *, inflow_fft, write_products
) -> None:
    """Write requested inflow diagnostics and attach their workspace-relative paths."""
    if inflow_fft and write_products:
        from pyflightstream.workspace import write_plan_products

        base["inflow_harmonics"] = [
            path.relative_to(workspace.root).as_posix()
            for path in write_plan_products(
                case, workspace.plan_dir(matrix_stem) / "inflow" / case.sim_id / stem
            )
        ]


def _output_collision(
    campaign: Campaign, case: SimCase, workspace: CampaignWorkspace
) -> str | None:
    """Return why ONE point's output names collide, or None.

    A point's declared outputs are collected into that point's own
    folder under the name
    :func:`pyflightstream.workspace.collection_name` gives them, so two
    outputs of one point that collect to a single name overwrite each
    other's evidence while the manifest lists the survivor for both
    (incident INC-20260723-2113-pyflightstream). The check renders the
    names the way the loop will, so it judges the actual collision
    rather than the presence of a particular placeholder.

    Check cross-point collisions (FR-92). Each point collects into its own
    ``datapoints/DP-<point>/`` folder, but ``post/products.py`` keys products
    by the loads file's stem. Repeated stems can overwrite a product or
    duplicate one point in a superfile, so separate collection folders do
    not establish unique product names.

    So the check stays, and its REASON is what changed: it is about the
    products a name will collide in, not about the folder it lands in.
    Making those product names carry the point tag the folder already
    carries would let it be lifted, and that is registered rather than
    taken on release eve, because it moves file names a user's
    downstream scripts read.

    The within-one-point half is the half that kept being got wrong
    (PLN-20260802-1904). Two inputs planned as READY and died at
    collection, each after the solver had run and each costing a
    licensed seat:

    * ``["loads.txt", "loads.txt"]`` on a single point, because the
      old check skipped a repeat carrying the same point tag as itself;
    * ``["a/loads.txt", "b/loads.txt"]`` on one point, because it keyed
      on the DECLARED string, where those differ, while collection keys
      on the base name, where they do not.

    The keying is the shared function, so the plan-time answer and the
    collect-time answer cannot disagree again.
    """
    seen: dict[str, str] = {}
    for point in case.sweep.points():
        try:
            _, names = _point_names(campaign, case, point, workspace)
        except NamingTemplateError:
            return None  # the rendering error is reported by the point itself
        tag = point_name(case, point)
        within: dict[str, str] = {}
        for declared in names:
            collected = collection_name(declared)
            if collected in within:
                first = within[collected]
                detail = (
                    f"{first!r} and {declared!r}" if first != declared else f"{declared!r}, twice"
                )
                return (
                    f"sim {case.sim_id!r} declares {detail} for point {tag}, and both "
                    f"collect to {SIM_DATAPOINTS_DIR}/{datapoint_dir_name(PointName(tag))}/"
                    f"{collected}: collection moves each output under its "
                    "base name, so the second would overwrite the first and the manifest "
                    "would record one name twice while only the last content survived. "
                    "Declare outputs whose base names differ; a directory part does not "
                    "make them differ, because collection drops it"
                )
            within[collected] = declared
        for collected, declared in within.items():
            if collected in seen:
                return (
                    f"sim {case.sim_id!r} would write {declared!r} for point {tag} and "
                    f"the same collected name {collected} for point {seen[collected]}: "
                    "each point collects into its own folder, so nothing is "
                    "overwritten there, and what two points sharing one collected "
                    "name lose is the ability to be told apart anywhere downstream. "
                    "MEASURED FOR THE LOADS TABLE, which is the case that costs "
                    "data: a point's post-processing products are named after its "
                    "loads file's stem, so two points produce ONE table naming both "
                    "runs while holding one point's, and a superfile recording one "
                    "point twice. The check is applied to EVERY declared name rather "
                    "than only the loads one, deliberately and knowing that some "
                    "kinds produce no product: which kind a name turns out to be "
                    "depends on the recipe that exports it, and refusing a name that "
                    "would have been safe costs a rename while allowing one that is "
                    "not costs a run. Name the outputs per point, for example "
                    "'loads_{point}.txt', and export case.outputs[i] from the recipe"
                )
            seen[collected] = tag
    return None


def _names_two_cases_share(campaign: Campaign, workspace: CampaignWorkspace) -> dict[str, str]:
    """Return, per ``sim_id``, why a case renders an output name another case renders too.

    :func:`_output_collision` ACROSS CASES, keyed the same way, by the
    name collection files an output under. Each simulation collects into its
    own folder, so nothing on disk is overwritten there. WHERE TWO CASES MEET
    IS THE PRODUCTS FOLDER, which a campaign has one of: every per-point
    product (sections, probes, plots, reductions, series) is named by the stem
    of the point's loads file and carries no simulation id. The library's
    default point name writes the flight condition alone, so two cases at one
    condition (two geometries, two post-processing artifacts) render one stem,
    and the second case's product archives the first one's and takes its key in
    the products manifest.

    The matrix command line names by ``{polar}``, which carries ``P<sim>-``,
    and never meets this. A campaign authored in Python does, and is refused
    HERE, at plan time, for BOTH cases, because neither is the one at fault.

    A campaign converted from a matrix (``matrix_stem`` set) is excluded.
    Matrix rows may repeat a condition under the default template. When
    driven from Python without ``{polar}``, that path remains exposed to
    duplicate names; this check does not cover it.

    Empty when no two cases share a name. A case whose names cannot be
    rendered is left to its own points, which report why.
    """
    if campaign.matrix_stem is not None:
        return {}
    owner: dict[str, tuple[str, str]] = {}
    said: dict[str, str] = {}
    for case in campaign.sims:
        for point in case.sweep.points():
            try:
                _, names = _point_names(campaign, case, point, workspace)
                tag = point_name(case, point)
            except (NamingTemplateError, CampaignConfigError):
                break
            for declared in names:
                collected = collection_name(declared)
                first = owner.setdefault(collected, (case.sim_id, tag))
                if first[0] == case.sim_id:
                    continue
                reason = (
                    f"sims {first[0]!r} and {case.sim_id!r} both render the output name "
                    f"{collected} (points {first[1]} and {tag}). Each simulation collects "
                    "into its own folder, so nothing is overwritten there; the two meet in "
                    "the campaign's ONE products folder, where every per-point product is "
                    "named by the stem of its point's loads file and carries no simulation "
                    "id, so the second case's tables would replace the first one's and take "
                    "their place in products.json. Put the simulation in the name: declare "
                    "the outputs with '{sim}' or '{polar}' (for example "
                    "'loads_{sim}_{point}.txt'); the matrix command line names by '{polar}', "
                    "which carries the simulation, and never meets this"
                )
                said.setdefault(first[0], reason)
                said.setdefault(case.sim_id, reason)
    return said


def _staged_inputs_conflict(
    campaign: Campaign,
    case: SimCase,
    workspace: CampaignWorkspace,
    manifest: dict[str, RunRecord],
    already: list[str],
    queued: Collection[str] = frozenset(),
) -> str | None:
    """Refuse a partial resume whose inputs changed since the recorded points.

    Returns the refusal message, or None when resuming is safe.

    Staging is a copy, so on a partial resume the file the new points would
    run against replaces the one the recorded points DID run against. If the
    source changed in between, the campaign would end up with one manifest
    holding two sets of records that used different inputs, distinguishable
    only by a hash the later staging has already overwritten. Comparing
    before staging is what keeps the manifest's ``inputs_sha256`` a fact
    about the run rather than about whatever was last copied (NFR-07).

    A recorded point with no ``inputs_sha256`` (a case with no geometry, or a
    record from a preparation failure) constrains nothing and is skipped.
    """
    if case.geometry is None:
        return None
    origin = Path(case.geometry)
    if not origin.is_file():
        # Absent sources are stage_inputs' refusal to make, with its own
        # message; anticipating it here would report the wrong cause.
        return None
    current = file_sha256(origin)
    name = origin.name
    for run_id in already:
        record = manifest.get(run_id)
        if record is None:
            # Recorded during THIS call rather than read from disk: it staged
            # the same inputs by construction, so it constrains nothing.
            # `recorded` grows as points execute while `manifest` is read once,
            # so the two stop being equal and indexing would raise.
            continue
        recorded_hashes = record.inputs_sha256 or {}
        # BY THE NAME THE FILE SYSTEM SEES: staging writes inputs/<name>, and on
        # Windows `WING.FSM` and `wing.fsm.` are the file the record keys as
        # `wing.fsm`, so an exact-spelling lookup let a new spelling restage it.
        folded = name.rstrip(" .").casefold()
        was = next(
            (
                digest
                for key, digest in recorded_hashes.items()
                if key.rstrip(" .").casefold() == folded
            ),
            None,
        )
        if was is None or was == current:
            continue
        if run_id in queued:
            return (
                f"cannot run {campaign.name}/sim_{case.sim_id}: its input {name!r} has "
                f"changed since {run_id!r} was submitted, and that job is still in a "
                f"scheduler's queue. The record hashes {was[:12]}... and {origin} now "
                f"hashes to {current[:12]}...: staging the new content would replace "
                "the copy the queued job opens when it starts. Collect it first "
                "(pyfs-matrix collect), or restore the original input; nothing was run."
            )
        return (
            f"cannot resume {campaign.name}/sim_{case.sim_id}: its input {name!r} "
            f"has changed since {run_id!r} ran. The manifest records "
            f"{was[:12]}... for that point and {origin} now hashes to "
            f"{current[:12]}.... Resuming would stage the new content over the "
            "copy the recorded points used, leaving one manifest describing two "
            "different sets of inputs. Restore the original input to resume, or "
            "archive the simulation and run it again as new evidence."
        )
    return None


def _structural_facts(case: SimCase) -> dict[str, Any]:
    """Report structural assessment only for a point carrying an FSI configuration."""
    config = effective_fsi_config(case)
    return {"fsi": structural_assessment(config)} if config is not None else {}
