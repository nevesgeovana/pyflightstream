"""The workflow table's entries, :func:`build_script` and :func:`workflow_registry`.

The entries of :data:`WORKFLOWS` name the builders, so they are written
here, above every builder, into the table object ``_conventions`` holds.
A new run type is a builder module of this package and one entry here.
"""

from __future__ import annotations

from pyflightstream.cases import (
    ScriptRecipe,
    SimCase,
)
from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_COUNTER_ACTION as UNSTEADY_COUNTER_ACTION,
)
from pyflightstream.commands import (
    CommandRegistry,
)
from pyflightstream.script import (
    Script,
)

from ._conventions import (
    WORKFLOWS,
    Workflow,
    WorkflowConventions,
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
from ._steady import (
    _after_the_build,
    _before_the_build,
    _build_steady,
)
from ._unsteady import (
    _build_unsteady,
)
from ._vocabulary import (
    _QSTEADY_ROTOR_KEYS,
    _STEADY_KEYS,
    _UNSTEADY_KEYS,
    _UNSTEADY_ROTOR_KEYS,
    QSTEADY_ROTOR,
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
    CommandArgumentError
        If the script targets build 26.100 and the case asks for a rotor
        (an ``unsteady_rotor`` or ``qsteady_rotor`` run type, a motion or a
        rotor-speed variable): the angular-velocity unit of that build is
        not measured, so the case is refused by name.
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
    workflow = _before_the_build(case, script, conventions=conventions, registry=registry)
    workflow.builder(case, script, conventions or WorkflowConventions.for_case(case))
    _after_the_build(case, script)


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

    FR-890: a row whose probes are normal and which states a per-step
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
