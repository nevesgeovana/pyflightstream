"""The quasi-steady wheel's corrected products and its diagnostic (0.31.0, P0310-CAL).

The one applicator of the correction routes a pproc's ``[qsteady_correction]``
table names (:mod:`pyflightstream.cases.corrections`), run by the post stage
for every ``qsteady_rotor`` WHEEL point of a simulation whose pproc names a
route, and needing no new run: everything here reads the files the post has
just written, as a user holds them.

NOTHING HERE IS VALIDATED, and nothing is written over a raw product. Each
corrected product is a new file beside its raw file, ``<name>_corrected.csv``:

* the rotor table (``polars/P<sim>-<ALIAS>_rotor.csv``) and the average table
  (``polars/P<sim>-<ALIAS>_qs_avg.csv``): a 0P quantity ``q`` a component names
  becomes ``GAIN_0P q + OFFSET_0P``;
* the harmonic product (``sections/<point>_harmonics.csv``), per station:
  ``H0' = GAIN_0P H0 + OFFSET_0P``, ``A1' = GAIN_1P A1``,
  ``PHI1' = PHI1 + PHASE_1P_DEG``, ``A2`` unchanged;
* the sections (``sections/<point>_sections.csv``), each row of each blade at
  each clocking at its own azimuth ``psi`` (its ``AZIMUTH``)::

      load' = load + (H0' - H0) + [A1' cos(psi - PHI1') - A1 cos(psi - PHI1)]

  the raw row plus the change of its 0P and 1P terms, so what the fit does not
  explain is kept.

A column derived from a corrected one that this module does not derive again
(``CP``, ``ETA`` and ``ETAW`` from ``CT`` and ``CQ``; the rotor state from the
thrust; a strip's integrated load from its load) is ``NA`` in the corrected
file and named in its ``products.json`` entry, never carried raw beside a
corrected neighbour. Every corrected file ends with :data:`PROVENANCE_COLUMNS`,
and its entry names the raw file, the route, the calibration and its sha256,
the grid cells used and the words "not validated". A point outside the
calibration's grid is never extrapolated: its corrected cells are ``NA``,
named under ``skipped`` and a WARNING line of ``post.log``. Nothing blocks.

The Theodorsen and Sears functions (route 1) are a DIAGNOSTIC only,
``sections/<point>_theodorsen.csv``: :func:`theodorsen` and :func:`sears` of
each station's 1P reduced frequency beside the measured 1P amplitude and phase
of the harmonic product. They are computed from their closed forms with the
Bessel functions of the first and second kind of orders 0 and 1, implemented
here (:func:`bessel_j`, :func:`bessel_y`) because scipy is not a core
dependency of this package: a power series summed in decimal arithmetic at a
precision that grows with the argument, and Hankel's asymptotic expansion
above 30.

:func:`sector_offset_calibration` builds a route 2 file from a recorded wheel
point and a recorded axial sector point at the same ``J``.
"""

from __future__ import annotations

import cmath
import json
import math
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream._errors import ProductError, PyflightstreamWarning, warn
from pyflightstream._tokens import CONTEXT_COLUMNS, NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.cases.corrections import (
    CALIBRATIONS_DIR,
    SECTION_COMPONENTS,
    Calibration,
    CalibrationError,
    CalibrationRow,
    Lookup,
    QsteadyCorrectionSpec,
    calibration_path,
    calibration_text,
    read_calibration,
)
from pyflightstream.post._tables import ROTOR_TABLE_SUFFIX, read_csv_table, write_csv_table
from pyflightstream.post.harmonics import HARMONICS_SUFFIX
from pyflightstream.post.qsteady import AVERAGE_SUFFIX, STATION_COLUMN, STATION_TOLERANCE

__all__ = [
    "CALIBRATION_SHA256_COLUMN",
    "CORRECTED_KIND",
    "CORRECTED_SUFFIX",
    "CORRECTION_ROUTE_COLUMN",
    "NOT_VALIDATED",
    "PROVENANCE_COLUMNS",
    "THEODORSEN_COLUMNS",
    "THEODORSEN_KIND",
    "THEODORSEN_SUFFIX",
    "WheelPointRef",
    "bessel_j",
    "bessel_y",
    "corrected_name",
    "sears",
    "sector_offset_calibration",
    "theodorsen",
    "write_qsteady_corrections",
]

#: What a corrected file's name adds before ``.csv``.
CORRECTED_SUFFIX = "_corrected"
#: The ``kind`` of a corrected file's ``products.json`` entry.
CORRECTED_KIND = "corrected"
#: The route that made the file, on every row.
CORRECTION_ROUTE_COLUMN = "CORRECTION_ROUTE"
#: The sha256 of the calibration file applied, on every row.
CALIBRATION_SHA256_COLUMN = "CALIBRATION_SHA256"
#: The two columns every corrected file ends with.
PROVENANCE_COLUMNS: tuple[str, ...] = (CORRECTION_ROUTE_COLUMN, CALIBRATION_SHA256_COLUMN)
#: The words every corrected product's entry carries.
NOT_VALIDATED = "not validated"
#: The diagnostic's file, after the point's name, and its entry's ``kind``.
THEODORSEN_SUFFIX = "_theodorsen.csv"
THEODORSEN_KIND = "theodorsen"
#: The diagnostic's columns after ``POL`` and the condition.
THEODORSEN_COLUMNS: tuple[str, ...] = (
    "ROTOR",
    "QUANTITY",
    "STATION_R_M",
    "R_OVER_R",
    "K_1P",
    "C_ABS",
    "C_PHASE_DEG",
    "S_ABS",
    "S_PHASE_DEG",
    "H1_AMP",
    "H1_PHASE_DEG",
)

