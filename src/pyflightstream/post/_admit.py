"""Admitting a simulation's records: which can supply a product row, and what each states.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0), the first part of the simulation stage of
:mod:`pyflightstream.post._sim`. Each record of a simulation is read once,
in the records' order, into an :class:`_Admitted`:

* a record that names no output, whose loads export is not on disk or is not
  a loads table, or whose loads are not printed in coefficients, is SKIPPED
  under ``runs/<run id>`` with the reason, never dropped in silence;
* an admitted record becomes a point: its loads, its own state resolved
  from its row, the induced drag the solver declined, the freeze its native
  log shows, and its sectional, plots and probe exports, each said once per
  point where a product cannot say it;
* its REDUCTION PLAN and its averaging WINDOW are the matrix's as it stands
  today where the row states them, else the record's, else the window the
  run defaulted to, said once;
* the first record that names its probe points gives the positions every
  point's probe table carries.

The containers it fills become fields of the
:class:`~pyflightstream.post._sim.SimContext`, so each step reads the very
dictionaries admission filled.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pyflightstream.post._stage as _stage
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import PprocSpec, classify_outputs
from pyflightstream.cases.windows import regate, replan
from pyflightstream.post._condition import (
    _defaulted_window,
    _in_coefficients,
    _matrix_window,
    _recorded_window,
    _stated_window,
    _vorticity_selection,
    point_state,
)
from pyflightstream.post._stage import PROBES_DIR
from pyflightstream.post._tables import ProductError
from pyflightstream.post.point_tables import read_probe_positions
from pyflightstream.post.polar import PolarPoint, declined_induced_drag
from pyflightstream.results import FrozenSolve, LoadsReport, classify_solver_mode, parse_loads

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import RunRecord


@dataclass
class _Admitted:
    """The records of one simulation that can supply a product row, as they are admitted.

    Filled by :func:`_admit`, one record at a time, in the records' order; the
    containers then become fields of the :class:`SimContext`, so a step reads
    the very dictionaries the first part filled.
    """

    skipped: dict[str, str]
    points: list[PolarPoint] = field(default_factory=list)
    record_of: dict[str, RunRecord] = field(default_factory=dict)
    sources: dict[str, list[str]] = field(default_factory=dict)
    exports: dict[str, tuple[Path | None, Path | None, Path | None]] = field(default_factory=dict)
    plans: dict[str, dict[str, object] | None] = field(default_factory=dict)
    point_windows: dict[str, tuple[int, int]] = field(default_factory=dict)
    frozen_points: dict[str, FrozenSolve] = field(default_factory=dict)
    probe_positions: dict[int, tuple[float, float, float, str]] = field(default_factory=dict)


# ------------------------------------------------------------------ admitting the records


def _admit(
    admitted: _Admitted,
    record: RunRecord,
    sim_dir: Path,
    matrix_row: MatrixRow | None,
    pproc: PprocSpec,
) -> None:
    """Admit one record: its point, its exports, its plan and window, its probe positions."""
    loads = _loads_of(record, sim_dir, admitted.skipped)
    if loads is None:
        return
    stem = _admit_point(admitted, record, loads)
    _admit_windows(admitted, record, stem, matrix_row, pproc)
    # FR-91. Where this run put its probe points. Per SIM and identical
    # across the sweep, so the first record that names one answers for
    # every point; a record written before 0.16.0 names none and the
    # probe table is then written without the position columns, as it
    # always was.
    if record.probe_points_file and not admitted.probe_positions:
        # CAUGHT HERE, AND THE BLAST RADIUS IS WHY. `read_probe_positions`
        # refuses a file that is there and cannot be read, which is the
        # distinction round one asked for; but this function's caller
        # catches `ProductError` per SIMULATION, so letting it out would
        # cost this simulation its polar table, its plots tables and every
        # reduction over one unreadable positions file. That is the rename
        # taking a product away that the probe-export reader twenty lines
        # below is written against (the QA lens, round two, 2026-09-11).
        try:
            admitted.probe_positions.update(
                read_probe_positions(sim_dir / record.probe_points_file)
            )
        except ProductError as error:
            admitted.skipped[f"{PROBES_DIR}/{record.probe_points_file}"] = str(error)


def _loads_of(
    record: RunRecord, sim_dir: Path, skipped: dict[str, str]
) -> tuple[str, LoadsReport, dict[str, Path], dict[str, str]] | None:
    """Return a record's loads export, read, with its outputs; else name why it has none."""
    if not record.outputs:
        # NAMED, NOT DROPPED. A converged record with no outputs is what a
        # submitted sweep leaves per point, and it vanished from every
        # product on a bare `continue` with the manifest none the wiser.
        skipped[f"runs/{record.run_id}"] = (
            f"this run has status {record.status.value} and names no output file, so no "
            "product holds a row of it; collect it, or look at how it was submitted"
        )
        return None
    kinds = classify_outputs([Path(o).name for o in record.outputs])
    by_name = {Path(o).name: sim_dir / o for o in record.outputs}
    loads_name = kinds.get("loads")
    if loads_name is None or not by_name[loads_name].is_file():
        missing = (
            "no loads export among its outputs" if loads_name is None else str(by_name[loads_name])
        )
        skipped[f"runs/{record.run_id}"] = (
            f"this run has status {record.status.value} and its loads table is not on disk "
            f"({missing}), so no product holds a row of it"
        )
        return None
    text = by_name[loads_name].read_text(encoding="utf-8", errors="replace")
    try:
        report = parse_loads(text)
    except PyflightstreamError as error:
        skipped[f"runs/{record.run_id}"] = (
            f"{by_name[loads_name]} is not a loads table: {error}. "
            "Recollect the complete loads export or run this point again."
        )
        return None
    if not _in_coefficients(report):
        # G09 (0.27.0): a setup's load_units makes the solver print forces and
        # moments under the columns every product reads as coefficients.
        skipped[f"runs/{record.run_id}"] = (
            f"{by_name[loads_name]} prints its loads in {report.force_units or 'no unit'} "
            f"and its moments in {report.moment_units or 'no unit'}, and every product "
            "here is written in coefficients, so none holds a row of it. The setup this "
            "row names states load_units; drop it, or state COEFFICIENTS, and run the "
            "point again."
        )
        return None
    return loads_name, report, by_name, kinds


