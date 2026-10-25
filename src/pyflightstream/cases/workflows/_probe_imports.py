"""Counted CSV imports and the window/final partition of conventional probes."""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

import numpy as np

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.probes.layouts import emit_probe_import, write_points_csv, write_probe_csv
from pyflightstream.script import Script


@dataclass
class _ProbeSet:
    """One declaration and the records of the exports that read it."""

    id: str
    points: list[tuple[float, ...]]
    kind: str
    exports: set[str] = field(default_factory=lambda: {"final"})
    records: list[dict[str, Any]] = field(default_factory=list)
    parts: dict[tuple[str, int], int] = field(default_factory=dict)


def _shape_key(shape):
    """Keep the existing unique-shape key, without searching concatenated points."""
    return (shape.kind, shape.source, shape.entry, shape.points_m.tobytes())


def _emit_probe_sets(script, sets, native_per_m):
    """Append sets in declaration order and record their positions at append time."""
    window, final = [], []
    for probe_set in sets:
        target = window if "window" in probe_set.exports else final
        phase = "window-start" if target is window else "after-march"
        offset = len(target)
        target.extend(probe_set.points)
        for record in probe_set.records:
            record.update(
                id=probe_set.id,
                offset=offset,
                set_count=len(probe_set.points),
                import_phase=phase,
                exports=["window", "final"] if target is window else ["final"],
            )
    for probe_set in sets:
        for record in probe_set.records:
            record["final_offset"] = record["offset"] + (
                0 if record["import_phase"] == "window-start" else len(window)
            )
    if window:
        _park_window(script, window, native_per_m)
    if final:
        _stage_import(script, [], final, native_per_m)
    return window + final


def _phased_farfield(
    case, script, shapes, *, records, vertex, native_per_m, analysis_points, windows
):
    """Import window sets once at window start, and append final-only sets later."""
    sets = analysis_points if analysis_points is not None else []
    by_id = {probe_set.id: probe_set for probe_set in sets}
    shape_ids = {}
    spans = [(first, last) for first, last, kind in windows if kind == "farfield_probes"]
    for shape, record in zip(shapes, records, strict=True):
        key = _shape_key(shape)
        identity = (
            f"probes[{shape.entry}]"
            if shape.source in {"reused", "declared"}
            else (shape_ids.setdefault(key, f"farfield:{shape.kind}:{len(shape_ids)}"))
        )
        if identity not in by_id:
            native = np.round(shape.points_m * native_per_m, 5)
            by_id[identity] = _ProbeSet(identity, list(map(tuple, native.tolist())), "far-field")
            sets.append(by_id[identity])
        probe_set = by_id[identity]
        if shape.component is not None:
            record["sample_offset"] = probe_set.parts.get(shape.component, 0)
        probe_set.records.append(record)
        if shape.geometry["export_type"] == "avg_window":
            probe_set.exports.add("window")
        record["positions_frame"] = "REFERENCE"
    for probe_set in sets:
        in_window = "window" in probe_set.exports
        for record in probe_set.records:
            record["exported_steps"] = [list(span) for span in spans] if in_window else []
        if not any(record in records for record in probe_set.records):
            continue
        steps = ", ".join(f"{first}-{last}" for first, last in spans) if in_window else "none"
        warn(
            f"case {case.sim_id!r}: the far-field {probe_set.records[-1]['kind']} samples "
            f"{len(probe_set.points)} points "
            f"per exported step; "
            f"window exported steps {steps}; final export after the march (FR-1052).",
            PyflightstreamWarning,
            stacklevel=3,
        )
    script.farfield_layout.append({"point": dict(case.point), "shapes": records})
    if analysis_points is None:
        _emit_probe_sets(script, sets, native_per_m)
    return sum(len(probe_set.points) for probe_set in sets)


def _park_window(script, points, native_per_m):
    """Validate and park the action's analysis commands independently of the march."""
    action = Script(script.version, registry=script.registry)
    if script.simulation_length_unit is not None:
        action.record_opened_length_unit(script.simulation_length_unit)
    action.emit("DELETE_PROBE_POINTS")
    _stage_import(action, [], points, native_per_m)
    script.park_input_file("farfield_window_create.txt", action.render())
    for name, payload in action.pending_input_files.items():
        script.park_input_file(name, payload)


def _stage_import(
    script: Script,
    shapes: Sequence[Any],
    imported: Sequence[tuple[float, ...]],
    native_per_m: float,
) -> None:
    """Park the csv of a steady row's added far-field points and import it (FR-455).

    THE PROBES HOME WRITES THE CSV (PFS-2140.001): the public writer of the
    PROBE_POINTS_IMPORT format is what the plan runs, into the text it parks. A
    lattice added alone is written from the lattice, placed and rounded as
    :func:`farfield_probes` recorded it; a plane, alone or before the lattice,
    from the recorded points.
    """
    staged = io.StringIO()
    added = [shape for shape in shapes if shape.source == "added"]
    if len(added) == 1 and added[0].kind == "lattice" and len(imported) == len(added[0].points_m):
        write_probe_csv(
            added[0].lattice,
            staged,
            axis=added[0].geometry["axis"],
            origin=added[0].geometry["origin_m"],
            scale=native_per_m,
            decimals=5,
        )
    else:
        write_points_csv(np.asarray([point[:3] for point in imported], dtype=float), staged)
    payload = staged.getvalue()
    if any(len(point) == 4 for point in imported):
        lines = payload.splitlines()
        for index, point in enumerate(imported, 1):
            if len(point) == 4:
                lines[index] = lines[index].rsplit(",", 1)[0] + f",{int(point[3])}"
        payload = "\n".join(lines) + "\n"
    path = f"farfield_probes_{sha256(payload.encode()).hexdigest()}.csv"
    script.park_input_file(path, payload)
    emit_probe_import(script, path, units=script.simulation_length_unit or "METER")
