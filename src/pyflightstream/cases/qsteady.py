"""The quasi-steady rotor's own arithmetic (0.30.0): clocking, validity and the inflow.

The ``qsteady_rotor`` run type solves an isolated rotor with its blades held
still and the rotation carried by the free stream. Three questions it asks are
arithmetic and live here, below the builder that asks them:

* where the wheel is clocked for each steady solve (:func:`clocking_angles`);
* how far the quasi-steady assumption is from the flow, read as the 1P reduced
  frequency along the blade (:func:`reduced_frequencies`), from stations the
  mesh gives (:func:`blade_stations`, :func:`obj_group_vertices`) or the
  sectional loads export gives after the run;
* whether a custom inflow varies with the radius alone (:func:`azimuthal_variation`),
  which is what a periodic sector can stand for;
* the momentum-theory induced inflow of a rotor state
  (:func:`glauert_induced_inflow`, 0.31.0), which the wheel's correction
  routes read.

It also holds the point's quasi-steady record, ``<point>_qsteady.json``, as one
type (:class:`QsteadyRecord`) with one reader (:func:`read_qsteady_record`) and
one refusal (:class:`QsteadyRecordError`), beside the name of the file
(:func:`record_file_name`): the builder writes it, the run and the post read it.

The 1P reduced frequency of a blade station at radius ``r`` with chord ``c`` is::

    Omega = 2 pi RPM / 60                  (rad/s)
    V_rel = sqrt(V^2 + (Omega r)^2)
    k     = Omega c / (2 V_rel)

the once-per-revolution frequency of the load a non-uniform inflow puts on the
blade, made dimensionless by the time the relative flow takes to cross half a
chord. The ``1P`` is counted in the blade's own frame: how many times ONE blade
meets the non-uniformity in one of its revolutions. It is not the blade-passing
excitation a fixed surface near the rotor feels, nor what a balance summing
every blade reads. Below about 0.05 the flow at the station follows the load's change as
it happens and a steady solution stands for it; above about 0.1 the lag of the
unsteady wake is no longer small and the quasi-steady load is an estimate.

This module imports nothing from a higher layer; the builder in
:mod:`pyflightstream.cases.workflows`, the run and the post stage call it.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, ClassVar

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import CampaignConfigError

__all__ = [
    "AXISYMMETRY_RADIUS_TOLERANCE",
    "AXISYMMETRY_SPEED_TOLERANCE",
    "AZIMUTH_SAMPLES",
    "DEFAULT_STATIONS",
    "HARMONIC_AMPLITUDE_FLOOR_DEG",
    "HARMONIC_VARIANCE_SHARE",
    "INFLOW_ITERATIONS",
    "INFLOW_TOLERANCE",
    "InflowHarmonics",
    "POSITION_SUFFIX",
    "QsteadyClocking",
    "QsteadyRecord",
    "QsteadyRecordError",
    "RECORD_CASES",
    "RECORD_RUN_TYPE",
    "RECORD_SCHEMA_VERSION",
    "RECORD_SUFFIX",
    "REDUCED_FREQUENCY_LIMIT",
    "REDUCED_FREQUENCY_WATCH",
    "ReducedFrequencies",
    "VALIDITY_FILE_SUFFIX",
    "Vector",
    "azimuthal_variation",
    "blade_inflow_angles",
    "blade_inflow_harmonics",
    "blade_stations",
    "clocking_angles",
    "glauert_induced_inflow",
    "harmonic_order",
    "harmonic_variance_shares",
    "obj_group_vertices",
    "position_export_name",
    "position_loads_name",
    "qsteady_record_rotor_alias",
    "read_qsteady_record",
    "record_file_name",
    "reduced_frequencies",
    "reduced_frequency",
    "strip_lengths",
    "suggested_passage_positions",
    "summarise",
    "summarise_inflow_harmonics",
    "validity_file_name",
]

Vector = tuple[float, float, float]

#: The reduced frequency above which the plan warns and the products count a
#: station as outside the quasi-steady assumption.
REDUCED_FREQUENCY_LIMIT = 0.1
#: The lower threshold the datapoint file also reports a span fraction for.
REDUCED_FREQUENCY_WATCH = 0.05
#: How many radial stations a blade's mesh is cut into for its chord.
DEFAULT_STATIONS = 20
#: The directions over half a turn in which a section's width is measured; its
#: largest width is its chord to within ``1 - cos(1.25 deg)``, 0.024 per cent.
_WIDTH_DIRECTIONS = 72


def clocking_angles(blades: int, positions: int) -> tuple[float, ...]:
    """Return the clocking of each steady solve, ``theta_i = i * (360 / N) / k``, in deg.

    The positions are uniform inside ONE blade passage, the arc ``360 / N``
    between two blades, because an axisymmetric wheel of ``N`` identical blades
    repeats itself every passage: a clocking outside it is one inside it.

    Parameters
    ----------
    blades : int
        ``N``, the blade count, one or more.
    positions : int
        ``k``, the row's ``PASSAGE_POSITIONS``, one or more.

    Returns
    -------
    tuple of float
        ``k`` angles, the first 0.

    Raises
    ------
    CampaignConfigError
        A count that is not a positive integer.

    Examples
    --------
    >>> clocking_angles(6, 3)
    (0.0, 20.0, 40.0)
    """
    for name, value in (("blades", blades), ("positions", positions)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CampaignConfigError(
                f"clocking_angles: {name} = {value!r}; a count of blades or of passage "
                "positions is a whole number, one or more"
            )
    passage = 360.0 / blades
    return tuple(index * passage / positions for index in range(positions))


def reduced_frequency(
    *, omega_rad_s: float, chord_m: float, radius_m: float, velocity_m_per_s: float
) -> float:
    """Return the 1P reduced frequency ``k = Omega c / (2 V_rel)`` of one station.

    Parameters
    ----------
    omega_rad_s : float
        The rotor's angular speed; its sign is the hand and is not read.
    chord_m : float
        The station's chord, zero or more.
    radius_m : float
        The station's distance from the shaft.
    velocity_m_per_s : float
        The free-stream speed.

    Returns
    -------
    float

    Raises
    ------
    CampaignConfigError
        A quantity that is not finite, a negative chord, or a station the flow
        does not reach (``V_rel = 0``).

    Examples
    --------
    >>> round(reduced_frequency(omega_rad_s=100.0, chord_m=0.2, radius_m=1.0,
    ...     velocity_m_per_s=0.0), 6)
    0.1
    """
    for name, value in (
        ("omega_rad_s", omega_rad_s),
        ("chord_m", chord_m),
        ("radius_m", radius_m),
        ("velocity_m_per_s", velocity_m_per_s),
    ):
        if not math.isfinite(value):
            raise CampaignConfigError(f"reduced_frequency: {name} = {value!r} is not finite")
    if chord_m < 0.0:
        raise CampaignConfigError(
            f"reduced_frequency: chord_m = {chord_m!r}; a chord is not negative"
        )
    relative = math.hypot(velocity_m_per_s, omega_rad_s * radius_m)
    if relative <= 0.0:
        raise CampaignConfigError(
            "reduced_frequency: the station sees no relative flow (no free stream and no "
            "rotation at its radius), so no time scale exists to compare the rotation with"
        )
    return abs(omega_rad_s) * chord_m / (2.0 * relative)


def strip_lengths(radii: Sequence[float]) -> tuple[float, ...]:
    """Return the length of span each station stands for, by the midpoint rule.

    A strip runs from the midpoint to the previous station to the midpoint to
    the next; the first and the last are half strips. The stations are read in
    the order given, which is ascending radius.

    Parameters
    ----------
    radii : sequence of float
        The stations' radii, ascending, in any length unit.

    Returns
    -------
    tuple of float
        The span each station stands for, in the radii's unit; ``(0.0,)`` for one station and empty
        for none.
    """
    count = len(radii)
    if count == 0:
        return ()
    if count == 1:
        return (0.0,)
    lengths = []
    for index in range(count):
        low = radii[index] if index == 0 else 0.5 * (radii[index - 1] + radii[index])
        high = radii[index] if index == count - 1 else 0.5 * (radii[index] + radii[index + 1])
        lengths.append(abs(high - low))
    return tuple(lengths)


#: The step of the induced inflow below which :func:`glauert_induced_inflow`
#: has converged (0.31.0).
INFLOW_TOLERANCE = 1e-10
#: The Newton steps :func:`glauert_induced_inflow` takes before it says it did
#: not converge.
INFLOW_ITERATIONS = 100


def glauert_induced_inflow(
    ct: float,
    mu: float,
    lambda_c: float,
    *,
    tolerance: float = INFLOW_TOLERANCE,
    iterations: int | None = None,
) -> float | None:
    """Return the momentum-theory induced inflow ``lambda_i`` of a rotor state, or None (0.31.0).

    Glauert's relation for a rotor of thrust coefficient ``ct`` (rotor
    convention, ``T / (rho A (Omega R)^2)``), advance ratio ``mu`` and climb
    inflow ``lambda_c``, both over the tip speed ``Omega R``::

        lambda_i = ct / (2 sqrt(mu^2 + (lambda_c + lambda_i)^2))

    solved by Newton's method on
    ``f(l) = l - ct / (2 sqrt(mu^2 + (lambda_c + l)^2))`` from the hover value
    ``sign(ct) sqrt(|ct| / 2)``, until a step is no larger than ``tolerance``
    (:data:`INFLOW_TOLERANCE`). A thrust of zero induces nothing and is 0.

    None where it does not converge in ``iterations`` steps
    (:data:`INFLOW_ITERATIONS` where not given), where a step is not a finite
    number, or where an input is not one: momentum theory then states no
    inflow, which is typical of a rotor descending into its own wake, and a
    caller writes ``NA`` rather than the last iterate.

    Parameters
    ----------
    ct : float
        Thrust coefficient in rotor convention, ``T / (rho A (Omega R)^2)``.
    mu : float
        Advance ratio over the tip speed.
    lambda_c : float
        Climb inflow over the tip speed.
    tolerance : float, optional
        The largest Newton step taken as converged, :data:`INFLOW_TOLERANCE` by default.
    iterations : int, optional
        The most Newton steps taken, :data:`INFLOW_ITERATIONS` where not given.

    Returns
    -------
    float or None
        ``lambda_i``, 0.0 for zero thrust, or None where the iteration does not converge or an
        input or step is not finite.

    Examples
    --------
    Axial climb, ``mu = 0``: ``l (lambda_c + l) = ct / 2``, so
    ``l = -lambda_c / 2 + sqrt(lambda_c^2 / 4 + ct / 2)``.

    >>> round(glauert_induced_inflow(0.01, 0.0, 0.05), 12)
    0.05
    >>> glauert_induced_inflow(0.0, 0.2, 0.01)
    0.0
    >>> glauert_induced_inflow(0.01, 0.1, 0.0, iterations=1) is None
    True
    """
    steps = INFLOW_ITERATIONS if iterations is None else int(iterations)
    stated = (float(ct), float(mu), float(lambda_c))
    if not all(math.isfinite(value) for value in stated):
        return None
    thrust, advance, climb = stated
    if thrust == 0.0:
        return 0.0
    inflow = math.copysign(math.sqrt(abs(thrust) / 2.0), thrust)
    for _ in range(steps):
        through = climb + inflow
        speed = math.hypot(advance, through)
        if speed == 0.0:
            return None
        residual = inflow - thrust / (2.0 * speed)
        slope = 1.0 + thrust * through / (2.0 * speed**3)
        if slope == 0.0 or not math.isfinite(slope):
            return None
        step = residual / slope
        inflow -= step
        if not math.isfinite(inflow):
            return None
        if abs(step) <= tolerance:
            return inflow
    return None


@dataclass(frozen=True)
class ReducedFrequencies:
    """The 1P reduced frequency of every station of one blade, and its summaries.

    Attributes
    ----------
    radii_m, chords_m, k, strips_m : tuple of float
        Per station, in ascending radius: where it is, its chord, its reduced
        frequency and the span it stands for (:func:`strip_lengths`).
    source : str
        Where the chords came from: ``"mesh"`` (a geometric estimate from the
        blade's surface mesh, the plan's) or ``"sections"`` (the sectional loads
        export of the run).
    """

    radii_m: tuple[float, ...]
    chords_m: tuple[float, ...]
    k: tuple[float, ...]
    strips_m: tuple[float, ...]
    source: str

    @property
    def k_min(self) -> float:
        """The smallest station value."""
        return min(self.k)

    @property
    def k_max(self) -> float:
        """The largest station value."""
        return max(self.k)

    @property
    def k_mean(self) -> float:
        """The mean over the span, each station weighted by its strip."""
        span = sum(self.strips_m)
        if span <= 0.0:
            return sum(self.k) / len(self.k)
        return sum(k * w for k, w in zip(self.k, self.strips_m, strict=True)) / span

    def span_fraction_above(self, limit: float) -> float:
        """Return the fraction of the span, 0 to 1, whose stations exceed ``limit``."""
        span = sum(self.strips_m)
        if span <= 0.0:
            return float(any(k > limit for k in self.k))
        return sum(w for k, w in zip(self.k, self.strips_m, strict=True) if k > limit) / span

    def record(self) -> dict[str, object]:
        """Return the JSON-ready summary the plan, the datapoint file and the products carry."""
        return {
            "k_min": self.k_min,
            "k_max": self.k_max,
            "k_mean": self.k_mean,
            "span_pct_k_gt_0_05": 100.0 * self.span_fraction_above(REDUCED_FREQUENCY_WATCH),
            "span_pct_k_gt_0_1": 100.0 * self.span_fraction_above(REDUCED_FREQUENCY_LIMIT),
            "stations": len(self.k),
            "chord_source": self.source,
        }


def reduced_frequencies(
    radii_m: Sequence[float],
    chords_m: Sequence[float],
    *,
    omega_rad_s: float,
    velocity_m_per_s: float,
    source: str,
) -> ReducedFrequencies:
    """Return the reduced frequency of every station, sorted by radius.

    Parameters
    ----------
    radii_m : sequence of float
        The stations' radii, in metres.
    chords_m : sequence of float
        The chord at each station, in metres.
    omega_rad_s : float
        The rotor's angular speed in radians per second.
    velocity_m_per_s : float
        The free-stream speed in metres per second.
    source : str
        Where the chords came from, ``mesh`` or ``sections``.

    Returns
    -------
    ReducedFrequencies
        The stations sorted by radius with their chords, reduced frequencies and strip lengths.

    Raises
    ------
    CampaignConfigError
        No station, or radii and chords of different counts.
    """
    if not radii_m or len(radii_m) != len(chords_m):
        raise CampaignConfigError(
            f"reduced_frequencies: {len(radii_m)} radii and {len(chords_m)} chords; the "
            "stations are one radius and one chord each, one or more of them"
        )
    ordered = sorted(zip(radii_m, chords_m, strict=True))
    radii = tuple(abs(r) for r, _ in ordered)
    chords = tuple(c for _, c in ordered)
    values = tuple(
        reduced_frequency(
            omega_rad_s=omega_rad_s,
            chord_m=chord,
            radius_m=radius,
            velocity_m_per_s=velocity_m_per_s,
        )
        for radius, chord in zip(radii, chords, strict=True)
    )
    return ReducedFrequencies(radii, chords, values, strip_lengths(radii), source)


def _sub(a: Sequence[float], b: Sequence[float]) -> Vector:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Sequence[float], b: Sequence[float]) -> Vector:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Sequence[float]) -> Vector:
    norm = math.sqrt(_dot(a, a))
    if norm <= 0.0:
        raise CampaignConfigError("a direction of no length names no direction")
    return (a[0] / norm, a[1] / norm, a[2] / norm)


def blade_stations(
    vertices: Iterable[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    count: int = DEFAULT_STATIONS,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Estimate a blade's chord at ``count`` radial stations from its surface vertices.

    The blade's span, from its innermost to its outermost vertex measured from
    the shaft, is cut into ``count`` equal bands; each band's vertices are laid
    on the plane of the shaft and the band's tangential direction, and the
    chord is the section's largest width in that plane, measured over
    :data:`_WIDTH_DIRECTIONS` directions. A band holding fewer than two
    vertices gives no station. It is a GEOMETRIC ESTIMATE: the largest width
    of a cambered, twisted section is its leading-edge to trailing-edge
    distance for any section thinner than it is long, and the band's radial
    width adds nothing because it is removed by the projection.

    Parameters
    ----------
    vertices : iterable of (x, y, z)
        One blade's surface vertices, in metres.
    hub, axis : (x, y, z)
        A point of the shaft and its direction, in the same frame.
    count : int
        How many bands the span is cut into.

    Returns
    -------
    tuple of (radii, chords)
        Per station with two vertices or more, the band's mid radius and the
        chord estimate, in metres, in ascending radius.

    Raises
    ------
    CampaignConfigError
        No vertex, or a span of no length.
    """
    n = _unit(axis)
    placed: list[tuple[float, float, Vector]] = []
    for vertex in vertices:
        p = _sub(vertex, hub)
        a = _dot(p, n)
        q = (p[0] - a * n[0], p[1] - a * n[1], p[2] - a * n[2])
        placed.append((math.sqrt(_dot(q, q)), a, q))
    if not placed:
        raise CampaignConfigError("blade_stations: the blade has no vertex to measure")
    r_low = min(r for r, _, _ in placed)
    r_high = max(r for r, _, _ in placed)
    if r_high - r_low <= 0.0:
        raise CampaignConfigError("blade_stations: the blade's vertices span no radius")
    width = (r_high - r_low) / count
    bands: list[list[tuple[float, float, Vector]]] = [[] for _ in range(count)]
    for entry in placed:
        index = min(int((entry[0] - r_low) / width), count - 1)
        bands[index].append(entry)
    radii: list[float] = []
    chords: list[float] = []
    for index, band in enumerate(bands):
        if len(band) < 2:
            continue
        mean = (
            sum(q[0] for _, _, q in band),
            sum(q[1] for _, _, q in band),
            sum(q[2] for _, _, q in band),
        )
        if _dot(mean, mean) <= 0.0:
            continue
        tangent = _unit(_cross(n, _unit(mean)))
        plane = [(a, _dot(q, tangent)) for _, a, q in band]
        chord = 0.0
        for step in range(_WIDTH_DIRECTIONS):
            angle = math.pi * step / _WIDTH_DIRECTIONS
            c, s = math.cos(angle), math.sin(angle)
            projections = [u * c + v * s for u, v in plane]
            chord = max(chord, max(projections) - min(projections))
        radii.append(r_low + (index + 0.5) * width)
        chords.append(chord)
    return tuple(radii), tuple(chords)


