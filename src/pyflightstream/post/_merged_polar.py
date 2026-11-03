"""The unsteady polar with its rotor tables and ROTATE angles on one row (FR-3511, FR-3512).

``[products] merged_polar`` writes ``P<sim>_<name>_merge.csv`` beside the unsteady polar. It
reads the tables the post has just written, so no solver run is added, and the definition is
on ``docs/definitions/the-unsteady-polar.md`` ("The merged polar"). A private module below
:mod:`pyflightstream.post._sim`, which calls it.

A rotor row joins a polar row by the run both came from. The flight condition cannot be the
key: a simulation that sweeps incidence at one advance ratio holds several rows of one ``J``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import NotApplicableWarning, warn
from pyflightstream._tokens import POLAR_ID_COLUMN, ROTOR_ID_COLUMN
from pyflightstream.post._stage import POLARS_DIR
from pyflightstream.post._tables import ROTOR_TABLE_SUFFIX, read_csv_table, write_csv_table

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext

__all__ = ["MERGED_POLAR_SUFFIX", "RotorRows", "merged_polar_products", "merged_polar_rows"]

#: The file suffix of the merged polar, replacing the unsteady polar's.
MERGED_POLAR_SUFFIX = "_merge.csv"
_UNSTEADY_POLAR_SUFFIX = "_uns_avg.csv"
_RUN_COLUMN = "run_id"


@dataclass(frozen=True)
class RotorRows:
    """One rotor table as written: its alias, columns, rows and the run of each row."""

    alias: str
    columns: tuple[str, ...]
    rows: Sequence[Mapping[str, str]]
    runs: Sequence[str]


def _angle_columns(
    rules: Mapping[str, str], rotations: Sequence[Mapping[str, str]] | None
) -> tuple[dict[str, float | None], list[str]]:
    """Return each declared column's angle and what the row did not state.

    A rotation the matrix row does not state is not turned, so its angle is 0. A run with
    no matrix row states nothing either way, so its angle is left unknown.
    """
    angles: dict[str, float | None] = {}
    notes: list[str] = []
    for column, rotation in rules.items():
        if rotations is None:
            angles[column] = None
            continue
        alias, _, axis = rotation.rpartition(":")
        stated = [
            record["ANGLE"]
            for record in rotations
            if record.get("AXIS") == axis.strip() and record.get("ALIAS") == alias.strip()
        ]
        angles[column] = float(stated[-1]) if stated else 0.0
        if not stated:
            notes.append(f"{column} reads 0: the row states no ROTATE of {rotation}")
    if rotations is None and angles:
        notes.append(f"{', '.join(angles)} read NA: this simulation has no matrix row")
    return angles, notes


def merged_polar_rows(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    rotor_tables: Sequence[RotorRows],
    rules: Mapping[str, str] | None = None,
    rotations: Sequence[Mapping[str, str]] | None = (),
) -> tuple[list[str], list[list[object]], list[str]]:
    """Return the merged header, its rows and what could not be filled.

    The polar's columns come first and keep their values. Each rotor table adds the columns
    the polar does not hold, ``ROTOR`` naming the rotors that have a row, then the declared
    ROTATE columns. A polar row with no rotor row reads ``NA`` in that rotor's columns.
    """
    header = list(columns)
    notes: list[str] = []
    added = _added_columns(header, rotor_tables)
    states_rotor = bool(rotor_tables) and ROTOR_ID_COLUMN not in header
    header.extend([ROTOR_ID_COLUMN] if states_rotor else [])
    header.extend(added)
    angles, angle_notes = _angle_columns(rules or {}, rotations)
    notes.extend(angle_notes)
    for column in [name for name in angles if name in header]:
        del angles[column]
        notes.append(f"{column} is not added: the table already holds that column")
    header.extend(angles)
    by_run = [
        (table, dict(zip(table.runs, table.rows, strict=True)))
        for table in rotor_tables
        if _runs_match(table, notes)
    ]
    body: list[list[object]] = []
    for row in rows:
        cells: dict[str, object] = {**row, **angles}
        present = _take_rotor_rows(cells, row.get(_RUN_COLUMN, ""), by_run, set(added), notes)
        if states_rotor:
            cells[ROTOR_ID_COLUMN] = "+".join(present) or None
        body.append([cells.get(column) for column in header])
    return header, body, notes


def _added_columns(header: Sequence[str], rotor_tables: Sequence[RotorRows]) -> list[str]:
    """Return the rotor tables' columns the polar does not hold, first seen first."""
    names = [column for table in rotor_tables for column in table.columns]
    return [
        column
        for column in dict.fromkeys(names)
        if column not in (POLAR_ID_COLUMN, ROTOR_ID_COLUMN) and column not in header
    ]


