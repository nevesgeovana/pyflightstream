"""P0380-BLOCKS (FR-920, FR-921, FR-923): smooth tubes and multiblock grids, recovered and
 resampled.

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
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
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
    """P0380-BLOCKS (FR-920, FR-923): no trailing edge and no ridge give a smooth tube.

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
    """P0380-BLOCKS (FR-921): at factor 1 a smooth tube's faces equal the source's, in order.

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
    """P0380-BLOCKS (FR-920): the periodic spline keeps the new nodes on the circle.

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
    """P0380-BLOCKS (FR-920): the periodic spline is exact at its knots and closes smoothly.

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
    """P0380-BLOCKS (FR-920, FR-924): the numpy periodic spline is scipy's to 1e-12.

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
    """P0380-BLOCKS (FR-918, FR-921, FR-923; FR-938): refine.json names the smooth tube.

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
    """P0380-BLOCKS (FR-920, FR-923): the separatrices cut the family into four-sided patches.

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
    """P0380-BLOCKS (FR-921): at factor 1 the faces equal the source's, in order.

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
    """P0380-BLOCKS (FR-920; FR-936): one welded quad surface, every node on the surface.

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
    """P0380-BLOCKS (FR-920): each arc is resampled once; both patches hold its nodes.

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
    """P0380-BLOCKS (FR-923): a triangle leaves the family without a multiblock grid.

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
    """P0380-BLOCKS (FR-918, FR-921, FR-923; FR-938): refine.json names the layout and patches.

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


@pytest.mark.parametrize("factor", [0.01, 0.2, 0.24])
def test_a_patch_side_a_factor_cannot_coarsen_is_kept_and_reported(tmp_path, capsys, factor):
    """P0380-BLOCKS (FR-915, FR-925, FR-930): a factor below 1/m of a patch side keeps that side.

    The L-shaped sheet's shortest patch side holds 4 source intervals, so a
    factor below 1/4 cannot coarsen it. Owner decision of 2026-10-22 (it
    replaces the refusal RV-08 of the 0.38.0 release review): the family is
    not refused; such a side keeps max(1, round(f m)) intervals, the rest of
    the family is resampled, the level is written and its audit gates pass,
    the warning names the family, each patch and side and where it lies, and
    refine.json lists the same under ``kept_sides``. The command exits 0.
    Control: exactly 1/4 keeps no side, and the report says so.
    """
    from pyflightstream.run import cli

    sheet = l_sheet()
    mesh = Composite(sheet.verts, {"M": sheet.faces}, np.zeros((0, 3)), {})
    src = write_source(tmp_path / "src", "plate", mesh)
    with pytest.warns(PyflightstreamWarning) as caught:
        level = refine_mesh(src, factor, out_dir=tmp_path / "a")
    text = " ".join(str(w.message) for w in caught)
    assert f"family M: the factor {factor:g} cannot coarsen" in text, text
    entry = level.report["M"]
    assert entry["layout"] == "multiblock"
    kept = entry["kept_sides"]
    assert kept, entry
    for k in kept:
        m = k["source_intervals"]
        assert factor * m < 1.0
        assert k["intervals"] == max(1, round(m * factor)) >= 1
        assert f"patch {k['patch']} {k['side']}" in text
        assert all(
            lo <= c <= hi
            for lo, c, hi in zip(k["bbox_min"], k["centroid"], k["bbox_max"], strict=True)
        )
    assert any(k["source_intervals"] == 4 for k in kept)
    # The written level, not the report's own formula: each kept side's patch holds
    # that many intervals along the side (a column side spans the patch's rows).
    blocks = entry["blocks"]
    for k in kept:
        along = "rows" if k["side"].endswith("column") else "columns"
        assert blocks[k["patch"] - 1][along] == [k["source_intervals"], k["intervals"]], blocks
    assert all(g.passed for g in level.audit.gates), {g.name: g.verdict for g in level.audit.gates}
    capsys.readouterr()
    assert cli.main(["refine", str(src), str(factor), "--out", str(tmp_path / "b")]) == 0
    err = capsys.readouterr().err
    for stage in ("read plate.obj", "family 1 of 1: M", "grid 1 of 1: M", "writing", "auditing"):
        assert f"] {stage}" in err, err
    assert any(line.startswith("[refine ") for line in err.splitlines())
    level = refine_mesh(src, 0.25, out_dir=tmp_path / "c")
    assert level.report["M"]["kept_sides"] == []
    assert min(min(b["rows"][1], b["columns"][1]) for b in level.report["M"]["blocks"]) == 1


def test_refine_progress_names_each_stage_and_quiet_hides_it(tmp_path, capsys):
    """P0380-BLOCKS (FR-424): refine_mesh reports its stages to ``progress``, in order.

    Called with a callback it receives one line per stage and family, read,
    family, grid, writing and auditing in that order; without one it says
    nothing. The command prints the lines as ``[refine HH:MM:SS +N.N s] ...`` on
    stderr, and ``--log-level quiet`` hides them while the level is written.
    """
    from pyflightstream.run import cli

    sheet = l_sheet()
    mesh = Composite(sheet.verts, {"M": sheet.faces}, np.zeros((0, 3)), {})
    src = write_source(tmp_path / "src", "plate", mesh)
    lines: list[str] = []
    refine_mesh(src, 0.5, out_dir=tmp_path / "a", progress=lines.append)
    stages = ["read plate.obj", "family 1 of 1: M", "grid 1 of 1: M", "writing", "auditing"]
    found = [next(i for i, line in enumerate(lines) if line.startswith(s)) for s in stages]
    assert found == sorted(found), lines
    capsys.readouterr()
    refine_mesh(src, 0.5, out_dir=tmp_path / "b")
    assert "[refine " not in capsys.readouterr().err
    assert (
        cli.main(["refine", str(src), "0.5", "--log-level", "quiet", "--out", str(tmp_path / "q")])
        == 0
    )
    assert "[refine " not in capsys.readouterr().err
    assert (tmp_path / "q" / "plate_R0p5" / "plate_R0p5.obj").is_file()


# ------------------------------------------- grids resampled as one layout (0.44.0)

# P0440-LAYOUT (FR-932, FR-921, PFS-2151): touching grid families are resampled as one layout.
#
# The source is synthetic, a tail in miniature built on one structured surface
# of 13 chordwise by 18 spanwise cells, its numbering shuffled: ``W``, a sheet
# (the stabilizer) over spanwise cells 10 to 18; ``C``, a sheet (the centre
# strip) over 3 to 7; ``J``, two junction strips over 0 to 3 and 7 to 10, one
# family and so a multiblock grid of two patches; and ``T``, a strip of
# triangles beyond W's tip that no factor selects. The trailing edge is the
# chordwise index 0 line of every family. W and J share a station, C and J
# two. Before 0.44.0 only the first of them in the source's order stayed a grid.

NX = 13  # chordwise cells
BANDS = {"W": [(10, 18)], "C": [(3, 7)], "J": [(0, 3), (7, 10)]}
NY = 18
FACTOR = 0.76923


def _point(i, j):
    """Return the surface at the (fractional) indices: chordwise i from the trailing edge."""
    u, v = np.asarray(i, float) / NX, np.asarray(j, float) / NY
    x = 1.0 - u - 0.05 * u**3 + 0.1 * v
    y = 2.0 * v + 0.05 * v**2
    z = 0.06 * np.sin(np.pi * u) * (1.0 - 0.3 * v)
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


def tail(*, strip: bool = True, seed: int = 7) -> Composite:
    """Return the tail: W, C, J (and T beyond W), numbering shuffled, faces row by row."""
    rows = NY + (5 if strip else 0)
    used = [(i, j) for j in range(rows + 1) for i in range(NX + 1)]
    perm = np.random.default_rng(seed).permutation(len(used))
    number = {ij: int(perm[n]) for n, ij in enumerate(used)}
    verts = np.empty((len(used), 3))
    for (i, j), n in number.items():
        verts[n] = _point(i, j)
    families: dict[str, list[list[int]]] = {}
    for name, bands in BANDS.items():
        families[name] = [
            [number[(i, j)], number[(i + 1, j)], number[(i + 1, j + 1)], number[(i, j + 1)]]
            for lo, hi in bands
            for j in range(lo, hi)
            for i in range(NX)
        ]
    if strip:
        tri = []
        for j in range(NY, rows):
            for i in range(NX):
                a, b = number[(i, j)], number[(i + 1, j)]
                c, d = number[(i + 1, j + 1)], number[(i, j + 1)]
                tri += [[a, b, c], [a, c, d]] if (i + j) % 2 else [[a, b, d], [b, c, d]]
        families["T"] = tri
    te = 0.5 * (_point(0, np.arange(NY)) + _point(0, np.arange(1, NY + 1)))
    return Composite(verts, families, te, {})


def _source(tmp_path: Path, refine_toml: str | None = None, **kwargs) -> Path:
    return write_source(tmp_path / "src", "tail", tail(**kwargs), refine_toml=refine_toml)


def _nodes(faces) -> set[int]:
    return {v for f in faces for v in f}


def _centroids(verts, faces) -> np.ndarray:
    return np.array([verts[f].mean(axis=0) for f in faces])


def _in_source_order(level_verts, level_faces, source_verts, source_faces) -> bool:
    """Return whether the level's faces follow their nearest source faces in order (FR-921)."""
    old = _centroids(source_verts, source_faces)
    new = _centroids(level_verts, level_faces)
    nearest = np.argmin(np.linalg.norm(new[:, None, :] - old[None, :, :], axis=2), axis=1)
    return bool(np.all(np.diff(nearest) >= 0))


