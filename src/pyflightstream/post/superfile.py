"""FR-89: one derived file per polar and group that carries everything the workspace knows.

Knowing what one simulation WAS and what it PRODUCED took six files until
0.16.0: the polar table, the campaign sweep table, the matrix row, the setup,
the reference and the unsteady plots, five of them in different shapes. The
author's seventh feedback item of 2026-09-10 asked for one:

    post/<matrix>/polars/SUPER-0001_M15AL+000BE+000J+sweep_g01.csv

THE NAME IS HERS: the standard point convention with ``SUPER-`` in place of
``POLAR-``, so it is told apart at a glance, the swept variable written
literally as ``sweep``, and the group suffix at the end.

IT IS WRITTEN AFTER THE UNSTEADY POST-PROCESS, which settles its shape: one
row per CONVERGED point and no time series, so nothing is repeated down the
file and a reader cannot tell from it whether the run behind a row was steady
or unsteady. That transparency is the point of it rather than a consequence,
and it is why the COLUMN SET IS THE CAMPAIGN'S rather than the polar's: a
steady polar's file carries the same header as the rotor's beside it, with
empty cells where that run produced nothing.

ITS COLUMN SET IS A SUPERSET of the union of what the workspace knows about
that simulation, and the rule is a superset rather than a list because a list
is a judgement about what matters and she asked for completeness. Her own
statement of the acceptance is one sentence: if she has to open a second file
to know something about that simulation, it failed.

WHERE EVERY VALUE COMES FROM, and NONE of them is assembled a second time
here. Each block is a table some other writer already built, carried across
under its own column names:

    the polar table's own row     `products.polar_table_rows`, the one
                                  assembly the polar table is written from
    the matrix row                `cases.matrix.read_matrix`, the row whose
                                  POL is this polar
    the flight condition          the manifest record: what the row stated,
                                  what the setup pinned, and what the
                                  resolver solved
    the rotor speed               the record's reduction windows, per rotor
    the campaign sweep table      `results.tables.sweep_table`, the frame
                                  `campaign_sweep.csv` is written from
    the solver flags              the record's solver-setup snapshot, keyed
                                  by the solver command
    the unsteady plots            the plots table this stage has just
                                  written, at its LAST time step

A field already carried by an earlier block is NOT overwritten by a later
one: the blocks overlap on purpose (``MACH`` is a polar column and a flight
condition key; ``DESCRIPTION`` is a polar column and a matrix cell), and the
first writer of a name is the one whose precision and units the column
documents.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pyflightstream.cases.matrix import MatrixError, MatrixRow, read_matrix
from pyflightstream.post._tables import ProductError, write_csv_table
from pyflightstream.post._tables import _cell as _fixed_cell
from pyflightstream.workspace.naming import polar_name

__all__ = [
    "REPORTS_DIR",
    "RPM_COLUMN",
    "SUPERFILE_REPORT_PREFIX",
    "SUPER_PREFIX",
    "SuperfileDraft",
    "declared_sweep",
    "matrix_rows",
    "plots_last_row",
    "release_tag",
    "super_file_name",
    "superfile_row",
    "union_the_workspace_knows",
    "write_superfile_report",
    "write_superfiles",
]

#: What the superfile carries in place of ``POLAR-`` (FR-89). The rest of
#: the name is the point convention every script and export of the same
#: point already carries, so the two sort side by side and a reader tells
#: them apart by the one word that differs.
SUPER_PREFIX = "SUPER-"

#: Where a workspace's measurements land, beside ``post/`` and ``sims/``.
REPORTS_DIR = "reports"

#: The stem of the measurement this module writes; the release tag is
#: appended, so ``reports/superfile-0160.json``.
SUPERFILE_REPORT_PREFIX = "superfile-"

#: The suffix of the campaign's own matrix file.
_MATRIX_SUFFIX = ".fs"

#: The two matrix cells whose content is a LIST OF KEYS rather than one
#: value, so the union of what the workspace knows includes the keys
#: inside them and not only the cell's own name.
_KEYED_CELLS = {"FLIGHT_CONDITION": ",", "VAR_NAMES_VALUES": "/"}

#: The point axes a matrix row states in its FLIGHT_CONDITION cell that are
#: resolved PER POINT rather than held for the whole row, mapped to the
#: column the polar table already writes the resolved value under. A cell
#: key named here takes the point's value; every other key takes the row's.
_AXIS_COLUMNS = {"ALPHA": "ALPHA", "BETA": "BETA", "ADVANCE_RATIO": "J"}

#: The column naming the rotor speed her sentence asks for by name. A row
#: that turns several rotors also gets ``RPM_<alias>`` per rotor, because
#: one number cannot be two speeds; ``RPM`` then carries the speed only
#: where the row turns exactly one.
RPM_COLUMN = "RPM"


def release_tag(version: str) -> str:
    """Return the release tag of ``version``: ``0.16.0.dev0`` becomes ``0160``.

    MEASURED FROM THE WORKSPACE NAMES ON DISK rather than invented here.
    `GeoverseResearch/tools/fts_workspace/` holds `pfs030`, `pfs040`,
    `pfs080`, `pfs0100`, `pfs0101`, `pfs0110`, `pfs0150` and `pfs0160`,
    one per release since 0.3.0, and each is the three version numbers
    written one after another with no separator: 0.10.1 is `0101` and
    0.8.0 is `080`. The goal's own reports are named the same way, which
    is why this function exists at all: the measurement this module
    writes has to land where the arm that reads it looks.
    """
    parts = version.split(".")
    if len(parts) < 3:
        raise ProductError(f"the version {version!r} has no major, minor and patch to tag with")
    numbers = []
    for part in parts[:3]:
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            raise ProductError(f"the version {version!r} carries a part with no digits")
        numbers.append(str(int(digits)))
    return "".join(numbers)


def super_file_name(
    sim: str,
    *,
    mach: float,
    group: str | int,
    point: Mapping[str, float],
    swept: Sequence[str] = (),
    suffix: str = ".csv",
) -> str:
    """``SUPER-<point convention with 'sweep' in the swept field>_g<group:02d>.csv``.

    The same stem :func:`~pyflightstream.post.products.swept_polar_file_name`
    renders for the polar table beside it, with the one word that tells the
    two apart substituted in front.
    """
    stem = polar_name(
        sim,
        mach,
        float(point.get("alpha", 0.0) or 0.0),
        float(point.get("beta", 0.0) or 0.0),
        None if point.get("advance_ratio") is None else float(point["advance_ratio"]),
        swept=swept,
    )
    return f"{SUPER_PREFIX}{stem.removeprefix('POLAR-')}_g{int(group):02d}{suffix}"


def matrix_rows(root: Path, matrix_stem: str | None) -> dict[str, MatrixRow]:
    """Return the rows of the campaign's own matrix, keyed by POL; empty when there is none.

    WHERE THE FILE IS LOOKED FOR, and it is a measurement rather than a
    rule the format states: both workspaces that ran on the licensed
    machine on 2026-09-11, `pfs0160` and `pfs0160-extract`, hold their
    matrix at the workspace root under the stem every record names, so
    `matrix_stem = "matriz"` is `<root>/matriz.fs`. A matrix kept
    elsewhere is not found, and the consequence is stated rather than
    hidden: its cells are then absent from the superfile AND from the
    union of what the workspace knows, so the two still agree and no
    field is silently dropped from a file that claims to be complete.

    EVERY ROW, active or not. `active_only` would drop a row whose RUN
    cell was set back to 0 after it ran, and the records of that run are
    in the manifest either way; a superfile of a recorded point must be
    able to say what its row said.
    """
    if not matrix_stem:
        return {}
    path = root / f"{matrix_stem}{_MATRIX_SUFFIX}"
    if not path.is_file():
        return {}
    try:
        rows = read_matrix(path, active_only=False)
    except (MatrixError, OSError):
        # A matrix this reader cannot read is not this stage's refusal: the
        # products of a recorded campaign must not depend on a file that is
        # not evidence of any run. The cells are absent from both sides.
        return {}
    return {row.pol: row for row in rows}


def declared_sweep(row: MatrixRow | None, measured: Sequence[str]) -> tuple[str, ...]:
    """Return the axes the superfile writes as ``sweep``: the row's, else the measured ones.

    THE ROW'S DECLARATION WINS, and this is the one place the superfile's
    name differs from the polar table's beside it. MEASURED on `pfs0160`:
    simulation 6002 declares `ADVANCE_RATIO:sweep` and its SWEEP_VALUES
    cell holds a single value, so nothing VARIES across its points and
    `swept_axes` correctly reports no axis. The polar table is therefore
    named for the value it has, `POLAR-6002_M14AL+000BE+000J+170_g01.csv`,
    which is FR-85's own rule and right for a table of one row.

    A superfile named that way would carry no `sweep` field at all, which
    the requirement's own example and her decision exclude: the superfile
    is about the SWEEP, whatever the sweep resolved to. So the axis comes
    from the cell that declares it, and falls back to what varied only
    where no matrix row is in reach.
    """
    if row is None:
        return tuple(measured)
    if row.sweep.type == "alpha_beta":
        return ("alpha", "beta")
    return (row.sweep.type,)


# --- the row ---------------------------------------------------------------


def _free(value: object) -> str:
    """One cell whose precision is the SOURCE's, not the polar table's.

    The polar table writes at five decimals, the author's precision, and every
    value that comes from it keeps that. A value that comes from anywhere
    else must not be rounded to it: measured on `pfs0160`, the residual of
    the rotor point is 5.381595e-06, and five decimals would write it
    `0.00001` and destroy the only digit a reader of a residual wants.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float | np.floating):
        number = float(value)
        return "" if math.isnan(number) else repr(number)
    if isinstance(value, np.integer):
        return str(int(value))
    return str(value)


