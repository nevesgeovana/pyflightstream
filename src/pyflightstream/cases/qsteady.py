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
  which is what a periodic sector can stand for.

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

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from pyflightstream.cases import CampaignConfigError

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


def azimuthal_variation(
    rows: Sequence[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    relative: float = 1e-6,
) -> str | None:
    """Say why an inflow field varies with azimuth, or None when it varies with radius alone.

    The field's rows are ``x y z vx vy vz`` in one frame. Each row's velocity
    is read in the shaft's cylindrical frame, axial, radial and swirl; rows at
    the same radius, to ``relative`` of the largest radius, must state the same
    three components, to ``relative`` of the largest speed. A field in which no
    two rows share a radius cannot show that it varies with the radius alone
    and is named too, because a row is refused rather than guessed.

    Returns
    -------
    str or None
        The reason, naming the two rows' radius and components, or None.
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
    radius_tolerance = relative * max(largest_radius, 1e-12)
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
                    f"({other[0]:.6g}, {other[1]:.6g}, {other[2]:.6g}) m/s"
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


def position_loads_name(loads: str, index: int) -> str:
    """Return the loads export of clocking ``index``, beside the point's own loads export.

    Examples
    --------
    >>> position_loads_name("DP_AL+050.txt", 3)
    'DP_AL+050_qs03.txt'
    """
    path = PurePath(loads)
    return str(path.with_name(f"{path.stem}{POSITION_SUFFIX}{index:02d}{path.suffix}"))


def record_file_name(loads: str) -> str:
    """Return the quasi-steady record's name, beside the point's own loads export.

    Examples
    --------
    >>> record_file_name("DP_AL+050.txt")
    'DP_AL+050_qsteady.json'
    """
    path = PurePath(loads)
    return str(path.with_name(f"{path.stem}{RECORD_SUFFIX}"))
