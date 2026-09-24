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
import re

import numpy
import pytest

from pyflightstream.commands import CommandRegistry
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz
from pyflightstream.workspace.wake_edges import (
    _METRES_PER_UNIT,
    DEFAULT_EDGE_TYPE,
    DEFAULT_TOLERANCE,
    LENGTH_UNIT_COMMAND,
    TRAILING_EDGE_DETECTION_COMMAND,
    WAKE_EDGE_IMPORT_COMMAND,
    WakeEdgeImport,
    check_trailing_edge_points,
    edge_types,
    evidence_notice,
    length_scale,
    node_file_units,
    read_trailing_edge_points,
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
    verified on no build: it was run once outside the compatibility
    harness, on 26.124 (RPT-061), which settled its grammar there and
    promoted nothing, while what it replaces carries committed probe
    reports on three builds. A later reader who meets only the default
    reads it as settled practice, which is what this sentence exists to
    prevent.

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

    later = evidence_notice("26.124")
    assert "RPT-061" in later and "verified on none" in later, (
        "the notice does not say that the 26.124 grammar rests on a run that promoted no status"
    )

    imported = registry.commands[WAKE_EDGE_IMPORT_COMMAND]
    assert not [row for row in imported.versions.values() if row.report], (
        "the wake-edge import now cites a probe report, so the notice's claim that "
        "no run has exercised it is false and this test is the thing that says so"
    )
    assert WakeEdgeImport(nodes=ONE_NODE).evidence_notice("26.123") == notice


# --- PFS-2025.16.02: the package writes the node file ------------------------

THREE_NODES = numpy.array([[0.0, 0.5, 0.25], [1.5, -0.5, 0.25], [-2.0, 0.125, -0.75]], dtype=float)


def test_the_node_file_is_the_count_a_placeholder_triple_and_the_midpoints_in_the_simulation_unit(
    tmp_path,
):
    """G02 (RPT-061). The layout is the one 26.124 reads, pinned here so a later
    edit cannot change it quietly: the count, one coordinate triple the solver
    consumes and does not use, then one bare ``x,y,z`` row per edge mid-point,
    CONVERTED to the simulation's length unit, because the file's own unit is not
    read. No line carries a letter: a word on any line makes the import mark
    nothing, and a unit line and id columns are exactly the layout that marked
    nothing when it was run.
    """
    destination = tmp_path / "n.txt"
    written = write_node_file(
        destination,
        [[1000.0, -3750.0, 0.0], [1000.0, -3250.0, 0.0]],
        unit="MILLIMETER",
        simulation_unit="METER",
    )
    assert written == destination
    lines = destination.read_text(encoding="utf-8").splitlines()
    assert lines == ["2", "0,0,0", "1.0,-3.75,0.0", "1.0,-3.25,0.0"]
    assert not [line for line in lines if re.search("[A-Za-z]", line)], lines


def test_a_coordinate_too_small_for_a_plain_decimal_is_still_written_without_a_letter(tmp_path):
    """A trailing-edge vertex of the committed wing sits at z = 1.665e-17, and the
    shortest round-trip form of that number carries an exponent letter. The writer
    spells every number as a plain decimal that reads back to the same float,
    because no layout with a letter in it has ever marked an edge."""
    tiny = 1.6653345369999999e-17
    destination = write_node_file(
        tmp_path / "tiny.txt", [[1.0, -3.75, tiny]], unit="METER", simulation_unit="METER"
    )
    lines = destination.read_text(encoding="utf-8").splitlines()
    assert not re.search("[A-Za-z]", lines[2]), lines[2]
    assert [float(value) for value in lines[2].split(",")] == [1.0, -3.75, tiny]


def test_every_recorded_length_unit_but_other_has_a_scale():
    """The conversion covers the solver's whole length-unit vocabulary, read from the
    command record, except OTHER, which names no scale and is refused."""
    assert set(node_file_units()) - {"OTHER"} == set(_METRES_PER_UNIT)
    assert length_scale("MILLIMETER", "METER") == 0.001
    assert length_scale("METER", "MILLIMETER") == 1000.0
    assert length_scale("INCH", "MILLIMETER") == 25.4
    assert length_scale("FEET", "FEET") == 1.0
    with pytest.raises(InputArtifactError, match="OTHER"):
        length_scale("OTHER", "METER")
    with pytest.raises(InputArtifactError, match="furlong"):
        length_scale("METER", "furlong")


def test_an_empty_node_list_is_refused_because_it_marks_nothing(tmp_path):
    """A file with no rows is a marking pass that marks nothing."""
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(
            tmp_path / "empty.csv", numpy.zeros((0, 3)), unit="METER", simulation_unit="METER"
        )
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
        write_node_file(tmp_path / "wrong.csv", wrong, unit="METER", simulation_unit="METER")
    assert str(tuple(wrong.shape)) in str(raised.value)


def test_a_unit_outside_the_documented_set_is_refused_naming_the_unit_it_got(tmp_path):
    """The coordinates are converted from the unit they are given in.

    That is what makes a wrong token expensive rather than cosmetic: the
    solver reads the file in the simulation's unit and never reads a unit
    from it, so a token with no scale leaves nothing to convert by.
    """
    with pytest.raises(InputArtifactError) as raised:
        write_node_file(tmp_path / "unit.csv", THREE_NODES, unit="furlong", simulation_unit="METER")
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
        write_node_file(tmp_path / "nan.csv", nodes, unit="METER", simulation_unit="METER")
    assert "row 2" in str(raised.value)
    assert not (tmp_path / "nan.csv").exists()


def test_an_existing_node_file_is_not_replaced_without_being_asked(tmp_path):
    """One path, one file, and the second write says so before it wins."""
    destination = tmp_path / "wake_edges.csv"
    write_node_file(destination, THREE_NODES, unit="METER", simulation_unit="METER")
    with pytest.raises(InputArtifactError, match="overwrite=True"):
        write_node_file(destination, THREE_NODES[:2], unit="METER", simulation_unit="METER")
    assert destination.read_text(encoding="utf-8").splitlines()[0] == "3"

    write_node_file(
        destination, THREE_NODES[:2], unit="METER", simulation_unit="METER", overwrite=True
    )
    assert destination.read_text(encoding="utf-8").splitlines()[0] == "2"


def test_a_plain_nested_sequence_is_accepted_as_well_as_an_array(tmp_path):
    """The caller's extraction need not already be a numpy array."""
    destination = tmp_path / "plain.csv"
    write_node_file(
        destination, [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]], unit="INCH", simulation_unit="INCH"
    )
    assert destination.read_text(encoding="utf-8").splitlines() == [
        "2",
        "0,0,0",
        "0.0,1.0,2.0",
        "3.0,4.0,5.0",
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
        write_node_file(
            tmp_path / "unreadable.csv", unreadable, unit="METER", simulation_unit="METER"
        )
    assert "array of coordinates" in str(raised.value)
    assert not (tmp_path / "unreadable.csv").exists()


# --- T05: the trailing-edge points file, checked against the mesh before the run ---
#
# The package-side points file a geometry names carries its unit on the first line
# and one edge mid-point per line after it. Before any seat is spent, every point
# must lie within the import's tolerance of a mesh-edge mid-point: the solver drops
# a point outside it in silence, and an edge's end vertex is such a point.


def _blade_points_file(tmp_path, *, unit="METER"):
    """The synthetic blade's mesh and the points file the extraction writes for it."""
    from pyflightstream.workspace import write_trailing_edge_node_file
    from tests.tier1_offline.test_trailing_edges import _blade_file

    mesh, _, trailing = _blade_file(tmp_path)
    points = write_trailing_edge_node_file(
        mesh, tmp_path / "blade.te.txt", axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), unit=unit
    )
    return mesh, points, trailing


