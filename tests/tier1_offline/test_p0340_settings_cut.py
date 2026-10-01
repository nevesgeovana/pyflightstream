"""The cut of script/helpers.py: solver_settings over per-family emitters (AD-17, WP9a).

``pyflightstream.script.helpers.solver_settings`` became, in 0.34.0, the
facade over the per-family emitters of the private module
``script/_settings.py``, and the relaxed trailing edge moved to
``script/_relaxed_te.py``. What the cut must not change is pinned here
against the 0.33.0 tree, not against the code it tests: the signature (all
61 parameters, their order and their defaults), the emitted lines and their
order on three builds whose grammars differ, the one home of every keyword,
and the public path of every name that moved.
"""

from __future__ import annotations

import inspect

import pytest

from pyflightstream.script import Script, helpers
from pyflightstream.script._settings import (
    ADVANCED_FAMILY,
    BOUNDARY_LAYER_FAMILY,
    CONVERGENCE_FAMILY,
    RUNTIME_FAMILY,
    SEPARATION_FAMILY,
)

#: The keyword-only parameters of solver_settings at v0.33.0, in order. Every
#: default is None except disable_ref_velocity, whose default is False.
V0330_KEYWORDS = (
    "vorticity_drag_boundaries",
    "mode",
    "time_iterations",
    "delta_time",
    "aoa",
    "sideslip",
    "velocity",
    "mach",
    "ref_velocity",
    "ref_mach",
    "ref_area",
    "ref_length",
    "iterations",
    "convergence",
    "forced_iterations",
    "max_threads",
    "boundary_layer",
    "viscous_coupling",
    "viscous_excluded",
    "surface_roughness",
    "thin_boundaries",
    "bulk_separation",
    "airfoil_separation",
    "axial_vortex_separation",
    "cylindrical_bulk_separation",
    "stratford_bulk_separation",
    "delete_separations",
    "axial_separation_boundaries",
    "valarezo_separation_boundaries",
    "crossflow_separation_boundaries",
    "crossflow_separation_diameter",
    "crossflow_separation_axisymmetric",
    "laminar_separation",
    "convergence_iterations",
    "minimum_cp",
    "reynolds_averaged_drag",
    "mesh_induced_wake_velocity",
    "farfield_layers",
    "unsteady_pressure_and_kutta",
    "wake_termination_time_steps",
    "wake_on_wake_induction",
    "additional_wake_relaxation",
    "aeroelastic_rbf_type",
    "kutta_joukowski_lift",
    "print_rotor_induced_velocities",
    "adaptive_field_grid_refinement",
    "jet_wake_filaments_grid_induction",
    "rotor_induced_velocity_blending",
    "wake_numerical_relaxation",
    "jet_wake_decay_normalized_length",
    "wake_decay_constant",
    "solver_stabilization",
    "disable_ref_velocity",
    "solver_model",
    "valarezo_criterion",
    "crossflow_separation_mean_diameter",
    "wake_relaxation",
    "wake_streamwise_agglomeration",
    "adverse_gradient_boundary_layer",
    "vortex_ring_normalization",
)

#: The keywords no family table emits: the time regime, the separation erase
#: and the assignment models, the minimum-Cp limiter (it has a library
#: default) and the deferred induced-drag selection, each with its own emitter.
OWN_EMITTER = {
    "mode",
    "time_iterations",
    "delta_time",
    "delete_separations",
    "bulk_separation",
    "airfoil_separation",
    "axial_vortex_separation",
    "cylindrical_bulk_separation",
    "stratford_bulk_separation",
    "minimum_cp",
    "vorticity_drag_boundaries",
}

SEPARATION = {"name": "s1", "boundaries": [1, 2]}

