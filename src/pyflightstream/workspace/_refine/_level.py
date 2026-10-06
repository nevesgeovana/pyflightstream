"""Write a level: the orchestration behind ``pyfs-matrix refine`` and ``refine_mesh``.

FR-424, FR-425 and FR-427. With ``[periodic]``, the source's cut boundaries
are found, and refused when they do not match, before any work; the remeshed
sides of the cuts are rebuilt on matching nodes like the neighbours of step
4; and the level's cuts are matched and measured after assembly
(:mod:`._periodic`).

The order, from the source to the level folder:

1. read the mesh, the request (:mod:`._config`) and the trailing-edge points;
2. recover the grid of every family asked to change (a sheet, a tube, or a
   multiblock grid of quadrilaterals, :mod:`._blocks`) and decide its
   method, refusing before any work (FR-424 R9 to R11);
3. refine the grid families first, in the source's family order; a grid that
   shares nodes with a grid refined before it is remeshed (FR-425 R1);
4. hand each neighbour the grid's new nodes on their shared curve: a remeshed
   neighbour is rebuilt on them (FR-425 R2), an unchanged one is remeshed at
   factor 1 in a band of two face layers (FR-425 R3);
5. remesh the other families, together where they touch (FR-424 R8); a
   body refined along and around its axis is remeshed in its stretched space
   (FR-428), together only with bodies stretched alike, and its curve with
   a factor-1 family or the band of an unchanged neighbour stays frozen;
6. assemble in the source's family order, weld the shared nodes, put each
   band back into its family in the source's order, group the components
   (FR-425 R4), write the level into a temporary folder, audit it there
   (FR-426), and rename it once complete; an existing level is replaced only
   then (FR-424 R4, R5).

Every input the audit refuses (the boundaries file, the trailing-edge points
file it names) is read in step 1, so a refusal comes before any work (R11).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
import shutil
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy
from numpy.typing import NDArray

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._refine import _blocks, _config, _geometry, _grid, _obj, _periodic
from pyflightstream.workspace._refine._audit import MeshAudit, audit_mesh
from pyflightstream.workspace._refine._config import FamilySpec, RefineRequest
from pyflightstream.workspace._refine._geometry import NearestIndex, Stretch, order_like
from pyflightstream.workspace._refine._obj import Faces, ObjMesh

Points = NDArray[numpy.float64]

#: The suffix of a band family while it is remeshed; it never reaches the level.
BAND_SUFFIX = "~band"
#: The trailing-edge points file of a mesh, when its boundaries file names none.
TE_SUFFIX = _obj.TE_SUFFIX
#: The folder a level is written into before it is renamed to its own name (FR-424 R5).
STAGING_SUFFIX = ".partial"
#: The name an existing level is moved to while ``overwrite`` replaces it, until the new
#: level is in place (FR-424 R5): an error before then puts it back.
PREVIOUS_SUFFIX = ".previous"


@dataclass(frozen=True)
class RefinedMesh:
    """What a refinement wrote: the level folder, its files and the report of each family.

    Attributes
    ----------
    folder : pathlib.Path
        The level folder ``<out-dir>/<stem>_<tag>/``.
    obj : pathlib.Path
        The level's OBJ.
    files : tuple of pathlib.Path
        Every file written, the OBJ first.
    report : dict
        The ``families`` entry of ``refine.json``: per family, the method,
        the reason, the layout and the counts before and after.
    audit : MeshAudit
        The audit of the level against its source (FR-426), written beside it.
    """

    folder: Path
    obj: Path
    files: tuple[Path, ...]
    report: dict[str, Any]
    audit: MeshAudit | None = None


@dataclass
class _Work:
    """The state a refinement carries from one step to the next."""

    source: Path
    mesh: ObjMesh
    request: RefineRequest
    te_unit: str
    te_to_file: float
    te_points: Points  # in the mesh's unit; te_to_file turns a length into te_unit's
    names: list[str]
    original: dict[str, Faces]
    fam_v: dict[str, set[int]]
    te_of: dict[str, set[int]]
    scale: float
    grids: dict[str, _grid.Grid | _blocks.Blocks] = field(default_factory=dict)
    remesh: list[str] = field(default_factory=list)
    report: dict[str, dict[str, Any]] = field(default_factory=dict)
    parts: dict[str, tuple[Points, dict[str, Faces], Points]] = field(default_factory=dict)
    conform: dict[str, list[tuple[set[int], Points]]] = field(default_factory=dict)
    bands: dict[str, str] = field(default_factory=dict)
    cuts: list[_periodic.CutPair] = field(default_factory=list)
    periodic: dict[str, Any] | None = None
    sidecar: str | None = None  # the level's boundaries file, rewritten before any work
    unchanged: list[str] = field(default_factory=list)  # the families G6 compares


def _refuse(where: str, reason: str) -> InputArtifactError:
    return InputArtifactError(f"{where}: {reason}. Nothing was written.", kind=_obj.KIND)


# --------------------------------------------------------------------- reading


def _te_vertices(mesh: ObjMesh, family: str, points: Points, scale: float) -> set[int]:
    """Return the trailing-edge vertices: the ends of the edges whose mid-point is listed."""
    if not len(points):
        return set()
    edges, mid = _obj.edge_midpoints(mesh.verts, mesh.families[family])
    dist, index = NearestIndex(mid).query(points)
    hit = dist < _geometry.TE_POINT_FRACTION * scale
    return {int(v) for v in edges[index[hit]].ravel()}


def _start(source: Path, request: RefineRequest, mesh: ObjMesh) -> _Work:
    te = _obj.te_points(source)
    unit, points = ("METER", numpy.zeros((0, 3))) if te is None else (te.unit, te.points)
    scale = mesh.size
    names = list(mesh.families)
    return _Work(
        source=source,
        mesh=mesh,
        request=request,
        te_unit=unit,
        te_to_file=1.0 if te is None else te.to_file,
        te_points=points,
        names=names,
        original={n: list(fs) for n, fs in mesh.families.items()},
        fam_v={n: set(mesh.family_vertices(n).tolist()) for n in names},
        te_of={n: _te_vertices(mesh, n, points, scale) for n in names},
        scale=scale,
    )


# ------------------------------------------------------------------- deciding


def _decide(work: _Work) -> None:
    """Recover the grids and choose each family's method, refusing before any work (R9, R10)."""
    chosen = [n for n in work.names if n in work.request.specs]
    for name in chosen:
        spec = work.request.specs[name]
        if spec.method == "remesh" or spec.axial is not None:
            _remesh_or_keep(work, name, "the refinement file states remesh")
            continue
        found = _blocks.recover_family(work.mesh.verts, work.mesh.families[name], work.te_of[name])
        if isinstance(found, str):
            if spec.method == "grid":
                raise _refuse(
                    f"{work.source} family {name}",
                    f"method is grid and no grid was recovered: {found}",
                )
            _remesh_or_keep(work, name, f"no grid recovered: {found}")
            continue
        if isinstance(found, _blocks.Blocks):
            _blocks.check_factor(found, name, spec)
        else:
            chordwise, spanwise = spec.directions
            _grid.check_factors(found, name, chordwise=chordwise, spanwise=spanwise)
        work.grids[name] = found
    _grid_after_grid(work)
    _bodies_apart(work)
    for name in work.remesh:
        spec = work.request.specs[name]
        if spec.chordwise is not None or spec.spanwise is not None:
            raise _refuse(
                f"{work.source} family {name}",
                "chordwise and spanwise apply to a grid; it is remeshed, give factor",
            )
    bands = _planned_bands(work)
    if work.remesh or bands:
        from pyflightstream.workspace._refine._remesh import require_geometry_extra

        require_geometry_extra([*work.remesh, *bands])


