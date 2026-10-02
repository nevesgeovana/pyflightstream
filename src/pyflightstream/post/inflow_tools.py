"""The quasi-steady inflow tools: frame change and the blade-view harmonics (0.32.0).

Pipeline role: the post row, where recorded exports become products.
It holds the inflow tools beyond the field operations of
:mod:`pyflightstream.workspace.fields` (the fluctuation report and
``fill-interior`` live there, beside the other operations that build a custom
free stream):

* :func:`to_installed_frame` writes a product table stated in the isolated
  frame as a second table in the installed frame, the mirror through y = 0.
  Which columns change sign, and which azimuths map, is the one list of
  :data:`FLIPPED_COLUMNS` and :data:`AZIMUTH_COLUMNS`, stated with its reason
  on the definitions page (``docs/post-processing-definitions.md``, "The
  installed-frame copy of a product table"); a test holds the two equal.
* :func:`blade_view_harmonics` and :func:`inflow_harmonics_map` read a custom
  inflow as one blade of a wheel meets it. The plan's ``--inflow-fft``
  (:func:`pyflightstream.cases.qsteady.blade_inflow_harmonics`) already reads
  the field, turns the blade through it and gives ``n95`` per radius, ``n_max``
  and the suggested ``PASSAGE_POSITIONS``; this module uses THAT reading
  (:func:`pyflightstream.cases.qsteady.blade_inflow_angles`) and adds only what
  the plan does not give: the variance share of each of the first eight
  harmonics, the rms and half peak-to-peak of the angle-of-attack
  perturbation in degrees, the reduced frequency ``k_1P = Omega c / (2 mean
  V_rel)`` with the mean relative speed of the revolution (the plan's uses the
  free-stream speed), ``k_eff = n95 k_1P``, and the map over the advance ratio
  ``J`` of one fixed field (``J`` moves the rotor's speed, ``V`` stays), written
  as the two tables ``inflow_harmonics.csv`` and ``inflow_harmonics_J.csv``.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream._errors import ProductError, ProductExistsError
from pyflightstream.cases.qsteady import (
    AZIMUTH_SAMPLES,
    HARMONIC_AMPLITUDE_FLOOR_DEG,
    blade_inflow_angles,
    harmonic_order,
    harmonic_variance_shares,
    suggested_passage_positions,
)

__all__ = [
    "AZIMUTH_COLUMNS",
    "FLIPPED_COLUMNS",
    "HARMONIC_SHARES",
    "ColumnClassification",
    "HarmonicsMap",
    "StationHarmonics",
    "blade_view_harmonics",
    "inflow_harmonics_map",
    "installed_frame_columns",
    "to_installed_frame",
    "write_inflow_harmonics",
]

#: The columns the mirror through y = 0 negates, as patterns matched
#: case-insensitively at the START of a column name and followed by ``_``, a
#: digit or the end of the name (so ``FY``, ``FY_BLADE1`` and ``CNB1`` match and
#: ``FYZ`` does not). A force or moment component along y, a moment about x or
#: z, the side and yaw coefficients, the sense of rotation and its derived
#: quantities. ONE LIST: the definitions page states the same and a test holds
#: them equal.
FLIPPED_COLUMNS: tuple[str, ...] = (
    "FY",
    "MX",
    "MZ",
    "CY[A-Z]*",
    "CR[A-Z]*",
    "CN[BSW]\\d*",
    "CMX",
    "CMZ",
    "TORQUE",
    "RPM",
    "BETA",
    "CS",
    "CMN",
)

#: The columns the mirror maps by ``psi -> -psi (mod 360)``, matched
#: case-insensitively and whole.
AZIMUTH_COLUMNS: tuple[str, ...] = ("AZIMUTH", "AZIMUTH_START", "AZIMUTH_END", "azimuth_deg")

_FLIP = re.compile(r"^(" + "|".join(FLIPPED_COLUMNS) + r")(?=_|\d|$)", re.IGNORECASE)
_AZIMUTH = {name.upper() for name in AZIMUTH_COLUMNS}

#: How many harmonics ``share_n1 ... share_nN`` the blade-view tables carry.
HARMONIC_SHARES = 8


@dataclass(frozen=True)
class ColumnClassification:
    """Which columns of a table the installed-frame copy negates and which it maps."""

    flipped: tuple[str, ...]
    mapped: tuple[str, ...]


def installed_frame_columns(
    columns: Sequence[str], *, flip: Sequence[str] = ()
) -> ColumnClassification:
    """Classify the columns of a table for the installed-frame copy.

    Parameters
    ----------
    columns : sequence of str
        The table's header.
    flip : sequence of str
        Further columns to negate, by name (case-insensitive): the sectional
        ``FX``, ``FZ`` and ``Moment`` are NOT negated by default because the
        section axes' orientation is not settled.

    Returns
    -------
    ColumnClassification
        The columns negated and the columns mapped, in the table's order.

    Raises
    ------
    ProductError
        If a name of ``flip`` is not a column.

    Examples
    --------
    >>> installed_frame_columns(["FX", "FY", "AZIMUTH", "CT"])
    ColumnClassification(flipped=('FY',), mapped=('AZIMUTH',))
    """
    wanted = {name.upper() for name in flip}
    known = {column.upper() for column in columns}
    missing = sorted(wanted - known)
    if missing:
        raise ProductError(
            f"refused: flip (CLI: --flip) names {', '.join(missing)}, which is not a column of "
            f"the table (columns: {', '.join(columns)})."
        )
    flipped = tuple(c for c in columns if _FLIP.match(c) or c.upper() in wanted)
    mapped = tuple(c for c in columns if c.upper() in _AZIMUTH)
    return ColumnClassification(flipped, mapped)


def _negated(text: str) -> str:
    """Return ``text`` with its sign flipped, character for character; not a number stays."""
    stripped = text.strip()
    try:
        value = float(stripped)
    except ValueError:
        return text
    if value == 0.0 or not math.isfinite(value):
        return text
    if stripped.startswith("-"):
        return stripped[1:]
    return "-" + stripped.removeprefix("+")


def _mirrored_azimuth(text: str) -> str:
    try:
        value = float(text)
    except ValueError:
        return text
    if not math.isfinite(value):
        return text
    return format(round((-value) % 360.0, 9), ".15g")


def to_installed_frame(
    table: str | Path, *, out: str | Path | None = None, flip: Sequence[str] = ()
) -> Path:
    """Write a table stated in the isolated frame in the installed frame.

    The installed frame is the isolated one mirrored through ``y = 0``: the
    columns of :data:`FLIPPED_COLUMNS` (and those named in ``flip``) change
    sign, the azimuths of :data:`AZIMUTH_COLUMNS` map ``psi -> -psi mod 360``,
    every other cell is copied as written. Blade and family names do not
    change: blade ``k`` of the image wheel (at ``+(k - 1) 60`` degrees on a
    six-blade wheel) is blade ``k`` of the installed wheel (at ``-(k - 1)
    60``). A rotor table may open with ONE alias line with no comma, which is
    kept. Applying it twice returns the input.

    Parameters
    ----------
    table : str or Path
        A product table (CSV) stated in the isolated frame.
    out : str or Path, optional
        Where the converted table is written; by default ``<table>_installed.csv``
        beside the input.
    flip : sequence of str
        Further columns to negate, by name.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ProductError
        If the table is empty or a name of ``flip`` is not a column.
    ProductExistsError
        If the target exists: this never overwrites.
    """
    source = Path(table)
    target = Path(out) if out is not None else source.with_name(f"{source.stem}_installed.csv")
    lines = source.read_text(encoding="utf-8").splitlines()
    alias: list[str] = []
    # An alias line has no comma and a table follows it; a one-column table has no
    # comma anywhere, and its header is a header.
    if len(lines) > 1 and "," not in lines[0] and "," in lines[1]:
        alias, lines = lines[:1], lines[1:]
    rows = list(csv.reader(lines))
    if not rows:
        raise ProductError(f"refused: {source} holds no header line.")
    header, body = rows[0], rows[1:]
    classes = installed_frame_columns(header, flip=flip)
    if target.exists():
        raise ProductExistsError(f"refused to overwrite {target}; nothing is overwritten.")
    negate = {i for i, c in enumerate(header) if c in classes.flipped}
    mirror = {i for i, c in enumerate(header) if c in classes.mapped}
    buffer = io.StringIO()
    writer = _textio.csv_writer(buffer)
    writer.writerow(header)
    for row in body:
        writer.writerow(
            _negated(cell) if i in negate else _mirrored_azimuth(cell) if i in mirror else cell
            for i, cell in enumerate(row)
        )
    text = "".join(f"{line}\n" for line in alias) + buffer.getvalue()
    _textio.write_text(target, text)
    return target


@dataclass(frozen=True)
class StationHarmonics:
    """The harmonic content of the angle of attack one blade meets at one radius.

    Attributes
    ----------
    radius_m, chord_m : float, float or None
        The station; the chord where it is known.
    dalpha_rms_deg, dalpha_half_ptp_deg : float
        The root mean square and the half peak-to-peak of the perturbation
        ``dalpha(psi) = -(phi - mean phi)`` over one revolution, in degrees.
    n95 : int
        The plan's ``n95`` (0 for a perturbation the blade meets as constant).
    shares : tuple of float
        The variance share of harmonics 1 to :data:`HARMONIC_SHARES`.
    k_1p, k_eff : float or None
        ``Omega c / (2 mean V_rel)`` and ``n95 k_1P``, where the chord is known.
    """

    radius_m: float
    chord_m: float | None
    dalpha_rms_deg: float
    dalpha_half_ptp_deg: float
    n95: int
    shares: tuple[float, ...]
    k_1p: float | None
    k_eff: float | None


def _refuse_a_wrong_axis(axis: Sequence[float]) -> None:
    norm = math.sqrt(sum(a * a for a in axis))
    if norm <= 0.0 or abs(axis[1]) > 1e-9 * norm or abs(axis[2]) > 1e-9 * norm:
        raise ProductError(
            f"refused: the rotor axis is {tuple(axis)}; the inflow profile is a plane of the "
            "global YZ, so the blade-view harmonics need the axis along X."
        )


def blade_view_harmonics(
    rows: Sequence[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    omega_rad_s: float,
    radii_m: Sequence[float],
    chords_m: Sequence[float] | None = None,
    samples: int = AZIMUTH_SAMPLES,
) -> tuple[StationHarmonics, ...]:
    """Return the harmonic content of a custom inflow as one blade meets it, per radius.

    The blade turns once round the disc through the field (blade 1 along +Z at
    ``psi = 0``, ``psi`` positive in the sense of ``omega_rad_s``, the sign of
    which is its hand about +X); at each azimuth the inflow angle
    ``phi = atan2(V_a, V_t)`` is read by
    :func:`pyflightstream.cases.qsteady.blade_inflow_angles`, the pitch
    cancels, and no self-induction is in a power-off field. ``n95`` and the
    shares are the plan's own counting: a harmonic below
    :data:`~pyflightstream.cases.qsteady.HARMONIC_AMPLITUDE_FLOOR_DEG` is not
    counted, so the shares (those of the harmonics counted) and ``n95`` agree.

    Parameters
    ----------
    rows : sequence of (x, y, z, vx, vy, vz)
        The field, metres and m/s, global frame.
    hub, axis : (x, y, z)
        A point of the shaft and its direction; the axis must be along X.
    omega_rad_s : float
        The angular speed, signed by its hand.
    radii_m : sequence of float
        The stations.
    chords_m : sequence of float, optional
        The chord at each station, from the mesh cut; without it ``k_1p`` and
        ``k_eff`` are None.
    samples : int
        Azimuths per revolution.

    Returns
    -------
    tuple of StationHarmonics
        One entry per radius, in the order given: ``n95``, the per-harmonic shares, the
        perturbation's size and, with chords, ``k_1p`` and ``k_eff``.

    Raises
    ------
    ProductError
        If the axis is not along X, or ``chords_m`` does not match ``radii_m``.
    """
    import numpy as np

    _refuse_a_wrong_axis(axis)
    if chords_m is not None and len(chords_m) != len(radii_m):
        raise ProductError(
            f"refused: {len(chords_m)} chords for {len(radii_m)} radii; give one chord per radius."
        )
    floor = math.radians(HARMONIC_AMPLITUDE_FLOOR_DEG)
    stations = []
    for index, radius in enumerate(radii_m):
        phi, relative = blade_inflow_angles(
            rows, hub=hub, axis=axis, omega_rad_s=omega_rad_s, radius_m=radius, samples=samples
        )
        dalpha = -np.degrees(phi - phi.mean())
        n95 = harmonic_order(phi.tolist(), floor=floor)
        shares = np.zeros(HARMONIC_SHARES)
        found = harmonic_variance_shares(phi.tolist(), floor=floor)[:HARMONIC_SHARES]
        shares[: len(found)] = found
        chord = None if chords_m is None else float(chords_m[index])
        k_1p = None
        if chord is not None:
            mean_relative = float(relative.mean())
            if mean_relative <= 0.0:
                raise ProductError(
                    f"refused: the station at r = {radius:g} m sees no relative flow."
                )
            k_1p = abs(omega_rad_s) * chord / (2.0 * mean_relative)
        stations.append(
            StationHarmonics(
                radius_m=float(radius),
                chord_m=chord,
                dalpha_rms_deg=float(np.sqrt(np.mean(dalpha**2))),
                dalpha_half_ptp_deg=float((dalpha.max() - dalpha.min()) / 2.0),
                n95=n95,
                shares=tuple(float(s) for s in shares),
                k_1p=k_1p,
                k_eff=None if k_1p is None else n95 * k_1p,
            )
        )
    return tuple(stations)


@dataclass(frozen=True)
class HarmonicsMap:
    """The blade-view harmonics of one fixed field over a range of advance ratios.

    Attributes
    ----------
    stations : tuple of (float, StationHarmonics)
        ``(J, station)``, advance ratio major, radius minor.
    diameter_m, v_inf_m_s : float
        The rotor diameter and the fixed speed ``J`` is read against.
    blades : int
        ``N``.
    """

    stations: tuple[tuple[float, StationHarmonics], ...]
    diameter_m: float
    v_inf_m_s: float
    blades: int

    @property
    def n_max(self) -> int:
        """The largest ``n95`` of any station at any ``J``."""
        return max((s.n95 for _j, s in self.stations), default=0)

    @property
    def suggested_passage_positions(self) -> int:
        """``ceil(n_max / N + 1)``: the plan's rule (:func:`suggested_passage_positions`)."""
        return suggested_passage_positions(self.n_max, self.blades)


