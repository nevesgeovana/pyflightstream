"""Degenerate geometries derived from a blade mesh: the thin blade (FR-330).

A thin-blade study replaces a blade by its mean surface, a sheet with no
thickness, and until 0.34.0 that sheet was built by hand. This module builds
it from the blade's own surface mesh and writes it beside the source, with
the boundary inventory the raw-mesh route reads (FR-55), so the command
``pyfs-matrix degenerate --kind thin-blade`` (FR-330 R1) has one library
function to call: :func:`derive_thin_blade`.

WHAT IS COMPUTED, in the mesh's own frame and length unit:

1. THE SPAN. The span direction is the principal axis of the blade's
   vertices (the direction of their largest spread), snapped to a global
   axis when it lies within :data:`SNAP_DEGREES` of one, so a blade modelled
   along an axis is cut in its own modelling planes. Its sense goes from the
   root to the tip, the ROOT being the end nearer the origin of the mesh's
   coordinates, where a rotor's blade meets its spinner; a blade whose two
   ends lie equally far from the origin is refused, because which end is the
   root cannot be told.
2. THE STATIONS. The root station is the blade's lowest span coordinate
   moved outward by the required root offset (FR-330 R3), so the sheet does
   not cross the spinner. A mesh built in rings (its vertices on planes of
   constant span) is cut at its own rings above the root station; any other
   mesh at :data:`SPAN_STATIONS` evenly spaced stations, the last one
   :data:`TIP_MARGIN` of the span below the tip, where a closed tip cap
   leaves no chord.
3. THE SECTIONS. Each station's plane cuts the surface in one closed loop,
   the vertices an export writes once per side (an unwelded trailing edge)
   merged first, so such an edge is joined. Its two ends are the two loop
   points farthest apart (the leading and the trailing edge, in either
   order), and the two halves of the loop between them are the blade's two
   sides.
4. THE MEAN SURFACE. Each side is projected on its chord, resampled at the
   cosine stations ``(1 - cos(pi k / n)) / 2`` of :data:`CHORD_PANELS`
   panels, and the thin blade's point at each station is the mean of the two
   sides there (FR-330 R2): the surface midway between them, from the root
   to the tip, with the solid section's leading and trailing edge.

WHAT IS WRITTEN. ``<stem>_thin_blade.obj`` beside the source, one group named
as the source's boundary, in triangles; and its ``<stem>_thin_blade.boundaries.toml``
naming that group, stating the root offset used and, where the source states
it, the ``[import]`` table: the saved simulation's length unit, or the OBJ
sidecar's unit and mesh operations whole, because the thin blade lies in the
blade's own frame and the same operations place it. The source is only read
(FR-330 R4).

WHAT IS REFUSED, by name and with the reason, before anything is written
(FR-330 R6): a file that is not a saved simulation or an OBJ, one that cannot
be read, one holding more than one boundary when ``boundary`` names none, a
boundary the file does not hold or holds twice, an OBJ whose sidecar states a
CAD or CCS conversion, a root offset that is not a positive length shorter
than the blade, a blade whose root cannot be told from its tip, a section
that is not one closed loop (an open surface, such as a sheet already without
thickness, or a plane that cuts another closed body in the same group), and
a section whose two sides cannot be separated. An existing output is refused
unless ``overwrite`` is given.

WHICH BLADE. A file that holds the blade with a spinner, a nacelle or other
bodies is read with ``boundary`` naming the blade's boundary (FR-330 R9): only
its faces are taken, so the other bodies take no part in the span, the stations
or the sections, and the output's stem carries the boundary's name.

WHAT IT IS NOT. The derived geometry is a modelling choice of the user; this
module makes no claim about the solver's behaviour on it, which a run
confirms (FR-330 R8). No trailing edge is marked on the sheet: the sidecar's
``[trailing_edges]`` table is the user's to write, as for any raw mesh.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy
from numpy.typing import NDArray

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream._fsm import (
    MeshReadError,
    _mesh_block,
    boundary_names,
    saved_mesh_coordinate_unit,
    surface_mesh,
)
from pyflightstream.cases import MeshOperation
from pyflightstream.workspace.sidecars import inventory_sidecar, read_mesh_import

__all__ = [
    "CHORD_PANELS",
    "THIN_BLADE_KIND",
    "ThinBlade",
    "derive_thin_blade",
    "thin_blade_path",
]

#: The one kind of degenerate geometry of 0.34.0 (FR-330 R1).
THIN_BLADE_KIND = "thin-blade"

#: The suffixes read: a saved simulation and an OBJ, the forms ``inventory`` reads.
READ_SUFFIXES = (".fsm", ".obj")

#: What the output's stem adds to the source's (FR-330 R4).
THIN_BLADE_STEM = "_thin_blade"

#: The chordwise panels of the thin sheet, at cosine stations.
CHORD_PANELS = 40

#: The spanwise stations of a mesh that is not built in rings.
SPAN_STATIONS = 41

#: The fraction of the span below the tip where a mesh not built in rings
#: has its last station, because a closed tip cap leaves no chord at the tip.
TIP_MARGIN = 0.005

#: A principal axis this close to a global axis (degrees) is taken as it.
SNAP_DEGREES = 5.0

#: The fewest vertices a plane of constant span holds to count as a ring.
RING_MIN_VERTICES = 8

#: The share of the vertices that must lie on rings for the mesh to be cut there.
RING_SHARE = 0.9

#: Lengths below this fraction of the span are round-off.
SPAN_TOLERANCE = 1e-9

#: The share of the span at each end whose vertices say how far that end lies
#: from the origin, for telling the root from the tip.
END_BAND = 0.05

_KIND = "geometry"

Points = NDArray[numpy.float64]
Faces = NDArray[numpy.int64]


@dataclass(frozen=True)
class ThinBlade:
    """What :func:`derive_thin_blade` wrote.

    Attributes
    ----------
    mesh : Path
        The thin blade, an OBJ beside the source.
    sidecar : Path
        Its boundary inventory, ``<stem>.boundaries.toml`` beside it.
    boundary : str
        The one boundary (OBJ group) of the thin blade, named as the source's.
    root_offset : float
        The offset the root was moved outward by, in the mesh's length unit.
    span_direction : tuple of float
        The unit vector from the blade's root to its tip.
    root_span, tip_span : float
        The span coordinates (along ``span_direction``, from the origin) of
        the first and the last station of the thin blade.
    stations : int
        The spanwise sections the sheet passes through.
    unit : str or None
        The length unit written in the sidecar's ``[import]`` table, None
        when the source does not state one.
    """

    mesh: Path
    sidecar: Path
    boundary: str
    root_offset: float
    span_direction: tuple[float, float, float]
    root_span: float
    tip_span: float
    stations: int
    unit: str | None


def thin_blade_path(geometry: str | Path, boundary: str | None = None) -> Path:
    """Return the path the thin blade of ``geometry`` is written at (FR-330 R4).

    Parameters
    ----------
    geometry : str or Path
        The source blade mesh.
    boundary : str, optional
        The boundary the blade was selected by (FR-330 R9); its name, with
        every character that is not a letter, a digit or a hyphen turned
        into an underscore, joins the stem so two blades of one file do
        not share an output.

    Returns
    -------
    Path
        ``<stem>_thin_blade.obj`` beside it, or ``<stem>_<boundary>_thin_blade.obj``
        with a boundary, whether or not it exists.
    """
    path = Path(geometry)
    part = "_" + re.sub(r"[^0-9A-Za-z-]", "_", boundary) if boundary else ""
    return path.with_name(path.stem + part + THIN_BLADE_STEM + ".obj")


def _refuse(source: Path, reason: str) -> InputArtifactError:
    """Return the refusal of ``source``: its name, the reason, and that nothing was written."""
    return InputArtifactError(
        f"{source}: no thin blade is derived from it: {reason}. Nothing was written.",
        kind=_KIND,
    )


# --- reading the blade -------------------------------------------------------------


@dataclass(frozen=True)
class _Blade:
    vertices: Points
    faces: Faces
    boundary: str
    unit: str | None
    #: The source sidecar's mesh operations, carried to the thin blade's (FR-330 R5).
    operations: tuple[MeshOperation, ...] = ()


def _not_one_blade(source: Path, kind: str, names: Sequence[str]) -> InputArtifactError:
    """Return the refusal of a file holding several boundaries or groups, naming the way out."""
    return _refuse(
        source,
        f"it holds {len(names)} {kind} ({', '.join(names)}), and a thin blade is derived "
        "from a file holding one blade alone, or from the one boundary named with --boundary",
    )


def _no_such_boundary(source: Path, boundary: str, names: Sequence[str]) -> InputArtifactError:
    """Return the refusal of a ``boundary`` the file does not hold, or holds under two names."""
    if names.count(boundary) > 1:
        return _refuse(
            source,
            f"--boundary {boundary!r} names {names.count(boundary)} of its boundaries, so it "
            "selects none; rename one in the geometry",
        )
    return _refuse(
        source,
        f"it holds no boundary named {boundary!r} (--boundary); it holds "
        f"{', '.join(names) or 'none'}",
    )


def _sub_mesh(vertices: Points, faces: Faces) -> tuple[Points, Faces]:
    """Return the faces with only the vertices they use, renumbered in their own order."""
    used, inverse = numpy.unique(faces.reshape(-1), return_inverse=True)
    return vertices[used], inverse.reshape(-1, 3).astype(numpy.int64)


def _fsm_boundary_faces(source: Path, names: Sequence[str], boundary: str) -> tuple[Points, Faces]:
    """Return the vertices and faces of the saved simulation's boundary named ``boundary``."""
    if names.count(boundary) != 1:
        raise _no_such_boundary(source, boundary, names)
    try:
        vertices, triangles, _, owners = _mesh_block(source)
    except MeshReadError as error:
        raise _refuse(source, f"its mesh block cannot be read ({error})") from error
    faces = numpy.asarray(triangles, dtype=numpy.int64).reshape(-1, 3)
    if len(owners) != len(faces):
        raise _refuse(
            source, "its mesh block carries no boundary row, so no face can be told to a boundary"
        )
    mine = numpy.asarray(owners, dtype=numpy.int64) == names.index(boundary) + 1
    return _sub_mesh(numpy.asarray(vertices, dtype=float).reshape(-1, 3), faces[mine])


