"""Anchor-based parsers for FlightStream output files.

Pipeline role: reads solver output text files into typed results.
Values are located by their printed labels (:func:`labeled_value`) and
tables by their header rows (:func:`delimited_table`), never by fixed
line numbers, so cosmetic layout changes between FlightStream versions
do not silently corrupt data (SAD Section 8, PP-4). Completeness is
structural: a missing footer or table terminator raises
:class:`IncompleteOutputError`, never a silently shorter table
(FR-17).

The FlightStream version printed in each output is cross-checked
against the requested version (FR-18). The printed string is coarser
than the canonical scheme: the 26.120 build reports itself as
``Flightstream version 26.1, build #7012026`` (observed in the
committed fixtures), so the check compares by alias prefix and records
the reported string and build verbatim; the build number is the
precise discriminator.

Number forms follow the solver's printing: ``.000`` (no leading
zero), ``4380000.`` (trailing point), and ``1.000E-05`` all parse.

On top of the parsers, a pandas tabular layer turns the parsed
results into DataFrames: :func:`to_table`/:func:`to_csv` for each
parser, :func:`parse_run_loads` for one run's coefficients, and
:func:`run_table`/:func:`sweep_table` for one run or a whole sweep
read from the manifest (the manifest, an execution-layer artifact, is
imported lazily so the layer rule is not violated at module load).

Two vocabularies live here beside the parsers, both because every layer
above needs them and none of them may own them.

:data:`DATA_ORIGIN_CODES` and :data:`REDUCTION_CODES` are the published
answer to "did these numbers come off the run or out of a reduction"
(PFS-2014.05). The tables carry the tokens as columns and the
numeric-only writers carry the integers; the code sets are append only,
because a file written last month is read with this table and cannot be
asked what it meant.

:data:`EXPORT_CONVERSIONS` classifies every ``phase: export`` command of
the database as parsed, excluded, not-an-export or owed (PFS-2014.02),
and the tier 1 suite compares its keys against the live census, so a new
export command fails until somebody says which of the four it is.
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream.versions import FsVersion, known_versions, resolve

_DASHED_LINE = re.compile(r"^-{4,}$")
_SOFTWARE_LINE = re.compile(
    r"Software\s*:\s*Flightstream version\s+(?P<version>\S+),\s*build\s*#(?P<build>\d+)",
    re.IGNORECASE,
)


class MalformedOutputError(PyflightstreamError, ValueError):
    """An output file is present and whole but cannot be read as itself.

    The sibling of :class:`IncompleteOutputError`, and deliberately a
    different type: incomplete means the solver stopped mid-write, this
    means the bytes are all there and do not describe what the file
    claims to be. A duplicated column, a second concatenated export, a
    fractional or negative count, and a token that is not a number all
    land here.

    Added 2026-08-03 for FR-39: these conditions raised a bare
    ``ValueError``, so ``except PyflightstreamError`` did not catch
    them. It keeps ``ValueError`` as a second base, so an existing
    ``except ValueError`` catches exactly what it caught before.
    """


class FieldNotInExportError(PyflightstreamError, KeyError):
    """A named field is not among the columns an export printed.

    ``KeyError`` as the second base, because that is what a mapping
    lookup by name has always raised here and user code catching it
    must keep working (FR-39).
    """

    def __str__(self) -> str:
        """Render the message as prose (KeyError would quote it)."""
        return str(self.args[0]) if self.args else ""


class AnchorNotFoundError(PyflightstreamError, ValueError):
    """A printed label or table header was not found in the output.

    Anchor-based parsing refuses to fall back to line offsets; a
    missing anchor means the file is not the expected kind of output
    or the format changed, and both must surface loudly.
    """


class IncompleteOutputError(PyflightstreamError, ValueError):
    """The output file ends before its structural terminator.

    A loads spreadsheet without its footer or a table without its
    closing dashed line means the solver stopped mid-write; the
    campaign records the point as FAILED_INCOMPLETE_OUTPUT instead of
    consuming a silently shorter table (FR-17).
    """


class VersionMismatchWarning(UserWarning):
    """The version printed in an output disagrees with the requested one.

    Warned, not raised: the run evidence is still recorded, with the
    reported string and build stored verbatim in the manifest (FR-18).
    """


def labeled_value(text: str, label: str) -> str:
    """Return the value printed after a label, located by the label itself.

    Parameters
    ----------
    text : str
        Complete output file text.
    label : str
        Printed label, for example ``"Angle of attack (Deg)"``; the
        first line whose content starts with it provides the value.

    Returns
    -------
    str
        The remainder of the line after the label, stripped.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(label):
            return stripped[len(label) :].strip()
    raise AnchorNotFoundError(
        f"label {label!r} was not found in the output; anchor-based parsing refuses "
        "line offsets, so a missing label means the file is not the expected output "
        "kind or its format changed"
    )


def _optional_labeled_value(text: str, label: str) -> str | None:
    try:
        return labeled_value(text, label)
    except AnchorNotFoundError:
        return None


def parse_number(token: str) -> float:
    """Parse one solver-printed number.

    Accepts the solver's forms: ``.000``, ``4380000.``, ``1.000E-05``,
    and signed values such as ``+0.0002056``.
    """
    try:
        return float(token)
    except ValueError as error:
        raise MalformedOutputError(
            f"{token!r} is not a solver-printed number; expected forms like "
            "'.000', '4380000.', or '1.000E-05'"
        ) from error


def reject_duplicate_columns(columns: Sequence[str], *, what: str) -> None:
    """Refuse a table header that names the same column twice.

    A duplicated name is not a cosmetic problem: the row is read into a
    mapping, so one physical quantity silently takes another's label and
    a column disappears. The loads parser has refused this since
    PYFS-009; the probe parser did not, and the review's reproduction is
    exact (a header rewritten from ``Mach, Cp_ref`` to
    ``Cp_ref, Cp_ref`` returned the Mach value under the Cp label).
    Both call this now, so the two cannot drift apart again
    (REV010-003).

    Parameters
    ----------
    columns : sequence of str
        The header names, already stripped.
    what : str
        Name of the export, for the error message.

    Raises
    ------
    ValueError
        If any normalized name appears more than once.
    """
    seen: dict[str, str] = {}
    repeated: set[str] = set()
    for column in columns:
        key = column.strip().casefold()
        if key in seen:
            repeated.add(seen[key])
        else:
            seen[key] = column
    if repeated:
        raise MalformedOutputError(
            f"the {what} header names {', '.join(sorted(repeated))} more than once, "
            "so a row cannot say which column a value came from: the repeated name "
            "takes the other column's value and that other quantity disappears "
            "entirely. Fix the export, or the field being read is not the field "
            "being named"
        )


