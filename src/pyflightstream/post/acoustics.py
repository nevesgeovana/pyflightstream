"""The acoustic signals product of a point: reading the solver's acoustic export.

Pipeline role: the post row. Work package E1 fills it (FR-260 to FR-264): it
reads the file a point's ``EXPORT_ACOUSTIC_SIGNALS`` wrote (named by
:data:`pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`) into one
:class:`~pyflightstream.cases.acoustics.AcousticSignal` per observer, the
contract :mod:`pyflightstream.cases.acoustics` states, and writes from them,
per observer, the pressure against time, the spectrum, the OASPL and the
blade-passage harmonics, and the directivity on an arc when the observers
form one. The definitions of every number are in
``docs/post-processing-definitions.md``, the one home of them.

THE FILE, as measured on build 26.124 (licensed round 1, probe A1): one block
per observer, a line ``Observer: <name>`` (the name may hold spaces), a line
``Position: x,y,z`` in Fortran style (``.00,10.0,.00``), a line
``Columns: Observer time (sec), PL (Pa), PT (Pa), PO (Pa)`` and one row of four
numbers per sample. The signal the package reads is the ``PO`` column. The
manual pages of the toolbox (SRC-003 pp.374 and 380) do not define PL, PT and
PO; the probe shows ``PO`` equal to ``PL`` plus ``PT`` in every row (``PT`` was
zero in the probe) and the package reads ``PO`` as the overall pressure, PL as
the loading part and PT as the thickness part, which is the customary split
and is not a vendor statement. The length unit of the position is not stated
by the file and is read as the contract's metre.

Nothing here blocks a post (invariant 12): the writers return the lines the
post log carries and a value that cannot be computed is ``NA``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pyflightstream._errors import ProductError
from pyflightstream.cases.acoustics import ACOUSTIC_SIGNALS_SUFFIX, AcousticSignal
from pyflightstream.post._tables import write_csv_table

__all__ = [
    "ACOUSTICS_DIR",
    "ACOUSTIC_SIGNALS_SUFFIX",
    "REFERENCE_PRESSURE_PA",
    "AcousticProducts",
    "AcousticSignal",
    "ArcFit",
    "Spectrum",
    "arc_of",
    "blade_passage_harmonics",
    "oaspl_db",
    "read_acoustic_signals",
    "spectrum_of",
    "write_acoustic_products",
]

#: The folder of the acoustic products, under the products folder.
ACOUSTICS_DIR = "acoustics"

#: The reference pressure of a sound pressure level, 20 micropascals.
REFERENCE_PRESSURE_PA = 20e-6

#: How many blade-passage harmonics a point's table lists (DECISION: four).
DEFAULT_HARMONICS = 4

#: The fewest observers that form an arc for the directivity (DECISION: three
#: points always lie on a circle, so an arc claim needs a fourth to test it).
MINIMUM_ARC_OBSERVERS = 4

#: The relative tolerance of the sampling uniformity, of coplanarity and of a
#: point's distance from the circle, measured against the sampling step, the
#: extent and the radius; the export prints sixteen digits, so this is far
#: above its rounding.
_TOLERANCE = 1e-3

_Harmonic = tuple[int, float | None, float | None, float | None, float | None]

_OBSERVER = re.compile(r"^\s*Observer\s*:\s*(.*?)\s*$")
_POSITION = re.compile(r"^\s*Position\s*:\s*(.*?)\s*$")
_COLUMNS = re.compile(r"^\s*Columns\s*:\s*(.*?)\s*$")


def _refuse(path: object, line: int, why: str) -> ProductError:
    return ProductError(f"acoustic signals {path}, line {line}: {why}")


def read_acoustic_signals(path: str | Path) -> tuple[AcousticSignal, ...]:
    """Read a point's acoustic export into one signal per observer (FR-260).

    Parameters
    ----------
    path : str or Path
        The exported file, ``<point>`` followed by
        :data:`~pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`.

    Returns
    -------
    tuple of AcousticSignal
        One per observer, in the order the file holds them. The pressure is
        the ``PO`` column, the time is the observer time in seconds.

    Raises
    ------
    ProductError
        The file cannot be read, holds no observer, or a block lacks its
        position, its columns or its samples, states no ``PO`` column, or holds
        a row that is not numbers. The message names the line.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ProductError(f"acoustic signals {path} cannot be read: {error}") from error
    signals: list[AcousticSignal] = []
    name: str | None = None
    head = 0
    position: tuple[float, float, float] | None = None
    columns: list[str] | None = None
    times: list[float] = []
    pressures: list[float] = []

    def close() -> None:
        if name is None:
            return
        if position is None or columns is None:
            raise _refuse(path, head, f"observer {name!r} has no Position and Columns lines")
        if not times:
            raise _refuse(path, head, f"observer {name!r} has no samples")
        signals.append(AcousticSignal(name, *position, tuple(times), tuple(pressures)))

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if (found := _OBSERVER.match(line)) is not None:
            close()
            name, head, position, columns = found.group(1), number, None, None
            times, pressures = [], []
        elif name is None:
            raise _refuse(path, number, "a line before the first 'Observer:' line")
        elif (found := _POSITION.match(line)) is not None:
            try:
                x, y, z = (float(part) for part in found.group(1).split(","))
            except ValueError:
                raise _refuse(path, number, "the Position line is not three numbers") from None
            position = (x, y, z)
        elif (found := _COLUMNS.match(line)) is not None:
            columns = [part.strip() for part in found.group(1).split(",")]
            if not columns[0].lower().startswith("observer time"):
                raise _refuse(path, number, "the first column is not the observer time")
            if not any(part.startswith("PO") for part in columns):
                raise _refuse(path, number, "the Columns line states no PO column")
        elif columns is None:
            raise _refuse(path, number, "a sample before the Columns line")
        else:
            try:
                values = [float(part) for part in line.split()]
            except ValueError:
                raise _refuse(path, number, "a sample row is not numbers") from None
            if len(values) != len(columns):
                raise _refuse(
                    path, number, f"a sample row holds {len(values)} values for {len(columns)}"
                )
            column = next(i for i, part in enumerate(columns) if part.startswith("PO"))
            times.append(values[0])
            pressures.append(values[column])
    close()
    if not signals:
        raise ProductError(f"acoustic signals {path} hold no observer")
    return tuple(signals)


