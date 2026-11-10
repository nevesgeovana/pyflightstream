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