def _read_fsm(source: Path, boundary: str | None) -> _Blade:
    """Read a saved simulation holding one boundary, or the one named, refusing by name."""
    try:
        names = boundary_names(source) or ()
        vertices, triangles = surface_mesh(source)
    except MeshReadError as error:
        raise _refuse(source, f"its mesh block cannot be read ({error})") from error
    if boundary is None and len(names) > 1:
        raise _not_one_blade(source, "boundaries", names)
    try:
        unit = saved_mesh_coordinate_unit(source)
    except MeshReadError:
        unit = None
    points = numpy.asarray(vertices, dtype=float).reshape(-1, 3)
    faces = numpy.asarray(triangles, dtype=numpy.int64).reshape(-1, 3)
    if boundary is not None:
        points, faces = _fsm_boundary_faces(source, names, boundary)
    return _Blade(points, faces, boundary or (names[0] if names else source.stem), unit)


def _obj_face(words: Sequence[str], count: int, where: str) -> list[int]:
    """Return the 0-based vertex indices of one OBJ face statement."""
    indices = []
    for word in words:
        index = int(word.split("/", 1)[0])
        indices.append(index - 1 if index > 0 else count + index)
    if len(indices) < 3 or not all(0 <= i < count for i in indices):
        raise ValueError(f"{where} names a vertex outside the {count} read before it")
    return indices


