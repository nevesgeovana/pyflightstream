"""The setup keys of a preset: the command each reaches, and the tables some of them hold.

Pipeline role: vocabulary, read by :class:`pyflightstream.cases.SolverSettings`
while the package loads, by the generated input glossary, by the setup
standards and by the setup-key audit (FR-319). It imports pydantic and the
command database only, so the package root may import it at load time.

ONE TABLE, THE ONE THE AUDIT WALKS. :data:`SOLVER_SETTING_COMMANDS` names the
solver command every setup key reaches. The audit of the Solver Settings,
Advanced Settings, Runtime Settings, Unsteady Solver and Solver Analysis
chapters (RPT-106) reads it to decide which choosable command has a key, and
its test fails when a command marked covered names a key this table does not
route to that command.

THE TABLE ADDED BY FR-319 is the Unsteady Solver chapter's per-step action,
the one choosable command of that chapter the audit found with no key and a
command on 26.124. It is a TABLE in a preset, and it cannot be written in a
matrix cell (FR-316): the cell grammar separates records with a comma and
pairs with a slash, and a file name carries a slash of its own.

WHAT THIS MODULE DOES NOT DO: validate an enumerated value twice. The tokens a
command takes are the command database's, per build, and the emitter checks
them when the line is written; the moments model is the one enumerated key
read here, from the same database, because a preset naming a token the
command never takes is refused at load rather than at the first build.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from pyflightstream.commands import CommandRegistry

__all__ = [
    "DEFAULT_MOMENTS_MODEL",
    "SOLVER_SETTING_COMMANDS",
    "TEMPLATE_SETTINGS_LEFT_OUT",
    "MomentsModel",
    "UnsteadyAction",
    "moments_models",
]

#: The moments model a script states when no key states one. It is BOTH the
#: default the command database records for SET_ANALYSIS_MOMENTS_MODEL (its
#: notes: "PRESSURE is the solver default", SRC-003 p.350) AND the value every
#: script of this package emitted before FR-317, so a setup naming none emits
#: the line it always emitted.
DEFAULT_MOMENTS_MODEL = "PRESSURE"


def moments_models() -> tuple[str, ...]:
    """Return the tokens SET_ANALYSIS_MOMENTS_MODEL takes, read off the database."""
    entry = CommandRegistry.load().commands["SET_ANALYSIS_MOMENTS_MODEL"]
    return tuple(str(token) for token in entry.args[0].values or ())


def _a_moments_model(value: str) -> str:
    """Return the database's spelling of a moments model, refusing any other word."""
    allowed = moments_models()
    if not allowed:
        # AN EMPTY LIST REFUSES EVERY WORD, and says why: a database entry that
        # lost its token list must not read as "your value is not one of ()".
        raise ValueError(
            f"moments_model = {value!r} cannot be checked: the command database lists no "
            "token for SET_ANALYSIS_MOMENTS_MODEL (commands/solver_analysis.yaml)"
        )
    for token in allowed:
        if token.upper() == str(value).strip().upper():
            return token
    raise ValueError(
        f"moments_model = {value!r} is not one of {', '.join(allowed)} "
        "(SET_ANALYSIS_MOMENTS_MODEL, SRC-003 p.350)"
    )


#: A moments model as a setup states it, checked against the command database.
MomentsModel = Annotated[str, AfterValidator(_a_moments_model)]