def _gates(level) -> dict[str, str]:
    return {f"{g.name} {g.family}": g.verdict for g in level.audit.gates}


GROUP = ["W", "C", "J"]


def test_three_touching_grids_stay_grids_in_their_own_families_and_conform(tmp_path):
    """P0440-LAYOUT (FR-932, FR-921, FR-936): W, C and J at 0.76923 are all grids, conforming.

    Each is a grid of its own family that names the other two under
    ``grouped_with``; every curve two of them share holds round(13 f) + 1 = 11
    nodes from both sides; the audit's gates G1 to G5 pass, G5 judged on each
    pair of families that shared nodes in the source; each family's faces follow its own
    source faces in order; T, unchanged, is remeshed only in its band beside W.
    Controls: the order check fails on a family's faces reversed; before
    PFS-2151 C and J were remeshed.
    """
    src = _source(tmp_path)
    level = refine_mesh(src, FACTOR, families=GROUP)
    report = level.report
    for name in GROUP:
        assert report[name]["method"] == "grid", report[name]
        assert report[name]["grouped_with"] == [n for n in GROUP if n != name]
    assert report["J"]["layout"] == "multiblock" and report["W"]["layout"] == "sheet"
    assert report["T"]["method"] == "unchanged" and report["T"]["band"] > 0
    gates = _gates(level)
    assert all(g.passed for g in level.audit.gates), gates
    assert {"G5 W and J", "G5 C and J", "G5 W and T"} <= set(gates), gates
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    for a, b, curves in (("W", "J", 1), ("C", "J", 2)):
        assert len(_nodes(lf[a]) & _nodes(lf[b])) == curves * (round(NX * FACTOR) + 1)
        assert len(_nodes(sf[a]) & _nodes(sf[b])) == curves * (NX + 1)
    assert not _nodes(lf["W"]) & _nodes(lf["C"])
    for name in GROUP:
        assert len(lf[name]) < len(sf[name])
        assert _in_source_order(lv, lf[name], sv, sf[name]), name
    assert not _in_source_order(lv, lf["C"][::-1], sv, sf["C"])


