"""The far-field product family: Trefftz-plane and balance tables of one simulation (FR-456).

Pipeline role: the body of the post step that writes ``farfield/<group>_trefftz.csv``,
``farfield/<group>_ledgers.csv`` (``_instant`` and ``_average`` on an unsteady
row) and the spanwise files ``sections/<point>_trefftz_<family>.csv`` from the
exports a run recorded, through the numpy core of :mod:`pyflightstream.farfield`.
It reads the exports with the ``results`` readers, turns every vector to the
far-field axes (FR-450 R3), and states every point an analysis cannot serve as
a named skip in ``products.json`` and a WARNING in ``post.log`` (FR-450 R5).
Which analysis applies to which row is the one function the plan uses
(:func:`pyflightstream.cases.farfield_inputs.applies`). A simulation whose pproc
artifact has no ``[farfield]`` table writes nothing and logs nothing, so its
products keep their bytes (FR-456 R8).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import classify_outputs
from pyflightstream.cases.farfield_inputs import (
    ROTOR_RUN_TYPES,
    UNSTEADY_RUN_TYPES,
    applies,
    few_stations_warning,
)
from pyflightstream.farfield import (
    TraceResult,
    calibration_scale,
    trace_coefficients,
    trace_forces,
    wake_crossings,
)
from pyflightstream.post._condition import _recorded_speeds, row_rotor_speeds
from pyflightstream.post._tables import CONTEXT_COLUMNS, _cell, context_row, write_csv_table
from pyflightstream.post.axes import EXPORT_TO_BODY, body_to_wind, wind_force_coefficients
from pyflightstream.post.farfield_fields import (
    LEDGER_COLUMNS,
    FarLayout,
    ProbeSamples,
    average_rows,
    derived_layout,
    far_samples,
    frame_lattice,
    lattice_samples,
    ledger_values,
    native_per_m,
    plane_values,
    recorded_layout,
    rotor_lattice,
    rotor_values,
    steady_samples,
    unsteady_samples,
)
from pyflightstream.post.section_distributions import distributions_of
from pyflightstream.results.loads import drag_pair, parse_unsteady_plots
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

#: The product folder of the far-field tables (FR-456 R1).
FARFIELD_DIR = "farfield"

#: The columns of ``farfield/<group>_trefftz.csv`` after ``POL``, ``STEP`` and the
#: condition block (FR-456 R2).
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
#: The columns of a spanwise file ``sections/<point>_trefftz_<family>.csv`` (FR-456 R3).
SPANWISE_COLUMNS: tuple[str, ...] = (
    "POL",
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
_NA = float("nan")
_VARIANT_NAMES = {"sections": "A", "wake": "B", "plane": "C"}
#: Above this Mach number the C row is written with a WARNING that the
#: incompressible relations of the definitions page are used (FR-453 R7).
_INCOMPRESSIBLE_MACH = 0.3
#: A Trefftz C plane whose own lift (its vorticity's first moment) departs from
#: the solver's CL by more than this fraction is flagged: its field does not hold
#: the circulation the loads shed, so its crossflow energy is not their induced
#: drag (FR-453 R9; RPT-170 measured 0.74 on 26.124 and 1.05 on 26.125, one wing).
_PLANE_LIFT_TOLERANCE = 0.10
#: Trefftz A over families whose traced lift departs from the solver's CL by
#: more than this fraction is warned: another family or a body carries the
#: rest, so CDI_T and E_T are of the traced families alone (FR-451 R13). A wing
#: traced alone agreed to 0.15 percent (RPT-170's wing); a wing traced without
#: its body departed by 6.6 and 7 percent.
_TRACED_LIFT_TOLERANCE = 0.05
_AXES = {"X": np.array([1.0, 0.0, 0.0]), "Y": np.array([0.0, 1.0, 0.0]), "Z": np.array([0, 0, 1.0])}


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


@dataclass
class _Tables:
    """The rows of one simulation's far-field files, by file suffix."""

    rows: dict[str, list[tuple[object, ...]]] = field(default_factory=dict)
    owners: dict[str, list[str]] = field(default_factory=dict)
    runs: dict[str, list[str]] = field(default_factory=dict)
    inputs: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def extend(self, suffix: str, point: str, runs: Sequence[str], rows: list) -> None:
        if not rows:
            return
        self.rows.setdefault(suffix, []).extend(rows)
        self.owners.setdefault(suffix, []).extend([point] * len(rows))
        held = self.runs.setdefault(suffix, [])
        held += [run for run in runs if run not in held]
        self.inputs.setdefault(suffix, {}).setdefault(point, list(runs))

    def super_rows(self) -> list[tuple[tuple[object, ...], str]]:
        """Return the rows the super file reads: steady, else each point's average or instant."""
        out = list(zip(self.rows.get("trefftz", []), self.owners.get("trefftz", []), strict=True))
        averaged = set(self.owners.get("trefftz_average", []))
        for suffix in ("trefftz_average", "trefftz_instant"):
            pairs = zip(self.rows.get(suffix, []), self.owners.get(suffix, []), strict=True)
            out += [
                (row, point)
                for row, point in pairs
                if suffix == "trefftz_average" or point not in averaged
            ]
        return out


