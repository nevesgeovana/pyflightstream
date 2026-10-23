"""Grid families resampled as one layout: neighbouring grids, and a lone multiblock family.

(FR-932, FR-915, FR-920, FR-921).

GRIDS THAT SHARE NODES ARE RESAMPLED TOGETHER (FR-932). The grid families of
quadrilaterals that touch, sheets and multiblock families alike, are taken
as one surface: the edges where two of them meet are cut, and the grid line
through each is traced on to its end like a separatrix
(:func:`._blocks.recover_joined`), so the union is cut into four-sided
patches each inside one family, and every curve two families share is the
side of a patch, an ARC, resampled ONCE: both families hold the same nodes on
it. Each new cell is written back to the family of its patch, oriented like
that patch's source faces, and each family's faces are written in its own
source order (FR-921, the nearest source face's position). A lone multiblock
family is the same layout with one family.

THE COUNT OF AN ARC (FR-915) is ``max(1, round(f m))`` of its m source
intervals, f the factor of each family holding it in the arc's direction
(``factor`` in both; a sheet's ``chordwise`` along its stations and
``spanwise`` along its columns). Two families giving one arc different counts
are refused naming both and the curve, before any work (FR-925). A side whose
``f m`` is below 1 is kept and reported, as on a lone multiblock family.

A family that cannot join a layout, a tube, a family with a triangle, or one
that keeps its first row (FR-430), and the touching grids whose union is not a
layout of four-sided patches, are left to the rule before this one: the first
of them in the source's family order is a grid, and a later one sharing its
nodes is remeshed, or refused under ``method = "grid"``.

This module imports neither scipy nor rtree (FR-924).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import numpy

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream.workspace._refine import _blocks
from pyflightstream.workspace._refine._config import FamilySpec
from pyflightstream.workspace._refine._geometry import Faces, Points, edge_faces, order_like
from pyflightstream.workspace._refine._grid import Grid, GridLevel
from pyflightstream.workspace._refine._obj import KIND

Edge = tuple[int, int]
Recovered = Grid | _blocks.Blocks


@dataclass(frozen=True, eq=False)
class Layout:
    """Grid families resampled as one multiblock layout.

    Attributes
    ----------
    names : tuple of str
        Its families, in the source's family order.
    kinds : tuple of str
        Each family's own layout: ``"sheet"`` or ``"multiblock"``.
    blocks : Blocks
        The layout of their faces taken together, in the order of ``names``.
    owner : tuple of int
        Per patch, the index in ``names`` of the family holding it.
    counts : tuple of int
        Per arc, its new interval count.
    kept : dict
        Per family, the patch sides its factor cannot coarsen (FR-915).
    """

    names: tuple[str, ...]
    kinds: tuple[str, ...]
    blocks: _blocks.Blocks
    owner: tuple[int, ...]
    counts: tuple[int, ...]
    kept: Mapping[str, list[dict[str, object]]]

    def patches_of(self, name: str) -> list[int]:
        """Return the patches of one family, in layout order."""
        i = self.names.index(name)
        return [p for p, o in enumerate(self.owner) if o == i]

    def changes(self, name: str) -> bool:
        """Return whether resampling changes the nodes of any side of the family's patches.

        Read from the counts alone, before any family is resampled (FR-424,
        FR-925); any side changing is taken to change every curve it shares.
        """
        arcs = {arc for p in self.patches_of(name) for arc, _ in self.blocks.sides[p]}
        return any(self.counts[a] != len(self.blocks.arcs[a]) - 1 for a in arcs)


def _refuse(text: str) -> InputArtifactError:
    return InputArtifactError(f"{text}. Nothing was written.", kind=KIND)


def _joinable(grid: Recovered, faces: Faces) -> bool:
    """Return whether a grid family can join a layout: quadrilaterals as a sheet or multiblock."""
    sheet = isinstance(grid, Grid) and grid.layout == "sheet"
    return (sheet or isinstance(grid, _blocks.Blocks)) and all(len(f) == 4 for f in faces)


def _touching(names: Sequence[str], nodes: Mapping[str, set[int]]) -> list[list[str]]:
    """Return the groups of families joined by shared nodes, each in the order of ``names``."""
    groups: list[list[str]] = []
    for name in names:
        hit = [g for g in groups if any(nodes[name] & nodes[m] for m in g)]
        merged = sorted([name, *(m for g in hit for m in g)], key=names.index)
        groups = [g for g in groups if g not in hit] + [merged]
    return sorted(groups, key=lambda g: names.index(g[0]))


def _join(
    verts: Points, families: Mapping[str, Faces], group: Sequence[str], te: Collection[int]
) -> tuple[_blocks.Blocks, tuple[int, ...]] | str:
    """Return the layout of a group of families taken as one and each patch's family, or why not."""
    faces = [f for n in group for f in families[n]]
    family = numpy.repeat(numpy.arange(len(group)), [len(families[n]) for n in group])
    joins = {
        e for e, fs in edge_faces(faces).items() if len(fs) == 2 and family[fs[0]] != family[fs[1]]
    }
    found = _blocks.recover_joined(verts, faces, te, joins)
    if isinstance(found, str):
        return found
    return found, tuple(int(family[int(cells[0, 0])]) for cells in found.cells)


