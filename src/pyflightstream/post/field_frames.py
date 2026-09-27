# GEOVERSE_HEADER
# file_version: 1.1.4
# last_modified_at: 2026-09-27T19:58:35.738Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [numpy]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind independent moving-MM proof with SI velocities and native-coordinate records.
# revision_source: git
"""Coordinate and velocity transforms whose native conventions are explicit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from pyflightstream.script.motion import resolve_frame_motion


@dataclass(frozen=True)
class FramePose:
    """A frame's native-unit placement and physical angular velocity at one STEP."""

    origin_native: np.ndarray
    basis: np.ndarray
    initial_basis: np.ndarray
    angular_velocity_reference: np.ndarray
    center_native: np.ndarray


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"field transform requires finite {name}") from error
    if not np.isfinite(result):
        raise ValueError(f"field transform requires finite {name}")
    return result


def _vector(value: Any, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(f"field transform requires a finite three-component {name}")
    return result


def _native_proof(proof: Any, identity: Mapping[str, Any], name: str) -> None:
    if not isinstance(proof, Mapping) or not proof.get("evidence"):
        raise ValueError(f"{name} has no recorded native evidence")
    for key in ("fs_exe_sha256", "fs_build"):
        actual = identity.get(key)
        if not actual or proof.get(key) != actual:
            raise ValueError(f"{name} does not match the run's {key}")
    digest = identity["fs_exe_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest.lower())
    ):
        raise ValueError(f"{name} requires an executable SHA-256 identity")


def frame_pose(
    motion_record: Mapping[str, Any],
    *,
    step: float | None,
    solver_identity: Mapping[str, Any],
) -> FramePose:
    """Resolve fixed or proved constant-rotation placement at an actual STEP.

    Parameters
    ----------
    motion_record
        The resolved frame ledger; unknown geometry or timing is refused.
    step
        Actual exported STEP, required for a rotating frame.
    solver_identity
        The run's fs_exe_sha256 and fs_build, checked against timing evidence.

    Returns
    -------
    FramePose
        Native-unit origin and basis columns, with angular velocity in rad/s.
    """
    motion_record = resolve_frame_motion(motion_record, solver_identity=solver_identity)
    if motion_record.get("state") != "known":
        raise ValueError(f"unknown sampling frame: {motion_record.get('reason')}")
    proof = motion_record.get("proof")
    if not isinstance(proof, Mapping) or not proof.get("geometry"):
        raise ValueError("sampling frame has no geometry evidence")
    origin = _vector(motion_record.get("origin_native"), "frame origin")
    basis = np.column_stack(
        [_vector(motion_record.get(key), "basis axis") for key in ("x_axis", "y_axis", "z_axis")]
    )
    if not np.allclose(basis.T @ basis, np.eye(3), rtol=0, atol=1e-10):
        raise ValueError("sampling frame basis is not orthonormal")
    if not np.isclose(np.linalg.det(basis), 1.0, rtol=0, atol=1e-10):
        raise ValueError("sampling frame basis is not right-handed")
    trajectory = motion_record.get("trajectory")
    if not isinstance(trajectory, Mapping):
        raise ValueError("sampling frame has no trajectory")
    if trajectory.get("kind") == "fixed":
        return FramePose(origin.copy(), basis.copy(), basis.copy(), np.zeros(3), origin.copy())
    if trajectory.get("kind") != "constant_rotation":
        raise ValueError("sampling frame trajectory is not a proved constant rotation")
    timing = proof.get("timing")
    if not isinstance(timing, Mapping):
        raise ValueError("sampling frame has no timing proof")
    _native_proof(timing, solver_identity, "frame timing")
    center = _vector(trajectory.get("center_native"), "rotation center")
    axis = _vector(trajectory.get("axis_reference"), "rotation axis")
    if not np.isclose(np.linalg.norm(axis), 1.0, rtol=0, atol=1e-10):
        raise ValueError("rotation axis must be a proved unit vector")
    omega = _number(trajectory.get("omega_rad_s"), "angular velocity")
    dt = _number(trajectory.get("dt_s"), "time-step duration")
    zero = _number(trajectory.get("step_time_origin"), "STEP time origin")
    start = _number(trajectory.get("start_time_s", 0.0), "motion start time")
    if dt <= 0 or start < 0:
        raise ValueError("time-step duration must be positive and start time nonnegative")
    if start and timing.get("start_time_rule") != "stationary-until-start":
        raise ValueError("delayed motion has no proved start-time convention")
    elapsed = (_number(step, "exported STEP") - zero) * dt
    if elapsed < -1e-12:
        raise ValueError("exported STEP precedes the proved time origin")
    active = max(0.0, elapsed - start)
    angle = omega * active
    x, y, z = axis
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    rotation = np.eye(3) + np.sin(angle) * cross + (1.0 - np.cos(angle)) * (cross @ cross)
    angular_velocity = axis * omega if elapsed >= start else np.zeros(3)
    return FramePose(
        center + rotation @ (origin - center),
        rotation @ basis,
        basis.copy(),
        angular_velocity,
        center.copy(),
    )


def field_in_reference(
    points_native: Any,
    velocity: Any,
    motion_record: Mapping[str, Any],
    *,
    step: float | None,
    native_to_m: float,
    velocity_proof: Mapping[str, Any],
    solver_identity: Mapping[str, Any],
    export_kind: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return global SI positions and absolute velocity using proved conventions.

    Parameters
    ----------
    points_native
        Original local sample coordinates as an N by 3 array.
    velocity
        Exported velocity components in the units bound by velocity_proof.
    motion_record
        Recorded fixed or resolved constant-rotation frame trajectory.
    step
        Actual STEP of these samples, not their row offset.
    native_to_m
        Separately established coordinate conversion to metres.
    velocity_proof
        Exact export-kind and executable-bound component/velocity conventions.
    solver_identity
        The executable hash and build recorded for this run.
    export_kind
        Native export family, for example unsteady-fluid-plot or steady-probe.

    Returns
    -------
    tuple of numpy.ndarray
        Reference-frame positions in metres and absolute velocity in m/s.
    """
    scale = _number(native_to_m, "coordinate conversion")
    if scale <= 0:
        raise ValueError("coordinate conversion must be positive")
    points = np.asarray(points_native, dtype=float)
    values = np.asarray(velocity, dtype=float)
    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or values.shape != points.shape
        or not len(points)
        or not np.isfinite(points).all()
        or not np.isfinite(values).all()
    ):
        raise ValueError("field positions and velocity must be finite matching N by 3 arrays")
    if velocity_proof.get("state") != "known":
        raise ValueError("native velocity meaning has not been established")
    _native_proof(velocity_proof, solver_identity, "velocity convention")
    unit = motion_record.get("length_unit")
    if not unit or velocity_proof.get("length_unit") != unit:
        raise ValueError("velocity evidence describes different or unknown length units")
    if velocity_proof.get("export_kind") != export_kind:
        raise ValueError("velocity evidence describes a different native export kind")
    proved_scale = velocity_proof.get("coordinate_to_m")
    if proved_scale is not None and not np.isclose(scale, float(proved_scale), rtol=0, atol=0):
        raise ValueError("coordinate conversion differs from measured export units")
    velocity_scale = _number(velocity_proof.get("velocity_to_m_s", 1.0), "velocity conversion")
    if velocity_scale <= 0:
        raise ValueError("velocity conversion must be positive")
    values = values * velocity_scale
    pose = frame_pose(motion_record, step=step, solver_identity=solver_identity)
    reference_native = points @ pose.basis.T + pose.origin_native
    components = velocity_proof.get("components")
    if components == "REFERENCE":
        component_basis = np.eye(3)
    elif components == "instantaneous-local":
        component_basis = pose.basis
    elif components == "initial-local":
        component_basis = pose.initial_basis
    else:
        raise ValueError("unknown native velocity component basis")
    origin_rule = velocity_proof.get("origin_rule")
    corrected = values.copy()
    if origin_rule in ("reference-before-basis", "component-after-basis"):
        offset = pose.origin_native * _number(
            velocity_proof.get("origin_velocity_scale"), "proved origin correction scale"
        )
        if origin_rule == "component-after-basis":
            corrected += offset
        reference_velocity = corrected @ component_basis.T
        if origin_rule == "reference-before-basis":
            reference_velocity += offset
    elif origin_rule == "none":
        reference_velocity = corrected @ component_basis.T
    else:
        raise ValueError("unknown native velocity origin convention")
    meaning = velocity_proof.get("velocity_kind")
    if meaning == "relative":
        radius_m = (reference_native - pose.center_native) * scale
        reference_velocity += np.cross(pose.angular_velocity_reference, radius_m)
    elif meaning != "absolute":
        raise ValueError("unknown absolute/relative native velocity meaning")
    return reference_native * scale, reference_velocity


def native_velocity_proof(
    motion_record: Mapping[str, Any],
    *,
    solver_identity: Mapping[str, Any],
    export_kind: str,
) -> dict[str, Any]:
    """Return only the convention measured for this exact native export/build.

    Fluid-plot evidence does not establish steady probe or surface-vector
    conventions, and metre controls do not establish millimetre behavior.
    """
    expected_hash = "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65"
    unit = motion_record.get("length_unit")
    if (
        motion_record.get("solver_version") != "26.124"
        or solver_identity.get("fs_exe_sha256") != expected_hash
        or solver_identity.get("fs_build") != "8172026"
    ):
        raise ValueError("native velocity convention has no evidence for this export/build/unit")
    if export_kind == "unsteady-fluid-plot" and unit == "METER":
        scale = 1.0
        evidence = {
            "receipt": "GOAL-033/g61-velocity-comparison",
            "receipt_sha256": "af4cc684043546188b4de86320c00b8a45041d7da40b6b2cd62b0172cf55130b",
            "native_plot_sha256": (
                "2f34cf5dd7053a462f19fd618757c274bd4e076d01059e7c38d43d3bcf139a29"
            ),
            "comparison": "nineteen coincident fixed/moving samples at six actual STEPs",
        }
    elif export_kind == "unsteady-fluid-plot" and unit == "MILLIMETER":
        scale = 1.0
        evidence = {
            "receipt": "GOAL-033/g61-moving-millimeter-fluid-si-comparison",
            "receipt_sha256": "4193840726b01d12b9cfd81c854636ed5b9328a431d315020f5cde8b505c62b6",
            "native_plot_sha256": (
                "effbbb615dc64144fe0e7f685f8f6c2f8b966532db16ffe3f3b1029b8fed7f33"
            ),
            "comparison": "all76 columns at six STEPs exactly match the METER control",
        }
    elif export_kind == "steady-probe" and unit in ("METER", "MILLIMETER"):
        scale = 1.0 if unit == "METER" else 0.001
        evidence = {
            "receipt": "GOAL-033/g61-probe-basis-comparison",
            "receipt_sha256": "58b314eaf3aa7ce2cb7823255b8b8031e99bc6b67664cae000b17c321316e9cb",
            "comparison": "same four samples under reference, fixed and rotating analysis frames",
        }
    else:
        raise ValueError("native velocity convention has no evidence for this export/build/unit")
    return {
        "state": "known",
        "fs_exe_sha256": expected_hash,
        "fs_build": "8172026",
        "length_unit": unit,
        "export_kind": export_kind,
        "coordinate_to_m": 1.0 if unit == "METER" else 0.001,
        "velocity_to_m_s": scale,
        "components": "REFERENCE",
        "velocity_kind": "absolute",
        "origin_rule": "none",
        "evidence": evidence,
    }
