"""Counted CSV imports and the window/final partition of conventional probes."""

from __future__ import annotations

import io
from collections.abc import Sequence
from hashlib import sha256
from typing import Any

import numpy as np

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.probes.layouts import emit_probe_import, write_points_csv, write_probe_csv
from pyflightstream.script import Script


def _phased_farfield(
    case, script, shapes, *, records, vertex, native_per_m, analysis_points, windows
):
    """Import window sets once at window start, and append final-only sets later."""
    window_keys = {
        np.round(shape.points_m * native_per_m, 5).tobytes()
        for shape in shapes
        if shape.geometry["export_type"] == "avg_window"
    }
    window, final = [], []
    seen = set()
    spans = [(first, last) for first, last, kind in windows if kind == "farfield_probes"]
    for shape, record in zip(shapes, records, strict=True):
        native = np.round(shape.points_m * native_per_m, 5)
        key = native.tobytes()
        in_window = key in window_keys
        record.update(
            import_phase="window-start" if in_window else "after-march",
            exports=["window", "final"] if in_window else ["final"],
            exported_steps=[list(span) for span in spans] if in_window else [],
            positions_frame="REFERENCE",
        )
        if key in seen:
            continue
        seen.add(key)
        declared_at = _declared_index(analysis_points, native)
        if in_window:
            window.extend(map(tuple, native.tolist()))
            if declared_at is not None:
                del analysis_points[declared_at : declared_at + len(native)]
        elif declared_at is None:
            final.extend(map(tuple, native.tolist()))
        steps = ", ".join(f"{first}-{last}" for first, last in spans) if in_window else "none"
        warn(
            f"case {case.sim_id!r}: the far-field {shape.kind} samples {len(native)} points "
            f"per exported step; "
            f"window exported steps {steps}; final export after the march (FR-1052).",
            PyflightstreamWarning,
            stacklevel=3,
        )
    script.farfield_layout.append({"point": dict(case.point), "shapes": records})
    if window:
        _park_window(script, window, native_per_m)
    if analysis_points is not None:
        analysis_points.extend(final)
    elif final:
        _stage_import(script, [], final, native_per_m)
    return vertex + len(window) + len(final)


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


def _declared_index(points, native):
    """Find a whole reused declaration at the emitted coordinate precision."""
    if not points:
        return None
    for start in range(len(points) - len(native) + 1):
        candidate = np.round([point[:3] for point in points[start : start + len(native)]], 5)
        if np.array_equal(candidate, native):
            return start
    return None


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
