"""Tier 1, 0.38.0 S4: the two cut faces of a periodic sector, refined node for node (FR-427).

Every fixture is built here: a 60 degree wedge of a cylinder band about the
z axis (six copies make a turn), triangulated so that its two cuts, at 0 and
at 60 degrees, match node for node. The level's cuts are measured from the
level's OBJ by this file's own rotation, never from the refinement's report,
and each measurement is also run on an input it must reject.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy
import pytest

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine import _obj
from pyflightstream.workspace._refine._config import Periodic
from pyflightstream.workspace._refine._geometry import (
    PERIODIC_LEVEL_FRACTION,
    PERIODIC_SOURCE_FRACTION,
    boundary_edges,
)
from pyflightstream.workspace._refine._obj import ObjMesh
from pyflightstream.workspace._refine._periodic import find_cuts, level_distance, match_level

pytest.importorskip("trimesh")

SIX = Periodic(axis=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0), copies=6)
PERIODIC = "[periodic]\naxis = [0.0, 0.0, 1.0]\norigin = [0.0, 0.0, 0.0]\ncopies = 6\n"

# ---- fixtures


def _band(na: int = 6, nz: int = 5, degrees: float = 60.0) -> numpy.ndarray:
    """Return the nodes of a cylinder band of radius 1: na intervals around, nz along z."""
    theta = numpy.radians(numpy.linspace(0.0, degrees, na + 1))
    z = 0.5 * (1.0 - numpy.cos(numpy.pi * numpy.arange(nz + 1) / nz))  # clustered at both ends
    t, h = numpy.meshgrid(theta, z)
    return numpy.column_stack([numpy.cos(t).ravel(), numpy.sin(t).ravel(), h.ravel()])


def _cells(na: int, cells) -> list[list[int]]:
    """Return the two triangles of each cell (i around, j along), the diagonal alternating."""
    faces = []
    for i, j in cells:
        a, b = j * (na + 1) + i, j * (na + 1) + i + 1
        c, d = a + na + 1, b + na + 1
        faces += [[a, b, d], [a, d, c]] if (i + j) % 2 else [[a, b, c], [b, d, c]]
    return faces


def _quads(na: int, cells) -> list[list[int]]:
    """Return each cell (i around, j along) as one quadrilateral."""
    return [
        [j * (na + 1) + i, j * (na + 1) + i + 1, (j + 1) * (na + 1) + i + 1, (j + 1) * (na + 1) + i]
        for i, j in cells
    ]


def _wedge(na: int = 6, nz: int = 5, *, quads: bool = False) -> ObjMesh:
    """Return the 60 degree wedge as one family ``W``; vertex 0 is on the cut at 0 degrees."""
    cells = [(i, j) for j in range(nz) for i in range(na)]
    return ObjMesh(_band(na, nz), {"W": (_quads if quads else _cells)(na, cells)})


def _two_family_wedge(na: int = 6, nz: int = 5) -> ObjMesh:
    """Return the wedge cut at 30 degrees into ``A`` (0 to 30, quadrilaterals) and ``B``."""
    half = na // 2
    a = [(i, j) for j in range(nz) for i in range(half)]
    b = [(i, j) for j in range(nz) for i in range(half, na)]
    return ObjMesh(_band(na, nz), {"A": _quads(na, a), "B": _cells(na, b)})


def _full_band(na: int = 24, nz: int = 4) -> ObjMesh:
    """Return a whole cylinder band (no cut): the last column of nodes is the first."""
    nodes = _band(na, nz, 360.0)
    cells = [(i, j) for j in range(nz) for i in range(na)]
    faces = _cells(na, cells)
    ring = {j * (na + 1) + na: j * (na + 1) for j in range(nz + 1)}
    faces = [[ring.get(v, v) for v in f] for f in faces]
    return ObjMesh(nodes, {"W": faces})


def _write(
    tmp_path: Path, mesh: ObjMesh, refine: str | None, *, te: bool = False, name: str = "W"
) -> Path:
    """Write the mesh as ``<tmp>/src/<name>.obj`` with, when asked, its refinement file.

    ``te`` writes the bottom arc (z = 0) as the trailing edge, the grid line a
    sheet is recovered from.
    """
    folder = tmp_path / "src"
    folder.mkdir(parents=True, exist_ok=True)
    source = _obj.write_obj(mesh, folder / f"{name}.obj")
    if te:
        bottom = numpy.nonzero(numpy.abs(mesh.verts[:, 2]) < 1e-12)[0]
        mid = 0.5 * (mesh.verts[bottom[:-1]] + mesh.verts[bottom[1:]])
        _obj.write_te(folder / f"{name}.te.txt", "METER", mid)
    if refine is not None:
        _textio.write_text(folder / f"{name}.refine.toml", refine)
    return source


# ---- this file's own measurement


def _turn(points: numpy.ndarray, degrees: float) -> numpy.ndarray:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    rot = numpy.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return points @ rot.T


def _cut_nodes(verts: numpy.ndarray, faces: list[list[int]], degrees: float) -> numpy.ndarray:
    """Return the boundary nodes lying on the half-plane at the given angle about z."""
    used = sorted({v for e in boundary_edges(faces) for v in e})
    p = _turn(verts[used], -degrees)
    on = (numpy.abs(p[:, 1]) < 1e-7) & (p[:, 0] > 0.5)
    return verts[used][on]


def _mismatch(first: numpy.ndarray, second: numpy.ndarray) -> float:
    """Return the largest distance of a node of the first cut, turned 60 degrees, from the second.

    Infinite when the two cuts hold different numbers of nodes.
    """
    if len(first) != len(second):
        return math.inf
    turned = _turn(first, 60.0)
    d = numpy.linalg.norm(turned[:, None, :] - second[None, :, :], axis=2)
    return float(max(d.min(axis=1).max(), d.min(axis=0).max()))


def _size(verts: numpy.ndarray) -> float:
    return float(numpy.linalg.norm(verts.max(axis=0) - verts.min(axis=0)))


def _level(result) -> tuple[numpy.ndarray, list[list[int]]]:
    mesh = _obj.read_obj(result.obj)
    return mesh.verts, [f for fs in mesh.families.values() for f in fs]


# ---- R1: the level's cuts match node for node


@pytest.mark.parametrize("factor", [2.0, 0.5])
def test_a_remeshed_sector_keeps_its_cuts_node_for_node(tmp_path, factor):
    """P0380-SECTOR (FR-427 R1): a remeshed wedge's two cuts match within 1e-9 of the size.

    The cut holds about factor times its source intervals, so the cut was
    rebuilt rather than kept. Control: the same level with the nodes of one
    cut shifted by 1e-6 of the size fails both this file's measurement and
    the package's own check.
    """
    mesh = _wedge(na=6, nz=6)
    table = f'[families.W]\nfactor = {factor}\nmethod = "remesh"\n'
    source = _write(tmp_path, mesh, PERIODIC + table)
    result = refine_mesh(source)
    verts, faces = _level(result)
    size = _size(mesh.verts)
    first, second = _cut_nodes(verts, faces, 0.0), _cut_nodes(verts, faces, 60.0)
    assert len(first) == round(factor * 6) + 1
    assert _mismatch(first, second) <= PERIODIC_LEVEL_FRACTION * size
    record = json.loads(result.files[-2].read_text(encoding="utf-8"))
    assert record["periodic"]["copies"] == 6
    assert record["periodic"]["level_distance"] <= PERIODIC_LEVEL_FRACTION * size
    assert record["periodic"]["pairs"][0]["master"] == ["W"]
    shifted = second + numpy.array([0.0, 0.0, 1e-6 * size])
    assert _mismatch(first, shifted) > PERIODIC_LEVEL_FRACTION * size
    assert level_distance(first, shifted, SIX, 1) > PERIODIC_LEVEL_FRACTION * size
    assert level_distance(first, second, SIX, 1) <= PERIODIC_LEVEL_FRACTION * size


def test_a_grid_sector_keeps_its_cuts_node_for_node(tmp_path):
    """P0380-SECTOR (FR-427 R1): a wedge refined as a grid at factor 2 keeps its cuts matched.

    Control: the level's cut nodes shifted by 1e-6 of the size fail the measurement.
    """
    mesh = _wedge(quads=True)
    source = _write(tmp_path, mesh, PERIODIC, te=True)
    result = refine_mesh(source, 2)
    assert result.report["W"]["method"] == "grid"
    verts, faces = _level(result)
    size = _size(mesh.verts)
    first, second = _cut_nodes(verts, faces, 0.0), _cut_nodes(verts, faces, 60.0)
    assert len(first) == 11
    assert _mismatch(first, second) <= PERIODIC_LEVEL_FRACTION * size
    assert _mismatch(first, second + 1e-6 * size) > PERIODIC_LEVEL_FRACTION * size


def test_a_grid_master_rebuilds_the_remeshed_slave_on_its_nodes(tmp_path):
    """P0380-SECTOR (FR-427 R1): the cut of grid A at 0 degrees is imposed on remeshed B at 60.

    Control: the slave cut of the level, read back without the rotation's
    sense reversed, does not match (a check that cannot tell the senses apart fails here).
    """
    mesh = _two_family_wedge()
    table = '[families.A]\nfactor = 2\n[families.B]\nfactor = 2\nmethod = "remesh"\n'
    source = _write(tmp_path, mesh, PERIODIC + table, te=True)
    result = refine_mesh(source)
    assert result.report["A"]["method"] == "grid"
    assert result.report["B"]["method"] == "remesh"
    verts, faces = _level(result)
    size = _size(mesh.verts)
    first, second = _cut_nodes(verts, faces, 0.0), _cut_nodes(verts, faces, 60.0)
    assert len(first) == 11
    assert _mismatch(first, second) <= PERIODIC_LEVEL_FRACTION * size
    assert level_distance(first, second, SIX, -1) > PERIODIC_LEVEL_FRACTION * size


# ---- R2: the source's cuts


def test_the_source_cut_pair_is_found_with_its_sense():
    """P0380-SECTOR (FR-427 R2): the wedge's cuts are one pair, master at 0 degrees, sense +60.

    Control: the same wedge with seven copies (51.4 degrees) finds no pair and is refused.
    """
    mesh = _wedge()
    cuts = find_cuts(mesh.verts, mesh.families, SIX, size=mesh.size, where="w")
    assert len(cuts) == 1
    assert cuts[0].sense == 1
    assert numpy.allclose(mesh.verts[list(cuts[0].master)][:, 1], 0.0)
    assert cuts[0].families == (("W",), ("W",))
    seven = Periodic(axis=SIX.axis, origin=SIX.origin, copies=7)
    with pytest.raises(InputArtifactError, match="no two open boundary chains"):
        find_cuts(mesh.verts, mesh.families, seven, size=mesh.size, where="w")


def _moved(fraction: float, *, quads: bool = False) -> tuple[ObjMesh, float]:
    """Return the wedge with one interior node of the 60 degree cut moved along z."""
    mesh = _wedge(quads=quads)
    size = _size(mesh.verts)
    verts = mesh.verts.copy()
    verts[2 * 7 + 6, 2] += fraction * size  # station 2 of the column at 60 degrees
    return ObjMesh(verts, mesh.families), fraction * size


def test_a_source_whose_cut_node_moved_is_refused_naming_the_distance(tmp_path):
    """P0380-SECTOR (FR-427 R2): one cut node moved by 1e-4 of the size refuses, naming 1e-4.

    Control: a node moved by 1e-8 of the size (inside PERIODIC_SOURCE_FRACTION)
    is accepted; refined as a grid, whose spline carries the move into the
    level, the level's cuts still match within 1e-9 of the size.
    """
    mesh, moved = _moved(1e-4)
    source = _write(tmp_path, mesh, PERIODIC)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(source, 2)
    text = str(caught.value)
    assert "do not map onto each other" in text
    assert text.endswith("Nothing was written.")
    stated = float(text.split("the largest distance is ")[1].split(" ")[0])
    assert stated == pytest.approx(moved, rel=1e-4)
    assert not (tmp_path / "W_R2").exists()
    assert 1e-4 > PERIODIC_SOURCE_FRACTION > 1e-8
    near, _ = _moved(1e-8, quads=True)
    other = tmp_path / "near"
    result = refine_mesh(_write(other, near, PERIODIC, te=True), 2)
    assert result.report["W"]["method"] == "grid"
    verts, faces = _level(result)
    first, second = _cut_nodes(verts, faces, 0.0), _cut_nodes(verts, faces, 60.0)
    assert _mismatch(first, second) <= PERIODIC_LEVEL_FRACTION * _size(near.verts)


def test_a_mesh_without_cut_boundaries_is_refused(tmp_path):
    """P0380-SECTOR (FR-427 R2): a whole band (no cut) with a [periodic] table is refused.

    Control: the wedge with the same table is accepted (the first test of this file).
    """
    mesh = _full_band()
    assert len(boundary_edges(mesh.families["W"])) == 2 * 24
    source = _write(tmp_path, mesh, PERIODIC)
    with pytest.raises(InputArtifactError, match="the mesh has no cut boundaries") as caught:
        refine_mesh(source, 2)
    assert "[periodic]" in str(caught.value)
    assert str(caught.value).endswith("Nothing was written.")
    assert not (tmp_path / "W_R2").exists()


def test_a_level_whose_cuts_do_not_match_is_refused_before_writing():
    """P0380-SECTOR (FR-427 R1): the level check refuses a cut moved beyond the source tolerance.

    Control: the unmoved wedge passes the same check and is reported.
    """
    mesh = _wedge()
    size = _size(mesh.verts)
    cuts = find_cuts(mesh.verts, mesh.families, SIX, size=size, where="w")
    _, report = match_level(
        mesh.verts, mesh.families, cuts, SIX, source=mesh.verts, size=size, where="w"
    )
    assert report is not None
    assert report["level_distance"] <= PERIODIC_LEVEL_FRACTION * size
    bad = mesh.verts.copy()
    bad[2 * 7 + 6, 2] += 1e-5 * size
    with pytest.raises(InputArtifactError, match="do not match node for node"):
        match_level(bad, mesh.families, cuts, SIX, source=mesh.verts, size=size, where="w")


# ---- R3: without [periodic]


def test_without_periodic_the_cuts_are_free(tmp_path):
    """P0380-SECTOR (FR-427 R3): without [periodic] a wedge whose cuts differ is refined as any.

    The source with a cut node moved by 1e-4 of the size, refused with
    [periodic] (the control, asserted here too), is refined without it; its
    level reports no periodic entry and the source's bytes are unchanged.
    """
    mesh, _ = _moved(1e-4)
    source = _write(tmp_path, mesh, None)
    before = source.read_bytes()
    result = refine_mesh(source, 2)
    record = json.loads(result.files[-2].read_text(encoding="utf-8"))
    assert "periodic" not in record
    assert source.read_bytes() == before
    with pytest.raises(InputArtifactError, match="do not map onto each other"):
        refine_mesh(_write(tmp_path / "with", mesh, PERIODIC), 2)
