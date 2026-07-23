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
results into DataFrames: :func:`to_dataframe`/:func:`to_csv` for each
parser, :func:`parse_run_loads` for one run's coefficients, and
:func:`run_frame`/:func:`sweep_frame` for one run or a whole sweep
read from the manifest (the manifest, an execution-layer artifact, is
imported lazily so the layer rule is not violated at module load).
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass

import numpy as np

from pyflightstream.versions import FsVersion, resolve

_DASHED_LINE = re.compile(r"^-{4,}$")
_SOFTWARE_LINE = re.compile(
    r"Software\s*:\s*Flightstream version\s+(?P<version>\S+),\s*build\s*#(?P<build>\d+)",
    re.IGNORECASE,
)


class AnchorNotFoundError(ValueError):
    """A printed label or table header was not found in the output.

    Anchor-based parsing refuses to fall back to line offsets; a
    missing anchor means the file is not the expected kind of output
    or the format changed, and both must surface loudly.
    """


class IncompleteOutputError(ValueError):
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
        raise ValueError(
            f"{token!r} is not a solver-printed number; expected forms like "
            "'.000', '4380000.', or '1.000E-05'"
        ) from error


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
    header_cells = labeled_value(text, "Surface,")
    columns = [cell.strip() for cell in header_cells.split(",") if cell.strip()]
    rows = delimited_table(text, "Surface,")
    surfaces: dict[str, dict[str, float]] = {}
    total: dict[str, float] | None = None
    for row in rows:
        name, values = row[0], row[1:]
        if len(values) != len(columns):
            raise ValueError(
                f"loads row for {name!r} holds {len(values)} values but the header "
                f"names {len(columns)} columns; the table layout changed"
            )
        parsed = {
            column: parse_number(value) for column, value in zip(columns, values, strict=True)
        }
        if name.lower() == "total":
            total = parsed
        else:
            surfaces[name] = parsed
    if total is None:
        raise IncompleteOutputError(
            "the loads table has no Total row; per-surface rows without the closing "
            "Total mean the export stopped mid-table"
        )
    forced = _optional_labeled_value(text, "Force solver to run all iterations")
    reported = software.group("version")
    if requested_version is not None:
        _cross_check_version(reported, requested_version)
    return LoadsReport(
        angle_of_attack_deg=parse_number(labeled_value(text, "Angle of attack (Deg)")),
        sideslip_deg=parse_number(labeled_value(text, "Side-slip angle (Deg)")),
        freestream_velocity_m_s=parse_number(labeled_value(text, "Freestream velocity (m/s)")),
        requested_iterations=int(parse_number(labeled_value(text, "Requested solver iterations"))),
        convergence_limit=parse_number(labeled_value(text, "Solver convergence limit")),
        solver_mode=labeled_value(text, "Solver mode:"),
        current_iteration=int(
            parse_number(labeled_value(text, "Current solver iteration number:"))
        ),
        solver_model=_optional_labeled_value(text, "Solver model:"),
        forced_iterations=None if forced is None else forced.upper().startswith("T"),
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


def _cross_check_version(reported: str, requested: str | FsVersion) -> None:
    alias = resolve(requested).alias
    consistent = alias == reported or alias.startswith(reported) or reported.startswith(alias)
    if not consistent:
        warnings.warn(
            f"the output reports FlightStream {reported!r} but the run requested "
            f"{alias!r}; the wrong executable may have run. The reported string and "
            "build are recorded verbatim in the manifest (FR-18).",
            VersionMismatchWarning,
            stacklevel=3,
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
            raise ValueError(
                f"residual row {row!r} holds fewer than three columns (iteration, "
                "velocity residual, pressure residual); the log table layout changed"
            )
        history.append(
            ResidualSample(
                iteration=int(parse_number(row[0])),
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
            raise KeyError(
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
    declared = int(parse_number(labeled_value(text, "Number of Probe Points:")))
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
    rows = delimited_table(text, "X, Y, Z,")
    parsed_rows = []
    for row in rows:
        cells = [cell for cell in row if cell]
        if len(cells) != len(columns):
            raise ValueError(
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
        _cross_check_version(software.group("version"), requested_version)
    return ProbePointsReport(
        columns=columns,
        values=np.asarray(parsed_rows, dtype=float),
        angle_of_attack_deg=parse_number(labeled_value(text, "Angle of attack (Deg)")),
        freestream_velocity_m_s=parse_number(labeled_value(text, "Freestream velocity (m/s)")),
        current_iteration=int(
            parse_number(labeled_value(text, "Current solver iteration number:"))
        ),
        reported_version=software.group("version"),
        reported_build=software.group("build"),
    )


# Tabular views (pandas) build on the parsers above, so their import
# must follow the definitions; __all__ re-exports them as part of the
# public face of the results layer.
from pyflightstream.results.tables import (  # noqa: E402
    AmbiguousLoadsError,
    LoadsNotFoundError,
    parse_run_loads,
    run_frame,
    sweep_frame,
    to_csv,
    to_dataframe,
)

__all__ = [
    "AmbiguousLoadsError",
    "AnchorNotFoundError",
    "IncompleteOutputError",
    "LoadsNotFoundError",
    "LoadsReport",
    "ProbePointsReport",
    "ResidualSample",
    "VersionMismatchWarning",
    "delimited_table",
    "labeled_value",
    "parse_loads",
    "parse_number",
    "parse_probe_points",
    "parse_residual_history",
    "parse_run_loads",
    "run_frame",
    "sweep_frame",
    "to_csv",
    "to_dataframe",
]
