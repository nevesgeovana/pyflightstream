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
