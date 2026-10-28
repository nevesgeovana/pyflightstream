"""Prepare an OBJ for the refinement: families split into patches, a refine file and a node list.

``pyfs-workspace geometry prepare-to-refine`` (optional; the refinement reads
any OBJ and refine file without it) writes, beside the mesh:

1. ``<stem>_patches.obj``: every family cut into PATCHES, named
   ``<family>_<NNN>_grid`` or ``<family>_<NNN>_mixed``. A family is first cut
   along its sharp edges (:data:`._geometry.RIDGE_DEGREES`); in each piece, the
   quadrilaterals joined edge to edge whose layout the refinement recovers as a
   grid (a sheet, a tube or a multiblock grid, :mod:`._blocks`) are a grid patch
   each, and the other faces, joined edge to edge, a mixed patch each. The
   original families keep their order; within each, the patches are numbered
   from the largest extent along y down, and each patch keeps its faces in the
   source's order.
2. ``<stem>_patches.refine.toml``: one table per patch, ``method = "grid"`` or
   ``"remesh"`` at factor 1 for the user to edit, the quad-dominant remesh,
   ``[components]`` grouping each family's patches back into the family, and a
   ``[[perimeter]]`` naming the node list with ``te_families``.
3. ``<stem>_patches.nodes.txt``: the node list the refinement reads (an ANSA SET
   node-window export, ``Id, Name, X, Y, Z``): for each grid patch, the nodes of
   the rearmost line of its outer boundary (:func:`._obj.rearmost_edges`) whose
   edges lie in or near the plane across the aft direction (the yz plane for
   +x), within ``max_angle`` (:func:`near_yz`),
   ordered along y. A node two patches share is listed
   once.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy
from numpy.typing import NDArray

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream.workspace._refine import _blocks, _geometry, _lines, _obj
from pyflightstream.workspace._refine._obj import Faces, ObjMesh

Points = NDArray[numpy.float64]

#: The suffix of the prepared files' stem.
PATCHES_SUFFIX = "_patches"
#: The largest angle, in degrees, between a trailing-edge edge and the yz plane when none
#: is stated: a trailing edge runs across the flow (along y on a wing, along z on a fin),
#: at its sweep from that plane, while a tip or a root line runs along the flow.
MAX_ANGLE = 45.0
#: A quadrilateral piece of fewer faces than this is not a grid patch: the islands of
#: quadrilaterals a quad-dominant mesh holds among its triangles stay in their mixed patch.
GRID_MIN_FACES = 4


@dataclass(frozen=True)
class PreparedMesh:
    """What prepare-to-refine wrote: the patches OBJ, the refine file, the node list, the patches.

    ``patches`` maps each original family to its patch names in order.
    """

    obj: Path
    config: Path
    nodes: Path
    patches: dict[str, list[str]]


def prepare_to_refine(
    mesh: str | Path,
    *,
    max_angle: float = MAX_ANGLE,
    aft: tuple[float, float, float] = _obj.AFT,
    overwrite: bool = False,
) -> PreparedMesh:
    """Split an OBJ's families into patches and write its refine file and node list.

    Parameters
    ----------
    mesh : str or pathlib.Path
        The source OBJ; it is never modified.
    max_angle : float
        The largest angle, in degrees, between a listed edge and the plane
        across ``aft`` (default :data:`MAX_ANGLE`).
    aft : tuple of float
        The direction from the nose to the tail (default +x).
    overwrite : bool
        Replace the prepared files of an earlier run.

    Returns
    -------
    PreparedMesh
        The three files written and the patches of each family.

    Raises
    ------
    InputArtifactError
        The mesh cannot be read, or a prepared file exists and ``overwrite`` is false.
    """
    source = Path(mesh)
    aft = _obj.aft_direction(aft, str(source))
    obj = _obj.read_obj(source)
    stem = source.stem + PATCHES_SUFFIX
    targets = [
        source.with_name(f"{stem}.obj"),
        source.with_name(f"{stem}.refine.toml"),
        source.with_name(f"{stem}.nodes.txt"),
    ]
    existing = [t for t in targets if t.exists()]
    if existing and not overwrite:
        raise InputArtifactError(
            f"{existing[0]}: exists; pass overwrite (CLI: --overwrite) to replace the prepared "
            "files. Nothing was written.",
            kind=_obj.KIND,
        )
    families: dict[str, Faces] = {}
    kinds: dict[str, str] = {}
    patches: dict[str, list[str]] = {}
    for name, faces in obj.families.items():
        found = sorted(_patches(obj.verts, faces), key=lambda p: -_extent_y(obj.verts, faces, p[1]))
        patches[name] = []
        for number, (kind, members) in enumerate(found, start=1):
            patch = f"{name}_{number:03d}_{kind}"
            families[patch] = [faces[i] for i in sorted(members)]
            kinds[patch] = kind
            patches[name].append(patch)
    rows, listed = _te_rows(obj.verts, families, kinds, max_angle, aft)
    note = f"patches of {source.name}, prepared by pyflightstream prepare-to-refine"
    out = ObjMesh(obj.verts, families, list(obj.header), obj.family_tag, list(obj.vertex_text))
    _obj.write_obj(out, targets[0], note)
    _textio.write_text(targets[2], "\n".join(["#  Id, Name, X , Y, Z", *rows]) + "\n")
    te_families = [n for n, ps in patches.items() if any(p in listed for p in ps)]
    _textio.write_text(targets[1], _toml(source, targets[2], patches, kinds, te_families))
    return PreparedMesh(targets[0], targets[1], targets[2], patches)


def _patches(verts: Points, faces: Faces) -> list[tuple[str, list[int]]]:
    """Return a family's patches as (kind, face indices): its grids first, then the rest."""
    dihedral = _geometry.dihedral_degrees(verts, faces)
    sharp = {e for e, angle in dihedral.items() if angle > _geometry.RIDGE_DEGREES}
    holders = _geometry.edge_faces(faces)
    quads = {i for i, f in enumerate(faces) if len(f) == 4}
    out: list[tuple[str, list[int]]] = []
    taken: set[int] = set()
    for piece in _joined(quads, holders, sharp, quads):
        if len(piece) >= GRID_MIN_FACES and _is_grid(verts, [faces[i] for i in piece]):
            out.append(("grid", piece))
            taken.update(piece)
    rest = set(range(len(faces))) - taken
    for piece in _joined(rest, holders, sharp, rest):
        out.append(("mixed", piece))
    return out


