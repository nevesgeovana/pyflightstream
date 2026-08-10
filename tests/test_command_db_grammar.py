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

# command -> version -> the delta the manual pages showed, in the four
# forms it takes: `names` for an argument set that differs, `enum:<arg>`
# for a value set that differs, `unit:<arg>` for a unit that differs,
# and `optional` for an argument a newer build stopped requiring.
#
# `enum:` said "a value list that GREW" until 2026-08-10 and that was
# wrong for two of the three rows it then carried:
# SET_TRAILING_EDGE_TYPE on 26.100 SHRANK from four tokens to three, and
# CREATE_NEW_MOTION on 26.100 renamed one, ROTARY becoming EUCLIDEAN.
# Three more value deltas were missing from the table entirely, so the
# claim below that this is the review record of every pair of pages read
# twice was false while it was being made.
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
        # The unit is a manual claim and it belongs in a delta table
        # rather than in the code. The base grammar carries a units
        # TOKEN and so states no unit on the value; this edition takes
        # no token and its page states the value is in feet on the
        # parameter row itself (SRC-749 p.286). Same call, factor of
        # 3.28, which is why the helper refuses silence on this build.
        "25.000": {"names": ("value",), "unit:value": "ft"},
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
        "25.000": {
            "names": ("filename", "format", "units", "surfaces", "boundary_indices"),
            "enum:format": (
                "CP-FREESTREAM",
                "CP-REFERENCE",
                "PRESSURE",
                "DIFFERENCE-PRESSURE",
            ),
        },
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
                ),
                "enum:solver_model": (
                    "INCOMPRESSIBLE",
                    "SUBSONIC_PRANDTL_GLAUERT",
                    "TRANSONIC_FIELD_PANEL",
                    "SUPERSONIC_LINEAR_DOUBLET",
                    "TANGENT_CONE",
                    "MODIFIED_NEWTONIAN",
                ),
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
        for key, unit in expected.items():
            if not key.startswith("unit:"):
                continue
            arg_name = key.removeprefix("unit:")
            assert by_name[arg_name].unit == unit, (
                f"{command} on {version} states a different unit for {arg_name} than "
                "recorded; a unit is a manual claim and moves with its page"
            )
            base_arg = next(a for a in entry.args if a.name == arg_name)
            assert base_arg.unit != unit, (
                f"{command} records the same {arg_name} unit for {version} as for "
                "every other build, so the row claims a difference it does not have"
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
    # 33 fields inherit in the shipped database, distributed cites 12,
    # unit 12, separator 7 and joins_previous 2. The floor was written
    # as 25 against a stated 29, so its message contradicted its own
    # output and its slack was 8 rather than the 4 intended: a 24
    # percent silent-drop budget on a guard whose subject is drops.
    # Deleting a whole ROW is caught by the set assertion above, so this
    # floor's real job is only that the walk still reaches the chapter
    # files, and it sits near the true value.
    # EXACT, not a floor. A floor was tried at 25 against a stated 29,
    # then at 30 against a measured 33, and both times the slack was
    # large enough that whole chapter files could drop out of the walk
    # unnoticed: four of the seven, at the second floor. Deleting a row
    # is caught by the set assertion above, so the only job left here is
    # that the walk still reaches everything, and a number is the way to
    # say that. It moves when an override is added, which is a sentence
    # in a delta table anyway.
    assert checked == 33, (
        f"{checked} inherited fields were checked and the shipped database has 33, "
        "distributed cites 12, unit 12, separator 7 and joins_previous 2. A change "
        "here is an override that stopped inheriting or started, both of which are "
        "readable in the diff; a DROP with no such diff means the walk stopped "
        "reaching a chapter file"
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


#: The fields on which an override argument may differ from the base
#: argument of the same name, each of them named per row by a delta
#: table above. Measured across the shipped database on 2026-08-10:
#: `required` in three places, `values` in six, and `unit` in one. The
#: unit joined the same day and by this guard firing on it, which is the
#: intended way for a tenth field to arrive: as a finding a reader
#: answers, not as a silent difference. Every other field is identical
#: everywhere.
_FIELDS_A_DELTA_MAY_TOUCH = frozenset({"required", "values", "unit"})

#: Every field an ArgSpec carries that the check below compares.
_COMPARED_FIELDS = (
    "type",
    "values",
    "required",
    "unit",
    "separator",
    "cites",
    "own_line",
    "joins_previous",
    "on_command_line",
    "fixed_length",
    "all_sentinel",
)


def test_an_override_differs_from_its_base_only_where_a_delta_table_says_so():
    """Everything the two delta tables do not name, pinned in one loop.

    `PER_VERSION_GRAMMAR` pins argument NAMES and value sets;
    `PER_VERSION_OPTIONAL` pins optionality. Between them they leave
    `type`, `unit`, `separator`, `cites`, `own_line`, `joins_previous`,
    `on_command_line`, `fixed_length` and `all_sentinel` unguarded
    across 136 override argument declarations, and retyping one
    argument of one build from int to float left the whole tier 1 suite
    green while making the emitter render 3.0 where that build's page
    prints 3.

    Closed as one loop rather than nine table columns because the data
    allows it: measured over the shipped database, an override differs
    from its base on `required` and `values` and on nothing else, ever.
    A tenth field starting to differ is a finding for a reader, which is
    what this says when it fires.
    """
    registry, found = _overrides()
    compared = 0
    for command, rows in sorted(found.items()):
        base = {arg.name: arg for arg in registry.commands[command].args}
        for version, args in sorted(rows.items()):
            for arg in args:
                inherited = base.get(arg.name)
                if inherited is None:
                    continue
                for field in _COMPARED_FIELDS:
                    if field in _FIELDS_A_DELTA_MAY_TOUCH:
                        continue
                    compared += 1
                    assert getattr(arg, field) == getattr(inherited, field), (
                        f"{command} on {version} gives {arg.name!r} a different {field!r} "
                        f"from the base grammar. Only required and values have ever "
                        "differed in this database; a change here is either a manual "
                        "claim that needs its page and a line in a delta table, or an "
                        "edit nobody meant"
                    )
    # EXACT, for the reason the sibling floor above gives. At 900 the
    # slack was 162 and sixteen of the seventeen commands could vanish
    # from the walk with it green, on a guard whose subject is silent
    # drops. 944 is 118 override arguments with a base counterpart times
    # the eight fields no delta table may name; the other 18 arguments
    # name nothing the base carries and are skipped. It was 1062 before
    # `unit` became a delta form, which is one fewer compared field.
    assert compared == 944, (
        f"{compared} field comparisons ran and the shipped database supports 944. "
        "A rise is an override gaining an argument the base also carries, a fall is "
        "one losing it or the walk losing a chapter file"
    )


def test_every_value_delta_in_the_database_is_one_this_table_names():
    """The other direction, which the pair check does not cover.

    `test_the_set_of_per_version_grammars_is_the_set_this_table_states`
    compares (command, version) PAIRS, so a value set differing on a row
    already listed for some other reason is invisible to it. Appending
    an invented token to one override's value list passed the whole
    suite, on a row the table names for its argument set.

    `required` has had this guard since PER_VERSION_OPTIONAL, which
    reads with a default so a row absent from it asserts nothing is
    optional. This is the same shape for values.
    """
    registry, found = _overrides()
    measured = set()
    for command, rows in found.items():
        base = {arg.name: arg for arg in registry.commands[command].args}
        for version, args in rows.items():
            for arg in args:
                inherited = base.get(arg.name)
                if inherited is not None and arg.values != inherited.values:
                    measured.add((command, version, arg.name))
    listed = {
        (command, version, key.removeprefix("enum:"))
        for command, rows in PER_VERSION_GRAMMAR.items()
        for version, delta in rows.items()
        for key in delta
        if key.startswith("enum:")
    }
    assert measured == listed, (
        "the database and this table disagree about which overrides state their own "
        f"value set; only in the database: {sorted(measured - listed)}; only in the "
        f"table: {sorted(listed - measured)}. A value set is a manual claim and costs "
        "a line here"
    )
