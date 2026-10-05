"""The errors, the anchor primitives and the code vocabularies of the results layer.

Values are located by their printed labels (:func:`labeled_value`) and tables
by their header rows (:func:`delimited_table`), never by fixed line numbers,
so cosmetic layout changes between FlightStream versions do not silently
corrupt data (SAD Section 8, PP-4). Completeness is structural: a missing
footer or table terminator raises :class:`IncompleteOutputError`, never a
silently shorter table (FR-17). The FlightStream version printed in each
output is cross-checked against the requested version by alias prefix, the
reported string and build recorded verbatim (FR-18).

Beside the primitives live the two vocabularies every layer above reads and
none may own: :data:`DATA_ORIGIN_CODES` and :data:`REDUCTION_CODES`, append
only (PFS-2014.05), and :data:`EXPORT_CONVERSIONS`, the classification of
every ``phase: export`` command of the database (PFS-2014.02).

Every parser module of the layer imports from here and this module imports
none of them, so the package root is a facade over leaves and no module of
the layer imports the root.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.results`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "DATA_ORIGIN_CODES",
    "DATA_ORIGIN_COLUMN",
    "EXPORT_CONVERSIONS",
    "EXPORT_EXCLUDED",
    "EXPORT_NOT_AN_EXPORT",
    "EXPORT_OWED",
    "EXPORT_PARSED",
    "EXPORT_VERDICTS",
    "PROVENANCE_COLUMNS",
    "REDUCTION_CODES",
    "REDUCTION_COLUMN",
    "REDUCTION_WINDOW_CODES",
    "REDUCTION_WINDOW_COLUMN",
    "SOLVER_MODES",
    "AnchorNotFoundError",
    "ExportConversion",
    "FieldNotInExportError",
    "IncompleteOutputError",
    "MalformedOutputError",
    "UnsupportedResultTypeError",
    "VersionMismatchWarning",
    "classify_solver_mode",
    "delimited_table",
    "export_conversion",
    "labeled_value",
    "origin_code",
    "parse_count",
    "parse_number",
    "reduction_code",
    "reduction_for_solver_mode",
    "reject_duplicate_columns",
    "reject_trailing_export",
    "require_export_parser",
    "window_for_reduction",
]


DASHED_LINE = re.compile(r"^-{4,}$")
#: Where one page of the log's residual table ends and the next begins. The
#: export repeats the header periodically, so the table is read page by page
#: and the pages joined.
#:
#: THE PAGES ARE NOT A FIXED LENGTH, which the first writing of this comment
#: said they were. Measured on 26.123: a steady log pages at a hundred rows,
#: and an unsteady one pages PER TIME STEP, giving 36 pages of 81, 40, 23,
#: 33, 36, 39 and so on in one file. The anchor is the repeated header and
#: never a row count, which is why the split is on the header alone.
RESIDUAL_PAGE = re.compile(r"^Iteration", re.MULTILINE)
#: The export footer naming the build. Two product names are read: the
#: ``Flightstream version 26.1`` of every build up to 26.124 and the
#: ``Simcenter Flightstream version 2612`` that 26.125 prints in every export
#: (FR-423, measured on its exports of 2026-10-05). The version token is kept
#: verbatim; :func:`cross_check_version` reads it against the registry.
SOFTWARE_LINE = re.compile(
    r"Software\s*:\s*(?:Simcenter\s+)?Flightstream version\s+(?P<version>\S+),"
    r"\s*build\s*#(?P<build>\d+)",
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


class UnsupportedResultTypeError(PyflightstreamError, TypeError):
    """:func:`~pyflightstream.results.to_table` was handed a kind it cannot tabulate.

    ``TypeError`` as the second base, and it is the whole point of the
    class rather than a compatibility courtesy: ``except TypeError`` is
    how a caller distinguishes "I passed the wrong KIND of thing" from
    "I passed a bad VALUE", which is what every ``ValueError``-based
    refusal in this package means. A handler that already catches
    ``TypeError`` around the call catches exactly what it caught before
    and ``except PyflightstreamError`` now catches it too (FR-39,
    OPS-2009.01.08).

    Raised for a result of a type no parser here produces, and for a
    :class:`pandas.DataFrame`, which is a table already and is refused
    rather than tabulated twice.
    """


class VersionMismatchWarning(PyflightstreamWarning):
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

    Raises
    ------
    AnchorNotFoundError
        If no line of ``text`` starts with ``label`` (a ``ValueError``).
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


def optional_labeled_value(text: str, label: str) -> str | None:
    try:
        return labeled_value(text, label)
    except AnchorNotFoundError:
        return None


def parse_number(token: str) -> float:
    """Parse one solver-printed number.

    Accepts the solver's forms: ``.000``, ``4380000.``, ``1.000E-05``,
    and signed values such as ``+0.0002056``.

    Parameters
    ----------
    token : str
        The printed number, as it stands in the file.

    Returns
    -------
    float
        The value of the token.

    Raises
    ------
    MalformedOutputError
        If the token is not a number (a ``ValueError``).
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

    Returns
    -------
    None
        The header is acceptable when the call returns.

    Raises
    ------
    MalformedOutputError
        If any normalized name appears more than once (a ``ValueError``).
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

    Returns
    -------
    None
        The file is acceptable when the call returns.

    Raises
    ------
    MalformedOutputError
        If the file holds more than one software footer (a ``ValueError``).

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
    if len(SOFTWARE_LINE.findall(text)) > 1:
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
    MalformedOutputError
        If the token is not a number at all, is a number with a
        fractional part, or is below ``minimum`` (a ``ValueError``).
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
# PFS-2014.05, the requirement of 2026-08-16. A sweep table carries one row
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
# THE TOKENS AND THEIR CODES ARE A SEAT DECISION and are built here under
# the lane's default, which that seat has not yet ruled on; the vocabulary is a
# proposal until it does, and NFR-19 is where its status is tracked. Two
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

