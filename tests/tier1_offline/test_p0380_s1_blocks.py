"""P0380-BLOCKS (FR-424 R6, R7, R9): a smooth tube without trailing edge, recovered and resampled.

A body of revolution (a spinner, a nacelle barrel) holds no trailing edge: its
seam is the lowest source vertex index of its first station, and its sections
are resampled by a periodic spline, so the closed section has no knot at the
seam. The fixtures are synthetic (tests/p0380_mesh_fixtures.py): circles about
the x axis whose radius varies along it, the numbering shuffled.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._grid import (
    Grid,
    not_a_knot,
    periodic,
    recover_grid,
    refine_grid,
)
from tests.p0380_mesh_fixtures import (
    Body,
    Composite,
    body_of_revolution,
    face_coordinates,
    read_mesh,
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
