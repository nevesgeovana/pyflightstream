"""Admit blade distributions only after measuring their cut against the blade.

Pipeline role: reuse section loads where the measured section-plane normal
lies along the measured surface span; retain surface re-cuts otherwise.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream.farfield.rotor_sections import FRAME_SPAN_TOLERANCE_DEG
from pyflightstream.results.exports import parse_surface_sections
from pyflightstream.results.sectional_loads import parse_sectional_loads

__all__ = ["aligned_blade_sections", "section_span_angle"]


def section_span_angle(points: np.ndarray, radial: np.ndarray) -> float:
    """Return the acute angle in degrees between a cut normal and blade span.

    Parameters
    ----------
    points : numpy.ndarray
        At least three noncollinear cut points, shape (n, 3).
    radial : numpy.ndarray
        Measured blade span unit vector in the same axes.

    Returns
    -------
    float
        Angle in degrees; infinity for an underdetermined cut plane.
    """
    if len(points) < 3 or not np.isfinite(points).all():
        return float("inf")
    _, singular, vh = np.linalg.svd(points - points.mean(axis=0), full_matrices=False)
    if singular[1] <= 1e-10 * max(singular[0], 1.0):
        return float("inf")
    return float(np.degrees(np.arccos(np.clip(abs(vh[-1] @ radial), 0.0, 1.0))))


def aligned_blade_sections(
    sections,
    layout,
    loads_path: Path | None,
    cp_path: Path | None,
    *,
    axis,
    rho,
    reference_speed,
    per_m,
):
    """Reuse measured on-span distributions, returning re-cut reasons by blade.

    Surface re-cuts remain available when a distribution or its geometric
    evidence is missing. Section CF uses reference dynamic pressure, unlike
    the surface VTK coefficient which uses local dynamic pressure.

    Parameters
    ----------
    sections : dict
        Surface re-cuts by blade name, retained when section evidence is absent.
    layout : sequence of dict
        Recorded section distributions in exported order.
    loads_path, cp_path : pathlib.Path or None
        Matching section-load and cut-geometry exports.
    axis : numpy.ndarray
        Unit shaft direction in geometry axes.
    rho : float
        Density in kg/m^3.
    reference_speed : float
        Reference velocity in m/s for section coefficients.
    per_m : float
        Native exported length units per metre.

    Returns
    -------
    tuple of dict
        Accepted loads by blade and the reasons for retained surface re-cuts.
    """
    output = dict(sections)
    reasons = {
        name: "no matching sectional loads and cut geometry; surface re-cut used"
        for name in sections
    }
    if loads_path is None or cp_path is None or not loads_path.is_file() or not cp_path.is_file():
        return output, reasons
    try:
        loads = parse_sectional_loads(loads_path.read_text(encoding="utf-8"))
        cuts = parse_surface_sections(cp_path.read_text(encoding="utf-8"))
    except (OSError, PyflightstreamError, ValueError):
        return output, reasons
    start = 0
    for block in layout:
        count = int(block["count"])
        rows = loads.values[start : start + count]
        rings = cuts.sections[start : start + count]
        start += count
        families = block.get("families") or []
        if not _blade_block(families, sections, block):
            continue
        name = families[0]
        blade = sections[name]
        useful = _live_cuts(rows, rings)
        if len(useful) < 2:
            continue
        angle = max(section_span_angle(ring.positions, blade.radial) for _, ring in useful)
        if angle > FRAME_SPAN_TOLERANCE_DEG:
            reasons[name] = (
                f"frame is {angle:.3g} degrees off blade span, exceeding "
                f"{FRAME_SPAN_TOLERANCE_DEG:g} degrees; surface re-cut used"
            )
            continue
        row_values = np.array([row for row, _ in useful])
        r = row_values[:, 0] / per_m
        if np.any(np.diff(r) <= 0):
            continue
        tangent = np.cross(axis, blade.radial)
        force = row_values[:, 4, None] * axis - row_values[:, 5, None] * tangent
        friction = []
        for _, ring in useful:
            p = ring.positions / per_m
            ds = np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)
            cf = ring.field("CF")
            velocity = np.column_stack([ring.field(key) for key in ("vx", "vy", "vz")])
            velocity = 0.5 * (velocity + np.roll(velocity, -1, axis=0))
            norm = np.linalg.norm(velocity, axis=1)
            direction = np.divide(
                velocity, norm[:, None], out=np.zeros_like(velocity), where=norm[:, None] > 0
            )
            friction.append(
                (0.5 * rho * reference_speed**2 * 0.5 * (cf + np.roll(cf, -1)) * ds) @ direction
            )

        def interpolate(values, target=blade.radius, source=r):
            return np.column_stack([np.interp(target, source, values[:, k]) for k in range(3)])

        output[name] = replace(
            blade,
            force=interpolate(force),
            friction=interpolate(np.array(friction)),
            moment=np.interp(blade.radius, r, row_values[:, 6]),
        )
        reasons.pop(name, None)
    return output, reasons


def _live_cuts(rows, rings):
    if len(rows) != len(rings):
        return []
    return [
        (row, ring) for row, ring in zip(rows, rings, strict=True) if row[1] > 0 and ring.count > 2
    ]


def _blade_block(families, sections, block):
    return len(families) == 1 and families[0] in sections and block.get("plane") == "XY"