def _planned_bands(work: _Work) -> list[str]:
    """Return the unchanged families whose band will be remeshed (FR-425 R3), before any work.

    An unchanged neighbour gets a band when it shares a curve with a grid
    family whose nodes on that curve change, which the grid's counts tell
    without resampling it (:func:`._grid.curve_changes`,
    :func:`._blocks.nodes_change`); its remesh needs the geometry extra like
    any other (FR-424 R10, R11).
    """
    planned: list[str] = []
    for name in [n for n in work.names if n not in work.request.specs]:
        for grid_name, grid in work.grids.items():
            old = work.fam_v[grid_name] & work.fam_v[name]
            edges = [
                e
                for e in _geometry.boundary_edges(work.mesh.families[grid_name])
                if e[0] in old and e[1] in old
            ]
            if not edges:
                continue
            chordwise, spanwise = work.request.specs[grid_name].directions
            if isinstance(grid, _blocks.Blocks):
                changes = _blocks.nodes_change(grid, chordwise)
            else:
                changes = _grid.curve_changes(grid, edges, chordwise=chordwise, spanwise=spanwise)
            if changes:
                planned.append(name)
                break
    return planned


def _grid_after_grid(work: _Work) -> None:
    """Remesh a grid that shares nodes with a grid refined first, or refuse it (FR-425 R1)."""
    done: list[str] = []
    for name in [n for n in work.names if n in work.grids]:
        first = [m for m in done if work.fam_v[name] & work.fam_v[m]]
        if not first:
            done.append(name)
            continue
        if work.request.specs[name].method == "grid":
            raise _refuse(
                f"{work.source} family {name}",
                f"method is grid and it shares nodes with {first[0]}, refined as a grid first",
            )
        del work.grids[name]
        _remesh_or_keep(work, name, f"shares nodes with the grid {first[0]}")
    work.remesh.sort(key=work.names.index)


