"""The half model of a full model cut at its symmetry plane (requirement C8).

Pipeline role: the kernel body of ``split_symmetry``. Every face that crosses the plane is cut
on it by the kernel's own boolean, one face at a time so faces that meet elsewhere are not
imprinted on each other; the pieces on the positive side are kept with the name of the face
they came from, and the cut edges are left open on the plane. Surfaces only: no solid is built.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputValueError

from ._cad import CadKernel, Face, NamedFaces, Point

__all__ = ["split"]

#: A bounding box, ``(minimum, maximum)``.
Box = tuple[Point, Point]

_AXES = {"x": 0, "y": 1, "z": 2}
#: Relative difference of the areas either side of the plane above which a component is warned
#: as not symmetric.
_SYMMETRY_LIMIT = 1e-6
#: Distance to the plane, as a fraction of the model's extent (at least 1 m), within which a
#: point of an edge lies on it.
_ON_PLANE = 1e-9
#: Points sampled along an edge to place it against the plane.
_EDGE_SAMPLES = 17


def _plane_face(kernel: CadKernel, axis: int, low: Sequence[float], high: Sequence[float]) -> Face:
    """Add a rectangle in the plane that covers the box ``low``, ``high`` with a margin."""
    others = [k for k in range(3) if k != axis]
    margin = max(high[k] - low[k] for k in range(3)) + 1.0
    lo = [low[k] - margin for k in others]
    hi = [high[k] + margin for k in others]
    corners = []
    for a, b in ((lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])):
        point = [0.0, 0.0, 0.0]
        point[others[0]], point[others[1]] = a, b
        corners.append((point[0], point[1], point[2]))
    return kernel.add_planar_face(corners)


def _cut(kernel: CadKernel, face: Face, axis: int) -> tuple[Face, ...]:
    """Cut ``face`` on the plane and return its pieces; the plane's own pieces are removed."""
    low, high = kernel.bbox(face)
    result = kernel.fragment([face], [_plane_face(kernel, axis, low, high)])
    pieces = result.from_a[0]
    kept = set(pieces)
    plane = [p for row in result.from_b for p in row if p not in kept]
    if plane:
        kernel.remove(plane)
    return pieces


def _span(kernel: CadKernel, face: Face, axis: int) -> tuple[float, float]:
    """Return the lowest and highest coordinate along ``axis`` of the trimmed boundary of ``face``.

    The boundary is exact where a bounding box is not: the kernel takes a box from the untrimmed
    surface, so a trimmed face that only touches the plane can have a box across it.
    """
    values = [
        kernel.edge_values(edge, np.linspace(*kernel.edge_bounds(edge), _EDGE_SAMPLES).tolist())[
            :, axis
        ]
        for edge in kernel.boundary(face)
    ]
    if not values:
        low, high = kernel.bbox(face)
        return low[axis], high[axis]
    joined = np.concatenate(values)
    return float(joined.min()), float(joined.max())


def _cut_length(kernel: CadKernel, faces: Sequence[Face], axis: int, tolerance: float) -> float:
    """Return the length of the edges of ``faces`` that lie on the plane."""
    seen: set[int] = set()
    total = 0.0
    for face in faces:
        for edge in kernel.boundary(face):
            if abs(edge) in seen:
                continue
            first, last = kernel.edge_bounds(edge)
            points = kernel.edge_values(edge, np.linspace(first, last, _EDGE_SAMPLES).tolist())
            if float(np.max(np.abs(points[:, axis]))) <= tolerance:
                seen.add(abs(edge))
                total += kernel.edge_length(edge)
    return total


def _refuse(message: str) -> InputValueError:
    return InputValueError(f"{message}; nothing was written")


def _row() -> dict[str, Any]:
    return {"faces_before": 0, "faces_after": 0, "cut": 0, "area_kept": 0.0, "area_removed": 0.0}


class _Plane:
    """One symmetry plane through the origin, with the tolerances of one model."""

    def __init__(self, kernel: CadKernel, plane: str, boxes: Sequence[Box]) -> None:
        self.kernel, self.name, self.axis = kernel, plane, _AXES[plane]
        extent = max((abs(c) for box in boxes for corner in box for c in corner), default=0.0)
        self.tolerance = _ON_PLANE * max(extent, 1.0)

    def offered(self, box: Box) -> bool:
        """Return True when the bounding box reaches past the plane on both sides."""
        return box[0][self.axis] < 0.0 and box[1][self.axis] > 0.0

    def crosses(self, face: Face) -> bool:
        """Return True when the trimmed boundary of ``face`` has points on both sides."""
        low, high = _span(self.kernel, face, self.axis)
        return low < -self.tolerance and high > self.tolerance

    def pieces(self, face: Face, box: Box, name: str) -> tuple[Face, ...]:
        """Return the pieces of ``face`` cut on the plane; a face that crosses uncut is refused."""
        pieces = _cut(self.kernel, face, self.axis) if self.offered(box) else (face,)
        if len(pieces) == 1 and self.offered(box) and self.crosses(face):
            raise _refuse(
                f"a face of component {name!r} crosses the plane {self.name} = 0 and the "
                "kernel did not cut it there"
            )
        return pieces

    def kept(self, piece: Face) -> bool:
        """Return True when ``piece`` lies on the positive side or in the plane."""
        return _span(self.kernel, piece, self.axis)[0] >= -self.tolerance


