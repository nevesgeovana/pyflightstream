"""Matrix column layouts, shared declarations and cell grammar."""

from __future__ import annotations

import re
from collections.abc import Mapping

from pyflightstream._errors import PyflightstreamError
from pyflightstream._tokens import NOT_APPLICABLE
from pyflightstream.cases import InputKey
from pyflightstream.cases.workflows import ROW_KEY_MEANINGS, WALLTIME_UNITS_GLOSS, WALLTIME_VARIABLE

#: The current layout, in file order. WORKFLOW is second from last and
#: VAR_NAMES_VALUES is last because its free-form content has no fixed width.
#: Keys every row answers have columns; keys conditional on the run type or
#: machine stay in the free cell. HIDDEN and RUN follow POL so the switches
#: that decide whether a row runs are visible before its other inputs.
_COLUMNS = (
    "POL",
    "HIDDEN",
    "RUN",
    "AIRCRAFT",
    "CONFIGURATION",
    "DESCRIPTION",
    "FLIGHT_CONDITION",
    "SWEEP_VALUES",
    "GEOMETRY",
    "REF",
    "SET",
    "PPROC",
    "SYMMETRY",
    "SYMMETRY_LOADS",
    "NCPUS",
    "WALLTIME",
    "FS_BUILD",
    "WORKFLOW",
    "VAR_NAMES_VALUES",
)

#: WHAT EACH COLUMN SETS, one entry per column of the layout above and in its
#: order, for the generated input glossary ``INPUTS.md`` (G08). A
#: column added to the layout without an entry here is a row of the glossary
#: with no meaning, which its test refuses.
COLUMN_MEANINGS: Mapping[str, InputKey] = {
    "POL": InputKey(
        "The row's identifier: the simulation id its points are recorded and named under.",
        "an id, unique in the matrix",
    ),
    "HIDDEN": InputKey("Whether the solver runs without its window.", "1 is hidden"),
    "RUN": InputKey("Whether the row runs at all; only a row reading 1 is active.", "an integer"),
    "AIRCRAFT": InputKey("The configuration's name.", "text"),
    "CONFIGURATION": InputKey(
        "The user's own label for the configuration; it configures nothing.", "text"
    ),
    "DESCRIPTION": InputKey("Free text about the row.", "text"),
    "FLIGHT_CONDITION": InputKey(
        "The flow condition and the attitude of every point: the keys given decide "
        "which quantity is solved for, and the swept key carries the word sweep.",
        "KEY:value pairs, comma separated; see the table below",
    ),
    "SWEEP_VALUES": InputKey(
        "The values of the key the FLIGHT_CONDITION cell sweeps, one point each.",
        "numbers, comma separated",
    ),
    "GEOMETRY": InputKey(
        "The geometry the row opens, a file of inputs/geometries/.",
        "a file name with its extension",
        "OPEN, IMPORT",
    ),
    "REF": InputKey(
        "The reference artifact the row's lengths, frames, rotors and discs come from.",
        "an id of inputs/references/",
    ),
    "SET": InputKey(
        "The setup artifact the row's solver settings come from.",
        "an id of inputs/setups/",
    ),
    "PPROC": InputKey(
        "The post-processing artifact the row's sections, plots, probes, exports and "
        "products come from.",
        "an id of inputs/pproc/",
    ),
    "SYMMETRY": InputKey(
        "The symmetry the solver is initialized under, which states what was meshed.",
        "NONE, MIRROR or PERIODIC",
        "INITIALIZE_SOLVER",
    ),
    "SYMMETRY_LOADS": InputKey(
        "Whether the reported loads are the meshed sector's or the whole wheel's.",
        "true or false",
        "SET_ANALYSIS_SYMMETRY_LOADS",
    ),
    "NCPUS": InputKey(
        "The processor count: the solver's thread count and, on a cluster, the scheduler's ncpus.",
        "a count",
        "SET_MAX_PARALLEL_THREADS",
    ),
    "WALLTIME": InputKey(
        "The wall clock the row asks for: the scheduler's limit on a cluster, and what "
        "the watchdog counts down on an unsteady row.",
        f"a number and its unit, {WALLTIME_UNITS_GLOSS}, as 240m or 4h",
        unscripted=ROW_KEY_MEANINGS[WALLTIME_VARIABLE].unscripted,
    ),
    "FS_BUILD": InputKey(
        "The solver build the row runs on, as inputs/executables.toml names it.",
        "a build identifier",
    ),
    "WORKFLOW": InputKey(
        "The run type that builds the row's script, or LEGACY for a row a recipe of "
        "the user builds.",
        "steady, unsteady, unsteady_rotor, qsteady_rotor or LEGACY",
    ),
    "VAR_NAMES_VALUES": InputKey(
        "The row's own keys, the ones its run type reads; see the table of row keys.",
        "KEY: value pairs separated by /",
    ),
}

