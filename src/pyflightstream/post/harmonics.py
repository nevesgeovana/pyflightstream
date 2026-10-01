"""The per-station harmonic product of a rotor point (0.31.0, P0310-HARMONICS).

For each rotor of a point, each blade station and each sectional load
quantity of the sections export, the least-squares fit

    load(psi) = H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)

over every sample of that station, ``psi`` being the sample's blade azimuth
as the WRITTEN sections table states it. The samples are:

* on a quasi-steady WHEEL, every blade at every clocking of the point, read
  from ``sections/<point>_sections.csv``, whose ``AZIMUTH`` is each block's own
  blade at its clocking (the wheel's premise is identical blades);
* on an ``unsteady_rotor`` point, every blade at every step of the last
  complete revolution of that rotor, read from
  ``series/<point>_sections_series.csv``, whose ``AZIMUTH`` is, since 0.31.0,
  each block's own blade's (the writer places blade n through
  :func:`pyflightstream.post.axes.placed_blade_azimuth_deg`).

No azimuth is computed here: every angle is the table's own or comes from
:mod:`pyflightstream.post.axes`, the one home of where a blade is.

``PHI_k`` is the phase of the k-th harmonic in degrees in [0, 360): the kP
term peaks where ``k psi = PHI_k``, so the 1P peak is at the azimuth
``PHI1`` and the 2P peaks at ``PHI2 / 2`` and ``PHI2 / 2 + 180``. A harmonic
whose station holds fewer distinct azimuths than it needs (1P needs 3, 2P
needs 5, the unknowns of the fit up to it) is ``NA``. The definitions page,
``docs/post-processing-definitions.md``, is the definition of record.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pyflightstream._errors import ProductError
from pyflightstream._tokens import (
    CONTEXT_COLUMNS,
    INTEGRATED_SECTION_COLUMNS,
    NOT_APPLICABLE,
    POLAR_ID_COLUMN,
)
from pyflightstream.post._tables import write_csv_table
from pyflightstream.post.axes import placed_blade_azimuth_deg
from pyflightstream.post.qsteady import CLOCKING_COLUMN, STATION_COLUMN, VALIDITY_COLUMNS

__all__ = [
    "AZIMUTH_TOLERANCE_DEG",
    "HARMONICS_COLUMNS",
    "HARMONIC_COLUMNS",
    "HARMONICS_KIND",
    "HARMONICS_SUFFIX",
    "MINIMUM_DISTINCT_AZIMUTHS",
    "SOURCE_UNSTEADY",
    "SOURCE_WHEEL",
    "STATION_MATCH_TOLERANCE",
    "HarmonicFit",
    "HarmonicRotor",
    "StationHarmonics",
    "blade_of",
    "distinct_azimuths",
    "fit_harmonics",
    "last_complete_revolution",
    "load_quantities",
    "sample_blocks",
    "station_harmonics",
    "write_harmonics_table",
]

#: The file a point's harmonic product is written to, after the point's name.
HARMONICS_SUFFIX = "_harmonics.csv"
#: The ``kind`` of its ``products.json`` entry.
HARMONICS_KIND = "harmonics"
#: The ``source`` of its entry, for each of the two run types that have one.
SOURCE_WHEEL = "wheel clockings"
SOURCE_UNSTEADY = "unsteady last revolution"
#: The columns after ``POL`` and the condition, in this order.
HARMONIC_COLUMNS: tuple[str, ...] = (
    "ROTOR",
    "QUANTITY",
    "STATION_R_M",
    "R_OVER_R",
    "SAMPLES",
    "DISTINCT_AZIMUTHS",
    "H0",
    "H1_AMP",
    "H1_PHASE_DEG",
    "H2_AMP",
    "H2_PHASE_DEG",
    "RESIDUAL_RMS",
)
#: The whole header of the product.
HARMONICS_COLUMNS: tuple[str, ...] = (POLAR_ID_COLUMN, *CONTEXT_COLUMNS, *HARMONIC_COLUMNS)
#: The distinct azimuths each harmonic needs: the unknowns of the fit up to it.
MINIMUM_DISTINCT_AZIMUTHS: Mapping[int, int] = {1: 3, 2: 5}
#: Two azimuths closer than this, in degrees around the circle, are one azimuth.
AZIMUTH_TOLERANCE_DEG = 1e-6
#: How far a sample's station may sit from the first sample's, as a fraction
#: of the largest radius of the first sample, before the station is refused.
STATION_MATCH_TOLERANCE = 1e-6
#: The sections columns that locate a station rather than load it.
_GEOMETRY_COLUMNS = frozenset({"Offset", "Chord", "X_QC", "Z_QC"})
#: The columns the post adds after the export's own, which are not loads.
_ADDED_COLUMNS = frozenset(
    {CLOCKING_COLUMN, STATION_COLUMN, *VALIDITY_COLUMNS, *INTEGRATED_SECTION_COLUMNS}
)


@dataclass(frozen=True)
class HarmonicFit:
    """The fit of one station and quantity; a harmonic that cannot be fitted is None."""

    samples: int
    distinct: int
    h0: float
    h1_amp: float | None
    h1_phase_deg: float | None
    h2_amp: float | None
    h2_phase_deg: float | None
    residual_rms: float


@dataclass(frozen=True)
class HarmonicRotor:
    """What the product needs of one rotor.

    ``blades`` holds, for blade n (from 1), the section families a block of
    that blade may state; a block is blade n's when every family it states
    is one of them, and a block of any other families is not a sample.
    ``azimuth_is_blade_one`` says what the table's ``AZIMUTH`` is: blade one's
    (a table written before 0.31.0 states it for every block), so a block of
    blade n is placed at its own blade, or the block's own blade's (a wheel's
    sections table and, since 0.31.0, an unsteady sections series).
    """

    alias: str
    blades: tuple[tuple[str, ...], ...]
    diameter_m: float | None
    azimuth_is_blade_one: bool


@dataclass
class StationHarmonics:
    """The fits of one point and what could not be fitted, for the stage to say.

    ``rows`` are ``(rotor, quantity, radius, r / R, fit)``. ``samples`` counts
    the blade samples of each rotor fitted. ``skipped`` maps a marker
    (``#rotor=<alias>`` or ``#rotor=<alias>#station=<j>``) to why nothing of it
    is a row. ``notes`` are the post-log lines, one per rotor and harmonic
    that is ``NA`` somewhere.
    """

    rows: list[tuple[str, str, float, float | None, HarmonicFit]] = field(default_factory=list)
    samples: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def distinct_azimuths(azimuths_deg: Sequence[float]) -> int:
    """Return how many distinct azimuths the samples hold, around the circle.

    Two azimuths within :data:`AZIMUTH_TOLERANCE_DEG` of each other, 360 and 0
    included, are one.

    Parameters
    ----------
    azimuths_deg : sequence of float
        The samples' azimuths, in degrees.

    Returns
    -------
    int
        The number of distinct azimuths; 0 for no sample.

    Examples
    --------
    >>> distinct_azimuths([0.0, 360.0, 90.0, 90.0, 180.0])
    3
    """
    turned = sorted(float(value) % 360.0 for value in azimuths_deg)
    if not turned:
        return 0
    count = 1
    for before, after in zip(turned[:-1], turned[1:], strict=True):
        if after - before > AZIMUTH_TOLERANCE_DEG:
            count += 1
    if count > 1 and turned[0] + 360.0 - turned[-1] <= AZIMUTH_TOLERANCE_DEG:
        count -= 1
    return count


#: Degrees below 360 still read as 0: far above round-off (1e-13 deg) and far below any
#: azimuth a sectional export resolves.
_PHASE_WRAP_DEG = 1e-9


def _phase_deg(cosine: float, sine: float) -> float:
    """Return the phase of ``cosine cos x + sine sin x`` in degrees in [0, 360)."""
    phase = math.degrees(math.atan2(sine, cosine)) % 360.0
    # A least-squares sine of a pure cosine is round-off, about -1e-17, whose atan2
    # lands a hair below 360 (359.99999999999994 on Linux, 0.0 on Windows): a phase
    # within _PHASE_WRAP_DEG of 0 or of 360 is the same azimuth and is stated as 0.
    return 0.0 if phase < _PHASE_WRAP_DEG or phase >= 360.0 - _PHASE_WRAP_DEG else phase


def fit_harmonics(azimuths_deg: Sequence[float], values: Sequence[float]) -> HarmonicFit:
    """Fit ``H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)`` by least squares.

    The fit holds the harmonics the samples can carry: 2P with five distinct
    azimuths or more, 1P with three or more, ``H0`` alone below that; a
    harmonic left out is None. ``RESIDUAL_RMS`` is the root mean square of
    the samples less the fit that was made.

    Parameters
    ----------
    azimuths_deg : sequence of float
        The samples' azimuths, in degrees.
    values : sequence of float
        The value at each azimuth.

    Returns
    -------
    HarmonicFit
        The sample counts, ``H0``, the amplitude and phase [deg] of each harmonic fitted (None for
        one left out) and ``RESIDUAL_RMS``.

    Raises
    ------
    ProductError
        When there is not one value per azimuth, or no sample at all. It is
        a ``ValueError``, so an existing ``except ValueError`` still holds.

    Examples
    --------
    >>> psi = [0.0, 90.0, 180.0, 270.0]
    >>> fit = fit_harmonics(psi, [2.0 + math.cos(math.radians(p - 90.0)) for p in psi])
    >>> round(fit.h0, 9), round(fit.h1_amp, 9), round(fit.h1_phase_deg, 9), fit.h2_amp
    (2.0, 1.0, 90.0, None)
    """
    psi = np.radians(np.asarray(azimuths_deg, dtype=float))
    load = np.asarray(values, dtype=float)
    if psi.shape != load.shape or load.size == 0:
        raise ProductError("a fit needs one value per azimuth and at least one sample")
    distinct = distinct_azimuths([float(value) for value in azimuths_deg])
    orders = max(
        (order for order, needed in MINIMUM_DISTINCT_AZIMUTHS.items() if distinct >= needed),
        default=0,
    )
    design = [np.ones_like(psi)]
    for order in range(1, orders + 1):
        design.extend((np.cos(order * psi), np.sin(order * psi)))
    matrix = np.column_stack(design)
    coefficients, *_ = np.linalg.lstsq(matrix, load, rcond=None)
    residual = load - matrix @ coefficients
    terms: list[float | None] = []
    for order in (1, 2):
        if order > orders:
            terms.extend((None, None))
            continue
        cosine, sine = float(coefficients[2 * order - 1]), float(coefficients[2 * order])
        terms.extend((math.hypot(cosine, sine), _phase_deg(cosine, sine)))
    return HarmonicFit(
        samples=int(load.size),
        distinct=distinct,
        h0=float(coefficients[0]),
        h1_amp=terms[0],
        h1_phase_deg=terms[1],
        h2_amp=terms[2],
        h2_phase_deg=terms[3],
        residual_rms=float(np.sqrt(np.mean(residual**2))),
    )


def last_complete_revolution(
    first_step: int, last_step: int, steps_per_revolution: float
) -> tuple[int, int] | None:
    """Return the first and last step of the last complete revolution, or None.

    Revolution k is steps ``first + (k - 1) N`` to ``first + k N - 1``, counted
    from the history's first step as the per-revolution product counts from
    its first row, with ``N`` the steps per revolution rounded to a whole
    step; the last one whose steps all lie inside the history is returned.

    Parameters
    ----------
    first_step : int
        The history's first step.
    last_step : int
        The history's last step.
    steps_per_revolution : float
        The rotor's clock, in steps per revolution.

    Returns
    -------
    tuple of (int, int) or None
        The first and last step of that revolution, or None where no revolution is complete.

    Examples
    --------
    >>> last_complete_revolution(3, 13, 4.0)
    (7, 10)
    >>> last_complete_revolution(3, 5, 4.0) is None
    True
    """
    steps = int(round(float(steps_per_revolution)))
    if steps < 1 or last_step < first_step:
        return None
    complete = (last_step - first_step + 1) // steps
    if complete < 1:
        return None
    start = first_step + (complete - 1) * steps
    return start, start + steps - 1


def load_quantities(columns: Sequence[str]) -> list[str]:
    """Return the sectional load columns of a sections table, in its order.

    Every column of the export after the condition that is not a station's
    place (``Offset``, ``Chord``, ``X_QC``, ``Z_QC``) nor one the post adds
    (the clocking, the reduced frequency, the validity, the integrated
    strips): ``Fx``, ``Fz`` and ``Moment`` on today's export.

    Parameters
    ----------
    columns : sequence of str
        The sections table's columns.

    Returns
    -------
    list of str
        The load columns, in the table's order.
    """
    names = list(columns)
    start = max((names.index(name) for name in CONTEXT_COLUMNS if name in names), default=-1)
    return [
        name
        for name in names[start + 1 :]
        if name not in _GEOMETRY_COLUMNS and name not in _ADDED_COLUMNS
    ]


def blade_of(families: Sequence[str], rotor: HarmonicRotor) -> int | None:
    """Return the blade of ``rotor`` (from 1) whose families include every one given, or None.

    Parameters
    ----------
    families : sequence of str
        The families of one block of the table.
    rotor : HarmonicRotor
        The rotor, with its blades' families.

    Returns
    -------
    int or None
        The blade's number, from 1, or None where no blade carries every family.
    """
    if not families:
        return None
    for number, members in enumerate(rotor.blades, start=1):
        if set(families) <= set(members):
            return number
    return None


def sample_blocks(
    rows: Sequence[Mapping[str, str]], sample_column: str
) -> list[list[Mapping[str, str]]]:
    """Split the table into its blocks: consecutive rows of one sample and one distribution.

    Parameters
    ----------
    rows : sequence of mapping of str to str
        The table's rows as :func:`~pyflightstream.post.products.read_csv_table` reads them, cut to
        the samples wanted.
    sample_column : str
        The column that tells one sample from the next, ``CLOCKING`` or ``STEP``.

    Returns
    -------
    list of list of mapping
        The blocks, each the consecutive rows of one sample and one distribution, in table order.
    """
    blocks: list[list[Mapping[str, str]]] = []
    key: tuple[str, str, str, str] | None = None
    for row in rows:
        now = (
            row.get(sample_column, ""),
            row.get("FAMILY", ""),
            row.get("PLANE", ""),
            row.get("ROTOR", ""),
        )
        if now != key:
            blocks.append([])
            key = now
        blocks[-1].append(row)
    return blocks


def station_harmonics(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    rotors: Mapping[str, HarmonicRotor],
    *,
    sample_column: str,
) -> StationHarmonics:
    """Fit every station of every rotor in one written sections table.

    ``rows`` are the table's rows as :func:`~pyflightstream.post.products.read_csv_table`
    reads them, already cut to the samples wanted (an unsteady point's last
    complete revolution); ``sample_column`` tells one sample from the next
    (``CLOCKING`` on a wheel, ``STEP`` on a series). A block is the consecutive
    rows of one sample, family, plane and rotor; a block of one blade of a
    rotor in ``rotors`` is a sample of that rotor, at its blade's azimuth.

    Station j of a rotor is the j-th row of each of its blade blocks, at the
    radius ``|Offset|``. A rotor whose blocks hold different numbers of
    stations, or states no azimuth, is skipped by name; a station whose
    radius differs from the first sample's by more than
    :data:`STATION_MATCH_TOLERANCE` of the first sample's largest radius is
    skipped by name, and the others are fitted.

    Parameters
    ----------
    columns : sequence of str
        The sections table's columns.
    rows : sequence of mapping of str to str
        The table's rows as :func:`~pyflightstream.post.products.read_csv_table` reads them, cut to
        the samples wanted.
    rotors : mapping of str to HarmonicRotor
        The rotors to fit, by alias.
    sample_column : str
        The column that tells one sample from the next, ``CLOCKING`` or ``STEP``.

    Returns
    -------
    StationHarmonics
        The fit of every station of every rotor fitted, and what was skipped and why.
    """
    result = StationHarmonics()
    quantities = load_quantities(columns)
    samples: dict[str, list[tuple[float, list[Mapping[str, str]]]]] = {}
    for block in sample_blocks(rows, sample_column):
        first = block[0]
        rotor = rotors.get(first.get("ROTOR", ""))
        if rotor is None:
            continue
        family = first.get("FAMILY", "")
        families = [] if family in ("", NOT_APPLICABLE) else family.split("+")
        blade = blade_of(families, rotor)
        stated = _number(first.get("AZIMUTH"))
        if blade is None or stated is None:
            continue
        psi = (
            placed_blade_azimuth_deg(stated, blade=blade, blades=len(rotor.blades))
            if rotor.azimuth_is_blade_one
            else stated
        )
        if psi is None:
            continue
        samples.setdefault(rotor.alias, []).append((psi, block))
    for alias in rotors:
        if alias not in samples:
            result.skipped[f"#rotor={alias}"] = (
                f"no block of the table is one blade of rotor {alias!r} at a stated azimuth, "
                "so the rotor has no sample"
            )
    for alias, taken in samples.items():
        _fit_rotor(result, rotors[alias], taken, quantities)
    return result


def _fit_rotor(
    result: StationHarmonics,
    rotor: HarmonicRotor,
    taken: Sequence[tuple[float, Sequence[Mapping[str, str]]]],
    quantities: Sequence[str],
) -> None:
    alias = rotor.alias
    counts = {len(block) for _, block in taken}
    if len(counts) != 1:
        result.skipped[f"#rotor={alias}"] = (
            f"the blade blocks of rotor {alias!r} hold {sorted(counts)} stations; the "
            "stations of one blade cannot be matched across samples"
        )
        return
    radii = [[_number(row.get("Offset")) for row in block] for _, block in taken]
    if any(radius is None for block in radii for radius in block):
        result.skipped[f"#rotor={alias}"] = (
            f"a block of rotor {alias!r} states no Offset, so its stations have no radius"
        )
        return
    reference = [abs(float(radius or 0.0)) for radius in radii[0]]
    largest = max(reference, default=0.0)
    result.samples[alias] = len(taken)
    half = (
        0.5 * float(rotor.diameter_m)
        if rotor.diameter_m is not None and rotor.diameter_m > 0
        else None
    )
    short: dict[int, int] = {1: 0, 2: 0}
    fewest: dict[int, int] = {}
    fitted: list[tuple[int, float]] = []
    for station, radius in enumerate(reference):
        off = [
            abs(float(block[station] or 0.0))
            for block in radii
            if abs(abs(float(block[station] or 0.0)) - radius) > STATION_MATCH_TOLERANCE * largest
        ]
        if off:
            result.skipped[f"#rotor={alias}#station={station + 1}"] = (
                f"station {station + 1} of rotor {alias!r} is at r = {radius:.6g} m in the "
                f"first sample and at {sorted(set(off))} m in {len(off)} other(s), more than "
                f"{STATION_MATCH_TOLERANCE:g} of the largest radius {largest:.6g} m apart"
            )
            continue
        fitted.append((station, radius))
    for quantity in quantities:
        for station, radius in fitted:
            pairs = [
                (psi, value)
                for psi, block in taken
                if (value := _number(block[station].get(quantity))) is not None
            ]
            if not pairs:
                continue
            fit = fit_harmonics([p for p, _ in pairs], [v for _, v in pairs])
            for order, needed in MINIMUM_DISTINCT_AZIMUTHS.items():
                if fit.distinct < needed:
                    short[order] += 1
                    fewest[order] = min(fewest.get(order, fit.distinct), fit.distinct)
            result.rows.append(
                (alias, quantity, radius, None if half is None else radius / half, fit)
            )
    for order, needed in MINIMUM_DISTINCT_AZIMUTHS.items():
        if short[order]:
            result.notes.append(
                f"rotor {alias!r}: the {order}P harmonic is NA in {short[order]} row(s), whose "
                f"stations hold as few as {fewest[order]} distinct azimuth(s); a {order}P fit "
                f"needs {needed}"
            )


def write_harmonics_table(
    path: Path, *, pol: str, context: Sequence[object], result: StationHarmonics
) -> Path:
    """Write the harmonic product: ``POL``, the condition, then :data:`HARMONIC_COLUMNS`.

    Parameters
    ----------
    path : Path
        The table to write.
    pol : str
        The polar the point belongs to, written as ``POL``.
    context : sequence of object
        The point's condition values, written after ``POL``.
    result : StationHarmonics
        The fits of :func:`station_harmonics`.

    Returns
    -------
    Path
        The written table.
    """
    return write_csv_table(
        path,
        HARMONICS_COLUMNS,
        [
            (
                pol,
                *context,
                alias,
                quantity,
                float(radius),
                None if ratio is None else float(ratio),
                fit.samples,
                fit.distinct,
                fit.h0,
                fit.h1_amp,
                fit.h1_phase_deg,
                fit.h2_amp,
                fit.h2_phase_deg,
                fit.residual_rms,
            )
            for alias, quantity, radius, ratio, fit in result.rows
        ],
    )
