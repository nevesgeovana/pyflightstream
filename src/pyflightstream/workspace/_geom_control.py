"""Measured control-surface sub-steps behind the guarded CAD kernel adapter.

Pipeline role: F0 reads every written piece, F1/F2 sew separate pieces, F3
measures native host clearance, F4 checks the combined slot boundaries, F5/F6
consume trimmed assembly boundaries, and F7 checks the capped tail group.
Distances are in metres. A topology check uses sewing at 0.01 mm.
"""

from __future__ import annotations

import time

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputValueError
from pyflightstream.geometry.stages import check_entry

__all__ = ["check_stage"]

# Stage F closure tolerance; each operation records this value with its inputs.
_SEW_M = 1e-5


def _maximum(name, measured, limit=0, *, unit="count", where=None):
    return check_entry(
        name,
        "passed" if measured <= limit else "failed",
        measured,
        limit,
        unit=unit,
        where=where,
        note="BUG: output violates the sub-step check" if measured > limit else "",
    )


def _faces_read(kernel, inputs):
    checks, files = [], {}
    for name, piece in inputs["pieces"].items():
        path = piece["path"]
        read = len(kernel.inspect_file(path, None).areas)
        checks.append(
            _maximum("control.faces_read", abs(read - piece["written"]), where={"piece": name})
        )
        files[name] = {
            "path": path,
            "sha256": file_sha256(path),
            "written": piece["written"],
            "read": read,
        }
    if not checks:
        raise InputValueError("F0.pieces: empty; supply at least one written control piece")
    return checks, {
        "inputs": files,
        **(
            {"applied_controls": inputs["applied_controls"]} if "applied_controls" in inputs else {}
        ),
    }


def _clearance(kernel, inputs):
    distances = {}
    for name, faces in inputs["controls"].items():
        for host, host_faces in inputs["hosts"].items():
            distances[f"{name}/{host}"] = kernel.minimum_distance(faces, host_faces)
    if not distances:
        raise InputValueError("F3: empty face sets; supply controls and their hosts")
    # check_entry supports inclusive bounds. Count contact pairs to express
    # the required strict distance > 0 without inventing a clearance floor.
    checks = [_maximum("control.host_contact", sum(d <= 0 for d in distances.values()))]
    return checks, {
        "distances_m": distances,
        "distance_threshold": "> 0 m",
        "inputs": {"controls": list(inputs["controls"]), "hosts": list(inputs["hosts"])},
    }


def _on_segments(points, segments):
    """Whether every inspected boundary point lies on the named straight rim."""
    nearest = np.full(len(points), np.inf)
    for start, end in segments:
        a, b = np.asarray(start, float), np.asarray(end, float)
        delta = b - a
        length2 = float(delta @ delta)
        if length2 == 0:
            continue
        fraction = np.clip((points - a) @ delta / length2, 0, 1)
        nearest = np.minimum(
            nearest, np.linalg.norm(points - a - fraction[:, None] * delta, axis=1)
        )
    return bool(np.all(nearest <= _SEW_M))


def _topology(kernel, inputs):
    path = inputs["path"]
    topology = kernel.inspect_file(path, _SEW_M)
    if not topology.areas:
        raise InputValueError("control geometry: no faces read")
    free = [points for points, owners in topology.edges if len(owners) == 1]
    symmetry = inputs.get("symmetry_axis")
    if symmetry is not None:
        if symmetry not in (0, 1, 2):
            raise InputValueError("symmetry_axis: expected 0, 1 or 2")
        free = [p for p in free if not np.all(np.abs(p[:, symmetry]) <= _SEW_M)]
    slots = inputs.get("slots", {})
    unnamed = sum(
        not any(name and _on_segments(p, rim) for name, rim in slots.items()) for p in free
    )
    outputs = {
        "free_edges": len(free),
        "unnamed_free_edges": unnamed,
        "triple_edges": sum(len(owners) > 2 for _, owners in topology.edges),
        "sew_tolerance_m": _SEW_M,
        "inputs": {"geometry": {"path": path, "sha256": file_sha256(path)}, "slots": slots},
    }
    return outputs


def _sewn(kernel, stage, inputs):
    outputs = _topology(kernel, inputs)
    free = outputs["free_edges"]
    checks = [_maximum("control.triple_edges", outputs["triple_edges"])]
    if stage in ("F4", "F5", "F6"):
        checks.append(_maximum("control.free_delta", abs(free - inputs["previous_free"])))
    if stage not in ("F5", "F6"):
        checks.append(_maximum("control.free_edges", outputs["unnamed_free_edges"]))
    if stage in ("F5", "F6"):
        measured = inputs["junction_lengths_m"]
        reference = inputs["clean_junction_lengths_m"]
        if not reference or set(measured) != set(reference):
            raise InputValueError(
                f"{stage}.junctions: supply the same nonempty named pairs as the clean reference"
            )
        for pair, expected in reference.items():
            checks.append(
                _maximum(
                    "control.junction_length",
                    abs(measured[pair] - expected),
                    unit="m",
                    where={"pair": pair},
                )
            )
        outputs["junction_lengths_m"] = measured
        outputs["inputs"]["clean_junction_lengths_m"] = reference
    return checks, outputs


def check_stage(kernel, stage, inputs):
    """Measure one control sub-step using a caller-owned kernel.

    Parameters
    ----------
    kernel : CadKernel
        Open guarded adapter; face handles belong to this instance.
    stage : str
        F0 through F7.
    inputs : dict
        F0 takes pieces with path and written count. F3 takes named controls
        and hosts as face sets. Other steps take a path, optional named slot
        segments and symmetry_axis. F4/F5/F6 also take previous_free; F5/F6
        take junction_lengths_m and clean_junction_lengths_m by pair.

    Returns
    -------
    dict
        Checks, measured outputs, input hashes and elapsed seconds.

    Raises
    ------
    InputValueError
        If the stage or a required face set or reference is invalid.
    """
    clock = time.perf_counter()
    if "batch" in inputs:
        checks, outputs = [], {"inputs": {}}
        for name, item in inputs["batch"].items():
            result = check_stage(kernel, stage, item)
            checks.extend(
                {**c, "where": {"piece": name, **(c.get("where") or {})}} for c in result["checks"]
            )
            outputs[name] = result["outputs"]
            outputs["inputs"][name] = result["outputs"]["inputs"]
        if not checks:
            raise InputValueError(f"{stage}.batch: no pieces supplied")
        return {"checks": checks, "outputs": outputs, "wall_s": time.perf_counter() - clock}
    if stage == "F0":
        checks, outputs = _faces_read(kernel, inputs)
    elif stage == "F3":
        checks, outputs = _clearance(kernel, inputs)
    elif stage in ("F1", "F2", "F4", "F5", "F6", "F7"):
        checks, outputs = _sewn(kernel, stage, inputs)
    else:
        raise InputValueError(f"control stage {stage!r}: expected F0 through F7")
    return {"checks": checks, "outputs": outputs, "wall_s": time.perf_counter() - clock}
