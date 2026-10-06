"""Synthetic panel meshes shared by the 0.38.0 refinement tests (FR-424, FR-425).

Every mesh is built here from an analytic surface; no test reads a research
mesh. Two families of builders:

- the structured grids of the grid tests: a cambered, tapered, swept wing
  tube (pole or zipper ends) and a cambered thin sheet, their coordinates
  cubic polynomials of the grid indices and their vertex numbering shuffled;
- the unstructured families of the remesh tests: an icosphere, a curved plate
  with a square hole, a cube and a plate cut into two families.

On top of them, :func:`sheet_with_strips` composes a level source: the sheet
grid ``G`` followed by strips extruded from its tip station, each strip a
family sharing the previous part's last row of nodes, and :func:`write_source`
writes such a mesh as an OBJ with its trailing-edge points file and its
boundaries file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CELL_QUAD = (((0, 0), (0, 1), (1, 1), (1, 0)),)
CELL_DIAG = {
    0: (((0, 0), (0, 1), (1, 1)), ((0, 0), (1, 1), (1, 0))),
    1: (((0, 0), (0, 1), (1, 0)), ((0, 1), (1, 1), (1, 0))),
}


# ------------------------------------------------------------ structured grids


def _wing(u, v):
    """Return a closed cambered section around u (TE at 0 and 1) on a straight tapered planform."""
    y = 2.0 * (1.5 * v - 0.5 * v**3) + 0.0 * u
    chord, xle = 1.0 - 0.2 * y, 0.15 * y
    x = xle + chord * (2.0 * u - 1.0) ** 2
    z = chord * (0.4 * u * (1.0 - u) * (1.0 - 2.0 * u) + 0.08 * u * (1.0 - u))
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


def _sheet(u, v):
    """Return a cambered thin sheet from the trailing edge (u = 0) to the leading edge (u = 1)."""
    y = 2.0 * (1.5 * v - 0.5 * v**3) + 0.0 * u
    chord, xle = 1.0 - 0.2 * y, 0.15 * y
    x = xle + chord * (1.0 - (3.0 * u**2 - 2.0 * u**3))
    z = chord * 0.1 * u * (1.0 - u)
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


@dataclass
class Fixture:
    """A synthetic grid family, its source faces and what the test knows of its grid."""

    name: str
    wrap: bool
    stations: int
    nodes: int
    ends: tuple[str, str]
    diag: dict[int, int] | None  # chordwise cell -> diagonal, None for quadrilaterals
    verts: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    faces: list[list[int]] = field(default_factory=list)
    te: set[int] = field(default_factory=set)
    place: dict[int, tuple[int, int]] = field(default_factory=dict)  # vertex -> (k, i)
    pole: int | None = None
    lateral: int = 0

    @property
    def le(self) -> int:
        """Return the leading edge's chordwise index."""
        return self.nodes // 2 if self.wrap else self.nodes - 1

    def surface(self, s, t):
        """Return the analytic nodes at chordwise index s and station index t."""
        u = np.asarray(s, float) / (self.nodes if self.wrap else self.nodes - 1)
        v = np.asarray(t, float) / (self.stations - 1)
        return (_wing if self.wrap else _sheet)(u[None, :], v[:, None])

    @property
    def size(self) -> float:
        """Return the diagonal of the bounding box."""
        return float(np.linalg.norm(self.verts.max(axis=0) - self.verts.min(axis=0)))


def _cell_faces(gid, k, i, n, diag):
    """Return the source faces of one lateral cell (k-major, i ascending)."""
    j = (i + 1) % n
    corners = {(0, 0): gid[k, i], (0, 1): gid[k, j], (1, 1): gid[k + 1, j], (1, 0): gid[k + 1, i]}
    template = CELL_QUAD if diag is None else CELL_DIAG[diag[i]]
    return [[int(corners[o]) for o in face] for face in template]


def _caps(fx, gid, rotate):
    """Return the zipper caps of both ends, each face rotated by `rotate`."""
    out = []
    n, h = fx.nodes, fx.le
    for k in (0, fx.stations - 1):
        r = [int(x) for x in gid[k]]
        cap = [[r[0], r[1], r[n - 1]]]
        cap += [[r[i], r[i + 1], r[n - i - 1], r[n - i]] for i in range(1, h - 1)]
        cap.append([r[h - 1], r[h], r[h + 1]])
        cap = [f[::-1] for f in cap] if k == 0 else cap
        out += [f[rotate:] + f[:rotate] for f in cap]
    return out


