"""Strategy 1 boundary laws and measured surface-mesh policy.

Pipeline role: workspace mesh planning and acceptance, downstream of the pure
schema. Shared edges use one ordered node list. Measurements are made on the
realized mesh, independently of the requested controls.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import numpy as np

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._mesh_schema import mesh_measurements
from pyflightstream.geometry._mesh_topology import Mesh
from pyflightstream.geometry._records import check_entry


def follower_edges(controls: Mapping[str, Any], edge_nodes: Mapping) -> dict:
    """Copy neighbour boundary divisions in dependency and declared priority order.

    Node identities and their order are preserved. A follower may not prescribe
    its own edge distribution; flexible interiors are handled after boundaries.
    """
    result = deepcopy(dict(edge_nodes))
    for name in controls["order"]:
        component = controls["components"][name]
        if component["role"] != "follower":
            result.setdefault(name, {})
            continue
        if result.get(name):
            raise InputValueError(f"{name}: follower cannot own a distribution")
        result[name] = {}
        for neighbour in component["follows"]:
            for edge, nodes in result.get(neighbour, {}).items():
                result[name].setdefault(edge, deepcopy(nodes))
    return result


def _check(name: str, value: float, limit: float = 0.0, *, where=None, unit="") -> dict:
    return check_entry(
        name, "passed" if value <= limit else "failed", value, limit, where=where, unit=unit
    )


def _canonical(cell) -> tuple:
    values = tuple(cell)
    return min(values[i:] + values[:i] for i in range(len(values)))


def structured_check(mesh, node_ids, component: str, kind: str) -> dict:
    """Compare oriented mesh cells with every cell of the declared rectangular grid."""
    ids = np.asarray(node_ids, dtype=int)
    if ids.ndim != 2 or min(ids.shape) < 2 or len(set(ids.flat)) != ids.size:
        return _check("mesh.structured", 1, where={"component": component, "kind": kind})
    expected = {
        _canonical((ids[j, i], ids[j, i + 1], ids[j + 1, i + 1], ids[j + 1, i]))
        for j in range(ids.shape[0] - 1)
        for i in range(ids.shape[1] - 1)
    }
    cells = [c for c, name in zip(mesh.cells, mesh.components, strict=True) if name == component]
    realized = {_canonical(c) for c in cells}
    defects = len(expected ^ realized) + len(cells) - len(realized)
    return _check("mesh.structured", defects, where={"component": component, "kind": kind})


def row_check(xyz, node_ids, kind: str) -> dict:
    """Measure constant-y deviation on all rows, including the root row."""
    ids = np.asarray(node_ids, dtype=int)
    points = np.asarray(xyz)[ids[:1] if kind == "fillet" else ids]
    deviation = float(np.max(np.ptp(points[:, :, 1], axis=1)))
    return _check("mesh.flow_aligned_rows", deviation, 1e-12, where={"kind": kind}, unit="m")


def trailing_edge_check(node_ids) -> dict:
    """Measure the number of base cells across the blunt trailing edge."""
    across = np.asarray(node_ids).shape[1] - 1
    return _check("mesh.trailing_edge_one_quad", abs(across - 1), where={"cells_across": across})


def axial_check(xyz, node_ids, spacing_m: float) -> dict:
    """Measure uniform axial stations without a junction blend or a local refinement."""
    stations = np.asarray(xyz)[np.asarray(node_ids, dtype=int), 0]
    deviation = max(
        float(np.max(np.ptp(stations, axis=1))),
        float(np.max(np.abs(np.diff(stations, axis=0) - spacing_m))),
    )
    return _check("mesh.fuselage_uniform_axial", deviation, 1e-12, unit="m")


def transition_checks(
    mesh, component: str, region: str, limits: Mapping, *, intersects=()
) -> list[dict]:
    """Measure region eligibility, triangle fraction, quad aspect and corner skew.

    Lifting surfaces and fillets stay structured even when marked flexible.
    Junction ratio targets are deliberately not applied here.
    """
    cells = [
        cell for cell, name in zip(mesh.cells, mesh.components, strict=True) if name == component
    ]
    triangles = sum(len(cell) == 3 for cell in cells)
    allowed = region == "fairing" or (
        region == "aft_patch" and bool(set(intersects) & {"pylon", "vertical_tail"})
    )
    checks = [_check("mesh.transition.region", int(bool(triangles) and not allowed))]
    checks.append(
        _check(
            "mesh.transition.triangle_fraction",
            triangles / max(1, len(cells)),
            float(limits.get("max_triangle_fraction", 0)),
        )
    )
    aspect, skew = 0.0, 0.0
    for cell in cells:
        if len(cell) != 4:
            continue
        points = mesh.xyz[list(cell)]
        edges = np.roll(points, -1, axis=0) - points
        lengths = np.linalg.norm(edges, axis=1)
        if min(lengths) <= 0:
            return [*checks, _check("mesh.transition.degenerate", 1)]
        aspect = max(aspect, float(max(lengths) / min(lengths)))
        cosines = np.sum(-np.roll(edges, 1, axis=0) * edges, axis=1) / (
            np.roll(lengths, 1) * lengths
        )
        skew = max(skew, float(np.max(np.abs(np.degrees(np.arccos(np.clip(cosines, -1, 1))) - 90))))
    checks.append(_check("mesh.transition.aspect", aspect, float(limits.get("max_aspect", 8))))
    checks.append(
        _check("mesh.transition.skew", skew, float(limits.get("max_skew_deg", 50)), unit="deg")
    )
    return checks


def fillet_checks(xyz, node_ids, wing_root, wing_next, *, tolerance_m: float) -> list[dict]:
    """Measure shared root identities and uniform cross spacing from the wing law."""
    ids = np.asarray(node_ids, dtype=int)
    root, next_row = np.asarray(wing_root, dtype=int), np.asarray(wing_next, dtype=int)
    points = np.asarray(xyz)
    shared = int(not np.array_equal(ids[0], root))
    first_span = float(np.median(np.linalg.norm(points[next_row] - points[root], axis=1)))
    across = np.linalg.norm(np.diff(points[ids], axis=0), axis=2)
    return [
        _check("mesh.fillet.shared_root", shared),
        _check(
            "mesh.fillet.root_refinement",
            float(np.max(np.abs(across - first_span))),
            tolerance_m,
            unit="m",
        ),
    ]


def keel_check(keel_x, fuselage_x) -> dict:
    """Measure the keel edge's distance to the fuselage axial stations."""
    keel, body = np.asarray(keel_x), np.asarray(fuselage_x)
    if not len(keel) or not len(body):
        return _check("mesh.fairing.keel_stations", 1)
    distance = np.min(np.abs(keel[:, None] - body[None, :]), axis=1)
    return _check("mesh.fairing.keel_stations", float(max(distance)), 1e-12, unit="m")