#: One value for every keyword; each build drops the ones it does not take.
EVERY = {
    "mode": "UNSTEADY",
    "time_iterations": 20,
    "delta_time": 0.02,
    "aoa": 2.0,
    "sideslip": -1.5,
    "velocity": 30.0,
    "mach": 0.1,
    "ref_velocity": 40.0,
    "ref_mach": 0.12,
    "ref_area": 1.5,
    "ref_length": 0.3,
    "iterations": 500,
    "convergence": 1e-05,
    "forced_iterations": True,
    "max_threads": 4,
    "boundary_layer": "turbulent",
    "viscous_coupling": "ENABLE",
    "viscous_excluded": [2],
    "surface_roughness": 0.0,
    "thin_boundaries": "all",
    "axial_separation_boundaries": [1],
    "valarezo_separation_boundaries": [],
    "crossflow_separation_boundaries": "all",
    "crossflow_separation_diameter": 0.4,
    "crossflow_separation_axisymmetric": False,
    "delete_separations": "all",
    "airfoil_separation": [SEPARATION],
    "axial_vortex_separation": [SEPARATION],
    "cylindrical_bulk_separation": [SEPARATION],
    "stratford_bulk_separation": [SEPARATION],
    "convergence_iterations": 3,
    "minimum_cp": -50.0,
    "reynolds_averaged_drag": True,
    "mesh_induced_wake_velocity": False,
    "farfield_layers": 5,
    "unsteady_pressure_and_kutta": True,
    "wake_termination_time_steps": 120,
    "wake_on_wake_induction": "DISABLE",
    "additional_wake_relaxation": True,
    "laminar_separation": False,
    "aeroelastic_rbf_type": "gaussian",
    "kutta_joukowski_lift": True,
    "print_rotor_induced_velocities": False,
    "adaptive_field_grid_refinement": True,
    "rotor_induced_velocity_blending": 0.3,
    "wake_numerical_relaxation": 0.1,
    "jet_wake_decay_normalized_length": 50.0,
    "jet_wake_filaments_grid_induction": True,
    "wake_decay_constant": 19.1,
    "solver_stabilization": 0.5,
    "disable_ref_velocity": True,
    "solver_model": "SUBSONIC",
    "valarezo_criterion": True,
    "crossflow_separation_mean_diameter": 0.2,
    "wake_relaxation": False,
    "wake_streamwise_agglomeration": True,
    "adverse_gradient_boundary_layer": False,
    "vortex_ring_normalization": True,
    "vorticity_drag_boundaries": [1, "tail"],
}

#: The keywords each build refuses, measured on the 0.33.0 tree.
REFUSED = {
    "25.000": {
        "adaptive_field_grid_refinement",
        "additional_wake_relaxation",
        "aeroelastic_rbf_type",
        "airfoil_separation",
        "axial_vortex_separation",
        "crossflow_separation_axisymmetric",
        "crossflow_separation_diameter",
        "cylindrical_bulk_separation",
        "jet_wake_decay_normalized_length",
        "jet_wake_filaments_grid_induction",
        "kutta_joukowski_lift",
        "laminar_separation",
        "print_rotor_induced_velocities",
        "reynolds_averaged_drag",
        "rotor_induced_velocity_blending",
        "solver_stabilization",
        "stratford_bulk_separation",
        "thin_boundaries",
        "valarezo_separation_boundaries",
        "wake_decay_constant",
        "wake_numerical_relaxation",
        "wake_on_wake_induction",
        "bulk_separation",
        "delete_separations",
        "disable_ref_velocity",
    },
    "26.100": {
        "adverse_gradient_boundary_layer",
        "aeroelastic_rbf_type",
        "airfoil_separation",
        "axial_vortex_separation",
        "crossflow_separation_mean_diameter",
        "cylindrical_bulk_separation",
        "jet_wake_decay_normalized_length",
        "jet_wake_filaments_grid_induction",
        "rotor_induced_velocity_blending",
        "solver_model",
        "solver_stabilization",
        "stratford_bulk_separation",
        "thin_boundaries",
        "valarezo_criterion",
        "vortex_ring_normalization",
        "wake_decay_constant",
        "wake_numerical_relaxation",
        "wake_relaxation",
        "wake_streamwise_agglomeration",
        "bulk_separation",
        "delete_separations",
        "disable_ref_velocity",
    },
    "26.124": {
        "adverse_gradient_boundary_layer",
        "axial_separation_boundaries",
        "axial_vortex_separation",
        "crossflow_separation_axisymmetric",
        "crossflow_separation_boundaries",
        "crossflow_separation_diameter",
        "crossflow_separation_mean_diameter",
        "cylindrical_bulk_separation",
        "jet_wake_filaments_grid_induction",
        "solver_model",
        "valarezo_criterion",
        "valarezo_separation_boundaries",
        "vortex_ring_normalization",
        "wake_relaxation",
        "wake_streamwise_agglomeration",
        "bulk_separation",
    },
}

