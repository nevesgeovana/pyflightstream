"""Tabular views of parsed FlightStream results, on pandas for now.

Pipeline role: turns the typed parser outputs of
:mod:`pyflightstream.results` (and, when the optional ``[fsi]`` extra
is installed, the sectional loads report of
:mod:`pyflightstream.fsi.loads`) into tidy :class:`pandas.DataFrame`
tables, then assembles run-level and sweep-level tables by joining the
campaign manifest records with the parsed coefficient tables. Tables
rest on pandas today and labeled physical fields on xarray in
:mod:`pyflightstream.farfield`; both substrates leave the runtime set
at the release SRS NFR-06 names (SRS AD-06, which replaced the division
this docstring used to state as permanent). Downstream code should
depend on the documented column schema (SRS NFR-19), not on the
library holding the values.

Three steps of one ladder:

1. :func:`to_table` / :func:`to_csv` tabulate any single parsed
   result.
2. :func:`run_table` joins one manifest :class:`RunRecord` (identity,
   sweep point, versions, outcome) with the run's parsed loads into
   one wide row; :func:`parse_run_loads` resolves and parses that
   loads spreadsheet from the managed workspace through the record's
   collected outputs.
3. :func:`sweep_table` reads a whole campaign manifest and returns the
   tidy sweep table, one row per run; :func:`write_table` then writes
   the final csv.

EVERY TABLE SAYS WHAT PRODUCED ITS NUMBERS (PFS-2014.05, her
requirement of 2026-08-16). Each frame these functions build carries
``data_origin`` and ``reduction``, and :func:`write_table` refuses to
write one that does not. They are constant columns for a single parsed
result and genuinely PER ROW in the sweep table, which is the one file
here that mixes provenances: a steady point's coefficients are a direct
integration and an unsteady point's are the solver's own time average,
printed under the same names. The vocabulary and its integer codes live
in :mod:`pyflightstream.results`, one layer below the writers that
publish them.

Column names carry units the way the source dataclasses document them:
printed coefficient names (Cx .. CMz) with the ``force_units`` /
``moment_units`` metadata alongside for the loads spreadsheet,
dimensionless residuals for the solver log, printed column names for
the probe export (X, Y, Z in simulation length units), and
unit-suffixed names (``offset_m``, ``fx_n_per_m``, ...) for the
sectional loads, matching :class:`SectionalLoadsReport`.

The manifest is read only through the public API of
:mod:`pyflightstream.workspace`, and this module imports that layer
NOWHERE at runtime: :func:`parse_run_loads` and :func:`sweep_table` take
a :class:`~pyflightstream.workspace.CampaignWorkspace` the caller has
already constructed. The only mention of the workspace layer here is an
annotation, under ``if TYPE_CHECKING``, which the interpreter never
executes.

That is a CHANGE, and the reason it is worth a paragraph. Both
functions used to accept a bare root path as well, coerced by a helper
that imported the workspace layer inside its own body. Deferring an
import to call time hides its direction from every module-level reader
without changing it: results sits BELOW run/workspace, so the coercion
was the parsing layer reaching up for a constructor. AD-01 allows a
documented exception and the alternative was to delete it; deleting it
is what happened (OPS-2009.02.05), because a layering guard whose
permitted set is empty cannot go green while one convenience import
stands. Callers pass ``CampaignWorkspace(root)`` instead of ``root``,
which is one line and is what every shipped example already did.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from pyflightstream._errors import PyflightstreamError
from pyflightstream.extras import missing_extra
from pyflightstream.results import (
    DATA_ORIGIN_CODES,
    DATA_ORIGIN_COLUMN,
    PROVENANCE_COLUMNS,
    REDUCTION_CODES,
    REDUCTION_COLUMN,
    IncompleteOutputError,
    LoadsReport,
    MalformedOutputError,
    ProbePointsReport,
    ResidualSample,
    parse_loads,
    reduction_for_solver_mode,
)
from pyflightstream.results.conditions import bind_conditions

if TYPE_CHECKING:  # typing only: no runtime import of the execution layers
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

# Fixed identity and outcome columns of one run row, in output order;
# sweep point axes are inserted after sim_id and must not collide.
_RUN_IDENTITY_COLUMNS = ("run_id", "sim_id")
_RUN_OUTCOME_COLUMNS = (
    "fs_version_requested",
    "fs_version_reported",
    "fs_build",
    "package_version",
    "status",
    "iterations",
    "residual",
    "wall_time_s",
)

# Printed sectional loads columns (asserted at parse time by the FSI
# parser) mapped to the unit-suffixed names its dataclass documents:
# positions in m, force densities in N/m, moment densities in N m / m.
_SECTIONAL_COLUMN_UNITS = {
    "Offset": "offset_m",
    "Chord": "chord_m",
    "X_QC": "x_qc_m",
    "Z_QC": "z_qc_m",
    "Fx": "fx_n_per_m",
    "Fz": "fz_n_per_m",
    "Moment": "moment_qc_nm_per_m",
}


class LoadsNotFoundError(PyflightstreamError, ValueError):
    """No collected output of a run yields its loads spreadsheet.

    Expected for failed points: a run that stopped before
    EXPORT_SOLVER_ANALYSIS_SPREADSHEET leaves no coefficient table
    behind, and :func:`sweep_table` turns this into a row without
    coefficient columns instead of dropping the run.
    """


class AmbiguousLoadsError(PyflightstreamError, ValueError):
    """Several collected outputs of one run parse as loads spreadsheets.

    The resolver refuses to guess which table is the run's coefficient
    evidence; pass ``loads_file`` with the exact exported file name.
    """


def to_table(result: object) -> pd.DataFrame:
    """Tabulate one parsed FlightStream result as a tidy DataFrame.

    Dispatches on the parsed result type:

    - :class:`LoadsReport` (:func:`parse_loads`): one row per surface
      plus the Total row, columns ``surface``, the printed coefficient
      names (Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz), and the
      constant ``force_units`` / ``moment_units`` metadata columns;
      force and moment values follow those printed units, in the
      analysis frame named by the report.
    - list of :class:`ResidualSample`
      (:func:`parse_residual_history`): columns ``iteration``,
      ``velocity_residual``, ``pressure_residual`` (dimensionless).
    - :class:`ProbePointsReport` (:func:`parse_probe_points`): the
      printed columns, starting with X, Y, Z in simulation length
      units in the analysis reference frame.
    - ``SectionalLoadsReport`` (:mod:`pyflightstream.fsi.loads`,
      optional ``[fsi]`` extra): unit-suffixed columns ``offset_m``,
      ``chord_m``, ``x_qc_m``, ``z_qc_m`` [m], ``fx_n_per_m``,
      ``fz_n_per_m`` [N/m], ``moment_qc_nm_per_m`` [N m / m], in the
      cut-plane axes the FSI parser documents.

    Every one of them also carries the two provenance columns
    (PFS-2014.05): ``data_origin``, ``raw`` for anything read off a
    solver export, and ``reduction``, which is ``none`` where nothing
    was averaged, ``time_average`` where the unsteady solver averaged
    over its window, and ``unknown`` where the file printed no solver
    mode to decide it by.

    Parameters
    ----------
    result : object
        One parsed result of the kinds above.

    Returns
    -------
    pandas.DataFrame
        Tidy table, one observation per row; write it with
        :func:`to_csv` or :func:`write_table`.
    """
    if isinstance(result, LoadsReport):
        return _loads_frame(result)
    if isinstance(result, ProbePointsReport):
        return _probe_points_frame(result)
    if isinstance(result, (list, tuple)):
        if result and all(isinstance(sample, ResidualSample) for sample in result):
            return _residual_history_frame(list(result))
        if not result:
            raise MalformedOutputError(
                "an empty result list holds no rows to tabulate; the parsers never "
                "return an empty history (they raise IncompleteOutputError instead), "
                "so an empty list points at filtering upstream of this call"
            )
    if isinstance(result, pd.DataFrame):
        raise TypeError(
            "the result is already a pandas DataFrame; call its .to_csv method "
            "directly instead of tabulating it again"
        )
    sectional_type = _sectional_loads_type()
    if sectional_type is not None and isinstance(result, sectional_type):
        return _sectional_loads_frame(result)
    if sectional_type is None and _looks_like_sectional(result):
        raise missing_extra(
            "fsi",
            package="pyflightstream.fsi.loads",
            purpose=("tabulating an object that looks like a SectionalLoadsReport"),
        )
    raise TypeError(
        f"to_table cannot tabulate {type(result).__name__}; supported parsed "
        "results are LoadsReport (parse_loads), a list of ResidualSample "
        "(parse_residual_history), ProbePointsReport (parse_probe_points), and "
        "SectionalLoadsReport (pyflightstream.fsi.loads, optional [fsi] extra)"
    )


def write_table(frame: pd.DataFrame, path: str | Path, *, overwrite: bool = True) -> Path:
    """Write one table as a csv, refusing a file that cannot say what it is.

    THE ONE WRITE PATH of this module (PFS-2014.05). Every file this
    package writes has to state whether its numbers came off the run or
    out of a reduction, and the identifier is carried PER ROW, because
    the sweep table mixes a steady point's direct integration with an
    unsteady point's time average under the same column names. A reader
    who cannot tell those apart compares them and reads a method
    difference as physics.

    The refusal is on ABSENCE, never on multiplicity: a frame holding
    several distinct ``(data_origin, reduction)`` pairs is exactly the
    mixed sweep this exists to make readable, so it is written. What is
    refused is a frame that cannot answer the question at all, or one
    whose answer contradicts itself.

    Parameters
    ----------
    frame : pandas.DataFrame
        The table to write, carrying ``data_origin`` and ``reduction``
        columns whose values are keys of
        :data:`~pyflightstream.results.DATA_ORIGIN_CODES` and
        :data:`~pyflightstream.results.REDUCTION_CODES`.
    path : str or Path
        Target csv file; its parent folder must exist.
    overwrite : bool, optional
        Whether an existing file may be replaced. True by default, which
        is what this module has always done; the non-overwrite policy of
        the flow-visualization writers is a separate decision and this
        function does not smuggle it in.

    Returns
    -------
    Path
        The written file.

    Raises
    ------
    MalformedOutputError
        When either provenance column is absent, when a cell is empty or
        is not a published token, or when a row says its numbers are
        ``reduced`` and names no reduction.

    Examples
    --------
    >>> import pandas as pd
    >>> from pyflightstream.results import write_table
    >>> frame = pd.DataFrame(
    ...     {"CL": [0.4], "data_origin": ["raw"], "reduction": ["none"]}
    ... )
    >>> written = write_table(frame, "polar.csv")   # doctest: +SKIP
    """
    _refuse_a_frame_that_cannot_say_what_it_is(frame)
    target = Path(path)
    if target.exists() and not overwrite:
        raise MalformedOutputError(
            f"{target} already exists and overwrite=False; write under a name that "
            "carries the point, or pass overwrite=True to replace it deliberately"
        )
    frame.to_csv(target, index=False)
    return target


def to_csv(result: object, path: str | Path) -> Path:
    """Write one parsed FlightStream result as a csv file.

    The tidy table of :func:`to_table` is written without the
    positional index, so the csv holds exactly the documented columns
    in their documented units, plus the ``data_origin`` and
    ``reduction`` columns every file this package writes carries
    (PFS-2014.05). It routes through :func:`write_table`, so a table
    that cannot say what produced its numbers is refused here too.

    Parameters
    ----------
    result : object
        One parsed result of the kinds :func:`to_table` covers.
    path : str or Path
        Target csv file; its parent folder must exist.

    Returns
    -------
    Path
        The written file.
    """
    return write_table(to_table(result), path)


def _refuse_a_frame_that_cannot_say_what_it_is(frame: pd.DataFrame) -> None:
    """Refuse a table whose rows cannot be traced to raw or reduced.

    Parameters
    ----------
    frame : pandas.DataFrame
        The table about to be written.

    Raises
    ------
    MalformedOutputError
        With the column or the offending values named.
    """
    missing = [name for name in PROVENANCE_COLUMNS if name not in frame.columns]
    if missing:
        raise MalformedOutputError(
            f"this table carries no {' and no '.join(missing)} column, so a reader "
            "cannot tell whether a row's numbers came off the run or out of a "
            "reduction without opening another file. Build it through to_table, "
            "run_table or sweep_table, which stamp both columns"
        )
    for column, published in (
        (DATA_ORIGIN_COLUMN, DATA_ORIGIN_CODES),
        (REDUCTION_COLUMN, REDUCTION_CODES),
    ):
        seen = {str(value) for value in frame[column].tolist()}
        unknown = sorted(value for value in seen if value not in published)
        if unknown:
            raise MalformedOutputError(
                f"the {column} column holds {unknown}, which this package does not "
                f"publish; the tokens are {', '.join(sorted(published))}. An empty "
                "cell is refused for the same reason: it reads back out of a csv as "
                "NaN, so the identifier would not survive its own file"
            )
    contradictory = frame[
        (frame[DATA_ORIGIN_COLUMN] == "reduced") & (frame[REDUCTION_COLUMN] == "none")
    ]
    if not contradictory.empty:
        raise MalformedOutputError(
            f"{len(contradictory)} row(s) say their numbers are reduced and name no "
            "reduction, which is a contradiction rather than a default: name the "
            "reduction that produced them, or say the numbers are raw"
        )


def run_table(record: RunRecord, *, loads: LoadsReport | None = None) -> pd.DataFrame:
    """Join one manifest record with its parsed loads into one wide row.

    The row carries the run identity and conditions from the manifest
    (``run_id``, ``sim_id``, the ``data_origin`` and ``reduction`` pair
    of PFS-2014.05, the sweep point axes in their sweep units:
    alpha and beta in deg, advance_ratio dimensionless), the recorded
    versions and outcome (``fs_version_requested``,
    ``fs_version_reported``, ``fs_build``, ``package_version``,
    ``status``, ``iterations``, ``residual``, ``wall_time_s`` in s),
    and, when ``loads`` is given, the analysis ``frame``, the
    ``force_units`` / ``moment_units`` metadata, and the Total row
    coefficients under their printed names in those printed units.

    Parameters
    ----------
    record : RunRecord
        One manifest record, read through
        :meth:`pyflightstream.workspace.CampaignWorkspace.read_manifest`.
    loads : LoadsReport, optional
        The run's parsed loads spreadsheet, for example from
        :func:`parse_run_loads`; None keeps the identity and outcome
        columns only, which is how failed points appear in a sweep.

    Returns
    -------
    pandas.DataFrame
        One row; missing numeric outcomes are NaN.
    """
    return pd.DataFrame([_run_row(record, loads)])


def parse_run_loads(
    workspace: CampaignWorkspace,
    record: RunRecord | str,
    *,
    loads_file: str | None = None,
) -> LoadsReport:
    """Resolve and parse the loads spreadsheet of one recorded run.

    The record's collected outputs (paths relative to its managed
    simulation folder) are the only search space: run evidence lives
    where the manifest says it does, never where a folder name
    suggests. Without ``loads_file`` every collected output is tried
    and exactly one must parse as a loads spreadsheet. The parsed
    conditions are cross-checked against the record's sweep point
    (alpha and beta in deg), so a same-named export overwritten by a
    later point of the same simulation is refused instead of silently
    standing in for this run's coefficients.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The managed campaign workspace, already constructed. A bare
        root path is NOT accepted: taking one made this layer import
        the layer above it to build the workspace, which is the
        upward dependency AD-01 forbids. Pass
        ``CampaignWorkspace(root)``.
    record : RunRecord or str
        The manifest record, or its ``run_id`` to look up in the
        manifest.
    loads_file : str, optional
        Exact file name of the loads spreadsheet among the collected
        outputs; required when several outputs parse as loads tables.

    Returns
    -------
    LoadsReport
        The parsed spreadsheet; the version printed in its footer is
        cross-checked against the version the run requested (FR-18).

    Raises
    ------
    LoadsNotFoundError
        When no collected output yields a loads spreadsheet (the
        normal outcome of a failed point).
    AmbiguousLoadsError
        When several collected outputs parse as loads spreadsheets and
        ``loads_file`` does not single one out.
    FileNotFoundError
        When a recorded output is no longer on disk, for example after
        the simulation folder was archived.
    MalformedOutputError
        When ``workspace`` is a path rather than a constructed
        :class:`~pyflightstream.workspace.CampaignWorkspace`.
    """
    _refuse_a_bare_root(workspace, "parse_run_loads")
    record = _as_record(workspace, record)
    sim_dir = workspace.sim_dir(record.sim_id)
    if not record.outputs:
        raise LoadsNotFoundError(
            f"run {record.run_id!r} recorded no collected outputs "
            f"(status {record.status}); a point that failed before "
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET leaves no coefficient table behind"
        )
    if loads_file is not None:
        candidates = [name for name in record.outputs if Path(name).name == loads_file]
        if not candidates:
            raise LoadsNotFoundError(
                f"run {record.run_id!r} has no collected output named {loads_file!r}; "
                f"recorded outputs: {', '.join(record.outputs)}. The name must match "
                "the file the recipe exported."
            )
        report = parse_loads(
            _read_output(sim_dir, candidates[0], record),
            requested_version=record.fs_version_requested,
        )
        _check_point_printback(record, report, candidates[0])
        return report
    parsed: list[tuple[str, LoadsReport]] = []
    for name in record.outputs:
        try:
            report = parse_loads(
                _read_output(sim_dir, name, record),
                requested_version=record.fs_version_requested,
            )
        except (IncompleteOutputError, ValueError):
            continue  # not a loads spreadsheet (a solver log, a probe export, ...)
        parsed.append((name, report))
    if not parsed:
        raise LoadsNotFoundError(
            f"no collected output of run {record.run_id!r} parses as a loads "
            f"spreadsheet (status {record.status}; outputs: "
            f"{', '.join(record.outputs)}); a point that failed before "
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET leaves no coefficient table behind"
        )
    if len(parsed) > 1:
        names = ", ".join(name for name, _ in parsed)
        raise AmbiguousLoadsError(
            f"run {record.run_id!r} holds {len(parsed)} collected outputs that parse "
            f"as loads spreadsheets ({names}); pass loads_file with the exact file "
            "name of the coefficient table of this run"
        )
    name, report = parsed[0]
    _check_point_printback(record, report, name)
    return report


def sweep_table(
    workspace: CampaignWorkspace,
    *,
    loads_file: str | None = None,
    require_loads: bool = True,
) -> pd.DataFrame:
    """Assemble the tidy table of a whole campaign sweep.

    One row per manifest record, in manifest order: the run identity,
    sweep point, versions, and outcome of :func:`run_table`, joined
    with the Total coefficients of each run's loads spreadsheet
    resolved through :func:`parse_run_loads`. Runs without a loads
    spreadsheet (failed points) keep their identity row with NaN
    coefficients, so the sweep table always accounts for every
    executed point. ``DataFrame.to_csv(path, index=False)`` then
    writes the final csv.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The managed campaign workspace, already constructed. A bare
        root path is NOT accepted, for the reason
        :func:`parse_run_loads` states: pass
        ``CampaignWorkspace(root)``.
    loads_file : str, optional
        Exact loads file name per run, forwarded to
        :func:`parse_run_loads`; needed when the recipes export more
        than one file that parses as a loads spreadsheet.
    require_loads : bool, optional
        Whether a sweep in which NO run yielded coefficients is an
        error. True by default, which is the historical behaviour and
        the right answer for a caller asking for a polar. Pass False
        where the table is being written as the record of what ran
        (PFS-2014.03): a campaign whose every point failed still has to
        leave a file a colleague can open, and raising here would leave
        nothing to write. The condition is warned about instead, and
        the identity rows are returned; per-record misses are already
        tolerated either way, as NaN coefficient rows.

    Returns
    -------
    pandas.DataFrame
        The sweep table; sweep point axes are in their sweep units
        (alpha and beta in deg, advance_ratio dimensionless) and the
        coefficient columns follow each run's printed units, exposed
        in the ``force_units`` / ``moment_units`` columns. Every row
        also carries ``data_origin`` and ``reduction`` (PFS-2014.05),
        which is what lets a mixed steady and unsteady sweep be read
        without opening another file.

    Raises
    ------
    MalformedOutputError
        When the manifest holds no records, or when ``workspace`` is a
        path rather than a constructed
        :class:`~pyflightstream.workspace.CampaignWorkspace`.
    LoadsNotFoundError
        When no successful run yields a coefficient table (which points
        at a wrong ``loads_file`` name) and ``require_loads`` is True.

    Warns
    -----
    UserWarning
        In the same condition when ``require_loads`` is False.

    Examples
    --------
    >>> from pyflightstream.results import sweep_table
    >>> from pyflightstream.workspace import CampaignWorkspace
    >>> table = sweep_table(CampaignWorkspace("campaign"))   # doctest: +SKIP
    >>> table[["run_id", "alpha", "CL"]]                     # doctest: +SKIP
    """
    _refuse_a_bare_root(workspace, "sweep_table")
    records = workspace.read_manifest()
    if not records:
        raise MalformedOutputError(
            f"the campaign root {workspace.root} has no manifest records; "
            "run_campaign writes one runs.json record per executed point, so "
            "aggregate after the campaign ran, and check the root path"
        )
    rows: list[dict[str, object]] = []
    runs_with_loads = 0
    for record in records:
        try:
            loads = parse_run_loads(workspace, record, loads_file=loads_file)
            runs_with_loads += 1
        except LoadsNotFoundError:
            loads = None  # the row keeps identity and status, coefficients stay NaN
        rows.append(_run_row(record, loads))
    if runs_with_loads == 0:
        successful = [r.run_id for r in records if not r.status.startswith("FAILED")]
        if successful:
            hint = (
                f"no collected output is named {loads_file!r}"
                if loads_file is not None
                else "no collected output parses as a loads spreadsheet"
            )
            complaint = (
                f"none of the {len(successful)} successful runs yielded a coefficient "
                f"table: {hint}. Check the exported file name against the recorded "
                f"outputs, for example {records[0].outputs!r} for run "
                f"{records[0].run_id!r}."
            )
            if require_loads:
                raise LoadsNotFoundError(complaint)
            warnings.warn(complaint, stacklevel=2)
    return pd.DataFrame(rows)


def _stamped(frame: pd.DataFrame, *, origin: str, reduction: str) -> pd.DataFrame:
    """Add the two provenance columns to a whole-file table (PFS-2014.05).

    A single parsed result is one provenance throughout, so the columns
    are constant here and per row only where a file MIXES the two, which
    is the sweep table. They are written on the frame all the same: a
    reader must be able to answer the question with the one file in hand,
    and "this one is constant so it needs no column" is exactly how a
    file ends up needing another file.

    Parameters
    ----------
    frame : pandas.DataFrame
        The tidy table, already built.
    origin : str
        One key of :data:`~pyflightstream.results.DATA_ORIGIN_CODES`.
    reduction : str
        One key of :data:`~pyflightstream.results.REDUCTION_CODES`.

    Returns
    -------
    pandas.DataFrame
        The same table with the two columns appended.
    """
    frame[DATA_ORIGIN_COLUMN] = origin
    frame[REDUCTION_COLUMN] = reduction
    return frame


def _loads_frame(report: LoadsReport) -> pd.DataFrame:
    """One row per surface plus Total, with the printed units alongside."""
    rows = []
    for surface, coefficients in {**report.surfaces, "Total": report.total}.items():
        row: dict[str, object] = {"surface": surface}
        row.update(coefficients)
        row["force_units"] = report.force_units
        row["moment_units"] = report.moment_units
        rows.append(row)
    # The solver did the averaging on an unsteady export, so the numbers
    # are still raw off the run and it is the reduction token that names
    # what they are.
    return _stamped(
        pd.DataFrame(rows),
        origin="raw",
        reduction=reduction_for_solver_mode(report.solver_mode),
    )


def _residual_history_frame(history: list[ResidualSample]) -> pd.DataFrame:
    """Tabulate the residual history in iteration order, dimensionless."""
    # ``none`` rather than ``unknown``, and the difference is not cosmetic.
    # A residual history is a per-iteration reading, so no reduction is
    # applicable to it at all, whereas an unread solver mode on a
    # COEFFICIENT row leaves open whether the number was averaged.
    return _stamped(
        pd.DataFrame(
            {
                "iteration": [sample.iteration for sample in history],
                "velocity_residual": [sample.velocity_residual for sample in history],
                "pressure_residual": [sample.pressure_residual for sample in history],
            }
        ),
        origin="raw",
        reduction="none",
    )


def _probe_points_frame(report: ProbePointsReport) -> pd.DataFrame:
    """Tabulate the probe table under its printed names, rows in probe order."""
    # A probe export is a point sample, so nothing was averaged to make it
    # (see the residual history above for why that is ``none`` and not
    # ``unknown``).
    return _stamped(
        pd.DataFrame(report.values, columns=list(report.columns)),
        origin="raw",
        reduction="none",
    )


def _sectional_loads_frame(report: object) -> pd.DataFrame:
    """Tabulate the sectional loads under the unit-suffixed column names.

    Duck-typed on the ``columns`` / ``values`` attributes of the FSI
    ``SectionalLoadsReport``, so tabulating an already parsed report
    never needs the optional extra to be importable again.
    """
    printed = tuple(report.columns)  # type: ignore[attr-defined]
    expected = tuple(_SECTIONAL_COLUMN_UNITS)
    if printed != expected:
        raise ValueError(
            f"the sectional loads report names columns {printed}, expected "
            f"{expected}; the unit-suffixed mapping (offset_m .. moment_qc_nm_per_m) "
            "is only valid for the layout the FSI parser asserts"
        )
    columns = [_SECTIONAL_COLUMN_UNITS[name] for name in printed]
    return _stamped(
        pd.DataFrame(report.values, columns=columns),  # type: ignore[attr-defined]
        origin="raw",
        reduction=reduction_for_solver_mode(getattr(report, "solver_mode", None)),
    )


def _sectional_loads_type() -> type | None:
    """Return the optional SectionalLoadsReport type, or None without it.

    The import is deferred and failure tolerated because the sectional
    loads parser ships with the optional ``[fsi]`` extra; the core
    tables never require it.
    """
    try:
        from pyflightstream.fsi.loads import SectionalLoadsReport
    except ImportError:
        return None
    return SectionalLoadsReport


def _looks_like_sectional(result: object) -> bool:
    """Duck-check for a sectional loads report when the extra is absent."""
    return all(
        hasattr(result, attribute)
        for attribute in ("columns", "values", "offset_m", "moment_qc_nm_per_m")
    )


def _run_row(record: RunRecord, loads: LoadsReport | None) -> dict[str, object]:
    """Build the wide row of one run: manifest identity plus coefficients."""
    row: dict[str, object] = {"run_id": record.run_id, "sim_id": record.sim_id}
    # PER ROW, straight after the identity, because this is the one table
    # this package writes that MIXES provenances: a steady point's
    # coefficients are a direct integration and an unsteady point's are the
    # solver's own time average, under the same column names.
    row[DATA_ORIGIN_COLUMN] = "raw"
    row[REDUCTION_COLUMN] = (
        "unknown" if loads is None else reduction_for_solver_mode(loads.solver_mode)
    )
    reserved = set(_RUN_IDENTITY_COLUMNS + _RUN_OUTCOME_COLUMNS + PROVENANCE_COLUMNS)
    reserved.update(("frame", "force_units", "moment_units"))
    for axis, value in record.point.items():
        if axis in reserved:
            raise ValueError(
                f"sweep point axis {axis!r} of run {record.run_id!r} collides with a "
                "fixed run table column; rename the axis so identity and conditions "
                "stay distinguishable in the wide row"
            )
        row[axis] = float(value)
    row["fs_version_requested"] = record.fs_version_requested
    row["fs_version_reported"] = record.fs_version_reported
    row["fs_build"] = record.fs_build
    row["package_version"] = record.package_version
    row["status"] = str(record.status)
    row["iterations"] = math.nan if record.iterations is None else record.iterations
    row["residual"] = math.nan if record.residual is None else record.residual
    row["wall_time_s"] = math.nan if record.wall_time_s is None else record.wall_time_s
    if loads is not None:
        row["frame"] = loads.frame
        row["force_units"] = loads.force_units
        row["moment_units"] = loads.moment_units
        for column, value in loads.total.items():
            if column in row:
                raise ValueError(
                    f"coefficient column {column!r} of run {record.run_id!r} collides "
                    "with an identity or sweep point column of the wide row; rename "
                    "the sweep axis so the coefficient keeps its printed name"
                )
            row[column] = value
    return row


def _refuse_a_bare_root(workspace: object, caller: str) -> None:
    """Refuse a root path where a constructed workspace is required.

    The replacement for the coercion helper this module carried until
    2026-08-19 (OPS-2009.02.05). That helper built a
    :class:`~pyflightstream.workspace.CampaignWorkspace` out of a path,
    which needed an import of the layer ABOVE this one, deferred to call
    time so it would not show at module level. The direction was the
    same either way, so the coercion went and the refusal took its
    place.

    Duck-typed on the two methods the callers use, not on the class, so
    a test double or a subclass is accepted exactly as before and this
    module still names no type it would have to import.

    The refusal is a :class:`~pyflightstream.results.MalformedOutputError`
    rather than a bare ``TypeError``: every exception a public name of
    this package raises is a catalogued class descending from
    ``PyflightstreamError`` and keeping its standard-library base, so
    ``except ValueError`` around these calls still catches it.

    Parameters
    ----------
    workspace : object
        What the caller passed.
    caller : str
        Public function name, quoted back in the message so the reader
        knows which call to fix.

    Raises
    ------
    MalformedOutputError
        When ``workspace`` does not offer the managed-workspace surface.
    """
    if hasattr(workspace, "read_manifest") and hasattr(workspace, "sim_dir"):
        return
    raise MalformedOutputError(
        f"{caller}() needs a constructed CampaignWorkspace and got "
        f"{type(workspace).__name__}. Until v0.8.0 it also accepted the campaign "
        "root as a path and built the workspace itself, which made the results "
        "layer import the execution layer above it; that convenience is gone. "
        "Write: from pyflightstream.workspace import CampaignWorkspace, then "
        f"{caller}(CampaignWorkspace(root), ...). The workspace is what knows "
        "where the manifest and the simulation folders are, so constructing it "
        "once and passing it is also what lets several calls share one root."
    )


def _as_record(workspace: CampaignWorkspace, record: RunRecord | str) -> RunRecord:
    """Look a run_id up in the manifest, or pass a record through."""
    if not isinstance(record, str):
        return record
    records = workspace.read_manifest()
    for candidate in records:
        if candidate.run_id == record:
            return candidate
    known = ", ".join(candidate.run_id for candidate in records[:20]) or "none"
    raise ValueError(
        f"run_id {record!r} is not in the manifest of {workspace.root}; the manifest "
        f"is the only run identity authority, and it records: {known}"
    )


def _read_output(sim_dir: Path, name: str, record: RunRecord) -> str:
    """Read one collected output of a run, refusing evidence gaps."""
    path = Path(sim_dir) / name
    if not path.is_file():
        raise FileNotFoundError(
            f"the collected output {name!r} of run {record.run_id!r} is not on disk "
            f"under {sim_dir}; the simulation folder may have been archived or "
            "cleaned, and sweep tables read the live sims folders only"
        )
    return path.read_text(encoding="utf-8", errors="replace")


def _check_point_printback(record: RunRecord, report: LoadsReport, name: str) -> None:
    """Refuse a loads export whose printed conditions contradict the record.

    Within one simulation folder a later sweep point overwrites a same
    named export, so a spreadsheet printing another point's angles is
    not the evidence of this run; exporting one uniquely named
    spreadsheet per point avoids the overwrite.
    """
    # REV010-001. This comparison used to live here and ONLY here, which is
    # why a wrong-point export could be recorded CONVERGED and contradicted
    # afterwards by a helper the manifest never consults. It is now the
    # shared bind_conditions, called by the assessor before the status is
    # decided and by this reader afterwards, so the two can never disagree
    # about what counts as the same point.
    binding = bind_conditions(record.point, reported=report)
    if binding.mismatches:
        raise ValueError(
            f"the loads spreadsheet {name!r} of run {record.run_id!r} is evidence "
            f"of a different operating point than the manifest records: "
            f"{binding.describe()}; a later point of the same simulation "
            "overwrites a same named export, so this file is not the evidence "
            "of this run. Export one uniquely named spreadsheet per point."
        )