def _take(row: dict[str, str], key: str, value: object, *, fixed: bool = False) -> None:
    """Write one field, and never over a field an earlier block already wrote."""
    if key in row:
        return
    row[key] = _fixed_cell(value) if fixed else _free(value)


#: The record's own scalar fields the superfile carries, in ONE home.
#:
#: THE WRITER LOOPS THIS AND THE UNION REQUIRES IT, which is the whole point
#: of the constant. They were two lists until 2026-09-11: the writer named
#: these seven and `union_the_workspace_knows` read only a record's
#: `flight_condition`, `flight_condition_defaults`, `solver_setup.flags` and
#: `reductions.rotors`, so NONE of these was visible to the superset check.
#: The QA lens of the push review proved it with a surviving mutant: deleting
#: `flight_condition_defaults_from` from the writer left all fifty post tests
#: green, including the one whose name is the completeness claim.
#:
#: With one home there is no writer line to delete on its own. Removing a
#: field is one visible edit to this tuple, and
#: `test_every_record_scalar_is_carried_or_excluded_on_purpose` then refuses
#: it unless the exclusion is written down beside it.
RECORD_SCALARS = (
    "flight_condition_defaults_from",
    "velocity_requested_m_s",
    "density_kg_m3",
    "temperature_k",
    "viscosity_pa_s",
    "density_source",
    "reference_length_m",
)


