"""P0380-REFINE (FR-424): the structured grid family, recovered and resampled.

Every fixture is built here from an analytic surface whose coordinates are
cubic polynomials of the grid indices (a cambered, tapered, swept wing with
clustering toward the leading edge and the tip, and a cambered thin sheet
with clustering at both edges). The not-a-knot spline reproduces a cubic
exactly, so the level's nodes are known in advance: each level node is
matched to the analytic node of its new indices, which proves the counts and
the knots and gives every node its (station, chordwise) place for the face
order checks. The vertex numbering of every source is shuffled, so nothing
is read from the file's vertex order.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

import pyflightstream
from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._refine._geometry import GRID_SURFACE_DISTANCE
from pyflightstream.workspace._refine._grid import (
    Grid,
    check_factors,
    not_a_knot,
    recover_grid,
    refine_grid,
)

CELL_QUAD = (((0, 0), (0, 1), (1, 1), (1, 0)),)
CELL_DIAG = {
    0: (((0, 0), (0, 1), (1, 1)), ((0, 0), (1, 1), (1, 0))),
    1: (((0, 0), (0, 1), (1, 0)), ((0, 1), (1, 1), (1, 0))),
}


# ------------------------------------------------------------------ fixtures


def _wing(u, v):
    """Return a closed cambered section around u (TE at 0 and 1) on a straight tapered planform."""
    y = 2.0 * (1.5 * v - 0.5 * v**3) + 0.0 * u
    chord, xle = 1.0 - 0.2 * y, 0.15 * y
    x = xle + chord * (2.0 * u - 1.0) ** 2
    z = chord * (0.4 * u * (1.0 - u) * (1.0 - 2.0 * u) + 0.08 * u * (1.0 - u))
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


def _sheet(u, v):
    """Return a cambered thin sheet from the trailing edge (u = 0) to the leading edge (u = 1)."""
    y = 2.0 * (1.5 * v - 0.5 * v**3) + 0.0 * u
    chord, xle = 1.0 - 0.2 * y, 0.15 * y
    x = xle + chord * (1.0 - (3.0 * u**2 - 2.0 * u**3))
    z = chord * 0.1 * u * (1.0 - u)
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


@dataclass
class Fixture:
    """A synthetic grid family, its source faces and what the test knows of its grid."""

    name: str
    wrap: bool
    stations: int
    nodes: int
    ends: tuple[str, str]
    diag: dict[int, int] | None  # chordwise cell -> diagonal, None for quadrilaterals
    verts: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    faces: list[list[int]] = field(default_factory=list)
    te: set[int] = field(default_factory=set)
    place: dict[int, tuple[int, int]] = field(default_factory=dict)  # vertex -> (k, i)
    pole: int | None = None
    lateral: int = 0

    @property
    def le(self) -> int:
        """Return the leading edge's chordwise index."""
        return self.nodes // 2 if self.wrap else self.nodes - 1

    def surface(self, s, t):
        """Return the analytic nodes at chordwise index s and station index t."""
        u = np.asarray(s, float) / (self.nodes if self.wrap else self.nodes - 1)
        v = np.asarray(t, float) / (self.stations - 1)
        return (_wing if self.wrap else _sheet)(u[None, :], v[:, None])

    @property
    def size(self) -> float:
        """Return the diagonal of the bounding box."""
        return float(np.linalg.norm(self.verts.max(axis=0) - self.verts.min(axis=0)))


def _cell_faces(gid, k, i, n, diag):
    """Return the source faces of one lateral cell (k-major, i ascending)."""
    j = (i + 1) % n
    corners = {(0, 0): gid[k, i], (0, 1): gid[k, j], (1, 1): gid[k + 1, j], (1, 0): gid[k + 1, i]}
    template = CELL_QUAD if diag is None else CELL_DIAG[diag[i]]
    return [[int(corners[o]) for o in face] for face in template]


def _caps(fx, gid, rotate):
    """Return the zipper caps of both ends, each face rotated by `rotate`."""
    out = []
    n, h = fx.nodes, fx.le
    for k in (0, fx.stations - 1):
        r = [int(x) for x in gid[k]]
        cap = [[r[0], r[1], r[n - 1]]]
        cap += [[r[i], r[i + 1], r[n - i - 1], r[n - i]] for i in range(1, h - 1)]
        cap.append([r[h - 1], r[h], r[h + 1]])
        cap = [f[::-1] for f in cap] if k == 0 else cap
        out += [f[rotate:] + f[:rotate] for f in cap]
    return out


