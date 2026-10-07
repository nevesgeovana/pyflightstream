"""The audit of a panel mesh, alone or against its source (FR-426).

THREE KINDS OF RESULT. A GATE (R2) is judged on its own terms: the topology,
the orientation, the open boundary, the trailing edge, the shared nodes and
the faces a grid family at factor 1 keeps. A RELATIVE CHECK (R3) compares a
95th percentile of the level with the source's, because the source is the
accepted mesh. A FIGURE (R4) is reported and never judged. Without a
source only G1, G2 and G4 are judged and the rest is reported (R5).

HOW IT MEASURES. Every measure is computed once on all the faces of a mesh
and read per family through the family of each face; an edge belongs to a
family when both its faces do. The audit needs numpy alone and imports
nothing of the refinement modules (FR-424 R10, R14), so it judges a level
without them.

WHAT IT WRITES. ``<stem>.audit.json`` beside the mesh audited (a level's
stem is ``<stem>_<tag>``), with ``schema_version``, through the package's one
text route; a gate or check that fails is a warning naming it, the family and
its values. The trailing-edge points file of a mesh is the one its
``<stem>.boundaries.toml`` names under ``[trailing_edges] file``, or else
``<stem>.te.txt`` beside it; its points are converted from the unit on its
first line to the mesh's (the ``[import] units`` of the boundaries file)
before they are matched to the mesh's edges.
"""

from __future__ import annotations

import json
import os
import warnings
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy
from numpy.typing import NDArray

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace._refine._geometry import (
    ASPECT_LIMIT,
    CHECK_TOLERANCE,
    DUPLICATE_FRACTION,
    GROWTH_DIHEDRAL_DEGREES,
    GROWTH_FLOOR,
    OPENING_FRACTION,
    PANEL_PRACTICE_COUNTS,
    PERCENTILE,
    QUALITY_GOOD,
    SCHEMA_VERSION,
    SKEWNESS_MARGIN,
    TE_POINT_FRACTION,
    WARP_FLOOR_DEGREES,
    ZERO_AREA_FRACTION,
    NearestIndex,
    boundary_edges,
    boundary_loops,
    close_pairs,
    dihedral_degrees,
    edge_faces,
    normals_and_centroids,
    segment_distances,
    triangles,
)
from pyflightstream.workspace._refine._obj import (
    KIND,
    SIDECAR_SUFFIX,
    ObjMesh,
    edge_midpoints,
    read_obj,
    te_file,
    te_points,
)

Faces = list[list[int]]
Value = float | int | str | bool | None
Array = NDArray[Any]

#: The family name a result on all the faces of the mesh carries.
WHOLE_MESH = "(whole mesh)"
#: The verdicts of a gate or a check.
PASS, FAIL, NOT_JUDGED = "pass", "fail", "not judged"
#: The suffix of the audit written beside the mesh.
AUDIT_SUFFIX = ".audit.json"
#: The suffix of a level's refinement record, beside it, which the audit reads.
RECORD_SUFFIX = ".refine.json"
#: The relative checks of R3: the name and the figure each compares.
CHECKS = (("skewness", "skewness_p95"), ("warp", "warp_p95"), ("growth", "growth_p95"))
_TINY = 1e-300


@dataclass(frozen=True)
class AuditItem:
    """One gate or relative check: its name, the family, its values and its verdict."""

    kind: str
    name: str
    family: str
    values: Mapping[str, Value]
    verdict: str

    @property
    def passed(self) -> bool:
        """Return whether the item did not fail (a result not judged did not fail)."""
        return self.verdict != FAIL

    def warning(self) -> str:
        """Return the warning of a failed item: its name, the family and its values."""
        said = ", ".join(f"{key} {_said(value)}" for key, value in self.values.items())
        return f"audit {self.kind} {self.name} failed on {self.family}: {said}"

    def line(self) -> str:
        """Return the console line of the item."""
        said = ", ".join(f"{key} {_said(value)}" for key, value in self.values.items())
        return f"{self.name} {self.verdict} on {self.family}: {said}"

    def as_json(self) -> dict[str, object]:
        """Return the item as written in ``audit.json``."""
        return {
            "name": self.name,
            "family": self.family,
            "verdict": self.verdict,
            "values": dict(self.values),
        }


