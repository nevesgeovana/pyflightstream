"""Rotor section products from matching surface and wake snapshots.

Pipeline role: adapt the resolved post context to blade-local numerical
reductions and write their long and strip tables beside the polar products.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.farfield.rotor_sections import (
    anchored_wake_loads,
    complete_induction_wake,
    project_sections,
    wake_velocity,
)
from pyflightstream.post._condition import _recorded_speeds, row_rotor_speeds
from pyflightstream.post._reduction_stage import _last_step
from pyflightstream.post._tables import CONTEXT_COLUMNS, context_row, write_csv_table
from pyflightstream.post.axes import free_stream_in_export_frame
from pyflightstream.post.rotor_section_frames import aligned_blade_sections
from pyflightstream.post.rotor_sections_surface import blade_surface_strips
from pyflightstream.post.section_distributions import distributions_of
from pyflightstream.post.series import stamped_exports
from pyflightstream.results.loads import parse_loads
from pyflightstream.workspace.naming import sweep_file_stem

__all__ = ["rotor_sections_products", "rotor_section_snapshot"]


def rotor_sections_products(ctx, *, output, read_wake, flow, per_m, copies, window, skip):
    """Write the selected rotor's blade-local long and strip tables."""
    spec = ctx.pproc.farfields[0]
    rotor = (getattr(ctx.live, "rotors", None) or {}).get(spec.rotor)
    rows, strips, contexts = [], [], {}
    readers = dict(
        output=output,
        read_wake=read_wake,
        flow=flow,
        per_m=per_m,
        copies=copies,
        window=window,
        skip=skip,
    )
    for point in ctx.points:
        if rotor is None:
            skip(
                ctx,
                f"farfield/rotor_sections#{point.name}",
                point.name,
                f"rotor {spec.rotor!r} is absent on this row; the entry is skipped",
            )
            continue
        contexts[point.name] = _context(ctx, point)
        long, local = _point_products(ctx, point, rotor, **readers)
        rows.extend(long)
        strips.extend(local)
    _write_products(ctx, rows, strips, contexts)


def _context(ctx, point):
    status = getattr(ctx.record_of[point.name], "status", None)
    return {
        **dict(
            zip(
                CONTEXT_COLUMNS,
                context_row(ctx.condition(point), ctx.reference.as_lengths()),
                strict=True,
            )
        ),
        "STATUS": str(getattr(status, "value", status) or "NA"),
    }


def _snapshots(ctx, point, *, output, window):
    spec = ctx.pproc.farfields[0]
    record = ctx.record_of[point.name]
    last = _last_step(record)
    if spec.export_type not in ("avg_window", "export_window"):
        return [(last, output(ctx, point, "vtk"))], None
    span, _ = window(
        ctx, point, int(last) if isinstance(last, (int, float)) and math.isfinite(last) else 0
    )
    folder = ctx.workspace.sim_dir(ctx.sim_id)
    exports = stamped_exports(
        folder, point.name, *(folder / Path(p).parent for p in record.outputs)
    )
    files = exports.get(("", "vtk"), {})
    steps = list(range(int(span[0]), int(span[1]) + 1)) if span else []
    if not steps or any(step not in files for step in steps):
        raise ValueError(
            "rotor sections need a surface and wake snapshot at every window step; "
            "no average is written"
        )
    return [(step, files[step]) for step in steps], span


def _sample(ctx, point, rotor, *, surface, saved, averaging, read_wake, flow, per_m, copies):
    if surface is None or saved is None:
        raise ValueError("rotor sections need the surface VTK and labelled saved simulation")
    if averaging:
        point = replace(
            point, loads=parse_loads(surface.with_suffix(".txt").read_text(encoding="utf-8"))
        )
    units = per_m(ctx, point)
    if units is None:
        raise ValueError("the saved simulation must state its length unit")
    wake, _ = read_wake(ctx, point, surface.with_name(surface.stem + "_wakes.vtk"), units)
    rho, speed, alpha, beta = flow(point)
    record = ctx.record_of[point.name]
    speeds = _recorded_speeds(record.reductions, row_rotor_speeds(record, point.loads_path))
    rpm = speeds.get(ctx.pproc.farfields[0].rotor)
    if rpm is None and len(ctx.live.rotors) == 1:
        rpm = (record.reductions or {}).get("rpm")
    if not rpm:
        raise ValueError("rotor sections need a recorded nonzero rotor speed")
    return rotor_section_snapshot(
        ctx,
        point,
        rotor=rotor,
        wake=wake,
        surface=surface,
        saved=saved,
        units=units,
        rho=rho,
        speed=speed,
        alpha=alpha,
        beta=beta,
        rpm=float(rpm),
        copies=copies(ctx),
    )