def _build(fx: Fixture, *, shuffle_faces=False, cap_rotate=1, seed=3) -> Fixture:
    """Build the source mesh of a fixture, its vertex numbering shuffled."""
    k_count, n = fx.stations, fx.nodes
    pts = fx.surface(np.arange(n), np.arange(k_count)).reshape(-1, 3)
    gid = np.arange(k_count * n).reshape(k_count, n)
    faces = []
    for k in range(k_count - 1):
        for i in range(n if fx.wrap else n - 1):
            faces += _cell_faces(gid, k, i, n, fx.diag)
    fx.lateral = len(faces)
    if fx.ends[1] == "pole":
        tip = fx.surface(np.array([fx.le]), np.array([k_count - 1]))[0, 0] * [1, 1, 0]
        pts = np.vstack([pts, (tip + [0.5 * 0.6, 0.02, 0.0])[None, :]])
        pole = len(pts) - 1
        ring = [int(x) for x in gid[-1]]
        faces += [[pole, ring[i], ring[(i + 1) % n]] for i in range(n)]
    if "zipper" in fx.ends:
        faces += _caps(fx, gid, cap_rotate)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(pts))
    fx.verts = np.empty_like(pts)
    fx.verts[perm] = pts
    fx.faces = [[int(perm[v]) for v in f] for f in faces]
    if shuffle_faces:
        fx.faces = [fx.faces[j] for j in rng.permutation(len(fx.faces))]
    fx.place = {int(perm[gid[k, i]]): (k, i) for k in range(k_count) for i in range(n)}
    fx.te = {int(perm[gid[k, 0]]) for k in range(k_count)}
    fx.pole = int(perm[len(pts) - 1]) if fx.ends[1] == "pole" else None
    return fx


