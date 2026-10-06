"""Tier 1, 0.38.0 S5: a body refined along and around its axis (FR-428).

Every fixture is built here: an open cylinder of near-equilateral triangles
(each ring of nodes turned half a step from the one before), written as an
OBJ with its refinement file beside it, and refined through
:func:`pyflightstream.workspace.refine_mesh`. R1 is measured on the level's
OBJ against the source's, never on the remesher's own bookkeeping, and each
measurement is run once on a level it must reject, so a check that accepts
everything cannot pass.
"""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest
import trimesh

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._geometry import (
    AXIAL_BAND,
    Stretch,
    boundary_edges,
    edge_faces,
)
from pyflightstream.workspace._refine._obj import ObjMesh, read_obj, write_obj
from pyflightstream.workspace._refine._remesh import Patch, Remesher, refine_group

AXIS = numpy.array([0.0, 0.0, 1.0])

# ---- fixtures


def _cylinder(n: int = 24, length: float = 3.0) -> tuple[numpy.ndarray, list[list[int]]]:
    """Return the nodes and triangles of an open unit cylinder about z, near-equilateral."""
    h = 2.0 * numpy.pi / n
    rings = round(length / (h * numpy.sqrt(3.0) / 2.0))
    nodes = []
    for i in range(rings + 1):
        for j in range(n):
            t = h * (j + 0.5 * (i % 2))
            nodes.append([numpy.cos(t), numpy.sin(t), i * length / rings])
    faces = []
    for i in range(rings):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c, d = a + n, (i + 1) * n + (j + 1) % n
            faces += [[a, b, c], [b, d, c]] if i % 2 == 0 else [[a, d, c], [a, b, d]]
    return numpy.array(nodes), faces


def _source(folder: Path, refine: str, *, split: bool = False) -> Path:
    """Write the cylinder ``cyl.obj`` (one family ``B``, or ``B`` below z = 1.5 and ``U``).

    The refinement file ``cyl.refine.toml`` beside it holds ``refine``.
    """
    nodes, faces = _cylinder()
    if split:
        low = [f for f in faces if nodes[f, 2].mean() < 1.5]
        high = [f for f in faces if nodes[f, 2].mean() >= 1.5]
        families = {"B": low, "U": high}
    else:
        families = {"B": faces}
    folder.mkdir(parents=True, exist_ok=True)
    path = write_obj(ObjMesh(nodes, families), folder / "cyl.obj")
    _textio.write_text(folder / "cyl.refine.toml", refine)
    return path


def _body(axial: float, circumferential: float, family: str = "B") -> str:
    return (
        f"[families.{family}]\naxial = {axial}\ncircumferential = {circumferential}\n"
        "axis = [0.0, 0.0, 1.0]\n"
    )


# ---- the measurement of R1


def _mean_components(nodes: numpy.ndarray, faces: list[list[int]]) -> tuple[float, float]:
    """Return the mean, over the edges not on a curve, of |component| along and around the axis.

    The open boundary is the only curve of a cylinder (its dihedrals are 15
    degrees at most). Around the axis is the direction perpendicular to the
    axis and to the radius at the edge's mid-point.
    """
    curve = set(boundary_edges(faces))
    edges = numpy.array([e for e in edge_faces(faces) if e not in curve])
    a, b = nodes[edges[:, 0]], nodes[edges[:, 1]]
    vector, mid = b - a, 0.5 * (a + b)
    radial = mid - numpy.outer(mid @ AXIS, AXIS)
    radial /= numpy.linalg.norm(radial, axis=1)[:, None]
    around = numpy.cross(AXIS, radial)
    return float(numpy.abs(vector @ AXIS).mean()), float(numpy.abs((vector * around).sum(1)).mean())


def _r1(source: Path, level: Path, axial: float, circumferential: float) -> tuple[bool, bool]:
    """Return whether the level meets R1 along the axis and around it for the given factors."""
    before = read_obj(source)
    after = read_obj(level)
    along0, around0 = _mean_components(before.verts, before.families["B"])
    along1, around1 = _mean_components(after.verts, after.families["B"])
    return (
        abs(along1 / along0 * axial - 1.0) <= AXIAL_BAND,
        abs(around1 / around0 * circumferential - 1.0) <= AXIAL_BAND,
    )


