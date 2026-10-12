"""The preview of a built geometry: a legacy VTK file coloured by boundary (FR-471 R6).

Pipeline role: the workspace row. :func:`write_preview_vtk` writes the
surface of a built body with one cell array ``boundary`` (the boundary's
position, counted from 1, so ParaView colours each surface), its marked
trailing edges as a line set, and a field ``names`` listing the boundaries in
order, so one file shows the surfaces, their names, a control surface's gap
and which edges will shed a wake. The surface is read from the saved
simulation; where its mesh block is not one this package reads (a loft that
saves quadrilaterals), from the exported OBJ, whose families are the boundaries
and which carries no trailing edge.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pyflightstream import _textio
from pyflightstream._fsm import (
    MeshReadError,
    boundary_owners,
    surface_mesh,
    trailing_edge_midpoints,
)
from pyflightstream.workspace._refine._obj import read_obj

__all__ = ["PREVIEW_SUFFIX", "write_preview_vtk"]

#: The suffix of the preview file: ``<name>.preview.vtk``.
PREVIEW_SUFFIX = ".preview.vtk"

Point = tuple[float, float, float]


def _from_the_saved_file(
    fsm: Path,
) -> tuple[list[Point], list[tuple[int, ...]], list[int], list[tuple[int, int]]]:
    vertices, triangles = surface_mesh(fsm)
    owners = boundary_owners(fsm) or (1,) * len(triangles)
    marked = set(trailing_edge_midpoints(fsm))
    lines: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for triangle in triangles:
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a, b = triangle[first], triangle[second]
            edge = (min(a, b), max(a, b))
            if edge in seen:
                continue
            seen.add(edge)
            pa, pb = vertices[a], vertices[b]
            middle = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2)
            if middle in marked:
                lines.append(edge)
    return list(vertices), [tuple(t) for t in triangles], list(owners), lines


def _from_the_mesh(
    obj: Path, names: Sequence[str]
) -> tuple[list[Point], list[tuple[int, ...]], list[int], list[tuple[int, int]]]:
    mesh = read_obj(obj)
    vertices = [(float(x), float(y), float(z)) for x, y, z in mesh.verts.tolist()]
    faces: list[tuple[int, ...]] = []
    owners: list[int] = []
    for position, (family, family_faces) in enumerate(mesh.families.items(), start=1):
        owner = list(names).index(family) + 1 if family in names else position
        for face in family_faces:
            faces.append(tuple(int(index) for index in face))
            owners.append(owner)
    return vertices, faces, owners, []


def write_preview_vtk(
    target: Path, *, fsm: Path | None, obj: Path | None, names: Sequence[str]
) -> Path:
    """Write the preview of one built body and return its path.

    Parameters
    ----------
    target : Path
        The ``<name>.preview.vtk`` to write.
    fsm : Path or None
        The saved simulation, read first.
    obj : Path or None
        The exported mesh, read when the saved file's block is not readable.
    names : sequence of str
        The boundaries, in order.
    """
    try:
        if fsm is None:
            raise MeshReadError("no saved simulation")
        vertices, faces, owners, lines = _from_the_saved_file(fsm)
    except MeshReadError:
        if obj is None:
            raise
        vertices, faces, owners, lines = _from_the_mesh(obj, names)
    rows = [
        "# vtk DataFile Version 3.0",
        "pyflightstream geometry preview",
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {len(vertices)} double",
        *(f"{x!r} {y!r} {z!r}" for x, y, z in vertices),
        f"POLYGONS {len(faces)} {sum(len(face) + 1 for face in faces)}",
        *(" ".join(str(value) for value in (len(face), *face)) for face in faces),
    ]
    if lines:
        rows += [f"LINES {len(lines)} {3 * len(lines)}", *(f"2 {a} {b}" for a, b in lines)]
    rows += [
        f"CELL_DATA {len(faces) + len(lines)}",
        "SCALARS boundary int 1",
        "LOOKUP_TABLE default",
        # POLYDATA numbers its cells lines first, then polygons: a line is boundary 0.
        *("0" for _ in lines),
        *(str(owner) for owner in owners),
        "FIELD names 1",
        f"names 1 {len(names)} string",
        *names,
    ]
    _textio.write_lines(target, rows)
    return target