def reject_trailing_export(text: str, *, what: str) -> None:
    """Refuse a file that holds a second complete export after the first.

    The footer is located with a first-match search and the table helper
    stops at the first closing separator, so a second normally
    terminated export was simply invisible: the duplicate-total guard
    never saw it and the caller received the first report with no
    indication that another one existed (REV010-006). Appended or stale
    solver output must not be silently ignored, because the consumer
    cannot then know which complete export was intended.

    Parameters
    ----------
    text : str
        Complete file text.
    what : str
        Name of the export, for the error message.

    Raises
    ------
    ValueError
        If the file holds more than one software footer.

    Notes
    -----
    This took a second positional argument, an offset just past the
    first footer, until 2026-08-03. Only the module-private footer
    regex could produce that value, so a public function required
    reading the source to call it, and the offset froze an internal
    convention into the public contract (architect and api-designer
    passes). The function owns the whole rule now: it counts footers
    itself.
    """
    if len(_SOFTWARE_LINE.findall(text)) > 1:
        raise MalformedOutputError(
            f"the {what} holds more than one complete export: a second software "
            "footer follows the first. Only the first was read, so which export "
            "this file is evidence of would have been decided by position rather "
            "than by anything the file says. Two runs were appended, or an earlier "
            "export was never truncated"
        )


def parse_count(token: str, *, label: str, minimum: int = 0, counts: str = "iterations") -> int:
    """Parse a solver-printed COUNT, refusing anything but a whole number.

    Iteration numbers and limits are counts, and every one of them used
    to be read as ``int(parse_number(token))``, which truncates: a
    printed ``312.9`` became 312 and a run's iteration count silently
    lost its fractional part instead of saying that the field it came
    from is not a count at all (PYFS-009). Truncation is the wrong
    failure here because the consequence is a plausible number: nothing
    downstream can tell 312 from a real 312.

    Integrality was the whole guard until REV010-002, which pointed out
    that it is only half of what a count means: ``-1`` is a perfectly
    whole number and not a possible iteration. A negative count printed
    into a loads footer was read, believed, and carried into a
    ``CONVERGED`` assessment. The domain floor is therefore part of the
    parse rather than a check somebody downstream remembers to make.

    Parameters
    ----------
    token : str
        The printed value.
    label : str
        The printed label, named in the error so the reader knows which
        field of which export is malformed.
    minimum : int
        Smallest value this field can physically take. Iteration
        NUMBERS count from zero, which is the default; a REQUESTED
        iteration budget passes ``minimum=1``, because a solve of zero
        iterations is not a solve that could have produced the export
        the number is printed in.
    counts : str
        What the field counts, named in the error message. REV010-007
        routed the FSI sectional parser and the probe parser through
        this function, and the messages went on saying "this field
        counts iterations" about surface sections and probe points,
        which is a didactic-policy defect exactly where it matters
        most, in the terminal a user is standing at (api-designer
        pass, 2026-08-03).

    Returns
    -------
    int
        The value, exactly.

    Raises
    ------
    ValueError
        If the token is not a number at all, is a number with a
        fractional part, or is below ``minimum``.
    """
    value = parse_number(token)
    whole = int(value)
    if value != whole:
        raise MalformedOutputError(
            f"{label} printed {token!r}, which is not a whole number. This field "
            f"counts {counts}, so a fractional value means the export is "
            "malformed or the label matched the wrong line; truncating it would "
            "hand every reader downstream a count that looks ordinary"
        )
    if whole < minimum:
        # Two different impossibilities, so two different sentences. Below
        # zero is a direction error; below one is an existence error, and
        # telling a user that zero surface sections "run backwards" would
        # be worse than saying nothing.
        why = (
            f"{counts} do not run backwards"
            if minimum <= 0
            else f"an export cannot have been produced by fewer than {minimum} of them"
        )
        raise MalformedOutputError(
            f"{label} printed {token!r}, and this field cannot be below {minimum}: "
            f"it counts {counts}, and {why}. A value below the floor means the "
            "export is malformed or the label matched the wrong line, and "
            "accepting it would carry an impossible count into a terminal run "
            "status that reads as ordinary"
        )
    return whole


#: The solver modes this package knows how to judge, canonically lower
#: case. FlightStream prints ``Steady`` or ``Unsteady`` in the loads
#: footer, and the two are judged by entirely different rules: a steady
#: export is judged on its iteration count against the requested budget,
#: an unsteady one is not. Anything else is a mode this package has
#: never seen, so it cannot know which rule applies (REV010-002).
SOLVER_MODES: tuple[str, ...] = ("steady", "unsteady")


def classify_solver_mode(printed: str) -> str | None:
    """Return the canonical solver mode, or None when it is unknown.

    The printed string is kept on the report as evidence; this is the
    single place that decides whether the package recognizes it.

    Parameters
    ----------
    printed : str
        The value printed after ``Solver mode:``, as parsed.

    Returns
    -------
    str or None
        One of :data:`SOLVER_MODES`, or None when the printed value is
        not a mode this package knows. None is not an error here: the
        caller decides what an unrecognized mode means for its own
        judgment, and the assessor maps it to incomplete output rather
        than guessing a rule.
    """
    candidate = printed.strip().lower()
    return candidate if candidate in SOLVER_MODES else None


# --- provenance vocabulary: raw off the run, or out of a reduction ---------
#
# PFS-2014.05, her requirement of 2026-08-16. A sweep table carries one row
# per point, and in a mixed campaign a steady point's row holds a direct
# integration while an unsteady point's row holds a time average. Same
# column, two different quantities, and a reader who cannot tell them apart
# reads a method difference as physics.
#
# The vocabulary lives HERE rather than in the table module because it is
# published in every result file the package writes, tabular or not: the
# tables carry the tokens as columns and the numeric-only writers carry the
# integer codes. Both live above this layer, so one home below them is the
# only place neither has to copy.
#
# THE TOKENS AND THEIR CODES ARE THE AUTHOR'S CALL and are built here under
# the lane's default, which she has not yet ruled on; the vocabulary is a
# proposal until she does, and NFR-19 is where its status is tracked. Two
# origin tokens, three reduction
# tokens; a row with no loads report says ``unknown`` rather than ``none``,
# because ``none`` would assert a direct integration that never happened; and
# an unsteady solver export counts as ``raw``, because the solver did the
# averaging and the reduction token is what names it.

#: What produced the numbers in a row or a file, and the integer each token
#: is published as in the numeric-only formats. APPEND ONLY: a published
#: integer never changes meaning, because a file written last month is read
#: with this table and cannot be asked what it meant.
DATA_ORIGIN_CODES: dict[str, int] = {"raw": 0, "reduced": 1}

#: Which reduction produced them, on the same append-only rule.
#: ``none`` is a direct integration the solver printed, ``time_average`` is
#: an average over a window, and ``unknown`` is a row whose mode was never
#: printed at all. ``unknown`` is deliberately a WORD and not an empty cell:
#: an empty cell reads back out of a csv as NaN, so the identifier would not
#: survive its own file.
REDUCTION_CODES: dict[str, int] = {"none": 0, "time_average": 1, "unknown": 2}

#: The two column labels, named once so no writer spells them itself.
DATA_ORIGIN_COLUMN = "data_origin"
REDUCTION_COLUMN = "reduction"