def _obj_statements(text: str) -> tuple[list[list[float]], dict[str, list[list[int]]]]:
    """Return the vertices and the triangles by group of an OBJ's text."""
    vertices: list[list[float]] = []
    groups: dict[str, list[list[int]]] = {}
    current = ""
    for number, line in enumerate(text.splitlines(), start=1):
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if words[0] == "v":
            if len(words) < 4:
                raise ValueError(
                    f"line {number} states a vertex of {len(words) - 1} coordinates, not three"
                )
            vertices.append([float(word) for word in words[1:4]])
        elif words[0] in ("o", "g") and len(words) > 1:
            current = words[1]
        elif words[0] == "f":
            face = _obj_face(words[1:], len(vertices), f"line {number}")
            fan = [[face[0], face[k], face[k + 1]] for k in range(1, len(face) - 1)]
            groups.setdefault(current, []).extend(fan)
    return vertices, groups


def _read_obj(source: Path, boundary: str | None) -> _Blade:
    """Read an OBJ holding one group of faces, or the one named, refusing by name."""
    try:
        vertices, groups = _obj_statements(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, IndexError) as error:
        raise _refuse(source, f"it cannot be read as an OBJ ({error})") from error
    names = [name or "(no group)" for name in groups]
    if boundary is None and len(groups) > 1:
        raise _not_one_blade(source, "groups of faces", names)
    if boundary is not None and boundary not in groups:
        raise _no_such_boundary(source, boundary, names)
    sidecar = inventory_sidecar(source)
    stated = read_mesh_import(sidecar) if sidecar.is_file() else None
    if stated is not None and (stated.cad is not None or stated.ccs is not None):
        table = "[import.cad]" if stated.cad is not None else "[import.ccs]"
        raise _refuse(
            source,
            f"its sidecar {sidecar.name} states {table}, a conversion of a CAD or CCS "
            "file, which a mesh read as an OBJ does not take",
        )
    name, faces = (boundary, groups[boundary]) if boundary else next(iter(groups.items()), ("", []))
    points = numpy.asarray(vertices, dtype=float).reshape(-1, 3)
    triangles = numpy.asarray(faces, dtype=numpy.int64).reshape(-1, 3)
    if boundary is not None:
        points, triangles = _sub_mesh(points, triangles)
    return _Blade(
        points,
        triangles,
        name or source.stem,
        stated.units if stated is not None else None,
        stated.operations if stated is not None else (),
    )