def _point_products(ctx, point, rotor, *, output, read_wake, flow, per_m, copies, window, skip):
    spec = ctx.pproc.farfields[0]
    key = f"farfield/rotor_sections#point={point.name}#entry={spec.name}"
    rows, local, samples = [], [], []
    try:
        snapshots, span = _snapshots(ctx, point, output=output, window=window)
    except ValueError as error:
        skip(ctx, key, point.name, str(error))
        return rows, local
    installed = _installed(ctx.record_of[point.name], rotor)
    averaging = span is not None
    for step, surface in snapshots:
        try:
            totals, strips = _sample(
                ctx,
                point,
                rotor,
                surface=surface,
                saved=output(ctx, point, "simulation"),
                averaging=averaging,
                read_wake=read_wake,
                flow=flow,
                per_m=per_m,
                copies=copies,
            )
        except (OSError, ValueError, PyflightstreamError) as error:
            skip(ctx, key, point.name, str(error))
            continue
        if not samples:
            _limitations(installed)
        sample = _columns(totals, spec.rotor)
        samples.append(sample)
        base = dict(
            POL=point.name,
            ENTRY=spec.name,
            STEP=step,
            INDUCTION=spec.induction,
            LOCAL_VALIDATED=not installed,
        )
        if not averaging or spec.export_type == "export_window":
            rows.append({**base, **sample})
        for name, diagnostics in strips.items():
            local.extend(
                {
                    **base,
                    "BLADE": name,
                    **{key: float(value[i]) for key, value in diagnostics.items()},
                }
                for i in range(len(diagnostics["R_M"]))
            )
    if averaging and (not samples or len(samples) != len(snapshots)):
        skip(
            ctx,
            key,
            point.name,
            "rotor section snapshots are incomplete; no average or polar value is written",
        )
    elif samples:
        reduced = _publish_polar(ctx, point, samples, span=span, step=snapshots[-1][0])
        if averaging:
            rows.append(
                dict(
                    POL=point.name,
                    ENTRY=spec.name,
                    STEP="AVERAGE",
                    INDUCTION=spec.induction,
                    LOCAL_VALIDATED=not installed,
                    **reduced,
                )
            )
    return rows, local


def _publish_polar(ctx, point, samples, *, span, step):
    spec = ctx.pproc.farfields[0]
    reduced = (
        {key: float(np.mean([sample[key] for sample in samples])) for key in samples[0]}
        if span
        else samples[-1]
    )
    ctx.farfield_super.setdefault(point.name, {}).update(
        {key: str(value) for key, value in reduced.items()}
    )
    row_span = getattr(ctx, "point_windows", {}).get(point.name)
    if not span:
        ctx.farfield_off_window.append(
            f"{point.name} entry {spec.name}: the instant of step {step}"
        )
    elif row_span and list(span) != list(row_span):
        ctx.farfield_off_window.append(
            f"{point.name} entry {spec.name}: the average over steps {span}"
        )
    return reduced


def _installed(record, rotor):
    return bool(
        set(getattr(record, "inventory", ()) or ())
        - set(rotor.families_blades)
        - set(getattr(rotor, "families_general", ()) or ())
    )


