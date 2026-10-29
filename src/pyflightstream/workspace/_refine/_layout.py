"""Plan and resample connected grid families as one layout (FR-932)."""

from __future__ import annotations

import warnings
from collections import Counter, defaultdict, deque
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

import numpy

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream.workspace._refine._blocks import (
    Blocks,
    Edge,
    count,
    kept_sides,
    recover_joined,
    report,
    resample,
    sheet_directions,
    te_directions,
)
from pyflightstream.workspace._refine._config import FamilySpec
from pyflightstream.workspace._refine._geometry import Faces, Points, edge_faces, order_like
from pyflightstream.workspace._refine._grid import Grid, GridLevel

Recovered = Grid | Blocks


@dataclass(frozen=True)
class ArcDirection:
    """The orientation of an arc and the family and reference that supplied it.

    Attributes
    ----------
    direction : str
        ``parallel`` or ``normal`` to the reference.
    source_family : str
        The family supplying the orientation, including a propagated seed.
    provenance : str
        ``listed_te``, ``longest_side``, ``sheet_index``,
        ``propagated_from:<family>``, ``own_orientation_conflict`` or
        ``own_orientation_unlinked``.
    """

    direction: str
    source_family: str
    provenance: str


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
    directions : mapping of int to mapping of int to ArcDirection
        Per patch and arc, the orientation and its source, including conflicting patch references.
    band_leads : mapping of int to (str, str)
        Per band, the family whose count was selected and its local direction.
    labels : mapping of int to str
        Per arc, its band's stable parallel (P) or normal (N) label.
    leads : mapping of str to (str, int)
        Per label, the lead family and the arc that supplied its selected count.
    """

    names: tuple[str, ...]
    kinds: tuple[str, ...]
    blocks: Blocks
    owner: tuple[int, ...]
    counts: tuple[int, ...]
    kept: Mapping[str, list[dict[str, object]]]
    directions: Mapping[int, Mapping[int, ArcDirection]] = field(default_factory=dict)
    band_leads: dict[int, tuple[str, str]] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    leads: dict[str, tuple[str, int]] = field(default_factory=dict)

    def patches_of(self, name: str) -> list[int]:
        """Return the patches of one family, in layout order."""
        i = self.names.index(name)
        return [p for p, o in enumerate(self.owner) if o == i]


@dataclass
class _Planner:
    """Shared inputs for grouping, orientation and counting in one planning call."""

    verts: Points
    families: Mapping[str, Faces]
    grids: dict[str, Recovered]
    specs: dict[str, FamilySpec]
    te_edges: Mapping[str, Collection[Edge]]
    where: str
    followers: dict[str, str]
    assumed: Collection[str]
    prepare: bool = False
    failures: dict[str, str] = field(default_factory=dict)

    def counted(self, names, found, *, prepare=False) -> Layout:
        """Count one recovered layout and retain its directions and governing decisions."""
        verts, grids, specs = self.verts, self.grids, self.specs
        where, followers = self.where, self.followers
        blocks, owner = found
        lengths = {
            a: float(numpy.linalg.norm(numpy.diff(verts[list(arc)], axis=0), axis=1).sum())
            for a, arc in enumerate(blocks.arcs)
        }
        perimeter = _perimeters(lengths, names, blocks, owner)
        governing = [n for n in names if any(specs[n].leads)]
        declared = [n for n in names if specs[n].method != "grid_auto"]
        leaders = {
            d: _band_lead(declared, names, specs, perimeter, direction=d)
            for d in ("normal", "parallel")
        }
        for name in names:
            if specs[name].method == "grid_auto" and governing:
                lead = _band_lead(governing, names, specs, perimeter)
                specs[name] = FamilySpec(
                    chordwise=specs[leaders["normal"]].directions[0],
                    spanwise=specs[leaders["parallel"]].directions[1],
                    method="grid_auto",
                )
                followers[name] = lead
        proposed: dict[int, list[tuple[str, int, int]]] = {}
        kept: dict[str, list[dict[str, object]]] = {}
        runs, provenance = self.follower_directions(
            names, found, {d: n for d, n in leaders.items() if specs[n].leads[d == "parallel"]}
        )
        directions = {}
        for i, name in enumerate(names):
            mine = [p for p, o in enumerate(owner) if o == i]
            directions.update(
                self.arc_directions(
                    blocks,
                    mine,
                    name,
                    runs=runs.get(name),
                    source=provenance.get(name, self.failures.get(name)),
                )
            )
            kept[name] = []
            for number, p in enumerate(mine, 1):
                factors = {
                    a: specs[name].directions[d.direction == "parallel"]
                    for a, d in directions[p].items()
                }
                for arc, f in factors.items():
                    proposed.setdefault(arc, []).append(
                        (name, p, count(len(blocks.arcs[arc]) - 1, f))
                    )
                kept[name].extend(
                    dict(side, patch=number)
                    for side in kept_sides(blocks, verts, factors, patches=[p])
                )
        kinds = tuple(grids[n].layout for n in names)
        layout = Layout(names, kinds, blocks, owner, (), kept, directions)
        if prepare:
            self.prepare_leads(layout, lengths)
            return self.counted(names, found)
        failed = {n: s for n, s in provenance.items() if isinstance(s, str)} if self.prepare else {}
        if failed:
            self.failures.update(failed)
            for n in failed:
                specs[n] = replace(specs[n], method="grid")
                followers.pop(n, None)
            return self.counted(names, found)
        counts = _band_counts(layout, proposed, specs, perimeter, where=where)
        return replace(layout, counts=tuple(counts[a] for a in range(len(blocks.arcs))))

    def prepare_leads(self, layout, lengths):
        """Mark the longest total parallel and normal sides, with source-order ties."""
        names = layout.names
        totals = Counter()
        for p, told in layout.directions.items():
            for a, d in told.items():
                totals[names[layout.owner[p]], d.direction] += lengths[a]
        leads = {d: max(names, key=lambda n: totals[n, d]) for d in ("parallel", "normal")}
        for n in names:
            self.specs[n] = replace(
                self.specs[n],
                governing_parallel=n == leads["parallel"],
                governing_normal=n == leads["normal"],
                method="grid" if n in leads.values() else "grid_auto",
            )

    def arc_directions(self, blocks, patches, name, *, runs, source):
        """Orient this family's patches using the planner's geometry and reference."""
        verts, grid, spec = self.verts, self.grids[name], self.specs[name]
        edges, where, assumed = self.te_edges[name], self.where, name in self.assumed
        local = {}
        if runs is None:
            # Equal factors did not request geometric warnings before directions were
            # retained. Recording their orientation must not add those diagnostics.
            with warnings.catch_warnings():
                if spec.directions[0] == spec.directions[1] and not any(spec.leads):
                    warnings.simplefilter("ignore", PyflightstreamWarning)
                runs = _reference_directions(
                    verts,
                    blocks,
                    patches,
                    grid,
                    edges,
                    family=f"{where} family {name}",
                    patch_runs=local,
                )
        provenance = (
            "listed_te" if edges else "sheet_index" if isinstance(grid, Grid) else "longest_side"
        )
        if assumed:
            provenance = "longest_side"
        if isinstance(source, str):
            provenance = "own_orientation_" + source.removeprefix("own reference: ")
        if not local:
            local = {p: {a: runs[a] for a, _ in blocks.sides[p]} for p in patches}
        return {
            p: {
                a: ArcDirection(
                    "parallel" if d == "spanwise" else "normal",
                    source[a] if isinstance(source, dict) else name,
                    f"propagated_from:{source[a]}" if isinstance(source, dict) else provenance,
                )
                for a, d in told.items()
            }
            for p, told in local.items()
        }

    def follower_directions(self, names, found, leaders):
        """Propagate each directional leader through the selected followers."""
        verts, grids, followers = self.verts, self.grids, self.followers
        te_edges, where = self.te_edges, self.where
        blocks, indices = found
        owner = tuple(names[i] for i in indices)
        runs, provenance = {}, {}
        selected = [n for n in names if n in followers]
        if not selected:
            return runs, provenance
        evidence = {}
        for lead in dict.fromkeys(leaders.values() if leaders else followers.values()):
            seed = {}
            if lead in names:
                patches = [p for p, n in enumerate(owner) if n == lead]
                grid, edges, label = grids[lead], te_edges[lead], f"{where} family {lead}"
                seed = _reference_directions(verts, blocks, patches, grid, edges, family=label)
            evidence[lead] = propagate_directions(blocks, owner, seed, selected)
        for name in selected:
            arcs = {a for p, n in enumerate(owner) if n == name for a, _ in blocks.sides[p]}
            failures = [failed[name] for _, failed in evidence.values() if name in failed]
            values = {a: {told[a] for told, _ in evidence.values() if a in told} for a in arcs}
            if failures or any(len(ds) != 1 for ds in values.values()):
                conflict = "conflict" in failures or any(len(ds) > 1 for ds in values.values())
                reason = "conflict" if conflict else "unlinked"
                warn_direction_fallback(name, ", ".join(evidence), reason, where=where)
                provenance[name] = f"own reference: {reason}"
            else:
                runs[name] = {a: next(iter(ds)) for a, ds in values.items()}
                provenance[name] = {
                    a: leaders.get("parallel" if d == "spanwise" else "normal", followers[name])
                    for a, d in runs[name].items()
                }
        return runs, provenance

    def grouped(self, groups, *, accept):
        """Plan each connected group with this planner's recovery and counting context."""
        verts, families, grids, specs = self.verts, self.families, self.grids, self.specs
        te_edges, where = self.te_edges, self.where
        layouts: list[Layout] = []
        why: dict[str, str] = {}
        for group in groups:
            if not any(any(specs[n].leads) for n in group):
                for name in group:
                    if specs[name].method == "grid_auto":
                        _skip_unled(grids, specs, name, where)
                group = [n for n in group if n in grids]
            if len(group) < 2:
                continue
            te = {v for n in group for e in te_edges[n] for v in e}
            found = _join(verts, families, group, te)
            if isinstance(found, str):
                why.update(
                    dict.fromkeys(group, f"; the grids {', '.join(group)} form no layout: {found}")
                )
                continue
            try:
                layouts.append(self.counted(tuple(group), found, prepare=self.prepare))
            except InputArtifactError as error:
                if not accept:
                    raise
                why.update(dict.fromkeys(group, _skipped_layout(error, group, where)))
        return layouts, why


