"""Quads collected as the triangle pairs of a saved simulation, and the file written (PFS-2186.06).

Pipeline role: the writing half of ``pyfs-workspace geometry sector-remesh`` and ``power-off-body``.
A surface is built as quads; the saved layout records a quad as two triangles that name each
other as partner, so :class:`QuadSink` keeps them in that order and :func:`face_rows` writes the
25 per-face rows of the layout.

THE LAYOUT IS INFERRED FROM SAVED FILES, as in :mod:`pyflightstream.workspace._wheel_fsm`, whose
reader is used here; the rows written are:

* 0 face id, 1 vertices per face (3), 2 to 4 node ids, 5 group (a base-region number on a base
  face, a trailing-edge group number on a rim face, else 0);
* 6 to 8 and 13 to 19 zeros; 9 the edge shared with the partner (3 for the first triangle of a
  quad, 1 for the second, since the quad is split on the diagonal that joins its first and third
  node), 10 the partner face; 11 the boundary position, 12 the kind (1 rim, 3 base, 0 other);
* 20 and 24 the T/F rows copied from the source's first value; 21 to 23 the trailing-edge flag per
  edge slot of the face that carries the rim edge.

Faces are written in the order the quads were added, which the solver's results depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy
from numpy.typing import NDArray

from pyflightstream._errors import InputValueError
from pyflightstream._fsm import MeshReadError, boundary_names, surface_mesh
from pyflightstream.workspace._wheel import Faces, merge_nodes, rotate, wheel_symmetry
from pyflightstream.workspace._wheel_fsm import (
    _flag_row,
    _int_row,
    _parse,
    _real_row,
    _UnrecognizedError,
    edge_rows,
)

__all__ = ["QuadSink", "RemeshResult", "compose_sector", "mesh_checks", "wheel_checks"]


@dataclass
class RemeshResult:
    """What a remesh or power-off-body run did: whether it wrote, the files and the checks.

    Attributes
    ----------
    written : bool
        False, with nothing written, when the topology or the saved layout is not handled.
    output : Path or None
        The saved simulation written; None when nothing was written.
    files : list of Path
        Every file written, the ``<out stem>.remesh.json`` or ``<out stem>.body.json`` record
        included.
    report : dict
        What that record holds: the source sha256 and the checks.
    summary : list of str
        The printed lines of the checks.
    """

    written: bool
    output: Path | None = None
    files: list[Path] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    summary: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        """Return the printed summary: the files written, then the checks."""
        return [f"wrote {path}" for path in self.files] + self.summary


class QuadSink:
    """Quads as the saved layout's triangle pairs: nodes, boundary, kind, group, rim slot."""

    def __init__(self) -> None:
        self.tris: list[tuple[int, int, int]] = []
        self.owner: list[int] = []
        self.kind: list[int] = []
        self.group: list[int] = []
        self.slot: list[int | None] = []

    def quad(
        self,
        nodes: tuple[int, int, int, int],
        owner: int,
        *,
        kind: int = 0,
        group: int = 0,
        rim: tuple[int, int] | None = None,
    ) -> None:
        """Add a quad as the triangles (a, b, c) and (a, c, d).

        ``rim`` is the quad's trailing-edge edge: only the triangle that holds it carries the
        kind, the group and the slot flag; without ``rim`` both triangles carry them.
        """
        a, b, c, d = (int(n) for n in nodes)
        for tri in ((a, b, c), (a, c, d)):
            slot = _slot(tri, rim)
            on = rim is None or slot is not None
            self.tris.append(tri)
            self.owner.append(owner)
            self.kind.append(kind if on else 0)
            self.group.append(group if on else 0)
            self.slot.append(slot)

    def __len__(self) -> int:
        return len(self.tris)

    def quads(
        self,
    ) -> list[tuple[tuple[int, int, int, int], int, int, int, tuple[int, int] | None]]:
        """Return the quads as (nodes, owner, kind, group, rim edge), in the order added."""
        out = []
        for i in range(0, len(self.tris), 2):
            (a, b, c), (_, _, d) = self.tris[i], self.tris[i + 1]
            rim = None
            for k in (i, i + 1):
                slot = self.slot[k]
                if slot is not None:
                    t = self.tris[k]
                    rim = (t[slot], t[(slot + 1) % 3])
            out.append(
                (
                    (a, b, c, d),
                    self.owner[i],
                    max(self.kind[i], self.kind[i + 1]),
                    max(self.group[i], self.group[i + 1]),
                    rim,
                )
            )
        return out

    def array(self) -> NDArray[numpy.int64]:
        """Return the triangles as an array of node ids."""
        return numpy.array(self.tris, dtype=numpy.int64).reshape(-1, 3)


def _slot(tri: tuple[int, int, int], rim: tuple[int, int] | None) -> int | None:
    """Return the edge slot of a triangle that holds the rim edge, if it does."""
    if rim is None:
        return None
    for slot, (x, y) in enumerate(((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))):
        if {x, y} == {int(rim[0]), int(rim[1])}:
            return slot
    return None


