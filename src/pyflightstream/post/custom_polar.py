"""Read and write the fixed-width custom polar product.

The format shares the polar's coefficient and reference blocks from
:mod:`pyflightstream.post._tables`. Its existing import spellings remain
available through :mod:`pyflightstream.post.products`.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream._tokens import NOT_APPLICABLE
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
    """``<polar>_M<mach code:02d>_g<group:02d>.dat``: the custom format beside the polar table.

    Parameters
    ----------
    polar : str or int
        The polar's number.
    mach : float
        The Mach number, written as its two-digit code.
    group : str or int
        The plot group's number, as an int or as the text of one.

    Returns
    -------
    str
        The ``.dat`` file name beside the polar table.

    Raises
    ------
    ProductError
        If ``group`` is a name: the convention states a group by number.
    """
    return polar_file_name(polar, mach, group)[: -len(".csv")] + ".dat"


def custom_field(value: object) -> str:
    """Right-align one custom polar field to the fixed format width.

    Parameters
    ----------
    value : object
        The field's value.

    Returns
    -------
    str
        The value as text, right-aligned to the format's width.

    Raises
    ------
    ProductError
        If the text does not fit the width with a blank before it.
    """
    text = f"{value!s}"
    if len(text) >= CUSTOM_WIDTH:
        raise ProductError(
            f"{text!r} does not fit the custom polar format's {CUSTOM_WIDTH}-character field "
            "with a blank before it; a header name has at most "
            f"{CUSTOM_WIDTH - 1} characters"
        )
    return f"{text:>{CUSTOM_WIDTH}}"


def _bounded_field(value: float, decimals: int | None = None) -> str:
    """Write one number in a field that keeps a blank before it, or refuse it by value.

    A field is CUSTOM_WIDTH characters, right-aligned, and a reader splits a
    line on blanks: text as wide as the field fuses with its left neighbour,
    and text wider overflows it. So a number keeps its own spelling (``repr``,
    or ``decimals`` fixed decimals) where that leaves a blank, and gives up
    decimals, then significant digits, until it does.
    """
    room = CUSTOM_WIDTH - 1
    if math.isinf(value):
        # AN INFINITE VALUE IS NA, as in every other table. A NaN keeps the spelling the
        # format's `%10.5f` gives it (`nan`), which PFS-2006 pins as the declined column.
        return f"{'NA':>{CUSTOM_WIDTH}}"
    if decimals is None:
        spellings = [str(value), *(f"{value:.{digits}g}" for digits in range(room, 0, -1))]
    else:
        spellings = [f"{value:.{places}f}" for places in range(decimals, -1, -1)]
    for text in spellings:
        if len(text) <= room:
            return f"{text:>{CUSTOM_WIDTH}}"
    raise ProductError(
        f"{value!r} does not fit the custom polar format's {CUSTOM_WIDTH}-character field "
        "with a blank before it"
    )


def group_number(group: str | int, *, position: int | None = None) -> int:
    """Return the NUMBER line four of the fixed-width format states for a group.

    The format has room for two digits and nothing else, and it was written when
    a group WAS a number. A group is named and ``int(group)`` on a
    name was a bare ``ValueError`` that no handler of the products stage catches:
    a pproc naming its groups and asking for this format stopped the whole stage.
    A named group states its 1-based POSITION in the ``[groups]`` table, which is
    the number it would have had; the file's NAME carries the alias.

    Parameters
    ----------
    group : str or int
        The group: a number, or a name.
    position : int, optional
        A named group's 1-based position in the ``[groups]`` table.

    Returns
    -------
    int
        The group's number, or its position for a named group.

    Raises
    ------
    ProductError
        If the group is a name and no position is given.
    """
    try:
        return int(group)
    except (TypeError, ValueError):
        pass
    if position is None:
        raise ProductError(
            f"the fixed-width polar format states a group by NUMBER and {group!r} is a name; "
            "pass position= with the group's 1-based position in the [groups] table"
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
    columns: Sequence[str] = COEFFICIENT_COLUMNS,
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
      A character outside ASCII is TRANSLITERATED (:func:`_ascii_title`): an
      accent is dropped from its letter, and anything with no ASCII letter
      under it is written ``?``.
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
      written as Python writes a float (``50.0`` and ``2.526``) when it
      fits with a leading blank; otherwise significant digits are reduced
      until it fits. Each field is right-aligned to width 10;
    * line 7: the number of data rows as three digits, ``013``;
    * line 8: ``len(columns)`` as three digits, ``024`` for the default schema;
    * line 9: the names in ``columns``, in the supplied order, each
      right-aligned to width 10; the default is :data:`COEFFICIENT_COLUMNS`;
    * then one line per data row, every number right-aligned to width 10
      with up to five decimals. Decimal places are reduced until a leading
      blank fits; a value that cannot fit is refused; an infinite value is written NA
      (a NaN stays ``nan``, the declined column). Values follow the order of
      line 9, the rows in the order given (the stage gives them alpha
      ascending, as the polar table).

    The rows carry the selected columns of the polar table, so the two
    files are two serializations of one table; :func:`read_custom_polar_format` reads this one back.

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
        The coefficient rows, each with ``len(columns)`` values in that order.
    date : str, optional
        Line 3 as it should be written; the local clock when None.
    configuration : str, optional
        The row's `CONFIGURATION` label (FR-94), appended to the title of
        line 1 after ` - `. Absent from the title when the row states
        none (blank, a dash or ``NA``), so a file written by a row without
        one is unchanged.
    group_number : int, optional
        The number line 4 states for a named group, its 1-based position in the ``[groups]`` table
        (:func:`group_number`).
    columns : sequence of str, optional
        The data columns of lines 8 and 9, :data:`COEFFICIENT_COLUMNS` by default.
        A polar of 26.125 names its drag split ``CDV, CDP`` in the last two, and a
        polar holding rows of both builds carries both pairs (FR-423,
        :func:`pyflightstream.post.polar.drag_columned_rows`).

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    ProductError
        If a row has a different length from ``columns``, a value does not fit a
        field with a blank before it even with no decimals, a header name has
        ten or more characters, or a header line other than the title holds a
        character outside ASCII. A value that is not a number is written ``nan``
        (the format writes every number ``%10.5f``) and
        :func:`read_custom_polar_format` reads ``nan``, ``NA`` and the
        historical ``-`` back as missing; a line break in the description or
        the configuration is folded to a blank.
    """
    # FR-94. THE CONFIGURATION GOES ON LINE 1 AND NOWHERE ELSE, because
    # the format has exactly nine header lines and the reader counts them:
    # a tenth would make every file this writes unreadable by the
    # reference tooling. The title is the one line with room for a word,
    # and ` - ` is the separator the prefix itself already uses.
    # A line break in the description would add a tenth header line.
    title = f"{CUSTOM_TITLE_PREFIX}{' '.join(str(description).split())}"
    if (
        configuration
        and configuration.strip()
        and configuration.strip() not in ("-", NOT_APPLICABLE)
    ):
        title = f"{title} - {' '.join(configuration.split())}"
    lines = [
        _ascii_title(title),
        f"{polar}{_mach_code(mach):02d}",
        date if date is not None else datetime.now().strftime(CUSTOM_DATE_FORMAT),
        f"{len(CUSTOM_REFERENCE_COLUMNS):03d} {_group_number(group, position=group_number):02d}",
        "".join(custom_field(name) for name in CUSTOM_REFERENCE_COLUMNS),
        "".join(_bounded_field(float(value)) for value in (mach, *reference.as_row())),
        f"{len(rows):03d}",
        f"{len(columns):03d}",
        "".join(custom_field(name) for name in columns),
    ]
    # EVERY HEADER LINE IS ASCII OR THE CALL IS REFUSED BY NAME. Only the title is
    # transliterated, so a polar identifier, a verbatim date or a column name with
    # a character outside ASCII reached the strict encoder as a UnicodeEncodeError
    # instead of the documented ProductError.
    for number, line in enumerate(lines, start=1):
        outside = next((char for char in line if not char.isascii()), None)
        if outside is not None:
            raise ProductError(
                f"line {number} of the custom polar header holds {outside!r}, which the "
                "ASCII custom format cannot carry; rename the polar, date or column to "
                "ASCII letters, digits and punctuation"
            )
    for row in rows:
        if len(row) != len(columns):
            raise ProductError(f"a polar row has {len(row)} values, not {len(columns)}")
        lines.append("".join(_bounded_field(float(value), _DECIMALS) for value in row))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _textio.write_text(target, "\n".join(lines) + "\n", encoding="ascii")
    return target


