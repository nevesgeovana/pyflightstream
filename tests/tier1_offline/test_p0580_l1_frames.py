"""PFS-2231 (0.58.0, lane L1): the rotor frame R<id> and the airframe coefficients per frame.

The design of the 0.58.0 post outputs, sections 4.2, 5.2, 5.3 and 5.4: the
frames W, S, B and R<id>; the sense rule that makes a rotor's thrust positive
forward; ``C_R/B = C2(theta) C3(psi)``; ``y_R = -S`` and ``z_R = -N`` of the
0.57.0 in-plane axes; CD positive aft and CL positive up in every frame.

The expected values are built here from the axis vectors themselves, not from
the module's matrices, so the module is checked against geometry rather than
against itself.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.post.axes import (
    EXPORT_TO_BODY,
    airframe_axis_coefficients,
    frame_rotations,
    rotor_frame,
    rotor_in_plane_axes,
)

_TO_EXPORT = np.diag([-1.0, 1.0, -1.0])  # body (forward, right, down) to export (aft, right, up)


def _rotor_axes_in_body(pitch_deg: float, toe_deg: float) -> tuple[np.ndarray, ...]:
    """x_R, y_R, z_R in body axes from pitch and toe, built by hand."""
    theta, psi = math.radians(pitch_deg), math.radians(toe_deg)
    x = np.array(
        [math.cos(theta) * math.cos(psi), math.cos(theta) * math.sin(psi), -math.sin(theta)]
    )
    y = np.array([-math.sin(psi), math.cos(psi), 0.0])
    return x, y, np.cross(x, y)


def _export_axis(pitch_deg: float, toe_deg: float, forward: bool = True) -> tuple[float, ...]:
    x, _y, _z = _rotor_axes_in_body(pitch_deg, toe_deg)
    vector = _TO_EXPORT @ (x if forward else -x)
    return tuple(float(c) for c in vector)


def test_a_level_tractor_flies_in_body_axes():
    frame = rotor_frame((-1.0, 0.0, 0.0), rotor_id=0)
    assert frame.name == "R0"
    assert frame.pitch_deg == 0.0 and frame.toe_deg == 0.0
    assert frame.sense == 1 and not frame.declared_aft
    np.testing.assert_allclose(frame.body_to_rotor, np.eye(3), atol=1e-15)


def test_a_pusher_pitched_five_degrees_declared_aft_is_turned_forward():
    frame = rotor_frame(_export_axis(5.0, 0.0, forward=False), rotor_id=1)
    assert frame.sense == -1 and frame.declared_aft
    assert frame.pitch_deg == pytest.approx(5.0, abs=1e-12)
    assert frame.toe_deg == pytest.approx(0.0, abs=1e-12)
    x, y, z = _rotor_axes_in_body(5.0, 0.0)
    np.testing.assert_allclose(frame.body_to_rotor, np.vstack([x, y, z]), atol=1e-12)


def test_a_toed_rotor_turns_about_z_first():
    frame = rotor_frame(_export_axis(3.0, 10.0), rotor_id=2)
    assert frame.sense == 1 and not frame.declared_aft
    assert frame.toe_deg == pytest.approx(10.0, abs=1e-12)
    assert frame.pitch_deg == pytest.approx(3.0, abs=1e-12)
    x, y, z = _rotor_axes_in_body(3.0, 10.0)
    np.testing.assert_allclose(frame.body_to_rotor, np.vstack([x, y, z]), atol=1e-12)
    np.testing.assert_allclose(frame.body_to_rotor @ x, [1.0, 0.0, 0.0], atol=1e-12)


def test_a_vertical_lift_rotor_has_toe_zero_and_thrust_up():
    up = rotor_frame((0.0, 0.0, 1.0))
    assert up.sense == 1 and up.toe_deg == 0.0
    assert up.pitch_deg == pytest.approx(90.0, abs=1e-12)
    # x_R is body up, (0, 0, -1): thrust positive up.
    np.testing.assert_allclose(up.body_to_rotor.T @ [1.0, 0.0, 0.0], [0.0, 0.0, -1.0], atol=1e-12)
    down = rotor_frame((0.0, 0.0, -1.0))
    assert down.sense == -1 and down.toe_deg == 0.0 and not down.declared_aft
    np.testing.assert_allclose(down.body_to_rotor, up.body_to_rotor, atol=1e-12)


def test_a_rotor_square_to_x_and_z_points_right():
    frame = rotor_frame((0.0, -1.0, 0.0))
    assert frame.sense == -1
    np.testing.assert_allclose(frame.body_to_rotor.T @ [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], atol=1e-12)


@pytest.mark.parametrize("pitch, toe", [(0.0, 0.0), (5.0, 0.0), (3.0, 10.0), (-7.0, -20.0)])
def test_y_r_is_minus_s_and_z_r_is_minus_n(pitch, toe):
    axis = _export_axis(pitch, toe)
    frame = rotor_frame(axis)
    to_rotor = frame.body_to_rotor @ EXPORT_TO_BODY
    thrust, side, normal = rotor_in_plane_axes(axis)
    np.testing.assert_allclose(to_rotor[0], thrust, atol=1e-12)
    np.testing.assert_allclose(to_rotor[1], -side, atol=1e-12)
    np.testing.assert_allclose(to_rotor[2], -normal, atol=1e-12)


def _frames_in_body(alpha_deg: float, beta_deg: float, rotor) -> dict[str, np.ndarray]:
    """The (x, y, z) axes of W, S, B and R0 as rows, in body axes, built by hand."""
    a, b = math.radians(alpha_deg), math.radians(beta_deg)
    v = np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])
    alpha_s = math.atan2(v[2], v[0])
    x_s = np.array([math.cos(alpha_s), 0.0, math.sin(alpha_s)])
    z_s = np.array([-math.sin(alpha_s), 0.0, math.cos(alpha_s)])
    y_s = np.array([0.0, 1.0, 0.0])
    x_w, z_w = v, z_s
    y_w = np.cross(z_w, x_w)
    x_r, y_r, z_r = _rotor_axes_in_body(rotor[0], rotor[1])
    return {
        "W": np.vstack([x_w, y_w, z_w]),
        "S": np.vstack([x_s, y_s, z_s]),
        "B": np.eye(3),
        "R0": np.vstack([x_r, y_r, z_r]),
    }


def test_the_frames_come_in_file_order():
    turns = frame_rotations(4.0, 2.0, [rotor_frame((-1.0, 0.0, 0.0), 3), rotor_frame((0, 0, 1), 0)])
    assert list(turns) == ["W", "S", "B", "R0", "R3"]


def test_two_frames_of_one_id_are_refused():
    with pytest.raises(ValueError):
        frame_rotations(0.0, 0.0, [rotor_frame((-1.0, 0, 0), 1), rotor_frame((0, 0, 1), 1)])


@pytest.mark.parametrize("name", ["W", "S", "B", "R0"])
def test_a_known_load_at_alpha_4_beta_2_reads_cd_aft_and_cl_up(name):
    rotor = (6.0, 4.0)
    axes = _frames_in_body(4.0, 2.0, rotor)[name]
    q, sref, cref, bref = 250.0, 2.0, 0.5, 6.0
    drag, side, lift = 30.0, -12.0, 400.0
    roll, pitch, yaw = 15.0, -40.0, 9.0
    # Drag acts along -x_f (aft), lift along -z_f (up), side along +y_f.
    force_body = -drag * axes[0] + side * axes[1] - lift * axes[2]
    moment_body = roll * axes[0] + pitch * axes[1] + yaw * axes[2]
    turns = frame_rotations(4.0, 2.0, [rotor_frame(_export_axis(*rotor), 0)])
    row = airframe_axis_coefficients(
        _TO_EXPORT @ force_body,
        _TO_EXPORT @ moment_body,
        turns,
        q_ref_pa=q,
        sref_m2=sref,
        cref_m=cref,
        bref_m=bref,
    )
    assert row[f"CD{name}"] == pytest.approx(drag / (q * sref), abs=1e-12)
    assert row[f"CY{name}"] == pytest.approx(side / (q * sref), abs=1e-12)
    assert row[f"CL{name}"] == pytest.approx(lift / (q * sref), abs=1e-12)
    assert row[f"Cl{name}"] == pytest.approx(roll / (q * sref * bref), abs=1e-12)
    assert row[f"Cm{name}"] == pytest.approx(pitch / (q * sref * cref), abs=1e-12)
    assert row[f"Cn{name}"] == pytest.approx(yaw / (q * sref * bref), abs=1e-12)


def test_the_coefficient_columns_follow_the_frames():
    turns = frame_rotations(0.0, 0.0, [rotor_frame((-1.0, 0, 0), 0)])
    row = airframe_axis_coefficients(
        (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), turns, q_ref_pa=1.0, sref_m2=1.0, cref_m=1.0, bref_m=1.0
    )
    stems = ("CD", "CY", "CL", "Cl", "Cm", "Cn")
    assert list(row) == [f"{stem}{frame}" for frame in ("W", "S", "B", "R0") for stem in stems]


def test_no_dynamic_pressure_gives_na_not_a_number():
    row = airframe_axis_coefficients(
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        frame_rotations(0.0, 0.0),
        q_ref_pa=0.0,
        sref_m2=1.0,
        cref_m=1.0,
        bref_m=1.0,
    )
    assert set(row.values()) == {"NA"}