def _remesh_or_keep(work: _Work, name: str, reason: str) -> None:
    """Remesh a family, or keep it unchanged when every factor it is given is 1.

    A remeshed family at factor 1 is an UNCHANGED FAMILY (FR-424): it is
    copied as the source holds it, and a band of it is remeshed only where a
    grid beside it changed their shared curve (FR-425 R3). A family the
    refinement file states ``method = "remesh"`` is remeshed at any factor.
    """
    spec = work.request.specs[name]
    if spec.unchanged and spec.method == "auto":
        del work.request.specs[name]
        work.report[name] = {"method": "unchanged", "reason": f"factor 1 ({reason})"}
        return
    work.remesh.append(name)
    work.report[name] = {"method": "remesh", "reason": reason}


def _stretch_of(work: _Work, name: str) -> Stretch | None:
    """Return the stretch of a body (FR-428), its origin defaulting to the family's centroid."""
    spec = work.request.specs.get(name)
    if spec is None or spec.axis is None:
        return None
    centroid = work.mesh.verts[sorted(work.fam_v[name])].mean(axis=0)
    origin = centroid if spec.origin is None else spec.origin
    return Stretch(spec.axis, origin, spec.axial or 1.0, spec.circumferential or 1.0)


def _stretched_unlike(work: _Work, name: str, other: str) -> bool:
    """Return whether two families are not stretched alike (FR-428).

    They are not when one is a body and the other not, or when two bodies
    differ in axis or factors; the origin only translates the space.
    """
    mine, theirs = _stretch_of(work, name), _stretch_of(work, other)
    if mine is None or theirs is None:
        return (mine is None) != (theirs is None)
    return not mine.same_linear_part(theirs)


def _kept_apart(work: _Work, name: str, other: str) -> bool:
    """Return whether two families not stretched alike are each remeshed alone (FR-428).

    They are when one of them is unchanged: a remeshed family at factor 1,
    a body at axial and circumferential 1, or the band of an unchanged
    neighbour (FR-425 R3). The curve they share keeps its nodes on both
    sides, as an interface with an unchanged family does (FR-424 R8).
    """
    specs = work.request.specs
    unchanged = specs[name].unchanged or specs[other].unchanged
    return unchanged and _stretched_unlike(work, name, other)


def _bodies_apart(work: _Work) -> None:
    """Refuse a body remeshed together with a family not stretched alike (FR-428).

    Two remeshed families that share nodes are remeshed together, so their
    shared curve is remeshed once (FR-424 R8). A stretch applies to the whole
    group, so a body can join only bodies with the same axis and factors; an
    unchanged family beside it is remeshed apart (:func:`_kept_apart`), and
    any other pair is refused naming both families.
    """
    for i, name in enumerate(work.remesh):
        for other in work.remesh[i + 1 :]:
            if not work.fam_v[name] & work.fam_v[other]:
                continue
            if not _stretched_unlike(work, name, other) or _kept_apart(work, name, other):
                continue
            raise _refuse(
                f"{work.source} families {name} and {other}",
                "they share nodes and are remeshed together, and they are not refined with "
                "the same axial, circumferential and axis; state the same three on both, "
                "or leave one of them unchanged",
            )


# ------------------------------------------------------------------- refining


