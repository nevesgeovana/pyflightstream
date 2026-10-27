"""The far-field product family: Trefftz-plane and balance tables of one simulation (FR-456).

Pipeline role: the body of the post step that writes ``farfield/<group>_trefftz.csv``,
``farfield/<group>_ledgers.csv`` (``_instant`` and ``_average`` on an unsteady
row) and spanwise files ``sections/<point>_trefftz_<family>.csv`` for A or
``sections/<point>_trefftz_net_<entry>.csv`` for B from the
exports a run recorded, through the numpy core of :mod:`pyflightstream.farfield`.
It reads the exports with the ``results`` readers, turns every vector to the
far-field axes (FR-1005), and states every point an analysis cannot serve as
a named skip in ``products.json`` and a WARNING in ``post.log`` (FR-1007).
Which analysis applies to which row is the one function the plan uses
(:func:`pyflightstream.cases.farfield_inputs.applies`). A simulation whose pproc
artifact has no ``[[farfields]]`` entries writes nothing and logs nothing, so its
products keep their bytes (FR-1060).

Size exemption: this family writer keeps per-point diagnostic provenance beside
the instant/window dispatch that determines it; numerical reductions stay in farfield_fields.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np

import pyflightstream.post._reduction_stage as ff
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import classify_outputs, select_group_members
from pyflightstream.cases.farfield_inputs import (
    ROTOR_RUN_TYPES,
    UNSTEADY_RUN_TYPES,
    applies,
    few_stations_warning,
    traced_family,
)
from pyflightstream.cases.qsteady import QsteadyRecordError, read_qsteady_record
from pyflightstream.farfield import (
    TraceResult,
    calibration_scale,
    rotor_wake_lines,
    trace_coefficients,
    trace_forces,
    wake_crossings,
    wake_rotor_loads,
)
from pyflightstream.farfield.balances import DiskLoading
from pyflightstream.post._condition import (
    _recorded_speeds,
    recorded_blade_count,
    row_rotor_speeds,
)
from pyflightstream.post._reduction_stage import (
    _AXES,
    _NA,
    _farfield_window,
    _flow,
    _hub,
    _layout,
    _Probe,
)
from pyflightstream.post._tables import CONTEXT_COLUMNS, context_row, write_csv_table
from pyflightstream.post.axes import EXPORT_TO_BODY, body_to_wind, wind_force_coefficients
from pyflightstream.post.farfield_fields import (
    LEDGER_COLUMNS,
    ROTOR_LEDGER_COLUMNS,
    disk_loading,
    far_samples,
    lattice_samples,
    ledger_values,
    native_per_m,
    plane_values,
    rotor_g4,
    rotor_values,
    steady_samples,
    symmetry_excluded_orders,
)
from pyflightstream.post.rotor_table import rotor_shaft_loads
from pyflightstream.post.section_distributions import distributions_of
from pyflightstream.post.series import stamped_exports
from pyflightstream.results.loads import drag_pair
from pyflightstream.results.sectional_loads import parse_sectional_loads
from pyflightstream.results.wake import parse_wake_export
from pyflightstream.workspace.naming import sweep_file_stem

if TYPE_CHECKING:
    from pyflightstream.cases._farfield_spec import FarfieldSpec, LedgersSpec, TrefftzSpec
    from pyflightstream.post._sim import SimContext
    from pyflightstream.post.polar import PolarPoint

__all__ = [
    "FARFIELD_DIR",
    "SPANWISE_COLUMNS",
    "TREFFTZ_COLUMNS",
    "farfield_axes",
    "farfield_products",
]

#: The product folder of the far-field tables (FR-1053).
FARFIELD_DIR = "farfield"

#: The columns of ``farfield/<group>_trefftz.csv`` after ``POL``, ``STEP`` and the
#: condition block (FR-1054).
TREFFTZ_COLUMNS: tuple[str, ...] = (
    "FAMILY",
    "VARIANT",
    "CL_T",
    "CDI_T",
    "CDI_T_ISOLATED",
    "CY_T",
    "E_T",
    "AR",
    "N_TRACE",
    "X_T_M",
    "GAMMA_SCALE",
    "COVERAGE",
    "CDI_T_QERR",
    "CDI_T_VORT",
    "BERNOULLI_RESIDUAL",
    "CDI_NEAR_PRESSURE",
    "CDI_NEAR_VORTICITY",
    "P_AXIAL_W",
    "P_SWIRL_W",
    "P_CROSSFLOW_W",
    "P_TOTAL_W",
    "ETA_FF",
    # PFS-2081.97: the point's solver termination status, as the sweep table writes it.
    "STATUS",
)
#: The rotor columns (P0470-FFR): the D columns of the disk total-pressure correction
#: (option 1a) and the wake-loads columns (option 3), written before ``STATUS`` only in
#: a table where a rotor row holds a value, so a table without a rotor keeps its columns.
_ROTOR_TREFFTZ_COLUMNS: tuple[str, ...] = (
    "P_TOTAL_CORRECTED_W",
    "ETA_FF_CORRECTED",
    "T_WAKE_N",
    "Q_WAKE_NM",
    "T_NEAR_N",
    "Q_NEAR_NM",
    "DT_WAKE_COUNTS",
    "DQ_WAKE_COUNTS",
)
#: Every cell a row is built with; :func:`_write` drops the rotor columns no row holds.
_TREFFTZ_CELLS = (*TREFFTZ_COLUMNS[:-1], *_ROTOR_TREFFTZ_COLUMNS, TREFFTZ_COLUMNS[-1])
_LEDGER_CELLS = (*LEDGER_COLUMNS[:-1], *ROTOR_LEDGER_COLUMNS, LEDGER_COLUMNS[-1])
#: The columns of A's per-family and B's per-entry spanwise files (FR-1055).
SPANWISE_COLUMNS: tuple[str, ...] = (
    "POL",
    # The condition and reference block every product table carries.
    *CONTEXT_COLUMNS,
    "VARIANT",
    "FAMILY",
    "Y_M",
    "Z_M",
    "DY_M",
    "GAMMA_M2_S",
    "W_M_S",
    "ALPHA_I_DEG",
    "DI_N_M",
    "CDI_LOCAL",
    "STATUS",
)
#: A blade's trailing edge lies within this fraction of the tip radius of its hub plane
#: (the start-node rule that tells a rotor's wake lines from a wing's, P0470-FFR).
_BLADE_REACH = 0.25
_VARIANT_NAMES = {"sections": "A", "wake": "B", "plane": "C"}
#: Above this Mach number the C row is written with a WARNING that the
#: incompressible relations of the definitions page are used (FR-1036).
_INCOMPRESSIBLE_MACH = 0.3
#: A Trefftz C plane whose own lift (its vorticity's first moment) departs from
#: the solver's CL by more than this fraction is flagged: its field does not hold
#: the circulation the loads shed, so its crossflow energy is not their induced
#: drag (FR-1038; RPT-171 measured 0.74 on 26.124 and 1.05 on 26.125, one wing).
_PLANE_LIFT_TOLERANCE = 0.10
#: Trefftz A over families whose traced lift departs from the solver's CL by
#: more than this fraction is warned: another family or a body carries the
#: rest, so CDI_T and E_T are of the traced families alone (FR-1021). A wing
#: traced alone agreed to 0.15 percent (RPT-171's wing); a wing traced without
#: its body departed by 6.6 and 7 percent.
_TRACED_LIFT_TOLERANCE = 0.05


def farfield_axes(alpha_deg: float, beta_deg: float) -> np.ndarray:
    """Return the matrix taking export-frame components to the far-field axes.

    The far-field axes are the wind axes of :mod:`pyflightstream.post.axes`
    turned half a turn about their y axis: x along the free stream downstream,
    y to the right, z up, so at zero incidence and sideslip they are the export
    frame's own (x aft, y right, z up).

    Parameters
    ----------
    alpha_deg : float
        Incidence angle in degrees.
    beta_deg : float
        Sideslip angle in degrees.

    Returns
    -------
    np.ndarray
        Orthonormal free-stream axes for transforming reference-frame samples.
    """
    return EXPORT_TO_BODY @ body_to_wind(alpha_deg, beta_deg) @ EXPORT_TO_BODY


def _spec(ctx: SimContext) -> FarfieldSpec:
    """Return the simulation's ``[[farfields]]`` entry; the step runs only where there is one."""
    return cast("FarfieldSpec", ctx.pproc.farfield)


def _trefftz(ctx: SimContext) -> TrefftzSpec:
    return cast("TrefftzSpec", _spec(ctx).trefftz)


def _ledgers(ctx: SimContext) -> LedgersSpec:
    return cast("LedgersSpec", _spec(ctx).ledgers)