def test_at_factor_one_each_grouped_family_is_its_source_face_for_face(tmp_path):
    """P0440-LAYOUT (FR-921, FR-938): at factor 1 every family is the source, G6 passing.

    Control: the level's faces of J rotated by one vertex differ from the source's.
    """
    src = _source(tmp_path, strip=False)
    level = refine_mesh(src, 1.0)
    sv, sf = read_mesh(src)
    lv, lf = read_mesh(level.obj)
    for name in GROUP:
        assert face_coordinates(lv, lf[name]) == face_coordinates(sv, sf[name]), name
    rotated = [f[1:] + f[:1] for f in lf["J"]]
    assert face_coordinates(lv, rotated) != face_coordinates(sv, sf["J"])
    gates = _gates(level)
    assert all(g.passed for g in level.audit.gates) and "G6 W" in gates, gates


def test_two_grids_giving_a_shared_curve_different_counts_are_refused_naming_both(tmp_path):
    """P0440-LAYOUT (FR-932, FR-925): J at 0.5 beside W and C at 0.76923 is refused.

    A station of 13 intervals would hold round(13 x 0.76923) = 10 intervals on
    one side and round(13 x 0.5) = 6 on the other; the refusal names both
    families, the curve and both counts, and nothing is written. Control: J at
    0.76923 is accepted (the test above).
    """
    toml = (
        f"[families.W]\nfactor = {FACTOR}\n\n[families.C]\nfactor = {FACTOR}\n\n"
        "[families.J]\nfactor = 0.5\n"
    )
    src = _source(tmp_path, toml, strip=False)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src)
    text = str(caught.value)
    assert text.startswith(f"{src} families ") and " and J: the curve they share from node " in text
    assert "of 13 source intervals, would hold 10 intervals as " in text
    assert "and 6 as J is" in text and text.endswith("Nothing was written.")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]


