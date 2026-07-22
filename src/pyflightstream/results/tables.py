"""Tabular views of parsed FlightStream results, on pandas.

Pipeline role: turns the typed parser outputs of
:mod:`pyflightstream.results` (and, when the optional ``[fsi]`` extra
is installed, the sectional loads report of
:mod:`pyflightstream.fsi.loads`) into tidy :class:`pandas.DataFrame`
tables, then assembles run-level and sweep-level tables by joining the
campaign manifest records with the parsed coefficient tables. Tables
are the pandas domain of the package; labeled physical fields stay on
xarray in :mod:`pyflightstream.farfield` (PLN-006 division).

Three steps of one ladder:

1. :func:`to_dataframe` / :func:`to_csv` tabulate any single parsed
   result.
2. :func:`run_frame` joins one manifest :class:`RunRecord` (identity,
   sweep point, versions, outcome) with the run's parsed loads into
   one wide row; :func:`parse_run_loads` resolves and parses that
   loads spreadsheet from the managed workspace through the record's
   collected outputs.
3. :func:`sweep_frame` reads a whole campaign manifest and returns the
   tidy sweep table, one row per run; ``DataFrame.to_csv`` then writes
   the final csv.

Column names carry units the way the source dataclasses document them:
printed coefficient names (Cx .. CMz) with the ``force_units`` /
``moment_units`` metadata alongside for the loads spreadsheet,
dimensionless residuals for the solver log, printed column names for
the probe export (X, Y, Z in simulation length units), and
unit-suffixed names (``offset_m``, ``fx_n_per_m``, ...) for the
sectional loads, matching :class:`SectionalLoadsReport`.

The manifest is read only through the public API of
:mod:`pyflightstream.files`, imported inside the functions that need
it: importing the results parsing layer never pulls the execution
layers, so the downward dependency order of the package is preserved
at import time.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from pyflightstream.results import (
    IncompleteOutputError,
    LoadsReport,
    ProbePointsReport,
    ResidualSample,
    parse_loads,
)

if TYPE_CHECKING:  # typing only: no runtime import of the execution layers
    from pyflightstream.files import CampaignWorkspace, RunRecord

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

# Sweep axes whose values the loads spreadsheet prints back; used to
# cross-check that a collected export is the evidence of its record.
_POINT_PRINTBACK = (("alpha", "angle_of_attack_deg"), ("beta", "sideslip_deg"))
# Loads spreadsheets print angles with three decimals, so a half count
# of the last digit is the tightest honest comparison tolerance [deg].
_POINT_TOLERANCE_DEG = 5e-4


class LoadsNotFoundError(ValueError):
    """No collected output of a run yields its loads spreadsheet.

    Expected for failed points: a run that stopped before
    EXPORT_SOLVER_ANALYSIS_SPREADSHEET leaves no coefficient table
    behind, and :func:`sweep_frame` turns this into a row without
    coefficient columns instead of dropping the run.
    """


class AmbiguousLoadsError(ValueError):
    """Several collected outputs of one run parse as loads spreadsheets.

    The resolver refuses to guess which table is the run's coefficient
    evidence; pass ``loads_file`` with the exact exported file name.
    """


def to_dataframe(result: object) -> pd.DataFrame:
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

    Parameters
    ----------
    result : object
        One parsed result of the kinds above.

    Returns
    -------
    pandas.DataFrame
        Tidy table, one observation per row; write it with
        :func:`to_csv` or ``DataFrame.to_csv``.
    """
    if isinstance(result, LoadsReport):
        return _loads_frame(result)
    if isinstance(result, ProbePointsReport):
        return _probe_points_frame(result)
    if isinstance(result, (list, tuple)):
        if result and all(isinstance(sample, ResidualSample) for sample in result):
            return _residual_history_frame(list(result))
        if not result:
            raise ValueError(
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
        raise ImportError(
            "this object looks like a SectionalLoadsReport but "
            "pyflightstream.fsi.loads is not importable in this environment; the "
            "sectional loads parser ships with the optional FSI extra, so install "
            "it with: pip install pyflightstream[fsi]"
        )
    raise TypeError(
        f"to_dataframe cannot tabulate {type(result).__name__}; supported parsed "
        "results are LoadsReport (parse_loads), a list of ResidualSample "
        "(parse_residual_history), ProbePointsReport (parse_probe_points), and "
        "SectionalLoadsReport (pyflightstream.fsi.loads, optional [fsi] extra)"
    )


def to_csv(result: object, path: str | Path) -> Path:
    """Write one parsed FlightStream result as a csv file.

    The tidy table of :func:`to_dataframe` is written without the
    positional index, so the csv holds exactly the documented columns
    in their documented units.

    Parameters
    ----------
    result : object
        One parsed result of the kinds :func:`to_dataframe` covers.
    path : str or Path
        Target csv file; its parent folder must exist.

    Returns
    -------
    Path
        The written file.
    """
    target = Path(path)
    to_dataframe(result).to_csv(target, index=False)
    return target


def run_frame(record: RunRecord, loads: LoadsReport | None = None) -> pd.DataFrame:
    """Join one manifest record with its parsed loads into one wide row.

    The row carries the run identity and conditions from the manifest
    (``run_id``, ``sim_id``, the sweep point axes in their sweep units:
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
        :meth:`pyflightstream.files.CampaignWorkspace.read_manifest`.
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
    workspace: CampaignWorkspace | str | Path,
    record: RunRecord | str,
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
    workspace : CampaignWorkspace, str, or Path
        The managed campaign workspace, or its root folder.
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
    """
    workspace = _as_workspace(workspace)
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


def sweep_frame(
    workspace: CampaignWorkspace | str | Path,
    loads_file: str | None = None,
) -> pd.DataFrame:
    """Assemble the tidy table of a whole campaign sweep.

    One row per manifest record, in manifest order: the run identity,
    sweep point, versions, and outcome of :func:`run_frame`, joined
    with the Total coefficients of each run's loads spreadsheet
    resolved through :func:`parse_run_loads`. Runs without a loads
    spreadsheet (failed points) keep their identity row with NaN
    coefficients, so the sweep table always accounts for every
    executed point. ``DataFrame.to_csv(path, index=False)`` then
    writes the final csv.

    Parameters
    ----------
    workspace : CampaignWorkspace, str, or Path
        The managed campaign workspace, or its root folder.
    loads_file : str, optional
        Exact loads file name per run, forwarded to
        :func:`parse_run_loads`; needed when the recipes export more
        than one file that parses as a loads spreadsheet.

    Returns
    -------
    pandas.DataFrame
        The sweep table; sweep point axes are in their sweep units
        (alpha and beta in deg, advance_ratio dimensionless) and the
        coefficient columns follow each run's printed units, exposed
        in the ``force_units`` / ``moment_units`` columns.

    Raises
    ------
    ValueError
        When the manifest holds no records, or when no successful run
        yields a coefficient table (which points at a wrong
        ``loads_file`` name).
    """
    workspace = _as_workspace(workspace)
    records = workspace.read_manifest()
    if not records:
        raise ValueError(
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
            raise LoadsNotFoundError(
                f"none of the {len(successful)} successful runs yielded a coefficient "
                f"table: {hint}. Check the exported file name against the recorded "
                f"outputs, for example {records[0].outputs!r} for run "
                f"{records[0].run_id!r}."
            )
    return pd.DataFrame(rows)


def _loads_frame(report: LoadsReport) -> pd.DataFrame:
    """One row per surface plus Total, with the printed units alongside."""
    rows = []
    for surface, coefficients in {**report.surfaces, "Total": report.total}.items():
        row: dict[str, object] = {"surface": surface}
        row.update(coefficients)
        row["force_units"] = report.force_units
        row["moment_units"] = report.moment_units
        rows.append(row)
    return pd.DataFrame(rows)


def _residual_history_frame(history: list[ResidualSample]) -> pd.DataFrame:
    """Tabulate the residual history in iteration order, dimensionless."""
    return pd.DataFrame(
        {
            "iteration": [sample.iteration for sample in history],
            "velocity_residual": [sample.velocity_residual for sample in history],
            "pressure_residual": [sample.pressure_residual for sample in history],
        }
    )


def _probe_points_frame(report: ProbePointsReport) -> pd.DataFrame:
    """Tabulate the probe table under its printed names, rows in probe order."""
    return pd.DataFrame(report.values, columns=list(report.columns))


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
    return pd.DataFrame(report.values, columns=columns)  # type: ignore[attr-defined]


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
    reserved = set(_RUN_IDENTITY_COLUMNS + _RUN_OUTCOME_COLUMNS)
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


def _as_workspace(workspace: CampaignWorkspace | str | Path) -> CampaignWorkspace:
    """Coerce a root path to the managed workspace of the files layer.

    The import is deferred to the call (module docstring): tabulating
    results must not make the parsing layer import the execution
    layers at module import time.
    """
    if hasattr(workspace, "read_manifest") and hasattr(workspace, "sim_dir"):
        return workspace
    from pyflightstream.files import CampaignWorkspace

    return CampaignWorkspace(workspace)


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
    for axis, attribute in _POINT_PRINTBACK:
        if axis not in record.point:
            continue
        printed = float(getattr(report, attribute))
        recorded = float(record.point[axis])
        if abs(printed - recorded) > _POINT_TOLERANCE_DEG:
            raise ValueError(
                f"the loads spreadsheet {name!r} of run {record.run_id!r} prints "
                f"{axis} {printed:+.3f} deg but the manifest records the point at "
                f"{axis} {recorded:+.3f} deg; a later point of the same simulation "
                "overwrites a same named export, so this file is not the evidence "
                "of this run. Export one uniquely named spreadsheet per point."
            )
