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

from pyflightstream.fsi import beam, centrifugal

PHYSICS_FUNCTIONS = [
    (centrifugal, "axial_load_distribution"),
    (centrifugal, "axial_tension"),
    (centrifugal, "total_pitch_rad"),
    (centrifugal, "propeller_moment_distribution"),
    (centrifugal, "propeller_moment_twist_stiffness"),
    (centrifugal, "southwell_fit"),
    (beam, "lumped_station_masses"),
    (beam, "_condense_massless"),
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
    for module, key in ((centrifugal, "centrifugal"), (beam, "beam")):
        listed = {name for mod, name in PHYSICS_FUNCTIONS if mod is module}
        unclassified = _public_functions(module) - listed - NON_PHYSICS_PUBLIC[key]
        assert not unclassified, (
            f"unclassified public functions in {module.__name__}: {unclassified}; "
            "add each to PHYSICS_FUNCTIONS (with a Source: line) or to "
            "NON_PHYSICS_PUBLIC"
        )