def _take_rotor_rows(
    cells: dict[str, object],
    run: str,
    by_run: Sequence[tuple[RotorRows, Mapping[str, Mapping[str, str]]]],
    added: set[str],
    notes: list[str],
) -> list[str]:
    """Fill ``cells`` from each rotor's row of ``run``; return the rotors that have one."""
    present: list[str] = []
    for table, table_rows in by_run:
        rotor_row = table_rows.get(run)
        if rotor_row is None:
            notes.append(f"run {run or 'NA'} has no row of rotor {table.alias}")
            continue
        present.append(table.alias)
        for column in added.intersection(table.columns):
            cells.setdefault(column, rotor_row.get(column))
    return present


def _runs_match(table: RotorRows, notes: list[str]) -> bool:
    """Say whether each row of ``table`` has its run; name the table when it does not."""
    if len(table.runs) == len(table.rows) and len(set(table.runs)) == len(table.runs):
        return True
    notes.append(
        f"rotor {table.alias} reads NA: its {len(table.rows)} rows do not each name one run "
        f"of the {len(table.runs)} recorded"
    )
    return False


def merged_polar_products(ctx: SimContext) -> None:
    """Write the merged polar beside the simulation's unsteady polar, when the pproc asks.

    It runs last, so it reads the polar and the rotor tables as every other step left them.
    What it cannot fill is named under ``skipped`` for the file and warned once, and the
    table is still written. A simulation with no unsteady polar has nothing to merge, which
    is said the same way.
    """
    products = ctx.pproc.products
    if not products.merged_polar:
        if products.rotate_columns:
            _say(
                ctx,
                f"{POLARS_DIR}/{ctx.sim_id}#merged_polar",
                "rotate_columns is read only with merged_polar = true",
            )
        return
    polars = [
        name
        for name in ctx.written_names
        if name.startswith(f"{POLARS_DIR}/") and name.endswith(_UNSTEADY_POLAR_SUFFIX)
    ]
    if not polars:
        _say(
            ctx,
            f"{POLARS_DIR}/{ctx.sim_id}#merged_polar",
            "this simulation wrote no unsteady polar, so there is nothing to merge",
        )
        return
    for name in polars:
        _write_merged_polar(ctx, name)


def _write_merged_polar(ctx: SimContext, name: str) -> None:
    """Write the merged polar of the unsteady polar the manifest names ``name``."""
    columns, rows = read_csv_table(ctx.out / name)
    tables = [
        RotorRows(str(entry["rotor"]), *read_csv_table(ctx.out / other), _runs_of(entry))
        for other, entry in ctx.written_names.items()
        if other.endswith(ROTOR_TABLE_SUFFIX) and "rotor" in entry
    ]
    row = ctx.matrix_row
    header, body, notes = merged_polar_rows(
        columns,
        rows,
        tables,
        ctx.pproc.products.rotate_columns,
        None if row is None else row.rotations,
    )
    source = ctx.out / name
    target = ctx.target(source.with_name(_merged_name(source)))
    write_csv_table(target, header, body)
    relative = target.relative_to(ctx.out).as_posix()
    ctx.add(
        target,
        {
            "kind": "merged_polar",
            "runs": ctx.written_names[name].get("runs", []),
            "source": name,
            "rotors": [table.alias for table in tables],
        },
    )
    if notes:
        _say(ctx, relative, "; ".join(dict.fromkeys(notes)))


def _merged_name(source: Path) -> str:
    """Return the merged polar's file name beside the unsteady polar ``source``."""
    return source.name.removesuffix(_UNSTEADY_POLAR_SUFFIX) + MERGED_POLAR_SUFFIX


def _runs_of(entry: Mapping[str, object]) -> list[str]:
    """Return the runs a rotor table's manifest entry states, one per row in row order."""
    runs = entry.get("runs")
    return [str(run) for run in runs] if isinstance(runs, list) else []


def _say(ctx: SimContext, key: str, text: str) -> None:
    """Name what was not written under ``skipped`` and warn it once."""
    ctx.skipped[key] = text
    warn(f"{key}: {text}", NotApplicableWarning, stacklevel=2)