def _ascii_title(text: str) -> str:
    """Return ``text`` in ASCII: accents dropped from their letters, any other character ``?``.

    The custom format is ASCII and its title carries the row's DESCRIPTION and
    CONFIGURATION, which nothing upstream holds to ASCII. Written strictly, one
    accented letter raised a UnicodeEncodeError out of the campaign post.

    >>> _ascii_title("Asa em cruzeiro, " + chr(0xE2) + "ngulo de 5" + chr(0xB0))
    'Asa em cruzeiro, angulo de 5?'
    """
    folded = unicodedata.normalize("NFKD", text)
    kept = "".join(char for char in folded if not unicodedata.combining(char))
    return kept.encode("ascii", errors="replace").decode("ascii")


def custom_count(line: str, path: Path, number: int, what: str) -> int:
    """Read a count from a custom polar line, naming malformed input.

    Parameters
    ----------
    line : str
        The line read.
    path : Path
        The file, named in the refusal.
    number : int
        The line's number, named in the refusal.
    what : str
        What the count counts, named in the refusal.

    Returns
    -------
    int
        The count.

    Raises
    ------
    ProductError
        If the line does not open with the count as digits.
    """
    try:
        return int(line.split()[0])
    except (IndexError, ValueError):
        raise ProductError(
            f"{path} line {number} should be the number of {what} as digits; it reads {line!r}"
        ) from None