def inflow_harmonics_map(
    rows: Sequence[Sequence[float]],
    *,
    hub: Sequence[float],
    axis: Sequence[float],
    radii_m: Sequence[float],
    diameter_m: float,
    v_inf_m_s: float,
    advance_ratios: Sequence[float],
    blades: int,
    chords_m: Sequence[float] | None = None,
    sense: int = 1,
) -> HarmonicsMap:
    """Return the blade-view harmonics of one field at each advance ratio ``J``.

    The field is fixed and ``J = V / (n D)`` moves through the rotor's speed
    ``n``, ``V`` staying ``v_inf_m_s``: ``omega = sense 2 pi V / (J D)``.

    Parameters
    ----------
    sense : int
        ``+1`` for a rotor right-handed about +X, ``-1`` for the other hand.
    rows : sequence of (x, y, z, vx, vy, vz)
        The field, metres and m/s, global frame.
    hub : (x, y, z)
        A point of the shaft, in metres.
    axis : (x, y, z)
        The shaft's direction; it must be along X.
    radii_m : sequence of float
        The stations, in metres.
    diameter_m : float
        The rotor's diameter D, in metres.
    v_inf_m_s : float
        The free-stream speed V, in m/s.
    advance_ratios : sequence of float
        The advance ratios J mapped.
    blades : int
        The blade count.
    chords_m : sequence of float, optional
        The chord at each station, in metres; without it ``k_1p`` and ``k_eff`` are None.

    Returns
    -------
    HarmonicsMap
        The stations of every J, with the diameter, the speed and the blade count.

    Raises
    ------
    ProductError
        For a non-positive ``J``, diameter, speed or blade count, a ``sense``
        other than +-1, or what :func:`blade_view_harmonics` refuses.
    """
    if sense not in (1, -1):
        raise ProductError(f"refused: sense is +1 or -1; got {sense!r}.")
    if diameter_m <= 0.0 or v_inf_m_s <= 0.0 or blades < 1 or not advance_ratios:
        raise ProductError(
            "refused: a J map needs a positive diameter and free-stream speed, at least one "
            "blade and at least one advance ratio."
        )
    stations: list[tuple[float, StationHarmonics]] = []
    for j in advance_ratios:
        if j <= 0.0:
            raise ProductError(f"refused: an advance ratio is positive; got {j!r}.")
        omega = sense * 2.0 * math.pi * v_inf_m_s / (j * diameter_m)
        for station in blade_view_harmonics(
            rows, hub=hub, axis=axis, omega_rad_s=omega, radii_m=radii_m, chords_m=chords_m
        ):
            stations.append((float(j), station))
    return HarmonicsMap(tuple(stations), float(diameter_m), float(v_inf_m_s), int(blades))