def build_grid(fx: Fixture, *, shuffle_faces=False, cap_rotate=1, seed=3) -> Fixture:
    """Build the source mesh of a fixture, its vertex numbering shuffled."""
    k_count, n = fx.stations, fx.nodes
    pts = fx.surface(np.arange(n), np.arange(k_count)).reshape(-1, 3)
    gid = np.arange(k_count * n).reshape(k_count, n)
    faces = []
    for k in range(k_count - 1):
        for i in range(n if fx.wrap else n - 1):
            faces += _cell_faces(gid, k, i, n, fx.diag)
    fx.lateral = len(faces)
    if fx.ends[1] == "pole":
        tip = fx.surface(np.array([fx.le]), np.array([k_count - 1]))[0, 0] * [1, 1, 0]
        pts = np.vstack([pts, (tip + [0.5 * 0.6, 0.02, 0.0])[None, :]])
        pole = len(pts) - 1
        ring = [int(x) for x in gid[-1]]
        faces += [[pole, ring[i], ring[(i + 1) % n]] for i in range(n)]
    if "zipper" in fx.ends:
        faces += _caps(fx, gid, cap_rotate)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(pts))
    fx.verts = np.empty_like(pts)
    fx.verts[perm] = pts
    fx.faces = [[int(perm[v]) for v in f] for f in faces]
    if shuffle_faces:
        fx.faces = [fx.faces[j] for j in rng.permutation(len(fx.faces))]
    fx.place = {int(perm[gid[k, i]]): (k, i) for k in range(k_count) for i in range(n)}
    fx.te = {int(perm[gid[k, 0]]) for k in range(k_count)}
    fx.pole = int(perm[len(pts) - 1]) if fx.ends[1] == "pole" else None
    return fx


