"""Read the native FEPolygon export without inventing nodal values from panel data.

Only the single-zone BLOCK layout measured in RPT-074 is accepted. Native
coordinates are in REFERENCE. :func:`attach_native_strength` matches two
surfaces already in one frame; the translation of a VTK written in a loads
frame carries the native INTO that frame instead and matches there
(:mod:`pyflightstream.results._native_frame`), so the rounding of the written
VTK is allowed along the axes it was written in. Matching includes connectivity, not
just equal node counts.
"""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from pyflightstream.results import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.surface import VtkSurface

_STRENGTH = "Singularity_strength"


def _values(tokens: Iterator[str], count: int, *, integer: bool, label: str) -> np.ndarray:
    """Consume one bounded block, refusing truncation and nonfinite values."""
    try:
        cast = int if integer else float
        result = np.fromiter(
            (cast(next(tokens)) for _ in range(count)),
            dtype=np.int64 if integer else float,
            count=count,
        )
    except (StopIteration, RuntimeError) as error:
        raise IncompleteOutputError(f"Native Tecplot ends inside {label}") from error
    except (ValueError, OverflowError) as error:
        raise MalformedOutputError(f"Native Tecplot {label} contains invalid values") from error
    if not np.isfinite(result).all():
        raise MalformedOutputError(f"Native Tecplot {label} must be finite")
    return result


def _count(zone: str, name: str, *, allow_zero: bool = False) -> int:
    match = re.search(r"\b" + name + r"\s*=\s*([^,\s]+)", zone, re.I)
    if not match:
        raise MalformedOutputError(f"Native Tecplot declares no {name}")
    token = match.group(1)
    if re.fullmatch(r"[0-9]+", token) is None:
        raise MalformedOutputError(f"Native Tecplot {name} has invalid count {token!r}")
    count = int(token)
    if count < (0 if allow_zero else 1):
        raise MalformedOutputError(f"Native Tecplot {name} has invalid count {count}")
    return count


def _rings(
    edges: np.ndarray, left: np.ndarray, right: np.ndarray, elements: int, nodes: int
) -> tuple[np.ndarray, np.ndarray]:
    if np.any(edges < 1) or np.any(edges > nodes):
        raise MalformedOutputError("Native Tecplot face names an invalid node")
    if np.any(left < 0) or np.any(right < 0) or np.any(left > elements) or np.any(right > elements):
        raise MalformedOutputError("Native Tecplot face names an invalid element")
    adjacency: list[list[tuple[int, int]]] = [[] for _ in range(elements)]
    for (a, b), lft, rgt in zip(edges, left, right, strict=True):
        if a == b or lft == rgt:
            raise MalformedOutputError("Native Tecplot face has degenerate incidence")
        if lft:
            adjacency[int(lft) - 1].append((int(a) - 1, int(b) - 1))
        if rgt:
            adjacency[int(rgt) - 1].append((int(b) - 1, int(a) - 1))
    offsets = [0]
    connectivity: list[int] = []
    for cell, pairs in enumerate(adjacency):
        following = dict(pairs)
        if len(pairs) < 3 or len(following) != len(pairs):
            raise MalformedOutputError(
                f"Native Tecplot topology of element {cell + 1} is not a ring"
            )
        first = min(following)
        ring = []
        current = first
        while current not in ring:
            ring.append(current)
            if current not in following:
                raise MalformedOutputError(f"Native Tecplot topology of element {cell + 1} is open")
            current = following[current]
        if current != first or len(ring) != len(pairs):
            raise MalformedOutputError(
                f"Native Tecplot topology of element {cell + 1} is disconnected"
            )
        connectivity.extend(ring)
        offsets.append(len(connectivity))
    return np.asarray(offsets, dtype=np.int64), np.asarray(connectivity, dtype=np.int64)