def _skip(ctx: SimContext, key: str, point: str, reason: str) -> None:
    name = _spec(ctx).name
    ctx.skipped[key if "#entry=" in key else f"{key}#entry={name}"] = reason
    warn(
        f"point={point} product=farfield entry={name}: {reason}",
        PyflightstreamWarning,
        stacklevel=3,
    )


def _symmetry(ctx: SimContext) -> tuple[bool, bool]:
    """Return (mirror, half loads) from the row's SYMMETRY and SYMMETRY_LOADS."""
    variables: Mapping[str, object] = getattr(ctx.matrix_row, "variables", None) or {}
    mirror = str(variables.get("SYMMETRY", "")).strip().upper() == "MIRROR"
    loads = str(variables.get("SYMMETRY_LOADS", "")).strip().lower()
    return mirror, mirror and loads in ("false", "0", "no", "disable")


def _selected(
    spec_families: str | Sequence[str], families: Sequence[str], aliases, is_blade
) -> list[str]:
    """Use the planner's selector grammar over the recorded family inventory."""
    from pyflightstream.cases.selection import select_families

    groups = select_families(spec_families, families, is_blade, aliases, strict=False)
    return list(dict.fromkeys(name for group in groups for name in (group or families)))


def _near_cl_on_vinf(point: PolarPoint) -> float:
    """Return the solver's CL (on VREF) restated on the free-stream dynamic pressure.

    The trace coefficients are taken on ``0.5 rho VINF^2``; the solver's CL on
    ``0.5 rho VREF^2``, so the two meet only after the factor ``(VREF / VINF)^2``.
    """
    loads = point.loads
    cl = _near_field(point)[0]
    speed = float(loads.freestream_velocity_m_s)
    v_ref = float(loads.reference_velocity_m_s or speed)
    if not (math.isfinite(cl) and math.isfinite(speed) and speed > 0.0 and math.isfinite(v_ref)):
        return cl
    return cl * (v_ref / speed) ** 2


def _near_field(point: PolarPoint) -> tuple[float, float, float]:
    """Return the solver's CL and its pressure and vorticity induced drags (FR-1054).

    The solver prints one induced drag: from the vorticity where the run
    selected boundaries for it (``SET_VORTICITY_DRAG_BOUNDARIES``), from the
    surface pressures otherwise; the other column is ``NA``. It is the first
    column of the printed drag split (:func:`~pyflightstream.results.loads.drag_pair`):
    ``CDi`` up to 26.124, ``CDp`` on 26.125, which takes the vorticity value
    when the run selects it and leaves ``CDv`` unchanged, as ``CDi`` does
    beside ``CDo`` (PFS-2081.98, RPT-171). A table printing neither split
    gives ``NA``.
    """
    total = point.loads.total
    cl = float(total.get("CL", _NA))
    try:
        induced, _profile = drag_pair(total)
    except PyflightstreamError:
        return cl, _NA, _NA
    cdi = float(total.get(induced, _NA))
    if point.vorticity_selection:
        return cl, _NA, cdi
    return cl, cdi, _NA


def _context(ctx: SimContext, point: PolarPoint) -> tuple[object, ...]:
    return tuple(context_row(ctx.condition(point), ctx.reference.as_lengths()))


def _status(ctx: SimContext, point: PolarPoint) -> str:
    """Return the point's solver termination status, as the sweep table writes it (FR-1061)."""
    status = getattr(ctx.record_of[point.name], "status", None)
    return str(getattr(status, "value", status) or "NA")


def _row(ctx: SimContext, point: PolarPoint, step: object, values: Mapping[str, object]):
    _cl, pressure, vorticity = _near_field(point)
    merged = {
        "CDI_NEAR_PRESSURE": pressure,
        "CDI_NEAR_VORTICITY": vorticity,
        "STATUS": _status(ctx, point),
        **values,
    }
    cells = (merged.get(column, _NA) for column in _TREFFTZ_CELLS)
    return (ctx.sim_id, _spec(ctx).name, step, *_context(ctx, point), *cells)


def _trace_rows(
    ctx: SimContext,
    point: PolarPoint,
    result: TraceResult,
    *,
    variant: str,
    names: Sequence[str],
    factor: float,
    extra: Mapping[str, float],
    blank: Sequence[str] = (),
) -> list[tuple[object, ...]]:
    """Return A's family rows and TOTAL, or B's whole-flow net row."""
    rho, speed, _alpha, _beta = _flow(point)
    q = 0.5 * rho * speed * speed
    sref, bref = float(ctx.reference.sref_m2), float(ctx.reference.bref_m)
    entries = []
    if len(names) > 1:
        for index, name in enumerate(names):
            count = int(np.count_nonzero(result.sheet == result.sheets[index]))
            entries.append(
                (
                    name,
                    result.sheet_lift[index],
                    result.sheet_side_force[index],
                    result.sheet_drag_share[index],
                    result.sheet_drag_isolated[index],
                    count,
                )
            )
    total = "TOTAL" if variant == "sections" else "net"
    entries.append((total, result.lift, result.side_force, result.induced_drag, _NA, len(result.y)))
    rows = []
    for name, lift, side, drag, alone, count in entries:
        c = trace_coefficients(
            lift * factor,
            side_force=side * factor,
            induced_drag=drag * factor,
            q=q,
            s_ref=sref,
            b_ref=bref,
        )
        values: dict[str, object] = {
            "FAMILY": name,
            "VARIANT": _VARIANT_NAMES[variant],
            **c,
            "CDI_T_ISOLATED": alone * factor / (q * sref) if math.isfinite(alone) else _NA,
            "N_TRACE": count,
            **extra,
        }
        values.update({column: _NA for column in blank})
        rows.append(_row(ctx, point, _NA, values))
    return rows


def _spanwise(
    ctx: SimContext,
    point: PolarPoint,
    *,
    variant: str,
    name: str,
    result: TraceResult,
    chords: np.ndarray | None,
) -> None:
    """Write a sheet's spanwise strips, qualifying whole-flow B files by entry."""
    rho, speed, _alpha, _beta = _flow(point)
    q = 0.5 * rho * speed * speed
    keep = result.original
    w = result.downwash[keep]
    gamma = result.gamma[keep]
    di = rho * gamma * w
    rows = []
    for index in range(int(keep.sum())):
        chord = float(chords[index]) if chords is not None else _NA
        rows.append(
            (
                ctx.sim_id,
                *_context(ctx, point),
                _VARIANT_NAMES[variant],
                name,
                float(result.y[keep][index]),
                float(result.z[keep][index]),
                float(result.dy[keep][index]),
                float(gamma[index]),
                float(w[index]),
                math.degrees(math.atan2(float(w[index]), speed)),
                float(di[index]),
                float(di[index]) / (q * chord) if chord and math.isfinite(chord) else _NA,
                _status(ctx, point),
            )
        )
    suffix = f"{name}_{_spec(ctx).name}" if variant == "wake" else name
    safe = re.sub(r"[^A-Za-z0-9_.+-]", "_", suffix)
    path = ctx.target(ctx.out / f"sections/{point.name}_trefftz_{safe}.csv")
    write_csv_table(path, SPANWISE_COLUMNS, rows)
    ctx.add(
        path, {"runs": list(ctx.sources[point.name]), "analysis": "trefftz", "variant": variant}
    )


def _sheet(result: TraceResult, index: int) -> TraceResult:
    """Return the strips of one sheet of a trace, as a trace of its own for the spanwise file."""
    pick = result.sheet == result.sheets[index]
    return replace(
        result,
        y=result.y[pick],
        z=result.z[pick],
        dy=result.dy[pick],
        dz=result.dz[pick],
        ds=result.ds[pick],
        gamma=result.gamma[pick],
        normalwash=result.normalwash[pick],
        sheet=result.sheet[pick],
        original=result.original[pick],
    )


def _a_blocks(
    ctx: SimContext, point: PolarPoint, key: str, sloads: Path | None = None
) -> dict[str, np.ndarray] | None:
    """Return the sectional-load rows of each family cut in XZ of a reference frame, or skip."""
    sloads = sloads or ctx.exports.get(point.name, (None, None, None))[0]
    if sloads is None:
        _skip(
            ctx,
            key,
            point.name,
            "the point exported no sectional loads; the plan of a new "
            "run adds the distribution and the export",
        )
        return None
    try:
        layout, _ = distributions_of(ctx.record_of[point.name], ctx.pproc)
        report = parse_sectional_loads(Path(sloads).read_text(encoding="utf-8"))
    except (PyflightstreamError, OSError) as error:
        _skip(ctx, key, point.name, f"the sectional loads cannot be read: {error}")
        return None
    blocks: dict[str, np.ndarray] = {}
    inventory = list(ctx.record_of[point.name].inventory or ())
    start = 0
    for block in layout:
        count = int(str(block["count"]))
        rows = report.values[start : start + count]
        start += count
        names = [str(name) for name in cast("list[object]", block.get("families") or [])]
        frame = str(block.get("frame") or "MRP").upper()
        # PFS-2081.100: the plan's rule, so an `all` block of one family is traced.
        name = traced_family(names, inventory)
        if block.get("plane") == "XZ" and frame in ("MRP", "REFERENCE") and name is not None:
            blocks.setdefault(name, rows[np.argsort(rows[:, 0], kind="stable")])
    return blocks


