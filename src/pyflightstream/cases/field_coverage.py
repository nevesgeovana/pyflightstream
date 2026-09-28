"""Conservative spatial bounds; containment does not prove interpolation support."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from itertools import product
from typing import Any

from pyflightstream._lengths import scale
from pyflightstream.cases import CampaignConfigError

Point = tuple[float, float, float]


def _point(value: Any) -> Point:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise CampaignConfigError("unknown three-dimensional placement")
    p = tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in p):
        raise CampaignConfigError("nonfinite placement")
    return p  # type: ignore[return-value]


def _scale(unit: Any) -> float:
    if unit not in {"METER", "MILLIMETER"}:
        raise CampaignConfigError(f"unmeasured length unit {unit!r}")
    factor = scale(unit, "METER")
    assert factor is not None  # The measured-unit whitelist above guarantees this.
    return factor


def _corners(points: Iterable[Sequence[float]]) -> list[Point]:
    points = [_point(p) for p in points]
    if not points:
        raise CampaignConfigError("no mesh vertices")
    return [
        _point(p)
        for p in product(
            *[(min(p[i] for p in points), max(p[i] for p in points)) for i in range(3)]
        )
    ]


def _rotation(p: Point, center: Point, axis: Point, angle: float) -> Point:
    v = [p[i] - center[i] for i in range(3)]
    dot = sum(v[i] * axis[i] for i in range(3))
    cross = (
        axis[1] * v[2] - axis[2] * v[1],
        axis[2] * v[0] - axis[0] * v[2],
        axis[0] * v[1] - axis[1] * v[0],
    )
    c, s = math.cos(angle), math.sin(angle)
    return tuple(center[i] + v[i] * c + cross[i] * s + axis[i] * dot * (1 - c) for i in range(3))  # type: ignore[return-value]


def _axis(value: Any) -> Point:
    axis = _point(value)
    norm = math.sqrt(sum(v * v for v in axis))
    if not math.isclose(norm, 1.0, abs_tol=1e-9):
        raise CampaignConfigError("rotation axis is not a proved unit vector")
    return axis


def spatial_envelope(
    points_m: Iterable[Sequence[float]],
    operations: Sequence[Mapping[str, Any]],
    motions: Sequence[Mapping[str, Any]],
) -> tuple[tuple[float, float, float, float], list[str]]:
    """Return YZ bounds in metres, conservatively including unresolved subsets.

    An AABB may exceed the actual shape. Partial-boundary operations union the
    original and transformed envelope because no face-association is assumed.
    Rotation includes both angular signs; a full rotor sweep is independent of
    direction and STEP convention. Unknown transformations yield no claim.
    """
    points = _corners(points_m)
    notes = ["conservative bounding-box envelope; excess is not proof of a missed surface"]
    for event in operations:
        name = event["command"]
        args = event["arguments"]
        frame = event.get("frame")
        if name not in {"TRANSLATE_SURFACE_IN_FRAME", "ROTATE_SURFACE"}:
            raise CampaignConfigError(f"unsupported emitted transform {name}")
        if not frame:
            raise CampaignConfigError("unknown transform frame")
        center = _point(frame["origin"])
        scale = _scale(event.get("length_unit"))
        center = _point([v * scale for v in center])
        axes = [_axis(a) for a in frame["axes"]]
        selected = args.get("surface", args.get("surfaces"))
        all_surfaces = selected == -1 or event.get("boundary_count") == 1
        if name == "TRANSLATE_SURFACE_IN_FRAME":
            unit_scale = _scale(args.get("units"))
            delta = [
                sum(float(args[k]) * axes[j][i] * unit_scale for j, k in enumerate(("x", "y", "z")))
                for i in range(3)
            ]
            moved = [tuple(p[i] + delta[i] for i in range(3)) for p in points]
        else:
            axis = axes["XYZ".index(str(args["axis"]))]
            angle = math.radians(float(args["angle"]))
            if not math.isfinite(angle):
                raise CampaignConfigError("nonfinite rotation")
            moved = [_rotation(p, center, axis, sign * angle) for p in points for sign in (-1, 1)]
            notes.append("both rotation signs included; no new native sense claim")
        if not all_surfaces:
            moved += points
            notes.append("partial selection uses a conservative union with the unmoved body")
        points = _corners(moved)
    seen = set()
    for record in motions:
        motion = record.get("motion_index")
        trajectory = record.get("trajectory", {})
        if motion is None or motion in seen or trajectory.get("kind") == "fixed":
            continue
        seen.add(motion)
        if trajectory.get("kind") != "constant_rotation":
            raise CampaignConfigError("unsupported moving-frame trajectory")
        if "center moves" in str(record.get("reason", "")).lower():
            raise CampaignConfigError("moving rotation center is not a fixed swept disk")
        scale = _scale(record.get("length_unit"))
        center = _point([v * scale for v in _point(trajectory.get("center_native"))])
        axis = _axis(trajectory.get("axis_reference"))
        swept = list(points)
        for p in points:
            v = [p[i] - center[i] for i in range(3)]
            along = sum(v[i] * axis[i] for i in range(3))
            radius = math.sqrt(max(0.0, sum(x * x for x in v) - along * along))
            mid = [center[i] + along * axis[i] for i in range(3)]
            span = [radius * math.sqrt(max(0.0, 1 - axis[i] * axis[i])) for i in range(3)]
            swept.extend(
                _point(p)
                for p in product(*[(mid[i] - span[i], mid[i] + span[i]) for i in range(3)])
            )
        points = _corners(swept)
        notes.append("full rotary sweep of the conservative body envelope; STEP timing unused")
    return (
        min(p[1] for p in points),
        max(p[1] for p in points),
        min(p[2] for p in points),
        max(p[2] for p in points),
    ), notes
