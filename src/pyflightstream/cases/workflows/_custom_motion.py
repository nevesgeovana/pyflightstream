"""The custom motion a ``MOTIONS`` record drives by a table file (PFS-2254).

A record ``{ALIAS: flap / TABLE: flap.txt / TABLE_TYPE: POSITION-TIME}`` on an
``unsteady`` row moves the boundaries of the alias by a table of
``inputs/motions/``: the solver reads one row per time, seven numbers, the time
in seconds and then three translational and three angular components
(``SET_MOTION_CUSTOM_TABLE``, FSM-26.127 p.246 for the file and p.345 for the
command). The table is bound when the row is planned (its absolute path and
SHA-256 ride on the record), checked here before any line is emitted, and its
exact bytes are parked as the point's own copy, which the run writes and
hashes. The package never rewrites the file.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import CampaignConfigError, SimCase
from pyflightstream.script import Script

from ._conventions import declared_run_type
from ._names import (
    _declared_labels,
    _refuse_name_absent_from_inventory,
    _refuse_name_without_inventory,
    _resolve_token,
)
from ._row_cells import _variable
from ._timing import TimeStepping
from ._vocabulary import (
    CLOCK_MOTION_VARIABLE,
    DELTA_TIME_VARIABLE,
    MOTION_TABLE_COPY_SUFFIX,
    MOTION_TABLE_KEY,
    MOTION_TABLE_PATH_KEY,
    MOTION_TABLE_RECORD_KEYS,
    MOTION_TABLE_SHA256_KEY,
    MOTION_TABLE_TYPE_KEY,
    MOTION_TABLE_TYPES,
    MOTIONS_DIR,
    MOTIONS_VARIABLE,
    ROTATION_ALIAS_KEY,
)

__all__ = [
    "MOTION_TABLE_COLUMNS",
    "bind_motion_tables",
    "custom_motion_record_refusal",
    "emit_custom_motions",
    "read_motion_table",
    "refuse_a_table_motion_without_its_clock",
    "resolve_motion_tables",
    "written_record",
]

#: The numbers on one row of a motion table: the time, then three
#: translational and three angular components (FSM-26.127 p.246).
MOTION_TABLE_COLUMNS = 7

#: Commas or spaces separate the numbers of a row (FSM-26.127 p.246).
_SEPARATOR = re.compile(r"[,\s]+")


def written_record(record: Mapping[str, str]) -> str:
    """Return a record as the row wrote it, for a message: ``{KEY: value / ...}``."""
    shown = (key for key in record if key not in (MOTION_TABLE_PATH_KEY, MOTION_TABLE_SHA256_KEY))
    return "{" + " / ".join(f"{key}: {record[key]}" for key in shown) + "}"


def custom_motion_record_refusal(record: Mapping[str, str]) -> str | None:
    """Return why a custom motion record is not in its form, or None when it is.

    The record states ``ALIAS``, ``TABLE`` (a bare file name of
    ``inputs/motions/``) and ``TABLE_TYPE`` (``POSITION-TIME`` or
    ``VELOCITY-TIME``, the solver's own tokens, with no default: the two read
    the same columns as different quantities), and nothing else.
    """
    written = written_record(record)
    unknown = sorted(
        key
        for key in record
        if key not in (*MOTION_TABLE_RECORD_KEYS, MOTION_TABLE_PATH_KEY, MOTION_TABLE_SHA256_KEY)
    )
    if unknown:
        return (
            f"{MOTIONS_VARIABLE} record {written} states {', '.join(unknown)}, which a table "
            f"motion does not read; it states {', '.join(MOTION_TABLE_RECORD_KEYS)}."
        )
    missing = [key for key in MOTION_TABLE_RECORD_KEYS if not str(record.get(key) or "").strip()]
    if missing:
        return (
            f"{MOTIONS_VARIABLE} record {written} states no {' and no '.join(missing)}. A table "
            f"motion names the alias it moves ({ROTATION_ALIAS_KEY}), its file of "
            f"inputs/{MOTIONS_DIR}/ ({MOTION_TABLE_KEY}) and what the file holds "
            f"({MOTION_TABLE_TYPE_KEY}: {' or '.join(MOTION_TABLE_TYPES)}), which has no "
            "default: the two kinds read the same columns as different quantities."
        )
    kind = str(record[MOTION_TABLE_TYPE_KEY]).strip()
    if kind not in MOTION_TABLE_TYPES:
        return (
            f"{MOTIONS_VARIABLE} record {written} states {MOTION_TABLE_TYPE_KEY}: {kind}; it is "
            f"{' or '.join(MOTION_TABLE_TYPES)}, the solver's own tokens, with the hyphen."
        )
    name = str(record[MOTION_TABLE_KEY]).strip()
    if name in {".", ".."} or PurePath(name).name != name or "\\" in name or "/" in name:
        return (
            f"{MOTIONS_VARIABLE} record {written} names the table {name!r}, which is not a bare "
            f"file name: a motion table lives in the workspace's inputs/{MOTIONS_DIR}/ folder "
            "and the record names it without a folder part."
        )
    return None


def read_motion_table(text: str, *, source: str) -> list[tuple[float, ...]]:
    """Read and check a motion table: seven finite numbers a row, the time strictly increasing.

    Parameters
    ----------
    text : str
        The file's text.
    source : str
        What the file is, for the message.

    Returns
    -------
    list of tuple of float
        The rows, in the file's order; blank lines are skipped.

    Raises
    ------
    CampaignConfigError
        A row that is not seven numbers, a value that is not finite, a time
        that does not increase, or a file with no row.
    """
    rows: list[tuple[float, ...]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        cells = [cell for cell in _SEPARATOR.split(stripped) if cell]
        try:
            values = tuple(float(cell) for cell in cells)
        except ValueError:
            values = ()
        if len(cells) != MOTION_TABLE_COLUMNS or len(values) != MOTION_TABLE_COLUMNS:
            raise CampaignConfigError(
                f"{source}, line {number} ({stripped!r}): a row of a motion table is "
                f"{MOTION_TABLE_COLUMNS} numbers separated by commas or spaces, the time in "
                "seconds and then three translational and three angular components; the "
                "table has no header line."
            )
        if not all(math.isfinite(value) for value in values):
            raise CampaignConfigError(
                f"{source}, line {number} ({stripped!r}) holds a value that is not finite."
            )
        if rows and values[0] <= rows[-1][0]:
            raise CampaignConfigError(
                f"{source}, line {number}: the time {values[0]:g} s does not increase on "
                f"the row before it ({rows[-1][0]:g} s); the solver interpolates between "
                "rows in time, so each time follows the last."
            )
        rows.append(values)
    if not rows:
        raise CampaignConfigError(f"{source} holds no row.")
    return rows


def refuse_a_table_motion_without_its_clock(case: SimCase) -> None:
    """Refuse a row with a table motion that does not name its clock and its time step.

    A table has no rotation speed to derive a step from, so the row states
    ``CLOCK_MOTION``, naming one of its table motions, and ``DELTA_TIME``.
    """
    if not case.custom_motions:
        return
    aliases = [str(record.get(ROTATION_ALIAS_KEY) or "").strip() for record in case.custom_motions]
    clock = _variable(case, CLOCK_MOTION_VARIABLE)
    missing = [
        key
        for key, absent in (
            (CLOCK_MOTION_VARIABLE, clock is None),
            (DELTA_TIME_VARIABLE, _variable(case, DELTA_TIME_VARIABLE) is None),
        )
        if absent
    ]
    if missing:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states a table motion ({', '.join(aliases)}) and no "
            f"{' and no '.join(missing)}. A table has no rotation speed to derive a time step "
            f"from, so the row names the motion that owns its clock "
            f"('{CLOCK_MOTION_VARIABLE}: <alias>') and states its step "
            f"('{DELTA_TIME_VARIABLE}: <seconds>')."
        )
    assert clock is not None  # missing is empty
    if not any(clock.strip().casefold() == alias.casefold() for alias in aliases):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {CLOCK_MOTION_VARIABLE}: {clock}, which is not a "
            f"table motion of the row; name one of {', '.join(aliases)}."
        )


def emit_custom_motions(case: SimCase, script: Script, stepping: TimeStepping) -> None:
    """Emit each table motion of the row, every table checked before the first line.

    Per record, in the setup phase before the solver is initialised:
    ``CREATE_NEW_MOTION CUSTOM``, ``SET_MOTION_CUSTOM_TABLE <TYPE> <motion id>``
    with the point's copy of the table on its own line, and
    ``SET_MOTION_BOUNDARIES`` with the boundaries of the record's alias.

    Raises
    ------
    CampaignConfigError
        A record not in its form or not bound to its file, a table changed
        since the row was planned, not in its form, or ending before the run
        does, or an alias that names no boundary of the geometry.
    """
    if not case.custom_motions:
        return
    end_s = stepping.time_iterations * stepping.delta_time_s
    labels = script.entities.labels("boundaries")
    planned: list[tuple[dict[str, str], bytes, list[int]]] = []
    for record in case.custom_motions:
        refusal = custom_motion_record_refusal(record)
        if refusal is not None:
            raise CampaignConfigError(f"case {case.sim_id!r}: {refusal}")
        payload = _the_bound_table(case, record)
        source = f"the motion table {record[MOTION_TABLE_KEY]} of {written_record(record)}"
        rows = read_motion_table(payload.decode("utf-8", errors="replace"), source=source)
        # A table written to the run's end in decimal meets the step product's
        # rounding, so the end is compared to one part in a billion.
        if rows[-1][0] < end_s * (1.0 - 1e-9):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: {source} ends at {rows[-1][0]:g} s and the run at "
                f"{end_s:g} s ({stepping.time_iterations} steps of {stepping.delta_time_s:g} "
                "s); the table covers the whole run, so extend it or shorten the run."
            )
        planned.append((record, payload, _the_boundaries_it_moves(case, record, labels)))
    for record, payload, boundaries in planned:
        name = f"{PurePath(record[MOTION_TABLE_KEY].strip()).stem}{MOTION_TABLE_COPY_SUFFIX}"
        script.park_input_file(name, payload)
        copy = name if script.working_dir is None else str(PurePath(script.working_dir) / name)
        script.emit("CREATE_NEW_MOTION", "CUSTOM")
        motion = script.num_motions
        script.emit("SET_MOTION_CUSTOM_TABLE", record[MOTION_TABLE_TYPE_KEY].strip(), motion, copy)
        script.emit("SET_MOTION_BOUNDARIES", motion, len(boundaries), boundaries)


def _the_bound_table(case: SimCase, record: Mapping[str, str]) -> bytes:
    """Return the bytes of a record's table, refusing one unbound or changed since the plan."""
    written = written_record(record)
    path = record.get(MOTION_TABLE_PATH_KEY)
    if not path:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {MOTIONS_VARIABLE} record {written} carries no resolved "
            f"table. A matrix row's table is resolved against the workspace's "
            f"inputs/{MOTIONS_DIR}/ when the row binds; a case built in Python sets "
            f"{MOTION_TABLE_PATH_KEY} and {MOTION_TABLE_SHA256_KEY} on the record."
        )
    table = Path(path)
    if not table.is_file():
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the motion table {table} of {written} is no longer present."
        )
    planned = record.get(MOTION_TABLE_SHA256_KEY)
    if planned and file_sha256(table) != planned:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the motion table {table} of {written} changed after the "
            "row was planned; plan the row again so the record names the bytes the solver reads."
        )
    return table.read_bytes()