def _joined(
    members: set[int],
    holders: dict[tuple[int, int], list[int]],
    sharp: set[tuple[int, int]],
    allowed: set[int],
) -> list[list[int]]:
    """Return the members joined through edges that are not sharp, each piece once."""
    neighbours: dict[int, set[int]] = {i: set() for i in members}
    for edge, fs in holders.items():
        if edge in sharp:
            continue
        inside = [f for f in fs if f in allowed]
        if len(inside) == 2:
            a, b = inside
            neighbours[a].add(b)
            neighbours[b].add(a)
    pieces: list[list[int]] = []
    seen: set[int] = set()
    for start in sorted(members):
        if start in seen:
            continue
        stack, piece = [start], {start}
        while stack:
            for n in neighbours[stack.pop()] - piece:
                piece.add(n)
                stack.append(n)
        seen |= piece
        pieces.append(sorted(piece))
    return pieces


def rearmost_lines(
    verts: Points,
    faces: Faces,
    aft: tuple[float, float, float] = _obj.AFT,
    max_angle: float = MAX_ANGLE,
) -> set[tuple[int, int]]:
    """Return a family's trailing edge found from the mesh alone.

    The family is cut along its sharp edges into pieces; a piece's perimeter is
    its boundary edges and the sharp edges inside it (a sharp trailing edge
    joins the upper and the lower surface of a wing whose leading edge is
    smooth). Of each piece, only the perimeter reaching furthest aft is read
    (:func:`._obj.rearmost_perimeter`), and of it the edges the piece lies
    forward of (:func:`._obj.rearmost_edges`) that lie in or near the plane
    across ``aft`` (the yz plane for +x), within ``max_angle`` (:func:`near_yz`).
    """
    dihedral = _geometry.dihedral_degrees(verts, faces)
    sharp = {e for e, angle in dihedral.items() if angle > _geometry.RIDGE_DEGREES}
    holders = _geometry.edge_faces(faces)
    every = set(range(len(faces)))
    found: set[tuple[int, int]] = set()
    for piece in _joined(every, holders, sharp, every):
        members = [faces[i] for i in piece]
        held = _geometry.edge_faces(members)
        perimeter = {e for e, fs in held.items() if len(fs) == 1 or e in sharp}
        rear = _obj.rearmost_perimeter(verts, members, perimeter, aft)
        found |= _obj.rearmost_edges(verts, members, rear, aft)
    return near_yz(verts, found, max_angle, aft)


