"""The gmsh half of ``geometry iges-grid``: join the faces, set the laws, mesh, read the elements.

The faces of every component are healed and fragmented together, so an edge two faces share
becomes one curve and its nodes are shared. Four-sided patches of a structured component get
transfinite curves with the laws of the grid control file and are recombined into quads; every
other patch is meshed quad-dominant (MeshAdapt, Blossom recombination) at its component's size,
graded from any curve shorter than it. The opposite sides of a four-sided patch must take one
count, so the curves that must agree are grouped and each group takes the count of the first
component that asks; every other request in the group is recorded as overridden.
"""

from __future__ import annotations

import math
from collections.abc import Callable
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
#: gmsh 2D algorithm 1, MeshAdapt, and recombination algorithm 1, Blossom. MeshAdapt keeps the
#: component's size on a face whose parametrization is stretched and meshes a narrow face
#: without slivers, where Frontal-Delaunay for quads (8) left cells many sizes long across both
#: in the release validation assembly (200 sliver faces with 8, 29 with MeshAdapt).
_MESH_ADAPT, _BLOSSOM = 1, 1
#: How fast the size grows with the distance from a short curve: a cell about a third larger
#: than its neighbour nearer the curve.
_GROWTH = 0.3
#: The least quality of a quad Blossom may make: 1 less the largest departure of a corner from
#: 90 degrees over 90. 6/90 refuses a quad with a corner over 174 or under 6 degrees, which stays
#: two triangles, so recombination makes no sliver (the record's limit is 5 degrees).
_RECOMBINE_QUALITY = 6.0 / 90.0


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
    """Fix degenerate edges and sew the faces; small edges are left as they are.

    Fixing small edges took the zero-length apex edge off the two half cones of the SMI-L2-PN
    nacelle nose, and the join after it gave both halves, and both half rings behind them, one
    half circle of the four: the mesh of the other half folded across the nose and four faces met
    along each of its edges.
    """
    tags = [(2, t) for t in model.faces]
    out = gmsh.model.occ.healShapes(tags, tolerance, True, False, False, True, False)
    gmsh.model.occ.synchronize()
    healed = sorted(t for d, t in out if d == 2)
    if healed == sorted(model.faces):
        return "healed (degenerate edges fixed, faces sewn)"
    return "healing changed the faces and was not kept"


def _crossings(gmsh: Any, owner: dict[int, str], warnings: list[str]) -> dict[tuple[str, ...], int]:
    """Count and warn the curves more than two faces meet along, by the components that meet."""
    crossings: dict[tuple[str, ...], int] = {}
    for _, curve in gmsh.model.getEntities(1):
        up, _ = gmsh.model.getAdjacencies(1, curve)
        if len(up) > 2:
            names = tuple(sorted({owner.get(int(t), "?") for t in up}))
            crossings[names] = crossings.get(names, 0) + 1
    for names, count in sorted(crossings.items()):
        warnings.append(
            f"more than two faces meet along {count} curve(s) of {' and '.join(names)}: a face "
            "crosses another without a trimmed junction; after the mesh the faces that lie "
            "inside the assembly are removed (remove_inner_faces in [defaults])"
        )
    return crossings


def _join(gmsh: Any, faces: list[int]) -> list[list[tuple[int, int]]]:
    """Fragment the faces against each other; return the pieces of each face, in their order.

    A single face has nothing to be joined to, and gmsh's fragment of one shape returns no map
    at all: it is kept whole, its own only piece.
    """
    if len(faces) < 2:
        return [[(2, t)] for t in faces]
    _, mapping = gmsh.model.occ.fragment([(2, t) for t in faces], [])
    gmsh.model.occ.synchronize()
    return [list(pieces) for pieces in mapping]