NODES = 24  # nodes around a tube section, even for the zipper caps
MIRRORED = {i: (0 if i < NODES // 2 else 1) for i in range(NODES)}


def tube_pole_triangles():
    """Return a wing tube of split quadrilaterals, mirrored diagonals, open root, pole tip."""
    return _build(Fixture("tube-pole-triangles", True, 9, NODES, ("open", "pole"), MIRRORED))


def tube_pole_quads():
    """Return a wing tube of quadrilaterals, open root, pole tip."""
    return _build(Fixture("tube-pole-quads", True, 9, NODES, ("open", "pole"), None))


def tube_zipper():
    """Return a blade tube of quadrilaterals closed by a zipper cap at each end."""
    return _build(Fixture("tube-zipper", True, 9, NODES, ("zipper", "zipper"), None))


def sheet_quads():
    """Return a thin cambered sheet of quadrilaterals."""
    return _build(Fixture("sheet", False, 9, 19, ("edge", "edge"), None))


FIXTURES = [tube_pole_triangles, tube_pole_quads, tube_zipper, sheet_quads]


def _recovered(fx: Fixture) -> Grid:
    grid = recover_grid(fx.verts, fx.faces, fx.te)
    assert isinstance(grid, Grid), grid
    return grid


# ------------------------------------------------------------------ the oracle


def _params(fx: Fixture, chordwise: float, spanwise: float):
    """Return the new chordwise and station indices of FR-424 R6: round(f m) per stretch."""
    t = np.linspace(0, fx.stations - 1, round(spanwise * (fx.stations - 1)) + 1)
    if not fx.wrap:
        return np.linspace(0, fx.nodes - 1, round(chordwise * (fx.nodes - 1)) + 1), t
    h, n = fx.le, fx.nodes
    n1 = round(chordwise * h)
    n2 = n1 if "zipper" in fx.ends else round(chordwise * (n - h))
    s = np.concatenate([np.linspace(0, h, n1 + 1)[:-1], h + np.linspace(0, n - h, n2 + 1)[:-1]])
    return s, t


def _places(fx: Fixture, level, chordwise: float, spanwise: float):
    """Match every level node to its analytic node; return node -> (k', i') and the shape."""
    s, t = _params(fx, chordwise, spanwise)
    expected = fx.surface(s, t)
    flat = expected.reshape(-1, 3)
    grid_points = level.points[:-1] if fx.pole is not None else level.points
    d = np.linalg.norm(grid_points[:, None, :] - flat[None, :, :], axis=2)
    best = d.argmin(axis=1)
    assert float(d.min(axis=1).max()) < 1e-9 * fx.size
    assert len(grid_points) == len(flat) and len(set(best.tolist())) == len(flat)
    shape = expected.shape[:2]
    return {p: divmod(int(b), shape[1]) for p, b in enumerate(best)}, shape


def _expected_lateral(fx: Fixture, where, shape, chordwise: float):
    """Return the lateral faces in the source's sweep: k-major, i ascending, source templates."""
    node = {v: p for p, v in where.items()}
    kp, nc = shape
    s, _ = _params(fx, chordwise, 1.0)
    ends = np.append(s, fx.nodes) if fx.wrap else s
    old_i = np.floor(0.5 * (ends[:-1] + ends[1:])).astype(int)
    out = []
    for k in range(kp - 1):
        for i in range(nc if fx.wrap else nc - 1):
            j = (i + 1) % nc
            corner = {(0, 0): (k, i), (0, 1): (k, j), (1, 1): (k + 1, j), (1, 0): (k + 1, i)}
            source_i = int(old_i[i]) % fx.nodes if fx.wrap else min(int(old_i[i]), fx.nodes - 2)
            template = CELL_QUAD if fx.diag is None else CELL_DIAG[fx.diag[source_i]]
            out += [[node[corner[o]] for o in face] for face in template]
    return out


def _sweep_holds(fx, level, where, shape, chordwise, faces=None):
    """Return whether the level's lateral faces are the source's sweep, face for face."""
    faces = level.faces if faces is None else faces
    expected = _expected_lateral(fx, where, shape, chordwise)
    return faces[: len(expected)] == expected


def _cell_runs(faces, where, count):
    """Group the first `count` faces into runs of one cell each, keyed by the cell."""
    runs: list[tuple[tuple[int, int], list[list[int]]]] = []
    for f in faces[:count]:
        places = [where[v] for v in f]
        key = (min(k for k, _ in places), min(i for _, i in places))
        if runs and runs[-1][0] == key:
            runs[-1][1].append(f)
        else:
            runs.append((key, [f]))
    return runs


def _reverse_sweep(faces, where, count):
    """Control writer: the cells in reverse order, each cell's faces unchanged."""
    runs = _cell_runs(faces, where, count)
    return [f for _, run in runs[::-1] for f in run] + faces[count:]


def _transpose_sweep(faces, where, count):
    """Control writer: the cells column by column instead of row by row."""
    runs = sorted(_cell_runs(faces, where, count), key=lambda r: (r[0][1], r[0][0]))
    return [f for _, run in runs for f in run] + faces[count:]


def _rotate_faces(faces):
    """Control writer: every face starts one vertex later."""
    return [f[1:] + f[:1] for f in faces]


def _distance_to_surface(points, verts, faces):
    """Return each point's distance to the source's faces (fanned into triangles)."""
    tri = np.array([[f[0], f[k], f[k + 1]] for f in faces for k in range(1, len(f) - 1)])
    a, b, c = verts[tri[:, 0]], verts[tri[:, 1]], verts[tri[:, 2]]
    out = np.empty(len(points))
    for n0 in range(0, len(points), 64):
        p = points[n0 : n0 + 64, None, :]
        best = np.full(p.shape[0], np.inf)
        for x, y in ((a, b), (b, c), (c, a)):
            e = y - x
            t = np.clip(((p - x) * e).sum(-1) / (e * e).sum(-1), 0.0, 1.0)
            best = np.minimum(best, np.linalg.norm(p - (x + t[..., None] * e), axis=2).min(1))
        normal = np.cross(b - a, c - a)
        normal /= np.linalg.norm(normal, axis=1)[:, None]
        height = ((p - a) * normal).sum(-1)
        q = p - height[..., None] * normal
        inside = np.ones(height.shape, bool)
        for x, y in ((a, b), (b, c), (c, a)):
            inside &= (np.cross(y - x, q - x) * normal).sum(-1) >= -1e-15
        plane = np.where(inside, np.abs(height), np.inf).min(axis=1)
        out[n0 : n0 + 64] = np.minimum(best, plane)
    return out


# ------------------------------------------------------------------ the tests


@pytest.mark.parametrize("make", FIXTURES, ids=lambda m: m.__name__)
def test_factor_one_is_the_source_in_coordinates_and_order(make):
    """P0380-REFINE (FR-424 R7): at factor 1 a grid's faces equal the source's, in order.

    Coordinates face for face and vertex for vertex, so the start vertex of
    every face is checked too. Control: each control writer fails the check.
    """
    fx = make()
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=1.0, spanwise=1.0)

    def same(faces):
        return len(faces) == len(fx.faces) and all(
            np.array_equal(level.points[f], fx.verts[g])
            for f, g in zip(faces, fx.faces, strict=True)
        )

    assert same(level.faces)
    assert {tuple(p) for p in level.points} == {tuple(p) for p in fx.verts}
    assert not same(_rotate_faces(level.faces))
    assert not same(level.faces[::-1])


@pytest.mark.parametrize("make", FIXTURES, ids=lambda m: m.__name__)
def test_factor_two_doubles_the_intervals_keeps_the_knots_on_the_surface(make):
    """P0380-REFINE (FR-424 R6): factor 2 gives 2m by 2n intervals, knots exact, nodes on it.

    Every source node is a level node bit for bit (the trailing edge, the
    leading edge and the end stations among them), and every level node lies
    within 1e-3 of the size from the source's faces. Control: a node moved by
    2e-3 of the size off the surface is caught.
    """
    fx = make()
    grid = _recovered(fx)
    level = refine_grid(fx.verts, fx.faces, grid, chordwise=2.0, spanwise=2.0)
    where, shape = _places(fx, level, 2.0, 2.0)
    m_chord, m_span = grid.intervals
    assert level.report["intervals"] == {
        "chordwise": [m_chord, 2 * m_chord],
        "spanwise": [m_span, 2 * m_span],
    }
    assert shape == (2 * m_span + 1, 2 * m_chord + (0 if fx.wrap else 1))
    held = {tuple(p) for p in level.points}
    assert all(tuple(p) in held for p in fx.verts)
    distance = _distance_to_surface(level.points, fx.verts, fx.faces)
    assert float(distance.max()) <= GRID_SURFACE_DISTANCE * fx.size
    off = level.points.copy()
    off[len(off) // 3] += [0.0, 0.0, 2e-3 * fx.size]
    assert _distance_to_surface(off, fx.verts, fx.faces).max() > GRID_SURFACE_DISTANCE * fx.size


@pytest.mark.parametrize("make", FIXTURES, ids=lambda m: m.__name__)
def test_factor_two_is_written_in_the_source_sweep(make):
    """P0380-REFINE (FR-424 R7): the level keeps the source's start cell, directions, cell order.

    Controls: a writer that sweeps the cells in reverse, one that transposes
    the index directions and one that rotates each face's vertices all fail.
    """
    fx = make()
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=2.0, spanwise=2.0)
    where, shape = _places(fx, level, 2.0, 2.0)
    count = len(_expected_lateral(fx, where, shape, 2.0))
    assert level.report["order"] == "sweep"
    assert _sweep_holds(fx, level, where, shape, 2.0)
    for control in (
        _reverse_sweep(level.faces, where, count),
        _transpose_sweep(level.faces, where, count),
        _rotate_faces(level.faces),
    ):
        assert not _sweep_holds(fx, level, where, shape, 2.0, control)


def _diagonals(fx, level, where):
    """Return the diagonal each new split cell uses, keyed by the cell."""
    found = {}
    faces = level.faces[: 4 * fx.lateral]
    for a, b in zip(faces[0::2], faces[1::2], strict=True):
        (k0, i0), (_, i1) = sorted(where[v] for v in set(a) & set(b))
        rising = (i1 - i0) % (2 * fx.nodes) == 1
        found[(k0, i0 if rising else i1)] = 0 if rising else 1
    return found


def test_each_new_cell_is_split_along_its_source_cells_diagonal():
    """P0380-REFINE (FR-424 R6): a mirrored split is kept cell by cell at factor 2.

    The fixture splits the upper half of the section along one diagonal and
    the lower half along the other. Control: the same wing split along one
    diagonal everywhere does not match the mirrored split.
    """
    fx = tube_pole_triangles()
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=2.0, spanwise=2.0)
    got = _diagonals(fx, level, _places(fx, level, 2.0, 2.0)[0])
    assert len(got) == 2 * fx.lateral  # one entry per new cell, two triangles each
    assert all(d == MIRRORED[i // 2] for (_, i), d in got.items())
    plain = _build(
        Fixture(
            "tube-one-diagonal", True, 9, NODES, ("open", "pole"), dict.fromkeys(range(NODES), 0)
        )
    )
    level = refine_grid(plain.verts, plain.faces, _recovered(plain), chordwise=2.0, spanwise=2.0)
    other = _diagonals(plain, level, _places(plain, level, 2.0, 2.0)[0])
    assert set(other.values()) == {0}
    assert not all(d == MIRRORED[i // 2] for (_, i), d in other.items())


@pytest.mark.parametrize(
    ("chordwise", "spanwise"), [(0.5, 0.5), (2.0, 1.0), (1.0, 2.0), (1.5, 0.7)]
)
def test_counts_round_each_direction_and_the_knots_stay(chordwise, spanwise):
    """P0380-REFINE (FR-424 R1, R6): round(f m) intervals per direction; TE, LE, ends are knots.

    Factor 0.5, each direction separately, and uneven factors. The trailing
    edge, the leading edge and the two end stations keep the source's nodes
    bit for bit. Control: the source counts are not the level's.
    """
    fx = tube_pole_quads()
    grid = _recovered(fx)
    level = refine_grid(fx.verts, fx.faces, grid, chordwise=chordwise, spanwise=spanwise)
    where, shape = _places(fx, level, chordwise, spanwise)
    s, t = _params(fx, chordwise, spanwise)
    assert shape == (len(t), len(s))
    assert level.report["intervals"]["spanwise"] == [8, round(8 * spanwise)]
    assert level.report["intervals"]["chordwise"][1] == len(s)
    node = {v: p for p, v in where.items()}
    source = {place: v for v, place in fx.place.items()}
    le_new = int(np.nonzero(s == fx.le)[0][0])
    for k_old, k_new in ((0, 0), (fx.stations - 1, len(t) - 1)):
        for i_new, i_old in enumerate(s):
            if i_old == int(i_old):
                assert np.array_equal(
                    level.points[node[(k_new, i_new)]], fx.verts[source[(k_old, int(i_old))]]
                )
    for k_new, k_old in enumerate(t):
        if k_old == int(k_old):
            for i_new, i_old in ((0, 0), (le_new, fx.le)):
                assert np.array_equal(
                    level.points[node[(k_new, i_new)]], fx.verts[source[(int(k_old), i_old)]]
                )
    assert (chordwise, spanwise) == (1.0, 1.0) or shape != (fx.stations, fx.nodes)


@pytest.mark.parametrize("direction", ["chordwise", "spanwise"])
def test_a_factor_below_one_over_m_is_refused(direction):
    """P0380-REFINE (FR-424 R1): a factor below 1/m is refused naming family, direction, value.

    Exactly 1/m is accepted and leaves one interval (the control); zero,
    negative, infinite and not-a-number factors are refused the same way.
    """
    fx = tube_pole_quads()
    grid = _recovered(fx)
    m = dict(zip(("chordwise", "spanwise"), grid.intervals, strict=True))[direction]
    factors = {"chordwise": 1.0, "spanwise": 1.0}
    for bad in (0.99 / m, 0.0, -1.0, float("inf"), float("nan")):
        factors[direction] = bad
        with pytest.raises(InputArtifactError) as caught:
            check_factors(grid, "Wing", **factors)
        text = str(caught.value)
        assert "family Wing" in text and direction in text and f"1/{m}" in text
        assert text.endswith("Nothing was written.")
        with pytest.raises(InputArtifactError):
            refine_grid(fx.verts, fx.faces, grid, family="Wing", **factors)
    factors[direction] = 1.0 / m
    check_factors(grid, "Wing", **factors)
    level = refine_grid(fx.verts, fx.faces, grid, **factors)
    assert level.report["intervals"][direction][1] >= 1


@pytest.mark.parametrize("make", [tube_pole_quads, tube_zipper], ids=lambda m: m.__name__)
def test_the_end_faces_start_on_the_source_role(make):
    """P0380-REFINE (FR-424 R7): pole fans and zipper caps start where the source's start.

    The source's fan triangles start at the pole and its cap faces start one
    vertex after the cap builder's first; the level at factor 2 keeps both.
    Control: the level's end faces rotated by one vertex fail.
    """
    fx = make()
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=2.0, spanwise=2.0)
    where, shape = _places(fx, level, 2.0, 2.0)
    pole_new = len(level.points) - 1 if fx.pole is not None else None
    h_new = int(np.nonzero(_params(fx, 2.0, 2.0)[0] == fx.le)[0][0])

    def first_roles(faces, place, pole, h, last):
        roles = set()
        for f in faces:
            if pole is not None and pole in f:
                roles.add(("fan", "P" if f[0] == pole else "ring"))
                continue
            spots = [place.get(v) for v in f]
            if None in spots or len({k for k, _ in spots}) != 1 or spots[0][0] not in (0, last):
                continue
            p = [i for _, i in spots]
            upper = sorted(x for x in p if 0 < x < h)
            role = "TE" if p[0] == 0 else "LE" if p[0] == h else "U" if p[0] < h else "L"
            if len(f) == 4 and role == "U":
                role = "U0" if p[0] == upper[0] else "U1"
            roles.add((spots[0][0] == 0, len(f), role))
        return roles

    source = first_roles(fx.faces, fx.place, fx.pole, fx.le, fx.stations - 1)
    got = first_roles(level.faces, where, pole_new, h_new, shape[0] - 1)
    assert source and got == source
    count = len(_expected_lateral(fx, where, shape, 2.0))
    rotated = level.faces[:count] + _rotate_faces(level.faces[count:])
    assert first_roles(rotated, where, pole_new, h_new, shape[0] - 1) != source


def test_a_source_not_in_one_sweep_takes_the_nearest_source_face_order():
    """P0380-REFINE (FR-424 R7): faces follow their nearest source face, starting like it.

    The source's faces are shuffled, so they form no sweep. At factor 1 the
    level is still the source in coordinates and order; at factor 2 the
    positions of the nearest source faces never go back, and every face starts
    at the vertex nearest its source face's first vertex. Controls: the level
    reversed, and its faces rotated, fail.
    """
    fx = _build(
        Fixture("tube-shuffled", True, 9, NODES, ("open", "pole"), MIRRORED), shuffle_faces=True
    )
    grid = _recovered(fx)
    same = refine_grid(fx.verts, fx.faces, grid, chordwise=1.0, spanwise=1.0)
    assert same.report["order"] == "nearest"
    assert all(
        np.array_equal(same.points[f], fx.verts[g])
        for f, g in zip(same.faces, fx.faces, strict=True)
    )
    level = refine_grid(fx.verts, fx.faces, grid, chordwise=2.0, spanwise=2.0)
    centroids = np.array([fx.verts[g].mean(axis=0) for g in fx.faces])

    def nearest_order_holds(faces):
        mine = np.array([level.points[f].mean(axis=0) for f in faces])
        j = np.linalg.norm(mine[:, None] - centroids[None], axis=2).argmin(axis=1)
        if np.any(np.diff(j) < 0):
            return False
        for f, k in zip(faces, j, strict=True):
            first = fx.verts[fx.faces[k][0]]
            if int(np.argmin(np.linalg.norm(level.points[f] - first, axis=1))) != 0:
                return False
        return True

    assert nearest_order_holds(level.faces)
    assert not nearest_order_holds(level.faces[::-1])
    assert not nearest_order_holds(_rotate_faces(level.faces))


def test_recovery_reads_the_connectivity_and_names_why_it_fails():
    """P0380-REFINE (FR-424 R9): a grid is recovered from connectivity, or the reason is named.

    Each fixture's numbering is shuffled and its layout and ends are still
    found. Planted bad inputs: a face removed, no trailing-edge vertex, and
    trailing-edge vertices that are no grid line each return their reason.
    """
    for make, layout, ends in (
        (tube_pole_triangles, "tube", ("open", "pole")),
        (tube_pole_quads, "tube", ("open", "pole")),
        (tube_zipper, "tube", ("zipper", "zipper")),
        (sheet_quads, "sheet", ("edge", "edge")),
    ):
        fx = make()
        grid = _recovered(fx)
        assert (grid.layout, grid.ends) == (layout, ends)
        assert grid.i_le == fx.le
        assert grid.describe().startswith(f"a {layout} of {fx.stations} stations")
    fx = tube_pole_quads()
    holed = recover_grid(fx.verts, fx.faces[:40] + fx.faces[41:], fx.te)
    assert isinstance(holed, str) and holed
    assert recover_grid(fx.verts, fx.faces, set()) == "no trailing-edge vertex on the end loop"
    sheet = sheet_quads()
    stray = set(list(sheet.place)[:5])
    assert recover_grid(sheet.verts, sheet.faces, stray) == "the trailing edge is not a grid line"


def test_the_grid_runs_with_scipy_and_rtree_unimportable():
    """P0380-REFINE (FR-424 R10): the grid module imports neither scipy nor rtree.

    A fresh interpreter makes both unimportable before importing the module,
    then recovers and refines a grid and finds neither loaded.
    """
    script = "\n".join(
        [
            "import sys",
            "sys.modules['scipy'] = None",
            "sys.modules['rtree'] = None",
            "import numpy as np",
            "from pyflightstream.workspace._refine._grid import recover_grid, refine_grid",
            "k, n = 5, 7",
            "u, v = np.meshgrid(np.arange(n) / (n - 1), np.arange(k) / (k - 1))",
            "pts = np.stack([1 - u, 2 * v, 0.1 * u * (1 - u)], axis=-1).reshape(-1, 3)",
            "g = np.arange(k * n).reshape(k, n)",
            "faces = [[int(g[a, b]), int(g[a, b + 1]), int(g[a + 1, b + 1]), int(g[a + 1, b])]",
            "         for a in range(k - 1) for b in range(n - 1)]",
            "grid = recover_grid(pts, faces, set(g[:, 0].tolist()))",
            "level = refine_grid(pts, faces, grid, chordwise=2.0, spanwise=2.0)",
            "loaded = [m for m in sys.modules if m.split('.')[0] in ('scipy', 'rtree')",
            "          and sys.modules[m] is not None]",
            "print(len(level.faces), loaded)",
        ]
    )
    src = str(Path(pyflightstream.__file__).resolve().parents[1])
    env = dict(os.environ, PYTHONPATH=src + os.pathsep + os.environ.get("PYTHONPATH", ""))
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["96", "[]"]


def test_the_spline_reproduces_a_cubic_and_keeps_its_knots():
    """P0380-REFINE (FR-424 R6): the index-space spline is exact on a cubic and at the knots.

    A not-a-knot spline reproduces any cubic. Control: a linear interpolation
    through the same nodes misses it.
    """
    m = 12
    x = np.arange(m + 1, dtype=float)
    cubic = np.stack([0.3 * x**3 - 2 * x**2 + x - 4, -0.01 * x**3 + 5.0], axis=1)
    p = np.linspace(0, m, 97)
    want = np.stack([0.3 * p**3 - 2 * p**2 + p - 4, -0.01 * p**3 + 5.0], axis=1)
    got = not_a_knot(cubic, p)
    assert float(np.abs(got - want).max()) < 1e-9
    knots = not_a_knot(cubic, x)
    assert np.array_equal(knots, cubic)
    noisy = np.random.default_rng(1).normal(size=(m + 1, 3))
    assert np.array_equal(not_a_knot(noisy, x), noisy)
    natural = np.interp(p, x, cubic[:, 0])
    assert float(np.abs(natural - want[:, 0]).max()) > 1e-3


def test_the_spline_equals_scipys_not_a_knot_where_scipy_is_installed():
    """P0380-REFINE (FR-424 R6, R10): the numpy spline is scipy's not-a-knot to 1e-12.

    Runs only where scipy is installed (the geometry extra); the module itself
    never imports it. Control: scipy's natural spline differs.
    """
    interpolate = pytest.importorskip("scipy.interpolate")
    rng = np.random.default_rng(7)
    for m in (3, 4, 5, 8, 33, 200):
        y = rng.normal(size=(m + 1, 2, 3)) * 10
        p = np.sort(np.concatenate([rng.uniform(0, m, 300), np.arange(m + 1)]))
        spline = interpolate.CubicSpline(np.arange(m + 1), y, axis=0, bc_type="not-a-knot")
        assert float(np.abs(not_a_knot(y, p) - spline(p)).max()) < 1e-12
        natural = interpolate.CubicSpline(np.arange(m + 1), y, axis=0, bc_type="natural")
        assert float(np.abs(not_a_knot(y, p) - natural(p)).max()) > 1e-6