def superfile_row(
    *,
    polar_columns: Sequence[str],
    polar_values: Sequence[object],
    matrix_row: MatrixRow | None,
    record: object | None,
    sweep_row: Mapping[str, object] | None,
    plots_row: Mapping[str, str] | None,
) -> dict[str, str]:
    """Assemble one row of a superfile: one CONVERGED point, everything known about it.

    ``record`` is the manifest record of THIS point, duck-typed rather than
    imported: this module sits under the workspace layer the way every
    other product writer does.

    NONE WHERE THE POINT HAS NO RECORD, and then this row simply carries no
    key the record would have supplied. It does not need to: the header is
    the campaign's, and :func:`write_superfiles` unions the keys of every
    row and writes an empty cell for a row that lacks one, so the file's
    columns are the same whatever any single row knows.

    Borrowing another point's record was the alternative and it is the
    worse one: a missing cell is visible and a wrong one is not, in the one
    file whose claim is that it says everything about that simulation. The
    first writing of the campaign path did borrow, as
    ``by_run.get(run_id, records[0])``.
    """
    row: dict[str, str] = {}
    # 1. THE POLAR TABLE'S OWN ROW, verbatim and at its own precision, so
    #    the two files agree digit for digit on every column they share.
    for column, value in zip(polar_columns, polar_values, strict=True):
        _take(row, column, value, fixed=True)
    # 2. EVERY INPUT OF THE MATRIX ROW, under the cell names the matrix
    #    itself carries, including DESCRIPTION and the two activity flags.
    if matrix_row is not None:
        _take(row, "POL", matrix_row.pol)
        _take(row, "AIRCRAFT", matrix_row.aircraft)
        _take(row, "DESCRIPTION", matrix_row.description)
        _take(row, "REF", matrix_row.ref_code)
        _take(row, "SET", matrix_row.set_code)
        _take(row, "PPROC", matrix_row.pproc_code)
        _take(row, "FS_BUILD", matrix_row.fs_build)
        _take(row, "HIDDEN", matrix_row.hidden)
        _take(row, "RUN", matrix_row.run)
        _take(row, "WORKFLOW", matrix_row.workflow)
        _take(row, "RECIPE", matrix_row.script_code)
        # The two free cells as one string each, rendered from what the
        # reader parsed rather than re-read off the file: the cell is kept
        # so a reader sees the row as it was written, and every key inside
        # it is ALSO a column of its own below, so nothing is only inside a
        # string.
        _take(row, "FLIGHT_CONDITION", _condition_cell(matrix_row))
        _take(row, "SWEEP_VALUES", ",".join(_free(value) for value in matrix_row.sweep.values))
        _take(row, "SWEEP_VARIABLE", matrix_row.sweep.type)
        _take(
            row,
            "VAR_NAMES_VALUES",
            " / ".join(f"{key}: {_free(value)}" for key, value in matrix_row.variables.items()),
        )
        for key, value in matrix_row.variables.items():
            _take(row, key, value)
        # The three cell keys the matrix reader parses OUT of the variables
        # into lists of their own; written always, empty where the row
        # states none, so the column set does not depend on the row.
        _take(row, "MOTIONS", _records_cell(matrix_row.motions))
        _take(row, "ROTATE", _records_cell(matrix_row.rotations))
        _take(row, "RAW", _records_cell(matrix_row.raw))
        for key in matrix_row.flight_condition:
            _take(row, key, matrix_row.flight_condition[key])
        for key, column in _AXIS_COLUMNS.items():
            _take(row, key, row.get(column, ""))
    # 3. EVERY VARIABLE THAT DEFINES THE FLIGHT CONDITION, which is her
    #    second instruction of the same evening: what the row STATED, what
    #    the setup PINNED, and what the resolver SOLVED, under the keys
    #    each of the three is recorded by.
    for key, value in (getattr(record, "flight_condition", None) or {}).items():
        _take(row, key, value)
    for key, value in (getattr(record, "flight_condition_defaults", None) or {}).items():
        _take(row, key, value)
    for field in RECORD_SCALARS:
        _take(row, field, getattr(record, field, None))
    # 4. RPM, by name, and one column per rotor where the row turns several.
    for key, value in _rotor_speeds(getattr(record, "reductions", None)).items():
        _take(row, key, value)
    # 5. EVERYTHING THE CAMPAIGN SWEEP TABLE HOLDS: the run id, the status,
    #    the iterations, the residual, the wall time, the solver build and
    #    the package version, under that table's own column names.
    for key, value in (sweep_row or {}).items():
        _take(row, key, value)
    # 6. THE FLAGS, keyed by the solver command they set, which is the name
    #    the snapshot itself is keyed by and the name the solver knows.
    setup = getattr(record, "solver_setup", None) or {}
    flags = setup.get("flags") if isinstance(setup, Mapping) else None
    for command, flag in (flags or {}).items():
        _take(row, command, flag.get("value") if isinstance(flag, Mapping) else flag)
    # 7. EVERY PARAMETER THE UNSTEADY PLOTS PRODUCE, forces and fluids
    #    alike, AT THE LAST TIME STEP. See `plots_last_row`.
    for key, value in (plots_row or {}).items():
        _take(row, key, value)
    return row


