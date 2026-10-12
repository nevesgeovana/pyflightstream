"""The far-field product family: Trefftz-plane tables of one simulation (FR-456).

Pipeline role: the body of the post step that writes ``farfield/<group>_trefftz.csv``
and the spanwise files ``sections/<point>_trefftz_<family>.csv`` from the
exports a run recorded, through the numpy core of :mod:`pyflightstream.farfield`.
It reads the exports with the ``results`` readers, turns every vector with
:mod:`pyflightstream.post.axes` (FR-450 R3), and states every point an analysis
cannot serve as a named skip in ``products.json`` and a WARNING in ``post.log``
(FR-450 R5). A simulation whose pproc artifact has no ``[farfield]`` table
writes nothing and logs nothing, so its products keep their bytes (FR-456 R8).

This build serves variant A (``sections``) and variant B (``wake``) on steady
rows; variant C and the ledgers are named skips until the plan lays their
probes (FR-455).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import classify_outputs
from pyflightstream.cases.farfield_inputs import applies
from pyflightstream.farfield import (
    TraceResult,
    calibration_scale,
    trace_coefficients,
    trace_forces,
    wake_crossings,
)
from pyflightstream.post._tables import CONTEXT_COLUMNS, context_row, write_csv_table
from pyflightstream.post.axes import EXPORT_TO_BODY, body_to_wind, wind_force_coefficients
from pyflightstream.post.section_distributions import _distributions
from pyflightstream.results.sectional_loads import parse_sectional_loads
from pyflightstream.results.wake import parse_wake_export

if TYPE_CHECKING:
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
)
_NA = float("nan")
_VARIANT_NAMES = {"sections": "A", "wake": "B", "plane": "C"}
#: The measured strip bias of the discrete trace on an elliptic loading, in
#: percent of E_T, at the station counts per side the definitions page states.
_BIAS_PCT = {40: 1.05, 80: 0.52, 160: 0.26}


def farfield_axes(alpha_deg: float, beta_deg: float) -> np.ndarray:
    """Return the matrix taking export-frame components to the far-field axes.

    The far-field axes are the wind axes of :mod:`pyflightstream.post.axes`
    turned half a turn about their y axis: x along the free stream downstream,
    y to the right, z up, so at zero incidence and sideslip they are the export
    frame's own (x aft, y right, z up).
    """
    return EXPORT_TO_BODY @ body_to_wind(alpha_deg, beta_deg) @ EXPORT_TO_BODY


def _skip(ctx: SimContext, key: str, point: str, reason: str) -> None:
    ctx.skipped[key] = reason
    warn(f"point={point} product=farfield: {reason}", PyflightstreamWarning, stacklevel=3)


def _symmetry(ctx: SimContext) -> tuple[bool, bool]:
    """Return (mirror, half loads) from the row's SYMMETRY and SYMMETRY_LOADS."""
    variables: Mapping[str, object] = getattr(ctx.matrix_row, "variables", None) or {}
    mirror = str(variables.get("SYMMETRY", "")).strip().upper() == "MIRROR"
    loads = str(variables.get("SYMMETRY_LOADS", "")).strip().lower()
    return mirror, mirror and loads in ("false", "0", "no", "disable")


def _selected(spec_families: str | Sequence[str], families: Sequence[str], aliases) -> list[str]:
    """Return the families of a block list the ``[farfield] families`` selection names."""
    words = [spec_families] if isinstance(spec_families, str) else list(spec_families)
    if "all" in words:
        return list(families)
    chosen: list[str] = []
    for word in words:
        members = list(aliases.get(word, ())) if aliases else []
        for name in members or [word]:
            if name in families and name not in chosen:
                chosen.append(name)
    return chosen


def _point_state(point: PolarPoint) -> tuple[float, float]:
    rho = float(getattr(point.state, "density_kg_m3", _NA) or _NA)
    speed = float(point.loads.freestream_velocity_m_s)
    return rho, speed


