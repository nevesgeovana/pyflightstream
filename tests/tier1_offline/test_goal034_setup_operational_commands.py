"""Tier 1, GOAL-033 setup/BC: each in-scope setup command is operational at script level.

WHAT IS HELD, command by command, on the primary build 26.124: a case states
an input through the route the package offers for that command (a
``SolverSettings`` field, a matrix row key, a reference or disc block, a raw
mesh declaration or a setup port), the full ``build_script`` path builds the
26.124 script, and the command appears there in its measured layout WITH THE
VALUE THE INPUT STATED. Each case is paired with a control, the same route at
another value or without the input, whose script must NOT carry that block,
so a line the workflow would write anyway cannot pass for the input's.

This is operation at script level, not a name lookup: the registry is never
consulted directly, the block is read off the rendered script. It is not a
native claim; what the solver does with each line is the native-evidence
obligations' business.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-152.

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import (
    MeshImport,
    PprocSpec,
    ReferenceData,
    SimCase,
    SolverSettings,
    TrailingEdgeMarking,
)
from pyflightstream.cases.workflows import build_script, build_steady_sweep
from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.script import BrokenCommandError, Script, helpers
from pyflightstream.versions import resolve
from tests.tier1_offline.test_boundary_setup_coverage import _port_case
from tests.tier1_offline.test_g25_surface_time_average import _rotor
from tests.tier1_offline.test_goal031_g08_glossary_claims import (
    HUB,
    PROP,
    ROW_KEY_VARIATIONS,
    SETTING_VARIATIONS,
    _disc,
    _freestream,
    _over_wing,
    _plain,
    _ported,
    _raw_mesh,
)
from tests.tier1_offline.test_raw_mesh_conditions import DETECT_AUTO, FILE_ROUTE, _library
from tests.tier1_offline.test_raw_mesh_conditions import _case as _raw_mesh_row
from tests.tier1_offline.test_steady_start import _points
from tests.tier1_offline.test_workflows import (
    _wb_geometry,
    _with_pproc,
    steady_case,
    steady_case_resolved,
    unsteady_case,
)

BUILD = "26.124"

Make = Callable[[Path], SimCase]


@dataclass(frozen=True)
class Route:
    """A stated input, its control, and the block the stated input must emit.

    ``stated`` builds the case whose input names the value; ``control`` the
    same route at another value or without the input. ``block`` is the run of
    consecutive script lines the stated case must carry and the control must
    not; ``control`` is ``None`` only for a command every script of the
    workflow emits unconditionally, which then must still be present.
    """

    stated: Make
    control: Make | None
    block: tuple[str, ...]


def _swap(key: str) -> tuple[Make, Make]:
    """A setting variation read the other way: its second value is the control."""
    variation = SETTING_VARIATIONS[key]
    return variation.first, variation.second


def _set(key: str, *block: str) -> Route:
    """The glossary's two values of a setting: the second is stated, the first the control."""
    variation = SETTING_VARIATIONS[key]
    return Route(variation.second, variation.first, block)


def _row(key: str, *block: str) -> Route:
    """The glossary's two values of a row key: the second is stated, the first the control."""
    variation = ROW_KEY_VARIATIONS[key]
    return Route(variation.second, variation.first, block)


def _applied(key: str, *block: str) -> Route:
    """An ``apply_*`` choice: applying it (the first value) is stated, leaving it the control."""
    stated, control = _swap(key)
    return Route(stated, control, block)


def _disc_with(**update: object) -> Make:
    """The one-disc steady case, with its actuator block changed by ``update``."""

    def make(_: Path) -> SimCase:
        block = PROP.model_copy(update=update)
        case = steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120")
        return case.model_copy(update={"frames": [HUB], "actuators": {"PROP": block}})

    return make


def _referenced(area: float, length: float) -> Make:
    return lambda _: steady_case().model_copy(
        update={"reference": ReferenceData(area=area, length=length)}
    )


def _raw_trailing_edges(**marking: object) -> Make:
    """The raw mesh whose sidecar detects trailing edges as ``marking`` says."""

    def make(tmp: Path) -> SimCase:
        case = _raw_mesh(tmp)
        conditions = case.raw_mesh_conditions.model_copy(
            update={"trailing_edges": TrailingEdgeMarking(route="detect", **marking)}
        )
        return case.model_copy(update={"raw_mesh_conditions": conditions})

    return make


def _raw_wake_termination(value: object) -> Make:
    def make(tmp: Path) -> SimCase:
        case = _raw_mesh(tmp)
        conditions = case.raw_mesh_conditions.model_copy(update={"wake_termination": value})
        return case.model_copy(update={"raw_mesh_conditions": conditions})

    return make


def _port(**options: bool) -> Make:
    """The duct's setup ports, on a mesh in metres whose sidecar marks no trailing edge."""

    def make(tmp: Path) -> SimCase:
        case = _port_case(tmp, **options)[0]
        conditions = case.raw_mesh_conditions.model_copy(
            update={"trailing_edges": TrailingEdgeMarking(route="none")}
        )
        return case.model_copy(
            update={"mesh_import": MeshImport(units="METER"), "raw_mesh_conditions": conditions}
        )

    return make


def _base(*operations: dict[str, object]) -> Make:
    """The saved wing with a base region created on ``Base`` and then ``operations``."""
    create = {"operation": "create", "boundary": "Base", "model": "USER", "cp": -0.2}
    return lambda tmp: _over_wing(tmp).model_copy(
        update={"solver": SolverSettings(base_region_operations=[create, *operations])}
    )


def _solver(**settings: object) -> Make:
    return lambda _: steady_case().model_copy(update={"solver": SolverSettings(**settings)})


ENABLE_DISABLE = {
    "ADDITIONAL_WAKE_RELAXATION_ITERATION": "additional_wake_relaxation",
    "KUTTA_JOUKOWSKI_LIFT_FORCES": "kutta_joukowski_lift",
    "LAMINAR_SEPARATION": "laminar_separation",
    "PRINT_ROTOR_INDUCED_VELOCITIES": "print_rotor_induced_velocities",
    "REYNOLDS_AVERAGED_DRAG_FORCES": "reynolds_averaged_drag",
    "SET_ADAPTIVE_FIELD_GRID_REFINEMENT": "adaptive_field_grid_refinement",
    "SET_WAKE_ON_WAKE_INDUCTION": "wake_on_wake_induction",
    "SOLVER_SET_FORCED_ITERATIONS": "forced_iterations",
    "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY": "mesh_induced_wake_velocity",
    "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA": "unsteady_pressure_and_kutta",
    "SET_SOLVER_VISCOUS_COUPLING": "viscous_coupling",
    "SET_INVISCID_LOADS": "inviscid_loads",
    "SET_ANALYSIS_SYMMETRY_LOADS": "symmetry_loads",
}
NUMBER_07 = {
    "ROTOR_INDUCED_VELOCITY_BLENDING": "rotor_induced_velocity_blending",
    "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH": "jet_wake_decay_normalized_length",
    "SET_WAKE_DECAY_CONSTANT": "wake_decay_constant_per_m",
    "SET_WAKE_NUMERICAL_RELAXATION": "wake_numerical_relaxation",
    "SOLVER_STABILIZATION": "solver_stabilization",
}
SELECTION_OF_BODY = {
    "SET_SOLVER_ANALYSIS_BOUNDARIES": "analysis_families",
    "SET_VORTICITY_DRAG_BOUNDARIES": "vorticity_drag_families",
    "SET_THIN_BOUNDARIES": "thin_boundaries",
    "SET_VISCOUS_EXCLUDED_BOUNDARIES": "viscous_excluded",
    "SOLVER_PROXIMAL_BOUNDARIES": "proximal_boundaries",
}
SECOND_INDEX = {
    "DELETE_INLET": "delete_inlets",
    "DELETE_OUTLET": "delete_outlets",
    "DELETE_TRANSITION_TRIP": "delete_transition_trips",
    "DISABLE_WAKE_NODES_ON_TRAILING_EDGE": "disabled_wake_trailing_edges",
}

