"""The disc maps of a rotor point: sectional load by radius and azimuth (0.32.0).

Pipeline role: the post row, where recorded exports become products.
It tabulates the sectional load of a rotor over its disc, by radius and
azimuth, from the WRITTEN sections of the point: every blade at every
clocking of a quasi-steady wheel (``sections/<point>_sections.csv``, 0.31.0),
or every blade at every step of the last complete revolution of an
``unsteady_rotor`` point (``series/<point>_sections_series.csv``).

One CSV per rotor and quantity, ``sections/<point>_disc_<ROTOR>_<QUANTITY>.csv``.
A row is one blade station at one sample: ``SAMPLE`` (the clocking or the
step), ``BLADE``, ``AZIMUTH_DEG`` (where THAT blade is, 0 to 360, placed as
:func:`pyflightstream.post.axes.placed_blade_azimuth_deg` places it), the
station's radius ``STATION_R_M`` and, where the rotor's diameter is known,
``R_OVER_R``, and the load ``VALUE``. Rows run by azimuth, then radius, so
the table is the disc read as a polar grid. No azimuth is computed here: every
angle is the table's own, or comes from :mod:`pyflightstream.post.axes`, the
one home of where a blade is.

The table is the product; no figure is drawn, because matplotlib is not a
dependency the post uses. The definitions page,
``docs/post-processing-definitions.md``, is the definition of record.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._errors import ProductError
from pyflightstream._tokens import CONTEXT_COLUMNS, NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.post._tables import write_csv_table
from pyflightstream.post.axes import placed_blade_azimuth_deg
from pyflightstream.post.harmonics import HarmonicRotor, blade_of, load_quantities, sample_blocks

__all__ = [
    "DISC_MAP_COLUMNS",
    "DISC_MAP_KIND",
    "DISC_MAP_MARK",
    "DiscMaps",
    "disc_map_name",
    "disc_map_rows",
    "write_disc_map",
    "write_disc_maps",
]

#: What sits between the point's name and the rotor in a disc map's file name.
DISC_MAP_MARK = "_disc_"
#: The ``kind`` of a disc map's ``products.json`` entry.
DISC_MAP_KIND = "disc_map"
#: The columns after ``POL`` and the condition, in this order.
_MAP_COLUMNS: tuple[str, ...] = (
    "ROTOR",
    "QUANTITY",
    "SAMPLE",
    "BLADE",
    "AZIMUTH_DEG",
    "STATION_R_M",
    "R_OVER_R",
    "VALUE",
)
#: The whole header of a disc map.
DISC_MAP_COLUMNS: tuple[str, ...] = (POLAR_ID_COLUMN, *CONTEXT_COLUMNS, *_MAP_COLUMNS)

_UNSAFE = re.compile(r"[^A-Za-z0-9_.+-]")

_Row = tuple[str, str, str, int, float, float, float | None, float | None]


@dataclass
class DiscMaps:
    """The disc maps of one table, and what could not be mapped, for the stage to say.

    ``maps`` holds, for each ``(rotor, quantity)``, the rows
    ``(rotor, quantity, sample, blade, azimuth, radius, r / R, value)`` by
    azimuth then radius (a radius that is not a number is NaN and sorts last).
    ``samples`` counts the blade samples of each rotor. ``skipped`` maps a
    marker (``#rotor=<alias>``) to why the rotor has no map.
    """

    maps: dict[tuple[str, str], list[_Row]] = field(default_factory=dict)
    samples: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def disc_map_name(point: str, rotor: str, quantity: str) -> str:
    """Return the file name of one rotor's and quantity's disc map.

    Characters a file name should not carry are written ``_``.

    Examples
    --------
    >>> disc_map_name("DP_AL+000", "PROP", "Fz")
    'DP_AL+000_disc_PROP_Fz.csv'
    """
    return f"{point}{DISC_MAP_MARK}{_UNSAFE.sub('_', rotor)}_{_UNSAFE.sub('_', quantity)}.csv"


def _place(entry: _Row) -> tuple[float, float]:
    return entry[4], math.inf if math.isnan(entry[5]) else entry[5]


def disc_map_rows(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    rotors: Mapping[str, HarmonicRotor],
    *,
    sample_column: str,
) -> DiscMaps:
    """Map every rotor of one written sections table over its disc.

    ``rows`` are the table's rows as :func:`~pyflightstream.post.products.read_csv_table`
    reads them, already cut to the samples wanted (an unsteady point's last
    complete revolution); ``sample_column`` tells one sample from the next
    (``CLOCKING`` on a wheel, ``STEP`` on a series). A block is the consecutive
    rows of one sample, family, plane and rotor; a block of one blade of a
    rotor in ``rotors`` is a sample of that rotor at its blade's azimuth, and
    each of its rows a station at the radius ``|Offset|``. A row whose radius
    or load is not a number keeps its place and states ``NA``; a block that
    states no azimuth, or that is no blade of the rotor, is not a sample.
    """
    result = DiscMaps()
    quantities = load_quantities(columns)
    taken: dict[str, list[_Row]] = {}
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
        psi %= 360.0
        result.samples[rotor.alias] = result.samples.get(rotor.alias, 0) + 1
        mine = taken.setdefault(rotor.alias, [])
        half = (
            0.5 * float(rotor.diameter_m)
            if rotor.diameter_m is not None and rotor.diameter_m > 0
            else None
        )
        for row in block:
            offset = _number(row.get("Offset"))
            radius = math.nan if offset is None else abs(offset)
            ratio = None if math.isnan(radius) or half is None else radius / half
            for quantity in quantities:
                sample = row.get(sample_column, "")
                mine.append(
                    (
                        rotor.alias,
                        quantity,
                        sample,
                        blade,
                        psi,
                        radius,
                        ratio,
                        _number(row.get(quantity)),
                    )
                )
    for alias in rotors:
        if alias not in taken:
            result.skipped[f"#rotor={alias}"] = (
                f"no block of the table is one blade of rotor {alias!r} at a stated azimuth, "
                "so the rotor has no disc map"
            )
    for alias, entries in taken.items():
        for quantity in quantities:
            result.maps[(alias, quantity)] = sorted(
                (entry for entry in entries if entry[1] == quantity), key=_place
            )
    return result


def write_disc_maps(
    rows_of: DiscMaps,
    *,
    point: str,
    pol: str,
    context: Sequence[object],
    out_dir: str | Path,
    target: Callable[[Path], Path] | None = None,
) -> tuple[Path, ...]:
    """Write one CSV per rotor and quantity of ``rows_of`` in ``out_dir``, and return the paths.

    The header is ``POL``, the condition, then the map's own columns; a radius
    that is not a number is written ``NA``. ``target``, where given, maps each
    path to the one written (the stage's guard against replacing a product).
    """
    folder = Path(out_dir)
    place = target if target is not None else (lambda path: path)
    return tuple(
        write_csv_table(
            place(folder / disc_map_name(point, alias, quantity)),
            DISC_MAP_COLUMNS,
            [
                (
                    pol,
                    *context,
                    rotor,
                    name,
                    sample,
                    blade,
                    psi,
                    None if math.isnan(radius) else radius,
                    ratio,
                    value,
                )
                for rotor, name, sample, blade, psi, radius, ratio, value in entries
            ],
        )
        for (alias, quantity), entries in sorted(rows_of.maps.items())
    )


def write_disc_map(
    sections: str | Path,
    rotors: Mapping[str, HarmonicRotor],
    *,
    sample_column: str,
    out_dir: str | Path | None = None,
    point: str | None = None,
) -> tuple[Path, ...]:
    """Write the disc maps of a written sections table, one CSV per rotor and quantity.

    Parameters
    ----------
    sections : str or Path
        A written sections table of a rotor point: a quasi-steady wheel's
        (``CLOCKING`` tells the samples) or an unsteady point's sections
        series (``STEP`` does).
    rotors : mapping of str to HarmonicRotor
        The rotors to map, each with its blades' section families.
    sample_column : str
        The column that tells one sample from the next.
    out_dir : str or Path, optional
        Where the maps are written; the table's own folder where not given.
    point : str, optional
        The point's name in the file names; the table's stem, less a trailing
        ``_sections`` or ``_sections_series``, where not given.

    Returns
    -------
    tuple of Path
        The files written, sorted by rotor and quantity.

    Raises
    ------
    ProductError
        The table cannot be read, or it holds no blade of any rotor at a
        stated azimuth, so there is nothing to map.
    """
    table = Path(sections)
    try:
        with table.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = list(reader.fieldnames or ())
            rows = [{key: value or "" for key, value in row.items()} for row in reader]
    except OSError as error:
        raise ProductError(f"the sections table {table.name} cannot be read: {error}") from error
    result = disc_map_rows(columns, rows, rotors, sample_column=sample_column)
    if not result.maps:
        reasons = "; ".join(result.skipped.values()) or "the table holds no block"
        raise ProductError(f"{table.name} has no disc map to write: {reasons}")
    stem = point or re.sub(r"_sections(_series)?$", "", table.stem)
    lead = next(row for row in rows if row.get("ROTOR") in result.samples)
    return write_disc_maps(
        result,
        point=stem,
        pol=lead.get(POLAR_ID_COLUMN, ""),
        context=tuple(lead.get(name) for name in CONTEXT_COLUMNS),
        out_dir=out_dir if out_dir is not None else table.parent,
    )
