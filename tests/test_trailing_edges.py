"""Tier 1: the trailing-edge extraction, and the reader it now arrives with.

PFS-2025.20, PFS-2025.20.02, PFS-2025.20.03 and PFS-2025.16, whose
decision half is the design note DD-27.

THE IMPORT OF ``trimesh`` AT THE TOP OF THIS FILE IS THE ACCEPTANCE
CLAUSE, not a convenience. PFS-2025.20.03 asks that a package installed
with NO extras can mark a trailing edge end to end, and the way that is
measured is that this module fails rather than skips when the reader is
absent. ``pytest.importorskip`` is what every OTHER optional-dependency
test in this suite uses and is exactly wrong here: it would turn the
promotion into a silent skip on the one CI leg built to measure it, and
a guard nothing executes is not weaker evidence than a red test, it is
none. That sentence is not this file's: it is the reason
``tests/test_extras_isolation.py`` and the ``test-all-extras`` CI leg
exist, and both were written after a release tag failed on exactly it.

WHAT THE MESH IS. A synthetic rotor blade, twisted from 90 degrees at
the root to 0 at the tip and swept through 60 degrees of azimuth, built
here rather than committed: invariant 5 keeps research geometry out of
this repository, and a blade whose trailing edge is known BY
CONSTRUCTION is what lets the assertions be about the criterion rather
than about a fixture. Both deformations are the point and they break
different things. The TWIST turns the chord out of the rotor plane, so
no one direction in space is the chordwise direction of two stations;
the SWEEP turns the radial direction itself, so no one direction is even
the SPANWISE direction of two stations.
``test_a_global_chord_direction_gets_this_blade_wrong`` measures that a
single global chord direction really does fail here, rather than
asserting it: the numbers are a deliberate worst case, because a
trailing edge is a sharp spike and a wrong direction still finds it
until the two chords are nearly square.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys

import numpy
import pytest
import trimesh

from pyflightstream.workspace import (
    TrailingEdge,
    extract_trailing_edge,
    write_trailing_edge_node_file,
)
from pyflightstream.workspace.inputs import InputArtifactError
from pyflightstream.workspace.trailing_edges import (
    DEFAULT_SECTIONS,
    MINIMUM_SECTION_VERTICES,
)

#: Chordwise stations of the aerofoil outline, leading edge to trailing
#: edge. Both ends are single points, so the section closes on a sharp
#: leading and a sharp trailing edge and each carries exactly one vertex
#: per spanwise station.
_CHORD_STATIONS = (0.0, 0.15, 0.35, 0.6, 0.8, 1.0)

#: Where the quarter chord sits on the axis of rotation's radius line.
_QUARTER = 0.25

#: Root and tip twist of the fixture, degrees, and the azimuth the tip
#: is swept to. Both matter and for different reasons: the TWIST turns
#: the chord out of the rotor plane, and the SWEEP turns the radial
#: direction itself, so no single direction in space is the chordwise
#: direction of more than one station.
#:
#: The 90 degrees at the root is a WORST CASE and is chosen rather than
#: typical: it is what puts the root chord nearly perpendicular to the
#: tip chord, and a trailing edge is such a sharp spike that a wrong
#: chordwise direction still finds it until the two are almost square.
#: `test_a_global_chord_direction_gets_this_blade_wrong` is what measures
#: that boundary, so lowering these numbers is a decision that shows up
#: as a red control rather than as a quietly weaker fixture.
_TWIST_ROOT_DEG = 90.0
_TWIST_TIP_DEG = 0.0
_SWEEP_DEG = 60.0


def _section_frame(fraction: float, root: float, tip: float):
    """Radius, chordwise and thickness directions of one spanwise station.

    The rotor axis is +z and the hub is the origin, so a station at
    azimuth psi sits on the radial direction ``(cos psi, sin psi, 0)``
    and its tangential direction, ``axis x radial``, is
    ``(-sin psi, cos psi, 0)``. The leading edge faces the tangential
    direction and the trailing edge is the aft one, against it, tilted
    out of the rotor plane by the local twist.
    """
    radius = root + (tip - root) * fraction
    azimuth = math.radians(_SWEEP_DEG * fraction)
    twist = math.radians(_TWIST_ROOT_DEG + (_TWIST_TIP_DEG - _TWIST_ROOT_DEG) * fraction)
    radial = numpy.array([math.cos(azimuth), math.sin(azimuth), 0.0])
    tangential = numpy.array([-math.sin(azimuth), math.cos(azimuth), 0.0])
    chordwise = -math.cos(twist) * tangential + math.sin(twist) * numpy.array([0.0, 0.0, 1.0])
    return radius, radial, chordwise, numpy.cross(radial, chordwise)


def _blade(
    stations: int = 25,
    root: float = 0.20,
    tip: float = 1.00,
    thickness: float = 0.12,
):
    """Build a twisted, swept blade about the +z rotor axis.

    Returns the vertex array, the face array, and the leading- and
    trailing-edge vertex coordinates that the criterion must find.
    """
    vertices: list[tuple[float, float, float]] = []
    leading: list[tuple[float, float, float]] = []
    trailing: list[tuple[float, float, float]] = []
    per_station = 2 * len(_CHORD_STATIONS) - 2
    for index in range(stations):
        fraction = index / (stations - 1)
        radius, radial, chordwise, normal = _section_frame(fraction, root, tip)
        chord = 0.30 - 0.10 * fraction
        base = radius * radial

        def _outline(
            station: float, side: float, base=base, chord=chord, chordwise=chordwise, normal=normal
        ):
            spine = base + (station - _QUARTER) * chord * chordwise
            half = 0.5 * thickness * chord * math.sin(math.pi * station)
            return tuple(spine + side * half * normal)

        loop = [_outline(_CHORD_STATIONS[0], 0.0)]
        loop += [_outline(station, +1.0) for station in _CHORD_STATIONS[1:-1]]
        loop.append(_outline(_CHORD_STATIONS[-1], 0.0))
        loop += [_outline(station, -1.0) for station in reversed(_CHORD_STATIONS[1:-1])]
        assert len(loop) == per_station
        leading.append(loop[0])
        trailing.append(loop[len(_CHORD_STATIONS) - 1])
        vertices.extend(loop)

    faces: list[tuple[int, int, int]] = []
    for index in range(stations - 1):
        here = index * per_station
        there = (index + 1) * per_station
        for position in range(per_station):
            following = (position + 1) % per_station
            faces.append((here + position, there + position, there + following))
            faces.append((here + position, there + following, here + following))
    return (
        numpy.asarray(vertices, dtype=float),
        numpy.asarray(faces, dtype=int),
        numpy.asarray(leading, dtype=float),
        numpy.asarray(trailing, dtype=float),
    )


def _blade_file(tmp_path, name: str = "blade.obj", **kwargs):
    """Export the synthetic blade to an .obj and return the path and the edges."""
    vertices, faces, leading, trailing = _blade(**kwargs)
    # process=False: the constructor otherwise merges and reorders
    # vertices, and the fixture's claim is about coordinates.
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    path = tmp_path / name
    mesh.export(path)
    return path, leading, trailing


def _matches(nodes, candidates, tolerance: float = 1.0e-9) -> list[bool]:
    """One flag per node: is it (numerically) one of the candidate points?"""
    return [
        bool((numpy.linalg.norm(candidates - node, axis=1) < tolerance).any()) for node in nodes
    ]


def _loose_mesh(vertices):
    """Wrap a bare vertex array as a mesh, with faces that only connect it.

    The refusal fixtures below are POINT CLOUDS: what each one measures is
    a property of the vertices (a whole annulus about the axis, a
    duplicated band, a section holding two of them), and the extraction
    reads vertices and nothing else. The faces exist because a mesh
    carries some, not because the criterion consults them, so they are a
    fan over consecutive indices rather than a surface anyone should read
    meaning into. ``process=False`` for the reason the blade builder
    gives: the constructor otherwise merges duplicate vertices, which
    would silently repair the very fixture that exists to carry them.
    """
    vertices = numpy.asarray(vertices, dtype=float)
    faces = numpy.asarray([(i, i + 1, i + 2) for i in range(len(vertices) - 2)], dtype=int)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


#: Spanwise stations of the ANCHOR blade, and the local twist at each, in
#: degrees. This fixture exists for one claim and is shaped around it: the
#: global aft sense is decided on the section whose chord is MOST nearly
#: tangential, and the docstring of `_orient` says that deciding it
#: elsewhere "is where a wrong answer flips one node of the edge and
#: nothing says so".
#:
#: The alignment of a section is its chord direction dotted with its own
#: tangential direction, which for this fixture is ``-cos(twist)``: it is
#: -1 where the chord lies in the rotor plane and 0 where the chord is
#: axial. The twists below put the ROOT just past 90 degrees, so its
#: alignment is small and POSITIVE, and the tip at 0, so its alignment is
#: 1 and NEGATIVE. Most-aligned and least-aligned therefore disagree
#: about the sign, and the whole node list follows whichever one is
#: consulted: the trailing edge from the tip, the LEADING edge from the
#: root.
#:
#: 92 rather than 90 is deliberate and is the fixture's other job. At
#: exactly 90 the root alignment is zero, the module refuses on the
#: tangential floor, and a wrong anchor would announce itself. At 92 the
#: root alignment is 0.035, comfortably above that floor, so a wrong
#: anchor is SILENT, which is the failure being measured rather than a
#: convenient one. `test_the_global_sign_is_decided_on_the_most_tangential_section`
#: asserts that property of these numbers before it uses them, so
#: changing them shows up as a red control rather than as a quietly
#: vacuous test.
#:
#: Neighbouring twists step by no more than 12 degrees, well under the
#: right angle at which the consistency walk in `_orient` would flip a
#: section against its neighbour. The sweep is zero here, unlike the
#: blade above: this fixture measures the SIGN decision, and a swept
#: fixture would put the answer at the mercy of the section binning too.
_ANCHOR_TWISTS_DEG = (92.0, 80.0, 60.0, 40.0, 20.0, 0.0)
_ANCHOR_RADII = (1.0, 1.2, 1.4, 1.6, 1.8, 2.0)


def _anchor_blade(chord: float = 0.30, thickness: float = 0.12):
    """Build the unswept blade whose root chord is just past axial.

    One station per entry of ``_ANCHOR_TWISTS_DEG``, all at azimuth zero
    about the +z rotor axis, each carrying the same aerofoil outline as
    the main fixture. The radii are equally spaced and the stations are
    far enough apart that cutting the span into ``len(_ANCHOR_RADII)``
    sections gives one station per section, which is what makes the
    alignment of section ``i`` the ``-cos`` of twist ``i``.

    Returns
    -------
    tuple
        The vertex array, the face array, and the leading- and
        trailing-edge vertex coordinates the criterion must find.
    """
    vertices: list[tuple[float, float, float]] = []
    leading: list[tuple[float, float, float]] = []
    trailing: list[tuple[float, float, float]] = []
    per_station = 2 * len(_CHORD_STATIONS) - 2
    radial = numpy.array([1.0, 0.0, 0.0])
    tangential = numpy.array([0.0, 1.0, 0.0])
    for radius, twist_deg in zip(_ANCHOR_RADII, _ANCHOR_TWISTS_DEG, strict=True):
        twist = math.radians(twist_deg)
        chordwise = -math.cos(twist) * tangential + math.sin(twist) * numpy.array([0.0, 0.0, 1.0])
        normal = numpy.cross(radial, chordwise)
        base = radius * radial

        def _outline(station: float, side: float, base=base, chordwise=chordwise, normal=normal):
            spine = base + (station - _QUARTER) * chord * chordwise
            half = 0.5 * thickness * chord * math.sin(math.pi * station)
            return tuple(spine + side * half * normal)

        loop = [_outline(_CHORD_STATIONS[0], 0.0)]
        loop += [_outline(station, +1.0) for station in _CHORD_STATIONS[1:-1]]
        loop.append(_outline(_CHORD_STATIONS[-1], 0.0))
        loop += [_outline(station, -1.0) for station in reversed(_CHORD_STATIONS[1:-1])]
        assert len(loop) == per_station
        leading.append(loop[0])
        trailing.append(loop[len(_CHORD_STATIONS) - 1])
        vertices.extend(loop)

    faces: list[tuple[int, int, int]] = []
    for index in range(len(_ANCHOR_RADII) - 1):
        here = index * per_station
        there = (index + 1) * per_station
        for position in range(per_station):
            following = (position + 1) % per_station
            faces.append((here + position, there + position, there + following))
            faces.append((here + position, there + following, here + following))
    return (
        numpy.asarray(vertices, dtype=float),
        numpy.asarray(faces, dtype=int),
        numpy.asarray(leading, dtype=float),
        numpy.asarray(trailing, dtype=float),
    )


def _axial_chord_blade(chord: float = 1.0, thickness: float = 0.12):
    """Build a blade whose chord is PARALLEL to the rotor axis everywhere.

    The same aerofoil outline as the other fixtures, but laid out with
    its chord along +z and its thickness along +y at every station, all
    at azimuth zero about the +z axis. Every section therefore has a
    chord direction exactly along the axis, whose component along the
    tangential direction ``axis x radial`` is zero, and there is no end
    of the chord that the rotor frame calls aft.

    It is a real surface with a real spanwise extent, not a degenerate
    one: each of the four stations carries the full outline, so every
    other refusal in the module is cleared before the tangential floor is
    reached. That is the point of it. A cloud that also had too few
    vertices per section, or no radial direction, would refuse earlier
    and measure the wrong guard.

    Returns
    -------
    tuple
        The vertex array and the face array.
    """
    vertices: list[tuple[float, float, float]] = []
    per_station = 2 * len(_CHORD_STATIONS) - 2
    for radius in (1.0, 1.2, 1.4, 1.6):

        def _outline(station: float, side: float, radius=radius):
            half = 0.5 * thickness * chord * math.sin(math.pi * station)
            return (radius, side * half, (station - _QUARTER) * chord)

        loop = [_outline(_CHORD_STATIONS[0], 0.0)]
        loop += [_outline(station, +1.0) for station in _CHORD_STATIONS[1:-1]]
        loop.append(_outline(_CHORD_STATIONS[-1], 0.0))
        loop += [_outline(station, -1.0) for station in reversed(_CHORD_STATIONS[1:-1])]
        assert len(loop) == per_station
        vertices.extend(loop)

    faces: list[tuple[int, int, int]] = []
    for index in range(3):
        here = index * per_station
        there = (index + 1) * per_station
        for position in range(per_station):
            following = (position + 1) % per_station
            faces.append((here + position, there + position, there + following))
            faces.append((here + position, there + following, here + following))
    return numpy.asarray(vertices, dtype=float), numpy.asarray(faces, dtype=int)


# --- the acceptance clauses -------------------------------------------------


def test_the_reader_arrives_with_the_package_alone():
    """PFS-2025.20.02: trimesh is a RUNTIME dependency, in no extra.

    Both halves, because either alone is satisfiable by a wrong change:
    a dependency line that stayed in `[geom]` would pass the first, and
    a reader named in both places would pass the second.
    """
    import tomllib
    from pathlib import Path

    from pyflightstream.extras import EXTRAS

    repo = Path(__file__).resolve().parents[1]
    with open(repo / "pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)["project"]
    runtime = {
        spec.split(">")[0].split("<")[0].split("=")[0].strip(): spec
        for spec in project["dependencies"]
    }
    assert "trimesh" in runtime, (
        "trimesh is not a runtime dependency, so a base install cannot read a mesh "
        f"and PFS-2025.20.03 is unmeetable. The runtime set is {sorted(runtime)}"
    )
    for extra, packages in EXTRAS.items():
        assert "trimesh" not in {name.lower() for name in packages}, (
            f"the extras table still lists trimesh under [{extra}]. A refusal built "
            "from that entry would tell a reader to install an extra to obtain a "
            "distribution the base install already gave them"
        )


def test_the_dependency_envelope_records_the_tested_range_at_both_ends():
    """PFS-2025.20.02: both ends, and the installed reader inside them.

    A floor alone lets an untested major arrive silently; a ceiling alone
    says nothing about how far back the package was exercised. And a
    range nothing is measured against is a hope, so the version this
    suite actually runs on is held inside it.
    """
    import tomllib
    from pathlib import Path

    from packaging.requirements import Requirement
    from packaging.version import Version

    repo = Path(__file__).resolve().parents[1]
    with open(repo / "pyproject.toml", "rb") as handle:
        runtime = tomllib.load(handle)["project"]["dependencies"]
    declared = [Requirement(spec) for spec in runtime]
    reader = next((item for item in declared if item.name.lower() == "trimesh"), None)
    assert reader is not None, "no runtime requirement names trimesh"

    operators = {clause.operator for clause in reader.specifier}
    assert {">=", "<"} <= operators, (
        f"the trimesh requirement is {str(reader)!r} and records "
        f"{sorted(operators)}. The envelope states the tested range at BOTH ends: a "
        "floor for the oldest release this package was exercised against, and a "
        "ceiling that keeps the next major out until there is evidence about it"
    )
    assert reader.specifier.contains(Version(trimesh.__version__)), (
        f"the installed trimesh {trimesh.__version__} is outside the declared "
        f"{str(reader.specifier)!r}, so the range is not the range anything was "
        "tested against"
    )


def test_the_extraction_runs_with_no_optional_extra_installed(tmp_path):
    """PFS-2025.20.03, measured on EVERY leg rather than only the lean one.

    The lean CI job installs no user-facing extra and runs this file, and
    that job is the acceptance clause's own home. It is also invisible to
    a maintainer until CI answers, so the same claim is measured here in
    a CHILD interpreter whose import system refuses every distribution
    any extra installs. A blocker inside this process would prove
    nothing: trimesh imports scipy at its own import time, so by the time
    a test runs the module is already in `sys.modules` and a later block
    cannot be reached.
    """
    path, _, trailing = _blade_file(tmp_path)
    script = tmp_path / "lean_extraction.py"
    script.write_text(
        "import sys\n"
        "\n"
        "BLOCKED = {'scipy', 'rtree', 'Pynite', 'PyNiteFEA', 'pypdf', 'matplotlib'}\n"
        "\n"
        "\n"
        "class Blocker:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname.split('.')[0] in BLOCKED:\n"
        "            raise ModuleNotFoundError('blocked for the lean measurement: '\n"
        "                                      + fullname, name=fullname)\n"
        "        return None\n"
        "\n"
        "\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "from pyflightstream.workspace import write_trailing_edge_node_file\n"
        "\n"
        "written = write_trailing_edge_node_file(\n"
        "    sys.argv[1], sys.argv[2], axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0),\n"
        "    unit='METER', sections=6,\n"
        ")\n"
        "print(written)\n",
        encoding="utf-8",
    )
    written = tmp_path / "lean_wake_edges.csv"
    completed = subprocess.run(
        [sys.executable, str(script), str(path), str(written)],
        capture_output=True,
        text=True,
        check=False,
        # Explicit, and identical to the inherited default. The child has
        # to find the installed package, so it inherits; the kit's spawn
        # rule is that the inheritance is a DECISION at the call site,
        # and tests/test_kit_checkers.py ratchets the count of spawns
        # that do not make it.
        env=os.environ.copy(),
    )
    assert completed.returncode == 0, (
        "the trailing-edge extraction could not run with every extra's "
        f"distributions blocked, so it is not on the base install path:\n"
        f"{completed.stdout}\n{completed.stderr}"
    )
    rows = written.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "6"
    assert rows[1] == "METER"
    nodes = numpy.asarray(
        [[float(field) for field in row.split(",")[1:]] for row in rows[2:]], dtype=float
    )
    assert all(_matches(nodes, trailing, tolerance=1.0e-6)), (
        "the lean child extracted nodes that are not trailing-edge vertices"
    )


def test_the_extracted_nodes_are_the_trailing_edge_of_a_twisted_blade(tmp_path):
    """The criterion, on the blade whose trailing edge is known."""
    path, _, trailing = _blade_file(tmp_path)
    edge = extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=8)
    assert isinstance(edge, TrailingEdge)
    assert edge.nodes.shape == (8, 3)
    found = _matches(edge.nodes, trailing, tolerance=1.0e-6)
    assert all(found), (
        f"{found.count(False)} of the 8 extracted nodes are not trailing-edge "
        f"vertices of the blade:\n{edge.nodes}"
    )
    assert numpy.all(numpy.diff(edge.span) > 0.0), (
        f"the nodes are not ordered by increasing span: {edge.span}"
    )
    assert numpy.isclose(numpy.linalg.norm(edge.axis), 1.0)


def test_a_global_chord_direction_gets_this_blade_wrong(tmp_path):
    """The control that earns the per-section chord direction.

    DD-27 rests on the claim that taking the chordwise direction from a
    GLOBAL axis fails on a twisted blade. Asserted as a measurement
    rather than as prose: the same sectioning, scored against the tip's
    own chord direction everywhere, picks vertices that are not on the
    trailing edge. Without this the per-section machinery could be
    replaced by a constant and every other test here would stay green.
    """
    path, _, trailing = _blade_file(tmp_path)
    mesh = trimesh.load_mesh(str(path))
    vertices = numpy.asarray(mesh.vertices, dtype=float)
    span = numpy.linalg.norm(vertices[:, :2], axis=1)
    edges = numpy.linspace(span.min(), span.max(), 9)
    membership = numpy.clip(numpy.searchsorted(edges, span, side="right") - 1, 0, 7)

    # The TIP section's own chord direction, used as a global one. This
    # is the most favourable global direction available, because it is a
    # real chord direction of this blade rather than an invented axis.
    _, _, global_chord, _ = _section_frame(1.0, 0.20, 1.00)
    picked = numpy.asarray(
        [
            vertices[numpy.flatnonzero(membership == index)][
                int(numpy.argmax(vertices[numpy.flatnonzero(membership == index)] @ global_chord))
            ]
            for index in range(8)
        ]
    )
    wrong = _matches(picked, trailing, tolerance=1.0e-6).count(False)
    assert wrong > 0, (
        "a single global chord direction found the trailing edge of this blade at "
        "every section, so the fixture is not twisted enough to demonstrate why the "
        "chordwise direction is taken from each section's own extent. Increase the "
        "root twist rather than deleting this control"
    )


def test_reversing_the_axis_reverses_which_end_of_the_chord_is_aft(tmp_path):
    """The aft sense is the rotor frame's, and the axis carries it.

    The module documents that the rotor is taken to turn the right-handed
    way about ``axis``, so a rotor turning the other way is described by
    passing the axis reversed. That is a claim about behaviour: reversed,
    the same mesh must yield the LEADING edge, which is the other end of
    the same chord. If the sign were resolved by anything but the axis,
    this would return the same nodes twice.
    """
    path, leading, trailing = _blade_file(tmp_path)
    forward = extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=8)
    reversed_ = extract_trailing_edge(path, axis=(0.0, 0.0, -1.0), hub=(0.0, 0.0, 0.0), sections=8)
    assert all(_matches(forward.nodes, trailing, tolerance=1.0e-6))
    assert all(_matches(reversed_.nodes, leading, tolerance=1.0e-6)), (
        f"reversing the axis did not move the answer to the leading edge:\n{reversed_.nodes}"
    )


def test_the_global_sign_is_decided_on_the_most_tangential_section(tmp_path):
    """`_orient` anchors on argmax of |alignment|, and argmin is not the same.

    DENIES the mutant ``anchor = int(numpy.argmin(numpy.abs(alignments)))``
    in ``_orient``, which survived every other case in this file.

    The docstring of ``_orient`` makes a design claim: the one remaining
    global sign is settled on the section whose chord is most nearly
    TANGENTIAL, "where the answer is least ambiguous", and settling it on
    a strongly twisted root section instead "is where a wrong answer
    flips one node of the edge and nothing says so". Every other fixture
    here has all sections agreeing about the sign, so which section
    answers is unobservable and the claim is untested.

    This blade makes the two answers disagree. Its root chord is just
    past axial (92 degrees of twist) so its alignment is small and
    positive; its tip chord lies in the rotor plane so its alignment is
    -1. Anchoring on the most aligned section keeps the family pointing
    aft; anchoring on the least aligned one flips all six chords and
    returns the LEADING edge, silently and with no refusal, which is
    exactly the failure the design note claims to have removed. Both
    halves are asserted, because "these are trailing-edge vertices" alone
    would also pass on a blade whose two ends happen to coincide.
    """
    # The fixture's own property, asserted before it is relied on: the
    # most- and least-aligned sections must disagree about the SIGN, and
    # the least aligned must still clear the tangential floor, so a wrong
    # anchor gives a wrong answer rather than a refusal.
    alignments = [-math.cos(math.radians(twist)) for twist in _ANCHOR_TWISTS_DEG]
    most = int(numpy.argmax(numpy.abs(alignments)))
    least = int(numpy.argmin(numpy.abs(alignments)))
    assert alignments[most] < 0.0 < alignments[least], (
        "the most- and least-aligned sections of this fixture agree about the sign, "
        f"so the anchor is unobservable again: {alignments}"
    )
    assert abs(alignments[least]) > 1.0e-3, (
        "the least-aligned section is below the module's tangential floor, so a "
        "wrong anchor would REFUSE rather than answer, and this case would stop "
        f"measuring a silent failure: {alignments}"
    )

    vertices, faces, leading, trailing = _anchor_blade()
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    path = tmp_path / "anchor.obj"
    mesh.export(path)
    edge = extract_trailing_edge(
        path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=len(_ANCHOR_RADII)
    )
    assert edge.nodes.shape == (len(_ANCHOR_RADII), 3), (
        "the span was not cut one station per section, so the alignment of section i "
        f"is no longer the -cos of twist i and the control above is about nothing: "
        f"{edge.nodes.shape}"
    )
    found = _matches(edge.nodes, trailing, tolerance=1.0e-6)
    assert all(found), (
        f"{found.count(False)} of {len(_ANCHOR_RADII)} nodes are not trailing-edge "
        f"vertices, so the global sign was taken from the wrong section:\n{edge.nodes}"
    )
    wrong = _matches(edge.nodes, leading, tolerance=1.0e-6)
    assert not any(wrong), (
        f"{wrong.count(True)} of the extracted nodes are LEADING-edge vertices of "
        f"this blade:\n{edge.nodes}"
    )


def test_the_documented_default_and_minimum_are_the_documented_numbers(tmp_path):
    """DENIES ``DEFAULT_SECTIONS = 7`` and ``MINIMUM_SECTION_VERTICES = 1``.

    Both are public names with a paragraph of reasoning behind them, and
    both were free to change without a test noticing. The default is
    pinned twice over, as the constant AND as the number of nodes a call
    that does not ask for a count comes back with, because the constant
    alone would not catch a signature that stopped defaulting to it.
    """
    assert DEFAULT_SECTIONS == 20
    assert MINIMUM_SECTION_VERTICES == 3
    path, _, trailing = _blade_file(tmp_path)
    edge = extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0))
    assert edge.nodes.shape == (DEFAULT_SECTIONS, 3)
    assert edge.sections == DEFAULT_SECTIONS
    assert all(_matches(edge.nodes, trailing, tolerance=1.0e-6))


def test_a_loaded_mesh_and_its_file_give_the_same_edge(tmp_path):
    """The reader is a convenience of the entry point, not of the criterion."""
    path, _, _ = _blade_file(tmp_path)
    from_path = extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=6)
    from_mesh = extract_trailing_edge(
        trimesh.load_mesh(str(path)), axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=6
    )
    assert numpy.allclose(from_path.nodes, from_mesh.nodes)


# --- the named import route, PFS-2025.16 ------------------------------------


def test_the_edge_is_written_as_the_node_list_a_wake_edge_import_reads(tmp_path):
    """PFS-2025.16: the extraction feeds `wake_edges.write_node_file`."""
    path, _, trailing = _blade_file(tmp_path)
    written = write_trailing_edge_node_file(
        path,
        tmp_path / "wake_edges.csv",
        axis=(0.0, 0.0, 1.0),
        hub=(0.0, 0.0, 0.0),
        unit="METER",
        sections=8,
    )
    rows = written.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "8", "the node count line does not carry the node count"
    assert rows[1] == "METER", "the file does not declare the unit the solver reads it in"
    assert len(rows) == 10
    identifiers = [int(row.split(",")[0]) for row in rows[2:]]
    assert identifiers == list(range(1, 9))
    nodes = numpy.asarray(
        [[float(field) for field in row.split(",")[1:]] for row in rows[2:]], dtype=float
    )
    assert all(_matches(nodes, trailing, tolerance=1.0e-6))


def test_the_route_refuses_a_unit_the_command_database_does_not_record(tmp_path):
    """The writer's refusals reach through the route unchanged."""
    path, _, _ = _blade_file(tmp_path)
    with pytest.raises(InputArtifactError, match="does not record"):
        write_trailing_edge_node_file(
            path,
            tmp_path / "wake_edges.csv",
            axis=(0.0, 0.0, 1.0),
            hub=(0.0, 0.0, 0.0),
            unit="MILES",
            sections=4,
        )
    assert not (tmp_path / "wake_edges.csv").exists(), "a refused write left a file behind"


