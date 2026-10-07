"""The OBJ and trailing-edge points files a refinement reads and writes (FR-424).

A mesh is one vertex array and an ordered mapping from family name to its
faces, each face a list of 0-based vertex indices. Families are the OBJ
groups (``g``) or objects (``o``) in file order; the comment lines before the
first vertex are kept and written back. Every write goes through the
package's one text route, so a level holds no carriage return (NFR-32).
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy
from numpy.typing import NDArray

import pyflightstream._textio as _textio
from pyflightstream._decimal import plain_decimal
from pyflightstream._errors import InputArtifactError
from pyflightstream._lengths import METRES_PER_UNIT, scale

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
    #: Per vertex, the coordinate text to write (the source's ``v`` words, as read),
    #: or None to write the number itself; empty to write every vertex's number.
    vertex_text: list[str | None] = field(default_factory=list)

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
    index counts back from the last vertex read. A vertex coordinate that is
    not a finite number, a face index that is not an integer, and a face with
    fewer than three vertices or naming a vertex that does not exist, are
    refused naming the file and the line.
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
            if len(verts) > len(mesh.vertex_text):
                mesh.vertex_text.append(" ".join(s.split()[1:4]))
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
        x, y, z = (_coordinate(where, word) for word in words[:3])
        verts.append((x, y, z))
    elif tag == "f":
        idx = [_index(where, tok.split("/")[0]) for tok in rest.split()]
        face = [i - 1 if i > 0 else len(verts) + i for i in idx]
        if len(face) < 3 or any(not 0 <= v < len(verts) for v in face):
            raise _refuse_at(where, "a face with fewer than three vertices or a missing vertex")
        mesh.families.setdefault(current, []).append(face)
    elif tag in ("g", "o"):
        mesh.family_tag = tag
        return rest.strip() or DEFAULT_FAMILY
    return current


def _coordinate(where: str, word: str) -> float:
    """Return a vertex coordinate, refusing a word that is not a finite number."""
    try:
        value = float(word)
    except ValueError:
        raise _refuse_at(where, f"a vertex whose coordinate {word!r} is not a number") from None
    if not math.isfinite(value):
        raise _refuse_at(where, f"a vertex whose coordinate {word!r} is not finite")
    return value


def _index(where: str, word: str) -> int:
    """Return a face's vertex index, refusing a word that is not an integer."""
    try:
        return int(word)
    except ValueError:
        raise _refuse_at(where, f"a face whose vertex index {word!r} is not an integer") from None


def coordinates(point: NDArray[numpy.float64]) -> str:
    """Return a point as written: each coordinate the plain decimal that reads back to it.

    The shortest round-trip digits and never an exponent
    (:func:`pyflightstream._decimal.plain_decimal`), so a node written and
    read back is the node computed, at any scale (FR-424 R7).
    """
    return " ".join(plain_decimal(float(x)) for x in point)


def obj_text(mesh: ObjMesh, note: str | None = None) -> str:
    """Return the OBJ text of a mesh, families in their order.

    A vertex whose source text is known (``vertex_text``) is written as the
    source wrote it; every other is written by :func:`coordinates`.
    """
    lines = list(mesh.header)
    if note:
        lines.append(f"# {note}")
    known = mesh.vertex_text if len(mesh.vertex_text) == len(mesh.verts) else []
    lines += [
        f"v {known[i] if known and known[i] is not None else coordinates(p)}"
        for i, p in enumerate(mesh.verts)
    ]
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


#: The suffix of a mesh's boundaries file, beside it.
SIDECAR_SUFFIX = ".boundaries.toml"
#: The suffix of a mesh's trailing-edge points file when its boundaries file names none.
TE_SUFFIX = ".te.txt"


