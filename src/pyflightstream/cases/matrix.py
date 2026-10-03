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

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._errors import PyflightstreamError as PyflightstreamError
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._tokens import NOT_APPLICABLE as NOT_APPLICABLE
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
from pyflightstream.cases import InputKey as InputKey
from pyflightstream.cases._matrix_layouts import _COLUMNS as _COLUMNS
from pyflightstream.cases._matrix_layouts import _LAYOUT_0_9_0 as _LAYOUT_0_9_0
from pyflightstream.cases._matrix_layouts import _LAYOUT_0_11_0 as _LAYOUT_0_11_0
from pyflightstream.cases._matrix_layouts import _LAYOUT_0_15_0 as _LAYOUT_0_15_0
from pyflightstream.cases._matrix_layouts import _LEGACY_COLUMNS_15 as _LEGACY_COLUMNS_15
from pyflightstream.cases._matrix_layouts import _LEGACY_COLUMNS_16 as _LEGACY_COLUMNS_16
from pyflightstream.cases._matrix_layouts import _RECIPE_REFERENCE as _RECIPE_REFERENCE
from pyflightstream.cases._matrix_layouts import CODE_COLUMNS as CODE_COLUMNS
from pyflightstream.cases._matrix_layouts import COLUMN_MEANINGS as COLUMN_MEANINGS
from pyflightstream.cases._matrix_layouts import COLUMNS_NEW_AT_0_17_0 as COLUMNS_NEW_AT_0_17_0
from pyflightstream.cases._matrix_layouts import (
    COLUMNS_THAT_MAY_BE_UNSTATED as COLUMNS_THAT_MAY_BE_UNSTATED,
)
from pyflightstream.cases._matrix_layouts import LEGACY_WORKFLOW as LEGACY_WORKFLOW
from pyflightstream.cases._matrix_layouts import MATRIX_COLUMNS as MATRIX_COLUMNS
from pyflightstream.cases._matrix_layouts import OUTPUTS_VARIABLE as OUTPUTS_VARIABLE
from pyflightstream.cases._matrix_layouts import RECIPE_VARIABLE as RECIPE_VARIABLE
from pyflightstream.cases._matrix_layouts import (
    RECOGNIZED_MATRIX_LAYOUTS as RECOGNIZED_MATRIX_LAYOUTS,
)
from pyflightstream.cases._matrix_layouts import UNSTATED_CELL as UNSTATED_CELL
from pyflightstream.cases._matrix_layouts import UNSTATED_CELLS as UNSTATED_CELLS
from pyflightstream.cases._matrix_layouts import MatrixError as MatrixError
from pyflightstream.cases._matrix_layouts import (
    _fold_columns_into_variables as _fold_columns_into_variables,
)
from pyflightstream.cases._matrix_layouts import _parse_records as _parse_records
from pyflightstream.cases._matrix_layouts import _parse_variables as _parse_variables
from pyflightstream.cases._matrix_layouts import _split_outside_braces as _split_outside_braces
from pyflightstream.cases._matrix_upgrade import _GEOMETRY_PAIR as _GEOMETRY_PAIR
from pyflightstream.cases._matrix_upgrade import (
    _KEYS_THAT_BECAME_COLUMNS as _KEYS_THAT_BECAME_COLUMNS,
)
from pyflightstream.cases._matrix_upgrade import _SWEEP_CODE_KEYS as _SWEEP_CODE_KEYS
from pyflightstream.cases._matrix_upgrade import _append_pair as _append_pair
from pyflightstream.cases._matrix_upgrade import (
    _drop_fs_script_and_name_pproc as _drop_fs_script_and_name_pproc,
)
from pyflightstream.cases._matrix_upgrade import _expand_to_nineteen as _expand_to_nineteen
from pyflightstream.cases._matrix_upgrade import _fold_flight_condition as _fold_flight_condition
from pyflightstream.cases._matrix_upgrade import _fold_sweep_type as _fold_sweep_type
from pyflightstream.cases._matrix_upgrade import _header_names as _header_names
from pyflightstream.cases._matrix_upgrade import _insert_workflow_cell as _insert_workflow_cell
from pyflightstream.cases._matrix_upgrade import _name_geometry_files as _name_geometry_files
from pyflightstream.cases._matrix_upgrade import _pad_like as _pad_like
from pyflightstream.cases._matrix_upgrade import _paired_sweep_as_one as _paired_sweep_as_one
from pyflightstream.cases._matrix_upgrade import _peel_terminator as _peel_terminator
from pyflightstream.cases._matrix_upgrade import (
    _refuse_a_key_the_cell_already_names as _refuse_a_key_the_cell_already_names,
)
from pyflightstream.cases._matrix_upgrade import _retag_cell as _retag_cell
from pyflightstream.cases._matrix_upgrade import _split_free_cell as _split_free_cell
from pyflightstream.cases._matrix_upgrade import (
    _strip_keys_from_variables as _strip_keys_from_variables,
)
from pyflightstream.cases._matrix_upgrade import _strip_pairs as _strip_pairs
from pyflightstream.cases._matrix_upgrade import _upgraded_bytes as _upgraded_bytes
from pyflightstream.cases._matrix_upgrade import rewrite_codes as rewrite_codes
from pyflightstream.cases._sweep_names import _HELD_POINT_KEYS as _HELD_POINT_KEYS
from pyflightstream.cases._sweep_names import ATTITUDE_KEYS as ATTITUDE_KEYS
from pyflightstream.cases._sweep_names import FLIGHT_CONDITION_KEYS as FLIGHT_CONDITION_KEYS
from pyflightstream.cases._sweep_names import _condition_sweep_axes, _sweep_of_condition
from pyflightstream.cases.naming import POINT_AXIS_KEYS as POINT_AXIS_KEYS

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
    RESERVED_CONTINUATION_VARIABLES,
    ROTATE_VARIABLE,
    ROTATION_ALIAS_KEY,
    ROTATION_FAMILIES_KEY,
    ROTATION_OPTIONAL_KEYS,
    ROTATION_RECORD_KEYS,
    SWEEP_WORD,
    TRANSLATE_VARIABLE,
    TRANSLATION_ALIAS_KEY,
    TRANSLATION_OPTIONAL_KEYS,
    TRANSLATION_RECORD_KEYS,
    workflow_names,
)
from pyflightstream.cases.workflows import ROW_KEY_MEANINGS as ROW_KEY_MEANINGS
from pyflightstream.cases.workflows import WALLTIME_UNITS_GLOSS as WALLTIME_UNITS_GLOSS
from pyflightstream.cases.workflows import WALLTIME_VARIABLE as WALLTIME_VARIABLE