@pytest.fixture(scope="module")
def levels(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[tuple[float, float], tuple[Path, Path]]:
    """Return the source and the level of the cylinder at (2, 1) and at (1, 2)."""
    out: dict[tuple[float, float], tuple[Path, Path]] = {}
    for axial, circumferential in ((2, 1), (1, 2)):
        root = tmp_path_factory.mktemp(f"a{axial}t{circumferential}")
        source = _source(root / "src", _body(axial, circumferential))
        out[(axial, circumferential)] = (source, refine_mesh(source).obj)
    return out


# ---- R1


@pytest.mark.parametrize(("axial", "circumferential"), [(2, 1), (1, 2)])
def test_r1_edges_shrink_by_their_own_factor_along_and_around_the_axis(
    levels: dict[tuple[float, float], tuple[Path, Path]], axial: int, circumferential: int
) -> None:
    """P0380-AXIAL (FR-428 R1): each component of the edges shrinks by its own factor.

    Control: the level refined along the wrong direction (the two factors
    swapped) fails both halves of the same check.
    """
    source, level = levels[(axial, circumferential)]
    assert _r1(source, level, axial, circumferential) == (True, True)
    _, swapped = levels[(circumferential, axial)]
    assert _r1(source, swapped, axial, circumferential) == (False, False)


def test_r1_every_node_lies_on_the_source_surface(
    levels: dict[tuple[float, float], tuple[Path, Path]],
) -> None:
    """P0380-AXIAL (FR-428 R1, FR-424 R8): the stretched remesh projects onto the real surface.

    Control: the same level with its nodes pushed out radially by 1e-4 of
    the size is caught.
    """
    for source, level in levels.values():
        before, after = read_obj(source), read_obj(level)
        surface = trimesh.Trimesh(before.verts, before.families["B"], process=False)
        size = before.size
        _, distance, _ = trimesh.proximity.closest_point(surface, after.verts)
        assert float(distance.max()) < 1e-9 * size
        pushed = after.verts * numpy.array([1.0 + 1e-4 * size, 1.0 + 1e-4 * size, 1.0])
        _, moved, _ = trimesh.proximity.closest_point(surface, pushed)
        assert float(moved.max()) > 1e-9 * size


def test_the_tag_and_the_report_name_the_axial_and_circumferential_factors(
    levels: dict[tuple[float, float], tuple[Path, Path]],
) -> None:
    """P0380-AXIAL (FR-428): the level is tagged a<axial>t<circumferential> and says it stretched.

    Control: the other level carries the other tag and the other factors.
    """
    import json

    for (axial, circumferential), (_, level) in levels.items():
        assert level.parent.name == f"cyl_Ra{axial}t{circumferential}"
        record = json.loads(level.with_suffix(".refine.json").read_text(encoding="utf-8"))
        stretched = record["families"]["B"]["stretched"]
        assert (stretched["axial"], stretched["circumferential"]) == (axial, circumferential)
        assert stretched["axis"] == [0.0, 0.0, 1.0]
    names = {level.parent.name for _, level in levels.values()}
    assert names == {"cyl_Ra2t1", "cyl_Ra1t2"}


def _turning_patch(degrees: float, stretch: Stretch | None) -> Patch:
    """Return a flat two-triangle patch whose open boundary turns by ``degrees`` at node 1."""
    t = numpy.radians(degrees)
    verts = numpy.array(
        [[-1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [numpy.cos(t), 0.0, numpy.sin(t)], [0.0, 0.0, -1.0]]
    )
    curve = {(0, 1): "boundary", (1, 2): "boundary"}
    return Patch(verts, [[0, 1, 3], [1, 2, 3]], ["B", "B"], numpy.ones(4), curve, stretch=stretch)


def test_a_corner_of_a_curve_is_judged_in_the_real_space() -> None:
    """P0380-AXIAL (FR-428, FR-424 R8): a stretch does not make a corner of a smooth turn.

    A boundary turning by 30 degrees is no corner (the ridge angle is 40);
    stretched 4 times across the axis it would turn by 67 degrees, and a
    corner keeps its place. Control: a turn of 50 degrees is a corner with
    and without the stretch.
    """
    stretch = Stretch([1.0, 0.0, 0.0], [0.0, 0.0, 0.0], 1.0, 4.0)
    assert 1 not in Remesher(_turning_patch(30.0, stretch)).corner
    assert 1 not in Remesher(_turning_patch(30.0, None)).corner
    assert 1 in Remesher(_turning_patch(50.0, stretch)).corner
    assert 1 in Remesher(_turning_patch(50.0, None)).corner


# ---- neighbours of a body


def test_an_unchanged_neighbour_keeps_the_shared_ring_exactly(tmp_path: Path) -> None:
    """P0380-AXIAL (FR-428, FR-424 R8): the curve a body shares with an unchanged family stays.

    The body ``B`` is remeshed in its stretched space while ``U`` is not
    asked to change: in the level every source node of their shared ring is
    present and ``U`` keeps its faces; in the remesh itself each ring node
    comes back from the stretched space with its source coordinates bit for
    bit (a round trip through the map alone changes 32 of the 48). Control:
    the remesh's points with the map's round trip applied to the ring miss it.
    """
    source = _source(tmp_path / "src", _body(3, 1.5), split=True)
    level = read_obj(refine_mesh(source).obj)
    before = read_obj(source)
    ring = sorted(
        set(before.family_vertices("B").tolist()) & set(before.family_vertices("U").tolist())
    )
    assert len(ring) == 48  # the zigzag between two rings
    written = {tuple(p) for p in level.verts.tolist()}
    assert all(tuple(before.verts[v].tolist()) in written for v in ring)
    assert len(level.families["U"]) == len(before.families["U"])
    assert len(level.families["B"]) > len(before.families["B"])
    centroid = before.verts[before.family_vertices("B")].mean(axis=0)
    stretch = Stretch(AXIS, centroid, 3.0, 1.5)
    done = refine_group(before, ["B"], set(), 1.0, stretch=stretch)
    present = {tuple(p) for p in done.points.tolist()}
    assert all(tuple(before.verts[v].tolist()) in present for v in ring)
    tripped = stretch.inverse(stretch.forward(before.verts[ring]))
    assert not all(tuple(p) in present for p in tripped.tolist())


def test_a_body_sharing_a_curve_with_an_isotropic_remeshed_family_is_refused(
    tmp_path: Path,
) -> None:
    """P0380-AXIAL (FR-428, FR-424 R8, R11): a body and a family not stretched alike are refused.

    Their shared curve would be remeshed once for both (R8), and a stretch
    applies to the whole group. The refusal names both families and leaves
    no level folder; two bodies with swapped factors are refused alike.
    Control: the same two families stretched alike refine.
    """
    text = _body(2, 1) + '[families.U]\nfactor = 2\nmethod = "remesh"\n'
    source = _source(tmp_path / "a" / "src", text, split=True)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(source)
    message = str(caught.value)
    assert "families B and U" in message
    assert "same axial, circumferential and axis" in message
    assert message.endswith("Nothing was written.")
    assert [p.name for p in (tmp_path / "a").iterdir()] == ["src"]
    unlike = _source(tmp_path / "c" / "src", _body(2, 1) + _body(1, 2, "U"), split=True)
    with pytest.raises(InputArtifactError, match="families B and U"):
        refine_mesh(unlike)
    alike = _source(tmp_path / "b" / "src", _body(2, 1) + _body(2, 1, "U"), split=True)
    level = refine_mesh(alike)
    assert level.folder.name == "cyl_Ra2t1"
    assert level.report["B"]["remeshed_together"] == ["B", "U"]


def test_a_body_beside_a_factor_one_family_is_remeshed_apart(tmp_path: Path) -> None:
    """P0380-AXIAL (FR-428, FR-424 R8): a body and a family at factor 1 keep their shared curve.

    A remeshed family at factor 1 is unchanged, so the body is remeshed
    alone and the curve they share keeps every source node. Control: the
    same family at factor 2 is refused (the test above).
    """
    text = _body(2, 1) + '[families.U]\nfactor = 1\nmethod = "remesh"\n'
    source = _source(tmp_path / "src", text, split=True)
    refined = refine_mesh(source)
    assert refined.report["B"]["remeshed_together"] == ["B"]
    assert refined.report["U"]["remeshed_together"] == ["U"]
    before, level = read_obj(source), read_obj(refined.obj)
    ring = set(before.family_vertices("B").tolist()) & set(before.family_vertices("U").tolist())
    written = {tuple(p) for p in level.verts.tolist()}
    assert all(tuple(before.verts[v].tolist()) in written for v in sorted(ring))


# ---- R2, each refusal through refine_mesh


REFUSALS = [
    ("axial = 2\n", "need axis"),
    ("circumferential = 2\n", "need axis"),
    ("axial = 2\naxis = [0, 0, 1]\nfactor = 2\n", "replace factor"),
    ("axial = 2\naxis = [0, 0, 1]\nchordwise = 2\n", "replace chordwise"),
    ("circumferential = 2\naxis = [0, 0, 1]\nspanwise = 2\n", "replace spanwise"),
    ('axial = 2\naxis = [0, 0, 1]\nmethod = "grid"\n', "not a grid"),
    ("axial = 2\naxis = [0, 1]\n", "axis: [0, 1] is not three finite numbers"),
    ('axial = 2\naxis = "z"\n', "axis: 'z' is not three finite numbers"),
    ("axial = 2\naxis = [0, 0, 0]\n", "axis: the axis is zero"),
    ("axial = 2\naxis = [0, 0, 1]\norigin = [0, 0]\n", "origin: [0, 0] is not three"),
    ("axial = 2\naxis = [0, 0, 1]\norigin = [0, true, 0]\n", "origin: [0, True, 0] is not"),
    ("axial = 0\naxis = [0, 0, 1]\n", "axial: the factor 0 is not above zero"),
    ("factor = 2\naxis = [0, 0, 1]\n", "axis and origin go with axial and circumferential"),
]


@pytest.mark.parametrize(("table", "expected"), REFUSALS)
def test_r2_each_refusal_reaches_the_user_through_refine_mesh(
    tmp_path: Path, table: str, expected: str
) -> None:
    """P0380-AXIAL (FR-428 R2): each refusal names the file, the table and the key.

    Control: the same body stated well refines (the module's levels), and a
    refused call leaves no level folder beside the source's folder.
    """
    source = _source(tmp_path / "src", "[families.B]\n" + table)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(source)
    message = str(caught.value)
    assert f"{source.with_name('cyl.refine.toml')} [families.B]" in message
    assert expected in message
    assert message.endswith("Nothing was written.")
    assert [p.name for p in tmp_path.iterdir()] == ["src"]