#: EVERY IN-SCOPE COMMAND THIS MODULE MAKES OPERATIONAL ON 26.124, by its route.
ROUTES: dict[str, Route] = {
    **{c: _set(k, f"{c} DISABLE") for c, k in ENABLE_DISABLE.items()},
    **{c: _set(k, f"{c} 0.7") for c, k in NUMBER_07.items()},
    # A selection names the saved wing's Body, boundary 2, where the control names Wing.
    **{c: _set(k, f"{c} 1", "2") for c, k in SELECTION_OF_BODY.items()},
    **{c: _set(k, f"{c} 2") for c, k in SECOND_INDEX.items()},
    "AEROELASTIC_RBF_TYPE": Route(
        _solver(aeroelastic_rbf_type="THIN_PLATE_SPLINE"),
        _solver(aeroelastic_rbf_type="GAUSSIAN"),
        ("AEROELASTIC_RBF_TYPE THIN_PLATE_SPLINE",),
    ),
    "SET_SOLVER_CONVERGENCE_ITERATIONS": _set(
        "convergence_iterations", "SET_SOLVER_CONVERGENCE_ITERATIONS 10"
    ),
    "SET_WAKE_TERMINATION_TIME_STEPS": Route(
        SETTING_VARIATIONS["wake_termination_steps"].second,
        SETTING_VARIATIONS["wake_termination_steps"].first,
        ("SET_WAKE_TERMINATION_TIME_STEPS 20",),
    ),
    "SOLVER_SET_FARFIELD_LAYERS": _set("farfield_layers", "SOLVER_SET_FARFIELD_LAYERS 5"),
    "SET_BOUNDARY_LAYER_TYPE": _set("boundary_layer", "SET_BOUNDARY_LAYER_TYPE TURBULENT"),
    "SET_MAX_PARALLEL_THREADS": _set("max_threads", "SET_MAX_PARALLEL_THREADS 8"),
    "SET_SURFACE_ROUGHNESS": _set("surface_roughness", "SET_SURFACE_ROUGHNESS 20.0"),
    "SET_LOADS_AND_MOMENTS_UNITS": _set("load_units", "SET_LOADS_AND_MOMENTS_UNITS POUND-FORCE"),
    "SET_SIGNIFICANT_DIGITS": _set("significant_digits", "SET_SIGNIFICANT_DIGITS 8"),
    "SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE": _set(
        "geometric_edge_bluntness_angle_deg", "SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE 120.0"
    ),
    "SET_VERTEX_MERGE_TOLERANCE": _set(
        "vertex_merge_tolerance_m", "SET_VERTEX_MERGE_TOLERANCE 0.0002"
    ),
    "SET_SIMULATION_LENGTH_UNITS": _set(
        "simulation_length_unit", "SET_SIMULATION_LENGTH_UNITS MILLIMETER"
    ),
    "SET_BASE_REGION_BENDING_ANGLE": _set(
        "base_region_bending_angle_deg", "SET_BASE_REGION_BENDING_ANGLE 30.0"
    ),
    "SOLVER_SET_REF_MACH_NUMBER": _set("reference_mach", "SOLVER_SET_REF_MACH_NUMBER 0.2"),
    "SOLVER_SET_REF_VELOCITY": _set("reference_velocity_m_per_s", "SOLVER_SET_REF_VELOCITY 40.0"),
    "SOLVER_SET_ITERATIONS": _set("iterations", "SOLVER_SET_ITERATIONS 800"),
    "SOLVER_SET_CONVERGENCE": _set("convergence", "SOLVER_SET_CONVERGENCE 1e-06"),
    "SOLVER_MINIMUM_CP": _set("minimum_cp", "SOLVER_MINIMUM_CP -5.0"),
    "CREATE_AIRFOIL_SEPARATION": _set(
        "airfoil_separation", "CREATE_AIRFOIL_SEPARATION WING -1 ENABLE"
    ),
    "CREATE_AXIAL_VORTEX_SEPARATION": _set(
        "axial_vortex_separation", "CREATE_AXIAL_VORTEX_SEPARATION FUSELAGE -1 1 X 0.6 DISABLE"
    ),
    "CREATE_CYLINDRICAL_BULK_SEPARATION": _set(
        "cylindrical_bulk_separation", "CREATE_CYLINDRICAL_BULK_SEPARATION GEAR -1 0.3"
    ),
    "CREATE_STRATFORD_BULK_SEPARATION": _set(
        "stratford_bulk_separation", "CREATE_STRATFORD_BULK_SEPARATION STRUT 1", "2"
    ),
    # ``"all"`` is the solver's -1; the control deletes the first.
    "DELETE_SEPARATION": _set("delete_separations", "DELETE_SEPARATION -1"),
    "DELETE_VORTICITY_DRAG_BOUNDARIES": _set(
        "clear_vorticity_drag_boundaries", "DELETE_VORTICITY_DRAG_BOUNDARIES"
    ),
    "DETECT_LEADING_EDGES_WAKES_BY_SURFACE": _set(
        "leading_edge_wake_boundaries", "DETECT_LEADING_EDGES_WAKES_BY_SURFACE", "SURFACES 1", "2"
    ),
    "MARK_WAKE_TERMINATION_NODES": _set(
        "mark_wake_termination_nodes", "MARK_WAKE_TERMINATION_NODES"
    ),
    "REMOVE_INITIALIZATION": _set("remove_initialization", "REMOVE_INITIALIZATION"),
    "SET_TRAILING_EDGE_TYPE": _set("trailing_edge_types", "SET_TRAILING_EDGE_TYPE 1 JET_OUTFLOW"),
    "CREATE_NEW_BASE_REGION": _set("base_region_operations", "CREATE_NEW_BASE_REGION 3 USER -0.3"),
    "SET_ACTUATOR_NAME": _set("actuator_operations", "SET_ACTUATOR_NAME 1 Rear"),
    "INITIALIZE_SOLVER": _set(
        "solver_model", "INITIALIZE_SOLVER", "SOLVER_MODEL SUBSONIC_PRANDTL_GLAUERT"
    ),
    # An emptied selection clears the boundaries a selection would set.
    "DELETE_THIN_BOUNDARIES": Route(
        lambda tmp: _over_wing(tmp).model_copy(
            update={"solver": SolverSettings(thin_boundaries=[])}
        ),
        _over_wing,
        ("DELETE_THIN_BOUNDARIES",),
    ),
    "DELETE_VISCOUS_EXCLUDED_BOUNDARIES": Route(
        lambda tmp: _over_wing(tmp).model_copy(
            update={"solver": SolverSettings(viscous_excluded=[])}
        ),
        _over_wing,
        ("DELETE_VISCOUS_EXCLUDED_BOUNDARIES",),
    ),
    # The sidecar's declarations, applied against left.
    "AUTO_DETECT_BASE_REGIONS": _applied("apply_base_regions", "AUTO_DETECT_BASE_REGIONS"),
    "AUTO_DETECT_TRAILING_EDGES": _applied("apply_trailing_edges", "AUTO_DETECT_TRAILING_EDGES"),
    "AUTO_DETECT_WAKE_TERMINATION_NODES": _applied(
        "apply_wake_termination", "AUTO_DETECT_WAKE_TERMINATION_NODES"
    ),
    # Row keys, read where the builder reads them.
    "SOLVER_SET_AOA": _row("ALPHA", "SOLVER_SET_AOA 4.0"),
    "SOLVER_SET_SIDESLIP": _row("BETA", "SOLVER_SET_SIDESLIP 4.0"),
    "SOLVER_SET_VELOCITY": _row("VELOCITY", "SOLVER_SET_VELOCITY 40.0"),
    # FR-331: the disc speed handed to the solver is minus the block's hand times the speed.
    "SET_PROP_ACTUATOR_RPM": _row("ACTUATOR_RPM", "SET_PROP_ACTUATOR_RPM 1 -3000.0"),
    "SET_PROP_ACTUATOR_THRUST": _row("ACTUATOR_THRUST", "SET_PROP_ACTUATOR_THRUST 1 150.0 NEWTONS"),
    "CREATE_NEW_ACTUATOR": _row("ACTUATOR", "CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL FAN"),
    "SET_PROP_ACTUATOR_PROFILE": _row(
        "PROFILE", "SET_PROP_ACTUATOR_PROFILE 1 NEWTONS 3", "prop_cq.actuator_profile.txt"
    ),
    "DETECT_BASE_REGIONS_BY_SURFACE": _row("BASE_REGIONS", "DETECT_BASE_REGIONS_BY_SURFACE 2"),
    "SET_SOLVER_UNSTEADY": _row(
        "DELTA_TIME", "SET_SOLVER_UNSTEADY", "TIME_ITERATIONS 480", "DELTA_TIME 0.0002"
    ),
    "SET_FREESTREAM": Route(
        lambda tmp: _freestream(tmp, "fs_b", 32.0), _plain, ("SET_FREESTREAM CUSTOM STRUCTURED",)
    ),
    "FLUID_PROPERTIES": Route(
        lambda _: steady_case_resolved(), _plain, ("FLUID_PROPERTIES", "DENSITY 1.44598")
    ),
    # The reference: its area and length, and the moment point's loads frame.
    "SOLVER_SET_REF_AREA": Route(
        _referenced(12.5, 1.7), _referenced(10.0, 1.2), ("SOLVER_SET_REF_AREA 12.5",)
    ),
    "SOLVER_SET_REF_LENGTH": Route(
        _referenced(12.5, 1.7), _referenced(10.0, 1.2), ("SOLVER_SET_REF_LENGTH 1.7",)
    ),
    "SET_SOLVER_ANALYSIS_LOADS_FRAME": Route(
        _over_wing, _plain, ("SET_SOLVER_ANALYSIS_LOADS_FRAME 2",)
    ),
    "SET_ANALYSIS_MOMENTS_MODEL": Route(
        _over_wing, _plain, ("SET_ANALYSIS_MOMENTS_MODEL PRESSURE",)
    ),
    # The disc: created and enabled only when stated, shaped by its block.
    "ENABLE_ACTUATOR": Route(_disc, _plain, ("ENABLE_ACTUATOR 1",)),
    "SET_ACTUATOR_AXIS": Route(
        _disc_with(axis="Y"), _disc_with(axis="X"), ("SET_ACTUATOR_AXIS 1 2 Y 0.0",)
    ),
    "SET_ACTUATOR_RADIUS": Route(
        _disc_with(tip_radius_m=0.6), _disc_with(), ("SET_ACTUATOR_RADIUS 1 0.6 0.1",)
    ),
    "SET_ACTUATOR_WAKE_TYPE": Route(
        _disc_with(wake_type="RELAXED"), _disc_with(), ("SET_ACTUATOR_WAKE_TYPE 1 RELAXED",)
    ),
    "SET_PROP_ACTUATOR_SWIRL": Route(
        _disc_with(swirl=0.25), _disc_with(), ("SET_PROP_ACTUATOR_SWIRL 1 0.25",)
    ),
    "DELETE_ACTUATOR": Route(
        lambda tmp: _disc(tmp).model_copy(
            update={
                "solver": SolverSettings(actuator_operations=[{"op": "delete", "actuator": "PROP"}])
            }
        ),
        _disc,
        ("DELETE_ACTUATOR 1",),
    ),
    # The setup ports the matrix reader binds.
    "CREATE_NEW_INLET": Route(
        lambda tmp: _ported(tmp, "feed", "inlet", "-10"),
        lambda tmp: _ported(tmp, "exit", "outlet", "10"),
        ("CREATE_NEW_INLET 1 -10.0",),
    ),
    "CREATE_NEW_OUTLET": Route(
        lambda tmp: _ported(tmp, "exit", "outlet", "10"),
        lambda tmp: _ported(tmp, "feed", "inlet", "-10"),
        ("CREATE_NEW_OUTLET 2 10.0",),
    ),
    "REMESH_INLET": Route(
        _port(remesh=True, profile=False),
        _port(profile=False),
        ("REMESH_INLET", "INLET 1"),
    ),
    "REMESH_OUTLET": Route(
        _port(inlet=False, outlet=True, profile=False, remesh=True),
        _port(inlet=False, outlet=True, profile=False),
        ("REMESH_OUTLET", "OUTLET 1"),
    ),
    "SET_INLET_CUSTOM_PROFILE": Route(
        _port(),
        _port(profile=False),
        ("SET_INLET_CUSTOM_PROFILE 1", "pfs_inlet_1_6407f9a79378640b.txt"),
    ),
    # The raw mesh's trailing-edge and wake-termination declarations.
    "DETECT_TRAILING_EDGES_BY_SURFACE": Route(
        _raw_trailing_edges(detect_surfaces=("Wing",)),
        _raw_trailing_edges(),
        ("DETECT_TRAILING_EDGES_BY_SURFACE", "SURFACES 1", "1"),
    ),
    "SET_TRAILING_EDGE_SWEEP_ANGLE": Route(
        _raw_trailing_edges(sweep_angle_deg=35.0),
        _raw_trailing_edges(),
        ("SET_TRAILING_EDGE_SWEEP_ANGLE 35.0",),
    ),
    "DETECT_WAKE_TERMINATION_NODES_BY_SURFACE": Route(
        _raw_wake_termination(("Wing",)),
        _raw_wake_termination("auto"),
        ("DETECT_WAKE_TERMINATION_NODES_BY_SURFACE 1",),
    ),
    # Base-region operations on the region created on the wing's Base.
    "SET_BASE_REGION_CP": Route(
        _base({"operation": "set_pressure", "index": 1, "model": "CUSTOM", "cp": -0.4}),
        _base(),
        ("SET_BASE_REGION_CP 1 CUSTOM -0.4",),
    ),
    "SET_BASE_REGION_TRAILING_EDGES": Route(
        _base({"operation": "mark_trailing_edges", "index": 1}),
        _base(),
        ("SET_BASE_REGION_TRAILING_EDGES 1",),
    ),
    "SELECT_BASE_REGION_FACES": Route(
        _base({"operation": "select_faces", "index": 1}), _base(), ("SELECT_BASE_REGION_FACES 1",)
    ),
    "DELETE_BASE_REGION": Route(
        _base({"operation": "delete", "index": 1}), _base(), ("DELETE_BASE_REGION 1",)
    ),
    "SET_OUTLET_TRAILING_EDGES": Route(
        _base({"operation": "mark_outflow_edges", "boundary": "Base"}),
        _base(),
        ("SET_OUTLET_TRAILING_EDGES 3",),
    ),
    "REMESH_BASE_REGION": Route(
        _base(
            {
                "operation": "remesh",
                "index": 1,
                "mesh": {"inner_radius_m": 0.02, "radial_faces": 4, "growth_scheme": "dual_sided"},
            }
        ),
        _base(),
        ("REMESH_BASE_REGION",),
    ),
    # The workflow's solve stage: every steady script starts the solver once.
    "START_SOLVER": Route(_plain, None, ("START_SOLVER",)),
}


