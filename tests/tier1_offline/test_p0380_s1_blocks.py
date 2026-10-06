"""P0380-BLOCKS (FR-424 R6, R7, R9): smooth tubes and multiblock grids, recovered and resampled.

A body of revolution (a spinner, a nacelle barrel) holds no trailing edge: its
seam is the lowest source vertex index of its first station, and its sections
are resampled by a periodic spline, so the closed section has no knot at the
seam. An all-quadrilateral family that is not one grid (an L-shaped sheet, a
sheet with a hole) is cut along the grid lines leaving its singular vertices
into four-sided patches; each patch side is resampled once and shared.

The fixtures are synthetic (tests/p0380_mesh_fixtures.py), the numbering
shuffled: circles about the x axis whose radius varies along it, and sheets
cut from a grid on a bicubic surface, which the index-space splines
reproduce exactly, so every level node is known to lie on the surface.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._blocks import Blocks, recover_family, refine_blocks
from pyflightstream.workspace._refine._grid import (
    Grid,
    not_a_knot,
    periodic,
    recover_grid,
    refine_grid,
)
from tests.p0380_mesh_fixtures import (
    Blocky,
    Body,
    Composite,
    body_of_revolution,
    face_coordinates,
    l_sheet,
    open_loop_count,
    read_mesh,
    square_hole_sheet,
    tube_pole_quads,
    write_source,
)

#: The radial error a periodic spline of 24 nodes per circle stays within (the open
#: not-a-knot spline through the same closed chain misses by about 6e-5 at the seam).
CIRCLE_TOLERANCE = 2e-5


def _radial_error(points: np.ndarray) -> np.ndarray:
    return np.abs(np.hypot(points[:, 1], points[:, 2]) - Body.radius(points[:, 0]))


def _smooth(body: Body) -> Grid:
    grid = recover_grid(body.verts, body.faces, set())
    assert isinstance(grid, Grid), grid
    return grid


@pytest.mark.parametrize("pole", [False, True], ids=["open", "pole"])
def test_a_smooth_tube_is_recovered_with_its_seam_at_the_lowest_source_index(pole):
    """P0380-BLOCKS (FR-424 R6, R9): no trailing edge and no ridge give a smooth tube.

    The seam is the lowest source vertex index of the first station. Control:
    a wing tube without its trailing-edge vertices has a sharp trailing edge,
    and is still refused with today's reason.
    """
    body = body_of_revolution(pole=pole)
    grid = _smooth(body)
    assert grid.layout == "tube" and grid.smooth
    assert grid.ends == (("open", "pole") if pole else ("open", "open"))
    assert int(grid.ids[0, 0]) == int(grid.ids[0].min())
    assert grid.describe().startswith("a smooth tube without trailing edge of 7 stations")
    wing = tube_pole_quads()
    assert recover_grid(wing.verts, wing.faces, set()) == "no trailing-edge vertex on the end loop"


@pytest.mark.parametrize("pole", [False, True], ids=["open", "pole"])
def test_a_smooth_tube_at_factor_one_is_the_source_in_coordinates_and_order(pole):
    """P0380-BLOCKS (FR-424 R7): at factor 1 a smooth tube's faces equal the source's, in order.

    Control: the level's faces rotated by one vertex, and reversed, fail.
    """
    body = body_of_revolution(pole=pole)
    level = refine_grid(body.verts, body.faces, _smooth(body), chordwise=1.0, spanwise=1.0)
    want = face_coordinates(body.verts, body.faces)
    assert face_coordinates(level.points, level.faces) == want
    assert face_coordinates(level.points, [f[1:] + f[:1] for f in level.faces]) != want
    assert face_coordinates(level.points, level.faces[::-1]) != want
    assert len(level.te_midpoints) == 0
    assert level.report["chordwise_spline"] == "periodic"


@pytest.mark.parametrize("pole", [False, True], ids=["open", "pole"])
def test_factor_two_puts_the_sections_on_the_circle_and_the_seam_has_no_kink(pole):
    """P0380-BLOCKS (FR-424 R6): the periodic spline keeps the new nodes on the circle.

    At chordwise 2 every level node lies within 2e-5 of the analytic circle
    of its station, the source nodes are kept bit for bit, and the count
    doubles around. Control: the open not-a-knot spline through the same
    closed chain (today's tube spline) misses the circle by more at the seam
    and fails the tolerance.
    """
    body = body_of_revolution(pole=pole)
    grid = _smooth(body)
    level = refine_grid(body.verts, body.faces, grid, chordwise=2.0, spanwise=1.0)
    ring = level.points[:-1] if pole else level.points
    assert len(ring) == 2 * body.nodes * body.stations
    assert float(_radial_error(ring).max()) < CIRCLE_TOLERANCE
    held = {tuple(p) for p in level.points}
    assert all(tuple(p) in held for p in body.verts)
    assert level.report["intervals"]["chordwise"] == [body.nodes, 2 * body.nodes]

    station = body.verts[grid.ids[0]]
    s = np.linspace(0.0, body.nodes, 2 * body.nodes + 1)[:-1]
    closed = periodic(station, s)
    opened = not_a_knot(np.vstack([station, station[:1]]), s)
    seam = [1, len(s) - 1]  # the new nodes either side of the seam
    assert _radial_error(closed)[seam].max() < 0.2 * _radial_error(opened)[seam].max()
    assert float(_radial_error(opened).max()) > CIRCLE_TOLERANCE


def test_the_periodic_spline_keeps_its_knots_and_is_smooth_across_the_seam():
    """P0380-BLOCKS (FR-424 R6): the periodic spline is exact at its knots and closes smoothly.

    Its slope just before the seam equals its slope just after it. Control:
    the open not-a-knot spline through the same closed chain has a kink there.
    """
    n = 16
    angle = 2.0 * np.pi * np.arange(n) / n
    loop = np.stack([np.cos(angle) + 0.3 * np.cos(3 * angle), np.sin(2 * angle)], axis=1)
    assert np.array_equal(periodic(loop, np.arange(n)), loop)
    eps = 1e-6

    def kink(f):
        before = (f(np.array([n - eps])) - f(np.array([n - 2 * eps]))) / eps
        after = (f(np.array([eps])) - f(np.array([0.0]))) / eps
        return float(np.abs(before - after).max())

    assert kink(lambda p: periodic(loop, p % n)) < 1e-4
    closed = np.vstack([loop, loop[:1]])
    assert kink(lambda p: not_a_knot(closed, p)) > 1e-2


def test_the_periodic_spline_equals_scipys_where_scipy_is_installed():
    """P0380-BLOCKS (FR-424 R6, R10): the numpy periodic spline is scipy's to 1e-12.

    Control: scipy's not-a-knot spline through the same closed chain differs.
    """
    interpolate = pytest.importorskip("scipy.interpolate")
    rng = np.random.default_rng(5)
    for n in (3, 4, 7, 30):
        y = rng.normal(size=(n, 3))
        closed = np.vstack([y, y[:1]])
        p = np.sort(rng.uniform(0, n, 200))
        spline = interpolate.CubicSpline(np.arange(n + 1), closed, bc_type="periodic")
        assert float(np.abs(periodic(y, p) - spline(p)).max()) < 1e-12
        if n > 3:
            other = interpolate.CubicSpline(np.arange(n + 1), closed, bc_type="not-a-knot")
            assert float(np.abs(periodic(y, p) - other(p)).max()) > 1e-6


def test_a_smooth_tube_is_refined_as_a_grid_by_refine_mesh(tmp_path):
    """P0380-BLOCKS (FR-424 R4, R7, R9; FR-426 R2): refine.json names the smooth tube.

    At factor 1 the level's faces are the source's (G6 judged and passed); at
    2 and 0.5 the gates G1 to G5 pass and no trailing-edge points are written.
    Control: the level at factor 2 is not the source.
    """
    body = body_of_revolution(pole=True)
    mesh = Composite(body.verts, {"S": body.faces}, np.zeros((0, 3)), {})
    src = write_source(tmp_path / "src", "body", mesh)
    source = face_coordinates(*_family(src, "S"))
    for factor in (1.0, 2.0, 0.5):
        level = refine_mesh(src, factor, out_dir=tmp_path / f"f{factor}")
        entry = level.report["S"]
        assert entry["method"] == "grid", entry
        assert entry["reason"].startswith("a smooth tube without trailing edge")
        assert entry["chordwise_spline"] == "periodic"
        gates = {g.name: g.verdict for g in level.audit.gates}
        assert all(g.passed for g in level.audit.gates), gates
        assert not any(p.name.endswith(".te.txt") for p in level.files)
        written = face_coordinates(*_family(level.obj, "S"))
        if factor == 1.0:
            assert gates.get("G6") == "pass", gates
            assert written == source
        else:
            assert written != source


def _family(path, name):
    verts, families = read_mesh(path)
    return verts, families[name]


# ------------------------------------------------------------ multiblock grids

SHEETS = {
    "l-sheet": (l_sheet, [(4, 7), (4, 5), (6, 7)], 1),
    "square-hole": (square_hole_sheet, [(4, 4)] * 8, 2),
}


def _blocks(sheet: Blocky) -> Blocks:
    found = recover_family(sheet.verts, sheet.faces, set())
    assert isinstance(found, Blocks), found
    return found


def _edge_uses(faces) -> Counter:
    return Counter(
        (min(a, b), max(a, b)) for f in faces for a, b in zip(f, f[1:] + f[:1], strict=True)
    )


def _conforming(points, faces, loops: int) -> bool:
    """Return whether a level is one welded all-quadrilateral surface with the source's loops.

    No edge has more than two faces, no two nodes share a position, and the
    open boundary loops are the source's in number: a shared curve whose two
    sides held different nodes would leave a slit, and the count would grow.
    """
    uses = _edge_uses(faces)
    distinct = len({tuple(np.round(p, 12)) for p in points}) == len(points)
    return (
        all(len(f) == 4 for f in faces)
        and max(uses.values()) <= 2
        and distinct
        and open_loop_count(faces) == loops
    )


def _off_surface(points) -> float:
    return float(np.abs(points[:, 2] - Blocky.height(points[:, 0], points[:, 1])).max())


@pytest.mark.parametrize("name", SHEETS)
def test_the_layout_is_cut_along_the_grid_lines_leaving_the_singular_vertices(name):
    """P0380-BLOCKS (FR-424 R6, R9): the separatrices cut the family into four-sided patches.

    The L-shaped sheet (six corners) is cut by the two grid lines leaving its
    re-entrant corner into three patches; the sheet with a square hole by the
    eight lines leaving the hole's corners into eight. Neither is one grid
    (the control: its sheet or tube recovery names why).
    """
    make, dims, _ = SHEETS[name]
    sheet = make()
    blocks = _blocks(sheet)
    assert sorted(tuple(int(n) - 1 for n in ids.shape) for ids in blocks.patches) == sorted(dims)
    assert sum(cells.size for cells in blocks.cells) == len(sheet.faces)
    assert blocks.describe() == f"a multiblock of {len(dims)} four-sided patches of quadrilaterals"
    assert isinstance(recover_grid(sheet.verts, sheet.faces, set()), str)


@pytest.mark.parametrize("shuffled", [False, True], ids=["rows", "shuffled"])
@pytest.mark.parametrize("name", SHEETS)
def test_a_multiblock_family_at_factor_one_is_the_source_in_coordinates_and_order(name, shuffled):
    """P0380-BLOCKS (FR-424 R7): at factor 1 the faces equal the source's, in order.

    The source's faces are written row by row, or shuffled. Control: the
    level's faces rotated by one vertex, and reversed, fail.
    """
    sheet = SHEETS[name][0]()
    if shuffled:
        order = np.random.default_rng(2).permutation(len(sheet.faces))
        sheet.faces = [sheet.faces[k] for k in order]
    level = refine_blocks(sheet.verts, sheet.faces, _blocks(sheet), factor=1.0)
    want = face_coordinates(sheet.verts, sheet.faces)
    assert face_coordinates(level.points, level.faces) == want
    assert face_coordinates(level.points, [f[1:] + f[:1] for f in level.faces]) != want
    assert face_coordinates(level.points, level.faces[::-1]) != want
    assert len(level.points) == len(sheet.verts)


@pytest.mark.parametrize("factor", [2.0, 0.5])
@pytest.mark.parametrize("name", SHEETS)
def test_factor_two_and_half_give_a_conforming_all_quad_family_on_the_surface(name, factor):
    """P0380-BLOCKS (FR-424 R6; FR-425 R5): one welded quad surface, every node on the surface.

    Every edge has at most two faces, no two nodes share a position, the open
    boundary loops are the source's, the counts are round(f m) per patch, and
    every node lies on the bicubic surface within 1e-9. At factor 2 every
    source node is kept bit for bit. Control: the same level with the faces of
    one corner given their own nodes (cut loose along a curve) fails the
    conformity check.
    """
    make, dims, loops = SHEETS[name]
    sheet = make()
    level = refine_blocks(sheet.verts, sheet.faces, _blocks(sheet), factor=factor)
    assert _conforming(level.points, level.faces, loops)
    rows = sorted(tuple(b["rows"]) + tuple(b["columns"]) for b in level.report["blocks"])
    assert rows == sorted(
        (r, max(1, round(factor * r)), c, max(1, round(factor * c))) for r, c in dims
    )
    assert len(level.faces) == sum(b["rows"][1] * b["columns"][1] for b in level.report["blocks"])
    assert _off_surface(level.points) < 1e-9
    if factor == 2.0:
        held = {tuple(p) for p in level.points}
        assert all(tuple(p) in held for p in sheet.verts)
    assert not _conforming(*_unweld(level.points, level.faces), loops)


def _unweld(points, faces):
    """Control: give the faces of the sheet's corner at x, y < 0.26 their own copy of each node."""
    centroids = np.array([points[f].mean(axis=0) for f in faces])
    mine = set(np.nonzero((centroids[:, 0] < 0.26) & (centroids[:, 1] < 0.26))[0].tolist())
    assert 0 < len(mine) < len(faces)
    extra = {}
    out = []
    for k, f in enumerate(faces):
        if k in mine:
            f = [extra.setdefault(v, len(points) + len(extra)) for v in f]
        out.append(f)
    copies = np.array([points[v] for v in extra], dtype=float).reshape(-1, 3)
    shifted = copies + 1e-6
    return np.vstack([points, shifted]), out


@pytest.mark.parametrize("name", SHEETS)
def test_a_shared_patch_side_is_the_same_nodes_from_both_sides(name):
    """P0380-BLOCKS (FR-424 R6): each arc is resampled once; both patches hold its nodes.

    For every source edge two patches share, the level's nodes between its
    two ends, run straight through 2 m level edges, each of them used by two
    faces, one of each patch. A side resampled once per patch would leave
    those edges with one face each (the mutation that names an arc's nodes
    per patch fails here).
    """
    sheet = SHEETS[name][0]()
    blocks = _blocks(sheet)
    level = refine_blocks(sheet.verts, sheet.faces, blocks, factor=2.0)
    users = Counter(arc for sides in blocks.sides for arc, _ in sides)
    shared = [a for a, n in users.items() if n == 2]
    assert shared
    uses = _edge_uses(level.faces)
    for arc in shared:
        listed = level.points.tolist()
        ends = [listed.index(sheet.verts[v].tolist()) for v in blocks.arcs[arc]]
        chain = _walk(level.points, uses, ends[0], ends[-1], 2 * (len(blocks.arcs[arc]) - 1))
        assert chain is not None and len(chain) == 2 * (len(blocks.arcs[arc]) - 1) + 1
        assert all(
            uses[(min(a, b), max(a, b))] == 2 for a, b in zip(chain, chain[1:], strict=False)
        )


def _walk(points, uses, start, stop, steps):
    """Return the straight chain of level nodes from start to stop in the given number of edges."""
    adj = {}
    for a, b in uses:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    chain = [start]
    for _ in range(steps):
        here = points[chain[-1]]
        aim = points[stop] - here
        best = max(
            adj[chain[-1]] - set(chain),
            key=lambda u: float(np.dot(points[u] - here, aim) / np.linalg.norm(points[u] - here)),
        )
        chain.append(best)
    return chain if chain[-1] == stop else None


def test_a_family_with_a_triangle_falls_back_as_before(tmp_path):
    """P0380-BLOCKS (FR-424 R9): a triangle leaves the family without a multiblock grid.

    ``recover_family`` gives the sheet or tube recovery's own reason; under
    ``method = "grid"`` the refinement is refused naming it. Control: the
    same sheet without the split cell is a multiblock grid.
    """
    sheet = l_sheet(split={(2, 2)})
    why = recover_family(sheet.verts, sheet.faces, set())
    assert isinstance(why, str) and why == recover_grid(sheet.verts, sheet.faces, set())
    assert isinstance(recover_family(l_sheet().verts, l_sheet().faces, set()), Blocks)
    mesh = Composite(sheet.verts, {"L": sheet.faces}, np.zeros((0, 3)), {})
    src = write_source(
        tmp_path / "src", "plate", mesh, refine_toml='[families.L]\nmethod = "grid"\nfactor = 2\n'
    )
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src)
    text = str(caught.value)
    assert "family L" in text and f"no grid was recovered: {why}" in text
    assert not (tmp_path / "plate_R2").exists()