def test_a_refused_extraction_writes_no_file(tmp_path):
    """The extraction runs before the writer, so a refusal costs nothing."""
    path, _, _ = _blade_file(tmp_path)
    destination = tmp_path / "wake_edges.csv"
    with pytest.raises(InputArtifactError):
        write_trailing_edge_node_file(
            path, destination, axis=(0.0, 0.0, 1.0), hub=None, unit="METER"
        )
    assert not destination.exists()


# --- the refusals -----------------------------------------------------------


@pytest.mark.parametrize(
    ("axis", "hub"),
    [(None, None), (None, (0.0, 0.0, 0.0)), ((0.0, 0.0, 1.0), None)],
)
def test_no_axis_and_no_hub_refuses_naming_both(tmp_path, axis, hub):
    """DD-27: it refuses rather than guessing a global axis, and says so."""
    path, _, _ = _blade_file(tmp_path)
    with pytest.raises(InputArtifactError) as caught:
        extract_trailing_edge(path, axis=axis, hub=hub)
    message = str(caught.value)
    assert "axis" in message and "hub" in message, message
    assert "guess" in message, (
        "the refusal does not say that nothing is guessed, which is the whole "
        f"reason it is a refusal: {message}"
    )
    assert caught.value.kind == "trailing_edges"


def test_a_zero_axis_names_no_direction_and_is_refused(tmp_path):
    path, _, _ = _blade_file(tmp_path)
    with pytest.raises(InputArtifactError, match="zero vector"):
        extract_trailing_edge(path, axis=(0.0, 0.0, 0.0), hub=(0.0, 0.0, 0.0))