def _near_field(point: PolarPoint) -> tuple[float, float, float]:
    """Return the solver's own CL and its pressure and vorticity induced drags (FR-456 R2)."""
    total = point.loads.total
    cl = float(total.get("CL", _NA))
    pressure = float(total["CDp"]) if "CDp" in total else _NA
    vorticity = float(total["CDi"]) if "CDi" in total and "CDp" not in total else _NA
    return cl, pressure, vorticity


def _rows_of(
    ctx: SimContext,
    point: PolarPoint,
    variant: str,
    result,
    *,
    names: Sequence[str],
    factor: float,
    q: float,
    extra: Mapping[str, float],
    isolated: bool,
    blank: Sequence[str] = (),
) -> list[tuple[object, ...]]:
    sref = float(ctx.reference.sref_m2 or _NA)
    bref = float(ctx.reference.bref_m or _NA)
    _cl_near, cdp_near, cdi_near = _near_field(point)
    context = context_row(ctx.condition(point), ctx.reference.as_lengths())
    rows = []
    entries = []
    if len(names) > 1:
        for index, name in enumerate(names):
            entries.append(
                (
                    name,
                    result.sheet_lift[index],
                    result.sheet_side_force[index],
                    result.sheet_drag_share[index],
                    result.sheet_drag_isolated[index] if isolated else _NA,
                    int(np.count_nonzero(result.sheet == result.sheets[index])),
                )
            )
    entries.append(
        ("TOTAL", result.lift, result.side_force, result.induced_drag, _NA, len(result.y))
    )
    for name, lift, side, drag, alone, count in entries:
        c = trace_coefficients(
            lift * factor, side * factor, drag * factor, q=q, s_ref=sref, b_ref=bref
        )
        cdi_alone = alone * factor / (q * sref) if math.isfinite(alone) and q * sref > 0 else _NA
        values = {
            "FAMILY": name,
            "VARIANT": _VARIANT_NAMES[variant],
            "CL_T": c["CL_T"],
            "CDI_T": c["CDI_T"],
            "CDI_T_ISOLATED": cdi_alone,
            "CY_T": c["CY_T"],
            "E_T": c["E_T"],
            "AR": c["AR"],
            "N_TRACE": count,
            "CDI_NEAR_PRESSURE": cdp_near,
            "CDI_NEAR_VORTICITY": cdi_near,
            **extra,
        }
        values.update({column: _NA for column in blank})
        rows.append(
            (ctx.sim_id, _NA, *context, *(values.get(column, _NA) for column in TREFFTZ_COLUMNS))
        )
    return rows


