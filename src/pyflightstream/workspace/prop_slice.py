"""Slice a propeller OBJ or IGES into blade sections and the G17 builder's inputs (PFS-2223).

Pipeline role: the workspace layer's reader and writer around the pure slicer
:mod:`pyflightstream.geometry._propeller_slice`. An OBJ is read as its polygons; an IGES is
imported by the gmsh kernel in a worker process of its own, triangulated finely and every
section point is projected back onto its exact face. The folder written holds the G17
definition ``propeller.toml`` that rebuilds the propeller, one normalized profile per
station under ``sections/``, the table ``table.csv`` and the record ``prop-slice.json``
(docs/propeller.md, "Slicing an existing propeller").
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from pyflightstream._errors import InputArtifactError, InputValueError
from pyflightstream._textio import csv_writer, write_text
from pyflightstream.geometry import Propeller
from pyflightstream.geometry.stages import (
    BladeFrame,
    BladeSurface,
    definition_text,
    profile_text,
    slice_blade,
)
from pyflightstream.workspace._gmsh import closest_on_face, gmsh_module, import_iges, session
from pyflightstream.workspace._gmsh_worker import run_isolated
from pyflightstream.workspace._refine._obj import read_obj

__all__ = ["OBJ_UNITS", "TABLE_COLUMNS", "slice_propeller"]

#: Millimetres per unit of an OBJ, which states no unit of its own.
OBJ_UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
#: The columns of ``table.csv``, in order.
TABLE_COLUMNS = (
    "r_R",
    "c_R",
    "beta_deg",
    "t_c",
    "camber",
    "te_gap_c",
    "skew_deg",
    "rake_x_R",
    "airfoil",
)
_PURPOSE = "slicing a propeller IGES"
#: Element size of the IGES triangulation, as a fraction of the model's diagonal.
_MESH_FRACTION = 0.003
#: Alternating projections onto the nearest exact face and back onto the cutting plane.
_PROJECTIONS = 2
#: A refined section has no step longer than this fraction of the model's diagonal and no
#: turn between neighbouring steps above this many degrees; midpoints are added until so.
_STEP_FRACTION = 1e-3
_TURN_DEG = 3.0
_SUBDIVISIONS = 8
#: A step shorter than this fraction of the diagonal is never split for its turn.
_SHORTEST = 2e-5
#: Nearest cut triangles whose faces a section point is projected onto.
_CANDIDATES = 3


def _refuse(text: str) -> InputArtifactError:
    return InputArtifactError(f"{text}. Nothing was written.", kind="geometry")


def _obj_surface(path: Path, unit: str, frame: BladeFrame) -> BladeSurface:
    mesh = read_obj(path)
    scale = OBJ_UNITS[unit]
    triangles = [
        (polygon[0], polygon[k], polygon[k + 1])
        for polygons in mesh.families.values()
        for polygon in polygons
        for k in range(1, len(polygon) - 1)
    ]
    return BladeSurface(mesh.verts * scale, np.asarray(triangles), frame)


def _iges_slice(
    path: str,
    *,
    blades: int,
    axis: list[float],
    origin: list[float],
    blade_dir: list[float],
    stations: list[float] | None,
) -> dict[str, Any]:
    """Triangulate the IGES, project each cut point onto its face and slice; worker side."""
    frame = BladeFrame(origin, axis, blade_dir)
    with session(_PURPOSE) as gmsh:
        gmsh.model.add("prop-slice")
        tags = import_iges(gmsh, path)
        gmsh.model.occ.synchronize()
        if not tags:
            raise _refuse(f"{path}: no blade found, the IGES holds no face")
        low = np.full(3, np.inf)
        high = -low
        for tag in tags:
            box = gmsh.model.getBoundingBox(2, tag)
            low, high = np.minimum(low, box[:3]), np.maximum(high, box[3:])
        size = float(np.linalg.norm(high - low))
        gmsh.option.setNumber("Mesh.MeshSizeMax", size * _MESH_FRACTION)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size * _MESH_FRACTION / 4)
        gmsh.model.mesh.generate(2)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        index = {int(t): i for i, t in enumerate(node_tags)}
        xyz = np.asarray(coords, float).reshape(-1, 3)
        triangles, owners = [], []
        for tag in tags:
            types, _, nodes = gmsh.model.mesh.getElements(2, tag)
            for kind, chunk in zip(types, nodes, strict=True):
                if int(kind) != 2:
                    continue
                for k in range(0, len(chunk), 3):
                    triangles.append([index[int(n)] for n in chunk[k : k + 3]])
                    owners.append(tag)
        corners, owner = np.asarray(triangles), np.asarray(owners)

        def refine(points, normal, offset):
            above = (xyz @ normal >= offset)[corners]
            crossing = above.any(axis=1) & ~above.all(axis=1)
            tree = cKDTree(xyz[corners[crossing]].mean(axis=1))
            faces = owner[crossing]
            return _onto_section(
                gmsh.model,
                lambda q: faces[tree.query(q, k=_CANDIDATES)[1]],
                points,
                plane=(normal, offset),
                size=size,
            )

        surface = BladeSurface(xyz, corners, frame, refine)
        return slice_blade(surface, blades=blades, stations=stations)


def _project(model, owner, points, normal, offset):
    """Move points alternately onto their nearest face and back onto the plane.

    ``owner(points)`` gives, per point, the faces of the nearest cut triangles; each point
    goes to the closest of its projections onto them.
    """
    p = np.array(points, float)
    candidates = np.asarray(owner(p)).reshape(len(p), -1)
    for _ in range(_PROJECTIONS):
        nearest = np.full(len(p), np.inf)
        moved = p.copy()
        for face in np.unique(candidates):
            chosen = (candidates == face).any(axis=1)
            on = closest_on_face(model, int(face), p[chosen])[0]
            gap = np.linalg.norm(on - p[chosen], axis=1)
            better = gap < nearest[chosen]
            rows = np.flatnonzero(chosen)[better]
            nearest[rows], moved[rows] = gap[better], on[better]
        p = moved - (moved @ normal - offset)[:, None] * normal
    return p


def _onto_section(model, owner, points, *, plane, size):
    """Project a closed section onto the exact faces, adding midpoints where it is coarse.

    A step longer than ``_STEP_FRACTION`` of the diagonal is divided into equal parts no
    longer than that, and one beside a turn above ``_TURN_DEG`` gets its midpoint; the new
    points are projected in turn, so the leading edge is sampled finely whatever the
    triangulation.
    """
    normal, offset = plane
    p = _project(model, owner, points, normal, offset)
    for _ in range(_SUBDIVISIONS):
        following = np.roll(p, -1, axis=0)
        step = following - p
        length = np.linalg.norm(step, axis=1)
        unit = step / np.maximum(length, 1e-300)[:, None]
        cosine = np.clip(np.einsum("ij,ij->i", unit, np.roll(unit, -1, axis=0)), -1, 1)
        turn = np.degrees(np.arccos(cosine))
        parts = np.maximum(np.ceil(length / (_STEP_FRACTION * size)), 1).astype(int)
        bent = ((turn > _TURN_DEG) | (np.roll(turn, 1) > _TURN_DEG)) & (length > _SHORTEST * size)
        parts[bent & (parts == 1)] = 2
        if np.all(parts == 1):
            break
        rows = np.repeat(np.arange(len(p)), parts - 1)
        within = np.concatenate([np.arange(1, n) / n for n in parts if n > 1])
        added = _project(model, owner, p[rows] + within[:, None] * step[rows], normal, offset)
        order = np.r_[np.arange(len(p)), rows + within]
        p = np.vstack((p, added))[np.argsort(order, kind="stable")]
    return p


def _vector(value: Sequence[float] | None, default: tuple[float, ...], name: str) -> list[float]:
    vector = list(default if value is None else value)
    if len(vector) != 3:
        raise InputValueError(f"{name}: expected three numbers")
    return [float(v) for v in vector]


def slice_propeller(
    geometry: str | Path,
    *,
    blades: int,
    out: str | Path,
    axis: Sequence[float] | None = None,
    origin: Sequence[float] | None = None,
    blade_dir: Sequence[float] | None = None,
    stations: Sequence[float] | None = None,
    unit: str = "mm",
) -> dict[str, Any]:
    """Cut one blade of a propeller at radial stations and write its G17 parametrization.

    Parameters
    ----------
    geometry : str or Path
        The propeller, an OBJ (``.obj``) or an IGES (``.igs``, ``.iges``); read only.
    blades : int
        The number of blades; the blades found about the axis must match it.
    out : str or Path
        The folder to write: ``propeller.toml``, ``sections/sNN.dat``, ``table.csv`` and
        ``prop-slice.json``.
    axis : sequence of float, optional
        The thrust direction, the builder's ``frame.thrust_dir``; default ``(-1, 0, 0)``.
    origin : sequence of float, optional
        A point of the shaft in mm, the builder's ``frame.pitch_axis_point_mm``; default 0.
    blade_dir : sequence of float, optional
        The reference blade direction, the builder's ``frame.blade_dir``; default
        ``(0, 0, 1)``. Blade 0 is the blade nearest it, and skew is measured from it.
    stations : sequence of float, optional
        r/R of the sections, at least four, increasing, up to 1; default 21 equal steps from
        the blade root to the tip, and 0.7.
    unit : str, optional
        The length unit of an OBJ: ``mm`` (default), ``cm``, ``m`` or ``in``. An IGES states
        its own unit.

    Returns
    -------
    dict
        The record written to ``prop-slice.json``: the inputs, the measured radius, root,
        rotation and blade count, the files, and the table without the profile points.

    Raises
    ------
    InputArtifactError
        The file is missing, its suffix is not .obj, .igs or .iges, or no blade is found.
    InputValueError
        The blade count is not a positive integer or does not match the blades found, or a
        station or a direction is invalid.
    MissingExtraError
        An IGES is given and the gmsh library cannot load.
    """
    source = Path(geometry)
    if not source.is_file():
        raise _refuse(f"{source}: no such geometry file; name an existing .obj or .igs")
    suffix = source.suffix.lower()
    if suffix not in (".obj", ".igs", ".iges"):
        raise _refuse(f"{source}: unsupported geometry suffix {suffix!r}; give .obj, .igs or .iges")
    if type(blades) is not int or blades < 1:
        raise InputValueError(f"blades: expected a positive integer, got {blades!r}")
    if unit not in OBJ_UNITS:
        raise InputValueError(f"unit: expected one of {sorted(OBJ_UNITS)}, got {unit!r}")
    arguments = {
        "axis": _vector(axis, (-1.0, 0.0, 0.0), "axis"),
        "origin": _vector(origin, (0.0, 0.0, 0.0), "origin"),
        "blade_dir": _vector(blade_dir, (0.0, 0.0, 1.0), "blade_dir"),
        "stations": None if stations is None else [float(s) for s in stations],
    }
    frame = BladeFrame(arguments["origin"], arguments["axis"], arguments["blade_dir"])
    if suffix == ".obj":
        result = slice_blade(
            _obj_surface(source, unit, frame), blades=blades, stations=arguments["stations"]
        )
    else:
        gmsh_module(_PURPOSE)
        result = run_isolated(
            f"{__name__}:_iges_slice",
            {"path": str(source), "blades": blades, **arguments},
            _iges_slice,
        )
    return _write(source, Path(out), frame, result, {"blades": blades, "unit": unit, **arguments})


def _write(source, folder, frame, result, inputs):
    sections = folder / "sections"
    sections.mkdir(parents=True, exist_ok=True)
    names = []
    for i, row in enumerate(result["table"]):
        label = f"s{i:02d}"
        write_text(sections / f"{label}.dat", profile_text(row, label))
        names.append(f"sections/{label}.dat")
        row["airfoil"] = label
    write_text(
        folder / "propeller.toml",
        definition_text(
            result, name=source.stem.upper() or "PROPELLER", frame=frame, profile_files=names
        ),
    )
    Propeller.from_toml(folder / "propeller.toml")
    buffer = io.StringIO()
    writer = csv_writer(buffer)
    writer.writerow(TABLE_COLUMNS)
    for row in result["table"]:
        writer.writerow([row[key] if key == "airfoil" else repr(row[key]) for key in TABLE_COLUMNS])
    write_text(folder / "table.csv", buffer.getvalue())
    record = {
        "geometry": str(source),
        "inputs": inputs,
        "measured": result["measured"],
        "files": {
            "definition": "propeller.toml",
            "table": "table.csv",
            "sections": names,
        },
        "table": [
            {key: value for key, value in row.items() if key != "profile"}
            for row in result["table"]
        ],
    }
    write_text(folder / "prop-slice.json", json.dumps(record, indent=2))
    return record