__all__ = [
    "MATRIX_COLUMNS",
    "RECOGNIZED_MATRIX_LAYOUTS",
    "COLUMN_MEANINGS",
    "COLUMNS_NEW_AT_0_17_0",
    "COLUMNS_THAT_MAY_BE_UNSTATED",
    "UNSTATED_CELL",
    "UNSTATED_CELLS",
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
    "renumber_pols",
    "rewrite_codes",
    "to_campaign",
    "upgrade_matrix",
    "workflow_types",
]


# The two rotation keys of VAR_NAMES_VALUES this reader knows about, one
# fixed offset and one geometric sweep, ARE NOT DEFINED HERE. They and the
# one-sweep-per-case limit they carry belong to `pyflightstream.cases`,
# the layer below and the single owner of the decision (PFS-2025.17): a
# second spelling in this module is how a hand-written campaign comes to
# run what the matrix refuses. Both are imported at the top of this file.


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
    #: The mesh translations the cell's ``TRANSLATE`` list states, one
    #: record each, in cell order (FR-100), DISTANCE in metres along one
    #: axis of the named frame; empty for a row stating none.
    translations: list[dict[str, str]] = field(default_factory=list)
    #: The raw solver commands the cell's ``RAW`` list states, one record
    #: each, in cell order (FR-67); empty for a row stating none. A record
    #: holds ``COMMAND`` or ``FILE``, never both, and ``BEFORE``.
    raw: list[dict[str, str]] = field(default_factory=list)
    #: 0.21.0: the canonical keys of the FLIGHT_CONDITION cell in the order the
    #: row wrote them, the swept key included; the point name follows it.
    condition_order: list[str] = field(default_factory=list)


