"""The ONE home of every axis rotation a product makes (0.24.0).

Two copies of one rotation are how two published numbers come to disagree about
which way the air is going: until 0.24.0 the polar row turned its coefficients
inline and the rotor table built its own free-stream vector, and the second one
carried two wrong signs into a published column. Both call this module now.

THE CONVENTION. Direction-cosine matrices are
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
    "REFERENCE_UP",
    "ROTOR_NORMAL_FLOOR",
    "blade_azimuth_deg",
    "body_to_stability",
    "clocked_blade_azimuth_deg",
    "placed_blade_azimuth_deg",
    "body_to_wind",
    "dcm",
    "free_stream_in_export_frame",
    "free_stream_on_rotor_axis",
    "polar_axis_coefficients",
    "rotor_in_plane_axes",
    "rotor_in_plane_loads",
    "section_station_shaft_loads",
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


def clocked_blade_azimuth_deg(
    datum_deg: object,
    *,
    blade: object,
    blades: object,
    clocking: object,
    positions: object,
    rpm: object,
) -> float | None:
    """Return where blade ``blade`` of a quasi-steady wheel is at clocking ``clocking``, or None.

    A wheel of ``blades`` blades solved at ``positions`` clockings (0.31.0).
    Blade n sits ``(n - 1) / N`` of a turn from blade one, right-handed about the
    shaft, as the builder places the blade frames; clocking i turns the whole
    wheel by ``theta_i = i * (360 / N) / k`` in the sense of the sign of ``rpm``,
    as the builder turns the surfaces. So

        psi = (datum + (n - 1) * 360 / N + sign(rpm) * theta_i) mod 360,

    in degrees in [0, 360). Both turns are counted by :func:`blade_azimuth_deg`,
    the one home of a turn counted in steps: the blade's place is step n - 1 of
    a revolution of N steps turned forwards, and the clocking is step i of a
    revolution of N k steps turned in the sense of ``rpm``.

    None where anything is not stated: a datum, a blade from 1 to N, a count of
    blades or of clockings that is not a positive integer, a clocking that is
    not an integer, or an ``rpm`` that is zero or not a number.

    Examples
    --------
    >>> clocked_blade_azimuth_deg(0.0, blade=2, blades=3, clocking=1, positions=3, rpm=1200.0)
    160.0
    >>> clocked_blade_azimuth_deg(0.0, blade=2, blades=3, clocking=1, positions=3, rpm=-1200.0)
    80.0
    >>> clocked_blade_azimuth_deg(0.0, blade=4, blades=3, clocking=0, positions=3, rpm=1.0) is None
    True
    """
    counts = (blade, blades, clocking, positions)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
        return None
    assert isinstance(blade, int) and isinstance(blades, int)
    assert isinstance(clocking, int) and isinstance(positions, int)
    if blades < 1 or positions < 1 or not 1 <= blade <= blades or clocking < 0:
        return None
    placed = placed_blade_azimuth_deg(datum_deg, blade=blade, blades=blades)
    if placed is None:
        return None
    return blade_azimuth_deg(
        placed, step=clocking, steps_per_revolution=blades * positions, rpm=rpm
    )


def placed_blade_azimuth_deg(
    blade_one_deg: object, *, blade: object, blades: object
) -> float | None:
    """Return where blade ``blade`` of ``blades`` is when blade one is at ``blade_one_deg``.

    Blade n sits ``(n - 1) / N`` of a turn from blade one, right-handed about
    the shaft, whatever the sense of rotation, as the builder places the
    blade frames and as :func:`clocked_blade_azimuth_deg` and the per-blade
    table place them (0.31.0). The turn is counted by
    :func:`blade_azimuth_deg`: the blade's place is step n - 1 of a revolution
    of N steps turned forwards. The harmonic product reads blade one's
    ``AZIMUTH`` of an unsteady sections series through here, so that a block
    of blade n is fitted at that blade's own azimuth.

    None where anything is not stated: an azimuth that is not a number, a
    blade from 1 to N, or a count of blades that is not a positive integer.

    Examples
    --------
    >>> placed_blade_azimuth_deg(300.0, blade=2, blades=3)
    60.0
    >>> placed_blade_azimuth_deg(300.0, blade=4, blades=3) is None
    True
    """
    counts = (blade, blades)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
        return None
    assert isinstance(blade, int) and isinstance(blades, int)
    if blades < 1 or not 1 <= blade <= blades:
        return None
    return blade_azimuth_deg(blade_one_deg, step=blade - 1, steps_per_revolution=blades, rpm=1.0)


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


#: The reference frame's UP, in the export frame (x aft, y right, z up): the
#: direction a rotor's normal axis N is taken from (0.31.0, G8).
REFERENCE_UP: tuple[float, float, float] = (0.0, 0.0, 1.0)

#: The length below which the part of UP square to a rotor's axis names no
#: direction: an axis along UP has no normal and no side axis, and the four
#: in-plane components are not defined rather than zero.
ROTOR_NORMAL_FLOOR = 1e-9


def rotor_in_plane_axes(axis: Sequence[float]) -> tuple[Vector, Vector, Vector] | None:
    """Return a rotor's ``(T, S, N)`` unit vectors in the export frame, or None.

    ``T`` is the rotor's axis as declared, the sense in which its thrust is
    counted positive. ``N``, the normal, is the part of :data:`REFERENCE_UP`
    square to ``T``, normalised. ``S``, the side axis, completes the
    right-handed set ``(T, S, N)``: ``S = N x T``, so ``T x S = N``. On a
    level rotor whose axis points forward (``-x``, the export's x being aft)
    ``N`` is up (``+z``) and ``S`` is ``-y``: the right of a viewer standing
    upstream of the rotor and looking downstream at it.

    None where the direction is undefined: an axis of no length, or one along
    UP, whose square part is shorter than :data:`ROTOR_NORMAL_FLOOR`.

    Examples
    --------
    >>> t, s, n = rotor_in_plane_axes((-1.0, 0.0, 0.0))
    >>> [float(c) + 0.0 for c in s], [float(c) + 0.0 for c in n]
    ([0.0, -1.0, 0.0], [0.0, 0.0, 1.0])
    >>> rotor_in_plane_axes((0.0, 0.0, 2.0)) is None
    True
    """
    thrust = np.asarray(axis, dtype=float)
    length = float(np.linalg.norm(thrust))
    if not math.isfinite(length) or length == 0.0:
        return None
    thrust = thrust / length
    up = np.asarray(REFERENCE_UP, dtype=float)
    square = up - float(up @ thrust) * thrust
    reach = float(np.linalg.norm(square))
    if reach <= ROTOR_NORMAL_FLOOR:
        return None
    normal = square / reach
    side = np.cross(normal, thrust)
    return thrust, side, normal


def rotor_in_plane_loads(
    force: Sequence[float], moment: Sequence[float], axis: Sequence[float]
) -> tuple[float, float, float, float] | None:
    """Return ``(N, S, MN, MS)``: a rotor's in-plane force and moment components.

    ``force`` is the rotor's force and ``moment`` its moment about the HUB,
    both in the export frame; ``N`` and ``S`` are the force along the normal
    and the side axes of :func:`rotor_in_plane_axes`, ``MN`` and ``MS`` the
    moment about them. None where those axes are undefined.

    Examples
    --------
    >>> rotor_in_plane_loads((0.0, -3.0, 2.0), (0.0, 5.0, 7.0), (-1.0, 0.0, 0.0))
    (2.0, 3.0, 7.0, -5.0)
    """
    axes = rotor_in_plane_axes(axis)
    if axes is None:
        return None
    _thrust, side, normal = axes
    f = np.asarray(force, dtype=float)
    m = np.asarray(moment, dtype=float)
    # `+ 0.0` turns a negative zero into zero: a table prints `-0.00000` otherwise.
    return (
        float(f @ normal) + 0.0,
        float(f @ side) + 0.0,
        float(m @ normal) + 0.0,
        float(m @ side) + 0.0,
    )


#: The cutting planes whose sectional loads export the package reads in the
#: section frame's own axes (0.31.0): for each, the axes its ``Fx`` and ``Fz``
#: columns lie along and the axis its ``Offset`` is measured along. A cut in
#: the frame's XZ plane states ``Fx`` along the frame's x, ``Fz`` along its z
#: and ``Offset`` along its y, the normal (the pilot evidence of RPT-005 and
#: RPT-006: the export's ``Fx`` of a blade cut in a blade frame whose x is the
#: shaft matched the integrated axial force). A cut in the XY plane states
#: ``Fx`` along the frame's x, ``Fz`` along its y and ``Offset`` along its z:
#: measured on 26.124 (the 0.31.0 short confirmation of the clocked wheel, an
#: XY distribution over blade one in the rotor's hub frame whose x is the
#: shaft), where the strip integrals of ``Fx``, ``Fz`` and ``Fz Offset``
#: matched the blade's force along x, its force along y and its moment about x
#: to about 2 per cent, the midpoint rule's error at 30 stations. The YZ plane
#: is not read: no run has stated which frame axes its two force columns lie
#: along.
SECTION_FORCE_AXES: dict[str, tuple[int, int, int]] = {"XZ": (0, 2, 1), "XY": (0, 1, 2)}


def section_station_shaft_loads(
    force_x: float,
    force_z: float,
    offset: float,
    *,
    plane: str,
    shaft: Sequence[float],
) -> tuple[float, float] | None:
    """Return ``(axial, torque)`` of one station of a sectional loads export, per unit span.

    ``force_x`` and ``force_z`` are the export's ``Fx`` and ``Fz`` of the
    station and ``offset`` its ``Offset``, all in the SECTION FRAME's own
    axes, the frame the distribution was cut in; ``plane`` is the cut's plane
    in that frame and ``shaft`` the rotor's axis stated in the same frame's
    axes, in the sense its thrust is counted positive. The station's force is
    ``F = Fx e_x + Fz e_z`` for an XZ cut, ``Fx e_x + Fz e_y`` for an XY cut
    (:data:`SECTION_FORCE_AXES`), and it sits at ``r = Offset e_y`` (XZ) or
    ``Offset e_z`` (XY) from the frame's origin, the rotor's hub for a
    frame of the rotor:

    * ``axial = F . a``, the force along the shaft ``a``;
    * ``torque = (r x F) . a``, its moment about the shaft, which only the
      in-plane (tangential) component of ``F`` produces.

    None where the plane is not one whose force axes are known or the shaft
    names no direction.

    Examples
    --------
    A blade frame whose x is the shaft: the export's Fx is the thrust and
    ``Offset Fz`` the torque; one whose z is the shaft: Fz is the thrust.

    >>> section_station_shaft_loads(10.0, 2.0, 0.5, plane="XZ", shaft=(1.0, 0.0, 0.0))
    (10.0, 1.0)
    >>> section_station_shaft_loads(10.0, 2.0, 0.5, plane="XZ", shaft=(0.0, 0.0, 1.0))
    (2.0, -5.0)

    An XY cut in the hub frame of a rotor whose shaft is x, the blade along z:
    Fx is the thrust and ``-Offset Fz`` the torque.

    >>> section_station_shaft_loads(10.0, 2.0, 0.5, plane="XY", shaft=(1.0, 0.0, 0.0))
    (10.0, -1.0)
    >>> section_station_shaft_loads(10.0, 2.0, 0.5, plane="YZ", shaft=(1.0, 0.0, 0.0)) is None
    True
    """
    axes = SECTION_FORCE_AXES.get(str(plane).strip().upper())
    if axes is None:
        return None
    along = np.asarray(shaft, dtype=float)
    length = float(np.linalg.norm(along))
    if not math.isfinite(length) or length == 0.0:
        return None
    along = along / length
    first, second, normal = axes
    force = np.zeros(3)
    force[first] = float(force_x)
    force[second] = float(force_z)
    arm = np.zeros(3)
    arm[normal] = float(offset)
    # `+ 0.0` turns a negative zero into zero: a table prints `-0.00000` otherwise.
    return float(force @ along) + 0.0, float(np.cross(arm, force) @ along) + 0.0


def free_stream_on_rotor_axis(
    axis: Sequence[float], alpha_deg: float, beta_deg: float
) -> tuple[float, float] | None:
    """Return ``(cos alpha_p, sin alpha_p)``: the flight direction on a rotor's axis (0.31.0).

    ``alpha_p`` is the angle between the rotor's axis ``axis``, in the sense
    its thrust is counted positive, and the direction the free stream comes
    FROM (the rotor's direction of flight through the air, the opposite of
    :func:`free_stream_in_export_frame`). ``cos alpha_p`` is that direction's
    component along the axis and ``sin alpha_p`` the length of its component
    square to it, so ``alpha_p`` is 0 in axial flight along the thrust and 90
    degrees edgewise. Both are taken from the vectors rather than through the
    angle, so an axis along a geometry axis gives them exactly.

    None where the axis names no direction.

    Examples
    --------
    >>> free_stream_on_rotor_axis((-1.0, 0.0, 0.0), 0.0, 0.0)
    (1.0, 0.0)
    >>> free_stream_on_rotor_axis((0.0, 0.0, 1.0), 0.0, 0.0)
    (0.0, 1.0)
    """
    along = np.asarray(axis, dtype=float)
    length = float(np.linalg.norm(along))
    if not math.isfinite(length) or length == 0.0:
        return None
    along = along / length
    flight = -free_stream_in_export_frame(alpha_deg, beta_deg)
    cosine = float(flight @ along)
    square = flight - cosine * along
    # `+ 0.0` turns a negative zero into zero.
    return cosine + 0.0, float(np.linalg.norm(square)) + 0.0