def read_sidecar(obj: str | Path) -> tuple[Path, dict[str, Any]] | None:
    """Return a mesh's boundaries file and its tables, or None when it has none.

    Raises
    ------
    InputArtifactError
        The file is not TOML; nothing was written.
    """
    sidecar = Path(obj).with_name(Path(obj).stem + SIDECAR_SUFFIX)
    if not sidecar.is_file():
        return None
    try:
        return sidecar, tomllib.loads(sidecar.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise InputArtifactError(
            f"{sidecar}: not TOML ({error}). Fix the file and run again. Nothing was written.",
            kind=KIND,
        ) from error


def te_file(obj: str | Path) -> Path | None:
    """Return a mesh's trailing-edge points file, or None when it has none.

    It is the file the boundaries file names under ``[trailing_edges] file``,
    or else ``<stem>.te.txt`` beside the mesh. The refinement and the audit
    both read it here, so they refuse the same inputs (FR-424 R11).

    Raises
    ------
    InputArtifactError
        The boundaries file is not TOML, or names a points file that does not
        exist; nothing was written.
    """
    read = read_sidecar(obj)
    named = None
    if read is not None:
        table = read[1].get("trailing_edges")
        named = table.get("file") if isinstance(table, dict) else None
    if read is not None and isinstance(named, str):
        file = read[0].parent / named
        if not file.is_file():
            raise InputArtifactError(
                f"{read[0]}: names the trailing-edge file {named}, which does not exist. "
                "Write the points file or remove the key and run again. Nothing was written.",
                kind=KIND,
            )
        return file
    default = Path(obj).with_name(Path(obj).stem + TE_SUFFIX)
    return default if default.is_file() else None


def mesh_unit(obj: str | Path) -> str | None:
    """Return the length unit the boundaries file states for the mesh, ``[import] units``.

    The unit a raw mesh is written in is stated there and never assumed
    (:class:`pyflightstream.cases.mesh.MeshImport`); None when it is not stated.
    """
    read = read_sidecar(obj)
    table = None if read is None else read[1].get("import")
    units = table.get("units") if isinstance(table, dict) else None
    return units.strip().upper() if isinstance(units, str) and units.strip() else None


@dataclass(frozen=True)
class TrailingPoints:
    """A mesh's trailing-edge points: the file's unit line and the points in the mesh's unit.

    ``to_file`` multiplies a length in the mesh's unit into the file's unit,
    so a points file written back keeps the source file's unit line.
    """

    unit: str
    points: NDArray[numpy.float64]
    to_file: float


def te_points(obj: str | Path) -> TrailingPoints | None:
    """Read a mesh's trailing-edge points and convert them to the mesh's unit.

    The points file states its unit on its first line; the mesh's unit is the
    ``[import] units`` of its boundaries file. When both are stated and differ
    the points are converted (:func:`pyflightstream._lengths.scale`), as the
    package converts a points file for a run; when the mesh states none, the
    points are read in the mesh's unit.

    Raises
    ------
    InputArtifactError
        The points file, or the boundaries file that names it, is refused
        (:func:`te_file`, :func:`read_te`), or the two units cannot be
        converted (a unit that names no scale); nothing was written.
    """
    file = te_file(obj)
    if file is None:
        return None
    unit, points = read_te(file)
    target = mesh_unit(obj)
    if target is None or unit.strip().upper() == target:
        return TrailingPoints(unit, points, 1.0)
    into, back = scale(unit.strip().upper(), target), scale(target, unit.strip().upper())
    if into is None or back is None:
        raise InputArtifactError(
            f"{file}: its points are in {unit} and the mesh is in {target} (the [import] units "
            "of its boundaries file), and one of the two names no length scale, so the points "
            f"cannot be converted. Give both in one of {', '.join(METRES_PER_UNIT)} and run "
            "again. Nothing was written.",
            kind=KIND,
        )
    return TrailingPoints(unit, points * into, back)


def read_te(path: str | Path) -> tuple[str, NDArray[numpy.float64]]:
    """Read a trailing-edge points file: a unit line, then one ``x,y,z`` row per point.

    Every row holds exactly three finite numbers; any other row is refused
    naming the file and its line, so no row is ever read as part of another
    point.
    """
    source = Path(path)
    lines = source.read_text(encoding="utf-8").splitlines()
    rows = [(n, r.strip()) for n, r in enumerate(lines, start=1) if r.strip()]
    if not rows:
        raise _refuse(source, "the trailing-edge points file is empty")
    points = [_te_row(source, number, row) for number, row in rows[1:]]
    return rows[0][1], numpy.array(points, dtype=float).reshape(-1, 3)


def _te_row(source: Path, number: int, row: str) -> list[float]:
    """Return one trailing-edge row as its three coordinates, refusing any other row."""
    words = [w.strip() for w in row.split(",")]
    said = None
    if len(words) != 3:
        said = f"holds {len(words)} number(s)"
    else:
        try:
            values = [float(w) for w in words]
        except ValueError:
            said = "holds a word that is not a number"
        else:
            if all(math.isfinite(v) for v in values):
                return values
            said = "holds a number that is not finite"
    raise _refuse(source, f"line {number} {row!r} {said}; a trailing-edge row is x,y,z")


def write_te(path: str | Path, unit: str, midpoints: NDArray[numpy.float64]) -> Path:
    """Write a trailing-edge points file under the given unit line and return the path."""
    target = Path(path)
    rows = [unit] + [coordinates(p).replace(" ", ",") for p in midpoints]
    _textio.write_lines(target, rows)
    return target


def edge_midpoints(
    verts: NDArray[numpy.float64], faces: Faces
) -> tuple[NDArray[numpy.int64], NDArray[numpy.float64]]:
    """Return every undirected edge of the faces, sorted, and its mid-point."""
    edges = {(min(a, b), max(a, b)) for f in faces for a, b in zip(f, f[1:] + f[:1], strict=True)}
    e = numpy.array(sorted(edges), dtype=numpy.int64).reshape(-1, 2)
    return e, 0.5 * (verts[e[:, 0]] + verts[e[:, 1]])