def _condition_cell(row: MatrixRow) -> str:
    """Render the row's FLIGHT_CONDITION cell from what the reader parsed."""
    parts = [f"{key}:{_free(value)}" for key, value in row.flight_condition.items()]
    swept = {"alpha": "ALPHA", "beta": "BETA", "advance_ratio": "ADVANCE_RATIO"}.get(row.sweep.type)
    if swept:
        parts.append(f"{swept}:sweep")
    elif row.sweep.type == "alpha_beta":
        parts += ["ALPHA:sweep", "BETA:sweep"]
    return ", ".join(parts)


def _records_cell(records: Sequence[Mapping[str, str]]) -> str:
    """Render a list cell of the matrix, ``{K: V}`` per entry, in cell order."""
    return " ".join(
        "{" + ", ".join(f"{key}: {value}" for key, value in record.items()) + "}"
        for record in records
    )


def _rotor_speeds(reductions: object) -> dict[str, object]:
    """Return ``RPM`` and one ``RPM_<alias>`` per rotor the record's windows name."""
    speeds: dict[str, object] = {}
    rotors = reductions.get("rotors") if isinstance(reductions, Mapping) else None
    named: dict[str, object] = {}
    if isinstance(rotors, Mapping):
        for alias, block in rotors.items():
            if isinstance(block, Mapping) and block.get("rpm") is not None:
                named[str(alias)] = block["rpm"]
                speeds[f"{RPM_COLUMN}_{alias}"] = block["rpm"]
    flat = reductions.get("rpm") if isinstance(reductions, Mapping) else None
    if flat is not None:
        speeds[RPM_COLUMN] = flat
    elif len(named) == 1:
        speeds[RPM_COLUMN] = next(iter(named.values()))
    else:
        # EMPTY AND NOT ABSENT where the row turns none or several. The
        # column is the campaign's, so a file whose rows have no single
        # rotor speed still carries the header a reader looks for.
        speeds[RPM_COLUMN] = None
    return speeds