def _render(case: SimCase) -> tuple[list[str] | None, str]:
    script = Script(BUILD)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            build_script(case, script)
    except PyflightstreamError as error:
        return None, str(error)
    return script.render().splitlines(), ""


def _carries(lines: list[str], block: tuple[str, ...]) -> bool:
    width = len(block)
    return any(tuple(lines[i : i + width]) == block for i in range(len(lines) - width + 1))


@pytest.mark.parametrize("command", [pytest.param(c, id=c) for c in ROUTES])
def test_setup_command_is_emitted_with_its_stated_argument_on_26124(command, tmp_path):
    """The stated input reaches the 26.124 script as the command, the control does not.

    GOAL033:setup_bc:operational_commands:ADDITIONAL_WAKE_RELAXATION_ITERATION
    GOAL033:setup_bc:operational_commands:KUTTA_JOUKOWSKI_LIFT_FORCES
    GOAL033:setup_bc:operational_commands:LAMINAR_SEPARATION
    GOAL033:setup_bc:operational_commands:PRINT_ROTOR_INDUCED_VELOCITIES
    GOAL033:setup_bc:operational_commands:REYNOLDS_AVERAGED_DRAG_FORCES
    GOAL033:setup_bc:operational_commands:SET_ADAPTIVE_FIELD_GRID_REFINEMENT
    GOAL033:setup_bc:operational_commands:SET_WAKE_ON_WAKE_INDUCTION
    GOAL033:setup_bc:operational_commands:SOLVER_SET_FORCED_ITERATIONS
    GOAL033:setup_bc:operational_commands:SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY
    GOAL033:setup_bc:operational_commands:SOLVER_UNSTEADY_PRESSURE_AND_KUTTA
    GOAL033:setup_bc:operational_commands:SET_SOLVER_VISCOUS_COUPLING
    GOAL033:setup_bc:operational_commands:SET_INVISCID_LOADS
    GOAL033:setup_bc:operational_commands:SET_ANALYSIS_SYMMETRY_LOADS
    GOAL033:setup_bc:operational_commands:ROTOR_INDUCED_VELOCITY_BLENDING
    GOAL033:setup_bc:operational_commands:SET_JET_WAKE_DECAY_NORMALIZED_LENGTH
    GOAL033:setup_bc:operational_commands:SET_WAKE_DECAY_CONSTANT
    GOAL033:setup_bc:operational_commands:SET_WAKE_NUMERICAL_RELAXATION
    GOAL033:setup_bc:operational_commands:SOLVER_STABILIZATION
    GOAL033:setup_bc:operational_commands:SET_SOLVER_ANALYSIS_BOUNDARIES
    GOAL033:setup_bc:operational_commands:SET_VORTICITY_DRAG_BOUNDARIES
    GOAL033:setup_bc:operational_commands:SET_THIN_BOUNDARIES
    GOAL033:setup_bc:operational_commands:SET_VISCOUS_EXCLUDED_BOUNDARIES
    GOAL033:setup_bc:operational_commands:SOLVER_PROXIMAL_BOUNDARIES
    GOAL033:setup_bc:operational_commands:DELETE_INLET
    GOAL033:setup_bc:operational_commands:DELETE_OUTLET
    GOAL033:setup_bc:operational_commands:DELETE_TRANSITION_TRIP
    GOAL033:setup_bc:operational_commands:DISABLE_WAKE_NODES_ON_TRAILING_EDGE
    GOAL033:setup_bc:operational_commands:AEROELASTIC_RBF_TYPE
    GOAL033:setup_bc:operational_commands:SET_SOLVER_CONVERGENCE_ITERATIONS
    GOAL033:setup_bc:operational_commands:SET_WAKE_TERMINATION_TIME_STEPS
    GOAL033:setup_bc:operational_commands:SOLVER_SET_FARFIELD_LAYERS
    GOAL033:setup_bc:operational_commands:SET_BOUNDARY_LAYER_TYPE
    GOAL033:setup_bc:operational_commands:SET_MAX_PARALLEL_THREADS
    GOAL033:setup_bc:operational_commands:SET_SURFACE_ROUGHNESS
    GOAL033:setup_bc:operational_commands:SET_LOADS_AND_MOMENTS_UNITS
    GOAL033:setup_bc:operational_commands:SET_SIGNIFICANT_DIGITS
    GOAL033:setup_bc:operational_commands:SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE
    GOAL033:setup_bc:operational_commands:SET_VERTEX_MERGE_TOLERANCE
    GOAL033:setup_bc:operational_commands:SET_SIMULATION_LENGTH_UNITS
    GOAL033:setup_bc:operational_commands:SET_BASE_REGION_BENDING_ANGLE
    GOAL033:setup_bc:operational_commands:SOLVER_SET_REF_MACH_NUMBER
    GOAL033:setup_bc:operational_commands:SOLVER_SET_REF_VELOCITY
    GOAL033:setup_bc:operational_commands:SOLVER_SET_ITERATIONS
    GOAL033:setup_bc:operational_commands:SOLVER_SET_CONVERGENCE
    GOAL033:setup_bc:operational_commands:SOLVER_MINIMUM_CP
    GOAL033:setup_bc:operational_commands:CREATE_AIRFOIL_SEPARATION
    GOAL033:setup_bc:operational_commands:CREATE_AXIAL_VORTEX_SEPARATION
    GOAL033:setup_bc:operational_commands:CREATE_CYLINDRICAL_BULK_SEPARATION
    GOAL033:setup_bc:operational_commands:CREATE_STRATFORD_BULK_SEPARATION
    GOAL033:setup_bc:operational_commands:DELETE_SEPARATION
    GOAL033:setup_bc:operational_commands:DELETE_VORTICITY_DRAG_BOUNDARIES
    GOAL033:setup_bc:operational_commands:DETECT_LEADING_EDGES_WAKES_BY_SURFACE
    GOAL033:setup_bc:operational_commands:MARK_WAKE_TERMINATION_NODES
    GOAL033:setup_bc:operational_commands:REMOVE_INITIALIZATION
    GOAL033:setup_bc:operational_commands:SET_TRAILING_EDGE_TYPE
    GOAL033:setup_bc:operational_commands:CREATE_NEW_BASE_REGION
    GOAL033:setup_bc:operational_commands:SET_ACTUATOR_NAME
    GOAL033:setup_bc:operational_commands:INITIALIZE_SOLVER
    GOAL033:setup_bc:operational_commands:DELETE_THIN_BOUNDARIES
    GOAL033:setup_bc:operational_commands:DELETE_VISCOUS_EXCLUDED_BOUNDARIES
    GOAL033:setup_bc:operational_commands:AUTO_DETECT_BASE_REGIONS
    GOAL033:setup_bc:operational_commands:AUTO_DETECT_TRAILING_EDGES
    GOAL033:setup_bc:operational_commands:AUTO_DETECT_WAKE_TERMINATION_NODES
    GOAL033:setup_bc:operational_commands:SOLVER_SET_AOA
    GOAL033:setup_bc:operational_commands:SOLVER_SET_SIDESLIP
    GOAL033:setup_bc:operational_commands:SOLVER_SET_VELOCITY
    GOAL033:setup_bc:operational_commands:SET_PROP_ACTUATOR_RPM
    GOAL033:setup_bc:operational_commands:SET_PROP_ACTUATOR_THRUST
    GOAL033:setup_bc:operational_commands:CREATE_NEW_ACTUATOR
    GOAL033:setup_bc:operational_commands:SET_PROP_ACTUATOR_PROFILE
    GOAL033:setup_bc:operational_commands:DETECT_BASE_REGIONS_BY_SURFACE
    GOAL033:setup_bc:operational_commands:SET_SOLVER_UNSTEADY
    GOAL033:setup_bc:operational_commands:SET_FREESTREAM
    GOAL033:setup_bc:operational_commands:FLUID_PROPERTIES
    GOAL033:setup_bc:operational_commands:SOLVER_SET_REF_AREA
    GOAL033:setup_bc:operational_commands:SOLVER_SET_REF_LENGTH
    GOAL033:setup_bc:operational_commands:SET_SOLVER_ANALYSIS_LOADS_FRAME
    GOAL033:setup_bc:operational_commands:SET_ANALYSIS_MOMENTS_MODEL
    GOAL033:setup_bc:operational_commands:ENABLE_ACTUATOR
    GOAL033:setup_bc:operational_commands:SET_ACTUATOR_AXIS
    GOAL033:setup_bc:operational_commands:SET_ACTUATOR_RADIUS
    GOAL033:setup_bc:operational_commands:SET_ACTUATOR_WAKE_TYPE
    GOAL033:setup_bc:operational_commands:SET_PROP_ACTUATOR_SWIRL
    GOAL033:setup_bc:operational_commands:DELETE_ACTUATOR
    GOAL033:setup_bc:operational_commands:CREATE_NEW_INLET
    GOAL033:setup_bc:operational_commands:CREATE_NEW_OUTLET
    GOAL033:setup_bc:operational_commands:REMESH_INLET
    GOAL033:setup_bc:operational_commands:REMESH_OUTLET
    GOAL033:setup_bc:operational_commands:SET_INLET_CUSTOM_PROFILE
    GOAL033:setup_bc:operational_commands:DETECT_TRAILING_EDGES_BY_SURFACE
    GOAL033:setup_bc:operational_commands:SET_TRAILING_EDGE_SWEEP_ANGLE
    GOAL033:setup_bc:operational_commands:DETECT_WAKE_TERMINATION_NODES_BY_SURFACE
    GOAL033:setup_bc:operational_commands:SET_BASE_REGION_CP
    GOAL033:setup_bc:operational_commands:SET_BASE_REGION_TRAILING_EDGES
    GOAL033:setup_bc:operational_commands:SELECT_BASE_REGION_FACES
    GOAL033:setup_bc:operational_commands:DELETE_BASE_REGION
    GOAL033:setup_bc:operational_commands:SET_OUTLET_TRAILING_EDGES
    GOAL033:setup_bc:operational_commands:REMESH_BASE_REGION
    GOAL033:setup_bc:operational_commands:START_SOLVER
    """
    route = ROUTES[command]
    stated_dir, control_dir = tmp_path / "stated", tmp_path / "control"
    stated_dir.mkdir()
    control_dir.mkdir()
    lines, why = _render(route.stated(stated_dir))
    assert lines is not None, f"{command}: the stated case does not build on {BUILD}: {why}"
    near = [line for line in lines if line.startswith(command)]
    assert _carries(lines, route.block), (
        f"{command}: {route.block} not in the {BUILD} script; lines naming it: {near}"
    )
    if route.control is None:
        return
    control, why = _render(route.control(control_dir))
    assert control is not None, f"{command}: the control does not build on {BUILD}: {why}"
    assert not _carries(control, route.block), (
        f"{command}: the control carries {route.block} too, so the input did not put it there"
    )


