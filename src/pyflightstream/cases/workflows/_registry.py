"""The workflow table's entries, :func:`build_script` and :func:`workflow_registry`.

The entries of :data:`WORKFLOWS` name the builders, so they are written
here, above every builder, into the table object ``_conventions`` holds.
A new run type is a builder module of this package and one entry here.
"""

from __future__ import annotations

import pyflightstream.cases._setup_link as _setup_link
from pyflightstream.cases import (
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    classify_outputs,
)
from pyflightstream.cases import (
    setup_surfaces as _setup_surfaces,
)
from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_COUNTER_ACTION,
)
from pyflightstream.commands import (
    CommandNotInVersionError,
    CommandRegistry,
)
from pyflightstream.script import (
    MARCH_ACTIONS,
    Script,
)

from ._conventions import (
    _AVERAGE_ACTION,
    WORKFLOWS,
    BuildCapabilities,
    Workflow,
    WorkflowConventions,
    WorkflowCoverageError,
    require_coverage,
    resolve_workflow,
    select_workflow,
)
from ._exports import (
    surface_time_averaging,
)
from ._probes import (
    _creation_of_normal_probes,
)
from ._qsteady_rotor import (
    _build_qsteady_rotor,
)
from ._rotor import (
    _build_unsteady_rotor,
)
from ._rows import (
    _refuse_rotor_shedding,
    continuation_of,
)
from ._steady import (
    _build_steady,
    refuse_an_untranslatable_surface,
)
from ._timing import (
    march_strategy,
)
from ._unsteady import (
    _build_unsteady,
)
from ._vocabulary import (
    _QSTEADY_ROTOR_KEYS,
    _STEADY_KEYS,
    _UNSTEADY_KEYS,
    _UNSTEADY_RECIPES,
    _UNSTEADY_ROTOR_KEYS,
    QSTEADY_ROTOR,
    _refuse_retired_window_keys,
)