#: The rotor table's column of each component, after the rotor's alias.
_ROTOR_TABLE_COMPONENTS: Mapping[str, str] = {
    "CT": "CT",
    "CQ": "CQ",
    "CN": "CN",
    "CS": "CS",
    "CMN": "CMN",
    "CMS": "CMS",
}
#: The rotor table's columns derived from components, and from which.
_ROTOR_TABLE_DERIVED: Mapping[str, tuple[str, ...]] = {
    "CP": ("CQ",),
    "ETA": ("CT", "CQ"),
    "ETAW": ("CT", "CQ"),
}
#: The average table's column of each component, alias-suffixed or as named.
_AVERAGE_COMPONENTS: Mapping[str, str] = {
    "THRUST": "THRUST_{alias}",
    "TORQUE": "TORQUE_{alias}",
    "FX": "FX_{alias}",
    "FY": "FY_{alias}",
    "FZ": "FZ_{alias}",
    "MX": "MX_{alias}",
    "MY": "MY_{alias}",
    "MZ": "MZ_{alias}",
    "CT": "CT_PROPELLER",
    "CT_ROTOR": "CT_ROTOR",
}
#: The average table's rotor-state columns derived from components, and from which.
_AVERAGE_DERIVED: Mapping[str, tuple[str, ...]] = {
    "CT_ROTOR": ("THRUST",),
    "CT_PROPELLER": ("THRUST",),
    "LAMBDA_I": ("THRUST", "CT_ROTOR"),
    "CHI_DEG": ("THRUST", "CT_ROTOR"),
}
#: A strip's integrated load, derived from the load of its station.
_SECTION_DERIVED: Mapping[str, tuple[str, ...]] = {
    "Fx_int": ("Fx",),
    "Fz_int": ("Fz",),
    "My_int": ("Moment",),
}


def corrected_name(relative: str) -> str:
    """Return the corrected file's name beside a raw file's.

    Parameters
    ----------
    relative : str
        The raw file's path, relative to the products folder.

    Returns
    -------
    str
        The path with ``_corrected`` before its extension.

    Examples
    --------
    >>> corrected_name("polars/P7001-PROP_rotor.csv")
    'polars/P7001-PROP_rotor_corrected.csv'
    """
    stem, dot, suffix = relative.rpartition(".")
    return f"{stem}{CORRECTED_SUFFIX}.{suffix}" if dot else f"{relative}{CORRECTED_SUFFIX}"


# ------------------------------------------------------------ Bessel functions


#: pi and Euler's constant to 100 digits, for the decimal series.
_PI = Decimal(
    "3.141592653589793238462643383279502884197169399375105820974944592307816406286208998628034825342117068"
)
_GAMMA = Decimal(
    "0.5772156649015328606065120900824024310421593359399235988057672348848677267776646709369470632917467495"
)
#: Above this argument the functions are Hankel's asymptotic expansions.
_ASYMPTOTIC_FROM = 30.0


def _series(order: int, x: float) -> tuple[float, float]:
    """``(J_n(x), Y_n(x))`` for n in (0, 1) and x > 0, by the power series.

    Abramowitz and Stegun 9.1.10 and 9.1.11, summed in decimal arithmetic
    with the precision raised by the digits the alternating terms cancel
    (about ``0.4343 x``), so the float returned is correct to its last bit
    or so.
    """
    digits = 40 + int(0.4343 * x) + 5
    with localcontext() as context:
        context.prec = digits
        big = Decimal(x)
        half = big / 2
        quarter = half * half
        tiny = Decimal(10) ** (-(digits - 8))
        # The k = 0 term of the sum, 1 / (0! n!), which is 1 for n in (0, 1).
        term = Decimal(1)
        harmonic_k = Decimal(0)
        harmonic_kn = Decimal(0) if order == 0 else Decimal(1)
        sum_j = Decimal(0)
        sum_y = Decimal(0)
        k = 0
        while True:
            sum_j += term
            sum_y += (2 * -_GAMMA + harmonic_k + harmonic_kn) * term
            k += 1
            term = term * (-quarter) / (k * (k + order))
            harmonic_k += Decimal(1) / k
            harmonic_kn += Decimal(1) / (k + order)
            if k > x and abs(term) * (1 + abs(harmonic_kn) + abs(harmonic_k)) < tiny:
                break
        power = half if order == 1 else Decimal(1)
        bessel_first = power * sum_j
        logarithm = half.ln()
        second = 2 / _PI * logarithm * bessel_first - power / _PI * sum_y
        if order == 1:
            second -= 1 / (_PI * half)
        return float(bessel_first), float(second)