def test_every_route_names_a_marker_of_its_own():
    """The docstring above names each routed command exactly once, and nothing else."""
    doc = test_setup_command_is_emitted_with_its_stated_argument_on_26124.__doc__ or ""
    prefix = "GOAL033:setup_bc:operational_commands:"
    named = [line.strip()[len(prefix) :] for line in doc.splitlines() if prefix in line]
    assert sorted(named) == sorted(ROUTES)
    assert len(named) == len(set(named))


#: Typed settings whose command has no recorded 26.124 evidence, by that command.
UNSUPPORTED_ON_26124 = {
    "jet_wake_filaments_grid_induction": "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
    "vortex_ring_normalization": "SOLVER_VORTEX_RING_NORMALIZATION",
    "axial_separation_families": "SET_AXIAL_SEPARATION_BOUNDARIES",
    "valarezo_separation_boundaries": "SET_VALAREZO_SEPARATION_BOUNDARIES",
    "crossflow_separation_boundaries": "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
    "bulk_separation": "CREATE_BULK_SEPARATION",
    "valarezo_criterion": "VALAREZO_CRITERION",
    "crossflow_separation_diameter": "SET_CROSSFLOW_SEPARATION_DIAMETER",
    "crossflow_separation_mean_diameter": "SET_CROSSFLOW_SEPARATION_CP",
    "crossflow_separation_axisymmetric": "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC",
    "legacy_solver_model": "SET_SOLVER_MODEL",
    "sonic_velocity_m_per_s": "SONIC_VELOCITY",
    "physics_auto_trailing_edges": "PHYSICS",
}