#: The legacy thirteen-column layout, recognized for conversion rather than
#: read as current. Conversion extracts GEOMETRY and SYMMETRY from the free
#: cell. NCPUS and SYMMETRY_LOADS remain available through the cited setup;
#: the converter itself has no workspace and writes their unstated token.
#: WALLTIME and CONFIGURATION are also unstated because the row implies neither.
_LAYOUT_0_15_0 = (
    "POL",
    "AIRCRAFT",
    "DESCRIPTION",
    "FLIGHT_CONDITION",
    "SWEEP_VALUES",
    "REF",
    "SET",
    "PPROC",
    "FS_BUILD",
    "HIDDEN",
    "RUN",
    "WORKFLOW",
    "VAR_NAMES_VALUES",
)

#: What the converter writes into each of the six dedicated columns.
#: It has no workspace and does not fetch setup values. Where the setup remains
#: a fallback, the description explains why writing an unstated cell is lossless.
COLUMNS_NEW_AT_0_17_0 = {
    "CONFIGURATION": "nothing implies it; the upgrade writes the unstated cell",
    "GEOMETRY": "the row's own GEOMETRY key, out of the free cell",
    "SYMMETRY": "the row's own SYMMETRY key, out of the free cell",
    "SYMMETRY_LOADS": (
        "the unstated cell; the cited setup's symmetry_loads is still read, so nothing is lost"
    ),
    "NCPUS": (
        "the unstated cell; the cited setup's max_parallel_threads is still read, "
        "so nothing is lost"
    ),
    "WALLTIME": "no earlier row could state one, so it is written as the unstated cell",
}

#: The visible token a column writes when the row states nothing.
#: A visible token distinguishes an unstated value from a truncated line.
#: All product writers share pyflightstream._tokens.NOT_APPLICABLE, below
#: every layer. This is the write token; UNSTATED_CELLS separately defines
#: the accepted spellings, including a dash and an empty cell.
UNSTATED_CELL = NOT_APPLICABLE

#: Every accepted spelling of an unstated matrix value. Readers accept a
#: dash and an empty cell as well as the shared write token, preserving
#: compatibility with matrices that use either spelling.
UNSTATED_CELLS: tuple[str, ...] = ("", "-", NOT_APPLICABLE)

#: The six dedicated columns that may read the unstated token.
#: The reader and converter share this tuple so their optional-column
#: rules agree.
COLUMNS_THAT_MAY_BE_UNSTATED = (
    "CONFIGURATION",
    "GEOMETRY",
    "SYMMETRY",
    "SYMMETRY_LOADS",
    "NCPUS",
    "WALLTIME",
)

#: The legacy layout carrying SWEEP_TYPE, recognized and refused with the
#: converter named. In the current layout the FLIGHT_CONDITION key whose
#: value is sweep already identifies the swept variable (FR-69).
_LAYOUT_0_11_0 = (
    "POL",
    "AIRCRAFT",
    "DESCRIPTION",
    "FLIGHT_CONDITION",
    "SWEEP_TYPE",
    "SWEEP_VALUES",
    "REF",
    "SET",
    "PPROC",
    "FS_BUILD",
    "HIDDEN",
    "RUN",
    "WORKFLOW",
    "VAR_NAMES_VALUES",
)

#: The legacy layout carrying FS_SCRIPT and ENTRY, recognized and refused
#: with the converter named (PFS-2029.04, PFS-2029.07.02). Registered WORKFLOW
#: values select their builders; LEGACY rows carry a RECIPE variable. PPROC
#: identifies the post-processing artifact.
_LAYOUT_0_9_0 = (
    "POL",
    "AIRCRAFT",
    "DESCRIPTION",
    "FLIGHT_CONDITION",
    "SWEEP_TYPE",
    "SWEEP_VALUES",
    "REF",
    "SET",
    "ENTRY",
    "FS_SCRIPT",
    "FS_BUILD",
    "HIDDEN",
    "RUN",
    "WORKFLOW",
    "VAR_NAMES_VALUES",
)

