"""Matrix column layouts, shared declarations and cell grammar."""

from __future__ import annotations

import re
from collections.abc import Mapping

from pyflightstream._errors import PyflightstreamError
from pyflightstream._tokens import NOT_APPLICABLE
from pyflightstream.cases import InputKey
from pyflightstream.cases.workflows import ROW_KEY_MEANINGS, WALLTIME_UNITS_GLOSS, WALLTIME_VARIABLE

#: The verified layout, in file order, since v0.17.0. ``WORKFLOW`` sits
#: SECOND FROM LAST, in front of ``VAR_NAMES_VALUES`` rather than after
#: it, and the position is stated rather than appended:
#: ``VAR_NAMES_VALUES`` is the only cell whose content is free and whose
#: width is not fixed by the format, so it stays last and every
#: fixed-width column stays in front of it.
#:
#: SIX COLUMNS ARRIVED AT 0.17.0 and the rule that let them in is one
#: sentence: A KEY EVERY ROW MUST ANSWER EARNS A COLUMN; A KEY
#: CONDITIONAL ON THE RUN TYPE OR THE MACHINE STAYS IN THE FREE CELL.
#: That is why ``GEOMETRY`` and ``SYMMETRY`` left the free cell, why
#: ``NCPUS`` and ``SYMMETRY_LOADS`` left the SETUP artifact, why
#: ``WALLTIME`` and ``CONFIGURATION`` are new here, and why ``COLD_START``
#: and ``RESTART`` did not come with them.
#:
#: ``HIDDEN`` and ``RUN`` moved to the FRONT, straight after ``POL``. They
#: are not new and their meaning is unchanged; what changed is that the
#: two cells deciding whether a row runs at all are now the first thing
#: read, instead of sitting between ``FS_BUILD`` and ``WORKFLOW`` at the
#: right-hand end of a wide line where a row switched off was easy to
#: miss.
#:
#: The order after those three is what the row IS (aircraft,
#: configuration, description), what it FLIES (condition, sweep), what it
#: CITES (geometry and the three input artifacts), how it SOLVES
#: (symmetry, symmetry loads, processors, wall clock, build), and what
#: BUILDS it (workflow, free cell).
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
#: order, for the generated input glossary ``INPUTS.md`` (G08 of 0.27.0). A
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
        "steady, unsteady, unsteady_rotor or LEGACY",
    ),
    "VAR_NAMES_VALUES": InputKey(
        "The row's own keys, the ones its run type reads; see the table of row keys.",
        "KEY: value pairs separated by /",
    ),
}

#: The layout of v0.15.0 to v0.16.0, frozen as a literal for the same
#: reason the three older ones are: it is RECOGNISED and converted,
#: never read. At 0.17.0 it GAINED SIX COLUMNS and MOVED TWO. What each new
#: column costs a file already written is nothing it cannot derive: ``GEOMETRY`` and ``SYMMETRY``
#: come out of that row's own free cell, ``NCPUS`` and
#: ``SYMMETRY_LOADS`` come from the setup artifact the row cites,
#: ``WALLTIME`` is written ``-`` because no earlier row could state one,
#: and ``CONFIGURATION`` is the ONE column nothing implies, so the
#: upgrade leaves it empty rather than inventing a label.
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

#: The six that arrived at 0.17.0, and WHAT THE UPGRADE WRITES IN EACH.
#:
#: Read as: column -> what the converter puts there for a row written
#: before 0.17.0. Two of them used to be described by where the FACT used
#: to live, which read as a promise that the converter goes and fetches it;
#: it does not, it has no workspace, and it writes the unstated cell (the interface
#: lens, 2026-09-13). Where the older home still answers, this says so,
#: because that is what makes the dash safe rather than lossy.
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

#: The cell a column uses when the row states nothing. It is a visible token
#: rather than an empty cell so a reader can tell "stated nothing" from "the
#: line is truncated", which an empty cell at the end of a run of them cannot.
#:
#: The written token is `NA`, shared for no value. It replaces `-`.
#: This ended a split this package carried in five places: the CSV products wrote `NA` through
#: one funnel while this cell,
#: the printed plan and cost table, and three QA report tables each wrote a
#: dash. One idea, two tokens, and a reader comparing two files had to
#: know which convention each followed. The token itself now lives at
#: :data:`pyflightstream._tokens.NOT_APPLICABLE`, below every layer, because
#: `qa` cannot import `post` and must not learn to.
#:
#: **EVERY EXISTING MATRIX STILL BINDS.** This constant is what the
#: package WRITES; :data:`UNSTATED_CELLS` is what it ACCEPTS, and the dash is
#: still in it. Converging the read side would have made the package refuse the
#: campaigns it exists to run, violating backwards compatibility.
UNSTATED_CELL = NOT_APPLICABLE

#: Every spelling of "this row states nothing" that a matrix may be READ with.
#:
#: THE WRITE SIDE CONVERGED AND THE READ SIDE DID NOT, deliberately. `-` is what
#: every matrix written before 0.23.0 carries, and an empty cell has always been
#: accepted. A reader that took only the current token would refuse files this
#: package itself produced one release ago.
UNSTATED_CELLS: tuple[str, ...] = ("", "-", NOT_APPLICABLE)

#: The six columns of 0.17.0, every one of which MAY read ``-``.
#:
#: Kept as a named tuple rather than inlined because two places read it:
#: the fold that puts a column into the row's variables, and the upgrade
#: that writes a dash where a converted file has nothing to say.
COLUMNS_THAT_MAY_BE_UNSTATED = (
    "CONFIGURATION",
    "GEOMETRY",
    "SYMMETRY",
    "SYMMETRY_LOADS",
    "NCPUS",
    "WALLTIME",
)