#: Both labels together, in the order they are written.
PROVENANCE_COLUMNS: tuple[str, str] = (DATA_ORIGIN_COLUMN, REDUCTION_COLUMN)


def origin_code(token: str) -> int:
    """Return the published integer of one ``data_origin`` token.

    Parameters
    ----------
    token : str
        One key of :data:`DATA_ORIGIN_CODES`.

    Returns
    -------
    int
        The integer the numeric-only formats carry.

    Raises
    ------
    MalformedOutputError
        When the token is not one this package publishes. Refused rather
        than passed through, because an unrecognised token written into a
        file is an identifier that identifies nothing.
    """
    try:
        return DATA_ORIGIN_CODES[token]
    except KeyError:
        raise MalformedOutputError(
            f"{token!r} is not a data origin this package publishes; the tokens are "
            f"{', '.join(sorted(DATA_ORIGIN_CODES))}. 'raw' means the numbers came off "
            "the run as the solver printed them, 'reduced' that post-processing "
            "produced them"
        ) from None


def reduction_code(token: str) -> int:
    """Return the published integer of one ``reduction`` token.

    Parameters
    ----------
    token : str
        One key of :data:`REDUCTION_CODES`.

    Returns
    -------
    int
        The integer the numeric-only formats carry.

    Raises
    ------
    MalformedOutputError
        When the token is not one this package publishes.
    """
    try:
        return REDUCTION_CODES[token]
    except KeyError:
        raise MalformedOutputError(
            f"{token!r} is not a reduction this package publishes; the tokens are "
            f"{', '.join(sorted(REDUCTION_CODES))}. 'none' is a direct integration, "
            "'time_average' an average over a window, and 'unknown' a row whose solver "
            "mode was never printed"
        ) from None


def reduction_for_solver_mode(printed: str | None) -> str:
    """Name the reduction behind a row, from the solver mode it printed.

    The single place the mapping is decided, so the sweep table, the
    per-parser tables and the numeric-only writers cannot disagree about
    what an unsteady export's coefficients are.

    Parameters
    ----------
    printed : str or None
        The value printed after ``Solver mode:``, as parsed, or None when
        the row carries no loads report at all (a failed point).

    Returns
    -------
    str
        One key of :data:`REDUCTION_CODES`. A steady export is ``none``,
        an unsteady one ``time_average``, and anything else ``unknown``:
        a mode this package has never seen is a mode whose reduction it
        cannot name, and guessing ``none`` would assert a direct
        integration that never happened.
    """
    if printed is None:
        return "unknown"
    mode = classify_solver_mode(printed)
    if mode == "steady":
        return "none"
    if mode == "unsteady":
        return "time_average"
    return "unknown"


# --- which solver exports this package can read ----------------------------
#
# PFS-2014.02, her scoping of 2026-08-16. The census of ``phase: export``
# commands CANNOT be the default set: two of the eighteen entries export
# nothing at all (they set the VTK variable list and delete a profile), so
# the classification has to be explicit data rather than a filter.
#
# The keys are compared against the live command database by
# ``tests/test_results.py``, so an export command added to any yaml fails
# the suite until it is classified here.

#: The export has a parser and a tabular conversion in this package.
EXPORT_PARSED = "parsed"

#: A structured format deliberately outside the default set (her scoping of
#: 2026-08-16): Tecplot, VTK and Nastran files are read by their own tools,
#: and flattening one to a table loses the structure that made it worth
#: exporting. Converted only when the user names it in the optional
#: variables.
EXPORT_EXCLUDED = "excluded"

#: The command carries ``phase: export`` and writes no data file of its own.
EXPORT_NOT_AN_EXPORT = "not_an_export"

#: In the default set, and this package cannot read it yet. The debt, named
#: one command at a time, because a count nobody can enumerate is not a debt.
EXPORT_OWED = "owed"

#: Every verdict an entry of :data:`EXPORT_CONVERSIONS` may carry.
EXPORT_VERDICTS: tuple[str, ...] = (
    EXPORT_PARSED,
    EXPORT_EXCLUDED,
    EXPORT_NOT_AN_EXPORT,
    EXPORT_OWED,
)


@dataclass(frozen=True)
class ExportConversion:
    """How one ``phase: export`` command's output is read, if at all.

    Attributes
    ----------
    verdict : str
        One of :data:`EXPORT_VERDICTS`.
    parser : str or None
        Dotted path of the callable that reads the file, for a
        ``parsed`` verdict; None otherwise. A dotted STRING rather than
        the callable itself, because the sectional-loads parser ships
        with the optional ``[fsi]`` extra and naming it here must not
        make this module require it.
    format : str or None
        The structured format an ``excluded`` entry writes (``tecplot``,
        ``vtk`` or ``nastran``), named so the refusal can say which tool
        already reads it; None otherwise.
    note : str
        Why this entry has the verdict it has, in one sentence.
    """

    verdict: str
    parser: str | None
    format: str | None
    note: str


#: Every ``phase: export`` command of the database, classified. Measured
#: against the live census on 2026-08-19: eighteen entries, four parsed,
#: five excluded, two that export nothing, seven owed.
EXPORT_CONVERSIONS: dict[str, ExportConversion] = {
    "EXPORT_SOLVER_ANALYSIS_SPREADSHEET": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_loads",
        None,
        "the coefficient table every campaign point exports",
    ),
    "EXPORT_PROBE_POINTS": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_probe_points",
        None,
        "the probe survey, read under its printed column names",
    ),
    "UNSTEADY_SOLVER_EXPORT_PLOTS": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_unsteady_plots",
        None,
        "one row per time step; the entry is documented, not verified",
    ),
    "EXPORT_SURFACE_SECTIONAL_LOADS": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.fsi.loads.parse_sectional_loads",
        None,
        "spanwise load densities; ships with the optional [fsi] extra",
    ),
    "EXPORT_SOLVER_ANALYSIS_TECPLOT": ExportConversion(
        EXPORT_EXCLUDED, None, "tecplot", "read by Tecplot itself"
    ),
    "EXPORT_VOLUME_SECTION_TECPLOT": ExportConversion(
        EXPORT_EXCLUDED, None, "tecplot", "read by Tecplot itself"
    ),
    "EXPORT_SOLVER_ANALYSIS_VTK": ExportConversion(
        EXPORT_EXCLUDED, None, "vtk", "read by ParaView and every VTK reader"
    ),
    "EXPORT_VOLUME_SECTION_VTK": ExportConversion(
        EXPORT_EXCLUDED, None, "vtk", "read by ParaView and every VTK reader"
    ),
    "EXPORT_SOLVER_ANALYSIS_PLOAD_BDF": ExportConversion(
        EXPORT_EXCLUDED, None, "nastran", "a Nastran bulk-data deck, read by the solver it feeds"
    ),
    "SET_VTK_EXPORT_VARIABLES": ExportConversion(
        EXPORT_NOT_AN_EXPORT, None, None, "chooses the variables a later VTK export writes"
    ),
    "DELETE_BL_VELOCITY_PROFILE": ExportConversion(
        EXPORT_NOT_AN_EXPORT, None, None, "deletes a profile; it writes no file"
    ),
    "EXPORT_SOLVER_ANALYSIS_CSV": ExportConversion(
        EXPORT_OWED, None, None, "a csv whose columns nobody here has pinned yet"
    ),
    "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS": ExportConversion(
        EXPORT_OWED, None, None, "force distributions, no observed export captured"
    ),
    "EXPORT_BL_VELOCITY_PROFILE": ExportConversion(
        EXPORT_OWED, None, None, "boundary-layer velocity profile, no observed export captured"
    ),
    "EXPORT_ALL_OFF_BODY_STREAMLINES": ExportConversion(
        EXPORT_OWED, None, None, "off-body streamlines, no observed export captured"
    ),
    "EXPORT_SURFACE_SECTIONS": ExportConversion(
        EXPORT_OWED, None, None, "the section geometry, no observed export captured"
    ),
    "EXPORT_ALL_SURFACE_SECTIONS": ExportConversion(
        EXPORT_OWED, None, None, "every section's geometry, no observed export captured"
    ),
    "SWEEPER_EXPORT_SPREADSHEET": ExportConversion(
        EXPORT_OWED, None, None, "the sweeper's own spreadsheet, no observed export captured"
    ),
}