#: The variables key holding a LEGACY row's recipe code (PFS-2029.04).
#: Conversion copies the FS_SCRIPT cell here; reading supplies script_code
#: so --recipe CODE=... resolves the row's recipe.
RECIPE_VARIABLE = "RECIPE"

#: The shape of a recipe REFERENCE as opposed to a recipe CODE: a dotted
#: module path, a colon, a function name. A RECIPE cell carrying this shape
#: is the reference itself and needs no mapping (PFS-2031.11); a bare code
#: such as ``003`` is mapped by ``recipes`` or refused.
_RECIPE_REFERENCE = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*:[A-Za-z_][\w]*$")

#: The frozen fifteen-column legacy layout without WORKFLOW.
#: It is compared for recognition and refused with the conversion command,
#: never read as a current row. A literal tuple keeps recognition independent
#: of changes to the current column list (PFS-2027.01).
_LEGACY_COLUMNS_15 = (
    "POL",
    "AIRCRAFT",
    "DESCRIPTION",
    "RE",
    "MACH",
    "SWEEP_TYPE",
    "SWEEP_VALUES",
    "REF",
    "SET",
    "ENTRY",
    "FS_SCRIPT",
    "FS_BUILD",
    "HIDDEN",
    "RUN",
    "VAR_NAMES_VALUES",
)

#: The frozen sixteen-column legacy layout: the fifteen-column form plus
#: WORKFLOW. It is recognized without being read as current (PFS-2027.01).
_LEGACY_COLUMNS_16 = (
    "POL",
    "AIRCRAFT",
    "DESCRIPTION",
    "RE",
    "MACH",
    "SWEEP_TYPE",
    "SWEEP_VALUES",
    "REF",
    "SET",
    "ENTRY",
    "FS_SCRIPT",
    "FS_BUILD",
    "HIDDEN",
    "RUN",
    "WORKFLOW",
    "VAR_NAMES_VALUES",
)

#: Current file-order columns, shared by matrix and workbook writers.
MATRIX_COLUMNS = _COLUMNS

#: Current and historical headers that tools can recognize without reinterpreting
#: a legacy row as current. The matrix reader still requires the current layout;
#: migration and byte-preserving workbook synchronization use the frozen tuples.
RECOGNIZED_MATRIX_LAYOUTS = (
    _COLUMNS,
    _LAYOUT_0_9_0,
    _LAYOUT_0_11_0,
    _LAYOUT_0_15_0,
    _LEGACY_COLUMNS_15,
    _LEGACY_COLUMNS_16,
)

#: The workflow assigned when a converted layout has no WORKFLOW column.
#: LEGACY selects the user's recipe rather than a registered builder.
#: The workflows module shares the spelling through the file-format contract;
#: neither module owns the other's constant.
LEGACY_WORKFLOW = "LEGACY"


class MatrixError(PyflightstreamError, ValueError):
    """A run-matrix file does not match the verified layout.

    The reader supports exactly the verified format (FR-10); a
    deviation means the file is not a run matrix or was edited
    beyond what the matrix workflow produces.
    """


MatrixError.__module__ = "pyflightstream.cases.matrix"


#: The columns whose cells carry an input-library id, in file order.
#: These are the three the kind-letter rule renames (PFS-2009.03); every
#: other column names something that is not a library artifact.
CODE_COLUMNS = ("REF", "SET", "PPROC")


#: Matrix variable naming the files a row's recipe exports, several
#: separated by commas. NOT by the slash: the slash already separates
#: the KEY:VALUE pairs of VAR_NAMES_VALUES, so a slash inside a value
#: splits the variable itself. Comma is what SWEEP_VALUES already uses
#: to separate values within one group.
OUTPUTS_VARIABLE = "OUTPUTS"


