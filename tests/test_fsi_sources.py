"""Tier 1: every FSI physics function cites its formula source.

DLV-007 Section 2: the primary sources of the structural model are not
yet independently verified (TSR-014), so every physics formula must
live in a small function whose docstring states the formula source.
This schema test keeps that discipline mechanical: physics functions
must carry a "Source:" line, and every public function of the physics
modules must be classified as physics or not, so new functions cannot
slip in unlabeled.
"""

import inspect

from pyflightstream.fsi import beam, centrifugal, driver, kinematics, loads, nodes, state

PHYSICS_FUNCTIONS = [
    (centrifugal, "axial_load_distribution"),
    (centrifugal, "axial_tension"),
    (centrifugal, "total_pitch_rad"),
    (centrifugal, "propeller_moment_distribution"),
    (centrifugal, "propeller_moment_twist_stiffness"),
    (centrifugal, "southwell_fit"),
    (beam, "lumped_station_masses"),
    (beam, "_condense_massless"),
    (loads, "transfer_moment_to_elastic_axis"),
    (loads, "project_rotor_frame_loads"),
    (kinematics, "station_normal_translation"),
    (kinematics, "twist_from_node_translations"),
    (driver, "relax_displacements"),
    (driver, "revolutions_per_step"),
]

# Public functions that orchestrate solves or bookkeeping but contain no
# physical formula of their own (their physics is delegated to the list
# above). A new public function must land in exactly one of the two sets.
NON_PHYSICS_PUBLIC = {
    "centrifugal": {"solve_rotating_static", "rotating_frequencies", "campbell_sweep"},
    "beam": {
        "station_name",
        "build_beam_model",
        "apply_station_loads",
        "solve_static",
        "extract_solution",
        "modal_frequencies",
        "tributary_lengths",
    },
    "loads": {"parse_sectional_loads", "to_elastic_axis", "cross_check_totals"},
    "kinematics": {"encode_station_translations", "decode_station_translations"},
    "nodes": {
        "generate_node_layout",
        "station_triads",
        "node_positions",
        "write_node_file",
        "write_node_map",
        "load_node_map",
        "flatten_blade_translations",
        "unflatten_translations",
        "write_fsidisp",
        "read_fsidisp",
    },
    "driver": {"coupling_step"},
    "state": {"initial_state", "load_state", "write_state_atomic"},
}


def _public_functions(module):
    return {
        name
        for name, obj in vars(module).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == module.__name__
    }


def test_physics_functions_cite_their_source():
    missing = []
    for module, name in PHYSICS_FUNCTIONS:
        doc = inspect.getdoc(getattr(module, name)) or ""
        if "Source:" not in doc:
            missing.append(f"{module.__name__}.{name}")
    assert not missing, f"physics functions without a Source citation: {missing}"


def test_every_public_function_is_classified():
    modules = (
        (centrifugal, "centrifugal"),
        (beam, "beam"),
        (loads, "loads"),
        (kinematics, "kinematics"),
        (nodes, "nodes"),
        (driver, "driver"),
        (state, "state"),
    )
    for module, key in modules:
        listed = {name for mod, name in PHYSICS_FUNCTIONS if mod is module}
        unclassified = _public_functions(module) - listed - NON_PHYSICS_PUBLIC[key]
        assert not unclassified, (
            f"unclassified public functions in {module.__name__}: {unclassified}; "
            "add each to PHYSICS_FUNCTIONS (with a Source: line) or to "
            "NON_PHYSICS_PUBLIC"
        )
