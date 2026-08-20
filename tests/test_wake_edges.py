"""Tier 1: the workspace-layer wake-edge marking inputs.

Pipeline role: quality gate on the two solver inputs the wake-edge
import takes, and on the node list the file it reads carries.

REPRODUCTION, for the half of this that is a defect rather than a
feature. Before this module existed the two inputs the trailing-edge
route needs had no home at all: a case could reach the emitter with no
nodes to mark and a tolerance of zero, and the emitted script was
perfectly well formed. The shortest call that showed it was

>>> from pyflightstream.script import Script
>>> script = Script(version="26.122")
>>> script.emit("IMPORT_WAKE_EDGES_FROM_FILE", "VORTEX_SHEDDING", 0.0)
>>> script.render().strip()
'IMPORT_WAKE_EDGES_FROM_FILE VORTEX_SHEDDING 0.0'

A tolerance of zero matches an imported coordinate to a mesh edge only
on exact floating-point equality, so the run marks nothing and reports
no error; the emitter cannot see that, because the grammar is right.
The refusal has to sit where the case is assembled, which is here.
"""

import math

import numpy
import pytest

from pyflightstream.commands import CommandRegistry
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz
from pyflightstream.workspace.wake_edges import (
    DEFAULT_EDGE_TYPE,
    DEFAULT_TOLERANCE,
    LENGTH_UNIT_COMMAND,
    TRAILING_EDGE_DETECTION_COMMAND,
    WAKE_EDGE_IMPORT_COMMAND,
    WakeEdgeImport,
    edge_types,
    evidence_notice,
    node_file_units,
    tolerance_unit,
    write_node_file,
)

ONE_NODE = (PointXyz(x_m=1.0, y_m=0.0, z_m=0.0),)


def test_the_two_inputs_default_to_what_the_manual_page_prints():
    """Both defaults are the vendor's own, not this package's taste.

    The page prints a sample call passing VORTEX_SHEDDING and 0.0001 and
    states the same number as the parameter default in its own table, so
    a caller who sets neither gets the call the manual documents. That
    is the whole defence of these two numbers, and it is the reason the
    item asked for a default with a source rather than a default.
    """
    settings = WakeEdgeImport(nodes=ONE_NODE)
    assert settings.edge_type == DEFAULT_EDGE_TYPE == "VORTEX_SHEDDING"
    assert settings.tolerance == DEFAULT_TOLERANCE == 0.0001


def test_the_edge_types_come_from_the_command_record_and_not_from_a_copy():
    """One vocabulary, one home.

    The four types are a per-version closed set in the command database,
    and SET_TRAILING_EDGE_TYPE carries three of them on 26.100. A
    constant here would be a second copy that cannot follow a build, so
    the values are read from the record every time.
    """
    entry = CommandRegistry.load().commands[WAKE_EDGE_IMPORT_COMMAND]
    (declared,) = [arg for arg in entry.args if arg.name == "type"]
    assert edge_types() == declared.values
    assert DEFAULT_EDGE_TYPE in edge_types()


def test_the_tolerance_unit_is_read_from_the_record_and_not_copied_here():
    """One home for a derived reading, found by trying to break this module.

    The unit is not printed in the manual; it is derived from what the
    page describes, and that derivation carries the entry's citation. It
    was a constant in this module for one draft, which made a second
    copy that could disagree with the record it was derived from: the
    refusal would have gone on naming a unit the database had stopped
    recording, and every test here would still have passed. Read from
    the record, deleting the unit from the yaml turns this red.
    """
    entry = CommandRegistry.load().commands[WAKE_EDGE_IMPORT_COMMAND]
    (declared,) = [arg for arg in entry.args if arg.name == "tolerance"]
    assert tolerance_unit() == declared.unit == "simulation length units"