#: The three keys that turn the free stream, in the order a name writes them.
RATE_KEYS = ("roll_rate", "pitch_rate", "yaw_rate")


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
    pol: str = "",
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
    _refuse_a_speed_and_a_ratio_over_a_velocity(condition, pol)
    _refuse_two_body_rates(condition, pol)
    return state, attitude


def _refuse_two_body_rates(condition: dict[str, float | str], pol: str) -> None:
    """Refuse a cell that turns the free stream two ways at once.

    ONE non-zero rate per row. The free stream is
    given one axis and one angular velocity, so two rates would have to be
    composed into an axis nobody wrote, and the row would run something other
    than what it says. A rate stated as zero is not a rotation and is free to
    sit beside another.
    """
    turning = [
        key
        for key in RATE_KEYS
        if key in condition
        and (
            str(condition[key]).strip().casefold() == SWEEP_WORD.casefold()
            or float(condition[key]) != 0.0
        )
    ]
    if len(turning) < 2:
        return
    raise MatrixError(
        f"POL {pol}: FLIGHT_CONDITION states {len(turning)} non-zero body rates "
        f"({', '.join(turning)}), and a rotating free stream turns about ONE axis at one "
        "speed. Two rates would be composed into an axis this row does not write. State "
        "one rate per row, and write the others as 0."
    )


#: The two keys of the cell that fix the free-stream velocity directly.
VELOCITY_KEYS = ("MACH", "TASmps")


def _refuse_a_speed_and_a_ratio_over_a_velocity(
    condition: dict[str, float | str], pol: str
) -> None:
    """Refuse a cell that states the rotor speed, the advance ratio AND a velocity.

    The three are one relation, V = J n D, so any
    two of them give the third: RPM with ADVANCE_RATIO and no velocity is the
    static-rig form and the velocity is COMPUTED from it, which is the case a
    rotor study writes. All three is one number too many, and the package
    cannot know which two were intended.
    """
    stated = [key for key in VELOCITY_KEYS if key in condition]
    if not stated or "RPM" not in condition or "ADVANCE_RATIO" not in condition:
        return
    raise MatrixError(
        f"POL {pol}: FLIGHT_CONDITION states RPM, ADVANCE_RATIO and "
        f"{', '.join(stated)}. Those are one relation, V = J x (RPM/60) x D, so the "
        "three over-state the point and nothing here can know which two you meant. "
        "State RPM and ADVANCE_RATIO and the velocity is computed from them against "
        "the diameter of the rotor CLOCK_MOTION names; or state a velocity with one "
        "of the two and the other is derived."
    )


#: EVERY key of the cell, to the sweep axis each becomes (0.21.0). The rule
#: always licensed any key; until 0.21.0 only the two angles and the ratio
#: were implemented, and a row sweeping a Mach number was refused naming the
#: three. It is built from :data:`pyflightstream.cases.POINT_AXIS_KEYS` and the
#: cell's own vocabulary, so a variable that joins the cell is sweepable the
#: day it joins and the two cannot drift apart.
#:
#: A key outside this map is still refused NAMING the set rather than accepted
#: and silently ignored, which is the failure the ratio sweep had before 0.15.0
#: (PFS-2035.06, measured 2026-09-10: the axis existed, the point carried it
#: and nothing read it).
_CONDITION_SWEEP_AXES = _condition_sweep_axes()

#: The FLIGHT_CONDITION keys whose HELD value joins every point of the
#: sweep rather than staying on the row. The two angles and no more: they
#: are the only ones a run tag has ever carried as a held value, through
#: the paired ``AL/BE`` code, and widening the set would rename runs in
#: the other direction. See :attr:`pyflightstream.cases.SweepAxis.held`.
# Imported from _sweep_names, kept here for existing readers.


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


