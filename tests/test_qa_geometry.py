"""Tier 1: synthetic NACA wing generator for the physics cases."""

import math

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


def test_blade_spec_twist_is_anchored_and_monotonic():
    from pyflightstream.qa.geometry import BladeSpec

    spec = BladeSpec()
    assert abs(np.degrees(spec.beta_rad(0.75)) - spec.beta_75_deg) < 1e-9
    fractions = np.linspace(spec.hub_ratio, 1.0, 20)
    betas = [spec.beta_rad(float(rr)) for rr in fractions]
    assert all(a > b for a, b in zip(betas, betas[1:], strict=False))


def test_blade_mesh_is_watertight_and_outward():
    from collections import Counter

    from pyflightstream.qa.geometry import BladeSpec, blade_triangles

    triangles = blade_triangles(BladeSpec(n_chord=10, n_span=8))
    edges = Counter()
    for triangle in triangles:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            key = tuple(sorted((tuple(np.round(triangle[a], 9)), tuple(np.round(triangle[b], 9)))))
            edges[key] += 1
    assert all(count == 2 for count in edges.values())
    volume = sum(np.dot(t[0], np.cross(t[1], t[2])) for t in triangles) / 6.0
    assert volume > 0.0


def test_generate_blade_stl_writes_ascii(tmp_path):
    from pyflightstream.qa.geometry import BladeSpec, generate_blade_stl

    path = generate_blade_stl(BladeSpec(n_chord=8, n_span=6), tmp_path / "blade.stl")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("solid generic_blade_naca4409")
    assert text.count("facet normal") == text.count("endfacet")


def test_a_wing_can_be_generated_at_an_offset_without_moving_its_shape():
    """Two components at a controlled gap need the offset IN THE MESH.

    A solver command that translates a surface is a different
    measurement: it exercises the transform as well as the thing under
    test, and on a build whose transform commands were renamed one
    release ago that is a second variable nobody asked for. The offset
    belongs in the vertex array, where it is arithmetic.
    """
    from pyflightstream.qa.geometry import WingSpec, wing_triangles

    spec = WingSpec()
    at_origin = wing_triangles(spec)
    lifted = wing_triangles(spec, translation_m=(0.0, 0.0, 0.5))

    assert lifted.shape == at_origin.shape
    assert np.allclose(lifted - at_origin, np.array([0.0, 0.0, 0.5])), (
        "the offset moved something other than the position: every vertex must "
        "shift by exactly the offset and by nothing else"
    )
    # The shape is untouched, which is what makes the pair comparable:
    # every edge length is identical.
    assert np.allclose(
        np.linalg.norm(np.diff(lifted, axis=1), axis=2),
        np.linalg.norm(np.diff(at_origin, axis=1), axis=2),
    )


def test_the_local_face_length_is_measured_from_the_mesh_and_not_assumed():
    """The vendor's own caveat about the proximity mapping is a RATIO.

    It says the mapping may fail where the gap is large relative to the
    faces around it, so a gap measurement with no face length beside it
    means nothing either way. This is what makes the ratio computable.
    """
    from pyflightstream.qa.geometry import WingSpec, mean_edge_length, wing_triangles

    # THE VALUE IS PINNED ON A FIXTURE WHOSE EDGES ARE ARITHMETIC, and
    # that is the arm this test did not have. It asserted only a range
    # and monotonicity, so dropping the wrap-around edge, which measures
    # 2 of every 3 edges instead of 3, passed both. This number is the
    # DENOMINATOR of the gap ratio the whole proximity study rests on, so
    # a systematically short face length silently rescales the result.
    # A UNIT RIGHT TRIANGLE, and NOT a 3-4-5 one. Its edges are 1,
    # sqrt(2) and 1; the closing edge from the last vertex back to the
    # first is the one a naive np.diff drops, and dropping it here gives
    # (1 + sqrt(2)) / 2 = 1.207 against the true (2 + sqrt(2)) / 3 =
    # 1.138. On a 3-4-5 triangle those two are BOTH exactly 4, so the
    # obvious fixture would have pinned the value and still passed under
    # the sabotage, which is how a test can be wrong while looking
    # stricter than the one it replaced.
    right = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    expected = (2.0 + math.sqrt(2.0)) / 3.0
    assert mean_edge_length(right) == pytest.approx(expected)
    two = np.concatenate([right, right + np.array([10.0, 0.0, 0.0])])
    assert mean_edge_length(two) == pytest.approx(expected), "a translated copy changed the mean"

    spec = WingSpec()
    triangles = wing_triangles(spec)
    length = mean_edge_length(triangles)
    assert 0.0 < length < spec.chord_m, (
        f"a mean edge of {length} m on a {spec.chord_m} m chord is not a face length"
    )
    # Refining the mesh shortens the faces, which is the property that
    # makes this a measurement rather than a constant.
    finer = wing_triangles(WingSpec(n_chord=spec.n_chord * 2, n_span=spec.n_span * 2))
    assert mean_edge_length(finer) < length


def test_the_written_stl_carries_the_offset_and_a_name_of_its_own(tmp_path):
    """The function the study actually calls, and the collision that cost it.

    ``wing_triangles`` was tested and ``generate_wing_stl`` was not, so
    dropping the offset in the pass-through left both components of the
    proximity study on top of each other with the suite green. And the
    solid NAME was derived from the aerofoil and the half flag alone, so
    two translated copies of one wing were written under one name: on
    2026-08-17 that made the loads parser refuse all sixteen exports of
    a licensed run.
    """
    from pyflightstream.qa.geometry import WingSpec, generate_wing_stl

    spec = WingSpec()
    lower = generate_wing_stl(spec, tmp_path / "lower.stl", name="lower")
    upper = generate_wing_stl(
        spec, tmp_path / "upper.stl", translation_m=(0.0, 0.0, 0.5), name="upper"
    )

    def z_values(path):
        return [
            float(line.split()[3])
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("vertex")
        ]

    low, high = z_values(lower), z_values(upper)
    assert len(low) == len(high)
    assert max(low) < min(high), "the two components overlap, so the offset never arrived"
    assert np.allclose(np.array(high) - np.array(low), 0.5)

    names = {path.read_text(encoding="utf-8").splitlines()[0].split()[1] for path in (lower, upper)}
    assert names == {"lower", "upper"}, (
        "two components of one study wrote the same solid name, which is what made a "
        "parser refuse every export of a licensed run"
    )


def test_the_four_boolean_arguments_are_keyword_only():
    """The fourth announced incompatible change, made falsifiable.

    The CHANGELOG promises downstream callers that `half` and
    `include_smi` became keyword-only. The commit body's own reason for
    why the change is safe, that every caller in the tree already passed
    them by keyword, is exactly why the suite could not see it: the
    review pass removed the `*` from two signatures and 75 tests stayed
    green. A promise nothing can falsify can be reverted by a merge, a
    refactor, or a reviewer who thinks the star looks odd.
    """
    from pyflightstream.qa.physics import case_table, registered_cases

    spec = WingSpec()
    with pytest.raises(TypeError):
        wing_triangles(spec, True)
    with pytest.raises(TypeError):
        generate_wing_stl(spec, "unused.stl", True)
    with pytest.raises(TypeError):
        registered_cases(True)
    with pytest.raises(TypeError):
        case_table(True)
