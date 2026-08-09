"""Tier 1: the per-version grammar overrides, pinned as data.

Nine entries state a grammar for one build that differs from the one
every other build uses. Each was hand-written from a manual page read
side by side with another edition's page, which is the most expensive
evidence in this database and the least mechanical: nothing regenerates
it, and until this module nothing pinned it either. A bulk edit could
quietly restore the base grammar and the emitter would go on writing a
line the older solver refuses, silently, for that build alone.

The delta is the fact worth keeping, so the delta is what the table
below states, rather than a copy of each argument list.
"""

import pytest

from pyflightstream.commands import CommandRegistry

# command -> version -> the delta the manual pages showed, in the three
# forms it takes: `names` for an argument a build does not take,
# `enum:<arg>` for a value list that grew, `optional` for an argument a
# newer build stopped requiring.
PER_VERSION_GRAMMAR: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "CREATE_NEW_MOTION": {
        "26.100": {"enum:type": ("EUCLIDEAN", "6DOF", "CUSTOM")},
    },
    "SET_TRAILING_EDGE_TYPE": {
        "26.100": {"enum:type": ("STANDARD", "RELAXED", "JET_OUTFLOW")},
    },
    "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION": {
        "26.100": {"names": ("motion_id", "wake_stabilization")},
    },
    "CREATE_BULK_SEPARATION": {
        "26.101": {"names": ("name", "num_boundaries", "diameter", "boundary_indices")},
    },
    "NEW_CCS_WING_CONTROL_SURFACE": {
        "26.100": {"names": ("name", "v0", "v1", "u0", "u1", "hinge_height", "angle", "slot_gap")},
        "26.101": {"names": ("name", "v0", "v1", "u0", "u1", "hinge_height", "angle", "slot_gap")},
    },
    "NEW_SURFACE_SECTION_DISTRIBUTION": {
        "26.100": {
            "names": (
                "frame",
                "plane",
                "num_sections",
                "plot_direction",
                "surfaces",
                "surface_indices",
            )
        },
        "26.101": {
            "names": (
                "frame",
                "plane",
                "num_sections",
                "plot_direction",
                "surfaces",
                "surface_indices",
            )
        },
    },
    "SOLVER_PROXIMAL_BOUNDARIES": {
        "26.121": {"optional": ("boundary_indices",)},
    },
    "UNSTEADY_SOLVER_NEW_FLUID_PLOT": {
        "26.121": {
            "enum:parameter": (
                "CP_FREE",
                "CP_REF",
                "MACH",
                "VELOCITY",
                "VX",
                "VY",
                "VZ",
                "STATIC_PRESSURE_RATIO",
                "BL_MOMENTUM_THICKNESS",
                "BL_DISPLACEMENT_THICKNESS",
                "BL_TOTAL_THICKNESS",
                "BL_SHAPE_FACTOR",
                "BL_SKIN_FRICTION",
                "BL_TRANSITION_MARKER",
            )
        },
    },
}


def _overrides():
    """Return the registry and every (command, version) row stating args."""
    registry = CommandRegistry.load()
    found: dict[str, dict[str, tuple]] = {}
    for name, entry in registry.commands.items():
        for version, row in entry.versions.items():
            if row.args:
                found.setdefault(name, {})[version] = row.args
    return registry, found


def test_the_set_of_per_version_grammars_is_the_set_this_table_states():
    """A tenth override arriving unlisted is a finding, not a pass.

    The table is the review record of every pair of pages read twice. An
    override added without a line here was written by nobody's reading,
    and this is the assertion that makes adding one cost a sentence.
    """
    _, found = _overrides()
    listed = {(name, version) for name, rows in PER_VERSION_GRAMMAR.items() for version in rows}
    actual = {(name, version) for name, rows in found.items() for version in rows}
    assert actual == listed, (
        "the database and this table disagree about which builds state their own "
        f"grammar; only in the database: {sorted(actual - listed)}; only in the "
        f"table: {sorted(listed - actual)}"
    )


@pytest.mark.parametrize("command", sorted(PER_VERSION_GRAMMAR))
def test_a_per_version_grammar_actually_differs_from_the_base(command):
    """An override equal to the base is dead weight that reads as evidence.

    A reader who sees a row stating its own grammar concludes the
    editions were compared and found to differ. If the two are
    identical, that conclusion is wrong, and the row should be deleted
    rather than left to mislead.
    """
    registry, found = _overrides()
    base = tuple((a.name, a.required, a.values) for a in registry.commands[command].args)
    for version, args in found[command].items():
        override = tuple((a.name, a.required, a.values) for a in args)
        assert override != base, (
            f"{command} states a grammar for {version} that is identical to the base "
            "grammar, so it claims a difference it does not have"
        )


@pytest.mark.parametrize("command", sorted(PER_VERSION_GRAMMAR))
def test_a_per_version_grammar_differs_in_the_way_the_manual_says(command):
    """The delta itself, per pair, in each of the three forms."""
    registry, found = _overrides()
    entry = registry.commands[command]
    for version, expected in PER_VERSION_GRAMMAR[command].items():
        by_name = {a.name: a for a in found[command][version]}
        if "names" in expected:
            assert tuple(by_name) == expected["names"], (
                f"{command} on {version} takes a different argument list than recorded"
            )
        for arg_name in expected.get("optional", ()):
            assert by_name[arg_name].required is False, (
                f"{command} on {version} must leave {arg_name} optional; that build "
                "documents a call form omitting it entirely"
            )
            base_arg = next(a for a in entry.args if a.name == arg_name)
            assert base_arg.required is True, (
                f"{command} already leaves {arg_name} optional in the base grammar, "
                "so the override records nothing"
            )
        for key, values in expected.items():
            if not key.startswith("enum:"):
                continue
            arg_name = key.removeprefix("enum:")
            assert by_name[arg_name].values == values, (
                f"{command} on {version} accepts a different value set than recorded"
            )
            base_arg = next(a for a in entry.args if a.name == arg_name)
            assert base_arg.values != values, (
                f"{command} records the same {arg_name} values for {version} as for "
                "every other build"
            )


def test_a_list_argument_keeps_its_separator_across_a_per_version_override():
    """The one defect this family has actually produced.

    A 26.121 override of SOLVER_PROXIMAL_BOUNDARIES was written with a
    comma separator while every other build writes one index per line.
    Restating a whole argument in order to change one flag is how a
    second flag changes by accident, and the emitted line was wrong for
    that build alone, which no single-version test would have caught.
    """
    registry, found = _overrides()
    for command, rows in found.items():
        base = {a.name: a for a in registry.commands[command].args}
        for version, args in rows.items():
            for arg in args:
                if arg.name not in base or base[arg.name].separator is None:
                    continue
                assert arg.separator == base[arg.name].separator, (
                    f"{command} on {version} writes {arg.name} with the {arg.separator} "
                    f"separator while every other build uses {base[arg.name].separator}; "
                    "a per-version override is for the difference the manual states, "
                    "not for the flags around it"
                )
