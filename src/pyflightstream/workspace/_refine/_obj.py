"""The OBJ and trailing-edge points files a refinement reads and writes (FR-424).

A mesh is one vertex array and an ordered mapping from family name to its
faces, each face a list of 0-based vertex indices. Families are the OBJ
groups (``g``) or objects (``o``) in file order; the comment lines before the
first vertex are kept and written back. Every write goes through the
package's one text route, so a level holds no carriage return (NFR-32).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy
from numpy.typing import NDArray

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError

Faces = list[list[int]]

#: The family a face belongs to when it comes before any ``g`` or ``o`` line.
DEFAULT_FAMILY = "default"


@dataclass
class ObjMesh:
    """One OBJ: vertices, families in file order, the header comments and the family keyword."""

    verts: NDArray[numpy.float64]
    families: dict[str, Faces]
    header: list[str] = field(default_factory=list)
    family_tag: str = "g"

    def family_vertices(self, name: str) -> NDArray[numpy.int64]:
        """Return the sorted indices of the vertices the family's faces use."""
        faces = self.families[name]
        return numpy.unique(numpy.fromiter((v for f in faces for v in f), dtype=numpy.int64))

    @property
    def size(self) -> float:
        """Return the diagonal of the bounding box of the used vertices (the SIZE of FR-424)."""
        used = numpy.unique(
            numpy.fromiter(
                (v for faces in self.families.values() for f in faces for v in f), dtype=numpy.int64
            )
        )
        if not used.size:
            return 0.0
        box = self.verts[used]
        return float(numpy.linalg.norm(box.max(axis=0) - box.min(axis=0)))


#: The artifact kind a refusal of this package names.
KIND = "mesh"


def _refuse(path: Path, reason: str) -> InputArtifactError:
    """Return the refusal of a file: its name, the reason, the remedy, and nothing written."""
    return InputArtifactError(
        f"{path}: {reason}. Fix the file and run again. Nothing was written.", kind=KIND
    )


def _refuse_at(where: str, what: str) -> InputArtifactError:
    """Return the refusal of one line of an OBJ."""
    return InputArtifactError(
        f"{where} is {what}. Fix the file and run again. Nothing was written.", kind=KIND
    )


def read_obj(path: str | Path) -> ObjMesh:
    """Read an OBJ: ``v`` and ``f`` lines, ``g`` or ``o`` families, header comments.

    Texture and normal indices of a face (``f 1/2/3``) are dropped; a negative
    index counts back from the last vertex read. A face with fewer than three
    vertices, or naming a vertex that does not exist, is refused.
    """
    source = Path(path)
    mesh = ObjMesh(numpy.zeros((0, 3)), {})
    verts: list[tuple[float, float, float]] = []
    current = DEFAULT_FAMILY
    text = source.read_text(encoding="utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if s.startswith("#") and not verts:
            mesh.header.append(s)
        elif s and not s.startswith("#"):
            current = _statement(f"{source}: line {number}", s, verts, mesh, current)
    if not mesh.families:
        raise _refuse(source, "the file holds no face")
    mesh.verts = numpy.asarray(verts, dtype=float).reshape(-1, 3)
    return mesh


def _statement(
    where: str, s: str, verts: list[tuple[float, float, float]], mesh: ObjMesh, current: str
) -> str:
    """Read one ``v``, ``f``, ``g`` or ``o`` statement into the mesh; return the current family."""
    tag, _, rest = s.partition(" ")
    if tag == "v":
        words = rest.split()
        if len(words) < 3:
            raise _refuse_at(where, "a vertex with fewer than three numbers")
        verts.append((float(words[0]), float(words[1]), float(words[2])))
    elif tag == "f":
        idx = [int(tok.split("/")[0]) for tok in rest.split()]
        face = [i - 1 if i > 0 else len(verts) + i for i in idx]
        if len(face) < 3 or any(not 0 <= v < len(verts) for v in face):
            raise _refuse_at(where, "a face with fewer than three vertices or a missing vertex")
        mesh.families.setdefault(current, []).append(face)
    elif tag in ("g", "o"):
        mesh.family_tag = tag
        return rest.strip() or DEFAULT_FAMILY
    return current


def obj_text(mesh: ObjMesh, note: str | None = None) -> str:
    """Return the OBJ text of a mesh, nine decimals per coordinate, families in their order."""
    lines = list(mesh.header)
    if note:
        lines.append(f"# {note}")
    lines += [f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in mesh.verts]
    for name, faces in mesh.families.items():
        lines.append(f"{mesh.family_tag} {name}")
        lines += ["f " + " ".join(str(v + 1) for v in f) for f in faces]
    return "\n".join(lines) + "\n"


def write_obj(mesh: ObjMesh, path: str | Path, note: str | None = None) -> Path:
    """Write a mesh as an OBJ through the package's text route and return the path."""
    target = Path(path)
    _textio.write_text(target, obj_text(mesh, note))
    return target


def compact(
    verts: NDArray[numpy.float64], families: dict[str, Faces]
) -> tuple[NDArray[numpy.float64], dict[str, Faces]]:
    """Drop unreferenced vertices and renumber, keeping the order of first use."""
    order: dict[int, int] = {}
    for faces in families.values():
        for f in faces:
            for v in f:
                if v not in order:
                    order[v] = len(order)
    keep = numpy.fromiter(order.keys(), dtype=numpy.int64)
    return verts[keep], {n: [[order[v] for v in f] for f in fs] for n, fs in families.items()}


def read_te(path: str | Path) -> tuple[str, NDArray[numpy.float64]]:
    """Read a trailing-edge points file: a unit line, then one ``x,y,z`` row per point."""
    source = Path(path)
    rows = [r.strip() for r in source.read_text(encoding="utf-8").splitlines() if r.strip()]
    if not rows:
        raise _refuse(source, "the trailing-edge points file is empty")
    try:
        pts = numpy.array([[float(x) for x in r.split(",")] for r in rows[1:]], dtype=float)
    except ValueError as error:
        raise _refuse(source, f"a trailing-edge row is not three numbers ({error})") from error
    return rows[0], pts.reshape(-1, 3)


def write_te(path: str | Path, unit: str, midpoints: NDArray[numpy.float64]) -> Path:
    """Write a trailing-edge points file under the given unit line and return the path."""
    target = Path(path)
    rows = [unit] + [f"{x:.9f},{y:.9f},{z:.9f}" for x, y, z in midpoints]
    _textio.write_lines(target, rows)
    return target


def edge_midpoints(
    verts: NDArray[numpy.float64], faces: Faces
) -> tuple[NDArray[numpy.int64], NDArray[numpy.float64]]:
    """Return every undirected edge of the faces, sorted, and its mid-point."""
    edges = {(min(a, b), max(a, b)) for f in faces for a, b in zip(f, f[1:] + f[:1], strict=True)}
    e = numpy.array(sorted(edges), dtype=numpy.int64).reshape(-1, 2)
    return e, 0.5 * (verts[e[:, 0]] + verts[e[:, 1]])
