"""The optional all-numeric projection of a solver-setup snapshot.

Pipeline role: a projection FOR TOOLS, never the record. The settings
record PFS-2012.11 writes beside every result is strings and mixed
types, which a plotting script or a spreadsheet cannot treat as data.
This module turns one or more snapshots into a table holding nothing but
numbers, so those tools can read it, and it is lossy by construction,
which is why it is optional and never replaces the full record.

THE MEASUREMENT THE LAYOUT RESTS ON. Across the sixty-five flags of a
bare snapshot on 26.120 the value field holds FIVE Python types:
fifty-seven ``None``, two ``int``, four ``float``, one ``str`` and one
``list``. One column cannot carry that and stay numeric.

THE RULE: A SENTINEL MAY ONLY APPEAR IN A COLUMN WHOSE DOMAIN WE
CONTROL. The code columns are assigned here, densely from 1, so 999 is
free in them by construction. The value columns are not ours: they carry
iteration counts, angles and boundary indices, any of which can
legitimately be 999. Carrying the value AND whether we know it in one
cell is the collision; separating them is the whole fix, and unknown
stops being a magic number and becomes the provenance code it always
was.

THE CODEBOOK IS FROZEN AND ITS HOME IS THE PAGE. ``docs/settings-codebook.md``
carries the flag ids, the provenance and kind codes and the per-flag
enumerations, and ``tests/test_settings_codebook.py`` reads that page
and fails when this module disagrees with it. That direction is
deliberate: if the only thing holding the encoding still were a page
describing the code, the two would drift the first time a flag gained a
state, and every file written in between would be misread from then on.

FLAG IDS ARE APPENDED, NEVER DERIVED. ``FLAG_SPECS`` grows whenever a
registered build adds a settings command, and it grows in the MIDDLE:
its order is the helper's emission order, not an arrival order. An id
read off a position there would renumber half the codebook on the next
build. So the order below is frozen literally, and a new flag takes the
next unused id in the same commit that moves the page.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pyflightstream.post.writers import OutputExistsError
from pyflightstream.results import MalformedOutputError
from pyflightstream.script.solver_setup import FLAG_SPECS, SolverSetup

__all__ = [
    "CODEBOOK_VERSION",
    "ENUMERATIONS",
    "FLAG_IDS",
    "LOSSY_KINDS",
    "PROVENANCE_CODES",
    "TIDY_COLUMNS",
    "VALUE_KINDS",
    "codebook",
    "read_settings_table",
    "settings_table",
    "write_settings_table",
]

#: Version of the frozen encoding. Every file written names it, and
#: reading a file that names another one is REFUSED rather than
#: reinterpreted. It changes when an id, a code or an enumeration
#: changes meaning, never when a flag is appended.
CODEBOOK_VERSION = 1

#: The frozen flag order. Position is the flag id, counted from 1.
#: Append only; see the module docstring for why it is not derived.
_FROZEN_ORDER: tuple[str, ...] = (
    "SET_SOLVER_STEADY",
    "SET_SOLVER_UNSTEADY",
    "SOLVER_SET_AOA",
    "SOLVER_SET_SIDESLIP",
    "SOLVER_SET_VELOCITY",
    "SOLVER_SET_MACH_NUMBER",
    "SOLVER_SET_REF_VELOCITY",
    "SOLVER_SET_REF_MACH_NUMBER",
    "SOLVER_SET_REF_AREA",
    "SOLVER_SET_REF_LENGTH",
    "SOLVER_SET_ITERATIONS",
    "SOLVER_SET_CONVERGENCE",
    "SET_MAX_PARALLEL_THREADS",
    "SOLVER_SET_FORCED_ITERATIONS",
    "SET_BOUNDARY_LAYER_TYPE",
    "SET_SOLVER_VISCOUS_COUPLING",
    "SET_VISCOUS_EXCLUDED_BOUNDARIES",
    "DELETE_VISCOUS_EXCLUDED_BOUNDARIES",
    "SET_SURFACE_ROUGHNESS",
    "SET_THIN_BOUNDARIES",
    "DELETE_THIN_BOUNDARIES",
    "CREATE_BULK_SEPARATION",
    "KUTTA_JOUKOWSKI_LIFT_FORCES",
    "PRINT_ROTOR_INDUCED_VELOCITIES",
    "SET_ADAPTIVE_FIELD_GRID_REFINEMENT",
    "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
    "ROTOR_INDUCED_VELOCITY_BLENDING",
    "SET_WAKE_NUMERICAL_RELAXATION",
    "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH",
    "SET_WAKE_DECAY_CONSTANT",
    "SOLVER_STABILIZATION",
    "DISABLE_SOLVER_REF_VELOCITY",
    "SET_SOLVER_MODEL",
    "VALAREZO_CRITERION",
    "SET_CROSSFLOW_SEPARATION_CP",
    "SET_WAKE_RELAXATION",
    "SET_WAKE_STREAMWISE_AGGLOMERATION",
    "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
    "SOLVER_VORTEX_RING_NORMALIZATION",
    "DELETE_SEPARATION",
    "CREATE_AIRFOIL_SEPARATION",
    "CREATE_AXIAL_VORTEX_SEPARATION",
    "CREATE_CYLINDRICAL_BULK_SEPARATION",
    "CREATE_STRATFORD_BULK_SEPARATION",
    "SET_AXIAL_SEPARATION_BOUNDARIES",
    "DELETE_AXIAL_SEPARATION_BOUNDARIES",
    "SET_VALAREZO_SEPARATION_BOUNDARIES",
    "DELETE_VALAREZO_SEPARATION_BOUNDARIES",
    "DELETE_VALAREZO_CRITERION_BOUNDARIES",
    "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
    "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES",
    "SET_CROSSFLOW_SEPARATION_DIAMETER",
    "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC",
    "LAMINAR_SEPARATION",
    "SET_SOLVER_CONVERGENCE_ITERATIONS",
    "SOLVER_MINIMUM_CP",
    "REYNOLDS_AVERAGED_DRAG_FORCES",
    "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY",
    "SOLVER_SET_FARFIELD_LAYERS",
    "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA",
    "SET_WAKE_TERMINATION_TIME_STEPS",
    "SET_WAKE_ON_WAKE_INDUCTION",
    "ADDITIONAL_WAKE_RELAXATION_ITERATION",
    "AEROELASTIC_RBF_TYPE",
    "SET_VORTICITY_DRAG_BOUNDARIES",
)

#: FlightStream command name to its frozen numeric id, dense from 1.
FLAG_IDS: dict[str, int] = {name: index for index, name in enumerate(_FROZEN_ORDER, start=1)}

#: Provenance of a flag, as a code. Dense from 1, so the fill value is
#: free here. ``unknown`` IS the way the file says it does not know,
#: which is why no value column ever carries a sentinel.
PROVENANCE_CODES: dict[str, int] = {"explicit": 1, "default": 2, "unknown": 3}

#: What kind of thing the value columns of a row hold.
VALUE_KINDS: dict[str, int] = {
    "bool": 1,
    "int": 2,
    "float": 3,
    "enumerated": 4,
    "list": 5,
    "mapping": 6,
}

#: The kinds this projection cannot carry whole. A boundary selection
#: contributes its LENGTH and a mapping its entry COUNT, and nothing
#: else: that is what makes this form optional and never the only copy.
LOSSY_KINDS: tuple[str, ...] = ("list", "mapping")

#: Per-flag token sets, coded densely from 1 IN THIS ORDER. Per flag
#: rather than global, which is what lets a reader tell that 999 is the
#: sentinel here and a value there.
ENUMERATIONS: dict[str, tuple[str, ...]] = {
    "SET_BOUNDARY_LAYER_TYPE": ("LAMINAR", "TRANSITIONAL", "TURBULENT"),
    "SET_SOLVER_MODEL": ("INCOMPRESSIBLE", "SUBSONIC", "TRANSONIC", "LOW_ORDER_SUPERSONIC"),
    "AEROELASTIC_RBF_TYPE": (
        "WENDLAND_C2",
        "GAUSSIAN",
        "THIN_PLATE_SPLINE",
        "MULTI_QUADRATIC",
        "INV_MULTI_QUADRATIC",
    ),
    "SET_VISCOUS_EXCLUDED_BOUNDARIES": ("all",),
    "SET_THIN_BOUNDARIES": ("all",),
    "SET_AXIAL_SEPARATION_BOUNDARIES": ("all",),
    "SET_VALAREZO_SEPARATION_BOUNDARIES": ("all",),
    "SET_CROSSFLOW_SEPARATION_BOUNDARIES": ("all",),
    "SET_VORTICITY_DRAG_BOUNDARIES": ("all",),
    "DELETE_SEPARATION": ("all",),
}

#: The tidy layout, one row per run and flag. Order is documented but
#: NOT guaranteed: a reader resolves a column by its LABEL (her
#: convention of 2026-08-17, NFR-19).
TIDY_COLUMNS: tuple[str, ...] = (
    "codebook_version",
    "run_index",
    "flag_id",
    "provenance_code",
    "emitted",
    "value_kind",
    "value_num",
    "value_code",
    "value_count",
)

#: The columns a fill value may reach. Ours by construction, so a fill
#: cannot be mistaken for a measurement.
_CODE_COLUMNS: tuple[str, ...] = ("value_kind", "value_code")

#: The columns a fill value may NEVER reach, because their domain is the
#: solver's rather than ours.
_VALUE_COLUMNS: tuple[str, ...] = ("value_num", "value_count")

Row = dict[str, int | float | None]


def _numeric_flags() -> list[str]:
    """Return the flags whose value column carries an unbounded quantity."""
    numeric = {"scalar", "mode_unsteady"}
    return [spec.command for spec in FLAG_SPECS if spec.kind in numeric]


def _encode(command: str, value: object) -> tuple[int | None, float | None, int | None, int | None]:
    """Return ``(value_kind, value_num, value_code, value_count)``."""
    if value is None:
        return None, None, None, None
    if isinstance(value, bool):
        return VALUE_KINDS["bool"], float(value), None, None
    if isinstance(value, int):
        return VALUE_KINDS["int"], float(value), None, None
    if isinstance(value, float):
        return VALUE_KINDS["float"], float(value), None, None
    if isinstance(value, str):
        tokens = ENUMERATIONS.get(command)
        if tokens is None or value not in tokens:
            raise MalformedOutputError(
                f"{command} holds the token {value!r}, which the frozen codebook does not "
                f"code. Known tokens for this flag: {list(tokens or ())}. A token cannot "
                "be given a code at write time, because a file written with an invented "
                "code is misread by every reader holding the published codebook: add it "
                "to ENUMERATIONS and to docs/settings-codebook.md in one commit."
            )
        return VALUE_KINDS["enumerated"], None, tokens.index(value) + 1, None
    if isinstance(value, Mapping):
        return VALUE_KINDS["mapping"], None, None, len(value)
    if isinstance(value, Sequence):
        return VALUE_KINDS["list"], None, None, len(value)
    raise MalformedOutputError(
        f"{command} holds a {type(value).__name__}, which this projection has no kind for; "
        "the full record beside it carries the value, and this form is deliberately the "
        "lossy one"
    )


def _refuse_a_value_fill(fill: object) -> None:
    """Refuse a fill aimed at a column whose domain is not ours."""
    at_risk = _numeric_flags()
    raise MalformedOutputError(
        f"filling a value column with {fill!r} is refused. The code columns "
        f"({', '.join(_CODE_COLUMNS)}) are assigned here, densely from 1, so a fill "
        f"cannot collide with them; the value columns ({', '.join(_VALUE_COLUMNS)}) carry "
        "solver quantities whose domain is the solver's, and read back a filled cell and "
        "a real setting equal to the fill are the same bytes. The flags whose legal range "
        f"contains {fill!r} are: {', '.join(at_risk)}. Leave the value columns empty, "
        "which reads as missing everywhere and collides with nothing."
    )


def _rows_for(setup: SolverSetup, run_index: int, fill: int | None) -> list[Row]:
    """Tidy rows for one snapshot."""
    rows: list[Row] = []
    for command, flag_id in FLAG_IDS.items():
        record = setup.flags.get(command)
        provenance = record.provenance if record is not None else "unknown"
        emitted = bool(record.emitted) if record is not None else False
        kind, num, code, count = _encode(command, record.value if record is not None else None)
        row: Row = {
            "codebook_version": CODEBOOK_VERSION,
            "run_index": run_index,
            "flag_id": flag_id,
            "provenance_code": PROVENANCE_CODES[provenance],
            "emitted": int(emitted),
            "value_kind": kind,
            "value_num": num,
            "value_code": code,
            "value_count": count,
        }
        if fill is not None:
            for column in _CODE_COLUMNS:
                if row[column] is None:
                    row[column] = fill
        rows.append(row)
    return rows


def settings_table(
    setups: Sequence[SolverSetup],
    *,
    wide: bool = False,
    fill: int | None = None,
    fill_values: bool = False,
) -> list[Row]:
    """Project solver-setup snapshots into an all-numeric table.

    Parameters
    ----------
    setups : sequence of SolverSetup
        One snapshot per run, in the order the runs are to be indexed.
        ``run_index`` is the 0-based position in this sequence.
    wide : bool, keyword-only
        One row per run instead of one row per run and flag. Each flag
        contributes ``f<id>_value`` and ``f<id>_prov``, never one column
        doing both jobs. Two columns suffice here and three are needed
        in the tidy form for a structural reason: a per-flag column is
        monomorphic, so ``f15_value`` always holds an enumeration code
        and ``f11_value`` always holds a count, whereas one shared
        ``value`` column would hold both.
    fill : int, optional
        Value written into an empty CODE column, for a tool that cannot
        read an empty cell. 999 is the conventional choice and is free
        by construction, because the code columns are assigned densely
        from 1. Default None, which leaves the cells empty; an empty CSV
        cell reads as missing everywhere and collides with nothing.
    fill_values : bool, keyword-only
        Ask for the VALUE columns to be filled too. Always REFUSED, and
        the refusal names the flags whose legal range contains the fill:
        a silent fill there would reintroduce the collision wearing an
        option flag.

    Returns
    -------
    list of dict
        Rows keyed by column label. Every cell is an ``int``, a
        ``float`` or None; no cell is a string.

    Raises
    ------
    MalformedOutputError
        If ``fill_values`` is asked for; if a flag holds a token the
        frozen codebook does not code; or if a flag holds a type this
        projection has no kind for.

    Examples
    --------
    >>> from pyflightstream.post.settings_table import FLAG_IDS, settings_table
    >>> from pyflightstream.script import Script, helpers
    >>> setup = helpers.solver_settings(Script(version="26.120"), velocity=30.0)
    >>> rows = {row["flag_id"]: row for row in settings_table([setup])}
    >>> rows[FLAG_IDS["SOLVER_SET_VELOCITY"]]["value_num"]
    30.0
    >>> rows[FLAG_IDS["SOLVER_SET_AOA"]]["provenance_code"]
    3
    """
    if fill_values:
        _refuse_a_value_fill(fill)
    tidy = [row for index, setup in enumerate(setups) for row in _rows_for(setup, index, fill)]
    if not wide:
        return tidy

    by_run: dict[int, Row] = {}
    for row in tidy:
        run = int(row["run_index"])  # type: ignore[arg-type]
        wide_row = by_run.setdefault(run, {"codebook_version": CODEBOOK_VERSION, "run_index": run})
        flag_id = int(row["flag_id"])  # type: ignore[arg-type]
        carried = row["value_num"]
        if carried is None:
            carried = row["value_code"]
        if carried is None:
            carried = row["value_count"]
        wide_row[f"f{flag_id}_value"] = carried
        wide_row[f"f{flag_id}_prov"] = row["provenance_code"]
    return [by_run[run] for run in sorted(by_run)]


def codebook() -> dict[str, object]:
    """Return the legend written beside every table.

    The file has to be readable alone, so its legend travels with it
    rather than living only on the documentation page. The page is still
    the contract, and the test that compares the two is what keeps this
    dictionary from becoming a second opinion.

    Returns
    -------
    dict
        ``codebook_version``, ``flag_ids``, ``provenance_codes``,
        ``value_kinds``, ``enumerations``, ``lossy_kinds`` and
        ``tidy_columns``.
    """
    return {
        "codebook_version": CODEBOOK_VERSION,
        "tidy_columns": list(TIDY_COLUMNS),
        "flag_ids": dict(FLAG_IDS),
        "provenance_codes": dict(PROVENANCE_CODES),
        "value_kinds": dict(VALUE_KINDS),
        "enumerations": {name: list(tokens) for name, tokens in ENUMERATIONS.items()},
        "lossy_kinds": list(LOSSY_KINDS),
        "lossy_note": (
            "this form is LOSSY: a list-valued flag contributes its LENGTH and a "
            "mapping its entry COUNT, "
            "and nothing else; the full settings record beside the data file carries "
            "the values this form drops, which is why this form is optional and never "
            "the only copy"
        ),
    }


def write_settings_table(
    path: str | Path,
    setups: Sequence[SolverSetup],
    *,
    wide: bool = False,
    fill: int | None = None,
    fill_values: bool = False,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write the numeric table and its legend, and return the pair.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination CSV file. The legend is written beside it as
        ``<name>.codebook.json``.
    setups : sequence of SolverSetup
        One snapshot per run.
    wide, fill, fill_values : see :func:`settings_table`
        Passed through unchanged.
    overwrite : bool, keyword-only
        Replace existing files. Default False, the same refusal the
        flow-visualization writers take.

    Returns
    -------
    tuple of pathlib.Path
        ``(table, legend)``.

    Raises
    ------
    OutputExistsError
        If either file exists and ``overwrite`` is False.
    MalformedOutputError
        As :func:`settings_table`.
    """
    destination = Path(path)
    legend = destination.with_name(destination.name + ".codebook.json")
    rows = settings_table(setups, wide=wide, fill=fill, fill_values=fill_values)
    for target in (destination, legend):
        if target.exists() and not overwrite:
            raise OutputExistsError(
                f"{target} already exists. Pass overwrite=True to replace it "
                "deliberately: a numeric table silently replaced by another run's is "
                "unreadable as either."
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0]) if rows else list(TIDY_COLUMNS)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})
    legend.write_text(json.dumps(codebook(), indent=2) + "\n", encoding="utf-8")
    return destination, legend


