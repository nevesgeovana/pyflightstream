"""The frame a mesh is built in, and its conversion to the expected frame (PFS-2233, M-9).

pyflightstream expects every mesh in x aft, y right, z up, the frame the solver
takes from the mesh. A mesh built in another axis-aligned right-handed frame
declares it in its boundaries sidecar as ``mesh_frame = [x, y, z]``, the
direction each of the mesh's own axes points to, and its vertices are mapped
into the expected frame by a signed permutation matrix before the solver reads
the mesh. Face order, group names and group order are kept, because the order
of the faces moves the solver's results.

No arbitrary rotation is accepted: only the 24 axis-aligned right-handed frames.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pyflightstream._digest import file_sha256
from pyflightstream._errors import MeshFrameError

__all__ = [
    "EXPECTED_MESH_FRAME",
    "MESH_FRAME_WORDS",
    "MeshFrameError",
    "convert_obj_frame",
    "frame_matrix",
    "mesh_frame_record",
    "parse_mesh_frame",
]

#: What the mesh's +x, +y and +z point to in the expected frame.
EXPECTED_MESH_FRAME: tuple[str, str, str] = ("aft", "right", "up")

#: Each accepted word as the unit vector it names in the expected frame
#: (x aft, y right, z up), and the axis it lies along (0 x, 1 y, 2 z).
MESH_FRAME_WORDS: dict[str, tuple[int, int]] = {
    "aft": (0, 1),
    "forward": (0, -1),
    "right": (1, 1),
    "left": (1, -1),
    "up": (2, 1),
    "down": (2, -1),
}


def parse_mesh_frame(value: object) -> tuple[str, str, str]:
    """Return the three declared words, lower case, or raise :class:`MeshFrameError`.

    The three words must name three different axes (one of aft or forward, one
    of right or left, one of up or down) and form a right-handed set. A
    left-handed set is a mirrored mesh: converting it would reverse the
    orientation of every face, so it is refused.

    Parameters
    ----------
    value : object
        The ``mesh_frame`` value of the sidecar.

    Returns
    -------
    tuple of str
        What the mesh's +x, +y and +z point to.

    Raises
    ------
    MeshFrameError
        A value that is not a list of three accepted words, words that repeat
        an axis, or a left-handed set.
    """
    if (
        not isinstance(value, list | tuple)
        or len(value) != 3
        or not all(isinstance(word, str) for word in value)
    ):
        raise MeshFrameError(
            f"mesh_frame = {value!r} is not a list of three words, what the mesh's +x, +y and +z "
            'point to, as in ["forward", "left", "up"]'
        )
    words = tuple(word.strip().lower() for word in value)
    unknown = [word for word in words if word not in MESH_FRAME_WORDS]
    if unknown:
        raise MeshFrameError(
            f"mesh_frame = {list(value)!r} uses {unknown[0]!r}; the words are "
            "aft, forward, right, left, up and down"
        )
    axes = {MESH_FRAME_WORDS[word][0] for word in words}
    if len(axes) != 3:
        raise MeshFrameError(
            f"mesh_frame = {list(value)!r} names an axis twice; the three words must name "
            "one of aft or forward, one of right or left and one of up or down"
        )
    declared = (words[0], words[1], words[2])
    if _determinant(frame_matrix(declared)) < 0:
        raise MeshFrameError(
            f"mesh_frame = {list(value)!r} is left-handed, a mirrored mesh; converting it would "
            "reverse the orientation of every face, so the mesh is refused. Mirror it in the "
            "geometry tool and declare the frame of the result"
        )
    return declared


def frame_matrix(declared: Sequence[str]) -> tuple[tuple[int, int, int], ...]:
    """Return ``C_E/M``: row ``r`` states expected axis ``r`` in terms of the mesh's axes.

    The vertex ``(x, y, z)`` of the mesh is ``C_E/M @ (x, y, z)`` in the expected frame.

    Parameters
    ----------
    declared : sequence of str
        Three accepted words.

    Returns
    -------
    tuple of tuple of int
        A signed permutation matrix.
    """
    rows = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    for column, word in enumerate(declared):
        axis, sign = MESH_FRAME_WORDS[word]
        rows[axis][column] = sign
    return tuple((row[0], row[1], row[2]) for row in rows)


def _determinant(m: tuple[tuple[int, int, int], ...]) -> int:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _negated(token: bytes) -> bytes:
    """Return a number's text with its sign flipped, every digit kept as written."""
    if token.startswith(b"-"):
        return token[1:]
    return b"-" + token.removeprefix(b"+")


def _mapped(tokens: list[bytes], matrix: tuple[tuple[int, int, int], ...]) -> list[bytes]:
    """Map three coordinate tokens; a signed permutation moves and negates, never rounds."""
    out: list[bytes] = []
    for row in matrix:
        column = next(index for index, entry in enumerate(row) if entry)
        out.append(tokens[column] if row[column] > 0 else _negated(tokens[column]))
    return out


def convert_obj_frame(source: str | Path, target: str | Path, declared: Sequence[str]) -> None:
    """Write ``source`` to ``target`` with its vertices and normals in the expected frame.

    Only the coordinates of ``v`` and ``vn`` lines change, and they change by
    moving and negating the numbers as written, so no digit is rounded. Every
    other line, the face lines and the group lines among them, is copied
    byte for byte: the face order, the group names and the group order are
    those of the source.

    Parameters
    ----------
    source, target : str or Path
        The OBJ to read and the converted copy to write.
    declared : sequence of str
        The mesh's frame, three accepted words.

    Raises
    ------
    MeshFrameError
        A vertex line that does not carry three coordinates.
    """
    matrix = frame_matrix(declared)
    lines = Path(source).read_bytes().splitlines(keepends=True)
    out: list[bytes] = []
    for number, line in enumerate(lines, start=1):
        tokens = line.split()
        if tokens[:1] in ([b"v"], [b"vn"]):
            if len(tokens) < 4:
                raise MeshFrameError(
                    f"{source}: line {number} is a vertex without three coordinates"
                )
            ending = line[len(line.rstrip(b"\r\n")) :]
            moved = [tokens[0], *_mapped(tokens[1:4], matrix), *tokens[4:]]
            out.append(b" ".join(moved) + ending)
        else:
            out.append(line)
    Path(target).write_bytes(b"".join(out))


def mesh_frame_record(
    declared: Sequence[str], source: str | Path, converted: str | Path | None
) -> dict[str, object]:
    """Return the run record's ``mesh_frame`` block.

    Parameters
    ----------
    declared : sequence of str
        The declared frame.
    source : str or Path
        The mesh as the library holds it.
    converted : str or Path or None
        The converted copy, or None where the declaration is the expected frame
        and no copy was made, which then carries the source's digest.

    Returns
    -------
    dict
        ``declared``, ``matrix``, ``source_sha256`` and ``converted_sha256``.
    """
    digest = file_sha256(Path(source))
    return {
        "declared": list(declared),
        "matrix": [list(row) for row in frame_matrix(declared)],
        "source_sha256": digest,
        "converted_sha256": digest if converted is None else file_sha256(Path(converted)),
    }
