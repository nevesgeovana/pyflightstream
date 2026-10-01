"""The solver's export tables: force distributions, streamlines, sections, sweeps, CSV.

THE COLUMN LAYOUTS OF THE FIVE NEWEST FORMATS ARE PINNED
(:data:`FORCE_DISTRIBUTION_COLUMNS` and its four siblings) rather than read
from the file the way the probe export's are. A probe export's columns are
chosen by the run; these are fixed by the solver, so a header that has moved
means a build reordered the numbers, and a table read by position would
publish one physical quantity under another one's label.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.results`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from pyflightstream.results.core import (
    _DASHED_LINE,
    _SOFTWARE_LINE,
    AnchorNotFoundError,
    FieldNotInExportError,
    IncompleteOutputError,
    MalformedOutputError,
    _cross_check_version,
    _optional_labeled_value,
    labeled_value,
    parse_count,
    parse_number,
    reject_duplicate_columns,
    reject_trailing_export,
)
from pyflightstream.versions import FsVersion

__all__ = [
    "FORCE_DISTRIBUTION_COLUMNS",
    "OFF_BODY_STREAMLINE_COLUMNS",
    "SOLVER_ANALYSIS_CSV_COLUMNS",
    "SOLVER_ANALYSIS_CSV_FIELD_UNSTATED",
    "SURFACE_SECTION_COLUMNS",
    "SWEEP_COLUMNS",
    "ExportSolution",
    "ForceDistributionReport",
    "OffBodyStreamline",
    "OffBodyStreamlinesReport",
    "SolverAnalysisCsvReport",
    "SurfaceSection",
    "SurfaceSectionsReport",
    "SweepSpreadsheetReport",
    "parse_force_distributions",
    "parse_off_body_streamlines",
    "parse_solver_analysis_csv",
    "parse_surface_sections",
    "parse_sweep_spreadsheet",
]


# --- the six exports PFS-2014.02 owed a parser -----------------------------
#
# Every format below is written against an OBSERVED file. The capture script
# `scripts/capture_export_corpus.py` put a coarse generated NACA 0012 wing
# through a licensed 26.123 solve on 2026-08-20 and committed one small file
# per format under `tests/tier1_offline/fixtures/`; two earlier 26.120 captures sit beside
# them. Nothing here is written from the manual alone, and the one format
# that has never been observed keeps its `owed` verdict rather than a parser
# guessed from its page (see EXPORT_BL_VELOCITY_PROFILE in
# :data:`EXPORT_CONVERSIONS`).
#
# THE FOUR TEXT FORMATS SHARE ONE SKELETON with the loads spreadsheet and the
# probe export: a block of labelled solution values, a dashed rule, a header
# row naming the columns, a dashed rule, the rows, a closing dashed rule, and
# a footer naming the software build. Only what sits between the two inner
# rules differs, so that is the only part each parser below writes for
# itself; the skeleton is the four helpers that follow.
#
# THE COLUMNS ARE PINNED rather than read, which is the opposite of what the
# probe parser does and is deliberate. A probe export's columns are chosen by
# the run, so they are data; these five carry a fixed layout the solver
# writes, so a header that has moved is a build that reordered the numbers,
# and reading it by position would shift a column of values under a label
# that still looks right. Each parser refuses a header that is not its pinned
# tuple, naming what it expected and what it found.

_SECTION_EDGES = re.compile(r"^Edges\s*=\s*(-?\d+)\s*$", re.IGNORECASE)
_SECTION_MARKER = re.compile(r"^Surface cross-section\s+(-?\d+)\s*$", re.IGNORECASE)
_STREAMLINE_MARKER = re.compile(r"^Streamline\s+(-?\d+)\s*$", re.IGNORECASE)


#: Printed columns of EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS, pinned.
#: ``Boundary`` is the 1-based mesh boundary index the row belongs to; X, Y, Z
#: are the panel position in simulation length units in the analysis frame the
#: file names; Cx, Cy, Cz are the pressure force coefficients of the panel and
#: Cxv, Cyv, Czv the viscous ones, all dimensionless and all in that frame.
FORCE_DISTRIBUTION_COLUMNS: tuple[str, ...] = (
    "Boundary",
    "X",
    "Y",
    "Z",
    "Cx",
    "Cy",
    "Cz",
    "Cxv",
    "Cyv",
    "Czv",
)

#: Printed columns of EXPORT_ALL_OFF_BODY_STREAMLINES, pinned. X, Y, Z are the
#: point of the streamline in simulation length units; ``Mach`` is the local
#: Mach number; vx, vy, vz and vtot are the velocity there in m/s; ``Cp`` and
#: ``Cp_ref`` are the pressure coefficient against the free stream and against
#: the reference velocity, both dimensionless. All in the analysis frame the
#: file names.
OFF_BODY_STREAMLINE_COLUMNS: tuple[str, ...] = (
    "X",
    "Y",
    "Z",
    "Mach",
    "Cp_ref",
    "vx",
    "vy",
    "vz",
    "vtot",
    "Cp",
)

#: Printed columns of the surface-section exports, pinned. Both
#: EXPORT_SURFACE_SECTIONS (one section) and EXPORT_ALL_SURFACE_SECTIONS
#: (every section) write this layout: the two committed fixtures are one of
#: each, on two different builds, and their headers agree character for
#: character. ``Section_direction_value`` is the station along the section's
#: own direction and X, Y, Z the point, in simulation length units; nx, ny, nz
#: is the unit surface normal there; ``L`` is the normalized position along the
#: cut; Cp, Cp_ref and Mach are dimensionless; vx, vy, vz and vtot are in m/s;
#: ``Theta``, ``CF``, ``Delta*``, ``Delta`` and ``H`` are the boundary-layer
#: quantities (momentum thickness, skin-friction coefficient, displacement
#: thickness, thickness and shape factor), the three thicknesses in simulation
#: length units and CF and H dimensionless.
SURFACE_SECTION_COLUMNS: tuple[str, ...] = (
    "Section_direction_value",
    "X",
    "Y",
    "Z",
    "nx",
    "ny",
    "nz",
    "L",
    "Cp",
    "Mach",
    "vx",
    "vy",
    "vz",
    "vtot",
    "Cp_ref",
    "Theta",
    "CF",
    "Delta*",
    "Delta",
    "H",
)

#: Printed columns of SWEEPER_EXPORT_SPREADSHEET, pinned. One row per sweep
#: point: the point's angle of attack and side-slip angle in deg, its velocity
#: in m/s, and the integrated coefficients of the whole model, dimensionless
#: when the export declares ``Force Units: Coefficients`` (which the report
#: carries verbatim) and in the printed units otherwise.
SWEEP_COLUMNS: tuple[str, ...] = (
    "AOA (deg)",
    "Beta (deg)",
    "Velocity (m/sec)",
    "Cx",
    "Cy",
    "Cz",
    "CL",
    "CDi",
    "CDo",
    "CMx",
    "CMy",
    "CMz",
)

#: Columns of EXPORT_SOLVER_ANALYSIS_CSV, pinned, and the ONLY names in this
#: module that are not printed anywhere in their own file: that export writes
#: no header at all. What each column means is settled in the docstring of
#: :func:`parse_solver_analysis_csv`, which is also where the fourth one is
#: named as unsettled BY THE FILE and settled only by the call.
SOLVER_ANALYSIS_CSV_COLUMNS: tuple[str, ...] = ("x", "y", "z", "scalar")

#: What the fourth CSV column is when the caller did not say. A WORD rather
#: than an empty cell, on the same reasoning as ``unknown`` in
#: :data:`REDUCTION_CODES`: an empty cell reads back out of a csv as NaN, so
#: the statement that nobody stated the field would not survive its own file.
SOLVER_ANALYSIS_CSV_FIELD_UNSTATED = "UNSTATED"


@dataclass(frozen=True)
class ExportSolution:
    """The solution block every FlightStream text export prints above its table.

    One dataclass rather than the same eight fields repeated on each
    report: the four text formats below print this block character for
    character, so it is a fact about the solver's export writer rather
    than about any one export. :class:`LoadsReport` and
    :class:`ProbePointsReport` keep their own flat fields, because they
    are published API that predates this and widening is cheaper than
    moving a name somebody imports.

    Attributes
    ----------
    angle_of_attack_deg : float
        Angle of attack of the exported solution, in deg.
    sideslip_deg : float
        Side-slip angle, in deg.
    freestream_velocity_m_s : float
        Free-stream velocity, in m/s.
    solver_mode : str
        ``Steady`` or ``Unsteady`` as printed. The reduction token every
        table of this export carries is decided from it by
        :func:`reduction_for_solver_mode`.
    current_iteration : int
        Solver iteration the export reflects.
    frame : str or None
        Coordinate frame the positions and vectors are expressed in, as
        printed after ``Coordinate frame for analysis:``; None when the
        export omits the label.
    reported_version : str
        Version string printed in the footer, verbatim.
    reported_build : str
        Build number printed in the footer, verbatim. The precise
        discriminator, because every registered 26.1x prints the same
        version string (FR-18).
    """

    angle_of_attack_deg: float
    sideslip_deg: float
    freestream_velocity_m_s: float
    solver_mode: str
    current_iteration: int
    frame: str | None
    reported_version: str
    reported_build: str


def _export_footer(text: str, *, what: str) -> re.Match[str]:
    """Locate the software footer, refusing a file that has none or two.

    The footer is the structural end of a FlightStream text export, so
    its absence means the solver stopped mid-write (FR-17) and a second
    one means two exports were concatenated (:func:`reject_trailing_export`).
    """
    software = _SOFTWARE_LINE.search(text)
    if software is None:
        raise IncompleteOutputError(
            f"the {what} has no software footer; the file ends before the closing "
            "block, so the solver stopped before finishing this export"
        )
    reject_trailing_export(text, what=what)
    return software


def _solution_block(text: str, *, what: str, software: re.Match[str]) -> ExportSolution:
    """Read the labelled solution values every text export prints."""
    return ExportSolution(
        angle_of_attack_deg=parse_number(labeled_value(text, "Angle of attack (Deg)")),
        sideslip_deg=parse_number(labeled_value(text, "Side-slip angle (Deg)")),
        freestream_velocity_m_s=parse_number(labeled_value(text, "Freestream velocity (m/s)")),
        solver_mode=labeled_value(text, "Solver mode:"),
        current_iteration=parse_count(
            labeled_value(text, "Current solver iteration number:"),
            label=f"the {what}'s iteration counter",
        ),
        frame=_optional_labeled_value(text, "Coordinate frame for analysis:"),
        reported_version=software.group("version"),
        reported_build=software.group("build"),
    )


def _table_region(text: str, header_anchor: str, *, what: str) -> tuple[str, list[str]]:
    """Return the header line and the non-blank lines of one table's body.

    The body runs from the rule that OPENS the table to the rule that
    closes it, and everything between comes back as raw stripped lines:
    two of the formats here interleave block markers with their rows, so
    the split into rows is each parser's own business.

    NOT :func:`delimited_table`, and the reason is a committed file
    rather than a preference. That helper treats every dashed rule as a
    separator until it has a row, so a table with NO rows never
    terminates for it and the 26.120 force-distribution fixture (a
    complete file, exported at iteration zero, with a header, two rules
    and nothing between them) came back as ``IncompleteOutputError: the
    file ends mid-table``, which names a defect the file does not have.
    Here the rule immediately after the header opens the table and the
    next one closes it, so an empty table is an empty table.

    Parameters
    ----------
    text : str
        Complete export file text.
    header_anchor : str
        Start of the header row, for example ``"Boundary,"``.
    what : str
        Name of the export, for the error messages.

    Returns
    -------
    tuple of str and list of str
        The header line, stripped, and the body lines, stripped.

    Raises
    ------
    AnchorNotFoundError
        When no line starts with the anchor.
    IncompleteOutputError
        When the text ends before the closing rule.
    """
    lines = text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip().startswith(header_anchor)),
        None,
    )
    if start is None:
        raise AnchorNotFoundError(
            f"the {what} table header {header_anchor!r} was not found; tables are located "
            "by their header rows and never by line numbers, so a missing header means "
            "this file is not that export or its layout changed"
        )
    cursor = start + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor < len(lines) and _DASHED_LINE.match(lines[cursor].strip()):
        cursor += 1
    body: list[str] = []
    for line in lines[cursor:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _DASHED_LINE.match(stripped):
            return lines[start].strip(), body
        body.append(stripped)
    raise IncompleteOutputError(
        f"the {what} table has no closing separator line; the file ends mid-table, so "
        "the solver stopped before finishing this export"
    )


def _pinned_columns(header: str, expected: tuple[str, ...], *, what: str) -> tuple[str, ...]:
    """Refuse a header that is not the pinned column layout of this export."""
    printed = tuple(cell.strip() for cell in header.split(",") if cell.strip())
    reject_duplicate_columns(printed, what=what)
    if printed != expected:
        raise MalformedOutputError(
            f"the {what} header names {list(printed)}, and this package reads the layout "
            f"{list(expected)}. The columns of this export are fixed by the solver rather "
            "than chosen by the run, so a header that has moved means the build reordered, "
            "renamed or added a column; reading it by position would carry one physical "
            "quantity under another one's label, which no value downstream would look "
            "wrong for. Pin the new layout against an observed export of that build"
        )
    return printed


def _row_values(
    line: str,
    *,
    columns: tuple[str, ...],
    what: str,
    ordinal: int,
    named_by: str = "the header names",
    truncation: str = (
        "the file ends part way through a row, so the solver stopped mid-write "
        "and the missing values are not zeros"
    ),
) -> list[float]:
    """Parse one data row, refusing an arity the header does not name.

    A trailing separator is punctuation rather than a column: three of
    the formats here end every row with a comma, exactly as the probe
    export ends its header.
    """
    cells = [cell.strip() for cell in line.split(",")]
    while cells and not cells[-1]:
        cells.pop()
    if len(cells) < len(columns):
        raise IncompleteOutputError(
            f"row {ordinal} of the {what} holds {len(cells)} values but {named_by} "
            f"{len(columns)} columns; {truncation}"
        )
    if len(cells) > len(columns):
        raise MalformedOutputError(
            f"row {ordinal} of the {what} holds {len(cells)} values but {named_by} "
            f"{len(columns)} columns; the table layout changed, so reading it by position "
            "would attribute a value to the wrong column"
        )
    values: list[float] = []
    for column, cell in zip(columns, cells, strict=True):
        try:
            values.append(parse_number(cell))
        except MalformedOutputError as error:
            raise MalformedOutputError(
                f"row {ordinal} of the {what} holds {cell!r} in column {column!r}, which is "
                "not a solver-printed number; expected forms like '.000', '4380000.', or "
                "'1.000E-05'"
            ) from error
    return values


def _as_table(rows: list[list[float]], width: int) -> np.ndarray:
    """Stack parsed rows, keeping the column arity of an EMPTY table.

    ``np.asarray([])`` is one dimensional, so an empty export would come
    back with a shape nothing downstream could index by column; a real
    empty export exists (the 26.120 surface section that cut no edges),
    so the width is carried explicitly rather than inferred from rows
    that are not there.
    """
    if not rows:
        return np.empty((0, width), dtype=float)
    return np.asarray(rows, dtype=float)


def _named_column(
    values: np.ndarray, columns: tuple[str, ...], name: str, *, what: str
) -> np.ndarray:
    """Return one pinned column by name, refusing a name the export lacks."""
    try:
        index = columns.index(name)
    except ValueError as error:
        raise FieldNotInExportError(
            f"column {name!r} is not in the {what}; available: {', '.join(columns)}"
        ) from error
    return values[:, index]


@dataclass(frozen=True)
class ForceDistributionReport:
    """Parsed EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS output.

    One row per panel of every exported boundary: the panel's position
    and its pressure and viscous force coefficients, which integrate to
    the coefficients the loads spreadsheet prints as a total.

    Attributes
    ----------
    columns : tuple of str
        Always :data:`FORCE_DISTRIBUTION_COLUMNS`; carried on the report
        so a caller can index a row without importing the constant.
    values : numpy.ndarray
        The full table, shape ``(count, 10)``, in printed order. Units
        and reference frame are the constant's.
    solution : ExportSolution
        The solution block printed above the table.
    force_units, moment_units : str
        Units of the force and moment columns as printed.
    """

    columns: tuple[str, ...]
    values: np.ndarray
    solution: ExportSolution
    force_units: str
    moment_units: str

    @property
    def count(self) -> int:
        """Number of panel rows."""
        return len(self.values)

    @property
    def boundary_indices(self) -> np.ndarray:
        """The ``Boundary`` column as 1-based integer indices."""
        return self.values[:, 0].astype(int)

    @property
    def positions(self) -> np.ndarray:
        """Panel positions, shape ``(count, 3)``: the X, Y, Z columns."""
        return self.values[:, 1:4]

    def field(self, name: str) -> np.ndarray:
        """Return one printed column as an array.

        Parameters
        ----------
        name : str
            One of :data:`FORCE_DISTRIBUTION_COLUMNS`, for example
            ``"Cxv"``.
        """
        return _named_column(self.values, self.columns, name, what="force distribution export")


def parse_force_distributions(
    text: str, *, requested_version: str | FsVersion | None = None
) -> ForceDistributionReport:
    """Parse an EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS file.

    Anchor-based like every parser here: the table is located by its
    ``Boundary,`` header, the columns are pinned against
    :data:`FORCE_DISTRIBUTION_COLUMNS`, and the footer is structural, so
    a file that stops mid-write raises rather than returning a shorter
    table (FR-17).

    GROUNDING. Written against two observed exports, both committed:
    ``force_distributions_26.123.txt`` (96 panel rows, build 8112026) and
    ``force_distributions_26.120.txt`` (build 7012026). The database
    entry is ``verified`` on 26.120 through 26.123 (SRC-003 pp.353-354).

    AN EMPTY DISTRIBUTION IS RETURNED, NOT REFUSED, and the 26.120
    fixture is why the question came up: it is a complete file, footer
    and both rules present, whose table holds no rows because the export
    ran at iteration zero. The file says so structurally, so returning
    zero rows reports what the solver wrote; raising would name a defect
    the file does not have. Check :attr:`ForceDistributionReport.count`
    before integrating anything.

    Parameters
    ----------
    text : str
        Complete export file text.
    requested_version : str, FsVersion, or None
        When given, the version and build printed in the footer are
        cross-checked against it and a mismatch warns (FR-18).

    Returns
    -------
    ForceDistributionReport
        The pinned table plus the printed solution block.

    Raises
    ------
    AnchorNotFoundError
        When the header or a labelled solution value is missing.
    MalformedOutputError
        When the header is not the pinned layout, a row holds too many
        values, a cell is not a solver-printed number, or a boundary
        index is not a whole number of at least one.
    IncompleteOutputError
        When the footer, the closing rule or part of a row is missing.
    """
    what = "force distribution export"
    text = text.replace("\x00", "")
    software = _export_footer(text, what=what)
    header, body = _table_region(text, "Boundary,", what=what)
    columns = _pinned_columns(header, FORCE_DISTRIBUTION_COLUMNS, what=what)
    rows: list[list[float]] = []
    for ordinal, line in enumerate(body, start=1):
        values = _row_values(line, columns=columns, what=what, ordinal=ordinal)
        boundary = values[0]
        if boundary != int(boundary) or boundary < 1:
            raise MalformedOutputError(
                f"row {ordinal} of the {what} names boundary {line.split(',')[0].strip()!r}, "
                "which is not a whole boundary index of at least one. The column indexes the "
                "mesh boundaries the run initialized, counting from one, so a fractional or "
                "non-positive value means the table layout changed and every coefficient in "
                "the row belongs to a different quantity"
            )
        rows.append(values)
    if requested_version is not None:
        _cross_check_version(software.group("version"), requested_version, software.group("build"))
    return ForceDistributionReport(
        columns=columns,
        values=_as_table(rows, len(columns)),
        solution=_solution_block(text, what=what, software=software),
        force_units=labeled_value(text, "Force Units:"),
        moment_units=labeled_value(text, "Moment Units:"),
    )


@dataclass(frozen=True)
class OffBodyStreamline:
    """One streamline of an off-body streamline export.

    Attributes
    ----------
    index : int
        The streamline's own 1-based number, as printed after
        ``Streamline``.
    declared_points : int
        The bare integer printed above the marker, verbatim. READ THE
        NOTE ON :func:`parse_off_body_streamlines` before treating it as
        the row count: on the only observed export it exceeds the row
        count by exactly one, on all three streamlines.
    values : numpy.ndarray
        The streamline's points, shape ``(points, 10)``, in integration
        order. Columns, units and frame are
        :data:`OFF_BODY_STREAMLINE_COLUMNS`.
    """

    index: int
    declared_points: int
    values: np.ndarray

    @property
    def points(self) -> int:
        """Number of points actually written for this streamline."""
        return len(self.values)

    @property
    def positions(self) -> np.ndarray:
        """The X, Y, Z columns, shape ``(points, 3)``."""
        return self.values[:, :3]

    def field(self, name: str) -> np.ndarray:
        """Return one printed column of this streamline as an array."""
        return _named_column(
            self.values, OFF_BODY_STREAMLINE_COLUMNS, name, what="off-body streamline export"
        )


@dataclass(frozen=True)
class OffBodyStreamlinesReport:
    """Parsed EXPORT_ALL_OFF_BODY_STREAMLINES output.

    Attributes
    ----------
    columns : tuple of str
        Always :data:`OFF_BODY_STREAMLINE_COLUMNS`.
    streamlines : tuple of OffBodyStreamline
        One entry per streamline, in printed order, numbered from one.
    declared_count : int
        The count printed after ``Number of Off-body Streamlines:``. It
        is checked against the number of blocks read, which is what makes
        a truncated export raise rather than return fewer streamlines.
    solution : ExportSolution
        The solution block printed above the table.
    """

    columns: tuple[str, ...]
    streamlines: tuple[OffBodyStreamline, ...]
    declared_count: int
    solution: ExportSolution

    @property
    def count(self) -> int:
        """Number of streamlines."""
        return len(self.streamlines)

    @property
    def points(self) -> int:
        """Total number of points over every streamline."""
        return sum(line.points for line in self.streamlines)


def parse_off_body_streamlines(
    text: str, *, requested_version: str | FsVersion | None = None
) -> OffBodyStreamlinesReport:
    """Parse an EXPORT_ALL_OFF_BODY_STREAMLINES file into per-streamline tables.

    The export writes one shared column header and then repeats, once per
    streamline, a bare integer, a ``Streamline N`` marker and that
    streamline's points. The blocks are located by their markers, never
    by counting lines, and the number of blocks is checked against the
    printed ``Number of Off-body Streamlines:`` (FR-17).

    GROUNDING. Written against ``off_body_streamlines_26.123.txt``, an
    observed export of build 8112026: three streamlines of thirty points
    each. The database entry is ``verified`` on 26.120 through 26.123
    (SRC-003 p.369).

    THE BARE INTEGER IS NOT ASSERTED TO BE THE ROW COUNT, and this is a
    measurement rather than a caution. Every one of the three streamlines
    in the observed export prints ``31`` and then writes thirty rows.
    Nothing in the file or in the manual paraphrase settles what the
    extra one is (a seed point that is counted and not written, a segment
    count, or an off-by-one in the export), so this package records the
    printed number verbatim as
    :attr:`OffBodyStreamline.declared_points` and does NOT equate it with
    :attr:`OffBodyStreamline.points`. Equating them would refuse every
    real export of this format, which is a worse answer than saying that
    one number is not yet understood. The count that IS checked is the
    number of streamlines, which the observed export gets right.

    Parameters
    ----------
    text : str
        Complete export file text.
    requested_version : str, FsVersion, or None
        When given, the version and build printed in the footer are
        cross-checked against it and a mismatch warns (FR-18).

    Returns
    -------
    OffBodyStreamlinesReport
        One table per streamline plus the printed solution block.

    Raises
    ------
    AnchorNotFoundError
        When the header or a labelled solution value is missing.
    MalformedOutputError
        When the header is not the pinned layout, a row is malformed, a
        row appears before any streamline marker, a block carries no
        point count, or the streamlines are not numbered one upward.
    IncompleteOutputError
        When the footer or the closing rule is missing, when a streamline
        holds no point at all, or when the number of streamlines written
        is not the number declared.
    """
    what = "off-body streamline export"
    text = text.replace("\x00", "")
    software = _export_footer(text, what=what)
    declared = parse_count(
        labeled_value(text, "Number of Off-body Streamlines:"),
        label="Number of Off-body Streamlines",
        counts="streamlines",
    )
    header, body = _table_region(text, "X, Y, Z, Mach,", what=what)
    columns = _pinned_columns(header, OFF_BODY_STREAMLINE_COLUMNS, what=what)

    streamlines: list[OffBodyStreamline] = []
    pending: int | None = None
    index: int | None = None
    block_points = 0
    rows: list[list[float]] = []
    ordinal = 0

    def close() -> None:
        if index is None:
            return
        if not rows:
            raise IncompleteOutputError(
                f"streamline {index} of the {what} holds no point at all. A streamline is "
                "written by an integration that has advanced through the flow field, so an "
                "empty one means the file was cut off after its marker"
            )
        streamlines.append(
            OffBodyStreamline(
                index=index,
                declared_points=block_points,
                values=_as_table(rows, len(columns)),
            )
        )

    for line in body:
        marker = _STREAMLINE_MARKER.match(line)
        if marker is not None:
            # BEFORE `pending` is consumed: the count of the NEXT block has
            # already been read by the time its marker arrives, so closing
            # after the handover would stamp block N with block N+1's count.
            close()
            if pending is None:
                raise MalformedOutputError(
                    f"the {what} opens {line!r} with no point count printed above it. Every "
                    "streamline in this format is introduced by its own count line, so a "
                    "marker without one means the block structure changed and the rows "
                    "below it cannot be attributed to a streamline"
                )
            index = int(marker.group(1))
            expected_index = len(streamlines) + 1
            if index != expected_index:
                raise MalformedOutputError(
                    f"the {what} numbers its streamlines {index} where {expected_index} was "
                    "expected; they are printed in order from one, so a gap or a repeat "
                    "means a block was lost or two exports were interleaved, and a caller "
                    "indexing by streamline number would read the wrong line of flow"
                )
            block_points = pending
            pending = None
            rows = []
            continue
        if "," in line:
            if index is None:
                raise MalformedOutputError(
                    f"the {what} holds a data row before any 'Streamline N' marker, so the "
                    "point it describes belongs to no streamline. The rows of this format "
                    "are only meaningful inside a block"
                )
            ordinal += 1
            rows.append(_row_values(line, columns=columns, what=what, ordinal=ordinal))
            continue
        pending = parse_count(
            line,
            label=f"the {what}'s per-streamline point count",
            minimum=1,
            counts="streamline points",
        )
    close()

    if len(streamlines) != declared:
        raise IncompleteOutputError(
            f"the {what} declares {declared} streamline(s) and holds {len(streamlines)}; the "
            "solver stopped mid-write, so the flow field this file describes is not the one "
            "the run generated"
        )
    if requested_version is not None:
        _cross_check_version(software.group("version"), requested_version, software.group("build"))
    return OffBodyStreamlinesReport(
        columns=columns,
        streamlines=tuple(streamlines),
        declared_count=declared,
        solution=_solution_block(text, what=what, software=software),
    )


@dataclass(frozen=True)
class SurfaceSection:
    """One cross-section of a surface-section export.

    Attributes
    ----------
    index : int
        The section's own 1-based number, as printed after
        ``Surface cross-section``.
    edges : int
        The count printed as ``Edges=N`` above the marker. Equal to the
        number of rows in every observed export, and asserted so by
        :func:`parse_surface_sections`.
    values : numpy.ndarray
        The cut points, shape ``(edges, 20)``, in printed order.
        Columns, units and frame are :data:`SURFACE_SECTION_COLUMNS`.
    """

    index: int
    edges: int
    values: np.ndarray

    @property
    def count(self) -> int:
        """Number of rows written for this section, which is ``edges``."""
        return len(self.values)

    @property
    def positions(self) -> np.ndarray:
        """The X, Y, Z columns, shape ``(edges, 3)``."""
        return self.values[:, 1:4]

    def field(self, name: str) -> np.ndarray:
        """Return one printed column of this section as an array."""
        return _named_column(
            self.values, SURFACE_SECTION_COLUMNS, name, what="surface section export"
        )


@dataclass(frozen=True)
class SurfaceSectionsReport:
    """Parsed EXPORT_SURFACE_SECTIONS or EXPORT_ALL_SURFACE_SECTIONS output.

    ONE REPORT FOR TWO COMMANDS, on evidence rather than on convenience:
    the committed 26.120 single-section export and the committed 26.123
    all-sections export carry the same banner, the same
    ``Number of Surface Sections:`` label, the same twenty-column header
    and the same ``Edges=`` block structure. The single-section command
    writes a file holding one section; the difference is in what the
    solver selects, not in the format.

    Attributes
    ----------
    columns : tuple of str
        Always :data:`SURFACE_SECTION_COLUMNS`.
    sections : tuple of SurfaceSection
        One entry per section, in printed order, numbered from one.
    declared_count : int
        The count printed after ``Number of Surface Sections:``, checked
        against the number of blocks read.
    solution : ExportSolution
        The solution block printed above the table.
    """

    columns: tuple[str, ...]
    sections: tuple[SurfaceSection, ...]
    declared_count: int
    solution: ExportSolution

    @property
    def count(self) -> int:
        """Number of sections."""
        return len(self.sections)

    @property
    def points(self) -> int:
        """Total number of cut points over every section."""
        return sum(section.count for section in self.sections)


def parse_surface_sections(
    text: str, *, requested_version: str | FsVersion | None = None
) -> SurfaceSectionsReport:
    """Parse a surface-section export into one table per cross-section.

    The export writes one shared column header and then repeats, once per
    section, an ``Edges=N`` line, a ``Surface cross-section N`` marker
    and that section's cut points. Two counts are declared and both are
    checked: the number of sections against
    ``Number of Surface Sections:``, and each section's row count against
    its own ``Edges=``. A mismatch raises rather than returning a shorter
    table (FR-17).

    GROUNDING. Written against two observed exports, both committed:
    ``all_surface_sections_26.123.txt`` (build 8112026,
    ``EXPORT_ALL_SURFACE_SECTIONS``, one section of twelve edges) and
    ``surface_sections_26.120.txt`` (build 7012026,
    ``EXPORT_SURFACE_SECTIONS``, one section of zero edges). The database
    entries are ``verified`` on 26.120 through 26.123 for the all-sections
    command and ``documented`` for the single-section one (SRC-003 p.365).

    A SECTION OF ZERO EDGES IS A REAL FILE and is returned as a section
    with no rows. The 26.120 fixture is one: its cutting plane was laid
    on a spanwise panel boundary, so it crossed no edge and the solver
    wrote ``Edges=0`` and no rows. The file declares that, so it is
    reported rather than refused; a caller integrating along a section
    checks :attr:`SurfaceSection.count` first. The equality between
    ``Edges`` and the row count still holds, and is what would catch a
    section that lost rows it declared.

    Parameters
    ----------
    text : str
        Complete export file text.
    requested_version : str, FsVersion, or None
        When given, the version and build printed in the footer are
        cross-checked against it and a mismatch warns (FR-18).

    Returns
    -------
    SurfaceSectionsReport
        One table per section plus the printed solution block.

    Raises
    ------
    AnchorNotFoundError
        When the header or a labelled solution value is missing.
    MalformedOutputError
        When the header is not the pinned layout, a row is malformed, a
        row appears before any section marker, a section carries no
        ``Edges=`` line, or the sections are not numbered one upward.
    IncompleteOutputError
        When the footer or the closing rule is missing, when a section
        holds fewer rows than the edges it declares, or when the number
        of sections written is not the number declared.
    """
    what = "surface section export"
    text = text.replace("\x00", "")
    software = _export_footer(text, what=what)
    declared = parse_count(
        labeled_value(text, "Number of Surface Sections:"),
        label="Number of Surface Sections",
        counts="surface sections",
    )
    header, body = _table_region(text, "Section_direction_value,", what=what)
    columns = _pinned_columns(header, SURFACE_SECTION_COLUMNS, what=what)

    sections: list[SurfaceSection] = []
    pending: int | None = None
    index: int | None = None
    edges = 0
    rows: list[list[float]] = []
    ordinal = 0

    def close() -> None:
        if index is None:
            return
        if len(rows) != edges:
            raise IncompleteOutputError(
                f"section {index} of the {what} declares {edges} edge(s) and holds "
                f"{len(rows)} row(s). The two are equal in every observed export, so a "
                "difference means the solver stopped mid-write and the cut this file "
                "describes is not the cut it declares"
            )
        sections.append(
            SurfaceSection(index=index, edges=edges, values=_as_table(rows, len(columns)))
        )

    for line in body:
        marker = _SECTION_MARKER.match(line)
        if marker is not None:
            # BEFORE `pending` is consumed, for the reason spelled out in
            # parse_off_body_streamlines: the next block's count is already
            # read by the time its marker arrives.
            close()
            if pending is None:
                raise MalformedOutputError(
                    f"the {what} opens {line!r} with no 'Edges=' line above it. Every section "
                    "in this format is introduced by its own edge count, so a marker without "
                    "one leaves the rows below it with nothing to be checked against"
                )
            index = int(marker.group(1))
            expected_index = len(sections) + 1
            if index != expected_index:
                raise MalformedOutputError(
                    f"the {what} numbers its sections {index} where {expected_index} was "
                    "expected; they are printed in order from one, so a gap or a repeat "
                    "means a block was lost or two exports were interleaved, and a caller "
                    "indexing by section number would read the wrong cut"
                )
            edges = pending
            pending = None
            rows = []
            continue
        edges_line = _SECTION_EDGES.match(line)
        if edges_line is not None:
            pending = parse_count(
                edges_line.group(1),
                label=f"the {what}'s per-section edge count",
                counts="section edges",
            )
            continue
        if index is None:
            raise MalformedOutputError(
                f"the {what} holds {line!r} before any 'Surface cross-section N' marker, so "
                "it belongs to no section. The rows of this format are only meaningful "
                "inside a block"
            )
        ordinal += 1
        rows.append(_row_values(line, columns=columns, what=what, ordinal=ordinal))
    close()

    if len(sections) != declared:
        raise IncompleteOutputError(
            f"the {what} declares {declared} surface section(s) and holds {len(sections)}; "
            "the solver stopped mid-write, so the geometry this file describes is not the "
            "one the run cut"
        )
    if requested_version is not None:
        _cross_check_version(software.group("version"), requested_version, software.group("build"))
    return SurfaceSectionsReport(
        columns=columns,
        sections=tuple(sections),
        declared_count=declared,
        solution=_solution_block(text, what=what, software=software),
    )


@dataclass(frozen=True)
class SweepSpreadsheetReport:
    """Parsed SWEEPER_EXPORT_SPREADSHEET output, one row per sweep point.

    The sweeper's own spreadsheet: the solver re-solves the case at each
    point of the sweep and prints one row of integrated coefficients per
    point, where :func:`parse_loads` reads the spreadsheet of a SINGLE
    point. The two are different files and the difference matters to a
    caller assembling a polar: this one already is the polar.

    Attributes
    ----------
    columns : tuple of str
        Always :data:`SWEEP_COLUMNS`.
    values : numpy.ndarray
        The full table, shape ``(points, 12)``, in printed order. Units
        and frame are the constant's.
    solution : ExportSolution
        The solution block printed above the table. Its angle of attack
        and iteration counter belong to the LAST point solved, not to
        the sweep: the sweep's own angles are the first column.
    force_units, moment_units : str
        Units of the force and moment columns as printed.
    """

    columns: tuple[str, ...]
    values: np.ndarray
    solution: ExportSolution
    force_units: str
    moment_units: str

    @property
    def points(self) -> int:
        """Number of sweep points, which is the number of rows."""
        return len(self.values)

    def field(self, name: str) -> np.ndarray:
        """Return one printed column as an array over the sweep points.

        Parameters
        ----------
        name : str
            One of :data:`SWEEP_COLUMNS`, for example ``"CL"``.
        """
        return _named_column(self.values, self.columns, name, what="sweeper spreadsheet")


def parse_sweep_spreadsheet(
    text: str, *, requested_version: str | FsVersion | None = None
) -> SweepSpreadsheetReport:
    """Parse a SWEEPER_EXPORT_SPREADSHEET file into the polar it holds.

    Anchor-based like every parser here: the table is located by its
    ``AOA (deg),`` header, the columns are pinned against
    :data:`SWEEP_COLUMNS`, and the footer is structural (FR-17).

    GROUNDING. Written against ``sweeper_spreadsheet_26.123.txt``, an
    observed export of build 8112026 holding a three-point angle sweep.
    The database entry is ``verified`` on 26.101 through 26.123
    (SRC-003 p.359).

    Parameters
    ----------
    text : str
        Complete export file text.
    requested_version : str, FsVersion, or None
        When given, the version and build printed in the footer are
        cross-checked against it and a mismatch warns (FR-18).

    Returns
    -------
    SweepSpreadsheetReport
        The pinned table plus the printed solution block.

    Raises
    ------
    AnchorNotFoundError
        When the header or a labelled solution value is missing.
    MalformedOutputError
        When the header is not the pinned layout or a row is malformed.
    IncompleteOutputError
        When the footer or the closing rule is missing, or when the sweep
        holds no point at all.
    """
    what = "sweeper spreadsheet"
    text = text.replace("\x00", "")
    software = _export_footer(text, what=what)
    header, body = _table_region(text, "AOA (deg),", what=what)
    columns = _pinned_columns(header, SWEEP_COLUMNS, what=what)
    rows = [
        _row_values(line, columns=columns, what=what, ordinal=ordinal)
        for ordinal, line in enumerate(body, start=1)
    ]
    if not rows:
        raise IncompleteOutputError(
            f"the {what} names {len(columns)} column(s) and holds no sweep point at all. "
            "An empty polar is not a sweep of zero points: this file is written after the "
            "sweeper has solved, so an empty table means it was cut off after its header"
        )
    if requested_version is not None:
        _cross_check_version(software.group("version"), requested_version, software.group("build"))
    return SweepSpreadsheetReport(
        columns=columns,
        values=_as_table(rows, len(columns)),
        solution=_solution_block(text, what=what, software=software),
        force_units=labeled_value(text, "Force Units:"),
        moment_units=labeled_value(text, "Moment Units:"),
    )


@dataclass(frozen=True)
class SolverAnalysisCsvReport:
    """Parsed EXPORT_SOLVER_ANALYSIS_CSV output.

    Attributes
    ----------
    columns : tuple of str
        Always :data:`SOLVER_ANALYSIS_CSV_COLUMNS`. THESE NAMES ARE THIS
        PACKAGE'S, not the solver's: the export prints no header.
    values : numpy.ndarray
        The full table, shape ``(count, 4)``, in printed order.
    field : str
        What the fourth column is, as the caller declared it from the
        FORMAT argument of the export call, upper cased; or
        :data:`SOLVER_ANALYSIS_CSV_FIELD_UNSTATED` when the caller said
        nothing. The file itself cannot say.
    """

    columns: tuple[str, ...]
    values: np.ndarray
    scalar_field: str

    @property
    def count(self) -> int:
        """Number of rows, which is the number of mesh nodes exported."""
        return len(self.values)

    @property
    def positions(self) -> np.ndarray:
        """Node positions, shape ``(count, 3)``: the x, y, z columns."""
        return self.values[:, :3]

    @property
    def scalar(self) -> np.ndarray:
        """The fourth column, shape ``(count,)``; see :attr:`scalar_field`."""
        return self.values[:, 3]


def parse_solver_analysis_csv(text: str, *, field: str | None = None) -> SolverAnalysisCsvReport:
    r"""Parse an EXPORT_SOLVER_ANALYSIS_CSV file, whose columns nothing names.

    THIS EXPORT WRITES NO HEADER. Four comma-separated columns of
    solver-printed floats and nothing else: no banner, no labelled
    solution block, no software footer. Every other parser here anchors
    on a printed label, and there is none to anchor on, so what the
    columns mean cannot be read out of the file and had to be settled
    from evidence. What follows is that evidence, because a column
    labelled on a guess is worse than a column labelled ``column_3``.

    WHAT IS SETTLED, and how. The observed export is
    ``solver_analysis_26.123.csv``, written by the capture run of
    2026-08-20 on a generated NACA 0012 wing of chord 1 m and span 8 m,
    called as ``EXPORT_SOLVER_ANALYSIS_CSV <path> CP-FREESTREAM PASCALS
    1 -1`` (the arguments the database names filename, format, units,
    frame and surfaces; SRC-003 p.353).

    - Column 1 is X. Its 86 rows take exactly seven values, and they are
      the seven cosine-spaced chordwise node stations of that mesh
      (0, 0.066987, 0.25, 0.5, 0.75, 0.933013, 1), spanning 0 to the
      1 m chord.
    - Column 2 is Y. It takes exactly seven values, the spanwise node
      stations at multiples of 8/6 m from -4 to +4, which is the wing's
      full span.
    - Column 3 is Z. At each X it takes the two values plus and minus the
      NACA 0012 half-thickness there (0.0312 at x = 0.75, 0.0093 at
      x = 0.933, 0 at the trailing edge), and its extreme, 0.0594, is the
      section's own maximum half-thickness.
    - Column 4 is the scalar the FORMAT argument asked for. Its values
      match, station for station and surface for surface, the ``Cp``
      column of the surface-section export captured in the same run
      (-0.2274 against -0.2293 on the upper surface near x = 0.93,
      -0.0570 against -0.0512 on the lower), so it is a pressure
      coefficient and not a pressure in the PASCALS the third argument
      names: that argument applies to the PRESSURE format.

    WHAT IS NOT SETTLED, and is therefore not labelled. Which pressure
    coefficient is a property of the CALL and not of the file: FORMAT
    selects among CP-FREESTREAM, CP-REFERENCE and PRESSURE, and the
    observed run cannot even distinguish the first two, because it set
    the reference velocity equal to the free-stream velocity, which makes
    the section export's ``Cp`` and ``Cp_ref`` columns identical to seven
    digits. The column is therefore named ``scalar`` and the caller may
    say what it asked for through ``field``, which is carried onto the
    report and into the table rather than inferred.

    NO VERSION IS CROSS-CHECKED (FR-18) and this function takes no
    ``requested_version``: the file prints no software footer, so there
    is nothing to check against and a parameter that silently did nothing
    would be worse than its absence.

    Parameters
    ----------
    text : str
        Complete export file text.
    field : str or None
        The FORMAT argument the export was called with, for example
        ``"CP-FREESTREAM"``. Recorded upper cased and never validated
        against the database here: the emitter already refused an
        unknown format when the script was written, and a second copy of
        that enumeration in this layer is a copy that can drift.

    Returns
    -------
    SolverAnalysisCsvReport
        The four columns plus what the caller said the fourth one is.

    Raises
    ------
    MalformedOutputError
        When a line does not hold exactly four solver-printed numbers,
        when the file carries the labelled block of a different export,
        or when ``field`` is given as blank.
    IncompleteOutputError
        When the file holds no row at all.

    Examples
    --------
    >>> from pyflightstream.results import parse_solver_analysis_csv
    >>> text = (
    ...     "  0.100E+01, -0.400E+01,  0.000E+00, -0.141E+00\n"
    ...     "  0.933E+00, -0.400E+01, -0.933E-02, -0.570E-01\n"
    ... )
    >>> report = parse_solver_analysis_csv(text, field="CP-FREESTREAM")
    >>> report.columns
    ('x', 'y', 'z', 'scalar')
    >>> report.count
    2
    >>> report.scalar_field
    'CP-FREESTREAM'
    >>> float(report.scalar[0])
    -0.141
    """
    what = "solver analysis csv"
    text = text.replace("\x00", "")
    if field is None:
        declared = SOLVER_ANALYSIS_CSV_FIELD_UNSTATED
    else:
        declared = field.strip().upper()
        if not declared:
            raise MalformedOutputError(
                "the field of this csv was declared as blank. This export writes no header, "
                "so the fourth column means whatever the FORMAT argument of the call asked "
                f"for; pass that token, or pass nothing and the column is recorded as "
                f"{SOLVER_ANALYSIS_CSV_FIELD_UNSTATED}"
            )
    if _SOFTWARE_LINE.search(text) is not None:
        raise MalformedOutputError(
            f"this file carries a FlightStream software footer, so it is one of the labelled "
            f"text exports and not the {what}, which writes four bare columns of numbers and "
            "nothing else. Read it with the parser of the export it actually is; reading it "
            "here would either refuse every labelled line or, worse, find four numbers in "
            "one of them"
        )
    columns = SOLVER_ANALYSIS_CSV_COLUMNS
    rows = [
        _row_values(
            line,
            columns=columns,
            what=what,
            ordinal=ordinal,
            # THIS EXPORT WRITES NO HEADER, so the shared refusal's default
            # sentence would send a reader looking for a line the format does
            # not have, and the two places that explain this format both shout
            # that it has none. And the mid-write reading is not available
            # either: there is no footer to be short of, so a short row here is
            # as likely to be a truncated cell or a hand edit as a solver that
            # stopped, and only the LAST row could mean truncation at all.
            named_by="this export writes",
            truncation=(
                "this format NAMES none of its columns, so nothing in the file "
                "says which value is missing. A short row here is a truncated "
                "write, a truncated cell or a hand edit, and a header-less "
                "export with no footer cannot tell them apart"
            ),
        )
        for ordinal, line in enumerate(
            (line for line in text.splitlines() if line.strip()), start=1
        )
    ]
    if not rows:
        raise IncompleteOutputError(
            f"the {what} holds no row at all. This export writes one row per exported mesh "
            "node, so an empty file means the export was asked for boundaries the run does "
            "not have, or the write never started"
        )
    return SolverAnalysisCsvReport(
        columns=columns, values=_as_table(rows, len(columns)), scalar_field=declared
    )