def read_native_tecplot_surface(source: str | Path) -> VtkSurface:
    """Read measured native nodal strength and its geometry; validate all blocks.

    Non-strength result variables are validated and discarded: the caller keeps
    the VTK's original cell values rather than replacing them with native nodal
    interpolation. Extra zones, connected boundaries and cell-centred strength
    are explicitly unsupported.
    """
    path = Path(source)
    with path.open(encoding="utf-8-sig") as stream:
        header = []
        zone = ""
        for line in stream:
            if line.lstrip().upper().startswith("ZONE "):
                zone = line.strip()
                break
            header.append(line)
        if not zone:
            raise IncompleteOutputError("Native Tecplot ends before its ZONE")
        if not re.search(r"\bDATAPACKING\s*=\s*BLOCK\b", zone, re.I) or not re.search(
            r"\bZONETYPE\s*=\s*FEPOLYGON\b", zone, re.I
        ):
            raise MalformedOutputError("Native Tecplot requires FEPolygon BLOCK layout")
        if _count(zone, "NumConnectedBoundaryFaces", allow_zero=True) or _count(
            zone, "TotalNumBoundaryConnections", allow_zero=True
        ):
            raise MalformedOutputError("Native Tecplot connected boundary faces are unsupported")
        before = "".join(header)
        if "VARIABLES" not in before.upper():
            raise MalformedOutputError("Native Tecplot declares no VARIABLES")
        var_text = re.split(r"\bVARIABLES\s*=", before, maxsplit=1, flags=re.I)[1]
        # Auxdata after VARIABLES is not a native variable declaration.
        var_text = re.split(r"\bDATASETAUXDATA\b", var_text, maxsplit=1, flags=re.I)[0]
        names = re.findall(r'"([^"]+)"', var_text)
        if len(names) != len(set(names)) or not {"X", "Y", "Z", _STRENGTH}.issubset(names):
            raise MalformedOutputError("Native Tecplot needs unique XYZ and Singularity_strength")
        nodes, elements, faces = (_count(zone, key) for key in ("NODES", "ELEMENTS", "FACES"))
        if nodes * len(names) + 4 * faces > path.stat().st_size:
            raise IncompleteOutputError(
                "Native Tecplot ends before the payload required by its declared counts"
            )
        cell_variables: set[int] = set()
        var_location = re.search(r"VARLOCATION\s*=\s*\(([^)]*)\)", zone, re.I)
        if var_location:
            parts = re.findall(r"\[([\d,\-]+)\]\s*=\s*CELLCENTERED", var_location.group(1), re.I)
            if not parts:
                raise MalformedOutputError("Native Tecplot variable location is unsupported")
            for part in parts:
                for token in part.split(","):
                    bounds = token.split("-")
                    lo, hi = int(bounds[0]), int(bounds[-1])
                    if not 1 <= lo <= hi <= len(names):
                        raise MalformedOutputError(
                            "Native Tecplot variable location index is invalid"
                        )
                    cell_variables.update(range(lo, hi + 1))
        for key in ("X", "Y", "Z", _STRENGTH):
            if names.index(key) + 1 in cell_variables:
                raise MalformedOutputError(f"Native Tecplot {key} must be nodal")
        tokens = (word for line in stream for word in line.split())
        values = {}
        for index, name in enumerate(names, 1):
            array = _values(
                tokens, elements if index in cell_variables else nodes, integer=False, label=name
            )
            if name in {"X", "Y", "Z", _STRENGTH}:
                values[name] = array
        edges = _values(tokens, 2 * faces, integer=True, label="face nodes").reshape(faces, 2)
        left = _values(tokens, faces, integer=True, label="left elements")
        right = _values(tokens, faces, integer=True, label="right elements")
        if next(tokens, None) is not None:
            raise MalformedOutputError("Native Tecplot has trailing data or multiple zones")
    offsets, connectivity = _rings(edges, left, right, elements, nodes)
    return VtkSurface(
        points=np.column_stack([values[k] for k in ("X", "Y", "Z")]),
        offsets=offsets,
        connectivity=connectivity,
        point_data={_STRENGTH: values[_STRENGTH]},
        title="Native FlightStream",
    )


def _topology(surface: VtkSurface, mapping: np.ndarray | None = None) -> Counter:
    rings = []
    for cell in range(surface.n_cells):
        ring = surface.connectivity[surface.offsets[cell] : surface.offsets[cell + 1]]
        if mapping is not None:
            ring = mapping[ring]
        edges = [
            tuple(sorted((int(a), int(b)))) for a, b in zip(ring, np.roll(ring, -1), strict=True)
        ]
        rings.append(tuple(sorted(edges)))
    return Counter(rings)