@dataclass(frozen=True)
class Spectrum:
    """The one-sided spectrum of one observer's pressure.

    ``frequency_hz`` and ``amplitude_pa`` have ``samples // 2 + 1`` entries;
    ``sample_rate_hz`` is the reciprocal of the constant step, ``df_hz`` the bin
    width ``sample_rate_hz / samples``.
    """

    frequency_hz: tuple[float, ...]
    amplitude_pa: tuple[float, ...]
    sample_rate_hz: float
    df_hz: float
    samples: int


def spectrum_of(signal: AcousticSignal) -> Spectrum:
    """Return the one-sided amplitude spectrum of a signal's pressure (FR-261).

    The samples are transformed as they are (no window, no mean removal) with
    the real FFT. For ``N`` samples, bin 0 is ``|X0| / N`` (the mean), a bin
    below the Nyquist bin is ``2 |Xk| / N`` and the Nyquist bin of an even
    ``N`` is ``|Xk| / N``, so a cosine of amplitude ``A`` on a bin reads ``A``.

    Raises
    ------
    ProductError
        The record has fewer than two samples, or its time step is not
        constant (relative spread above ``1e-3``), which an FFT cannot read.
    """
    count = len(signal.time_s)
    if count < 2:
        raise ProductError(
            f"observer {signal.observer!r}: {count} sample(s), too few for a spectrum"
        )
    steps = np.diff(np.asarray(signal.time_s, dtype=float))
    step = float(np.mean(steps))
    if not step > 0.0 or float(np.max(np.abs(steps - step))) > _TOLERANCE * step:
        raise ProductError(
            f"observer {signal.observer!r}: the observer time is not uniformly stepped, "
            "so no spectrum is read from it"
        )
    amplitude = np.abs(np.fft.rfft(np.asarray(signal.pressure_pa, dtype=float))) / count
    amplitude[1:] *= 2.0
    if count % 2 == 0:
        amplitude[-1] /= 2.0
    rate = 1.0 / step
    df = rate / count
    frequency = np.arange(len(amplitude)) * df
    return Spectrum(
        tuple(float(f) for f in frequency),
        tuple(float(a) for a in amplitude),
        rate,
        df,
        count,
    )


def _level_db(rms_pa: float) -> float | None:
    """Return ``20 log10(rms / 20 uPa)``, or None for a zero rms."""
    return 20.0 * math.log10(rms_pa / REFERENCE_PRESSURE_PA) if rms_pa > 0.0 else None


def oaspl_db(signal: AcousticSignal) -> float | None:
    """Return the overall sound pressure level of a signal in dB re 20 uPa (FR-262).

    ``20 log10(p_rms / 20e-6 Pa)``, ``p_rms`` the root mean square of the
    pressure about its mean over the whole record (the fluctuation). None for
    a silent record (``p_rms`` zero), which the caller states as ``NA``.
    """
    pressure = np.asarray(signal.pressure_pa, dtype=float)
    if pressure.size == 0:
        return None
    return _level_db(float(np.sqrt(np.mean((pressure - pressure.mean()) ** 2))))