def obj_group_vertices(path: str | Path, *, metres_per_unit: float) -> dict[str, list[Vector]]:
    """Return each ``o``/``g`` group of an OBJ file with the vertices its faces use, in metres.

    A vertex belongs to a group when a face of that group cites it; a vertex
    cited by two groups is in both. Negative (relative) face indices are read
    as the format defines them. A line the reader does not use is passed over.

    Parameters
    ----------
    path : str or Path
        The OBJ file.
    metres_per_unit : float
        The file's length unit in metres; every vertex is multiplied by it.

    Returns
    -------
    dict of str to list of (float, float, float)
        Group name to the vertices its faces cite, in metres, in index order.

    Raises
    ------
    OSError, UnicodeError
        The file cannot be read.
    ValueError
        A vertex or a face index is not a number.
    """
    vertices: list[Vector] = []
    groups: dict[str, set[int]] = {}
    current: str | None = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        head = parts[0]
        if head == "v" and len(parts) >= 4:
            vertices.append(
                (
                    float(parts[1]) * metres_per_unit,
                    float(parts[2]) * metres_per_unit,
                    float(parts[3]) * metres_per_unit,
                )
            )
        elif head in ("o", "g") and len(parts) >= 2:
            current = " ".join(parts[1:])
            groups.setdefault(current, set())
        elif head == "f" and current is not None:
            for token in parts[1:]:
                index = int(token.split("/")[0])
                groups[current].add(index - 1 if index > 0 else len(vertices) + index)
    return {
        name: [vertices[index] for index in sorted(indices) if 0 <= index < len(vertices)]
        for name, indices in groups.items()
    }