def near_yz(
    verts: Points,
    edges: set[tuple[int, int]],
    max_angle: float = MAX_ANGLE,
    aft: tuple[float, float, float] = _obj.AFT,
) -> set[tuple[int, int]]:
    """Return the edges whose tangent makes ``max_angle`` degrees or less with the plane across aft.

    The plane is the one normal to ``aft``, the yz plane for the default +x: a
    trailing edge runs across the flow, whichever axis the flow runs along.
    """
    most = numpy.sin(numpy.radians(max_angle))
    axis = numpy.asarray(aft, dtype=float)
    axis = axis / float(numpy.linalg.norm(axis))
    out = set()
    for a, b in edges:
        tangent = verts[b] - verts[a]
        length = float(numpy.linalg.norm(tangent))
        if length > 0.0 and abs(float(tangent @ axis)) <= most * length:
            out.add((a, b))
    return out


def _is_grid(verts: Points, faces: Faces) -> bool:
    """Return whether the refinement recovers the quadrilaterals as a grid (a sheet by a side)."""
    found = _blocks.recover_family(verts, faces, ())
    if not isinstance(found, str):
        return True
    for side in sorted(_lines.boundary_sides(verts, faces), key=lambda s: -len(s)):
        if not isinstance(_blocks.recover_family(verts, faces, side), str):
            return True
    return False


def _extent_y(verts: Points, faces: Faces, members: list[int]) -> float:
    ys = verts[sorted({v for i in members for v in faces[i]}), 1]
    return float(ys.max() - ys.min())


def _te_rows(
    verts: Points,
    families: dict[str, Faces],
    kinds: dict[str, str],
    max_angle: float,
    aft: tuple[float, float, float],
) -> tuple[list[str], set[str]]:
    """Return the node-list rows of the grid patches' rearmost lines, and the patches listed."""
    rows: list[str] = []
    listed: set[str] = set()
    written: set[int] = set()
    for name, faces in families.items():
        if kinds[name] != "grid":
            continue
        held = _geometry.edge_faces(faces)
        ring = _obj.rearmost_perimeter(
            verts, faces, {e for e, fs in held.items() if len(fs) == 1}, aft
        )
        edges = near_yz(verts, _obj.rearmost_edges(verts, faces, ring, aft), max_angle, aft)
        nodes = sorted({v for e in edges for v in e} - written, key=lambda v: float(verts[v, 1]))
        if not nodes:
            continue
        listed.add(name)
        written.update(nodes)
        for v in nodes:
            x, y, z = (repr(float(c)) for c in verts[v])
            rows.append(f"{v + 1}, {name}, {x}, {y}, {z}")
    if not rows:
        warn(
            "prepare-to-refine: no grid patch has a rearmost line within "
            f"{max_angle:g} degrees of the plane across the aft direction; the node list is empty",
            PyflightstreamWarning,
            stacklevel=3,
        )
    return rows, listed


def _toml(
    source: Path,
    nodes: Path,
    patches: dict[str, list[str]],
    kinds: dict[str, str],
    te_families: list[str],
) -> str:
    """Return the refine file text: one table per patch, the components and the perimeter."""
    lines = [
        f"# Refine file prepared by pyflightstream prepare-to-refine from {source.name}.",
        "# Edit the factors (and the method) of each patch; the [components] put each",
        "# family's patches back together in the level.",
        "",
        "[refine]",
        'elements = "quad-dominant"',
        "",
    ]
    for members in patches.values():
        for patch in members:
            method = "grid" if kinds[patch] == "grid" else "remesh"
            lines += [f"[families.{_key(patch)}]", f'method = "{method}"', "factor = 1.0", ""]
    lines.append("[components]")
    for family, members in patches.items():
        listed = ", ".join(f'"{m}"' for m in members)
        lines.append(f"{_key(family)} = [{listed}]")
    lines += [
        "",
        "# The rearmost line of each grid patch, its edges near the yz plane; the",
        "# trailing edges of te_families are written per family into the level.",
        "[[perimeter]]",
        f'file = "{nodes.name}"',
        "te_families = [" + ", ".join(f'"{n}"' for n in te_families) + "]",
        "",
    ]
    return "\n".join(lines)


def _key(name: str) -> str:
    """Return a TOML key: the name bare when it is one, else quoted."""
    bare = bool(name) and all(c.isascii() and (c.isalnum() or c in "_-") for c in name)
    return name if bare else '"' + name.replace('"', "'") + '"'
