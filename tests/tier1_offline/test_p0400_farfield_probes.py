"""P0400-PROBEHOME (FR-459, FR-79 amended): probes is the one home of probe geometry.

The layouts moved out of ``cases/workflows/_probes.py`` keep their point
order and their rounding (the expected coordinates are computed here from the
FR-79 rules, with ``math``); a lattice laid in a frame keeps its points; the
inside-the-body check counts, never drops a user's point, and says when it
could not run; and a guard refuses a probe layout defined outside ``probes/``.
"""

from __future__ import annotations

import ast
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyflightstream.probes import build_lattice
from pyflightstream.probes.geometry import points_inside
from pyflightstream.probes.layouts import (
    circle_points,
    farfield_plane,
    lattice_points,
    line_points,
    rectangle_points,
)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "pyflightstream"


@pytest.mark.requirement("FR-459")
@pytest.mark.requirement("FR-79")
def test_p0400_probehome_a_rectangle_runs_v_fastest_with_its_corners():
    """P0400-PROBEHOME (FR-459 R1, FR-79): three declared vertices are three corners."""
    rectangle = SimpleNamespace(
        origin=(0.0, -1.0, 0.0),
        along_u=(0.0, 1.0, 0.0),
        along_v=(0.0, -1.0, 1.0),
        points_u=3,
        points_v=4,
    )
    points = rectangle_points(rectangle, scale=2.0)
    assert len(points) == 12
    assert points[0] == [0.0, -2.0, 0.0]
    assert points[3] == [0.0, -2.0, 2.0]
    assert points[-4] == [0.0, 2.0, 0.0]
    assert points[1] == [0.0, -2.0, round(2.0 / 3.0, 5)]


@pytest.mark.requirement("FR-459")
@pytest.mark.requirement("FR-79")
def test_p0400_probehome_a_circle_has_its_centre_once_and_math_trig():
    """P0400-PROBEHOME (FR-459 R1, FR-79): the centre once; the rim by math.cos and math.sin."""
    circle = SimpleNamespace(
        center=(1.0, 0.0, 0.0),
        normal=(1.0, 0.0, 0.0),
        radius=0.5,
        points_radial=3,
        points_azimuth=7,
    )
    points = circle_points(circle, scale=3.0)
    assert len(points) == 1 + 2 * 7
    assert points[0] == [3.0, 0.0, 0.0]
    # The least aligned world axis of +x is y: first = y x n = -z, second = n x first = y.
    angle = 2.0 * math.pi * 3 / 7
    expected = [
        round((1.0 + 0.5 * (math.cos(angle) * 0.0 + math.sin(angle) * 0.0)) * 3.0, 5),
        round((0.0 + 0.5 * (math.cos(angle) * 0.0 + math.sin(angle) * 1.0)) * 3.0, 5),
        round((0.0 + 0.5 * (math.cos(angle) * -1.0 + math.sin(angle) * 0.0)) * 3.0, 5),
    ]
    assert points[-4] == expected


@pytest.mark.requirement("FR-459")
def test_p0400_probehome_a_line_includes_both_ends():
    """P0400-PROBEHOME (FR-459 R1): the line sampling of FR-77, rounded as the script is."""
    points = line_points((0.0, 0.0, 0.0), end=(1.0, 2.0, 3.0), points=4, scale=1.5)
    assert points[0] == [0.0, 0.0, 0.0] and points[-1] == [1.5, 3.0, 4.5]
    assert points[1] == [0.5, 1.0, 1.5]


@pytest.mark.requirement("FR-459")
@pytest.mark.parametrize(("axis", "order"), [("X", (0, 1, 2)), ("Y", (1, 2, 0)), ("Z", (2, 0, 1))])
def test_p0400_probehome_a_lattice_is_laid_along_its_frame_axis_right_handed(axis, order):
    """P0400-PROBEHOME (FR-459 R2): build_lattice's points, carried onto the frame cyclically."""
    lattice = build_lattice(tip_radius=0.8, stations=(-1.0, 1.0), n_r=4, n_psi=8)
    local = lattice.dimensional_points()
    laid = lattice_points(lattice, axis=axis)
    assert laid.shape == local.shape
    for source, target in enumerate(order):
        assert np.array_equal(laid[:, target], local[:, source])
    e = np.eye(3)
    assert np.cross(e[order[0]], e[order[1]]) @ e[order[2]] == 1.0