class UnsteadyAction(BaseModel):
    """``[[unsteady_solver_actions]]``: SET_NEW_UNSTEADY_SOLVER_ACTION.

    First documented by the 26.122 edition of the manual (SRC-750 p.353, the
    reference the command database carries for it; 26.124 prints it on
    p.353 of SRC-752).

    One action the solver runs after every time step of an unsteady run,
    registered at the end of the solver settings, before the package's own
    counter and wall-clock actions; the solver runs actions in creation
    order. ``type`` is the command's token, SCRIPT or COMMAND_LINE, and the
    file is named as written: nothing here writes or checks it.

    Attributes
    ----------
    type : str
        SCRIPT runs a FlightStream script, COMMAND_LINE a shell command.
    name : str
        The action's name, unique within the script.
    filename : str
        The script file or the shell command the action runs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str
    name: str = Field(min_length=1)
    filename: str = Field(min_length=1)


#: The solver command each :class:`SolverSettings` field reaches, for the
#: generated input glossary ``INPUTS.md`` (G08 of 0.27.0), which reads the
#: builds a setting is accepted on off the command's own evidence, and for the
#: setup-key audit (FR-319). A field absent here reaches no command:
#: ``timeout_s`` is the executor's and ``walltime_margin_s`` the wall-clock
#: program's. Written out rather than matched by name against the helper's
#: flags, because two fields share a helper keyword's name and reach another
#: command: ``solver_model`` and ``wall_collision_avoidance`` are arguments of
#: ``INITIALIZE_SOLVER``.
SOLVER_SETTING_COMMANDS: dict[str, str] = {
    "simulation_length_unit": "SET_SIMULATION_LENGTH_UNITS",
    "vertex_merge_tolerance_m": "SET_VERTEX_MERGE_TOLERANCE",
    "geometric_edge_bluntness_angle_deg": "SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE",
    "iterations": "SOLVER_SET_ITERATIONS",
    "convergence": "SOLVER_SET_CONVERGENCE",
    "forced_iterations": "SOLVER_SET_FORCED_ITERATIONS",
    "boundary_layer": "SET_BOUNDARY_LAYER_TYPE",
    "viscous_coupling": "SET_SOLVER_VISCOUS_COUPLING",
    "viscous_excluded": "SET_VISCOUS_EXCLUDED_BOUNDARIES",
    "surface_roughness": "SET_SURFACE_ROUGHNESS",
    "thin_boundaries": "SET_THIN_BOUNDARIES",
    "bulk_separation": "CREATE_BULK_SEPARATION",
    "airfoil_separation": "CREATE_AIRFOIL_SEPARATION",
    "axial_vortex_separation": "CREATE_AXIAL_VORTEX_SEPARATION",
    "cylindrical_bulk_separation": "CREATE_CYLINDRICAL_BULK_SEPARATION",
    "stratford_bulk_separation": "CREATE_STRATFORD_BULK_SEPARATION",
    "delete_separations": "DELETE_SEPARATION",
    "valarezo_criterion": "VALAREZO_CRITERION",
    "valarezo_separation_boundaries": "SET_VALAREZO_SEPARATION_BOUNDARIES",
    "crossflow_separation_boundaries": "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
    "crossflow_separation_diameter": "SET_CROSSFLOW_SEPARATION_DIAMETER",
    "crossflow_separation_mean_diameter": "SET_CROSSFLOW_SEPARATION_CP",
    "crossflow_separation_axisymmetric": "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC",
    "legacy_solver_model": "SET_SOLVER_MODEL",
    "trailing_edge_types": "SET_TRAILING_EDGE_TYPE",
    "disabled_wake_trailing_edges": "DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
    "leading_edge_wake_boundaries": "DETECT_LEADING_EDGES_WAKES_BY_SURFACE",
    "mark_wake_termination_nodes": "MARK_WAKE_TERMINATION_NODES",
    "delete_inlets": "DELETE_INLET",
    "delete_outlets": "DELETE_OUTLET",
    "proximal_boundaries": "SOLVER_PROXIMAL_BOUNDARIES",
    "remove_initialization": "REMOVE_INITIALIZATION",
    "base_region_bending_angle_deg": "SET_BASE_REGION_BENDING_ANGLE",
    "delete_transition_trips": "DELETE_TRANSITION_TRIP",
    "clear_vorticity_drag_boundaries": "DELETE_VORTICITY_DRAG_BOUNDARIES",
    "sonic_velocity_m_per_s": "SONIC_VELOCITY",
    "physics_auto_trailing_edges": "PHYSICS",
    "physics_auto_wake_nodes": "PHYSICS",
    "max_threads": "SET_MAX_PARALLEL_THREADS",
    "solver_model": "INITIALIZE_SOLVER",
    "wall_collision_avoidance": "INITIALIZE_SOLVER",
    "convergence_iterations": "SET_SOLVER_CONVERGENCE_ITERATIONS",
    "minimum_cp": "SOLVER_MINIMUM_CP",
    "farfield_layers": "SOLVER_SET_FARFIELD_LAYERS",
    "mesh_induced_wake_velocity": "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY",
    "unsteady_pressure_and_kutta": "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA",
    "wake_on_wake_induction": "SET_WAKE_ON_WAKE_INDUCTION",
    "additional_wake_relaxation": "ADDITIONAL_WAKE_RELAXATION_ITERATION",
    "reynolds_averaged_drag": "REYNOLDS_AVERAGED_DRAG_FORCES",
    "solver_stabilization": "SOLVER_STABILIZATION",
    "laminar_separation": "LAMINAR_SEPARATION",
    "kutta_joukowski_lift": "KUTTA_JOUKOWSKI_LIFT_FORCES",
    "aeroelastic_rbf_type": "AEROELASTIC_RBF_TYPE",
    "print_rotor_induced_velocities": "PRINT_ROTOR_INDUCED_VELOCITIES",
    "adaptive_field_grid_refinement": "SET_ADAPTIVE_FIELD_GRID_REFINEMENT",
    "rotor_induced_velocity_blending": "ROTOR_INDUCED_VELOCITY_BLENDING",
    "wake_numerical_relaxation": "SET_WAKE_NUMERICAL_RELAXATION",
    "wake_relaxation": "SET_WAKE_RELAXATION",
    "wake_decay_constant_per_m": "SET_WAKE_DECAY_CONSTANT",
    "wake_streamwise_agglomeration": "SET_WAKE_STREAMWISE_AGGLOMERATION",
    "jet_wake_decay_normalized_length": "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH",
    "jet_wake_filaments_grid_induction": "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
    "adverse_gradient_boundary_layer": "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
    "vortex_ring_normalization": "SOLVER_VORTEX_RING_NORMALIZATION",
    "wake_termination_revolutions": "SET_WAKE_TERMINATION_TIME_STEPS",
    "wake_termination_steps": "SET_WAKE_TERMINATION_TIME_STEPS",
    "symmetry_loads": "SET_ANALYSIS_SYMMETRY_LOADS",
    "significant_digits": "SET_SIGNIFICANT_DIGITS",
    "reference_velocity_m_per_s": "SOLVER_SET_REF_VELOCITY",
    "freestream_input": "SOLVER_SET_MACH_NUMBER",
    "reference_mach": "SOLVER_SET_REF_MACH_NUMBER",
    "disable_reference_velocity": "DISABLE_SOLVER_REF_VELOCITY",
    "vorticity_drag_families": "SET_VORTICITY_DRAG_BOUNDARIES",
    "axial_separation_families": "SET_AXIAL_SEPARATION_BOUNDARIES",
    "delete_surfaces": "DELETE_SURFACES",
    "slipstream_wake_stabilization": "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION",
    "load_solver_initialization": "OPEN",
    "analysis_families": "SET_SOLVER_ANALYSIS_BOUNDARIES",
    "load_units": "SET_LOADS_AND_MOMENTS_UNITS",
    "inviscid_loads": "SET_INVISCID_LOADS",
    "vorticity_lift_model": "SET_VORTICITY_LIFT_MODEL",
    "unsteady_viscous_coupling_iteration": "SET_UNSTEADY_VISCOUS_COUPLING_ITERATION",
    "moments_model": "SET_ANALYSIS_MOMENTS_MODEL",
    "unsteady_solver_actions": "SET_NEW_UNSTEADY_SOLVER_ACTION",
}

#: The setup's solver settings the input template's example leaves at their
#: defaults (G47 of 0.28.0), read by :mod:`pyflightstream.post.guides`; a setup
#: key added to the package is stated by the example or named here.
TEMPLATE_SETTINGS_LEFT_OUT: tuple[str, ...] = (
    "apply_trailing_edges",
    "apply_wake_termination",
    "apply_base_regions",
    "simulation_length_unit",
    "vertex_merge_tolerance_m",
    "geometric_edge_bluntness_angle_deg",
    "actuator_operations",
    "base_region_operations",
    "base_region_bending_angle_deg",
    "delete_inlets",
    "delete_outlets",
    "proximal_boundaries",
    "remove_initialization",
    "delete_transition_trips",
    "clear_vorticity_drag_boundaries",
    "viscous_excluded",
    "surface_roughness",
    "legacy_solver_model",
    "trailing_edge_types",
    "thin_boundaries",
    "bulk_separation",
    "airfoil_separation",
    "axial_vortex_separation",
    "cylindrical_bulk_separation",
    "stratford_bulk_separation",
    "delete_separations",
    "valarezo_criterion",
    "valarezo_separation_boundaries",
    "crossflow_separation_boundaries",
    "crossflow_separation_diameter",
    "crossflow_separation_mean_diameter",
    "crossflow_separation_axisymmetric",
    "disabled_wake_trailing_edges",
    "leading_edge_wake_boundaries",
    "mark_wake_termination_nodes",
    "sonic_velocity_m_per_s",
    "physics_auto_trailing_edges",
    "physics_auto_wake_nodes",
    "forced_iterations",
    "max_threads",
    "timeout_s",
    "walltime_margin_s",
    "solver_model",
    "convergence_iterations",
    "minimum_cp",
    "mesh_induced_wake_velocity",
    "unsteady_pressure_and_kutta",
    "wake_on_wake_induction",
    "additional_wake_relaxation",
    "reynolds_averaged_drag",
    "laminar_separation",
    "kutta_joukowski_lift",
    "aeroelastic_rbf_type",
    "print_rotor_induced_velocities",
    "adaptive_field_grid_refinement",
    "rotor_induced_velocity_blending",
    "wake_numerical_relaxation",
    "wake_relaxation",
    "wake_decay_constant_per_m",
    "wake_streamwise_agglomeration",
    "jet_wake_decay_normalized_length",
    "jet_wake_filaments_grid_induction",
    "adverse_gradient_boundary_layer",
    "vortex_ring_normalization",
    "wake_termination_revolutions",
    "wake_termination_steps",
    "symmetry_loads",
    "significant_digits",
    "reference_velocity_m_per_s",
    "freestream_input",
    "reference_mach",
    "disable_reference_velocity",
    "vorticity_drag_families",
    "axial_separation_families",
    "load_solver_initialization",
    "analysis_families",
    "load_units",
    "inviscid_loads",
    "vorticity_lift_model",
    "unsteady_viscous_coupling_iteration",
    "delete_surfaces",
    "slipstream_wake_stabilization",
    "moments_model",
    "unsteady_solver_actions",
)