def _refine_grids(work: _Work) -> None:
    """Refine every grid family and record what its neighbours must take (FR-425 R2, R3)."""
    for name, grid in work.grids.items():
        chordwise, spanwise = work.request.specs[name].directions
        if isinstance(grid, _blocks.Blocks):
            level = _blocks.refine_blocks(
                work.mesh.verts, work.mesh.families[name], grid, factor=chordwise
            )
        else:
            level = _grid.refine_grid(
                work.mesh.verts,
                work.mesh.families[name],
                grid,
                chordwise=chordwise,
                spanwise=spanwise,
                family=name,
            )
        info: dict[str, Any] = dict(level.report, method="grid", reason=grid.describe())
        if work.request.elements_of(name) != _config.TRIANGLES:
            info["elements"] = (
                f"{work.request.elements_of(name)} ignored: it applies to a remeshed family, "
                "and a grid keeps its cells"
            )
        interfaces: dict[str, str] = {}
        for other in work.names:
            old = work.fam_v[name] & work.fam_v[other] if other != name else set()
            new = _interface_points(work, name, old, level) if old else None
            if new is None or _unchanged_curve(work, old, new):
                continue
            work.conform.setdefault(other, []).append((old, new))
            interfaces[other] = f"{len(old)} -> {len(new)} nodes"
        if interfaces:
            info["interfaces"] = interfaces
        work.report[name] = info
        work.parts[name] = (level.points, {name: level.faces}, level.te_midpoints)


def _interface_points(
    work: _Work, name: str, old: set[int], level: _grid.GridLevel
) -> Points | None:
    """Return the grid's new boundary nodes on the curve it shares with a neighbour.

    The curve is the grid's source boundary edges whose two ends are shared
    (``old``); a new node is on it when it lies within
    :data:`._geometry.ON_CURVE_FRACTION` of a segment's length from one of
    those edges.
    """
    source_edges = [
        e for e in _geometry.boundary_edges(work.mesh.families[name]) if e[0] in old and e[1] in old
    ]
    if not source_edges:
        return None
    a = work.mesh.verts[[e[0] for e in source_edges]]
    b = work.mesh.verts[[e[1] for e in source_edges]]
    length = numpy.linalg.norm(b - a, axis=1)
    ab = b - a
    keep = []
    for v in sorted({v for e in _geometry.boundary_edges(level.faces) for v in e}):
        p = level.points[v]
        t = numpy.clip(
            ((p - a) * ab).sum(axis=1) / numpy.maximum((ab * ab).sum(axis=1), 1e-300), 0.0, 1.0
        )
        d = numpy.linalg.norm(a + t[:, None] * ab - p, axis=1)
        j = int(numpy.argmin(d))
        if d[j] < _geometry.ON_CURVE_FRACTION * length[j]:
            keep.append(v)
    return level.points[keep] if keep else None


def _unchanged_curve(work: _Work, old: set[int], new: Points) -> bool:
    """Return whether the grid kept exactly the source nodes of a shared curve."""
    olds = work.mesh.verts[sorted(old)]
    tolerance = _geometry.DUPLICATE_FRACTION * work.scale
    return len(new) == len(olds) and float(NearestIndex(olds).query(new)[0].max()) < tolerance


def _bands(work: _Work) -> None:
    """Cut a band of face layers out of each unchanged neighbour whose curve changed (FR-425 R3)."""
    for name in [n for n in work.names if n in work.conform and n not in work.request.specs]:
        seed = set().union(*(old for old, _ in work.conform[name]))
        faces = work.mesh.families[name]
        band = _band(faces, seed, _geometry.BAND_LAYERS)
        bname = name + BAND_SUFFIX
        families: dict[str, Faces] = {}
        for n, fs in work.mesh.families.items():
            if n == name:
                families[name] = [f for i, f in enumerate(fs) if i not in band]
                families[bname] = [f for i, f in enumerate(fs) if i in band]
            else:
                families[n] = fs
        work.mesh.families = families
        work.names = list(families)
        for n in (name, bname):
            work.fam_v[n] = set(work.mesh.family_vertices(n).tolist())
            work.te_of[n] = _te_vertices(work.mesh, n, work.te_points, work.scale)
        work.request.specs[bname] = FamilySpec(factor=1.0, method="remesh")
        work.remesh.append(bname)
        work.conform[bname] = work.conform.pop(name)
        work.bands[bname] = name
        work.report[name] = {
            "method": "unchanged",
            "band": len(band),
            "faces": len(work.original[name]),
        }


def _band(faces: Faces, seed: set[int], layers: int) -> set[int]:
    """Return the faces within ``layers`` face layers of the seed vertices."""
    vertices, selected = set(seed), set()
    for _ in range(layers):
        new = [
            i for i, f in enumerate(faces) if i not in selected and any(v in vertices for v in f)
        ]
        selected.update(new)
        vertices |= {v for i in new for v in faces[i]}
    return selected


def _cut_factor(spec: FamilySpec) -> float:
    """Return the factor a remeshed family's cut is resampled by (the finer of axial and around)."""
    if spec.axial is None and spec.circumferential is None:
        return spec.factor
    return max(spec.axial or 1.0, spec.circumferential or 1.0)


