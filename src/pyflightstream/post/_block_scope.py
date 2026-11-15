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
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._tokens import NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.post._run_block import RUN_BLOCK_SPEC

__all__ = [
    "add_run_block_to_vtk",
    "run_block_text",
    "tecplot_run_block",
    "vtk_run_block_lines",
    "BLOCK_FOLDERS",
    "RUN_BLOCK_LAST",
    "after_run_block",
    "apply_point_blocks",
    "apply_row_blocks",
    "block_of_point",
    "collect_block",
    "collected_block",
    "collecting_blocks",
    "rotor_ids_for",
    "run_blocks",
    "scope_rotor_ids",
    "with_rotor_alias",
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


def scope_rotor_ids() -> dict[str, int]:
    """Return each rotor alias's declared id in the open scope, empty outside one.

    Examples
    --------
    >>> scope_rotor_ids()
    {}
    """
    scope = _SCOPE.get()
    return {} if scope is None else dict(scope.rotor_ids)


def rotor_ids_for(
    aliases: Iterable[object], rotor_ids: Mapping[str, int] | None = None
) -> dict[str, int]:
    """Return each rotor alias's declared id: those given, else the open scope's.

    Where neither states an id and the table knows one rotor only, that rotor
    is rotor 0, the id a rotor block takes when it declares none (design D6).

    Examples
    --------
    >>> rotor_ids_for(["PUSHER"], {"PUSHER": 2}), rotor_ids_for(["PROP"])
    ({'PUSHER': 2}, {'PROP': 0})
    >>> rotor_ids_for(["A", "B"])
    {}
    """
    ids = dict(rotor_ids) if rotor_ids else scope_rotor_ids()
    names = list(dict.fromkeys(str(alias) for alias in aliases if alias))
    if not ids and len(names) == 1:
        return {names[0]: 0}
    return ids


def with_rotor_alias(
    rows: Sequence[Mapping[str, str]],
    rotor_ids: Mapping[str, int] | None = None,
    *,
    aliases: Iterable[object] = (),
) -> list[dict[str, str]]:
    """Return the rows of a table that names its rotor by ``ROTOR_ID`` only, with its alias.

    The sections table states the rotor by its declared id (``ROTOR_ID``); a
    reader that selects a rotor's rows by alias reads ``ROTOR`` here, resolved
    from the id through :func:`rotor_ids_for` of ``aliases`` (the rotors the
    reader knows) and ``rotor_ids``. A row that already states ``ROTOR``, or
    whose id names no rotor, is left as it is.

    Parameters
    ----------
    rows : sequence of mapping
        The table's rows as :func:`~pyflightstream.post._tables.read_csv_table` reads them.
    rotor_ids : mapping of str to int, optional
        Each rotor alias to its declared id.
    aliases : iterable of str, optional
        The rotors the reader knows.

    Returns
    -------
    list of dict
        The rows, each with ``ROTOR`` where its id resolves.

    Examples
    --------
    >>> with_rotor_alias([{"ROTOR_ID": "2"}, {"ROTOR_ID": "NA"}], {"PUSHER": 2})
    [{'ROTOR_ID': '2', 'ROTOR': 'PUSHER'}, {'ROTOR_ID': 'NA'}]
    """
    ids = rotor_ids_for(aliases, rotor_ids)
    alias_of = {str(rotor_id): str(alias) for alias, rotor_id in ids.items()}
    out: list[dict[str, str]] = []
    for row in rows:
        own = dict(row)
        if _ROTOR_COLUMN not in own and (alias := alias_of.get(str(own.get(_ROTOR_ID)))):
            own[_ROTOR_COLUMN] = alias
        out.append(own)
    return out


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


def apply_point_blocks(
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    points: Sequence[str | None],
) -> tuple[Sequence[str], Sequence[Sequence[object]]]:
    """Return a table opened with the run block of the point each row names, in the open scope.

    Parameters
    ----------
    columns : sequence of str
        The table's header.
    rows : sequence of sequence of object
        Its rows.
    points : sequence of str or None
        The point of each row, None for a row of no known point.

    Returns
    -------
    tuple
        As :func:`apply_row_blocks`; the table untouched outside a post.

    Examples
    --------
    >>> apply_point_blocks(("X",), [(1,)], ["AL+000"])
    (('X',), [(1,)])
    """
    scope = _SCOPE.get()
    rotor_ids = None if scope is None else scope.rotor_ids
    blocks = [None if point is None else block_of_point(point) for point in points]
    return apply_row_blocks(columns, rows, blocks, rotor_ids)


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


# --- the run block in a visualization file: Tecplot auxiliary data and VTK field data ---

#: The run block columns whose value is text: a numeric column that has no value
#: is ``nan`` in a VTK array, a text one keeps ``NA``.
_TEXT_BLOCK_COLUMNS = frozenset({"POL", "POINT", "RUN_TYPE", "MU"})


def _is_text(name: str, value: object) -> bool:
    return name in _TEXT_BLOCK_COLUMNS or (isinstance(value, str) and value != "NA")


def run_block_text(value: object) -> str:
    """Return one run block value as the text an auxiliary record carries.

    Examples
    --------
    >>> run_block_text(4.0), run_block_text(None), run_block_text("steady")
    ('4.0', 'NA', 'steady')
    """
    if value is None or value == "":
        return "NA"
    if isinstance(value, float) and not math.isfinite(value):
        return "NA"
    return str(value).replace('"', "'").replace("\n", " ")


def tecplot_run_block(block: Mapping[str, object]) -> dict[str, str]:
    """Return the run block as Tecplot ``DATASETAUXDATA`` records, in the block's order.

    Parameters
    ----------
    block : mapping
        The point's run block row.

    Returns
    -------
    dict of str to str
        One record per column, name to text.

    Examples
    --------
    >>> tecplot_run_block({"POL": "7001", "ALPHA": 4.0})
    {'POL': '7001', 'ALPHA': '4.0'}
    """
    return {str(name): run_block_text(value) for name, value in block.items()}


def vtk_run_block_lines(block: Mapping[str, object]) -> list[str]:
    """Return the legacy VTK ``FIELD FieldData`` block of the run block's columns.

    One array per column: ``<COLUMN> 1 1 double`` for a number (``nan`` where it
    has none) and ``<COLUMN> 1 1 string`` for a text column, spaces made
    underscores.

    Examples
    --------
    >>> vtk_run_block_lines({"POL": "7001", "ALPHA": 4.0, "RHO": None})[:6]
    ['FIELD FieldData 3', 'POL 1 1 string', '7001', 'ALPHA 1 1 double', '4', 'RHO 1 1 double']
    """
    lines = [f"FIELD FieldData {len(block)}"]
    for name, value in block.items():
        if _is_text(str(name), value):
            lines += [f"{name} 1 1 string", run_block_text(value).replace(" ", "_")]
        else:
            number = (
                float(value)
                if isinstance(value, int | float) and not isinstance(value, bool)
                else math.nan
            )
            lines += [f"{name} 1 1 double", "nan" if not math.isfinite(number) else f"{number:g}"]
    return lines


def add_run_block_to_vtk(path: str | Path, block: Mapping[str, object]) -> Path:
    """Put the run block in a legacy ASCII VTK file as dataset field data.

    The ``FIELD`` block goes after the geometry and before the first
    ``POINT_DATA`` or ``CELL_DATA`` line, or at the end of a file that has none,
    so it is the dataset's own and no attribute's. Whether ParaView's legacy
    reader of this estate shows ``string`` field arrays is unconfirmed here; the
    numeric arrays are the part a reader can rely on.

    Parameters
    ----------
    path : str or Path
        The VTK file, already written.
    block : mapping
        The point's run block row.

    Returns
    -------
    Path
        ``path``.
    """
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines()
    at = next(
        (i for i, line in enumerate(lines) if line.startswith(("POINT_DATA", "CELL_DATA"))),
        len(lines),
    )
    lines[at:at] = vtk_run_block_lines(block)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