def test_a_setting_whose_command_26124_lacks_is_refused_by_name_not_dropped(tmp_path):
    """No setup capability the build lacks is dropped silently from the script.

    GOAL033:setup_bc:checks:no_silent_unsupported

    Each typed setting above states a value whose command the registry holds
    no 26.124 evidence for. Stated on 26.124 through ``build_script``, every
    one must refuse, in an error naming that command; the same case without
    the setting must build, so the refusal is the setting's and not the
    case's. A builder that skipped the line and wrote the rest of the script
    would pass a presence test and fail this one.
    """
    silent = []
    for setting, command in UNSUPPORTED_ON_26124.items():
        variation = SETTING_VARIATIONS[setting]
        stated = variation.second(tmp_path)
        assert getattr(stated.solver, setting) is not None, setting
        lines, why = _render(stated)
        if lines is not None or command not in why:
            silent.append(f"{setting} -> {command}: {why[:160] or 'built a script'}")
        keyless = stated.model_copy(update={"solver": SolverSettings()})
        assert _render(keyless)[0] is not None, f"{setting}: the case without it does not build"
    assert not silent, "stated on 26.124 and not refused by name:\n  " + "\n  ".join(silent)


# --- the commands a script-level route reaches other than one case's build ----------
#
# Ten in-scope commands are reached by a route that is not the one-case
# ``build_script`` of a setting: the sweep builder's cold start, the public
# script helpers, the raw mesh's file route and the pproc declarations of an
# unsteady row. Each is held exactly as ``ROUTES`` holds its commands: the
# stated input puts the command's block in the 26.124 script, a control on the
# same route without that input does not carry it.