def fairing_boundary_check(mesh, component: str, boundary_edges, small_m: float) -> dict:
    """Count small cells outside the single row touching the prescribed boundary."""
    boundary = {tuple(sorted(edge)) for edge in boundary_edges}
    defects = 0
    for cell, name in zip(mesh.cells, mesh.components, strict=True):
        if name != component:
            continue
        p = mesh.xyz[list(cell)]
        area = sum(
            float(np.linalg.norm(np.cross(p[j] - p[0], p[j + 1] - p[0]))) / 2
            for j in range(1, len(cell) - 1)
        )
        touches = any(
            tuple(sorted(edge)) in boundary for edge in zip(cell, cell[1:] + cell[:1], strict=True)
        )
        defects += int(np.sqrt(area) < small_m and not touches)
    return _check("mesh.fairing.small_boundary_row", defects)


def aft_growth_checks(paths, *, first_m: float, far_m: float) -> list[dict]:
    """Measure new aft distributions from the fillet cross spacing to body spacing."""
    widths = [np.diff(np.asarray(path, dtype=float)) for path in paths]
    if not widths or any(len(w) < 2 or np.any(w <= 0) for w in widths):
        return [_check("mesh.fairing.aft_monotone", 1)]
    growth = max(float(max(w[1:] / w[:-1])) for w in widths)
    ends = max(max(abs(float(w[0]) - first_m), abs(float(w[-1]) - far_m)) for w in widths)
    # A strict inequality remains strict in the machine-readable record.
    return [
        _check("mesh.fairing.aft_end_spacing", ends, 1e-12, unit="m"),
        _check("mesh.fairing.aft_growth", growth, float(np.nextafter(1.2, 0.0))),
    ]