def plots_last_row(rows: Sequence[Mapping[str, str]]) -> Mapping[str, str] | None:
    """Return the LAST time step of a plots table already read back, or None.

    WHY THE LAST STEP AND NOT AN AVERAGE, stated because it is the one
    judgement in this file. The superfile is written AFTER the unsteady
    post-process and carries one row per CONVERGED point, so the time
    history has to become one value per parameter. The solver's own time
    average of the FORCES is already in the file twice over, as the
    coefficients of the polar table and of the campaign sweep table, both
    of which come from the loads spreadsheet an unsteady run writes as
    that average. What the plots export adds is what those cannot say:
    the per-body and per-blade breakdown and the fluid samples. The last
    exported step is the state the converged run ENDED at, it exists for
    every unsteady point, and it needs no window: MEASURED on `pfs0160`,
    the rotor point's three reductions were all SKIPPED because the row
    states no rotor speed, so a superfile built on the time-average
    reduction would have carried no fluid sample at all for the one point
    in that workspace that has any.

    The step it came from is not a guess: ``Time-step`` is a column of the
    plots table and travels with the rest.
    """
    return rows[-1] if rows else None


# --- the files --------------------------------------------------------------


@dataclass(frozen=True)
class SuperfileDraft:
    """One superfile before the campaign's column set is known.

    The rows are complete and the COLUMNS are not: the header is the union
    over every draft of the campaign, so that a steady polar's file and an
    unsteady one's carry the same header and a reader cannot tell them
    apart by their shape.
    """

    path: Path
    rows: tuple[dict[str, str], ...]
    entry: dict[str, object]


def write_superfiles(
    drafts: Sequence[SuperfileDraft], *, target: Callable[[Path], Path]
) -> tuple[list[Path], dict[Path, dict[str, object]], tuple[str, ...]]:
    """Write every superfile of a campaign under ONE column set, its union.

    Returns the files written, their manifest entries and the columns.
    """
    columns: list[str] = []
    seen: set[str] = set()
    for draft in drafts:
        for row in draft.rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
    written: list[Path] = []
    entries: dict[Path, dict[str, object]] = {}
    for draft in drafts:
        path = target(draft.path)
        write_csv_table(
            path, columns, [[row.get(column, "") for column in columns] for row in draft.rows]
        )
        written.append(path)
        entries[path] = {**draft.entry, "rows": len(draft.rows)}
    return written, entries, tuple(columns)


# --- the measurement --------------------------------------------------------