#: The layout of v0.11.0 to v0.14.0, frozen as a literal for the same
#: reason the three older ones are: it is RECOGNISED and refused naming
#: the converter, never read. At 0.15.0 it LOST ``SWEEP_TYPE`` (FR-69,
#: the rule of 2026-09-10): the swept variable is the key of
#: ``FLIGHT_CONDITION`` whose value is the word ``sweep``, so the cell
#: already says which variable varies and a column naming it a second
#: time is a second home for one fact.
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

#: The layout of v0.9.0 to v0.10.1, frozen as a literal for the same
#: reason the two older ones are: it is RECOGNISED and refused naming
#: the converter, never read. At 0.11.0 it LOST ONE AND RENAMED ONE
#: (PFS-2029.04, PFS-2029.07.02): ``FS_SCRIPT`` went, because a row that
#: names a registered run type in WORKFLOW names its builder already and
#: a LEGACY row carries its recipe code as the ``RECIPE`` key of its own
#: variables; and ``ENTRY`` became ``PPROC``, because the artifact it
#: names became the post-processing artifact, whose ids begin with p.
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

#: The variables key a LEGACY row carries its recipe code under since
#: 0.11.0, where the FS_SCRIPT column went (PFS-2029.04). Written by the
#: upgrade from the column's cell and read back into ``script_code``, so
#: a LEGACY row's ``--recipe CODE=...`` still finds its code.
RECIPE_VARIABLE = "RECIPE"

#: The shape of a recipe REFERENCE as opposed to a recipe CODE: a dotted
#: module path, a colon, a function name. A RECIPE cell carrying this shape
#: is the reference itself and needs no mapping (PFS-2031.11); a bare code
#: such as ``003`` is mapped by ``recipes`` or refused.
_RECIPE_REFERENCE = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*:[A-Za-z_][\w]*$")

#: The width that preceded ``WORKFLOW``, frozen so a file written under
#: it is RECOGNISED and refused with the command that fixes it instead of
#: meeting the generic "this is not a run matrix" message. It is only
#: ever COMPARED: no row is ever read through it, so the reader keeps its
#: single-grammar property and gains no tolerant second path.
#:
#: WRITTEN OUT IN FULL as of PFS-2027.01, and that is the point rather
#: than verbosity. It used to be derived as ``_COLUMNS`` minus
#: ``WORKFLOW``, which was correct exactly while the only difference
#: between the two layouts was that one column. The moment ``_COLUMNS``
#: lost ``RE`` and ``MACH``, a derived legacy shape would have silently
#: FOLLOWED the change and stopped describing any file that ever
#: existed, so the recognition message would have vanished for the files
#: it was written for. A frozen historical layout must be a literal.
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

#: The v0.8.0 and v0.8.1 layout: the 15 above plus ``WORKFLOW``. Frozen
#: for the same reason and recognised the same way (PFS-2027.01).
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

#: The workflow every row written before the column existed asks for:
#: the established matrix behaviour, whose builder is the user's own
#: recipe. It is deliberately NOT a registered workflow; it means "no
#: workflow", which is what keeps every matrix written before v0.8.0
#: running exactly as it always ran. Spelled here as well as in
#: :mod:`pyflightstream.cases.workflows` because the two modules meet
#: only through the file format, and neither owns the other's constant.
LEGACY_WORKFLOW = "LEGACY"


class MatrixError(PyflightstreamError, ValueError):
    """A run-matrix file does not match the verified layout.

    The reader supports exactly the verified format (FR-10); a
    deviation means the file is not a run matrix or was edited
    beyond what the matrix workflow produces.
    """


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
    """Put the six columns of 0.17.0 where the run types already look.

    THE COLUMN IS THE SOURCE OF TRUTH and the variables mapping is the
    internal one. A row that states the same fact in both is REFUSED
    rather than resolved by precedence: a precedence rule is a second
    thing to know, and the whole reason these six became columns is that
    a mandatory key in a free cell is a key that gets forgotten.

    A column reading :data:`UNSTATED_CELL` states nothing and contributes
    nothing, which is how a row says it wants the default.

    NO COLUMN IS MANDATORY, and the first draft of this function made four
    of them so. That was an invention: measured against the fixtures before
    the change, ``workflow_rotor_matrix.fs`` row 7001 is an
    ``unsteady_rotor`` row that has never stated a geometry, and all eight
    rows of ``matrix.fs`` are LEGACY rows built by a recipe that opens what
    it opens. This release moves WHERE a fact lives; it does not make a
    fact required that was optional, and a column that refused what the
    free cell allowed would refuse files that run today.
    """
    for column in ("GEOMETRY", "SYMMETRY", "SYMMETRY_LOADS", "NCPUS", "WALLTIME", "CONFIGURATION"):
        cell = str(record.get(column, "")).strip()
        if column in variables and cell not in UNSTATED_CELLS:
            raise MatrixError(
                f"matrix row POL {pol}: {column} is stated twice, in its own column as "
                f"{cell!r} and in VAR_NAMES_VALUES as {variables[column]!r}. Since "
                f"v0.17.0 {column} is a COLUMN; take it out of the free cell. One fact, "
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
        # A KEY STATED TWICE IS REFUSED, NOT RESOLVED BY ITS POSITION. Assigning
        # into the dict kept the last one in silence, so `RPM:1000/RPM:2000` ran
        # at 2000 and nothing said a second value had been written. Two that
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
