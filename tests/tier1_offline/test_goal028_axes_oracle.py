"""The axes module against an INDEPENDENT oracle: scipy's Rotation.

Reproduction of the defect this module replaces. In 0.23.0 the free stream was
built by ``post.products._free_stream`` as ``(ca cb, +sb, -sa cb)``, whose y and
z terms carry the opposite sign to its x term. Its only tests read their expected
values off the implementation, so both signs passed. Every expectation below
comes from scipy or from a geometric identity, never from ``post.axes`` itself.

The convention under test is the one the owner chose on 2026-09-18: passive,
right-handed direction-cosine matrices on forward-right-down body axes, the
general form ``C_n(mu) = (1 - cos mu) n n^T + cos mu I - sin mu n~``; the export
frame (x aft, y right, z up) reaches the body frame by ``C2(pi)``; the wind axes
are ``C3(beta_w) C2(-alpha_s)`` with the angles taken GEOMETRICALLY from the
velocity vector the solver builds, ``V (ca cb, ca sb, sa)``.

scipy's Rotation is ACTIVE (it turns the vector); the matrices here are PASSIVE
(they turn the coordinate system), so the oracle is the TRANSPOSE.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

scipy_transform = pytest.importorskip("scipy.spatial.transform")
Rotation = scipy_transform.Rotation

from pyflightstream.post import axes  # noqa: E402

ANGLES = [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0), (-2.0, 3.0), (4.0, 2.0), (12.0, -9.0), (35.0, 20.0)]


def passive(axis: tuple[float, float, float], angle: float) -> np.ndarray:
    """The oracle: scipy's active rotation, transposed into a coordinate rotation."""
    unit = np.asarray(axis, dtype=float)
    unit = unit / np.linalg.norm(unit)
    return Rotation.from_rotvec(unit * angle).as_matrix().T


def test_the_general_dcm_is_scipys_passive_rotation_about_any_axis():
    rng = np.random.default_rng(28)
    for _ in range(500):
        axis = rng.normal(size=3)
        angle = rng.uniform(-math.pi, math.pi)
        assert np.allclose(axes.dcm(axis, angle), passive(tuple(axis), angle), atol=1e-12)


def test_the_export_frame_reaches_the_body_frame_by_a_half_turn_about_y():
    assert np.allclose(axes.EXPORT_TO_BODY, passive((0, 1, 0), math.pi), atol=1e-12)
    # x aft -> x forward, y right unchanged, z up -> z down.
    assert np.allclose(axes.EXPORT_TO_BODY @ np.array([1.0, 2.0, 3.0]), [-1.0, 2.0, -3.0])


@pytest.mark.parametrize(("alpha", "beta"), ANGLES)
def test_the_wind_x_axis_is_the_velocity_and_z_wind_lies_in_the_plane_of_symmetry(alpha, beta):
    a, b = math.radians(alpha), math.radians(beta)
    velocity = np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])
    c_wb = axes.body_to_wind(alpha, beta)
    assert np.allclose(c_wb @ velocity, [1.0, 0.0, 0.0], atol=1e-12)
    assert abs(c_wb[2, 1]) < 1e-12, "z_w has a body-y component, so it left the plane of symmetry"
    assert np.allclose(c_wb @ c_wb.T, np.eye(3), atol=1e-12)
    assert math.isclose(float(np.linalg.det(c_wb)), 1.0, abs_tol=1e-12)


@pytest.mark.parametrize(("alpha", "beta"), ANGLES)
def test_body_to_wind_is_the_stevens_and_lewis_chain_built_by_the_oracle(alpha, beta):
    a, b = math.radians(alpha), math.radians(beta)
    # THE GEOMETRIC ANGLES, derived here from the solver's vector and not read
    # off the module: alpha_s = atan2(w, u), beta_w = asin(v / V).
    alpha_s = math.atan2(math.sin(a), math.cos(a) * math.cos(b))
    beta_w = math.asin(math.cos(a) * math.sin(b))
    expected = passive((0, 0, 1), beta_w) @ passive((0, 1, 0), -alpha_s)
    assert np.allclose(axes.body_to_wind(alpha, beta), expected, atol=1e-12)
    got_alpha, got_beta = axes.wind_angles(alpha, beta)
    assert math.isclose(got_alpha, alpha_s, abs_tol=1e-12)
    assert math.isclose(got_beta, beta_w, abs_tol=1e-12)