def _spanwise(
    ctx: SimContext,
    point: PolarPoint,
    *,
    variant: str,
    name: str,
    result: TraceResult,
    flow: tuple[float, float],
    chords: np.ndarray | None,
) -> None:
    """Write ``sections/<point>_trefftz_<family>.csv``, the meshed strips of one sheet."""
    rho, speed = flow
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
            )
        )
    path = ctx.target(ctx.out / f"sections/{point.name}_trefftz_{name}.csv")
    write_csv_table(path, SPANWISE_COLUMNS, rows)
    ctx.add(
        path, {"runs": list(ctx.sources[point.name]), "analysis": "trefftz", "variant": variant}
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
        layout, _ = _distributions(ctx.record_of[point.name], ctx.pproc)
        report = parse_sectional_loads(Path(sloads).read_text(encoding="utf-8"))
    except (PyflightstreamError, OSError) as error:
        _skip(ctx, key, point.name, f"the sectional loads cannot be read: {error}")
        return None
    blocks: dict[str, np.ndarray] = {}
    start = 0
    for block in layout:
        count = int(block["count"])
        rows = report.values[start : start + count]
        start += count
        names = list(block.get("families") or [])
        frame = str(block.get("frame") or "MRP").upper()
        if block.get("plane") == "XZ" and frame in ("MRP", "REFERENCE") and len(names) == 1:
            blocks.setdefault(names[0], rows[np.argsort(rows[:, 0], kind="stable")])
    return blocks


def _a_sheets(
    point: PolarPoint,
    blocks: Mapping[str, np.ndarray],
    chosen: Sequence[str],
    *,
    flow: tuple[float, float],
    stations: int,
    mirror: bool,
) -> tuple[list[np.ndarray], ...]:
    """Return per family the trace points, the circulation, the sheet labels and the chords."""
    rho, speed = flow
    ys, zs, gammas, sheets, chords = [], [], [], [], []
    for index, name in enumerate(chosen):
        rows = blocks[name]
        lift = np.array(
            [
                wind_force_coefficients((fx, 0.0, fz), point.alpha_deg, 0.0)[2]
                for fx, fz in zip(rows[:, 4], rows[:, 5], strict=True)
            ]
        )
        ys.append(rows[:, 0])
        zs.append(rows[:, 3])
        gammas.append(lift / (rho * speed))
        sheets.append(np.full(len(rows), index))
        chords.append(rows[:, 1])
        per_side = len(rows) if mirror else len(rows) // 2
        if per_side < stations:
            nearest = min(_BIAS_PCT, key=lambda n: abs(n - per_side))
            warn(
                f"point={point.name} product=farfield: family {name} has {per_side} stations per "
                f"side, fewer than the {stations} of [farfield.trefftz]; the strip bias of E_T is "
                f"about {_BIAS_PCT[nearest]} percent at {nearest} (the definitions page)",
                PyflightstreamWarning,
                stacklevel=2,
            )
    return ys, zs, gammas, sheets, chords


def _variant_a(ctx: SimContext, point: PolarPoint, families_word, stations: int) -> list:
    """Trefftz A of one steady point (FR-451): rows, or a named skip."""
    key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=sections"
    if abs(float(point.beta_deg)) > 0.0:
        _skip(
            ctx,
            key,
            point.name,
            "variant A traces the span with the free stream in the "
            "reference XZ plane, and this point has sideslip; variants B and C serve it",
        )
        return []
    rho, speed = _point_state(point)
    if not (math.isfinite(rho) and speed > 0.0):
        _skip(ctx, key, point.name, "the point states no density or free-stream speed")
        return []
    blocks = _a_blocks(ctx, point, key)
    if blocks is None:
        return []
    chosen = _selected(families_word, list(blocks), ctx.aliases)
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
        point, blocks, chosen, flow=(rho, speed), stations=stations, mirror=mirror
    )
    try:
        result = trace_forces(
            np.concatenate(ys),
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
            flow=(rho, speed),
            chords=chords[index],
        )
    return _rows_of(
        ctx,
        point,
        "sections",
        result,
        names=chosen,
        factor=0.5 if half else 1.0,
        q=0.5 * rho * speed * speed,
        extra={"X_T_M": _NA},
        isolated=True,
    )


def _sheet(result, index: int):
    """Return the strips of one sheet of a trace, as a trace of its own for the spanwise file."""
    from dataclasses import replace

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