def _limitations(installed):
    warn(
        "rotor sections use the surface force magnitude and are not an independent thrust; "
        "they add the wake-induced direction and local decomposition. CF friction is removed: "
        "local dynamic pressure on surface re-cuts, reference dynamic pressure on section cuts.",
        PyflightstreamWarning,
        stacklevel=3,
    )
    if installed:
        warn(
            "rotor sections LOCAL_VALIDATED=false: this row has surfaces beyond the rotor and hub; "
            "local alpha_i and Cd_i remain unvalidated even when all row wakes are included.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _write_products(ctx, rows, strips, contexts):
    spec = ctx.pproc.farfields[0]
    group = sweep_file_stem(ctx.sim_id, ctx.table_name)
    for suffix, records in (("", rows), ("_strips", strips)):
        if not records:
            continue
        records = [
            {**row, **contexts[str(row["POL"])], "POINT": row["POL"], "POL": ctx.sim_id}
            for row in records
        ]
        path = ctx.target(ctx.out / "farfield" / f"{group}_rotor_sections_{spec.rotor}{suffix}.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = tuple(dict.fromkeys(key for row in records for key in row if key != "STATUS")) + (
            "STATUS",
        )
        write_csv_table(
            path, columns, [tuple(row.get(key, float("nan")) for key in columns) for row in records]
        )
        ctx.add(
            path,
            {
                "analysis": "rotor_sections",
                "entry": spec.name,
                "friction": "CF: surface local pressure; section reference pressure",
                "induction": spec.induction,
                "export_type": spec.export_type,
            },
        )


def rotor_section_snapshot(
    ctx,
    point,
    *,
    rotor,
    wake,
    surface,
    saved,
    units,
    rho,
    speed,
    alpha,
    beta,
    rpm,
    copies,
    repair_w=False,
):
    """Reduce one matching surface and wake snapshot in physical geometry axes."""
    from pyflightstream.farfield import rotor_wake_lines

    spec = ctx.pproc.farfields[0]
    hub = np.array([rotor.x_m, rotor.y_m, rotor.z_m], dtype=float)
    axis = np.asarray(rotor.axis_vector, dtype=float)
    axis /= np.linalg.norm(axis)
    moment = np.array([ctx.reference.xmom_m, ctx.reference.ymom_m, ctx.reference.zmom_m])
    mask = rotor_wake_lines(
        wake.lines,
        hub=hub,
        axis=axis,
        radius=rotor.diameter_m * 0.51,
        reach=rotor.diameter_m * 0.125,
    )
    lines = [line for line, use in zip(wake.lines, mask, strict=True) if use]
    values = wake.values[mask]
    if str(ctx.record_of[point.name].recipe) == "qsteady_rotor":
        values = -values
    thrust_sign = sum(
        np.array([point.loads.surfaces.get(name, {}).get(key, 0.0) for key in ("Cx", "Cy", "Cz")])
        @ axis
        for name in rotor.families_blades
    )
    if thrust_sign == 0:
        raise ValueError("surface winding needs a nonzero measured blade axial load")
    sections, groups, attachments = blade_surface_strips(
        surface,
        saved,
        list(rotor.families_blades),
        lines,
        hub=hub,
        axis=axis,
        moment_point=moment,
        per_m=units,
        rho=rho,
        reference_speed=float(point.loads.reference_velocity_m_s or speed),
        thrust_sign=thrust_sign,
        chord_fraction=spec.chord_fraction,
    )
    sections = _reuse_sections(
        ctx, point, sections, surface=surface, axis=axis, rho=rho, speed=speed, units=units
    )
    selected = np.sort(np.concatenate(list(groups.values())))
    remap = {int(old): new for new, old in enumerate(selected)}
    groups = {name: np.array([remap[int(i)] for i in group]) for name, group in groups.items()}
    lines = [lines[i] for i in selected]
    values, attachments = values[selected], attachments[selected]
    all_lines, all_values, all_attachments = [], [], []
    for k in range(copies):
        angle = 2 * math.pi * k / copies
        all_lines.extend(_turn(line - hub, axis, angle) + hub for line in lines)
        all_values.extend(values)
        all_attachments.extend(_turn(attachments - hub, axis, angle) + hub)
    all_lines, all_values, all_attachments = _induction_wake(
        ctx,
        point,
        wake,
        all_lines,
        all_values,
        attachments=all_attachments,
        rotor_mask=mask,
        repair_w=repair_w,
    )
    wind = free_stream_in_export_frame(alpha, beta) * speed
    omega = 2 * math.pi * rpm / 60
    totals, diagnostics = {}, {}
    for name, blade in sections.items():
        per_copy = []
        for k in range(copies):
            angle = 2 * math.pi * k / copies
            total, strip = _copy_result(
                blade,
                groups.get(name),
                angle=angle,
                k=k,
                lines=lines,
                all_lines=all_lines,
                all_values=all_values,
                all_attachments=all_attachments,
                hub=hub,
                axis=axis,
                moment=moment,
                wind=wind,
                omega=omega,
                rho=rho,
                installed=_installed(ctx.record_of[point.name], rotor),
                repair_w=repair_w,
            )
            per_copy.append(total)
            if k == 0:
                diagnostics[name] = strip
        totals[name] = per_copy[0]
        totals.setdefault("ROTOR", {key: 0.0 for key in per_copy[0]})
        for result in per_copy:
            for key, value in result.items():
                if key != "ETA":
                    totals["ROTOR"][key] += value
    total = totals["ROTOR"]
    power = abs(total["Q"] * 2 * math.pi * rpm / 60)
    total["ETA"] = abs(total["T"]) * float(wind @ axis) / power if power else float("nan")
    return totals, diagnostics


def _induction_wake(ctx, point, wake, lines, values, *, attachments, rotor_mask, repair_w):
    if repair_w or ctx.pproc.farfields[0].induction == "rotor":
        return lines, values, attachments
    other = [line for line, rotor in zip(wake.lines, rotor_mask, strict=True) if not rotor]
    exported_values = wake.values[~rotor_mask]
    if str(ctx.record_of[point.name].recipe) == "qsteady_rotor":
        exported_values = -exported_values
    return complete_induction_wake(
        lines,
        values,
        attachments,
        other,
        exported_values,
        mirror=str(ctx.matrix_row.variables.get("SYMMETRY", "")).upper() == "MIRROR",
    )


def _turn(vectors, axis, angle):
    along = np.asarray(vectors @ axis)[..., None] * axis
    across = vectors - along
    return along + across * math.cos(angle) + np.cross(axis, across) * math.sin(angle)


def _columns(totals, alias):
    out = {}
    for name, values in totals.items():
        for key, value in values.items():
            if key in ("T_WAKE_REPAIRED_N", "Q_WAKE_REPAIRED_NM", "W_ANCHOR"):
                continue
            if key.startswith(("T_NEAR", "Q_NEAR", "T_FRICTION", "Q_FRICTION")):
                if name == "ROTOR":
                    out[f"{key}_{alias}"] = value
            else:
                out[f"{key}_FF_RS_{name}"] = value
    return out


def _reuse_sections(ctx, point, sections, *, surface, axis, rho, speed, units):
    record = ctx.record_of[point.name]
    try:
        layout, _ = distributions_of(record, ctx.pproc)
    except (PyflightstreamError, AttributeError, ValueError):
        layout = []
    stem, marker, step = surface.stem.partition("_iteration=")
    stamp = marker + step if marker else ""
    source = surface.with_name(stem + "_sloads" + stamp + ".txt")
    cp = surface.with_name(stem + "_cp" + stamp + ".txt")
    if "_iteration=" not in surface.stem:
        exported = getattr(ctx, "exports", {}).get(point.name) or (None, None)
        source = Path(exported[0]) if exported[0] is not None else source
    sections, reasons = aligned_blade_sections(
        sections,
        layout,
        source,
        cp,
        axis=axis,
        rho=rho,
        reference_speed=float(point.loads.reference_velocity_m_s or speed),
        per_m=units,
    )
    for name, reason in reasons.items():
        warn(f"rotor sections blade {name}: {reason}", PyflightstreamWarning, stacklevel=2)
    return sections


def _copy_result(
    blade,
    group,
    *,
    angle,
    k,
    lines,
    all_lines,
    all_values,
    all_attachments,
    hub,
    axis,
    moment,
    wind,
    omega,
    rho,
    installed,
    repair_w,
):
    rotated = replace(
        blade,
        radial=_turn(blade.radial, axis, angle),
        points=_turn(blade.points - hub, axis, angle) + hub,
        force=_turn(blade.force, axis, angle),
        friction=_turn(blade.friction, axis, angle),
    )
    sample_radii = rotated.radius
    sample_points = rotated.points
    if group is not None:
        starts = np.array([lines[i][0] for i in group]) - hub
        radii = np.linalg.norm(starts - (starts @ axis)[:, None] * axis, axis=1)
        sample_radii = 0.5 * (radii[:-1] + radii[1:])
        sample_points = np.column_stack(
            [np.interp(sample_radii, rotated.radius, rotated.points[:, j]) for j in range(3)]
        )
    sampled = wake_velocity(
        sample_points, all_lines, np.array(all_values), np.array(all_attachments)
    )
    induced = np.column_stack(
        [np.interp(rotated.radius, sample_radii, sampled[:, j]) for j in range(3)]
    )
    total, strip = project_sections(
        rotated,
        induced,
        axis=axis,
        wind=wind,
        hub=hub,
        moment_point=moment,
        omega=omega,
        rho=rho,
    )
    if group is not None and repair_w:
        anchor_gamma = (
            rotated.circulation if installed and rotated.circulation is not None else strip["GAMMA"]
        )
        t_w, q_w, anchor = anchored_wake_loads(
            rotated,
            anchor_gamma,
            all_lines,
            np.array(all_values),
            group + k * len(lines),
            hub=hub,
            axis=axis,
            wind=wind,
            omega=omega,
            rho=rho,
        )
        total.update(T_WAKE_REPAIRED_N=t_w, Q_WAKE_REPAIRED_NM=q_w, W_ANCHOR=anchor)
    return total, strip