_HEAD = (
    "SET_SOLVER_UNSTEADY\nTIME_ITERATIONS 20\nDELTA_TIME 0.02\n\n"
    "SOLVER_SET_AOA 2.0\nSOLVER_SET_SIDESLIP -1.5\nSOLVER_SET_VELOCITY 30.0\n"
    "SOLVER_SET_MACH_NUMBER 0.1\nSOLVER_SET_REF_VELOCITY 40.0\n"
    "SOLVER_SET_REF_MACH_NUMBER 0.12\nSOLVER_SET_REF_AREA 1.5\nSOLVER_SET_REF_LENGTH 0.3\n"
    "SOLVER_SET_ITERATIONS 500\nSOLVER_SET_CONVERGENCE 1e-05\nSET_MAX_PARALLEL_THREADS 4\n"
    "SOLVER_SET_FORCED_ITERATIONS ENABLE\nSET_BOUNDARY_LAYER_TYPE TURBULENT\n"
    "SET_SOLVER_VISCOUS_COUPLING ENABLE\nSET_VISCOUS_EXCLUDED_BOUNDARIES 1\n2\n\n"
    "SET_SURFACE_ROUGHNESS 0.0\n"
)
_TAIL = "START_SOLVER\nSET_VORTICITY_DRAG_BOUNDARIES 2\n1,3\n\n"

#: The script each build rendered on the 0.33.0 tree (tag v0.33.0) for EVERY
#: minus the keywords it refuses, then start_solver: the oracle of the cut.
V0330_SCRIPTS = {
    "25.000": _HEAD
    + "SET_AXIAL_SEPARATION_BOUNDARIES 1\n1\n\n"
    + "SET_CROSSFLOW_SEPARATION_BOUNDARIES -1\n\n"
    + "SET_SOLVER_CONVERGENCE_ITERATIONS 3\nSOLVER_MINIMUM_CP -50.0\n"
    + "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY DISABLE\nSOLVER_SET_FARFIELD_LAYERS 5\n"
    + "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA ENABLE\nSET_WAKE_TERMINATION_TIME_STEPS 120\n"
    + "SET_SOLVER_MODEL SUBSONIC\nVALAREZO_CRITERION ENABLE\nSET_CROSSFLOW_SEPARATION_CP 0.2\n"
    + "SET_WAKE_RELAXATION DISABLE\nSET_WAKE_STREAMWISE_AGGLOMERATION ENABLE\n"
    + "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER DISABLE\n"
    + "SOLVER_VORTEX_RING_NORMALIZATION ENABLE\n"
    + _TAIL,
    "26.100": _HEAD
    + "SET_AXIAL_SEPARATION_BOUNDARIES 1\n1\n\n"
    + "DELETE_VALAREZO_SEPARATION_BOUNDARIES\n"
    + "SET_CROSSFLOW_SEPARATION_BOUNDARIES -1\n\n"
    + "SET_CROSSFLOW_SEPARATION_DIAMETER 0.4\nSET_CROSSFLOW_SEPARATION_AXISYMMETRIC DISABLE\n"
    + "SET_SOLVER_CONVERGENCE_ITERATIONS 3\nSOLVER_MINIMUM_CP -50.0\n"
    + "REYNOLDS_AVERAGED_DRAG_FORCES ENABLE\nSOLVER_SET_MESH_INDUCED_WAKE_VELOCITY DISABLE\n"
    + "SOLVER_SET_FARFIELD_LAYERS 5\nSOLVER_UNSTEADY_PRESSURE_AND_KUTTA ENABLE\n"
    + "SET_WAKE_TERMINATION_TIME_STEPS 120\nSET_WAKE_ON_WAKE_INDUCTION DISABLE\n"
    + "ADDITIONAL_WAKE_RELAXATION_ITERATION ENABLE\nLAMINAR_SEPARATION DISABLE\n"
    + "KUTTA_JOUKOWSKI_LIFT_FORCES ENABLE\nPRINT_ROTOR_INDUCED_VELOCITIES DISABLE\n"
    + "SET_ADAPTIVE_FIELD_GRID_REFINEMENT ENABLE\n"
    + _TAIL,
    "26.124": _HEAD
    + "SET_THIN_BOUNDARIES -1\n\n"
    + "DELETE_SEPARATION -1\n"
    + "CREATE_AIRFOIL_SEPARATION s1 2 DISABLE\n1,2\n\n"
    + "CREATE_STRATFORD_BULK_SEPARATION s1 2\n1,2\n\n"
    + "SET_SOLVER_CONVERGENCE_ITERATIONS 3\nSOLVER_MINIMUM_CP -50.0\n"
    + "REYNOLDS_AVERAGED_DRAG_FORCES ENABLE\nSOLVER_SET_MESH_INDUCED_WAKE_VELOCITY DISABLE\n"
    + "SOLVER_SET_FARFIELD_LAYERS 5\nSOLVER_UNSTEADY_PRESSURE_AND_KUTTA ENABLE\n"
    + "SET_WAKE_TERMINATION_TIME_STEPS 120\nSET_WAKE_ON_WAKE_INDUCTION DISABLE\n"
    + "ADDITIONAL_WAKE_RELAXATION_ITERATION ENABLE\nLAMINAR_SEPARATION DISABLE\n"
    + "AEROELASTIC_RBF_TYPE GAUSSIAN\nKUTTA_JOUKOWSKI_LIFT_FORCES ENABLE\n"
    + "PRINT_ROTOR_INDUCED_VELOCITIES DISABLE\nSET_ADAPTIVE_FIELD_GRID_REFINEMENT ENABLE\n"
    + "ROTOR_INDUCED_VELOCITY_BLENDING 0.3\nSET_WAKE_NUMERICAL_RELAXATION 0.1\n"
    + "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH 50.0\nSET_WAKE_DECAY_CONSTANT 19.1\n"
    + "SOLVER_STABILIZATION 0.5\nDISABLE_SOLVER_REF_VELOCITY\n"
    + _TAIL,
}