def test_the_geometric_angles_are_not_the_written_ones_when_both_are_non_zero():
    alpha_s, beta_w = axes.wind_angles(4.0, 2.0)
    assert math.isclose(math.degrees(alpha_s), 4.0024, abs_tol=5e-5)
    assert math.isclose(math.degrees(beta_w), 1.9951, abs_tol=5e-5)


@pytest.mark.parametrize(("alpha", "beta"), ANGLES)
def test_the_free_stream_in_the_export_frame_has_x_aft_y_against_beta_and_z_up(alpha, beta):
    a, b = math.radians(alpha), math.radians(beta)
    # Derived from the frames: the AIR moves opposite to the aircraft, and the
    # export frame is the body frame turned half a turn about y.
    expected = [math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a)]
    assert np.allclose(axes.free_stream_in_export_frame(alpha, beta), expected, atol=1e-12)


def test_a_pure_drag_force_reads_as_drag_alone_in_wind_axes():
    alpha, beta = 6.0, -5.0
    drag = 0.03 * axes.free_stream_in_export_frame(alpha, beta)
    cd, cy, cl = axes.wind_force_coefficients(drag, alpha, beta)
    assert math.isclose(cd, 0.03, abs_tol=1e-12)
    assert abs(cy) < 1e-12
    assert abs(cl) < 1e-12


def test_lift_is_up_at_zero_angles_and_side_force_is_to_the_right():
    # In the export frame +z is up and +y is right; lift and side force are
    # positive that way in every table this package writes.
    assert np.allclose(
        axes.wind_force_coefficients(np.array([0.0, 0.0, 1.0]), 0.0, 0.0), [0.0, 0.0, 1.0]
    )
    assert np.allclose(
        axes.wind_force_coefficients(np.array([0.0, 1.0, 0.0]), 0.0, 0.0), [0.0, 1.0, 0.0]
    )
    assert np.allclose(
        axes.wind_force_coefficients(np.array([1.0, 0.0, 0.0]), 0.0, 0.0), [1.0, 0.0, 0.0]
    )


class _Rotor:
    alias = "PUSHER"
    x_m = y_m = z_m = 0.0
    members = ["Blade1"]

    def __init__(self, axis):
        self.axis_vector = axis


def _stream_force(surface, axis, alpha, beta):
    from pyflightstream.post.products import ReferenceValues, rotor_shaft_loads

    reference = ReferenceValues(
        sref_m2=1.0, cref_m=1.0, bref_m=1.0, xmom_m=0.0, ymom_m=0.0, zmom_m=0.0
    )
    loads = rotor_shaft_loads(
        {"Blade1": surface},
        rotor=_Rotor(axis),
        reference=reference,
        density_kg_m3=2.0,
        speed_m_s=1.0,
        alpha_deg=alpha,
        beta_deg=beta,
    )
    return loads


def test_the_rotor_table_projects_its_force_on_the_measured_free_stream_under_sideslip():
    # Dynamic pressure is 1, so Newtons equal coefficients. At alpha 0 the air
    # moves along (cos b, -sin b, 0): a force to the RIGHT opposes a sideslip.
    beta = 20.0
    loads = _stream_force({"Cx": 1.0, "Cy": 1.0, "Cz": 0.0}, (1.0, 0.0, 0.0), 0.0, beta)
    b = math.radians(beta)
    assert math.isclose(loads.wind_force_n, math.cos(b) - math.sin(b), abs_tol=1e-12)


@pytest.mark.parametrize("axis", [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)])
def test_the_stream_force_follows_the_sense_the_reference_gave_the_shaft(axis):
    # A pulling rotor pushes the aircraft FORWARD, which is -x in the export
    # frame. Whichever way the reference points the axis, the thrust and the
    # force along the stream are the same number at zero incidence, so ETAW
    # reduces to ETA and their ratio never changes sign with that choice.
    loads = _stream_force({"Cx": -0.4, "Cy": 0.0, "Cz": 0.0}, axis, 0.0, 0.0)
    assert math.isclose(loads.wind_force_n, loads.thrust_n, abs_tol=1e-12)
    assert math.isclose(abs(loads.thrust_n), 0.4, abs_tol=1e-12)
