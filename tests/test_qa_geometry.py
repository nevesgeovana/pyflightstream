"""Tier 1: synthetic NACA wing generator for the physics cases."""

import numpy as np
import pytest

from pyflightstream.qa.geometry import (
    WingSpec,
    generate_wing_stl,
    naca4_contour,
    wing_triangles,
    write_stl,
)


def edge_census(triangles: np.ndarray) -> dict[tuple, int]:
    """Count directed edges; a watertight outward mesh pairs each with its reverse."""
    edges: dict[tuple, int] = {}
    for triangle in triangles:
        vertices = [tuple(np.round(vertex, 9)) for vertex in triangle]
        for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            edges[(a, b)] = edges.get((a, b), 0) + 1
    return edges


def signed_volume(triangles: np.ndarray) -> float:
    """Divergence-theorem volume; positive iff the winding points outward."""
    return float(sum(np.dot(t[0], np.cross(t[1], t[2])) for t in triangles) / 6.0)


def test_naca0012_contour_is_symmetric_and_closed():
    contour = naca4_contour("0012", 50)
    assert np.allclose(contour[0], contour[-1])
    thickness = contour[:, 1]
    assert thickness.max() == pytest.approx(0.06, abs=0.002)
    assert thickness.min() == pytest.approx(-0.06, abs=0.002)
    lower, upper = contour[:51], contour[50:]
    assert np.allclose(lower[::-1, 1], -upper[:, 1], atol=1e-12)


def test_naca2412_camber_peaks_where_designated():
    contour = naca4_contour("2412", 200)
    camber_line = (contour[:201][::-1, 1] + contour[200:, 1]) / 2.0
    x = contour[200:, 0]
    peak = camber_line.max()
    assert peak == pytest.approx(0.02, abs=0.002)
    assert x[camber_line.argmax()] == pytest.approx(0.4, abs=0.05)


def test_full_wing_is_watertight_and_wound_outward():
    spec = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=10)
    triangles = wing_triangles(spec)
    edges = edge_census(triangles)
    assert all(count == 1 for count in edges.values())
    assert all((b, a) in edges for (a, b) in edges)
    volume = signed_volume(triangles)
    assert volume > 0.0
    # The enclosed volume must sit below the thickness-box bound
    # chord * span * max thickness = 1 * 8 * 0.12 m^3.
    assert volume < spec.chord_m * spec.span_m * 0.12


def test_half_wing_opens_exactly_at_the_symmetry_plane():
    spec = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=10)
    triangles = wing_triangles(spec, half=True)
    assert triangles[:, :, 1].min() == pytest.approx(0.0, abs=1e-12)
    edges = edge_census(triangles)
    boundary = [(a, b) for (a, b) in edges if (b, a) not in edges]
    assert boundary, "the root section must stay open for MIRROR symmetry"
    assert all(a[1] == 0.0 and b[1] == 0.0 for a, b in boundary)


def test_stl_writer_is_deterministic_and_parseable(tmp_path):
    spec = WingSpec(n_chord=6, n_span=4)
    first = write_stl(wing_triangles(spec), tmp_path / "a.stl")
    second = write_stl(wing_triangles(spec), tmp_path / "b.stl")
    text_a = first.read_text(encoding="utf-8")
    assert text_a == second.read_text(encoding="utf-8")
    assert text_a.startswith("solid ")
    assert text_a.count("facet normal") == text_a.count("endfacet")
    assert text_a.count("vertex") == 3 * text_a.count("facet normal")


def test_generate_wing_stl_labels_the_solid(tmp_path):
    spec = WingSpec(n_chord=6, n_span=4)
    path = generate_wing_stl(spec, tmp_path / "half.stl", half=True)
    assert path.read_text(encoding="utf-8").startswith("solid naca0012_half")


def test_wing_spec_rejects_non_4digit_designations():
    with pytest.raises(ValueError, match="4-digit"):
        WingSpec(naca="23012")