def _arc_factors(
    blocks: _blocks.Blocks, patches: Sequence[int], grid: Recovered, spec: FamilySpec
) -> dict[int, float]:
    """Return the factor of each arc of a family's patches, in the arc's direction."""
    chordwise, spanwise = spec.directions
    arcs = sorted({arc for p in patches for arc, _ in blocks.sides[p]})
    if chordwise == spanwise or not isinstance(grid, Grid):
        return dict.fromkeys(arcs, chordwise)
    runs = _blocks.sheet_directions(grid, blocks, arcs)
    return {a: chordwise if runs[a] == "chordwise" else spanwise for a in arcs}


def _counted(
    verts: Points,
    names: tuple[str, ...],
    found: tuple[_blocks.Blocks, tuple[int, ...]],
    grids: Mapping[str, Recovered],
    specs: Mapping[str, FamilySpec],
    where: str,
) -> Layout:
    """Return the layout with every arc's count, refusing an arc two families count apart."""
    blocks, owner = found
    counts: dict[int, tuple[int, str]] = {}
    kept: dict[str, list[dict[str, object]]] = {}
    for i, name in enumerate(names):
        mine = [p for p, o in enumerate(owner) if o == i]
        factors = _arc_factors(blocks, mine, grids[name], specs[name])
        for arc, f in factors.items():
            chain = blocks.arcs[arc]
            new = _blocks.count(len(chain) - 1, f)
            old, other = counts.setdefault(arc, (new, name))
            if old != new:
                raise _refuse(
                    f"{where} families {other} and {name}: the curve they share from node "
                    f"{chain[0] + 1} to node {chain[-1] + 1}, of {len(chain) - 1} source "
                    f"intervals, would hold {old} intervals as {other} is refined and {new} as "
                    f"{name} is; grids that share nodes are resampled as one layout, so give "
                    "the two factors that make one count of it"
                )
        kept[name] = _blocks.kept_sides(blocks, verts, factors, patches=mine)
    kinds = tuple(grids[n].layout for n in names)
    return Layout(
        names, kinds, blocks, owner, tuple(counts[a][0] for a in range(len(blocks.arcs))), kept
    )


def _warn_kept(layout: Layout, specs: Mapping[str, FamilySpec], where: str) -> None:
    """Warn once per family naming each patch side its factor cannot coarsen (FR-915)."""
    for name in layout.names:
        kept = layout.kept[name]
        if not kept:
            continue
        chordwise, spanwise = specs[name].directions
        label = (
            f"factor {chordwise:g}"
            if chordwise == spanwise
            else f"factors chordwise {chordwise:g} and spanwise {spanwise:g}"
        )
        lines = "; ".join(
            f"patch {k['patch']} {k['side']}: {k['source_intervals']} source interval(s), "
            f"{k['intervals']} written, centroid {k['centroid']}, "
            f"box {k['bbox_min']} to {k['bbox_max']}"
            for k in kept
        )
        what = f"{len(layout.patches_of(name))} patches of {', '.join(layout.names)}"
        if len(layout.names) == 1:
            what = layout.blocks.describe()
        warn(
            f"{where} family {name}: the {label} cannot coarsen {len(kept)} patch side(s) of "
            f"{what}; they are kept and the rest of the family is resampled: {lines}",
            PyflightstreamWarning,
            stacklevel=6,  # past _warn_kept, plan, _grid_after_grid, _decide and refine_mesh
        )