def _welded(blade: _Blade) -> _Blade:
    """Return the blade with coincident vertices merged, in their first order.

    An export that writes a vertex once per side (an unwelded trailing edge)
    leaves the surface open along that edge; merging the copies closes it.
    The faces a merge collapses to a line are dropped. A mesh with no
    coincident vertices is returned with its vertices and faces unchanged.
    """
    _, first, inverse = numpy.unique(blade.vertices, axis=0, return_index=True, return_inverse=True)
    if len(first) == len(blade.vertices):
        return blade
    order = numpy.argsort(first)
    rank = numpy.empty_like(order)
    rank[order] = numpy.arange(len(order))
    faces = rank[inverse.reshape(-1)][blade.faces]
    kept = (
        (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 2] != faces[:, 0])
    )
    return _Blade(
        blade.vertices[first[order]],
        faces[kept],
        blade.boundary,
        blade.unit,
        blade.operations,
    )


def _read_blade(source: Path, boundary: str | None = None) -> _Blade:
    """Read the blade mesh ``source`` names, refusing what cannot be read (FR-330 R6)."""
    if not source.is_file():
        raise _refuse(source, "it is not a file")
    if source.suffix.lower() not in READ_SUFFIXES:
        raise _refuse(
            source,
            f"a blade mesh is read from a saved simulation (.fsm) or an OBJ (.obj), "
            f"and this file is a {source.suffix or 'file without a suffix'}",
        )
    if source.suffix.lower() == ".fsm":
        blade = _read_fsm(source, boundary)
    else:
        blade = _read_obj(source, boundary)
    if len(blade.faces) < 4 or len(blade.vertices) < 4:
        raise _refuse(source, "it holds no surface mesh of a blade (fewer than four faces)")
    if not bool(numpy.isfinite(blade.vertices).all()):
        raise _refuse(source, "a vertex coordinate is not a finite number")
    return _welded(blade)