def export_conversion(command: str) -> ExportConversion:
    """Return how one export command's output is read, refusing an unknown.

    Parameters
    ----------
    command : str
        Command name as the database spells it, for example
        ``"EXPORT_PROBE_POINTS"``.

    Returns
    -------
    ExportConversion
        The classification.

    Raises
    ------
    FieldNotInExportError
        When the name is not a classified export command.

    Examples
    --------
    >>> from pyflightstream.results import export_conversion
    >>> export_conversion("EXPORT_PROBE_POINTS").parser
    'pyflightstream.results.parse_probe_points'
    """
    try:
        return EXPORT_CONVERSIONS[command]
    except KeyError:
        raise FieldNotInExportError(
            f"{command!r} is not a classified export command of this package; the "
            "classification covers every phase: export entry of the command database "
            "and is compared against it by the tier 1 suite"
        ) from None


def require_export_parser(command: str) -> str:
    """Return the parser of one export command, or refuse naming the format.

    The refusal is the point of this function: a conversion that is not
    available must SAY so, naming the format and the reason, rather than
    being skipped and leaving a caller with a shorter set of tables than
    it asked for.

    Parameters
    ----------
    command : str
        Command name as the database spells it.

    Returns
    -------
    str
        Dotted path of the parser callable.

    Raises
    ------
    FieldNotInExportError
        When the name is not a classified export command.
    MalformedOutputError
        When the command has no converter: an excluded structured format,
        a command that exports nothing, or one whose parser is still
        owed. The message names which of the three it is.
    """
    entry = export_conversion(command)
    if entry.parser is not None:
        return entry.parser
    if entry.verdict == EXPORT_EXCLUDED:
        raise MalformedOutputError(
            f"{command} writes a {entry.format} file, which is outside the default "
            f"conversion set on purpose ({entry.note}): flattening it to a table loses "
            "the structure that made it worth exporting. Name it in the optional "
            "variables to convert it anyway"
        )
    if entry.verdict == EXPORT_NOT_AN_EXPORT:
        raise MalformedOutputError(
            f"{command} carries phase: export and writes no data file of its own "
            f"({entry.note}), so there is nothing to convert"
        )
    raise MalformedOutputError(
        f"{command} is in the default conversion set and this package cannot read it "
        f"yet ({entry.note}); PFS-2014.02 owes the parser, and it needs one real "
        "export from a licensed run to pin the columns against"
    )


def delimited_table(text: str, header_anchor: str, delimiter: str | None = ",") -> list[list[str]]:
    """Read a table's data rows, from its header row to its terminator.

    The table is located by the first line starting with
    ``header_anchor``; dashed separator lines after the header are
    skipped, and rows accumulate until the closing dashed line. The
    terminator is structural: reaching the end of the text without it
    raises :class:`IncompleteOutputError` (FR-17).

    Parameters
    ----------
    text : str
        Complete output file text.
    header_anchor : str
        Start of the header row, for example ``"Surface,"`` for the
        loads table or ``"Iteration"`` for the log residual table.
    delimiter : str or None
        Cell separator of the data rows; None splits on any
        whitespace (the log tables are tab separated).

    Returns
    -------
    list of list of str
        One list of stripped cells per data row.
    """
    lines = iter(text.splitlines())
    for line in lines:
        if line.strip().startswith(header_anchor):
            break
    else:
        raise AnchorNotFoundError(
            f"table header {header_anchor!r} was not found in the output; tables are "
            "located by their header rows, never by line numbers"
        )
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _DASHED_LINE.match(stripped):
            if rows:
                return rows
            continue
        cells = stripped.split(delimiter) if delimiter else stripped.split()
        rows.append([cell.strip() for cell in cells])
    raise IncompleteOutputError(
        f"the table under {header_anchor!r} has no closing separator line; the file "
        "ends mid-table, so the solver stopped before finishing this output"
    )


@dataclass(frozen=True)
class LoadsReport:
    """Typed content of one aerodynamic loads spreadsheet.

    The spreadsheet is the primary quantitative output of a run
    (EXPORT_SOLVER_ANALYSIS_SPREADSHEET, SRC-003 p.352). Coefficients
    are expressed in the analysis frame named by ``frame``; forces
    follow ``force_units`` and moments ``moment_units``.

    Attributes
    ----------
    angle_of_attack_deg : float
        Angle of attack in deg.
    sideslip_deg : float
        Side-slip angle in deg.
    freestream_velocity_m_s : float
        Free-stream velocity in m/s.
    requested_iterations : int
        Solver iteration limit of the run.
    convergence_limit : float
        Residual threshold declaring convergence.
    solver_mode : str
        ``Steady`` or ``Unsteady`` as printed.
    current_iteration : int
        Iteration counter at export time.
    solver_model : str or None
        Solver model as printed, when present.
    forced_iterations : bool or None
        Whether the solver was forced to run all iterations.
    reference_velocity_m_s, reference_length, reference_area : float or None
        Coefficient normalization references, in the printed units.
    reynolds : float or None
        Reynolds number of the condition.
    frame : str or None
        Coordinate frame of the analysis.
    surfaces : dict of str to dict of str to float
        Per-surface coefficients, keyed surface name then column name
        (Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz).
    total : dict of str to float
        The Total row, same columns.
    force_units, moment_units : str
        Units of the force and moment columns as printed.
    fs_version_reported : str
        Version string printed in the footer, verbatim.
    fs_build : str
        Build number printed in the footer, verbatim.
    """

    angle_of_attack_deg: float
    sideslip_deg: float
    freestream_velocity_m_s: float
    requested_iterations: int
    convergence_limit: float
    solver_mode: str
    current_iteration: int
    solver_model: str | None
    forced_iterations: bool | None
    reference_velocity_m_s: float | None
    reference_length: float | None
    reference_area: float | None
    reynolds: float | None
    frame: str | None
    surfaces: dict[str, dict[str, float]]
    total: dict[str, float]
    force_units: str
    moment_units: str
    fs_version_reported: str
    fs_build: str

    def diverged_columns(self) -> list[str]:
        """Return the Total columns holding NaN or infinite values."""
        return [
            column for column, value in self.total.items() if math.isnan(value) or math.isinf(value)
        ]