# ------------------------------------------- PFS-2150 chordwise and spanwise on a multiblock


def _pairs(entry) -> list[list[tuple[int, int]]]:
    """Return each patch's (before, after) interval pairs, its two directions sorted."""
    return sorted(sorted([tuple(b["rows"]), tuple(b["columns"])]) for b in entry["blocks"])


def test_the_junction_coarsened_chordwise_only_keeps_its_spanwise_counts(tmp_path):
    """P0440-LAYOUT (FR-915, FR-932, PFS-2150): J at chordwise 0.76923, spanwise 1.

    J's arcs are told chordwise or spanwise from its trailing edge: its
    spanwise arcs (3 intervals across each strip, along the trailing edge)
    keep 3, its chordwise arcs (13 intervals) take 10, and so do the curves it
    shares with W and C at 0.76923; the level conforms and its gates pass.
    Control: J at factor 0.76923 in both directions takes 2 across each strip.
    """
    toml = (
        f"[families.W]\nfactor = {FACTOR}\n\n[families.C]\nfactor = {FACTOR}\n\n"
        f"[families.J]\nchordwise = {FACTOR}\nspanwise = 1\n"
    )
    src = _source(tmp_path, toml, strip=False)
    level = refine_mesh(src)
    report = level.report
    lv, lf = read_mesh(level.obj)
    assert len(_nodes(lf["C"]) & _nodes(lf["J"])) == 2 * (round(NX * FACTOR) + 1)
    # Count the written OBJ's span stations and cells, independently of refine.json.
    for lo, hi in BANDS["J"]:
        cells = [f for f in lf["J"] if _point(0, lo)[1] < lv[f, 1].mean() < _point(0, hi)[1]]
        assert len(cells) == 3 * round(NX * FACTOR)
        assert len(np.unique(np.round(lv[sorted(_nodes(cells)), 1], 12))) == 4
    assert _pairs(report["J"]) == [[(3, 3), (13, 10)]] * 2, report["J"]
    assert _pairs(report["C"]) == [[(4, 3), (13, 10)]]
    assert _pairs(report["W"]) == [[(8, 6), (13, 10)]]
    assert report["J"]["kept_sides"] == []
    assert all(g.passed for g in level.audit.gates), _gates(level)
    both = refine_mesh(src, FACTOR, out_dir=tmp_path / "both").report
    assert _pairs(both["J"]) == [[(3, 2), (13, 10)]] * 2


def _l_with_trailing_edge(shear: float = 0.0) -> Composite:
    """Return the L-shaped multiblock sheet M with its j = 0 row as the trailing edge."""
    sheet = l_sheet()
    verts = sheet.verts.copy()
    verts[:, 0] += shear * verts[:, 1]
    row = sorted((v for v, (i, j) in sheet.place.items() if j == 0), key=lambda v: sheet.place[v])
    te = 0.5 * (verts[row[:-1]] + verts[row[1:]])
    return Composite(verts, {"M": sheet.faces}, te, {})


