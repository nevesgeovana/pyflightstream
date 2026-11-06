"""The gmsh half of ``geometry iges-grid``: join the faces, set the laws, mesh, read the elements.

The faces of every component are healed and fragmented together, so an edge two faces share
becomes one curve and its nodes are shared. Four-sided patches of a structured component get
transfinite curves with the laws of the grid control file and are recombined into quads; every
other patch is meshed quad-dominant (Frontal-Delaunay for quads, Blossom recombination) at its
component's size. The opposite sides of a four-sided patch must take one count, so the curves
that must agree are grouped and each group takes the count of the first component that asks;
every other request in the group is recorded as overridden.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.workspace._gmsh import NamedModel
from pyflightstream.workspace._iges_grid_config import (
    DEFAULT_RATIO,
    ComponentGrid,
    Direction,
    GridConfig,
)

__all__ = ["Meshed", "mesh_model"]

#: gmsh's mesh element type numbers of the linear triangle and quadrangle.
_TRIANGLE, _QUAD = 2, 3
#: gmsh 2D algorithm 8: Frontal-Delaunay for quads; recombination algorithm 1: Blossom.
_FRONTAL_QUADS, _BLOSSOM = 8, 1


@dataclass
class Meshed:
    """The mesh of every component: nodes, faces per component and what the run recorded."""

    nodes: NDArray[np.float64]
    faces: dict[str, list[list[int]]]
    jacobian: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    #: The mesh edges on true boundaries of the body, as sorted node index pairs.
    boundary: set[tuple[int, int]] = field(default_factory=set)
    record: dict[str, Any] = field(default_factory=dict)


class _Groups:
    """Union-find over curve tags: the curves that must take one count."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, a: int) -> int:
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


@dataclass
class _Side:
    """One pair of opposite curves of a four-sided patch, as a component asks for it."""

    component: str
    curves: tuple[int, int]
    direction: str
    count: int
    law: str
    ratio: float | None
    axis: NDArray[np.float64]


def _heal(gmsh: Any, model: NamedModel, tolerance: float) -> str:
    tags = [(2, t) for t in model.faces]
    out = gmsh.model.occ.healShapes(tags, tolerance, True, True, False, True, False)
    gmsh.model.occ.synchronize()
    healed = sorted(t for d, t in out if d == 2)
    if healed == sorted(model.faces):
        return "healed (degenerate and small edges fixed, faces sewn)"
    return "healing changed the faces and was not kept"


def _fragment(
    gmsh: Any, model: NamedModel, order: list[str], tolerance: float, warnings: list[str]
) -> tuple[dict[str, list[int]], dict[str, Any]]:
    """Fragment every face against every other; return the faces of each component after."""
    by_name = model.components()
    inputs = [(name, t) for name in order for t in by_name[name]]
    gmsh.option.setNumber("Geometry.ToleranceBoolean", tolerance)
    _, mapping = gmsh.model.occ.fragment([(2, t) for _, t in inputs], [])
    gmsh.model.occ.synchronize()
    owner: dict[int, str] = {}
    overlaps: dict[tuple[str, str], int] = {}
    for (name, _), pieces in zip(inputs, mapping, strict=True):
        for dim, tag in pieces:
            if dim != 2:
                continue
            if tag in owner and owner[tag] != name:
                key = (owner[tag], name)
                overlaps[key] = overlaps.get(key, 0) + 1
                continue
            owner.setdefault(tag, name)
    for (first, second), count in overlaps.items():
        warnings.append(
            f"{count} face(s) of {second} lie on faces of {first} and were given to {first}"
        )
    faces: dict[str, list[int]] = {name: [] for name in order}
    for tag, name in owner.items():
        faces[name].append(tag)
    for name in faces:
        faces[name].sort()
    crossings: dict[tuple[str, ...], int] = {}
    for _, curve in gmsh.model.getEntities(1):
        up, _ = gmsh.model.getAdjacencies(1, curve)
        if len(up) > 2:
            names = tuple(sorted({owner.get(int(t), "?") for t in up}))
            crossings[names] = crossings.get(names, 0) + 1
    for names, count in sorted(crossings.items()):
        warnings.append(
            f"more than two faces meet along {count} curve(s) of {' and '.join(names)}: a face "
            "crosses another without a trimmed junction, and both parts are kept (the "
            "intersection of untrimmed parts is outside this command)"
        )
    record = {
        "faces_before": len(inputs),
        "faces_after": len(owner),
        "split": sum(1 for pieces in mapping if sum(1 for d, _ in pieces if d == 2) > 1),
        "crossings": [{"components": list(k), "curves": v} for k, v in sorted(crossings.items())],
    }
    return faces, record


