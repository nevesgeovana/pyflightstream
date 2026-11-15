"""The columns a matrix row's ``IDENTIFIERS`` put in the tables a post writes (FR-3564).

Private to the package, in this layer because its writer is at or above it:
:func:`pyflightstream.post._tables.write_csv_table`, the funnel of the post's tables. A
row states
``IDENTIFIERS: {FLAP:0,TESTE:10}`` and every table the post writes for that row's polar gains a
column of each name, holding the value as text. The tables are many and their writers do not know
of it: the post driver opens :func:`stated_identifiers` over the matrix it read, and the funnel asks
here. With no identifiers in the matrix the scope is empty and a table passes untouched.

A table the post wrote and reads back to build another comes back without them
(:func:`without_stamped`), since the scope knows what it stamped where. That is what tells a column
the post put there from one the table holds as its own, which keeps its value.

Only the post reads a matrix's identifiers.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._tokens import (
    NOT_APPLICABLE,
    POLAR_ID_COLUMN,
    ROTOR_ID_COLUMN,
    plain_cell,
)


@dataclass
class _Scope:
    """One post's identifiers: the matrix's, by polar, and what has been done with them."""

    by_polar: Mapping[str, Mapping[str, str]]
    #: The simulation being posted, for a table with no ``POL`` to say whose it is.
    polar: str | None = None
    #: The names every table written now carries, whoever states them (the super files' union).
    held: tuple[str, ...] = ()
    warned: set[str] = field(default_factory=set)
    stamped: dict[Path, tuple[str, ...]] = field(default_factory=dict)

    def of_polar(self, polar: object) -> Mapping[str, str]:
        return self.by_polar.get(str(polar), {})


_SCOPE: ContextVar[_Scope | None] = ContextVar("identifier_columns", default=None)


@contextmanager
def stated_identifiers(stated: Mapping[str, Mapping[str, str]]) -> Iterator[None]:
    """Let the tables written inside this block take the identifiers ``stated``, by polar.

    Parameters
    ----------
    stated : mapping of str to mapping of str to str
        Each polar's identifiers, name to value, as written; a polar absent from it states none.

    Yields
    ------
    None
        The block.
    """
    outer = _SCOPE.get()
    by_polar = {
        polar: {plain_cell(name): value for name, value in names.items()}
        for polar, names in stated.items()
        if names
    }
    scope = _Scope(by_polar, warned=set() if outer is None else outer.warned)
    token = _SCOPE.set(scope if by_polar else None)
    try:
        yield
    finally:
        _SCOPE.reset(token)


@contextmanager
def tables_of_polar(polar: str) -> Iterator[None]:
    """Say whose the tables written inside this block are, for one that opens without ``POL``.

    Parameters
    ----------
    polar : str
        The simulation being posted.

    Yields
    ------
    None
        The block.
    """
    scope = _SCOPE.get()
    before = None if scope is None else scope.polar
    if scope is not None:
        scope.polar = polar
    try:
        yield
    finally:
        if scope is not None:
            scope.polar = before


def _position(columns: Sequence[str]) -> int:
    """Return where the identifier columns go: after ``POL``, and ``ROTOR`` right after it."""
    if not columns or columns[0] != POLAR_ID_COLUMN:
        return len(columns)
    return 2 if len(columns) > 1 and columns[1] == ROTOR_ID_COLUMN else 1


def _cell(value: object) -> str:
    """Return one identifier's cell: its text, as written, under the rule of every text cell."""
    text = "" if value is None else str(value)
    return plain_cell(text) if text.strip() else NOT_APPLICABLE


def _say_a_name_the_table_holds(scope: _Scope, name: str, path: Path) -> None:
    """Warn, once per post and name, of an identifier a table already holds as a column."""
    if name not in scope.warned:
        scope.warned.add(name)
        polars = sorted(polar for polar, names in scope.by_polar.items() if name in names)
        warn(
            f"POL {', '.join(polars)}: the identifier {name} is the name of a column {path.name} "
            "already holds; that "
            "table keeps its own value, here and in any other table holding the name. Rename "
            "the identifier to have it written.",
            PyflightstreamWarning,
            stacklevel=4,
        )


def stamped_table(
    path: str | Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> tuple[Sequence[str], Sequence[Sequence[object]]]:
    """Return a table with the columns of its rows' identifiers, and remember which it added.

    A table opening with ``POL`` takes each row's by that row's POL; the columns are the union
    over the table, right after ``POL`` (and after ``ROTOR`` where it stands right after ``POL``),
    and a row stating none reads ``NA``. A table opening without it takes its simulation's as its
    last columns. A name the table already holds keeps the table's value and warns once. With no
    identifiers the very ``columns`` and ``rows`` come back.

    Parameters
    ----------
    path : str or Path
        The table being written.
    columns : sequence of str
        Its header.
    rows : sequence of sequence of object
        Its rows, one value per column.

    Returns
    -------
    tuple of (sequence of str, sequence of sequence of object)
        The header and the rows to write.
    """
    scope = _SCOPE.get()
    if scope is None:
        return columns, rows
    rows = list(rows)
    opens = bool(columns) and columns[0] == POLAR_ID_COLUMN
    own = scope.of_polar(scope.polar)
    stated = [
        (scope.of_polar(row[0]) if row[0] is not None else own) if opens else own for row in rows
    ]
    named = dict.fromkeys(
        name for one in ([own] if not opens or not rows else stated) for name in one
    )
    held = {str(name) for name in columns}
    for name in named:
        if name in held:
            _say_a_name_the_table_holds(scope, name, Path(path))
    fresh = [name for name in (*scope.held, *named) if name not in held]
    fresh = list(dict.fromkeys(fresh))
    if not fresh:
        return columns, rows
    scope.stamped[Path(path).resolve()] = tuple(fresh)
    at = _position(columns)
    return (
        (*columns[:at], *fresh, *columns[at:]),
        [
            [*row[:at], *(_cell(one.get(name)) for name in fresh), *row[at:]]
            for row, one in zip(rows, stated, strict=True)
        ],
    )


def stamped_names(path: str | Path) -> tuple[str, ...]:
    """Return the identifier columns this post put in the table at ``path``.

    Parameters
    ----------
    path : str or Path
        A table.

    Returns
    -------
    tuple of str
        The names; empty outside a post or for a table the post did not stamp.
    """
    scope = _SCOPE.get()
    return () if scope is None else scope.stamped.get(Path(path).resolve(), ())


def without_stamped(
    path: str | Path, columns: tuple[str, ...], rows: list[dict[str, str]]
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Return a table read back without the columns this post's identifiers put in it.

    Parameters
    ----------
    path : str or Path
        The table read.
    columns : tuple of str
        Its header.
    rows : list of dict
        Its rows.

    Returns
    -------
    tuple of (tuple of str, list of dict)
        The table as its product wrote it.
    """
    names = stamped_names(path)
    if not names:
        return columns, rows
    return (
        tuple(name for name in columns if name not in names),
        [{key: value for key, value in row.items() if key not in names} for row in rows],
    )