def _joinable(grid: Recovered, faces: Faces) -> bool:
    """Return whether a grid family can join a layout: quadrilaterals as a sheet or multiblock."""
    sheet = isinstance(grid, Grid) and grid.layout == "sheet"
    return (sheet or isinstance(grid, Blocks)) and all(len(f) == 4 for f in faces)


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
) -> tuple[Blocks, tuple[int, ...]] | str:
    """Return the layout of a group of families taken as one and each patch's family, or why not."""
    faces = [f for n in group for f in families[n]]
    family = numpy.repeat(numpy.arange(len(group)), [len(families[n]) for n in group])
    joins = {
        e for e, fs in edge_faces(faces).items() if len(fs) == 2 and family[fs[0]] != family[fs[1]]
    }
    found = recover_joined(verts, faces, te, joins)
    if isinstance(found, str):
        return found
    return found, tuple(int(family[int(cells[0, 0])]) for cells in found.cells)


def _direction_links(blocks: Blocks, owner: Sequence[str], followers: Collection[str]):
    """Join follower sides with equal or opposite direction constraints."""
    links: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for p, name in enumerate(owner):
        if name not in followers:
            continue
        arcs = [a for a, _ in blocks.sides[p]]
        for i, a in enumerate(arcs):
            for j, b in enumerate(arcs):
                links[a].append((b, (i < 2) != (j < 2)))
    return links


