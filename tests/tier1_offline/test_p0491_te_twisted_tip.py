"""identify-te from the mesh alone follows a twisted blade's trailing edge to the tip.

A propeller blade's chord turns toward the rotation plane at the tip, so the
surface lies forward of the trailing edge there at a wide angle from the aft
axis, and a closed tip cap is a piece of its own whose aft-facing contour lies
in the plane across the axis.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.workspace._refine import _prepare

SECTION = 12  # points per surface, leading edge to trailing edge
STATIONS = 9


def _blade(cap: bool = True):
    """Return a blade along z, pitched 60 deg at the root and 20 at the tip, its edge sharp."""
    ring = []
    for i in range(SECTION + 1):
        s = 0.5 * (1.0 - math.cos(math.pi * i / SECTION))
        ring.append((s, 0.12 * math.sqrt(s) * (1.0 - s)))
    upper = ring[::-1]  # trailing edge to leading edge
    lower = [(s, -t) for s, t in ring[1:-1]]  # leading edge to trailing edge, both ends shared
    contour = upper + lower
    verts: list[tuple[float, float, float]] = []
    for k in range(STATIONS):
        z = 1.0 + k / (STATIONS - 1)
        pitch = math.radians(60.0 - 40.0 * k / (STATIONS - 1))
        # The chord runs from the leading edge to the trailing edge, its aft part along +x.
        chord = np.array([math.sin(pitch), math.cos(pitch), 0.0])
        normal = np.array([-math.cos(pitch), math.sin(pitch), 0.0])
        for s, t in contour:
            p = (s - 0.5) * 0.3 * chord + t * 0.3 * normal
            verts.append((float(p[0]), float(p[1]), z))
    n = len(contour)
    faces = []
    for k in range(STATIONS - 1):
        for j in range(n):
            a, b = k * n + j, k * n + (j + 1) % n
            faces.append([a, b, b + n, a + n])
    if cap:
        tip = (STATIONS - 1) * n
        centre = np.mean(np.asarray(verts[tip : tip + n]), axis=0)
        verts.append(tuple(float(c) for c in centre))
        for j in range(n):
            faces.append([len(verts) - 1, tip + (j + 1) % n, tip + j])
    trailing = {(k * n, (k + 1) * n) for k in range(STATIONS - 1)}
    return np.asarray(verts, dtype=float), faces, trailing, n


def test_the_trailing_edge_is_followed_to_the_twisted_tip_and_the_tip_cap_is_left_out() -> None:
    verts, faces, trailing, _ = _blade()
    assert _prepare.rearmost_lines(verts, faces) == trailing


def test_an_open_tip_blade_finds_the_whole_trailing_edge_too() -> None:
    verts, faces, trailing, _ = _blade(cap=False)
    assert _prepare.rearmost_lines(verts, faces) == trailing


def test_a_blunt_base_touching_a_sharp_trailing_edge_keeps_its_rim() -> None:
    """A closed box (blunt base at x = 1) and a wedge fin sharing one vertex with it."""
    verts = np.asarray(
        [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
        + [(1, 1, 1), (1, 1.2, 1), (3, 1.1, 1), (1, 1, 2), (1, 1.2, 2), (3, 1.1, 2)],
        dtype=float,
    )
    box = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    fin = [[6, 10, 13, 11], [10, 9, 12, 13], [9, 6, 11, 12], [6, 9, 10], [11, 13, 12]]
    rim = {(1, 2), (1, 5), (2, 6), (5, 6)}
    assert _prepare.rearmost_lines(verts, box + fin) == rim | {(10, 13)}


def test_the_fixture_tip_chord_lies_20_degrees_from_the_rotation_plane() -> None:
    verts, _, _, n = _blade()
    tip_te = verts[(STATIONS - 1) * n]
    tip_le = verts[(STATIONS - 1) * n + SECTION]
    chord = (tip_te - tip_le) / np.linalg.norm(tip_te - tip_le)
    assert math.degrees(math.asin(chord[0])) == pytest.approx(20.0, abs=0.5)


def test_a_trailing_edge_mostly_found_is_taken_to_its_root() -> None:
    """FR-3294: a root bent far aft leaves the rearmost tests; its line is taken whole."""
    verts, faces, trailing, n = _blade()
    verts = verts.copy()
    for k in range(3):  # a bend over three sections: no corner of the line over 60 degrees
        verts[k * n : (k + 1) * n, 0] += 0.6 * (1 - k / 3) ** 2
    root = (0, n)
    assert root in _prepare.near_yz(verts, {root}, max_angle=85.0)
    found = _prepare.rearmost_lines(verts, faces, max_angle=85.0)
    assert trailing <= found
    # The tip line, a line of its own past the corner, stays out.
    ring = range(8 * n, 9 * n)
    tip = {(min(a, b), max(a, b)) for a, b in zip(ring[:-1], ring[1:], strict=True)}
    assert not found & tip


def _lens_plate(tip_x: float, tip_y: float, chord: int = 6, span: int = 12):
    """Return a thin plate whose upper and lower surfaces meet at every perimeter edge.

    The trailing edge runs along y at x = 1, the tip from (1, 1) to (tip_x, tip_y).
    """

    def at(u: float, v: float) -> np.ndarray:
        le = np.array([tip_x, tip_y]) * v
        te = np.array([1.0, 0.0]) * (1 - v) + np.array([1.0, 1.0]) * v
        return le * (1 - u) + te * u

    index: dict[tuple[int, int, int], int] = {}
    verts: list[tuple[float, float, float]] = []

    def vertex(i: int, j: int, side: int) -> int:
        edge = i in (0, chord) or j in (0, span)
        key = (i, j, 0 if edge else side)
        if key not in index:
            u, v = i / chord, j / span
            x, y = at(u, v)
            z = 0.0 if edge else side * 0.12 * math.sin(math.pi * u) * math.sin(math.pi * v)
            index[key] = len(verts)
            verts.append((float(x), float(y), z))
        return index[key]

    faces = []
    for side in (1, -1):
        for i in range(chord):
            for j in range(span):
                quad = [vertex(i, j, side), vertex(i + 1, j, side)]
                quad += [vertex(i + 1, j + 1, side), vertex(i, j + 1, side)]
                faces.append(quad if side > 0 else quad[::-1])

    def pair(a: int, b: int) -> tuple[int, int]:
        return (min(a, b), max(a, b))

    te = {pair(index[(chord, j, 0)], index[(chord, j + 1, 0)]) for j in range(span)}
    tip = {pair(index[(i, span, 0)], index[(i + 1, span, 0)]) for i in range(chord)}
    return np.asarray(verts), faces, te, tip


def test_a_raked_tip_fold_is_not_taken_with_the_trailing_edge() -> None:
    """FR-3294: a tip continuing the trailing edge at a 51 degree corner runs along the flow."""
    verts, faces, te, tip = _lens_plate(0.5, 1.4)
    found = _prepare.rearmost_lines(verts, faces)
    assert te <= found
    assert not found & tip