_WORKFLOW_ENTRIES: dict[str, Workflow] = {
    "steady": Workflow(
        name="steady",
        summary=(
            "One steady point of a polar: a uniform free stream, the solver settings the "
            "row and its input library resolved to, one solve, one loads export."
        ),
        commands=(
            "SET_FREESTREAM",
            "SOLVER_SET_AOA",
            "SOLVER_SET_VELOCITY",
            "SOLVER_SET_ITERATIONS",
            "SOLVER_SET_CONVERGENCE",
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "UPDATE_ALL_SURFACE_SECTIONS",
            "COMPUTE_SURFACE_SECTIONAL_LOADS",
            "UPDATE_PROBE_POINTS",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "SET_VTK_EXPORT_VARIABLES",
            "EXPORT_SOLVER_ANALYSIS_VTK",
            "EXPORT_ALL_SURFACE_SECTIONS",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            "EXPORT_PROBE_POINTS",
            "SET_PLOT_TYPE",
            "SAVE_PLOT_TO_FILE",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_steady,
        keys=_STEADY_KEYS,
    ),
    "unsteady": Workflow(
        name="unsteady",
        summary=(
            "One unsteady point of a body that does not move: a uniform free stream, a "
            "physical time loop stated directly by the row, one solve, one loads export."
        ),
        commands=(
            "SET_FREESTREAM",
            "SET_SOLVER_UNSTEADY",
            "SOLVER_SET_AOA",
            "SOLVER_SET_VELOCITY",
            "SOLVER_SET_ITERATIONS",
            "SOLVER_SET_CONVERGENCE",
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "UPDATE_ALL_SURFACE_SECTIONS",
            "COMPUTE_SURFACE_SECTIONAL_LOADS",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "SET_VTK_EXPORT_VARIABLES",
            "EXPORT_SOLVER_ANALYSIS_VTK",
            "EXPORT_ALL_SURFACE_SECTIONS",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            "UNSTEADY_SOLVER_EXPORT_PLOTS",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_unsteady,
        keys=_UNSTEADY_KEYS,
    ),
    "unsteady_rotor": Workflow(
        name="unsteady_rotor",
        summary=(
            "A blade-resolved rotor run: a rotor coordinate system, one rotary motion "
            "turning at the row's RPM about the row's axis, and a physical time loop."
        ),
        commands=(
            "CREATE_NEW_COORDINATE_SYSTEM",
            "EDIT_COORDINATE_SYSTEM",
            "SET_FREESTREAM",
            "CREATE_NEW_MOTION",
            "SET_MOTION_BOUNDARIES",
            "SET_MOTION_MOVING_FRAMES",
            "SET_MOTION_COORDINATE_SYSTEM",
            "SET_MOTION_ROTOR_AXIS",
            "SET_MOTION_ROTOR_RPM",
            "SET_SOLVER_UNSTEADY",
            "SOLVER_SET_AOA",
            "SOLVER_SET_VELOCITY",
            "SOLVER_SET_ITERATIONS",
            "SOLVER_SET_CONVERGENCE",
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "UPDATE_ALL_SURFACE_SECTIONS",
            "COMPUTE_SURFACE_SECTIONAL_LOADS",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "SET_VTK_EXPORT_VARIABLES",
            "EXPORT_SOLVER_ANALYSIS_VTK",
            "EXPORT_ALL_SURFACE_SECTIONS",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            "UNSTEADY_SOLVER_EXPORT_PLOTS",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_unsteady_rotor,
        keys=_UNSTEADY_ROTOR_KEYS,
    ),
    QSTEADY_ROTOR: Workflow(
        name=QSTEADY_ROTOR,
        summary=(
            "An isolated, axisymmetric rotor solved steady with its blades held still and "
            "the free stream turning at the rotor's speed: one periodic sector, or the whole "
            "wheel at PASSAGE_POSITIONS clockings averaged by the post."
        ),
        commands=(
            "CREATE_NEW_COORDINATE_SYSTEM",
            "SET_FREESTREAM",
            "SOLVER_SET_AOA",
            "SOLVER_SET_VELOCITY",
            "SOLVER_SET_ITERATIONS",
            "SOLVER_SET_CONVERGENCE",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_qsteady_rotor,
        keys=_QSTEADY_ROTOR_KEYS,
    ),
}


# The entries are written into the one table object ``_conventions`` holds, in
# the order above, which is the order the command line lists the run types in.
WORKFLOWS.update(_WORKFLOW_ENTRIES)


def build_script(
    case: SimCase,
    script: Script,
    *,
    conventions: WorkflowConventions | None = None,
    registry: CommandRegistry | None = None,
) -> None:
    """Build one case's whole script from the run type it names.

    In order: select the workflow (refusing two builders or none), check
    that the script's build is covered (refusing BEFORE the first
    emission), then build.

    Parameters
    ----------
    case : SimCase
        The case, with its sweep point already filled by the campaign
        loop.
    script : Script
        An empty script bound to the campaign's FlightStream build.
    conventions : WorkflowConventions, optional
        What the run layer says about the workspace; defaults to the
        names the case carries.
    registry : CommandRegistry, optional
        Alternative command database, used by tests.

    Raises
    ------
    CampaignConfigError
        If the case names two builders or none, or if a value the run
        type needs is absent or unparsable.
    WorkflowCoverageError
        If the script's build is outside the workflow's derived
        coverage.

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> from pyflightstream.script import Script
    >>> case = SimCase(
    ...     sim_id="7002",
    ...     aircraft="RotorRig",
    ...     sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     recipe="steady",
    ...     outputs=["loads_a+00.0.txt"],
    ...     variables={"VELOCITY": "30.0"},
    ...     point={"alpha": 0.0},
    ... )
    >>> script = Script("26.120")
    >>> build_script(case, script)
    >>> script.render().splitlines()[0]
    'SET_FREESTREAM CONSTANT'
    """
    _refuse_retired_window_keys(case)
    _refuse_rotor_shedding(case)
    if case.pproc is not None and case.pproc.products.boundary_layer_integrals:
        names = list((conventions.outputs if conventions else None) or case.outputs)
        kinds = classify_outputs(names)
        if "sections" not in kinds or not ({"vtk", "tecplot"} & kinds.keys()):
            raise CampaignConfigError(
                "boundary_layer_integrals requires the section-coordinate export and VTK "
                "surface of the same point; retain the pproc's generated output dependencies"
            )
    workflow = resolve_workflow(select_workflow(case))
    require_coverage(workflow, script.version, registry=registry)
    if case.pproc is not None and case.pproc.time_averaging is not None:
        # G25: THE PACKAGE AVERAGES THE SURFACE THE RUN WRITES AS TECPLOT, from
        # its per-step VTK exports; a point exporting no Tecplot has nothing to
        # average into one.
        names = list((conventions.outputs if conventions else None) or case.outputs)
        if case.recipe in _UNSTEADY_RECIPES:
            try:
                script.entry(_AVERAGE_ACTION)
            except CommandNotInVersionError as error:
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: the pproc's [time_averaging] exports the surface "
                    f"at every step of its window through an unsteady solver action, and "
                    f"FlightStream {script.version.canonical} does not carry it: {error} Run "
                    "the row on a build that does, or remove [time_averaging]."
                ) from error
        if "tecplot" not in classify_outputs(names):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc's [time_averaging] asks for the surface "
                "averaged over its window, which the package writes as a Tecplot from the "
                "per-step VTK exports, and the point exports no Tecplot (its outputs "
                f"{', '.join(names) or 'name none'}). Leave tecplot on under [exports], "
                "the default, or remove [time_averaging]."
            )
        surface_time_averaging(case)
    # THE SEAM (ARCH-0200): how this case is marched on this build, decided
    # once and before the first emission, so a refusal leaves nothing written.
    script.march_strategy = march_strategy(
        case, capabilities=BuildCapabilities.of(script._view), registry=registry
    )
    workflow.builder(case, script, conventions or WorkflowConventions.for_case(case))
    _setup_surfaces.refuse_setup_keys_that_reached_nothing(script, case)
    if case.pproc is not None and case.pproc.products.boundary_layer_integrals:
        for block in script.section_blocks:
            block["loads_frame_index"] = script.loads_frame
    # A continuation's loads frame is its saved simulation's, which the run takes
    # from the run it continues; only an unsteady row continues one.
    if case.recipe not in _UNSTEADY_RECIPES or continuation_of(case) is None:
        refuse_an_untranslatable_surface(case, script)
    # THE LABEL IS THE SCRIPT: a point recorded as marched by actions registers
    # at least one of the package's own, and one recorded as a single march
    # registers none but the step counter, which counts only on such a row
    # (FR-314). The builders emit the actions from the row, so this is where the
    # two are held together (architect lens, GOAL-023 opening round). A setup's
    # own per-step actions (FR-319) are the user's, and no label's.
    emitted = any(
        name != UNSTEADY_COUNTER_ACTION for name in _setup_link.package_actions(case, script)
    )
    if script.march_strategy is not None and emitted != (script.march_strategy == MARCH_ACTIONS):
        raise WorkflowCoverageError(
            f"internal defect: case {case.sim_id!r} on FlightStream {script.version.canonical} "
            f"was labelled {script.march_strategy!r} and its script registers "
            f"{len(script.unsteady_actions)} unsteady solver action(s). Report it; the "
            "label and the script must agree before either is recorded."
        )


def workflow_registry(*, conventions: WorkflowConventions | None = None) -> dict[str, ScriptRecipe]:
    """Return the workflows as a recipe registry the campaign loop can take.

    This is the seam that makes a workflow reachable with NO user
    function: hand it to ``run_matrix(recipe_registry=...)`` and a row
    whose ``FS_SCRIPT`` code maps to a workflow NAME builds through the
    table instead of through an import.

    Parameters
    ----------
    conventions : WorkflowConventions, optional
        Passed down to every builder; the run layer owns these, since
        ``workspace`` sits above ``cases``.

    Returns
    -------
    dict of str to callable
        ``{name: build(case, script) -> None}``, satisfying
        :class:`pyflightstream.cases.ScriptRecipe`.

    Examples
    --------
    >>> from pyflightstream.cases.workflows import workflow_registry
    >>> registry = workflow_registry()
    >>> "steady" in registry
    True
    >>> registry["steady"].__name__
    'workflow_steady'
    """

    def _bind(name: str) -> ScriptRecipe:
        def build(case: SimCase, script: Script) -> None:
            # Selected again rather than assumed: the registry entry says
            # which name the loop LOOKED UP, and the case is what says
            # whether that name conflicts with a recipe of its own.
            build_script(case, script, conventions=conventions)

        build.__name__ = f"workflow_{name}"
        build.__doc__ = WORKFLOWS[name].summary
        return build

    return {name: _bind(name) for name in WORKFLOWS}


def normal_probe_creation(
    case: SimCase,
    version: str,
    *,
    conventions: WorkflowConventions | None = None,
) -> str:
    """Return the lines that create a row's normal probes on its first exporting step.

    FR-417 R7: a row whose probes are normal and which states a per-step
    export window exports them at every step of the window, so the exports
    script of the window's first step creates them: ``DELETE_PROBE_POINTS``,
    then the creation commands the row's full script emits after the march,
    taken from that script built on a scratch script that is never written.

    Parameters
    ----------
    case : SimCase
        The bound row, continued or not.
    version : str
        The FlightStream build the script is written for.
    conventions : WorkflowConventions, optional
        The rendered output names; defaults to the case's own.

    Returns
    -------
    str
        The lines, each ending in a newline; empty for a row whose probes are
        not normal or that states no per-step window.

    Raises
    ------
    CampaignConfigError
        If the row cannot be built from its mesh, naming the entries and the
        remedy.
    """
    return _creation_of_normal_probes(
        case,
        Script(version),
        lambda full, scratch: build_script(full, scratch, conventions=conventions),
    )
