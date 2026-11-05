"""Carry OBJ boundary declarations and their mesh-attached points through repitch."""

import hashlib
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputValueError, NotApplicableWarning, warn
from pyflightstream._fsm import saved_mesh_coordinate_unit
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.workspace._geometry_sidecar import toml_key, toml_value
from pyflightstream.workspace._refine._obj import (
    ObjMesh,
    mesh_unit,
    points_from_file,
    read_sidecar,
)
from pyflightstream.workspace._repitch_grid import incidence
from pyflightstream.workspace._wheel import parse_axis


def _carry(value: Any, point_file: Any) -> Any:
    """Rewrite mesh-attached point paths inside a declaration tree."""
    if isinstance(value, list):
        return [_carry(v, point_file) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, val in value.items():
        if key in {"file", "wake_termination_nodes"} and isinstance(val, str) and val != "auto":
            result[key] = point_file(val, terminations=key == "wake_termination_nodes")
        else:
            result[key] = _carry(val, point_file)
    return result


def _need_rotor(ok: bool, message: str) -> None:
    if not ok:
        raise InputValueError(f"repitch: {message}. No file was written.")


def read_rotor(cfg: dict[str, Any], control: Path, mesh: Path) -> dict[str, Any] | None:
    """Return the rotor table a ``[repitch]`` reference names, in mesh units, or None."""
    if "reference" not in cfg:
        return None
    source = control.parent / cfg["reference"]
    data = tomllib.loads(source.read_text(encoding="utf-8"))
    candidates = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("kind") == "rotor"}
    if "rotor" in cfg:
        _need_rotor(cfg["rotor"] in candidates, f"reference has no rotor {cfg['rotor']!r}")
        rotor = candidates[cfg["rotor"]]
    else:
        _need_rotor(len(candidates) == 1, "reference must have one rotor or set repitch.rotor")
        rotor = next(iter(candidates.values()))
    stated_axis = rotor["axis"]
    rotor["axis"] = parse_axis(
        stated_axis.get("vector_wrt_global", []) if isinstance(stated_axis, dict) else stated_axis
    ).tolist()
    unit = mesh_unit(mesh) if mesh.suffix.lower() == ".obj" else saved_mesh_coordinate_unit(mesh)
    if unit is None:
        warn(
            "repitch: mesh unit is unstated; reference origin is interpreted in metres",
            NotApplicableWarning,
        )
        unit = "METER"
    _need_rotor(
        unit in METRES_PER_UNIT, f"mesh unit {unit!r} has no metre scale; state a known unit"
    )
    for key in ("x_m", "y_m", "z_m"):
        rotor[key] = float(rotor.get(key, 0)) / METRES_PER_UNIT[unit]
    return rotor


@dataclass
class Rewrite:
    """How a verb that changes the node list (collapse-te) rewrites the carried declarations.

    ``edit`` changes the declaration tables before the points are carried; ``synthetic`` holds
    points the verb computed itself, by the name the edited tables give them (unit, points in the
    mesh unit, factor into the file unit); ``merged`` names a point file whose rows are the rows
    of several source files; ``dead`` holds the source edges the verb removed, so that a marking
    still on one is refused; ``counts`` states the face total of the output and its count per
    family, in family order; ``dedupe`` names the termination files whose repeated rows are
    dropped.
    """

    edit: Callable[[dict[str, Any]], None] | None = None
    synthetic: dict[str, tuple[str, Any, float]] = field(default_factory=dict)
    merged: dict[str, list[str]] = field(default_factory=dict)
    dead: set[tuple[int, int]] = field(default_factory=set)
    counts: tuple[int, list[int]] | None = None
    dedupe: set[str] = field(default_factory=set)


def attachments(
    source: Path,
    target: Path,
    mesh: ObjMesh,
    new: Any,
    payload: bytes,
    rewrite: Rewrite | None = None,
) -> dict:
    """Prepare sidecar and point-file bytes in memory, refusing unmatched moving markings.

    ``new`` holds, per source node, that node's position in the output. With a ``rewrite`` the
    declarations are edited first and the counts of the output are stated, not read from ``mesh``.
    """
    from scipy.spatial import cKDTree

    sidecar = read_sidecar(source)
    if sidecar is None:
        return {}
    _, data = sidecar
    rw = rewrite or Rewrite()
    if rw.edit is not None:
        rw.edit(data)
    faces = [f for fs in mesh.families.values() for f in fs]
    pairs = np.array(list(incidence(faces)))
    old_points = np.vstack([mesh.verts, mesh.verts[pairs].mean(axis=1)])
    new_points = np.vstack([new, new[pairs].mean(axis=1)])
    tree = cKDTree(old_points)
    outputs: dict[Path, bytes] = {}
    named: dict[str, str] = {}

    def point_file(value: str, terminations: bool = False) -> str:
        if value in named:
            return named[value]
        file = target.with_name(f"{target.stem}.mark{len(named) + 1}.txt")
        if value in rw.synthetic:
            unit, made, to_file = rw.synthetic[value]
            rows = [",".join(format(float(x), ".17g") for x in p) for p in made * to_file]
            outputs[file] = ("\n".join([unit, *rows]) + "\n").encode("utf-8")
            named[value] = file.name
            return file.name
        loads = [points_from_file(source, source.parent / n) for n in rw.merged.get(value, [value])]
        loaded = loads[0]
        assert loaded is not None
        found = np.vstack([x.points for x in loads if x is not None])
        distance, ids = tree.query(found)
        tolerance = max(mesh.size * 1e-8, 1e-10)
        if np.any(distance > tolerance):
            raise InputValueError(
                f"repitch: marking {value!r} is not on source nodes or edge midpoints; "
                "regenerate its points before repitch. No file was written."
            )
        count = len(mesh.verts)
        if rw.dead and any(i >= count and tuple(pairs[i - count]) in rw.dead for i in ids.tolist()):
            raise InputValueError(
                f"collapse_te: marking {value!r} lies on an edge of the removed strip; "
                "move or remove that marking. No file was written."
            )
        points = new_points[ids] * loaded.to_file
        if terminations and value in rw.dedupe:
            _, first = np.unique(points, axis=0, return_index=True)
            points = points[np.sort(first)]
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
    if rw.counts is None:
        data["boundary_faces"] = [len(fs) for fs in mesh.families.values()]
    else:
        data["mesh_faces"], data["boundary_faces"] = rw.counts
    text = "\n".join(f"{toml_key(k)} = {toml_value(v)}" for k, v in data.items()) + "\n"
    outputs[Path(str(target) + ".boundaries.toml")] = text.encode("utf-8")
    return outputs