def cut_check(mesh, node_ids, intercept: float, slope: float, *, required: set[str]) -> dict:
    """Check a TE-plane cut is a mesh-edge chain across all required components."""
    ids = [int(i) for i in node_ids]
    edges: dict[tuple, set[str]] = {}
    for cell, name in zip(mesh.cells, mesh.components, strict=True):
        for edge in zip(cell, cell[1:] + cell[:1], strict=True):
            edges.setdefault(tuple(sorted(edge)), set()).add(name)
    components: set[str] = set()
    missing = int(len(ids) < 2)
    for edge in zip(ids[:-1], ids[1:], strict=True):
        key = tuple(sorted(edge))
        missing += int(key not in edges)
        components.update(edges.get(key, set()))
    if ids:
        points = mesh.xyz[ids]
        missing += int(np.max(np.abs(points[:, 0] - intercept - slope * points[:, 1])) > 1e-10)
    missing += len(required - components)
    return _check("mesh.trailing_edge.cut_continuation", missing)


def omission_checks(
    mesh, excluded_surfaces: set[int], source_before: str, source_after: str
) -> list[dict]:
    """Measure omitted CAD-tip faces and unchanged source identity independently."""
    return [
        _check("mesh.fillet.tip_omitted", len(set(mesh.surfaces) & excluded_surfaces)),
        _check("mesh.source.unchanged", int(source_before != source_after)),
    ]


def surface_only_check(dimensions) -> dict:
    """Refuse volume, prism and solid entities in the realized entity inventory."""
    return _check("mesh.surfaces_only", sum(int(value != 2) for value in dimensions))


def body_aspect_checks(xyz, node_ids, band) -> list[dict]:
    """Check realized circumferential over axial edge lengths at every station."""
    points = np.asarray(xyz)[np.asarray(node_ids, dtype=int)]
    cross = np.linalg.norm(np.diff(points, axis=1), axis=2)
    axial = np.linalg.norm(np.diff(points, axis=0), axis=2)
    checks = []
    for j in range(len(axial)):
        for i in range(cross.shape[1]):
            if axial[j, i] <= 0:
                raise InputValueError("E14: zero axial spacing in realized body grid")
            for k in (j, j + 1):
                checks.append(
                    mesh_measurements(
                        "E14", f"station {k}, azimuth {i}", float(cross[k, i] / axial[j, i]), band
                    )
                )
    return checks


def _collapsed_nodes(mesh: Mesh, pairs, tolerance_m: float):
    xyz = mesh.xyz.copy()
    if not np.all(np.isfinite(xyz)):
        raise InputValueError("collapse distance: mesh coordinates must be finite")
    representatives = np.arange(len(xyz))
    used: set[int] = set()
    distance = 0.0
    for a, b in pairs:
        if a == b or min(a, b) < 0 or max(a, b) >= len(xyz) or {a, b} & used:
            raise InputValueError("collapse: disjoint valid upper/lower TE pairs required")
        used.update((a, b))
        distance = max(distance, float(np.linalg.norm(xyz[a] - xyz[b]) / 2))
        if not np.isfinite(distance) or distance > tolerance_m:
            raise InputValueError(f"collapse distance {distance} exceeds tolerance {tolerance_m} m")
        xyz[a] = (xyz[a] + xyz[b]) / 2
        representatives[b] = a
    return xyz, representatives, used, distance


