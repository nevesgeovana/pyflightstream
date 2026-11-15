"""The run block at the head of every table the post writes to the tree (FR-3778).

The post's tables are many and their writers do not know of the block: the
stage opens :func:`run_blocks` over the rows of the points it posts, and the
funnel :func:`pyflightstream.post._tables.write_csv_table` asks here. A table
written into a folder of the tree for a point that has a block opens with that
block, in the order of :mod:`pyflightstream.post._run_block`, and keeps its own
columns after it. A column the table and the block both state keeps the
table's value in each row (a reduction's own window), and the block's where the
table holds none. Outside a post, or for a table of no point, nothing changes.

The block ends at :data:`RUN_BLOCK_LAST`; a reader that must skip it finds that
column (:func:`after_run_block`).
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._tokens import NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.post._run_block import RUN_BLOCK_SPEC

__all__ = [
    "BLOCK_FOLDERS",
    "RUN_BLOCK_LAST",
    "after_run_block",
    "apply_row_blocks",
    "block_of_point",
    "collect_block",
    "collected_block",
    "collecting_blocks",
    "run_blocks",
    "with_run_block",
]

#: The folders of the tree whose per-point tables open with the run block. The
#: names are those of :mod:`pyflightstream.post._stage`, spelled here so this
#: module sits below the table funnel.
BLOCK_FOLDERS: frozenset[str] = frozenset({"time_history", "reductions", "probes", "sections"})

#: The last column of the run block, whatever the matrix and the rotors state.
RUN_BLOCK_LAST: str = RUN_BLOCK_SPEC[-1].name

_ROTOR_COLUMN = "ROTOR"
_ROTOR_ID = "ROTOR_ID"


@dataclass
class _Blocks:
    """The run block row of each point being posted, and the id of each rotor alias."""

    rows: dict[str, dict[str, object]]
    rotor_ids: dict[str, int]

    def of(self, file_name: str) -> dict[str, object] | None:
        """Return the row of the point whose name opens ``file_name`` (longest name wins)."""
        best: str | None = None
        for point in self.rows:
            if file_name.startswith(f"{point}_") and (best is None or len(point) > len(best)):
                best = point
        return None if best is None else self.rows[best]


_SCOPE: ContextVar[_Blocks | None] = ContextVar("run_block_scope", default=None)


@contextmanager
def run_blocks(
    rows: Mapping[str, Mapping[str, object]], rotor_ids: Mapping[str, int] | None = None
) -> Iterator[None]:
    """Open the tables written inside this block with the run block of their point.

    Parameters
    ----------
    rows : mapping of str to mapping
        The point name to its run block row, as
        :func:`~pyflightstream.post._run_block.run_block_row` returns it.
    rotor_ids : mapping of str to int, optional
        Each rotor alias to its declared id, for a table that names a rotor by
        alias and states its id beside it.

    Yields
    ------
    None
        The block.

    Examples
    --------
    >>> with run_blocks({"AL+000": {"POL": "P1"}}):
    ...     pass
    """
    token = _SCOPE.set(
        _Blocks({str(p): dict(r) for p, r in rows.items()}, dict(rotor_ids or {})) if rows else None
    )
    try:
        yield
    finally:
        _SCOPE.reset(token)


#: The run block row of every point of every simulation posted so far in this
#: post, by run id, for the tables that span simulations (the settings table).
_COLLECTED: ContextVar[dict[str, dict[str, object]] | None] = ContextVar(
    "run_block_collected", default=None
)


@contextmanager
def collecting_blocks() -> Iterator[None]:
    """Remember the run block row of each run id posted inside this block, and only here."""
    token = _COLLECTED.set({})
    try:
        yield
    finally:
        _COLLECTED.reset(token)


def collect_block(run_id: str, row: Mapping[str, object]) -> None:
    """Remember ``row`` as the run block of the run ``run_id``, inside :func:`collecting_blocks`."""
    held = _COLLECTED.get()
    if held is not None:
        held[str(run_id)] = dict(row)


def collected_block(run_id: str) -> dict[str, object] | None:
    """Return the run block row remembered for ``run_id``, None where there is none.

    Examples
    --------
    >>> with collecting_blocks():
    ...     collect_block("r1", {"POL": "7001"})
    ...     collected_block("r1"), collected_block("r2")
    ({'POL': '7001'}, None)
    """
    held = _COLLECTED.get()
    row = None if held is None else held.get(str(run_id))
    return None if row is None else dict(row)


def block_of_point(point: str) -> dict[str, object] | None:
    """Return the run block row of ``point`` in the open scope, None outside one.

    Examples
    --------
    >>> block_of_point("AL+000") is None
    True
    >>> with run_blocks({"AL+000": {"POL": "P1"}}):
    ...     block_of_point("AL+000")
    {'POL': 'P1'}
    """
    scope = _SCOPE.get()
    if scope is None:
        return None
    row = scope.rows.get(str(point))
    return None if row is None else dict(row)


def _absent(value: object) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value == NOT_APPLICABLE


def with_run_block(
    path: str | Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> tuple[Sequence[str], Sequence[Sequence[object]]]:
    """Return a table opened with its point's run block, or the table untouched.

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
        The run block's columns, then the table's own that the block does not
        state; with a ``ROTOR`` column and rotor ids known, ``ROTOR_ID`` stands
        before it.

    Examples
    --------
    >>> with_run_block("a.csv", ("X",), [(1,)])
    (('X',), [(1,)])
    """
    scope = _SCOPE.get()
    target = Path(path)
    if scope is None or target.parent.name not in BLOCK_FOLDERS:
        return columns, rows
    block = scope.of(target.name)
    if block is None:
        return columns, rows
    return apply_row_blocks(columns, rows, [block] * len(rows), scope.rotor_ids, head=block)


def apply_row_blocks(
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    blocks: Sequence[Mapping[str, object] | None],
    rotor_ids: Mapping[str, int] | None = None,
    *,
    head: Mapping[str, object] | None = None,
) -> tuple[Sequence[str], Sequence[Sequence[object]]]:
    """Return a table opened with the run block of each row's own point.

    For a table that spans points (the quasi-steady tables): ``blocks`` holds the
    block of each row, None for a row of no known point (its block columns read
    ``NA``). The header is the block's, taken from ``head`` or the first block.

    Parameters
    ----------
    columns : sequence of str
        The table's header.
    rows : sequence of sequence of object
        Its rows.
    blocks : sequence of mapping or None
        One per row.
    rotor_ids : mapping of str to int, optional
        Each rotor alias to its id, for a ``ROTOR`` column.
    head : mapping, optional
        The block that names the columns; the first row's block by default.

    Returns
    -------
    tuple
        The table with the block first; untouched when no block is known or a row
        has the wrong width.

    Examples
    --------
    >>> apply_row_blocks(("X",), [(1,)], [None])
    (('X',), [(1,)])
    """
    header = [str(name) for name in columns]
    block = head if head is not None else next((b for b in blocks if b is not None), None)
    if block is None or any(len(row) != len(header) for row in rows):
        return columns, rows  # the funnel refuses a wrong width, naming it
    ids = dict(rotor_ids or {})
    own = {name: at for at, name in enumerate(header)}
    rest = [name for name in header if name not in block]
    if _ROTOR_COLUMN in rest and _ROTOR_ID not in header and ids:
        rest.insert(rest.index(_ROTOR_COLUMN), _ROTOR_ID)
    out_rows: list[list[object]] = []
    for row, one in zip(rows, blocks, strict=True):
        cells: list[object] = []
        for name in block:
            at = own.get(name)
            stated = None if one is None else one.get(name)
            if at is not None and (not _absent(row[at]) or name == POLAR_ID_COLUMN):
                cells.append(row[at])
            else:
                cells.append(stated)
        for name in rest:
            if name == _ROTOR_ID and name not in own:
                cells.append(ids.get(str(row[own[_ROTOR_COLUMN]])))
            else:
                cells.append(row[own[name]])
        out_rows.append(cells)
    return (*block, *rest), out_rows


def after_run_block(columns: Sequence[str]) -> int:
    """Return the index of the first column after the run block, 0 when the table has none.

    Parameters
    ----------
    columns : sequence of str
        A table's header.

    Returns
    -------
    int
        One past :data:`RUN_BLOCK_LAST`, or 0.

    Examples
    --------
    >>> after_run_block(("POL", RUN_BLOCK_LAST, "FAMILY"))
    2
    >>> after_run_block(("POL", "X"))
    0
    """
    names = list(columns)
    return names.index(RUN_BLOCK_LAST) + 1 if RUN_BLOCK_LAST in names else 0