def _variant_b(ctx: SimContext, point: PolarPoint, distance_bref: float) -> list:
    """Trefftz B of one steady point (FR-452): rows, or a named skip."""
    key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant=wake"
    record = ctx.record_of[point.name]
    vtk = classify_outputs(list(record.outputs or ()), package_version=record.package_version).get(
        "vtk"
    )
    wakes = None
    if vtk:
        stem = Path(str(vtk)).name[: -len(".vtk")]
        wakes = ctx.workspace.sim_dir(ctx.sim_id) / f"{stem}_wakes.vtk"
    if wakes is None or not wakes.is_file():
        _skip(
            ctx,
            key,
            point.name,
            "the point wrote no wake export; the plan of a new run "
            "switches the wake on in the VTK export",
        )
        return []
    rho, speed = _point_state(point)
    bref = float(ctx.reference.bref_m or _NA)
    try:
        wake = parse_wake_export(wakes.read_text(encoding="utf-8"))
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the wake export cannot be read: {error}")
        return []
    turn = farfield_axes(point.alpha_deg, point.beta_deg)
    lines = [line @ turn.T for line in wake.lines]
    x_t = max(float(line[0, 0]) for line in lines) + distance_bref * bref
    trace = wake_crossings(lines, wake.values, x_t=x_t)
    if trace.problem is not None:
        _skip(ctx, key, point.name, f"no trace at x = {x_t:.4g} m: {trace.problem}")
        return []
    mirror, half = _symmetry(ctx)
    try:
        raw = trace_forces(trace.y, trace.z, trace.values, rho=rho, v_inf=speed, mirror=mirror)
    except PyflightstreamError as error:
        _skip(ctx, key, point.name, f"the trace cannot be formed: {error}")
        return []
    q = 0.5 * rho * speed * speed
    factor = 0.5 if half else 1.0
    cl_near = _near_field(point)[0]
    k = calibration_scale(
        raw.lift * factor, cl_near=cl_near, q=q, s_ref=float(ctx.reference.sref_m2 or _NA)
    )
    result = raw.scaled(k) if math.isfinite(k) else raw
    calibrated = math.isfinite(k)
    rows = _rows_of(
        ctx,
        point,
        "wake",
        result,
        names=["TOTAL"],
        factor=factor,
        q=q,
        extra={"X_T_M": x_t, "GAMMA_SCALE": k},
        isolated=False,
        blank=() if calibrated else ("CL_T", "CDI_T", "CY_T"),
    )
    if not calibrated:
        _skip(
            ctx,
            f"{key}#scale",
            point.name,
            "the point has no near-field CL to calibrate the "
            "wake values from, so E_T alone is written",
        )
    _spanwise(
        ctx, point, variant="wake", name="TOTAL", result=result, flow=(rho, speed), chords=None
    )
    return rows


def farfield_products(ctx: SimContext) -> None:
    """Write the far-field tables of one simulation (FR-456), or nothing without ``[farfield]``."""
    spec = getattr(ctx.pproc, "farfield", None)
    if spec is None or spec.trefftz is None and spec.ledgers is None:
        return
    rows: list[tuple[object, ...]] = []
    runs: list[str] = []
    variants = list(spec.trefftz.variant) if spec.trefftz is not None else []
    for point in ctx.points:
        record = ctx.record_of[point.name]
        run_type = str(record.recipe or "steady")
        rotor = bool(getattr(ctx.live, "rotors", None)) and run_type != "steady"
        before = len(rows)
        for variant in variants:
            why = applies(f"trefftz:{variant}", run_type, rotor=rotor)
            key = f"{FARFIELD_DIR}/trefftz#point={point.name}#variant={variant}"
            if why:
                _skip(ctx, key, point.name, f"variant {variant} does not apply: {why}")
            elif variant == "sections":
                rows += _variant_a(ctx, point, spec.families, spec.trefftz.stations)
            elif variant == "wake":
                rows += _variant_b(ctx, point, spec.trefftz.distance_bref)
            else:
                _skip(
                    ctx,
                    key,
                    point.name,
                    "variant C reads the far-field plane the plan lays as "
                    "probes, which this build does not lay yet",
                )
        if spec.ledgers is not None:
            _skip(
                ctx,
                f"{FARFIELD_DIR}/ledgers#point={point.name}",
                point.name,
                "the balances read the survey lattice the plan lays as probes, which this "
                "build does not lay yet",
            )
        if len(rows) > before:
            runs += [run for run in ctx.sources[point.name] if run not in runs]
    if not rows:
        return
    path = ctx.target(ctx.out / FARFIELD_DIR / f"{ctx.sim_id}_{ctx.table_name}_trefftz.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_table(path, ("POL", "STEP", *CONTEXT_COLUMNS, *TREFFTZ_COLUMNS), rows)
    ctx.add(
        path,
        {
            "runs": runs,
            "analysis": "trefftz",
            "variants": variants,
            "strip_rule": "extended",
        },
    )