#: The tokens the solver prints for a boolean flag in an export footer,
#: observed on 26.120 and 26.121. Enumerated rather than sniffed: the
#: reading used to be ``token.upper().startswith("T")``, which mapped
#: every unrecognised token to False in silence, so a footer printing
#: "yes" or a label that matched the wrong line reported the flag OFF
#: with the same confidence as a real F (PYFS-009). A flag read wrongly
#: as off is worse than an unreadable one, because a run then carries a
#: setting it did not have.
_TRUE_TOKENS = frozenset({"T", "TRUE"})
_FALSE_TOKENS = frozenset({"F", "FALSE"})


def _parse_solver_flag(token: str | None, label: str) -> bool | None:
    """Read a printed solver flag, or None when the footer omits it."""
    if token is None:
        return None
    normalized = token.strip().upper()
    if normalized in _TRUE_TOKENS:
        return True
    if normalized in _FALSE_TOKENS:
        return False
    raise ValueError(
        f"{label} printed {token!r}, which is not one of the tokens the solver "
        f"uses for this flag ({', '.join(sorted(_TRUE_TOKENS | _FALSE_TOKENS))}). "
        "An unrecognised token used to read as off, so a run carried a setting it "
        "did not have; if this is a real solver spelling, add it here with the "
        "export that printed it"
    )


def parse_loads(text: str, requested_version: str | FsVersion | None = None) -> LoadsReport:
    """Parse one aerodynamic loads spreadsheet.

    Parameters
    ----------
    text : str
        Complete file text.
    requested_version : str, FsVersion, or None
        When given, the version printed in the footer is cross-checked
        against it by alias prefix (the printed string is coarser than
        the canonical scheme; see the module docstring) and a
        :class:`VersionMismatchWarning` is issued on inconsistency
        (FR-18).

    Returns
    -------
    LoadsReport
        Typed report; the footer and the table terminator are
        structural, so an incomplete file raises
        :class:`IncompleteOutputError` instead of returning less.
    """
    software = _SOFTWARE_LINE.search(text)
    if software is None:
        raise IncompleteOutputError(
            "the loads spreadsheet has no software footer; the file ends before the "
            "closing block, so the solver stopped before finishing this export"
        )
    # REV010-006. The footer above is a FIRST-match search and the table
    # helper stops at the first closing separator, so a second complete
    # export was invisible to every guard below, including the duplicate
    # Total refusal that exists for exactly this class of confusion.
    reject_trailing_export(text, what="loads spreadsheet")
    header_cells = labeled_value(text, "Surface,")
    columns = [cell.strip() for cell in header_cells.split(",") if cell.strip()]
    # PYFS-009, now shared with the probe parser (REV010-003). A repeated
    # column name used to build the row dict with the later value winning,
    # so a header naming CL twice lost CDi ENTIRELY and published CDi's
    # number under CL. Every coefficient downstream then read a plausible
    # value from the wrong column, and nothing anywhere said so.
    reject_duplicate_columns(columns, what="loads")
    rows = delimited_table(text, "Surface,")
    surfaces: dict[str, dict[str, float]] = {}
    total: dict[str, float] | None = None
    for row in rows:
        name, values = row[0], row[1:]
        if len(values) != len(columns):
            raise MalformedOutputError(
                f"loads row for {name!r} holds {len(values)} values but the header "
                f"names {len(columns)} columns; the table layout changed"
            )
        parsed = {
            column: parse_number(value) for column, value in zip(columns, values, strict=True)
        }
        if name.lower() == "total":
            # PYFS-009. A second Total row used to overwrite the first in
            # silence, so a concatenated or double-exported file published
            # whichever total came last as though it were the only one.
            if total is not None:
                raise MalformedOutputError(
                    "the loads table holds more than one Total row, so which total the "
                    "run produced is not determined by the file. Two exports were "
                    "concatenated, or the table was written twice; the second used to "
                    "replace the first without a word"
                )
            total = parsed
        else:
            if name in surfaces:
                raise MalformedOutputError(
                    f"the loads table names the surface {name!r} more than once, so "
                    "its coefficients are not determined by the file: the later row "
                    "used to replace the earlier and the report carried one surface "
                    "where the solver reported two"
                )
            surfaces[name] = parsed
    if total is None:
        raise IncompleteOutputError(
            "the loads table has no Total row; per-surface rows without the closing "
            "Total mean the export stopped mid-table"
        )
    forced = _optional_labeled_value(text, "Force solver to run all iterations")
    reported = software.group("version")
    if requested_version is not None:
        _cross_check_version(reported, requested_version, software.group("build"))
    return LoadsReport(
        angle_of_attack_deg=parse_number(labeled_value(text, "Angle of attack (Deg)")),
        sideslip_deg=parse_number(labeled_value(text, "Side-slip angle (Deg)")),
        freestream_velocity_m_s=parse_number(labeled_value(text, "Freestream velocity (m/s)")),
        requested_iterations=parse_count(
            labeled_value(text, "Requested solver iterations"),
            label="Requested solver iterations",
            minimum=1,
        ),
        convergence_limit=parse_number(labeled_value(text, "Solver convergence limit")),
        solver_mode=labeled_value(text, "Solver mode:"),
        current_iteration=parse_count(
            labeled_value(text, "Current solver iteration number:"),
            label="Current solver iteration number",
        ),
        solver_model=_optional_labeled_value(text, "Solver model:"),
        forced_iterations=_parse_solver_flag(forced, "Force solver to run all iterations"),
        reference_velocity_m_s=_optional_number(text, "Reference velocity (m/s)"),
        reference_length=_optional_number(text, "Reference length (m)"),
        reference_area=_optional_number(text, "Reference area (m^2)"),
        reynolds=_optional_number(text, "Reynolds Number"),
        frame=_optional_labeled_value(text, "Coordinate frame for analysis:"),
        surfaces=surfaces,
        total=total,
        force_units=labeled_value(text, "Force Units:"),
        moment_units=labeled_value(text, "Moment Units:"),
        fs_version_reported=reported,
        fs_build=software.group("build"),
    )


def _optional_number(text: str, label: str) -> float | None:
    value = _optional_labeled_value(text, label)
    return None if value is None else parse_number(value)


