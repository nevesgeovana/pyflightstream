# GEOVERSE_HEADER
# file_version: "1.3.0"
# file_role: prescribed-frame-motion-ledger
# last_modified_at: "2026-09-27T19:59:10.058Z"
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementation-agent}
# dependencies: [pyflightstream.script]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: "Bind independently measured MM rotary timing to the exact native identity."
# revision_source: git
"""Geometry/time provenance from emitted commands, never velocity-basis evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

# Exact version, simulation unit and executable digest. Delayed starts remain unproved.
_ROTARY_PROOFS: dict[tuple[str, str, str], dict[str, Any]] = {
    (
        "26.124",
        "METER",
        "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65",
    ): {
        "fs_build": "8172026",
        "signed_rpm_factor": 1,
        "step_time_origin": 0,
        "evidence": {
            "kind": "native coincident-probe rotation control",
            "receipt_sha256": ("af4cc684043546188b4de86320c00b8a45041d7da40b6b2cd62b0172cf55130b"),
            "executed_script_sha256": (
                "96b0b4d591fcc58bc02bffec579e8bad9b549adb2041e3e27ca09bf1484c8d62"
            ),
            "measured_steps": [1, 2, 3, 4, 5, 6],
            "measured_dt_s": 0.00625,
            "measured_emitted_rpm": -800,
            "measured_axis_reference": [1, 0, 0],
            "printed_matching_residual": 0.0,
            "limits": "No delayed-start or other-unit proof; no accuracy claim.",
        },
    },
    (
        "26.124",
        "MILLIMETER",
        "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65",
    ): {
        "fs_build": "8172026",
        "signed_rpm_factor": 1,
        "step_time_origin": 0,
        "evidence": {
            "kind": "native isolated-MM coincident-probe rotation control",
            "receipt_sha256": ("4193840726b01d12b9cfd81c854636ed5b9328a431d315020f5cde8b505c62b6"),
            "executed_script_sha256": (
                "6702ff2cc9532820d63caeaa1d119f29c107035375cb7e1069673a7cbc5a7ca3"
            ),
            "measured_steps": [1, 2, 3, 4, 5, 6],
            "measured_dt_s": 0.00625,
            "measured_emitted_rpm": -800,
            "measured_axis_reference": [1, 0, 0],
            "printed_matching_residual": 0.0,
            "limits": "No delayed-start or other-unit proof; fluid-plot VERTEX is SI.",
        },
    },
}


def _basis(placement: Any) -> tuple[Any, Any]:
    origin = getattr(placement, "origin", None)
    axes = getattr(placement, "axes", None)
    if origin is None or axes is None:
        return origin, None
    valid = all(math.isfinite(float(v)) for v in [*origin, *(v for a in axes for v in a)])
    valid = valid and all(abs(sum(v * v for v in a) - 1) < 1e-8 for a in axes)
    valid = valid and all(
        abs(sum(a * b for a, b in zip(axes[i], axes[j], strict=True))) < 1e-8
        for i, j in ((0, 1), (0, 2), (1, 2))
    )
    x, y, z = axes
    cross = (x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0])
    valid = valid and all(abs(a - b) < 1e-8 for a, b in zip(cross, z, strict=True))
    return origin, axes if valid else None


def resolve_frame_motion(
    record: Mapping[str, Any], *, solver_identity: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve recorded timing against exact native identity without mutating facts."""
    result = deepcopy(dict(record))
    trajectory = result.get("trajectory", {})
    if result.get("reason") not in {
        "Native rotation sense and STEP timing are not measured for this build/unit.",
        "Delayed-start timing is not measured for this build/unit.",
    }:
        return result
    if trajectory.get("kind") != "constant_rotation":
        return result
    proof = _ROTARY_PROOFS.get(
        (
            str(result.get("solver_version", "")),
            str(result.get("length_unit", "")),
            str(solver_identity.get("fs_exe_sha256", "")),
        )
    )
    if proof is None or proof.get("fs_build") != solver_identity.get("fs_build"):
        return result
    if not solver_identity.get("fs_build"):
        return result
    vectors = [result.get(k) for k in ("origin_native", "x_axis", "y_axis", "z_axis")]
    vectors += [trajectory.get(k) for k in ("center_native", "axis_reference")]
    if any(not isinstance(v, (list, tuple)) or len(v) != 3 for v in vectors):
        return result
    try:
        for vector in vectors:
            if not isinstance(vector, (list, tuple)):
                return result
            if not all(math.isfinite(float(x)) for x in vector):
                return result
        rpm = float(trajectory["emitted_rpm"])
        dt = float(trajectory["dt_s"])
        start = float(trajectory["start_time_s"])
    except (KeyError, TypeError, ValueError):
        return result
    if not all(math.isfinite(x) for x in (rpm, dt, start)) or dt <= 0:
        return result
    if start and proof.get("start_time_rule") != "stationary-until-start":
        return result
    trajectory["omega_rad_s"] = rpm * math.pi / 30 * proof["signed_rpm_factor"]
    trajectory["step_time_origin"] = proof["step_time_origin"]
    result["proof"]["timing"] = {
        **deepcopy(proof),
        "fs_exe_sha256": solver_identity["fs_exe_sha256"],
        "length_unit": result.get("length_unit"),
    }
    result["state"], result["reason"] = "known", None
    return result


