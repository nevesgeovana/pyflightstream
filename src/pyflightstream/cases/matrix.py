"""Pipe-delimited run matrix: the reader and the converter.

Pipeline role: keeps the established run-matrix workflow working
unchanged, forever (BRF-08), and promotes the matrix to a first-class
interface of the file-managed modality (v0.3 decision): reading a
matrix and running it is one call,
:func:`pyflightstream.run.matrix.run_matrix`, with the native
``campaign.toml`` model staying the canonical internal form, so
nothing changes for campaign.toml users. The verified layout is read as
is: POL, AIRCRAFT, DESCRIPTION, FLIGHT_CONDITION, SWEEP_TYPE,
SWEEP_VALUES, REF, SET, ENTRY, FS_SCRIPT, FS_BUILD, HIDDEN, RUN,
WORKFLOW, VAR_NAMES_VALUES. Rows with RUN = 1 are active. SWEEP_TYPE names its
axes separated by ``/`` (verified codes: ``AL`` for alpha, ``BE`` for
beta) and SWEEP_VALUES carries one comma-separated value list per
axis, also ``/``-separated; the matrix workflow varies one axis while
the other holds a single value, which broadcasts here.
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

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases import (
    ROTATION_OFFSET_KEY,
    ROTATION_SWEEP_KEY,
    Campaign,
    SimCase,
    SweepAxis,
    multiplied_sweep,
)

# SAME LAYER, so this is a sideways import and not an upward one: both
# modules are `pyflightstream.cases`, and the layer rule
# (`tests.test_conventions`) is about direction. The reader asks the
# registry which types exist rather than keeping a second list, because a
# second list is how a value gets refused for naming a workflow that was
# registered last week.
from pyflightstream.cases.workflows import workflow_names

__all__ = [
    "CODE_COLUMNS",
    "DEFAULT_VERSION_OPTION",
    "LEGACY_WORKFLOW",
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

#: The verified layout, in file order. ``WORKFLOW`` sits at index 13, in
#: front of ``VAR_NAMES_VALUES`` rather than after it, and the position
#: is stated rather than appended: ``VAR_NAMES_VALUES`` is the only cell
#: whose content is free and whose width is not fixed by the format, so
#: it stays last and every fixed-width column stays in front of it.
_COLUMNS = (
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

_SWEEP_CODES = {"AL": "alpha", "BE": "beta"}

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
    ref_code, set_code, entry_code, script_code : str
        The historical 3-digit codes (REF, SET, ENTRY, FS_SCRIPT).
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
    entry_code: str
    script_code: str
    fs_build: str
    hidden: bool
    run: int
    workflow: str
    variables: dict[str, str]


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
    # fluid its author's own scripts pinned and the emitted FLUID_PROPERTIES
    # block carries those numbers and no others. The units ride the keys.
    "RHOkgm3": ("kg/m^3", "density directly, overriding both the atmosphere and REmi"),
    "MUPas": ("Pa s", "dynamic viscosity, which REmi then solves the density against"),
    "ASMPS": ("m/s", "sonic velocity, which MACH is then taken against"),
    "TK": ("kelvin", "temperature, stated rather than lapsed"),
    "PPA": ("pascal", "pressure, stated rather than lapsed"),
}

#: Canonical spelling by upper-cased key, for the case-insensitive match
#: below. Built from the table so the two cannot drift apart.
_FLIGHT_CONDITION_CANONICAL = {key.upper(): key for key in FLIGHT_CONDITION_KEYS}


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
    condition: dict[str, float] = {}
    if not cell.strip():
        return condition
    accepted = ", ".join(FLIGHT_CONDITION_KEYS)
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
        try:
            number = float(value.strip())
        except ValueError:
            raise MatrixError(
                f"FLIGHT_CONDITION key {key} of POL {pol} carries {value.strip()!r}, "
                f"which is not a number. {key} is in {FLIGHT_CONDITION_KEYS[key][0]}."
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


def _parse_sweep(sweep_type: str, sweep_values: str) -> SweepAxis:
    axes = [token.strip() for token in sweep_type.split("/")]
    groups = [token.strip() for token in sweep_values.split("/")]
    unknown = [axis for axis in axes if axis not in _SWEEP_CODES]
    if unknown:
        raise MatrixError(
            f"SWEEP_TYPE code(s) {', '.join(unknown)} are not among the verified "
            f"codes ({', '.join(sorted(_SWEEP_CODES))}); extending the mapping needs "
            "evidence from a matrix that uses the code"
        )
    if len(axes) != len(groups):
        raise MatrixError(
            f"SWEEP_TYPE names {len(axes)} axes but SWEEP_VALUES holds {len(groups)} "
            "value groups; each axis takes one '/'-separated group"
        )
    values = {
        _SWEEP_CODES[axis]: [float(token) for token in group.split(",")]
        for axis, group in zip(axes, groups, strict=True)
    }
    if set(values) == {"alpha", "beta"}:
        alpha, beta = values["alpha"], values["beta"]
        if len(alpha) > 1 and len(beta) == 1:
            beta = beta * len(alpha)
        elif len(beta) > 1 and len(alpha) == 1:
            alpha = alpha * len(beta)
        elif len(alpha) != len(beta):
            raise MatrixError(
                "an AL/BE sweep varies one axis while the other holds a single "
                f"value; got {len(alpha)} alpha and {len(beta)} beta values"
            )
        return SweepAxis(
            type="alpha_beta", values=[list(pair) for pair in zip(alpha, beta, strict=True)]
        )
    axis_name, axis_values = next(iter(values.items()))
    return SweepAxis(type=axis_name, values=axis_values)


def _parse_variables(cell: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    if not cell.strip():
        return variables
    for pair in cell.split("/"):
        name, separator, value = pair.partition(":")
        if not separator:
            raise MatrixError(
                f"variable {pair.strip()!r} is not a KEY:VALUE pair; VAR_NAMES_VALUES "
                "holds '/'-separated KEY:VALUE entries"
            )
        variables[name.strip()] = value.strip()
    return variables


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
            f"the recipe its FS_SCRIPT code names, writes {LEGACY_WORKFLOW}."
        )
    return value


def _check_one_sweep_per_row(pol: str, sweep: SweepAxis, variables: dict[str, str]) -> None:
    """Refuse a row asking for an aerodynamic AND a geometric sweep.

    The DECISION and its reasoning live in
    :func:`pyflightstream.cases.multiplied_sweep`, which is called here
    rather than restated: this function owns only the matrix's own
    vocabulary, so the refusal a matrix user reads names POL,
    ``SWEEP_TYPE`` and the cell they typed instead of naming a
    ``campaign.toml`` field they have never seen.

    The refusal names the fixed-offset form, because the user asking for
    both almost always wants one rotation held fixed across an alpha
    sweep, which is what ``angle_deg`` already does.
    """
    rotation = multiplied_sweep(sweep, variables)
    if not rotation:
        return
    raise MatrixError(
        f"POL {pol} asks for two sweeps at once: the SWEEP_TYPE {sweep.type} sweep of "
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
        known = set(_COLUMNS) | set(_LEGACY_COLUMNS_15) | set(_LEGACY_COLUMNS_16)
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
        row = MatrixRow(
            # From the enumerate above, so it is assigned before the RUN
            # filter below and an inactive row does not shift the numbers
            # of the rows after it (PFS-2009.08.03).
            row_number=row_number,
            pol=record["POL"],
            aircraft=record["AIRCRAFT"],
            description=record["DESCRIPTION"],
            flight_condition=_require_flight_condition(
                record["FLIGHT_CONDITION"], record["POL"], row_number, path
            ),
            sweep=_parse_sweep(record["SWEEP_TYPE"], record["SWEEP_VALUES"]),
            ref_code=record["REF"],
            set_code=record["SET"],
            entry_code=record["ENTRY"],
            script_code=record["FS_SCRIPT"],
            fs_build=record["FS_BUILD"],
            hidden=record["HIDDEN"] == "1",
            run=int(record["RUN"]),
            workflow=_check_workflow(record["WORKFLOW"], record["POL"]),
            variables=_parse_variables(record["VAR_NAMES_VALUES"]),
        )
        # Every row is checked, active or not: the sweep codes and the
        # variable grammar already are, and a refusal a user only meets
        # after flipping RUN to 1 is a refusal that waited.
        _check_one_sweep_per_row(row.pol, row.sweep, row.variables)
        if row.run == 1 or not active_only:
            rows.append(row)
    return rows


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
#: `pyfs-manual` that the author kept, so renaming it here would have
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
    raise MatrixError(
        f"no campaign default version was given for {path}. Every active row names "
        "its own build, so the default answers for nothing today, but it is what a "
        "row added tomorrow with an empty FS_BUILD cell would fall back to, and the "
        "scripts are emitted against a version rather than against an executable. "
        f"Pass {DEFAULT_VERSION_OPTION} <version> (default_fs_version=... in "
        "Python)."
    )


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


def _upgraded_bytes(data: bytes, source: str) -> bytes:
    """Bring a matrix of any earlier layout up to the current one.

    TWO STAGES, because two layouts precede the current one and a file
    written before v0.8.0 needs both: it gains the WORKFLOW column, and
    then its RE and MACH columns fold into FLIGHT_CONDITION. Chaining
    them rather than writing a third direct converter is what keeps the
    oldest path exercised by the same code the newer one uses.
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
        return data
    if header == _LEGACY_COLUMNS_15:
        return _fold_flight_condition(_insert_workflow_cell(data, source), source)
    if header == _LEGACY_COLUMNS_16:
        return _fold_flight_condition(data, source)
    raise MatrixError(
        f"{source} is not a run matrix at a layout this converter upgrades: its "
        f"header names {', '.join(header)}. The layouts it reads are the "
        f"{len(_LEGACY_COLUMNS_15)}-column one that precedes WORKFLOW "
        f"({', '.join(_LEGACY_COLUMNS_15)}) and the {len(_LEGACY_COLUMNS_16)}-column "
        f"one that precedes FLIGHT_CONDITION ({', '.join(_LEGACY_COLUMNS_16)})."
    )