def _cross_check_version(
    reported: str, requested: str | FsVersion, reported_build: str | None = None
) -> None:
    """Warn when the solver that ran is not the one the run asked for.

    Two checks, and the BUILD one is the load-bearing half. The version
    string a solver prints does not identify a build: every registered
    26.1x prints "26.1", so comparing it cannot tell 26.120 from 26.121,
    and those two are recorded differently: AIR_ALTITUDE is broken on
    26.120 and verified on 26.121 (RPT-014, which declines to attribute
    the change to the build, because the harness and the session file
    moved with it). Whatever the cause, the two builds cannot be told
    apart by the printed version string, so where the registry records
    the build number, that is what is compared.

    The version-string check stays as the fallback for a version with no
    registered build, and it still catches the coarse case of running a
    26.0 executable for a 26.1 campaign.

    Parameters
    ----------
    reported : str
        Version string printed in the output footer, verbatim.
    requested : str or FsVersion
        Version the run asked for.
    reported_build : str, optional
        Build number printed in the same footer, without the leading
        ``#``. When absent, only the version string is checked.
    """
    version = resolve(requested)
    if version.build is not None and reported_build is not None:
        if reported_build != version.build:
            warnings.warn(
                f"the output was produced by FlightStream build #{reported_build}, but "
                f"the run requested {version.canonical}, which is build "
                f"#{version.build}; the wrong executable ran. The version string alone "
                f"cannot show this, because both print {reported!r}: check the fs_exe "
                "path against the installation of the version the campaign names. The "
                "reported string and build are recorded verbatim in the manifest "
                "(FR-18).",
                VersionMismatchWarning,
                stacklevel=3,
            )
        return
    alias = version.alias
    consistent = alias == reported or alias.startswith(reported) or reported.startswith(alias)
    if not consistent:
        warnings.warn(
            f"the output reports FlightStream {reported!r} but the run requested "
            f"{alias!r}; the wrong executable may have run. The reported string and "
            "build are recorded verbatim in the manifest (FR-18).",
            VersionMismatchWarning,
            stacklevel=3,
        )
    elif version.build is None and _shares_alias(version):
        warnings.warn(
            f"the output reports FlightStream {reported!r}, which cannot confirm that "
            f"{version.canonical} ran: its vendor name is shared with "
            f"{', '.join(other.canonical for other in _shares_alias(version))} and no "
            "build number is registered for it, so nothing here distinguishes the "
            f"builds. The output's own build is #{reported_build or 'not printed'}; "
            "register it in commands/_meta.yaml from a committed report to close this.",
            VersionMismatchWarning,
            stacklevel=3,
        )


def _shares_alias(version: FsVersion) -> tuple[FsVersion, ...]:
    """Other registered versions carrying the same vendor release name."""
    return tuple(
        other
        for other in known_versions()
        if other.alias == version.alias and other.canonical != version.canonical
    )


@dataclass(frozen=True)
class ResidualSample:
    """One row of the solver residual history.

    Attributes
    ----------
    iteration : int
        Solver iteration number.
    velocity_residual : float
        Surface velocity residual, dimensionless.
    pressure_residual : float
        Surface pressure residual, dimensionless.
    """

    iteration: int
    velocity_residual: float
    pressure_residual: float


def parse_residual_history(text: str) -> list[ResidualSample]:
    """Parse the residual table of an exported solver log.

    The log's iteration table carries the velocity and pressure
    residuals the convergence threshold applies to (SRC-003 p.200);
    the final row is the convergence evidence of the run.

    Parameters
    ----------
    text : str
        Complete log text (EXPORT_LOG output or captured log file).

    Returns
    -------
    list of ResidualSample
        The history in iteration order; the first three columns of
        each row (iteration, velocity residual, pressure residual)
        are parsed, further columns vary with the run setup.
    """
    # Real hidden-mode log exports carry stray NUL bytes between lines
    # (observed on 26.120 build 7012026); scrub them before parsing.
    rows = delimited_table(text.replace("\x00", ""), "Iteration", delimiter=None)
    history: list[ResidualSample] = []
    for row in rows:
        if len(row) < 3:
            raise MalformedOutputError(
                f"residual row {row!r} holds fewer than three columns (iteration, "
                "velocity residual, pressure residual); the log table layout changed"
            )
        iteration = parse_count(row[0], label="the residual table's iteration counter")
        # PYFS-009. The counter was read and never checked, so a history of
        # [1, 2, 1574, 2] parsed clean. That shape is two runs' logs
        # concatenated, or a table that wrapped, and the CONVERGENCE JUDGMENT
        # READS THE LAST ROW: the run would be judged on a residual belonging
        # to an earlier iteration of a different solve. A monotonic counter is
        # what makes "the last row" mean "the final state".
        if history and iteration <= history[-1].iteration:
            raise MalformedOutputError(
                f"the residual table's iteration counter goes from "
                f"{history[-1].iteration} to {iteration}, so it does not increase. "
                "The final row is the convergence evidence of the run, and it is only "
                "the final state if the counter orders the table; a repeat or a "
                "decrease means two logs were concatenated or the table wrapped"
            )
        history.append(
            ResidualSample(
                iteration=iteration,
                velocity_residual=parse_number(row[1]),
                pressure_residual=parse_number(row[2]),
            )
        )
    if not history:
        raise IncompleteOutputError("the log residual table is empty")
    return history


@dataclass(frozen=True)
class ProbePointsReport:
    """Parsed EXPORT_PROBE_POINTS output (SRC-003 pp.362-363, p.249).

    Rows follow the probe creation order: the 26.120 round-trip
    evidence (reports/RPT-004) shows the solver preserves the count
    and row order of imported probes, which is what lets a
    :class:`~pyflightstream.probes.planar.PlannedProbes` plan map rows
    back to grid nodes.

    Attributes
    ----------
    columns : tuple of str
        Column names as printed, starting with X, Y, Z (simulation
        length units, reference frame).
    values : numpy.ndarray
        The full table, shape ``(count, len(columns))``, in printed
        order.
    angle_of_attack_deg : float
        Angle of attack of the exported solution (deg).
    freestream_velocity_m_s : float
        Free-stream velocity (m/s).
    current_iteration : int
        Solver iteration the export reflects.
    reported_version : str
        Version string printed in the footer, verbatim.
    reported_build : str
        Build number printed in the footer, verbatim (the precise
        discriminator, FR-18).
    """

    columns: tuple[str, ...]
    values: np.ndarray
    angle_of_attack_deg: float
    freestream_velocity_m_s: float
    current_iteration: int
    reported_version: str
    reported_build: str

    @property
    def count(self) -> int:
        """Number of probe rows."""
        return len(self.values)

    @property
    def positions(self) -> np.ndarray:
        """Probe positions, shape ``(count, 3)``: the X, Y, Z columns."""
        return self.values[:, :3]

    def field(self, name: str) -> np.ndarray:
        """Return one named column as an array.

        Parameters
        ----------
        name : str
            Printed column name, for example ``"vtot"`` or ``"Cp"``.
        """
        try:
            index = self.columns.index(name)
        except ValueError as error:
            raise FieldNotInExportError(
                f"column {name!r} is not in this export; available: {', '.join(self.columns)}"
            ) from error
        return self.values[:, index]

    def fields(self) -> dict[str, np.ndarray]:
        """All non-coordinate columns, keyed by printed name.

        Drops straight into the flow-visualization writers of
        :mod:`pyflightstream.post`.
        """
        return {name: self.field(name) for name in self.columns[3:]}


