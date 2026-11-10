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
    points = np.asarray(xyz)[np.asarray(node_ids, dtype=int)]
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