def _spec(ctx: SimContext) -> FarfieldSpec:
    """Return the simulation's ``[farfield]`` table; the step runs only where there is one."""
    return cast("FarfieldSpec", ctx.pproc.farfield)


def _trefftz(ctx: SimContext) -> TrefftzSpec:
    return cast("TrefftzSpec", _spec(ctx).trefftz)


def _ledgers(ctx: SimContext) -> LedgersSpec:
    return cast("LedgersSpec", _spec(ctx).ledgers)


def _skip(ctx: SimContext, key: str, point: str, reason: str) -> None:
    ctx.skipped[key] = reason
    warn(f"point={point} product=farfield: {reason}", PyflightstreamWarning, stacklevel=3)


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


def _flow(point: PolarPoint) -> tuple[float, float, float, float]:
    """Return the density, the free-stream speed, alpha and beta (deg) of a point."""
    state = point.state
    rho = float(state.density_kg_m3) if state and state.density_kg_m3 else _NA
    loads = point.loads
    return rho, float(loads.freestream_velocity_m_s), loads.angle_of_attack_deg, loads.sideslip_deg


def _q_ref(point: PolarPoint, rho: float) -> float:
    """Return the dynamic pressure the export's ``Cp_ref`` and coefficients are taken on."""
    loads = point.loads
    v_ref = loads.reference_velocity_m_s or loads.freestream_velocity_m_s
    return 0.5 * rho * float(v_ref) ** 2