@pytest.mark.requirement("FR-459")
@pytest.mark.requirement("FR-453")
def test_p0400_probehome_the_farfield_plane_is_normal_to_the_free_stream():
    """P0400-PROBEHOME (FR-453 R4): normal to each point's free stream, uniform, centred."""
    alpha = math.radians(8.0)
    direction = (math.cos(alpha), 0.0, math.sin(alpha))
    plane = farfield_plane(
        (2.0, 0.0, 0.0),
        direction=direction,
        distance=2.5,
        half_width=7.5,
        half_height=5.0,
        spacing=0.1,
    )
    assert len(plane.y) == 151 and len(plane.z) == 101
    assert plane.points.shape == (151 * 101, 3)
    offsets = plane.points - plane.points.mean(axis=0)
    assert np.allclose(offsets @ plane.axes[0], 0.0, atol=1e-9)
    assert np.allclose(plane.axes[0], direction)
    assert np.allclose(plane.axes @ plane.axes.T, np.eye(3), atol=1e-12)
    assert np.allclose(
        plane.points.mean(axis=0), np.array([2.0, 0.0, 0.0]) + 2.5 * np.array(direction)
    )
    level = farfield_plane(
        (0, 0, 0), direction=(1, 0, 0), distance=1, half_width=1, half_height=1, spacing=0.5
    )
    assert np.allclose(level.axes, np.eye(3))


def _box(path: Path, *, closed: bool = True) -> Path:
    vertices = [
        (-1, -1, -1),
        (1, -1, -1),
        (1, 1, -1),
        (-1, 1, -1),
        (-1, -1, 1),
        (1, -1, 1),
        (1, 1, 1),
        (-1, 1, 1),
    ]
    faces = [
        (1, 3, 2),
        (1, 4, 3),
        (5, 6, 7),
        (5, 7, 8),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 4, 8),
        (3, 8, 7),
        (4, 1, 5),
        (4, 5, 8),
    ]
    if not closed:
        faces = faces[:-2]
    lines = [f"v {x} {y} {z}" for x, y, z in vertices] + [f"f {a} {b} {c}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.requirement("FR-459")
def test_p0400_probehome_the_inside_check_counts_and_drops_nothing(tmp_path):
    """P0400-PROBEHOME (FR-459 R4): the count and the first points; every point is kept."""
    mesh = _box(tmp_path / "box.obj")
    points = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.5, 0.5, 0.5], [0.0, 4.0, 0.0]])
    report = points_inside(points, mesh_path=mesh)
    assert report.checked and report.reason is None
    assert report.inside.tolist() == [True, False, True, False]
    assert report.count == 2
    assert report.first(points) == [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5)]
    assert len(report.inside) == len(points)


@pytest.mark.requirement("FR-459")
def test_p0400_probehome_an_open_mesh_is_not_checked_and_not_refused(tmp_path):
    """P0400-PROBEHOME (FR-459 R4): the report says why, nothing is flagged, nothing raised."""
    mesh = _box(tmp_path / "open.obj", closed=False)
    report = points_inside(np.zeros((2, 3)), mesh_path=mesh)
    assert not report.checked and "not watertight" in report.reason
    assert report.count == 0


@pytest.mark.requirement("FR-459")
def test_p0400_probehome_a_missing_spatial_index_is_not_checked(tmp_path):
    """P0400-PROBEHOME (FR-459 R4): without the [geom] extra the plan warns, never refuses.

    Run in a fresh interpreter where scipy and rtree cannot be imported, which
    is the installation without the extra.
    """
    mesh = _box(tmp_path / "box.obj")
    program = (
        "import sys\n"
        "sys.modules['rtree'] = None\n"
        "sys.modules['scipy'] = None\n"
        "import numpy as np\n"
        "from pyflightstream.probes.geometry import points_inside\n"
        f"report = points_inside(np.zeros((2, 3)), mesh_path={str(mesh)!r})\n"
        "print(report.checked, report.reason)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.startswith("False") and "[geom]" in done.stdout


_LAYOUT_NAME = ("rectangle_points", "circle_points", "line_points", "lattice_points")


def layout_definitions(root: Path) -> list[str]:
    """Return every probe-layout function defined outside ``probes/`` (FR-459 R3)."""
    found = []
    for path in sorted(root.rglob("*.py")):
        if "probes" in path.relative_to(root).parts[:1]:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.lstrip("_") in _LAYOUT_NAME:
                found.append(f"{path.relative_to(root).as_posix()}:{node.name}")
    return found


@pytest.mark.requirement("FR-459")
def test_p0400_probehome_no_module_outside_probes_defines_a_layout(tmp_path):
    """P0400-PROBEHOME (FR-459 R3): the guard, with its planted control."""
    assert not layout_definitions(SRC)
    planted = tmp_path / "pkg" / "cases"
    planted.mkdir(parents=True)
    (planted / "shapes.py").write_text("def _rectangle_points(r, s):\n    return []\n", "utf-8")
    assert layout_definitions(tmp_path / "pkg") == ["cases/shapes.py:_rectangle_points"]