Lines = Callable[[Path], list[str]]


@dataclass(frozen=True)
class ScriptRoute:
    """A stated input and its control, each rendered to 26.124 script lines."""

    stated: Lines
    control: Lines
    block: tuple[str, ...]


def _built(make: Make) -> Lines:
    """One case through ``build_script`` on 26.124; a refusal fails the case, naming why."""

    def lines(tmp: Path) -> list[str]:
        rendered, why = _render(make(tmp))
        assert rendered is not None, f"does not build on {BUILD}: {why}"
        return rendered

    return lines


def _sweep(*, cold: bool) -> Lines:
    """The three-point steady sweep, started cold at every point or warm from the last."""

    def lines(_: Path) -> list[str]:
        script = Script(BUILD)
        build_steady_sweep(_points(), script, cold=cold)
        return script.render().splitlines()

    return lines


def _helper(call: Callable[[Script], None]) -> Lines:
    """A public script helper called on a fresh 26.124 script."""

    def lines(_: Path) -> list[str]:
        script = Script(BUILD)
        call(script)
        return script.render().splitlines()

    return lines


def _raw_mesh_route(tables: str) -> Lines:
    """The raw mesh row whose sidecar marks its trailing edges by ``tables``."""
    return _built(lambda tmp: _raw_mesh_row(tmp, _library(tmp, tables)))


def _unsteady_pproc(pproc: dict[str, object]) -> Make:
    """The bare unsteady row post-processed by ``pproc``, exporting what it declares."""
    spec = PprocSpec.model_validate(pproc)
    outputs = [name.replace("{name}", "P") for name in spec.outputs(unsteady=True)]
    return lambda _: unsteady_case().model_copy(update={"pproc": spec, "outputs": outputs})


def _wing_body_pproc(pproc: PprocSpec | None) -> Make:
    """The unsteady row on the wing-body with the author's pproc (``None``) or ``pproc``."""
    return lambda tmp: _with_pproc(unsteady_case(), _wb_geometry(tmp), pproc)


SURFACE_PROBE = {
    "name": "upper_cp",
    "parameter": "CP_FREE",
    "frame": "REFERENCE",
    "point_m": [0.25, 0.1, 0.02],
}

#: THE TEN IN-SCOPE COMMANDS ``ROUTES`` DOES NOT REACH, by the route that does.
SCRIPT_ROUTES: dict[str, ScriptRoute] = {
    # A cold point clears the solution before it starts; a warm one does not.
    "CLEAR_SOLUTION": ScriptRoute(
        _sweep(cold=True), _sweep(cold=False), ("CLEAR_SOLUTION", "START_SOLVER")
    ),
    "SET_SOLVER_STEADY": ScriptRoute(
        _helper(lambda s: helpers.solver_settings(s, mode="STEADY")),
        _helper(
            lambda s: helpers.solver_settings(
                s, mode="UNSTEADY", time_iterations=10, delta_time=0.01
            )
        ),
        ("SET_SOLVER_STEADY",),
    ),
    "AIR_ALTITUDE": ScriptRoute(
        _helper(lambda s: helpers.atmosphere(s, altitude=1500.0)),
        _helper(lambda s: helpers.atmosphere(s, altitude=900.0)),
        ("AIR_ALTITUDE 1500.0 METERS",),
    ),
    # The sidecar's file route imports the edges; its detect route does not.
    "IMPORT_WAKE_EDGES_FROM_FILE": ScriptRoute(
        _raw_mesh_route(FILE_ROUTE),
        _raw_mesh_route(DETECT_AUTO),
        ("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER", "wing.wake_nodes.txt"),
    ),
    # A time-averaging window registers the per-step exports action. FR-314
    # changed this expectation: every unsteady row registers the counter now,
    # the control included, so the block the window adds is the exports action.
    "SET_NEW_UNSTEADY_SOLVER_ACTION": ScriptRoute(
        _built(lambda _: _rotor(time_averaging={"last_revs": 1.5})),
        _built(lambda _: _rotor()),
        ("SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT pfs_unsteady_exports",),
    ),
    "NEW_UNSTEADY_SOLVER_SURFACE_PROBE": ScriptRoute(
        _built(_unsteady_pproc({"surface_probes": [SURFACE_PROBE]})),
        _built(_unsteady_pproc({})),
        ("NEW_UNSTEADY_SOLVER_SURFACE_PROBE SURFACE_upper_cp CP_FREE 1 0.25 0.1 0.02",),
    ),
    # A declared surface probe needs a clean plot list, so the list is cleared first.
    "UNSTEADY_SOLVER_DELETE_ALL_PLOTS": ScriptRoute(
        _built(_unsteady_pproc({"surface_probes": [SURFACE_PROBE]})),
        _built(_unsteady_pproc({})),
        ("UNSTEADY_SOLVER_DELETE_ALL_PLOTS",),
    ),
    "UNSTEADY_SOLVER_EXPORT_PLOTS": ScriptRoute(
        _built(_unsteady_pproc({})),
        _built(_unsteady_pproc({"exports": {"plots": False}})),
        ("UNSTEADY_SOLVER_EXPORT_PLOTS", "P_plots.txt"),
    ),
    # The author's pproc: probe-line fluid plots and coefficient force plots.
    "UNSTEADY_SOLVER_NEW_FLUID_PLOT": ScriptRoute(
        _built(_wing_body_pproc(None)),
        _built(_wing_body_pproc(PprocSpec())),
        (
            "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
            "FRAME 3",
            "PARAMETER MACH",
            "NAME MACH1",
            "VERTEX -3.6576 -1.8288 0.0",
        ),
    ),
    "UNSTEADY_SOLVER_NEW_FORCE_PLOT": ScriptRoute(
        _built(_wing_body_pproc(None)),
        _built(_wing_body_pproc(PprocSpec())),
        (
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            "FRAME 2",
            "UNITS COEFFICIENTS",
            "PARAMETER CL",
            "NAME CL_MRP_TOTAL",
        ),
    ),
}