def _near_field(point: PolarPoint) -> tuple[float, float, float]:
    """Return the solver's CL and its pressure and vorticity induced drags (FR-456 R2).

    The solver prints one induced drag: from the vorticity where the run
    selected boundaries for it (``SET_VORTICITY_DRAG_BOUNDARIES``), from the
    surface pressures otherwise; the other column is ``NA``. It is the first
    column of the printed drag split (:func:`~pyflightstream.results.loads.drag_pair`):
    ``CDi`` up to 26.124, ``CDp`` on 26.125, which takes the vorticity value
    when the run selects it and leaves ``CDv`` unchanged, as ``CDi`` does
    beside ``CDo`` (PFS-2081.98, RPT-170). A table printing neither split
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
    """Return the point's solver termination status, as the sweep table writes it (FR-456 R10)."""
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
    cells = (merged.get(column, _NA) for column in TREFFTZ_COLUMNS)
    return (ctx.sim_id, step, *_context(ctx, point), *cells)


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
    """Return the rows of one trace: each family where there are several, then TOTAL."""
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
    entries.append(
        ("TOTAL", result.lift, result.side_force, result.induced_drag, _NA, len(result.y))
    )
    rows = []
    for name, lift, side, drag, alone, count in entries:
        c = trace_coefficients(
            lift * factor, side * factor, drag * factor, q=q, s_ref=sref, b_ref=bref
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
    """Write ``sections/<point>_trefftz_<family>.csv``, the meshed strips of one sheet."""
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
    path = ctx.target(ctx.out / f"sections/{point.name}_trefftz_{name}.csv")
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


def _a_blocks(ctx: SimContext, point: PolarPoint, key: str) -> dict[str, np.ndarray] | None:
    """Return the sectional-load rows of each family cut in XZ of a reference frame, or skip."""
    sloads = ctx.exports.get(point.name, (None, None, None))[0]
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
    start = 0
    for block in layout:
        count = int(str(block["count"]))
        rows = report.values[start : start + count]
        start += count
        names = [str(name) for name in cast("list[object]", block.get("families") or [])]
        frame = str(block.get("frame") or "MRP").upper()
        if block.get("plane") == "XZ" and frame in ("MRP", "REFERENCE") and len(names) == 1:
            blocks.setdefault(names[0], rows[np.argsort(rows[:, 0], kind="stable")])
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


def _variant_a(ctx: SimContext, point: PolarPoint) -> list:
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
    blocks = _a_blocks(ctx, point, key)
    if blocks is None:
        return []
    inventory = ctx.record_of[point.name].inventory or list(blocks)
    selected = _selected(spec.families, inventory, ctx.aliases, ctx.pproc.is_blade)
    chosen = [name for name in selected if name in blocks]
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
            np.concatenate(zs),
            np.concatenate(gammas),
            rho=rho,
            v_inf=speed,
            sheets=np.concatenate(sheets),
            mirror=mirror,
        )
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the trace cannot be formed: {error}")
        return []
    for index, name in enumerate(chosen):
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
    """Warn where the families A traced do not carry the solver's lift (FR-451 R13, PFS-2081.96).

    A trace over a subset of the lifting surfaces (a wing without its body)
    sheds the circulation of those surfaces alone and ends at their root with
    whatever their loading holds there, so its induced drag and span
    efficiency are not the configuration's. The row is written; the WARNING
    names the families, both lifts and their ratio.
    """
    rho, speed, _alpha, _beta = _flow(point)
    cl_traced = lift / (0.5 * rho * speed * speed * float(ctx.reference.sref_m2))
    cl_near = _near_field(point)[0]
    if not (math.isfinite(cl_traced) and math.isfinite(cl_near) and cl_near):
        return
    ratio = cl_traced / cl_near
    if abs(ratio - 1.0) > _TRACED_LIFT_TOLERANCE:
        warn(
            f"point={point.name} product=farfield: Trefftz A traces {', '.join(families)} with "
            f"a lift CL_T = {cl_traced:.4g}, {ratio:.3g} times the solver's CL {cl_near:.4g}; "
            "the traced families do not carry the configuration's lift, so their CDI_T and "
            "E_T are of those families alone, not of the configuration (FR-451 R13)",
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


def _variant_b(ctx: SimContext, point: PolarPoint) -> list:
    """Trefftz B of one steady point (FR-452): rows, or a named skip."""
    spec = _trefftz(ctx)
    key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=wake"
    vtk = _output(ctx, point, "vtk")
    wakes = None if vtk is None else vtk.with_name(vtk.stem + "_wakes.vtk")
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
    turn = farfield_axes(alpha, beta)
    lines = [(line / per_m) @ turn.T for line in wake.lines]
    x_t = max((float(line[0, 0]) for line in lines), default=0.0)
    x_t += spec.distance_bref * ctx.reference.bref_m
    mirror, half = _symmetry(ctx)
    lines, shed_values = _wake_sheet(ctx, point, lines, wake.values, mirror=mirror)
    trace = wake_crossings(lines, shed_values, x_t=x_t)
    if trace.problem is not None:
        # FR-452 R3, R4: the point's B row is written NA, never dropped, and
        # the WARNING says why; a short wake states the length the run had.
        reach = min(float(line[-1, 0] - line[0, 0]) for line in lines) if lines else _NA
        length = (
            f"; the recorded wake is {reach:.4g} m long on its shortest line, and the plane "
            f"stands {spec.distance_bref * ctx.reference.bref_m:.4g} m behind the trailing edge"
            if trace.short
            else ""
        )
        _skip(ctx, key, point.name, f"no trace at x = {x_t:.4g} m: {trace.problem}{length}")
        values = {"FAMILY": "TOTAL", "VARIANT": "B", "X_T_M": x_t}
        return [_row(ctx, point, _NA, values)]
    try:
        raw = trace.forces(rho=rho, v_inf=speed, mirror=mirror)
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the trace cannot be formed: {error}")
        return []
    factor = 0.5 if half else 1.0
    k = calibration_scale(
        raw.lift * factor,
        cl_near=_near_field(point)[0],
        q=0.5 * rho * speed * speed,
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
    _spanwise(ctx, point, variant="wake", name="TOTAL", result=result, chords=None)
    return _trace_rows(
        ctx,
        point,
        result,
        variant="wake",
        names=["TOTAL"],
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
        # Both halves, including two coincident root lines, are exported.
        # Select by upstream nodes, before roll-up moves the crossings.
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


@dataclass(frozen=True)
class _Instant:
    """The probe values of one instant and the step they are of."""

    samples: ProbeSamples
    step: object


def _instants(ctx: SimContext, point: PolarPoint, unsteady: bool) -> tuple[list[_Instant], str]:
    """Return the instants a point's probes give: one steady, or every step of a window."""
    _sloads, plots, probes = ctx.exports.get(point.name, (None, None, None))
    try:
        if not unsteady:
            if probes is None:
                return [], "the point exported no probe values"
            return [_Instant(steady_samples(Path(probes).read_text(encoding="utf-8")), _NA)], ""
        if plots is None:
            return [], "the point exported no fluid plots"
        series = parse_unsteady_plots(Path(plots).read_text(encoding="utf-8")).series_by_name()
    except (PyflightstreamError, OSError) as error:
        return [], f"the probe values cannot be read: {error}"
    steps = series.get("Time-step")
    count = len(next(iter(series.values()))) if series else 0
    out = []
    for row in range(count):
        step = int(steps[row]) if steps is not None and math.isfinite(steps[row]) else row + 1
        out.append(_Instant(unsteady_samples(series, ctx.probe_positions, row), step))
    return out, "" if out else "the fluid plots hold no time step"


def _lattice_of(ctx: SimContext, spec) -> tuple[Any, np.ndarray | None, str] | None:
    if spec.ledgers is None:
        return None
    if spec.ledgers.rotor is None:
        return frame_lattice(spec.ledgers)
    rotor = (getattr(ctx.live, "rotors", None) or {}).get(spec.ledgers.rotor)
    if rotor is None:
        raise PyflightstreamError(
            f"the reference names no rotor {spec.ledgers.rotor!r} to place the lattice on"
        )
    return rotor_lattice(spec.ledgers, rotor)


def _plane_grid(ctx: SimContext, spec) -> tuple[float, float, float]:
    half_width, half_height, spacing = spec.trefftz.plane_bref()
    bref = float(ctx.reference.bref_m)
    return half_width * bref, half_height * bref, spacing * bref


@dataclass(frozen=True)
class _Probe:
    """Where a point's far-field probes are and how to read them."""

    per_m: float
    layout: FarLayout
    hub: tuple[float, np.ndarray, np.ndarray] | None
    rotor: bool = False


def _layout(ctx: SimContext, point: PolarPoint, spec, rotor: bool) -> FarLayout:
    """Return the far-field probes of a point: as its run recorded them, else from the table.

    PFS-2081.58: the record's layout is what the plan laid or reused, so post
    integrates exactly those probes with their own grid, whatever the table
    states today. A record written before the layout was recorded is matched
    to the table as it stands, the plane and a frame's lattice by shape.
    """
    record = ctx.record_of[point.name]
    shapes = (getattr(record, "farfield_layout", None) or {}).get("shapes")
    if shapes:
        return recorded_layout(shapes)
    plane = spec.trefftz is not None and "plane" in spec.trefftz.variant and not rotor
    _rho, _speed, alpha, beta = _flow(point)
    a, b = math.radians(alpha), math.radians(beta)
    direction = (math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a))
    return derived_layout(
        plane_grid=_plane_grid(ctx, spec) if plane else None,
        direction=direction,
        lattice=_lattice_of(ctx, spec),
    )


def _hub(
    ctx: SimContext, point: PolarPoint, spec, layout: FarLayout
) -> tuple[float, np.ndarray, np.ndarray] | None:
    """Return the frame speed (rad/s, signed), axis and origin of a quasi-steady rotor's probes.

    PFS-2081.93: the speed is read as every other product of the point reads
    it, the record's plan where it states one and otherwise the row's own
    speed from the quasi-steady record beside the loads export
    (:func:`~pyflightstream.post._condition.row_rotor_speeds`), which a
    ``qsteady_rotor`` run always writes and never plans. That speed is SIGNED
    by the rotor's hand (``rpm_sign`` times the row's magnitude), so the frame
    turns about the axis by the sign of the speed alone; the hand is not
    applied a second time. The axis and the hub are the lattice's as the run
    recorded it, or the reference's rotor block for a record without a layout.
    """
    record = ctx.record_of[point.name]
    if str(record.recipe or "") != "qsteady_rotor" or spec.ledgers is None:
        return None
    alias = spec.ledgers.rotor
    own = row_rotor_speeds(record, getattr(point, "loads_path", None))
    rpm = _recorded_speeds(record.reductions, own).get(str(alias))
    rotor: Any = (getattr(ctx.live, "rotors", None) or {}).get(alias)
    if rpm is None:
        raise PyflightstreamError(
            f"the quasi-steady rotor {alias!r} states no speed in the point's record nor in "
            "its quasi-steady record, so its probes cannot be converted to the hub frame"
        )
    if layout.lattice_origin_m is not None:
        letter, origin = layout.axis, np.asarray(layout.lattice_origin_m, dtype=np.float64)
    elif rotor is not None:
        letter = str(rotor.axis)
        origin = np.asarray([rotor.x_m, rotor.y_m, rotor.z_m], dtype=np.float64)
    else:
        raise PyflightstreamError(
            f"the reference names no rotor {alias!r}, so the hub its probes turn about is unknown"
        )
    return 2.0 * math.pi * float(rpm) / 60.0, _AXES[letter.strip().upper()], origin


def _locate(ctx: SimContext, point: PolarPoint, spec, rotor: bool) -> _Probe:
    per_m = _per_m(ctx, point)
    if per_m is None:
        raise PyflightstreamError(
            "the point saved no simulation whose length unit the package reads, so its probe "
            "positions cannot be matched in metres"
        )
    layout = _layout(ctx, point, spec, rotor)
    return _Probe(per_m=per_m, layout=layout, hub=_hub(ctx, point, spec, layout), rotor=rotor)


def _instant_values(
    ctx: SimContext, point: PolarPoint, instant: _Instant, probe: _Probe, analyses: Sequence[str]
) -> dict[str, Any]:
    """Return the C values and the ledger rows of one instant, keyed by analysis."""
    rho, speed, alpha, beta = _flow(point)
    q_ref = _q_ref(point, rho)
    layout = probe.layout
    lattice_at, plane_at, why = far_samples(instant.samples, layout, per_m=probe.per_m)
    # A wing's Trefftz C reads the plane; a rotor's reads a lattice station.
    wants_plane = "trefftz:plane" in analyses and not probe.rotor
    wants_lattice = "ledgers" in analyses or ("trefftz:plane" in analyses and probe.rotor)
    if (wants_plane and plane_at is None) or (wants_lattice and lattice_at is None):
        raise PyflightstreamError(why or "the run laid no far-field probes these analyses read")
    out: dict[str, Any] = {}
    if plane_at is not None and "trefftz:plane" in analyses:
        out["plane"] = plane_values(
            instant.samples,
            plane_at,
            flow=(rho, speed, alpha, beta),
            grid=cast("tuple[float, float, float]", layout.plane_grid),
            per_m=probe.per_m,
            q_ref=q_ref,
        )
    if lattice_at is None or layout.lattice is None:
        return out
    lattice, axis = layout.lattice, layout.axis
    hub = None
    if probe.hub is not None:
        hub = (probe.hub[0], probe.hub[1], probe.hub[2])
    fields = lattice_samples(instant.samples, lattice_at, lattice, axis, q=q_ref, hub=hub)
    if "trefftz:plane" in analyses and "plane" not in out:
        station = _trefftz(ctx).station
        station = float(lattice.stations[-1]) if station is None else float(station)
        out["rotor"] = rotor_values(fields, rho=rho, speed=speed, station=station)
    if "ledgers" in analyses:
        near = (
            -float(point.loads.total.get(f"C{axis.lower()}", _NA)) * q_ref * ctx.reference.sref_m2
        )
        out["ledgers"] = ledger_values(
            fields, _ledgers(ctx), rho=rho, speed=speed, near=(near, ctx.reference.sref_m2)
        )
    return out


def _c_row(ctx: SimContext, point: PolarPoint, values: Mapping[str, Any], step: object):
    rho, speed, _alpha, _beta = _flow(point)
    qs = 0.5 * rho * speed * speed * float(ctx.reference.sref_m2)
    if "plane" in values:
        plane = values["plane"]
        cdi = plane["D"] / qs
        cl = _near_field(point)[0]
        aspect = float(ctx.reference.bref_m) ** 2 / float(ctx.reference.sref_m2)
        e = cl * cl / (math.pi * aspect * cdi) if math.isfinite(cdi) and cdi else _NA
        cells = {
            "FAMILY": "TOTAL",
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
    cells = {"FAMILY": _ledgers(ctx).rotor, "VARIANT": "C", **rotor}
    return _row(ctx, point, step, cells)


def _ledger_rows(ctx: SimContext, point: PolarPoint, values: Mapping[str, Any], step: object):
    name = _ledgers(ctx).rotor or _ledgers(ctx).frame
    context = _context(ctx, point)
    rows = []
    for station in values["ledgers"]:
        cells = {"LATTICE": name, "STATUS": _status(ctx, point), **station}
        rows.append((ctx.sim_id, step, *context, *(cells.get(c, _NA) for c in LEDGER_COLUMNS)))
    return rows


def _probe_point(ctx: SimContext, point: PolarPoint, analyses: Sequence[str], tables: _Tables):
    """C and the ledgers of one point: steady, or instant and average (FR-38 R7, FR-456 R1)."""
    spec = _spec(ctx)
    record = ctx.record_of[point.name]
    run_type = str(record.recipe or "steady")
    unsteady = run_type in UNSTEADY_RUN_TYPES
    key = f"{FARFIELD_DIR}/probes#point={point.name}"
    rotor = run_type in ROTOR_RUN_TYPES
    # FR-455 R9: an unsteady row whose [[probes]] entries are of kind normal
    # holds its probes at the last time step only, in the probe export.
    normal = unsteady and _normal_probes(ctx)
    try:
        probe = _locate(ctx, point, spec, rotor)
        instants, why = _instants(ctx, point, unsteady and not normal)
        if why:
            raise PyflightstreamError(why)
        if unsteady and not normal:
            window = ctx.point_windows.get(point.name)
            last = instants[-1]
            chosen = [i for i in instants if window and window[0] <= _step(i) <= window[1]]
        else:
            last, chosen = instants[0], []
            if normal:
                last = replace(last, step=_last_step(record))
        sets = [(last, _instant_values(ctx, point, last, probe, analyses))]
        averaged = [(i, _instant_values(ctx, point, i, probe, analyses)) for i in chosen]
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the far-field probes cannot be read: {error}")
        return
    if "plane" in sets[0][1] or "rotor" in sets[0][1]:
        _warn_compressible(ctx, point)
    if "plane" in sets[0][1]:
        _flag_a_plane_short_of_the_lift(ctx, point, sets[0][1]["plane"])
    runs = ctx.sources[point.name]
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
            c_rows = average_rows([[row] for row in c_rows], 2 + len(CONTEXT_COLUMNS) + 2)
            l_rows = [average_rows(l_rows, 2 + len(CONTEXT_COLUMNS) + 1)] if l_rows else []
        tables.extend(f"trefftz{suffix}", point.name, runs, c_rows)
        tables.extend(f"ledgers{suffix}", point.name, runs, [r for rows in l_rows for r in rows])


def _step(instant: _Instant) -> float:
    step = instant.step
    return float(step) if isinstance(step, int | float) else math.nan


def _normal_probes(ctx: SimContext) -> bool:
    """Whether the row's ``[[probes]]`` entries are all of kind normal (FR-417, FR-455 R9)."""
    try:
        return bool(ctx.pproc.samples_normal_probes())
    except PyflightstreamError:
        return False


def _last_step(record: object) -> object:
    """Return the run's last time step, the instant a normal probe holds, or NA."""
    plan = getattr(record, "reductions", None) or {}
    last = plan.get("time_iterations") if isinstance(plan, Mapping) else None
    return int(last) if isinstance(last, int | float) and not isinstance(last, bool) else _NA


def _flag_a_plane_short_of_the_lift(
    ctx: SimContext, point: PolarPoint, plane: Mapping[str, float]
) -> None:
    """Warn where the C plane's own lift is not the solver's CL (FR-453 R9, PFS-2081.95).

    The plane's lift is the Kutta-Joukowski lift of the vorticity it holds,
    which roll-up does not change; a plane holding the wake the loads shed
    carries the solver's lift. Where it departs by more than
    :data:`_PLANE_LIFT_TOLERANCE`, the probe field does not hold that
    circulation (RPT-170) and the row's crossflow energy is not the loads'
    induced drag: the row is written, and flagged here.
    """
    rho, speed, _alpha, _beta = _flow(point)
    qs = 0.5 * rho * speed * speed * float(ctx.reference.sref_m2)
    cl_plane, cl_near = plane["L"] / qs, _near_field(point)[0]
    if not (math.isfinite(cl_plane) and math.isfinite(cl_near) and cl_near):
        return
    ratio = cl_plane / cl_near
    if abs(ratio - 1.0) > _PLANE_LIFT_TOLERANCE:
        warn(
            f"point={point.name} product=farfield: the Trefftz C plane carries a lift of its own "
            f"vorticity CL_T = {cl_plane:.4g}, {ratio:.3g} times the solver's CL {cl_near:.4g}; "
            "the probe field does not hold the circulation the loads shed, so its crossflow "
            "energy is not their induced drag (FR-453 R9, RPT-170)",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_compressible(ctx: SimContext, point: PolarPoint) -> None:
    """Warn once per point that a C row above Mach 0.3 uses incompressible relations (R7)."""
    mach = ctx.condition(point).get("MACH")
    if isinstance(mach, int | float) and float(mach) > _INCOMPRESSIBLE_MACH:
        warn(
            f"point={point.name} product=farfield: the point flies at Mach {float(mach):.4g}, "
            f"above {_INCOMPRESSIBLE_MACH}; its Trefftz C row is written with the "
            "incompressible relations of the definitions page (FR-453 R7)",
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
    elif normal:
        _skip(
            ctx,
            f"{FARFIELD_DIR}/average#point={point.name}",
            point.name,
            'the far-field probes of this unsteady row are [[probes]] of kind = "normal", '
            "which hold the last time step only: the instant is written and the average "
            "is not (FR-455 R9)",
        )
    else:
        _skip(
            ctx,
            f"{FARFIELD_DIR}/average#point={point.name}",
            point.name,
            "the point has no "
            "averaging window, or no plotted step inside it, so no average is written",
        )
    return out


def _analyses(spec, run_type: str, rotor: bool) -> tuple[list[str], dict[str, str]]:
    selected = []
    if spec.trefftz is not None:
        selected += [f"trefftz:{variant}" for variant in spec.trefftz.variant]
    if spec.ledgers is not None:
        selected.append("ledgers")
    reasons = {a: applies(a, run_type, rotor=rotor) for a in selected}
    return [a for a in selected if not reasons[a]], {a: r for a, r in reasons.items() if r}


def _super_cells(rows: Sequence[tuple[tuple[object, ...], str]]) -> dict[str, dict[str, str]]:
    """Return per point the super-file cells of its TOTAL rows, as the tables write them (R9)."""
    first = 2 + len(CONTEXT_COLUMNS)
    family = first + TREFFTZ_COLUMNS.index("FAMILY")
    variant = first + TREFFTZ_COLUMNS.index("VARIANT")
    out: dict[str, dict[str, str]] = {}
    for row, point in rows:
        if row[family] != "TOTAL":
            continue
        cells = out.setdefault(point, {})
        for column in ("CL_T", "CDI_T", "E_T"):
            cells[f"{column}_{row[variant]}"] = _cell(row[first + TREFFTZ_COLUMNS.index(column)])
    return out


def farfield_products(ctx: SimContext) -> None:
    """Write the far-field tables of one simulation (FR-456), or nothing without ``[farfield]``.

    Parameters
    ----------
    ctx : SimContext
        Product context carrying the resolved case, exports and output destinations.
    """
    spec = getattr(ctx.pproc, "farfield", None)
    if spec is None:
        return
    tables = _Tables()
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
        if "trefftz:sections" in analyses:
            steady_rows += _variant_a(ctx, point)
        if "trefftz:wake" in analyses:
            steady_rows += _variant_b(ctx, point)
        tables.extend("trefftz", point.name, runs, steady_rows)
        if "trefftz:plane" in analyses or "ledgers" in analyses:
            _probe_point(ctx, point, analyses, tables)
    _write(ctx, spec, tables)
    ctx.farfield_super.update(_super_cells(tables.super_rows()))


def _spins(ctx: SimContext, record: object) -> bool:
    """Whether a steady row turns a rotor: an ``RPM`` on its point, its row or a motion."""
    stated = dict(getattr(ctx.matrix_row, "variables", None) or {})
    stated.update(getattr(record, "point", None) or {})
    return any(str(name).upper() in ("RPM", "MOTIONS") for name in stated)


def _write(ctx: SimContext, spec, tables: _Tables) -> None:
    variants = list(spec.trefftz.variant) if spec.trefftz is not None else []
    for suffix, rows in tables.rows.items():
        analysis = suffix.split("_")[0]
        columns = TREFFTZ_COLUMNS if analysis == "trefftz" else LEDGER_COLUMNS
        # FR-456 R1: <group> is the stem of the simulation's polar tables, so
        # the far-field file sits beside its polars by name.
        group = sweep_file_stem(ctx.sim_id, ctx.table_name)
        path = ctx.target(ctx.out / FARFIELD_DIR / f"{group}_{suffix}.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_csv_table(path, ("POL", "STEP", *CONTEXT_COLUMNS, *columns), rows)
        entry: dict[str, object] = {
            "runs": tables.runs[suffix],
            "analysis": analysis,
            "variants": variants if analysis == "trefftz" else [],
            "inputs": tables.inputs.get(suffix, {}),
        }
        if "_" in suffix:
            entry["reduction"] = suffix.split("_")[1]
        if analysis == "trefftz" and "sections" in variants:
            entry["strip_rule"] = "extended"
        ctx.add(path, entry)