def _fragment(
    gmsh: Any,
    by_name: dict[str, list[int]],
    order: list[str],
    tolerance: float,
    warnings: list[str],
) -> tuple[dict[str, list[int]], dict[str, Any]]:
    """Fragment every face against every other; return the faces of each component after."""
    inputs = [(name, t) for name in order for t in by_name[name]]
    gmsh.option.setNumber("Geometry.ToleranceBoolean", tolerance)
    mapping = _join(gmsh, [t for _, t in inputs])
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
    crossings = _crossings(gmsh, owner, warnings)
    record = {
        "faces_before": len(inputs),
        "faces_after": len(owner),
        "split": sum(1 for pieces in mapping if sum(1 for d, _ in pieces if d == 2) > 1),
        "crossings": [{"components": list(k), "curves": v} for k, v in sorted(crossings.items())],
    }
    return faces, record


def _ends(gmsh: Any, curve: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the points at a curve's first and last parameter, the order its mesh runs in.

    The order ``getBoundary`` lists a curve's end points in need not be that one: after the join
    a curve can keep another face's orientation, and a law clustered by the listed order would
    then cluster toward the wrong end of that curve only.
    """
    lo, hi = gmsh.model.getParametrizationBounds(1, curve)
    start = np.asarray(gmsh.model.getValue(1, curve, [lo[0]]), dtype=float)
    end = np.asarray(gmsh.model.getValue(1, curve, [hi[0]]), dtype=float)
    return start, end


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


#: A patch is four-sided only when each of its four corners is below this angle. A curve that
#: meets the next nearly straight on (a side the join cut in two, a three-cornered patch whose
#: degenerate edge left) is a point on a side, not a corner, and the transfinite map flattens the
#: cell there; 160 degrees keeps every real corner of a wing, tail or body panel and leaves a
#: margin above them.
CORNER_LIMIT_DEG = 160.0


def _inward(gmsh: Any, curve: int) -> dict[int, NDArray[np.float64]]:
    """Return the unit tangent of a curve at each of its end points, pointing into the curve."""
    ends = [abs(t) for _, t in gmsh.model.getBoundary([(1, curve)], oriented=True)]
    where = {p: np.asarray(gmsh.model.getValue(0, p, []), dtype=float) for p in ends}
    lo, hi = gmsh.model.getParametrizationBounds(1, curve)
    out: dict[int, NDArray[np.float64]] = {}
    for at, sign in ((lo[0], 1.0), (hi[0], -1.0)):
        # The end a parameter bound is at, by position: the boundary's order need not follow it.
        here = np.asarray(gmsh.model.getValue(1, curve, [at]), dtype=float)
        point = min(where, key=lambda p: float(np.linalg.norm(where[p] - here)))
        d = sign * np.asarray(gmsh.model.getDerivative(1, curve, [at]), dtype=float)
        n = float(np.linalg.norm(d))
        if n > 0:
            out[point] = d / n
    return out


def corner_angles(gmsh: Any, loop: list[int]) -> list[float]:
    """Return the angle at each point where two consecutive curves of a loop meet, in degrees."""
    tangents = [_inward(gmsh, c) for c in loop]
    angles = []
    for i, here in enumerate(tangents):
        after = tangents[(i + 1) % len(loop)]
        shared = set(here) & set(after)
        if not shared:
            angles.append(180.0)
            continue
        point = shared.pop()
        cosine = float(np.clip(here[point] @ after[point], -1.0, 1.0))
        angles.append(math.degrees(math.acos(cosine)))
    return angles


def _four_sides(gmsh: Any, face: int) -> list[int] | None:
    loop = [abs(t) for _, t in gmsh.model.getBoundary([(2, face)], combined=False, oriented=True)]
    if len(loop) != 4 or len(set(loop)) != 4:
        return None
    if max(corner_angles(gmsh, loop)) >= CORNER_LIMIT_DEG:
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


def _span_pair(gmsh: Any, pairs: list[tuple[int, int]], axis: NDArray[np.float64]) -> int:
    """Return the index of the pair of opposite sides that runs closer to the span axis."""
    align = []
    for pair in pairs:
        total = 0.0
        for curve in pair:
            a, b = _ends(gmsh, curve)
            d = b - a
            n = float(np.linalg.norm(d))
            total += abs(float(d @ axis)) / n if n > 0 else 0.0
        align.append(total)
    return int(np.argmax(align))


def _sides(
    gmsh: Any,
    name: str,
    grid: ComponentGrid,
    faces: list[int],
    *,
    size: float,
    warnings: list[str],
) -> tuple[list[_Side], list[int]]:
    """Return the two sides of every four-sided patch of a component, and those patches."""
    axis = _span_axis(gmsh, faces, grid)
    sides: list[_Side] = []
    patches: list[int] = []
    strips: dict[tuple[str, int], int] = {}
    for face in faces:
        loop = _four_sides(gmsh, face)
        if loop is None or not grid.structured:
            continue
        pairs = [(loop[0], loop[2]), (loop[1], loop[3])]
        span_index = _span_pair(gmsh, pairs, axis)
        patches.append(face)
        for index, pair in enumerate(pairs):
            direction = "span" if index == span_index else "chord"
            spec = getattr(grid, direction) or Direction(count=None)
            length = max(gmsh.model.occ.getMass(1, c) for c in pair)
            if length < size:
                # A side shorter than the component's size is a strip, such as the base of a
                # blunt trailing edge: one cell across it, whatever the law of its direction.
                if spec.count is not None and spec.count != 1:
                    key = (direction, spec.count)
                    strips[key] = strips.get(key, 0) + 1
                spec = Direction(count=1)
            count = spec.count or max(1, round(length / size))
            ratio = spec.ratio
            if spec.law == "cosine":
                ratio = _bump(spec, count, grid, direction, warnings)
            elif spec.law in DEFAULT_RATIO and ratio is None:
                ratio = DEFAULT_RATIO[spec.law]
            sides.append(_Side(name, pair, direction, count, spec.law, ratio, axis))
    for (direction, asked), patches_cut in sorted(strips.items()):
        warnings.append(
            f"{name}: {patches_cut} patch(es) with a {direction} side shorter than the size "
            f"{size:g} take 1 cell across it, not the {direction} count of {asked}"
        )
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


def _point_sizes(
    gmsh: Any, faces: dict[str, list[int]], order: list[str], sizes: dict[str, float]
) -> None:
    """Set the mesh size: its component's at every point, and graded about every short curve.

    A point takes the size of the first component in the grid file whose faces reach it. A curve
    shorter than the size at its ends, such as a piece the join cut off, gets one cell; a
    quad-dominant face meshed at the full size around it would close that cell with a sliver. So
    the size about such a curve is its length, growing by :data:`_GROWTH` of the distance from it
    until it is the full size again: the cells grow from the curve and only near it.
    """
    size: dict[int, float] = {}
    for name in order:
        points = gmsh.model.getBoundary(
            [(2, t) for t in faces[name]], combined=False, recursive=True
        )
        for dim, tag in points:
            if dim == 0:
                size.setdefault(abs(tag), sizes[name])
    for point, value in size.items():
        gmsh.model.mesh.setSize([(0, point)], value)
    fields = []
    for _, curve in gmsh.model.getEntities(1):
        ends = [abs(t) for d, t in gmsh.model.getBoundary([(1, curve)]) if d == 0]
        full = min((size[p] for p in ends if p in size), default=0.0)
        length = gmsh.model.occ.getMass(1, curve)
        if not 0 < length < full:
            continue
        distance = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(distance, "CurvesList", [curve])
        threshold = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(threshold, "InField", distance)
        gmsh.model.mesh.field.setNumber(threshold, "SizeMin", length)
        gmsh.model.mesh.field.setNumber(threshold, "SizeMax", full)
        gmsh.model.mesh.field.setNumber(threshold, "DistMin", 0.0)
        gmsh.model.mesh.field.setNumber(threshold, "DistMax", (full - length) / _GROWTH)
        gmsh.model.mesh.field.setNumber(threshold, "StopAtDistMax", 1)
        fields.append(threshold)
    if fields:
        least = gmsh.model.mesh.field.add("Min")
        gmsh.model.mesh.field.setNumbers(least, "FieldsList", fields)
        gmsh.model.mesh.field.setAsBackgroundMesh(least)


def mesh_model(
    gmsh: Any,
    model: NamedModel,
    config: GridConfig,
    order: list[str],
    sizes: dict[str, float],
    *,
    tolerance: float,
    reopen: Callable[[], NamedModel] | None = None,
) -> Meshed:
    """Join, mesh and read back every component of an imported model.

    With ``reopen`` (which clears gmsh and imports the files again) and no stated tolerance, a
    gap the files leave between faces that should meet is measured after the first join and,
    when :data:`_CLOSE_FACTOR` times the widest is above that join's tolerance, the files are
    imported and joined again at it (:func:`_near_miss_gaps`).
    """
    warnings: list[str] = []
    healing = _heal(gmsh, model, tolerance)
    faces, fragment = _fragment(gmsh, model.components(), order, tolerance, warnings)
    closed: list[dict[str, Any]] = []
    if config.tolerance is None and reopen is not None:
        closed, joined = _near_miss_gaps(gmsh, faces, sizes)
        if joined > tolerance:
            first = {"tolerance": tolerance, **fragment}
            model, tolerance = reopen(), joined
            warnings.clear()
            healing = _heal(gmsh, model, tolerance)
            faces, fragment = _fragment(gmsh, model.components(), order, tolerance, warnings)
            fragment["first_join"] = first
            for entry in closed:
                warnings.append(
                    f"the files leave a gap of up to {entry['gap']:.4g} between faces of "
                    f"{' and '.join(entry['components'])} along {entry['curves']} curve(s); "
                    f"the faces were joined again at {joined:.4g}"
                )
        else:
            closed = []
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
        found, four = _sides(gmsh, name, grid, faces[name], size=sizes[name], warnings=warnings)
        sides += found
        patches[name] = four
    overrides = _transfinite(gmsh, sides)
    _point_sizes(gmsh, faces, order, sizes)
    for name in order:
        for face in patches.get(name, []):
            gmsh.model.mesh.setTransfiniteSurface(face)
        for face in faces[name]:
            gmsh.model.mesh.setRecombine(2, face)
    gmsh.option.setNumber("Mesh.Algorithm", _MESH_ADAPT)
    gmsh.option.setNumber("Mesh.RecombinationAlgorithm", _BLOSSOM)
    gmsh.option.setNumber("Mesh.RecombineMinimumQuality", _RECOMBINE_QUALITY)
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
            "closed_gaps": closed,
            "transfinite_patches": {n: len(p) for n, p in patches.items()},
            "count_overrides": overrides,
        },
    )
    owner = {f: n for n, fs in faces.items() for f in fs}
    meshed.boundary, meshed.record["unsewn_curves"] = _boundary_edges(gmsh, owner, sizes)
    return meshed


#: A free curve that lies on another within this share of the smaller of their components'
#: sizes is a join the file missed: a grid of that size cannot show an opening so narrow, and a
#: wider one, such as a blunt trailing edge left open, is a boundary of the body.
NEAR_MISS_SHARE = 0.01
#: The second join that closes a near miss takes this multiple of the widest gap measured.
_CLOSE_FACTOR = 1.5


def lies_on(
    params: NDArray[np.float64],
    bounds: tuple[float, float],
    gaps: NDArray[np.float64],
    reach: float,
) -> bool:
    """Return whether sampled points lie on a curve: every gap within reach, on its own span.

    ``params`` are the parameters of the closest points on the curve and ``bounds`` its
    parameter range. A projection outside the range lands on the curve's extension, where the
    next piece of a curve the join cut continues: such points lie beside the curve, not on it.
    """
    lo, hi = bounds
    margin = 1e-9 * max(abs(hi - lo), 1.0)
    inside = bool(np.all(params >= lo - margin) and np.all(params <= hi + margin))
    return inside and bool(np.all(gaps <= reach))


def _near_misses(
    gmsh: Any, owner: dict[int, str], sizes: dict[str, float]
) -> list[tuple[int, int, float]]:
    """Return each free curve that lies on another free curve, that curve and the widest gap.

    A free curve bounds one face. Five points of it are projected on each other free curve
    whose box comes within reach, the reach being :data:`NEAR_MISS_SHARE` of the smaller size
    of the two curves' components.
    """
    free: dict[int, str] = {}
    for _, curve in gmsh.model.getEntities(1):
        up, _ = gmsh.model.getAdjacencies(1, curve)
        if len(up) == 1:
            free[curve] = owner.get(int(up[0]), "")
    samples: dict[int, NDArray[np.float64]] = {}
    boxes: dict[int, NDArray[np.float64]] = {}
    for curve in free:
        lo, hi = gmsh.model.getParametrizationBounds(1, curve)
        ts = np.linspace(lo[0], hi[0], 7)[1:-1]
        samples[curve] = np.asarray(gmsh.model.getValue(1, curve, ts), dtype=float)
        boxes[curve] = np.asarray(gmsh.model.getBoundingBox(1, curve), dtype=float)
    smallest = min(sizes.values()) if sizes else 0.0
    out: list[tuple[int, int, float]] = []
    for a, name_a in free.items():
        for b, name_b in free.items():
            if a == b:
                continue
            reach = NEAR_MISS_SHARE * min(sizes.get(name_a, smallest), sizes.get(name_b, smallest))
            box_a, box_b = boxes[a], boxes[b]
            if np.any(box_a[:3] > box_b[3:] + reach) or np.any(box_b[:3] > box_a[3:] + reach):
                continue
            closest, params = gmsh.model.getClosestPoint(1, b, samples[a])
            gaps = np.linalg.norm(
                np.asarray(closest).reshape(-1, 3) - samples[a].reshape(-1, 3), axis=1
            )
            lo, hi = gmsh.model.getParametrizationBounds(1, b)
            if lies_on(np.asarray(params, dtype=float), (lo[0], hi[0]), gaps, reach):
                out.append((a, b, float(gaps.max())))
                break
    return out


def _near_miss_gaps(
    gmsh: Any, faces: dict[str, list[int]], sizes: dict[str, float]
) -> tuple[list[dict[str, Any]], float]:
    """Return the near misses of a join by pair of components, and the tolerance that closes them.

    The first join's tolerance is a share of the assembly; a gap the files leave between two
    faces that should meet can be wider. Each such gap is measured (:func:`_near_misses`); the
    closing tolerance is :data:`_CLOSE_FACTOR` times the widest, 0 when there is none.
    """
    owner = {f: n for n, fs in faces.items() for f in fs}
    misses = _near_misses(gmsh, owner, sizes)
    pairs: dict[tuple[str, ...], dict[str, Any]] = {}
    for a, b, gap in misses:
        names = tuple(
            sorted({owner.get(int(gmsh.model.getAdjacencies(1, c)[0][0]), "") for c in (a, b)})
        )
        entry = pairs.setdefault(names, {"components": list(names), "curves": 0, "gap": 0.0})
        entry["curves"] += 1
        entry["gap"] = max(entry["gap"], gap)
    widest = max((gap for *_, gap in misses), default=0.0)
    return [pairs[k] for k in sorted(pairs)], _CLOSE_FACTOR * widest


def _boundary_edges(
    gmsh: Any, owner: dict[int, str], sizes: dict[str, float]
) -> tuple[set[tuple[int, int]], int]:
    """Return the mesh edges on true boundaries of the body, and the free curves left unsewn.

    A true boundary is a curve that bounds one face and lies on no other such curve: the open
    root of a wing, the open base of a blunt trailing edge. A free curve that lies on another
    (:func:`_near_misses`) is an edge the join missed, and its mesh edges are not boundaries.
    """
    tags, _, _ = gmsh.model.mesh.getNodes()
    index = {int(t): i for i, t in enumerate(tags)}
    unsewn = {a for a, _, _ in _near_misses(gmsh, owner, sizes)}
    free = [
        curve
        for _, curve in gmsh.model.getEntities(1)
        if len(gmsh.model.getAdjacencies(1, curve)[0]) == 1
    ]
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