def test_a_case_with_nothing_to_mark_is_refused_and_the_count_is_in_the_message():
    """An empty node list is the silently empty marking, before the run.

    The file is what names the edges. With no nodes the solver marks
    nothing and says nothing, so the case has to be refused where it is
    assembled rather than diagnosed afterwards from a wake that is not
    there.
    """
    with pytest.raises(InputArtifactError) as refusal:
        WakeEdgeImport(nodes=())
    message = str(refusal.value)
    assert "0" in message, "the refusal does not state how many nodes were supplied"
    assert WAKE_EDGE_IMPORT_COMMAND in message, (
        "the refusal does not name the command whose input this is"
    )


@pytest.mark.parametrize("tolerance", [0.0, -1e-6, math.inf, math.nan])
def test_a_tolerance_that_can_match_nothing_is_refused_with_its_own_value(tolerance):
    """Positive and finite, and the message carries the number given.

    Zero matches on exact equality and matches nothing in practice; a
    negative distance is not a distance; infinity and a NaN both make
    the mid-point test meaningless. Each is refused with the value the
    caller wrote, because a refusal that does not echo the input leaves
    the caller checking the wrong field.
    """
    with pytest.raises(InputArtifactError) as refusal:
        WakeEdgeImport(nodes=ONE_NODE, tolerance=tolerance)
    message = str(refusal.value)
    assert repr(tolerance) in message or str(tolerance) in message, (
        f"the refusal does not name the value it refused ({tolerance!r})"
    )
    assert "simulation length units" in message, (
        "the refusal states no unit, so a caller cannot tell whether the number they "
        "wrote was in the unit the solver reads"
    )


def test_an_edge_type_outside_the_record_is_refused_with_the_set():
    """A closed set is only closed if something closes it."""
    with pytest.raises(InputArtifactError) as refusal:
        WakeEdgeImport(nodes=ONE_NODE, edge_type="SUPERSONIC")
    message = str(refusal.value)
    assert "SUPERSONIC" in message
    for value in edge_types():
        assert value in message, f"the refusal does not offer {value}"


def test_the_evidence_behind_the_default_route_is_stated_with_both_commands():
    """The trade is deliberate, so it has to be visible.

    Marking wake edges from a file replaces an angle criterion that
    cannot mark the edges this capability exists for. The replacement is
    documented and has been run by nobody; what it replaces carries
    committed probe reports on three builds. A later reader who meets
    only the default reads it as settled practice, which is what this
    sentence exists to prevent.

    Derived from the registry rather than written out, so the day a
    probe promotes the command the sentence moves with it.
    """
    notice = evidence_notice("26.123")
    assert WAKE_EDGE_IMPORT_COMMAND in notice
    assert TRAILING_EDGE_DETECTION_COMMAND in notice
    assert "26.123" in notice, "the notice does not name the build it is about"

    registry = CommandRegistry.load()
    detection = registry.commands[TRAILING_EDGE_DETECTION_COMMAND]
    verified = sorted(
        canonical for canonical, row in detection.versions.items() if row.status.value == "verified"
    )
    assert verified, "AUTO_DETECT_TRAILING_EDGES is verified nowhere; the trade moved"
    for canonical in verified:
        assert canonical in notice, (
            f"the notice does not name {canonical}, one of the builds a committed "
            "probe report covers for the command being replaced"
        )

    imported = registry.commands[WAKE_EDGE_IMPORT_COMMAND]
    assert not [row for row in imported.versions.values() if row.report], (
        "the wake-edge import now cites a probe report, so the notice's claim that "
        "no run has exercised it is false and this test is the thing that says so"
    )
    assert WakeEdgeImport(nodes=ONE_NODE).evidence_notice("26.123") == notice


# --- PFS-2025.16.02: the package writes the node file ------------------------

THREE_NODES = numpy.array([[0.0, 0.5, 0.25], [1.5, -0.5, 0.25], [-2.0, 0.125, -0.75]], dtype=float)