@pytest.mark.parametrize("command", [pytest.param(c, id=c) for c in SCRIPT_ROUTES])
def test_setup_command_is_emitted_through_its_script_route_on_26124(command, tmp_path):
    """The stated input reaches the 26.124 script as the command, the control does not.

    GOAL033:setup_bc:operational_commands:CLEAR_SOLUTION
    GOAL033:setup_bc:operational_commands:SET_SOLVER_STEADY
    GOAL033:setup_bc:operational_commands:AIR_ALTITUDE
    GOAL033:setup_bc:operational_commands:IMPORT_WAKE_EDGES_FROM_FILE
    GOAL033:setup_bc:operational_commands:SET_NEW_UNSTEADY_SOLVER_ACTION
    GOAL033:setup_bc:operational_commands:NEW_UNSTEADY_SOLVER_SURFACE_PROBE
    GOAL033:setup_bc:operational_commands:UNSTEADY_SOLVER_DELETE_ALL_PLOTS
    GOAL033:setup_bc:operational_commands:UNSTEADY_SOLVER_EXPORT_PLOTS
    GOAL033:setup_bc:operational_commands:UNSTEADY_SOLVER_NEW_FLUID_PLOT
    GOAL033:setup_bc:operational_commands:UNSTEADY_SOLVER_NEW_FORCE_PLOT
    """
    route = SCRIPT_ROUTES[command]
    stated_dir, control_dir = tmp_path / "stated", tmp_path / "control"
    stated_dir.mkdir()
    control_dir.mkdir()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lines = route.stated(stated_dir)
        control = route.control(control_dir)
    near = [line for line in lines if line.startswith(command)]
    assert _carries(lines, route.block), (
        f"{command}: {route.block} not in the {BUILD} script; lines naming it: {near}"
    )
    assert not _carries(control, route.block), (
        f"{command}: the control carries {route.block} too, so the input did not put it there"
    )


def test_every_script_route_names_a_marker_of_its_own():
    """The docstring above names each script-routed command exactly once, and nothing else."""
    doc = test_setup_command_is_emitted_through_its_script_route_on_26124.__doc__ or ""
    prefix = "GOAL033:setup_bc:operational_commands:"
    named = [line.strip()[len(prefix) :] for line in doc.splitlines() if prefix in line]
    assert sorted(named) == sorted(SCRIPT_ROUTES)
    assert len(named) == len(set(named))
    assert not set(SCRIPT_ROUTES) & set(ROUTES), "a command is routed twice"


# --- what 26.124 does not have, and the build support of the rest --------------------

#: The setup/BC chapters of the command database, as the GOAL-033 checker reads them.
SETUP_CHAPTERS = (
    "solver_settings",
    "solver_initialization",
    "solver_analysis",
    "advanced_settings",
    "boundary_conditions",
    "inlets_outlets",
    "actuators",
    "base_regions",
    "transition_trips",
    "unsteady_solver",
    "simulation_controls",
    "runtime_settings",
    "aeroelastic_coupling",
)

#: In-scope commands whose operation is held by the recorded native replays elsewhere.
PROVED_ELSEWHERE = {
    "tests/tier1_offline/test_fsi_native_interface_evidence.py": (
        "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS",
        "ASSIGN_AEROELASTIC_SURFACES",
        "DELETE_AEROELASTIC_STRUCTURAL_NODES",
        "EXECUTE_AEROELASTIC_ANALYSIS",
        "IMPORT_AEROELASTIC_STRUCTURAL_NODES",
        "SET_AEROELASTIC_COUPLING_IN_UNSTEADY",
        "SET_AEROELASTIC_ITERATIONS",
        "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
        "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
        "SET_AEROELASTIC_WORKING_DIRECTORY",
    ),
    "tests/tier1_offline/test_setup_native_state_evidence.py": (
        "DISABLE_SOLVER_REF_VELOCITY",
        "SOLVER_SET_MACH_NUMBER",
    ),
}

#: Every setup/BC command the emitter refuses on 26.124, by the error it refuses with:
#: no recorded 26.124 evidence, recorded removed there, or recorded broken there.
REFUSED_ON_26124: dict[str, type[Exception]] = {
    **dict.fromkeys(
        (
            "CREATE_BULK_SEPARATION",
            "DELETE_AXIAL_SEPARATION_BOUNDARIES",
            "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES",
            "DELETE_VALAREZO_CRITERION_BOUNDARIES",
            "DELETE_VALAREZO_SEPARATION_BOUNDARIES",
            "DISABLE_ACTUATOR",
            "PHYSICS",
            "SET_AXIAL_SEPARATION_BOUNDARIES",
            "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC",
            "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
            "SET_CROSSFLOW_SEPARATION_CP",
            "SET_CROSSFLOW_SEPARATION_DIAMETER",
            "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
            "SET_OUTFLOW_TRAILING_EDGES",
            "SET_SOLVER_MODEL",
            "SET_TRAILING_EDGE_BLUNTNESS_ANGLE",
            "SET_VALAREZO_SEPARATION_BOUNDARIES",
            "SOLVER_CLEAR",
            "SOLVER_UNINITIALIZE",
            "SOLVER_VORTEX_RING_NORMALIZATION",
            "SONIC_VELOCITY",
            "VALAREZO_CRITERION",
            # Excluded before this release, each on its own report.
            "SET_UNSTEADY_VISCOUS_COUPLING_ITERATION",
            "SET_VORTICITY_LIFT_MODEL",
            "SET_WAKE_RELAXATION",
            "SET_WAKE_STREAMWISE_AGGLOMERATION",
            "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
            "TRAILING_EDGES_IMPORT",
            # Documented first by the 26.125 edition (item S10, SRC-753): no 26.124
            # row; their setup keys are listed by the setup-key audit addendum.
            "DISABLE_SOLVER_TIME_AVERAGING",
            "ENABLE_SOLVER_TIME_AVERAGING",
            "SET_AEROELASTIC_CONVERGENCE_THRESHOLD",
            # Recorded removed on 26.124 by the probe that found the build
            # refusing it (RPT-154); the quasi-steady sector's direct route
            # refuses it at plan on that build.
            "SET_DIRECT_AEROELASTIC_MESH_MORPHING",
        ),
        CommandNotInVersionError,
    ),
    # Measured hanging 26.124 on 2026-09-19 and recorded broken there.
    "SOLVER_TIME_AVERAGING": BrokenCommandError,
}