def test_a_lone_multiblock_takes_chordwise_and_spanwise_from_its_trailing_edge(tmp_path):
    """P0440-LAYOUT (FR-915, PFS-2150): the L-shaped multiblock M at chordwise 0.5, spanwise 1.

    Its trailing edge runs along its rows, so every row arc is spanwise and
    keeps its count, every column arc is chordwise and halves. Control: the
    single factor 0.5 halves both, as before.
    """
    src = write_source(tmp_path / "src", "plate", _l_with_trailing_edge())
    level = refine_mesh(src, chordwise=0.5, spanwise=1.0, out_dir=tmp_path / "a")
    assert _pairs(level.report["M"]) == [
        [(4, 2), (5, 5)],
        [(4, 2), (7, 7)],
        [(6, 3), (7, 7)],
    ], level.report["M"]
    assert all(g.passed for g in level.audit.gates), _gates(level)
    half = refine_mesh(src, 0.5, out_dir=tmp_path / "b").report["M"]
    assert _pairs(half) == [[(4, 2), (5, 2)], [(4, 2), (7, 4)], [(6, 3), (7, 4)]]


def test_a_patch_whose_two_directions_cannot_be_told_apart_is_refused_naming_it(tmp_path):
    """P0440-LAYOUT (FR-915, FR-925, PFS-2150): M sheared until its columns run near the edge.

    Sheared by 1.5, its columns run within 35 degrees of the trailing edge,
    like its rows, so patch 1 has no chordwise direction: chordwise and
    spanwise are refused naming the family and the patch, nothing written.
    Control: the single factor is accepted on the sheared M.
    """
    src = write_source(tmp_path / "src", "plate", _l_with_trailing_edge(shear=1.5))
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, chordwise=0.5, spanwise=1.0, out_dir=tmp_path / "a")
    text = str(caught.value)
    assert text.startswith(f"{src} family M: chordwise and spanwise cannot be told apart on ")
    assert "patch 1 of a multiblock of 3 four-sided patches" in text
    assert "its rows run spanwise and its columns spanwise" in text
    assert text.endswith("Nothing was written.") and not (tmp_path / "a").exists()
    assert refine_mesh(src, 0.5, out_dir=tmp_path / "b").report["M"]["method"] == "grid"


@pytest.mark.parametrize("direction", ["chordwise", "spanwise"])
def test_p0440_multiblock_direction_without_trailing_edge_is_refused(tmp_path, direction):
    mesh = _l_with_trailing_edge()
    mesh.te = np.empty((0, 3))
    src = write_source(tmp_path / "src", "plate", mesh)
    with pytest.raises(InputArtifactError, match="trailing edge, and it has none"):
        refine_mesh(src, **{direction: 0.5}, out_dir=tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    assert refine_mesh(src, 0.5, out_dir=tmp_path / "control").report["M"]["method"] == "grid"


@pytest.mark.parametrize("dy,expected", [(1.0, True), (1.0 - 1e-10, True), (1.0 + 1e-10, False)])
def test_p0440_spanwise_includes_the_45_degree_boundary(dy, expected):
    from pyflightstream.workspace._refine._blocks import runs_spanwise

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, dy, 0.0]])
    edge = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]])
    assert runs_spanwise(vertices, [0, 1], edge) is expected


def test_p0440_union_without_four_sided_layout_joins_none():
    from pyflightstream.workspace._refine._blocks import plan
    from pyflightstream.workspace._refine._config import FamilySpec

    vertices = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [1, -1, 0], [0, -1, 0], [1, 0, 1], [0, 0, 1]],
        dtype=float,
    )
    families = {"A": [[0, 1, 2, 3]], "B": [[0, 1, 4, 5]], "C": [[0, 1, 6, 7]]}
    edges = {name: {(0, 1)} for name in families}
    grids = {
        n: recover_family(vertices, faces, {v for e in edges[n] for v in e})
        for n, faces in families.items()
    }
    assert all(isinstance(grid, Grid) for grid in grids.values())
    layouts, late = plan(
        vertices,
        families,
        grids,
        {n: FamilySpec(factor=2.0) for n in families},
        edges,
        held=(),
        where="three sheets sharing one edge",
    )
    assert layouts == {}
    assert [row[:2] for row in late] == [("B", "A"), ("C", "A")]
    assert all("form no layout" in row[2] for row in late)