@dataclass(frozen=True)
class MeshAudit:
    """The audit of one mesh, alone or against its source (FR-426).

    Attributes
    ----------
    mesh : Path
        The OBJ audited.
    source : Path or None
        The source it was audited against, or None (FR-426 R5).
    gates : tuple of AuditItem
        G1 to G6 (R2), each with its family, its values and its verdict.
    checks : tuple of AuditItem
        The relative checks of R3, per family and on the whole mesh.
    figures : Mapping
        Per family (and ``"(whole mesh)"``), each reported figure (R4) and the
        95th percentiles the checks read.
    path : Path
        The ``<stem>.audit.json`` written beside the mesh.
    """

    mesh: Path
    source: Path | None
    gates: tuple[AuditItem, ...]
    checks: tuple[AuditItem, ...]
    figures: Mapping[str, Mapping[str, Value]]
    path: Path

    @property
    def passed(self) -> bool:
        """Return whether every gate and every check passed or was not judged."""
        return not self.failures

    @property
    def failures(self) -> tuple[AuditItem, ...]:
        """Return the gates and checks that failed, gates first."""
        return tuple(item for item in self.gates + self.checks if not item.passed)

    def as_json(self) -> dict[str, object]:
        """Return the audit as written in ``audit.json`` (``schema_version`` 1)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "mesh": self.mesh.name,
            "source": None if self.source is None else self.source.name,
            "passed": self.passed,
            "gates": [item.as_json() for item in self.gates],
            "checks": [item.as_json() for item in self.checks],
            "figures": {family: dict(values) for family, values in self.figures.items()},
        }

    def summary(self) -> list[str]:
        """Return the console summary: each gate, the checks counted, each failure."""
        against = "alone" if self.source is None else f"against {self.source.name}"
        lines = [f"audit of {self.mesh.name} {against}"]
        lines += [item.line() for item in self.gates]
        counts = Counter(item.verdict for item in self.checks)
        lines.append(
            f"relative checks: {counts[PASS]} pass, {counts[FAIL]} fail, "
            f"{counts[NOT_JUDGED]} not judged"
        )
        lines += [item.line() for item in self.checks if not item.passed]
        lines.append("every gate and check passed" if self.passed else "the audit FAILED")
        return lines

    def write_csv(self, path: str | Path) -> Path:
        """Write one row per family and figure (``--csv``) and return the path."""
        target = Path(path)
        rows = (
            [family, figure, "" if value is None else str(value)]
            for family, values in self.figures.items()
            for figure, value in values.items()
        )
        _textio.write_csv(target, rows, header=("family", "figure", "value"))
        return target


@dataclass(frozen=True)
class _Trailing:
    """The trailing edge of a mesh: its points, those on an edge, its chains, its faces."""

    present: bool
    points: int
    on_edges: int
    chains: int
    faces: Array


@dataclass(frozen=True)
class _Mesh:
    """Every measure of one mesh, computed once on all its faces."""

    obj: ObjMesh
    faces: Faces
    family: Array
    size: float
    shape: Mapping[str, Array]
    pair: Array
    dihedral: Array
    flipped: int
    nonmanifold: int
    trailing: _Trailing


def audit_mesh(
    mesh: str | Path,
    *,
    against: str | Path | None = None,
    unchanged_grids: Sequence[str] = (),
) -> MeshAudit:
    """Audit an OBJ, alone or against its source, and write its audit beside it.

    Parameters
    ----------
    mesh : str or Path
        The OBJ to audit; its trailing-edge points file is the one its
        ``<stem>.boundaries.toml`` names, or else ``<stem>.te.txt``.
    against : str or Path, optional
        The source the mesh was made from. Without it only G1, G2 and G4 are
        judged and the rest is reported (FR-426 R5).
    unchanged_grids : sequence of str, optional
        The grid families a refinement wrote at factor 1, whose faces G6
        compares with the source's. Without them they are read from the
        level's ``<stem>.refine.json`` when it names this level and the
        source ``against`` (its ``unchanged_grids``), so a saved level is
        re-audited as the refinement audited it; with neither, G6 is not
        judged.

    Returns
    -------
    MeshAudit
        Each gate and check with its values and verdict, the figures, and
        ``passed``. ``<stem>.audit.json`` is written beside the mesh whatever
        the verdict, and each failed gate or check is a warning.

    Raises
    ------
    InputArtifactError
        A mesh or source that is not a readable OBJ, or a trailing-edge points
        file named and missing or malformed; nothing is written.
    """
    level = _read(Path(mesh))
    record = _record_of(Path(mesh))
    components = _components_of(record)
    source = None if against is None else _read(Path(against), components)
    target = Path(mesh).with_name(Path(mesh).stem + AUDIT_SUFFIX)
    _refuse_an_input_as_target(target, Path(mesh), None if against is None else Path(against))
    grids = tuple(unchanged_grids) or _recorded_grids(record, Path(mesh), against)
    gates = _gates(level, source, grids)
    figures = dict(_all_figures(level))
    checks = tuple(_checks(figures, None if source is None else dict(_all_figures(source))))
    audit = MeshAudit(
        mesh=Path(mesh),
        source=None if against is None else Path(against),
        gates=gates,
        checks=checks,
        figures=MappingProxyType(
            {name: MappingProxyType(values) for name, values in figures.items()}
        ),
        path=target,
    )
    _textio.write_json(target, audit.as_json())
    for item in audit.failures:
        warnings.warn(item.warning(), PyflightstreamWarning, stacklevel=2)
    return audit


def _refusal(subject: Path, reason: str, remedy: str) -> InputArtifactError:
    """Return a refusal naming the file, the reason and the remedy; nothing was written."""
    return InputArtifactError(f"{subject}: {reason}. {remedy} Nothing was written.", kind=KIND)


def _inputs(mesh: Path, against: Path | None) -> list[tuple[str, Path]]:
    """Return the files the audit of ``mesh`` reads, each with what it is (FR-426 R1).

    The OBJ, its boundaries file, its trailing-edge points file and its
    ``refine.json``; with ``against``, the source, its boundaries file and
    its points file. Call it once both meshes were read, so their boundaries
    files are known to be readable.
    """
    files = [
        ("the OBJ", mesh),
        ("its boundaries file", mesh.with_name(mesh.stem + SIDECAR_SUFFIX)),
        ("its refinement record", mesh.with_name(mesh.stem + RECORD_SUFFIX)),
    ]
    points = te_file(mesh)
    if points is not None:
        files.append(("its trailing-edge points file", points))
    if against is not None:
        files += [
            ("the source", against),
            ("the source's boundaries file", against.with_name(against.stem + SIDECAR_SUFFIX)),
        ]
        points = te_file(against)
        if points is not None:
            files.append(("the source's trailing-edge points file", points))
    return files


def _same_file(a: Path, b: Path) -> bool:
    """Return whether two paths name one file: one spelling, or one file on disk."""
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
        return os.path.normcase(a.resolve()) == os.path.normcase(b.resolve())
    except OSError:
        return False


def _refuse_an_input_as_target(target: Path, mesh: Path, against: Path | None) -> None:
    """Refuse an audit JSON that is a file the audit reads, before anything is written (R1)."""
    for what, path in _inputs(mesh, against):
        if _same_file(target, path):
            raise _refusal(
                target,
                f"the audit JSON would be written over {what}, {path}, which the audit reads",
                "Rename or move the mesh, or the file it would overwrite, and run again.",
            )


def _read(path: Path, components: Mapping[str, Sequence[str]] | None = None) -> _Mesh:
    """Read an OBJ and its trailing-edge points and measure them.

    With ``components``, the families each component lists are measured as
    that one family, so a level whose families were grouped into components
    (FR-425 R4) is compared with the union of its members in the source.
    """
    if not path.is_file():
        raise _refusal(path, "no such OBJ file", "Name an existing OBJ and run again.")
    obj = read_obj(path)
    if components:
        obj = _grouped(obj, components)
    te = te_points(path)
    points = None if te is None else te.points
    return _measure(obj, points)


def _record_of(level: Path) -> dict[str, Any]:
    """Return the level's ``refine.json`` (an empty record when there is none or it is not JSON)."""
    path = level.with_name(level.stem + RECORD_SUFFIX)
    if not path.is_file():
        return {}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return record if isinstance(record, dict) else {}


