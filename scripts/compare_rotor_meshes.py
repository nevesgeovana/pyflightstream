"""Compare rotor meshes surface by surface, straight from the solver's own `.fsm` files.

Usage::

    python scripts/compare_rotor_meshes.py <sector.fsm> <wheel.fsm> [<other.fsm> ...]

It answers one question a campaign asks of its geometries: is this full wheel the
periodic sector completed, or another body? For every surface of every file it prints
the face count, the axial and radial extent and the wetted area; then, for the files
after the first, how many vertices of each surface land on the FIRST file's surface of
that name, and whether each blade is a rotation of the first blade about x.

It reads the mesh block through the package's own reader (``pyflightstream._fsm``), so
the format has one reader: the boundary names, the triangles, the boundary each face
belongs to (the measured per-face row) and the vertex coordinates, every one located by
the block's own counts. The element count the block states first is not used; the
package documents it as untrustworthy (one campaign geometry states 7848 where every
array holds 7784). No solver, no licence.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from pathlib import Path

from pyflightstream._fsm import MeshReadError, _mesh_block, boundary_names


def load(path: Path) -> tuple[list[str], list[list[int]], list[int], list[list[float]]]:
    """Return (surface names, the three vertex indices per face, the surface of each face, xyz).

    The vertex indices are 1-based, as the file writes them, and the surface of a face is
    its 1-based boundary position.
    """
    try:
        names = boundary_names(path)
        vertices, triangles, _flags, owners = _mesh_block(path)
    except MeshReadError as error:
        raise SystemExit(str(error)) from error
    if names is None:
        raise SystemExit(f"{path.name}: carries no mesh block")
    if not owners:
        raise SystemExit(f"{path.name}: no per-face row names the boundary of every face")
    triangle = [[face[corner] + 1 for face in triangles] for corner in range(3)]
    xyz = [[vertex[axis] for vertex in vertices] for axis in range(3)]
    return list(names), triangle, list(owners), xyz


def surface(
    names: Sequence[str],
    triangle: Sequence[Sequence[int]],
    of_face: Sequence[int],
    xyz: Sequence[Sequence[float]],
    wanted: str,
) -> tuple[int, list[tuple[float, float, float]], float]:
    """Return the face count, the vertices and the wetted area of one surface."""
    index = names.index(wanted) + 1
    faces = [f for f, s in enumerate(of_face) if s == index]
    vertices = sorted({triangle[c][f] - 1 for f in faces for c in range(3)})
    points = [(xyz[0][v], xyz[1][v], xyz[2][v]) for v in vertices]
    area = 0.0
    for f in faces:
        p = [tuple(xyz[c][triangle[k][f] - 1] for c in range(3)) for k in range(3)]
        u = [p[1][c] - p[0][c] for c in range(3)]
        v = [p[2][c] - p[0][c] for c in range(3)]
        cross = (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )
        area += 0.5 * math.sqrt(sum(c * c for c in cross))
    return len(faces), points, area


def _extent(points: Sequence[tuple[float, float, float]]) -> str:
    axial = [p[0] for p in points]
    radial = [math.hypot(p[1], p[2]) for p in points]
    return (
        f"x [{min(axial):.4f}, {max(axial):.4f}] r [{min(radial):.4f}, {max(radial):.4f}]"
        if points
        else "empty"
    )


def main(argv: list[str]) -> int:
    """Print the comparison of every named mesh against the first one."""
    if len(argv) < 2:
        print(__doc__)
        return 2
    files = [Path(a) for a in argv]
    loaded = {path: load(path) for path in files}
    first = files[0]
    reference: dict[str, set[tuple[float, float, float]]] = {}
    for path in files:
        names, triangle, of_face, xyz = loaded[path]
        print(f"== {path.name}: {len(xyz[0])} vertices, {len(of_face)} faces, surfaces {names}")
        for name in names:
            faces, points, area = surface(names, triangle, of_face, xyz, name)
            rounded = {(round(x, 9), round(y, 9), round(z, 9)) for x, y, z in points}
            shared = ""
            if path is first:
                reference[name] = rounded
            elif name in reference:
                shared = (
                    f", {len(rounded & reference[name])} of {len(rounded)} shared with {first.name}"
                )
            print(f"   {name:8s} faces {faces:6d}  {_extent(points)}  area {area:.5f} m2{shared}")
        blades = [n for n in names if n.lower().startswith("blade")]
        if len(blades) > 1:
            base = {
                (round(x, 6), round(y, 6), round(z, 6))
                for x, y, z in surface(names, triangle, of_face, xyz, blades[0])[1]
            }
            for order, blade in enumerate(blades[1:], start=1):
                points = surface(names, triangle, of_face, xyz, blade)[1]
                best = 0
                for sign in (1, -1):
                    angle = -sign * 2 * math.pi * order / len(blades)
                    cos, sin = math.cos(angle), math.sin(angle)
                    turned = {
                        (round(x, 6), round(cos * y - sin * z, 6), round(sin * y + cos * z, 6))
                        for x, y, z in points
                    }
                    best = max(best, len(turned & base))
                print(
                    f"   {blade:8s} {best} of {len(points)} vertices land on {blades[0]} "
                    f"after turning back {360 * order // len(blades)} degrees about x"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