def _a_sheets(
    point: PolarPoint,
    blocks: Mapping[str, np.ndarray],
    chosen: Sequence[str],
    *,
    stations: int,
    mirror: bool,
) -> tuple[list[np.ndarray], ...]:
    """Return per family the trace points, the circulation, the sheet labels and the chords."""
    rho, speed, alpha, _beta = _flow(point)
    ys, zs, gammas, sheets, chords = [], [], [], [], []
    for index, name in enumerate(chosen):
        rows = blocks[name]
        lift = np.array(
            [
                wind_force_coefficients((fx, 0.0, fz), alpha, 0.0)[2]
                for fx, fz in zip(rows[:, 4], rows[:, 5], strict=True)
            ]
        )
        ys.append(rows[:, 0])
        zs.append(rows[:, 3])
        gammas.append(lift / (rho * speed))
        sheets.append(np.full(len(rows), index))
        chords.append(rows[:, 1])
        few = few_stations_warning(name, len(rows) if mirror else len(rows) // 2, stations)
        if few:
            warn(f"point={point.name} product=farfield: {few}", PyflightstreamWarning, stacklevel=2)
    return ys, zs, gammas, sheets, chords


def _variant_a(ctx: SimContext, point: PolarPoint, sloads: Path | None = None) -> list:
    """Trefftz A of one steady point (FR-451): rows, or a named skip."""
    spec = _spec(ctx)
    key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=sections"
    rho, speed, _alpha, beta = _flow(point)
    if abs(float(beta)) > 0.0:
        _skip(
            ctx,
            key,
            point.name,
            "variant A traces the span with the free stream in the "
            "reference XZ plane, and this point has sideslip; variants B and C serve it",
        )
        return []
    if not (math.isfinite(rho) and speed > 0.0):
        _skip(ctx, key, point.name, "the point states no density or free-stream speed")
        return []
    blocks = _a_blocks(ctx, point, key, sloads)
    if blocks is None:
        return []
    inventory = ctx.record_of[point.name].inventory or list(blocks)
    selected = _selected(spec.families or "all", inventory, ctx.aliases, ctx.pproc.is_blade)
    chosen = [name for name in selected if name in blocks]
    for name in (name for name in selected if name not in blocks):
        _skip(
            ctx,
            f"{key}#family={name}",
            point.name,
            f"the selected family {name} has no distribution cut in planes XZ of a "
            "reference-axes frame, so the trace leaves it out and its TOTAL row is of "
            "the other families alone",
        )
    if not chosen:
        _skip(
            ctx,
            key,
            point.name,
            "no distribution of the run cuts a selected family in planes "
            "XZ of a reference-axes frame; the plan of a new run adds one",
        )
        return []
    mirror, half = _symmetry(ctx)
    ys, zs, gammas, sheets, chords = _a_sheets(
        point, blocks, chosen, stations=_trefftz(ctx).stations, mirror=mirror
    )
    y = np.concatenate(ys)
    if mirror and not (np.all(y > 0.0) or np.all(y < 0.0)):
        _skip(
            ctx,
            key,
            point.name,
            "a half model's stations straddle the symmetry plane, so "
            "the export cannot say which half was meant",
        )
        return []
    try:
        result = trace_forces(
            y,
            z=np.concatenate(zs),
            gamma=np.concatenate(gammas),
            rho=rho,
            v_inf=speed,
            sheets=np.concatenate(sheets),
            mirror=mirror,
        )
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the trace cannot be formed: {error}")
        return []
    for index, name in enumerate(chosen if sloads is None else []):
        _spanwise(
            ctx,
            point,
            variant="sections",
            name=name,
            result=_sheet(result, index),
            chords=chords[index],
        )
    factor = 0.5 if half else 1.0
    _warn_traced_lift(ctx, point, result.lift * factor, chosen)
    return _trace_rows(
        ctx, point, result, variant="sections", names=chosen, factor=factor, extra={}
    )


def _warn_traced_lift(
    ctx: SimContext, point: PolarPoint, lift: float, families: Sequence[str]
) -> None:
    """Warn where the families A traced do not carry the solver's lift (FR-1021, PFS-2081.96).

    A trace over a subset of the lifting surfaces (a wing without its body)
    sheds the circulation of those surfaces alone and ends at their root with
    whatever their loading holds there, so its induced drag and span
    efficiency are not the configuration's. The row is written; the WARNING
    names the families, both lifts and their ratio.
    """
    rho, speed, _alpha, _beta = _flow(point)
    cl_traced = lift / (0.5 * rho * speed * speed * float(ctx.reference.sref_m2))
    cl_near = _near_cl_on_vinf(point)
    if not (math.isfinite(cl_traced) and math.isfinite(cl_near) and cl_near):
        return
    ratio = cl_traced / cl_near
    if abs(ratio - 1.0) > _TRACED_LIFT_TOLERANCE:
        warn(
            f"point={point.name} product=farfield: Trefftz A traces {', '.join(families)} with "
            f"a lift CL_T = {cl_traced:.4g}, {ratio:.3g} times the solver's CL {cl_near:.4g}; "
            "the traced families do not carry the configuration's lift, so their CDI_T and "
            "E_T are of those families alone, not of the configuration (FR-1021)",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _output(ctx: SimContext, point: PolarPoint, kind: str) -> Path | None:
    record = ctx.record_of[point.name]
    outputs = [str(name) for name in record.outputs or ()]
    names = [Path(name).name for name in outputs]
    chosen = classify_outputs(names, package_version=record.package_version).get(kind)
    sim_dir = ctx.workspace.sim_dir(ctx.sim_id)
    return next((sim_dir / name for name in outputs if Path(name).name == chosen), None)


def _per_m(ctx: SimContext, point: PolarPoint) -> float | None:
    record = ctx.record_of[point.name]
    return native_per_m(
        ctx.workspace.sim_dir(ctx.sim_id),
        [str(o) for o in record.outputs or ()],
        record.package_version,
    )


def _variant_b(
    ctx: SimContext,
    point: PolarPoint,
    wakes: Path | None,
    *,
    rotor: bool = False,
    spanwise: bool = True,
) -> list:
    """Trefftz B of one point (FR-452): rows, or a named skip.

    ``wakes`` is the wake export to read (the final one: :func:`_final_wakes`). On a
    rotor row (``rotor``) B traces only the lines that leave another family
    than the rotors' (P0470-FFR); the rotors' lines feed the wake loads.
    """
    spec = _trefftz(ctx)
    key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=wake"
    if wakes is None or not wakes.is_file():
        _skip(
            ctx,
            key,
            point.name,
            "the point wrote no wake export; the plan of a new run "
            "switches the wake on in the VTK export",
        )
        return []
    per_m = _per_m(ctx, point)
    if per_m is None:
        _skip(
            ctx,
            key,
            point.name,
            "the point saved no simulation whose length unit the "
            "package reads, so the wake coordinates cannot be put in metres",
        )
        return []
    try:
        wake = parse_wake_export(wakes.read_text(encoding="utf-8"))
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the wake export cannot be read: {error}")
        return []
    rho, speed, alpha, beta = _flow(point)
    if not (math.isfinite(rho) and speed > 0.0):
        _skip(ctx, key, point.name, "the point states no density or free-stream speed")
        return []
    turn = farfield_axes(alpha, beta)
    picked = _wing_lines(ctx, point, key, wake, per_m=per_m, turn=turn) if rotor else None
    if rotor and picked is None:
        return []
    lines, values = picked or ([(line / per_m) @ turn.T for line in wake.lines], wake.values)
    x_t = max((float(line[0, 0]) for line in lines), default=0.0)
    x_t += spec.distance_bref * ctx.reference.bref_m
    mirror, half = _symmetry(ctx)
    lines, shed_values = _wake_sheet(ctx, point, lines, values, mirror=mirror)
    trace = wake_crossings(lines, values=shed_values, x_t=x_t)
    if trace.problem is not None:
        # FR-1025, FR-1026: the point's B row is written NA, never dropped, and
        # the WARNING says why; a short wake states the length the run had.
        reach = min(float(line[-1, 0] - line[0, 0]) for line in lines) if lines else _NA
        length = (
            f"; the recorded wake is {reach:.4g} m long on its shortest line, and the plane "
            f"stands {spec.distance_bref * ctx.reference.bref_m:.4g} m behind the trailing edge"
            if trace.short
            else ""
        )
        _skip(ctx, key, point.name, f"no trace at x = {x_t:.4g} m: {trace.problem}{length}")
        unavailable = {"FAMILY": "net", "VARIANT": "B", "X_T_M": x_t}
        return [_row(ctx, point, _NA, unavailable)]
    try:
        raw = trace.forces(rho=rho, v_inf=speed, mirror=mirror)
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the trace cannot be formed: {error}")
        return []
    factor = 0.5 if half else 1.0
    k = calibration_scale(
        raw.lift * factor,
        cl_near=_wing_near_cl(ctx, point) if rotor else _near_field(point)[0],
        q=ff._q_ref(point, rho),
        s_ref=ctx.reference.sref_m2,
    )
    calibrated = math.isfinite(k)
    result = raw.scaled(k) if calibrated else raw
    if not calibrated:
        _skip(
            ctx,
            f"{key}#scale",
            point.name,
            "the point has no near-field CL to calibrate "
            "the wake values from, so E_T alone is written",
        )
    if spanwise:
        _spanwise(ctx, point, variant="wake", name="net", result=result, chords=None)
    return _trace_rows(
        ctx,
        point,
        result,
        variant="wake",
        names=["net"],
        factor=factor,
        extra={"X_T_M": x_t, "GAMMA_SCALE": k},
        blank=() if calibrated else ("CL_T", "CDI_T", "CY_T"),
    )


def _wake_sheet(
    ctx: SimContext,
    point: PolarPoint,
    lines: list[np.ndarray],
    values: np.ndarray,
    *,
    mirror: bool,
) -> tuple[list[np.ndarray], np.ndarray]:
    """Select one exported mirror half and omit zero-strength collapsed lines."""
    starts = np.array([line[0, 1] for line in lines])
    keep = np.ones(len(lines), dtype=bool)
    if mirror:
        # A mirrored model is taken to export both halves, including two coincident
        # root lines (no committed report measures this layout; a one-sided export
        # is also handled below). Select by upstream nodes, before roll-up moves
        # the crossings.
        keep &= starts < -1e-9 if np.any(starts < -1e-9) else starts > 1e-9
    collapsed = np.array([np.ptp(line[:, 0]) == 0.0 for line in lines], dtype=bool)
    omitted = collapsed & (values == 0.0)
    if np.any(keep & omitted):
        warn(
            f"point={point.name} product=farfield: {int(np.count_nonzero(keep & omitted))} "
            "zero-strength collapsed wake lines omitted; their shed circulation is missing "
            "from the export, so Trefftz B can underestimate lift before calibration",
            PyflightstreamWarning,
            stacklevel=3,
        )
    keep &= ~omitted
    return [line for line, use in zip(lines, keep, strict=True) if use], values[keep]


def _wing_lines(
    ctx: SimContext, point: PolarPoint, key: str, wake: Any, *, per_m: float, turn: np.ndarray
) -> tuple[list[np.ndarray], np.ndarray] | None:
    """Return the wake lines (wind axes) and values that leave no rotor, or skip (P0470-FFR)."""
    rotors = getattr(ctx.live, "rotors", None) or {}
    bladed = _rotor_line_mask(rotors, [line / per_m for line in wake.lines])
    if np.all(bladed):
        _skip(
            ctx,
            key,
            point.name,
            "every wake line of the point leaves a rotor's blades, so no wing sheet is "
            "traced; the rotor's lines give the wake loads (VARIANT W)",
        )
        return None
    lines = [(line / per_m) @ turn.T for line, own in zip(wake.lines, bladed, strict=True)]
    return [line for line, own in zip(lines, bladed, strict=True) if not own], wake.values[~bladed]


def _wing_near_cl(ctx: SimContext, point: PolarPoint) -> float:
    """Return the lift of the non-rotor families used to calibrate their wake trace."""
    surfaces = point.loads.surfaces
    rotors = getattr(ctx.live, "rotors", None) or {}
    members = [member for rotor in rotors.values() for member in rotor.members]
    owned = (
        set(
            select_group_members(
                members, list(surfaces), getattr(ctx, "aliases", None), strict=False
            )
        )
        if members
        else set()
    )
    lift = [float(row.get("CL", _NA)) for name, row in surfaces.items() if name not in owned]
    return sum(lift) if lift else _NA


def _final_wakes(ctx: SimContext, point: PolarPoint) -> Path | None:
    """Return the wake export beside the point's final surface VTK, or None."""
    vtk = _output(ctx, point, "vtk")
    return None if vtk is None else vtk.with_name(vtk.stem + "_wakes.vtk")


def _rotor_line_mask(rotors: Mapping[str, Any], lines: Sequence[np.ndarray]) -> np.ndarray:
    """Return which wake lines (metres, geometry axes) leave a rotor of the reference."""
    mask = np.zeros(len(lines), dtype=bool)
    for rotor in rotors.values():
        radius = float(rotor.diameter_m) / 2.0
        mask |= rotor_wake_lines(
            lines,
            hub=(float(rotor.x_m), float(rotor.y_m), float(rotor.z_m)),
            axis=rotor.axis_vector,
            radius=1.02 * radius,
            reach=_BLADE_REACH * radius,
        )
    return mask


def _variant_w(ctx: SimContext, point: PolarPoint, wakes: Path | None) -> list:
    """Return the wake loads of each rotor of one point (option 3, P0470-FFR), or skip."""
    key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=wake_loads"
    rotors = getattr(ctx.live, "rotors", None) or {}
    if wakes is None or not wakes.is_file():
        _skip(
            ctx,
            key,
            point.name,
            "the point wrote no wake export, so no rotor wake loads are formed; the plan of a "
            "new run switches the wake on in the VTK export",
        )
        return []
    per_m = _per_m(ctx, point)
    try:
        if per_m is None:
            raise PyflightstreamError(
                "the point saved no simulation whose length unit the package reads"
            )
        wake = parse_wake_export(wakes.read_text(encoding="utf-8"))
    except (PyflightstreamError, OSError) as error:
        _skip(ctx, key, point.name, f"the wake export cannot be read: {error}")
        return []
    rho, speed, alpha, beta = _flow(point)
    record = ctx.record_of[point.name]
    plan = getattr(record, "reductions", None)
    speeds = _recorded_speeds(plan, row_rotor_speeds(record, getattr(point, "loads_path", None)))
    flat = plan.get("rpm") if isinstance(plan, Mapping) else None
    if not speeds and len(rotors) == 1 and isinstance(flat, int | float):
        # A plan of one rotor states its speed at the row level.
        speeds = {str(next(iter(rotors))): float(flat)}
    lines = [line / per_m for line in wake.lines]
    wind = farfield_axes(alpha, beta)[0]
    loads = point.loads
    v_ref = float(loads.reference_velocity_m_s or loads.freestream_velocity_m_s)
    qs = 0.5 * rho * speed * speed * float(ctx.reference.sref_m2)
    # Hover retains dimensional loads; a zero free-stream pressure defines no counts.
    qs = qs if qs > 0.0 else _NA
    rows = []
    for alias, rotor in rotors.items():
        mask = _rotor_line_mask({alias: rotor}, lines)
        rpm = speeds.get(str(alias))
        if rpm is None or not np.any(mask):
            why = "states no speed" if rpm is None else "sheds no wake line the export holds"
            _skip(ctx, f"{key}#rotor={alias}", point.name, f"the rotor {alias} {why}")
            continue
        axis = np.asarray(rotor.axis_vector, dtype=np.float64)
        axis = axis / float(np.linalg.norm(axis))
        count = recorded_blade_count(record, str(alias), len(rotors)) or rotor.blade_count
        try:
            wake_loads = wake_rotor_loads(
                [line for line, own in zip(lines, mask, strict=True) if own],
                values=wake.values[mask],
                hub=(float(rotor.x_m), float(rotor.y_m), float(rotor.z_m)),
                axis=axis.tolist(),
                omega=2.0 * math.pi * float(rpm) / 60.0,
                v_axial=speed * float(wind @ axis),
                rho=rho,
                blades=int(count),
            )
        except PyflightstreamError as error:
            reason = f"the wake loads cannot be formed: {error}"
            _skip(ctx, f"{key}#rotor={alias}", point.name, reason)
            continue
        near = rotor_shaft_loads(
            loads.surfaces,
            rotor=rotor,
            reference=ctx.reference,
            density_kg_m3=rho,
            speed_m_s=v_ref,
            alpha_deg=alpha,
            beta_deg=beta,
        )
        # A rotor whose families the loads export does not hold has no near field: NA, not 0.
        t_near = near.thrust_n if near.families_used else _NA
        q_near = near.torque_nm if near.families_used else _NA
        values = {
            "FAMILY": str(alias),
            "VARIANT": "W",
            "N_TRACE": int(np.count_nonzero(mask)),
            # The raw scale: the exported values are read as the circulation itself.
            "GAMMA_SCALE": 1.0,
            "T_WAKE_N": wake_loads.thrust,
            "Q_WAKE_NM": wake_loads.torque,
            "T_NEAR_N": t_near,
            "Q_NEAR_NM": q_near,
            "DT_WAKE_COUNTS": 1e4 * (wake_loads.thrust - t_near) / qs,
            "DQ_WAKE_COUNTS": (
                1e4 * (wake_loads.torque - q_near) / (qs * float(ctx.reference.bref_m))
            ),
        }
        rows.append(_row(ctx, point, _NA, values))
    return rows


def _wake_rotor_products(
    ctx: SimContext, point: PolarPoint, tables: ff._Tables, run_type: str
) -> None:
    """B on the non-rotor lines and the rotors' wake loads: final, and the window average."""
    final = _final_wakes(ctx, point)
    runs = ctx.sources[point.name]
    rows = _variant_b(ctx, point, final, rotor=True) + _variant_w(ctx, point, final)
    if run_type not in UNSTEADY_RUN_TYPES:
        tables.extend("trefftz", point.name, ff._named(ctx, [final]), rows, runs=runs)
        return
    record = ctx.record_of[point.name]
    last_step = ff._last_step(record)
    instant = [row[:2] + (last_step,) + row[3:] for row in rows]
    tables.extend("trefftz_instant", point.name, ff._named(ctx, [final]), instant, runs=runs)
    key = f"farfield/trefftz_average#point={point.name}#entry={_spec(ctx).name}"
    if _spec(ctx).export_type != "avg_window":
        reason = f"export_type = {_spec(ctx).export_type!r} reads the last step only"
        _skip(ctx, key, point.name, reason + "; no average is written")
        return
    window, source_name = _farfield_window(
        ctx,
        point,
        int(last_step) if isinstance(last_step, int | float) and math.isfinite(last_step) else 0,
    )
    vtk = _output(ctx, point, "vtk")
    root = ctx.workspace.sim_dir(ctx.sim_id)
    files = (
        {}
        if vtk is None
        else stamped_exports(
            root, vtk.stem, *(root / Path(output).parent for output in record.outputs)
        ).get(("", "vtk"), {})
    )
    wakes = {step: path.with_name(path.stem + "_wakes.vtk") for step, path in files.items()}
    steps = range(int(window[0]), int(window[1]) + 1) if window else range(0)
    if not steps or any(step not in wakes or not wakes[step].is_file() for step in steps):
        _skip(ctx, key, point.name, "the wake average needs a wake export at every window step")
        return
    samples = [
        _variant_b(ctx, point, wakes[step], rotor=True, spanwise=False)
        + _variant_w(ctx, point, wakes[step])
        for step in steps
    ]
    first = 3 + len(CONTEXT_COLUMNS)
    identities = [[row[first : first + 2] for row in sample] for sample in samples]
    if not all(samples) or any(identity != identities[0] for identity in identities):
        _skip(ctx, key, point.name, "the per-step wake rows differ between window steps")
        return
    tables.extend(
        "trefftz_average",
        point.name,
        ff._named(ctx, [wakes[step] for step in steps]),
        ff._average_entry_rows(samples, 2 + len(CONTEXT_COLUMNS) + 2),
        runs=runs,
        window=window,
        samples=len(samples),
        source=source_name,
    )


def _instants(ctx: SimContext, point: PolarPoint, unsteady: bool) -> tuple[list[ff._Instant], str]:
    """Read only the far field's conventional probe exports, including stamped steps."""
    probes = _output(ctx, point, "farfield_probes")
    try:
        if probes is None:
            return [], "the point exported no far-field probe values"
        per_m = _per_m(ctx, point)
        if per_m != 1.0:
            return (
                [],
                f"conventional probe velocity units are unmeasured at {per_m!r} "
                "simulation length units per metre",
            )
        final = ff._Instant(
            steady_samples(probes.read_text(encoding="utf-8")),
            ff._last_step(ctx.record_of[point.name]) if unsteady else _NA,
        )
        files = (
            _probe_exports(ctx, point)
            if unsteady and _spec(ctx).export_type == "avg_window"
            else {}
        )
        window, _ = _farfield_window(ctx, point, int(ff._step(final))) if files else (None, "")
        instants = []
        for step, path in sorted(files.items()):
            if window is None or not window[0] <= step <= window[1]:
                continue
            try:
                instants.append(ff._Instant(steady_samples(path.read_text(encoding="utf-8")), step))
            except (PyflightstreamError, OSError) as error:
                _skip(
                    ctx,
                    f"{FARFIELD_DIR}/average#point={point.name}#step={step}",
                    point.name,
                    f"far-field snapshot cannot be read: {error}; restore or collect "
                    "the complete snapshot, or rerun the point",
                )
        return [*instants, final], ""
    except (PyflightstreamError, OSError) as error:
        return [], f"the probe values cannot be read: {error}"


def _probe_exports(ctx: SimContext, point: PolarPoint) -> dict[int, Path]:
    """Find stamped exports beside the run's recorded outputs."""
    root = ctx.workspace.sim_dir(ctx.sim_id)
    record = ctx.record_of[point.name]
    return stamped_exports(
        root, point.name, *(root / Path(name).parent for name in record.outputs)
    ).get(("_farfield_survey", "txt"), {})


def _locate(ctx: SimContext, point: PolarPoint, spec, rotor: bool) -> _Probe:
    per_m = _per_m(ctx, point)
    if per_m is None:
        raise PyflightstreamError(
            "the point saved no simulation whose length unit the package reads, so its probe "
            "positions cannot be matched in metres"
        )
    layout = _layout(ctx, point, spec, rotor)
    hub = _hub(ctx, point, spec, layout)
    record = ctx.record_of[point.name]
    plane = spec.trefftz is not None and "plane" in spec.trefftz.variant
    if hub is None and plane and str(record.recipe or "") == "qsteady_rotor":
        # A quasi-steady row's C plane is read in the turning frame (FR-1037).
        hub = _plane_hub(ctx, point)
        _note_one_clocking(ctx, point)
    return _Probe(per_m=per_m, layout=layout, hub=hub, rotor=rotor)


def _plane_hub(ctx: SimContext, point: PolarPoint) -> tuple[float, np.ndarray, np.ndarray]:
    """Return the turning frame of a quasi-steady row's C plane: its one rotor's.

    The speed is read as D reads it (:func:`pyflightstream.post._reduction_stage._hub`):
    the record's plan, else the row's own signed speed in the quasi-steady record.
    A quasi-steady row holds an isolated rotor, so the plane turns about that one;
    its axis and hub are the reference's rotor block, else the quasi-steady record's.
    """
    record = ctx.record_of[point.name]
    loads = getattr(point, "loads_path", None)
    speeds = _recorded_speeds(record.reductions, row_rotor_speeds(record, loads))
    if len(speeds) != 1:
        raise PyflightstreamError(
            "the quasi-steady row states no single rotor speed in the point's record nor in "
            "its quasi-steady record, so its plane cannot be converted to the hub frame"
        )
    ((alias, rpm),) = speeds.items()
    rotor: Any = (getattr(ctx.live, "rotors", None) or {}).get(alias)
    if rotor is not None:
        axis = rotor.axis_vector
        origin = np.asarray([rotor.x_m, rotor.y_m, rotor.z_m], dtype=np.float64)
    else:
        try:
            quasi = read_qsteady_record(cast("Path", loads))
        except (QsteadyRecordError, TypeError) as error:
            raise PyflightstreamError(
                f"the reference names no rotor {alias!r} and its quasi-steady record cannot "
                f"be read ({error}), so the hub its plane turns about is unknown"
            ) from error
        axis, origin = quasi.axis_vector, np.asarray(quasi.hub_m, dtype=np.float64)
    shaft = _AXES[axis.strip().upper()] if isinstance(axis, str) else np.asarray(axis, dtype=float)
    return 2.0 * math.pi * float(rpm) / 60.0, shaft, origin


def _instant_values(
    ctx: SimContext,
    point: PolarPoint,
    instant: ff._Instant,
    probe: _Probe,
    analyses: Sequence[str],
    *,
    final: bool = True,
    near: tuple[float, float] = (_NA, _NA),
    loading: DiskLoading | None = None,
) -> dict[str, Any]:
    """Return the C values and the ledger rows of one instant, keyed by analysis.

    The final row uses the final loads. Window snapshots receive their own
    near-field axial force in N from the same plots history as the unsteady polar.
    """
    rho, speed, alpha, beta = _flow(point)
    q_ref = ff._q_ref(point, rho)
    layout = probe.layout
    lattice_at, plane_at, why = far_samples(instant.samples, layout, per_m=probe.per_m, final=final)
    # C reads a plane on every applicable row; D and balances read a lattice.
    wants_plane = "trefftz:plane" in analyses
    wants_lattice = "ledgers" in analyses or "trefftz:power" in analyses
    no_plane, no_lattice = wants_plane and plane_at is None, wants_lattice and lattice_at is None
    if no_plane or no_lattice:
        reason = why or "the run laid no far-field probes these analyses read"
        # Each entry keeps the named missing set, including when it is the entry's
        # only set. Independent entries still write their available analyses.
        left = "the Trefftz C plane" if no_plane else "the lattice analyses"
        _skip(
            ctx,
            f"{FARFIELD_DIR}/probes#point={point.name}#absent={'plane' if no_plane else 'lattice'}",
            point.name,
            f"{left} cannot be read: {reason}",
        )
        if not final and not ((wants_plane and not no_plane) or (wants_lattice and not no_lattice)):
            raise PyflightstreamError(reason)
    out: dict[str, Any] = {}
    if plane_at is not None and "trefftz:plane" in analyses:
        out["plane"] = plane_values(
            instant.samples,
            plane_at,
            flow=(rho, speed, alpha, beta),
            grid=cast("tuple[float, float, float]", layout.plane_grid),
            per_m=probe.per_m,
            q_ref=q_ref,
            # A quasi-steady row's plane is read in the turning frame (FR-1037).
            hub=None if layout.lattice is not None else probe.hub,
        )
    if lattice_at is None or layout.lattice is None:
        return out
    lattice, axis = layout.lattice, layout.axis
    hub = None
    if probe.hub is not None:
        hub = (probe.hub[0], probe.hub[1], probe.hub[2])
    fields = lattice_samples(instant.samples, lattice_at, lattice, axis, q=q_ref, hub=hub)
    if "trefftz:power" in analyses:
        station = _trefftz(ctx).station
        station = float(lattice.stations[-1]) if station is None else float(station)
        out["rotor"] = rotor_values(fields, rho=rho, speed=speed, station=station, loading=loading)
    if "ledgers" in analyses:
        near = ff._near_force(point, axis, ctx.reference.sref_m2) if final else near
        out["ledgers"] = ledger_values(
            fields,
            _ledgers(ctx),
            rho=rho,
            speed=speed,
            near=(near[0], ctx.reference.sref_m2),
            viscous=near[1],
            rotor=rotor_g4(_ledgers(ctx), ctx.record_of[point.name].recipe),
            excluded_orders=symmetry_excluded_orders(
                _ledgers(ctx), ctx.record_of[point.name], getattr(ctx.live, "rotors", None) or {}
            ),
            loading=loading,
        )
    return out


def _c_row(ctx: SimContext, point: PolarPoint, values: Mapping[str, Any], step: object):
    rho, speed, _alpha, _beta = _flow(point)
    qs = 0.5 * rho * speed * speed * float(ctx.reference.sref_m2)
    if "plane" in values:
        plane = values["plane"]
        cdi = plane["D"] / qs
        cl = _near_cl_on_vinf(point)
        aspect = float(ctx.reference.bref_m) ** 2 / float(ctx.reference.sref_m2)
        e = cl * cl / (math.pi * aspect * cdi) if math.isfinite(cdi) and cdi else _NA
        cells = {
            "FAMILY": "net",
            "VARIANT": "C",
            "CL_T": plane["L"] / qs,
            "CDI_T": cdi,
            "E_T": e,
            "AR": aspect,
            "N_TRACE": plane["N"],
            "X_T_M": plane["X_T_M"],
            "COVERAGE": plane["COVERAGE"],
            "CDI_T_QERR": plane["D_QERR"] / qs,
            "CDI_T_VORT": plane["D_VORT"] / qs,
            "BERNOULLI_RESIDUAL": plane["RESIDUAL"] / qs,
        }
        return _row(ctx, point, step, cells)
    rotor = values["rotor"]
    cells = {"FAMILY": "net", "VARIANT": "D", **rotor}
    return _row(ctx, point, step, cells)


def _ledger_rows(ctx: SimContext, point: PolarPoint, values: Mapping[str, Any], step: object):
    name = _ledgers(ctx).rotor or _ledgers(ctx).frame
    context = _context(ctx, point)
    rows = []
    for station in values["ledgers"]:
        cells = {"LATTICE": name, "STATUS": _status(ctx, point), **station}
        rows.append(
            (
                ctx.sim_id,
                _spec(ctx).name,
                step,
                *context,
                *(cells.get(c, _NA) for c in _LEDGER_CELLS),
            )
        )
    return rows


def _last_and_window(
    ctx: SimContext, point: PolarPoint, instants: list[ff._Instant], windowed: bool
):
    """Return the last instant and the window's instants (none when it is partly covered)."""
    if windowed:
        last = instants[-1]
        window, _ = _farfield_window(ctx, point, int(ff._step(last)))
        chosen = [i for i in instants[:-1] if window and window[0] <= ff._step(i) <= window[1]]
        # The average is of the whole window or it is not written: a window
        # the recorded steps only partly cover would average fewer steps.
        if window and {ff._step(i) for i in chosen} != set(
            range(int(window[0]), int(window[1]) + 1)
        ):
            chosen = []
        return last, chosen
    return instants[0], []


def _skip_rotor_g4(
    ctx: SimContext, point: PolarPoint, analyses: Sequence[str], loading: object = None
) -> None:
    """Name the rotor-pressure limitation without dropping any measured ledger flux."""
    if (
        "ledgers" in analyses
        and "axial" in _ledgers(ctx).balances
        and rotor_g4(_ledgers(ctx), ctx.record_of[point.name].recipe)
        and not isinstance(loading, DiskLoading)
    ):
        why = f" ({loading})" if isinstance(loading, str) else ""
        _skip(
            ctx,
            f"{FARFIELD_DIR}/ledgers#point={point.name}#SPURIOUS_COUNTS#F_NEAR_N",
            point.name,
            "G4 (SPURIOUS_COUNTS) and F_NEAR_N are NA on rotor rows: the probe pressure "
            "is the free-stream Bernoulli pressure and carries no disk total-pressure jump, "
            "so the lattice axial balance cannot balance rotor thrust, and the jump is "
            f"reconstructed only from the blade sectional loads{why}",
        )


def _blade_rows(
    ctx: SimContext, point: PolarPoint, path: Path, alias: str | None
) -> list[tuple[np.ndarray, str]]:
    """Return the rows and plane of each blade distribution in a blade or rotor frame."""
    record = ctx.record_of[point.name]
    layout, _ = distributions_of(record, ctx.pproc)
    report = parse_sectional_loads(Path(path).read_text(encoding="utf-8"))
    frame = re.compile(rf"{re.escape(alias)}_RMRP\d*" if alias else r".+_RMRP\d*")
    out, start = [], 0
    for block in layout:
        count = int(str(block["count"]))
        rows = report.values[start : start + count]
        start += count
        names = [str(name) for name in cast("list[object]", block.get("families") or [])]
        if (
            len(names) == 1
            and ctx.pproc.is_blade(names[0])
            and frame.fullmatch(str(block.get("frame") or ""))
        ):
            out.append((rows, str(block.get("plane") or "").upper()))
    return out


def _disk_loading(
    ctx: SimContext, point: PolarPoint, probe: _Probe, *, window: bool = False
) -> DiskLoading | str | None:
    """Return the rotor's disk loading from its blade sectional loads (P0470-FFR).

    None on a row without a rotor; a reason where the loads are missing. On an
    unsteady window product the per-step exports are averaged when they cover
    the window; otherwise the final export is read. An instant always reads
    the final export.
    """
    record = ctx.record_of[point.name]
    spec = _ledgers(ctx)
    if not rotor_g4(spec, record.recipe) or probe.layout.lattice is None:
        return None
    alias = spec.rotor if spec is not None else None
    paths = _blade_load_paths(ctx, point, window=window)
    if not paths:
        return "the point exported no blade sectional loads"
    try:
        samples = [_blade_rows(ctx, point, path, alias) for path in paths]
    except (PyflightstreamError, OSError) as error:
        return f"the blade sectional loads cannot be read: {error}"
    if not samples[0] or any(len(sample) != len(samples[0]) for sample in samples):
        return "no blade distribution in a blade or rotor frame was exported at every step"
    blocks = [
        (np.mean([sample[k][0] for sample in samples], axis=0), samples[0][k][1])
        for k in range(len(samples[0]))
    ]
    rotor: Any = (getattr(ctx.live, "rotors", None) or {}).get(alias)
    count = recorded_blade_count(
        record, str(alias or ""), len(getattr(ctx.live, "rotors", {}) or {}) or 1
    )
    if count is None and rotor is not None:
        count = len(getattr(rotor, "families_blades", ()) or ())
    return disk_loading(
        blocks,
        shaft=_shaft_letter(probe.layout.axis, rotor),
        blades=int(count or len(blocks)),
        tip_radius_m=float(probe.layout.lattice.tip_radius),
    )


def _shaft_letter(axis: object, rotor: Any) -> str:
    """Return the letter the shaft keeps in the blade frames."""
    if isinstance(axis, str):
        return axis.strip().upper()[-1]
    if rotor is not None and getattr(rotor, "shaft", None):
        return str(rotor.shaft).strip().upper()[-1]
    return "XYZ"[int(np.argmax(np.abs(np.asarray(axis, dtype=float))))]


def _blade_load_paths(ctx: SimContext, point: PolarPoint, *, window: bool = False) -> list[Path]:
    """Return the sectional-load exports to average: the window's steps, else the final one."""
    record = ctx.record_of[point.name]
    final = ctx.exports.get(point.name, (None, None, None))[0]
    paths: list[Path] = [] if final is None else [Path(final)]
    if not window or str(record.recipe or "steady") not in UNSTEADY_RUN_TYPES:
        return paths
    last = ff._last_step(record)
    try:
        span, _ = _farfield_window(ctx, point, int(last) if isinstance(last, int | float) else 0)
    except PyflightstreamError:
        return paths
    root = ctx.workspace.sim_dir(ctx.sim_id)
    stamped = stamped_exports(
        root, point.name, *(root / Path(name).parent for name in record.outputs)
    ).get(("_sloads", "txt"), {})
    steps = range(int(span[0]), int(span[1]) + 1) if span else range(0)
    if steps and all(step in stamped for step in steps):
        return [stamped[step] for step in steps]
    return paths


def _probe_window(
    ctx: SimContext,
    point: PolarPoint,
    probe: _Probe,
    analyses: Sequence[str],
    chosen: list[ff._Instant],
) -> list[tuple[ff._Instant, dict[str, Any]]]:
    """Reduce a complete probe window with its window-averaged blade loads."""
    if not chosen:
        return []
    found = _disk_loading(ctx, point, probe, window=True)
    loading = found if isinstance(found, DiskLoading) else None
    near = (
        ff._window_near_forces(ctx, point, chosen, probe.layout.axis)
        if "ledgers" in analyses
        else {}
    )
    return [
        (
            instant,
            _instant_values(
                ctx,
                point,
                instant,
                probe,
                analyses,
                final=False,
                near=near.get(ff._step(instant), (_NA, _NA)),
                loading=loading,
            ),
        )
        for instant in chosen
    ]


def _probe_point(
    ctx: SimContext,
    point: PolarPoint,
    analyses: Sequence[str],
    tables: ff._Tables,
    *,
    rotor: bool | None = None,
):
    """C and the ledgers of one point: steady, or instant and average (FR-484, FR-1053)."""
    spec = _spec(ctx)
    record = ctx.record_of[point.name]
    run_type = str(record.recipe or "steady")
    unsteady = run_type in UNSTEADY_RUN_TYPES
    key = f"{FARFIELD_DIR}/probes#point={point.name}"
    if rotor is None:
        rotor = run_type in ROTOR_RUN_TYPES or (run_type == "steady" and _spins(ctx, record))
    # Each entry chooses its window independently of declared probes.
    normal = unsteady and spec.export_type != "avg_window"
    try:
        probe = _locate(ctx, point, spec, rotor)
        found = _disk_loading(ctx, point, probe)
        loading = found if isinstance(found, DiskLoading) else None
        instants, why = _instants(ctx, point, unsteady)
        if why:
            raise PyflightstreamError(why)
        last, chosen = _last_and_window(ctx, point, instants, unsteady and not normal)
        sets = [(last, _instant_values(ctx, point, last, probe, analyses, loading=loading))]
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the far-field probes cannot be read: {error}")
        return
    _skip_rotor_g4(ctx, point, analyses, found)
    try:
        averaged = _probe_window(ctx, point, probe, analyses, chosen)
    except PyflightstreamError as error:
        averaged = []
        _skip(
            ctx,
            f"{key}#average",
            point.name,
            f"the far-field window cannot be read: {error}; restore or collect "
            "complete window snapshots, or rerun the point",
        )
    if "plane" in sets[0][1] or "rotor" in sets[0][1]:
        _warn_compressible(ctx, point)
    if "plane" in sets[0][1]:
        _flag_a_plane_short_of_the_lift(ctx, point, sets[0][1]["plane"])
    runs = ctx.sources[point.name]
    taken = ff._named(
        ctx,
        [
            _output(ctx, point, "farfield_probes"),
            ctx.plots_tables.get(point.name) if averaged and "ledgers" in analyses else None,
            *(_probe_exports(ctx, point).values() if unsteady and not normal else []),
        ],
    )
    for suffix, group in _suffixes(unsteady, sets, averaged, ctx, point, normal=normal):
        c_rows = [
            _c_row(ctx, point, values, inst.step)
            for inst, values in group
            if "plane" in values or "rotor" in values
        ]
        l_rows = [
            _ledger_rows(ctx, point, values, inst.step)
            for inst, values in group
            if "ledgers" in values
        ]
        if suffix.endswith("average"):
            c_rows = ff._average_entry_rows([[row] for row in c_rows], 2 + len(CONTEXT_COLUMNS) + 2)
            l_rows = (
                [ff._average_entry_rows(l_rows, 2 + len(CONTEXT_COLUMNS) + 1)] if l_rows else []
            )
        reduced: dict[str, Any] = {}
        if suffix.endswith("average"):
            window, source = _farfield_window(ctx, point, int(ff._step(last)))
            reduced = {"window": window, "samples": len(averaged), "source": source}
        tables.extend(f"trefftz{suffix}", point.name, taken, c_rows, runs=runs, **reduced)
        tables.extend(
            f"ledgers{suffix}",
            point.name,
            taken,
            [r for rows in l_rows for r in rows],
            runs=runs,
            **reduced,
        )


def _note_one_clocking(ctx: SimContext, point: PolarPoint) -> None:
    """Name a wheel's C row as clocking 0's where the wheel was solved at several clockings.

    The plane is exported with the point's full export set, at clocking 0 alone,
    so the clocking average is not formed; the row is written and the limitation
    named, never one clocking presented as the average.
    """
    try:
        quasi = read_qsteady_record(cast("Path", getattr(point, "loads_path", None)))
    except (QsteadyRecordError, TypeError):
        return
    if len(quasi.positions) > 1:
        _skip(
            ctx,
            f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=plane#clockings",
            point.name,
            f"the wheel was solved at {len(quasi.positions)} clockings and its Trefftz C "
            "plane is exported at clocking 0 alone, so the C row is clocking 0's and "
            "no clocking average is written",
        )


def _flag_a_plane_short_of_the_lift(
    ctx: SimContext, point: PolarPoint, plane: Mapping[str, float]
) -> None:
    """Warn where the C plane's own lift is not the solver's CL (FR-1038, PFS-2081.95).

    The plane's lift is the Kutta-Joukowski lift of the vorticity it holds,
    which roll-up does not change; a plane holding the wake the loads shed
    carries the solver's lift. Where it departs by more than
    :data:`_PLANE_LIFT_TOLERANCE`, the probe field does not hold that
    circulation (RPT-171) and the row's crossflow energy is not the loads'
    induced drag: the row is written, and flagged here.
    """
    rho, speed, _alpha, _beta = _flow(point)
    qs = 0.5 * rho * speed * speed * float(ctx.reference.sref_m2)
    cl_plane, cl_near = plane["L"] / qs, _near_cl_on_vinf(point)
    if not (math.isfinite(cl_plane) and math.isfinite(cl_near)):
        return
    difference = abs(cl_plane - cl_near)
    tolerance = 1e-3 if abs(cl_near) < 1e-3 else _PLANE_LIFT_TOLERANCE * abs(cl_near)
    comparison = (
        f"absolute difference {difference:.4g} from"
        if abs(cl_near) < 1e-3
        else f"{cl_plane / cl_near:.3g} times"
    )
    if difference > tolerance:
        warn(
            f"point={point.name} product=farfield: the Trefftz C plane carries a lift of its own "
            f"vorticity CL_T = {cl_plane:.4g}, {comparison} the solver's CL {cl_near:.4g}; "
            "the probe field does not hold the circulation the loads shed, so its crossflow "
            "energy is not their induced drag (FR-1038, RPT-171)",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_compressible(ctx: SimContext, point: PolarPoint) -> None:
    """Warn once per point that a C row above Mach 0.3 uses incompressible relations (FR-1036)."""
    mach = ctx.condition(point).get("MACH")
    if isinstance(mach, int | float) and float(mach) > _INCOMPRESSIBLE_MACH:
        warn(
            f"point={point.name} product=farfield: the point flies at Mach {float(mach):.4g}, "
            f"above {_INCOMPRESSIBLE_MACH}; its Trefftz C row is written with the "
            "incompressible relations of the definitions page (FR-1036)",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _suffixes(
    unsteady: bool,
    sets: list,
    averaged: list,
    ctx: SimContext,
    point: PolarPoint,
    *,
    normal: bool = False,
):
    if not unsteady:
        return [("", sets)]
    out = [("_instant", sets)]
    if averaged:
        out.append(("_average", averaged))
    else:
        reason = (
            f"export_type = {_spec(ctx).export_type!r} reads the last step only"
            if normal
            else "the per-step far-field probes do not cover the averaging window"
        )
        _skip(
            ctx,
            f"{FARFIELD_DIR}/average#point={point.name}",
            point.name,
            reason + "; no average is written",
        )
    return out


def _analyses(spec, run_type: str, rotor: bool) -> tuple[list[str], dict[str, str]]:
    selected = []
    if spec.trefftz is not None:
        selected += [f"trefftz:{variant}" for variant in spec.trefftz.variant]
    if spec.balances:
        selected.append("ledgers")
    reasons = {a: applies(a, run_type, rotor=rotor) for a in selected}
    return [a for a in selected if not reasons[a]], {a: r for a, r in reasons.items() if r}


def farfield_products(ctx: SimContext) -> None:
    """Write far-field tables of one simulation (FR-456), or nothing without ``[[farfields]]``.

    Parameters
    ----------
    ctx : SimContext
        Product context carrying the resolved case, exports and output destinations.
    """
    if not ctx.pproc.farfields:
        return
    tables = ff._Tables()
    for entry in ctx.pproc.farfields:
        selected = (
            ctx
            if len(ctx.pproc.farfields) == 1
            else replace(ctx, pproc=ctx.pproc.model_copy(update={"farfields": [entry]}))
        )
        _entry_products(selected, tables)
    _write(ctx, tables)
    ctx.farfield_super.update(ff._super_cells(tables.super_rows(), _TREFFTZ_CELLS))


def _entry_products(ctx: SimContext, tables: ff._Tables) -> None:
    spec = _spec(ctx)
    for point in ctx.points:
        record = ctx.record_of[point.name]
        run_type = str(record.recipe or "steady")
        rotor = run_type in ROTOR_RUN_TYPES or (run_type == "steady" and _spins(ctx, record))
        analyses, refused = _analyses(spec, run_type, rotor)
        for analysis, reason in refused.items():
            _skip(
                ctx,
                f"{FARFIELD_DIR}/{analysis}#point={point.name}",
                point.name,
                f"{analysis} does not apply: {reason}",
            )
        runs = ctx.sources[point.name]
        steady_rows = []
        read: list[Path | None] = []
        if "trefftz:sections" in analyses:
            _sections_products(ctx, point, tables, run_type)
        if "trefftz:wake" in analyses and rotor:
            _wake_rotor_products(ctx, point, tables, run_type)
        elif "trefftz:wake" in analyses:
            steady_rows += _variant_b(ctx, point, _final_wakes(ctx, point))
            vtk = _output(ctx, point, "vtk")
            read.append(None if vtk is None else vtk.with_name(vtk.stem + "_wakes.vtk"))
        tables.extend("trefftz", point.name, ff._named(ctx, read), steady_rows, runs=runs)
        if any(a in analyses for a in ("trefftz:plane", "trefftz:power", "ledgers")):
            _probe_point(ctx, point, analyses, tables, rotor=rotor)


def _sections_products(
    ctx: SimContext, point: PolarPoint, tables: ff._Tables, run_type: str
) -> None:
    """Trace the final sections and each stamped export inside the averaging window."""
    source = ctx.exports.get(point.name, (None, None, None))[0]
    runs = ctx.sources[point.name]
    rows = _variant_a(ctx, point)
    if run_type not in UNSTEADY_RUN_TYPES:
        tables.extend("trefftz", point.name, ff._named(ctx, [source]), rows, runs=runs)
        return
    key = f"farfield/trefftz_average#point={point.name}#entry={_spec(ctx).name}"
    record = ctx.record_of[point.name]
    instant = [row[:2] + (ff._last_step(record),) + row[3:] for row in rows]
    tables.extend("trefftz_instant", point.name, ff._named(ctx, [source]), instant, runs=runs)
    if _spec(ctx).export_type != "avg_window":
        reason = f"export_type = {_spec(ctx).export_type!r} reads the last step only"
        _skip(ctx, key, point.name, reason + "; no average is written")
        return
    last_step = ff._last_step(record)
    window, source_name = _farfield_window(
        ctx,
        point,
        int(last_step) if isinstance(last_step, int | float) and math.isfinite(last_step) else 0,
    )
    root = ctx.workspace.sim_dir(ctx.sim_id)
    files = stamped_exports(
        root, point.name, *(root / Path(output).parent for output in record.outputs)
    ).get(("_sloads", "txt"), {})
    steps = range(int(window[0]), int(window[1]) + 1) if window else range(0)
    if not steps or any(step not in files for step in steps):
        reason = "Trefftz A average needs per-step sectional exports covering its window"
        _skip(ctx, key, point.name, reason)
        return
    samples = [_variant_a(ctx, point, files[step]) for step in steps]
    if not all(samples) or any(len(sample) != len(samples[0]) for sample in samples):
        reason = "per-step sectional traces do not cover the same families at every step"
        _skip(ctx, key, point.name, reason)
        return
    tables.extend(
        "trefftz_average",
        point.name,
        ff._named(ctx, [files[step] for step in steps]),
        ff._average_entry_rows(samples, 2 + len(CONTEXT_COLUMNS) + 2),
        runs=runs,
        window=window,
        samples=len(samples),
        source=source_name,
    )


def _spins(ctx: SimContext, record: object) -> bool:
    """Whether a steady row turns a rotor: an ``RPM`` on its point, its row or a motion.

    Names only: a zero or empty ``RPM`` still counts, since the row states a rotor speed.
    """
    stated = dict(getattr(ctx.matrix_row, "variables", None) or {})
    stated.update(getattr(record, "point", None) or {})
    return any(str(name).upper() in ("RPM", "MOTIONS") for name in stated)


def _held_columns(
    cells: Sequence[str], optional: Sequence[str], rows: Sequence[tuple[object, ...]]
) -> tuple[tuple[str, ...], list[tuple[object, ...]]]:
    """Drop the optional rotor columns no row holds a finite value in (P0470-FFR).

    A table of rows without a rotor keeps exactly the columns it had.
    """
    first = 3 + len(CONTEXT_COLUMNS)
    drop = {
        first + cells.index(name)
        for name in optional
        if not any(
            isinstance(row[first + cells.index(name)], int | float)
            and math.isfinite(float(cast("float", row[first + cells.index(name)])))
            for row in rows
        )
    }
    kept = tuple(name for index, name in enumerate(cells) if first + index not in drop)
    return kept, [tuple(c for i, c in enumerate(row) if i not in drop) for row in rows]


def _write(ctx: SimContext, tables: ff._Tables) -> None:
    variants = list(dict.fromkeys(entry.variant for entry in ctx.pproc.farfields))
    for suffix, rows in tables.rows.items():
        analysis = suffix.split("_")[0]
        columns, rows = _held_columns(
            _TREFFTZ_CELLS if analysis == "trefftz" else _LEDGER_CELLS,
            _ROTOR_TREFFTZ_COLUMNS if analysis == "trefftz" else ROTOR_LEDGER_COLUMNS,
            rows,
        )
        # FR-1053: <group> is the stem of the simulation's polar tables, so
        # the far-field file sits beside its polars by name.
        group = sweep_file_stem(ctx.sim_id, ctx.table_name)
        path = ctx.target(ctx.out / FARFIELD_DIR / f"{group}_{suffix}.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_csv_table(path, ("POL", "ENTRY", "STEP", *CONTEXT_COLUMNS, *columns), rows)
        entry: dict[str, object] = {
            "runs": tables.runs[suffix],
            "analysis": analysis,
            "variants": variants if analysis == "trefftz" else [],
            "inputs": tables.inputs.get(suffix, {}),
            "entries": {
                item.name: {"export_type": item.export_type} for item in ctx.pproc.farfields
            },
        }
        if "_" in suffix:
            entry["reduction"] = suffix.split("_")[1]
        if suffix in tables.reduced:
            # The averaging window and the sample count each point's reduced rows hold.
            entry["reduced_from"] = tables.reduced[suffix]
        if analysis == "trefftz" and "sections" in variants:
            entry["strip_rule"] = "extended"
        if analysis == "ledgers":
            entry["symmetry_excluded_orders"] = {
                point.name: {
                    item.name: symmetry_excluded_orders(
                        item.ledgers,
                        ctx.record_of[point.name],
                        getattr(ctx.live, "rotors", None) or {},
                    )
                    for item in ctx.pproc.farfields
                    if item.ledgers is not None
                }
                for point in ctx.points
                if point.name in tables.inputs.get(suffix, {})
            }
        ctx.add(path, entry)