def _refuse_the_packages_continuation_keys(variables: Mapping[str, str], pol: str) -> None:
    """Refuse a row that writes the two names the run path resolves for it.

    FOUND BY THE ARCHITECT LENS of the 0.18.0 release round, 2026-09-14.
    ``RESTART_FROM`` and ``RESTART_ITERATIONS`` are how the run path hands a
    resolved continuation to the builder, and they travel in the same free
    variable namespace a user's ``VAR_NAMES_VALUES`` cell writes into. So a
    row stating ``RESTART`` together with both of them reached
    :func:`~pyflightstream.cases.workflows.continuation_of` with the facts
    already present and built a continuation DIRECTLY, skipping
    ``resolve_continuation`` entirely: no check that a recorded run exists,
    no check that it stopped in a state a continuation may resume, no archive
    of the outputs about to be replaced, and no stamped run id. The
    continuation then overwrote the stopped run's outputs in place under the
    predecessor's own run id, which is the collision the stamp exists to
    prevent.

    REFUSED RATHER THAN RENAMED into the reserved ``matrix_`` namespace,
    which was the other way to close it. A rename is SILENT: the user who
    wrote the key would find it ignored rather than refused, and the shape of
    this mistake is somebody copying a name out of a generated script or a
    manifest and reasonably expecting it to mean what it says.

    It is called from the row reader, so the refusal lands at plan time and
    spends nothing.
    """
    stated = [name for name in RESERVED_CONTINUATION_VARIABLES if name in variables]
    if not stated:
        return
    raise MatrixError(
        f"POL {pol}: {', '.join(stated)} is set by the package and not by a row. A continuation "
        "states RESTART and nothing else about the run it continues: WHICH run that is, and how "
        "many steps are left, are answers the manifest holds, and the run path reads them off "
        "the recorded run being continued. Stating them here skips that resolution, which is "
        "what checks the recorded run exists, that it stopped in a state a continuation may "
        "resume, and that its outputs are archived before they are replaced. Write "
        "RESTART: {FINISH_PENDING} and run the row once."
    )


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