def _point(gmsh: Any, tag: int) -> NDArray[np.float64]:
    return np.asarray(gmsh.model.getValue(0, tag, []), dtype=float)


def _ends(gmsh: Any, curve: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    points = [abs(t) for _, t in gmsh.model.getBoundary([(1, curve)], oriented=True)]
    if len(points) < 2:
        p = _point(gmsh, points[0]) if points else np.zeros(3)
        return p, p
    return _point(gmsh, points[0]), _point(gmsh, points[-1])


def _span_axis(gmsh: Any, faces: list[int], grid: ComponentGrid) -> NDArray[np.float64]:
    if grid.span_axis is not None:
        return np.asarray(grid.span_axis, dtype=float)
    # x is the streamwise axis, along which no lifting surface spans: the span axis is y or z,
    # whichever the component extends along more (y for a wing or a pylon, z for a fin).
    boxes = np.array([gmsh.model.getBoundingBox(2, t) for t in faces], dtype=float)
    extent = boxes[:, 3:].max(axis=0) - boxes[:, :3].min(axis=0)
    axis = np.zeros(3)
    axis[1 if extent[1] >= extent[2] else 2] = 1.0
    return axis


def _four_sides(gmsh: Any, face: int) -> list[int] | None:
    loop = [abs(t) for _, t in gmsh.model.getBoundary([(2, face)], combined=False, oriented=True)]
    if len(loop) != 4 or len(set(loop)) != 4:
        return None
    return loop


def _bump(
    law: Direction, count: int, grid: ComponentGrid, direction: str, warnings: list[str]
) -> float:
    """Return the end-to-middle ratio of a cosine law: given, else the clusters, else its own."""
    if law.ratio is not None:
        return law.ratio
    if direction == "chord":
        clusters = [c for c in (grid.le_cluster, grid.te_cluster) if c is not None]
        if clusters:
            if len(set(clusters)) > 1:
                warnings.append(
                    f"{grid.name}: the cosine law is symmetric, so the smaller of le_cluster and "
                    f"te_cluster, {min(clusters):g}, is used at both edges"
                )
            return min(clusters)
    return math.tan(math.pi / (2 * max(count, 1)))


def _sides(
    gmsh: Any,
    name: str,
    grid: ComponentGrid,
    faces: list[int],
    size: float,
    warnings: list[str],
) -> tuple[list[_Side], list[int]]:
    """Return the two sides of every four-sided patch of a component, and those patches."""
    axis = _span_axis(gmsh, faces, grid)
    sides: list[_Side] = []
    patches: list[int] = []
    for face in faces:
        loop = _four_sides(gmsh, face)
        if loop is None or not grid.structured:
            continue
        pairs = [(loop[0], loop[2]), (loop[1], loop[3])]
        align = []
        for pair in pairs:
            total = 0.0
            for curve in pair:
                a, b = _ends(gmsh, curve)
                d = b - a
                n = float(np.linalg.norm(d))
                total += abs(float(d @ axis)) / n if n > 0 else 0.0
            align.append(total)
        span_index = int(np.argmax(align))
        patches.append(face)
        for index, pair in enumerate(pairs):
            direction = "span" if index == span_index else "chord"
            law = getattr(grid, direction)
            length = max(gmsh.model.occ.getMass(1, c) for c in pair)
            spec = law or Direction(count=None)
            if length < size:
                # A side shorter than the component's size is a strip, such as the base of a
                # blunt trailing edge: one cell across it, whatever the law of its direction.
                spec = Direction(count=1)
            count = spec.count or max(1, round(length / size))
            ratio = spec.ratio
            if spec.law == "cosine":
                ratio = _bump(spec, count, grid, direction, warnings)
            elif spec.law in DEFAULT_RATIO and ratio is None:
                ratio = DEFAULT_RATIO[spec.law]
            sides.append(_Side(name, pair, direction, count, spec.law, ratio, axis))
    return sides, patches


def _transfinite(gmsh: Any, sides: list[_Side]) -> list[dict[str, Any]]:
    """Give every group of curves one count and law; return the overridden requests."""
    groups = _Groups()
    for side in sides:
        groups.union(*side.curves)
    chosen: dict[int, _Side] = {}
    overrides: dict[tuple[str, str, int, int], int] = {}
    for side in sides:
        root = groups.find(side.curves[0])
        first = chosen.setdefault(root, side)
        if first.count != side.count:
            key = (side.component, first.component, side.count, first.count)
            overrides[key] = overrides.get(key, 0) + 1
    done: set[int] = set()
    for side in sides:
        first = chosen[groups.find(side.curves[0])]
        for curve in side.curves:
            if curve in done:
                continue
            done.add(curve)
            _set_curve(gmsh, curve, first)
    return [
        {"component": a, "wanted": w, "used": u, "from": b, "pairs": n}
        for (a, b, w, u), n in sorted(overrides.items())
    ]


def _set_curve(gmsh: Any, curve: int, side: _Side) -> None:
    nodes = side.count + 1
    if side.law == "uniform" or side.count == 1:
        gmsh.model.mesh.setTransfiniteCurve(curve, nodes, "Progression", 1.0)
        return
    if side.law == "cosine":
        gmsh.model.mesh.setTransfiniteCurve(curve, nodes, "Bump", float(side.ratio or 1.0))
        return
    a, b = _ends(gmsh, curve)
    if side.direction == "span":
        # Toward the tip: the end farther from the plane of symmetry, along the span axis.
        at_start = abs(float(a @ side.axis)) > abs(float(b @ side.axis))
    else:
        # Toward the downstream end: the end with the larger x.
        at_start = a[0] > b[0]
    ratio = float(side.ratio or 1.0)
    kind = "Progression" if side.law == "geometric" else "Beta"
    # A positive coefficient clusters at the curve's start, a negative one at its end.
    gmsh.model.mesh.setTransfiniteCurve(curve, nodes, kind, ratio if at_start else -ratio)


def mesh_model(
    gmsh: Any,
    model: NamedModel,
    config: GridConfig,
    order: list[str],
    sizes: dict[str, float],
    tolerance: float,
) -> Meshed:
    """Join, mesh and read back every component of an imported model."""
    warnings: list[str] = []
    healing = _heal(gmsh, model, tolerance)
    faces, fragment = _fragment(gmsh, model, order, tolerance, warnings)
    # Said now, before the mesh: on overlapping or crossing faces the mesher can take long, and
    # whoever waits should already know why. The record keeps them with the others.
    for message in warnings:
        warn(f"iges-grid: {message}", PyflightstreamWarning)
    fragment["warned"] = len(warnings)
    sides: list[_Side] = []
    patches: dict[str, list[int]] = {}
    for name in order:
        grid = config.components.get(name, ComponentGrid(name=name))
        if not faces[name]:
            continue
        found, four = _sides(gmsh, name, grid, faces[name], sizes[name], warnings)
        sides += found
        patches[name] = four
    overrides = _transfinite(gmsh, sides)
    for name in reversed(order):
        points = gmsh.model.getBoundary(
            [(2, t) for t in faces[name]], combined=False, recursive=True
        )
        gmsh.model.mesh.setSize([(0, abs(t)) for d, t in points if d == 0], sizes[name])
    for name in order:
        for face in patches.get(name, []):
            gmsh.model.mesh.setTransfiniteSurface(face)
        for face in faces[name]:
            gmsh.model.mesh.setRecombine(2, face)
    gmsh.option.setNumber("Mesh.Algorithm", _FRONTAL_QUADS)
    gmsh.option.setNumber("Mesh.RecombinationAlgorithm", _BLOSSOM)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 1)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.MeshSizeMax", max(sizes.values()))
    gmsh.model.mesh.generate(2)
    meshed = _read(
        gmsh,
        faces,
        order,
        warnings,
        {
            "healing": healing,
            "fragment": fragment,
            "tolerance": tolerance,
            "transfinite_patches": {n: len(p) for n, p in patches.items()},
            "count_overrides": overrides,
        },
    )
    meshed.boundary, meshed.record["unsewn_curves"] = _boundary_edges(gmsh, tolerance)
    return meshed