@pytest.mark.parametrize("axis", [(0.0, 1.0), (1.0, 0.0, 0.0, 0.0), (float("nan"), 0.0, 1.0)])
def test_an_axis_that_is_not_three_finite_numbers_is_refused(tmp_path, axis):
    path, _, _ = _blade_file(tmp_path)
    with pytest.raises(InputArtifactError):
        extract_trailing_edge(path, axis=axis, hub=(0.0, 0.0, 0.0))


@pytest.mark.parametrize("sections", [1, 0, -3, 2.5, True])
def test_fewer_than_two_sections_name_no_edge_and_are_refused(tmp_path, sections):
    """One node is a point, and a point names no edge."""
    path, _, _ = _blade_file(tmp_path)
    with pytest.raises(InputArtifactError, match="names no edge|no sectioning"):
        extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=sections)


def test_sections_finer_than_the_mesh_resolves_are_refused(tmp_path):
    """A silent answer here would be a node list shorter than it claims.

    WHAT THIS CASE ACTUALLY REACHES, measured rather than assumed on
    2026-08-20: 200 sections over a 6-station blade leaves 182 of them
    holding NOTHING, and the first section that refuses holds zero
    vertices. So it exercises the EMPTY section and says nothing about
    the threshold: it passes unchanged with ``MINIMUM_SECTION_VERTICES``
    lowered to one. The 1-or-2-vertex case that the constant's own
    docstring exists to justify is
    `test_a_section_holding_two_vertices_is_too_few_to_read_a_chord_from`
    below; this one is kept because a coarse mesh asked for far too many
    sections is the way a user really arrives here, and both shapes are
    worth having.
    """
    path, _, _ = _blade_file(tmp_path, stations=6)
    with pytest.raises(InputArtifactError, match="finer than the mesh"):
        extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=200)


