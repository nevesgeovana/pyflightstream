"""The ONE home of every axis rotation a product makes (0.24.0).

Two copies of one rotation are how two published numbers come to disagree about
which way the air is going: until 0.24.0 the polar row turned its coefficients
inline and the rotor table built its own free-stream vector, and the second one
carried two wrong signs into a published column. Both call this module now.

THE CONVENTION, the owner's of 2026-09-18. Direction-cosine matrices are
PASSIVE and right-handed: ``C @ v`` gives the components of the SAME vector in
the coordinate system turned by ``mu`` about ``n``,

    C_n(mu) = (1 - cos mu) n n^T + cos mu I - sin mu n~

with ``n~`` the cross-product matrix of ``n``. Body axes are forward, right,
down. ``C2`` and ``C3`` are that matrix about y and about z.

THREE FRAMES, in the order a force travels through them:

1. THE EXPORT FRAME is the geometry's: x AFT, y RIGHT, z UP. Measured on the
   recorded licensed exports rather than assumed: the drag an export states is
   the projection of its own ``(Cx, Cy, Cz)`` on ``(ca cb, -ca sb, sa)``.
2. THE BODY FRAME, forward-right-down, is half a turn about y away:
   ``v_b = C2(pi) v_G``, which is ``diag(-1, 1, -1)`` and a proper rotation.
3. THE WIND AXES follow Stevens and Lewis: stability axes by ``C2(-alpha_s)``,
   then wind axes by ``C3(beta_w)``. ``x_w`` lies along the velocity and
   ``z_w`` stays in the aircraft's plane of symmetry.

THE ANGLES ARE GEOMETRIC, NOT THE WRITTEN ONES. The solver turns sideslip about
the body z axis FIRST and incidence second, so it flies
``V (ca cb, ca sb, sa)``, which is not the ``V (ca cb, sb, sa cb)`` the
Stevens and Lewis angles describe. The two agree when either angle is zero and
differ at second order otherwise. The axes are a property of the velocity
VECTOR and the body, so the angles that enter the chain are read off that
vector: ``alpha_s = atan2(w, u)`` and ``beta_w = asin(v / V)``. A row's
``ALPHA`` and ``BETA`` stay what the user wrote.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from pyflightstream._errors import ProductError

__all__ = [
    "EXPORT_TO_BODY",
    "blade_azimuth_deg",
    "body_to_stability",
    "body_to_wind",
    "dcm",
    "free_stream_in_export_frame",
    "polar_axis_coefficients",
    "stability_force_coefficients",
    "velocity_in_body_frame",
    "wind_angles",
    "wind_force_coefficients",
]


def blade_azimuth_deg(
    datum_deg: object,
    *,
    step: object,
    steps_per_revolution: object,
    rpm: object,
) -> float | None:
    """Return where a blade is at a step, in degrees in [0, 360), or None.

    ``datum_deg`` is where the blade sits at step zero, and it turns by one
    revolution every ``steps_per_revolution`` steps, in the sense of the sign of
    ``rpm``. THE ONE HOME OF THIS RULE: the sections table, the per-blade table
    and the per-blade rows each wrote it out, with their own reading of the sign
    and of when the clock is not stated, and three copies of one rule are how
    two published columns come to disagree about where a blade is.

    None where the clock is not stated: a step, a datum, a positive number of
    steps per revolution or a non-zero ``rpm`` that is not a number. A caller
    publishes that as not applicable, never as zero.

    Examples
    --------
    >>> blade_azimuth_deg(10.0, step=18, steps_per_revolution=72, rpm=2000.0)
    100.0
    >>> blade_azimuth_deg(10.0, step=18, steps_per_revolution=72, rpm=-2000.0)
    280.0
    >>> blade_azimuth_deg(10.0, step=18, steps_per_revolution=72, rpm=None) is None
    True
    """
    stated = (datum_deg, step, steps_per_revolution, rpm)
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in stated):
        return None
    if not steps_per_revolution > 0 or not rpm:  # type: ignore[operator]
        return None
    sense = 1.0 if rpm > 0 else -1.0  # type: ignore[operator]
    turned = sense * float(step) * 360.0 / float(steps_per_revolution)  # type: ignore[arg-type]
    return (float(datum_deg) + turned) % 360.0 + 0.0  # type: ignore[arg-type]


Matrix = NDArray[np.float64]
Vector = NDArray[np.float64]

_Y = (0.0, 1.0, 0.0)
_Z = (0.0, 0.0, 1.0)


def dcm(axis: Sequence[float], angle_rad: float) -> Matrix:
    """Return the passive direction-cosine matrix of a turn ``angle_rad`` about ``axis``.

    Parameters
    ----------
    axis : sequence of float
        The direction the coordinate system turns about; it need not be a unit
        vector, and it may not be null.
    angle_rad : float
        The right-handed angle, in radians.

    Returns
    -------
    numpy.ndarray
        The 3 by 3 matrix ``C`` such that ``C @ v`` holds the components of
        ``v`` in the turned coordinate system.

    Raises
    ------
    ProductError
        If ``axis`` has no direction. It is a ``ValueError`` too.

    Examples
    --------
    A quarter turn about z carries the old y axis onto the new x axis:

    >>> import math
    >>> [round(float(c), 12) + 0.0 for c in dcm((0, 0, 1), math.pi / 2) @ [0.0, 1.0, 0.0]]
    [1.0, 0.0, 0.0]
    """
    n = np.asarray(axis, dtype=float)
    length = float(np.linalg.norm(n))
    if length == 0.0:
        raise ProductError("a rotation axis of zero length names no direction to turn about")
    n = n / length
    mu = float(angle_rad)
    tilde = np.array([[0.0, -n[2], n[1]], [n[2], 0.0, -n[0]], [-n[1], n[0], 0.0]])
    return (1.0 - math.cos(mu)) * np.outer(n, n) + math.cos(mu) * np.eye(3) - math.sin(mu) * tilde


#: The export frame (x aft, y right, z up) to the body frame (forward, right,
#: down): half a turn about y. Rounded, because ``sin(pi)`` is 1e-16 and a
#: frame change should not smear a zero.
EXPORT_TO_BODY: Matrix = np.round(dcm(_Y, math.pi), 12) + 0.0


def velocity_in_body_frame(alpha_deg: float, beta_deg: float) -> Vector:
    """Return the unit velocity of the AIRCRAFT in body axes, as the solver builds it.

    Sideslip is turned about body z first and incidence second, so the vector
    is ``(ca cb, ca sb, sa)``; see the module docstring for the measurement.
    """
    a = math.radians(float(alpha_deg))
    b = math.radians(float(beta_deg))
    return np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])


def wind_angles(alpha_deg: float, beta_deg: float) -> tuple[float, float]:
    """Return ``(alpha_s, beta_w)`` in RADIANS, read off the solver's velocity vector.

    ``alpha_s`` turns the body axes onto the stability axes and ``beta_w`` turns
    those onto the wind axes. They equal the written angles when either is zero.

    Examples
    --------
    >>> import math
    >>> [round(math.degrees(angle), 4) for angle in wind_angles(4.0, 2.0)]
    [4.0024, 1.9951]
    """
    u, v, w = velocity_in_body_frame(alpha_deg, beta_deg)
    return math.atan2(w, u), math.asin(max(-1.0, min(1.0, float(v))))


def body_to_stability(alpha_deg: float, beta_deg: float = 0.0) -> Matrix:
    """Return ``C_s/b = C2(-alpha_s)``: body axes to stability axes."""
    alpha_s, _beta_w = wind_angles(alpha_deg, beta_deg)
    return dcm(_Y, -alpha_s)


def body_to_wind(alpha_deg: float, beta_deg: float) -> Matrix:
    """Return ``C_w/b = C3(beta_w) C2(-alpha_s)``: body axes to wind axes."""
    alpha_s, beta_w = wind_angles(alpha_deg, beta_deg)
    return dcm(_Z, beta_w) @ dcm(_Y, -alpha_s)


def free_stream_in_export_frame(alpha_deg: float, beta_deg: float) -> Vector:
    """Return the unit direction the AIR moves along, in the export's own frame.

    It is the aircraft's velocity reversed and carried back to the export frame,
    ``(ca cb, -ca sb, sa)``: aft, against the sideslip, and UP at positive
    incidence. A force's projection on it is the drag along the free stream.
    """
    return EXPORT_TO_BODY.T @ (-velocity_in_body_frame(alpha_deg, beta_deg))


def _forward_right_down_to_drag_side_lift(components: Vector) -> tuple[float, float, float]:
    # Drag opposes +x and lift opposes +z on forward-right-down axes; the side
    # force keeps its sign.
    return -float(components[0]), float(components[1]), -float(components[2])


def wind_force_coefficients(
    force_in_export_frame: Sequence[float], alpha_deg: float, beta_deg: float
) -> tuple[float, float, float]:
    """Return ``(CD, CY, CL)`` in WIND axes of a force stated in the export frame.

    Works on coefficients and on Newtons alike: the rotation does not care.
    """
    force = np.asarray(force_in_export_frame, dtype=float)
    return _forward_right_down_to_drag_side_lift(
        body_to_wind(alpha_deg, beta_deg) @ EXPORT_TO_BODY @ force
    )


def stability_force_coefficients(
    force_in_export_frame: Sequence[float], alpha_deg: float, beta_deg: float = 0.0
) -> tuple[float, float, float]:
    """Return ``(CD, CY, CL)`` in STABILITY axes of a force stated in the export frame."""
    force = np.asarray(force_in_export_frame, dtype=float)
    return _forward_right_down_to_drag_side_lift(
        body_to_stability(alpha_deg, beta_deg) @ EXPORT_TO_BODY @ force
    )


def polar_axis_coefficients(
    force_in_export_frame: Sequence[float],
    moment_in_export_frame: Sequence[float],
    alpha_deg: float,
    beta_deg: float,
    *,
    cref_m: float,
    bref_m: float,
) -> tuple[float, ...]:
    """Return the eighteen axis coefficients of one polar row, from ONE force and ONE moment.

    Parameters
    ----------
    force_in_export_frame : sequence of float
        ``(Cx, Cy, Cz)`` as the loads export states them: x aft, y right, z up.
    moment_in_export_frame : sequence of float
        ``(CMx, CMy, CMz)`` in that frame, ALL THREE normalised by the reference
        chord, which is how the export states them.
    alpha_deg, beta_deg : float
        The angles the point flew, as written; the axes are turned by the
        geometric angles of :func:`wind_angles`.
    cref_m, bref_m : float
        The reference chord and span.

    Returns
    -------
    tuple of float
        ``CD, CY, CL, CR, CM, CN`` in body axes, then in stability axes, then in
        wind axes. Drag opposes +x and lift opposes +z of each forward-right-down
        system; the rolling and yawing moments are normalised by the SPAN and the
        pitching moment by the CHORD.

    Notes
    -----
    THE MOMENT TURNS AS ONE VECTOR IN ONE LENGTH, and takes the span or the chord
    only afterwards. That is where the ``c/b`` exchange between roll and pitch
    under sideslip comes from: it is not a separate rule.

    In body axes the forces are the export's own, ``CD == Cx`` and ``CL == Cz``.

    Examples
    --------
    At zero incidence and zero sideslip the three systems coincide:

    >>> row = polar_axis_coefficients((0.02, 0.0, 0.5), (0.0, -0.1, 0.0), 0.0, 0.0,
    ...                               cref_m=2.0, bref_m=10.0)
    >>> [round(value, 12) + 0.0 for value in row[:3]] == [round(v, 12) + 0.0 for v in row[12:15]]
    True
    """
    to_stability = body_to_stability(alpha_deg, beta_deg)
    to_wind = body_to_wind(alpha_deg, beta_deg)
    force = EXPORT_TO_BODY @ np.asarray(force_in_export_frame, dtype=float)
    moment = EXPORT_TO_BODY @ np.asarray(moment_in_export_frame, dtype=float)
    span = float(cref_m) / float(bref_m)
    row: list[float] = []
    for turn in (np.eye(3), to_stability, to_wind):
        turned = turn @ moment
        row.extend(_forward_right_down_to_drag_side_lift(turn @ force))
        row.extend((float(turned[0]) * span, float(turned[1]), float(turned[2]) * span))
    # `+ 0.0` turns a negative zero into zero: a table prints `-0.00000` otherwise.
    return tuple(value + 0.0 for value in row)