# --- the span ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
    """The span direction and two in-plane directions, orthonormal."""

    span: Points
    across: Points
    normal: Points

    def local(self, points: Points) -> Points:
        """Return (across, normal, span) coordinates of ``points``."""
        return numpy.stack([points @ self.across, points @ self.normal, points @ self.span], -1)

    def glob(self, local: Points) -> Points:
        """Return the global points of (across, normal, span) coordinates."""
        return (
            local[..., 0:1] * self.across
            + local[..., 1:2] * self.normal
            + local[..., 2:3] * self.span
        )


def _principal_axis(vertices: Points) -> Points:
    """Return the unit direction of the vertices' largest spread, snapped to a near axis."""
    centred = vertices - vertices.mean(axis=0)
    _, vectors = numpy.linalg.eigh(centred.T @ centred)
    axis = vectors[:, -1]
    for k in range(3):
        if abs(axis[k]) >= math.cos(math.radians(SNAP_DEGREES)):
            snapped = numpy.zeros(3)
            snapped[k] = math.copysign(1.0, axis[k])
            return snapped
    return axis / numpy.linalg.norm(axis)


def _span_frame(source: Path, vertices: Points) -> _Frame:
    """Return the blade's frame, its span from the root (the end nearer the origin) to the tip."""
    span = _principal_axis(vertices)
    s = vertices @ span
    low, high = float(s.min()), float(s.max())
    length = high - low
    if length <= 0.0:
        raise _refuse(source, "its vertices have no extent, so it has no span")
    band = END_BAND * length
    near_low = float(numpy.linalg.norm(vertices[s <= low + band], axis=1).mean())
    near_high = float(numpy.linalg.norm(vertices[s >= high - band], axis=1).mean())
    if abs(near_low - near_high) <= SPAN_TOLERANCE * length:
        raise _refuse(
            source,
            "its two ends lie equally far from the origin of its coordinates, so its root "
            "(the end nearer the origin, where a blade meets its spinner) cannot be told "
            "from its tip",
        )
    if near_low > near_high:
        span = -span
    seed = numpy.zeros(3)
    seed[int(numpy.argmin(numpy.abs(span)))] = 1.0
    across = seed - (seed @ span) * span
    across /= numpy.linalg.norm(across)
    return _Frame(span, across, numpy.cross(span, across))


# --- the stations ------------------------------------------------------------------


def _levels(s: Points, tolerance: float) -> list[tuple[float, int]]:
    """Return the distinct span levels of the vertices, each with its vertex count."""
    order = numpy.sort(s)
    breaks = numpy.nonzero(numpy.diff(order) > tolerance)[0] + 1
    return [(float(group.mean()), len(group)) for group in numpy.split(order, breaks)]


def _stations(source: Path, s: Points, root_offset: float) -> Points:
    """Return the span coordinates of the sections, the root moved by ``root_offset``."""
    low, high = float(s.min()), float(s.max())
    tolerance = SPAN_TOLERANCE * (high - low)
    full = [(level, count) for level, count in _levels(s, tolerance) if count >= RING_MIN_VERTICES]
    rings = [level for level, _ in full]
    on_rings = sum(count for _, count in full)
    structured = len(rings) >= 3 and on_rings >= RING_SHARE * len(s)
    top = max(rings) if structured else high - TIP_MARGIN * (high - low)
    root = low + root_offset
    if root >= top - tolerance:
        raise _refuse(
            source,
            f"the root offset {root_offset!r} reaches the blade's last section, "
            f"{top - low!r} from its root; the offset is a length shorter than the blade",
        )
    if structured:
        inner = [level for level in rings if level > root + 1e3 * tolerance]
        return numpy.asarray([root, *inner])
    return numpy.linspace(root, top, SPAN_STATIONS)