#: Present on 26.124 and excluded from 0.29.0 by the owner (2026-09-27): the
#: unsteady actions already deliver per-step exports.
OWNER_EXCLUDED = frozenset({"UNSTEADY_SOLVER_ANIMATION"})


@pytest.mark.parametrize("command", [pytest.param(c, id=c) for c in REFUSED_ON_26124])
def test_a_command_26124_lacks_is_refused_by_the_emitter_naming_it(command):
    """Emitting the command on 26.124 raises, naming it, and writes no line.

    The script-level half of the refusal ``no_silent_unsupported`` holds for
    the typed settings: whatever route asks for one of these commands on
    26.124, the emitter itself refuses it by name, so no route can drop it
    silently or write a line the build does not have.
    """
    script = Script(BUILD)
    with pytest.raises(REFUSED_ON_26124[command], match=command):
        script.emit(command)
    assert command not in script.render()


def test_every_in_scope_setup_command_is_in_the_26124_database_and_the_rest_refused():
    """Build support on 26.124, the one build this release supports.

    GOAL033:setup_bc:checks:build_support

    The setup/BC chapters of the command database divide exactly into three:
    the commands this release routes (``ROUTES``, ``SCRIPT_ROUTES`` and the
    native replays named in ``PROVED_ELSEWHERE``), the commands 26.124 lacks,
    and the one the owner excluded. Every routed command carries a documented
    or verified 26.124 status in the database; every command 26.124 lacks is
    refused by the emitter, naming it. A command added to a setup chapter
    without a route or a refusal fails the partition.
    """
    registry = CommandRegistry.load()
    build = resolve(BUILD)
    chapters = {
        name for name, entry in registry.commands.items() if entry.chapter in SETUP_CHAPTERS
    }
    elsewhere = {command for commands in PROVED_ELSEWHERE.values() for command in commands}
    routed = set(ROUTES) | set(SCRIPT_ROUTES) | elsewhere
    groups = (routed, set(REFUSED_ON_26124), set(OWNER_EXCLUDED))
    assert sum(len(group) for group in groups) == len(set().union(*groups)), "overlapping groups"
    assert set().union(*groups) == chapters, (
        f"unrouted: {sorted(chapters - set().union(*groups))}; "
        f"not in the chapters: {sorted(set().union(*groups) - chapters)}"
    )
    unsupported = {}
    for command in sorted(routed | OWNER_EXCLUDED):
        status = registry.commands[command].status_in(build)
        if status is None or str(status.status) not in ("documented", "verified"):
            unsupported[command] = None if status is None else str(status.status)
    assert not unsupported, f"routed but not supported on {BUILD}: {unsupported}"
    root = Path(__file__).resolve().parents[2]
    for path, commands in PROVED_ELSEWHERE.items():
        text = (root / path).read_text(encoding="utf-8")
        for command in commands:
            assert f"GOAL033:setup_bc:operational_commands:{command}" in text, (path, command)
    admitted = []
    for command, error in REFUSED_ON_26124.items():
        script = Script(BUILD)
        try:
            script.emit(command)
        except error as refusal:
            assert command in str(refusal), (command, str(refusal)[:160])
            continue
        admitted.append(command)
    assert not admitted, f"{BUILD} admits a command recorded absent: {admitted}"


# --- settings that act on one another ------------------------------------------------


def _steady_lines(reference: ReferenceData, **solver: object) -> list[str]:
    case = steady_case().model_copy(
        update={"reference": reference, "solver": SolverSettings(**solver)}
    )
    lines, why = _render(case)
    assert lines is not None, why
    return lines


def _at(lines: list[str], line: str) -> int:
    assert line in lines, f"{line!r} not in the script"
    return lines.index(line)


def test_interacting_setup_settings_are_emitted_in_the_order_and_units_they_need():
    """Settings whose meaning depends on another setting, held while the other varies.

    GOAL033:setup_bc:checks:model_interactions

    Three interactions the solver resolves by what came before or instead:

    * THE LENGTH UNIT RESCALES WHAT FOLLOWS IT. The solver reads velocities
      and SI-declared reference dimensions in the simulation length unit, so
      the unit line precedes them and the values follow it: 30 m/s is
      30000.0 in millimetres, an SI area of 12.5 m2 is 12500000.0 mm2, and a
      reference declared in native units is left as stated.
    * THE REFERENCE MACH DISPLACES THE REFERENCE VELOCITY. Stating it
      removes the reference velocity line, while the free-stream velocity
      is held.
    * THE FLOW MODEL VARIES ALONE. Changing the model changes its line in
      ``INITIALIZE_SOLVER`` and nothing else in the script.
    """
    si = ReferenceData(area=12.5, length=1.7, normalization_units="SI")
    native = ReferenceData(area=12.5, length=1.7)
    metres = _steady_lines(si)
    millimetres = _steady_lines(si, simulation_length_unit="MILLIMETER")
    for line in (
        "SOLVER_SET_VELOCITY 30.0",
        "SOLVER_SET_REF_VELOCITY 30.0",
        "SOLVER_SET_REF_AREA 12.5",
        "SOLVER_SET_REF_LENGTH 1.7",
    ):
        _at(metres, line)
    unit = _at(millimetres, "SET_SIMULATION_LENGTH_UNITS MILLIMETER")
    for line in (
        "SOLVER_SET_VELOCITY 30000.0",
        "SOLVER_SET_REF_VELOCITY 30000.0",
        "SOLVER_SET_REF_AREA 12500000.0",
        "SOLVER_SET_REF_LENGTH 1700.0",
    ):
        assert unit < _at(millimetres, line), f"{line} precedes the unit it is read in"
    stated_native = _steady_lines(native, simulation_length_unit="MILLIMETER")
    _at(stated_native, "SOLVER_SET_VELOCITY 30000.0")
    _at(stated_native, "SOLVER_SET_REF_AREA 12.5")
    _at(stated_native, "SOLVER_SET_REF_LENGTH 1.7")

    by_mach = _steady_lines(native, reference_mach=0.2)
    _at(by_mach, "SOLVER_SET_REF_MACH_NUMBER 0.2")
    _at(by_mach, "SOLVER_SET_VELOCITY 30.0")
    assert not [line for line in by_mach if line.startswith("SOLVER_SET_REF_VELOCITY")]
    _at(_steady_lines(native), "SOLVER_SET_REF_VELOCITY 30.0")

    incompressible = _steady_lines(native, solver_model="INCOMPRESSIBLE")
    subsonic = _steady_lines(native, solver_model="SUBSONIC_PRANDTL_GLAUERT")
    assert len(incompressible) == len(subsonic)
    moved = [(a, b) for a, b in zip(incompressible, subsonic, strict=True) if a != b]
    assert moved == [("SOLVER_MODEL INCOMPRESSIBLE", "SOLVER_MODEL SUBSONIC_PRANDTL_GLAUERT")]