def _conform_cuts(work: _Work) -> None:
    """Rebuild the remeshed sides of a periodic sector's cuts on matching nodes (FR-427)."""
    planned = _periodic.plan_conform(
        work.mesh.verts,
        work.mesh.families,
        work.cuts,
        work.request.periodic,
        remeshed={n: _cut_factor(work.request.specs[n]) for n in work.remesh},
        grids={n: (pts, fams[n]) for n, (pts, fams, _) in work.parts.items() if n in work.grids},
    )
    for name, entries in planned.items():
        work.conform.setdefault(name, []).extend(entries)


def _remesh_groups(work: _Work) -> None:
    """Remesh the other families, together where they share nodes (FR-424 R8)."""
    if not work.remesh:
        return
    from pyflightstream.workspace._refine._remesh import element_report, refine_group

    groups: list[list[str]] = []
    for name in work.remesh:
        hit = [g for g in groups if any(_together(work, name, m) for m in g)]
        merged = [name] + [m for g in hit for m in g]
        groups = [g for g in groups if g not in hit] + [merged]
    for group in groups:
        ordered = [n for n in work.names if n in group]
        te = set().union(*(work.te_of[n] for n in ordered))
        factors = {n: work.request.specs[n].factor for n in ordered}
        conform = [c for n in ordered for c in work.conform.get(n, [])]
        stretches = [s for s in (_stretch_of(work, n) for n in ordered) if s is not None]
        stretch = stretches[0] if stretches else None
        modes = {n: work.request.elements_of(work.bands.get(n, n)) for n in ordered}
        done = refine_group(
            work.mesh, ordered, te, factors, conform=conform, stretch=stretch, elements=modes
        )
        for n in ordered:
            entry = work.report.setdefault(n, {"method": "remesh"})
            entry.update(
                done.info,
                faces_before=len(work.mesh.families[n]),
                faces_after=len(done.families.get(n, [])),
                **element_report(modes[n], done.families.get(n, [])),
            )
        work.parts[ordered[0]] = (done.points, done.families, done.trailing_edge)


def _together(work: _Work, name: str, other: str) -> bool:
    """Return whether two remeshed families are remeshed in one group.

    They are when they share nodes, except a body and an unchanged family
    (:func:`_kept_apart`): their shared curve keeps its nodes on both sides.
    """
    return bool(work.fam_v[name] & work.fam_v[other]) and not _kept_apart(work, name, other)


# ------------------------------------------------------------------ assembling


def _assemble(work: _Work) -> tuple[Points, dict[str, Faces], Points]:
    """Assemble the parts in the source's family order; families not asked are copied unchanged."""
    blocks: list[Points] = []
    faces: dict[str, Faces] = {}
    te: list[Points] = []
    offset = 0
    copied_te = numpy.zeros(len(work.te_points), dtype=bool)
    changed = set(work.request.specs)
    for name in work.names:
        if name in work.parts:
            pts, fams, mids = work.parts[name]
            blocks.append(pts)
            faces.update({n: [[v + offset for v in f] for f in fs] for n, fs in fams.items()})
            offset += len(pts)
            if len(mids):
                te.append(mids)
        elif name not in changed:
            ids = sorted(work.fam_v[name])
            local = {v: i + offset for i, v in enumerate(ids)}
            blocks.append(work.mesh.verts[ids])
            faces[name] = [[local[v] for v in f] for f in work.mesh.families[name]]
            offset += len(ids)
            hit = _te_points_of(work, name) & ~copied_te
            if hit.any():
                te.append(work.te_points[hit])
                copied_te |= hit
    verts, faces = _weld(
        numpy.vstack(blocks), {n: faces[n] for n in work.names if n in faces}, work.scale
    )
    for band, family in work.bands.items():
        faces[family] = order_like(
            verts, faces[family] + faces.pop(band), work.mesh.verts, work.original[family]
        )
    midpoints = numpy.vstack(te) if te else numpy.zeros((0, 3))
    verts, faces = _source_numbering(verts, faces, work.mesh.verts, work.scale)
    return verts, faces, midpoints