def face_rows(sink: QuadSink, template: list[list[str]]) -> list[str]:
    """Return the 25 per-face rows of the saved layout for the quads of a sink."""
    n = len(sink)
    tris = sink.array()
    zero = _int_row(numpy.zeros(n, dtype=int))
    partner = numpy.arange(n) ^ 1
    out = {
        0: _int_row(numpy.arange(1, n + 1)),
        1: _int_row(numpy.full(n, 3)),
        2: _int_row(tris[:, 0] + 1),
        3: _int_row(tris[:, 1] + 1),
        4: _int_row(tris[:, 2] + 1),
        5: _int_row(sink.group),
        9: _int_row(numpy.where(numpy.arange(n) % 2 == 0, 3, 1)),
        10: _int_row(partner + 1),
        11: _int_row(sink.owner),
        12: _int_row(sink.kind),
    }
    for k in (6, 7, 8, 13, 14, 15, 16, 17, 18, 19):
        out[k] = zero
    for k in (20, 24):
        out[k] = _flag_row([template[k][0]] * n)
    # T/F, or a 26.127 source's integer form: the rim face's group on its flagged slot
    for k, row in zip((21, 22, 23), edge_rows(template, sink.slot, sink.group), strict=True):
        out[k] = row
    return [out[k] for k in range(25)]


def node_rows(nodes: NDArray[numpy.float64]) -> list[str]:
    """Return the node count and the x, y and z rows of a saved mesh block."""
    return [str(len(nodes)), *[_real_row(nodes[:, k]) for k in range(3)]]


def compose_sector(
    parsed: Any,
    sink: QuadSink,
    nodes: NDArray[numpy.float64],
    termination: list[list[int]],
) -> str:
    """Return the saved sector with a new mesh block and wake termination, the rest unchanged.

    The boundary records, the physics block and everything outside the mesh block are the
    source's. ``termination`` is the face, vertex slot and group rows of the wake termination.
    """
    lines, mesh = parsed.lines, parsed.mesh
    tail = mesh["tail"]
    total = str(len(sink))
    text = lines[: mesh["start"] + 1] + [total] + lines[mesh["start"] + 2 : mesh["first"] - 1]
    text += [total, *face_rows(sink, mesh["rows"]), lines[tail], *node_rows(nodes)]
    text += [lines[tail + 5]] + [_int_row(row) for row in termination] + lines[mesh["end"] :]
    return parsed.newline.join(text)


@dataclass
class ReadBack:
    """A composed file read again: the parsed layout and the triangle count per boundary."""

    parsed: Any
    triangles: dict[str, int]


def read_back(path: Path, expected_names: tuple[str, ...]) -> ReadBack:
    """Read a composed file with the package's own readers; count faces not in a pair (triangles).

    Raises
    ------
    ValueError
        The file does not read back as the layout, or reads back other boundaries.
    """
    try:
        parsed = _parse(path.read_bytes().decode("latin-1"))
        names = boundary_names(path)
        surface_mesh(path)
    except (_UnrecognizedError, MeshReadError, IndexError, KeyError) as error:
        raise InputValueError(f"the composed file does not read back ({error})") from error
    if tuple(names or ()) != expected_names:
        raise InputValueError(f"the composed file reads back boundaries {names!r}")
    return ReadBack(parsed, triangles_by_boundary(parsed))


def triangles_by_boundary(parsed: Any) -> dict[str, int]:
    """Count, per boundary, the faces that are not one half of a quad pair (R1)."""
    ints = parsed.mesh["ints"]
    partner, owner = ints[10] - 1, ints[11]
    index = numpy.arange(len(partner))
    safe = numpy.where(partner >= 0, partner, 0)
    tri = numpy.stack([ints[2], ints[3], ints[4]], axis=1)
    shared = numpy.array(
        [
            len(set(tri[i].tolist()) & set(tri[j].tolist())) == 2
            for i, j in zip(index, safe, strict=True)
        ]
    )
    paired = (partner >= 0) & (partner[safe] == index) & (owner[safe] == owner) & shared
    names = [h[4] for h in parsed.mesh["heads"]]
    return {name: int(((owner == k + 1) & ~paired).sum()) for k, name in enumerate(names)}


def mesh_checks(tris: NDArray[numpy.int64], nodes: NDArray[numpy.float64]) -> dict[str, Any]:
    """Return the non-manifold and open edges, repeated faces and the area of a triangle set."""
    faces = Faces(tris.ravel(), numpy.full(len(tris), 3))
    a, b, _ = faces.edges()
    key = numpy.minimum(a, b) * len(nodes) + numpy.maximum(a, b)
    _, times = numpy.unique(key, return_counts=True)
    return {
        "non_manifold_edges": int((times > 2).sum()),
        "open_edges": int((times == 1).sum()),
        "degenerate_faces": int(faces.repeated().sum()),
        "duplicate_faces": int(len(tris) - len({tuple(sorted(t)) for t in tris.tolist()})),
        "area": faces.area(nodes),
    }


def wheel_checks(
    nodes: NDArray[numpy.float64],
    tris: NDArray[numpy.int64],
    axis: NDArray[numpy.float64],
    copies: int,
    tol: float,
) -> dict[str, Any]:
    """Return the N-fold invariance of the sector's copies and the control that must fail it.

    The sector is copied ``copies`` times about the axis and its seam nodes merged within
    ``tol``; a turn by 360/N must map every node and face onto the wheel, and a turn one degree
    further must not (a derangement).
    """
    origin = numpy.zeros(3)
    stack = numpy.vstack([rotate(nodes, axis, origin, 360.0 * k / copies) for k in range(copies)])
    root = merge_nodes(stack, tol)
    used = numpy.unique(root)
    index = numpy.full(len(stack), -1, dtype=numpy.int64)
    index[used] = numpy.arange(len(used))
    flat = numpy.concatenate([index[root[tris.ravel() + k * len(nodes)]] for k in range(copies)])
    faces = Faces(flat, numpy.full(len(tris) * copies, 3))
    checks: dict[str, Any] = dict(
        wheel_symmetry(stack[used], faces, axis, origin, copies=copies, tol=tol)
    )
    checks["wheel_nodes"] = {"stack": len(stack), "merged": len(stack) - len(used)}
    checks["wheel_faces"] = len(tris) * copies
    return checks
