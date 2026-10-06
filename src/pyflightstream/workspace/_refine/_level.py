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
   (FR-425 R4), and write the level into a temporary folder renamed once
   complete (FR-424 R4, R5).
"""

from __future__ import annotations

import json
import os
import re
import shutil
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
TE_SUFFIX = ".te.txt"
#: The folder a level is written into before it is renamed to its own name (FR-424 R5).
STAGING_SUFFIX = ".partial"


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
    te_points: Points
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


def _refuse(where: str, reason: str) -> InputArtifactError:
    return InputArtifactError(f"{where}: {reason}. Nothing was written.", kind=_obj.KIND)


# --------------------------------------------------------------------- reading


def _te_file(source: Path) -> Path | None:
    """Return the trailing-edge points file the boundaries file names, else ``<stem>.te.txt``."""
    side = source.with_name(source.stem + ".boundaries.toml")
    if side.is_file():
        match = re.search(r'(?m)^\s*file\s*=\s*"([^"]+)"', side.read_text(encoding="utf-8"))
        if match and source.with_name(match.group(1)).is_file():
            return source.with_name(match.group(1))
    beside = source.with_name(source.stem + TE_SUFFIX)
    return beside if beside.is_file() else None


def _te_vertices(mesh: ObjMesh, family: str, points: Points, scale: float) -> set[int]:
    """Return the trailing-edge vertices: the ends of the edges whose mid-point is listed."""
    if not len(points):
        return set()
    edges, mid = _obj.edge_midpoints(mesh.verts, mesh.families[family])
    dist, index = NearestIndex(mid).query(points)
    hit = dist < 1e-6 * scale
    return {int(v) for v in edges[index[hit]].ravel()}


def _start(source: Path, request: RefineRequest, mesh: ObjMesh) -> _Work:
    te = _te_file(source)
    unit, points = _obj.read_te(te) if te else ("METER", numpy.zeros((0, 3)))
    scale = mesh.size
    names = list(mesh.families)
    return _Work(
        source=source,
        mesh=mesh,
        request=request,
        te_unit=unit,
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
    if work.remesh:
        from pyflightstream.workspace._refine._remesh import require_geometry_extra

        require_geometry_extra(work.remesh)


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
    (``old``); a new node is on it when it lies within a quarter of a
    segment's length from one of those edges.
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
        if d[j] < 0.25 * length[j]:
            keep.append(v)
    return level.points[keep] if keep else None


def _unchanged_curve(work: _Work, old: set[int], new: Points) -> bool:
    """Return whether the grid kept exactly the source nodes of a shared curve."""
    olds = work.mesh.verts[sorted(old)]
    return (
        len(new) == len(olds) and float(NearestIndex(olds).query(new)[0].max()) < 1e-9 * work.scale
    )


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


def _te_points_of(work: _Work, name: str) -> NDArray[numpy.bool_]:
    """Return which listed trailing-edge points lie on an edge of the family."""
    if not len(work.te_points):
        return numpy.zeros(0, dtype=bool)
    _, mid = _obj.edge_midpoints(work.mesh.verts, work.mesh.families[name])
    dist, _ = NearestIndex(mid).query(work.te_points)
    return dist < 1e-6 * work.scale


def _weld(
    verts: Points, families: dict[str, Faces], scale: float
) -> tuple[Points, dict[str, Faces]]:
    """Weld nodes that coincide within 1e-9 of the size; drop unused ones, in order of first use."""
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
    """Return the source's boundaries file naming the new points file and the components."""
    side = work.source.with_name(work.source.stem + ".boundaries.toml")
    if not side.is_file():
        return None
    text = side.read_text(encoding="utf-8")
    te = _te_file(work.source)
    if te is not None:
        text = text.replace(f'"{te.name}"', f'"{stem}{TE_SUFFIX}"')
    owner = {m: c for c, members in work.request.components.items() for m in members}
    match = re.search(r"boundaries\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if match and owner:
        names: list[str] = []
        for n in re.findall(r'"([^"]+)"', match.group(1)):
            if owner.get(n, n) not in names:
                names.append(owner.get(n, n))
        listed = "boundaries = [" + ", ".join(f'"{n}"' for n in names) + "]"
        text = text[: match.start()] + listed + text[match.end() :]
    return text


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
    mesh = ObjMesh(verts, faces, list(work.mesh.header), work.mesh.family_tag)
    note = f"refined by pyflightstream from {work.source.name}"
    written = [_obj.write_obj(mesh, folder / f"{stem}.obj", note)]
    if len(work.te_points):
        written.append(_obj.write_te(folder / f"{stem}{TE_SUFFIX}", work.te_unit, te))
    text = _boundaries_text(work, stem)
    if text is not None:
        target = folder / f"{stem}.boundaries.toml"
        _textio.write_text(target, text)
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
    staging = folder.with_name(folder.name + STAGING_SUFFIX)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        written = _write(work, staging, verts, faces, te)
        if folder.exists():
            shutil.rmtree(folder)
        staging.rename(folder)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    files = tuple(folder / p.name for p in written)
    report = json.loads(files[-1].read_text(encoding="utf-8"))["families"]
    merged = {m for members in work.request.components.values() for m in members}
    unchanged = [
        n for n in work.grids if work.request.specs[n].directions == (1.0, 1.0) and n not in merged
    ]
    audit = audit_mesh(files[0], against=source, unchanged_grids=unchanged)
    files = (*files, audit.path)
    return RefinedMesh(folder=folder, obj=files[0], files=files, report=report, audit=audit)
