"""The junction sub-steps of stage S10: dominance applied on the kernel, one check per step.

Pipeline role: kernel part of stage S10 of the geometry pipeline. An :class:`Assembly` holds the
pieces of one configuration as kernel faces and runs the sub-steps of the stage table in order:
pieces loaded, each piece alone, body joins and cuts by one fragment per group, projected
junctions imprinted on their hosts, the inside removed by a flood from each piece's own exposed
side, skin coverage in parameter space, the joins and the whole written, read back and sewn. Each
sub-step returns its named checks with the measured value and the limit, and a run stops at the
first failed check. The owner's rule is the one implemented: the dominant imprints on the
dominated, the dominated loses its inside, and the dominant is split along the junction too; no
area constant decides a removal.

The kernel is reached only through :class:`~pyflightstream.workspace._cad.CadKernel`.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream.geometry import _junctions as jn
from pyflightstream.geometry._patch import Patch, evaluate_patch
from pyflightstream.geometry._records import check_entry
from pyflightstream.geometry._stage_table import stage_row
from pyflightstream.workspace._cad import CadKernel, Face, FileTopology

__all__ = ["Assembly", "sewn_free_edges"]

#: The pieces whose join with each other is a body join (stage C of the research hand-off).
BLUFF = ("body", "blister")
#: A dominant's free edge within 0.5 mm of a host is a candidate projected junction (hand-off S5).
SEAT_REACH_M = 5e-4
_SAMPLES = 17


def _plain(value: Any) -> Any:
    """Return ``value`` with numpy scalars and arrays made JSON values."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _skip(ids: Sequence[str], note: str) -> list[dict[str, Any]]:
    return [check_entry(cid, "skipped", note=note) for cid in ids]


def _point(value: Any) -> tuple[float, float, float]:
    return (float(value[0]), float(value[1]), float(value[2]))


def _points(values: np.ndarray) -> list[tuple[float, float, float]]:
    return [_point(v) for v in np.asarray(values, float).reshape(-1, 3)]


def _add_patch(kernel: CadKernel, patch: Patch) -> Face:
    controls = np.asarray(patch.controls, float)
    net = [
        [_point(controls[i, j]) for j in range(controls.shape[1])] for i in range(controls.shape[0])
    ]
    return kernel.add_bspline_surface(
        net,
        knots_u=list(patch.knots_u),
        knots_v=list(patch.knots_v),
        mult_u=list(patch.multiplicities_u),
        mult_v=list(patch.multiplicities_v),
        deg_u=patch.degree_u,
        deg_v=patch.degree_v,
    )


def _hull(patches: Sequence[Patch], count: int = 9) -> np.ndarray:
    """Return the triangles of a piece's untrimmed patches, its hull for inside tests."""
    triangles = []
    for patch in patches:
        g = evaluate_patch(patch, count)
        a, b, c, d = g[:-1, :-1], g[1:, :-1], g[1:, 1:], g[:-1, 1:]
        triangles.append(np.stack([a, b, c], axis=2).reshape(-1, 3, 3))
        triangles.append(np.stack([a, c, d], axis=2).reshape(-1, 3, 3))
    return np.concatenate(triangles) if triangles else np.zeros((0, 3, 3))


def _free_boundaries(patches: Sequence[Patch], tolerance: float) -> list[np.ndarray]:
    """Return the boundary curves of a piece's patches that no other patch of it shares."""
    curves = []
    for patch in patches:
        g = evaluate_patch(patch, _SAMPLES)
        curves += [g[0, :], g[-1, :], g[:, 0], g[:, -1]]
    curves = [c for c in curves if jn.polyline_length(c) > tolerance]
    free = []
    for i, c in enumerate(curves):
        others = [d for j, d in enumerate(curves) if j != i]
        shared = any(
            min(
                max(np.linalg.norm(c[0] - d[0]), np.linalg.norm(c[-1] - d[-1])),
                max(np.linalg.norm(c[0] - d[-1]), np.linalg.norm(c[-1] - d[0])),
            )
            <= tolerance
            and jn.curve_distance(c, d) <= tolerance
            for d in others
        )
        # an edge that meets several shorter ones end to end (a T junction) is shared when
        # every sample of it lies on one of them
        if not shared and others:
            near = np.min([jn.distance_to_polyline(c, d) for d in others], axis=0)
            shared = bool(near.max() <= tolerance)
        if not shared:
            free.append(c)
    return free


def _bbox_hit(samples: np.ndarray, triangles: np.ndarray, margin: float) -> bool:
    """Whether any sample lies in the bounding box of the triangles, grown by ``margin``."""
    if not len(triangles):
        return False
    points = triangles.reshape(-1, 3)
    low, high = points.min(axis=0) - margin, points.max(axis=0) + margin
    return bool(np.any(np.all((samples >= low) & (samples <= high), axis=1)))


def _contact(a: np.ndarray, b: np.ndarray) -> float:
    """Return 0 when two hulls cross, otherwise the least distance between them (sampled)."""
    pa, pb = np.unique(a.reshape(-1, 3), axis=0), np.unique(b.reshape(-1, 3), axis=0)
    inside_a = jn.parity_inside(pb, a)
    inside_b = jn.parity_inside(pa, b)
    if (inside_a.any() and not inside_a.all()) or (inside_b.any() and not inside_b.all()):
        return 0.0
    return float(min(jn.distance_to_triangles(pb, a).min(), jn.distance_to_triangles(pa, b).min()))


def sewn_free_edges(kernel: CadKernel, paths: Sequence[str | Path], tolerance: float) -> list:
    """Return the free edges of the files read in ONE import each and sewn at ``tolerance``.

    A list of files is read file by file; faces of two imports are never sewn together, which
    is why a join is always written to one file before it is sewn (hand-off BJ4).
    """
    out = []
    for path in paths:
        topology = kernel.inspect_file(path, tolerance)
        out += [samples for samples, faces in topology.edges if len(faces) == 1]
    return out