def propagate_directions(
    blocks: Blocks, owner: Sequence[str], seed: Mapping[int, str], followers: Collection[str]
) -> tuple[dict[int, str], dict[str, str]]:
    """Propagate seeded arc directions through follower patches, reporting conflict or unlinked.

    Opposite sides retain a direction and adjacent sides switch it. Only follower
    patches transmit directions; a corner or a remeshed family cannot transmit one.
    Both directions are retained during traversal so a conflict cannot be hidden
    by patch order. Failed families must use their own geometric reference.
    """
    links = _direction_links(blocks, owner, followers)
    reached: dict[int, set[bool]] = defaultdict(set)
    queue = deque((a, d == "spanwise") for a, d in seed.items())
    while queue:
        arc, direction = queue.popleft()
        if direction in reached[arc]:
            continue
        reached[arc].add(direction)
        queue.extend((other, direction != flip) for other, flip in links.get(arc, ()))
    failures = {}
    for name in followers:
        arcs = {a for p, n in enumerate(owner) if n == name for a, _ in blocks.sides[p]}
        if any(len(reached[a]) == 2 for a in arcs):
            failures[name] = "conflict"
        elif not arcs or any(not reached[a] for a in arcs):
            failures[name] = "unlinked"
    return {
        a: "spanwise" if True in values else "chordwise"
        for a, values in reached.items()
        if len(values) == 1
    }, failures


def _reference_directions(verts, blocks, patches, grid, te_edges, *, family, patch_runs=None):
    """Read a family's directions using the existing geometric reference path."""
    arcs = {a for p in patches for a, _ in blocks.sides[p]}
    if isinstance(grid, Grid):
        return sheet_directions(grid, blocks, arcs)
    te = numpy.asarray(verts, dtype=float)[sorted(te_edges)].reshape(-1, 2, 3)
    local = {} if patch_runs is None else patch_runs
    runs = te_directions(
        verts, blocks, patches, te, family=family, what="its patches", patch_runs=local
    )
    return {
        a: d for a, d in runs.items() if len({told[a] for told in local.values() if a in told}) <= 1
    }