def _split_outside_braces(text: str, separator: str) -> list[str]:
    """Split on ``separator`` at brace depth zero, so a record list stays whole."""
    parts: list[str] = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(depth - 1, 0)
        elif character == separator and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _fold_columns_into_variables(
    record: Mapping[str, str], variables: dict[str, str], pol: str
) -> dict[str, str]:
    """Put the six dedicated columns into the run types' internal variables mapping.

    THE COLUMN IS THE SOURCE OF TRUTH and the variables mapping is the
    internal one. A row that states the same fact in both is REFUSED
    rather than resolved by precedence: a precedence rule is a second
    thing to know, and the whole reason these six became columns is that
    a mandatory key in a free cell is a key that gets forgotten.

    A column reading :data:`UNSTATED_CELL` states nothing and contributes
    nothing, which is how a row says it wants the default.

    No column is mandatory. For example, ``workflow_rotor_matrix.fs`` row
    7001 states no geometry, and the eight LEGACY rows of ``matrix.fs`` use
    recipes that open their own inputs. A dedicated column changes where a
    value is stated, not whether that value is required.
    """
    for column in ("GEOMETRY", "SYMMETRY", "SYMMETRY_LOADS", "NCPUS", "WALLTIME", "CONFIGURATION"):
        cell = str(record.get(column, "")).strip()
        if column in variables and cell not in UNSTATED_CELLS:
            raise MatrixError(
                f"matrix row POL {pol}: {column} is stated twice, in its own column as "
                f"{cell!r} and in VAR_NAMES_VALUES as {variables[column]!r}. "
                f"{column} is a COLUMN; take it out of the free cell. One fact, "
                "one home."
            )
        if cell in UNSTATED_CELLS:
            continue
        variables[column] = cell
    return variables


def _parse_variables(cell: str) -> dict[str, str]:
    """Read the flat ``KEY: value`` pairs of one cell; a record list stays as text."""
    variables: dict[str, str] = {}
    if not cell.strip():
        return variables
    for pair in _split_outside_braces(cell, "/"):
        name, separator, value = pair.partition(":")
        if not separator:
            raise MatrixError(
                f"variable {pair.strip()!r} is not a KEY:VALUE pair; VAR_NAMES_VALUES "
                "holds '/'-separated KEY:VALUE entries"
            )
        key = name.strip()
        # A KEY STATED TWICE IS REFUSED, NOT RESOLVED BY ITS POSITION. A plain
        # dict assignment would silently keep the second value in RPM:1000/RPM:2000.
        # Two that
        # agree are refused as well: the rule is about the declaration, and an
        # agreeing pair is the state the next edit of one of them breaks.
        if key in variables:
            raise MatrixError(
                f"variable {key!r} is stated twice in one VAR_NAMES_VALUES cell, as "
                f"{variables[key]!r} and as {value.strip()!r}. A cell states each key "
                "once; keep the value the row means and remove the other."
            )
        variables[key] = value.strip()
    return variables


def _parse_records(
    text: str, pol: str, key: str, noun: str, pair_separator: str = "/"
) -> list[dict[str, str]]:
    """Read ``{KEY: value / KEY: value}, {...}`` into records, one ``noun`` each."""
    if text.count("{") != text.count("}") or not text.startswith("{") or not text.endswith("}"):
        raise MatrixError(
            f"POL {pol}: {key} is {text!r}, which is not a list of "
            "brace-closed records; write {KEY: value / KEY: value}, {...}, one pair of "
            f"braces per {noun}."
        )
    records: list[dict[str, str]] = []
    body = text
    while body:
        body = body.lstrip(", ")
        if not body:
            break
        if not body.startswith("{") or "}" not in body:
            raise MatrixError(
                f"POL {pol}: {key} is {text!r}, and {body[:20]!r} is not a "
                "brace-closed record; the records are separated by commas and each one "
                "opens and closes its own braces."
            )
        inner, _, body = body[1:].partition("}")
        if "{" in inner:
            raise MatrixError(
                f"POL {pol}: {key} is {text!r}, and a record opens a brace "
                "inside another; a record holds KEY: value pairs only."
            )
        record: dict[str, str] = {}
        for pair in inner.split(pair_separator):
            if not pair.strip():
                continue
            name, separator, value = pair.partition(":")
            if not separator:
                raise MatrixError(
                    f"POL {pol}: {key} record {pair.strip()!r} is not a KEY: value pair."
                )
            field_name = name.strip()
            if field_name in record:
                raise MatrixError(
                    f"POL {pol}: {key} record {{{inner.strip()}}} states "
                    f"{field_name} twice, and one {noun} has one {field_name}."
                )
            record[field_name] = value.strip()
        if not record:
            raise MatrixError(
                f"POL {pol}: {key} is {text!r}, and one of its records is empty; "
                f"a record holds KEY: value pairs, one {noun} each."
            )
        records.append(record)
    if not records:
        raise MatrixError(
            f"POL {pol}: {key} is {text!r}, which names no record at all; "
            "write {KEY: value / KEY: value}, {...}, one pair of braces per " + f"{noun}."
        )
    return records