def test_the_node_file_carries_the_count_the_unit_and_one_row_per_node(tmp_path):
    """The layout is pinned here, so a later edit cannot change it quietly.

    The count, then the unit token, then one comma-separated row per node
    carrying an id and three coordinates. That is the layout the manual
    paraphrases for the node list a trailing-edge import reads
    (SRC-003 p.319), recorded in this repository's own words.
    """
    destination = tmp_path / "wake_edges.csv"
    written = write_node_file(destination, THREE_NODES, unit="METER")
    assert written == destination

    lines = destination.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "3"
    assert lines[1] == "METER"
    assert lines[2:] == [
        "1,0.0,0.5,0.25",
        "2,1.5,-0.5,0.25",
        "3,-2.0,0.125,-0.75",
    ]

    # Read back and compared node for node against what went in. This
    # checks the writer against ITS OWN output and nothing more: whether
    # the SOLVER accepts the file stays open until a probe report exists.
    parsed = numpy.array([[float(field) for field in line.split(",")[1:]] for line in lines[2:]])
    assert parsed == pytest.approx(THREE_NODES)


def test_an_empty_node_list_is_refused_because_it_marks_nothing(tmp_path):
    """A file with no rows is a marking pass that marks nothing."""
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(tmp_path / "empty.csv", numpy.zeros((0, 3)), unit="METER")
    assert "0 node" in str(raised.value)
    assert not (tmp_path / "empty.csv").exists(), "a refused write must leave no file"


@pytest.mark.parametrize(
    "wrong",
    [
        numpy.zeros((4, 2)),
        numpy.zeros((4,)),
        numpy.zeros((2, 3, 3)),
        numpy.zeros((3, 4)),
    ],
)
def test_an_array_that_is_not_n_by_three_is_refused_with_the_shape_it_had(wrong, tmp_path):
    """Three coordinates per node, and the shape it got is named."""
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(tmp_path / "wrong.csv", wrong, unit="METER")
    assert str(tuple(wrong.shape)) in str(raised.value)


def test_a_unit_outside_the_documented_set_is_refused_naming_the_unit_it_got(tmp_path):
    """The coordinates are read in the unit the FILE declares.

    That is what makes a wrong token expensive rather than cosmetic: the
    solver reads the file in the unit it names, not in the simulation's,
    so a token the solver does not know is a file whose coordinates have
    no scale.
    """
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(tmp_path / "unit.csv", THREE_NODES, unit="furlong")
    message = str(raised.value)
    assert "'furlong'" in message
    assert "METER" in message and "MILLIMETER" in message
    assert not (tmp_path / "unit.csv").exists()


def test_the_unit_vocabulary_comes_from_the_command_record_and_not_from_a_copy():
    """One vocabulary, one home, as the edge types already are."""
    entry = CommandRegistry.load().commands[LENGTH_UNIT_COMMAND]
    declared = next(arg for arg in entry.args if arg.name == "units")
    assert node_file_units() == tuple(declared.values)


def test_a_coordinate_that_is_not_a_finite_number_is_refused_with_its_row(tmp_path):
    """A NaN would be written as a word the solver reads as a coordinate."""
    nodes = THREE_NODES.copy()
    nodes[1, 2] = numpy.nan
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(tmp_path / "nan.csv", nodes, unit="METER")
    assert "row 2" in str(raised.value)
    assert not (tmp_path / "nan.csv").exists()


def test_an_existing_node_file_is_not_replaced_without_being_asked(tmp_path):
    """One path, one file, and the second write says so before it wins."""
    destination = tmp_path / "wake_edges.csv"
    write_node_file(destination, THREE_NODES, unit="METER")
    with pytest.raises(InputArtifactError, match="overwrite=True"):
        write_node_file(destination, THREE_NODES[:2], unit="METER")
    assert destination.read_text(encoding="utf-8").splitlines()[0] == "3"

    write_node_file(destination, THREE_NODES[:2], unit="METER", overwrite=True)
    assert destination.read_text(encoding="utf-8").splitlines()[0] == "2"


def test_a_plain_nested_sequence_is_accepted_as_well_as_an_array(tmp_path):
    """The caller's extraction need not already be a numpy array."""
    destination = tmp_path / "plain.csv"
    write_node_file(destination, [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]], unit="INCH")
    assert destination.read_text(encoding="utf-8").splitlines() == [
        "2",
        "INCH",
        "1,0.0,1.0,2.0",
        "2,3.0,4.0,5.0",
    ]


