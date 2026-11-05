"""Carry OBJ boundary declarations and their mesh-attached points through repitch."""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._geometry_sidecar import toml_value
from pyflightstream.workspace._refine._obj import ObjMesh, points_from_file, read_sidecar
from pyflightstream.workspace._repitch_grid import incidence


def _carry(value: Any, point_file: Any) -> Any:
    """Rewrite mesh-attached point paths inside a declaration tree."""
    if isinstance(value, list):
        return [_carry(v, point_file) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, val in value.items():
        if key in {"file", "wake_termination_nodes"} and isinstance(val, str) and val != "auto":
            result[key] = point_file(val)
        else:
            result[key] = _carry(val, point_file)
    return result


def attachments(source: Path, target: Path, mesh: ObjMesh, new: Any, payload: bytes) -> dict:
    """Prepare sidecar and point-file bytes in memory, refusing unmatched moving markings."""
    from scipy.spatial import cKDTree

    sidecar = read_sidecar(source)
    if sidecar is None:
        return {}
    _, data = sidecar
    faces = [f for fs in mesh.families.values() for f in fs]
    pairs = np.array(list(incidence(faces)))
    old_points = np.vstack([mesh.verts, mesh.verts[pairs].mean(axis=1)])
    new_points = np.vstack([new, new[pairs].mean(axis=1)])
    tree = cKDTree(old_points)
    outputs: dict[Path, bytes] = {}
    named: dict[str, str] = {}

    def point_file(value: str) -> str:
        if value in named:
            return named[value]
        loaded = points_from_file(source, source.parent / value)
        assert loaded is not None
        distance, ids = tree.query(loaded.points)
        tolerance = max(mesh.size * 1e-8, 1e-10)
        if np.any(distance > tolerance):
            raise InputValueError(
                f"repitch: marking {value!r} is not on source nodes or edge midpoints; "
                "regenerate its points before repitch. No file was written."
            )
        file = target.with_name(f"{target.stem}.mark{len(named) + 1}.txt")
        points = new_points[ids] * loaded.to_file
        lines = [loaded.unit, *[",".join(format(float(x), ".17g") for x in p) for p in points]]
        outputs[file] = ("\n".join(lines) + "\n").encode("utf-8")
        named[value] = file.name
        return file.name

    for key in ("trailing_edges", "base_regions"):
        if key in data:
            data[key] = _carry(data[key], point_file)
    data["file"] = target.name
    data["mesh_sha256"] = hashlib.sha256(payload).hexdigest()
    data["mesh_faces"] = len(faces)
    data["boundary_faces"] = {n: len(fs) for n, fs in mesh.families.items()}
    text = "\n".join(f"{toml_value(k)} = {toml_value(v)}" for k, v in data.items()) + "\n"
    outputs[Path(str(target) + ".boundaries.toml")] = text.encode("utf-8")
    return outputs