def _admit_point(
    admitted: _Admitted,
    record: RunRecord,
    loads: tuple[str, LoadsReport, dict[str, Path], dict[str, str]],
) -> str:
    """Admit one record's point and exports, warning what its export says of it."""
    loads_name, report, by_name, kinds = loads
    stem = loads_name[: -len(".txt")]
    point = PolarPoint(
        name=stem,
        loads=report,
        loads_path=by_name[loads_name],
        point=dict(record.point),
        state=point_state(record),
        vorticity_selection=_vorticity_selection(record),
    )
    admitted.points.append(point)
    admitted.record_of[stem] = record
    declined = declined_induced_drag(report, point.vorticity_selection)
    if declined:
        # ONCE PER POINT, not once per group: the polar of every group
        # holding one of these surfaces writes NA where it sums them.
        warn(
            f"point={stem} product=polars: the solver printed CDi exactly 0 for "
            f"{', '.join(declined)}, on the vorticity induced-drag list "
            "(SET_VORTICITY_DRAG_BOUNDARIES); a boundary there without a defined "
            "trailing edge is not computed (SRC-003 p.202). The Total row keeps the "
            "solver's printed number; every sum this package makes over those surfaces "
            "is NA. Give them a trailing edge, leave them off the list, or raise "
            "SET_SIGNIFICANT_DIGITS if the induced drag is merely small.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    log_path = by_name.get(kinds.get("log", ""))
    if log_path is not None:
        # LOOKED UP AT ITS ONE HOME, as the campaign stage looks it up: the stage's
        # one verdict of a frozen solve is replaced once, there, by a test.
        frozen = _stage.freeze_of_log(
            log_path, steady=classify_solver_mode(report.solver_mode) == "steady"
        )
        if frozen is not None:
            admitted.frozen_points[stem] = frozen
            warn(
                f"point={stem} product=native-log: {frozen.reason}. "
                "Recollect the native log or run the point again to settle it.",
                PyflightstreamWarning,
                stacklevel=2,
            )
    _warn_the_point_s_state(stem, report, point)
    sloads_path = by_name.get(kinds["sectional_loads"]) if "sectional_loads" in kinds else None
    plots_path = by_name.get(kinds["plots"]) if "plots" in kinds else None
    probes_path = by_name.get(kinds["probes"]) if "probes" in kinds else None
    admitted.exports[stem] = (sloads_path, plots_path, probes_path)
    return stem


def _warn_the_point_s_state(stem: str, report: LoadsReport, point: PolarPoint) -> None:
    """Say once per point what the export and the record state that the products cannot."""
    vinf = report.freestream_velocity_m_s
    vref = getattr(report, "reference_velocity_m_s", None)
    if (
        isinstance(vinf, int | float)
        and isinstance(vref, int | float)
        and abs(vref - vinf) > 1e-6 * max(1.0, abs(vinf))
    ):
        # SAID ONCE PER POINT (0.24.0). Both velocities are columns of every
        # product now, so nothing is hidden; what a reader still cannot see
        # from one file is that the FAMILIES differ in which one they use.
        warn(
            f"{stem}: the export states a reference velocity of {vref:g} m/s and a free "
            f"stream of {vinf:g} m/s. The steady polar's coefficients are normalised by "
            "the REFERENCE velocity; the plots table, the reductions and the unsteady "
            "polar are rescaled to the FREE STREAM. Both are in every row, as VREF and VINF.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    if point.state is not None and point.state.differs:
        warn(
            f"{stem}: the run record states the simulation's first point where this "
            f"point swept the flow ({'; '.join(point.state.differs)}). The products "
            "use the point's own state, resolved again from its row; the record is "
            "left as it was written.",
            PyflightstreamWarning,
            stacklevel=2,
        )


def _admit_windows(
    admitted: _Admitted,
    record: RunRecord,
    stem: str,
    matrix_row: MatrixRow | None,
    pproc: PprocSpec,
) -> None:
    """Resolve one point's reduction plan and averaging window, matrix first."""
    # THE MATRIX WINS THE RECORD FOR EVERY WINDOW OF THE POINT, NOT ONLY THE
    # POLAR'S (PO-01), AND PER POINT: each record carries its own clock, so a
    # count of revolutions is cut on THAT point's steps per revolution.
    row_variables = getattr(matrix_row, "variables", None)
    gate = getattr(pproc, "phase_locked", None)
    replanned = replan(record.reductions, row_variables, gate=gate)
    if replanned is not None and stem not in admitted.plans:
        ran = _recorded_window(record.reductions)
        now = _recorded_window(replanned)
        if ran is not None and now is not None and ran != now:
            # SAID, NOT ONLY DONE. The products of this point no longer
            # average what the run recorded, and a reader comparing them
            # with an earlier post needs to know that it was the matrix
            # that moved and not the data.
            warn(
                f"{stem}: the matrix now states an averaging window of steps "
                f"{now[0]} to {now[1]} and the run recorded {ran[0]} to {ran[1]}. "
                "Every reduction of this point follows the matrix; no re-run is needed.",
                PyflightstreamWarning,
                stacklevel=2,
            )
    # THE [phase_locked] TABLE IS READ AGAIN TOO, from the pproc as it stands
    # today, together with the window. Without a usable matrix window,
    # regate applies the same policy to the recorded plan instead.
    current = replanned or record.reductions
    regated = regate(current, gate) if replanned is None else None
    admitted.plans.setdefault(stem, regated or current)
    point_window = _matrix_window(matrix_row, record) or _stated_window(record)
    if point_window is None:
        point_window = _defaulted_point_window(admitted, record, stem)
    if point_window is not None:
        admitted.point_windows.setdefault(stem, point_window)
    admitted.sources.setdefault(stem, []).append(record.run_id)


def _defaulted_point_window(
    admitted: _Admitted, record: RunRecord, stem: str
) -> tuple[int, int] | None:
    """Return the window a record that stated none is averaged over, said once per point."""
    # A RECORD THAT STATED NO WINDOW IS AVERAGED OVER THE ONE IT DEFAULTED TO
    # (0.24.0, the post half of the required window). It used to take the
    # STEADY route: a polar read off the last time step, under a steady
    # name, beside a time average, with nothing marking either. A new row
    # is refused at plan; a record already held is never refused here.
    point_window = _defaulted_window(record)
    if point_window is not None and stem not in admitted.point_windows:
        key = "LAST_REVS_AVG" if record.recipe == "unsteady_rotor" else "LAST_ITERS_AVG"
        # WHERE THE WINDOW CAME FROM, as the record states it: a retired
        # `WINDOW_*` key of the row is not a default, and the warning called
        # every unstated window "the window the run defaulted to".
        entry = (record.reductions or {}).get("time_average")
        origin = entry.get("window_from") if isinstance(entry, Mapping) else None
        warn(
            f"{stem}: this record states no {key}. Its unsteady polar is averaged "
            f"over the window its run recorded, steps {point_window[0]} to "
            f"{point_window[1]}"
            + (f" ({origin})" if origin else "")
            + f". State {key} on the row and post again to choose the "
            "window; no re-run is needed.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return point_window