#: How far two rows on one ring may differ, in any of the axial, radial and
#: swirl velocities, and still be read as the same flow: a fraction of the
#: field's largest speed. 0.1 per cent: a field extracted from another solution
#: and interpolated onto rings carries round-off and interpolation noise far
#: above 1e-6 of its speed (the first writing refused such fields), while a
#: real azimuthal variation, a crossflow of an angle of attack of a degree or a
#: wake deficit, is well above it.
AXISYMMETRY_SPEED_TOLERANCE = 1e-3
#: How far two rows' distances from the shaft may differ and still be one
#: ring: a fraction of the field's largest radius (0.1 mm on a 1 m disc), above
#: the round-off of coordinates written with six significant digits.
AXISYMMETRY_RADIUS_TOLERANCE = 1e-4


def azimuthal_variation(
    rows: Sequence[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    relative: float = AXISYMMETRY_SPEED_TOLERANCE,
    radius_relative: float = AXISYMMETRY_RADIUS_TOLERANCE,
) -> str | None:
    """Say why an inflow field varies with azimuth, or None when it varies with radius alone.

    The field's rows are ``x y z vx vy vz`` in one frame. Each row's velocity
    is read in the shaft's cylindrical frame, axial, radial and swirl; rows at
    the same radius, to ``radius_relative`` of the largest radius, must state
    the same three components, to ``relative`` of the largest speed. A field
    in which no two rows share a radius cannot show that it varies with the
    radius alone and is named too, because a row is refused rather than
    guessed.

    Parameters
    ----------
    rows : sequence of (x, y, z, vx, vy, vz)
        The field, in metres and metres per second.
    hub, axis : (x, y, z)
        A point of the shaft and its direction.
    relative : float
        The speed tolerance, a fraction of the field's largest speed; by
        default :data:`AXISYMMETRY_SPEED_TOLERANCE`, 0.1 per cent. A caller
        who knows the noise of the field states another.
    radius_relative : float
        The ring tolerance, a fraction of the largest radius; by default
        :data:`AXISYMMETRY_RADIUS_TOLERANCE`.

    Returns
    -------
    str or None
        The reason, naming the two rows' radius and components and the
        tolerance, or None.
    """
    n = _unit(axis)
    placed: list[tuple[float, Vector]] = []
    largest_speed = 0.0
    for row in rows:
        p = _sub(row[:3], hub)
        a = _dot(p, n)
        q = (p[0] - a * n[0], p[1] - a * n[1], p[2] - a * n[2])
        r = math.sqrt(_dot(q, q))
        v = (row[3], row[4], row[5])
        largest_speed = max(largest_speed, math.sqrt(_dot(v, v)))
        if r <= 0.0:
            components: Vector = (_dot(v, n), 0.0, 0.0)
            radial_speed = math.sqrt(max(_dot(v, v) - components[0] ** 2, 0.0))
            components = (components[0], radial_speed, 0.0)
        else:
            e_r = (q[0] / r, q[1] / r, q[2] / r)
            e_t = _cross(n, e_r)
            components = (_dot(v, n), _dot(v, e_r), _dot(v, e_t))
        placed.append((r, components))
    largest_radius = max((r for r, _ in placed), default=0.0)
    radius_tolerance = radius_relative * max(largest_radius, 1e-12)
    speed_tolerance = relative * max(largest_speed, 1e-12)
    placed.sort(key=lambda entry: entry[0])
    shared = False
    for index, (r, components) in enumerate(placed):
        for other_r, other in placed[index + 1 :]:
            if other_r - r > radius_tolerance:
                break
            shared = True
            if any(abs(a - b) > speed_tolerance for a, b in zip(components, other, strict=True)):
                return (
                    f"two rows at radius {r:.6g} m state axial, radial and swirl velocities "
                    f"({components[0]:.6g}, {components[1]:.6g}, {components[2]:.6g}) and "
                    f"({other[0]:.6g}, {other[1]:.6g}, {other[2]:.6g}) m/s, apart by more "
                    f"than {relative:g} of the field's largest speed ({speed_tolerance:.3g} m/s)"
                )
    if not shared:
        return (
            "no two of its rows lie at the same radius from the shaft, so nothing in it shows "
            "that it varies with the radius alone; write it on rings about the hub"
        )
    return None


def _number(record: Mapping[str, object], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CampaignConfigError(f"the validity record states no number under {key!r}")
    return float(value)


def summarise(record: Mapping[str, object]) -> str:
    """Return the four values the plan shows for one point, in one line.

    Parameters
    ----------
    record : mapping of str to object
        One point's reduced-frequency record, with ``span_pct_k_gt_0_1``, ``k_min``, ``k_max`` and
        ``k_mean``.

    Returns
    -------
    str
        The four values in one line.

    Examples
    --------
    >>> summarise({"span_pct_k_gt_0_1": 12.5, "k_min": 0.01, "k_max": 0.2, "k_mean": 0.05})
    'k > 0.1 over 12.5 % of the span, k min 0.0100, k max 0.2000, k mean 0.0500'
    """
    return (
        f"k > {REDUCED_FREQUENCY_LIMIT:g} over {_number(record, 'span_pct_k_gt_0_1'):.1f} % of "
        f"the span, k min {_number(record, 'k_min'):.4f}, k max {_number(record, 'k_max'):.4f}, "
        f"k mean {_number(record, 'k_mean'):.4f}"
    )


#: What a clocking's own loads export adds to the point's loads name: the
#: position's index, two digits, before the extension.
POSITION_SUFFIX = "_qs"
#: The file the run writes beside a quasi-steady point's exports: the case,
#: the clockings and the validity of the quasi-steady assumption.
RECORD_SUFFIX = "_qsteady.json"
#: The file the POST writes beside it for a wheel point (0.30.0): the point's
#: validity after the run, the shares of thrust and torque from the stations
#: above k = 0.1 included. A file of its own because the run's record is a
#: hashed input of the run (its digest is in the run record), never rewritten.
VALIDITY_FILE_SUFFIX = "_qsteady_validity.json"


def position_loads_name(loads: str, index: int) -> str:
    """Return the loads export of clocking ``index``, beside the point's own loads export.

    Parameters
    ----------
    loads : str
        The point's own loads export.
    index : int
        The clocking's index, written with two digits.

    Returns
    -------
    str
        The loads export's name with ``_qs<index>`` before its suffix.

    Examples
    --------
    >>> position_loads_name("DP_AL+050.txt", 3)
    'DP_AL+050_qs03.txt'
    """
    path = PurePath(loads)
    return str(path.with_name(f"{path.stem}{POSITION_SUFFIX}{index:02d}{path.suffix}"))


def position_export_name(name: str, suffix: str, index: int) -> str:
    """Return export ``name`` of clocking ``index``: the position before its kind's suffix (0.31.0).

    A wheel exports its section distributions at every clocking, and each
    clocking's file keeps the suffix that says which kind of export it is, so
    ``_qs<i>`` goes in front of that suffix and never after it: a sectional
    loads export of clocking 2 still ends ``_sloads.txt``. For the loads table
    (suffix ``.txt``) this is :func:`position_loads_name`.

    Parameters
    ----------
    name : str
        The point's export name.
    suffix : str
        The suffix that says which kind of export it is.
    index : int
        The clocking's index, written with two digits.

    Returns
    -------
    str
        The name with ``_qs<index>`` in front of ``suffix``.

    Raises
    ------
    CampaignConfigError
        If ``name`` does not end with ``suffix`` (a ``ValueError``, as before).

    Examples
    --------
    >>> position_export_name("DP_AL+050_sloads.txt", "_sloads.txt", 2)
    'DP_AL+050_qs02_sloads.txt'
    >>> position_export_name("DP_AL+050.txt", ".txt", 3) == position_loads_name("DP_AL+050.txt", 3)
    True
    """
    if not name.endswith(suffix):
        raise CampaignConfigError(
            f"the export {name!r} does not end with its kind's suffix {suffix!r}"
        )
    return f"{name[: len(name) - len(suffix)]}{POSITION_SUFFIX}{index:02d}{suffix}"


def validity_file_name(loads: str) -> str:
    """Return the post's per-point validity file's name, beside the point's own loads export.

    Parameters
    ----------
    loads : str
        The point's own loads export.

    Returns
    -------
    str
        ``<loads stem>_qsteady_validity.json`` in the loads export's folder.

    Examples
    --------
    >>> validity_file_name("DP_AL+050.txt")
    'DP_AL+050_qsteady_validity.json'
    """
    path = PurePath(loads)
    return str(path.with_name(f"{path.stem}{VALIDITY_FILE_SUFFIX}"))


def record_file_name(loads: str) -> str:
    """Return the quasi-steady record's name, beside the point's own loads export.

    Parameters
    ----------
    loads : str
        The point's own loads export.

    Returns
    -------
    str
        ``<loads stem>_qsteady.json`` in the loads export's folder.

    Examples
    --------
    >>> record_file_name("DP_AL+050.txt")
    'DP_AL+050_qsteady.json'
    """
    path = PurePath(loads)
    return str(path.with_name(f"{path.stem}{RECORD_SUFFIX}"))


# --- the point's quasi-steady record (0.31.0): one type, one reader, one refusal ----
#
# ``<point>_qsteady.json`` is written by the builder and read by the run (which
# judges a wheel's one solver log clocking by clocking) and by the post (the
# rotor table's speed, the clockings and average tables, the validity). Until
# 0.31.0 it had no type and two readers with two failure contracts: the post's
# raised on a file it could not read and the run's returned None on the same
# file. Its one type and its one reader live here, beside the name of the file,
# and every failure is one refusal, :class:`QsteadyRecordError`; each caller
# decides what the point loses.

#: The one schema of the record this package writes and reads.
RECORD_SCHEMA_VERSION = 1
#: The run type a quasi-steady record is of: the builder's own name for it,
#: ``pyflightstream.cases.workflows.QSTEADY_ROTOR``, which this module cannot
#: import because the builder imports this module.
RECORD_RUN_TYPE = "qsteady_rotor"
#: The two cases a quasi-steady point is built as.
RECORD_CASES: tuple[str, ...] = ("sector", "wheel")
#: The record's keys, in the order the file holds them.
_RECORD_KEYS: tuple[str, ...] = (
    "schema_version",
    "run_type",
    "case",
    "rotor",
    "blades",
    "rpm",
    "shaft_frame_axis",
    "hub_m",
    "axis_vector",
    "diameter_m",
    "families_general",
    "families_blades",
    "blade1_azimuth_deg",
    "positions",
    "validity",
)
#: The keys of one clocking of the record, in the order the file holds them.
_CLOCKING_KEYS: tuple[str, ...] = ("index", "clocking_deg", "rotated_deg", "loads")
#: The one key a clocking holds only where it applies, after :data:`_CLOCKING_KEYS`:
#: the section exports of a wheel that cuts sections (0.31.0).
_CLOCKING_OPTIONAL_KEYS: tuple[str, ...] = ("section_exports",)


class QsteadyRecordError(PyflightstreamError, ValueError):
    """A point's quasi-steady record is missing, unreadable, or of no schema this package writes.

    The one refusal of :func:`read_qsteady_record`, whatever is wrong with the
    file, so that the callers, and not the reader, decide what the point
    loses: the run judges the point's solver log as one solve and records a
    warning on the point; the post leaves out each product that needs the
    record and names it in ``products.json`` and ``post.log``.
    """


@dataclass(frozen=True)
class QsteadyClocking:
    """One clocking a quasi-steady point was solved at, as its record states it.

    ``clocking_deg`` is where blade one was turned to, in the sense of the
    rotation; ``rotated_deg`` is the signed angle the surfaces were rotated
    by; ``loads`` is the loads export that clocking's solve wrote.
    ``section_exports`` (0.31.0) is, for a wheel that declares section
    distributions only, the file of each section export that clocking wrote,
    keyed by its export kind (``sectional_loads``, ``sections``,
    ``plot_sections_cp``); None for every other record, which then holds no
    such key, so its file is the one 0.30.0 wrote.
    """

    index: int
    clocking_deg: float
    rotated_deg: float
    loads: str
    section_exports: Mapping[str, str] | None = None

    def as_json(self) -> dict[str, Any]:
        """Return the clocking as the record's file holds it."""
        data: dict[str, Any] = {
            "index": self.index,
            "clocking_deg": self.clocking_deg,
            "rotated_deg": self.rotated_deg,
            "loads": self.loads,
        }
        if self.section_exports is not None:
            data["section_exports"] = dict(self.section_exports)
        return data


@dataclass(frozen=True)
class QsteadyRecord:
    """The point's quasi-steady record, ``<point>_qsteady.json``, as one type.

    The builder makes one and parks :meth:`to_text` beside the point's loads
    export; the run and the post read it back with :func:`read_qsteady_record`.
    One field per key of the file, except ``rotor``, held as
    :attr:`rotor_alias` because it is the ALIAS of the rotor block the point
    was built for, a name, and not that block (see
    :func:`qsteady_record_rotor_alias`). ``validity`` is the plan's validity
    record as the builder computed it, kept as it was written, or None where
    the plan estimated none (a sector).

    Examples
    --------
    >>> record = QsteadyRecord(
    ...     case="sector", rotor_alias="PROP", blades=3, rpm=1200.0, shaft_frame_axis="X",
    ...     hub_m=(0.0, 0.0, 0.0), axis_vector=(1.0, 0.0, 0.0), diameter_m=2.0,
    ...     families_general=(), families_blades=("Blade1", "Blade2", "Blade3"),
    ...     blade1_azimuth_deg=0.0,
    ...     positions=(QsteadyClocking(0, 0.0, 0.0, "DP.txt"),), validity=None,
    ... )
    >>> [clocking.index for clocking in record.solve_order()]
    [0]
    >>> record.as_json()["rotor"]
    'PROP'
    """

    #: The schema this type writes and reads (:data:`RECORD_SCHEMA_VERSION`).
    schema_version: ClassVar[int] = RECORD_SCHEMA_VERSION
    #: The run type the record is of (:data:`RECORD_RUN_TYPE`).
    run_type: ClassVar[str] = RECORD_RUN_TYPE

    case: str
    rotor_alias: str
    blades: int
    rpm: float
    shaft_frame_axis: str
    hub_m: tuple[float, float, float]
    axis_vector: tuple[float, float, float]
    diameter_m: float
    families_general: tuple[str, ...]
    families_blades: tuple[str, ...]
    blade1_azimuth_deg: float
    positions: tuple[QsteadyClocking, ...]
    validity: Mapping[str, Any] | None

    def solve_order(self) -> tuple[QsteadyClocking, ...]:
        """Return the clockings in the order the run solved them: 1 to k - 1, then 0.

        Clocking 0 is solved LAST, with the point's full export set, so that
        the solver log and the loads export the run judges the point by are
        of one solve (``cases/workflows/_qsteady_rotor.py::_build_qsteady_rotor``).
        """
        by_index = sorted(self.positions, key=lambda clocking: clocking.index)
        return (*by_index[1:], *by_index[:1])

    def as_json(self) -> dict[str, Any]:
        """Return the record as its file holds it, key for key and in the file's order."""
        return {
            "schema_version": self.schema_version,
            "run_type": self.run_type,
            "case": self.case,
            "rotor": self.rotor_alias,
            "blades": self.blades,
            "rpm": self.rpm,
            "shaft_frame_axis": self.shaft_frame_axis,
            "hub_m": list(self.hub_m),
            "axis_vector": list(self.axis_vector),
            "diameter_m": self.diameter_m,
            "families_general": list(self.families_general),
            "families_blades": list(self.families_blades),
            "blade1_azimuth_deg": self.blade1_azimuth_deg,
            "positions": [clocking.as_json() for clocking in self.positions],
            "validity": self.validity,
        }

    def to_text(self) -> str:
        """Return the record's file: the JSON of :meth:`as_json`, indented by two, one newline."""
        return json.dumps(self.as_json(), indent=2) + "\n"


def qsteady_record_rotor_alias(data: Mapping[str, Any]) -> str:
    """Return the rotor alias a quasi-steady record's JSON object names.

    ``rotor`` in ``<point>_qsteady.json`` is the alias the builder
    (``cases/workflows/_qsteady_rotor.py::_park_the_qsteady_record``) wrote, the NAME of the
    rotor block the point was built for; it is not a read of the recorded
    rotor block itself and shares that word by coincidence of vocabulary
    (PFS-2030.03.02). The record's reader takes it here, and every other
    module reads :attr:`QsteadyRecord.rotor_alias`.

    Parameters
    ----------
    data : mapping of str to object
        The record's JSON object.

    Returns
    -------
    str
        The rotor alias under ``rotor``.

    Raises
    ------
    QsteadyRecordError
        The object names no alias: the key is absent, or not a non-empty string.

    Examples
    --------
    >>> qsteady_record_rotor_alias({"rotor": "PROP"})
    'PROP'
    """
    alias = data.get("rotor")
    if not isinstance(alias, str) or not alias.strip():
        raise QsteadyRecordError(f"names no rotor alias under 'rotor' (it holds {alias!r})")
    return alias


def _record_number(value: object, key: str) -> float:
    """Return a finite JSON number of the record, or refuse it naming its key."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise QsteadyRecordError(f"states no finite number under {key!r} (it holds {value!r})")
    return value


def _record_integer(value: object, key: str, *, least: int) -> int:
    """Return a JSON integer of the record no smaller than ``least``, or refuse it."""
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise QsteadyRecordError(
            f"states no integer of at least {least} under {key!r} (it holds {value!r})"
        )
    return value


def _record_text(value: object, key: str) -> str:
    """Return a non-empty JSON string of the record, or refuse it naming its key."""
    if not isinstance(value, str) or not value.strip():
        raise QsteadyRecordError(f"states no name under {key!r} (it holds {value!r})")
    return value


def _record_vector(value: object, key: str) -> tuple[float, float, float]:
    """Return three JSON numbers of the record, or refuse them naming their key."""
    if not isinstance(value, list) or len(value) != 3:
        raise QsteadyRecordError(f"states no three numbers under {key!r} (it holds {value!r})")
    x, y, z = (_record_number(item, key) for item in value)
    return (x, y, z)


def _record_names(value: object, key: str) -> tuple[str, ...]:
    """Return a JSON list of names of the record, or refuse it naming its key."""
    if not isinstance(value, list):
        raise QsteadyRecordError(f"states no list of names under {key!r} (it holds {value!r})")
    return tuple(_record_text(item, key) for item in value)


def _exact_keys(
    data: Mapping[str, Any], keys: Sequence[str], what: str, *, optional: Sequence[str] = ()
) -> None:
    """Refuse an object whose keys are not exactly ``keys``, plus any of ``optional``.

    A missing key of ``keys`` or a key of neither is refused.
    """
    missing = [key for key in keys if key not in data]
    unknown = sorted(str(key) for key in data if key not in keys and key not in optional)
    if missing or unknown:
        said = "; ".join(
            part
            for part in (
                f"missing {missing}" if missing else "",
                f"unknown {unknown}" if unknown else "",
            )
            if part
        )
        raise QsteadyRecordError(
            f"is not a {what} of schema {RECORD_SCHEMA_VERSION}, the one this package writes: "
            f"{said}"
        )


def _record_clocking(value: object, at: int) -> QsteadyClocking:
    """Return clocking ``at`` of the record's ``positions``, or refuse it."""
    if not isinstance(value, Mapping):
        raise QsteadyRecordError(f"holds no object at positions[{at}] (it holds {value!r})")
    _exact_keys(
        value, _CLOCKING_KEYS, f"clocking (positions[{at}])", optional=_CLOCKING_OPTIONAL_KEYS
    )
    key = f"positions[{at}]"
    index = _record_integer(value["index"], f"{key}.index", least=0)
    if index != at:
        raise QsteadyRecordError(
            f"numbers its clocking at {key} {index}; the builder numbers them 0 to k - 1 "
            "in order, so which export is which clocking's cannot be told"
        )
    return QsteadyClocking(
        index=index,
        clocking_deg=_record_number(value["clocking_deg"], f"{key}.clocking_deg"),
        rotated_deg=_record_number(value["rotated_deg"], f"{key}.rotated_deg"),
        loads=_record_text(value["loads"], f"{key}.loads"),
        section_exports=(
            _record_exports(value["section_exports"], f"{key}.section_exports")
            if "section_exports" in value
            else None
        ),
    )


def _record_exports(value: object, key: str) -> dict[str, str]:
    """Return a clocking's section exports, a JSON object of kind to file name, or refuse it."""
    if not isinstance(value, Mapping):
        raise QsteadyRecordError(
            f"states no object of export kind to file name under {key!r} (it holds {value!r})"
        )
    return {
        _record_text(kind, f"{key} (a kind)"): _record_text(name, f"{key}.{kind}")
        for kind, name in value.items()
    }


def _parse_record(data: object) -> QsteadyRecord:
    """Return the typed record of one parsed JSON document, or refuse it."""
    if not isinstance(data, Mapping):
        raise QsteadyRecordError(f"is not a JSON object (it holds a {type(data).__name__})")
    version = data.get("schema_version")
    if isinstance(version, bool) or version != RECORD_SCHEMA_VERSION:
        raise QsteadyRecordError(
            f"is of schema {version!r}; this package writes and reads schema "
            f"{RECORD_SCHEMA_VERSION} only"
        )
    _exact_keys(data, _RECORD_KEYS, "record")
    if data["run_type"] != RECORD_RUN_TYPE:
        raise QsteadyRecordError(f"is of run type {data['run_type']!r}, not {RECORD_RUN_TYPE!r}")
    case = data["case"]
    if case not in RECORD_CASES:
        raise QsteadyRecordError(f"is of case {case!r}, which is neither of {RECORD_CASES}")
    positions = data["positions"]
    if not isinstance(positions, list) or not positions:
        raise QsteadyRecordError(f"states no clocking under 'positions' (it holds {positions!r})")
    validity = data["validity"]
    if validity is not None and not isinstance(validity, dict):
        raise QsteadyRecordError(
            f"states neither an object nor null under 'validity' (it holds {validity!r})"
        )
    return QsteadyRecord(
        case=str(case),
        rotor_alias=qsteady_record_rotor_alias(data),
        blades=_record_integer(data["blades"], "blades", least=1),
        rpm=_record_number(data["rpm"], "rpm"),
        shaft_frame_axis=_record_text(data["shaft_frame_axis"], "shaft_frame_axis"),
        hub_m=_record_vector(data["hub_m"], "hub_m"),
        axis_vector=_record_vector(data["axis_vector"], "axis_vector"),
        diameter_m=_record_number(data["diameter_m"], "diameter_m"),
        families_general=_record_names(data["families_general"], "families_general"),
        families_blades=_record_names(data["families_blades"], "families_blades"),
        blade1_azimuth_deg=_record_number(data["blade1_azimuth_deg"], "blade1_azimuth_deg"),
        positions=tuple(_record_clocking(value, at) for at, value in enumerate(positions)),
        validity=validity,
    )


def read_qsteady_record(loads_path: Path) -> QsteadyRecord:
    """Return the quasi-steady record the run wrote beside a point's loads export.

    The one reader of ``<point>_qsteady.json`` (:func:`record_file_name` of the
    loads export's name, in the loads export's folder), for the run and the
    post alike.

    Parameters
    ----------
    loads_path : Path
        The point's own loads export; the record is read from beside it.

    Returns
    -------
    QsteadyRecord
        The parsed record.

    Raises
    ------
    QsteadyRecordError
        The record is not on disk, cannot be read or parsed as JSON, is of
        another schema than :data:`RECORD_SCHEMA_VERSION` or another run type,
        misses a key or holds one this package does not write, or holds a
        value of the wrong kind. One refusal for every case: the caller
        decides what the point loses.
    """
    path = loads_path.with_name(Path(record_file_name(loads_path.name)).name)
    if not path.is_file():
        raise QsteadyRecordError(f"the quasi-steady record {path} is not on disk")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise QsteadyRecordError(
            f"the quasi-steady record {path} cannot be read: {error}"
        ) from error
    try:
        return _parse_record(data)
    except QsteadyRecordError as error:
        raise QsteadyRecordError(f"the quasi-steady record {path} {error}") from None


# --- the harmonic content of a custom inflow (0.30.0, ``plan --inflow-fft``) ----
#
# WHAT nP COUNTS. The harmonic order n of this section is the number of times
# ONE BLADE meets a perturbation of the inflow in one revolution, read in the
# blade's own frame as it turns through the field. It is NOT the blade-passing
# excitation N P a fixed surface beside the rotor feels as the N blades go by,
# and it is NOT what a balance under the whole rotor measures: summed over N
# identical blades spaced 360 / N apart, every harmonic of one blade cancels in
# the rotor's total except the multiples of N (m N P). That is why the count of
# clockings a wheel needs is read against n_max / N: the clockings sample one
# blade passage, 360 / N, in which the rotor total repeats.

#: Azimuths per revolution the blade's inflow is read at.
AZIMUTH_SAMPLES = 360
#: The share of the variance of the blade's angle-of-attack perturbation that
#: ``n95`` harmonics hold.
HARMONIC_VARIANCE_SHARE = 0.95
#: The smallest harmonic of the blade's angle-of-attack perturbation that is
#: counted, in degrees of amplitude. A harmonic below it is not counted, and a
#: perturbation with none above it is a constant (``n95`` 0). Measured on
#: 2026-09-29 on fields the blade meets as constant (radial profiles of 5 and
#: 20 % over the span on rings every 0.05 m with 72 per ring, on a 0.05 m
#: Cartesian grid and on 30 rings, and a uniform field with a relative noise of
#: 1e-6, at 1200 rev/min and 20 m/s), the sampling leaves at most 8.5e-5 deg, so
#: 0.001 deg sits twelve times above it; the smallest content that matters sits
#: well above it: a 1 deg crossflow reaches the blade as 0.03 deg at the tip of
#: that rotor, a 1 % six-lobed inflow as 0.10 deg, and 0.001 deg moves a
#: section's lift coefficient by 2 pi 1.7e-5, about 1e-4.
HARMONIC_AMPLITUDE_FLOOR_DEG = 0.001
#: How many of the field's rows one sample is fitted to.
_NEAREST_ROWS = 12


def harmonic_variance_shares(signal: Sequence[float], *, floor: float = 0.0) -> Any:
    """Return the share of the variance each harmonic 1, 2, ... holds, as an array.

    The rule of :func:`harmonic_order` (Parseval on the discrete Fourier
    transform of the mean-removed revolution, a harmonic below ``floor`` in
    amplitude not counted, the shares of those counted adding to 1), split
    out so the per-harmonic shares and ``n95`` are one computation. A signal
    with no variation, or none above ``floor``, gives all zeros; fewer than
    two samples give an empty array.

    Parameters
    ----------
    signal : sequence of float
        One revolution sampled uniformly in azimuth.
    floor : float, optional
        The amplitude below which a harmonic is not counted, in the signal's units.

    Returns
    -------
    ndarray
        The share of the counted variance each harmonic 1, 2, ... holds; all zeros with no counted
        harmonic, empty for fewer than two samples.

    Examples
    --------
    >>> import math
    >>> psi = [2 * math.pi * i / 360 for i in range(360)]
    >>> [round(float(s), 3) for s in harmonic_variance_shares(
    ...     [math.cos(p) + math.cos(2 * p) for p in psi])[:3]]
    [0.5, 0.5, 0.0]
    """
    import numpy as np

    values = np.asarray(signal, dtype=float)
    count = len(values)
    if count < 2:
        return np.zeros(0)
    spectrum = np.fft.rfft(values - values.mean())
    amplitude = 2.0 * np.abs(spectrum[1:]) / count
    energy = 2.0 * np.abs(spectrum[1:]) ** 2
    if count % 2 == 0:
        energy[-1] /= 2.0
        amplitude[-1] /= 2.0
    energy[amplitude < floor] = 0.0
    total = float(energy.sum())
    if total <= 1e-30 * max(1.0, float(np.abs(values).max()) ** 2 * count**2):
        return np.zeros(len(energy))
    return energy / total


def harmonic_order(
    signal: Sequence[float], *, share: float = HARMONIC_VARIANCE_SHARE, floor: float = 0.0
) -> int:
    """Return ``n95``: the smallest n whose harmonics 1 to n hold ``share`` of the variance.

    ``signal`` is one revolution sampled uniformly in azimuth; its mean is
    removed first. The variance of each harmonic is read off the discrete
    Fourier transform (Parseval: ``2 |X_n|^2`` for every bin below Nyquist,
    ``|X_n|^2`` at it, over ``N^2``). A harmonic whose amplitude (``2 |X_n| /
    N``, ``|X_n| / N`` at Nyquist, in the signal's units) is below ``floor`` is
    not counted, and the share is of the harmonics that are. A signal with no
    variation, or none above ``floor``, holds no harmonic and gives 0.

    Parameters
    ----------
    signal : sequence of float
        One revolution sampled uniformly in azimuth.
    share : float, optional
        The share of the variance to hold, :data:`HARMONIC_VARIANCE_SHARE` by default.
    floor : float, optional
        The amplitude below which a harmonic is not counted, in the signal's units.

    Returns
    -------
    int
        ``n95``, or 0 for a signal with no harmonic above ``floor``.

    Examples
    --------
    >>> import math
    >>> psi = [2 * math.pi * i / 360 for i in range(360)]
    >>> harmonic_order([math.cos(3 * p) for p in psi])
    3
    >>> harmonic_order([math.cos(3 * p) + 1e-4 * math.cos(40 * p) for p in psi], floor=1e-3)
    3
    >>> harmonic_order([1e-4 * math.cos(40 * p) for p in psi], floor=1e-3)
    0
    """
    import numpy as np

    shares = harmonic_variance_shares(signal, floor=floor)
    if len(shares) == 0 or float(shares.sum()) == 0.0:
        return 0
    return int(np.searchsorted(np.cumsum(shares), share - 1e-12) + 1)


def suggested_passage_positions(n_max: int, blades: int) -> int:
    """Return the fewest clockings holding the rotor total's harmonics: ``n_max / N + 1``, up.

    The rotor total carries only the multiples of N of one blade's
    harmonics, and the clockings sample one blade passage, so ``k`` clockings
    resolve the rotor-total harmonics up to about ``(k - 1) N``; the count
    that reaches ``n_max`` is the smallest whole ``k >= n_max / N + 1``.

    Parameters
    ----------
    n_max : int
        The highest per-blade harmonic to hold.
    blades : int
        The blade count N.

    Returns
    -------
    int
        The smallest whole ``k >= n_max / N + 1``; 1 where ``n_max`` is not positive.

    Examples
    --------
    >>> suggested_passage_positions(1, 3), suggested_passage_positions(6, 6)
    (2, 2)
    >>> suggested_passage_positions(0, 6), suggested_passage_positions(7, 6)
    (1, 3)
    """
    if n_max <= 0:
        return 1
    return -(-n_max // blades) + 1


def _field_sampler(
    rows: Sequence[Sequence[float]], *, hub: Sequence[float], axis: Sequence[float]
) -> tuple[Any, Any, tuple[Any, Any, Any]]:
    """Return the field's rows as disc-plane coordinates and velocities, and the plane basis."""
    import numpy as np

    n = np.asarray(_unit(axis))
    data = np.asarray(rows, dtype=float)
    relative = data[:, :3] - np.asarray(hub, dtype=float)
    trial = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = trial - n * float(trial @ n)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    plane = np.column_stack((relative @ e1, relative @ e2))
    return plane, data[:, 3:6], (n, e1, e2)


def _sample_velocities(plane: Any, velocities: Any, points: Any) -> Any:
    """Return the field's velocity at each of ``points``: a quadratic fitted to its nearest rows.

    At each point a quadratic in the disc-plane offsets is fitted, by least
    squares weighted by the inverse distance, to the point's
    :data:`_NEAREST_ROWS` nearest rows, and its value at the point is taken,
    held within the least and greatest of those rows so it never reaches past
    the field. A quadratic reproduces a field that varies smoothly between the
    rows, a radial profile on a Cartesian grid or on rings, to third order in
    the spacing, where a weighted mean of the rows leaves a ripple at the
    rows' own spacing that the spectrum would count (on the fields
    :data:`HARMONIC_AMPLITUDE_FLOOR_DEG` names, up to 1.4e-2 deg of angle of
    attack against 8.5e-5 deg).
    """
    import numpy as np

    nearest = min(_NEAREST_ROWS, len(plane))
    distance = np.hypot(
        points[:, None, 0] - plane[None, :, 0], points[:, None, 1] - plane[None, :, 1]
    )
    index = np.argpartition(distance, nearest - 1, axis=1)[:, :nearest]
    near = np.take_along_axis(distance, index, axis=1)
    offset = plane[index] - points[:, None, :]
    scale = np.maximum(near.max(axis=1), 1e-12)[:, None]
    x, y = offset[..., 0] / scale, offset[..., 1] / scale
    design = np.stack((np.ones_like(x), x, y, x * x, x * y, y * y), axis=-1)
    weight = (1.0 / np.maximum(near, 1e-12 * scale))[..., None]
    values = velocities[index]
    solution = np.linalg.pinv(design * weight) @ (values * weight)
    return np.clip(solution[:, 0, :], values.min(axis=1), values.max(axis=1))


def blade_inflow_harmonics(
    rows: Sequence[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    omega_rad_s: float,
    radii_m: Sequence[float],
    samples: int = AZIMUTH_SAMPLES,
) -> tuple[int, ...]:
    """Return ``n95`` of the angle-of-attack perturbation one blade meets at each radius.

    At each radius the blade is carried once round the disc: at every one of
    ``samples`` azimuths the field's TOTAL velocity ``v`` there is read (a
    quadratic fitted to its twelve nearest rows in the disc plane,
    :func:`_sample_velocities`, an estimate that smooths a feature finer than
    the field's own spacing), the velocity relative to the turning blade is
    composed, ``w = v - Omega axis x (p - hub)``, and its inflow angle is
    taken, ``phi = atan2(w_axial, w_tangential)`` with the tangential
    component counted against the blade's motion. The perturbation is ``phi``
    less its mean over the revolution (the angle of attack moves by minus
    that), and :func:`harmonic_order` counts its harmonics of at least
    :data:`HARMONIC_AMPLITUDE_FLOOR_DEG`, so a field the blade meets as a
    constant gives 0. The count is in the BLADE's frame (the section's
    comment above says what it is not).

    Parameters
    ----------
    rows : sequence of (x, y, z, vx, vy, vz)
        The field, in metres and metres per second, in one frame.
    hub, axis : (x, y, z)
        A point of the shaft and its direction, in that frame.
    omega_rad_s : float
        The rotor's angular speed, signed by its hand about ``axis``.
    radii_m : sequence of float
        The stations.
    samples : int
        Azimuths per revolution.

    Returns
    -------
    tuple of int
        ``n95`` per station, in the order given.
    """
    floor = math.radians(HARMONIC_AMPLITUDE_FLOOR_DEG)
    return tuple(
        harmonic_order(
            blade_inflow_angles(
                rows,
                hub=hub,
                axis=axis,
                omega_rad_s=omega_rad_s,
                radius_m=radius,
                samples=samples,
            )[0].tolist(),
            floor=floor,
        )
        for radius in radii_m
    )


def blade_inflow_angles(
    rows: Sequence[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    omega_rad_s: float,
    radius_m: float,
    samples: int = AZIMUTH_SAMPLES,
) -> tuple[Any, Any]:
    """Return the inflow angle and the relative speed one blade meets round one revolution.

    The reading :func:`blade_inflow_harmonics` takes at each radius, public
    so the tools that go beyond ``n95`` (0.32.0, the per-harmonic shares and
    the reduced frequency of :mod:`pyflightstream.post.inflow_tools`) read
    the field ONE way. At each of ``samples`` azimuths the TOTAL velocity is
    read, the velocity relative to the turning blade composed,
    ``w = v - Omega axis x (p - hub)``, and ``phi = atan2(w_axial,
    w_tangential)`` taken with the tangential component counted against the
    blade's motion. The azimuth is positive in the sense of ``omega_rad_s``.

    Parameters
    ----------
    rows : sequence of (x, y, z, vx, vy, vz)
        The field, in metres and metres per second, in one frame.
    hub : (x, y, z)
        A point of the shaft, in metres, in that frame.
    axis : (x, y, z)
        The shaft's direction in that frame.
    omega_rad_s : float
        The rotor's angular speed in radians per second, signed by its hand about ``axis``.
    radius_m : float
        The radius the blade section is carried round at, in metres.
    samples : int, optional
        Azimuths per revolution, :data:`AZIMUTH_SAMPLES` by default.

    Returns
    -------
    (ndarray, ndarray)
        ``phi`` in radians and the relative speed in the blade's section
        plane, ``hypot(w_axial, w_tangential)``, in metres per second, one
        per azimuth.
    """
    import numpy as np

    plane, velocities, (n, e1, e2) = _field_sampler(rows, hub=hub, axis=axis)
    psi = 2.0 * np.pi * np.arange(samples) / samples
    sense = 1.0 if omega_rad_s >= 0.0 else -1.0
    points = np.column_stack((radius_m * np.cos(psi), radius_m * np.sin(psi)))
    v = _sample_velocities(plane, velocities, points)
    e_r = np.outer(np.cos(psi), e1) + np.outer(np.sin(psi), e2)
    e_t = np.cross(n, e_r)
    w = v - omega_rad_s * radius_m * e_t
    axial = w @ n
    against = -sense * np.einsum("sc,sc->s", w, e_t)
    return np.arctan2(axial, against), np.hypot(axial, against)


@dataclass(frozen=True)
class InflowHarmonics:
    """The harmonic content of a custom inflow as one blade of a wheel meets it.

    Attributes
    ----------
    radii_m, n95 : tuple
        Per station: its radius and the harmonic order holding 95 per cent of
        its angle-of-attack perturbation (:func:`blade_inflow_harmonics`).
    k_1p : tuple of float or None
        Per station, the 1P reduced frequency, where the chord is known.
    strips_m : tuple of float
        The span each station stands for (:func:`strip_lengths`).
    blades : int
        ``N``.
    """

    radii_m: tuple[float, ...]
    n95: tuple[int, ...]
    k_1p: tuple[float, ...] | None
    strips_m: tuple[float, ...]
    blades: int

    @property
    def n_max(self) -> int:
        """The largest relevant harmonic: the highest ``n95`` of any station."""
        return max(self.n95, default=0)

    @property
    def k_eff(self) -> tuple[float, ...] | None:
        """``k_eff = n95 k_1P`` per station, or None where the chord is not known."""
        if self.k_1p is None:
            return None
        return tuple(n * k for n, k in zip(self.n95, self.k_1p, strict=True))

    def record(self, *, declared_positions: int | None) -> dict[str, object]:
        """Return the JSON-ready record the plan carries under ``inflow_fft``."""
        suggested = suggested_passage_positions(self.n_max, self.blades)
        record: dict[str, object] = {
            "radius_m": list(self.radii_m),
            "n95": list(self.n95),
            "n_max": self.n_max,
            "blades": self.blades,
            "suggested_passage_positions": suggested,
            "passage_positions": declared_positions,
            "sampling": (
                f"{AZIMUTH_SAMPLES} azimuths per revolution, the field read by a quadratic "
                f"fitted to its {_NEAREST_ROWS} nearest rows; harmonics below "
                f"{HARMONIC_AMPLITUDE_FLOOR_DEG} deg of angle of attack not counted"
            ),
        }
        effective = self.k_eff
        if effective is None:
            record.update(
                {
                    "k_eff_min": None,
                    "k_eff_max": None,
                    "k_eff_mean": None,
                    "span_pct_k_eff_gt_0_1": None,
                    "k_eff": None,
                }
            )
            return record
        span = sum(self.strips_m)
        mean = (
            sum(k * w for k, w in zip(effective, self.strips_m, strict=True)) / span
            if span > 0.0
            else sum(effective) / len(effective)
        )
        above = (
            sum(
                w
                for k, w in zip(effective, self.strips_m, strict=True)
                if k > REDUCED_FREQUENCY_LIMIT
            )
            / span
            if span > 0.0
            else float(any(k > REDUCED_FREQUENCY_LIMIT for k in effective))
        )
        record.update(
            {
                "k_eff_min": min(effective),
                "k_eff_max": max(effective),
                "k_eff_mean": mean,
                "span_pct_k_eff_gt_0_1": 100.0 * above,
                "k_eff": list(effective),
            }
        )
        return record


def summarise_inflow_harmonics(record: Mapping[str, object]) -> str:
    """Return the words the plan prints for one point's ``inflow_fft`` record.

    Parameters
    ----------
    record : mapping of str to object
        One point's ``inflow_fft`` record.

    Returns
    -------
    str
        The harmonic order and the suggested clockings, then the effective reduced frequency or why
        it was not computed, separated by a semicolon.

    Examples
    --------
    >>> words = summarise_inflow_harmonics({"n_max": 4, "suggested_passage_positions": 2,
    ...     "passage_positions": 2, "span_pct_k_eff_gt_0_1": 25.0, "k_eff_min": 0.02,
    ...     "k_eff_max": 0.3, "k_eff_mean": 0.1})
    >>> for part in words.split("; "):
    ...     print(part)
    inflow harmonics (per blade, nP): n_max 4, suggested PASSAGE_POSITIONS >= 2 (stated 2)
    k_eff > 0.1 over 25.0 % of the span, k_eff min 0.0200, k_eff max 0.3000, k_eff mean 0.1000
    """
    head = (
        f"inflow harmonics (per blade, nP): n_max {record.get('n_max')}, suggested "
        f"PASSAGE_POSITIONS >= {record.get('suggested_passage_positions')} "
        f"(stated {record.get('passage_positions')})"
    )
    if record.get("k_eff_max") is None:
        return head + "; k_eff not computed, the chord is not known at plan time"
    return (
        f"{head}; k_eff > {REDUCED_FREQUENCY_LIMIT:g} over "
        f"{_number(record, 'span_pct_k_eff_gt_0_1'):.1f} % of the span, "
        f"k_eff min {_number(record, 'k_eff_min'):.4f}, k_eff max "
        f"{_number(record, 'k_eff_max'):.4f}, k_eff mean {_number(record, 'k_eff_mean'):.4f}"
    )