@pytest.mark.parametrize("name", SHEETS)
def test_refine_mesh_reports_a_multiblock_grid_and_its_audit_passes(tmp_path, name):
    """P0380-BLOCKS (FR-424 R4, R7, R9; FR-426 R2): refine.json names the layout and patches.

    At factor 1 the level's faces are the source's and G6 passes; at 2 and
    0.5 the gates G1 to G5 pass. refine.json gives the method grid, the
    layout multiblock, the patch count and each patch's rows and columns.
    Control: chordwise is refused on the multiblock family, naming it.
    """
    make, dims, _ = SHEETS[name]
    sheet = make()
    mesh = Composite(sheet.verts, {"M": sheet.faces}, np.zeros((0, 3)), {})
    src = write_source(tmp_path / "src", "plate", mesh)
    verts, families = read_mesh(src)
    source = face_coordinates(verts, families["M"])
    for factor in (1.0, 2.0, 0.5):
        level = refine_mesh(src, factor, out_dir=tmp_path / f"f{factor}")
        entry = level.report["M"]
        assert entry["method"] == "grid" and entry["layout"] == "multiblock", entry
        assert entry["patches"] == len(dims)
        assert sorted((b["rows"][0], b["columns"][0]) for b in entry["blocks"]) == sorted(dims)
        assert (
            entry["reason"] == f"a multiblock of {len(dims)} four-sided patches of quadrilaterals"
        )
        gates = {g.name: g.verdict for g in level.audit.gates}
        assert all(g.passed for g in level.audit.gates), gates
        written = face_coordinates(*_family(level.obj, "M"))
        assert (written == source) == (factor == 1.0)
        if factor == 1.0:
            assert gates.get("G6") == "pass", gates
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, chordwise=2.0, out_dir=tmp_path / "c")
    assert "family M: chordwise and spanwise are not defined" in str(caught.value)