def blade_passage_harmonics(
    spectrum: Spectrum, *, blades: int, rpm: float, harmonics: int = DEFAULT_HARMONICS
) -> list[_Harmonic]:
    """Return the blade-passage harmonics read from a spectrum (FR-263).

    The blade-passage frequency is ``blades * rpm / 60`` hertz and harmonic
    ``n`` is ``n`` times it. Each row is ``(n, frequency_hz, bin_hz,
    amplitude_pa, level_db)`` read at the nearest bin; the bin, amplitude and
    level are None (``NA``) when the frequency is above the Nyquist frequency
    of the record or below its bin width (the record holds less than one
    period of it).
    """
    if blades < 1 or not rpm > 0.0:
        raise ProductError(f"blades={blades} and rpm={rpm} state no blade-passage frequency")
    base = blades * rpm / 60.0
    nyquist = spectrum.frequency_hz[-1]
    rows: list[_Harmonic] = []
    for order in range(1, harmonics + 1):
        frequency = order * base
        if frequency > nyquist or frequency < spectrum.df_hz:
            rows.append((order, frequency, None, None, None))
            continue
        index = min(int(round(frequency / spectrum.df_hz)), len(spectrum.amplitude_pa) - 1)
        amplitude = spectrum.amplitude_pa[index]
        rows.append(
            (
                order,
                frequency,
                spectrum.frequency_hz[index],
                amplitude,
                _level_db(amplitude / math.sqrt(2.0)),
            )
        )
    return rows


@dataclass(frozen=True)
class ArcFit:
    """Observers on a circular arc: its centre, radius and each observer's angle.

    ``angle_deg`` is each observer's angle about the centre, measured from the
    first observer and increasing toward the second, in ``[0, 360)``.
    """

    center: tuple[float, float, float]
    radius_m: float
    angle_deg: tuple[float, ...]


def arc_of(signals: Sequence[AcousticSignal]) -> ArcFit | None:
    """Return the arc the observers lie on, or None when they do not form one (FR-264).

    They form an arc when there are at least :data:`MINIMUM_ARC_OBSERVERS`, they
    are coplanar and lie on one circle, both to a relative tolerance of
    ``1e-3`` (of the extent, and of the radius).
    """
    if len(signals) < MINIMUM_ARC_OBSERVERS:
        return None
    points = np.array([[s.x_m, s.y_m, s.z_m] for s in signals], dtype=float)
    centroid = points.mean(axis=0)
    _, singular, axes = np.linalg.svd(points - centroid)
    if not singular[1] > _TOLERANCE * singular[0] or singular[2] > _TOLERANCE * singular[0]:
        return None
    plane = (points - centroid) @ axes[:2].T
    design = np.column_stack([2.0 * plane, np.ones(len(plane))])
    solution, *_ = np.linalg.lstsq(design, (plane**2).sum(axis=1), rcond=None)
    middle = solution[:2]
    radius = math.sqrt(max(float(solution[2] + middle @ middle), 0.0))
    distance = np.linalg.norm(plane - middle, axis=1)
    if not radius > 0.0 or float(np.max(np.abs(distance - radius))) > _TOLERANCE * radius:
        return None
    theta = np.arctan2(plane[:, 1] - middle[1], plane[:, 0] - middle[0])
    relative = theta - theta[0]
    if math.sin(float(relative[1])) < 0.0:
        relative = -relative
    angles = np.degrees(relative) % 360.0
    center = centroid + middle @ axes[:2]
    return ArcFit(
        (float(center[0]), float(center[1]), float(center[2])),
        radius,
        tuple(float(a) for a in angles),
    )


@dataclass
class AcousticProducts:
    """What :func:`write_acoustic_products` wrote and the post-log lines it owes."""

    files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "observer"