def test_a_section_holding_two_vertices_is_too_few_to_read_a_chord_from():
    """DENIES ``selected.size < 1`` and ``MINIMUM_SECTION_VERTICES = 1``.

    Two points define a line but not a section, which is the whole
    argument for the constant being three, and nothing measured it: the
    only case that reached this refusal did so with sections holding
    ZERO vertices, where any threshold at all refuses.

    The cloud below is built so that the inboard section holds exactly
    two vertices and the outboard one holds three. With the threshold at
    three the extraction refuses and names the count; with it at one, the
    two-vertex section has enough extent to yield a chord direction and
    the call SUCCEEDS, returning a two-node edge read off a section that
    cannot disagree with itself. The refusal's own text is matched,
    including the number, so lowering the constant is a red test rather
    than a quieter message.
    """
    cloud = [
        (1.0, -0.1, 0.0),
        (1.0, 0.1, 0.0),
        (2.0, -0.1, 0.0),
        (2.0, 0.0, 0.0),
        (2.0, 0.1, 0.0),
    ]
    with pytest.raises(InputArtifactError, match="holds 2 vertices") as caught:
        extract_trailing_edge(
            _loose_mesh(cloud), axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=2
        )
    assert "needs at least 3" in str(caught.value), (
        "the refusal no longer names three as the number a section needs, which is "
        f"the claim MINIMUM_SECTION_VERTICES makes: {caught.value}"
    )
    assert caught.value.kind == "trailing_edges"