# --- one section -------------------------------------------------------------------


def _crossings(
    faces: Faces, above: NDArray[numpy.bool_]
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Return the edges the plane crosses, each with the crossed edges it is joined to."""
    joined: dict[tuple[int, int], list[tuple[int, int]]] = {}
    cut = faces[above[faces].any(axis=1) & ~above[faces].all(axis=1)]
    for a, b, c in cut.tolist():
        keys = [(min(i, j), max(i, j)) for i, j in ((a, b), (b, c), (c, a)) if above[i] != above[j]]
        joined.setdefault(keys[0], []).append(keys[1])
        joined.setdefault(keys[1], []).append(keys[0])
    return joined


def _loops(
    joined: dict[tuple[int, int], list[tuple[int, int]]],
) -> list[list[tuple[int, int]]] | None:
    """Return the closed chains of crossed edges, None when one is open or branches."""
    if any(len(nexts) != 2 for nexts in joined.values()):
        return None
    seen: set[tuple[int, int]] = set()
    loops = []
    for start in joined:
        if start in seen:
            continue
        loop, previous, current = [start], None, start
        seen.add(start)
        while True:
            following = [n for n in joined[current] if n != previous] or joined[current][:1]
            if following[0] == start or following[0] in seen:
                break
            previous, current = current, following[0]
            loop.append(current)
            seen.add(current)
        loops.append(loop)
    return loops


def _section(local: Points, faces: Faces, station: float, tolerance: float) -> list[Points] | None:
    """Return every closed loop the plane of ``station`` cuts; None if one is open or none cut."""
    d = local[:, 2] - station
    d[numpy.abs(d) <= tolerance] = 0.0
    loops = _loops(_crossings(faces, d >= 0.0))
    if not loops:
        return None
    sections = []
    for loop in loops:
        i = numpy.asarray([edge[0] for edge in loop])
        j = numpy.asarray([edge[1] for edge in loop])
        t = d[i] / (d[i] - d[j])  # a crossed edge has one end on each side, so never 0 / 0
        points = local[i, :2] + t[:, None] * (local[j, :2] - local[i, :2])
        keep = numpy.linalg.norm(points - numpy.roll(points, 1, axis=0), axis=1) > tolerance
        sections.append(points[keep] if keep.any() else points[:1])
    return sections


def _ends(points: Points) -> tuple[int, int]:
    """Return the indices of the two loop points farthest apart (the chord's ends)."""
    a = int(numpy.argmax(numpy.linalg.norm(points - points[0], axis=1)))
    b = int(numpy.argmax(numpy.linalg.norm(points - points[a], axis=1)))
    a = int(numpy.argmax(numpy.linalg.norm(points - points[b], axis=1)))
    return a, b


def _resampled(side: Points, start: Points, chord: Points, stations: Points) -> Points:
    """Return one side resampled at the chord fractions ``stations``."""
    xi = numpy.maximum.accumulate((side - start) @ chord / float(chord @ chord))
    xi[0], xi[-1] = 0.0, 1.0
    return numpy.stack(
        [numpy.interp(stations, xi, side[:, 0]), numpy.interp(stations, xi, side[:, 1])], 1
    )


def _mean_line(points: Points, panels: int) -> Points | None:
    """Return the mean line of one closed section, None when its two sides cannot be told."""
    n = len(points)
    if n < 6:
        return None
    a, b = _ends(points)
    forward = points[[(a + k) % n for k in range((b - a) % n + 1)]]
    backward = points[[(a - k) % n for k in range((a - b) % n + 1)]]
    if len(forward) < 3 or len(backward) < 3:
        return None
    stations = 0.5 * (1.0 - numpy.cos(numpy.pi * numpy.arange(panels + 1) / panels))
    chord = points[b] - points[a]
    first = _resampled(forward, points[a], chord, stations)
    second = _resampled(backward, points[a], chord, stations)
    return 0.5 * (first + second)


# --- the sheet ---------------------------------------------------------------------


def _mean_surface(source: Path, blade: _Blade, frame: _Frame, stations: Points) -> Points:
    """Return the thin blade's grid, (stations, CHORD_PANELS + 1, 3), refusing a section."""
    local = frame.local(blade.vertices)
    tolerance = SPAN_TOLERANCE * float(numpy.ptp(local[:, 2]))
    rows = []
    for station in stations:
        where = f"the section at span {float(station)!r} (along {frame.span.round(6).tolist()})"
        loops = _section(local, blade.faces, float(station), tolerance)
        if loops is None:
            raise _refuse(
                source,
                f"{where} is not one closed loop: the surface is open there (a sheet already "
                "without thickness, or two sides not joined along an edge), so its two "
                "sides cannot be separated",
            )
        if len(loops) > 1:
            raise _refuse(
                source,
                f"{where} is not one closed loop: its plane cuts {len(loops)} closed loops, "
                "so the group holds another closed body beside the blade and the blade's "
                "two sides cannot be separated from it",
            )
        loop = loops[0]
        line = _mean_line(loop, CHORD_PANELS)
        if line is None:
            raise _refuse(
                source,
                f"{where} holds {len(loop)} points, too few for its two sides to be separated",
            )
        rows.append(numpy.column_stack([line, numpy.full(len(line), station)]))
    return frame.glob(numpy.asarray(rows))


def _triangles(stations: int, panels: int) -> Iterable[tuple[int, int, int]]:
    """Yield the sheet's triangles as 1-based OBJ indices, two per grid quad."""
    for k in range(stations - 1):
        for j in range(panels):
            a, b = k * (panels + 1) + j + 1, k * (panels + 1) + j + 2
            c, d = b + panels + 1, a + panels + 1
            yield a, b, c
            yield a, c, d


def _obj_text(source: Path, grid: Points, boundary: str, root_offset: float) -> str:
    """Return the thin blade's OBJ text, LF line ends (NFR-32)."""
    stations, columns = grid.shape[0], grid.shape[1]
    lines = [
        f"# Thin blade of {source.name}: the mean surface of its blade, the root moved",
        f"# outward along the span by {root_offset!r} (pyflightstream, FR-330).",
        f"o {boundary}",
        *(f"v {x:.15g} {y:.15g} {z:.15g}" for x, y, z in grid.reshape(-1, 3).tolist()),
        *(f"f {a} {b} {c}" for a, b, c in _triangles(stations, columns - 1)),
    ]
    return "\n".join(lines) + "\n"


def _sidecar_text(source: Path, mesh: Path, blade: _Blade, root_offset: float) -> str:
    """Return the thin blade's boundary inventory, the sidecar the raw-mesh route reads."""
    lines = [
        f"# Boundary inventory of {mesh.name}, the thin blade pyflightstream derived from",
        f"# {source.name} (sha256 {file_sha256(source)}) by `pyfs-matrix degenerate` (FR-330).",
        f"# root_offset = {root_offset!r}, in the mesh's own length unit: the root of the",
        "# thin blade is moved outward along the span by it, off the spinner.",
        "# Add the [trailing_edges] table beneath, as for any raw mesh (docs/mesh-inputs.md).",
        f"boundaries = [{json.dumps(blade.boundary, ensure_ascii=False)}]",
    ]
    if blade.unit is None:
        lines.append(
            f"# {source.name} states no length unit; write [import] units beneath this list."
        )
        return "\n".join(lines) + "\n"
    lines += [
        "",
        f"# The [import] table is {source.name}'s: the thin blade lies in the blade's own",
        "# frame, so the same unit and mesh operations place it as they place the blade.",
        "[import]",
        f"units = {json.dumps(blade.unit, ensure_ascii=False)}",
    ]
    for operation in blade.operations:
        lines += ["", "[[import.operations]]"]
        for key, value in operation.model_dump(exclude_none=True).items():
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _toml_value(value: object) -> str:
    """Return a mesh operation's value as TOML: a string, a number or a list of numbers."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return repr(float(value))
    raise TypeError(f"a mesh operation holds {value!r}, which the sidecar does not write")


def _checked_offset(source: Path, root_offset: float) -> float:
    """Return the root offset as a float, refusing one that is not a positive length."""
    if isinstance(root_offset, (bool, str, bytes)):
        raise _refuse(source, f"the root offset {root_offset!r} is not a number")
    try:
        offset = float(root_offset)
    except (TypeError, ValueError) as error:
        raise _refuse(source, f"the root offset {root_offset!r} is not a number") from error
    if not math.isfinite(offset) or offset <= 0.0:
        raise _refuse(
            source,
            f"the root offset {root_offset!r} is not a positive length; the root is moved "
            "outward by it so the thin blade does not cross the spinner",
        )
    return offset


def derive_thin_blade(
    geometry: str | Path,
    *,
    root_offset: float,
    overwrite: bool = False,
    boundary: str | None = None,
) -> ThinBlade:
    """Derive the thin blade of a blade mesh and write it beside the source (FR-330).

    Parameters
    ----------
    geometry : str or Path
        The blade mesh: a saved simulation (``.fsm``) or an OBJ holding one
        blade alone.
    root_offset : float
        How far the root is moved outward along the span, in the mesh's own
        length unit, so the thin blade does not cross the spinner. Required,
        positive and shorter than the blade.
    overwrite : bool
        Rewrite an existing thin blade and its sidecar. Without it an
        existing one is refused.
    boundary : str, optional
        The name of the one boundary (OBJ group) that is the blade, for a
        file that holds the blade with a spinner, a nacelle or other bodies
        (FR-330 R9). Only its faces are read, and the output is written
        under the name :func:`thin_blade_path` gives for it. Without it a
        file holding more than one boundary is refused.

    Returns
    -------
    ThinBlade
        The paths written and the frame and stations used.

    Raises
    ------
    InputArtifactError
        Naming the source and the reason, with nothing written: a file that
        is not a saved simulation or an OBJ or cannot be read, one holding
        more than one boundary, an OBJ whose sidecar states a CAD or CCS
        conversion, a root offset that is not a positive length shorter
        than the blade, a blade whose root cannot be told from its tip, a
        section that is not one closed loop (open, or one of several) or
        whose two sides cannot be separated, and an existing output without
        ``overwrite``.
    """
    source = Path(geometry)
    mesh = thin_blade_path(source, boundary)
    sidecar = inventory_sidecar(mesh)
    for existing in (mesh, sidecar):
        if existing.exists() and not overwrite:
            raise _refuse(source, f"{existing} already exists; pass overwrite to rewrite it")
    offset = _checked_offset(source, root_offset)
    blade = _read_blade(source, boundary)
    frame = _span_frame(source, blade.vertices)
    stations = _stations(source, blade.vertices @ frame.span, offset)
    grid = _mean_surface(source, blade, frame, stations)
    mesh.write_text(_obj_text(source, grid, blade.boundary, offset), encoding="utf-8", newline="\n")
    sidecar.write_text(_sidecar_text(source, mesh, blade, offset), encoding="utf-8", newline="\n")
    return ThinBlade(
        mesh=mesh,
        sidecar=sidecar,
        boundary=blade.boundary,
        root_offset=offset,
        span_direction=(
            float(frame.span[0]) + 0.0,
            float(frame.span[1]) + 0.0,
            float(frame.span[2]) + 0.0,
        ),
        root_span=float(stations[0]),
        tip_span=float(stations[-1]),
        stations=len(stations),
        unit=blade.unit,
    )