def _cell(value: float | None) -> str:
    return "" if value is None else format(value, ".9g")


def write_inflow_harmonics(
    folder: str | Path, result: HarmonicsMap, *, overwrite: bool = False
) -> tuple[Path, Path]:
    """Write ``inflow_harmonics.csv`` and ``inflow_harmonics_J.csv`` into ``folder``.

    The first carries ``J, r_over_R, c_over_R, dalpha_rms_deg,
    dalpha_half_ptp_deg, n95, k_1P, k_eff, share_n1 ... share_n8``, the second
    ``J, r_over_R, n95, k_1P, k_eff, dalpha_rms_deg``, one row per ``(J,
    radius)`` in both (values ``%.9g``, a blank where the chord is unknown).

    Parameters
    ----------
    folder : str or Path
        The folder the two files are written into.
    result : HarmonicsMap
        The map of :func:`inflow_harmonics_map`.
    overwrite : bool, optional
        Replace files that exist.

    Returns
    -------
    tuple of (Path, Path)
        The full table and the short one.

    Raises
    ------
    ProductExistsError
        If a file exists and ``overwrite`` is not set.
    """
    radius = result.diameter_m / 2.0
    full = Path(folder) / "inflow_harmonics.csv"
    short = Path(folder) / "inflow_harmonics_J.csv"
    existing = [p for p in (full, short) if p.exists()]
    if existing and not overwrite:
        raise ProductExistsError(
            f"refused to overwrite {', '.join(str(p) for p in existing)}; pass overwrite."
        )
    head = [
        "J",
        "r_over_R",
        "c_over_R",
        "dalpha_rms_deg",
        "dalpha_half_ptp_deg",
        "n95",
        "k_1P",
        "k_eff",
    ]
    head += [f"share_n{i}" for i in range(1, HARMONIC_SHARES + 1)]
    lines = [",".join(head)]
    lines_j = ["J,r_over_R,n95,k_1P,k_eff,dalpha_rms_deg"]
    for j, s in result.stations:
        r_over = s.radius_m / radius
        c_over = None if s.chord_m is None else s.chord_m / radius
        lines.append(
            ",".join(
                [
                    _cell(j),
                    _cell(r_over),
                    _cell(c_over),
                    _cell(s.dalpha_rms_deg),
                    _cell(s.dalpha_half_ptp_deg),
                    str(s.n95),
                    _cell(s.k_1p),
                    _cell(s.k_eff),
                    *(_cell(v) for v in s.shares),
                ]
            )
        )
        lines_j.append(
            ",".join(
                [
                    _cell(j),
                    _cell(r_over),
                    str(s.n95),
                    _cell(s.k_1p),
                    _cell(s.k_eff),
                    _cell(s.dalpha_rms_deg),
                ]
            )
        )
    Path(folder).mkdir(parents=True, exist_ok=True)
    _textio.write_text(full, "\n".join(lines) + "\n")
    _textio.write_text(short, "\n".join(lines_j) + "\n")
    return full, short