#: Every public name that left helpers.py in the cut, by its new home.
MOVED = {
    "pyflightstream.script._settings": (
        "free_stream",
        "fluid_fifth_property",
        "atmosphere",
        "unsteady_solver",
        "start_solver",
        "initialize_solver",
    ),
    "pyflightstream.script._relaxed_te": (
        "RELAXED_TE_KEYWORD",
        "RELAXED_TE_FIELDS_WITHOUT_DIRECTION",
        "RELAXED_TE_FIELDS_WITH_DIRECTION",
        "RELAXED_SHEDDING_DIRECTIONS",
        "DEFAULT_SHEDDING_DIRECTION",
        "resolve_shedding_direction",
        "RelaxedTrailingEdge",
        "parse_relaxed_trailing_edge",
    ),
}


def test_p0340_settings_cut_keeps_the_v0330_signature():
    """AD-17 (WP9a): the facade keeps all 61 parameters, their order and defaults."""
    parameters = list(inspect.signature(helpers.solver_settings).parameters.values())
    assert [p.name for p in parameters] == ["script", *V0330_KEYWORDS]
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters[1:])
    defaults = {p.name: p.default for p in parameters[1:]}
    assert defaults.pop("disable_ref_velocity") is False
    assert set(defaults.values()) == {None}


@pytest.mark.parametrize("version", sorted(V0330_SCRIPTS))
def test_p0340_settings_cut_emits_every_family_in_the_v0330_order(version):
    """AD-17 (WP9a): every family emits its lines in the 0.33.0 order, byte for byte.

    One call with every keyword the build takes, on three builds whose
    grammars differ (the pre-26.100 flags, the 26.100 separation lists, the
    26.12x assignment models), against the script the 0.33.0 tree rendered.
    The snapshot records the same call: the four boolean toggles read ahead
    of the first emission and the deferred selection by index.
    """
    script = Script(version=version)
    script.declare_existing(boundaries={"wing": 1, "body": 2, "tail": 3})
    kwargs = {key: value for key, value in EVERY.items() if key not in REFUSED[version]}
    setup = helpers.solver_settings(script, **kwargs)
    helpers.start_solver(script)
    assert script.render() == V0330_SCRIPTS[version]
    assert setup is script.solver_setup
    assert setup.flags["SET_VORTICITY_DRAG_BOUNDARIES"].value == [1, 3]
    assert setup.flags["SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY"].value is False


def test_p0340_settings_cut_gives_every_keyword_one_home():
    """AD-17 (WP9a): every keyword of the facade is emitted by exactly one family.

    A row in one family table, or one of the keywords with an emitter of
    their own; never two, and never none, so a keyword added to the facade
    without a row in its family's table fails here rather than validating and
    emitting nothing.
    """
    families = (
        RUNTIME_FAMILY,
        BOUNDARY_LAYER_FAMILY,
        SEPARATION_FAMILY,
        CONVERGENCE_FAMILY,
        ADVANCED_FAMILY,
    )
    rows = [row.argument for family in families for row in family]
    assert len(rows) == len(set(rows)), "a keyword sits in two family rows"
    assert not set(rows) & OWN_EMITTER, "a keyword has a row and an emitter of its own"
    assert set(rows) | OWN_EMITTER == set(V0330_KEYWORDS)
    for family in families:
        for row in family:
            assert (row.form == "list") == bool(row.erase), row


def test_p0340_settings_cut_keeps_every_moved_public_path():
    """AD-17 (WP9a): a moved name still imports from helpers, as the same object."""
    import importlib

    for home, names in MOVED.items():
        module = importlib.import_module(home)
        for name in names:
            assert getattr(helpers, name) is getattr(module, name), (home, name)
    # The facade's emitter is reached through the private module, so the
    # cut offers no new public name on helpers.
    assert not hasattr(helpers, "emit_solver_settings")