#: Over what window a reduced row was reduced, on the same append-only
#: rule as the two above, and for the same reason: a file written last
#: month is read with this table and cannot be asked what it meant.
#:
#: ALL THREE RECORD SOMETHING THE PACKAGE KNOWS, and two of them record
#: ignorance rather than a window. ``not_applicable`` is a direct
#: integration, which averages over nothing. ``not_printed`` is an
#: average the SOLVER took: the loads spreadsheet prints a solver mode
#: and an iteration counter and no averaging window, so this package does
#: not know the window and says so. ``unknown`` is a row whose mode was
#: never printed at all, so whether anything was averaged is itself
#: unknown; it exists because mapping that row to ``not_printed`` would
#: assert an average that may never have happened, which is the same
#: false assertion :data:`REDUCTION_CODES` refuses for ``none``.
#:
#: A TOKEN FOR A WINDOW THIS PACKAGE COMPUTED IS NOT PUBLISHED YET, and
#: deliberately: nothing in the package writes one. This table is append
#: only, so a token added later is cheap and a token whose meaning has to
#: change is impossible, which is the wrong way round to guess.
#:
#: A blank cell would say all three at once and survive none of them: it
#: reads back out of a csv as NaN.
REDUCTION_WINDOW_CODES: dict[str, int] = {
    "not_applicable": 0,
    "not_printed": 1,
    "unknown": 2,
}

#: The three column labels, named once so no writer spells them itself.
DATA_ORIGIN_COLUMN = "data_origin"
REDUCTION_COLUMN = "reduction"
REDUCTION_WINDOW_COLUMN = "reduction_window"

#: All three together, in the order they are written. The ARITY is data
#: rather than a promise: it went from two to three at 0.8.0, and a
#: consumer that unpacked the pair broke silently on the widening.
PROVENANCE_COLUMNS: tuple[str, ...] = (
    DATA_ORIGIN_COLUMN,
    REDUCTION_COLUMN,
    REDUCTION_WINDOW_COLUMN,
)