class MotionLedger:
    """Follow explicit attachments; unknown motion never means fixed."""

    def __init__(self) -> None:
        self.commands: list[dict[str, Any]] = []
        self.motions: dict[int, dict[str, Any]] = {}
        self.names: dict[int, str] = {1: "REFERENCE"}
        self.placed: set[int] = {1}
        self.delta_time: float | None = None
        self.unknown_reason: str | None = None

    def invalidate(self, reason: str) -> None:
        """Mark subsequent snapshots unproved after an untracked mutation."""
        self.unknown_reason = reason

    def follow(self, name: str, bound: Mapping[str, Any], *, line: int, next_motion: int) -> None:
        """Retain a validated command after argument binding and before entity creation."""
        if name in {"OPEN", "NEW_SIMULATION"}:
            self.commands.clear()
            self.motions.clear()
            self.names = {1: "REFERENCE"}
            self.placed = {1}
            self.delta_time = None
            self.unknown_reason = None
            return
        if name == "DELETE_COORDINATE_SYSTEM":
            self.invalidate("Coordinate-system deletion has no proved motion-index remap.")
        frame = bound.get("frame")
        if name == "EDIT_COORDINATE_SYSTEM" and isinstance(frame, int):
            self.names[frame] = str(bound.get("name", frame))
            self.placed.add(frame)
        elif name == "SET_COORDINATE_SYSTEM_ORIGIN" and isinstance(frame, int):
            self.placed.add(frame)
        if not (
            name.startswith("SET_MOTION_")
            or name in {"CREATE_NEW_MOTION", "DELETE_MOTION", "SET_SOLVER_UNSTEADY"}
            or "COORDINATE_SYSTEM" in name
        ):
            return
        command = {"name": name, "args": deepcopy(dict(bound)), "line": line}
        self.commands.append(command)
        if name == "SET_SOLVER_UNSTEADY":
            value = float(bound["delta_time"])
            self.delta_time = value if math.isfinite(value) and value > 0 else None
        if name == "CREATE_NEW_MOTION":
            self.motions[next_motion] = {
                "type": str(bound.get("type", "")),
                "commands": [command],
                "start_time_s": 0.0,
            }
            return
        if name == "DELETE_MOTION":
            self.invalidate("Motion deletion has no proved index-remapping rule.")
            return
        motion_id = bound.get("motion_id")
        if not isinstance(motion_id, int):
            return
        motion = self.motions.setdefault(motion_id, {"type": "unknown", "commands": []})
        motion["commands"].append(command)
        if name == "SET_MOTION_MOVING_FRAMES":
            motion["frames"] = (
                None if bound["num_frames"] == -1 else list(bound.get("frame_indices", []))
            )
            motion["all_frames"] = bound["num_frames"] == -1
        elif name == "SET_MOTION_BOUNDARIES":
            motion["boundaries"] = list(bound.get("boundary_indices", []))
            motion["all_boundaries"] = bound["num_boundaries"] == -1
        elif name == "SET_MOTION_COORDINATE_SYSTEM":
            motion["center_frame"] = int(bound["coordinate_system_id"])
        elif name == "SET_MOTION_ROTOR_AXIS":
            motion["axis"] = str(bound["axis"])
        elif name == "SET_MOTION_ROTOR_RPM":
            motion["rpm"] = float(bound["rpm"])
        elif name == "SET_MOTION_START_TIME":
            values = [v for k, v in bound.items() if k != "motion_id"]
            motion["start_time_s"] = float(values[0]) if len(values) == 1 else None
        elif name != "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION":
            motion["unsupported"] = name

    def snapshot(
        self,
        placements: Mapping[int, Any],
        *,
        frame_count: int,
        boundary_count: int | None,
        version: str,
        length_unit: str | None,
        executable_sha256: str | None = None,
        build: str | None = None,
    ) -> dict[int, dict[str, Any]]:
        """Return detached final placement and timing records, preserving unknowns."""
        result: dict[int, dict[str, Any]] = {}
        proof = _ROTARY_PROOFS.get((version, length_unit or "", executable_sha256 or ""))
        if proof is not None and (not build or proof.get("fs_build") != build):
            proof = None
        ambiguous = any("frames" not in m or m.get("all_frames") for m in self.motions.values())
        for index in range(1, frame_count + 1):
            origin, axes = _basis(placements.get(index) if index in self.placed else None)
            reason = (
                None if origin is not None and axes is not None else "Initial placement is unknown."
            )
            trajectory: dict[str, Any] = {
                "kind": "fixed",
                "center_native": None,
                "axis_reference": None,
                "omega_rad_s": None,
                "emitted_rpm": None,
                "dt_s": self.delta_time,
                "step_time_origin": None,
                "start_time_s": 0.0,
            }
            attached = [(n, m) for n, m in self.motions.items() if index in (m.get("frames") or [])]
            record: dict[str, Any] = {
                "frame_index": index,
                "frame_name": self.names.get(index),
                "state": "known",
                "reason": None,
                "origin_native": list(origin) if origin is not None else None,
                "x_axis": list(axes[0]) if axes is not None else None,
                "y_axis": list(axes[1]) if axes is not None else None,
                "z_axis": list(axes[2]) if axes is not None else None,
                "length_unit": length_unit,
                "solver_version": version,
                "trajectory": trajectory,
                "attached_boundaries": [],
                "motion_index": None,
                "command_provenance": deepcopy(self.commands),
                "proof": {
                    "geometry": {"basis": "explicit emitted frame commands"}
                    if origin is not None and axes is not None
                    else None,
                    "timing": None,
                },
            }
            if index != 1 and (self.unknown_reason or ambiguous):
                reason = self.unknown_reason or "A motion has implicit or all-frame attachments."
                trajectory["kind"] = "unknown"
                if self.unknown_reason:
                    record["proof"]["geometry"] = None
            elif len(attached) > 1:
                reason = "Multiple motions affect this frame; composition is unproved."
                trajectory["kind"] = "unknown"
            elif attached:
                number, motion = attached[0]
                record["motion_index"] = number
                record["attached_boundaries"] = (
                    list(range(1, boundary_count + 1))
                    if motion.get("all_boundaries") and boundary_count is not None
                    else list(motion.get("boundaries", []))
                )
                center_frame = motion.get("center_frame")
                center, basis = _basis(
                    placements.get(center_frame) if isinstance(center_frame, int) else None
                )
                axis = motion.get("axis")
                direction = (
                    basis["XYZ".index(axis)]
                    if basis is not None and isinstance(axis, str) and axis in ("X", "Y", "Z")
                    else None
                )
                trajectory.update(
                    kind="constant_rotation",
                    center_native=list(center) if center is not None else None,
                    axis_reference=list(direction) if direction is not None else None,
                    start_time_s=motion.get("start_time_s"),
                )
                rpm = motion.get("rpm")
                trajectory["emitted_rpm"] = rpm
                center_moves = any(
                    motion.get("center_frame") in (m.get("frames") or [])
                    for m in self.motions.values()
                )
                if motion.get("type") != "ROTARY" or motion.get("unsupported"):
                    reason = "This motion type or modifier has no proved trajectory rule."
                elif center_moves:
                    reason = "The rotation center moves; motion composition is unproved."
                elif center is None or direction is None:
                    reason = "The motion center or axis is unknown."
                elif rpm is None or not math.isfinite(rpm):
                    reason = "The emitted rotary speed is unknown."
                elif rpm == 0:
                    trajectory["kind"] = "fixed"
                elif proof is None or self.delta_time is None:
                    reason = (
                        "Native rotation sense and STEP timing are not measured "
                        "for this build/unit."
                    )
                elif motion.get("start_time_s") is None:
                    reason = "The motion start time is unknown."
                elif (
                    motion.get("start_time_s")
                    and proof.get("start_time_rule") != "stationary-until-start"
                ):
                    reason = "Delayed-start timing is not measured for this build/unit."
                else:
                    trajectory["omega_rad_s"] = rpm * math.pi / 30 * proof["signed_rpm_factor"]
                    trajectory["step_time_origin"] = proof["step_time_origin"]
                    record["proof"]["timing"] = {
                        **deepcopy(proof),
                        "fs_exe_sha256": executable_sha256,
                        "length_unit": length_unit,
                    }
            if reason:
                record["state"], record["reason"] = "unknown", reason
            result[index] = record
        return result