def test_a_full_annulus_about_the_axis_has_no_radial_direction_and_is_refused():
    """DENIES ``if False:`` in place of the ``length == 0.0`` refusal.

    A section whose vertices sit evenly all the way round the axis has a
    mean radial vector of exactly zero, so it has no radial direction of
    its own and no tangential direction either. That is a full disc or a
    complete rotor rather than one blade, and the module says so.

    Nothing reached it. With the refusal removed the mean radial is
    divided by zero, the chord direction is computed from a NaN radial,
    and the call ends in ``numpy.linalg.LinAlgError: Eigenvalues did not
    converge`` out of a public function of this package (measured
    2026-08-20, with the refusal replaced by ``if False:``): a bare
    third-party error naming neither the mesh nor the cause, which is
    exactly the shape FR-39 forbids.
    """
    rings = []
    for radius in (1.0, 2.0):
        rings += [
            (radius, 0.0, 0.0),
            (0.0, radius, 0.0),
            (-radius, 0.0, 0.0),
            (0.0, -radius, 0.0),
        ]
    with pytest.raises(InputArtifactError, match="spread evenly around the rotor axis") as caught:
        extract_trailing_edge(
            _loose_mesh(rings), axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=2
        )
    assert "one blade at a time" in str(caught.value), (
        f"the refusal no longer says what to do about it: {caught.value}"
    )
    assert caught.value.kind == "trailing_edges"