#: Two free curves closer than this many join tolerances everywhere are one edge left unsewn.
_UNSEWN_TOLERANCES = 10.0


def _boundary_edges(gmsh: Any, tolerance: float) -> tuple[set[tuple[int, int]], int]:
    """Return the mesh edges on true boundaries of the body, and the free curves left unsewn.

    A true boundary is a curve that bounds one face and lies on no other such curve: the open
    root of a wing, the open base of a blunt trailing edge. A free curve that lies on another
    (within :data:`_UNSEWN_TOLERANCES` join tolerances at five points) is an edge the join
    missed, and its mesh edges are not boundaries.
    """
    tags, _, _ = gmsh.model.mesh.getNodes()
    index = {int(t): i for i, t in enumerate(tags)}
    free = []
    for _, curve in gmsh.model.getEntities(1):
        up, _ = gmsh.model.getAdjacencies(1, curve)
        if len(up) == 1:
            free.append(curve)
    samples: dict[int, NDArray[np.float64]] = {}
    boxes: dict[int, NDArray[np.float64]] = {}
    for curve in free:
        lo, hi = gmsh.model.getParametrizationBounds(1, curve)
        ts = np.linspace(lo[0], hi[0], 7)[1:-1]
        samples[curve] = np.asarray(gmsh.model.getValue(1, curve, ts), dtype=float)
        boxes[curve] = np.asarray(gmsh.model.getBoundingBox(1, curve), dtype=float)
    reach = _UNSEWN_TOLERANCES * tolerance
    unsewn: set[int] = set()
    for a in free:
        for b in free:
            if a == b or a in unsewn:
                continue
            box_a, box_b = boxes[a], boxes[b]
            if np.any(box_a[:3] > box_b[3:] + reach) or np.any(box_b[:3] > box_a[3:] + reach):
                continue
            closest, _ = gmsh.model.getClosestPoint(1, b, samples[a])
            gap = np.linalg.norm(
                np.asarray(closest).reshape(-1, 3) - samples[a].reshape(-1, 3), axis=1
            )
            if float(gap.max()) <= reach:
                unsewn.add(a)
    boundary: set[tuple[int, int]] = set()
    for curve in free:
        if curve in unsewn:
            continue
        types, _, enodes = gmsh.model.mesh.getElements(1, curve)
        for kind, nodes in zip(types, enodes, strict=True):
            if int(kind) != 1:
                continue
            for a, b in np.asarray(nodes, dtype=np.int64).reshape(-1, 2):
                i, j = index[int(a)], index[int(b)]
                boundary.add((min(i, j), max(i, j)))
    return boundary, len(unsewn)


