"""Blade-local load projection onto the velocity normal.

Pipeline role: NumPy reduction of pressure loads and wake induction supplied
in geometry axes and SI units by post. The surface sets the force magnitude;
this reduction supplies its direction, not an independent thrust estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pyflightstream.farfield.trefftz import _segment_velocity

__all__ = [
    "FRAME_SPAN_TOLERANCE_DEG",
    "SectionLoads",
    "project_sections",
    "wake_velocity",
    "anchored_wake_loads",
    "complete_induction_wake",
]

#: Maximum angle between a section's radial axis and its blade's measured span.
FRAME_SPAN_TOLERANCE_DEG = 5.0


def complete_induction_wake(lines, values, attachments, exported_lines, exported_values, *, mirror):
    """Include all exported wakes and any missing reflection across geometry y=0.

    The rotor lattice already contains its periodic copies and chord legs.
    Other wakes start at their exported first node, without invented bound legs.
    Matching chains identify copies already supplied by that lattice.
    Constructed reflections reverse strength because vorticity is an axial
    vector. An image already in the export retains its recorded strength.
    Positions are in metres and strengths in square metres per second.
    """
    lines, values, attachments = list(lines), list(values), list(attachments)

    def key_of(line, value):
        coordinates = np.round(line, 8)
        coordinates[coordinates == 0] = 0.0
        return coordinates.tobytes(), round(float(value), 10)

    supplied = [key_of(line, value) for line, value in zip(lines, values, strict=True)]
    for line, value in zip(exported_lines, exported_values, strict=True):
        key = key_of(line, value)
        if key in supplied:
            supplied.remove(key)
        else:
            lines.append(line)
            values.append(value)
            attachments.append(line[0])
    if mirror:
        reflection = np.array([1.0, -1.0, 1.0])
        present = [key_of(line, 0.0) for line in lines]
        for line, value, attachment in list(zip(lines, values, attachments, strict=True)):
            reflected = line * reflection
            key = key_of(reflected, 0.0)
            if key in present:
                present.remove(key)
            else:
                lines.append(reflected)
                values.append(-value)
                attachments.append(attachment * reflection)
    return lines, values, attachments


@dataclass(frozen=True)
class SectionLoads:
    """One blade's strips in geometry axes, with friction stated separately.

    Attributes
    ----------
    radius, width, chord : numpy.ndarray
        Strip radii, widths and chord lengths, in metres.
    radial : numpy.ndarray
        Unit span direction in geometry axes, shape (3,).
    points : numpy.ndarray
        Chord evaluation points in geometry metres, shape (n, 3).
    force, friction : numpy.ndarray
        Total and friction force densities in geometry axes, N/m, shape (n, 3).
    moment : numpy.ndarray
        Section moments about the radial axis, N m/m, shape (n,).
    circulation : numpy.ndarray, optional
        Closed surface velocity integral about the span, in m^2/s.
    """

    radius: np.ndarray
    width: np.ndarray
    chord: np.ndarray
    radial: np.ndarray
    points: np.ndarray
    force: np.ndarray
    friction: np.ndarray
    moment: np.ndarray
    circulation: np.ndarray | None = None


def wake_velocity(
    points: np.ndarray,
    lines: list[np.ndarray],
    values: np.ndarray,
    attachment: np.ndarray,
) -> np.ndarray:
    """Read induction from newest filament values and chord-to-wake legs.

    Parameters
    ----------
    points : numpy.ndarray
        Evaluation points in geometry metres, shape (n, 3).
    lines : list of numpy.ndarray
        Wake chains in geometry metres, newest node first.
    values : numpy.ndarray
        Exported Normalized_Vorticity, one per line, used at scale one m^2/s.
        Strength along the exported chain is minus this value.
    attachment : numpy.ndarray
        Chord points from which straight legs reach the first wake nodes,
        one per line in geometry metres.

    Returns
    -------
    numpy.ndarray
        Induced velocity in geometry axes, m/s, shape (n, 3).
    """
    if not lines or len(values) != len(lines) or attachment.shape != (len(lines), 3):
        raise ValueError("wake induction needs one value and chord attachment per wake line")
    heads, tails, strengths = [], [], []
    for line, value, start in zip(lines, values, attachment, strict=True):
        if line.ndim != 2 or line.shape[1] != 3 or len(line) < 2:
            raise ValueError("each wake line needs at least two three-dimensional nodes")
        chain = np.vstack((start, line))
        head, tail = chain[:-1], chain[1:]
        keep = np.linalg.norm(tail - head, axis=1) > 0
        heads.append(head[keep])
        tails.append(tail[keep])
        strengths.append(np.full(np.count_nonzero(keep), -value))
    arrays = (points, *heads, *tails, *strengths)
    if not all(np.isfinite(array).all() for array in arrays):
        raise ValueError("wake induction needs finite positions and filament strengths")
    return _segment_velocity(
        points, np.concatenate(heads), np.concatenate(tails), np.concatenate(strengths)
    )


def project_sections(
    sections: SectionLoads,
    induced: np.ndarray,
    *,
    axis: np.ndarray,
    wind: np.ndarray,
    hub: np.ndarray,
    moment_point: np.ndarray,
    omega: float,
    rho: float,
) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    """Project inviscid section loads normal to the local blade velocity.

    Parameters
    ----------
    sections : SectionLoads
        One blade's strips; force includes the separately stated friction.
    induced : numpy.ndarray
        Wake-induced velocity in geometry axes, m/s, shape (n, 3).
    axis, wind : numpy.ndarray
        Unit shaft direction and free-stream velocity in geometry axes, m/s.
    hub, moment_point : numpy.ndarray
        Hub and requested moment origin in geometry metres. Torque is always
        about the hub; transverse moments are about moment_point.
    omega, rho : float
        Signed shaft speed in rad/s and positive density in kg/m^3.

    Returns
    -------
    tuple of dict
        Dimensional blade totals and strip diagnostics. Force is in N,
        moments in N m, power in W; GAMMA is signed in m^2/s.
    """
    _validate(
        sections,
        induced,
        axis=axis,
        wind=wind,
        hub=hub,
        moment_point=moment_point,
        omega=omega,
        rho=rho,
    )
    tangent = np.cross(axis, sections.radial)
    va0 = float(wind @ axis)
    vt0 = float(wind @ tangent) - omega * sections.radius
    va = va0 + induced @ axis
    vt = vt0 + induced @ tangent
    speed = np.hypot(va, vt)
    if np.any(speed == 0):
        raise ValueError("a zero relative section speed has no lift direction; omit that strip")
    pressure = sections.force - sections.friction
    normal = (-vt[:, None] * axis + va[:, None] * tangent) / speed[:, None]
    lift = np.einsum("ij,ij->i", pressure, normal)
    force = lift[:, None] * normal
    integrated = force * sections.width[:, None]
    near = pressure * sections.width[:, None]
    friction = sections.friction * sections.width[:, None]
    # Strip loading uses its radial lever. Section pitching moment acts about
    # the span, so contributes transverse moments but never shaft torque.
    arm = sections.radius[:, None] * sections.radial
    hub_moment = np.cross(arm, integrated)
    hub_moment += (sections.moment * sections.width)[:, None] * sections.radial
    total_force = integrated.sum(axis=0)
    total_moment = hub_moment.sum(axis=0) + np.cross(hub - moment_point, total_force)
    thrust = float(total_force @ axis)
    torque = float(hub_moment.sum(axis=0) @ axis)
    power = abs(torque * omega)
    useful = abs(thrust) * va0
    angle = np.arctan2(va, np.abs(vt)) - np.arctan2(np.full_like(vt0, va0), np.abs(vt0))
    angle = np.arctan2(np.sin(angle), np.cos(angle))
    cl = np.abs(lift) / (0.5 * rho * speed**2 * sections.chord)
    totals = {
        "T": thrust,
        "Q": torque,
        "PI": power - useful,
        "ETA": useful / power if power else float("nan"),
        "FY": float(total_force[1]),
        "FZ": float(total_force[2]),
        "MY": float(total_moment[1]),
        "MZ": float(total_moment[2]),
        "T_NEAR_INVISCID": float(near.sum(axis=0) @ axis),
        "Q_NEAR_INVISCID": float(np.cross(arm, near).sum(axis=0) @ axis),
        "T_FRICTION": float(friction.sum(axis=0) @ axis),
        "Q_FRICTION": float(np.cross(arm, friction).sum(axis=0) @ axis),
    }
    strips = {
        "R_M": sections.radius,
        "DR_M": sections.width,
        "CHORD_M": sections.chord,
        "CL": cl,
        "CDI": cl * np.tan(angle),
        "ALPHAI_DEG": np.degrees(angle),
        "GAMMA": lift / (rho * speed),
        "WA_M_S": induced @ axis,
        "WT_M_S": induced @ tangent,
    }
    return totals, strips


def _validate(sections, induced, *, axis, wind, hub, moment_point, omega, rho):
    n = len(sections.radius)
    for name in ("radius", "width", "chord", "moment"):
        value = getattr(sections, name)
        if value.shape != (n,) or not np.isfinite(value).all():
            raise ValueError(f"section {name} needs one finite value per strip")
    for value in (sections.force, sections.friction, sections.points, induced):
        if value.shape != (n, 3) or not np.isfinite(value).all():
            raise ValueError("section vectors need three finite components per strip")
    for value in (axis, sections.radial, wind, hub, moment_point):
        if value.shape != (3,) or not np.isfinite(value).all():
            raise ValueError("frame and flow vectors need three finite components")
    if not n or any(np.any(getattr(sections, key) <= 0) for key in ("radius", "width", "chord")):
        raise ValueError("section radii, widths and chords must be positive")
    if not np.isfinite([rho, omega]).all() or rho <= 0:
        raise ValueError("density must be positive and shaft speed must be finite")
    if not (
        np.isclose(np.linalg.norm(axis), 1)
        and np.isclose(np.linalg.norm(sections.radial), 1)
        and abs(float(axis @ sections.radial)) < 1e-8
    ):
        raise ValueError("shaft and blade span must be orthogonal unit vectors")


def anchored_wake_loads(sections, gamma, lines, values, group, *, hub, axis, wind, omega, rho):
    """Repair W's root sum by one section-derived constant for this blade.

    The mean section circulation minus the interpolated raw root sum over
    0.4 to 0.95 of the wake tip radius sets the constant. Induction remains at
    W's trailing-edge point with its original filament strengths and no legs.
    Returns thrust (N), torque (N m), and the anchor (m^2/s).
    """
    starts = np.array([lines[i][0] for i in group])
    radial = starts - hub
    radial -= (radial @ axis)[:, None] * axis
    radii = np.linalg.norm(radial, axis=1)
    order = np.argsort(radii)
    radii, starts = radii[order], starts[order]
    mid_radius = 0.5 * (radii[:-1] + radii[1:])
    bound = np.cumsum(values[np.asarray(group)[order]])[:-1]
    band = (sections.radius > 0.4 * radii[-1]) & (sections.radius < 0.95 * radii[-1])
    if not np.any(band):
        raise ValueError("W's anchor needs section circulation between 0.4 and 0.95 tip radius")
    anchor = float(np.mean(gamma[band] - np.interp(sections.radius[band], mid_radius, bound)))
    points = 0.5 * (starts[:-1] + starts[1:])
    velocity = wake_velocity(points, lines, values, np.array([line[0] for line in lines]))
    tangent = np.cross(axis, sections.radial)
    va = float(wind @ axis) + velocity @ axis
    vt = omega * mid_radius - velocity @ tangent
    repaired = rho * (bound + anchor) * np.diff(radii)
    return float(np.sum(repaired * vt)), float(np.sum(repaired * va * mid_radius)), anchor