def collapse_trailing_edge(
    mesh: Mesh, pairs, base_cells: set[int], *, tolerance_m: float
) -> tuple[Mesh, list[dict]]:
    """Collapse explicit upper/lower TE pairs at their midpoints in a new mesh.

    Only declared base cells are removed. The source geometry and source mesh
    are untouched; any unintended degenerate skin cell refuses the operation.
    """
    if not np.isfinite(tolerance_m) or tolerance_m <= 0 or not pairs or not base_cells:
        raise InputValueError(
            "collapse: positive distance tolerance, TE pairs and base cells required"
        )
    xyz, representatives, used, distance = _collapsed_nodes(mesh, pairs, tolerance_m)
    if not base_cells <= set(range(len(mesh.cells))):
        raise InputValueError("collapse: base cell indices outside mesh")
    cells, components, surfaces = [], [], []
    for i, cell in enumerate(mesh.cells):
        new_cell = tuple(int(representatives[j]) for j in cell)
        degenerate = len(set(new_cell)) != len(new_cell)
        if i in base_cells:
            if not degenerate or not set(cell) <= used:
                raise InputValueError("collapse: declared base cell does not collapse to its TE")
            continue
        if degenerate:
            raise InputValueError("collapse: undeclared base or skin cell would degenerate")
        cells.append(new_cell)
        components.append(mesh.components[i])
        surfaces.append(mesh.surfaces[i])
    keep = sorted({j for cell in cells for j in cell})
    indices = {node: i for i, node in enumerate(keep)}
    collapsed = Mesh(
        xyz[keep],
        [tuple(indices[j] for j in cell) for cell in cells],
        components,
        surfaces,
        mesh.node_tags[keep].copy(),
    )
    return collapsed, [
        _check("mesh.te.collapse_distance", distance, tolerance_m, unit="m"),
        _check("mesh.te.base_removed", abs(len(mesh.cells) - len(cells) - len(base_cells))),
    ]


#: Tolerance of a free edge on the symmetry plane y = 0 (MESH_STRATEGY section 5), m.
SYMMETRY_TOLERANCE_M = 1e-7
#: Smallest corner sine of a cell that is not degenerate (MESH_STRATEGY section 5).
DEGENERATE_SINE = 0.02


def edge_uses(mesh: Mesh) -> dict[tuple[int, int], list[int]]:
    """Map every undirected mesh edge to the cells that use it."""
    uses: dict[tuple[int, int], list[int]] = {}
    for index, cell in enumerate(mesh.cells):
        for a, b in zip(cell, cell[1:] + cell[:1], strict=True):
            uses.setdefault((min(a, b), max(a, b)), []).append(index)
    return uses


def shared_curves(mesh: Mesh) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """Discover the curves two components share: the edges used by a cell of each."""
    curves: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for edge, cells in edge_uses(mesh).items():
        names = sorted({mesh.components[c] for c in cells})
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                curves.setdefault((a, b), []).append(edge)
    return curves


def _on_symmetry(mesh: Mesh, edge) -> bool:
    return bool(np.all(np.abs(mesh.xyz[list(edge), 1]) <= SYMMETRY_TOLERANCE_M))


def follower_checks(mesh: Mesh, controls: Mapping[str, Any]) -> list[dict]:
    """Check each follower shares a curve, node to node, with every neighbour it follows.

    The shared curves are discovered on the realized mesh (edges used by a cell of each
    component); a neighbour with none is named. Hanging edges are the free-edge check's.
    """
    curves = shared_curves(mesh)
    checks = []
    for name, component in controls["components"].items():
        if component["role"] != "follower" or name not in mesh.components:
            continue
        missing = [n for n in component["follows"] if not curves.get(tuple(sorted((name, n))))]
        found = {n: len(curves.get(tuple(sorted((name, n))), [])) for n in component["follows"]}
        checks.append(
            _check(
                "mesh.follower.shared_curves",
                len(missing),
                where={"component": name, "missing_neighbours": missing, "shared_edges": found},
            )
        )
    return checks


def _corner_measures(points: np.ndarray) -> tuple[float, float, float]:
    """Return the smallest corner sine, the edge aspect and the largest skew of one cell."""
    edges = np.roll(points, -1, axis=0) - points
    lengths = np.linalg.norm(edges, axis=1)
    if min(lengths) <= 0:
        return 0.0, float("inf"), 90.0
    previous = -np.roll(edges, 1, axis=0)
    norms = np.roll(lengths, 1) * lengths
    sines = np.linalg.norm(np.cross(previous, edges), axis=1) / norms
    angles = np.degrees(np.arccos(np.clip(np.sum(previous * edges, axis=1) / norms, -1, 1)))
    skew = float(np.max(np.abs(angles - 90))) if len(points) == 4 else 0.0
    return float(np.min(sines)), float(max(lengths) / min(lengths)), skew


