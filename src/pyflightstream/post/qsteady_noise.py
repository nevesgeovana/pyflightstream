"""The quasi-steady rotor noise model (QS-NOISE, work package F): EXPLORATORY.

Pipeline role: a library beside the post row, NOT wired into the post stage.
QS-NOISE is exploratory: it carries no threshold and no gate, and 0.32.0
does not wait on it. The module holds the model of route A of the 0.32.0 scope (GEO-066
section 2.6 part 5): reconstruct a blade's load against azimuth from the loads
a ``qsteady_rotor`` wheel wrote at its clockings, and propagate it to an
observer by a compact tonal model. The comparison with the solver's own
acoustic signals of an ``unsteady_rotor`` run is report RPT-099.

THE MODEL. Every blade is replaced by two compact point forces turning with
it: its axial force at the axial load's centroid radius, and its in-plane
force (tangential and radial) at the torque's centroid radius. The pressure
of a point force is the loading term of Farassat's Formulation 1A for a
compact source (F. Farassat, "Derivation of Formulations 1 and 1A of
Farassat", NASA/TM-2007-214853, 2007; K. S. Brentner and F. Farassat,
"Modeling aerodynamically generated sound of helicopter rotors", Progress in
Aerospace Sciences 39, 2003, the loading-noise equation of section 3), with
the medium at rest:

    4 pi p_L(x, t) = [ Ldot_r / (c0 r (1 - M_r)^2) ]
                   + [ (L_r - L_M) / (r^2 (1 - M_r)^2) ]
                   + [ L_r (r Mdot_r + c0 (M_r - M^2)) / (c0 r^2 (1 - M_r)^3) ]

every bracket taken at the emission time ``tau``. ``L`` is the force the
surface exerts ON THE FLUID (the negative of the aerodynamic load a solver
reports on the blade), ``r`` the distance from the source to the observer and
``rhat`` its direction, ``M`` the source velocity over ``c0``, ``L_r = L . rhat``,
``Ldot_r = (dL/dtau) . rhat``, ``L_M = L . M``, ``M_r = M . rhat`` and
``Mdot_r = (dM/dtau) . rhat``. The first term is the far field; the other two
are the near field, which is kept because an observer a few radii away is
inside it at the shaft harmonic.

THE RETARDATION. The emission time of an observer time ``t`` is the root
``tau < t`` of ``|x(t) - y(tau)| = c0 (t - tau)``, unique for a subsonic
source, found by bisection between ``t`` and ``t - |x(t) - y(t)| / (c0 - v_max)``
where the left side is known to be negative. The observer may move (an
observer carried with the hub in flight is ``x(t) = x0 + V t``): the equation
holds point by point, so a moving observer only changes which points are
sampled.

NO THICKNESS TERM. The model carries loading noise only, so an unloaded
moving blade is silent. The thickness term needs the blade's volume, which
no loads export holds.

THE CHECK IN CLOSED FORM. For a steady load turning on a circle with a hub
at rest, the far-field harmonic ``n`` (of the shaft frequency) of ``B``
identical blades has the rms amplitude (Gutin 1936, in the form of
M. E. Goldstein, Aeroacoustics, 1976, chapter 3, and of the compact steady
limit of D. B. Hanson, "Helicoidal surface theory for harmonic noise of
propellers in the far field", AIAA Journal 18, 1980)

    p_n = B n Omega / (2 sqrt(2) pi c0 r)
          | F_a cos(theta) J_n(n M_a sin(theta)) + F_t c0 / (Omega r_t) J_n(n M_t sin(theta)) |

for ``n`` a multiple of ``B`` and zero otherwise, ``theta`` from the axis,
``M_a`` and ``M_t`` the rotational Mach numbers of the two centroids and
``F_a``, ``F_t`` the force on the fluid. :func:`gutin_harmonic_rms` computes
it and the tests hold the time-domain model to it.

THE CONVENTIONS. ``axis`` is the rotor's axis and ``reference`` the
direction of azimuth zero (its part square to the axis). Azimuth is
right-handed about the axis, from ``e1`` (the reference) towards
``e2 = axis x e1``; ``e_r = cos psi e1 + sin psi e2`` and
``e_t = axis x e_r``. A tangential force is counted along ``e_t`` and a
signed ``omega_rad_s`` turns the blades in that sense when positive. Blade
``b`` (from zero) sits ``b / B`` of a turn from blade one, right-handed, as
:func:`pyflightstream.post.axes.placed_blade_azimuth_deg` places them.

Nothing here reads a workspace: the workspace writer
:func:`write_qsteady_noise_report` stays a refusing contract in 0.32.0.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

from pyflightstream._errors import ContractNotImplementedError, ProductError

__all__ = [
    "AzimuthalSeries",
    "BladeLoad",
    "PointForce",
    "RotorMotion",
    "SignalComparison",
    "azimuth_from_moment",
    "compare_signals",
    "emission_times",
    "fit_azimuthal_series",
    "gutin_harmonic_rms",
    "loading_noise",
    "reconstruct_blade_load",
    "rotating_components",
    "rotor_loading_noise",
    "rotor_point_forces",
    "write_qsteady_noise_report",
]

Array = NDArray[np.float64]
Trajectory = Callable[[Array], Array]

#: Two azimuths closer than this, in degrees around the circle, are one.
_AZIMUTH_TOLERANCE_DEG = 1e-6
#: The most bisection steps an emission time takes; about 60 halve any bracket
#: a rotor produces below the spacing of a double, and the loop stops there.
_BISECTION_STEPS = 200
#: Points of the one-period quadrature of a Bessel function; the integrand is
#: periodic, so the trapezoid rule converges geometrically.
_BESSEL_POINTS = 2048


def _vector(value: ArrayLike, what: str) -> Array:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size != 3 or not np.all(np.isfinite(array)):
        raise ProductError(f"{what} must be three finite numbers, got {value!r}")
    return array


def _frame(axis: ArrayLike, reference: ArrayLike) -> tuple[Array, Array, Array]:
    """Return ``(e_a, e1, e2)``: the unit axis and the right-handed azimuth-zero pair."""
    e_a = _vector(axis, "axis")
    length = float(np.linalg.norm(e_a))
    if length == 0.0:
        raise ProductError("the rotor axis has no length")
    e_a = e_a / length
    e_1 = _vector(reference, "reference")
    e_1 = e_1 - float(e_1 @ e_a) * e_a
    reach = float(np.linalg.norm(e_1))
    if reach <= 1e-9:
        raise ProductError("the azimuth reference lies along the rotor axis")
    e_1 = e_1 / reach
    return e_a, e_1, np.cross(e_a, e_1)


def _distinct(azimuths_deg: Array) -> int:
    turned = np.sort(np.mod(azimuths_deg, 360.0))
    if turned.size == 0:
        return 0
    count = 1 + int(np.sum(np.diff(turned) > _AZIMUTH_TOLERANCE_DEG))
    if count > 1 and turned[0] + 360.0 - turned[-1] <= _AZIMUTH_TOLERANCE_DEG:
        count -= 1
    return count


# --------------------------------------------------------------------------- the load


@dataclass(frozen=True)
class AzimuthalSeries:
    """A periodic function of azimuth: ``mean + sum_n (a_n cos n psi + b_n sin n psi)``.

    ``cosines[n - 1]`` is ``a_n`` and ``sines[n - 1]`` is ``b_n``.
    """

    mean: float
    cosines: tuple[float, ...] = ()
    sines: tuple[float, ...] = ()

    def value(self, psi_rad: ArrayLike) -> Array:
        """Return the series at ``psi_rad`` (radians)."""
        psi = np.asarray(psi_rad, dtype=float)
        total = np.full_like(psi, self.mean)
        for order, (a, b) in enumerate(zip(self.cosines, self.sines, strict=True), start=1):
            total = total + a * np.cos(order * psi) + b * np.sin(order * psi)
        return total

    def slope(self, psi_rad: ArrayLike) -> Array:
        """Return the derivative of the series with respect to azimuth, per radian."""
        psi = np.asarray(psi_rad, dtype=float)
        total = np.zeros_like(psi)
        for order, (a, b) in enumerate(zip(self.cosines, self.sines, strict=True), start=1):
            total = total + order * (b * np.cos(order * psi) - a * np.sin(order * psi))
        return total


def fit_azimuthal_series(
    azimuths_deg: ArrayLike, values: ArrayLike, *, orders: int | None = None
) -> AzimuthalSeries:
    """Fit an :class:`AzimuthalSeries` to samples by least squares.

    ``orders`` harmonics need ``2 orders + 1`` distinct azimuths; by default
    the fit takes the most the samples carry, ``(distinct - 1) // 2``.

    Raises
    ------
    ProductError
        When there is not one value per azimuth, no sample at all, or more
        harmonics are asked than the samples carry.

    Examples
    --------
    >>> fit = fit_azimuthal_series([0.0, 120.0, 240.0], [3.0, 0.0, 0.0])
    >>> round(fit.mean, 12), round(fit.cosines[0], 12), round(fit.sines[0], 12) + 0.0
    (1.0, 2.0, 0.0)
    """
    azimuths = np.asarray(azimuths_deg, dtype=float).reshape(-1)
    samples = np.asarray(values, dtype=float).reshape(-1)
    if azimuths.size == 0 or azimuths.shape != samples.shape:
        raise ProductError("a series needs one value per azimuth and at least one sample")
    distinct = _distinct(azimuths)
    most = (distinct - 1) // 2
    if orders is None:
        orders = most
    if orders < 0 or orders > most:
        raise ProductError(
            f"{orders} harmonics need {2 * orders + 1} distinct azimuths; "
            f"the samples hold {distinct}"
        )
    psi = np.radians(azimuths)
    design = [np.ones_like(psi)]
    for order in range(1, orders + 1):
        design.extend((np.cos(order * psi), np.sin(order * psi)))
    coefficients, *_ = np.linalg.lstsq(np.column_stack(design), samples, rcond=None)
    return AzimuthalSeries(
        mean=float(coefficients[0]),
        cosines=tuple(float(value) for value in coefficients[1::2]),
        sines=tuple(float(value) for value in coefficients[2::2]),
    )


@dataclass(frozen=True)
class BladeLoad:
    """One blade's aerodynamic load (ON THE BLADE, in N) against its own azimuth.

    ``axial`` is along the rotor axis, ``tangential`` along ``e_t`` and
    ``radial`` along ``e_r`` (module docstring). The axial force acts at
    ``axial_radius_m`` and the in-plane force at ``inplane_radius_m``.
    """

    axial: AzimuthalSeries
    tangential: AzimuthalSeries
    radial: AzimuthalSeries
    axial_radius_m: float
    inplane_radius_m: float

    @classmethod
    def steady(
        cls,
        *,
        axial: float,
        tangential: float,
        axial_radius_m: float,
        radial: float = 0.0,
        inplane_radius_m: float | None = None,
    ) -> BladeLoad:
        """Return a load the same at every azimuth (the in-plane radius defaults to the axial)."""
        return cls(
            AzimuthalSeries(float(axial)),
            AzimuthalSeries(float(tangential)),
            AzimuthalSeries(float(radial)),
            float(axial_radius_m),
            float(axial_radius_m if inplane_radius_m is None else inplane_radius_m),
        )


def rotating_components(
    azimuths_deg: ArrayLike,
    forces: ArrayLike,
    moments: ArrayLike,
    *,
    axis: ArrayLike,
    reference: ArrayLike,
) -> Array:
    """Return, per sample, ``(F_a, F_t, F_r, M_a, M_t)`` of a blade at its azimuth.

    ``forces`` and ``moments`` are the blade's force and its moment about the
    HUB in the fixed frame, one row of three per sample. ``F_a``, ``F_t`` and
    ``F_r`` are the force along the axis, ``e_t`` and ``e_r``; ``M_a`` and
    ``M_t`` the moment about the axis and about ``e_t``. For a force applied at
    ``r e_r``, ``M_a = r F_t`` and ``M_t = -r F_a``.
    """
    e_a, e_1, e_2 = _frame(axis, reference)
    psi = np.radians(np.asarray(azimuths_deg, dtype=float).reshape(-1))
    force = np.asarray(forces, dtype=float).reshape(psi.size, 3)
    moment = np.asarray(moments, dtype=float).reshape(psi.size, 3)
    e_r = np.outer(np.cos(psi), e_1) + np.outer(np.sin(psi), e_2)
    e_t = np.cross(e_a, e_r)
    return np.column_stack(
        (
            force @ e_a,
            np.sum(force * e_t, axis=1),
            np.sum(force * e_r, axis=1),
            moment @ e_a,
            np.sum(moment * e_t, axis=1),
        )
    )


def azimuth_from_moment(
    moment: ArrayLike, axial_force: float, *, axis: ArrayLike, reference: ArrayLike
) -> float:
    """Return a blade's azimuth in degrees in [0, 360) from its moment about the hub.

    The in-plane part of the moment of an axial force ``F_a`` applied at
    ``r e_r`` is ``-r F_a e_t``, so its direction gives ``e_t`` and the
    azimuth. It neglects the in-plane moment of the in-plane force (a blade
    whose load centroid sits off the disc plane); used where a record gives
    the loads but not the blade's position (the unsteady run of RPT-099).

    Raises
    ------
    ProductError
        When the axial force is zero or the moment has no in-plane part.
    """
    e_a, e_1, e_2 = _frame(axis, reference)
    vector = _vector(moment, "moment")
    plane = vector - float(vector @ e_a) * e_a
    reach = float(np.linalg.norm(plane))
    if axial_force == 0.0 or reach == 0.0:
        raise ProductError("an azimuth needs an axial force and an in-plane moment")
    e_t = -plane / reach * math.copysign(1.0, axial_force)
    return math.degrees(math.atan2(-float(e_t @ e_1), float(e_t @ e_2))) % 360.0 + 0.0


def reconstruct_blade_load(
    azimuths_deg: ArrayLike,
    forces: ArrayLike,
    moments: ArrayLike,
    *,
    axis: ArrayLike,
    reference: ArrayLike,
    orders: int | None = None,
    axial_radius_m: float | None = None,
    inplane_radius_m: float | None = None,
) -> BladeLoad:
    """Return one blade's load against azimuth from blade samples at known azimuths.

    Route A of QS-NOISE: a quasi-steady wheel of ``B`` blades solved at ``k``
    clockings gives ``B k`` samples of one blade's load, each blade at its own
    azimuth, when the blades are identical. The three force components are
    fitted by :func:`fit_azimuthal_series` (``orders`` as there) and the
    radii are the centroids of the mean loads, ``r_a = -mean(M_t) / mean(F_a)``
    and ``r_t = mean(M_a) / mean(F_t)``, unless stated.

    Raises
    ------
    ProductError
        When a centroid is asked of a mean force that is zero, or comes out
        not positive.
    """
    parts = rotating_components(azimuths_deg, forces, moments, axis=axis, reference=reference)
    azimuths = np.asarray(azimuths_deg, dtype=float).reshape(-1)
    scale = float(np.max(np.abs(parts[:, :3]))) if parts.size else 0.0

    def centroid(moment: float, force: float, stated: float | None, what: str) -> float:
        if stated is not None:
            return float(stated)
        if force == 0.0 or abs(force) <= 1e-12 * scale:
            raise ProductError(f"the mean {what} force is zero: state the {what} radius")
        radius = moment / force
        if not radius > 0.0:
            raise ProductError(f"the {what} load centroid is not at a positive radius ({radius})")
        return float(radius)

    mean = parts.mean(axis=0)
    return BladeLoad(
        axial=fit_azimuthal_series(azimuths, parts[:, 0], orders=orders),
        tangential=fit_azimuthal_series(azimuths, parts[:, 1], orders=orders),
        radial=fit_azimuthal_series(azimuths, parts[:, 2], orders=orders),
        axial_radius_m=centroid(-mean[4], mean[0], axial_radius_m, "axial"),
        inplane_radius_m=centroid(mean[3], mean[1], inplane_radius_m, "in-plane"),
    )


# --------------------------------------------------------------------------- propagation


@dataclass(frozen=True)
class PointForce:
    """A compact source: a point force ON THE FLUID moving through the medium at rest.

    Each callable takes emission times ``tau`` (shape ``(n,)``) and returns an
    ``(n, 3)`` array: the position, velocity and acceleration of the point,
    the force and its rate of change. ``max_speed_m_s`` bounds the speed.
    """

    position: Trajectory
    velocity: Trajectory
    acceleration: Trajectory
    force: Trajectory
    force_rate: Trajectory
    max_speed_m_s: float


def emission_times(
    observer_times_s: ArrayLike,
    observer_positions_m: ArrayLike,
    position: Trajectory,
    *,
    c0: float,
    max_speed_m_s: float,
) -> Array:
    """Return the emission time of every observer time (module docstring, THE RETARDATION).

    ``observer_positions_m`` holds the observer's position at each of its
    times, one row of three per time.

    Raises
    ------
    ProductError
        When the source is not subsonic.
    """
    times = np.asarray(observer_times_s, dtype=float).reshape(-1)
    observer = np.asarray(observer_positions_m, dtype=float).reshape(times.size, 3)
    if not (0.0 <= max_speed_m_s < c0):
        raise ProductError(
            f"the retardation needs a subsonic source: speed {max_speed_m_s} against c0 {c0}"
        )
    reach = np.linalg.norm(observer - position(times), axis=1)
    high = times.copy()
    low = times - reach / (c0 - max_speed_m_s) * (1.0 + 1e-9)
    for _ in range(_BISECTION_STEPS):
        middle = 0.5 * (low + high)
        gap = np.linalg.norm(observer - position(middle), axis=1) - c0 * (times - middle)
        early = gap < 0.0
        low = np.where(early, middle, low)
        high = np.where(early, high, middle)
        if np.all(high - low <= 2.0 * np.spacing(np.maximum(np.abs(high), np.abs(low)))):
            break
    result: Array = 0.5 * (low + high)
    return result


def loading_noise(
    observer_times_s: ArrayLike,
    observer_positions_m: ArrayLike,
    source: PointForce,
    *,
    c0: float,
) -> Array:
    """Return the loading-noise pressure of one compact source (Formulation 1A), in Pa.

    The equation is in the module docstring; ``observer_positions_m`` holds
    the observer's position at each of its times.
    """
    times = np.asarray(observer_times_s, dtype=float).reshape(-1)
    observer = np.asarray(observer_positions_m, dtype=float).reshape(times.size, 3)
    tau = emission_times(
        times, observer, source.position, c0=c0, max_speed_m_s=source.max_speed_m_s
    )
    separation = observer - source.position(tau)
    r = np.linalg.norm(separation, axis=1)
    rhat = separation / r[:, None]
    mach = source.velocity(tau) / c0
    load = source.force(tau)
    m_r = np.sum(mach * rhat, axis=1)
    mdot_r = np.sum(source.acceleration(tau) * rhat, axis=1) / c0
    m_2 = np.sum(mach * mach, axis=1)
    l_r = np.sum(load * rhat, axis=1)
    ldot_r = np.sum(source.force_rate(tau) * rhat, axis=1)
    l_m = np.sum(load * mach, axis=1)
    doppler = 1.0 - m_r
    far = ldot_r / (c0 * r * doppler**2)
    near = (l_r - l_m) / (r**2 * doppler**2)
    motion = l_r * (r * mdot_r + c0 * (m_r - m_2)) / (c0 * r**2 * doppler**3)
    result: Array = (far + near + motion) / (4.0 * math.pi)
    return result


@dataclass(frozen=True)
class RotorMotion:
    """How a rotor's blades move through the medium at rest.

    ``omega_rad_s`` is signed (positive right-handed about ``axis``);
    ``azimuth0_deg`` is blade one's azimuth at ``tau = 0``; ``hub_m`` the hub
    at ``tau = 0`` and ``hub_velocity_m_s`` its velocity through the medium (in
    flight, the negative of the free stream).
    """

    blades: int
    omega_rad_s: float
    azimuth0_deg: float
    axis: tuple[float, float, float]
    reference: tuple[float, float, float]
    hub_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    hub_velocity_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _blade_sources(
    start: float,
    omega: float,
    frame: tuple[Array, Array, Array],
    hub: Array,
    hub_velocity: Array,
    load: BladeLoad,
) -> list[PointForce]:
    """Return one blade's axial and in-plane compact sources, blade one's azimuth at ``start``."""
    e_a, e_1, e_2 = frame
    speed = float(np.linalg.norm(hub_velocity))

    def psi(tau: Array) -> Array:
        return start + omega * np.asarray(tau, dtype=float)

    def radial(tau: Array) -> Array:
        angle = psi(tau)
        return np.outer(np.cos(angle), e_1) + np.outer(np.sin(angle), e_2)

    def tangential(tau: Array) -> Array:
        angle = psi(tau)
        return np.outer(-np.sin(angle), e_1) + np.outer(np.cos(angle), e_2)

    def axial_force(tau: Array) -> Array:
        return np.outer(-load.axial.value(psi(tau)), e_a)

    def axial_rate(tau: Array) -> Array:
        return np.outer(-omega * load.axial.slope(psi(tau)), e_a)

    def plane_force(tau: Array) -> Array:
        angle = psi(tau)
        f_t, f_r = load.tangential.value(angle), load.radial.value(angle)
        result: Array = -(f_t[:, None] * tangential(tau) + f_r[:, None] * radial(tau))
        return result

    def plane_rate(tau: Array) -> Array:
        angle = psi(tau)
        f_t, f_r = load.tangential.value(angle), load.radial.value(angle)
        d_t, d_r = load.tangential.slope(angle), load.radial.slope(angle)
        along_t = (d_t + f_r)[:, None] * tangential(tau)
        along_r = (d_r - f_t)[:, None] * radial(tau)
        result: Array = -omega * (along_t + along_r)
        return result

    def source(radius: float, force: Trajectory, rate: Trajectory) -> PointForce:
        def where(tau: Array) -> Array:
            result: Array = hub + np.outer(tau, hub_velocity) + radius * radial(tau)
            return result

        def velocity(tau: Array) -> Array:
            result: Array = hub_velocity + radius * omega * tangential(tau)
            return result

        def acceleration(tau: Array) -> Array:
            result: Array = -radius * omega**2 * radial(tau)
            return result

        return PointForce(where, velocity, acceleration, force, rate, speed + abs(omega * radius))

    return [
        source(float(load.axial_radius_m), axial_force, axial_rate),
        source(float(load.inplane_radius_m), plane_force, plane_rate),
    ]


def rotor_point_forces(motion: RotorMotion, load: BladeLoad) -> list[PointForce]:
    """Return the compact sources of a rotor: per blade, its axial then its in-plane force.

    Each is the negative of the blade's load (the force on the fluid), at its
    centroid radius, turning with the blade; the blade's load is the series
    evaluated at the blade's own azimuth.

    Raises
    ------
    ProductError
        When the blade count is not a positive whole number, or a vector is
        not three finite numbers.
    """
    if isinstance(motion.blades, bool) or not isinstance(motion.blades, int) or motion.blades < 1:
        raise ProductError(f"a rotor needs a positive whole number of blades, got {motion.blades}")
    frame = _frame(motion.axis, motion.reference)
    hub = _vector(motion.hub_m, "hub")
    hub_velocity = _vector(motion.hub_velocity_m_s, "hub velocity")
    sources: list[PointForce] = []
    for blade in range(motion.blades):
        start = math.radians(motion.azimuth0_deg) + 2.0 * math.pi * blade / motion.blades
        sources.extend(
            _blade_sources(start, float(motion.omega_rad_s), frame, hub, hub_velocity, load)
        )
    return sources


def rotor_loading_noise(
    observer_times_s: ArrayLike,
    observer_position_m: ArrayLike,
    motion: RotorMotion,
    load: BladeLoad,
    *,
    c0: float,
    observer_velocity_m_s: ArrayLike = (0.0, 0.0, 0.0),
) -> Array:
    """Return a rotor's loading-noise pressure at one observer, in Pa.

    The observer is at ``observer_position_m`` at time zero and moves at
    ``observer_velocity_m_s`` through the medium (the hub's velocity for an
    observer carried with the aircraft). The sum of :func:`loading_noise`
    over :func:`rotor_point_forces`.
    """
    times = np.asarray(observer_times_s, dtype=float).reshape(-1)
    start = _vector(observer_position_m, "observer position")
    velocity = _vector(observer_velocity_m_s, "observer velocity")
    observer = start + np.outer(times, velocity)
    total = np.zeros_like(times)
    for source in rotor_point_forces(motion, load):
        total = total + loading_noise(times, observer, source, c0=c0)
    return total


def _bessel_j(order: int, argument: float) -> float:
    """Return ``J_n(z) = (1 / 2 pi) int_0^2pi cos(n t - z sin t) dt`` by the trapezoid rule."""
    t = np.linspace(0.0, 2.0 * math.pi, _BESSEL_POINTS, endpoint=False)
    return float(np.mean(np.cos(order * t - argument * np.sin(t))))


def gutin_harmonic_rms(
    harmonic: int,
    *,
    blades: int,
    omega_rad_s: float,
    c0: float,
    distance_m: float,
    theta_rad: float,
    axial_force_n: float,
    tangential_force_n: float,
    axial_radius_m: float,
    inplane_radius_m: float,
) -> float:
    """Return the far-field rms amplitude of shaft harmonic ``harmonic`` of a steady rotor, in Pa.

    The closed form of the module docstring (Gutin), for ``blades`` identical
    blades with a steady load, the hub at rest in the medium, ``omega_rad_s``
    positive and the tangential force counted along the rotation; zero for a
    harmonic that is not a multiple of ``blades``. The sign convention of the
    forces cancels in the amplitude as long as both are on the blade or both
    on the fluid.

    Examples
    --------
    >>> gutin_harmonic_rms(1, blades=2, omega_rad_s=100.0, c0=340.0, distance_m=10.0,
    ...                    theta_rad=0.5, axial_force_n=1.0, tangential_force_n=0.0,
    ...                    axial_radius_m=1.0, inplane_radius_m=1.0)
    0.0
    """
    if harmonic < 1 or harmonic % blades:
        return 0.0
    wave = harmonic * omega_rad_s / c0
    sine = math.sin(theta_rad)
    term = axial_force_n * math.cos(theta_rad) * _bessel_j(harmonic, wave * axial_radius_m * sine)
    term += (
        tangential_force_n
        * c0
        / (omega_rad_s * inplane_radius_m)
        * _bessel_j(harmonic, wave * inplane_radius_m * sine)
    )
    scale = blades * harmonic * omega_rad_s / (2.0 * math.sqrt(2.0) * math.pi * c0 * distance_m)
    return scale * abs(term)


# --------------------------------------------------------------------------- comparison


@dataclass(frozen=True)
class SignalComparison:
    """How a predicted pressure record compares with a reference on the same times.

    Every measure is of the fluctuation about each record's own mean:
    ``rms_ratio`` is predicted over reference, ``level_difference_db`` is
    ``20 log10`` of it, ``correlation`` the Pearson coefficient and
    ``normalized_rms_difference`` the rms of the difference of the two
    fluctuations over the reference's rms. ``mean_ratio`` compares the means
    (None when the reference's is zero).
    """

    rms_ratio: float
    level_difference_db: float
    correlation: float
    normalized_rms_difference: float
    mean_ratio: float | None


def compare_signals(
    reference: Sequence[float] | Array, predicted: Sequence[float] | Array
) -> SignalComparison:
    """Return the :class:`SignalComparison` of two records sampled at the same times.

    Raises
    ------
    ProductError
        When the records differ in length, hold fewer than two samples, or
        either is constant.
    """
    ref = np.asarray(reference, dtype=float).reshape(-1)
    new = np.asarray(predicted, dtype=float).reshape(-1)
    if ref.size != new.size or ref.size < 2:
        raise ProductError(
            "a comparison needs two records of the same length, of two samples or more"
        )
    ref_wave, new_wave = ref - ref.mean(), new - new.mean()
    ref_rms = float(np.sqrt(np.mean(ref_wave**2)))
    new_rms = float(np.sqrt(np.mean(new_wave**2)))
    if ref_rms == 0.0 or new_rms == 0.0:
        raise ProductError("a comparison needs two records that are not constant")
    ratio = new_rms / ref_rms
    return SignalComparison(
        rms_ratio=ratio,
        level_difference_db=20.0 * math.log10(ratio),
        correlation=float(np.mean(ref_wave * new_wave) / (ref_rms * new_rms)),
        normalized_rms_difference=float(np.sqrt(np.mean((new_wave - ref_wave) ** 2)) / ref_rms),
        mean_ratio=None if ref.mean() == 0.0 else float(new.mean() / ref.mean()),
    )


def write_qsteady_noise_report(root: str | Path, *, matrix: str | None = None) -> Path:
    """Write the exploratory quasi-steady noise report of a workspace (NOT FILLED in 0.32.0).

    The contract laid down by the 0.32.0 preparation step. Work package F
    left it unfilled on purpose: QS-NOISE is exploratory and not wired into
    the post stage, and its one comparison is report RPT-099, made from the
    library functions above.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    matrix : str, optional
        The matrix stem whose points are compared.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ContractNotImplementedError
        Always, in 0.32.0.
    """
    raise ContractNotImplementedError(
        "pyflightstream.post.qsteady_noise.write_qsteady_noise_report: "
        "not implemented yet (0.32.0 contract)"
    )