def window_for_reduction(reduction: str) -> str:
    """Return the window token that goes with a reduction this package stamps.

    Parameters
    ----------
    reduction : str
        One key of :data:`REDUCTION_CODES`.

    Returns
    -------
    str
        One key of :data:`REDUCTION_WINDOW_CODES`.

    Raises
    ------
    MalformedOutputError
        When ``reduction`` is not a published token. A default here would
        stamp a window on a reduction nobody has thought about, which is
        the failure this mapping exists to prevent. The type is the
        catalogued one its two siblings raise: a public name of this
        package raises no bare stdlib error, which the FR-39 ratchet
        caught on this function's first run.

    Notes
    -----
    ``time_average`` maps to ``not_printed`` rather than to a window,
    because the average is the solver's and the spreadsheet does not
    describe it. ``unknown`` maps to ``unknown``: a row whose solver mode
    never printed cannot be said to have been averaged at all.

    A DICT RATHER THAN A CHAIN OF IFS, so an unhandled token is a refusal
    rather than a default. The chain it replaced ended in a fallback
    returning ``not_printed``, which made the ``time_average`` branch
    above it behaviourally dead and stamped a solver average on rows that
    may have had none.
    """
    windows = {
        "none": "not_applicable",
        "time_average": "not_printed",
        "unknown": "unknown",
    }
    try:
        return windows[reduction]
    except KeyError:
        raise MalformedOutputError(
            f"{reduction!r} is not a published reduction, so this package has no window "
            f"token for it. The reductions are {', '.join(sorted(REDUCTION_CODES))}; a "
            "new one arrives with its window rather than defaulting to a window that "
            "asserts an average nobody performed"
        ) from None


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
# PFS-2014.02, the scoping of 2026-08-16. The census of ``phase: export``
# commands CANNOT be the default set: two of the eighteen entries export
# nothing at all (they set the VTK variable list and delete a profile), so
# the classification has to be explicit data rather than a filter.
#
# The keys are compared against the live command database by
# ``tests/tier1_offline/test_results.py``, so an export command added to any yaml fails
# the suite until it is classified here.

#: The export has a parser and a tabular conversion in this package.
EXPORT_PARSED = "parsed"