def test_the_points_file_the_extraction_writes_passes_the_mesh_check(tmp_path):
    """T05. The file the extraction writes reads back as its unit and 24 points, and
    every point lies on a mesh-edge mid-point, so the check returns them, in the
    simulation's unit."""
    mesh, path, _ = _blade_points_file(tmp_path)
    read = read_trailing_edge_points(path)
    assert read.unit == "METER"
    assert read.points.shape == (24, 3)
    assert read.lines == tuple(range(2, 26))
    checked = check_trailing_edge_points(
        read.points,
        points_unit=read.unit,
        mesh=mesh,
        mesh_unit="METER",
        simulation_unit="METER",
        tolerance=1.0e-4,
        source=str(path),
        lines=read.lines,
    )
    assert checked.shape == (24, 3)
    assert numpy.allclose(checked, read.points, rtol=0.0, atol=0.0)


def test_a_point_moved_off_its_edge_midpoint_is_refused_by_its_line_and_position(tmp_path):
    """T05. Point 3 moved 0.2 mm along x, twice the tolerance: the first point that
    matches no edge is refused by its position, its file line, its coordinates as
    written and its distance, before the run."""
    mesh, path, _ = _blade_points_file(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    x, y, z = (float(value) for value in lines[3].split(","))
    lines[3] = f"{x + 2.0e-4!r},{y!r},{z!r}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    read = read_trailing_edge_points(path)
    with pytest.raises(InputArtifactError) as raised:
        check_trailing_edge_points(
            read.points,
            points_unit=read.unit,
            mesh=mesh,
            mesh_unit="METER",
            simulation_unit="METER",
            tolerance=1.0e-4,
            source=str(path),
            lines=read.lines,
        )
    message = str(raised.value)
    assert "point 3 of 24" in message and "line 4" in message, message
    assert lines[3] in message, message
    assert "0.0002" in message and "0.0001" in message, message


def test_an_end_vertex_in_place_of_a_midpoint_is_refused(tmp_path):
    """T05. A file of the trailing edge's end VERTICES is the layout that marks
    nothing, and each vertex lies half an edge from the nearest mid-point."""
    mesh, _, trailing = _blade_points_file(tmp_path)
    path = tmp_path / "vertices.te.txt"
    rows = [",".join(repr(float(value)) for value in point) for point in trailing]
    path.write_text("\n".join(["METER", *rows]) + "\n", encoding="utf-8")
    read = read_trailing_edge_points(path)
    with pytest.raises(InputArtifactError, match="point 1 of 25"):
        check_trailing_edge_points(
            read.points,
            points_unit=read.unit,
            mesh=mesh,
            mesh_unit="METER",
            simulation_unit="METER",
            tolerance=1.0e-4,
            source=str(path),
            lines=read.lines,
        )


def test_a_points_file_without_a_unit_line_is_refused(tmp_path):
    """T05. The first line names the unit, from the solver's length-unit vocabulary;
    a line of numbers there is a file with no unit, and OTHER names no scale."""
    path = tmp_path / "no_unit.te.txt"
    path.write_text("1.0,-3.75,0.0\n1.0,-3.25,0.0\n", encoding="utf-8")
    with pytest.raises(InputArtifactError) as raised:
        read_trailing_edge_points(path)
    message = str(raised.value)
    assert "unit line" in message and "METER" in message and "MILLIMETER" in message
    path.write_text("OTHER\n1.0,-3.75,0.0\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="OTHER"):
        read_trailing_edge_points(path)
    path.write_text("METER\n1.0,-3.75\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="line 2"):
        read_trailing_edge_points(path)
    path.write_text("METER\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="no point"):
        read_trailing_edge_points(path)


def test_a_points_file_in_millimetres_is_checked_and_converted(tmp_path):
    """T05. Points written in millimetres over a mesh in metres are compared in the
    simulation's unit and come back in it: the solver reads no unit from its file,
    so the conversion is the package's."""
    mesh, path, _ = _blade_points_file(tmp_path)
    metres = read_trailing_edge_points(path).points
    millimetres = tmp_path / "blade_mm.te.txt"
    rows = [",".join(repr(float(value) * 1000.0) for value in point) for point in metres]
    millimetres.write_text("\n".join(["MILLIMETER", *rows]) + "\n", encoding="utf-8")
    read = read_trailing_edge_points(millimetres)
    assert read.unit == "MILLIMETER"
    checked = check_trailing_edge_points(
        read.points,
        points_unit=read.unit,
        mesh=mesh,
        mesh_unit="METER",
        simulation_unit="METER",
        tolerance=1.0e-4,
        source=str(millimetres),
        lines=read.lines,
    )
    assert numpy.allclose(checked, metres, rtol=0.0, atol=1.0e-12)


def test_two_points_on_one_edge_are_refused_before_the_run(tmp_path):
    """T05. Two points nearest one mid-point mark one edge, so the solver would log
    fewer imported edges than points written and the run would be refused after the
    seat is spent; the check refuses it first, naming both points."""
    mesh, path, _ = _blade_points_file(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(3, lines[2])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    read = read_trailing_edge_points(path)
    with pytest.raises(InputArtifactError, match="points 2 and 3 of 25"):
        check_trailing_edge_points(
            read.points,
            points_unit=read.unit,
            mesh=mesh,
            mesh_unit="METER",
            simulation_unit="METER",
            tolerance=1.0e-4,
            source=str(path),
            lines=read.lines,
        )


def test_the_vertex_file_import_is_removed_on_26124_by_the_run_that_asked():
    """G02 (RPT-061). 26.124 answers TRAILING_EDGES_IMPORT as an unrecognized
    command, so its row is removed and the refusal cites the run and names the
    route that marks from a file there; 26.123, which no run asked, stays absent."""
    from pyflightstream.commands import CommandNotInVersionError

    registry = CommandRegistry.load()
    row = registry.commands["TRAILING_EDGES_IMPORT"].versions["26.124"]
    assert row.status.value == "removed"
    assert row.probe_ref and "RPT-061" in row.probe_ref
    with pytest.raises(CommandNotInVersionError) as refused:
        registry.for_version("26.124")["TRAILING_EDGES_IMPORT"]
    message = str(refused.value)
    assert "removed in FlightStream 26.124" in message
    assert "RPT-061" in message and "Use IMPORT_WAKE_EDGES_FROM_FILE instead" in message
    assert "26.123" not in registry.commands["TRAILING_EDGES_IMPORT"].versions