class Assembly:
    """The pieces of one configuration on a kernel, and the sub-steps of S10 run on them.

    Parameters
    ----------
    kernel : CadKernel
        An open kernel; the caller closes it.
    pieces : Mapping
        Component name to its placed patches.
    rows : Sequence of Mapping
        The ``[[dominance]]`` rows as resolved.
    out : path
        The folder the written files go to.
    members : sequence of str, optional
        The members of the configuration; every piece by default.
    kinds : Mapping, optional
        Component name to its type; two pieces of a type in :data:`BLUFF` form a body join.
    plane_axis : int, optional
        The axis normal to the symmetry plane of a half model (1 for y); None for a full model.
    expected_faces : Mapping, optional
        Face counts the generation reported, per piece; the patch counts by default.
    regenerated : Mapping, optional
        The pieces built a second time from their own resolved inputs.
    coverage_fraction : float, optional
        The largest missing area of a piece's skin, as a fraction of its area.
    """

    STEPS = (
        ("S10.D1", "load"),
        ("S10.C5", "regenerate"),
        ("S10.C6", "symmetry"),
        ("S10.C8", "rims"),
        ("S10.C9", "openings"),
        ("S10.D2", "alone"),
        ("S10.C7", "alone_fine"),
        ("S10.D3", "join_cut"),
        ("S10.D4", "cut"),
        ("S10.E1", "group"),
        ("S10.D5", "project"),
        ("S10.D6", "split"),
        ("S10.D8", "remove"),
        ("S10.D8b", "coverage"),
        ("S10.C1", "shared"),
        ("S10.C2", "written"),
        ("S10.C3", "on_surface"),
        ("S10.C4", "join_sewn"),
        ("S10.D9", "write"),
        ("S10.D10", "sew"),
        ("S10.E2", "clearance"),
    )

    def __init__(
        self,
        kernel: CadKernel,
        pieces: Mapping[str, Sequence[Patch]],
        rows: Sequence[Mapping[str, Any]],
        *,
        out: str | Path,
        members: Sequence[str] | None = None,
        kinds: Mapping[str, str] | None = None,
        plane_axis: int | None = None,
        expected_faces: Mapping[str, int] | None = None,
        regenerated: Mapping[str, Sequence[Patch]] | None = None,
        coverage_fraction: float = 1e-4,
    ) -> None:
        self.k = kernel
        self.sources = {name: list(patches) for name, patches in pieces.items()}
        self.kinds = dict(kinds or {})
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.warnings: list[str] = []
        self.plan = jn.dominance_plan(rows, list(members or pieces), self.warnings)
        self.plane_axis = plane_axis
        self.expected_faces = dict(expected_faces or {})
        self.regenerated = regenerated
        self.coverage_fraction = float(coverage_fraction)
        self.hulls = {name: _hull(p) for name, p in self.sources.items()}
        self.faces: dict[str, list[Face]] = {}
        self.origin: dict[Face, tuple[str, int]] = {}
        self.records: list[dict[str, Any]] = []
        self.cut_done = False
        self.alone_free: list[np.ndarray] = []
        self.alone_slivers = 0
        self.alone_files: dict[str, Path] = {}
        self.join_files: dict[tuple[str, str], Path] = {}
        self.j_edges: dict[jn.Operation, list[int]] = {}
        self.j_samples: dict[jn.Operation, list[np.ndarray]] = {}
        self.groups: list[list[str]] = []

    # ---- driving --------------------------------------------------------------------------

    def run(self) -> list[dict[str, Any]]:
        """Run every sub-step in order; stop after the first one with a failed check."""
        for stage, _ in self.STEPS:
            record = self.step(stage)
            if any(c["status"] == "failed" for c in record["checks"]):
                break
        return self.records

    def step(self, stage: str) -> dict[str, Any]:
        """Run one sub-step and return its record (checks, inputs, outputs, wall time)."""
        method = dict(self.STEPS)[stage]
        before = len(self.warnings)
        clock = time.perf_counter()
        checks, outputs = getattr(self, f"_{method}")()
        inputs = {"rows": [self._op_name(op) for op in self.plan], **outputs.pop("inputs", {})}
        outputs = {"inputs": inputs, **outputs}
        record = {
            "stage": stage,
            "name": stage_row(stage).name,
            "checks": checks,
            "outputs": _plain(outputs),
            "warnings": self.warnings[before:],
            "wall_s": round(time.perf_counter() - clock, 3),
        }
        self.records.append(record)
        return record

    @staticmethod
    def _op_name(op: jn.Operation) -> str:
        return f"{op.operation} {op.dominant} > {op.dominated}"

    def _ops(self, operation: str) -> list[jn.Operation]:
        return [op for op in self.plan if op.operation == operation]

    def _is_join(self, op: jn.Operation) -> bool:
        return self.kinds.get(op.dominant) in BLUFF and self.kinds.get(op.dominated) in BLUFF

    def _owner(self) -> dict[Face, str]:
        return {f: name for name, faces in self.faces.items() for f in faces}

    def _edge_map(self) -> dict[int, list[Face]]:
        edges: dict[int, list[Face]] = {}
        for faces in self.faces.values():
            for face in faces:
                for e in self.k.boundary(face):
                    edges.setdefault(abs(e), []).append(face)
        return edges

    def _samples(self, edge: int, count: int = _SAMPLES) -> np.ndarray:
        low, high = self.k.edge_bounds(edge)
        return np.asarray(self.k.edge_values(edge, np.linspace(low, high, count).tolist()), float)

    def _length(self, edge: int) -> float:
        return jn.polyline_length(self._samples(edge, 41))

    def _to_faces(self, points: np.ndarray, faces: Sequence[Face]) -> np.ndarray:
        best = np.full(len(points), np.inf)
        for face in faces:
            xyz, _ = self.k.project(face, _points(points))
            best = np.minimum(best, np.linalg.norm(np.asarray(xyz) - points, axis=1))
        return best

    def _on_plane(self, point: np.ndarray) -> bool:
        return self.plane_axis is not None and abs(point[self.plane_axis]) <= jn.SYMMETRY_M

    def _junction(self, a: str, b: str) -> list[int]:
        owner = self._owner()
        return [e for e, faces in self._edge_map().items() if {owner[f] for f in faces} >= {a, b}]

    # ---- D1, C5, C6, C8, C9: the pieces before any operation ------------------------------

    def _load(self):
        worst, where = 0, {}
        for name, patches in self.sources.items():
            built = [_add_patch(self.k, p) for p in patches]
            for index, face in enumerate(built):
                self.origin[face] = (name, index)
            gap = abs(len(built) - int(self.expected_faces.get(name, len(patches))))
            if gap > worst or not where:
                worst, where = gap, {"component": name, "built": len(built)}
            self.faces[name] = self._self_fragment(name, built)
        self._resolve_auto()
        contact, pair, limit = 0.0, {}, jn.SEW_M
        for op in self.plan:
            d = _contact(self.hulls[op.dominant], self.hulls[op.dominated])
            if d - op.tolerance_m >= contact - limit or not pair:
                contact, limit, pair = d, op.tolerance_m, {"pair": self._op_name(op)}
        checks = [
            jn.measured(
                "assembly.face_count",
                worst,
                0,
                unit="faces",
                where=where,
                cause="BUG: a piece holds another count of faces than its generation",
            ),
            jn.measured(
                "placement.contact",
                contact,
                limit,
                unit="m",
                where=pair,
                cause="STRATEGY: the pieces of a row do not touch (placement)",
            ),
        ]
        return checks, {"inputs": {"patches": {n: len(p) for n, p in self.sources.items()}}}

    def _self_fragment(self, name: str, built: list[Face]) -> list[Face]:
        """Fragment a piece's own faces together, so faces of one piece share their seams."""
        if len(built) < 2:
            return built
        result = self.k.fragment(built[:1], built[1:])
        return self._inherit(built, [*result.from_a, *result.from_b])

    def _inherit(
        self,
        inputs: Sequence[Face],
        rows: Sequence[Sequence[Face]],
        before: Mapping[Face, tuple[str, int]] | None = None,
    ) -> list[Face]:
        # the kernel numbers new faces again with tags of faces it removed, so the origin of a
        # piece is set from this call's inputs, never kept from an earlier face of the same tag
        out: list[Face] = []
        fresh: dict[Face, tuple[str, int]] = {}
        for face, row in zip(inputs, rows, strict=True):
            origin = (self.origin if before is None else before).get(face)
            for piece in row:
                if origin is not None and piece not in fresh:
                    fresh[piece] = origin
                if piece not in out:
                    out.append(piece)
        self.origin.update(fresh)
        return out

    def _resolve_auto(self) -> None:
        """Read an ``auto`` row as a projection when the dominant lies along the dominated."""
        resolved = []
        for op in self.plan:
            if op.operation == "auto":
                free = _free_boundaries(self.sources[op.dominant], jn.SEW_M)
                touching = any(
                    jn.distance_to_triangles(c, self.hulls[op.dominated]).max() <= op.tolerance_m
                    for c in free
                )
                kind = "project" if touching else "cut"
                self.warnings.append(f"{self._op_name(op)}: auto read as {kind}")
                op = jn.Operation(
                    kind, op.dominant, op.dominated, op.row, op.tolerance_m, op.contact_deg
                )
            resolved.append(op)
        self.plan = [o for o in resolved if o.operation == "cut"] + [
            o for o in resolved if o.operation == "project"
        ]

    def _regenerate(self):
        if self.regenerated is None:
            return _skip(["piece.regenerated"], "no second build of the pieces was given"), {}
        worst, where = 0.0, {}
        for name, patches in self.sources.items():
            try:
                change = jn.pole_change(patches, self.regenerated.get(name, []))
            except ValueError as error:
                change, where = 1.0, {"component": name, "error": str(error)}
            if change >= worst:
                worst, where = change, {**where, "component": name}
        return [
            jn.measured(
                "piece.regenerated",
                worst,
                jn.REGENERATE_M,
                unit="m",
                where=where,
                cause="BUG: the same inputs build other poles",
            )
        ], {}

    def _symmetry(self):
        if self.plane_axis is None:
            return _skip(["piece.symmetry_edges"], "a full model has no symmetry plane"), {}
        worst, where = 0.0, {}
        for name, patches in self.sources.items():
            near = [
                c
                for c in _free_boundaries(patches, jn.SEW_M)
                if np.abs(c[:, self.plane_axis]).max() <= jn.SHARED_PAIR_NEAR_M
            ]
            offset = jn.plane_offset(near, self.plane_axis)
            if offset >= worst:
                worst, where = offset, {"component": name, "edges": len(near)}
        return [
            jn.measured(
                "piece.symmetry_edges",
                worst,
                jn.SYMMETRY_M,
                unit="m",
                where=where,
                cause="BUG: a half model's open edges are off the symmetry plane",
            )
        ], {}

    def _rims(self):
        cuts = self._ops("cut")
        if not cuts:
            return _skip(["join.rim_inside"], "no cut row"), {}
        total, where = 0, {}
        for op in cuts:
            hull = self.hulls[op.dominant]
            for rim in self._rim_edges(op.dominated):
                if not _bbox_hit(rim, hull, jn.RIM_MARGIN_M):
                    continue
                count = jn.points_outside(rim, hull, margin=jn.RIM_MARGIN_M)
                if count:
                    total += count
                    where = {"pair": self._op_name(op), "at": rim[0].tolist()}
        return [
            jn.measured(
                "join.rim_inside",
                total,
                0,
                unit="points",
                where=where,
                cause="STRATEGY: an open rim of the dominated is not buried in the "
                "dominant, so the cut leaves it free",
            )
        ], {}

    def _rim_edges(self, name: str) -> list[np.ndarray]:
        return [
            c
            for c in _free_boundaries(self.sources[name], jn.SEW_M)
            if not (self.plane_axis is not None and self._on_plane_curve(c))
        ]

    def _on_plane_curve(self, curve: np.ndarray) -> bool:
        return bool(np.abs(curve[:, self.plane_axis]).max() <= jn.SYMMETRY_M)

    def _openings(self):
        cuts = self._ops("cut")
        if not cuts:
            return _skip(["join.opening_on_partner"], "no cut row"), {}
        worst, where = 0.0, {}
        for op in cuts:
            hull = self.hulls[op.dominated]
            for edge in self._rim_edges(op.dominant):
                if not _bbox_hit(edge, hull, jn.SEW_M) or jn.parity_inside(edge, hull).all():
                    continue
                d = float(jn.distance_to_triangles(edge, hull).max())
                if d >= worst:
                    worst, where = d, {"pair": self._op_name(op), "at": edge[0].tolist()}
        return [
            jn.measured(
                "join.opening_on_partner",
                worst,
                jn.OPENING_M,
                unit="m",
                where=where,
                cause="STRATEGY: the dominant's opening does not follow the dominated",
            )
        ], {}

    # ---- D2, C7: each piece alone, written, read back and sewn ---------------------------

    def _partners(self, name: str):
        hulls = [h for n, h in self.hulls.items() if n != name and len(h)]

        def distance(points: np.ndarray) -> np.ndarray:
            if not hulls:
                return np.full(len(points), np.inf)
            return np.min([jn.distance_to_triangles(points, h) for h in hulls], axis=0)

        def inside(points: np.ndarray) -> np.ndarray:
            if not hulls:
                return np.zeros(len(points), bool)
            return np.any([jn.parity_inside(points, h) for h in hulls], axis=0)

        return distance, inside

    def _unexplained(self, name: str, topology: FileTopology) -> int:
        free = [s for s, faces in topology.edges if len(faces) == 1]
        distance, inside = self._partners(name)
        classes = jn.classify_free_edges(
            free, distance=distance, inside=inside, plane_axis=self.plane_axis
        )
        return classes.count("unexplained")

    def _alone(self):
        read_gap, triple, worst, where = 0, 0, 0, {}
        per_piece = {}
        for name, faces in self.faces.items():
            path = self.out / f"S10-alone-{name}.igs"
            self.k.export_iges({name: faces}, path)
            self.alone_files[name] = path
            topology = self.k.inspect_file(path, jn.SEW_M)
            read_gap = max(read_gap, abs(len(topology.areas) - len(faces)))
            triple += sum(1 for _, f in topology.edges if len(f) > 2)
            self.alone_free += [s for s, f in topology.edges if len(f) == 1]
            widths = [
                jn.mean_width(a, p)
                for a, p in zip(topology.areas, topology.perimeters, strict=True)
            ]
            self.alone_slivers += len(jn.slivers(widths))
            count = self._unexplained(name, topology)
            per_piece[name] = count
            if count > worst or not where:
                worst, where = count, {"component": name}
        return [
            jn.measured(
                "reimport.faces",
                read_gap,
                0,
                unit="faces",
                cause="BUG: the writer or the reader lost a face",
            ),
            jn.measured(
                "piece.triple_edges",
                triple,
                0,
                unit="edges",
                cause="BUG: a piece alone has an edge of three faces",
            ),
            jn.measured(
                "piece.free_edges",
                worst,
                0,
                unit="edges",
                where=where,
                cause="BUG: a piece alone has an open edge nothing closes",
            ),
        ], {"unexplained": per_piece, "files": {n: p.name for n, p in self.alone_files.items()}}

    def _alone_fine(self):
        worst, where = 0, {}
        for name, path in self.alone_files.items():
            count = self._unexplained(name, self.k.inspect_file(path, jn.SEW_FINE_M))
            if count > worst or not where:
                worst, where = count, {"component": name}
        return [
            jn.measured(
                "junction.free_edges_classified",
                worst,
                0,
                unit="edges",
                where=where,
                cause="BUG: a seam of the piece closes only at the coarser tolerance",
            )
        ], {}

    # ---- D3, D4, E1: the cuts, one fragment per group ------------------------------------

    def _cut_all(self) -> None:
        if self.cut_done:
            return
        self.cut_done = True
        self.groups = self._cut_groups()
        for group in self.groups:
            fuzzy = 0.0 if len(group) == 2 else jn.GROUP_FUZZY_M
            a = list(self.faces[group[0]])
            b = [f for name in group[1:] for f in self.faces[name]]
            result = self.k.fragment(a, b, fuzzy=fuzzy)
            self._regroup(group, a + b, [*result.from_a, *result.from_b])

    def _cut_groups(self) -> list[list[str]]:
        groups: list[set[str]] = []
        for op in self._ops("cut"):
            pair = {op.dominant, op.dominated}
            touching = [g for g in groups if g & pair]
            merged = set(pair).union(*touching)
            groups = [g for g in groups if not g & pair] + [merged]
        order = list(self.sources)
        return [sorted(g, key=order.index) for g in groups]

    def _regroup(self, group: Sequence[str], inputs: Sequence[Face], rows) -> None:
        owner = {f: name for name in group for f in self.faces[name]}
        before = {f: self.origin[f] for f in inputs if f in self.origin}
        for name in group:
            mine = [(f, r) for f, r in zip(inputs, rows, strict=True) if owner[f] == name]
            self.faces[name] = self._inherit([f for f, _ in mine], [r for _, r in mine], before)

    def cut_pairs_separately(self) -> None:
        """Cut each row on its own pair, one fragment after another.

        The strategy the group fragment replaces (hand-off T1: pairs run separately fail where
        three pieces meet); kept so its failure stays measurable by :meth:`step` ``S10.E1``.
        """
        self.cut_done = True
        self.groups = self._cut_groups()
        for op in self._ops("cut"):
            a, b = list(self.faces[op.dominant]), list(self.faces[op.dominated])
            result = self.k.fragment(a, b)
            self._regroup([op.dominant, op.dominated], a + b, [*result.from_a, *result.from_b])

    def _gap_to_faces(self, edges: Sequence[int]) -> float:
        edge_map, worst = self._edge_map(), 0.0
        for e in edges:
            points = self._samples(e, 11)
            for face in edge_map.get(e, []):
                worst = max(worst, float(self._to_faces(points, [face]).max()))
        return worst

    def _join_cut(self):
        self._cut_all()
        joins = [op for op in self._ops("cut") if self._is_join(op)]
        if not joins:
            return _skip(["join.crease_gap", "join.length"], "no body join among the rows"), {}
        gap, shortest, where = 0.0, np.inf, {}
        for op in joins:
            edges = self._junction(op.dominant, op.dominated)
            if not edges:
                d = _contact(self.hulls[op.dominant], self.hulls[op.dominated])
                gap, shortest, where = max(gap, d), 0.0, {"pair": self._op_name(op)}
                continue
            gap = max(gap, self._gap_to_faces(edges))
            length = sum(self._length(e) for e in edges)
            if length < shortest:
                shortest, where = length, {"pair": self._op_name(op), "length_m": length}
        return [
            jn.measured(
                "join.crease_gap",
                gap,
                jn.CREASE_GAP_M,
                unit="m",
                where=where,
                cause="STRATEGY: the bodies only touch; a crease that is not crossed is never cut",
            ),
            jn.measured(
                "join.length",
                shortest,
                jn.MIN_JUNCTION_M,
                unit="m",
                bound="min",
                where=where,
                cause="STRATEGY: the join found no crease",
            ),
        ], {}

    def _cut(self):
        self._cut_all()
        ops = [op for op in self._ops("cut") if not self._is_join(op)]
        ids = [
            "junction.curve_gap",
            "junction.chain_ends",
            "junction.loop_closure",
            "junction.single_curve",
            "junction.shared_vertex",
            "junction.pcurve_on_face",
            "junction.length",
        ]
        if not ops:
            return _skip(ids, "no cut row other than body joins"), {}
        m = {"gap": 0.0, "lonely": 0, "closure": 0.0, "dup": 0, "vertex": 0, "pcurve": 0.0}
        shortest, where, lengths = np.inf, {}, {}
        for op in ops:
            edges = self._junction(op.dominant, op.dominated)
            self._measure_junction(op, edges, m)
            length = sum(self._length(e) for e in edges)
            lengths[self._op_name(op)] = length
            if length < shortest:
                shortest, where = length, {"pair": self._op_name(op)}
        return [
            jn.measured(
                "junction.curve_gap",
                m["gap"],
                jn.JUNCTION_GAP_M,
                unit="m",
                cause="BUG: a junction curve is off one of its surfaces",
            ),
            jn.measured(
                "junction.chain_ends",
                m["lonely"],
                0,
                unit="ends",
                cause="BUG: a junction chain stops with no partner",
            ),
            jn.measured(
                "junction.loop_closure",
                m["closure"],
                jn.LOOP_CLOSURE_M,
                unit="m",
                cause="BUG: a rebuilt loop does not close",
            ),
            jn.measured(
                "junction.single_curve",
                m["dup"],
                0,
                unit="curves",
                cause="BUG: a junction is two curves, one per side",
            ),
            jn.measured(
                "junction.shared_vertex",
                m["vertex"],
                0,
                unit="ends",
                cause="BUG: faces meet at a junction end without a common vertex",
            ),
            jn.measured(
                "junction.pcurve_on_face",
                m["pcurve"],
                jn.JUNCTION_GAP_M,
                unit="m",
                cause="BUG: a junction's parameter-space curve leaves its 3D curve",
            ),
            jn.measured(
                "junction.length",
                shortest,
                jn.MIN_JUNCTION_M,
                unit="m",
                bound="min",
                where=where,
                cause="STRATEGY: the pieces of a cut do not intersect",
            ),
        ], {"lengths_m": lengths}

    def _measure_junction(self, op: jn.Operation, edges: Sequence[int], m: dict) -> None:
        edge_map = self._edge_map()
        m["gap"] = max(m["gap"], self._gap_to_faces(edges))
        ends = [(s[0], s[-1]) for s in (self._samples(e, 3) for e in edges)]
        _, lonely = jn.chain(ends, jn.CHAIN_END_GAP_M)
        m["lonely"] += sum(1 for c, side in lonely if not self._on_plane(ends[c][side]))
        faces = {f for e in edges for f in edge_map.get(e, [])}
        m["closure"] = max([m["closure"], *(self._loop_gap(f) for f in faces)])
        m["dup"] += self._duplicates(op)
        m["vertex"] += self._loose_ends(ends, edge_map, faces)
        m["pcurve"] = max([m["pcurve"], *(self._pcurve_gap(e, edge_map[e]) for e in edges)])

    def _loop_gap(self, face: Face) -> float:
        """Return the largest closure gap of the loops of ``face``, in loop order."""
        ends = []
        for signed in self.k.boundary(face):
            s = self._samples(abs(signed), 3)
            ends.append((s[0], s[-1]) if signed > 0 else (s[-1], s[0]))
        loops, current = [], [ends[0]] if ends else []
        for prev, nxt in zip(ends, ends[1:], strict=False):
            if np.linalg.norm(prev[1] - nxt[0]) > jn.CHAIN_END_GAP_M:
                loops.append(current)
                current = []
            current.append(nxt)
        if current:
            loops.append(current)
        return max((jn.loop_closure(loop) for loop in loops), default=0.0)

    def _duplicates(self, op: jn.Operation) -> int:
        """Count free edges of the dominated that lie on the dominant: a junction left double."""
        edge_map, owner = self._edge_map(), self._owner()
        dominant = self.faces[op.dominant]
        count = 0
        for e, faces in edge_map.items():
            if len(faces) != 1 or owner[faces[0]] != op.dominated:
                continue
            points = self._samples(e, 9)
            if not _bbox_hit(points, self.hulls[op.dominant], jn.SEW_M):
                continue
            if float(self._to_faces(points, dominant).max()) <= jn.JUNCTION_GAP_M:
                count += 1
        return count

    def _loose_ends(self, ends, edge_map, faces) -> int:
        """Count junction ends where a free edge of the same faces ends: no common vertex."""
        free_ends = [
            p
            for e, fs in edge_map.items()
            if len(fs) == 1 and fs[0] in faces
            for p in (lambda s: (s[0], s[-1]))(self._samples(e, 3))
        ]
        return sum(
            1
            for pair in ends
            for p in pair
            if not self._on_plane(p)
            and any(np.linalg.norm(p - q) <= jn.CHAIN_END_GAP_M for q in free_ends)
        )

    def _pcurve_gap(self, edge: int, faces: Sequence[Face]) -> float:
        low, high = self.k.edge_bounds(edge)
        ts = np.linspace(low, high, 9)
        points = self.k.edge_values(edge, ts.tolist())
        worst = 0.0
        for face in faces:
            for t, p in zip(ts, points, strict=True):
                uv = self.k.reparametrize(edge, face, float(t))
                worst = max(worst, float(np.linalg.norm(np.subtract(self.k.value(face, uv), p))))
        return worst

    def _group(self):
        self._cut_all()
        groups = [g for g in self.groups if len(g) >= 3]
        ids = ["group.junction_length", "group.single_curve"]
        if not groups:
            return _skip(ids, "no group of three pieces or more"), {}
        lengths, dup = {}, 0
        for op in self._ops("cut"):
            if not any({op.dominant, op.dominated} <= set(g) for g in groups):
                continue
            edges = self._junction(op.dominant, op.dominated)
            lengths[f"{op.dominant} x {op.dominated}"] = sum(self._length(e) for e in edges)
            dup += self._duplicates(op)
        shortest = min(lengths.values()) if lengths else 0.0
        return [
            jn.measured(
                "group.junction_length",
                shortest,
                jn.MIN_JUNCTION_M,
                unit="m",
                bound="min",
                where={"lengths_m": lengths},
                cause="STRATEGY: a pair of the group does not intersect",
            ),
            jn.measured(
                "group.single_curve",
                dup,
                0,
                unit="curves",
                cause="STRATEGY: pairs cut one after another leave a junction double; "
                "cut the group in one fragment",
            ),
        ], {"groups": groups}

    # ---- D5, D6: projected junctions and the hosts they split ----------------------------

    def _project(self):
        ops = self._ops("project")
        ids = ["junction.projected_length", "junction.offset", "junction.ends_on_cut"]
        if not ops:
            return _skip(ids, "no projection row"), {}
        self._cut_all()
        rel, offset, lonely, where = 0.0, 0.0, 0, {}
        lengths = {}
        for op in ops:
            edges, samples, distances = self._seat(op)
            self.j_edges[op], self.j_samples[op] = edges, samples
            found = sum(jn.polyline_length(s) for s in samples)
            probe = sum(jn.polyline_length(c) for c in self._probe(op))
            lengths[self._op_name(op)] = {"projected_m": found, "probe_m": probe}
            r = abs(found - probe) / probe if probe > 0 else 1.0
            if r >= rel:
                rel, where = r, {"pair": self._op_name(op)}
            offset = max(offset, max(distances, default=0.0))
            lonely += self._open_j_ends(op, samples)
        tolerance = min(op.tolerance_m for op in ops)
        return [
            jn.measured(
                "junction.projected_length",
                rel,
                1e-3,
                unit="relative",
                where=where,
                cause="BUG: the projected curves are not the dominant's contact edges",
            ),
            jn.measured(
                "junction.offset",
                offset,
                tolerance,
                unit="m",
                cause="BUG: the dominant's contact edges are off the host",
            ),
            jn.measured(
                "junction.ends_on_cut",
                lonely,
                0,
                unit="ends",
                cause="STRATEGY: the projected curves do not close a footprint on the "
                "host with the cut's junction",
            ),
        ], {"lengths": lengths}

    def _seat(self, op: jn.Operation):
        """Return the dominant's free edges within :data:`SEAT_REACH_M` of the host."""
        edge_map, owner = self._edge_map(), self._owner()
        hosts = self.faces[op.dominated]
        edges, samples, distances = [], [], []
        for e, faces in edge_map.items():
            if len(faces) != 1 or owner[faces[0]] != op.dominant:
                continue
            points = self._samples(e)
            if not _bbox_hit(points, self.hulls[op.dominated], SEAT_REACH_M):
                continue
            d = float(self._to_faces(points, hosts).max())
            if d <= SEAT_REACH_M:
                edges.append(e)
                samples.append(points)
                distances.append(d)
        return edges, samples, distances

    def _probe(self, op: jn.Operation) -> list[np.ndarray]:
        """Return the dominant's contact curves from its own patches, apart from the kernel."""
        hull = self.hulls[op.dominated]
        return [
            c
            for c in _free_boundaries(self.sources[op.dominant], jn.SEW_M)
            if float(jn.distance_to_triangles(c, hull).max()) <= SEAT_REACH_M
        ]

    def _open_j_ends(self, op: jn.Operation, samples: Sequence[np.ndarray]) -> int:
        ends = [(s[0], s[-1]) for s in samples]
        _, lonely = jn.chain(ends, jn.CHAIN_END_GAP_M)
        edge_map, owner = self._edge_map(), self._owner()
        stops = [
            self._samples(e, 41)
            for e, faces in edge_map.items()
            if any(owner[f] == op.dominated for f in faces)
            and (len(faces) == 1 or {owner[f] for f in faces} - {op.dominated, op.dominant})
        ]
        count = 0
        for c, side in lonely:
            p = ends[c][side]
            if self._on_plane(p):
                continue
            if not any(jn.distance_to_polyline(p[None], s)[0] <= jn.J_END_ON_CUT_M for s in stops):
                count += 1
        return count

    def _split(self):
        ops = self._ops("project")
        ids = ["junction.on_host_loops", "junction.split_closure"]
        if not ops:
            return _skip(ids, "no projection row"), {}
        on_loop, closure = 0.0, 0.0
        for op in ops:
            faces = list(self.faces[op.dominated]) + list(self.faces[op.dominant])
            # an earlier imprint numbers the edges again, so the curves are found anew
            edges = self._seat(op)[0]
            result = self.k.imprint(faces, edges, fuzzy=op.tolerance_m)
            n = len(self.faces[op.dominated])
            before = {f: self.origin[f] for f in faces if f in self.origin}
            self.faces[op.dominated] = self._inherit(faces[:n], result.from_a[:n], before)
            self.faces[op.dominant] = self._inherit(faces[n:], result.from_a[n:], before)
            loops = self._host_loops(op)
            for s in self.j_samples.get(op, []):
                on_loop = max(on_loop, self._to_curves(s, loops))
            touched = [f for f in self.faces[op.dominated] if self._near_j(f, op)]
            closure = max([closure, *(self._loop_gap(f) for f in touched)])
        return [
            jn.measured(
                "junction.on_host_loops",
                on_loop,
                jn.J_ON_LOOP_M,
                unit="m",
                cause="BUG: a projected junction is on the host but not on its loops",
            ),
            jn.measured(
                "junction.split_closure",
                closure,
                jn.J_LOOP_CLOSURE_M,
                unit="m",
                cause="BUG: a split host face's loop does not close",
            ),
        ], {}

    def _host_loops(self, op: jn.Operation) -> list[int]:
        return sorted({abs(e) for f in self.faces[op.dominated] for e in self.k.boundary(f)})

    def _to_curves(self, points: np.ndarray, edges: Sequence[int]) -> float:
        """Return the largest distance of the points to the nearest of the curves (exact)."""
        best = np.full(len(points), np.inf)
        low, high = points.min(axis=0) - SEAT_REACH_M, points.max(axis=0) + SEAT_REACH_M
        for e in edges:
            box_low, box_high = self.k.edge_bbox(e)
            if np.any(np.asarray(box_high) < low) or np.any(np.asarray(box_low) > high):
                continue
            projected = self.k.edge_project(e, _points(points))
            best = np.minimum(best, np.linalg.norm(np.asarray(projected) - points, axis=1))
        return float(best.max()) if len(best) else 0.0

    def _near_j(self, face: Face, op: jn.Operation) -> bool:
        low, high = self.k.bbox(face)
        for s in self.j_samples.get(op, []):
            if np.all(s.min(axis=0) <= np.asarray(high) + SEAT_REACH_M) and np.all(
                s.max(axis=0) >= np.asarray(low) - SEAT_REACH_M
            ):
                return True
        return False

    # ---- D8, D8b: the inside removed, and the skin it leaves --------------------------------

    def _interior(self, face: Face) -> tuple[np.ndarray, np.ndarray]:
        """Return a point inside the trimmed face, nearest its centre, and the normal there."""
        (u0, v0), (u1, v1) = self.k.uv_bounds(face)
        grid = [
            (u0 + (u1 - u0) * a, v0 + (v1 - v0) * b)
            for a in np.linspace(0.05, 0.95, 7)
            for b in np.linspace(0.05, 0.95, 7)
        ]
        inside = self.k.inside(face, grid)
        centre = np.asarray(self.k.centroid(face))
        candidates = [uv for uv, ok in zip(grid, inside, strict=True) if ok] or grid
        points = self.k.values(face, candidates)
        k = int(np.argmin(np.linalg.norm(points - centre, axis=1)))
        return points[k], np.asarray(self.k.normal(face, candidates[k]))

    def _partners_of(self, name: str) -> tuple[list[str], list[str]]:
        """Return the pieces ``name`` is cut against, and the dominants projected on it."""
        cut = [
            op.dominant if op.dominated == name else op.dominated
            for op in self._ops("cut")
            if name in (op.dominant, op.dominated)
        ]
        under = [op.dominant for op in self._ops("project") if op.dominated == name]
        return cut, under

    def _legit(self, name: str, point: np.ndarray, normal: np.ndarray) -> bool:
        """Whether a point of ``name`` lies inside a cut partner or under a projected dominant."""
        cut, under = self._partners_of(name)
        for other in cut:
            hull = self.hulls[other]
            if jn.dominant_inside(point[None], hull, hull, near=jn.SEW_M)[0]:
                return True
        return any(jn.ray_hits(point, normal, self.hulls[other]) for other in under)

    def _remove(self):
        edge_map, owner = self._edge_map(), self._owner()
        barriers = {e for e, fs in edge_map.items() if len({owner[f] for f in fs}) > 1}
        expected = {}
        for name, faces in self.faces.items():
            expected[name] = sum(
                self.k.area(f) for f in faces if self._legit(name, *self._interior(f))
            )
        removed, dropped, emptied = {}, 0, 0
        for name in list(self.faces):
            kept, gone = self._flood(name, edge_map, owner, barriers)
            widths = [self._width(f) for f in kept]
            kept, thin = jn.drop_zero_width(kept, widths)
            dropped += len(thin)
            removed[name] = sum(self.k.area(f) for f in gone + thin)
            if gone or thin:
                self.k.remove(gone + thin)
            self.faces[name] = kept
            emptied += 0 if kept else 1
        rel, where = 0.0, {"removed_m2": removed, "independent_m2": expected, "dropped": dropped}
        for name, area in removed.items():
            scale = max(area, expected[name], 1e-300)
            rel = max(rel, abs(area - expected[name]) / scale if scale > 1e-300 else 0.0)
        if dropped:
            self.warnings.append(
                f"{dropped} region(s) under {jn.ZERO_WIDTH_M} m mean width dropped"
            )
        return [
            jn.measured(
                "removal.seeds_reach",
                emptied,
                0,
                unit="pieces",
                cause="BUG: a piece kept no face; its seed is not on its exposed side",
            ),
            *self._kept_on_loops(),
            jn.measured(
                "removal.area",
                rel,
                1e-3,
                unit="relative",
                where=where,
                cause="BUG: the flood removed another area than lies inside or under the dominants",
            ),
            jn.measured(
                "junction.no_vertex_inside",
                self._inside_kept(),
                0,
                unit="faces",
                cause="BUG: a kept face of a dominated piece lies inside its dominant",
            ),
            jn.measured(
                "junction.no_triple_edge",
                self._triple(),
                0,
                unit="edges",
                cause="BUG: an edge of three faces is left",
            ),
        ], {"removed_m2": removed, "dropped": dropped}

    def _width(self, face: Face) -> float:
        perimeter = sum(self._length(abs(e)) for e in self.k.boundary(face))
        return jn.mean_width(self.k.area(face), perimeter)

    def _flood(self, name, edge_map, owner, barriers):
        faces = self.faces[name]
        neighbours: dict[Face, list[tuple[int, Face]]] = {f: [] for f in faces}
        mine_barriers = set()
        for e, fs in edge_map.items():
            mine = [f for f in fs if owner[f] == name]
            if e in barriers and mine:
                mine_barriers.add(e)
            for f in mine:
                neighbours[f] += [(e, g) for g in mine if g != f]
        if not mine_barriers:
            return list(faces), []
        barrier_points = np.concatenate([self._samples(e, 9) for e in mine_barriers])
        far = {
            f: float(
                jn.distance_to_polyline(barrier_points, np.asarray(self.k.centroid(f))[None]).min()
            )
            for f in faces
        }
        # The junctions cut the piece into regions; each region is kept or lost whole, as its
        # face farthest from the junctions says (its seed). A dominant can cut a dominated piece
        # in two exposed halves (a fin through a tail plane), so every region gets a seed.
        kept: set[Face] = set()
        seen: set[Face] = set()
        for face in sorted(faces, key=lambda f: -far[f]):
            if face in seen:
                continue
            region = jn.flood(neighbours, seeds=[face], barriers=barriers)
            seen |= region
            if not self._legit(name, *self._interior(face)):
                kept |= region
        return [f for f in faces if f in kept], [f for f in faces if f not in kept]

    def _kept_on_loops(self) -> list[dict[str, Any]]:
        ops = self._ops("project")
        if not ops:
            return _skip(["removal.kept_on_loops"], "no projection row")
        worst = 0.0
        for op in ops:
            loops = self._host_loops(op)
            for s in self.j_samples.get(op, []):
                worst = max(worst, self._to_curves(s, loops))
        return [
            jn.measured(
                "removal.kept_on_loops",
                worst,
                jn.KEPT_ON_LOOP_M,
                unit="m",
                cause="BUG: the host kept the side under the dominant",
            )
        ]

    def _inside_kept(self) -> int:
        count = 0
        for op in self._ops("cut"):
            hull = self.hulls[op.dominant]
            for face in self.faces[op.dominated]:
                point, _ = self._interior(face)
                if jn.dominant_inside(point[None], hull, hull, near=jn.SEW_M)[0]:
                    count += 1
        return count

    def _triple(self) -> int:
        return sum(1 for fs in self._edge_map().values() if len(fs) > 2)

    def _coverage(self):
        worst, where, totals = 0.0, {}, {}
        for name, patches in self.sources.items():
            area, missing, largest = 0.0, 0.0, (0.0, -1)
            for index, patch in enumerate(patches):
                cells = self._cells(name, index, patch)
                area += cells["total"]
                missing += cells["missing"]
                if cells["largest"] > largest[0]:
                    largest = (cells["largest"], index)
            totals[name] = {"area_m2": area, "missing_m2": missing}
            fraction = largest[0] / area if area > 0 else 0.0
            if fraction >= worst:
                worst = fraction
                where = {"component": name, "patch": largest[1], "missing_m2": missing}
        return [
            jn.measured(
                "coverage.skin",
                worst,
                self.coverage_fraction,
                unit="fraction",
                where=where,
                cause="BUG: a part of a source skin is neither kept, "
                "inside a dominant nor under one",
            )
        ], {"pieces": totals}

    def _cells(self, name: str, index: int, patch: Patch, count: int = 24) -> dict[str, float]:
        """Sample one patch's domain: cell areas covered, removed with a reason, or missing."""
        g = evaluate_patch(patch, count + 1)
        a, b, c, d = g[:-1, :-1], g[1:, :-1], g[1:, 1:], g[:-1, 1:]
        areas = 0.5 * (
            np.linalg.norm(np.cross(b - a, c - a), axis=-1)
            + np.linalg.norm(np.cross(c - a, d - a), axis=-1)
        )
        centres = (a + b + c + d) / 4.0
        normals = np.cross(c - a, d - b)
        su = np.linspace(0.5 / count, 1 - 0.5 / count, count)
        ku, kv = patch.knots_u, patch.knots_v
        uvs = [(ku[0] + (ku[-1] - ku[0]) * s, kv[0] + (kv[-1] - kv[0]) * t) for s in su for t in su]
        covered = np.zeros(count * count, bool)
        for face in (f for f in self.faces.get(name, []) if self.origin.get(f) == (name, index)):
            covered |= np.asarray(self.k.inside(face, uvs), bool)
        missing = np.zeros(count * count, bool)
        flat_c, flat_n = centres.reshape(-1, 3), normals.reshape(-1, 3)
        for k in np.flatnonzero(~covered):
            missing[k] = not self._legit(name, flat_c[k], flat_n[k])
        return {
            "total": float(areas.sum()),
            "missing": float(areas.reshape(-1)[missing].sum()),
            "largest": _largest_group(missing.reshape(count, count), areas),
        }

    # ---- C1 to C4: the joins, written and sewn -------------------------------------------

    def _joins(self) -> list[jn.Operation]:
        return [op for op in self._ops("cut") if self._is_join(op)]

    def _shared(self):
        joins = self._joins()
        if not joins:
            return _skip(["join.shared_pairs"], "no body join among the rows"), {}
        counts = {self._op_name(op): len(self._junction(op.dominant, op.dominated)) for op in joins}
        return [
            jn.measured(
                "join.shared_pairs",
                min(counts.values()),
                1,
                unit="curves",
                bound="min",
                where={"pairs": counts},
                cause="STRATEGY: the join shares no curve; the crease was never cut",
            )
        ], {}

    def _written(self):
        joins = self._joins()
        if not joins:
            return _skip(["join.written_pairs"], "no body join among the rows"), {}
        worst, where = 0.0, {}
        for op in joins:
            path = self.out / f"S10-join-{op.dominant}-{op.dominated}.igs"
            self.k.export_iges(
                {n: self.faces[n] for n in (op.dominant, op.dominated) if self.faces[n]}, path
            )
            self.join_files[(op.dominant, op.dominated)] = path
            topology = self.k.inspect_file(path, None)
            curves = [(topology.names[f[0]], s) for s, f in topology.edges if len(f) == 1 and f]
            pairs = jn.pair_curves(curves, near=jn.SHARED_PAIR_NEAR_M, end_gap=jn.SHARED_PAIR_END_M)
            gap = max((p[2] for p in pairs), default=jn.SHARED_PAIR_NEAR_M)
            if gap >= worst:
                worst, where = gap, {"pair": self._op_name(op), "pairs": len(pairs)}
        return [
            jn.measured(
                "join.written_pairs",
                worst,
                jn.WRITTEN_PAIR_M,
                unit="m",
                where=where,
                cause="BUG: the two sides of a shared curve were written apart",
            )
        ], {}

    def _on_surface(self):
        joins = self._joins()
        if not joins:
            return _skip(["join.edge_on_surface"], "no body join among the rows"), {}
        worst = 0.0
        for name in {n for op in joins for n in (op.dominant, op.dominated)}:
            for face in self.faces[name]:
                for e in self.k.boundary(face):
                    points = self._samples(abs(e), 9)
                    worst = max(worst, float(self._to_faces(points, [face]).max()))
        return [
            jn.measured(
                "join.edge_on_surface",
                worst,
                jn.EDGE_ON_SURFACE_M,
                unit="m",
                cause="BUG: a face's edge is off the face's own surface",
            )
        ], {}

    def _join_sewn(self):
        if not self.join_files:
            return _skip(["join.group_free_edges"], "no body join among the rows"), {}
        worst, where = 0, {}
        for (a, b), path in self.join_files.items():
            others = {n: h for n, h in self.hulls.items() if n not in (a, b)}
            for tolerance in (jn.SEW_M, jn.SEW_FINE_M):
                free = [s for s, f in self.k.inspect_file(path, tolerance).edges if len(f) == 1]
                count = _unexplained(free, others, self.plane_axis)
                if count >= worst:
                    worst, where = count, {"join": f"{a} + {b}", "tolerance_m": tolerance}
        return [
            jn.measured(
                "join.group_free_edges",
                worst,
                0,
                unit="edges",
                where=where,
                cause="BUG: the join written in one file does not sew closed",
            )
        ], {}

    # ---- D9, D10, E2: the whole written, read back and sewn ------------------------------

    def _write(self):
        path = self.out / "S10-assembly.igs"
        groups = {n: f for n, f in self.faces.items() if f}
        self.k.export_iges(groups, path)
        topology = self.k.inspect_file(path, None)
        gap, rel, where = 0, 0.0, {}
        for name, faces in groups.items():
            read = [i for i, n in enumerate(topology.names) if n == name]
            area = sum(self.k.area(f) for f in faces)
            back = sum(topology.areas[i] for i in read)
            if abs(len(read) - len(faces)) >= gap:
                gap, where = abs(len(read) - len(faces)), {"component": name}
            rel = max(rel, abs(back - area) / area if area > 0 else 0.0)
        return [
            jn.measured(
                "write.read_back",
                gap,
                0,
                unit="faces",
                where=where,
                cause="BUG: the written file reads back another count of faces",
            ),
            jn.measured(
                "write.area",
                rel,
                1e-3,
                unit="relative",
                cause="BUG: a written face reads back with another area",
            ),
        ], {"iges": path.name, "faces": {n: len(f) for n, f in groups.items()}}

    def _sew(self):
        path = self.out / "S10-assembly.igs"
        new_free, triple, new_slivers, where = 0, 0, 0, {}
        for tolerance in (jn.SEW_M, jn.SEW_WIDE_M):
            topology = self.k.inspect_file(path, tolerance)
            free = [s for s, f in topology.edges if len(f) == 1]
            fresh = [s for s in free if not self._brought(s)]
            if len(fresh) >= new_free:
                new_free = len(fresh)
                where = {"tolerance_m": tolerance, "at": [s[0].tolist() for s in fresh[:4]]}
            triple = max(triple, sum(1 for _, f in topology.edges if len(f) > 2))
            widths = [
                jn.mean_width(a, p)
                for a, p in zip(topology.areas, topology.perimeters, strict=True)
            ]
            new_slivers = max(
                new_slivers, jn.introduced(len(jn.slivers(widths)), self.alone_slivers)
            )
        return [
            jn.measured(
                "sew.free_introduced",
                new_free,
                0,
                unit="edges",
                where=where,
                cause="BUG: the assembly opened an edge its pieces did not have",
            ),
            jn.measured(
                "sew.triple_edges",
                triple,
                0,
                unit="edges",
                cause="BUG: the written assembly sews an edge of three faces",
            ),
            jn.measured(
                "sew.slivers",
                new_slivers,
                0,
                unit="faces",
                cause="BUG: the assembly made a face under 5 mm wide",
            ),
        ], {}

    def _brought(self, samples: np.ndarray) -> bool:
        """Whether a free edge of the assembly is on the plane or was a free edge of a piece."""
        if self.plane_axis is not None and self._on_plane_curve(samples):
            return True
        return any(
            float(jn.distance_to_polyline(samples, s).max()) <= jn.OPENING_M
            for s in self.alone_free
        )

    def _clearance(self):
        joined = {n for op in self.plan for n in (op.dominant, op.dominated)}
        separate = [n for n in self.sources if n not in joined]
        if not separate:
            return _skip(["assembly.clearance"], "every piece takes part in a row"), {}
        least, where = np.inf, {}
        for name in separate:
            for other in self.sources:
                if other == name:
                    continue
                d = _contact(self.hulls[name], self.hulls[other])
                if d < least:
                    least, where = d, {"pieces": f"{name} and {other}"}
        return [
            jn.measured(
                "assembly.clearance",
                least,
                jn.SEW_M,
                unit="m",
                bound="min",
                where=where,
                cause="STRATEGY: a piece in no row meets another piece",
            )
        ], {}


