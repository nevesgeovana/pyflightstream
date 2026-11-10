"""Exact iso cuts of a named imported lifting skin for the control edit API.

Pipeline role: preserve the source native trims, add closure faces from its
polynomial definition, move the controls and measure the written result.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputValueError
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.geometry.stages import Patch, controls

from ._geom_control import check_stage
from ._geom_control_build import _faces
from ._geom_gate import _Surface
from ._iges_names import read_iges_names
from ._iges_write import read_iges

__all__ = ["edit"]


def _patch(surface, scale):
    if not np.allclose(surface.weights, surface.weights.flat[0], rtol=0, atol=0):
        raise InputValueError("control skin: rational bases need a polynomial definition")
    knots = [np.unique(axis, return_counts=True) for axis in surface.knots]
    if any(axis[0][0] != 0 or axis[0][-1] != 1 for axis in knots):
        raise InputValueError("control skin: expected normalized u and v domains")
    return Patch(
        family="skin",
        controls=surface.points.transpose(1, 0, 2) * scale,
        knots_u=tuple(knots[0][0]),
        knots_v=tuple(knots[1][0]),
        multiplicities_u=tuple(knots[0][1]),
        multiplicities_v=tuple(knots[1][1]),
        degree_u=surface.degrees[0],
        degree_v=surface.degrees[1],
    )


def _definitions(path, component):
    names = read_iges_names(path)
    entities = {item["id"]: item for item in read_iges(path)["entities"]}
    scale = float(METRES_PER_UNIT[names.unit])
    patches = {}
    for index, (name, identifier) in enumerate(zip(names.faces, names.entities, strict=True)):
        if name != component:
            continue
        entity = entities[identifier]
        if entity["type"] == 144:
            entity = entities[int(entity["parameters"][1])]
        if entity["type"] == 128:
            patches[index] = _patch(_Surface(entity["parameters"]), scale)
    if not patches:
        raise InputValueError(f"component {component!r}: no polynomial B-spline skin found")
    skin = max(patches.values(), key=lambda p: p.controls.shape[0])
    return patches, skin


def _same(a, b):
    return a.controls.shape == b.controls.shape and np.allclose(
        a.controls, b.controls, rtol=0, atol=1e-12
    )


def _split(kernel, faces, direction, values):
    axis = 0 if direction == "u" else 1
    for value in sorted(set(values)):
        result = []
        for face in faces:
            low, high = kernel.uv_bounds(face)
            if low[axis] + 1e-12 < value < high[axis] - 1e-12:
                result.extend(kernel.split_imported_face_uv(face, direction, value))
            else:
                result.append(face)
        faces = result
    return faces


def _selected(kernel, faces, limits, *, moving=False, te=False):
    low, high, a, b, gap = limits
    if moving:
        a, b = a + gap, b - gap
    selected, other = [], []
    for face in faces:
        uv0, uv1 = kernel.uv_bounds(face)
        u, v = (np.array(uv0) + uv1) / 2
        target = selected if a < v < b and (te or u < low or u > high) else other
        target.append(face)
    return selected, other


def edit(kernel, iges, component, entries, out):
    """Apply entries to a normalized named skin and retain all other source faces.

    Parameters
    ----------
    kernel : CadKernel
        Open guarded adapter.
    iges : str
        Source IGES with polynomial skin, trailing-edge face and existing caps.
    component : str
        Name of the lifting component.
    entries : list
        Public control tables, with disjoint eta intervals.
    out : str
        Destination IGES path.

    Returns
    -------
    dict
        Measured closure checks, face counts and source hash.

    Raises
    ------
    InputValueError
        If the source or entries cannot be represented by exact iso cuts.
    """
    if not entries:
        raise InputValueError("control entries: at least one table is required")
    if not Path(iges).is_file():
        raise InputValueError(f"control source: file does not exist: {iges}")
    patches, skin = _definitions(iges, component)
    prepared = [controls.imported(skin, dict(entry)) for entry in entries]
    ordered = sorted(p["limits"][2:4] for p in prepared)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:], strict=False)):
        raise InputValueError("control.eta: overlapping intervals")
    source = kernel.import_iges(iges)
    skin_faces, te_faces, groups = [], [], {}
    te = prepared[0]["main"].bases["trailing_edge"]
    for index, (face, name) in enumerate(zip(source.faces, source.names, strict=True)):
        patch = patches.get(index)
        if patch is not None and _same(patch, skin):
            skin_faces.append(face)
        elif patch is not None and _same(patch, te):
            te_faces.append(face)
        else:
            groups.setdefault(name, []).append(face)
    cuts = [
        value
        for p in prepared
        for value in (
            p["limits"][2],
            p["limits"][3],
            p["limits"][2] + p["limits"][4],
            p["limits"][3] - p["limits"][4],
        )
    ]
    skin_faces = _split(
        kernel, skin_faces, "u", [v for p in prepared for v in p.get("cuts_u", p["limits"][:2])]
    )
    skin_faces = _split(kernel, skin_faces, "v", cuts)
    te_faces = _split(kernel, te_faces, "v", cuts)
    main = groups.setdefault(component, [])
    for p in prepared:
        removed, skin_faces = _selected(kernel, skin_faces, p["limits"])
        removed_te, te_faces = _selected(kernel, te_faces, p["limits"], te=True)
        moving, _ = _selected(kernel, removed, p.get("moving_limits", p["limits"]), moving=True)
        moving_te, _ = _selected(kernel, removed_te, p["limits"], moving=True, te=True)
        main.extend(
            _faces(
                kernel,
                p["main"],
                [
                    t
                    for t in p["main"].pieces["main"]
                    if (
                        t.role not in ("skin", "trailing_edge")
                        if p.get("fowler")
                        else t.base in ("hinge", "inboard", "outboard")
                    )
                ],
            )
        )
        closures = (
            []
            if p.get("fowler")
            else _faces(
                kernel,
                p["moving"],
                [
                    t
                    for t in p["moving"].pieces["control"]
                    if t.base in ("hinge", "inboard", "outboard")
                ],
            )
        )
        for label, matrix in p["motions"].items():
            copy = kernel.copy([*moving, *moving_te, *closures])
            kernel.transform(copy, matrix)
            groups[f"{component}/{label}"] = list(copy)
            if p.get("fowler"):
                trims = [
                    t for t in p["moving"].pieces[label] if t.role not in ("skin", "trailing_edge")
                ]
                groups[f"{component}/{label}"].extend(_faces(kernel, p["moving"], trims))
    main.extend([*skin_faces, *te_faces])
    kernel.export_iges(groups, out)
    result = check_stage(kernel, "F4", {"path": out, "previous_free": 0, "symmetry_axis": 1})
    result["checks"].extend(c for p in prepared for c in p["main"].checks)
    return {
        "status": "passed" if all(c["status"] == "passed" for c in result["checks"]) else "failed",
        **result,
        "source_sha256": file_sha256(iges),
        "pieces": {name: len(faces) for name, faces in groups.items()},
        "path": out,
        "warnings": [warning for p in prepared for warning in p["warnings"]],
    }