def _source_numbering(
    verts: Points, faces: dict[str, Faces], source: Points, scale: float
) -> tuple[Points, dict[str, Faces]]:
    """Renumber the level's nodes the way the source numbers them (FR-424 R7).

    A node at a source node's position takes that node's place in the source's
    order; the new nodes follow, in their order of first use. A level that
    keeps every source node, a grid at factor 1, is written with the source's
    vertex list.
    """
    dist, index = _geometry.NearestIndex(source).query(verts)
    kept = dist <= _geometry.DUPLICATE_FRACTION * scale
    key = numpy.where(kept, index, len(source) + numpy.arange(len(verts)))
    order = numpy.argsort(key, kind="stable")
    rank = numpy.empty(len(verts), dtype=numpy.int64)
    rank[order] = numpy.arange(len(verts))
    renumbered = {n: [[int(rank[v]) for v in f] for f in fs] for n, fs in faces.items()}
    return verts[order], renumbered


def _source_text(work: _Work, verts: Points) -> list[str | None]:
    """Return, per level node, the source's coordinate text when the node is a source node.

    A node equal in every coordinate to the source node at its position is
    written as the source wrote it, so a node the refinement kept is the
    source's in its text too (FR-424 R7); any other node is written by
    :func:`._obj.coordinates`.
    """
    if not len(verts) or len(work.mesh.vertex_text) != len(work.mesh.verts):
        return []
    dist, index = NearestIndex(work.mesh.verts).query(verts)
    same = (dist == 0.0) & numpy.all(work.mesh.verts[index] == verts, axis=1)
    return [work.mesh.vertex_text[int(i)] if s else None for i, s in zip(index, same, strict=True)]


def _te_points_of(work: _Work, name: str) -> NDArray[numpy.bool_]:
    """Return which listed trailing-edge points lie on an edge of the family."""
    if not len(work.te_points):
        return numpy.zeros(0, dtype=bool)
    _, mid = _obj.edge_midpoints(work.mesh.verts, work.mesh.families[name])
    dist, _ = NearestIndex(mid).query(work.te_points)
    return dist < _geometry.TE_POINT_FRACTION * work.scale


def _weld(
    verts: Points, families: dict[str, Faces], scale: float
) -> tuple[Points, dict[str, Faces]]:
    """Weld nodes that coincide within DUPLICATE_FRACTION of the size; drop unused ones.

    The nodes kept are numbered in their order of first use.
    """
    tolerance = max(_geometry.DUPLICATE_FRACTION * scale, 1e-300)
    keys = numpy.round(verts / tolerance).astype(numpy.int64)
    _, first, inverse = numpy.unique(keys, axis=0, return_index=True, return_inverse=True)
    root = first[inverse.reshape(-1)]
    welded = {n: [[int(root[v]) for v in f] for f in fs] for n, fs in families.items()}
    return _obj.compact(verts, welded)


def _components(work: _Work, faces: dict[str, Faces]) -> dict[str, Faces]:
    """Write each component's members as one family, in the source's family order (FR-425 R4)."""
    owner = {m: c for c, members in work.request.components.items() for m in members}
    out: dict[str, Faces] = {}
    for name in [n for n in work.names if n not in work.bands]:
        out.setdefault(owner.get(name, name), []).extend(faces[name])
    return out


# --------------------------------------------------------------------- writing


def _boundaries_text(work: _Work, stem: str) -> str | None:
    """Return the source's boundaries file naming the new points file and the components.

    The file is read as TOML, and only the two values that change are
    rewritten in place: ``[trailing_edges] file`` and, with components, the
    ``boundaries`` list (FR-425 R4); every other byte, comments included, is
    the source's. Each rewrite is checked by parsing the result, which must
    equal the source's values with those two replaced, so no spelling of
    TOML can make a rewrite land on the wrong text.

    Raises
    ------
    InputArtifactError
        A value the rewrite cannot place; nothing was written. It is called
        before any family is resampled (FR-424 R11).
    """
    read = _obj.read_sidecar(work.source)
    if read is None:
        return None
    side, data = read
    text = side.read_text(encoding="utf-8")
    table = data.get("trailing_edges")
    named = table.get("file") if isinstance(table, dict) else None
    if isinstance(named, str):
        changed = copy.deepcopy(data)
        changed["trailing_edges"]["file"] = f"{stem}{TE_SUFFIX}"
        text = _rewrite(side, text, "file", named, changed)
        data = changed
    owner = {m: c for c, members in work.request.components.items() for m in members}
    listed = data.get("boundaries")
    if owner and isinstance(listed, list) and all(isinstance(n, str) for n in listed):
        names = list(dict.fromkeys(owner.get(n, n) for n in listed))
        changed = copy.deepcopy(data)
        changed["boundaries"] = names
        text = _rewrite(side, text, "boundaries", listed, changed)
    return text


#: The places a value can be closed: a quote of a string or the bracket of an array.
_VALUE_ENDS = re.compile(r"[\"'\]]")