def _asymptotic(order: int, x: float) -> tuple[float, float]:
    """``(J_n(x), Y_n(x))`` by Hankel's asymptotic expansion (A and S 9.2.5 to 9.2.10)."""
    mu = 4.0 * order * order
    p = q = 0.0
    term = 1.0
    k = 0
    while True:
        if k % 2 == 0:
            p += term if (k // 2) % 2 == 0 else -term
        else:
            q += term if ((k - 1) // 2) % 2 == 0 else -term
        following = term * (mu - (2 * k + 1) ** 2) / ((k + 1) * 8.0 * x)
        k += 1
        if abs(following) < 1e-18 or abs(following) >= abs(term):
            break
        term = following
    chi = x - (order / 2.0 + 0.25) * math.pi
    scale = math.sqrt(2.0 / (math.pi * x))
    return (
        scale * (p * math.cos(chi) - q * math.sin(chi)),
        scale * (p * math.sin(chi) + q * math.cos(chi)),
    )


def _bessel(order: int, x: float) -> tuple[float, float]:
    if order not in (0, 1):
        raise ProductError(f"only the orders 0 and 1 are implemented; asked {order}")
    if not math.isfinite(x) or x <= 0.0:
        raise ProductError(f"the argument must be a positive finite number; it is {x!r}")
    return _series(order, x) if x <= _ASYMPTOTIC_FROM else _asymptotic(order, x)


def bessel_j(order: int, x: float) -> float:
    """Return the Bessel function of the first kind ``J_n(x)``, n in (0, 1), x > 0.

    Parameters
    ----------
    order : int
        The order n, 0 or 1.
    x : float
        The argument, positive.

    Returns
    -------
    float
        ``J_n(x)``.

    Examples
    --------
    >>> round(bessel_j(0, 1.0), 12), round(bessel_j(1, 1.0), 12)
    (0.765197686558, 0.440050585745)
    """
    return _bessel(order, x)[0]


def bessel_y(order: int, x: float) -> float:
    """Return the Bessel function of the second kind ``Y_n(x)``, n in (0, 1), x > 0.

    Parameters
    ----------
    order : int
        The order n, 0 or 1.
    x : float
        The argument, positive.

    Returns
    -------
    float
        ``Y_n(x)``.

    Examples
    --------
    >>> round(bessel_y(0, 1.0), 12), round(bessel_y(1, 1.0), 12)
    (0.088256964216, -0.7812128213)
    """
    return _bessel(order, x)[1]


def theodorsen(k: float) -> complex:
    """Theodorsen's lift deficiency function ``C(k)`` at the reduced frequency ``k``.

    ``C(k) = H1(k) / (H1(k) + i H0(k))``, with ``Hn = Jn - i Yn`` the Hankel
    function of the second kind; ``C(0) = 1``. Its phase is a lag (negative).

    Parameters
    ----------
    k : float
        The reduced frequency, a finite number >= 0.

    Returns
    -------
    complex
        ``C(k)``.

    Raises
    ------
    ProductError
        If ``k`` is not a finite number >= 0.

    Examples
    --------
    >>> value = theodorsen(1.0)
    >>> round(value.real, 4), round(value.imag, 4)
    (0.5394, -0.1003)
    """
    if not math.isfinite(k) or k < 0.0:
        raise ProductError(f"a reduced frequency is a finite number >= 0; it is {k!r}")
    if k == 0.0:
        return complex(1.0, 0.0)
    j0, y0 = _bessel(0, k)
    j1, y1 = _bessel(1, k)
    h0 = complex(j0, -y0)
    h1 = complex(j1, -y1)
    return h1 / (h1 + 1j * h0)


def sears(k: float) -> complex:
    """Sears's function ``S(k)`` at the reduced frequency ``k``, the gust referred to mid-chord.

    ``S(k) = (J0(k) - i J1(k)) C(k) + i J1(k)``; ``S(0) = 1``.

    Parameters
    ----------
    k : float
        The reduced frequency, a finite number >= 0.

    Returns
    -------
    complex
        ``S(k)``.

    Examples
    --------
    >>> round(abs(sears(0.0)), 12)
    1.0
    """
    if k == 0.0:
        return complex(1.0, 0.0)
    j0 = bessel_j(0, k)
    j1 = bessel_j(1, k)
    return complex(j0, -j1) * theodorsen(k) + 1j * j1


# ------------------------------------------------------------------ helpers


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _read(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    # The post's one CSV reader, in `post._tables` since 0.33.0 (AD-10), so
    # this module no longer reaches into `post.products`, which imports it.
    return read_csv_table(path)


@dataclass(frozen=True)
class WheelPointRef:
    """A quasi-steady wheel point of the simulation: its name, run id and rotor alias."""

    name: str
    run_id: str
    rotor_alias: str


@dataclass
class _Record:
    """What a corrected file's manifest entry collects while it is written."""

    cells: list[dict[str, object]] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    derived_na: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def cell(self, point: str, component: str, found: Lookup, where: str | None = None) -> None:
        stated: dict[str, object] = {
            "point": point,
            "component": component,
            "cell": dict(found.cell),
        }
        if where is not None:
            stated["station"] = where
        key = json.dumps(stated, sort_keys=True)
        if key not in self.seen:
            self.seen.add(key)
            self.cells.append(stated)


def _say(skipped: dict[str, str], key: str, point: str, product: str, reason: str) -> None:
    skipped[key] = reason
    warn(f"point={point} product={product}: {reason}", PyflightstreamWarning, stacklevel=3)


def _entry(
    calibration: Calibration,
    *,
    raw: str,
    runs: Sequence[str],
    record: _Record,
    inputs_dir: Path,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    path = calibration.path or calibration_path(inputs_dir, calibration.calibration_id)
    try:
        shown = path.relative_to(inputs_dir.parent).as_posix()
    except ValueError:
        shown = path.as_posix()
    entry: dict[str, object] = {
        "runs": list(runs),
        "kind": CORRECTED_KIND,
        "raw": raw,
        "route": calibration.route,
        "calibration": shown,
        "calibration_sha256": calibration.sha256,
        "validation": NOT_VALIDATED,
        "note": (
            f"corrected by route {calibration.route!r} of the calibration "
            f"{calibration.calibration_id!r}, beside the raw file; the route is {NOT_VALIDATED}"
        ),
        "cells": record.cells,
        "derived_na": sorted(record.derived_na),
    }
    if calibration.source_run_id:
        entry["source_run_id"] = calibration.source_run_id
    if calibration.wheel_run_id:
        entry["wheel_run_id"] = calibration.wheel_run_id
    if record.notes:
        entry["notes"] = list(record.notes)
    entry.update(extra or {})
    return entry


def _table_of(
    written_names: Mapping[str, Mapping[str, object]], suffix: str, alias: str
) -> str | None:
    for relative, entry in written_names.items():
        if relative.endswith(suffix) and not relative.endswith(f"{CORRECTED_SUFFIX}.csv"):
            if str(entry.get("rotor")) == alias:
                return relative
    return None


def _rows_by_run(
    rows: Sequence[Mapping[str, str]], entry: Mapping[str, object]
) -> dict[str, Mapping[str, str]] | None:
    """Each row of a table by the run it holds, from its entry's ``runs`` in row order."""
    runs = entry.get("runs")
    if not isinstance(runs, list) or len(runs) != len(rows):
        return None
    return {str(run): row for run, row in zip(runs, rows, strict=True)}


# ----------------------------------------------------------------- 0P tables


def _correct_zero_p(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    *,
    calibration: Calibration,
    point_of_row: Sequence[WheelPointRef | None],
    coordinates: Mapping[str, Mapping[str, float | None]],
    component_columns: Mapping[str, str],
    derived: Mapping[str, str],
    relative: str,
    record: _Record,
    skipped: dict[str, str],
) -> list[list[object]]:
    """Correct the 0P columns of each row of one rotor or average table.

    ``component_columns`` maps each component to its column in this table,
    ``derived`` each derived column to the components it is derived from,
    joined by a comma.
    """
    present = {
        component: column
        for component, column in component_columns.items()
        if column in columns and component in calibration.grids
    }
    corrected_components = set(present)
    na_columns = {
        column
        for column, sources in derived.items()
        if column in columns
        and column not in present.values()
        and corrected_components & set(sources.split(","))
    }
    record.derived_na |= na_columns
    out_rows: list[list[object]] = []
    for row, point in zip(rows, point_of_row, strict=True):
        cells: list[object] = [row.get(column, NOT_APPLICABLE) for column in columns]
        for column in na_columns:
            cells[columns.index(column)] = None
        for component, column in present.items():
            at = columns.index(column)
            if point is None:
                cells[at] = None
                continue
            raw = _number(row.get(column))
            found = calibration.lookup(component, coordinates.get(point.name, {}))
            if found is None:
                continue
            if found.coefficients is None:
                cells[at] = None
                _say(
                    skipped,
                    f"{relative}#point={point.name}#component={component}",
                    point.name,
                    relative,
                    f"{component} of point {point.name} is not corrected: {found.reason}",
                )
                continue
            record.cell(point.name, component, found)
            offset, gain, _gain_1p, _phase = found.coefficients
            cells[at] = None if raw is None else gain * raw + offset
        out_rows.append(cells)
    return out_rows


# ------------------------------------------------------ harmonics and sections


@dataclass(frozen=True)
class _Station:
    """One station's fit of one quantity, raw and corrected; None where NA."""

    h0: float | None
    a1: float | None
    phi1: float | None
    h0_new: float | None
    a1_new: float | None
    phi1_new: float | None
    corrected: bool


def _station_k(
    sections: Sequence[Mapping[str, str]], alias: str
) -> tuple[list[tuple[float, float | None]], float]:
    """Each station radius of the rotor's section rows with its ``K_1P``, and the largest radius."""
    stations: list[tuple[float, float | None]] = []
    largest = 0.0
    for row in sections:
        if row.get("ROTOR") != alias:
            continue
        radius = _number(row.get("Offset"))
        if radius is None:
            continue
        radius = abs(radius)
        largest = max(largest, radius)
        if not any(abs(radius - known) <= 1e-12 for known, _ in stations):
            stations.append((radius, _number(row.get(STATION_COLUMN))))
    return stations, largest


def _nearest(radius: float, stations: Sequence[float], largest: float) -> int | None:
    if not stations:
        return None
    index = min(range(len(stations)), key=lambda at: abs(stations[at] - radius))
    return (
        index if abs(stations[index] - radius) <= STATION_TOLERANCE * max(largest, 1e-12) else None
    )


def _correct_wheel_point(
    point: WheelPointRef,
    *,
    calibration: Calibration,
    coordinates: Mapping[str, float | None],
    sections_rel: str,
    harmonics_rel: str | None,
    out: Path,
    target: Callable[[Path], Path],
    written_names: Mapping[str, Mapping[str, object]],
    inputs_dir: Path,
    skipped: dict[str, str],
) -> list[tuple[Path, dict[str, object]]]:
    """Write a wheel point's corrected harmonic product and corrected sections."""
    written: list[tuple[Path, dict[str, object]]] = []
    wanted = [name for name in SECTION_COMPONENTS if name in calibration.grids]
    if not wanted:
        return written
    sections_out = corrected_name(sections_rel)
    if harmonics_rel is None:
        _say(
            skipped,
            sections_out,
            point.name,
            sections_out,
            f"the sections of point {point.name} are not corrected: the point has no harmonic "
            "product, whose 0P and 1P terms the correction changes",
        )
        return written
    try:
        section_columns, section_rows = _read(out / sections_rel)
        harmonic_columns, harmonic_rows = _read(out / harmonics_rel)
    except (OSError, ValueError) as error:
        _say(
            skipped,
            sections_out,
            point.name,
            sections_out,
            f"the sections or harmonics of point {point.name} cannot be read back: {error}",
        )
        return written
    stations, largest = _station_k(section_rows, point.rotor_alias)
    radii = [radius for radius, _ in stations]
    fits: dict[tuple[str, int], _Station] = {}
    harmonic_record = _Record()
    outside: dict[str, list[str]] = {}
    new_harmonics: list[list[object]] = []
    for row in harmonic_rows:
        cells: list[object] = [row.get(column, NOT_APPLICABLE) for column in harmonic_columns]
        quantity = row.get("QUANTITY", "")
        if row.get("ROTOR") != point.rotor_alias or quantity not in wanted:
            new_harmonics.append(cells)
            continue
        radius = _number(row.get("STATION_R_M"))
        index = None if radius is None else _nearest(radius, radii, largest)
        k_1p = stations[index][1] if index is not None else None
        found = calibration.lookup(quantity, {**coordinates, "K_1P": k_1p})
        h0 = _number(row.get("H0"))
        a1 = _number(row.get("H1_AMP"))
        phi1 = _number(row.get("H1_PHASE_DEG"))
        if found is None or index is None or found.coefficients is None:
            reason = (
                found.reason
                if found is not None and found.reason
                else "its station is not a station of the sections table"
            )
            outside.setdefault(quantity, []).append(f"r = {radius} m: {reason}")
            for column in ("H0", "H1_AMP", "H1_PHASE_DEG"):
                cells[harmonic_columns.index(column)] = None
            if index is not None:
                fits[(quantity, index)] = _Station(h0, a1, phi1, None, None, None, False)
            continue
        harmonic_record.cell(point.name, quantity, found, where=f"{radius}")
        offset, gain_0p, gain_1p, phase = found.coefficients
        h0_new = None if h0 is None else gain_0p * h0 + offset
        a1_new = None if a1 is None else gain_1p * a1
        phi1_new = None if phi1 is None else (phi1 + phase) % 360.0
        fits[(quantity, index)] = _Station(h0, a1, phi1, h0_new, a1_new, phi1_new, True)
        cells[harmonic_columns.index("H0")] = h0_new
        cells[harmonic_columns.index("H1_AMP")] = a1_new
        cells[harmonic_columns.index("H1_PHASE_DEG")] = phi1_new
        new_harmonics.append(cells)
    harmonics_out = corrected_name(harmonics_rel)
    for quantity, reasons in outside.items():
        _say(
            skipped,
            f"{harmonics_out}#component={quantity}",
            point.name,
            harmonics_out,
            f"{quantity} of point {point.name} is not corrected at {len(reasons)} station(s), "
            "NA in both corrected files: " + "; ".join(reasons),
        )
    route, sha = calibration.route, calibration.sha256
    done = write_csv_table(
        target(out / harmonics_out),
        (*harmonic_columns, *PROVENANCE_COLUMNS),
        [(*cells, route, sha) for cells in new_harmonics],
    )
    written.append(
        (
            done,
            _entry(
                calibration,
                raw=harmonics_rel,
                runs=_runs_of(written_names, harmonics_rel, point),
                record=harmonic_record,
                inputs_dir=inputs_dir,
            ),
        )
    )
    section_record = _Record(cells=harmonic_record.cells, seen=harmonic_record.seen)
    na_columns = {
        column
        for column, sources in _SECTION_DERIVED.items()
        if column in section_columns and set(sources) & set(wanted)
    }
    section_record.derived_na |= na_columns
    no_first = 0
    new_sections: list[tuple[object, ...]] = []
    for row in section_rows:
        cells = [row.get(column, NOT_APPLICABLE) for column in section_columns]
        if row.get("ROTOR") != point.rotor_alias:
            new_sections.append((*cells, route, sha))
            continue
        for column in na_columns:
            cells[section_columns.index(column)] = None
        radius = _number(row.get("Offset"))
        index = None if radius is None else _nearest(abs(radius), radii, largest)
        psi = _number(row.get("AZIMUTH"))
        for quantity in wanted:
            if quantity not in section_columns:
                continue
            at = section_columns.index(quantity)
            fit = fits.get((quantity, index)) if index is not None else None
            raw = _number(row.get(quantity))
            if fit is None or not fit.corrected or raw is None or fit.h0 is None:
                cells[at] = None
                continue
            assert fit.h0_new is not None
            change = fit.h0_new - fit.h0
            if (
                fit.a1 is not None
                and fit.phi1 is not None
                and fit.a1_new is not None
                and fit.phi1_new is not None
            ):
                if psi is None:
                    cells[at] = None
                    continue
                change += fit.a1_new * math.cos(math.radians(psi - fit.phi1_new)) - fit.a1 * (
                    math.cos(math.radians(psi - fit.phi1))
                )
            else:
                no_first += 1
            cells[at] = raw + change
        new_sections.append((*cells, route, sha))
    if no_first:
        section_record.notes.append(
            f"{no_first} cell(s) of stations whose 1P harmonic is NA are corrected in their 0P "
            "term only"
        )
    done = write_csv_table(
        target(out / sections_out), (*section_columns, *PROVENANCE_COLUMNS), new_sections
    )
    written.append(
        (
            done,
            _entry(
                calibration,
                raw=sections_rel,
                runs=_runs_of(written_names, sections_rel, point),
                record=section_record,
                inputs_dir=inputs_dir,
                extra={"harmonics": harmonics_rel},
            ),
        )
    )
    return written


def _runs_of(
    written_names: Mapping[str, Mapping[str, object]], relative: str, point: WheelPointRef
) -> list[str]:
    runs = written_names.get(relative, {}).get("runs")
    return [str(run) for run in runs] if isinstance(runs, list) else [point.run_id]


# ------------------------------------------------------------- the diagnostic


def _theodorsen_file(
    point: WheelPointRef,
    *,
    sections_rel: str,
    harmonics_rel: str,
    out: Path,
    target: Callable[[Path], Path],
    written_names: Mapping[str, Mapping[str, object]],
    skipped: dict[str, str],
) -> tuple[Path, dict[str, object]] | None:
    relative = harmonics_rel.removesuffix(HARMONICS_SUFFIX) + THEODORSEN_SUFFIX
    try:
        _, section_rows = _read(out / sections_rel)
        _, harmonic_rows = _read(out / harmonics_rel)
    except (OSError, ValueError) as error:
        _say(
            skipped,
            relative,
            point.name,
            relative,
            f"the diagnostic of point {point.name} is not written: its tables cannot be read "
            f"back: {error}",
        )
        return None
    stations, largest = _station_k(section_rows, point.rotor_alias)
    radii = [radius for radius, _ in stations]
    rows = []
    unknown = 0
    for row in harmonic_rows:
        if row.get("ROTOR") != point.rotor_alias:
            continue
        radius = _number(row.get("STATION_R_M"))
        index = None if radius is None else _nearest(radius, radii, largest)
        k_1p = stations[index][1] if index is not None else None
        c_abs = c_phase = s_abs = s_phase = None
        if k_1p is not None and k_1p >= 0.0:
            c_value = theodorsen(k_1p)
            s_value = sears(k_1p)
            c_abs, c_phase = abs(c_value), math.degrees(cmath.phase(c_value)) + 0.0
            s_abs, s_phase = abs(s_value), math.degrees(cmath.phase(s_value)) + 0.0
        else:
            unknown += 1
        rows.append(
            (
                row.get(POLAR_ID_COLUMN, NOT_APPLICABLE),
                *(row.get(name, NOT_APPLICABLE) for name in CONTEXT_COLUMNS),
                point.rotor_alias,
                row.get("QUANTITY", NOT_APPLICABLE),
                row.get("STATION_R_M", NOT_APPLICABLE),
                row.get("R_OVER_R", NOT_APPLICABLE),
                k_1p,
                c_abs,
                c_phase,
                s_abs,
                s_phase,
                row.get("H1_AMP", NOT_APPLICABLE),
                row.get("H1_PHASE_DEG", NOT_APPLICABLE),
            )
        )
    if not rows:
        _say(
            skipped,
            relative,
            point.name,
            relative,
            f"the diagnostic of point {point.name} is not written: its harmonic product holds "
            f"no row of rotor {point.rotor_alias!r}",
        )
        return None
    if unknown:
        warn(
            f"point={point.name} product={relative}: {unknown} row(s) state no K_1P, so their "
            "Theodorsen and Sears functions are NA",
            PyflightstreamWarning,
            stacklevel=2,
        )
    done = write_csv_table(
        target(out / relative),
        (POLAR_ID_COLUMN, *CONTEXT_COLUMNS, *THEODORSEN_COLUMNS),
        rows,
    )
    return done, {
        "runs": _runs_of(written_names, harmonics_rel, point),
        "kind": THEODORSEN_KIND,
        "source": harmonics_rel,
        "diagnostic": (
            "the Theodorsen and Sears functions of each station's 1P reduced frequency, "
            "beside the measured 1P amplitude and phase; a diagnostic, never applied as a "
            "correction"
        ),
        "validation": NOT_VALIDATED,
    }


# ------------------------------------------------------------------- driver


def write_qsteady_corrections(
    spec: QsteadyCorrectionSpec,
    *,
    sim_id: str,
    inputs_dir: Path,
    out: Path,
    wheel_points: Sequence[WheelPointRef],
    written_names: Mapping[str, Mapping[str, object]],
    known_runs: Collection[str] | None,
    target: Callable[[Path], Path],
    skipped: dict[str, str],
    sections_dir: str = "sections",
) -> list[tuple[Path, dict[str, object]]]:
    """Write the corrected products and the diagnostic of one simulation's wheel points.

    ``written_names`` is the simulation's manifest entries so far, keyed by the
    file's path relative to ``out``; the raw files are read back from ``out``
    and never rewritten. Returns each file written with its entry. What is not
    written is named in ``skipped`` and warned; nothing raises.

    Parameters
    ----------
    spec : QsteadyCorrectionSpec
        The row's ``[qsteady_correction]`` choice.
    sim_id : str
        The simulation, named in the warnings.
    inputs_dir : Path
        The workspace's inputs folder, where the calibration files are.
    out : Path
        The products folder the raw files are read from and the corrected ones written to.
    wheel_points : sequence of WheelPointRef
        The simulation's quasi-steady wheel points.
    written_names : mapping of str to mapping
        The simulation's manifest entries so far, by path relative to ``out``.
    known_runs : collection of str, or None
        The run ids of the workspace's ``runs.json``; a sector-offset calibration naming another
        source run is warned. None skips that check.
    target : callable
        Prepare a destination path, applying the caller's archive policy.
    skipped : dict of str to str
        Mutable mapping of product names to skip reasons.
    sections_dir : str, optional
        The folder under ``out`` that holds the sections tables.

    Returns
    -------
    list of tuple of (Path, dict)
        Each file written with its manifest entry.
    """
    written: list[tuple[Path, dict[str, object]]] = []
    if not wheel_points or (spec.route == "none" and spec.diagnostic == "none"):
        return written
    calibration: Calibration | None = None
    if spec.route != "none" and spec.file:
        path = calibration_path(inputs_dir, spec.file)
        key = f"{CALIBRATIONS_DIR}/{spec.file}.toml#sim={sim_id}"
        try:
            calibration = read_calibration(path)
        except CalibrationError as error:
            _say(
                skipped,
                key,
                sim_id,
                "qsteady_correction",
                f"route {spec.route!r}: nothing of simulation {sim_id} is corrected, because "
                f"its calibration is refused: {error}",
            )
        else:
            if calibration.route != spec.route:
                _say(
                    skipped,
                    key,
                    sim_id,
                    "qsteady_correction",
                    f"the pproc asks route {spec.route!r} and the calibration {path.name} "
                    f"states route {calibration.route!r}, so nothing of simulation {sim_id} "
                    "is corrected",
                )
                calibration = None
        if (
            calibration is not None
            and calibration.route == "sector_offset"
            and known_runs is not None
            and calibration.source_run_id not in known_runs
        ):
            warn(
                f"point={sim_id} product=qsteady_correction: the calibration {path.name} "
                f"names source_run_id {calibration.source_run_id!r}, which is not a run of "
                "this workspace's runs.json; its offsets are applied as the file states them",
                PyflightstreamWarning,
                stacklevel=2,
            )
    by_run = {point.run_id: point for point in wheel_points}
    aliases = sorted({point.rotor_alias for point in wheel_points})
    tables: dict[str, tuple[tuple[str, ...], list[dict[str, str]]]] = {}
    rows_by_run: dict[str, dict[str, Mapping[str, str]]] = {}
    for alias in aliases:
        for suffix in (ROTOR_TABLE_SUFFIX, AVERAGE_SUFFIX):
            relative = _table_of(written_names, suffix, alias)
            if relative is None:
                continue
            try:
                tables[relative] = _read(out / relative)
            except (OSError, ValueError) as error:
                skipped[corrected_name(relative)] = f"{relative} cannot be read back: {error}"
                continue
            mapped = _rows_by_run(tables[relative][1], written_names[relative])
            if mapped is not None:
                rows_by_run[relative] = dict(mapped)
    coordinates: dict[str, dict[str, float | None]] = {}
    for point in wheel_points:
        rotor_rel = _table_of(written_names, ROTOR_TABLE_SUFFIX, point.rotor_alias)
        average_rel = _table_of(written_names, AVERAGE_SUFFIX, point.rotor_alias)
        rotor_row = rows_by_run.get(rotor_rel or "", {}).get(point.run_id)
        average_row = rows_by_run.get(average_rel or "", {}).get(point.run_id)
        alpha = next(
            (
                value
                for row in (rotor_row, average_row)
                if row is not None and (value := _number(row.get("ALPHA"))) is not None
            ),
            None,
        )
        coordinates[point.name] = {
            "J": None if rotor_row is None else _number(rotor_row.get(f"J_{point.rotor_alias}")),
            "ALPHA": alpha,
            "K_1P": None if average_row is None else _number(average_row.get("K_1P_MEAN")),
        }
    if calibration is not None:
        written += _corrected_tables(
            calibration,
            aliases=aliases,
            tables=tables,
            written_names=written_names,
            by_run=by_run,
            coordinates=coordinates,
            out=out,
            target=target,
            inputs_dir=inputs_dir,
            skipped=skipped,
        )
    for point in wheel_points:
        sections_rel = f"{sections_dir}/{point.name}_sections.csv"
        harmonics_rel = f"{sections_dir}/{point.name}{HARMONICS_SUFFIX}"
        if sections_rel not in written_names:
            continue
        harmonics = harmonics_rel if harmonics_rel in written_names else None
        if calibration is not None:
            section_coordinates = dict(coordinates[point.name])
            alpha = section_coordinates.get("ALPHA")
            if alpha is None:
                section_coordinates["ALPHA"] = _alpha_of_sections(out / sections_rel)
            written += _correct_wheel_point(
                point,
                calibration=calibration,
                coordinates=section_coordinates,
                sections_rel=sections_rel,
                harmonics_rel=harmonics,
                out=out,
                target=target,
                written_names=written_names,
                inputs_dir=inputs_dir,
                skipped=skipped,
            )
        if spec.diagnostic == "theodorsen":
            if harmonics is None:
                relative = f"{sections_dir}/{point.name}{THEODORSEN_SUFFIX}"
                _say(
                    skipped,
                    relative,
                    point.name,
                    relative,
                    f"the diagnostic of point {point.name} is not written: the point has no "
                    "harmonic product to read its 1P amplitude and phase from",
                )
                continue
            done = _theodorsen_file(
                point,
                sections_rel=sections_rel,
                harmonics_rel=harmonics,
                out=out,
                target=target,
                written_names=written_names,
                skipped=skipped,
            )
            if done is not None:
                written.append(done)
    return written


def _alpha_of_sections(path: Path) -> float | None:
    try:
        _, rows = _read(path)
    except (OSError, ValueError):
        return None
    return next((value for row in rows if (value := _number(row.get("ALPHA"))) is not None), None)


def _corrected_tables(
    calibration: Calibration,
    *,
    aliases: Sequence[str],
    tables: Mapping[str, tuple[tuple[str, ...], list[dict[str, str]]]],
    written_names: Mapping[str, Mapping[str, object]],
    by_run: Mapping[str, WheelPointRef],
    coordinates: Mapping[str, Mapping[str, float | None]],
    out: Path,
    target: Callable[[Path], Path],
    inputs_dir: Path,
    skipped: dict[str, str],
) -> list[tuple[Path, dict[str, object]]]:
    written: list[tuple[Path, dict[str, object]]] = []
    for alias in aliases:
        for suffix, components, derived in (
            (
                ROTOR_TABLE_SUFFIX,
                {name: f"{column}_{alias}" for name, column in _ROTOR_TABLE_COMPONENTS.items()},
                {
                    f"{column}_{alias}": ",".join(src)
                    for column, src in _ROTOR_TABLE_DERIVED.items()
                },
            ),
            (
                AVERAGE_SUFFIX,
                {name: column.format(alias=alias) for name, column in _AVERAGE_COMPONENTS.items()},
                {column: ",".join(src) for column, src in _AVERAGE_DERIVED.items()},
            ),
        ):
            relative = _table_of(written_names, suffix, alias)
            if relative is None or relative not in tables:
                continue
            columns, rows = tables[relative]
            if not any(
                column in columns and name in calibration.grids
                for name, column in components.items()
            ):
                continue
            entry = written_names[relative]
            runs = entry.get("runs")
            target_rel = corrected_name(relative)
            if not isinstance(runs, list) or len(runs) != len(rows):
                _say(
                    skipped,
                    target_rel,
                    "campaign",
                    target_rel,
                    f"{relative} is not corrected: its manifest entry does not name one run per "
                    "row, so its rows cannot be told apart",
                )
                continue
            points = [by_run.get(str(run)) for run in runs]
            record = _Record()
            corrected = _correct_zero_p(
                columns,
                rows,
                calibration=calibration,
                point_of_row=points,
                coordinates=coordinates,
                component_columns=components,
                derived=derived,
                relative=target_rel,
                record=record,
                skipped=skipped,
            )
            if any(point is None for point in points):
                record.notes.append(
                    "the rows of runs that are not quasi-steady wheel points are NA in the "
                    "corrected columns"
                )
            done = write_csv_table(
                target(out / target_rel),
                (*columns, *PROVENANCE_COLUMNS),
                [(*cells, calibration.route, calibration.sha256) for cells in corrected],
            )
            written.append(
                (
                    done,
                    _entry(
                        calibration,
                        raw=relative,
                        runs=[str(run) for run in runs],
                        record=record,
                        inputs_dir=inputs_dir,
                        extra={"rotor": alias},
                    ),
                )
            )
    return written


# ------------------------------------------------------------ route 2 helper


def _rotor_row(
    manifest: Mapping[str, Any], out: Path, run_id: str, rotor: str | None
) -> tuple[str, str, dict[str, str]]:
    """Return the rotor table row of a run: (table, alias, row)."""
    found = []
    for relative, entry in (manifest.get("products") or {}).items():
        if not relative.endswith(ROTOR_TABLE_SUFFIX) or not isinstance(entry, Mapping):
            continue
        runs = entry.get("runs")
        if not isinstance(runs, list) or run_id not in runs:
            continue
        if rotor is not None and str(entry.get("rotor")) != rotor:
            continue
        found.append((relative, str(entry.get("rotor")), runs))
    if len(found) != 1:
        raise CalibrationError(
            f"run {run_id!r} is a row of {len(found)} rotor tables of {out / 'products.json'}"
            + (f" for rotor {rotor!r}" if rotor else "")
            + "; the helper reads exactly one. Post the campaign first, or name the rotor"
        )
    relative, alias, runs = found[0]
    _, rows = _read(out / relative)
    if len(rows) != len(runs):
        raise CalibrationError(
            f"{relative} holds {len(rows)} rows and its entry names {len(runs)} runs, so the "
            f"row of {run_id!r} cannot be told"
        )
    return relative, alias, rows[runs.index(run_id)]


def _loads_of(row: Mapping[str, str], alias: str, where: str) -> dict[str, float]:
    values = {
        name: _number(row.get(column))
        for name, column in (
            ("J", f"J_{alias}"),
            ("CT", f"CT_{alias}"),
            ("CQ", f"CQ_{alias}"),
            ("RPM", f"RPM_{alias}"),
            ("D", f"DIAMETER_{alias}"),
            ("RHO", "RHO"),
            ("ALPHA", "ALPHA"),
            ("BETA", "BETA"),
        )
    }
    missing = sorted(name for name, value in values.items() if value is None)
    if missing:
        raise CalibrationError(f"the rotor table row of {where} states no {', '.join(missing)}")
    known = {name: float(value) for name, value in values.items() if value is not None}
    rate = abs(known["RPM"]) / 60.0
    known["THRUST"] = known["CT"] * known["RHO"] * rate**2 * known["D"] ** 4
    known["TORQUE"] = known["CQ"] * known["RHO"] * rate**2 * known["D"] ** 5
    return known


def sector_offset_calibration(
    workspace: Any,
    *,
    wheel_run_id: str,
    sector_run_id: str,
    calibration_id: str,
    rotor: str | None = None,
    matrix_stem: str | None = None,
    j_tolerance: float = 1e-4,
    overwrite: bool = False,
) -> Path:
    """Write a route 2 calibration from a recorded wheel point and a recorded sector point.

    Both points must be rows of a rotor table the post wrote (the sector's row
    of an ``unsteady_rotor`` point with a window is its window average, the
    wheel's the mean of its clockings), both at zero angle of attack and
    sideslip (axial), and at the same advance ratio ``J_<alias>`` within
    ``j_tolerance`` (the tables print five decimals). The file,
    ``inputs/calibrations/<calibration_id>.toml``, states route
    ``sector_offset``, the two run ids, and one row per component ``THRUST``,
    ``TORQUE``, ``CT`` and ``CQ`` at the wheel's ``J`` with

        OFFSET_0P = sector - wheel,  GAIN_0P = 1,  GAIN_1P = 1,  PHASE_1P_DEG = 0

    ``THRUST = CT rho n^2 D^4`` and ``TORQUE = CQ rho n^2 D^5`` of each row's
    own ``RHO``, ``RPM_<alias>`` and ``DIAMETER_<alias>``. Each component's grid
    is one node, constant on every axis, so it applies at every ``J``,
    ``ALPHA`` and ``K_1P``: the offset measured in axial flow, applied at
    incidence, is what route 2 is. Refused with :class:`CalibrationError`
    when a run is not in ``runs.json``, not a row of one rotor table, not
    axial, at another ``J``, or when the file exists and ``overwrite`` is
    False. The route is NOT VALIDATED. Returns the file written.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace whose ``runs.json`` and products are read.
    wheel_run_id : str
        The run id of the quasi-steady wheel point.
    sector_run_id : str
        The run id of the axial unsteady sector point.
    calibration_id : str
        The calibration's id, its file name without the suffix.
    rotor : str, optional
        The rotor alias whose table is read, where a run is a row of more than one.
    matrix_stem : str, optional
        The matrix whose products folder holds the rotor tables.
    j_tolerance : float, optional
        The largest difference in advance ratio the two points may have.
    overwrite : bool, optional
        Replace an existing file of that id.

    Returns
    -------
    Path
        The calibration file written.

    Raises
    ------
    CalibrationError
        If a run is not in ``runs.json``, is not a row of exactly one rotor table, is not axial,
        the two points are at different advance ratios, or the file exists and ``overwrite`` is
        False.
    """
    from pyflightstream.workspace import CampaignWorkspace

    space = workspace if isinstance(workspace, CampaignWorkspace) else CampaignWorkspace(workspace)
    known = {record.run_id for record in space.read_manifest()}
    for run in (wheel_run_id, sector_run_id):
        if run not in known:
            raise CalibrationError(f"run {run!r} is not in {space.root / 'runs.json'}")
    out = space.products_dir(matrix_stem)
    manifest_path = out / "products.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CalibrationError(
            f"{manifest_path} cannot be read; post the campaign first: {error}"
        ) from error
    _, wheel_alias, wheel_row = _rotor_row(manifest, out, wheel_run_id, rotor)
    _, sector_alias, sector_row = _rotor_row(manifest, out, sector_run_id, rotor)
    wheel = _loads_of(wheel_row, wheel_alias, f"the wheel point {wheel_run_id!r}")
    sector = _loads_of(sector_row, sector_alias, f"the sector point {sector_run_id!r}")
    for name, values in (("wheel", wheel), ("sector", sector)):
        if abs(values["ALPHA"]) > 1e-9 or abs(values["BETA"]) > 1e-9:
            raise CalibrationError(
                f"the {name} point is at ALPHA {values['ALPHA']:g} and BETA "
                f"{values['BETA']:g}; a sector offset is taken in axial flow, at zero of both"
            )
    if abs(wheel["J"] - sector["J"]) > j_tolerance:
        raise CalibrationError(
            f"the wheel point is at J {wheel['J']:.6g} and the sector point at J "
            f"{sector['J']:.6g}; a sector offset is taken at the same J (within {j_tolerance:g})"
        )
    rows = [
        CalibrationRow(
            component=name,
            j=wheel["J"],
            alpha_deg=0.0,
            k_1p=0.0,
            offset_0p=sector[name] - wheel[name],
            gain_0p=1.0,
            gain_1p=1.0,
            phase_1p_deg=0.0,
        )
        for name in ("THRUST", "TORQUE", "CT", "CQ")
    ]
    text = calibration_text(
        "sector_offset",
        rows,
        source_run_id=sector_run_id,
        wheel_run_id=wheel_run_id,
        description=(
            "route 2, a 0P offset: the axial unsteady sector point less the axial quasi-steady "
            "wheel point at the same J; not validated"
        ),
    )
    path = calibration_path(space.inputs_dir, calibration_id)
    if path.exists() and not overwrite:
        raise CalibrationError(f"{path} exists; pass overwrite=True to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_text(path, text)
    read_calibration(path)
    return path