def attach_native_strength(
    surface: VtkSurface,
    native: VtkSurface,
    *,
    coordinate_tolerance: float | np.ndarray | None = None,
) -> tuple[VtkSurface, dict[str, object]]:
    """Attach exact native strength after a unique coordinate/topology match.

    Both surfaces must already be in one frame and one length unit; the axes
    below are that frame's, the reference frame's for a caller holding
    reference geometry. An explicit tolerance is absolute, in that unit: a
    scalar, or a three-element array giving the tolerance along X, Y and Z, so
    a rounding that is large along one axis is not granted along the others
    (GOAL-034 Q8 CXQ8R4-1); any other shape is refused. By default it is, per
    axis, the larger of max(1e-10, 1e-6 of the native geometry's diagonal
    extent) and four single-precision epsilons of the largest native
    coordinate magnitude along that axis: a VTK written at single precision
    rounds with the coordinates' magnitude, which for a small part far from
    the origin exceeds any fraction of its extent. Ambiguous coincident
    vertices are refused; this function never averages, guesses orientation,
    or derives a strength from Cp. The resolved limits are returned in the
    mapping record as ``coordinate_tolerance_by_axis`` ([X, Y, Z], in the
    input length unit); ``coordinate_tolerance`` is their maximum.
    """
    if coordinate_tolerance is None:
        measurable = bool(native.n_points) and bool(np.isfinite(native.points).all())
        extent = float(np.linalg.norm(np.ptp(native.points, axis=0))) if measurable else 0.0
        magnitude = np.abs(native.points).max(axis=0) if measurable else np.zeros(3)
        rounding = 4.0 * float(np.finfo(np.float32).eps) * magnitude
        coordinate_tolerance = np.maximum(max(1e-10, extent * 1e-6), rounding)
    try:
        limits = np.broadcast_to(np.asarray(coordinate_tolerance, dtype=float), (3,)).copy()
    except ValueError as error:
        raise MalformedOutputError(
            "Native coordinate matching tolerance must be a scalar or an XYZ array"
        ) from error
    if not np.isfinite(limits).all() or np.any(limits <= 0):
        raise MalformedOutputError(
            "Native coordinate matching tolerance must be positive and finite"
        )
    if surface.n_points != native.n_points or surface.n_cells != native.n_cells:
        raise MalformedOutputError("Native/VTK counts cannot form a bijection")
    if _STRENGTH not in native.point_data or len(native.point_data[_STRENGTH]) != native.n_points:
        raise MalformedOutputError("Native nodal strength is missing or has inconsistent size")
    if not np.isfinite(surface.points).all() or not np.isfinite(native.points).all():
        raise MalformedOutputError("Native/VTK coordinates must be finite")
    bins: dict[tuple[int, ...], list[int]] = defaultdict(list)

    def key(point: np.ndarray) -> tuple[int, ...]:
        try:
            return tuple(
                math.floor(float(x) / float(limit)) for x, limit in zip(point, limits, strict=True)
            )
        except (OverflowError, ValueError) as error:
            raise MalformedOutputError(
                "Coordinates cannot be resolved at the requested tolerance"
            ) from error

    for index, point in enumerate(native.points):
        bins[key(point)].append(index)
    mapping = []
    for point in surface.points:
        bucket = key(point)
        candidates: list[int] = []
        for delta in itertools.product((-1, 0, 1), repeat=3):
            nearby = tuple(a + b for a, b in zip(bucket, delta, strict=True))
            candidates.extend(
                i
                for i in bins.get(nearby, ())
                if np.all(np.abs(native.points[i] - point) <= limits)
            )
        if len(candidates) != 1:
            raise MalformedOutputError("Native/VTK coordinate match is missing or ambiguous")
        mapping.append(candidates[0])
    mapped = np.asarray(mapping, dtype=np.int64)
    if len(set(mapping)) != surface.n_points:
        raise MalformedOutputError("Native/VTK coordinate mapping is not a bijection")
    if _topology(surface, mapped) != _topology(native):
        raise MalformedOutputError("Native/VTK polygon topology differs after node matching")
    data = dict(surface.point_data)
    if _STRENGTH in data:
        raise MalformedOutputError("VTK already states nodal strength; two sources would compete")
    data[_STRENGTH] = native.point_data[_STRENGTH][mapped].copy()
    result = VtkSurface(
        points=surface.points,
        offsets=surface.offsets,
        connectivity=surface.connectivity,
        point_data=data,
        cell_data=dict(surface.cell_data),
        title=surface.title,
    )
    return result, {
        "matched_nodes": surface.n_points,
        "topology_verified": True,
        "coordinate_tolerance": float(limits.max()),
        "coordinate_tolerance_by_axis": limits.tolist(),
        "method": "unique coordinates plus polygon-edge incidence; no interpolation",
    }