def _header(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        try:
            return set(next(csv.reader(handle)))
        except StopIteration:
            return set()


def _matrix_names(path: Path, pols: Iterable[str]) -> set[str]:
    """Every NAME a run matrix carries: its columns, and the keys inside its cells.

    It reads the file as text and takes NAMES ONLY, never a value and never
    a row: this is the measurement's gatherer and not a second reader of
    the format. Nothing here reaches a run, a script or a record, and the
    row the superfile writes comes from
    :func:`~pyflightstream.cases.matrix.read_matrix` like everything else.

    THE KEYS INSIDE A CELL ARE TAKEN FROM THE RECORDED ROWS ALONE, and the
    matrix's own thirteen COLUMN names from the file whatever it holds.
    MEASURED on `pfs0160`: its matrix carries a third row, 6003, with
    ``RUN`` 0 and a ``digits`` variable of its own, and that row never ran.
    ``digits`` is a fact about a simulation this campaign does not have, so
    requiring it of the superfile of 6001 would be requiring a field about
    someone else; the thirteen columns are a fact about the FORMAT and are
    carried by every row.
    """
    wanted = {str(pol) for pol in pols}
    names: set[str] = set()
    try:
        lines = [
            line
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and set(line.strip()) != {"-"}
        ]
    except OSError:
        return names
    if not lines:
        return names
    header = [cell.strip() for cell in lines[0].split("|")]
    names |= set(header)
    for line in lines[1:]:
        # NOT strict: this gathers NAMES from a file that may be anything,
        # and a row with the wrong number of cells is a file the matrix
        # reader will refuse on its own terms, not a crash for a measurement.
        cells = dict(zip(header, [cell.strip() for cell in line.split("|")], strict=False))
        if cells.get("POL", "") not in wanted:
            continue
        for cell, separator in _KEYED_CELLS.items():
            for pair in cells.get(cell, "").split(separator):
                if ":" in pair:
                    names.add(pair.split(":", 1)[0].strip())
    return names


def union_the_workspace_knows(
    root: Path,
    out: Path,
    matrix_stem: str | None,
    *,
    polars_dir: str,
    probes_dir: str,
) -> set[str]:
    """Build the union of what the workspace knows about a simulation, FROM THE WORKSPACE.

    IT READS THE FILES AND NEVER THE ASSEMBLY. The superfile is built from
    the manifest records in memory; this reads the headers the other
    writers left on disk, the manifest as JSON and the matrix as text, so
    the two sides of the superset comparison are built differently and a
    field that reaches one has to reach the other on its own. A union
    derived from the superfile's own columns would be a check that accepts
    everything, which is the defect this requirement exists to prevent.
    """
    known: set[str] = set()
    for table in sorted((out / polars_dir).glob("POLAR-*.csv")):
        known |= _header(table)
    # The CAMPAIGN-level tables sit at the top of the matrix's folder and
    # the per-polar ones do not (FR-88), so this glob is `campaign_sweep.csv`
    # and anything else about the campaign as a whole.
    for table in sorted(out.glob("*.csv")):
        known |= _header(table)
    for table in sorted((out / probes_dir).glob("*_plots.csv")):
        known |= _header(table)
    known.add(RPM_COLUMN)
    manifest = root / "runs.json"
    pols: set[str] = set()
    if manifest.is_file():
        try:
            records = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            records = []
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, Mapping):
                continue
            if matrix_stem and record.get("matrix_stem") != matrix_stem:
                continue
            pols.add(str(record.get("sim_id")))
            known |= set(record.get("flight_condition") or {})
            known |= set(record.get("flight_condition_defaults") or {})
            # THE RECORD'S OWN SCALARS, from the same tuple the writer loops.
            # Without this the union could not see a single one of them, and
            # a mutant that dropped one from the file passed the superset
            # check; measured by the push review of 2026-09-11.
            known |= {field for field in RECORD_SCALARS if record.get(field) is not None}
            setup = record.get("solver_setup") or {}
            known |= set((setup.get("flags") if isinstance(setup, Mapping) else None) or {})
            reductions = record.get("reductions") or {}
            rotors = reductions.get("rotors") if isinstance(reductions, Mapping) else None
            for alias in rotors or {}:
                known.add(f"{RPM_COLUMN}_{alias}")
    if matrix_stem:
        known |= _matrix_names(root / f"{matrix_stem}{_MATRIX_SUFFIX}", pols)
    return known


def write_superfile_report(
    root: Path,
    *,
    version: str,
    files: Iterable[tuple[Path, Sequence[str], int]],
    known: Iterable[str],
) -> Path:
    """Write the measurement of the superfiles: what was written, and what was known.

    The report the goal's superfile arm reads. It carries the union as its
    own field rather than letting the reader derive one, because an arm
    that decided the union itself would be deciding by judgement exactly
    what this requirement takes out of anyone's judgement.
    """
    payload = {
        "files": [
            {"name": path.name, "columns": list(columns), "rows": rows}
            for path, columns, rows in files
        ],
        "known": sorted(known),
    }
    target = root / REPORTS_DIR / f"{SUPERFILE_REPORT_PREFIX}{release_tag(version)}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return target