#: A structured format deliberately outside the default set (the scoping of
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
#: against the live census on 2026-08-20: eighteen entries, ten parsed,
#: five excluded, two that export nothing, one owed. It read four parsed
#: and seven owed until that day, when the capture run of
#: ``scripts/capture_export_corpus.py`` put six of the seven formats on
#: disk and PFS-2014.02 wrote their parsers against the files. Twenty since
#: 2026-09-24, when the two plot commands moved to the export phase on
#: RPT-067's measurement: one more that exports nothing, one more owed.
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
        "pyflightstream.results.sectional_loads.parse_sectional_loads",
        None,
        "spanwise load densities, the input of the FSI coupling",
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
    "FREE_SURFACE_EXPORT_TYPE": ExportConversion(
        EXPORT_EXCLUDED,
        None,
        "vtk",
        "a free-surface mesh as VTK (26.125, SRC-753 p.338), read by ParaView and every "
        "VTK reader; no workflow writes it",
    ),
    "SET_VTK_EXPORT_VARIABLES": ExportConversion(
        EXPORT_NOT_AN_EXPORT, None, None, "chooses the variables a later VTK export writes"
    ),
    "DELETE_BL_VELOCITY_PROFILE": ExportConversion(
        EXPORT_NOT_AN_EXPORT, None, None, "deletes a profile; it writes no file"
    ),
    "SET_PLOT_TYPE": ExportConversion(
        EXPORT_NOT_AN_EXPORT, None, None, "chooses which plot a later SAVE_PLOT_TO_FILE writes"
    ),
    "SAVE_PLOT_TO_FILE": ExportConversion(
        EXPORT_OWED,
        None,
        None,
        "the plotted series as text, a run header, one row per point of the plot and "
        "a units footer (RPT-067); collected and hashed as a product of the point, and "
        "never read as a coefficient source, because a plot is a display of the solve: "
        "its pitching moment is not the exported CMy",
    ),
    "EXPORT_SOLVER_ANALYSIS_CSV": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_solver_analysis_csv",
        None,
        "four bare columns under no header: x, y, z and the scalar the call asked for",
    ),
    "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_force_distributions",
        None,
        "per-panel pressure and viscous force coefficients, by boundary",
    ),
    "EXPORT_BL_VELOCITY_PROFILE": ExportConversion(
        EXPORT_OWED,
        None,
        None,
        "the one default-set format that has never been observed, and it is the SOLVER "
        "that will not write it rather than a capture nobody has run: two licensed 26.123 "
        "runs on 2026-08-20, bounded at 1800 s and at 240 s, both stopped at this command "
        "with every earlier export of the same script already written and the exported log "
        "showing the run reaching it. The cause was measured on 26.122 and is recorded in "
        "reports/RPT-027 and in the database entry: the command opens a modal window and "
        "waits for a person to dismiss it, under -hidden and with both streams redirected, "
        "so an unattended run waits forever. A parser is owed a file, and no file exists "
        "to owe it to; writing one from the manual page would be a guess wearing evidence's "
        "clothes",
    ),
    "EXPORT_ALL_OFF_BODY_STREAMLINES": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_off_body_streamlines",
        None,
        "one table per streamline, located by its printed marker",
    ),
    "EXPORT_SURFACE_SECTIONS": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_surface_sections",
        None,
        "one section's cut, in the same format the all-sections export writes",
    ),
    "EXPORT_ALL_SURFACE_SECTIONS": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_surface_sections",
        None,
        "every section's cut; one parser reads both commands, on two observed files",
    ),
    "SWEEPER_EXPORT_SPREADSHEET": ExportConversion(
        EXPORT_PARSED,
        "pyflightstream.results.parse_sweep_spreadsheet",
        None,
        "the sweeper's own polar, one row per sweep point",
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
        f"yet. PFS-2014.02 owes the parser, and a parser is written against one real "
        f"export from a licensed run rather than against a manual page; the entry's own "
        f"note says what stands in the way of getting one: {entry.note}"
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

    Raises
    ------
    AnchorNotFoundError
        If no line starts with ``header_anchor``.
    IncompleteOutputError
        If the text ends before the closing separator line.
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
        if DASHED_LINE.match(stripped):
            if rows:
                return rows
            continue
        cells = stripped.split(delimiter) if delimiter else stripped.split()
        rows.append([cell.strip() for cell in cells])
    raise IncompleteOutputError(
        f"the table under {header_anchor!r} has no closing separator line; the file "
        "ends mid-table, so the solver stopped before finishing this output"
    )


def cross_check_version(
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
            warn(
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
    # THE REGISTRY'S OWN RECORD OF WHAT THE BUILD PRINTS COMES FIRST (FR-423).
    # 26.125 prints its release as ``2612``, which no prefix of its alias
    # ``26.12`` matches, so a build that states ``prints`` is matched on it
    # exactly; the alias prefix stays the reading for a row that states none.
    consistent = (
        (version.prints is not None and reported == version.prints)
        or alias == reported
        or alias.startswith(reported)
        or reported.startswith(alias)
    )
    if not consistent:
        warn(
            f"the output reports FlightStream {reported!r} but the run requested "
            f"{alias!r}; the wrong executable may have run. The reported string and "
            "build are recorded verbatim in the manifest (FR-18).",
            VersionMismatchWarning,
            stacklevel=3,
        )
    elif version.build is None and _shares_alias(version):
        warn(
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
