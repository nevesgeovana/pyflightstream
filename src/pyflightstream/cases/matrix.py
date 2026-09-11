"""Pipe-delimited run matrix: the reader and the converter.

Pipeline role: keeps the established run-matrix workflow working
unchanged, forever (BRF-08), and promotes the matrix to a first-class
interface of the file-managed modality (v0.3 decision): reading a
matrix and running it is one call,
:func:`pyflightstream.run.matrix.run_matrix`, with the native
``campaign.toml`` model staying the canonical internal form, so
nothing changes for campaign.toml users. The verified layout is read as
is: POL, AIRCRAFT, DESCRIPTION, FLIGHT_CONDITION, SWEEP_VALUES, REF,
SET, PPROC, FS_BUILD, HIDDEN, RUN, WORKFLOW, VAR_NAMES_VALUES. Rows
with RUN = 1 are active. THE SWEPT VARIABLE IS A KEY OF
FLIGHT_CONDITION: whichever key carries the word ``sweep`` where its
value would be is the one that varies, exactly one may, and
SWEEP_VALUES carries its comma-separated values. Every other key of the
cell is a quantity the row holds at every point of the sweep.
VAR_NAMES_VALUES holds ``/``-separated ``KEY:VALUE`` pairs; values may
contain spaces and escaped newlines (a literal backslash-n sequence),
which are preserved verbatim.

The historical 3-digit codes (REF, SET, ENTRY, FS_SCRIPT) were
resolved to files by number at run time; that import-by-number system
is replaced (PP-7, FR-12): :func:`to_campaign` maps the FS_SCRIPT
code to a registered recipe name through an explicit mapping and
preserves all four codes in the case variables, so the conversion is
lossless. :func:`convert_matrix` (FR-11) emits the native
``campaign.toml`` equivalent; ``REmi`` is stated in millions in the
flight condition and converts to an absolute Reynolds number.

WHAT THIS MODULE DOES NOT DO, and where the rest went. The run path
needs the layer ABOVE this one: binding REF, SET, ENTRY and FS_BUILD to
the workspace input library, then planning and executing. Both halves
used to live here and paid for it with imports written inside the
function bodies, which recorded an upward dependency while hiding it
from every module-level reader. They moved on 2026-08-19 (OPS-2007.01,
PFS-2009.05): :class:`pyflightstream.workspace.matrix.ResolvedMatrix`
and :func:`pyflightstream.workspace.matrix.resolve_matrix` do the
binding, and :func:`pyflightstream.run.matrix.plan_matrix` and
:func:`pyflightstream.run.matrix.run_matrix` do the pre-flight and the
execution. Nothing about the format, the flags or the records moved
with them, and the ``pyfs-matrix`` command line kept its name.

THE LAYOUT HAS BROKEN TWICE, and both breaks are recognised rather than
merely refused.

At 0.8.0 it GREW BY ONE COLUMN (PFS-2025.01, PFS-2025.12). ``WORKFLOW``
names the workflow type a row asks for. It is a column of its own rather
than a pair inside ``VAR_NAMES_VALUES``, because that cell is where the
free CASE DATA lives and a type competing with it would be
indistinguishable from a user's own key.

At 0.9.0 it LOST TWO AND GAINED ONE (PFS-2027.01). ``RE`` and ``MACH``
were removed and ``FLIGHT_CONDITION`` replaced them, so a row states its
whole flow condition in one place and which quantity is solved for
follows from which keys it names. The cell is MANDATORY, exactly as the
two columns it replaced were.

A file written at either preceding width is not merely unparsable:
:func:`read_matrix` RECOGNISES it, says which of the two layouts it is,
and refuses it naming :func:`upgrade_matrix`. That converter runs both
stages, so a file written before 0.8.0 gains the workflow cell AND has
its two numeric columns folded, from one call.

What is left here imports nothing above the cases layer, at any level,
which is what :mod:`tests.test_conventions` now holds it to.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases import (
    ROTATION_OFFSET_KEY,
    ROTATION_SWEEP_KEY,
    Campaign,
    RawCommand,
    SimCase,
    SweepAxis,
    default_outputs,
    multiplied_sweep,
)

# SAME LAYER, so this is a sideways import and not an upward one: both
# modules are `pyflightstream.cases`, and the layer rule
# (`tests.test_conventions`) is about direction. The reader asks the
# registry which types exist rather than keeping a second list, because a
# second list is how a value gets refused for naming a workflow that was
# registered last week.
from pyflightstream.cases.workflows import (
    IGNORE_MISSING_FAMILIES_VARIABLE,
    LOG_OUTPUT_VARIABLE,
    MOTIONS_VARIABLE,
    RAW_BEFORE_KEY,
    RAW_COMMAND_KEY,
    RAW_FILE_KEY,
    RAW_PHASES,
    RAW_VARIABLE,
    ROTATE_VARIABLE,
    ROTATION_ALIAS_KEY,
    ROTATION_FAMILIES_KEY,
    ROTATION_OPTIONAL_KEYS,
    ROTATION_RECORD_KEYS,
    SWEEP_WORD,
    workflow_names,
)

__all__ = [
    "CODE_COLUMNS",
    "DEFAULT_VERSION_OPTION",
    "LEGACY_WORKFLOW",
    "RECIPE_VARIABLE",
    "SWEEP_WORD",
    "MatrixError",
    "MatrixRow",
    "convert_matrix",
    "read_matrix",
    "refuse_silent_rows_without_default",
    "rewrite_codes",
    "to_campaign",
    "upgrade_matrix",
    "workflow_types",
]

#: The verified layout, in file order. ``WORKFLOW`` sits SECOND FROM
#: LAST, in front of ``VAR_NAMES_VALUES`` rather than after it, and the
#: position is stated rather than appended: ``VAR_NAMES_VALUES`` is the only cell
#: whose content is free and whose width is not fixed by the format, so
#: it stays last and every fixed-width column stays in front of it.
_COLUMNS = (
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

#: The workflow every row written before the column existed asks for:
#: the established matrix behaviour, whose builder is the user's own
#: recipe. It is deliberately NOT a registered workflow; it means "no
#: workflow", which is what keeps every matrix written before v0.8.0
#: running exactly as it always ran. Spelled here as well as in
#: :mod:`pyflightstream.cases.workflows` because the two modules meet
#: only through the file format, and neither owns the other's constant.
LEGACY_WORKFLOW = "LEGACY"

# The two rotation keys of VAR_NAMES_VALUES this reader knows about, one
# fixed offset and one geometric sweep, ARE NOT DEFINED HERE. They and the
# one-sweep-per-case limit they carry belong to `pyflightstream.cases`,
# the layer below and the single owner of the decision (PFS-2025.17): a
# second spelling in this module is how a hand-written campaign comes to
# run what the matrix refuses. Both are imported at the top of this file.


class MatrixError(PyflightstreamError, ValueError):
    """A run-matrix file does not match the verified layout.

    The reader supports exactly the verified format (FR-10); a
    deviation means the file is not a run matrix or was edited
    beyond what the matrix workflow produces.
    """


@dataclass(frozen=True)
class MatrixRow:
    """One parsed row of the run matrix.

    Attributes
    ----------
    row_number : int
        Position of the row among the DATA rows of the file, 1-based.
        It counts CONTENT rows after blank lines and the dashed rule
        have been dropped, so it is not a physical line number, and it
        is assigned BEFORE the RUN filter: the number a refusal prints
        names the same row whether or not the row is active, which is
        what makes it usable for finding the cell to edit.
    pol : str
        Polar identifier (POL column); maps to the native ``sim_id``.
    aircraft, description : str
        Configuration name and free text.
    flight_condition : dict
        The FLIGHT_CONDITION cell, parsed to canonical key and float and
        kept in the units the KEYS name (PFS-2027.01). It replaced the
        RE and MACH columns at 0.9.0: a run states its flow condition in
        one place, and which quantity gets solved for follows from which
        keys are present rather than from which columns are mandatory.
        An empty cell is an empty mapping, not a refusal; a row that
        states no condition is legal here and is answered one layer up.
    sweep : SweepAxis
        The sweep, already in native form.
    ref_code, set_code, pproc_code : str
        The library ids the REF, SET and PPROC cells carry.
    script_code : str
        A LEGACY row's recipe code, the ``RECIPE`` key of its variables
        (PFS-2029.04); empty on a row naming a registered run type.
    fs_build : str
        FS_BUILD column, kept verbatim.
    hidden : bool
        HIDDEN column, the windowless-run flag.
    run : int
        Activity flag; rows with 1 are active.
    workflow : str
        WORKFLOW column, the workflow type the row asks for; one of
        :data:`WORKFLOW_TYPES`, checked when the row is read.
    variables : dict
        The KEY:VALUE variables, values kept as strings.
    """

    row_number: int
    pol: str
    aircraft: str
    description: str
    flight_condition: dict[str, float]
    sweep: SweepAxis
    ref_code: str
    set_code: str
    pproc_code: str
    script_code: str
    fs_build: str
    hidden: bool
    run: int
    workflow: str
    variables: dict[str, str]
    #: The rotor motions the cell's ``MOTIONS`` list states, one record
    #: each, in cell order (PFS-2029.11.01); empty for a flat row.
    motions: list[dict[str, str]] = field(default_factory=list)
    #: The mesh rotations the cell's ``ROTATE`` list states, one record
    #: each, in cell order (PFS-2034.02); empty for a row stating none.
    rotations: list[dict[str, str]] = field(default_factory=list)
    #: The raw solver commands the cell's ``RAW`` list states, one record
    #: each, in cell order (FR-67); empty for a row stating none. A record
    #: holds ``COMMAND`` or ``FILE``, never both, and ``BEFORE``.
    raw: list[dict[str, str]] = field(default_factory=list)


#: The CLOSED set of flight-condition keys, each with the unit it is
#: written in and the quantity it constrains (PFS-2027.01).
#:
#: A flight condition is a SET OF CONSTRAINTS on one flow state, and the
#: keys given decide which quantity is solved for. That sentence is the
#: whole design: the same resolver answers ``MACH:0.20, REmi:5.5`` and
#: ``TASmps:68.08, ALTFT:10000, dISA:5`` by solving for a different
#: unknown each time. This table is the vocabulary; the resolving lives
#: one layer up, where a row can reach the reference artifact.
#:
#: WHY THE SET IS CLOSED. An unrecognised key is REFUSED here rather
#: than ignored, which is the difference between a typo that costs a
#: message and a typo that costs a campaign. Extending it later costs
#: one row in this table and no rewrite, which is why the first cut can
#: be narrow without being a trap.
#:
#: THE UNITS RIDE THE KEYS rather than the values, which is why the
#: names are not plain words: ``ALTFT`` is feet, ``dISA`` is Celsius and
#: ``REmi`` is millions. A cell that said ``ALTITUDE:10000`` would be
#: ambiguous between feet and metres in a repository that has already
#: shipped a solver command whose metres argument three builds read as
#: feet.
FLIGHT_CONDITION_KEYS: dict[str, tuple[str, str]] = {
    "MACH": (
        "dimensionless",
        "velocity, through the speed of sound at the state's own temperature",
    ),
    "TASmps": ("m/s", "velocity directly"),
    # The second element is the quantity the key CONSTRAINS, which for
    # REmi is the density alone. It read "density, velocity and reference
    # length over viscosity" until a release review pointed out that this
    # is the DEFINITION of a Reynolds number rather than a constraint, and
    # that read as a constraint list it says REmi pins three things.
    "REmi": ("millions", "density"),
    "ALTFT": ("feet", "pressure, and temperature through the standard lapse"),
    "dISA": ("Celsius, a DELTA", "temperature, as an offset on the standard value"),
    # THE FIVE PINS (FR-54, PFS-2030.02). Each overrides the constant the
    # standard atmosphere would otherwise supply, so a row can state the
    # fluid the reference scripts pinned and the emitted FLUID_PROPERTIES
    # block carries those numbers and no others. The units ride the keys.
    "RHOkgm3": ("kg/m^3", "density directly, overriding both the atmosphere and REmi"),
    "MUPas": ("Pa s", "dynamic viscosity, which REmi then solves the density against"),
    "ASMPS": ("m/s", "sonic velocity, which MACH is then taken against"),
    "TK": ("kelvin", "temperature, stated rather than lapsed"),
    "PPA": ("pascal", "pressure, stated rather than lapsed"),
}

#: THE ATTITUDE KEYS (FR-69, the rule of 2026-09-10), which the same cell
#: carries and which are NOT part of the flow state: they fix where the
#: aircraft points, not what the air is doing, so they are parsed here and
#: never handed to the atmosphere resolver. A row states both on every
#: row, so that no run reaches the solver at an angle nobody wrote; the
#: swept one carries the word `sweep` and the other a number.
#:
#: ADVANCE_RATIO joins them (FR-70): stated here it governs every motion
#: of the row that states no speed of its own.
ATTITUDE_KEYS: dict[str, tuple[str, str]] = {
    "ALPHA": ("degrees", "the incidence of the free stream"),
    "BETA": ("degrees", "the sideslip of the free stream"),
    "ADVANCE_RATIO": ("dimensionless", "the speed of every motion that states none"),
}


#: Canonical spelling by upper-cased key, for the case-insensitive match
#: below. Built from the tables so the three cannot drift apart.
_FLIGHT_CONDITION_CANONICAL = {key.upper(): key for key in (*FLIGHT_CONDITION_KEYS, *ATTITUDE_KEYS)}


def _parse_flight_condition(cell: str, pol: str) -> dict[str, float]:
    """Parse a FLIGHT_CONDITION cell into canonical key to value.

    KEYS ARE MATCHED CASE-INSENSITIVELY and reported in their canonical
    spelling. Stated here rather than left to whichever the first caller
    happened to type, and asserted both ways in the tests.

    The reason is the keys themselves: ``REmi``, ``TASmps`` and ``dISA``
    carry deliberate internal capitals that a user types from memory, so
    refusing ``remi`` as an unknown key would be refusing a correct
    intention on a shift key. The repository's one existing precedent
    for a variable key, the rotation sweep in
    :func:`pyflightstream.cases.geometric_sweep_values`, is also
    case-insensitive.

    A DUPLICATED KEY IS REFUSED rather than last-wins, and the check is
    on the CANONICAL key, so ``MACH:0.2, mach:0.3`` is a duplicate and
    not two keys. Last-wins is what the general ``VAR_NAMES_VALUES``
    parser does beside this one, and it is wrong here for a reason worth
    the difference: those values are free case data a recipe interprets,
    while these are constraints on a flow state, and a silently dropped
    constraint changes what is solved.

    Parameters
    ----------
    cell : str
        The FLIGHT_CONDITION cell, comma-separated ``KEY:value`` pairs.
        An empty cell means the row states no flight condition and is
        returned as an empty mapping rather than refused.
    pol : str
        The row's POL, named in every refusal so the reader knows which
        cell to edit.

    Returns
    -------
    dict
        Canonical key to float value, in the order written.

    Examples
    --------
    >>> _parse_flight_condition("MACH:0.20, REmi:5.5", "P1")
    {'MACH': 0.2, 'REmi': 5.5}
    >>> _parse_flight_condition("TASmps:68.08, ALTFT:10000, dISA:5", "P1")
    {'TASmps': 68.08, 'ALTFT': 10000.0, 'dISA': 5.0}

    Whitespace around the separators and around the colon is accepted:

    >>> _parse_flight_condition("  MACH : 0.20 ,REmi:5.5  ", "P1")
    {'MACH': 0.2, 'REmi': 5.5}
    """
    condition: dict[str, float | str] = {}
    if not cell.strip():
        return condition
    accepted = ", ".join((*FLIGHT_CONDITION_KEYS, *ATTITUDE_KEYS))
    for pair in cell.split(","):
        if not pair.strip():
            raise MatrixError(
                f"FLIGHT_CONDITION of POL {pol} holds an empty entry between commas; "
                f"the cell is comma-separated KEY:value pairs, from {accepted}"
            )
        name, separator, value = pair.partition(":")
        if not separator:
            raise MatrixError(
                f"FLIGHT_CONDITION entry {pair.strip()!r} of POL {pol} is not a "
                f"KEY:value pair; the cell holds comma-separated KEY:value entries, "
                f"from {accepted}"
            )
        key = _FLIGHT_CONDITION_CANONICAL.get(name.strip().upper())
        if key is None:
            raise MatrixError(
                f"FLIGHT_CONDITION key {name.strip()!r} of POL {pol} is not one this "
                f"package knows; the accepted keys are {accepted}. The set is CLOSED "
                "so that a mistyped key costs a message rather than a campaign solved "
                "at a condition nobody asked for."
            )
        if key in condition:
            raise MatrixError(
                f"FLIGHT_CONDITION of POL {pol} names {key} more than once, as "
                f"{condition[key]} and {value.strip()!r}. A repeated key is refused "
                "rather than taking the last one, because these are constraints on "
                "one flow state and a silently dropped constraint changes what is "
                "solved."
            )
        # THE SWEPT KEY CARRIES A WORD (FR-69): the one variable this row
        # varies says so where its value would be, and SWEEP_VALUES holds
        # the values. Every other key carries a number.
        if value.strip().casefold() == SWEEP_WORD.casefold():
            condition[key] = SWEEP_WORD
            continue
        try:
            number = float(value.strip())
        except ValueError:
            units = (FLIGHT_CONDITION_KEYS.get(key) or ATTITUDE_KEYS[key])[0]
            raise MatrixError(
                f"FLIGHT_CONDITION key {key} of POL {pol} carries {value.strip()!r}, "
                f"which is neither a number nor the word {SWEEP_WORD!r}. {key} is in "
                f"{units}."
            ) from None
        # `float()` accepts 'nan' and 'inf', and both would travel all
        # the way into a solved flow state and out into a script without
        # anything downstream refusing them: a NaN density emits as
        # 'nan' and the solver reads whatever it reads. They are not
        # numbers a flow condition can be stated in, so they are refused
        # where every other malformed value is.
        if number != number or number in (float("inf"), float("-inf")):
            raise MatrixError(
                f"FLIGHT_CONDITION key {key} of POL {pol} carries {value.strip()!r}, "
                "which is not a finite number. A flow condition cannot be stated "
                "as a NaN or an infinity, and one would otherwise reach the "
                "emitted script unrefused."
            )
        condition[key] = number
    return condition


def _require_flight_condition(
    cell: str, pol: str, row_number: int, path: str | Path
) -> dict[str, float]:
    """Parse a row's FLIGHT_CONDITION, and refuse an empty one.

    WHY EMPTY IS REFUSED. ``RE`` and ``MACH`` were MANDATORY columns, and
    a blank cell in either was refused by the conversion that read it. The
    flight condition replaced them (PFS-2027.01), so it inherits their
    mandatoriness: letting a row state no flow condition at all would be a
    silent loosening smuggled in by a format change, and the case would
    reach a builder with no velocity, no density and no Reynolds number
    while looking exactly like a working row.

    The grammar function beside this one still answers ``{}`` for an empty
    string, because parsing nothing IS nothing; deciding that a ROW may
    not do that is a different question and belongs here, where the row
    and its number are in hand.
    """
    condition = _parse_flight_condition(cell, pol)
    if not condition:
        raise MatrixError(
            f"data row {row_number} of {path}, POL {pol}, states no FLIGHT_CONDITION. "
            "Every row states its flow condition: the cell replaced the mandatory RE "
            "and MACH columns and is mandatory in the same way, so that a case cannot "
            "reach a solver with no velocity and no density while looking like a "
            f"working row. Write one, for example 'MACH:0.20, REmi:5.5' or "
            "'TASmps:68.08, ALTFT:10000, dISA:5'."
        )
    return condition


def _split_attitude(
    condition: dict[str, float | str],
) -> tuple[dict[str, float], dict[str, object]]:
    """Split a parsed cell into the FLOW STATE and the row's attitude (FR-69, FR-70).

    The same cell carries both since 0.15.0, and they go to different
    readers: the flow state is resolved into density, velocity and
    temperature, and the attitude is what the aircraft is doing in it.
    Handing an angle to the flow resolver would ask it about a key that
    constrains nothing, so the two are separated where the cell is read
    rather than where either is consumed.

    Returns
    -------
    tuple
        ``(state, attitude)``. The state carries numbers only. The
        attitude is keyed by the row's own key names (``ALPHA``,
        ``BETA``, ``ADVANCE_RATIO``) and its values are numbers, or the
        word ``sweep`` for the one key the row varies.
    """
    # THE SWEPT KEY IS NOT A VALUE. Whichever key carries the word, it
    # names the variable that VARIES, and its values are the row's
    # SWEEP_VALUES; the flow state is what the row holds FIXED, so the
    # swept key is left out of it and the resolver never meets a word
    # where it expects a number.
    state = {
        key: float(value)
        for key, value in condition.items()
        if key in FLIGHT_CONDITION_KEYS and value != SWEEP_WORD
    }
    attitude = {key: value for key, value in condition.items() if key in ATTITUDE_KEYS}
    return state, attitude


#: The FLIGHT_CONDITION keys a row may sweep TODAY, to the sweep axis each
#: becomes. The rule licenses ANY key of the cell; what this release
#: implements is the two angles and the ratio, which is what the reference
#: matrices vary. A key outside this map is refused NAMING the set rather
#: than accepted and silently ignored, which is the failure the ratio
#: sweep had before this release (PFS-2035.06, measured 2026-09-10: the
#: axis existed, the point carried it and nothing read it).
_CONDITION_SWEEP_AXES = {
    "ALPHA": "alpha",
    "BETA": "beta",
    "ADVANCE_RATIO": "advance_ratio",
}

#: The FLIGHT_CONDITION keys whose HELD value joins every point of the
#: sweep rather than staying on the row. The two angles and no more: they
#: are the only ones a run tag has ever carried as a held value, through
#: the paired ``AL/BE`` code, and widening the set would rename runs in
#: the other direction. See :attr:`pyflightstream.cases.SweepAxis.held`.
_HELD_POINT_KEYS = ("ALPHA", "BETA")


def _sweep_of_condition(
    condition: dict[str, float | str], sweep_values: str, pol: str
) -> SweepAxis:
    """Build the row's sweep from the key of its condition that carries the word (FR-69).

    PRIVATE for the same reason as ``_split_attitude`` above, and it is
    the one that mattered: it took three POSITIONAL parameters of which
    two were adjacent strings with no unit between them, so swapping them
    was legal and produced a ValueError from ``float`` rather than a
    matrix refusal. It is a seam, called once, from the loop that builds
    a row (the interface and architecture lenses, 2026-09-10).

    The rule of 2026-09-10: a sweep is applied to a variable that DEFINES
    the flight condition, and to exactly ONE variable. The cell says which
    by carrying ``sweep`` where that key's value would be, and
    ``SWEEP_VALUES`` holds the values.

    A row with no swept key, or with two, is refused naming the keys: the
    first would run one point under a column of values nobody reads, and
    the second is the paired sweep this release retires.
    """
    swept = [key for key, value in condition.items() if value == SWEEP_WORD]
    if not swept:
        raise MatrixError(
            f"POL {pol}: no key of FLIGHT_CONDITION carries the word {SWEEP_WORD!r}, so "
            "nothing says which variable this row varies, and SWEEP_VALUES would be a "
            f"column nobody reads. Write {SWEEP_WORD} as the value of the one key that "
            "varies, for example 'MACH:0.2, REmi:5.5, ALPHA:sweep, BETA:0'."
        )
    if len(swept) > 1:
        raise MatrixError(
            f"POL {pol}: {len(swept)} keys of FLIGHT_CONDITION carry the word "
            f"{SWEEP_WORD!r} ({', '.join(swept)}), and a row sweeps ONE variable. Two "
            "swept variables were the paired AL/BE sweep, which this release retires: "
            "write one row per value of the second."
        )
    key = swept[0]
    axis = _CONDITION_SWEEP_AXES.get(key)
    if axis is None:
        raise MatrixError(
            f"POL {pol}: FLIGHT_CONDITION sweeps {key}, which this release cannot vary "
            f"yet. The keys it varies are {', '.join(sorted(_CONDITION_SWEEP_AXES))}. "
            "Every other key of the cell may carry the word in a later release; today "
            "it is refused rather than accepted and ignored."
        )
    values = [float(token) for token in sweep_values.split(",") if token.strip()]
    if not values:
        raise MatrixError(
            f"POL {pol}: FLIGHT_CONDITION sweeps {key} and SWEEP_VALUES holds "
            f"{sweep_values!r}, which is no values at all. Write them there, "
            "comma-separated, for example '0.0,2.0,4.0'. A cell of only separators or "
            "only spaces holds none, which is why this can look wrong to the eye."
        )
    # A HELD ANGLE IS PART OF THE POINT, which is what keeps the upgrade
    # from renaming a run: `AL/BE` over `-4,0,4/0` tagged its points
    # `a-04.0_b+00.0`, and the same row spelled `ALPHA:sweep, BETA:0.0`
    # tags them the same way. The reasoning is on `SweepAxis.held`.
    held = {
        _CONDITION_SWEEP_AXES[name]: float(value)
        for name, value in condition.items()
        if name in _HELD_POINT_KEYS and value != SWEEP_WORD
    }
    return SweepAxis(type=axis, values=values, held=held)


#: ``MOTIONS_VARIABLE``, the one ``VAR_NAMES_VALUES`` key whose value is a
#: LIST OF RECORDS (PFS-2029.11.01), is imported above from
#: :mod:`pyflightstream.cases.workflows`, its home since 0.13.0 beside
#: the other cell keys, so the rotor run type can register it
#: (PFS-2008.02.01); this module keeps the published name and reads the
#: list into :attr:`MatrixRow.motions`.

#: The keys a motion record may carry, and which a row may not state flat
#: beside a ``MOTIONS`` list, because two statements of one rotor's speed
#: or hub cannot both be the one the script obeys.
MOTION_RECORD_KEYS = (
    # FR-61, the design of 2026-09-10: the rotor's identity, and since
    # 0.15.0 the only one a row states. FOUR of the keys below it are what
    # the reference now says once, REFUSED since 0.15.0 naming the
    # replacement, and refused a second way in the same record as this
    # one: MOVING_BOUNDARIES,
    # ROTOR_AXIS, ROTOR_ORIGIN and RPM_SIGN, with BLADES a fifth further
    # down the tuple. RPM and ADVANCE_RATIO are NOT among them: a speed is
    # what the row states and the reference does not. The count said five
    # over six keys and named none of them (the interface lens of the
    # 0.15.0 release review).
    "MOVING_BC_ALIAS",
    "MOVING_BOUNDARIES",
    "RPM",
    "ADVANCE_RATIO",
    "RPM_SIGN",
    "ROTOR_AXIS",
    "ROTOR_ORIGIN",
)


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
        variables[name.strip()] = value.strip()
    return variables


_ROTATION_AXIS = re.compile(r"^.+-[XYZ]$")


def _parse_motions(variables: dict[str, str], pol: str) -> list[dict[str, str]]:
    """Take the ``MOTIONS`` list out of the flat variables and read its records.

    PFS-2029.11.01. The grammar is the reference one: ``MOTIONS: {KEY: value / KEY:
    value}, {...}``, the braces closing one rotor each, the records
    separated by commas, the pairs inside a record by ``/`` exactly as the
    flat cell is. An unclosed brace, a record repeating a key, and a flat
    motion key beside the list are each refused naming the cell, and a
    cell without the key reads exactly as it did before this release; a
    brace on another key is that key's own (``OUTPUTS: loads_{point}.txt``
    is a template) and is left alone.
    """
    text = variables.pop(MOTIONS_VARIABLE, None)
    if text is None:
        return []
    flat = sorted(key for key in variables if key in MOTION_RECORD_KEYS)
    if flat:
        raise MatrixError(
            f"POL {pol}: the cell states {MOTIONS_VARIABLE} and also the flat key(s) "
            f"{', '.join(flat)}; a row with a motion list states every rotor inside "
            "its record, so the flat key would be a second statement of one rotor."
        )
    return _parse_records(text, pol, MOTIONS_VARIABLE, "rotor")


def _raw_records(variables: dict[str, str], pol: str) -> list[dict[str, str]]:
    """Read the cell's ``RAW`` list into one record per raw command (FR-67).

    The design decision of 2026-09-10, EXTENDING the preset's ``[[raw]]`` table to
    the row. A record states the line itself, ``COMMAND``, or a text file
    of the workspace holding lines, ``FILE``, and never both: the two are
    the same statement made twice and there would be no order between
    them. It states ``BEFORE`` either way, which is the phase the line
    goes before, spelled as the preset spells it.

    THE LINE IS NOT CHECKED HERE and that is the layering. Whether the
    build has the command, whether its arguments are the right type and
    count, whether its phase permits it: all of that is the EMITTER's, and
    a second implementation of it here is how the two come to disagree.
    This reader checks only the shape of the record, which is a matrix
    fact.
    """
    text = variables.pop(RAW_VARIABLE, None)
    if text is None:
        return []
    # A SPACED SEPARATOR, and only here. A raw record's values are a PATH
    # and a COMMAND LINE, both of which carry slashes of their own, so the
    # bare separator every other record uses would cut `raw/pusher_extra.txt`
    # in half. The reference row 9209 is the case: it is the shape the user wrote the
    # specification in, and it did not parse.
    records = _parse_records(text, pol, RAW_VARIABLE, "raw command", pair_separator=" / ")
    allowed = (RAW_COMMAND_KEY, RAW_FILE_KEY, RAW_BEFORE_KEY)
    for record in records:
        written = " / ".join(f"{k}: {v}" for k, v in record.items())
        unknown = sorted(key for key in record if key not in allowed)
        if unknown:
            raise MatrixError(
                f"POL {pol}: {RAW_VARIABLE} record states {', '.join(unknown)}, which a raw "
                f"command does not read; a record holds {RAW_COMMAND_KEY} or {RAW_FILE_KEY}, "
                f"and {RAW_BEFORE_KEY}."
            )
        forms = [key for key in (RAW_COMMAND_KEY, RAW_FILE_KEY) if record.get(key)]
        if len(forms) != 1:
            states = (
                f"both {' and '.join(forms)}"
                if forms
                else f"neither {RAW_COMMAND_KEY} nor {RAW_FILE_KEY}"
            )
            raise MatrixError(
                f"POL {pol}: {RAW_VARIABLE} record {{{written}}} states {states}; a record "
                f"is ONE of the two. {RAW_COMMAND_KEY} is the line as the solver reads it, "
                f"arguments included; {RAW_FILE_KEY} is a path under the workspace's "
                "inputs, whose lines are emitted in order."
            )
        # THE SPACING IS THE CAUSE, AND IT IS NAMED. A record written with
        # tight slashes, `{FILE: raw/x.txt/BEFORE: init}`, is read as ONE
        # pair whose value swallowed the rest, so the user was told the
        # record states no BEFORE while the message quoted back, in the
        # same sentence, the BEFORE they had written. A refusal that argues
        # with the evidence it prints sends the user to fix the one part
        # of the cell that was right (the interface and architecture
        # lenses, independently, 2026-09-10).
        swallowed = next(
            (
                key
                for key in allowed
                if len(record) == 1
                and any(f"/{key}:" in value or f"/ {key}:" in value for value in record.values())
            ),
            None,
        )
        if swallowed is not None:
            raise MatrixError(
                f"POL {pol}: {RAW_VARIABLE} record {{{written}}} was read as ONE pair, "
                f"because its separator has no spaces around it and {swallowed} was "
                f"swallowed into the value before it. A raw record separates its pairs "
                f"with ' / ', a slash WITH SPACES, and only a raw record does: its values "
                "are a path and a command line and both carry slashes of their own."
            )
        if not record.get(RAW_BEFORE_KEY):
            raise MatrixError(
                f"POL {pol}: {RAW_VARIABLE} record {{{written}}} states no {RAW_BEFORE_KEY}; "
                f"every raw command names the phase it goes before, one of "
                f"{', '.join(RAW_PHASES[1:])}, or control for a line at the head of the "
                "script."
            )
        # THE PHASE IS CHECKED WHERE THE INFORMATION IS. A misspelled phase
        # passed this reader whole and was refused at `resolve_matrix` by
        # the model's own validator, as a pydantic error with no POL and no
        # matrix vocabulary, while the MISSING phase three lines above got
        # a careful refusal listing the phases. `RAW_PHASES` is already
        # imported here (the interface lens, 2026-09-10).
        before = record[RAW_BEFORE_KEY].strip()
        if before not in RAW_PHASES:
            raise MatrixError(
                f"POL {pol}: {RAW_VARIABLE} record {{{written}}} goes before {before!r}, "
                f"which is not a phase; write one of {', '.join(RAW_PHASES[1:])}, or "
                "control for a line at the head of the script."
            )
    return records


def _parse_rotations(variables: dict[str, str], pol: str) -> list[dict[str, str]]:
    """Take the ``ROTATE`` list out of the flat variables and read its records.

    PFS-2034.02, the same grammar as ``MOTIONS`` (the decision of
    2026-09-09: "the declaration stays as we do with motion; two braces
    are two, in the order of the input"). Each record states ``ANGLE``
    in degrees, ``AXIS`` as ``<frame>-<X|Y|Z>`` and ``ALIAS`` (the
    0.14.0 ``FAMILIES`` is refused, naming ``ALIAS``), and may
    state ``AUX_FRAMES``; a key outside those five, a missing one, an
    angle that is not a number and an axis token of another shape are
    refused here, naming the cell, so a row is refused at plan time and
    never at the solver. What the names RESOLVE to (the frame, the
    families) is the builder's, which holds the geometry and the setup.
    """
    text = variables.pop(ROTATE_VARIABLE, None)
    if text is None:
        return []
    records = _parse_records(text, pol, ROTATE_VARIABLE, "rotation")
    allowed = (
        *ROTATION_RECORD_KEYS,
        ROTATION_ALIAS_KEY,
        ROTATION_FAMILIES_KEY,
        *ROTATION_OPTIONAL_KEYS,
    )
    for record in records:
        unknown = sorted(key for key in record if key not in allowed)
        if unknown:
            raise MatrixError(
                f"POL {pol}: {ROTATE_VARIABLE} record states {', '.join(unknown)}, which a "
                f"rotation does not read; a record holds {', '.join(ROTATION_RECORD_KEYS)} "
                f"and {ROTATION_ALIAS_KEY}, and optionally "
                f"{', '.join(ROTATION_OPTIONAL_KEYS)}."
            )
        missing = [key for key in ROTATION_RECORD_KEYS if key not in record]
        if missing:
            written = " / ".join(f"{k}: {v}" for k, v in record.items())
            raise MatrixError(
                f"POL {pol}: {ROTATE_VARIABLE} record {{{written}}} states no "
                f"{', '.join(missing)}; every rotation states {', '.join(ROTATION_RECORD_KEYS)}."
            )
        _refuse_a_rotation_that_names_its_set_twice_or_not_at_all(record, pol)
        try:
            float(record["ANGLE"])
        except ValueError:
            raise MatrixError(
                f"POL {pol}: {ROTATE_VARIABLE} ANGLE is {record['ANGLE']!r}, which is not a "
                "number; write the angle in degrees, as 3 or -2.5."
            ) from None
        if not _ROTATION_AXIS.match(record["AXIS"]):
            raise MatrixError(
                f"POL {pol}: {ROTATE_VARIABLE} AXIS is {record['AXIS']!r}, which is not of the "
                "form frame-axis; write the frame's name, a hyphen and X, Y or Z (the axis letter "
                "uppercase), as NAC-Y."
            )
    return records


def _refuse_a_rotation_that_names_its_set_twice_or_not_at_all(
    record: Mapping[str, str], pol: str
) -> None:
    """Refuse a rotation that names what it turns twice, or not at all (FR-71).

    ``ALIAS`` since 0.15.0, ``FAMILIES`` before it, and never both: two
    statements of what one rotation turns cannot both be obeyed, and
    picking one silently is how the wrong half of a study gets turned.
    Neither is a record that says how far to turn and about what, and
    nothing to turn.
    """
    alias = record.get(ROTATION_ALIAS_KEY)
    families = record.get(ROTATION_FAMILIES_KEY)
    if alias is not None and families is not None:
        raise MatrixError(
            f"POL {pol}: {ROTATE_VARIABLE} record states {ROTATION_ALIAS_KEY}: {alias} AND "
            f"{ROTATION_FAMILIES_KEY}: {families}; one rotation turns ONE set, so the two "
            f"cannot both be what it turns. {ROTATION_FAMILIES_KEY} is the 0.14.0 spelling "
            f"and {ROTATION_ALIAS_KEY} replaces it: keep the alias, and let the reference "
            "say what it owns."
        )
    if alias is None and families is None:
        written = " / ".join(f"{k}: {v}" for k, v in record.items())
        raise MatrixError(
            f"POL {pol}: {ROTATE_VARIABLE} record {{{written}}} says how far to turn and "
            f"about what, and nothing to turn. State {ROTATION_ALIAS_KEY}: <the word the "
            "reference declares>, which is how a motion names a set too."
        )


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


def workflow_types() -> tuple[str, ...]:
    """Every value a ``WORKFLOW`` cell may name.

    :data:`LEGACY_WORKFLOW` first, then the registered workflow names in
    the order :func:`pyflightstream.cases.workflows.workflow_names`
    gives them. It is READ from the registry at call time rather than
    frozen here, so a workflow registered tomorrow is accepted by this
    reader the same day and no second list can disagree with the table.

    Returns
    -------
    tuple of str
        The accepted values, in the order the refusal lists them.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import workflow_types
    >>> workflow_types()[0]
    'LEGACY'
    """
    return (LEGACY_WORKFLOW, *workflow_names())


def _check_workflow(value: str, pol: str) -> str:
    """Refuse a WORKFLOW cell naming no registered workflow type."""
    known = workflow_types()
    if value not in known:
        raise MatrixError(
            f"WORKFLOW value {value!r} of POL {pol} names no known workflow type; the "
            f"registered types are {', '.join(known)}. The column names WHICH "
            "workflow builds the row's script, so an unrecognised value would run the "
            f"wrong one silently; a row that wants the established behaviour, built by "
            f"the recipe its {RECIPE_VARIABLE} code names, writes {LEGACY_WORKFLOW}."
        )
    return value


def _check_one_sweep_per_row(pol: str, sweep: SweepAxis, variables: dict[str, str]) -> None:
    """Refuse a row asking for an aerodynamic AND a geometric sweep.

    The DECISION and its reasoning live in
    :func:`pyflightstream.cases.multiplied_sweep`, which is called here
    rather than restated: this function owns only the matrix's own
    vocabulary, so the refusal a matrix user reads names POL,
    ``FLIGHT_CONDITION`` and the cell they typed instead of naming a
    ``campaign.toml`` field they have never seen.

    The refusal names the fixed-offset form, because the user asking for
    both almost always wants one rotation held fixed across an alpha
    sweep, which is what ``angle_deg`` already does.
    """
    rotation = multiplied_sweep(sweep, variables)
    if not rotation:
        return
    raise MatrixError(
        f"POL {pol} asks for two sweeps at once: the FLIGHT_CONDITION {sweep.type} sweep of "
        f"{len(sweep.values)} points and the geometric sweep "
        f"{ROTATION_SWEEP_KEY}: {','.join(rotation)} of {len(rotation)} angles. The "
        f"two would multiply into {len(sweep.values) * len(rotation)} runs this row "
        "does not name and whose points cannot "
        "be told apart. A rotation held FIXED across an aerodynamic sweep is written "
        f"{ROTATION_OFFSET_KEY}: <angle>, one value; a sweep OF the rotation is a row "
        "of its own with a single-point SWEEP_VALUES."
    )


def read_matrix(path: str | Path, *, active_only: bool = True) -> list[MatrixRow]:
    """Read a pipe-delimited ``matrix.fs`` run matrix.

    Parameters
    ----------
    path : str or Path
        Matrix file location.
    active_only : bool
        Keep only rows with RUN = 1, the matrix activity filter;
        False returns every row. Keyword-only, so a bare boolean
        never hides in the call.

    Returns
    -------
    list of MatrixRow
        Parsed rows in file order.
    """
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    content = [line for line in lines if line.strip() and not set(line.strip()) <= {"-"}]
    if not content:
        raise MatrixError(f"{path} holds no matrix content")
    header = tuple(cell.strip() for cell in content[0].split("|"))
    if header == _LEGACY_COLUMNS_15:
        raise MatrixError(
            f"{path} carries the {len(_LEGACY_COLUMNS_15)}-column layout that preceded "
            f"the WORKFLOW column, so it is a run matrix written before v0.8.0 rather "
            "than a file this reader cannot recognise. To upgrade it, pass "
            "in_place=True to pyflightstream.cases.matrix.upgrade_matrix(path), or "
            "run `pyfs-matrix upgrade <path> --in-place`. It "
            f"inserts one {LEGACY_WORKFLOW!r} cell per row and folds RE and MACH "
            "into a FLIGHT_CONDITION cell. Every VALUE moves across verbatim and "
            "every other cell, separator and line ending is untouched."
        )
    if header == _LEGACY_COLUMNS_16:
        raise MatrixError(
            f"{path} carries the {len(_LEGACY_COLUMNS_16)}-column layout of v0.8.0 and "
            "v0.8.1, which held RE and MACH as columns of their own. They are now two "
            "keys of the FLIGHT_CONDITION cell, so that a row states its whole flow "
            "condition in one place. To upgrade it, pass in_place=True to "
            "pyflightstream.cases.matrix.upgrade_matrix(path), or run "
            "`pyfs-matrix upgrade <path> --in-place`. It "
            "replaces the two cells with one reading 'MACH:<mach>, REmi:<re>'. The "
            "VALUES move across verbatim and every other cell, separator and line "
            "ending is untouched; the two columns' own PADDING cannot survive, "
            "because two cells become one and the widths are not recoverable from "
            "the joined text. The conversion is lossless in content: those columns "
            "carried exactly the two quantities those keys carry."
        )
    if header == _LAYOUT_0_9_0:
        raise MatrixError(
            f"{path} carries the {len(_LAYOUT_0_9_0)}-column layout of v0.9.0 to "
            "v0.10.1, with ENTRY and FS_SCRIPT. At v0.11.0 ENTRY became PPROC, naming "
            "the post-processing artifact, and FS_SCRIPT went: a row naming a "
            "registered run type in WORKFLOW names its builder already, and a LEGACY "
            f"row carries its recipe code as {RECIPE_VARIABLE}: <code> among its "
            "variables. To upgrade it, call "
            "pyflightstream.cases.matrix.upgrade_matrix(path) with in_place (CLI: "
            "--in-place) and move the groups library with "
            "pyflightstream.workspace.migrate_groups_to_pproc, whose inputs (CLI: "
            "--inputs) is the workspace inputs directory; the command is `pyfs-matrix "
            "upgrade <path> --in-place --inputs <inputs dir>`. It "
            "renames the column, drops the FS_SCRIPT cell of every "
            "row, moves a LEGACY row's code into its variables, and takes OUTPUTS and "
            "LOG_OUTPUT out of a workflow row's variables, whose export set the pproc "
            "artifact now decides. Every other cell, separator and line ending is "
            "untouched."
        )
    if header == _LAYOUT_0_11_0:
        raise MatrixError(
            f"{path} carries the {len(_LAYOUT_0_11_0)}-column layout of v0.11.0 to "
            "v0.14.0, with a SWEEP_TYPE column. At v0.15.0 the column went: a sweep is "
            "applied to a variable that DEFINES the flight condition, and to exactly "
            f"one, so the cell says which by carrying {SWEEP_WORD!r} where that key's "
            "value would be, and a column naming the same variable a second time is a "
            "second home for one fact. To upgrade it, pass in_place=True to "
            "pyflightstream.cases.matrix.upgrade_matrix(path), or run "
            "`pyfs-matrix upgrade <path> --in-place`. It "
            f"drops the cell and writes ALPHA:{SWEEP_WORD} or BETA:{SWEEP_WORD} into "
            "FLIGHT_CONDITION, with a paired code's held angle beside it as a number. "
            "Every other cell, separator and line ending is untouched. THE ONE THING "
            "IT WILL NOT DO is split a row that sweeps BOTH angles: that is one row "
            "per sideslip, each needing a POL of its own, and a POL is run identity."
        )
    if header != _COLUMNS:
        # The fallthrough, and the one an upgrading user is most likely
        # to reach: legacy recognition above is exact tuple equality, so
        # a file one character off both older layouts AND the current one
        # lands here. That is what a half-done hand edit looks like, and
        # a release review found this was the only refusal in the file
        # that named no converter, leaving that user in a two-refusal
        # loop with the one sentence that rescues them said nowhere.
        first_difference = next(
            (
                f"the first difference is column {index + 1}: expected "
                f"{expected!r}, found {found!r}"
                # strict=False deliberately: the two may differ in LENGTH, which
                # is reported on its own line above, and the pairwise walk is
                # only asked for the first NAME that differs.
                for index, (expected, found) in enumerate(zip(_COLUMNS, header, strict=False))
                if expected != found
            ),
            f"the columns agree as far as they go, and the file has {len(header)} "
            f"of them where {len(_COLUMNS)} are expected",
        )
        # WHETHER TO NAME THE CONVERTER IS DECIDED PER FILE, and the
        # distinction is deliberate rather than a hedge. A file that is
        # simply not a run matrix must NOT be sent to a converter that
        # cannot help it: a migration and a break read differently, which
        # `test_the_legacy_refusal_is_a_different_message_from_the_foreign_one`
        # pins. But a file that shares most of its column names with a
        # layout this package knows is a half-done hand edit, and that
        # reader needs exactly the sentence the foreign reader must not
        # get. Overlap against the current layout and both frozen legacy
        # ones, majority of the expected width, decides which they are.
        known = (
            set(_COLUMNS)
            | set(_LEGACY_COLUMNS_15)
            | set(_LEGACY_COLUMNS_16)
            | set(_LAYOUT_0_9_0)
            | set(_LAYOUT_0_11_0)
        )
        looks_half_edited = len(known & set(header)) * 2 > len(_COLUMNS)
        remedy = (
            " If this file was written before v0.9.0 AND has since been edited by "
            "hand, restore the original and upgrade THAT: pass in_place=True to "
            "pyflightstream.cases.matrix.upgrade_matrix(path), or run "
            "`pyfs-matrix upgrade <path> --in-place`. The converter reads the two "
            "older layouts as they were written and does not recognise a partly "
            "edited one."
            if looks_half_edited
            else ""
        )
        raise MatrixError(
            f"{path} header does not match the verified {len(_COLUMNS)}-column layout; "
            f"expected {', '.join(_COLUMNS)} and found {', '.join(header)}. "
            f"There are {len(header)} columns where {len(_COLUMNS)} are expected, and "
            f"{first_difference}.{remedy}"
        )
    rows: list[MatrixRow] = []
    for row_number, line in enumerate(content[1:], start=1):
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != len(_COLUMNS):
            raise MatrixError(
                f"data row {row_number} of {path} holds {len(cells)} cells against "
                f"the {len(_COLUMNS)} verified columns: {line.strip()[:60]}..."
            )
        record = dict(zip(_COLUMNS, cells, strict=True))
        variables = _parse_variables(record["VAR_NAMES_VALUES"])
        motions = _parse_motions(variables, record["POL"])
        rotations = _parse_rotations(variables, record["POL"])
        raw = _raw_records(variables, record["POL"])
        if rotations and record["WORKFLOW"] == LEGACY_WORKFLOW:
            # A LEGACY row is built by its recipe, which is the reader of
            # its keys (the rule of 2026-09-08, design 68) and reads no
            # rotation, so the list would be dropped in silence
            # (PFS-2034.03). Refused here, where the cell is read.
            raise MatrixError(
                f"POL {record['POL']} writes LEGACY and states {ROTATE_VARIABLE}; a LEGACY row "
                "is built by its own recipe, which reads no rotation, so the list would turn "
                f"nothing. Name a run type in the WORKFLOW column ({', '.join(workflow_names())}), "
                "which rotates what the records name, or drop the key."
            )
        if raw and record["WORKFLOW"] == LEGACY_WORKFLOW:
            # THE SAME RULE, FOR THE SAME REASON, and it was missing: a
            # LEGACY row is built by its own recipe, which emits no raw
            # command, so the case would carry the lines and the RUN
            # RECORD would claim them while the script never took them.
            # The preset's `[[raw]]` table is already refused on such a
            # row, one function away, and the row's own list walked past
            # that guard through a door opened beside it (the architecture
            # lens, 2026-09-10).
            raise MatrixError(
                f"POL {record['POL']} writes LEGACY and states {RAW_VARIABLE}; a LEGACY row "
                "is built by its own recipe, which emits no raw command, so the lines would "
                "be recorded as taken and never emitted. Name a run type in the WORKFLOW "
                f"column ({', '.join(workflow_names())}), which emits them at the phase each "
                "record names, or drop the key."
            )
        # THE CELL CARRIES TWO SUBJECTS SINCE 0.15.0 (FR-69, FR-70): the
        # flow state, which is resolved into density and velocity, and the
        # row's ATTITUDE, which is what the aircraft does in it. They are
        # separated here, so the flow resolver is never handed an angle,
        # and the attitude joins the row's own variables where the
        # builders read it.
        condition = _require_flight_condition(
            record["FLIGHT_CONDITION"], record["POL"], row_number, path
        )
        state, attitude = _split_attitude(condition)
        # The swept key is not a value the row states: it is the word that
        # says which variable varies, and the axis it becomes is the row's
        # sweep. The other attitude keys ride on the variables, where the
        # builders read them (FR-69).
        variables.update({key: value for key, value in attitude.items() if value != SWEEP_WORD})
        row = MatrixRow(
            # From the enumerate above, so it is assigned before the RUN
            # filter below and an inactive row does not shift the numbers
            # of the rows after it (PFS-2009.08.03).
            row_number=row_number,
            pol=record["POL"],
            aircraft=record["AIRCRAFT"],
            description=record["DESCRIPTION"],
            flight_condition=state,
            sweep=_sweep_of_condition(condition, record["SWEEP_VALUES"], record["POL"]),
            ref_code=record["REF"],
            set_code=record["SET"],
            pproc_code=record["PPROC"],
            script_code=variables.get(RECIPE_VARIABLE, ""),
            fs_build=record["FS_BUILD"],
            hidden=record["HIDDEN"] == "1",
            run=int(record["RUN"]),
            workflow=_check_workflow(record["WORKFLOW"], record["POL"]),
            variables=variables,
            motions=motions,
            rotations=rotations,
            raw=raw,
        )
        # Every row is checked, active or not: the sweep codes and the
        # variable grammar already are, and a refusal a user only meets
        # after flipping RUN to 1 is a refusal that waited.
        _check_one_sweep_per_row(row.pol, row.sweep, row.variables)
        _refuse_a_choice_that_belongs_to_the_invocation(row)
        if row.run == 1 or not active_only:
            rows.append(row)
    return rows


def _refuse_a_choice_that_belongs_to_the_invocation(row: MatrixRow) -> None:
    """Refuse a cell key that is a property of the RUN and not of the row.

    One key today, and it is registered on every run type because the
    command line writes it onto the case (PFS-2035.13). Registered means
    typable, and typed into a cell it would become a property of the row,
    which is the one thing this design is not: whether a family the opened
    mesh does not carry is a skip or a refusal depends on what THIS RUN was
    for, and the row is written to serve several geometries.

    The same shape as the LOG_OUTPUT refusal above, and for the same
    reason: a key with two homes is a key whose two homes disagree.
    """
    if IGNORE_MISSING_FAMILIES_VARIABLE not in row.variables:
        return
    raise MatrixError(
        f"POL {row.pol} states {IGNORE_MISSING_FAMILIES_VARIABLE} among its variables, "
        "and that is a choice of the RUN rather than a property of the row. Whether a "
        "family the opened mesh does not carry is left out or REFUSES the point depends "
        "on what this run is for: the same row planned across a wing and a rotor wants "
        "the skip, and planned against the one geometry that should carry everything "
        "wants the refusal. Take the key out of the cell and pass "
        "ignore_missing_families (CLI: --ignore-missing-families) to plan or run "
        "instead, which is where the intent of one invocation belongs (PFS-2035.13)."
    )


#: The command-line spelling of the campaign default, named in the
#: refusal below so the message points at the thing a user types rather
#: than at the keyword the library takes.
#:
#: IT IS `--fs-version` AND NOT `--default-fs-version`, which is what
#: this constant said until 2026-08-19. No `pyfs-*` tool defines the
#: latter, so a user following the refusal exactly got `unrecognized
#: arguments` from argparse. The library PARAMETER renamed to
#: `default_fs_version` (PFS-2009.08.01) and the flag deliberately did
#: not: `--fs-version` is a unification across `pyfs-qa` and
#: `pyfs-manual` that the project kept, so renaming it here would have
#: undone a decision as a side effect of a different item.
DEFAULT_VERSION_OPTION = "--fs-version"


def refuse_silent_rows_without_default(
    rows: list[MatrixRow],
    default: str | None,
    path: str | Path,
) -> None:
    """Refuse a matrix that names no build anywhere, naming the rows.

    A row whose ``FS_BUILD`` cell strips to empty is SILENT: it asks for
    no build at all and falls back to the campaign default. When that
    default is empty too, nothing in the run names a FlightStream build,
    and picking one, by any rule, would be the package deciding what the
    study runs on. That is the one case that must not proceed on a guess
    (FR-10, PFS-2009.08.03).

    Called before anything is resolved, so a refusal costs no executable
    lookup, no :class:`~pyflightstream.cases.Campaign` and no executor.
    Placed here rather than at the build selection because the explicit
    ``fs_exe`` override returns before the build set is ever built, so a
    check there is skipped exactly when the override is passed, and the
    acceptance is "with and without ``fs_exe``".

    Parameters
    ----------
    rows : list of MatrixRow
        The rows to judge. Callers pass the ACTIVE rows: an inactive row
        runs nothing, so its empty cell asks nothing of anybody.
    default : str or None
        The campaign default version, as given. None and a string that
        strips to empty are the same absence here.
    path : str or Path
        Matrix location, for the message.

    Raises
    ------
    MatrixError
        When the default is absent, whether or not any row is silent.
        The two cases produce different text: with silent rows it names
        every one of them by row number and POL, and without them it
        names the option alone, so a blank default is never reported by
        the version registry as an unregistered version.
    """
    if default is not None and default.strip():
        return
    silent = [row for row in rows if not row.fs_build.strip()]
    if silent:
        named = ", ".join(f"row {row.row_number} (POL {row.pol})" for row in silent)
        raise MatrixError(
            f"{len(silent)} active row(s) of {path} name no build in the FS_BUILD "
            f"column and no campaign default was given: {named}. Nothing names a "
            "FlightStream build for those rows, and choosing one here would make "
            "this package decide what the study runs on. Give the default with "
            f"{DEFAULT_VERSION_OPTION} <version> (default_fs_version=... in "
            "Python), or fill each row's FS_BUILD cell with the build it runs on. "
            "The row numbers count the file's data rows, 1-based, ignoring blank "
            "lines and the dashed rule, and they do not change when a row's RUN "
            "flag does."
        )
    # EVERY ACTIVE ROW NAMES ITS BUILD AND NO DEFAULT WAS GIVEN: legal since
    # 0.11.0 (PFS-2029.01). Until then this refused too, on the argument that
    # a row added tomorrow with an empty cell would need the default; but
    # that row is refused BY NAME the day it is added, by the branch above,
    # which is the better answer than asking every study to repeat on the
    # command line a build its rows already state.
    return


def _peel_terminator(line: bytes) -> tuple[bytes, bytes]:
    """Split one line into its body and its line terminator."""
    for terminator in (b"\r\n", b"\n", b"\r"):
        if line.endswith(terminator):
            return line[: -len(terminator)], terminator
    return line, b""


def _header_names(parts: list[bytes]) -> tuple[str, ...]:
    return tuple(cell.strip().decode("utf-8", "replace") for cell in parts)


def _insert_workflow_cell(data: bytes, source: str) -> bytes:
    """Stage one: the fifteen-column layout gains WORKFLOW, byte-wise.

    Works on BYTES and never through :func:`read_matrix`, which replaces
    undecodable bytes, drops the dashed rule and strips every cell: a
    converter built on it would hand back a file the user cannot diff
    against the one they had.
    """
    index = _LEGACY_COLUMNS_16.index("WORKFLOW")
    last = index == len(_LEGACY_COLUMNS_16) - 1
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            # A line with no pipe: the dashed rule as every committed
            # fixture writes it, and any blank line. Neither carries a
            # cell, so neither is touched.
            #
            # NOT a general statement about rules, and it said one until
            # a release review measured it. `read_matrix` recognises a
            # rule by ``set(line.strip()) <= {"-"}``, so a rule written
            # with pipes between its dashes HAS cells and reaches the
            # branch below. The file is refused rather than mangled,
            # because the folded cell is not a number, but the refusal
            # then names a FLIGHT_CONDITION cell the user never wrote,
            # which costs the reader the diagnosis. The repair is to give
            # both readers one rule predicate; registered, not taken
            # here, because it changes what the reader accepts.
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            cell = _LEGACY_COLUMNS_16[index].encode("utf-8")
        else:
            row_number += 1
            if len(parts) != len(_LEGACY_COLUMNS_15):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LEGACY_COLUMNS_15)} columns of the layout "
                    "being upgraded, so this converter cannot say which cell the "
                    "WORKFLOW value would sit beside; repair the row first."
                )
            cell = LEGACY_WORKFLOW.encode("utf-8")
        # One leading space always, one trailing space unless the new cell
        # is last: a trailing space at end of line is what the repository's
        # own pre-commit hook strips out from under a committed fixture.
        parts.insert(index, b" " + cell + (b"" if last else b" "))
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


def _fold_flight_condition(data: bytes, source: str) -> bytes:
    """Stage two: RE and MACH become one FLIGHT_CONDITION cell.

    LOSSLESS BY CONSTRUCTION, which is why the fold is mechanical rather
    than a judgement: the two columns carried exactly the two quantities
    ``MACH`` and ``REmi`` name, in exactly those units, so the values
    move across VERBATIM. ``5.5`` stays ``5.5`` and ``0.20`` keeps its
    trailing zero, because a converter that reformatted numbers would
    hand back a diff whose real change nobody could find.
    """
    re_index = _LEGACY_COLUMNS_16.index("RE")
    mach_index = _LEGACY_COLUMNS_16.index("MACH")
    assert mach_index == re_index + 1, "the fold assumes RE and MACH are adjacent"
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            cell = b" FLIGHT_CONDITION "
        else:
            row_number += 1
            if len(parts) != len(_LEGACY_COLUMNS_16):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LEGACY_COLUMNS_16)} columns of the layout "
                    "being upgraded, so this converter cannot say which cells carry "
                    "RE and MACH; repair the row first."
                )
            re_value = parts[re_index].strip().decode("utf-8", "replace")
            mach_value = parts[mach_index].strip().decode("utf-8", "replace")
            cell = f" MACH:{mach_value}, REmi:{re_value} ".encode()
        parts[re_index : mach_index + 1] = [cell]
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


def _strip_pairs(cell: bytes, keys: tuple[str, ...]) -> bytes:
    """Drop the KEY: VALUE pairs named from one variables cell, keeping its padding."""
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    body = cell.strip().decode("utf-8", "replace")
    if not body:
        return cell
    kept = [
        part.strip()
        for part in body.split("/")
        if part.strip() and part.split(":", 1)[0].strip().upper() not in keys
    ]
    return leading + " / ".join(kept).encode("utf-8") + trailing


def _append_pair(cell: bytes, key: str, value: str) -> bytes:
    """Append one KEY: VALUE pair to a variables cell, keeping its padding."""
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    body = cell.strip().decode("utf-8", "replace")
    joined = f"{body} / {key}: {value}" if body else f"{key}: {value}"
    return leading + joined.encode("utf-8") + trailing


def _drop_fs_script_and_name_pproc(data: bytes, source: str) -> bytes:
    """Stage three: FS_SCRIPT goes, ENTRY becomes PPROC, the variables move.

    PFS-2029.04 and PFS-2029.07.02, one layout change for the release.
    Byte-wise like the two stages before it. The FS_SCRIPT cell of every
    row is removed; a LEGACY row's code is appended to its variables as
    ``RECIPE: <code>`` so the row still names its recipe, and any other
    row's code is dropped, because its WORKFLOW cell names its builder.
    The ENTRY header cell becomes PPROC in the same width, and an id
    beginning with ``e`` in that column begins with ``p``, which is the
    kind letter of the artifact the column now names; the file it names
    moves with ``pyfs-matrix upgrade --inputs``. A workflow row's OUTPUTS
    and LOG_OUTPUT pairs leave its variables, since the pproc artifact
    decides the export set and the log is always exported; a LEGACY row
    keeps them, because its recipe reads them. A rule line of dashes is
    shortened by the width of the cell removed, so the file still lines
    up.
    """
    entry_index = _LAYOUT_0_9_0.index("ENTRY")
    script_index = _LAYOUT_0_9_0.index("FS_SCRIPT")
    workflow_index = _LAYOUT_0_9_0.index("WORKFLOW")
    variables_index = _LAYOUT_0_9_0.index("VAR_NAMES_VALUES")
    rebuilt: list[bytes] = []
    header_seen = False
    removed_width = 0
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            stripped = body.strip()
            if stripped and set(stripped) <= {ord("-")} and removed_width:
                body = body[: max(0, len(body) - removed_width)]
            rebuilt.append(body + terminator)
            continue
        row_number += 1
        parts = body.split(b"|")
        if len(parts) != len(_LAYOUT_0_9_0):
            raise MatrixError(
                f"{source} row {row_number} has {len(parts)} cells against the "
                f"{len(_LAYOUT_0_9_0)} columns of the layout being upgraded: "
                f"{body.strip()[:60]!r}"
            )
        if not header_seen:
            header_seen = True
            entry_cell = parts[entry_index]
            parts[entry_index] = entry_cell.replace(b"ENTRY", b"PPROC", 1)
            removed_width = len(parts[script_index]) + 1
            del parts[script_index]
            rebuilt.append(b"|".join(parts) + terminator)
            continue
        code = parts[script_index].strip().decode("utf-8", "replace")
        workflow = parts[workflow_index].strip().decode("utf-8", "replace")
        entry_cell = parts[entry_index]
        entry_id = entry_cell.strip()
        if entry_id[:1].lower() == b"e" and entry_id[1:].isdigit():
            parts[entry_index] = entry_cell.replace(entry_id, b"p" + entry_id[1:], 1)
        if workflow == LEGACY_WORKFLOW:
            if code:
                parts[variables_index] = _append_pair(parts[variables_index], RECIPE_VARIABLE, code)
        else:
            parts[variables_index] = _strip_pairs(
                parts[variables_index], (OUTPUTS_VARIABLE, LOG_OUTPUT_VARIABLE)
            )
        del parts[script_index]
        rebuilt.append(b"|".join(parts) + terminator)
    return b"".join(rebuilt)


_GEOMETRY_PAIR = re.compile(rb"(GEOMETRY\s*:\s*)([^/|\s]+)")


def _name_geometry_files(data: bytes) -> bytes:
    """Stage four: a GEOMETRY value with no extension gains ``.fsm``.

    PFS-2029.09.02. Since 0.11.0 the cell carries the file name, and every
    matrix written before it named a stem; the file a workflow opens is a
    saved simulation, so ``.fsm`` is the extension the stem lacked. A
    value already carrying an extension is left as written, so running
    this on an upgraded file changes nothing, and every other byte of the
    line survives.
    """
    return _GEOMETRY_PAIR.sub(
        lambda m: m.group(1) + m.group(2) + (b"" if b"." in m.group(2) else b".fsm"), data
    )


def _paired_sweep_as_one(code: str, values: str) -> tuple[str, str] | None:
    """Return the folded cell of a paired code that sweeps ONE variable, or None.

    ``AL/BE`` over ``0.0,2.0/0.0`` varies the incidence and HOLDS the
    sideslip: the reader has always broadcast the single value across the
    other axis, so it is one swept variable written in two columns. It
    folds to ``ALPHA:sweep, BETA:0.0`` with the same values and the same
    number of rows.

    None means the code is not a pair, or that both halves vary, which is
    the two-variable sweep this release retires and which cannot fold
    without inventing a POL per row.
    """
    codes = [token.strip().upper() for token in code.split("/")]
    groups = [token.strip() for token in values.split("/")]
    if len(codes) != 2 or len(groups) != 2:
        return None
    if any(token not in _SWEEP_CODE_KEYS for token in codes):
        return None
    counts = [len([v for v in group.split(",") if v.strip()]) for group in groups]
    if counts[0] > 1 and counts[1] > 1:
        return None
    if 0 in counts:
        # A GROUP OF NO VALUES IS NOT A HELD AXIS. `AL/BE` over `0.0,2.0/`
        # has counts [2, 0], and choosing by `counts[1] == 1` picked the
        # EMPTY group as the swept one and wrote the other's whole list
        # into the held cell, which parses as one pair and one bare
        # number. Refused by the caller instead, where the row can be
        # named (the architecture lens, 2026-09-10).
        return None
    # WHICH ONE VARIES, not which one has a count of exactly 1. The second
    # axis is the swept one ONLY when the first holds a single value and
    # the second varies; in every other case the first is swept, which
    # keeps the single-point row `AL/BE` over `0.0/0.0` reading as the
    # alpha sweep it has always been.
    swept, held = (1, 0) if counts[0] == 1 and counts[1] > 1 else (0, 1)
    return (
        f"{_SWEEP_CODE_KEYS[codes[swept]]}:{SWEEP_WORD}, "
        f"{_SWEEP_CODE_KEYS[codes[held]]}:{groups[held]}",
        groups[swept],
    )


def _refuse_a_key_the_cell_already_names(
    condition: str, addition: str, row_number: int, source: str, pol: str
) -> None:
    """Refuse a fold that would state one key twice (FR-69).

    TWO DEFECTS IN ONE CHECK, both found by the review round of
    2026-09-10 and both from the same omission: the fold decided what to
    append from the SWEEP_TYPE cell alone and never read the cell it was
    appending to.

    THE FIRST is a file this package writes and its own reader refuses.
    ``_parse_flight_condition`` refuses a duplicated canonical key, so a
    cell already stating ``ALPHA:2.0`` beside a SWEEP_TYPE of ``AL``
    converted to ``..., ALPHA:2.0, ALPHA:sweep``, the converter reported
    success, and the next read refused with a message about a duplicate
    key that said nothing about the conversion that wrote it.

    THE SECOND is the promise of this release. An angle the cell already
    states becomes a HELD coordinate of every point, so it joins the
    point tag; before the fold it rode on the row and did not. Appending
    over it would therefore RENAME the row's runs, which is the one thing
    this converter must not do.

    MEASURED before it was fixed, because the blast radius decides
    whether this is a migration hazard or a robustness hole: the two
    never coexisted in a RELEASE. ``ATTITUDE_KEYS`` arrived at
    0.15.0.dev0 (commit 2840078) and ``SWEEP_TYPE`` left in the same
    unreleased cycle, so at v0.14.0 an angle in the cell was refused as
    an unknown key, and 0 of the 7 licensed matrices name one. No file a
    released pyflightstream ever accepted can reach this. What can is a
    file part-edited by hand mid-migration, which is exactly what the
    paired refusal invites, so it is refused rather than left to a
    coincidence of dates.
    """
    key = addition.split(":", 1)[0].strip().upper()
    stated = [
        pair.strip()
        for pair in condition.split(",")
        if pair.split(":", 1)[0].strip().upper() == key
    ]
    if not stated:
        return
    raise MatrixError(
        f"data row {row_number} of {source}, POL {pol}: FLIGHT_CONDITION already states "
        f"{', '.join(stated)}, and folding SWEEP_TYPE here would add {addition!r}, so "
        f"the cell would name {key} twice and this package's own reader would refuse "
        "the file it just wrote. It is also not a rename this converter may make: an "
        "angle the cell states is carried at every point of the sweep, so it ends the "
        f"run_id, and overwriting it would rename the row's runs. Decide which {key} "
        "the row means, write that one in FLIGHT_CONDITION, and drop the SWEEP_TYPE "
        "cell's claim on it."
    )


def _fold_sweep_type(data: bytes, source: str) -> bytes:
    """Stage four: the SWEEP_TYPE cell folds into FLIGHT_CONDITION (FR-69).

    The rule of 2026-09-10: a sweep is one variable, it is one that
    DEFINES the flight condition, and the cell says which by carrying the
    word ``sweep`` where that key's value would be. The column named the
    same fact a second time, so it goes and its content moves into the
    cell beside it: ``AL`` becomes ``ALPHA:sweep``, ``BE`` becomes
    ``BETA:sweep``.

    LOSSLESS IN CONTENT, and the one place it is not lossless ROW FOR ROW
    is refused rather than guessed: a PAIRED ``AL/BE`` sweep is two swept
    variables, which the rule forbids, and it becomes one row per
    sideslip. That changes the row COUNT and every new row needs a POL of
    its own, which is run identity and is not a converter's to invent. So
    a file carrying one is refused, naming every such row, and the user
    splits them with the POLs they want.
    """
    type_index = _LAYOUT_0_11_0.index("SWEEP_TYPE")
    condition_index = _LAYOUT_0_11_0.index("FLIGHT_CONDITION")
    values_index = _LAYOUT_0_11_0.index("SWEEP_VALUES")
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    paired: list[str] = []
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
        else:
            row_number += 1
            if len(parts) != len(_LAYOUT_0_11_0):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LAYOUT_0_11_0)} columns of the layout being "
                    "upgraded, so this converter cannot say which cell carries "
                    "SWEEP_TYPE; repair the row first."
                )
            code = parts[type_index].strip().decode("utf-8", "replace")
            pol = parts[0].strip().decode("utf-8", "replace")
            values_cell = parts[values_index].strip().decode("utf-8", "replace")
            folded = _paired_sweep_as_one(code, values_cell)
            if folded is None and "/" in code:
                # WHY THE CODE IS CHECKED BEFORE THE SHAPE: `AL/XX` folds to
                # nothing for a reason that has nothing to do with sweeping
                # two variables, and the paired refusal below would tell its
                # user to split a row per sideslip, which cannot fix a
                # typo. Refused here, naming the codes (the architecture
                # lens, 2026-09-10).
                axes = [token.strip() for token in code.split("/")]
                groups = [group.strip() for group in values_cell.split("/")]
                if len(axes) != 2 or len(groups) != len(axes):
                    # A PAIR IS TWO. Three axes read as a pair drops the
                    # third group in silence, which a QA pass scored as a
                    # surviving mutant: the arity was guarded and the guard
                    # was reached only through the unknown-code check, so
                    # three KNOWN codes went past both.
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states SWEEP_TYPE "
                        f"{code!r} and SWEEP_VALUES {values_cell!r}: {len(axes)} axis or "
                        f"axes against {len(groups)} value group(s). A '/' code names "
                        "exactly TWO axes and takes one comma-separated group for each. "
                        "Since 0.15.0 a row sweeps ONE variable, so what a two-axis code "
                        "may still say is one swept axis and one held value."
                    )
                unknown = [
                    token.strip()
                    for token in code.split("/")
                    if token.strip().upper() not in _SWEEP_CODE_KEYS
                ]
                if unknown:
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states "
                        f"SWEEP_TYPE {code!r}, whose code(s) {', '.join(unknown)} this "
                        f"converter does not know. The codes it folds are "
                        f"{', '.join(sorted(_SWEEP_CODE_KEYS))}."
                    )
                if any(not group for group in groups):
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states "
                        f"SWEEP_TYPE {code!r} and SWEEP_VALUES {values_cell!r}, in which "
                        "one axis has no values at all. Each axis of a paired code takes "
                        "one comma-separated group, and a group of none is not a held "
                        "value: write the value the axis holds, or drop the axis from "
                        "both cells."
                    )
            if folded is not None:
                # A PAIRED CODE IS NOT ALWAYS A PAIRED SWEEP. `AL/BE` with
                # `0.0,2.0/0.0` varies ONE variable and holds the other,
                # which the reader has always broadcast; written in the new
                # cell it is `ALPHA:sweep, BETA:0.0`, and the row count does
                # not change. Only a code whose two groups BOTH hold several
                # values is the two-variable sweep this release retires.
                condition = parts[condition_index].strip().decode("utf-8", "replace")
                extra, values = folded
                _refuse_a_key_the_cell_already_names(condition, extra, row_number, source, pol)
                joined = f"{condition}, {extra}" if condition else extra
                parts[condition_index] = f" {joined} ".encode()
                parts[values_index] = f" {values} ".encode()
            elif "/" in code:
                paired.append(f"POL {pol} sweeps {code} over {values_cell}")
            else:
                key = _SWEEP_CODE_KEYS.get(code.upper())
                if key is None:
                    raise MatrixError(
                        f"data row {row_number} of {source}, POL {pol}, states "
                        f"SWEEP_TYPE {code!r}, which this converter does not know. The "
                        f"codes it folds are {', '.join(sorted(_SWEEP_CODE_KEYS))}."
                    )
                condition = parts[condition_index].strip().decode("utf-8", "replace")
                _refuse_a_key_the_cell_already_names(
                    condition, f"{key}:{SWEEP_WORD}", row_number, source, pol
                )
                joined = f"{condition}, {key}:{SWEEP_WORD}" if condition else f"{key}:{SWEEP_WORD}"
                parts[condition_index] = f" {joined} ".encode()
        del parts[type_index]
        rebuilt.append(b"|".join(parts) + terminator)
    if paired:
        raise MatrixError(
            f"{source} carries {len(paired)} row(s) that sweep TWO variables at once, "
            f"which 0.15.0 does not admit: {'; '.join(paired)}. A sweep is one variable "
            "and it is one that defines the flight condition (FR-69), so a paired sweep "
            "becomes ONE ROW PER SIDESLIP. This converter will not do it for you: each "
            "new row needs a POL of its own, a POL is run identity, and an invented "
            "identity is worse than a refusal. EDIT THE FILE AS IT STANDS, keeping the "
            "SWEEP_TYPE column and the old AL/BE spelling, which is what this converter "
            "reads: replace each row above with one row per value of its second axis, "
            "each still AL/BE, each holding ONE value there, and each with the POL you "
            "want. Then run the upgrade, which writes the new spelling for you."
        )
    return b"".join(rebuilt)


#: The SWEEP_TYPE codes the fold above knows, to the FLIGHT_CONDITION key
#: each becomes. FROZEN WITH THE LAYOUT IT CONVERTS and it does not grow.
#: It read "built from the reader's own code table so the two cannot
#: drift" until 0.15.0, which was true while the reader had a code table;
#: that table went with the column, so there is nothing left to agree
#: with and a comment promising the agreement would tell the next
#: maintainer they may add a code in one place and be safe.
_SWEEP_CODE_KEYS = {"AL": "ALPHA", "BE": "BETA"}


def _upgraded_bytes(data: bytes, source: str) -> bytes:
    """Bring a matrix of any earlier layout up to the current one.

    FOUR STAGES, because four layouts precede the current one and a file
    written before v0.8.0 needs all of them: it gains the WORKFLOW
    column, then its RE and MACH columns fold into FLIGHT_CONDITION, then
    FS_SCRIPT goes and ENTRY becomes PPROC, and then SWEEP_TYPE folds
    into the flight condition too. Chaining them rather than writing
    direct converters is what keeps the oldest path exercised by the same
    code the newest one uses.
    """
    header: tuple[str, ...] | None = None
    for line in data.splitlines():
        body, _ = _peel_terminator(line)
        if b"|" in body:
            header = _header_names(body.split(b"|"))
            break
    if header is None:
        raise MatrixError(f"{source} holds no matrix content: no line carries a cell separator")
    if header == _COLUMNS:
        return _name_geometry_files(data)
    if header == _LAYOUT_0_11_0:
        return _name_geometry_files(_fold_sweep_type(data, source))
    if header == _LEGACY_COLUMNS_15:
        data = _fold_flight_condition(_insert_workflow_cell(data, source), source)
    elif header == _LEGACY_COLUMNS_16:
        data = _fold_flight_condition(data, source)
    elif header != _LAYOUT_0_9_0:
        raise MatrixError(
            f"{source} is not a run matrix at a layout this converter upgrades: its "
            f"header names {', '.join(header)}. The layouts it reads are the "
            f"{len(_LEGACY_COLUMNS_15)}-column one that precedes WORKFLOW "
            f"({', '.join(_LEGACY_COLUMNS_15)}), the {len(_LEGACY_COLUMNS_16)}-column "
            f"one that precedes FLIGHT_CONDITION ({', '.join(_LEGACY_COLUMNS_16)}), "
            f"the {len(_LAYOUT_0_9_0)}-column one of v0.9.0 to v0.10.1 "
            f"({', '.join(_LAYOUT_0_9_0)}) and the {len(_LAYOUT_0_11_0)}-column one of "
            f"v0.11.0 to v0.14.0 ({', '.join(_LAYOUT_0_11_0)})."
        )
    return _name_geometry_files(
        _fold_sweep_type(_drop_fs_script_and_name_pproc(data, source), source)
    )


#: The columns whose cells carry an input-library id, in file order.
#: These are the three the kind-letter rule renames (PFS-2009.03); every
#: other column names something that is not a library artifact.
CODE_COLUMNS = ("REF", "SET", "PPROC")


def _retag_cell(cell: bytes, mapping: Mapping[str, str]) -> tuple[bytes, str | None]:
    """Return one rewritten cell and the old id it carried, or None.

    Padding is preserved where it can be: the leading run of spaces is
    kept as it is, and a longer id eats trailing spaces down to one, so
    a matrix whose columns line up still lines up afterwards. Where
    there is not enough padding the cell simply grows, which is a wider
    column rather than a wrong one.
    """
    old = cell.strip().decode("utf-8", "replace")
    new = mapping.get(old)
    if new is None:
        return cell, None
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    grew = len(new) - len(old)
    if grew > 0 and len(trailing) > 1:
        trailing = trailing[: max(1, len(trailing) - grew)]
    return leading + new.encode("utf-8") + trailing, old


def rewrite_codes(
    path: str | Path,
    mapping: Mapping[str, Mapping[str, str]],
    *,
    in_place: bool = False,
) -> tuple[bytes, dict[str, int]]:
    """Rewrite the REF, SET and ENTRY cells of a matrix, byte for byte.

    Every other cell, separator, comment rule and line ending survives
    unchanged, and EVERY data row is rewritten, active or not: a row
    whose RUN flag is 0 today is a row somebody flips to 1 tomorrow, and
    leaving its cell behind is exactly the half-resolving state the
    kind-letter rule exists to end (PFS-2009.03).

    Works on BYTES rather than through :func:`read_matrix`, for the same
    reason :func:`upgrade_matrix` does: the reader replaces undecodable
    bytes, drops the dashed rule and strips every cell, so a converter
    built on it hands back a file the user cannot diff against the one
    they had.

    Parameters
    ----------
    path : str or Path
        The matrix to rewrite. Read as bytes and not decoded.
    mapping : mapping of str to mapping of str to str
        Per column, old id to new id; the keys are
        :data:`CODE_COLUMNS`. A column absent from the mapping, or a
        cell whose id the column's mapping does not carry, is left
        exactly as it is.
    in_place : bool
        Write the rewritten bytes back over ``path``. Keyword-only and
        False by default, so nothing is rewritten unless it is asked
        for.

    Returns
    -------
    tuple of bytes and dict
        The rewritten file, and how many cells changed per column. The
        count is what lets a caller refuse a migration that silently
        matched nothing.

    Raises
    ------
    MatrixError
        The header does not name the verified layout, a data row holds
        the wrong number of cells, or no line carries a cell separator.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import rewrite_codes
    >>> text, counts = rewrite_codes(       # doctest: +SKIP
    ...     "matrix.fs", {"REF": {"003": "r003"}}, in_place=True
    ... )
    """
    unknown = sorted(set(mapping) - set(CODE_COLUMNS))
    if unknown:
        raise MatrixError(
            f"column(s) {', '.join(unknown)} carry no input-library id; the columns "
            f"this rewrite touches are {', '.join(CODE_COLUMNS)}."
        )
    source = str(path)
    data = Path(path).read_bytes()
    indices = {name: _COLUMNS.index(name) for name in CODE_COLUMNS if name in mapping}
    counts = {name: 0 for name in indices}
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            names = tuple(cell.strip().decode("utf-8", "replace") for cell in parts)
            if names != _COLUMNS:
                raise MatrixError(
                    f"{source} is not a run matrix at the verified layout: its header "
                    f"names {', '.join(names)} and the layout this rewrite reads names "
                    f"{', '.join(_COLUMNS)}. Upgrade it first if it predates a column."
                )
            rebuilt.append(line)
            continue
        row_number += 1
        if len(parts) != len(_COLUMNS):
            raise MatrixError(
                f"data row {row_number} of {source} holds {len(parts)} cells against "
                f"the {len(_COLUMNS)} verified columns, so this rewrite cannot say "
                "which cell carries which id; repair the row first."
            )
        for name, index in indices.items():
            parts[index], changed = _retag_cell(parts[index], mapping[name])
            if changed is not None:
                counts[name] += 1
        rebuilt.append(b"|".join(parts) + terminator)
    if not header_seen:
        raise MatrixError(f"{source} holds no matrix content: no line carries a cell separator")
    rewritten = b"".join(rebuilt)
    if in_place:
        Path(path).write_bytes(rewritten)
    return rewritten, counts


def upgrade_matrix(path: str | Path, *, in_place: bool = False) -> bytes:
    """Bring a matrix of ANY earlier layout up to the current one.

    FOUR STAGES, because the format has broken four times and a file
    written before v0.8.0 needs all four. A fifteen-column file gains the
    ``WORKFLOW`` cell; then ``RE`` and ``MACH`` fold into one
    ``FLIGHT_CONDITION`` cell; then ``FS_SCRIPT`` goes and ``ENTRY``
    becomes ``PPROC``; then ``SWEEP_TYPE`` folds into the flight
    condition too, ``AL`` becoming ``ALPHA:sweep`` and ``BE`` becoming
    ``BETA:sweep``. A file at any of the four earlier layouts enters the
    chain where its header says it belongs, and a file already at the
    current layout is returned unchanged, so running this twice is safe.

    THE ONE THING IT WILL NOT DO, since 0.15.0: split a row that sweeps
    BOTH angles. That is one row per sideslip, each new row needs a POL
    of its own, a POL is run identity, and an invented identity is worse
    than a refusal, so such a file is refused with every such row named.
    A paired ``AL/BE`` whose second axis holds ONE value is not one of
    those: it varied one variable all along and it folds with the same
    rows.

    AND IT DOES NOT RENAME A RUN. An angle a row holds is carried at
    every point of the sweep, so the point tags that end every ``run_id``
    in an existing manifest are the ones the converted file plans under,
    and a resume after the upgrade finds its records.

    WHAT SURVIVES, stated precisely because the earlier wording said
    "every other byte" and that is not quite true of the fold. Every
    VALUE moves across verbatim -- ``0.20`` keeps its trailing zero --
    and every other cell, separator, comment rule and line ending is
    untouched. What cannot survive is the two folded columns' own
    PADDING, because two cells become one and the original widths are
    not recoverable from the joined text.

    The value written into each data row is
    :data:`LEGACY_WORKFLOW`, which names the behaviour those rows already
    have; the header receives the column LABEL, so the result is a file
    :func:`read_matrix` accepts rather than one that merely has the right
    number of cells.

    Parameters
    ----------
    path : str or Path
        The matrix to upgrade. It is read as bytes and is not decoded.
    in_place : bool
        Write the upgraded bytes back over ``path``. Keyword-only, and
        False by default, so nothing is rewritten unless it is asked
        for; a caller wanting a different destination writes the
        returned bytes there.

    Returns
    -------
    bytes
        The upgraded file content. A matrix already carrying the column
        is returned unchanged, so running this twice is safe.

    Raises
    ------
    MatrixError
        The header names neither layout, a data row holds the wrong
        number of cells, or no line carries a cell separator.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import upgrade_matrix
    >>> upgrade_matrix("matrix.fs", in_place=True)  # doctest: +SKIP
    """
    target = Path(path)
    upgraded = _upgraded_bytes(target.read_bytes(), str(target))
    if in_place:
        target.write_bytes(upgraded)
    return upgraded


def _condition_reynolds(row: MatrixRow) -> float | None:
    """Return the absolute Reynolds number a row STATES, or None.

    The matrix stores it in millions, which is what ``REmi`` names, and
    the conversion is here rather than in the parser because the parser
    keeps every value in the unit its key declares.

    THIS IS NOT THE RESOLUTION, and the difference is the layering. A
    Reynolds number that is STATED is carried straight through; one that
    is DERIVED, from a velocity and an atmosphere and a reference
    length, is computed by
    :func:`pyflightstream.workspace.flight_condition.resolve_flight_condition`
    one layer above, because the length lives in an artifact this layer
    cannot reach. Nothing is dropped in between: the whole condition
    travels on :attr:`SimCase.flight_condition` as written, so the layer
    that can resolve it has everything it needs and a reader can see
    what was asked for.
    """
    millions = row.flight_condition.get("REmi")
    return None if millions is None else millions * 1e6


#: Matrix variable naming the files a row's recipe exports, several
#: separated by commas. NOT by the slash: the slash already separates
#: the KEY:VALUE pairs of VAR_NAMES_VALUES, so a slash inside a value
#: splits the variable itself. Comma is what SWEEP_VALUES already uses
#: to separate values within one group.
OUTPUTS_VARIABLE = "OUTPUTS"


def _declared_outputs(row: MatrixRow, *, required: bool = True) -> list[str]:
    """Return the outputs a matrix row declares, refusing a row with none.

    A campaign collects the outputs the case DECLARES: the recipe
    exports ``case.outputs[i]`` and the loop copies exactly those files
    into the run folder. `to_campaign` never set the field, so every
    matrix-driven case carried the empty default, and therefore no
    matrix-driven run has ever collected anything. With the standard
    :class:`~pyflightstream.run.LoadsAssessor`, which is what the README
    and the guides tell a user to pass, the point lands
    ``FAILED_INCOMPLETE_OUTPUT`` with "collected: nothing" AFTER the
    solver has run.

    Measured 2026-08-03 on the reference research campaign: a
    thirty-minute unsteady run completed, the solver wrote all eight
    expected files into the run folder, and the point was recorded as a
    failure with the files sitting beside it. The physics was fine and
    the bookkeeping threw it away.

    It stayed invisible because the one end-to-end matrix test passes a
    stub assessor that returns CONVERGED without reading a file, so
    nothing in tier 1 ever exercised collection through this path.

    Refusing a row that declares nothing is deliberate, and it is the
    half that matters: a silent empty list spends solver time before
    failing, while a refusal costs nothing and names the remedy.

    Parameters
    ----------
    row : MatrixRow
        One active row.

    Returns
    -------
    list of str
        The declared output file names, in the order written.

    Raises
    ------
    MatrixError
        If the row declares no outputs AND ``required`` is True.
    """
    raw = row.variables.get(OUTPUTS_VARIABLE, "").strip()
    outputs = [part.strip() for part in raw.split(",") if part.strip()]
    # A WORKFLOW ROW THAT DECLARES NONE GETS THE STUDY'S EXPORT SET (FR-51,
    # PFS-2029.14): the seven or eight kinds the reference driver wrote, every one
    # hanging off the point placeholder. A row that still declares OUTPUTS
    # keeps exactly what it declares, so a matrix written before this
    # release exports what it always did. A LEGACY row is a recipe's and
    # the recipe decides, so it is left as written.
    if row.workflow and row.workflow.upper() != LEGACY_WORKFLOW:
        carried = [key for key in (OUTPUTS_VARIABLE, LOG_OUTPUT_VARIABLE) if key in row.variables]
        if carried:
            raise MatrixError(
                f"POL {row.pol} names the run type {row.workflow!r} and carries "
                f"{' and '.join(carried)} among its variables. Since 0.11.0 the export "
                "set of a workflow row is decided by the pproc artifact its PPROC cell "
                "names ([exports], PFS-2029.07), every export is named for the point, "
                "and the log is always exported; the two keys would be a second home "
                "for the same fact. Remove them, or upgrade the matrix with "
                "pyflightstream.cases.matrix.upgrade_matrix(path) and in_place (CLI: "
                "--in-place), which takes them out of every workflow row."
            )
        return default_outputs(unsteady=row.workflow.startswith("unsteady"))
    if not outputs and not required:
        # Conversion is a translation and spends no solver time, so it
        # carries whatever the row declares, including nothing. FR-10
        # scopes "forever" to the external format, which is the promise
        # about the existing files, and FR-11 calls conversion
        # lossless; refusing here broke the one path off the legacy
        # matrix, since every matrix written before this variable
        # existed declares none. The refusal lives on the paths that
        # are about to start a solver (architect and API-designer
        # passes, 2026-08-03).
        return []
    if not outputs:
        raise MatrixError(
            f"POL {row.pol} declares no outputs, so a run of it would collect nothing "
            "and be recorded FAILED_INCOMPLETE_OUTPUT after the solver had already "
            f"spent its time. Add the files the recipe exports to the row's variables "
            f"as {OUTPUTS_VARIABLE}, several separated by commas, for example "
            f"'{OUTPUTS_VARIABLE}: loads_{{point}}.txt, loads_cp_{{point}}.txt'. The "
            "point placeholder is what keeps a swept row's points from "
            "overwriting each other in the one simulation folder they share; "
            "without it the campaign is refused again, later, for that. The "
            "names must be the "
            "ones the recipe passes to its EXPORT commands, which the managed "
            "protocol reads from case.outputs."
        )
    return outputs


def _raw_without_a_workspace(row: MatrixRow, *, defer_files: bool) -> list[RawCommand]:
    """Return the row's COMMAND records as commands, refusing a FILE record (FR-67).

    This layer reads a matrix and has no workspace, so it cannot open the
    text file a FILE record names. A COMMAND record needs nothing it does
    not have: the line and the phase are both in the cell.

    ``defer_files`` is TRUE for exactly one caller, `resolve_matrix`, which
    has the inputs and replaces this list with the fully resolved one a
    moment later. Every other caller is terminal for the matrix it reads,
    and a FILE record it silently dropped would be a raw command the user
    wrote and no script ever took.
    """
    entries: list[RawCommand] = []
    for record in row.raw:
        line = record.get(RAW_COMMAND_KEY)
        if not line:
            if defer_files:
                continue
            raise MatrixError(
                f"POL {row.pol}: {RAW_VARIABLE} names the file "
                f"{record.get(RAW_FILE_KEY, '')!r}, and this conversion has no workspace "
                f"to resolve it against. A {RAW_FILE_KEY} record is read where the "
                f"inputs are, which is `resolve_matrix`; a {RAW_COMMAND_KEY} record needs "
                "no workspace and converts here."
            )
        entries.append(
            RawCommand(command=line, before=record[RAW_BEFORE_KEY].strip(), source="matrix")
        )
    return entries


def to_campaign(
    path: str | Path,
    *,
    name: str,
    fs_version: str,
    fs_exe: str,
    recipes: Mapping[str, str],
    require_outputs: bool = True,
    defer_raw_files: bool = False,
) -> Campaign:
    """Convert a run matrix into a native :class:`Campaign`.

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows convert.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical identifier (26.120); a vendor
        release name works only where it names exactly one registered
        build. The FS_BUILD
        column does not identify one, so it is explicit input.
    fs_exe : str
        Explicit executable path (never guessed, SAD Section 5).
    recipes : mapping of str to str
        RECIPE code (a LEGACY row's) to recipe reference (``module:function`` or a
        name registered with the campaign loop); replaces the
        import-by-number system (PP-7, FR-12).

    Returns
    -------
    Campaign
        Native campaign; the matrix codes survive in each case's
        variables (``matrix_ref``, ``matrix_set``, ``matrix_pproc``,
        ``matrix_fs_script``, ``matrix_fs_build``, ``matrix_hidden``,
        ``matrix_workflow``) so the conversion is lossless (FR-11).
    """
    rows = read_matrix(path)
    # Read once and judged before anything is built, so the refusal below
    # happens with no Campaign in existence (PFS-2009.08.03). Hoisted out
    # of the loop header for that reason alone; the iteration is unchanged.
    refuse_silent_rows_without_default(rows, fs_version, path)
    sims = []
    for row in rows:
        # A ROW NAMING A REGISTERED RUN TYPE NAMES ITS BUILDER (PFS-2029.02):
        # the WORKFLOW cell is the recipe, resolved through the workflow
        # registry, and no option repeats it. A LEGACY row is built by a
        # function of the user's own, which its RECIPE code must map to.
        if row.workflow != LEGACY_WORKFLOW:
            recipe = recipes.get(row.script_code, row.workflow) if row.script_code else row.workflow
        elif row.script_code in recipes:
            recipe = recipes[row.script_code]
        elif _RECIPE_REFERENCE.match(row.script_code or ""):
            # THE CELL CARRIES THE REFERENCE ITSELF (PFS-2031.11): a matrix
            # whose LEGACY rows name their recipe as package.module:function
            # plans and runs with no --recipe option, which is what FR-50
            # promises of a matrix. A mapping for that same string, if one is
            # given, wins above, so nothing a user mapped changes meaning.
            recipe = row.script_code
        else:
            stated = (
                f"code {row.script_code!r} has no recipe mapping"
                if row.script_code
                else "cell is empty"
            )
            raise MatrixError(
                f"POL {row.pol} writes {LEGACY_WORKFLOW} and its {RECIPE_VARIABLE} {stated}; "
                "a LEGACY row is built by a function of your own: write the reference itself "
                f"in the cell, {RECIPE_VARIABLE}: package.module:function, or map the code "
                "with recipes={code: 'package.module:function'} in Python, or --recipe "
                "CODE=package.module:function on the pyfs-matrix command line. A row "
                "that wants a run type this package builds itself writes the type in "
                f"its WORKFLOW cell instead, one of: {', '.join(workflow_names())}"
            )
        variables: dict[str, str | float | int | bool] = dict(row.variables)
        variables.update(
            matrix_ref=row.ref_code,
            matrix_set=row.set_code,
            matrix_pproc=row.pproc_code,
            matrix_fs_script=row.script_code,
            matrix_fs_build=row.fs_build,
            matrix_hidden=row.hidden,
            # THE WORKFLOW BELONGS ON THE CASE, as a declared field beside
            # `recipe`, and it is carried here instead because `SimCase` is
            # `extra="forbid"` and adding the field is an edit to
            # `cases/__init__.py`, which this change does not own
            # (PFS-2025.01). The reserved `matrix_` namespace is written by
            # this converter and never by a user's VAR_NAMES_VALUES cell, so
            # the value cannot be shadowed by case data, and the conversion
            # stays lossless (FR-11) meanwhile. When the declared field
            # lands, pass `workflow=row.workflow` and drop this key.
            matrix_workflow=row.workflow,
        )
        sims.append(
            SimCase(
                sim_id=row.pol,
                aircraft=row.aircraft,
                description=row.description,
                flight_condition=dict(row.flight_condition),
                reynolds=_condition_reynolds(row),
                mach=row.flight_condition.get("MACH"),
                sweep=row.sweep,
                recipe=recipe,
                outputs=_declared_outputs(row, required=require_outputs),
                motions=[dict(record) for record in row.motions],
                rotations=[dict(record) for record in row.rotations],
                # A COMMAND RECORD IS ALREADY RESOLVED and rides on the case
                # here; a FILE record is not, because reading one needs the
                # workspace's inputs, which this layer does not have, and the
                # workspace expands those into `raw_commands`.
                #
                # THE FILE RECORD IS REFUSED RATHER THAN DROPPED. The first
                # writing dropped the whole cell in silence, so a matrix read
                # WITHOUT a workspace, which `to_campaign` and `convert_matrix`
                # both are and both public, lost every raw command a row
                # stated: no error, no warning, and the row had parsed
                # cleanly, so the user had every reason to think it took
                # (the architecture lens, 2026-09-10).
                raw_commands=_raw_without_a_workspace(row, defer_files=defer_raw_files),
                variables=variables,
            )
        )
    # NO DEFAULT AND EVERY ROW NAMING ITS BUILD (PFS-2029.01): the campaign
    # records the first active row's build as its version, since a blank
    # default answers for no row and the model asks for a version.
    if fs_version is None or not fs_version.strip():
        fs_version = next(row.fs_build.strip() for row in rows if row.fs_build.strip())
    # NO DEFAULT AND EVERY ROW NAMING ITS BUILD (PFS-2029.01): the campaign
    # records the first active row's build as its version, since a blank
    # default answers for no row and the model asks for a version.
    if fs_version is None or not fs_version.strip():
        fs_version = next(row.fs_build.strip() for row in rows if row.fs_build.strip())
    # NO DEFAULT AND EVERY ROW NAMING ITS BUILD (PFS-2029.01): the campaign
    # records the first active row's build as its version, since a blank
    # default answers for no row and the model asks for a version.
    if fs_version is None or not fs_version.strip():
        fs_version = next(row.fs_build.strip() for row in rows if row.fs_build.strip())
    # NO DEFAULT AND EVERY ROW NAMING ITS BUILD (PFS-2029.01): the campaign
    # records the first active row's build as its version, since a blank
    # default answers for no row and the model asks for a version.
    if fs_version is None or not fs_version.strip():
        fs_version = next(row.fs_build.strip() for row in rows if row.fs_build.strip())
    # NO DEFAULT AND EVERY ROW NAMING ITS BUILD (PFS-2029.01): the campaign
    # records the first active row's build as its version, since a blank
    # default answers for no row and the model asks for a version.
    if fs_version is None or not fs_version.strip():
        fs_version = next(row.fs_build.strip() for row in rows if row.fs_build.strip())
    return Campaign(
        name=name, fs_version=fs_version, fs_exe=fs_exe, sims=sims, matrix_stem=Path(path).stem
    )


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def convert_matrix(
    path: str | Path,
    *,
    name: str,
    fs_version: str,
    fs_exe: str,
    recipes: Mapping[str, str],
) -> str:
    """Emit the native ``campaign.toml`` text of a run matrix (FR-11).

    Parameters are those of :func:`to_campaign`. The returned text
    loads back through :func:`pyflightstream.cases.load_campaign`, so
    migration is one call and reversible only in the sense that the
    matrix file itself stays untouched and readable forever (FR-10).
    """
    # require_outputs=False: this is the migration tool. A row that
    # declares none converts to a sim that declares none, and the
    # warning below names the rows, so the existing matrices
    # keep converting (FR-10, FR-11) and learn what to add.
    campaign = to_campaign(
        path,
        name=name,
        fs_version=fs_version,
        fs_exe=fs_exe,
        recipes=recipes,
        require_outputs=False,
    )
    undeclared = [sim.sim_id for sim in campaign.sims if not sim.outputs]
    if undeclared:
        warnings.warn(
            f"{len(undeclared)} converted sim(s) declare no outputs "
            f"({', '.join(undeclared)}). The conversion is complete and lossless: the "
            f"matrix rows carry no {OUTPUTS_VARIABLE} variable, so the campaign carries "
            "no outputs either. Add them before running, either in the matrix as "
            f"'{OUTPUTS_VARIABLE}: loads_{{point}}.txt' or in the campaign file as "
            "outputs = [...], naming the files the recipe exports. Running a case that "
            "declares none collects nothing and records the point "
            "FAILED_INCOMPLETE_OUTPUT after the solver has already spent its time.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    lines = [
        "[campaign]",
        f"name = {_toml_value(campaign.name)}",
        f"fs_version = {_toml_value(campaign.fs_version)}",
        f"fs_exe = {_toml_value(campaign.fs_exe)}",
        # The matrix identity travels with the conversion (PFS-2031.04), so
        # a converted campaign keeps its products where the matrix would,
        # and the round trip through load_campaign stays lossless (FR-11).
        f"matrix_stem = {_toml_value(campaign.matrix_stem)}",
    ]
    for sim in campaign.sims:
        lines += [
            "",
            "[[sim]]",
            f"sim_id = {_toml_value(sim.sim_id)}",
            f"aircraft = {_toml_value(sim.aircraft)}",
        ]
        if sim.description:
            lines.append(f"description = {_toml_value(sim.description)}")
        if sim.reynolds is not None:
            lines.append(f"reynolds = {_toml_value(sim.reynolds)}")
        if sim.mach is not None:
            lines.append(f"mach = {_toml_value(sim.mach)}")
        if sim.flight_condition:
            # The condition AS WRITTEN, so the conversion stays lossless
            # (FR-11) and a campaign.toml round-trips back to the same
            # case. Without this the constraint set would survive the
            # matrix reader and die at the converter, which is the half
            # of a lossless claim nobody tests until it matters.
            pairs = ", ".join(
                f"{key} = {_toml_value(value)}" for key, value in sim.flight_condition.items()
            )
            lines.append(f"flight_condition = {{{pairs}}}")
        plain_values = [
            list(value) if isinstance(value, tuple) else value for value in sim.sweep.values
        ]
        held = (
            ", held = {"
            + ", ".join(f"{key} = {_toml_value(value)}" for key, value in sim.sweep.held.items())
            + "}"
            if sim.sweep.held
            else ""
        )
        lines.append(
            f"sweep = {{type = {_toml_value(sim.sweep.type)}, "
            f"values = {_toml_value(plain_values)}{held}}}"
        )
        lines.append(f"recipe = {_toml_value(sim.recipe)}")
        # FR-11 says the conversion is lossless, and the outputs are part
        # of what the row declares now, so they have to survive it. Before
        # 2026-08-03 there was nothing here to lose: every converted case
        # carried the empty default.
        if sim.outputs:
            lines.append(f"outputs = {_toml_value(list(sim.outputs))}")
        if sim.variables:
            lines.append("[sim.variables]")
            for key, value in sim.variables.items():
                lines.append(f"{_toml_value(key)} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"