def _limit_check(check_id: str, value: float, table: Mapping, key: str, unit: str = "") -> dict:
    if key in table:
        return _check(check_id, value, float(table[key]), unit=unit)
    return check_entry(check_id, "skipped", note=f"no {key} given; measured {value:.6g}", unit=unit)


def _quality(mesh: Mesh, transition: set[str], quality: Mapping[str, Any]) -> list[dict]:
    degenerate, aspect, skew = 0, 0.0, 0.0
    for cell, name in zip(mesh.cells, mesh.components, strict=True):
        sine, ratio, angle = _corner_measures(mesh.xyz[list(cell)])
        degenerate += int(sine < DEGENERATE_SINE)
        if name not in transition and len(cell) == 4:
            aspect, skew = max(aspect, ratio), max(skew, angle)
    return [
        _check("mesh.degenerate", degenerate),
        _limit_check("mesh.quality.aspect", aspect, quality, "max_aspect"),
        _limit_check("mesh.quality.skew", skew, quality, "max_skew_deg", "deg"),
    ]


def _triangle_checks(mesh: Mesh, limits: Mapping[str, Mapping]) -> list[dict]:
    """Triangles only in transition components, each under its stated fraction."""
    totals: dict[str, list[int]] = {}
    for cell, name in zip(mesh.cells, mesh.components, strict=True):
        counts = totals.setdefault(name, [0, 0])
        counts[0] += int(len(cell) == 3)
        counts[1] += 1
    outside = {n: c[0] for n, c in totals.items() if n not in limits and c[0]}
    checks = [
        _check("mesh.triangles.region", sum(outside.values()), where={"by_component": outside})
    ]
    for name, table in sorted(limits.items()):
        if name in totals:
            fraction = totals[name][0] / totals[name][1]
            entry = _limit_check(
                "mesh.triangles.fraction", fraction, table, "max_triangle_fraction"
            )
            entry["where"] = {"component": name}
            checks.append(entry)
    return checks


def _irregular_nodes(mesh: Mesh, transition: set[str]) -> dict:
    """Count interior nodes of one structured surface whose valence is not four."""
    boundary: set[int] = set()
    for edge, cells in edge_uses(mesh).items():
        if len(cells) == 1 or len({mesh.surfaces[c] for c in cells}) != 1:
            boundary.update(edge)
    incident: dict[int, list[int]] = {}
    for index, cell in enumerate(mesh.cells):
        for v in cell:
            incident.setdefault(v, []).append(index)
    irregular = sum(
        1
        for node, cells in incident.items()
        if node not in boundary
        and not any(mesh.components[c] in transition for c in cells)
        and len(cells) != 4
    )
    return _check("mesh.irregular_nodes", irregular)


def _topology(mesh: Mesh) -> list[dict]:
    uses = edge_uses(mesh)
    over = sum(1 for cells in uses.values() if len(cells) > 2)
    free = sum(1 for e, cells in uses.items() if len(cells) == 1 and not _on_symmetry(mesh, e))
    return [
        _check("mesh.node_to_node", over),
        _check("mesh.free_edges", free, where={"tolerance_m": SYMMETRY_TOLERANCE_M}),
    ]


def acceptance_checks(
    mesh: Mesh, record: Mapping[str, Any], controls: Mapping[str, Any], transition: Mapping
) -> list[dict]:
    """Measure the strategy 1 acceptance table of the surface-mesh design on a realized mesh.

    ``record`` is the kernel record (inverted cells, source distance, spacing rules);
    ``transition`` maps each transition component to its transition table. Every other check
    is measured here on the cells and nodes, independently of the requested controls.
    """
    names = set(transition)
    checks = [_check("mesh.inverted", int(record["inverted_count"]))]
    checks += _quality(mesh, names, controls.get("defaults", {}).get("quality", {}))
    checks += _topology(mesh)
    checks += _triangle_checks(mesh, transition)
    checks.append(_irregular_nodes(mesh, names))
    failures = record.get("spacing_rules", {}).get("failures", [None])
    checks.append(_check("mesh.spacing_laws", len(failures)))
    checks.append(
        _check(
            "mesh.source_distance",
            float(record["source_distance_max_m"]),
            float(record["source_distance_tolerance_m"]),
            unit="m",
        )
    )
    return checks + follower_checks(mesh, controls)