def _the_boundaries_it_moves(
    case: SimCase, record: Mapping[str, str], labels: Mapping[str, int]
) -> list[int]:
    """Resolve the record's alias to the boundary indices it moves, refusing one naming none."""
    alias = record[ROTATION_ALIAS_KEY].strip()
    if not labels:
        _refuse_name_without_inventory(case, MOTIONS_VARIABLE, alias)
    found: Sequence[int] = _resolve_token(case, alias, labels)
    if not found:
        _refuse_name_absent_from_inventory(case, MOTIONS_VARIABLE, alias, labels)
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {alias} names no boundary of {_declared_labels(labels)}."
        )
    return sorted(set(found))


def resolve_motion_tables(
    inputs_dir: str | Path, records: Sequence[Mapping[str, str]], *, pol: str, workflow: str
) -> list[dict[str, str]]:
    """Resolve and check each table motion's file, recording its path and SHA-256, when it binds.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace's input library, whose ``motions/`` folder holds the tables.
    records : sequence of mapping
        The row's table motion records, as the matrix read them.
    pol : str
        The row's POL, for the message.
    workflow : str
        The row's run type; a table motion is emitted on ``unsteady`` only.

    Returns
    -------
    list of dict
        Each record with ``TABLE_PATH`` and ``TABLE_SHA256`` added.

    Raises
    ------
    InputArtifactError
        Naming the record: a table motion on another run type, and a table
        missing, empty, outside ``inputs/motions/`` or not in its form. The
        file is read and never rewritten.
    """
    folder = (Path(inputs_dir) / MOTIONS_DIR).resolve()
    bound: list[dict[str, str]] = []
    for record in records:
        written = written_record(record)
        name = str(record.get(MOTION_TABLE_KEY) or "").strip()
        if workflow != "unsteady":
            raise InputArtifactError(
                f"matrix row POL {pol}: {MOTIONS_VARIABLE} record {written} is a table motion "
                f"and the row names the run type {workflow or 'steady'!r}. A table motion is "
                "emitted on the unsteady run type, whose row states its time step.",
                kind="motions",
                artifact_id=name,
            )
        table = (folder / name).resolve()
        if not table.is_relative_to(folder) or not table.is_file() or not table.stat().st_size:
            raise InputArtifactError(
                f"matrix row POL {pol}: {MOTIONS_VARIABLE} record {written} names the table "
                f"{name!r}, which is missing, empty or outside inputs/{MOTIONS_DIR}/. A motion "
                f"table lives in the workspace's inputs/{MOTIONS_DIR}/ folder.",
                kind="motions",
                artifact_id=name,
            )
        try:
            read_motion_table(
                table.read_text(encoding="utf-8", errors="replace"),
                source=f"the motion table {name} of {written}",
            )
        except CampaignConfigError as error:
            raise InputArtifactError(
                f"matrix row POL {pol}: {error}", kind="motions", artifact_id=name
            ) from None
        bound.append(
            {
                **record,
                MOTION_TABLE_PATH_KEY: str(table),
                MOTION_TABLE_SHA256_KEY: file_sha256(table),
            }
        )
    return bound


def bind_motion_tables(case: SimCase, inputs_dir: str | Path) -> SimCase:
    """Return the case with its table motions bound to their files (:func:`resolve_motion_tables`).

    A case with no table motion is returned as it is.
    """
    if not case.custom_motions:
        return case
    bound = resolve_motion_tables(
        inputs_dir,
        case.custom_motions,
        pol=case.sim_id,
        workflow=str(declared_run_type(case) or ""),
    )
    return case.model_copy(update={"custom_motions": bound})