def _rewrite(side: Path, text: str, key: str, old: object, wanted: dict[str, Any]) -> str:
    """Return ``text`` with the value of ``key`` replaced so that it parses to ``wanted``.

    Every spelling of the key (bare, quoted, the last part of a dotted key, a
    member of an inline table) is a candidate; the value after it is the
    shortest text that parses to ``old``; the first replacement whose whole
    file parses to ``wanted`` is the one. The new value is written as JSON
    strings, which are TOML basic strings.
    """
    new = json.dumps(_value_of(wanted, key), ensure_ascii=False)
    spelled = rf"(?<![\w\-\"'])(?:{key}|\"{key}\"|'{key}')\s*=[ \t]*"
    for match in re.finditer(spelled, text):
        start = match.end()
        for end in (m.end() for m in _VALUE_ENDS.finditer(text, start)):
            try:
                value = tomllib.loads("v = " + text[start:end] + "\n")["v"]
            except tomllib.TOMLDecodeError:
                continue
            if value != old:
                continue
            candidate = text[:start] + new + text[end:]
            try:
                if tomllib.loads(candidate) == wanted:
                    return candidate
            except tomllib.TOMLDecodeError:
                pass
            break
    raise _refuse(
        str(side),
        f"the value of {key} cannot be rewritten for the level; state it as "
        f"{key} = {json.dumps(old, ensure_ascii=False)} and run again",
    )


def _value_of(data: dict[str, Any], key: str) -> object:
    """Return the value a rewrite writes: the ``boundaries`` list or the points file name."""
    return data[key] if key == "boundaries" else data["trailing_edges"][key]


def _record(work: _Work, stem: str, counts: Mapping[str, int]) -> dict[str, Any]:
    specs = {
        n: {k: v for k, v in vars(s).items() if v is not None}
        for n, s in work.request.specs.items()
        if n not in work.bands
    }
    periodic = {} if work.periodic is None else {"periodic": work.periodic}
    return {
        "schema_version": _geometry.SCHEMA_VERSION,
        "source": work.source.name,
        "level": stem,
        "config": None if work.request.config is None else work.request.config.name,
        "specs": specs,
        "components": work.request.components,
        "ignored_families_tables": list(work.request.ignored),
        "unchanged_grids": list(work.unchanged),
        "families": {
            n: work.report.get(n, {"method": "copied"}) for n in work.names if n not in work.bands
        },
        "faces": dict(counts),
        **periodic,
    }


def _write(
    work: _Work, folder: Path, verts: Points, faces: dict[str, Faces], te: Points
) -> list[Path]:
    """Write the level's files into ``folder`` and return them, the OBJ first."""
    stem = folder.name.removesuffix(STAGING_SUFFIX)
    mesh = ObjMesh(
        verts, faces, list(work.mesh.header), work.mesh.family_tag, _source_text(work, verts)
    )
    note = f"refined by pyflightstream from {work.source.name}"
    written = [_obj.write_obj(mesh, folder / f"{stem}.obj", note)]
    if len(work.te_points):
        target = folder / f"{stem}{TE_SUFFIX}"
        written.append(_obj.write_te(target, work.te_unit, te * work.te_to_file))
    if work.sidecar is not None:
        target = folder / f"{stem}{_obj.SIDECAR_SUFFIX}"
        _textio.write_text(target, work.sidecar)
        written.append(target)
    record = folder / f"{stem}.refine.json"
    _textio.write_json(
        record, _record(work, stem, {n: len(fs) for n, fs in faces.items()}), indent=1
    )
    written.append(record)
    return written


def _place(source: Path, stem: str, out_dir: str | Path | None, overwrite: bool) -> Path:
    """Return the level folder, refusing an existing one unless ``overwrite`` (FR-424 R5)."""
    root = Path(out_dir) if out_dir is not None else source.parent.parent
    folder = root / stem
    if folder.resolve() == source.parent.resolve():
        raise _refuse(
            str(folder),
            "the level folder is the source's folder; choose another out_dir (CLI: --out-dir)",
        )
    if folder.exists() and not overwrite:
        raise _refuse(
            str(folder), "the level exists; give overwrite=True (--overwrite) to replace it"
        )
    return folder


# ---------------------------------------------------------------------- entry