def plan(
    verts: Points,
    families: Mapping[str, Faces],
    grids: Mapping[str, Recovered],
    specs: Mapping[str, FamilySpec],
    te_edges: Mapping[str, Collection[Edge]],
    *,
    held: Collection[str],
    where: str,
) -> tuple[dict[str, Layout], list[tuple[str, str, str]]]:
    """Group the grid families that share nodes into layouts, before any work (FR-932).

    Parameters
    ----------
    verts : numpy.ndarray
        All the mesh's vertices, shape (V, 3).
    families : mapping of str to faces
        Every family of the mesh, in the source's order.
    grids : mapping of str to Grid or Blocks
        The families recovered as grids.
    specs : mapping of str to FamilySpec
        The request of each family to change.
    te_edges : mapping of str to edges
        The trailing-edge edges of each family.
    held : collection of str
        Grids that keep their first row (FR-430), which join no layout.
    where : str
        The source, for a refusal or a warning.

    Returns
    -------
    dict, list
        The layout of each family resampled in one (every member of a group,
        and each lone multiblock family), and, per grid left to the rule of
        the first grid, its name, the grid refined first that it shares
        nodes with, and why it joined no layout ("" when it could not).

    Raises
    ------
    InputArtifactError
        Two families giving a shared curve different counts; nothing was written.
    """
    names = tuple(n for n in families if n in grids)
    nodes = {n: {v for f in families[n] for v in f} for n in names}
    joinable = [n for n in names if n not in held and _joinable(grids[n], families[n])]
    layouts: list[Layout] = []
    why: dict[str, str] = {}
    for group in _touching(joinable, nodes):
        if len(group) < 2:
            continue
        te = {v for n in group for e in te_edges[n] for v in e}
        found = _join(verts, families, group, te)
        if isinstance(found, str):
            why.update(
                dict.fromkeys(group, f"; the grids {', '.join(group)} form no layout: {found}")
            )
            continue
        layouts.append(_counted(verts, tuple(group), found, grids, specs, where))
    done = [n for lay in layouts for n in lay.names]
    late: list[tuple[str, str, str]] = []
    for name in names:
        if name in done:
            continue
        first = [m for m in names if m in done and nodes[name] & nodes[m]]
        if first:
            late.append((name, first[0], why.get(name, "")))
            continue
        done.append(name)
        grid = grids[name]
        if isinstance(grid, _blocks.Blocks):
            lone = (grid, (0,) * len(grid.patches))
            layouts.append(_counted(verts, (name,), lone, grids, specs, where))
    for layout in layouts:
        _warn_kept(layout, specs, where)
    return {n: lay for lay in layouts for n in lay.names}, late


def refine_layout(
    verts: Points, families: Mapping[str, Faces], layout: Layout
) -> dict[str, GridLevel]:
    """Resample a layout and write each new cell back to its family (FR-920, FR-921, FR-932).

    Every family's level holds the layout's points; its faces are its
    patches' new faces in the order of its source faces. The new trailing-edge
    mid-points are the first family's.
    """
    verts = numpy.asarray(verts, dtype=float)
    faces = [f for n in layout.names for f in families[n]]
    done = _blocks.resample(verts, faces, layout.blocks, layout.counts)
    out: dict[str, GridLevel] = {}
    for i, name in enumerate(layout.names):
        mine = layout.patches_of(name)
        built = [f for p in mine for f in done.cells[p]]
        ordered = order_like(done.points, built, verts, families[name])
        entry = _blocks.report(layout.blocks, done, mine, (len(families[name]), len(ordered)))
        if len(layout.names) > 1:
            entry["layout"] = layout.kinds[i]
            entry["grouped_with"] = [n for n in layout.names if n != name]
        te = done.te_midpoints if i == 0 else numpy.zeros((0, 3))
        out[name] = GridLevel(done.points, ordered, te, entry)
    return out
