"""Read and write the fixed-width custom polar product.

The format shares the polar's coefficient and reference blocks from
:mod:`pyflightstream.post._tables`. Its existing import spellings remain
available through :mod:`pyflightstream.post.products`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyflightstream.post._tables import (
    _DECIMALS,
    _REFERENCE_COLUMNS,
    COEFFICIENT_COLUMNS,
    ProductError,
    ReferenceValues,
    _mach_code,
    polar_file_name,
)

__all__ = [
    "CUSTOM_DATE_FORMAT",
    "CUSTOM_REFERENCE_COLUMNS",
    "CUSTOM_TITLE_PREFIX",
    "CUSTOM_WIDTH",
    "custom_count",
    "custom_field",
    "group_number",
    "CustomPolarTable",
    "custom_polar_file_name",
    "read_custom_polar_format",
    "write_custom_polar_format",
]

# --- PFS-2014.01: the custom polar format, the polar table as the reference tooling reads it --

#: The columns of the custom format's reference line: the nominal Mach and then the
#: reference block in the polar table's own order.
CUSTOM_REFERENCE_COLUMNS: tuple[str, ...] = ("MNOM", *_REFERENCE_COLUMNS)

#: Every field of the custom format is right-aligned to this width.
CUSTOM_WIDTH = 10

#: The reference date line, ``Tue Sep 08 23:41:07  2026``: two spaces before the year.
CUSTOM_DATE_FORMAT = "%a %b %d %H:%M:%S  %Y"

CUSTOM_TITLE_PREFIX = "FlightStream - "


@dataclass(frozen=True)
class CustomPolarTable:
    """One file of the custom polar format, read back: the header block and the rows.

    Attributes
    ----------
    description : str
        The title line's description, after ``FlightStream - ``.
    polar : str
        The polar identifier, line 2 without its two-digit Mach code.
    mach : float
        The nominal Mach number, ``MNOM`` of the reference line.
    date : str
        Line 3 as written; :func:`write_custom_polar_format` takes it back so
        a read file is rewritten byte for byte.
    group : int
        The group number of line 4.
    reference : ReferenceValues
        The reference block of line 6.
    columns : tuple of str
        The column names of line 9, in the file's order.
    rows : list of dict
        One mapping per data row, column name to value.
    """

    description: str
    polar: str
    mach: float
    date: str
    group: int
    reference: ReferenceValues
    columns: tuple[str, ...]
    rows: list[dict[str, float]]


def custom_polar_file_name(polar: str | int, *, mach: float, group: str | int) -> str:
    """``<polar>_M<mach code:02d>_g<group:02d>.dat``: the custom format beside the polar table."""
    return polar_file_name(polar, mach, group)[: -len(".csv")] + ".dat"


def custom_field(value: object) -> str:
    """Right-align one custom polar field to the fixed format width."""
    return f"{value!s:>{CUSTOM_WIDTH}}"


def group_number(group: str | int, position: int | None) -> int:
    """Return the NUMBER line four of the fixed-width format states for a group.

    The format has room for two digits and nothing else, and it was written when
    a group WAS a number. A group is named since 0.23.0, and ``int(group)`` on a
    name was a bare ``ValueError`` that no handler of the products stage catches:
    a pproc naming its groups and asking for this format stopped the whole stage.
    A named group states its 1-based POSITION in the ``[groups]`` table, which is
    the number it would have had; the file's NAME carries the alias.
    """
    try:
        return int(group)
    except (TypeError, ValueError):
        pass
    if position is None:
        raise ProductError(
            f"the fixed-width polar format states a group by NUMBER and {group!r} is a name; "
            "pass group_number, the group's 1-based position in the [groups] table"
        )
    return int(position)


# Keep the helper distinct from write_custom_polar_format's group_number keyword.
_group_number = group_number


def write_custom_polar_format(
    path: str | Path,
    *,
    polar: str | int,
    description: str,
    group: str | int,
    mach: float,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    date: str | None = None,
    configuration: str | None = None,
    group_number: int | None = None,
) -> Path:
    """Write one polar of one group in the fixed-width text format the reference tooling opens.

    THIS DOCSTRING IS THE SPECIFICATION OF THE FORMAT (PFS-2014.01.02). The
    shape was read off a recorded file and is pinned by the committed fixture
    ``tests/tier1_offline/fixtures/custom_polar_format_sample.dat``, whose
    every value is synthetic; the tier-1 test feeds the fixture's rows
    through this writer and requires byte equality with the fixture,
    except line 3. The file is ASCII, one line feed per line, a line feed
    after the last line, and no line carries a trailing space beyond the
    width of its fields:

    * line 1: the title, ``FlightStream - <description>``, with
      `` - <configuration>`` appended where the row states one (FR-94).
      THE HEADER IS EXACTLY NINE LINES AND THE READER COUNTS THEM, so the
      label joins a line rather than taking one of its own;
    * line 2: the polar identifier followed by the two-digit Mach code,
      ``<polar><round(mach * 100):02d>``, the same code the polar table's
      file name carries (``3207`` at Mach 0.20 is ``320720``);
    * line 3: the write time, ``%a %b %d %H:%M:%S  %Y`` of the local
      clock (``Tue Sep 08 23:41:07  2026``, two spaces before the year),
      or ``date`` verbatim when given, which is how a read file is
      rewritten byte for byte;
    * line 4: the number of reference columns as three digits, a space,
      and the group number as two digits: ``007 01``;
    * line 5: the reference column names ``MNOM SREF CREF BREF XMOM YMOM
      ZMOM``, each right-aligned to width 10;
    * line 6: their values, the nominal Mach and the reference block, each
      written as Python writes a float (the shortest text that reads
      back to the same number, ``50.0`` and ``2.526``) and right-aligned
      to width 10;
    * line 7: the number of data rows as three digits, ``013``;
    * line 8: the number of data columns as three digits, ``024``;
    * line 9: the twenty-four column names, exactly
      :data:`COEFFICIENT_COLUMNS` in that order, each right-aligned to
      width 10;
    * then one line per data row, every number formatted ``%10.5f``
      (width 10, five decimals, the reference precision), in the column order of
      line 9, the rows in the order given (the stage gives them alpha
      ascending, as the polar table).

    The rows are the same twenty-four values the polar table carries per
    point (:func:`polar_row`), so the two files are two serializations of
    one table; :func:`read_custom_polar_format` reads this one back.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination, ``<polar>_M<code>_g<group>.dat`` beside the polar table.
    polar : str or int
        The polar identifier, the simulation id.
    description : str
        The row's description, as the polar table carries it.
    group : str or int
        The group number.
    mach : float
        The nominal Mach number, written as ``MNOM`` and as the code of line 2.
    reference : ReferenceValues
        The reference block.
    rows : sequence of sequence of float
        The coefficient rows, each of :data:`COEFFICIENT_COLUMNS` width.
    date : str, optional
        Line 3 as it should be written; the local clock when None.
    configuration : str, optional
        The row's `CONFIGURATION` label (FR-94), appended to the title of
        line 1 after ` - `. Absent from the title when the row states
        none, so a file written by a row without one is unchanged.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    ProductError
        If a row is not twenty-four values wide.
    """
    # FR-94. THE CONFIGURATION GOES ON LINE 1 AND NOWHERE ELSE, because
    # the format has exactly nine header lines and the reader counts them:
    # a tenth would make every file this writes unreadable by the
    # reference tooling. The title is the one line with room for a word,
    # and ` - ` is the separator the prefix itself already uses.
    title = f"{CUSTOM_TITLE_PREFIX}{description}"
    if configuration and configuration.strip() and configuration.strip() != "-":
        title = f"{title} - {configuration.strip()}"
    lines = [
        title,
        f"{polar}{_mach_code(mach):02d}",
        date if date is not None else datetime.now().strftime(CUSTOM_DATE_FORMAT),
        f"{len(CUSTOM_REFERENCE_COLUMNS):03d} {_group_number(group, group_number):02d}",
        "".join(custom_field(name) for name in CUSTOM_REFERENCE_COLUMNS),
        "".join(custom_field(float(value)) for value in (mach, *reference.as_row())),
        f"{len(rows):03d}",
        f"{len(COEFFICIENT_COLUMNS):03d}",
        "".join(custom_field(name) for name in COEFFICIENT_COLUMNS),
    ]
    for row in rows:
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
        lines.append("".join(f"{float(value):{CUSTOM_WIDTH}.{_DECIMALS}f}" for value in row))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    return target


def custom_count(line: str, path: Path, number: int, what: str) -> int:
    """Read a count from a custom polar line, naming malformed input."""
    try:
        return int(line.split()[0])
    except (IndexError, ValueError):
        raise ProductError(
            f"{path} line {number} should be the number of {what} as digits; it reads {line!r}"
        ) from None


def read_custom_polar_format(path: str | Path) -> CustomPolarTable:
    """Read a custom polar format file back, as :func:`write_custom_polar_format` specifies it.

    The counts the file states are checked against what it holds, which is
    what makes the round trip (write, read, write again) a proof rather
    than a re-echo: a reference line, a row or a row's width that does not
    fit its count is refused naming the line.

    Parameters
    ----------
    path : str or pathlib.Path
        A file in the custom format.

    Returns
    -------
    CustomPolarTable
        The header block and the rows, each row a mapping of column name to
        value.

    Raises
    ------
    ProductError
        If the file does not have the shape the writer's docstring states.
    """
    target = Path(path)
    lines = target.read_text(encoding="ascii").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 9 or not lines[0].startswith(CUSTOM_TITLE_PREFIX):
        raise ProductError(
            f"{target} is not in the custom polar format: it needs nine header lines, the first "
            f"beginning {CUSTOM_TITLE_PREFIX!r}"
        )
    description = lines[0][len(CUSTOM_TITLE_PREFIX) :]
    identifier = lines[1].strip()
    if len(identifier) < 3 or not identifier[-2:].isdigit():
        raise ProductError(
            f"{target} line 2 should be the polar identifier and a two-digit Mach code; "
            f"it reads {lines[1]!r}"
        )
    counts = lines[3].split()
    if len(counts) != 2:
        raise ProductError(
            f"{target} line 4 should be the reference count and the group number; "
            f"it reads {lines[3]!r}"
        )
    reference_count, group = int(counts[0]), int(counts[1])
    names = tuple(lines[4].split())
    values = lines[5].split()
    if len(names) != reference_count or len(values) != reference_count:
        raise ProductError(
            f"{target} line 4 states {reference_count} reference columns and lines 5 and 6 "
            f"carry {len(names)} names and {len(values)} values"
        )
    reference_values = dict(zip(names, (float(v) for v in values), strict=True))
    row_count = custom_count(lines[6], target, 7, "data rows")
    column_count = custom_count(lines[7], target, 8, "data columns")
    columns = tuple(lines[8].split())
    if len(columns) != column_count:
        raise ProductError(
            f"{target} line 8 states {column_count} columns and line 9 names {len(columns)}"
        )
    data = lines[9:]
    if len(data) != row_count:
        raise ProductError(
            f"{target} line 7 states {row_count} rows and the file holds {len(data)}"
        )
    rows: list[dict[str, float]] = []
    for number, line in enumerate(data, start=10):
        cells = line.split()
        if len(cells) != column_count:
            raise ProductError(
                f"{target} line {number} carries {len(cells)} values for {column_count} columns"
            )
        rows.append(dict(zip(columns, (float(c) for c in cells), strict=True)))
    mach = reference_values.pop("MNOM", None)
    if mach is None:
        raise ProductError(f"{target} line 5 names no MNOM column; it names {names}")
    return CustomPolarTable(
        description=description,
        polar=identifier[:-2],
        mach=mach,
        date=lines[2],
        group=group,
        reference=ReferenceValues.from_mapping(reference_values),
        columns=columns,
        rows=rows,
    )