def read_settings_table(path: str | Path) -> list[Row]:
    """Read a numeric settings table, refusing another codebook.

    Parameters
    ----------
    path : str or pathlib.Path
        A file written by :func:`write_settings_table`.

    Returns
    -------
    list of dict
        The rows, with empty cells as None and every other cell as a
        number.

    Raises
    ------
    MalformedOutputError
        If the file carries no ``codebook_version`` column, or names a
        codebook other than :data:`CODEBOOK_VERSION`. It is REFUSED
        rather than resolved, because the one thing a reader must never
        do with an older encoding is reinterpret it silently: an id that
        moved makes every row of the file describe a different flag.
    """
    source = Path(path)
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        raw = list(reader)
    if "codebook_version" not in header:
        raise MalformedOutputError(
            f"{source} carries no codebook_version column, so nothing says which "
            "encoding wrote it and every code in it is unresolvable"
        )
    if not raw:
        # Distinguished from the header case deliberately: a file with
        # the column and no rows was written for no snapshot at all, and
        # telling that reader the column is missing sends them to look
        # for a defect in a file that has none.
        raise MalformedOutputError(
            f"{source} holds a header and no rows, so it describes no run. A settings "
            "table is written from a sequence of snapshots and that sequence was empty."
        )
    stamps = {row["codebook_version"] for row in raw}
    if stamps != {str(CODEBOOK_VERSION)}:
        raise MalformedOutputError(
            f"{source} was written under codebook version(s) {sorted(stamps)} and this "
            f"library holds version {CODEBOOK_VERSION}. It is refused rather than read: "
            "an id or a code that moved between the two would make every row describe a "
            "different flag, and a silent reinterpretation is exactly what the stamp "
            "exists to prevent."
        )
    rows: list[Row] = []
    for row in raw:
        converted: Row = {}
        for key, cell in row.items():
            if cell in ("", None):
                converted[key] = None
            else:
                number = float(cell)
                converted[key] = int(number) if number.is_integer() else number
        rows.append(converted)
    return rows