def test_a_duplicated_vertex_band_has_no_chord_direction_and_is_refused():
    """DENIES ``if False:`` in place of the ``chord is None`` refusal.

    A band of vertices at one point is what a degenerate or duplicated
    spanwise station looks like in a mesh, and once the spanwise
    component is projected out the section has no extent left to read a
    chord direction from. `_chord_direction` returns None for it, and
    only the refusal turns that None into a sentence.

    Nothing reached it. With the refusal removed the None is carried into
    `_orient` and matrix-multiplied by a real chord, and the user is told
    ``matmul: Input operand 1 does not have enough dimensions`` (measured
    2026-08-20, with the refusal replaced by ``if False:``): a bare
    ValueError about operand dimensions, naming neither the mesh nor the
    cause, which is the shape FR-39 forbids. ``process=False`` in
    `_loose_mesh` is load-bearing here: the mesh constructor would
    otherwise merge the duplicated band away.
    """
    cloud = [
        (1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (2.0, -0.1, 0.0),
        (2.0, 0.0, 0.1),
        (2.0, 0.1, 0.0),
    ]
    with pytest.raises(InputArtifactError, match="all its vertices at one point") as caught:
        extract_trailing_edge(
            _loose_mesh(cloud), axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=2
        )
    assert "duplicated band of vertices" in str(caught.value), (
        f"the refusal no longer names the usual cause: {caught.value}"
    )
    assert caught.value.kind == "trailing_edges"


def test_a_chord_parallel_to_the_axis_at_every_station_is_refused(tmp_path):
    """DENIES ``if False:`` in place of the tangential-alignment floor.

    THE FLOOR IS THE ONLY THING BETWEEN A REVERSED EDGE AND A WRITTEN
    NODE FILE. Aft is the end of the chord AGAINST ``axis x radial``, so
    a blade whose chord is parallel to the axis at every station gives
    that product nothing to read: the two ends of every chord are
    equally aft and the sign of the answer is whatever the eigen solver
    happened to hand back. With the floor removed the extraction returns
    a node list anyway, and half the time it is the LEADING edge, with
    nothing said.

    The fixture is a genuine surface with four stations, a real chord and
    a real thickness, so every earlier refusal in the module is cleared
    and the floor is the guard actually under test. Both the extraction
    and the whole write route are exercised, because the route is where a
    silently reversed edge would reach a file.
    """
    vertices, faces = _axial_chord_blade()
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    with pytest.raises(InputArtifactError, match="readable component along") as caught:
        extract_trailing_edge(mesh, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=2)
    message = str(caught.value)
    assert "aft" in message and "axis x radial" in message, (
        f"the refusal no longer names where the aft sense comes from: {message}"
    )
    assert caught.value.kind == "trailing_edges"

    path = tmp_path / "axial.obj"
    mesh.export(path)
    destination = tmp_path / "wake_edges.csv"
    with pytest.raises(InputArtifactError, match="readable component along"):
        write_trailing_edge_node_file(
            path,
            destination,
            axis=(0.0, 0.0, 1.0),
            hub=(0.0, 0.0, 0.0),
            unit="METER",
            sections=2,
        )
    assert not destination.exists(), (
        "an edge whose aft sense could not be read was written to a node file anyway"
    )


def test_a_mesh_with_no_spanwise_extent_about_the_axis_is_refused(tmp_path):
    """The blade lying ALONG the axis: every vertex at one radius."""
    path, _, _ = _blade_file(tmp_path)
    # The rotor axis taken along +x, which is the blade's own span
    # direction, so every vertex collapses to nearly one radius. The hub
    # is put on that line so the collapse is exact for the spine.
    ring = numpy.array([[0.0, 0.5, 0.0], [0.0, 0.0, 0.5], [0.0, -0.5, 0.0], [0.0, 0.0, -0.5]])
    flat = trimesh.Trimesh(vertices=ring, faces=numpy.array([[0, 1, 2], [0, 2, 3]]), process=False)
    with pytest.raises(InputArtifactError, match="no spanwise extent"):
        extract_trailing_edge(flat, axis=(1.0, 0.0, 0.0), hub=(0.0, 0.0, 0.0), sections=4)


def test_the_answer_does_not_depend_on_where_the_blade_sits_in_space(tmp_path):
    """The criterion is stated in the rotor frame, so it must ride with it.

    Every other test here puts the rotor axis on +z and the hub at the
    origin, which is the one arrangement in which a bug that quietly
    reads a GLOBAL axis is invisible. This one rotates the whole blade
    through an arbitrary angle about an arbitrary axis and moves it off
    the origin, then asks the same question in the moved frame: the
    answer must be the same vertices, moved.
    """
    vertices, faces, _, trailing = _blade()
    direction = numpy.array([1.0, 2.0, 3.0])
    direction = direction / numpy.linalg.norm(direction)
    angle = math.radians(90.0)
    cross = numpy.array(
        [
            [0.0, -direction[2], direction[1]],
            [direction[2], 0.0, -direction[0]],
            [-direction[1], direction[0], 0.0],
        ]
    )
    rotation = (
        math.cos(angle) * numpy.eye(3)
        + math.sin(angle) * cross
        + (1.0 - math.cos(angle)) * numpy.outer(direction, direction)
    )
    shift = numpy.array([5.0, -3.0, 2.0])

    moved = trimesh.Trimesh(vertices=vertices @ rotation.T + shift, faces=faces, process=False)
    path = tmp_path / "moved.obj"
    moved.export(path)
    edge = extract_trailing_edge(
        path, axis=rotation @ numpy.array([0.0, 0.0, 1.0]), hub=shift, sections=8
    )
    expected = trailing @ rotation.T + shift
    found = _matches(edge.nodes, expected, tolerance=1.0e-6)
    assert all(found), (
        f"{found.count(False)} of 8 nodes moved with the blade and the criterion did "
        f"not follow, so something is reading a global direction:\n{edge.nodes}"
    )
    # And the record says which frame it used, which is the sharper half
    # of the same question. Measured while writing this: the criterion is
    # forgiving of a WRONG axis, because a trailing edge is a spike and
    # stays the extreme point of an obliquely cut section. An axis 37
    # degrees off still returned the right eight nodes and 90 degrees
    # misses only one, so the coordinates alone are a blunt instrument
    # for "is the GIVEN axis the one being used". The robustness is a
    # property of the criterion rather than a hole; the recorded axis is
    # asserted beside the coordinates so the question has a sharp answer.
    assert numpy.allclose(edge.axis, rotation @ numpy.array([0.0, 0.0, 1.0]))
    assert numpy.allclose(edge.hub, shift)


@pytest.mark.parametrize("name", ["absent.obj", "prose.txt"])
def test_a_mesh_file_the_reader_refuses_is_refused_in_this_package_voice(tmp_path, name):
    """FR-39: no public name of this package raises a bare stdlib error.

    The reader answers a path that is not a file with a bare
    ``ValueError`` and a suffix it has no loader for with a bare
    ``NotImplementedError``, and both would come straight out of a
    public function here. Found by the adversarial pass rather than by a
    review of the happy path.
    """
    path = tmp_path / name
    if name.endswith(".txt"):
        path.write_text("this is not a mesh\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="could not be read"):
        extract_trailing_edge(path, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0))


def test_a_mesh_with_no_vertices_at_all_is_refused():
    """A public name refuses in this package's own vocabulary, never bare."""

    class NotAMesh:
        pass

    with pytest.raises(InputArtifactError, match="carries no vertices"):
        extract_trailing_edge(NotAMesh(), axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0))


def test_a_vertex_that_is_not_a_finite_number_is_refused():
    vertices = numpy.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, float("nan"), 0.0]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=numpy.array([[0, 1, 2]]), process=False)
    with pytest.raises(InputArtifactError, match="not a finite number"):
        extract_trailing_edge(mesh, axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0), sections=2)