def refine_mesh(  # noqa: PLR0913 (one keyword per option of the command)
    mesh: str | os.PathLike[str],
    factor: float | None = None,
    *,
    families: Sequence[str] | None = None,
    chordwise: float | None = None,
    spanwise: float | None = None,
    config: str | Path | None = None,
    out_dir: str | Path | None = None,
    overwrite: bool = False,
) -> RefinedMesh:
    """Refine or coarsen a panel mesh from its OBJ into a new geometry folder (FR-424, FR-425).

    Parameters
    ----------
    mesh : path-like
        The source OBJ; it and its folder are never modified.
    factor : float, optional
        The factor of every selected family; without it, and without
        ``chordwise`` or ``spanwise``, the factors come from the refinement file.
    families : sequence of str, optional
        The families to change (default: every family).
    chordwise, spanwise : float, optional
        The factor of one index direction of every selected grid family.
    config : path-like, optional
        The refinement file (default: ``<stem>.refine.toml`` beside the mesh).
    out_dir : path-like, optional
        Where the level folder goes (default: the parent of the source's folder).
    overwrite : bool
        Replace an existing level folder.

    Returns
    -------
    RefinedMesh
        The level folder, its files, the per-family report and the audit.

    Raises
    ------
    InputArtifactError
        Every refusal of FR-424 and FR-425, before any file is written.
    MissingExtraError
        A family must be remeshed and the geometry extra is missing (FR-424 R10).

    Examples
    --------
    >>> from pyflightstream.workspace import refine_mesh
    >>> level = refine_mesh("geometries/W1/W1.obj", 2)  # doctest: +SKIP
    >>> level.folder.name  # doctest: +SKIP
    'W1_R2'
    """
    source = Path(mesh)
    obj = _obj.read_obj(source)
    request = _config.resolve_request(
        source,
        list(obj.families),
        factor=factor,
        families=families,
        chordwise=chordwise,
        spanwise=spanwise,
        config=config,
    )
    stem = f"{source.stem}_{_config.level_tag(request, list(obj.families))}"
    folder = _place(source, stem, out_dir, overwrite)
    work = _start(source, request, obj)
    work.sidecar = _boundaries_text(work, stem)
    where = f"{source} [periodic]"
    work.cuts = _periodic.find_cuts(
        obj.verts, obj.families, request.periodic, size=work.scale, where=where
    )
    _decide(work)
    _refine_grids(work)
    _bands(work)
    _conform_cuts(work)
    _remesh_groups(work)
    verts, faces, te = _assemble(work)
    verts, work.periodic = _periodic.match_level(
        verts, faces, work.cuts, request.periodic, source=obj.verts, size=work.scale, where=where
    )
    faces = _components(work, faces)
    work.unchanged = _unchanged_grids(work, list(faces))
    unchanged = work.unchanged
    staging = folder.with_name(folder.name + STAGING_SUFFIX)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        written = _write(work, staging, verts, faces, te)
        audit = audit_mesh(written[0], against=source, unchanged_grids=unchanged)
        _publish(staging, folder)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    files = tuple(folder / p.name for p in (*written, audit.path))
    audit = dataclasses.replace(audit, mesh=files[0], path=files[-1])
    report = json.loads(files[-2].read_text(encoding="utf-8"))["families"]
    return RefinedMesh(folder=folder, obj=files[0], files=files, report=report, audit=audit)


def _unchanged_grids(work: _Work, families: list[str]) -> list[str]:
    """Return the level's families G6 compares with the source's (FR-426 R2, FR-424 R7).

    A grid family written at factor 1, and a component whose every member is
    one, in the level's family order. ``refine.json`` lists them, so the
    audit of a saved level judges G6 as the refinement's own audit does.
    """
    ones = {n for n in work.grids if work.request.specs[n].directions == (1.0, 1.0)}
    components = work.request.components
    return [
        n
        for n in families
        if (n in components and all(m in ones for m in components[n]))
        or (n not in components and n in ones)
    ]


def _publish(staging: Path, folder: Path) -> None:
    """Rename the complete, audited staging folder to the level (FR-424 R5).

    An existing level is moved aside first and removed only once the new one
    is in place; if the rename fails, it is put back. A path that is not a
    folder is never replaced.
    """
    previous = folder.with_name(folder.name + PREVIOUS_SUFFIX)
    shutil.rmtree(previous, ignore_errors=True)
    if folder.exists() and not folder.is_dir():
        raise FileExistsError(f"{folder} exists and is not a level folder; it was not replaced")
    if folder.exists():
        folder.rename(previous)
    try:
        staging.rename(folder)
    except BaseException:
        if previous.exists() and not folder.exists():
            previous.rename(folder)
        raise
    shutil.rmtree(previous, ignore_errors=True)