#: The columns whose cells carry an input-library id, in file order.
#: These are the three the kind-letter rule renames (PFS-2009.03); every
#: other column names something that is not a library artifact.
CODE_COLUMNS = ("REF", "SET", "ENTRY")


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
    """Bring a matrix of either older layout up to the current one.

    TWO STAGES, because the format has broken twice and a file written
    before v0.8.0 needs both. A fifteen-column file gains the
    ``WORKFLOW`` cell and then has its ``RE`` and ``MACH`` columns folded
    into one ``FLIGHT_CONDITION`` cell; a sixteen-column file, written
    under v0.8.0 or v0.8.1, needs the fold alone. A file already at the
    current layout is returned unchanged, so running this twice is safe.

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

    Measured 2026-08-03 on the author's own research campaign: a
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
    if not outputs and not required:
        # Conversion is a translation and spends no solver time, so it
        # carries whatever the row declares, including nothing. FR-10
        # scopes "forever" to the external format, which is the promise
        # about the author's existing files, and FR-11 calls conversion
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


def to_campaign(
    path: str | Path,
    *,
    name: str,
    fs_version: str,
    fs_exe: str,
    recipes: Mapping[str, str],
    require_outputs: bool = True,
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
        FS_SCRIPT code to recipe reference (``module:function`` or a
        name registered with the campaign loop); replaces the
        import-by-number system (PP-7, FR-12).

    Returns
    -------
    Campaign
        Native campaign; the matrix codes survive in each case's
        variables (``matrix_ref``, ``matrix_set``, ``matrix_entry``,
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
        if row.script_code not in recipes:
            raise MatrixError(
                f"FS_SCRIPT code {row.script_code!r} of POL {row.pol} has no recipe "
                "mapping; the import-by-number system is replaced by explicit recipe "
                "references: map the code with recipes={code: 'package.module:function'} "
                "in Python, or --recipe CODE=package.module:function on the pyfs-matrix "
                "command line. Or map the code to a run type this package builds "
                "itself, which needs no recipe function at all: name it in recipes "
                "and pass recipe_registry=workflows.workflow_registry(). The command "
                "line spells that same pair as one option, workflow (CLI: --workflow) "
                f"CODE=NAME. Registered run types: {', '.join(workflow_names())}"
            )
        variables: dict[str, str | float | int | bool] = dict(row.variables)
        variables.update(
            matrix_ref=row.ref_code,
            matrix_set=row.set_code,
            matrix_entry=row.entry_code,
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
                recipe=recipes[row.script_code],
                outputs=_declared_outputs(row, required=require_outputs),
                variables=variables,
            )
        )
    return Campaign(name=name, fs_version=fs_version, fs_exe=fs_exe, sims=sims)


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
    # warning below names the rows, so the author's existing matrices
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
        lines.append(
            f"sweep = {{type = {_toml_value(sim.sweep.type)}, "
            f"values = {_toml_value(plain_values)}}}"
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