def _read(
    gmsh: Any,
    faces: dict[str, list[int]],
    order: list[str],
    warnings: list[str],
    record: dict[str, Any],
) -> Meshed:
    tags, coords, _ = gmsh.model.mesh.getNodes()
    index = {int(t): i for i, t in enumerate(tags)}
    nodes = np.asarray(coords, dtype=float).reshape(-1, 3)
    out: dict[str, list[list[int]]] = {}
    jacobian: dict[str, float] = {}
    for name in order:
        polys: list[list[int]] = []
        elements: list[int] = []
        empty = 0
        for face in faces[name]:
            types, etags, enodes = gmsh.model.mesh.getElements(2, face)
            held = 0
            for kind, et, en in zip(types, etags, enodes, strict=True):
                width = {_TRIANGLE: 3, _QUAD: 4}.get(int(kind))
                if width is None:
                    continue
                rows = np.asarray(en, dtype=np.int64).reshape(-1, width)
                for row in rows:
                    poly = [index[int(v)] for v in row]
                    poly = [v for i, v in enumerate(poly) if v != poly[i - 1]]
                    if len(set(poly)) >= 3:
                        polys.append(poly)
                        held += 1
                elements += [int(e) for e in et]
            empty += held == 0
        if empty:
            warnings.append(f"{name}: {empty} face(s) could not be meshed and are missing")
        out[name] = polys
        if elements:
            quality = gmsh.model.mesh.getElementQualities(elements, "minSJ")
            jacobian[name] = float(np.min(quality))
    return Meshed(nodes, out, jacobian, warnings=warnings, record=record)