# --- PFS-2026.06: the relaxed trailing edge gains a direction, outside the
# --- script, and this package writes nothing that carries it ----------------
#
# The reading lands in this module's tests rather than in the command
# database's own because its subject is the trailing-edge and wake-edge
# marking family, which is what this module is about: the direction is a
# property of a relaxed trailing edge, and RELAXED is one of the four
# types both marking commands take.

RELAXED_TYPE_COMMAND = "SET_TRAILING_EDGE_TYPE"


def test_the_relaxed_trailing_edge_direction_is_recorded_where_it_belongs():
    """A 26.123 manual fact with no scripting command behind it.

    The newest edition gives the component-level relaxed trailing-edge
    specification a fifth field, an integer direction whose azimuth value
    is what a rotor case would want. It is not a scripting argument and
    this package writes no component file, so the only honest place for
    it is free text on the command a reader would go to first.
    """
    entry = CommandRegistry.load().commands[RELAXED_TYPE_COMMAND]
    notes = entry.notes or ""
    assert "SRC-751 p.85" in notes, (
        "the direction field the newest edition adds is recorded nowhere, so a rotor "
        "user meets the relaxed trailing edge and never learns the option exists"
    )
    for token in ("axial", "azimuth", "0", "1"):
        assert token in notes, f"the note does not state {token!r}"
    assert "SRC-750 p.85" in notes, (
        "the note does not say which edition printed the older form, so a reader "
        "cannot tell an addition from a fact that was always there"
    )


def test_the_direction_is_not_smuggled_in_as_a_scripting_argument():
    """Two arguments, on every registered build, and no third.

    This passes today and is pinned deliberately. The direction is a
    COMPONENT-FILE field: `script.helpers.parse_relaxed_trailing_edge`
    reads it and `cases.workflows.rotor_relaxed_trailing_edges` restates
    a rotor row's specifications in it, and none of that reaches a
    script, because no command on any registered build takes the
    direction. A later edit that added it as an argument would be
    inventing a grammar, which is what this guards.

    The docstring said something narrower until 2026-08-20, that the item
    asked for a parser and a refusal and there was nothing to parse. The
    second half was never true of the specification text and the first
    stopped being true when the restater landed; a guard whose stated
    premise is false is a guard a reader will delete for the wrong
    reason.
    """
    registry = CommandRegistry.load()
    entry = registry.commands[RELAXED_TYPE_COMMAND]
    for canonical in sorted(entry.versions):
        view = registry.for_version(canonical)
        if RELAXED_TYPE_COMMAND not in view:
            continue
        args = [arg.name for arg in view[RELAXED_TYPE_COMMAND].args]
        assert args == ["te_index", "type"], (
            f"{RELAXED_TYPE_COMMAND} declares {args} on {canonical}; the p.85 direction "
            "is a component-file field and never a scripting argument"
        )

    # And the citation is free text, never an evidence citation: p.85 is
    # outside the scripting reference every manual_ref and version note
    # must point into.
    assert "p.85" not in (entry.manual_ref or "")
    for canonical, row in entry.versions.items():
        assert "p.85" not in (row.note or ""), (
            f"the {canonical} version note cites p.85, which lies outside the "
            "registered scripting-reference range"
        )


@pytest.mark.parametrize(
    "unreadable",
    ["not an array", [[0.0, 1.0, 2.0], [3.0, 4.0]], [{"x": 1.0}]],
)
def test_something_that_is_not_coordinates_is_refused_in_this_catalogue(unreadable, tmp_path):
    """No bare ValueError out of a public name (FR-39).

    Found by the adversarial pass rather than by the plan: a string, a
    ragged list and a list of mappings all reached numpy and left its own
    ValueError on the way out, which is the one exception shape this
    repository refuses on an exported name.
    """
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(tmp_path / "unreadable.csv", unreadable, unit="METER")
    assert "array of coordinates" in str(raised.value)
    assert not (tmp_path / "unreadable.csv").exists()
