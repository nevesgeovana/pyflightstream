"""Mathematical controls use synthetic proof identities, never native evidence."""

from copy import deepcopy

import numpy as np
import pytest

from pyflightstream.post.field_frames import field_in_reference

IDENTITY = {"fs_exe_sha256": "a" * 64, "fs_build": "8172026"}


def _proof(**updates):
    return {
        "state": "known",
        **IDENTITY,
        "export_kind": "unsteady-fluid-plot",
        "length_unit": "METER",
        "components": "instantaneous-local",
        "velocity_kind": "absolute",
        "origin_rule": "none",
        "evidence": {"receipt_sha256": "b" * 64},
        **updates,
    }


def _motion(kind="fixed", scale=1.0):
    return {
        "frame_index": 4,
        "frame_name": "CONTROL",
        "state": "known",
        "reason": None,
        "solver_version": "26.124",
        "length_unit": "METER" if scale == 1 else "MILLIMETER",
        "origin_native": [4.5 / scale, 0, 0],
        "x_axis": [1, 0, 0],
        "y_axis": [0, 1, 0],
        "z_axis": [0, 0, 1],
        "trajectory": {
            "kind": kind,
            "center_native": [4.5 / scale, 0, 0],
            "axis_reference": [1, 0, 0],
            "omega_rad_s": np.pi / 2,
            "dt_s": 1.0,
            "step_time_origin": 0.0,
            "start_time_s": 0.0,
        },
        "proof": {
            "geometry": {"source": "synthetic-emitted"},
            "timing": {
                **IDENTITY,
                "evidence": {"receipt_sha256": "c" * 64},
                "start_time_rule": "stationary-until-start",
            },
        },
    }


def _convert(points, velocity, motion, *, step=None, scale=1.0, proof=None, identity=None):
    return field_in_reference(
        points,
        velocity,
        motion,
        step=step,
        native_to_m=scale,
        velocity_proof=proof or _proof(),
        solver_identity=identity or IDENTITY,
        export_kind="unsteady-fluid-plot",
    )


def test_fixed_local_basis_preserves_physical_vectors_and_input():
    motion = _motion()
    motion.update(x_axis=[0, 1, 0], y_axis=[-1, 0, 0])
    before = deepcopy(motion)
    points, velocity = _convert([[0, -5, 0]], [[3, -11, 5]], motion)
    np.testing.assert_allclose(points, [[9.5, 0, 0]], atol=1e-14)
    np.testing.assert_allclose(velocity, [[11, 3, 5]], atol=1e-14)
    assert motion == before


@pytest.mark.parametrize("scale", [1.0, 0.001])
def test_rotary_relative_velocity_uses_physical_radius_once(scale):
    # GOAL033:post:checks:units_frames_topology
    points, velocity = _convert(
        [[5 / scale, 1 / scale, 0]],
        [[11, 5, -(3 + np.pi / 2)]],
        _motion("constant_rotation", scale),
        step=1,
        scale=scale,
        proof=_proof(velocity_kind="relative", length_unit="METER" if scale == 1 else "MILLIMETER"),
    )
    np.testing.assert_allclose(points, [[9.5, 0, 1]], atol=1e-12)
    np.testing.assert_allclose(velocity, [[11, 3, 5]], atol=1e-12)


def test_reference_components_are_not_rotated_with_the_sampling_frame():
    points, velocity = _convert(
        [[5, 1, 0]],
        [[11, 3, 5]],
        _motion("constant_rotation"),
        step=1,
        proof=_proof(components="REFERENCE"),
    )
    np.testing.assert_allclose(points, [[9.5, 0, 1]], atol=1e-12)
    np.testing.assert_array_equal(velocity, [[11, 3, 5]])


@pytest.mark.parametrize("bad", ["unknown", "identity", "timing", "export"])
def test_unproved_native_conventions_are_refused(bad):
    motion = _motion("constant_rotation")
    proof = _proof()
    identity = dict(IDENTITY)
    if bad == "unknown":
        motion["state"] = "unknown"
        motion["reason"] = "raw motion command"
    if bad == "identity":
        identity["fs_exe_sha256"] = "d" * 64
    if bad == "timing":
        motion["proof"]["timing"] = None
    if bad == "export":
        proof["export_kind"] = "steady-probe"
    with pytest.raises(ValueError):
        _convert([[5, 1, 0]], [[11, 3, 5]], motion, step=1, proof=proof, identity=identity)


def test_actual_step_origin_and_delayed_start_are_separate():
    motion = _motion("constant_rotation")
    motion["trajectory"].update(step_time_origin=1.0, dt_s=0.5, start_time_s=1.0)
    first, first_velocity = _convert(
        [[5, 1, 0]],
        [[11, 3, 5]],
        motion,
        step=2,
        proof=_proof(components="REFERENCE", velocity_kind="relative"),
    )
    np.testing.assert_array_equal(first, [[9.5, 1, 0]])
    np.testing.assert_array_equal(first_velocity, [[11, 3, 5]])
    later, _ = _convert([[5, 1, 0]], [[11, 3, 5]], motion, step=4)
    np.testing.assert_allclose(later, [[9.5, 2**-0.5, 2**-0.5]], atol=1e-12)


@pytest.mark.parametrize(
    "rule,raw",
    [
        ("reference-before-basis", [3, -6.5, 5]),
        ("component-after-basis", [-1.5, -11, 5]),
    ],
)
def test_origin_correction_requires_the_explicit_measured_rule(rule, raw):
    motion = _motion()
    motion.update(x_axis=[0, 1, 0], y_axis=[-1, 0, 0])
    _, velocity = _convert(
        [[0, -5, 0]],
        [raw],
        motion,
        proof=_proof(origin_rule=rule, origin_velocity_scale=1.0),
    )
    np.testing.assert_allclose(velocity, [[11, 3, 5]], atol=1e-12)


def test_invalid_basis_is_not_silently_orthogonalized():
    motion = _motion()
    motion["y_axis"] = [1, 1, 0]
    with pytest.raises(ValueError, match="basis"):
        _convert([[1, 2, 3]], [[11, 3, 5]], motion)