def parse_probe_points(text: str, requested_version=None) -> ProbePointsReport:
    """Parse an EXPORT_PROBE_POINTS file into a typed report.

    Anchor-based like every parser here: the point count is read from
    its printed label, the table from its ``X, Y, Z,`` header to the
    closing dashed line, and a declared-versus-parsed row mismatch
    raises instead of returning less (FR-17). The boundary-layer
    columns are part of the table; with the viscous coupling off they
    are inert zeros, and asserting that is the caller's business
    (DLV-006 Sec. 2.3).

    Parameters
    ----------
    text : str
        Complete export file text.
    requested_version : str or FsVersion, optional
        Version the run requested; when given, the printed version is
        cross-checked and a mismatch warns (FR-18).

    Returns
    -------
    ProbePointsReport
        Typed table plus the solution metadata.
    """
    text = text.replace("\x00", "")
    software = _SOFTWARE_LINE.search(text)
    if software is None:
        raise IncompleteOutputError(
            "the probe export has no software footer; the file ends before the "
            "closing block, so the solver stopped before finishing this export"
        )
    declared = parse_count(
        labeled_value(text, "Number of Probe Points:"),
        label="Number of Probe Points",
        counts="probe points",
    )
    header_line = next(
        (line.strip() for line in text.splitlines() if line.strip().startswith("X, Y, Z,")),
        None,
    )
    if header_line is None:
        raise AnchorNotFoundError(
            "the probe table header 'X, Y, Z,' was not found; the file is not an "
            "EXPORT_PROBE_POINTS output or its format changed"
        )
    columns = tuple(cell.strip() for cell in header_line.split(",") if cell.strip())
    # REV010-003. The loads parser has refused a repeated column since
    # PYFS-009 and this one never did, although the consequence here is
    # worse: field() returns the FIRST tuple index of a name and fields()
    # collapses duplicates into one key, so a header rewritten to name
    # Cp_ref twice returned the Mach value under the Cp label. A pressure
    # coefficient reading 0.086 is not obviously wrong to anyone.
    reject_duplicate_columns(columns, what="probe export")
    reject_trailing_export(text, what="probe export")
    rows = delimited_table(text, "X, Y, Z,")
    parsed_rows = []
    for row in rows:
        cells = [cell for cell in row if cell]
        if len(cells) != len(columns):
            raise MalformedOutputError(
                f"a probe row holds {len(cells)} values but the header names "
                f"{len(columns)} columns; the table layout changed"
            )
        parsed_rows.append([parse_number(cell) for cell in cells])
    if len(parsed_rows) != declared:
        raise IncompleteOutputError(
            f"the export declares {declared} probe points but the table holds "
            f"{len(parsed_rows)} rows; the solver stopped mid-write"
        )
    if requested_version is not None:
        _cross_check_version(software.group("version"), requested_version, software.group("build"))
    return ProbePointsReport(
        columns=columns,
        values=np.asarray(parsed_rows, dtype=float),
        angle_of_attack_deg=parse_number(labeled_value(text, "Angle of attack (Deg)")),
        freestream_velocity_m_s=parse_number(labeled_value(text, "Freestream velocity (m/s)")),
        current_iteration=parse_count(
            labeled_value(text, "Current solver iteration number:"),
            label="the probe export's iteration counter",
        ),
        reported_version=software.group("version"),
        reported_build=software.group("build"),
    )


@dataclass(frozen=True)
class UnsteadyPlotsReport:
    """Parsed UNSTEADY_SOLVER_EXPORT_PLOTS output, one row per time step.

    The only file this package reads that carries a HISTORY rather than
    a converged state: the loads spreadsheet and the probe export each
    describe one instant, and the residual log counts iterations rather
    than physical time.

    GROUNDING, and read it before trusting a column: the shape comes
    from the command's manual paraphrase (SRC-003 p.347, one column per
    plot and one row per time step) and from no observed export. The
    database entry stays at ``documented`` and the committed fixture
    says SYNTHETIC in its own header.

    Attributes
    ----------
    columns : tuple of str
        Plot names exactly as printed, in file order. THE ORDER IS
        DATA, not a contract: the set of columns is whatever plots the
        run defined, so a reader resolves a series by its label
        through :meth:`series` and never by position.
    values : numpy.ndarray
        The full table, shape ``(steps, len(columns))``, in printed
        order. Units are per column and the export declares NONE: each
        column carries the unit of the plot it came from (a force
        coefficient is dimensionless, a velocity plot is in the
        simulation's own length and time units), and the time column is
        in the unit the run's time increment is stated in, seconds in
        every export observed for the neighbouring parsers. Nothing is
        converted here, because there is nothing in the file to convert
        from. No reference frame is printed either, so a column of
        forces or velocities is in whatever frame the plot was defined
        in.
    """

    columns: tuple[str, ...]
    values: np.ndarray

    @property
    def steps(self) -> int:
        """Number of time steps, which is the number of rows."""
        return len(self.values)

    def series(self, name: str) -> np.ndarray:
        """Return one plot's history as an array over the time steps.

        Parameters
        ----------
        name : str
            Printed column name, for example ``"CL"``.

        Returns
        -------
        numpy.ndarray
            Shape ``(steps,)``, in printed order.

        Raises
        ------
        FieldNotInExportError
            If the export carries no column of that name.
        """
        try:
            index = self.columns.index(name)
        except ValueError as error:
            raise FieldNotInExportError(
                f"column {name!r} is not in this unsteady plot export; available: "
                f"{', '.join(self.columns)}"
            ) from error
        return self.values[:, index]

    def series_by_name(self) -> dict[str, np.ndarray]:
        """Every column keyed by its printed name.

        Returns
        -------
        dict of str to numpy.ndarray
            One array of shape ``(steps,)`` per column, including the
            time column: which column is time is a property of the plot
            list rather than of this format, so this parser does not
            decide it for the caller.
        """
        return {name: self.series(name) for name in self.columns}