NODES = 24  # nodes around a tube section, even for the zipper caps
MIRRORED = {i: (0 if i < NODES // 2 else 1) for i in range(NODES)}


def tube_pole_triangles():
    """Return a wing tube of split quadrilaterals, mirrored diagonals, open root, pole tip."""
    return build_grid(Fixture("tube-pole-triangles", True, 9, NODES, ("open", "pole"), MIRRORED))


def tube_pole_quads():
    """Return a wing tube of quadrilaterals, open root, pole tip."""
    return build_grid(Fixture("tube-pole-quads", True, 9, NODES, ("open", "pole"), None))


def tube_zipper():
    """Return a blade tube of quadrilaterals closed by a zipper cap at each end."""
    return build_grid(Fixture("tube-zipper", True, 9, NODES, ("zipper", "zipper"), None))


def sheet_quads():
    """Return a thin cambered sheet of quadrilaterals."""
    return build_grid(Fixture("sheet", False, 9, 19, ("edge", "edge"), None))


FIXTURES = [tube_pole_triangles, tube_pole_quads, tube_zipper, sheet_quads]


# ------------------------------------------------------- unstructured families


def sphere():
    """Return a unit icosphere as one family ``S``."""
    import trimesh

    from pyflightstream.workspace._refine._obj import ObjMesh

    ico = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    return ObjMesh(np.asarray(ico.vertices, dtype=float), {"S": ico.faces.tolist()})


def plate_nodes(nx: int, ny: int, width: float = 1.0) -> np.ndarray:
    """Return the nodes of an nx by ny interval grid on a gently curved sheet."""
    x, y = np.meshgrid(np.linspace(0.0, width, nx + 1), np.linspace(0.0, 1.0, ny + 1))
    z = 0.15 * np.sin(np.pi * y)
    return np.column_stack([x.ravel(), y.ravel(), z.ravel()])


def plate_cells(nx: int, keep) -> list[list[int]]:
    """Return the two triangles of every kept cell, the diagonal alternating."""
    faces = []
    for i, j in keep:
        a, b = j * (nx + 1) + i, j * (nx + 1) + i + 1
        c, d = a + nx + 1, b + nx + 1
        faces += [[a, b, d], [a, d, c]] if (i + j) % 2 else [[a, b, c], [b, d, c]]
    return faces


def holed_plate():
    """Return a curved 12 by 12 plate with a 4 by 4 square hole as one family ``P``."""
    from pyflightstream.workspace._refine._obj import ObjMesh

    keep = [(i, j) for j in range(12) for i in range(12) if not (4 <= i < 8 and 4 <= j < 8)]
    return ObjMesh(plate_nodes(12, 12), {"P": plate_cells(12, keep)})


def two_families():
    """Return a 16 by 8 plate cut at x = 1 into family ``A`` (x < 1) and ``B`` (x > 1)."""
    from pyflightstream.workspace._refine._obj import ObjMesh

    nodes = plate_nodes(16, 8, width=2.0)
    left = [(i, j) for j in range(8) for i in range(8)]
    right = [(i, j) for j in range(8) for i in range(8, 16)]
    return ObjMesh(nodes, {"A": plate_cells(16, left), "B": plate_cells(16, right)})


def cube():
    """Return the surface of the cube [-1, 1]^3 as one family ``C``, six faces of 6 by 6."""
    import trimesh

    from pyflightstream.workspace._refine._obj import ObjMesh

    box = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    fine = box.subdivide().subdivide().subdivide()
    fine.merge_vertices()
    return ObjMesh(np.asarray(fine.vertices, dtype=float), {"C": fine.faces.tolist()})


# ------------------------------------------------------------- level sources


@dataclass
class Composite:
    """A multi-family source: nodes, families in order, trailing-edge mid-points, rows."""

    verts: np.ndarray
    families: dict[str, list[list[int]]]
    te: np.ndarray
    rows: dict[str, list[list[int]]]  # family -> its node rows, the shared row first


def _te_midpoints(verts: np.ndarray, column: Sequence[int]) -> np.ndarray:
    """Return the mid-points of the edges joining consecutive nodes of a column."""
    ids = list(column)
    return 0.5 * (verts[ids[:-1]] + verts[ids[1:]])


def sheet_with_strips(
    strips: Sequence[tuple[str, str, Sequence[float]]] = (), *, grid: str = "G", te: bool = True
) -> Composite:
    """Return the sheet grid ``grid`` followed by strips extruded from its tip station.

    Each strip is ``(name, kind, widths)``: ``kind`` is ``"tri"`` (each cell
    split along a diagonal that alternates like :func:`plate_cells`) or
    ``"quad"`` (quadrilaterals, a grid when ``te``); ``widths`` are the row
    spacings beyond the previous part's last row, which the strip shares node
    for node. Every strip has the tip station's section (x and z of the
    chordwise index), so the shared rows are one curve. With ``te`` the
    trailing-edge mid-points are those of the grid's u = 0 line and of every
    quadrilateral strip's u = 0 line.
    """
    fx = sheet_quads()
    verts = [fx.verts]
    count = len(fx.verts)
    by_place = {place: v for v, place in fx.place.items()}
    tip_row = [by_place[(fx.stations - 1, i)] for i in range(fx.nodes)]
    section = fx.verts[tip_row]
    families = {grid: list(fx.faces)}
    te_points = [_te_midpoints(fx.verts, [by_place[(k, 0)] for k in range(fx.stations)])]
    rows = {grid: [[by_place[(k, i)] for i in range(fx.nodes)] for k in range(fx.stations)]}
    last = tip_row
    y = float(section[0, 1])
    for name, kind, widths in strips:
        strip_rows = [last]
        for w in widths:
            y += float(w)
            row = section.copy()
            row[:, 1] = y
            verts.append(row)
            strip_rows.append(list(range(count, count + len(row))))
            count += len(row)
        faces = []
        for j in range(len(strip_rows) - 1):
            lo, hi = strip_rows[j], strip_rows[j + 1]
            for i in range(len(lo) - 1):
                a, b, c, d = lo[i], lo[i + 1], hi[i + 1], hi[i]
                if kind == "quad":
                    faces.append([a, b, c, d])
                elif (i + j) % 2:
                    faces += [[a, b, c], [a, c, d]]
                else:
                    faces += [[a, b, d], [b, c, d]]
        families[name] = faces
        rows[name] = strip_rows
        last = strip_rows[-1]
        if kind == "quad":
            all_verts = np.vstack(verts)
            te_points.append(_te_midpoints(all_verts, [r[0] for r in strip_rows]))
    points = np.vstack(te_points) if te else np.zeros((0, 3))
    return Composite(np.vstack(verts), families, points, rows)


def obj_text(verts: np.ndarray, families: dict[str, list[list[int]]]) -> str:
    """Return the OBJ text of a mesh, nine decimals per coordinate, ``g`` families in order."""
    lines = ["# synthetic source of the 0.38.0 refinement tests"]
    lines += [f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in verts]
    for name, faces in families.items():
        lines.append(f"g {name}")
        lines += ["f " + " ".join(str(v + 1) for v in f) for f in faces]
    return "\n".join(lines) + "\n"


def write_source(
    folder: Path,
    stem: str,
    mesh: Composite,
    *,
    boundaries: bool = True,
    refine_toml: str | None = None,
) -> Path:
    """Write a source as ``folder/stem.obj`` with its points, boundaries and refinement files.

    The trailing-edge points file ``<stem>.te.txt`` is written when the mesh
    has trailing-edge points; the boundaries file lists the families in order
    and names that points file.
    """
    folder.mkdir(parents=True, exist_ok=True)
    obj = folder / f"{stem}.obj"
    obj.write_bytes(obj_text(mesh.verts, mesh.families).encode("utf-8"))
    if len(mesh.te):
        rows = ["METER"] + [f"{x:.9f},{y:.9f},{z:.9f}" for x, y, z in mesh.te]
        (folder / f"{stem}.te.txt").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
    if boundaries:
        names = ", ".join(f'"{n}"' for n in mesh.families)
        text = f"boundaries = [{names}]\n"
        if len(mesh.te):
            text += f'\n[trailing_edges]\nfile = "{stem}.te.txt"\n'
        (folder / f"{stem}.boundaries.toml").write_bytes(text.encode("utf-8"))
    if refine_toml is not None:
        (folder / f"{stem}.refine.toml").write_bytes(refine_toml.encode("utf-8"))
    return obj


# ------------------------------------------------------------- reading levels


def read_mesh(path: Path) -> tuple[np.ndarray, dict[str, list[list[int]]]]:
    """Read an OBJ written by a test or a level: ``v`` rows and ``g`` families, 0-based faces."""
    verts: list[list[float]] = []
    families: dict[str, list[list[int]]] = {}
    current = "default"
    for line in path.read_text(encoding="utf-8").splitlines():
        words = line.split()
        if not words or words[0].startswith("#"):
            continue
        if words[0] == "v":
            verts.append([float(w) for w in words[1:4]])
        elif words[0] in ("g", "o"):
            current = " ".join(words[1:])
        elif words[0] == "f":
            families.setdefault(current, []).append([int(w.split("/")[0]) - 1 for w in words[1:]])
    return np.asarray(verts, dtype=float).reshape(-1, 3), families


def face_coordinates(verts: np.ndarray, faces: list[list[int]]) -> list[tuple]:
    """Return each face as the tuple of its vertices' coordinates, from its first vertex."""
    return [tuple(tuple(float(c) for c in verts[v]) for v in f) for f in faces]


def open_loops(faces: list[list[int]]) -> list[set[int]]:
    """Return the node sets of the open boundary loops: the components of the edges used once."""
    count: dict[tuple[int, int], int] = {}
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1], strict=True):
            key = (min(a, b), max(a, b))
            count[key] = count.get(key, 0) + 1
    parent: dict[int, int] = {}

    def root(v: int) -> int:
        while parent.setdefault(v, v) != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for (a, b), n in count.items():
        if n == 1:
            parent[root(a)] = root(b)
    loops: dict[int, set[int]] = {}
    for (a, b), n in count.items():
        if n == 1:
            loops.setdefault(root(a), set()).update((a, b))
    return list(loops.values())


def open_loop_count(faces: list[list[int]]) -> int:
    """Return the number of independent open boundary loops: edges - nodes + components.

    For disjoint simple loops it is their number; a crack along a curve whose
    two sides hold different nodes adds one loop per slit even where the slits
    touch the outer boundary, which a count of components would miss.
    """
    loops = open_loops(faces)
    edges = 0
    count: dict[tuple[int, int], int] = {}
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1], strict=True):
            key = (min(a, b), max(a, b))
            count[key] = count.get(key, 0) + 1
    edges = sum(1 for n in count.values() if n == 1)
    return edges - sum(len(loop) for loop in loops) + len(loops)
