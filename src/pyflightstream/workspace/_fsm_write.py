"""Write a generated surface mesh into a saved-simulation file (PFS-2214, sub-step 9).

Pipeline role: the output stage of the configuration mesh routes. A fresh saved simulation of
the target build is the template: every block other than the mesh block is kept as that file
holds it, and the mesh block is written from the generated mesh. Nothing of the layout is
guessed at; every row written is a row the library's own reader (:mod:`pyflightstream._fsm`)
reads and the sector-to-wheel writer documents:

* one boundary record per component (head line, name, the template's first display colour);
* the face count, then 25 rows of one value per face: 0 the face id, 1 the vertices (3), 2 to
  4 the 1-based node ids, 9 the edge slot shared with the partner face, 10 the partner face,
  11 the 1-based boundary, 20 and 24 set, 21 to 23 the trailing-edge flag of edge slots
  (1, 2), (2, 3) and (3, 1); the other rows are 0;
* a line reading 0, the node count, the x, y and z rows, and an empty wake termination (0).

A quadrilateral is written as two triangles that name each other as partners across their
shared diagonal (slot 3 of the first, slot 1 of the second). The template must hold no base
region, trailing-edge group or termination: those name faces of another mesh, and rewriting
them is not measured, so such a template is refused rather than edited.

WHAT IS NOT MEASURED HERE. Whether the solver opens the written file is owed by a licensed
probe; this module proves only that the library's reader returns the mesh and marks written.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError, InputValueError
from pyflightstream._fsm import (
    MESH_MARKER,
    MeshReadError,
    saved_base_regions,
    saved_termination_count,
    saved_trailing_edge_groups,
)
from pyflightstream.geometry.stages import Mesh

__all__ = ["paired_triangles", "write_fsm"]

_PER_FACE_ROWS = 25
_EDGE_ROWS = {21: (0, 1), 22: (1, 2), 23: (2, 0)}
_SET_ROWS = (20, 24)
_MESH_END = "$MESH_END$"


def paired_triangles(mesh: Mesh) -> tuple[np.ndarray, list[int], list[int], list[str]]:
    """Return triangles, partner face (1-based, 0 none), shared slot and owner of every face.

    A quadrilateral ``(a, b, c, d)`` becomes ``(a, b, c)`` and ``(a, c, d)``; the first shares
    its third edge slot ``(c, a)`` and the second its first slot ``(a, c)``.
    """
    triangles: list[tuple[int, int, int]] = []
    partners: list[int] = []
    slots: list[int] = []
    owners: list[str] = []
    for cell, owner in zip(mesh.cells, mesh.components, strict=True):
        if len(cell) == 4:
            a, b, c, d = (int(v) for v in cell)
            first = len(triangles) + 1
            triangles += [(a, b, c), (a, c, d)]
            partners += [first + 1, first]
            slots += [3, 1]
            owners += [owner, owner]
        elif len(cell) == 3:
            triangles.append(tuple(int(v) for v in cell))  # type: ignore[arg-type]
            partners.append(0)
            slots.append(0)
            owners.append(owner)
        else:
            raise InputValueError(f"fsm: a cell has {len(cell)} nodes; only 3 or 4 are written")
    return np.asarray(triangles, dtype=int).reshape(-1, 3), partners, slots, owners


def _row(values: Iterable) -> str:
    return ",".join(str(int(v)) for v in values) + ","


def _flags(values: Iterable[bool]) -> str:
    return "".join(f" {'T' if v else 'F'}," for v in values)


def _reals(values: Iterable[float]) -> str:
    return ",".join(f"{float(v): .17E}" for v in values)


def _template_lines(template: Path) -> tuple[list[str], str, int, int, str]:
    try:
        raw = template.read_bytes().decode("latin-1")
        bases = saved_base_regions(template)
        groups = saved_trailing_edge_groups(template)
        terminations = saved_termination_count(template)
    except (OSError, MeshReadError) as error:
        raise InputArtifactError(
            f"fsm template {template.name}: cannot be read: {error}"
        ) from error
    if bases or groups or terminations:
        raise InputArtifactError(
            f"fsm template {template.name}: holds {len(bases)} base region(s), {len(groups)} "
            f"trailing-edge group(s) and {terminations} termination(s); a template must be a "
            "fresh import with none, because they name faces of another mesh"
        )
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(newline)
    stripped = [line.strip() for line in lines]
    start, end = stripped.index(MESH_MARKER), stripped.index(_MESH_END)
    colour = lines[start + 5].strip() if end - start > 6 else ".494,.573,.576"
    return lines, newline, start, end, colour


def _te_flags(triangles: np.ndarray, trailing_edges: Iterable[Sequence[int]]) -> dict[int, list]:
    marked = {tuple(sorted((int(a), int(b)))) for a, b in trailing_edges}
    rows: dict[int, list[bool]] = {}
    found: set[tuple[int, int]] = set()
    for row, (i, j) in _EDGE_ROWS.items():
        edges = [tuple(sorted((int(t[i]), int(t[j])))) for t in triangles]
        rows[row] = [edge in marked for edge in edges]
        found.update(edge for edge in edges if edge in marked)  # type: ignore[misc]
    if found != marked:
        raise InputValueError(
            f"fsm: {len(marked - found)} trailing edge(s) are not an edge of the mesh"
        )
    return rows


def _mesh_block(mesh: Mesh, colour: str, trailing_edges) -> list[str]:
    triangles, partners, slots, owners = paired_triangles(mesh)
    if not len(triangles):
        raise InputValueError("fsm: the mesh holds no cell")
    names = list(dict.fromkeys(mesh.components))
    if any(not n or n.strip() != n or "\n" in n or n.lstrip("+-").isdigit() for n in names):
        raise InputValueError(f"fsm: component names {names} must be non-numeric single lines")
    ids = {name: i + 1 for i, name in enumerate(names)}
    count = len(triangles)
    rows: dict[int, list] = {k: [0] * count for k in range(_PER_FACE_ROWS)}
    rows[0] = list(range(1, count + 1))
    rows[1] = [3] * count
    for k in range(3):
        rows[2 + k] = list(triangles[:, k] + 1)
    rows[9], rows[10] = slots, partners
    rows[11] = [ids[o] for o in owners]
    flags = _te_flags(triangles, trailing_edges)
    block = [MESH_MARKER, str(count), str(len(names)), str(len(names))]
    for i, name in enumerate(names):
        block += [f"{i + 1}, T, F, F", name, colour]
    block.append(str(count))
    for k in range(_PER_FACE_ROWS):
        if k in _SET_ROWS:
            block.append(_flags([True] * count))
        elif k in flags:
            block.append(_flags(flags[k]))
        else:
            block.append(_row(rows[k]))
    xyz = np.asarray(mesh.xyz, dtype=float)
    block += ["0", str(len(xyz)), *(_reals(xyz[:, k]) for k in range(3)), "0", _MESH_END]
    return block


def write_fsm(
    path: str | Path,
    mesh: Mesh,
    *,
    template: str | Path,
    trailing_edges: Iterable[Sequence[int]] = (),
) -> Path:
    """Write ``mesh`` into a copy of a fresh saved simulation, one boundary per component.

    Parameters
    ----------
    path : str or Path
        The saved-simulation file to write; an existing file is refused.
    mesh : Mesh
        Triangles and quadrilaterals with one component label per cell.
    template : str or Path
        A fresh saved simulation of the target build, with no base region, trailing-edge
        group or termination; its other blocks are copied unchanged.
    trailing_edges : iterable of (int, int)
        Node index pairs of the mesh edges marked as trailing edges.

    Returns
    -------
    Path
        The written file.

    Raises
    ------
    InputArtifactError
        If the template cannot be read or holds assignments of another mesh, or ``path``
        exists.
    InputValueError
        If a cell is not a triangle or a quadrilateral, a name cannot be a boundary name,
        or a trailing edge is not a mesh edge.
    """
    target = Path(path)
    if target.exists():
        raise InputArtifactError(f"fsm: {target} exists; nothing was written")
    lines, newline, start, end, colour = _template_lines(Path(template))
    block = _mesh_block(mesh, colour, trailing_edges)
    text = newline.join([*lines[:start], *block, *lines[end + 1 :]])
    _textio.write_text(target, text, encoding="latin-1")
    return target