def write_acoustic_products(
    signals: Sequence[AcousticSignal],
    out_dir: str | Path,
    *,
    stem: str,
    rotors: Mapping[str, tuple[int | None, float | None]] | None = None,
    harmonics: int = DEFAULT_HARMONICS,
    target: Callable[[Path], Path] | None = None,
) -> AcousticProducts:
    """Write a point's acoustic products under ``out_dir`` and return them (FR-261 to FR-264).

    Per observer ``<stem>_<n>_<name>_pressure.csv`` (time, pressure) and
    ``<stem>_<n>_<name>_spectrum.csv`` (frequency, amplitude, level); per point
    ``<stem>_acoustics_summary.csv`` (position, samples, sampling, OASPL),
    ``<stem>_acoustics_bpf.csv`` (blade-passage harmonics per rotor and observer)
    and, when the observers form an arc, ``<stem>_acoustics_directivity.csv``.

    Parameters
    ----------
    rotors : mapping, optional
        Rotor alias to ``(blades, rpm)``. A rotor lacking either, or no rotor
        at all, gives ``NA`` harmonics and a line in the returned notes.
    target : callable, optional
        Maps a path to the path to write (the archive-or-refuse rule of the
        other products).

    Nothing blocks: an observer whose spectrum cannot be read keeps its pressure
    table and its OASPL, and is named in the notes.
    """
    folder = Path(out_dir)
    result = AcousticProducts()

    def emit(name: str, columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
        path = folder / name
        result.files.append(write_csv_table(target(path) if target else path, columns, rows))

    summary: list[Sequence[object]] = []
    bpf: list[Sequence[object]] = []
    stated = dict(rotors or {})
    usable = {a: (b, r) for a, (b, r) in stated.items() if b and r and r > 0}
    if not stated:
        result.notes.append(
            "the record states no rotor with blades and speed: the blade-passage harmonics are NA"
        )
    for alias, (blades_, rpm_) in stated.items():
        if alias not in usable:
            result.notes.append(
                f"rotor {alias!r} states blades={blades_} and rpm={rpm_}: "
                "its blade-passage harmonics are NA"
            )
    for index, signal in enumerate(signals, start=1):
        base = f"{stem}_{index:02d}_{_slug(signal.observer)}"
        emit(
            f"{base}_pressure.csv",
            ("TIME_S", "PRESSURE_PA"),
            list(zip(signal.time_s, signal.pressure_pa, strict=True)),
        )
        level = oaspl_db(signal)
        if level is None:
            result.notes.append(f"observer {signal.observer!r}: silent record, OASPL is NA")
        rate = df = None
        spectrum: Spectrum | None = None
        try:
            spectrum = spectrum_of(signal)
        except ProductError as error:
            result.notes.append(f"{error}; its spectrum and harmonics are NA")
        if spectrum is not None:
            rate, df = spectrum.sample_rate_hz, spectrum.df_hz
            emit(
                f"{base}_spectrum.csv",
                ("FREQUENCY_HZ", "AMPLITUDE_PA", "LEVEL_DB"),
                [
                    (f, a, None if k == 0 else _level_db(a / math.sqrt(2.0)))
                    for k, (f, a) in enumerate(
                        zip(spectrum.frequency_hz, spectrum.amplitude_pa, strict=True)
                    )
                ],
            )
        summary.append(
            (
                signal.observer,
                signal.x_m,
                signal.y_m,
                signal.z_m,
                len(signal.time_s),
                signal.time_s[0],
                signal.time_s[-1],
                rate,
                df,
                level,
            )
        )
        for alias in stated or {"": (None, None)}:
            blades, rpm = usable.get(alias, (None, None))
            rows: list[_Harmonic]
            if spectrum is not None and blades and rpm:
                rows = blade_passage_harmonics(
                    spectrum, blades=blades, rpm=rpm, harmonics=harmonics
                )
            else:
                rows = [(n, None, None, None, None) for n in range(1, harmonics + 1)]
            for order, frequency, bin_hz, amplitude, level_db in rows:
                if frequency is not None and amplitude is None:
                    result.notes.append(
                        f"observer {signal.observer!r} rotor {alias!r}: harmonic {order} at "
                        f"{frequency:g} Hz is outside what the record resolves, NA"
                    )
                bpf.append(
                    (alias or None, signal.observer, order, frequency, bin_hz, amplitude, level_db)
                )
    emit(
        f"{stem}_acoustics_summary.csv",
        (
            "OBSERVER",
            "X_M",
            "Y_M",
            "Z_M",
            "SAMPLES",
            "TIME_START_S",
            "TIME_END_S",
            "SAMPLE_RATE_HZ",
            "BIN_HZ",
            "OASPL_DB",
        ),
        summary,
    )
    emit(
        f"{stem}_acoustics_bpf.csv",
        ("ROTOR", "OBSERVER", "HARMONIC", "FREQUENCY_HZ", "BIN_HZ", "AMPLITUDE_PA", "LEVEL_DB"),
        bpf,
    )
    arc = arc_of(signals)
    if arc is not None:
        emit(
            f"{stem}_acoustics_directivity.csv",
            ("OBSERVER", "ANGLE_DEG", "RADIUS_M", "OASPL_DB"),
            [
                (s.observer, angle, arc.radius_m, oaspl_db(s))
                for s, angle in zip(signals, arc.angle_deg, strict=True)
            ],
        )
    return result
