"""Tier 1: the per-version grammar overrides, pinned as data.

Seventeen entries state a grammar for some build that differs from the
one the rest use, across twenty-nine rows. Each was hand-written from a
manual page read side by side with another edition's page, which is the
most expensive evidence in this database and the least mechanical:
nothing regenerates it, and until this module nothing pinned it either.
A bulk edit could quietly restore the base grammar and the emitter
would go on writing a line the older solver refuses, silently, for that
build alone.

The nineteen rows added when the three pre-26.100 editions were read
were all NEW rows and not one was a replacement, which is worth stating
because it was not arranged. The mechanical sweep that wrote the other
version rows withheld exactly the commands whose declared arity
disagreed with the page, and those are precisely the commands whose
grammar differs. The two passes were built independently and agree on
which commands are the hard ones.

The delta is the fact worth keeping, so the delta is what the table
below states, rather than a copy of each argument list.
"""

from importlib import resources

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
        # Five of the seven builds state this list, and the entry-level
        # grammar belongs to the two newest alone. That is the shape the
        # convention produces, the entry recording what the newest
        # edition documents, and it is left visible here rather than
        # inverted: the majority is not the authority, the newest
        # edition is.
        version: {
            "names": (
                "frame",
                "plane",
                "num_sections",
                "plot_direction",
                "surfaces",
                "surface_indices",
            )
        }
        for version in ("25.000", "25.100", "26.000", "26.100", "26.101")
    },
    "AIR_ALTITUDE": {
        "25.000": {"names": ("value",)},
    },
    "BOOLEAN_UNITE_MESH": {
        version: {"names": ("num_bodies", "body_unite_types")}
        for version in ("25.000", "25.100", "26.000")
    },
    "CAD_CREATE_AUTO_CROSS_SECTIONS": {
        "25.000": {
            "names": (
                "frame",
                "axis",
                "sections",
                "body_index",
                "growth_scheme",
                "growth_rate",
                "symmetry",
            )
        },
    },
    "EXPORT_SOLVER_ANALYSIS_CSV": {
        "25.000": {"names": ("filename", "format", "units", "surfaces", "boundary_indices")},
    },
    "FLUID_PROPERTIES": {
        version: {"names": ("density", "pressure", "sonic_velocity", "temperature", "viscosity")}
        for version in ("25.000", "25.100", "26.000")
    },
    "INITIALIZE_SOLVER": {
        "25.000": {
            "names": (
                "surfaces",
                "surface_toggles",
                "wake_termination_x",
                "symmetry_type",
                "symmetry_periodicity",
                "load_frame",
                "proximity_avoidance",
                "stabilization",
                "stabilization_strength",
                "fast_multipole",
            )
        },
        **{
            version: {
                "names": (
                    "solver_model",
                    "surfaces",
                    "surface_toggles",
                    "wake_termination_x",
                    "symmetry",
                    "symmetry_copies",
                    "wall_collision_avoidance",
                    "stabilization",
                    "stabilization_strength",
                )
            }
            for version in ("25.100", "26.000")
        },
    },
    "OPEN": {
        "25.000": {"names": ("filename", "reset_parallel_cores", "load_solver_initialization")},
    },
    "SET_PROP_ACTUATOR_PROFILE": {
        version: {"names": ("actuator_index", "units_type", "file_name")}
        for version in ("25.000", "25.100")
    },
    "SURFACE_CIRCULAR_COPY_PASTE": {
        "25.000": {"names": ("surface", "coordinate_system", "axis", "num_copies")},
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

#: Which arguments each override leaves OPTIONAL, stated exhaustively
#: rather than as the exceptions. The `names` tuples above pin the
#: argument SEQUENCE and nothing else, so deleting `required: false`
#: from one argument of one build left the whole tier 1 suite green
#: while turning an omissible keyword into one the emitter writes into
#: every script for that build. Arity versus optionality is exactly what
#: reading the pre-26.100 pages against each other found, so it is the
#: half worth pinning beside the names.
#:
#: A row absent from this mapping asserts that its override leaves NOTHING
#: optional, which is why the check below reads the mapping with a default
#: rather than skipping what it does not find.
PER_VERSION_OPTIONAL: dict[tuple[str, str], tuple[str, ...]] = {
    ("BOOLEAN_UNITE_MESH", "25.000"): ("body_unite_types",),
    ("BOOLEAN_UNITE_MESH", "25.100"): ("body_unite_types",),
    ("BOOLEAN_UNITE_MESH", "26.000"): ("body_unite_types",),
    ("CREATE_BULK_SEPARATION", "26.101"): ("boundary_indices",),
    ("EXPORT_SOLVER_ANALYSIS_CSV", "25.000"): ("boundary_indices",),
    ("INITIALIZE_SOLVER", "25.000"): ("surface_toggles",),
    ("INITIALIZE_SOLVER", "25.100"): (
        "surface_toggles",
        "wake_termination_x",
        "symmetry_copies",
        "wall_collision_avoidance",
        "stabilization",
        "stabilization_strength",
    ),
    ("INITIALIZE_SOLVER", "26.000"): (
        "surface_toggles",
        "wake_termination_x",
        "symmetry_copies",
        "wall_collision_avoidance",
        "stabilization",
        "stabilization_strength",
    ),
    ("NEW_SURFACE_SECTION_DISTRIBUTION", "25.000"): ("surface_indices",),
    ("NEW_SURFACE_SECTION_DISTRIBUTION", "25.100"): ("surface_indices",),
    ("NEW_SURFACE_SECTION_DISTRIBUTION", "26.000"): ("surface_indices",),
    ("NEW_SURFACE_SECTION_DISTRIBUTION", "26.100"): ("surface_indices",),
    ("NEW_SURFACE_SECTION_DISTRIBUTION", "26.101"): ("surface_indices",),
    ("OPEN", "25.000"): ("reset_parallel_cores", "load_solver_initialization"),
    ("SOLVER_PROXIMAL_BOUNDARIES", "26.121"): ("boundary_indices",),
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


def test_every_field_an_override_leaves_unstated_is_filled_from_the_base():
    """The inheritance itself, pinned, rather than two of its outcomes.

    Two guards in this repository catch a lost `separator` and a lost
    `cites`, and both were written after that field went missing. They
    are the only two, and the fill covers more: measured on the shipped
    database, 29 override arguments inherit at least one key, across
    `cites`, `unit`, `separator` and `joins_previous`.

    Narrowing the fill to skip `joins_previous` and `unit` left the whole
    tier 1 suite green while changing what INITIALIZE_SOLVER emits on
    two builds, from one line to two:

        SYMMETRY MIRROR 2   becomes   SYMMETRY MIRROR
                                      SYMMETRY_COPIES 2

    A wrong script for those builds alone, silently, which is the defect
    class the validator was added to end. So this asserts the MECHANISM
    and not a list of fields: for every key the base declares and the
    override does not write, the loaded value must equal the base's.

    It reads the raw YAML because that is where "did not write it" is
    observable at all; on the parsed models an omitted field and one
    stated at its default are the same value, which is the whole reason
    the validator runs before parsing.
    """
    import yaml  # noqa: PLC0415

    registry = CommandRegistry.load()
    checked = 0
    for path in resources.files("pyflightstream.commands").iterdir():
        if not path.name.endswith(".yaml") or path.name == "_meta.yaml":
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, body in raw.items():
            base_raw = {arg["name"]: arg for arg in body.get("args") or []}
            if not base_raw:
                continue
            entry = registry.commands[name]
            base_parsed = {arg.name: arg for arg in entry.args}
            for version, row in (body.get("versions") or {}).items():
                if not isinstance(row, dict) or not row.get("args"):
                    continue
                loaded = {arg.name: arg for arg in entry.versions[version].args}
                for written in row["args"]:
                    inherited_from = base_raw.get(written["name"])
                    if inherited_from is None:
                        continue
                    for key in inherited_from:
                        if key in written or key == "name":
                            continue
                        checked += 1
                        assert getattr(loaded[written["name"]], key) == getattr(
                            base_parsed[written["name"]], key
                        ), (
                            f"{name} on {version} states no {key!r} for argument "
                            f"{written['name']!r}, so it must carry the base entry's "
                            "value; an override states its difference and inherits "
                            "everything else"
                        )
    assert checked >= 25, (
        f"only {checked} inherited fields were checked, and 29 argument fields "
        "inherit in the shipped database. A drop means the overrides now restate "
        "what they used to inherit, which is the shape this guard exists to stop, "
        "or that this walk stopped reaching the chapter files"
    )


def test_each_override_leaves_optional_exactly_what_this_table_says():
    """Optionality, pinned per row, because the names tuples do not pin it.

    Deleting `required: false` from `wake_termination_x` in the 25.100
    INITIALIZE_SOLVER override left the whole suite green. That change
    makes the emitter demand a keyword on one build that the build's own
    manual documents a call form without, so a caller who omits it is
    refused for a reason the manual contradicts.
    """
    _, found = _overrides()
    for command, rows in sorted(found.items()):
        for version, args in sorted(rows.items()):
            optional = tuple(arg.name for arg in args if not arg.required)
            expected = PER_VERSION_OPTIONAL.get((command, version), ())
            assert optional == expected, (
                f"{command} on {version} leaves {optional} optional and this table "
                f"says {expected}. A change here is a claim about a call form the "
                "manual prints, so it moves with the page rather than with the code"
            )