def _unsteady_cells(line: str) -> list[str]:
    """Split one line of the export, dropping a trailing separator.

    A trailing comma is how this solver's other table exports end their
    header (the probe export's is ``X, Y, Z,``), so an empty last cell
    is punctuation rather than a column.
    """
    cells = [cell.strip() for cell in line.split(",")]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def parse_unsteady_plots(text: str) -> UnsteadyPlotsReport:
    r"""Parse an unsteady plot export into per-column time series.

    Anchor-based like every parser here, and the anchor is the
    SEPARATOR: the table starts at the first line carrying a comma, so
    a banner or a title block above it is skipped without this parser
    counting lines. Everything below the header is a time step until a
    dashed rule closes the table or the text ends.

    WHAT IS EVIDENCE HERE AND WHAT IS NOT. The row and column meaning
    is the manual's (SRC-003 p.347, paraphrased in the database entry
    for ``UNSTEADY_SOLVER_EXPORT_PLOTS``: one column per plot, one row
    per time step). The DELIMITER is not documented anywhere and no
    export of this command has been read: a comma is assumed because
    the loads and probe exports of the same solver use one. A file
    delimited some other way is refused by the anchor rather than
    misread, and a real export is owed before this parser can be called
    verified (PFS-2015.02.02).

    No version footer is required, and none is cross-checked (FR-18),
    because whether this export prints one is exactly the sort of thing
    a fixture would have to show.

    Parameters
    ----------
    text : str
        Complete export file text.

    Returns
    -------
    UnsteadyPlotsReport
        Column names in file order and the table as floats.

    Raises
    ------
    AnchorNotFoundError
        If no line carries the column separator, so there is no table.
    MalformedOutputError
        If the header names a column twice or leaves one unnamed, if a
        row holds MORE values than the header names, or if a cell is
        not a solver-printed number. Each names the step and the column
        it read.
    IncompleteOutputError
        If the header is followed by no time step at all, or a row
        holds FEWER values than the header names: both are a write that
        stopped part way (FR-17).

    Examples
    --------
    >>> from pyflightstream.results import parse_unsteady_plots
    >>> text = "Time (sec), CL\n.000, +2.3500000E-3\n.004, +2.1000000E-3\n"
    >>> report = parse_unsteady_plots(text)
    >>> report.columns
    ('Time (sec)', 'CL')
    >>> report.steps
    2
    >>> float(report.series("CL")[-1])
    0.0021
    """
    text = text.replace("\x00", "")
    # MEASURED, not anticipated: the committed probe fixture parsed
    # cleanly here and returned twelve "time steps" that are twelve
    # probe POSITIONS, because that export is also a comma table of
    # numbers under a header. A file that identifies itself as another
    # export is refused rather than read as a history; nothing else in
    # the format distinguishes them, which is one more reason a real
    # export of this command is owed (PFS-2015.02.02).
    if "Number of Probe Points:" in text:
        raise MalformedOutputError(
            "this file declares a probe-point count, so it is an EXPORT_PROBE_POINTS "
            "output and its rows are positions in space rather than steps in time. "
            "Read it with parse_probe_points; reading it here would report a spatial "
            "table as a time history, and every row index would be misread as an instant"
        )
    lines = text.splitlines()
    header_index = next((index for index, line in enumerate(lines) if "," in line), None)
    if header_index is None:
        raise AnchorNotFoundError(
            "no unsteady plot table header was found: no line in this file carries the "
            "comma separating one plot column from the next. Either the file is not an "
            "UNSTEADY_SOLVER_EXPORT_PLOTS output, or the export writes a separator this "
            "parser has never seen, which is possible because no real export of this "
            "command has been read yet"
        )
    columns = tuple(_unsteady_cells(lines[header_index]))
    if not all(columns):
        raise MalformedOutputError(
            f"the unsteady plot header {lines[header_index].strip()!r} leaves a column "
            "unnamed, so the values under it could not be attributed to a plot"
        )
    reject_duplicate_columns(columns, what="unsteady plot export")

    rows: list[list[float]] = []
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if _DASHED_LINE.match(stripped):
            if rows:
                break
            continue
        cells = _unsteady_cells(stripped)
        step = len(rows) + 1
        if len(cells) < len(columns):
            raise IncompleteOutputError(
                f"time step {step} of the unsteady plot export holds {len(cells)} values "
                f"but the header names {len(columns)} columns; the file ends part way "
                "through a row, so the solver stopped mid-write and the missing plots "
                "are not zeros"
            )
        if len(cells) > len(columns):
            raise MalformedOutputError(
                f"time step {step} of the unsteady plot export holds {len(cells)} values "
                f"but the header names {len(columns)} columns; the table layout changed, "
                "so reading it by position would attribute a value to the wrong plot"
            )
        values = []
        for column, cell in zip(columns, cells, strict=True):
            try:
                values.append(parse_number(cell))
            except MalformedOutputError as error:
                raise MalformedOutputError(
                    f"time step {step} of the unsteady plot export holds {cell!r} in "
                    f"column {column!r}, which is not a solver-printed number; expected "
                    "forms like '.000', '4380000.', or '1.000E-05'"
                ) from error
        rows.append(values)
    if not rows:
        raise IncompleteOutputError(
            f"the unsteady plot export names {len(columns)} plot column(s) and holds no "
            "time step at all. An empty history is not a run of zero steps: this export "
            "is written by a solver that has advanced in time, so an empty table means "
            "the file was cut off after its header"
        )
    return UnsteadyPlotsReport(columns=columns, values=np.asarray(rows, dtype=float))


# The operating-point binding is part of the public face of this layer
# too, so it is re-exported beside the tabular names rather than being
# reachable only as pyflightstream.results.conditions (api-designer and
# architect passes, 2026-08-03). It imports nothing from this package,
# so the import is unconditional and cycle-free.
from pyflightstream.results.conditions import (  # noqa: E402
    FIELD_BINDINGS,
    ConditionBinding,
    ConditionCheck,
    bind_conditions,
)

# Tabular views (pandas) build on the parsers above, so their import
# must follow the definitions; __all__ re-exports them as part of the
# public face of the results layer.
from pyflightstream.results.tables import (  # noqa: E402
    AmbiguousLoadsError,
    LoadsNotFoundError,
    parse_run_loads,
    run_table,
    sweep_table,
    to_csv,
    to_table,
    write_table,
)

__all__ = [
    "AmbiguousLoadsError",
    "AnchorNotFoundError",
    "ConditionBinding",
    "ConditionCheck",
    "DATA_ORIGIN_CODES",
    "DATA_ORIGIN_COLUMN",
    "EXPORT_CONVERSIONS",
    "EXPORT_EXCLUDED",
    "EXPORT_NOT_AN_EXPORT",
    "EXPORT_OWED",
    "EXPORT_PARSED",
    "EXPORT_VERDICTS",
    "ExportConversion",
    "FIELD_BINDINGS",
    "FieldNotInExportError",
    "IncompleteOutputError",
    "LoadsNotFoundError",
    "LoadsReport",
    "MalformedOutputError",
    "PROVENANCE_COLUMNS",
    "ProbePointsReport",
    "REDUCTION_CODES",
    "REDUCTION_COLUMN",
    "ResidualSample",
    "SOLVER_MODES",
    "UnsteadyPlotsReport",
    "VersionMismatchWarning",
    "bind_conditions",
    "classify_solver_mode",
    "delimited_table",
    "export_conversion",
    "labeled_value",
    "origin_code",
    "parse_count",
    "parse_loads",
    "parse_number",
    "parse_probe_points",
    "parse_residual_history",
    "parse_run_loads",
    "parse_unsteady_plots",
    "reduction_code",
    "reduction_for_solver_mode",
    "reject_duplicate_columns",
    "reject_trailing_export",
    "require_export_parser",
    "run_table",
    "sweep_table",
    "to_csv",
    "to_table",
    "write_table",
]
