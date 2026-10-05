"""The loads file, the probe-points export and the unsteady plots file, parsed.

:func:`parse_loads` reads one run's loads file into a :class:`LoadsReport`,
:func:`parse_probe_points` a probe-points export into a
:class:`ProbePointsReport`, and :func:`parse_unsteady_plots` the unsteady
solver's plot file into an :class:`UnsteadyPlotsReport`. A probe export's
columns are chosen by the run, so they are read from the file's header rather
than pinned.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.results`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from pyflightstream.results.core import (
    DASHED_LINE,
    SOFTWARE_LINE,
    AnchorNotFoundError,
    FieldNotInExportError,
    IncompleteOutputError,
    MalformedOutputError,
    cross_check_version,
    delimited_table,
    labeled_value,
    optional_labeled_value,
    parse_count,
    parse_number,
    reject_duplicate_columns,
    reject_trailing_export,
)
from pyflightstream.versions import FsVersion

__all__ = [
    "LoadsReport",
    "ProbePointsReport",
    "DRAG_PAIRS",
    "UnsteadyPlotsReport",
    "drag_pair",
    "parse_loads",
    "parse_probe_points",
    "parse_unsteady_plots",
]

#: THE TWO DRAG SPLITS A LOADS SPREADSHEET PRINTS, each under the names the
#: solver wrote (FR-423). Up to 26.124 the split is ``CDi, CDo``, induced and
#: skin friction drag (SRC-752 pp.225, 227); 26.125 prints ``CDp, CDv`` in the
#: same two positions, pressure drag and viscous and separation drag (SRC-753
#: pp.227, 229). The parsed report keeps whichever pair the header printed;
#: nothing here says the two pairs measure the same quantities.
DRAG_PAIRS: tuple[tuple[str, str], ...] = (("CDi", "CDo"), ("CDp", "CDv"))


def drag_pair(row: Mapping[str, float]) -> tuple[str, str]:
    """Return the drag split one parsed loads row carries, in the order it is printed.

    Parameters
    ----------
    row : mapping of str to float
        A row of :class:`LoadsReport`: ``total`` or one of ``surfaces``.

    Returns
    -------
    tuple of str
        ``("CDi", "CDo")`` up to 26.124, ``("CDp", "CDv")`` on 26.125.

    Raises
    ------
    MalformedOutputError
        If the row carries neither pair, or both.

    Examples
    --------
    >>> drag_pair({"CL": 0.4, "CDp": 0.01, "CDv": 0.002})
    ('CDp', 'CDv')
    """
    carried = [pair for pair in DRAG_PAIRS if all(name in row for name in pair)]
    if len(carried) != 1:
        raise MalformedOutputError(
            f"the loads row carries the columns {', '.join(row)}, and a loads table "
            f"names exactly one drag split of {' or '.join(', '.join(p) for p in DRAG_PAIRS)}; "
            "re-export the loads spreadsheet with EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
        )
    return carried[0]


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
    r"""Parse one aerodynamic loads spreadsheet.

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

    Raises
    ------
    IncompleteOutputError
        If the software footer or the closing Total row is missing, so the
        solver stopped before finishing the export.
    MalformedOutputError
        If a second export follows the first, a column or a surface name
        repeats, there is more than one Total row, or a row holds a number
        of values other than the header names.

    Examples
    --------
    >>> text = (
    ...     "Angle of attack (Deg)  2.000\n"
    ...     "Side-slip angle (Deg)  .000\n"
    ...     "Freestream velocity (m/s)  30.000\n"
    ...     "Requested solver iterations  500\n"
    ...     "Solver convergence limit  1.000E-05\n"
    ...     "Force solver to run all iterations  F\n"
    ...     "Solver mode:  Steady\n"
    ...     "Current solver iteration number:  312\n"
    ...     "Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz\n"
    ...     "-----------------\n"
    ...     "Wing,+0.01,+0.0,+0.43,+0.43,+0.009,+0.006,+0.0,-0.09,+0.0\n"
    ...     "Total,+0.01,+0.0,+0.43,+0.43,+0.009,+0.006,+0.0,-0.09,+0.0\n"
    ...     "-----------------\n"
    ...     "Force Units: Coefficients\n"
    ...     "Moment Units: Coefficients\n"
    ...     "Software : Flightstream version 26.1, build #7012026\n"
    ... )
    >>> report = parse_loads(text)
    >>> report.angle_of_attack_deg
    2.0
    >>> list(report.surfaces)
    ['Wing']
    >>> report.total['CL']
    0.43
    """
    software = SOFTWARE_LINE.search(text)
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
    # THE COLUMNS AS PRINTED, the 26.125 drag split ``CDp, CDv`` included
    # (FR-423, :data:`DRAG_PAIRS`).
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
    forced = optional_labeled_value(text, "Force solver to run all iterations")
    reported = software.group("version")
    if requested_version is not None:
        cross_check_version(reported, requested_version, software.group("build"))
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
        solver_model=optional_labeled_value(text, "Solver model:"),
        forced_iterations=_parse_solver_flag(forced, "Force solver to run all iterations"),
        reference_velocity_m_s=_optional_number(text, "Reference velocity (m/s)"),
        reference_length=_optional_number(text, "Reference length (m)"),
        reference_area=_optional_number(text, "Reference area (m^2)"),
        reynolds=_optional_number(text, "Reynolds Number"),
        frame=optional_labeled_value(text, "Coordinate frame for analysis:"),
        surfaces=surfaces,
        total=total,
        force_units=labeled_value(text, "Force Units:"),
        moment_units=labeled_value(text, "Moment Units:"),
        fs_version_reported=reported,
        fs_build=software.group("build"),
    )


def _optional_number(text: str, label: str) -> float | None:
    value = optional_labeled_value(text, label)
    return None if value is None else parse_number(value)


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

    Raises
    ------
    AnchorNotFoundError
        If a printed label or the table header the parser anchors on is
        absent.
    IncompleteOutputError
        If the software footer is missing, so the export ended early.
    MalformedOutputError
        If the declared point count differs from the rows parsed, or a row
        does not match the header.
    """
    text = text.replace("\x00", "")
    software = SOFTWARE_LINE.search(text)
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
    # A run defining no probe point exports the header, the count 0 and
    # the opening and closing dashed lines with nothing between them
    # (the solver's own file is committed as the fixture
    # tests/tier1_offline/fixtures/probe_points_zero_26.123.txt, step 4 of
    # the tier-3 actions row 6002 on 26.123, 2026-09-09; every stamped
    # probes file of the reference rows 1226 and 5913 carries the same
    # shape, read off the reference workspace and not committed; PFS-2031.18.01):
    # a complete table of no rows, which the
    # walker below would read as a table with no closing line, since it
    # skips every dashed line after the header until a row appears.
    rows = [] if declared == 0 else delimited_table(text, "X, Y, Z,")
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
        cross_check_version(software.group("version"), requested_version, software.group("build"))
    return ProbePointsReport(
        columns=columns,
        values=np.asarray(parsed_rows, dtype=float).reshape(len(parsed_rows), len(columns)),
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
        if DASHED_LINE.match(stripped):
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