def _parse_translations(variables: dict[str, str], pol: str) -> list[dict[str, str]]:
    """Take the ``TRANSLATE`` list out of the flat variables and read its records.

    FR-100, PFS-2034.06: the grammar of ``ROTATE``. Each record states
    ``DISTANCE`` in metres,
    ``AXIS`` as ``<frame>-<X|Y|Z>`` and ``ALIAS``, and may state
    ``AUX_FRAMES``; a key outside those four, a missing one, no alias, a
    distance that is not a finite number and an axis token of another shape are
    refused here, naming the row, so a row is refused at plan time and never
    at the solver. What the names RESOLVE to is the builder's.
    """
    text = variables.pop(TRANSLATE_VARIABLE, None)
    if text is None:
        return []
    records = _parse_records(text, pol, TRANSLATE_VARIABLE, "translation")
    allowed = (*TRANSLATION_RECORD_KEYS, TRANSLATION_ALIAS_KEY, *TRANSLATION_OPTIONAL_KEYS)
    for record in records:
        unknown = sorted(key for key in record if key not in allowed)
        if unknown:
            raise MatrixError(
                f"POL {pol}: {TRANSLATE_VARIABLE} record states {', '.join(unknown)}, which a "
                f"translation does not read; a record holds {', '.join(TRANSLATION_RECORD_KEYS)} "
                f"and {TRANSLATION_ALIAS_KEY}, and optionally "
                f"{', '.join(TRANSLATION_OPTIONAL_KEYS)}."
            )
        written = " / ".join(f"{k}: {v}" for k, v in record.items())
        missing = [key for key in TRANSLATION_RECORD_KEYS if key not in record]
        if missing:
            raise MatrixError(
                f"POL {pol}: {TRANSLATE_VARIABLE} record {{{written}}} states no "
                f"{', '.join(missing)}; every translation states "
                f"{', '.join(TRANSLATION_RECORD_KEYS)}."
            )
        if not record.get(TRANSLATION_ALIAS_KEY, "").strip():
            raise MatrixError(
                f"POL {pol}: {TRANSLATE_VARIABLE} record {{{written}}} says how far to move and "
                f"along what, and nothing to move. State {TRANSLATION_ALIAS_KEY}: <the word the "
                "reference declares>, which is how a rotation and a motion name a set too."
            )
        # FINITE, NOT MERELY PARSEABLE: float() reads nan and inf, and either
        # would reach the solver inside a coordinate.
        try:
            finite = math.isfinite(float(record["DISTANCE"]))
        except ValueError:
            finite = False
        if not finite:
            raise MatrixError(
                f"POL {pol}: {TRANSLATE_VARIABLE} DISTANCE is {record['DISTANCE']!r}, which is not "
                "a finite number; write the distance in metres, as 0.05 or -0.02."
            )
        if not _ROTATION_AXIS.match(record["AXIS"]):
            raise MatrixError(
                f"POL {pol}: {TRANSLATE_VARIABLE} AXIS is {record['AXIS']!r}, which is not of the "
                "form frame-axis; write the frame's name, a hyphen and X, Y or Z (the axis letter "
                "uppercase), as PUSHER_SMRP-X."
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

    Raises
    ------
    MatrixError
        If the file carries the column layout of an earlier release, or a LEGACY row states a raw
        command, a rotation or a translation.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> from pyflightstream.cases.matrix import MATRIX_COLUMNS
    >>> cells = dict.fromkeys(MATRIX_COLUMNS, "NA")
    >>> cells.update(
    ...     POL="9001", HIDDEN="0", RUN="1", AIRCRAFT="Wing", DESCRIPTION="POLAR",
    ...     FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep", SWEEP_VALUES="0.0,2.0",
    ...     FS_BUILD="MANUAL", WORKFLOW="LEGACY",
    ...     VAR_NAMES_VALUES="OUTPUTS: loads_{point}.txt / RECIPE: 003",
    ... )
    >>> path = Path(tempfile.mkdtemp()) / "matrix.fs"
    >>> with path.open("w", encoding="utf-8") as stream:
    ...     print(" | ".join(cells), file=stream)
    ...     print(" | ".join(cells.values()), file=stream)
    >>> [(row.pol, row.run) for row in read_matrix(path)]
    [('9001', 1)]
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
        variables = _fold_columns_into_variables(record, variables, record["POL"])
        _refuse_the_packages_continuation_keys(variables, record["POL"])
        motions = _parse_motions(variables, record["POL"])
        rotations = _parse_rotations(variables, record["POL"])
        translations = _parse_translations(variables, record["POL"])
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
        if translations and record["WORKFLOW"] == LEGACY_WORKFLOW:
            # THE ROTATION'S RULE, FOR THE ROTATION'S REASON (FR-100): a LEGACY
            # row's recipe reads no translation, so the list would move nothing.
            raise MatrixError(
                f"POL {record['POL']} writes LEGACY and states {TRANSLATE_VARIABLE}; a LEGACY "
                "row is built by its own recipe, which reads no translation, so the list would "
                f"move nothing. Name a run type in the WORKFLOW column "
                f"({', '.join(workflow_names())}), which moves what the records name, or drop "
                "the key."
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
        state, attitude = _split_attitude(condition, record["POL"])
        for key in sorted(attitude.keys() & variables.keys()):
            raise MatrixError(
                f"POL {record['POL']}: {key} is stated in FLIGHT_CONDITION as "
                f"{attitude[key]!r} and in VAR_NAMES_VALUES as {variables[key]!r}. "
                "Keep the declaration in FLIGHT_CONDITION only."
            )
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
            sweep=_sweep_of_condition(
                condition,
                record["SWEEP_VALUES"],
                record["POL"],
                error=MatrixError,
            ),
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
            translations=translations,
            raw=raw,
            condition_order=list(condition),
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


def renumber_pols(
    path: str | Path,
    changes: Mapping[int, str],
    *,
    in_place: bool = False,
) -> bytes:
    """Rewrite the POL cell of the named data rows, byte for byte (PFS-2031.21).

    BY ROW, NOT BY VALUE, which is the difference from :func:`rewrite_codes`:
    a POL stated twice in one matrix is two rows with one value, and only the
    second of them moves. Every other cell, the padding of the POL cell where
    it can be kept, the dashed rule and every line ending survive unchanged.

    Parameters
    ----------
    path : str or Path
        The matrix to rewrite, at the verified layout.
    changes : mapping of int to str
        Data row number, counted as :func:`read_matrix` counts it, to the new
        POL. A row number the file does not hold is refused, because a
        renumbering that silently touched nothing reads as done.
    in_place : bool
        Write the rewritten bytes back over ``path``.

    Returns
    -------
    bytes
        The rewritten file.

    Raises
    ------
    MatrixError
        The header does not name the verified layout, a data row holds the
        wrong number of cells, or a row number in ``changes`` is not in the file.
    """
    source = str(path)
    data = Path(path).read_bytes()
    index = _COLUMNS.index("POL")
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    done: set[int] = set()
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            if _header_names(parts) != _COLUMNS:
                raise MatrixError(
                    f"{source} is not a run matrix at the verified layout, so its POL "
                    "cells cannot be found; upgrade it first."
                )
            rebuilt.append(line)
            continue
        row_number += 1
        if row_number in changes:
            if len(parts) != len(_COLUMNS):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells against "
                    f"the {len(_COLUMNS)} verified columns; repair the row first."
                )
            old = parts[index].strip().decode("utf-8", "replace")
            parts[index], _ = _retag_cell(parts[index], {old: str(changes[row_number])})
            done.add(row_number)
        rebuilt.append(b"|".join(parts) + terminator)
    missing = sorted(set(changes) - done)
    if missing:
        raise MatrixError(
            f"{source} holds no data row {', '.join(map(str, missing))}, so nothing was "
            "renumbered there; the file is left as it was."
        )
    rewritten = b"".join(rebuilt)
    if in_place:
        Path(path).write_bytes(rewritten)
    return rewritten


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
    required : bool, optional
        Whether a row that declares no outputs is refused; the migration tool passes False.

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
    require_outputs : bool, optional
        Refuse a row that declares no outputs (the default); :func:`convert_matrix`, the migration
        tool, passes False.
    defer_raw_files : bool, optional
        Leave out a raw-command record that names a file instead of refusing it; only the caller
        that resolves those files against a workspace passes True.

    Returns
    -------
    Campaign
        Native campaign; the matrix codes survive in each case's
        variables (``matrix_ref``, ``matrix_set``, ``matrix_pproc``,
        ``matrix_fs_script``, ``matrix_fs_build``, ``matrix_hidden``,
        ``matrix_workflow``) so the conversion is lossless (FR-11).

    Raises
    ------
    MatrixError
        If a LEGACY row's RECIPE code is missing or not in ``recipes``, a row declares no outputs
        while ``require_outputs`` is true, or a raw-command record names a file while
        ``defer_raw_files`` is false.
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
                condition_order=list(row.condition_order),
                reynolds=_condition_reynolds(row),
                mach=row.flight_condition.get("MACH"),
                sweep=row.sweep,
                recipe=recipe,
                outputs=_declared_outputs(row, required=require_outputs),
                motions=[dict(record) for record in row.motions],
                rotations=[dict(record) for record in row.rotations],
                translations=[dict(record) for record in row.translations],
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

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows convert.
    name : str
        Campaign name, as :func:`to_campaign` takes it.
    fs_version : str
        FlightStream version, as :func:`to_campaign` takes it.
    fs_exe : str
        Explicit executable path.
    recipes : mapping of str to str
        RECIPE code to recipe reference, as :func:`to_campaign` takes it.

    Returns
    -------
    str
        The ``campaign.toml`` text, ending in a newline. A row that declares no outputs converts to
        a case that declares none, with a warning naming it.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> from pyflightstream.cases.matrix import MATRIX_COLUMNS
    >>> cells = dict.fromkeys(MATRIX_COLUMNS, "NA")
    >>> cells.update(
    ...     POL="9001", HIDDEN="0", RUN="1", AIRCRAFT="Wing", DESCRIPTION="POLAR",
    ...     FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep", SWEEP_VALUES="0.0,2.0",
    ...     FS_BUILD="MANUAL", WORKFLOW="LEGACY",
    ...     VAR_NAMES_VALUES="OUTPUTS: loads_{point}.txt / RECIPE: 003",
    ... )
    >>> path = Path(tempfile.mkdtemp()) / "matrix.fs"
    >>> with path.open("w", encoding="utf-8") as stream:
    ...     print(" | ".join(cells), file=stream)
    ...     print(" | ".join(cells.values()), file=stream)
    >>> text = convert_matrix(path, name="polar", fs_version="26.124",
    ...                       fs_exe="FlightStream.exe", recipes={"003": "recipes:build"})
    >>> text.splitlines()[:3]
    ['[campaign]', 'name = "polar"', 'fs_version = "26.124"']
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
        warn(
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
        if sim.condition_order:
            # 0.21.0: the cell's order, which names every point of the case.
            lines.append(f"condition_order = {_toml_value(list(sim.condition_order))}")
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