def _numbers(cells: Sequence[str], path: Path, number: int) -> list[float]:
    """Read a line's cells as numbers, refusing a cell that is not one by its line."""
    try:
        return [float("nan") if cell in (NOT_APPLICABLE, "-") else float(cell) for cell in cells]
    except ValueError:
        raise ProductError(
            f"{path} line {number} should hold numbers; it reads {' '.join(cells)!r}"
        ) from None


def _refuse_repeats(names: tuple[str, ...], target: Path, number: int) -> None:
    """Refuse a header line that names one column twice: a mapping would drop the earlier value."""
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ProductError(f"{target} line {number} names {', '.join(repeated)} more than once")


def _reference_count_and_group(target: Path, line: str) -> tuple[int, int]:
    """Read the reference count and the group number of the fourth header line."""
    counts = line.split()
    if len(counts) != 2:
        raise ProductError(
            f"{target} line 4 should be the reference count and the group number; it reads {line!r}"
        )
    try:
        return int(counts[0]), int(counts[1])
    except ValueError:
        raise ProductError(
            f"{target} line 4 should be the reference count and the group number as digits; "
            f"it reads {line!r}"
        ) from None


def _custom_rows(
    target: Path, data: list[str], columns: tuple[str, ...], row_count: int
) -> list[dict[str, float]]:
    """Read the data rows of a custom polar file, each checked against the stated counts."""
    if len(data) != row_count:
        raise ProductError(
            f"{target} line 7 states {row_count} rows and the file holds {len(data)}"
        )
    rows: list[dict[str, float]] = []
    for number, line in enumerate(data, start=10):
        cells = line.split()
        if len(cells) != len(columns):
            raise ProductError(
                f"{target} line {number} carries {len(cells)} values for {len(columns)} columns"
            )
        rows.append(dict(zip(columns, _numbers(cells, target, number), strict=True)))
    return rows


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
    # The writer's policy read back: a file someone wrote outside ASCII is read
    # with its text transliterated, never refused by a bare UnicodeDecodeError.
    lines = _ascii_title(target.read_text(encoding="utf-8", errors="replace")).split("\n")
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
    reference_count, group = _reference_count_and_group(target, lines[3])
    names = tuple(lines[4].split())
    values = lines[5].split()
    if len(names) != reference_count or len(values) != reference_count:
        raise ProductError(
            f"{target} line 4 states {reference_count} reference columns and lines 5 and 6 "
            f"carry {len(names)} names and {len(values)} values"
        )
    _refuse_repeats(names, target, 5)
    reference_values = dict(zip(names, _numbers(values, target, 6), strict=True))
    row_count = custom_count(lines[6], target, 7, "data rows")
    column_count = custom_count(lines[7], target, 8, "data columns")
    columns = tuple(lines[8].split())
    if len(columns) != column_count:
        raise ProductError(
            f"{target} line 8 states {column_count} columns and line 9 names {len(columns)}"
        )
    _refuse_repeats(columns, target, 9)
    rows = _custom_rows(target, lines[9:], columns, row_count)
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