def _check_selection(
    cut: _Plane, source: NamedFaces, boxes: Sequence[Box], component: str | None, iges: str
) -> None:
    """Refuse an unknown component, a named one off the plane, and one left whole across it."""
    if component is None:
        return
    names = sorted(set(source.names))
    if component not in names:
        raise _refuse(
            f"component {component!r}: not in {iges}; the components are {', '.join(names)}"
        )
    crossing = sorted(
        {
            n
            for n, f, b in zip(source.names, source.faces, boxes, strict=True)
            if cut.offered(b) and cut.crosses(f)
        }
    )
    if component not in crossing:
        raise _refuse(f"component {component!r} does not cross the plane {cut.name} = 0")
    whole = [n for n in crossing if n != component]
    if whole:
        raise _refuse(
            f"component {whole[0]!r} crosses the plane {cut.name} = 0 and would be written "
            "whole in the half model; cut it too (no component) or remove it first"
        )


def _place(
    cut: _Plane, source: NamedFaces, boxes: Sequence[Box], component: str | None
) -> tuple[dict[str, dict[str, Any]], dict[str, list[Face]], list[Face]]:
    """Cut the selected faces and sort every piece into kept (by name) and removed."""
    kernel = cut.kernel
    rows: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[Face]] = {}
    removed: list[Face] = []
    for face, name, box in zip(source.faces, source.names, boxes, strict=True):
        row = rows.setdefault(name, _row())
        row["faces_before"] += 1
        kept = groups.setdefault(name, [])
        selected = component is None or name == component
        pieces = cut.pieces(face, box, name) if selected else (face,)
        row["cut"] += int(len(pieces) > 1)
        for piece in pieces:
            if not selected or cut.kept(piece):
                kept.append(piece)
                row["area_kept"] += kernel.area(piece)
            else:
                removed.append(piece)
                row["area_removed"] += kernel.area(piece)
    return rows, groups, removed


def _warnings(cut: _Plane, rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Name each cut component whose two sides differ in area past the symmetry limit."""
    out = []
    for name, row in rows.items():
        kept, removed = row["area_kept"], row["area_removed"]
        if row["cut"] == 0 and removed == 0.0:
            continue
        if abs(kept - removed) > _SYMMETRY_LIMIT * (kept + removed):
            out.append(
                f"component {name!r} is not symmetric about {cut.name} = 0: {kept:.9g} m2 kept "
                f"and {removed:.9g} m2 removed"
            )
    return out


def split(
    kernel: CadKernel, iges: str, out: str, plane: str, component: str | None
) -> dict[str, Any]:
    """Cut the model of ``iges`` at the plane ``plane`` = 0 and write the positive half to ``out``.

    Parameters
    ----------
    kernel : CadKernel
        Open guarded adapter.
    iges : str
        The full model.
    out : str
        The half model to write.
    plane : str
        ``"x"``, ``"y"`` or ``"z"``.
    component : str or None
        The one component to cut; the others are written whole. None cuts every component.

    Returns
    -------
    dict
        Face counts, the cut length and the areas, per component and in total, in metres.

    Raises
    ------
    InputValueError
        If the component is unknown, a component left whole crosses the plane, the named
        component does not cross it, a face is not cut on it, or nothing of the model lies
        on the negative side.
    """
    source = kernel.import_iges(iges)
    boxes = [kernel.bbox(face) for face in source.faces]
    cut = _Plane(kernel, plane, boxes)
    _check_selection(cut, source, boxes, component, iges)
    rows, groups, removed = _place(cut, source, boxes, component)
    if not removed:
        raise _refuse(
            f"plane {plane} = 0: nothing of the model lies on the negative side, so {iges} is "
            "not a full model about this plane"
        )
    for name, row in rows.items():
        row["faces_after"] = len(groups[name])
        row["cut_length"] = _cut_length(kernel, groups[name], cut.axis, cut.tolerance)
    kernel.remove(removed)
    unit = source.unit if source.unit in ("m", "mm") else "m"
    kernel.export_iges({n: f for n, f in groups.items() if f}, out, unit=unit)
    return {
        "status": "passed",
        "plane": plane,
        "kept_side": "+",
        "component": component,
        "path": str(Path(out)),
        "source_sha256": file_sha256(iges),
        "faces": {
            "before": len(source.faces),
            "after": sum(len(f) for f in groups.values()),
            "cut": sum(row["cut"] for row in rows.values()),
            "removed": len(removed),
        },
        "cut_length": sum(row["cut_length"] for row in rows.values()),
        "free_edges": "the cut edges are left open on the plane, as the symmetry boundary",
        "components": rows,
        "warnings": _warnings(cut, rows),
    }