def _components_of(record: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return the components a refinement recorded in the level's ``refine.json``, if any."""
    found = record.get("components")
    if not isinstance(found, dict):
        return {}
    return {
        str(c): [str(m) for m in members]
        for c, members in found.items()
        if isinstance(members, list)
    }


def _recorded_grids(
    record: Mapping[str, Any], level: Path, against: str | Path | None
) -> tuple[str, ...]:
    """Return the grid families the refinement wrote at factor 1, which G6 compares (R2).

    They are read only from a record that names this level's stem and the
    source it is audited against, so a record of another refinement is not
    taken for this one's.
    """
    found = record.get("unchanged_grids")
    if against is None or record.get("level") != level.stem:
        return ()
    if record.get("source") != Path(against).name or not isinstance(found, list):
        return ()
    return tuple(n for n in found if isinstance(n, str))


def _grouped(obj: ObjMesh, components: Mapping[str, Sequence[str]]) -> ObjMesh:
    """Return the mesh with each component's member families merged, in the source's order."""
    owner = {m: c for c, members in components.items() for m in members}
    families: dict[str, list[list[int]]] = {}
    for name, faces in obj.families.items():
        families.setdefault(owner.get(name, name), []).extend(faces)
    return ObjMesh(obj.verts, families, obj.header, obj.family_tag)


def _measure(obj: ObjMesh, points: Array | None) -> _Mesh:
    """Measure every face and interior edge of a mesh once."""
    faces = [f for fs in obj.families.values() for f in fs]
    family = numpy.repeat(
        numpy.arange(len(obj.families)), [len(fs) for fs in obj.families.values()]
    )
    ef = edge_faces(faces)
    keys = [e for e, fs in ef.items() if len(fs) == 2]
    directed = Counter((a, b) for f in faces for a, b in zip(f, f[1:] + f[:1], strict=True))
    dihedral = dihedral_degrees(obj.verts, faces)
    size = obj.size
    return _Mesh(
        obj=obj,
        faces=faces,
        family=family,
        size=size,
        shape=_face_shapes(obj.verts, faces),
        pair=numpy.array([ef[e] for e in keys], dtype=numpy.int64).reshape(-1, 2),
        dihedral=numpy.array([dihedral[e] for e in keys], dtype=float),
        flipped=sum(directed[e] != 1 for e in keys),
        nonmanifold=sum(len(fs) > 2 for fs in ef.values()),
        trailing=_trailing(obj.verts, faces, ef, points, size),
    )


def _face_shapes(verts: Array, faces: Faces) -> dict[str, Array]:
    """Return every per-face measure, polygons of one vertex count at a time."""
    n = len(faces)
    shape = {
        key: numpy.full(n, numpy.nan)
        for key in ("aspect", "skewness", "warp", "quad_min_angle", "tri_min_angle")
    }
    shape.update(perimeter=numpy.zeros(n), max_abs_y=numpy.zeros(n))
    sides = numpy.array([len(f) for f in faces])
    for count in numpy.unique(sides):
        rows = numpy.nonzero(sides == count)[0]
        _polygon_shapes(verts[numpy.array([faces[r] for r in rows])], rows, shape)
    normals, _ = normals_and_centroids(verts, faces)
    shape["area"] = 0.5 * numpy.linalg.norm(normals, axis=1)
    shape["sides"] = sides
    return shape


def _polygon_shapes(p: Array, rows: Array, shape: dict[str, Array]) -> None:
    """Fill the measures of polygons of one vertex count (``p`` is faces by vertices by 3)."""
    edge = numpy.roll(p, -1, axis=1) - p
    length = numpy.linalg.norm(edge, axis=2)
    shape["aspect"][rows] = length.max(axis=1) / numpy.maximum(length.min(axis=1), _TINY)
    shape["perimeter"][rows] = length.sum(axis=1)
    shape["max_abs_y"][rows] = numpy.abs(p[:, :, 1]).max(axis=1)
    before = numpy.roll(edge, 1, axis=1)
    cosine = -(edge * before).sum(axis=2) / numpy.maximum(
        length * numpy.roll(length, 1, axis=1), _TINY
    )
    angle = numpy.degrees(numpy.arccos(numpy.clip(cosine, -1.0, 1.0)))
    n = p.shape[1]
    ideal = 180.0 * (n - 2) / n
    shape["skewness"][rows] = numpy.maximum(
        (angle.max(axis=1) - ideal) / (180.0 - ideal), (ideal - angle.min(axis=1)) / ideal
    )
    if n == 3:
        shape["tri_min_angle"][rows] = angle.min(axis=1)
    if n == 4:
        shape["quad_min_angle"][rows] = angle.min(axis=1)
        shape["warp"][rows] = _warp(p)


def _warp(p: Array) -> Array:
    """Return each quadrilateral's warp: the larger fold between the triangles of a diagonal."""
    folds = []
    for d in (0, 1):
        a, b, c, e = (p[:, (d + k) % 4] for k in range(4))
        n1 = numpy.cross(b - a, c - a)
        n2 = numpy.cross(c - a, e - a)
        cosine = (n1 * n2).sum(axis=1) / numpy.maximum(
            numpy.linalg.norm(n1, axis=1) * numpy.linalg.norm(n2, axis=1), _TINY
        )
        folds.append(numpy.degrees(numpy.arccos(numpy.clip(cosine, -1.0, 1.0))))
    return numpy.maximum(folds[0], folds[1])


def _trailing(
    verts: Array,
    faces: Faces,
    ef: Mapping[tuple[int, int], list[int]],
    points: Array | None,
    size: float,
) -> _Trailing:
    """Match each trailing-edge point to the mesh edge whose mid-point it is (G4)."""
    touched = numpy.zeros(len(faces), dtype=bool)
    if points is None or not len(points):
        return _Trailing(points is not None, 0, 0, 0, touched)
    edges, mids = edge_midpoints(verts, faces)
    distance, nearest = NearestIndex(mids).query(points)
    on = edges[nearest[distance <= TE_POINT_FRACTION * size]]
    for a, b in on:
        touched[ef[(int(a), int(b))]] = True
    return _Trailing(True, len(points), len(on), _components(on), touched)


def _components(edges: Array) -> int:
    """Return the number of connected chains the edges form."""
    parent: dict[int, int] = {}

    def root(v: int) -> int:
        while parent.setdefault(v, v) != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for a, b in edges:
        parent[root(int(a))] = root(int(b))
    return len({root(v) for v in list(parent)})


def _p95(values: Array) -> float | None:
    """Return the 95th percentile (linear interpolation between ranks), or None when empty."""
    values = values[~numpy.isnan(values)]
    return float(numpy.percentile(values, PERCENTILE, method="linear")) if len(values) else None


def _selections(m: _Mesh) -> Iterator[tuple[str, Array, Array]]:
    """Yield each family, then the whole mesh, with its face mask and its edge mask."""
    for k, name in enumerate(m.obj.families):
        inside = m.family == k
        yield name, inside, inside[m.pair[:, 0]] & inside[m.pair[:, 1]]
    yield WHOLE_MESH, numpy.ones(len(m.faces), dtype=bool), numpy.ones(len(m.pair), dtype=bool)


def _all_figures(m: _Mesh) -> Iterator[tuple[str, dict[str, Value]]]:
    """Yield each family's figures, then the whole mesh's."""
    growth, quality = _neighbour_ratios(m)
    for name, faces, edges in _selections(m):
        yield name, _figures(m, faces, edges, growth, quality)


def _neighbour_ratios(m: _Mesh) -> tuple[Array, Array]:
    """Return the area ratio of every smooth interior edge and each face's quality ratio.

    The size growth is the larger area over the smaller across an edge whose
    dihedral is below the growth limit, NaN elsewhere; the face quality ratio
    is the largest ratio of inscribed radii (twice the area over the
    perimeter) between a face and its neighbours, 1 for a face with none.
    """
    area = m.shape["area"]
    a, b = m.pair[:, 0], m.pair[:, 1]
    growth = numpy.maximum(area[a], area[b]) / numpy.maximum(numpy.minimum(area[a], area[b]), _TINY)
    growth[m.dihedral >= GROWTH_DIHEDRAL_DEGREES] = numpy.nan
    radius = 2.0 * area / numpy.maximum(m.shape["perimeter"], _TINY)
    ratio = numpy.maximum(radius[a], radius[b]) / numpy.maximum(
        numpy.minimum(radius[a], radius[b]), _TINY
    )
    quality = numpy.ones(len(m.faces))
    numpy.maximum.at(quality, a, ratio)
    numpy.maximum.at(quality, b, ratio)
    return growth, quality


def _figures(
    m: _Mesh, faces: Array, edges: Array, growth: Array, quality: Array
) -> dict[str, Value]:
    """Return the figures of one selection of faces and edges (R4 and the checks' figures)."""
    shape = m.shape
    aspect = shape["aspect"][faces]
    out: dict[str, Value] = {
        "faces": int(faces.sum()),
        "triangles": int((shape["sides"][faces] == 3).sum()),
        "quadrilaterals": int((shape["sides"][faces] == 4).sum()),
        "skewness_p95": _p95(shape["skewness"][faces]),
        "warp_p95": _p95(shape["warp"][faces]),
        "growth_p95": _p95(growth[edges]),
        "aspect_p95": _p95(aspect),
        "aspect_max": float(aspect.max()) if len(aspect) else None,
    }
    for figure, measure, above, limit in PANEL_PRACTICE_COUNTS:
        x = shape[measure][faces]
        out[figure] = int((x > limit).sum() if above else (x < limit).sum())
    out["quality_ratio_p95"] = _p95(quality[faces])
    out["quality_ratio_over_2"] = int((quality[faces] > QUALITY_GOOD).sum())
    out["aspect_over_50"] = int((aspect > ASPECT_LIMIT).sum())
    sliver = m.trailing.faces & (shape["sides"] == 3) & (shape["aspect"] > ASPECT_LIMIT)
    out["trailing_edge_triangles_aspect_over_50"] = int(sliver[faces].sum())
    plane = shape["max_abs_y"] <= DUPLICATE_FRACTION * m.size
    out["faces_on_y0_plane"] = int(plane[faces].sum())
    return out


def _item(kind: str, name: str, family: str, values: dict[str, Value], failed: bool) -> AuditItem:
    """Return a judged item."""
    return AuditItem(kind, name, family, MappingProxyType(values), FAIL if failed else PASS)


def _reported(kind: str, name: str, family: str, values: dict[str, Value]) -> AuditItem:
    """Return an item reported and not judged."""
    return AuditItem(kind, name, family, MappingProxyType(values), NOT_JUDGED)


def _gates(level: _Mesh, source: _Mesh | None, grids: tuple[str, ...]) -> tuple[AuditItem, ...]:
    """Return G1 to G6 in order (R2), the source-relative ones reported without a source."""
    return (
        _g1(level),
        *_g2(level),
        _g3(level, source),
        _g4(level, source),
        *_g5(level, source),
        *_g6(level, source, grids),
    )


def _g1(m: _Mesh) -> AuditItem:
    """G1: no edge of more than two faces, no two nodes at one position, no face of zero area."""
    used = numpy.unique(numpy.fromiter((v for f in m.faces for v in f), dtype=numpy.int64))
    values: dict[str, Value] = {
        "edges_of_more_than_two_faces": m.nonmanifold,
        "node_pairs_at_one_position": len(
            close_pairs(m.obj.verts[used], DUPLICATE_FRACTION * m.size)
        ),
        "faces_of_zero_area": int((m.shape["area"] < ZERO_AREA_FRACTION * m.size**2).sum()),
    }
    return _item("gate", "G1", WHOLE_MESH, values, any(v != 0 for v in values.values()))


def _volume(verts: Array, faces: Faces) -> float | None:
    """Return the volume a closed set of faces encloses (right-hand rule), None when open."""
    if boundary_edges(faces):
        return None
    p = verts[triangles(faces)]
    return float(numpy.einsum("ij,ij->i", p[:, 0], numpy.cross(p[:, 1], p[:, 2])).sum() / 6.0)


def _g2(m: _Mesh) -> Iterator[AuditItem]:
    """G2: no two neighbours of opposite orientation; a closed family encloses a positive volume."""
    yield _item(
        "gate", "G2", WHOLE_MESH, {"neighbours_of_opposite_orientation": m.flipped}, m.flipped > 0
    )
    for name, faces in m.obj.families.items():
        volume = _volume(m.obj.verts, faces)
        if volume is not None:
            yield _item("gate", "G2", name, {"enclosed_volume": volume}, volume <= 0.0)


def _unmatched_loops(level: _Mesh, source: _Mesh) -> int:
    """Return how many open loops of either mesh close no opening of the other.

    Each level loop is offered the source loops its nodes are nearest to,
    most votes first, and takes the first not yet taken that closes the same
    opening (:func:`_same_opening`), so the match is one to one and spatial;
    the count is the loops of both meshes left without a partner.
    """
    old, new = boundary_loops(source.faces), boundary_loops(level.faces)
    if not old or not new:
        return len(old) + len(new)
    label = numpy.repeat(numpy.arange(len(old)), [len(loop) for loop in old])
    index = NearestIndex(source.obj.verts[numpy.concatenate(old)])
    taken: set[int] = set()
    for loop in new:
        points = level.obj.verts[loop]
        votes = numpy.bincount(label[index.query(points)[1]], minlength=len(old))
        for k in numpy.argsort(-votes, kind="stable"):
            if votes[k] == 0:
                break
            if int(k) not in taken and _same_opening(points, source.obj.verts[old[k]]):
                taken.add(int(k))
                break
    return (len(new) - len(taken)) + (len(old) - len(taken))


def _same_opening(mine: Array, theirs: Array) -> bool:
    """Return whether two closed loops bound the same opening (FR-425 R5).

    Every node of each lies within :data:`OPENING_FRACTION` of the source
    loop's extent from the other's polyline, so the loops coincide up to the
    resampling of their segments.
    """
    extent = float(numpy.linalg.norm(numpy.ptp(theirs, axis=0)))
    limit = OPENING_FRACTION * max(extent, _TINY)
    for points, loop in ((mine, theirs), (theirs, mine)):
        distance, _ = segment_distances(points, loop, numpy.roll(loop, -1, axis=0))
        if float(distance.max()) > limit:
            return False
    return True


def _g3(level: _Mesh, source: _Mesh | None) -> AuditItem:
    """G3: the open boundary loops of the level are the source's (FR-425 R5)."""
    loops = len(boundary_loops(level.faces))
    if source is None:
        return _reported("gate", "G3", WHOLE_MESH, {"open_loops": loops})
    values: dict[str, Value] = {
        "open_loops": loops,
        "source_open_loops": len(boundary_loops(source.faces)),
        "unmatched_loops": _unmatched_loops(level, source),
    }
    failed = values["open_loops"] != values["source_open_loops"] or values["unmatched_loops"] != 0
    return _item("gate", "G3", WHOLE_MESH, values, failed)


def _g4(level: _Mesh, source: _Mesh | None) -> AuditItem:
    """G4: every trailing-edge point on a mesh edge, and the source's number of chains."""
    te = level.trailing
    values: dict[str, Value] = {
        "points": te.points,
        "points_on_edges": te.on_edges,
        "chains": te.chains,
    }
    failed = te.on_edges < te.points
    if source is not None:
        values["source_chains"] = source.trailing.chains
        failed = failed or te.chains != source.trailing.chains
    return _item("gate", "G4", WHOLE_MESH, values, failed)


def _shared(obj: ObjMesh, a: str, b: str) -> int:
    """Return the number of nodes two families of a mesh share."""
    return len(numpy.intersect1d(obj.family_vertices(a), obj.family_vertices(b)))


def _sharing_pairs(obj: ObjMesh) -> Iterator[tuple[str, str, int]]:
    """Yield each pair of families sharing nodes, in family order, with the count."""
    names = list(obj.families)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if count := _shared(obj, a, b):
                yield a, b, count


def _g5(level: _Mesh, source: _Mesh | None) -> Iterator[AuditItem]:
    """G5: families that shared nodes in the source still share them."""
    if source is None:
        pairs = sum(1 for _ in _sharing_pairs(level.obj))
        yield _reported("gate", "G5", WHOLE_MESH, {"family_pairs_sharing_nodes": pairs})
        return
    for a, b, count in _sharing_pairs(source.obj):
        family = f"{a} and {b}"
        if a not in level.obj.families or b not in level.obj.families:
            values: dict[str, Value] = {"shared_nodes": None, "source_shared_nodes": count}
            yield _reported("gate", "G5", family, values)
            continue
        now = _shared(level.obj, a, b)
        values = {"shared_nodes": now, "source_shared_nodes": count}
        yield _item("gate", "G5", family, values, now == 0)


def _differing_faces(level: _Mesh, source: _Mesh, name: str) -> int:
    """Return how many faces of a family differ from the source's, in order and coordinates."""
    new, old = level.obj.families[name], source.obj.families[name]
    tolerance = DUPLICATE_FRACTION * source.size
    differ = abs(len(new) - len(old))
    for f, g in zip(new, old, strict=False):
        if len(f) != len(g):
            differ += 1
        elif numpy.linalg.norm(level.obj.verts[f] - source.obj.verts[g], axis=1).max() > tolerance:
            differ += 1
    return differ


def _g6(level: _Mesh, source: _Mesh | None, grids: tuple[str, ...]) -> Iterator[AuditItem]:
    """G6: a grid family at factor 1 keeps the source's faces in coordinates and order."""
    if source is None or not grids:
        yield _reported("gate", "G6", WHOLE_MESH, {"grid_families_at_factor_1": len(grids)})
        return
    for name in grids:
        known = name in level.obj.families and name in source.obj.families
        values: dict[str, Value] = {
            "faces": len(level.obj.families.get(name, [])),
            "source_faces": len(source.obj.families.get(name, [])),
            "differing_faces": _differing_faces(level, source, name) if known else None,
        }
        yield _item("gate", "G6", name, values, not known or values["differing_faces"] != 0)


def _limit(check: str, source_value: float | None) -> float | None:
    """Return the limit of a relative check from the source's 95th percentile (R3)."""
    if check == "skewness":
        return None if source_value is None else source_value + SKEWNESS_MARGIN
    floor = WARP_FLOOR_DEGREES if check == "warp" else GROWTH_FLOOR
    return floor if source_value is None else max(source_value, floor)


def _checks(
    mine: Mapping[str, Mapping[str, Value]], theirs: Mapping[str, Mapping[str, Value]] | None
) -> Iterator[AuditItem]:
    """Yield the relative checks of each family and of the whole mesh (R3).

    A family the source does not hold, and every family without a source, is
    reported and not judged.
    """
    theirs = theirs or {}
    for family, figures in mine.items():
        for check, figure in CHECKS:
            value = figures[figure]
            if family not in theirs:
                yield _reported("check", check, family, {"p95": value, "source_p95": None})
                continue
            base = theirs[family][figure]
            yield _check(check, family, value, base)


def _check(check: str, family: str, value: Value, base: Value) -> AuditItem:
    """Return one relative check judged against its limit."""
    limit = _limit(check, None if base is None else float(base))
    values: dict[str, Value] = {"p95": value, "source_p95": base, "limit": limit}
    if check != "skewness":
        floor = WARP_FLOOR_DEGREES if check == "warp" else GROWTH_FLOOR
        values["source_beyond_practice"] = base is not None and float(base) > floor * (
            1.0 + CHECK_TOLERANCE
        )
    if value is None or limit is None or values.get("source_beyond_practice"):
        # R3: a source that fails a practice is reported, not judged.
        return _reported("check", check, family, values)
    failed = float(value) > limit + CHECK_TOLERANCE * abs(limit)
    return _item("check", check, family, values, failed)


def _said(value: Value) -> str:
    """Return a value as said in a warning, a console line or a CSV cell."""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