def _unexplained(free, hulls: Mapping[str, np.ndarray], plane_axis: int | None) -> int:
    partners = [h for h in hulls.values() if len(h)]

    def distance(points: np.ndarray) -> np.ndarray:
        if not partners:
            return np.full(len(points), np.inf)
        return np.min([jn.distance_to_triangles(points, h) for h in partners], axis=0)

    def inside(points: np.ndarray) -> np.ndarray:
        if not partners:
            return np.zeros(len(points), bool)
        return np.any([jn.parity_inside(points, h) for h in partners], axis=0)

    classes = jn.classify_free_edges(free, distance=distance, inside=inside, plane_axis=plane_axis)
    return classes.count("unexplained")


def _largest_group(missing: np.ndarray, areas: np.ndarray) -> float:
    """Return the area of the largest group of missing cells joined by a side."""
    seen = np.zeros_like(missing)
    largest = 0.0
    rows, cols = missing.shape
    for i in range(rows):
        for j in range(cols):
            if not missing[i, j] or seen[i, j]:
                continue
            total, stack = 0.0, [(i, j)]
            seen[i, j] = True
            while stack:
                a, b = stack.pop()
                total += float(areas[a, b])
                for x, y in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                    if 0 <= x < rows and 0 <= y < cols and missing[x, y] and not seen[x, y]:
                        seen[x, y] = True
                        stack.append((x, y))
            largest = max(largest, total)
    return largest