def warn_direction_fallback(name: str, lead: str, reason: str, *, where: str) -> None:
    """Warn that a follower's topology cannot inherit its governing directions."""
    warn(
        f"{where} family {name}: not a follower of {lead} in directions: {reason}; "
        "using its own reference. Declare its own grid table to set independent factors.",
        PyflightstreamWarning,
        stacklevel=4,
    )


def _perimeters(
    lengths: Mapping[int, float], names: Sequence[str], blocks: Blocks, owner: Sequence[int]
) -> dict[str, float]:
    """Return each family's perimeter in the layout: the arcs one of its patches holds."""
    out = {}
    for i, name in enumerate(names):
        held = Counter(a for p, o in enumerate(owner) if o == i for a, _ in blocks.sides[p])
        out[name] = sum(lengths[a] for a, n in held.items() if n == 1)
    return out


def arc_bands(blocks: Blocks, arcs: Iterable[int]) -> dict[int, int]:
    """Return each arc's band: arcs joined as opposite sides of a patch hold one count."""
    parent = {a: a for a in arcs}

    def root(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for sides in blocks.sides:
        ring = [arc for arc, _ in sides]
        for x, y in ((ring[0], ring[1]), (ring[2], ring[3])):
            if x in parent and y in parent:
                parent[root(x)] = root(y)
    return {a: root(a) for a in parent}


def _lead_rank(name, names, specs, perimeter, direction):
    """Rank a band's eligible directional governor, then declared perimeter and source order."""
    governing = (
        any(specs[name].leads) if direction is None else specs[name].leads[direction == "parallel"]
    )
    return not governing, specs[name].method == "grid_auto", -perimeter[name], names.index(name)


def _band_lead(candidates, names, specs, perimeter, *, direction=None):
    """Select a governing or declared family by perimeter, then source order."""
    return min(candidates, key=lambda n: _lead_rank(n, names, specs, perimeter, direction))


def _band_counts(
    layout: Layout,
    proposed: Mapping[int, list[tuple[str, int, int]]],
    specs: Mapping[str, FamilySpec],
    perimeter: Mapping[str, float],
    *,
    where: str,
) -> dict[int, int]:
    """Return one count per arc: each band's count from the family that leads it, warned."""
    names = layout.names
    band = arc_bands(layout.blocks, proposed)
    members: dict[int, list[tuple[str, int, str, int]]] = {}
    for arc, offers in proposed.items():
        members.setdefault(band[arc], []).extend(
            (n, c, layout.directions[p][arc].direction, arc) for n, p, c in offers
        )
    chosen: dict[int, int] = {}
    dominant: dict[int, int] = {}
    followed: dict[tuple[str, str], int] = {}
    for key, candidates in members.items():
        lead, value, direction, dominant[key] = min(
            candidates, key=lambda row: _lead_rank(row[0], names, specs, perimeter, row[2])
        )
        chosen[key] = value
        layout.band_leads[key] = (lead, direction)
        for n in {n for n, c, _, _ in candidates if c != value}:
            followed[(n, lead)] = followed.get((n, lead), 0) + 1
    _label_bands(layout, band, dominant)
    for (n, lead), bands in sorted(followed.items()):
        how = "governing" if any(specs[lead].leads) else "declared, of the largest perimeter"
        advice = (
            'To give this grid_auto family its own counts, declare method = "grid", '
            "its factors and governing = true in its [families] table."
            if specs[n].method == "grid_auto"
            else "Mark the family that should lead with governing = true in its [families] table."
        )
        warn(
            f"{where} family {n} follows {lead} ({how}) on {bands} band(s) of the curves they "
            f"share: those curves take {lead}'s counts. {advice}",
            PyflightstreamWarning,
            stacklevel=5,
        )
    return {arc: chosen[band[arc]] for arc in proposed}


def _label_bands(layout, bands, dominant):
    """Assign labels by the selected lead's source order, then its count-setting arc."""
    serial = {"parallel": 0, "normal": 0}
    ordered = sorted(
        layout.band_leads, key=lambda b: (layout.names.index(layout.band_leads[b][0]), dominant[b])
    )
    for band in ordered:
        lead, direction = layout.band_leads[band]
        serial[direction] += 1
        label = ("P" if direction == "parallel" else "N") + str(serial[direction])
        layout.leads[label] = (lead, dominant[band])
        layout.labels.update({a: label for a, b in bands.items() if b == band})


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
            else f"factors normal {chordwise:g} and parallel {spanwise:g}"
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
    grids: dict[str, Recovered],
    specs: dict[str, FamilySpec],
    te_edges: Mapping[str, Collection[Edge]],
    *,
    where: str,
    accept: bool = False,
    followers: dict[str, str] | None = None,
    assumed: Collection[str] = (),
    prepare: bool = False,
) -> tuple[dict[str, Layout], list[tuple[str, str, str]]]:
    """Group the grid families that share nodes into layouts, before any work (FR-932).

    Under ``accept`` (``accept_remesh``) a layout that is refused (two
    families counting a shared curve apart, a patch whose directions cannot
    be told apart) is warned and left to the rule of the first grid: the
    first of its families in the source's order is refined as a grid alone
    and the others are remeshed; a lone multiblock family refused alone is
    remeshed, listed with its own name as the grid it follows.

    Parameters
    ----------
    verts : numpy.ndarray
        All the mesh's vertices, shape (V, 3).
    families : mapping of str to faces
        Every family of the mesh, in the source's order.
    grids : mapping of str to Grid or Blocks
        The families recovered as grids.
    specs : mapping of str to FamilySpec
        Working specs, updated with each layout's governing factors for its followers.
    te_edges : mapping of str to edges
        The trailing-edge edges of each family.
    where : str
        The source, for a refusal or a warning.
    accept : bool
        Leave a refused layout to the rule of the first grid, with a
        warning, instead of refusing it (``accept_remesh``).
    followers : mapping of str to str, optional
        Working mapping populated with each grid_auto family's governing family.
    assumed : collection of str
        Families whose reference edges were assumed from their longest boundary side.
    prepare : bool
        Select each group's directional leads by total side length, then retain
        only followers whose every arc can propagate with the final declarations.

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
    joinable = [n for n in names if _joinable(grids[n], families[n])]
    planner = _Planner(
        verts,
        families,
        grids,
        specs,
        te_edges,
        where,
        {} if followers is None else followers,
        assumed,
        prepare,
    )
    layouts, why = planner.grouped(_touching(joinable, nodes), accept=accept)
    done = [n for lay in layouts for n in lay.names]
    late: list[tuple[str, str, str]] = []
    for name in names:
        if name not in grids or name in done:
            continue
        if specs[name].method == "grid_auto":
            _skip_unled(grids, specs, name, where)
            continue
        first = [m for m in names if m in done and nodes[name] & nodes[m]]
        if first:
            late.append((name, first[0], why.get(name, "")))
            continue
        done.append(name)
        grid = grids[name]
        if isinstance(grid, Blocks):
            lone = (grid, (0,) * len(grid.patches))
            try:
                layouts.append(planner.counted((name,), lone))
            except InputArtifactError as error:
                if not accept:
                    raise
                done.remove(name)
                late.append((name, name, _skipped_layout(error, [name], where)))
    for layout in layouts:
        _warn_kept(layout, specs, where)
    return {n: lay for lay in layouts for n in lay.names}, late


def _skip_unled(grids, specs, name, where):
    """Keep a grid_auto family unchanged when its layout has no governing family."""
    warn(
        f"{where} family {name}: grid_auto follows a governing family and the "
        "refinement file marks none in its grid-connected layout (governing = true); "
        "it is kept unchanged",
        PyflightstreamWarning,
        stacklevel=4,
    )
    del grids[name], specs[name]


def _skipped_layout(error: InputArtifactError, group: Sequence[str], where: str) -> str:
    """Warn that a refused layout is left to the first-grid rule and return the reason."""
    text = str(error).removesuffix(". Nothing was written.").removeprefix(f"{where} ")
    names = ", ".join(group)
    warn(
        f"{where}: {text}; the first of {names} in the source's order is refined as a grid "
        "alone and the others are remeshed (accept_remesh, CLI --accept-remesh)",
        PyflightstreamWarning,
        stacklevel=5,  # past _skipped_layout, plan, _grid_after_grid and _decide
    )
    return f"; {text}"


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
    done = resample(verts, faces, layout.blocks, layout.counts)
    out: dict[str, GridLevel] = {}
    for i, name in enumerate(layout.names):
        mine = layout.patches_of(name)
        built = [f for p in mine for f in done.cells[p]]
        ordered = order_like(done.points, built, verts, families[name])
        entry = report(layout.blocks, done, mine, (len(families[name]), len(ordered)))
        if len(layout.names) > 1:
            entry["layout"] = layout.kinds[i]
            entry["grouped_with"] = [n for n in layout.names if n != name]
        te = done.te_midpoints if i == 0 else numpy.zeros((0, 3))
        out[name] = GridLevel(done.points, ordered, te, entry)
    return out
