"""Read the native FEPolygon export without inventing nodal values from panel data.

Only the BLOCK layout measured in RPT-074 is accepted, one zone per file or
one zone per periodic copy (below). Native coordinates are in REFERENCE.
:func:`attach_native_strength` matches two surfaces already in one frame; the
translation of a VTK written in a loads frame carries the native INTO that
frame instead and matches there (``_strength_in_loads_frame`` in
:mod:`pyflightstream.results.surface`), so the rounding of the written VTK is
allowed along the axes it was written in. Matching includes connectivity, not
just equal node counts.

ONE ZONE PER PERIODIC COPY (0.30.0). A row under ``SYMMETRY PERIODIC`` writes
its native Tecplot as one zone per copy, each zone a complete file of its own
(``TITLE``, ``VARIABLES``, ``ZONE``, payload), the modelled sector first and
then its images turned about the axis, measured on 26.124 (reports/RPT-087,
a six-copy sector, 2026-09-28: six zones of 5961 nodes, zone k equal to the k-th block of the VTK
to 1e-13 m). The VTK route already carries the images after the real surface
(RPT-080), so the reading chosen is the VTK's: zone k joins the k-th copy of
the VTK, the real surface first, then the images. Each copy is matched on its
own, because the copies of a sector share the nodes of their seams (378
coincident positions on that sector) and one match over the whole disc would
be ambiguous there. The zone count is the copy count the row declared, and a
file holding any other count is refused naming both.
"""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter, defaultdict, deque
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np

from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
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


class _Tokens:
    """The whitespace-separated words of a stream of lines, one line at a time.

    A zone's payload is read by count, and the next zone's header is read by
    line, so what is left of the line a payload ended on is kept here and asked
    for (:meth:`leftover`) rather than lost inside a generator.
    """

    def __init__(self, lines: Iterator[str]) -> None:
        self._lines = lines
        self._pending: deque[str] = deque()

    def __iter__(self) -> _Tokens:
        return self

    def __next__(self) -> str:
        while not self._pending:
            self._pending.extend(next(self._lines).split())
        return self._pending.popleft()

    def leftover(self) -> bool:
        """Whether the line the last word came from holds more words."""
        return bool(self._pending)


def _variable_names(header: str) -> list[str]:
    var_text = re.split(r"\bVARIABLES\s*=", header, maxsplit=1, flags=re.I)[1]
    # Auxdata after VARIABLES is not a native variable declaration.
    var_text = re.split(r"\bDATASETAUXDATA\b", var_text, maxsplit=1, flags=re.I)[0]
    return re.findall(r'"([^"]+)"', var_text)


def _read_zone(zone: str, names: list[str], tokens: _Tokens, size: int) -> VtkSurface:
    """Read and validate one zone's payload, whose header line is ``zone``."""
    if not re.search(r"\bDATAPACKING\s*=\s*BLOCK\b", zone, re.I) or not re.search(
        r"\bZONETYPE\s*=\s*FEPOLYGON\b", zone, re.I
    ):
        raise MalformedOutputError("Native Tecplot requires FEPolygon BLOCK layout")
    if _count(zone, "NumConnectedBoundaryFaces", allow_zero=True) or _count(
        zone, "TotalNumBoundaryConnections", allow_zero=True
    ):
        raise MalformedOutputError("Native Tecplot connected boundary faces are unsupported")
    nodes, elements, faces = (_count(zone, key) for key in ("NODES", "ELEMENTS", "FACES"))
    if nodes * len(names) + 4 * faces > size:
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
                    raise MalformedOutputError("Native Tecplot variable location index is invalid")
                cell_variables.update(range(lo, hi + 1))
    for key in ("X", "Y", "Z", _STRENGTH):
        if names.index(key) + 1 in cell_variables:
            raise MalformedOutputError(f"Native Tecplot {key} must be nodal")
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
    if tokens.leftover():
        raise MalformedOutputError("Native Tecplot has trailing data after a zone's payload")
    offsets, connectivity = _rings(edges, left, right, elements, nodes)
    return VtkSurface(
        points=np.column_stack([values[k] for k in ("X", "Y", "Z")]),
        offsets=offsets,
        connectivity=connectivity,
        point_data={_STRENGTH: values[_STRENGTH]},
        title="Native FlightStream",
    )


def _zones_left(lines: Iterator[str]) -> int:
    """Count the zone headers among the lines not read, to name them in a refusal."""
    return sum(1 for line in lines if line.lstrip().upper().startswith("ZONE "))


def read_native_tecplot_zones(source: str | Path, *, zones: int = 1) -> list[VtkSurface]:
    """Read the ``zones`` zones of a native export, in file order; validate all blocks.

    Parameters
    ----------
    source : str or pathlib.Path
        The native Tecplot export (``<stem>_native_tecplot.dat``).
    zones : int, optional
        The zones the file must hold: 1, or the copy count of a row under
        ``SYMMETRY PERIODIC``, whose native export writes one zone per copy,
        the modelled sector first. A zone may restate ``TITLE`` and
        ``VARIABLES`` before its ``ZONE`` line, as the solver writes it; a
        restated variable list must be the first zone's.

    Returns
    -------
    list of VtkSurface
        One surface per zone, in file order, each carrying its nodal
        ``Singularity_strength``.

    Raises
    ------
    MalformedOutputError
        If the file holds another number of zones than ``zones`` (both counts
        are named), or if any zone is not the measured BLOCK FEPolygon layout.
    IncompleteOutputError
        If the file ends inside a zone.
    """
    if isinstance(zones, bool) or not isinstance(zones, int) or zones < 1:
        raise MalformedOutputError(
            f"Native Tecplot zone count must be a whole positive number, got {zones!r}"
        )
    path = Path(source)
    size = path.stat().st_size
    surfaces: list[VtkSurface] = []
    names: list[str] = []
    with path.open(encoding="utf-8-sig") as stream:
        lines = iter(stream)
        tokens = _Tokens(lines)
        while len(surfaces) < zones:
            header: list[str] = []
            zone = ""
            for line in lines:
                if line.lstrip().upper().startswith("ZONE "):
                    zone = line.strip()
                    break
                header.append(line)
            if not zone:
                if not surfaces:
                    raise IncompleteOutputError("Native Tecplot ends before its ZONE")
                raise MalformedOutputError(
                    f"Native Tecplot holds {len(surfaces)} zone(s) and {zones} were expected, "
                    f"one per periodic copy the row declares: {path.name}"
                )
            before = "".join(header)
            if "VARIABLES" in before.upper():
                stated = _variable_names(before)
                if names and stated != names:
                    raise MalformedOutputError(
                        f"Native Tecplot zone {len(surfaces) + 1} declares other VARIABLES "
                        "than zone 1"
                    )
                names = stated
            elif not names:
                raise MalformedOutputError("Native Tecplot declares no VARIABLES")
            if len(names) != len(set(names)) or not {"X", "Y", "Z", _STRENGTH}.issubset(names):
                raise MalformedOutputError(
                    "Native Tecplot needs unique XYZ and Singularity_strength"
                )
            surfaces.append(_read_zone(zone, names, tokens, size))
        trailing, extra = False, 0
        for line in lines:
            if line.strip():
                trailing = True
                extra = int(line.lstrip().upper().startswith("ZONE ")) + _zones_left(lines)
                break
        if trailing:
            if extra:
                raise MalformedOutputError(
                    f"Native Tecplot holds {zones + extra} zones and {zones} "
                    f"{'was' if zones == 1 else 'were'} expected"
                    + (
                        ": a row under SYMMETRY PERIODIC writes one zone per copy and "
                        "states its copy count, and a row under any other symmetry one zone"
                        if zones == 1
                        else ", one per periodic copy the row declares"
                    )
                )
            raise MalformedOutputError("Native Tecplot has trailing data after its last zone")
    return surfaces


def read_native_tecplot_surface(source: str | Path) -> VtkSurface:
    """Read measured native nodal strength and its geometry; validate all blocks.

    Non-strength result variables are validated and discarded: the caller keeps
    the VTK's original cell values rather than replacing them with native nodal
    interpolation. A second zone, connected boundaries and cell-centred
    strength are refused; the zones of a periodic row are read by
    :func:`read_native_tecplot_zones`.

    Parameters
    ----------
    source : str or pathlib.Path
        The native Tecplot export (``<stem>_native_tecplot.dat``).

    Returns
    -------
    VtkSurface
        The single zone, carrying its nodal ``Singularity_strength``.

    Raises
    ------
    MalformedOutputError
        If the file holds another number of zones than one, or is not the
        measured BLOCK FEPolygon layout.
    IncompleteOutputError
        If the file ends inside the zone.
    """
    return read_native_tecplot_zones(source, zones=1)[0]


def native_match_tolerance(points: np.ndarray, *, printed_digits: int | None = None) -> np.ndarray:
    """Return the per-axis match tolerance :func:`attach_native_strength` takes by default.

    THE ONE HOME of the rule (0.29.1-tol): the whole-surface match, the
    periodic-copy match and the time-averaged native strength all resolve it
    here. Per axis it is the largest of 1e-10, 1e-6 of the geometry's diagonal
    extent, and four single-precision epsilons of the largest coordinate
    magnitude (a VTK written at single precision rounds with the magnitude).

    A native far from the origin also carries the rounding of its own
    printing. When the caller states ``printed_digits``, the significant
    digits the native was printed at (:func:`native_printed_digits`), a fourth
    term joins: half a unit of the last printed digit, ``0.5 * 10**(1 -
    printed_digits)`` of the magnitude, plus half a single-precision spacing.
    Absent, the rule is the one it always was, and a native printed at full
    precision (the measured 26.124 export prints sixteen digits) adds nothing.

    Parameters
    ----------
    points : numpy.ndarray
        The native nodes, one row each, in the length unit of the match.
    printed_digits : int, optional
        Significant digits the native prints its coordinates at.

    Returns
    -------
    numpy.ndarray
        Three limits, along X, Y and Z, in the unit of ``points``.

    Raises
    ------
    MalformedOutputError
        If ``printed_digits`` is not a whole number or is below 1.
    """
    measurable = bool(len(points)) and bool(np.isfinite(points).all())
    extent = float(np.linalg.norm(np.ptp(points, axis=0))) if measurable else 0.0
    magnitude = np.abs(points).max(axis=0) if measurable else np.zeros(3)
    rounding = 4.0 * float(np.finfo(np.float32).eps) * magnitude
    if printed_digits is not None:
        if isinstance(printed_digits, bool) or not isinstance(printed_digits, int):
            raise MalformedOutputError(
                f"Printed significant digits must be a whole number, got {printed_digits!r}"
            )
        if printed_digits < 1:
            raise MalformedOutputError(
                f"Printed significant digits must be at least 1, got {printed_digits}"
            )
        relative = 0.5 * 10.0 ** (1 - printed_digits) + 0.5 * float(np.finfo(np.float32).eps)
        rounding = np.maximum(rounding, relative * magnitude)
    return np.maximum(max(1e-10, extent * 1e-6), rounding)


def _significant_digits(token: str) -> int:
    """Return the significant digits one printed number carries (at least 1)."""
    mantissa = re.split(r"[eEdD]", token.lstrip("+-"), maxsplit=1)[0]
    digits = mantissa.replace(".", "").lstrip("0")
    if "." not in mantissa:
        # A whole number's trailing zeros are place holders, not printed digits.
        digits = digits.rstrip("0")
    return max(1, len(digits))


#: Fewer significant digits than this, at most, are exact short numbers and not a
#: print precision (see :func:`native_printed_digits`).
_MIN_PRINTED_DIGITS = 4


def native_printed_digits(source: str | Path) -> int | None:
    """Return the significant digits a native export printed its coordinates at.

    The most any coordinate of the first zone shows, which is the printing
    precision because a number printed at ``d`` digits shows ``d`` unless its
    tail is zeros. None when the file's first zone cannot be read that way, in
    which case the caller states nothing and the default rule stands. A count
    under :data:`_MIN_PRINTED_DIGITS` is a file of short exact numbers (whole
    coordinates, say), not a print precision: read as one it would grant half
    the coordinate as slack, so it also states nothing.

    Parameters
    ----------
    source : str or pathlib.Path
        The native Tecplot export to read.

    Returns
    -------
    int or None
        The significant digits, or None when the file states none.
    """
    try:
        with Path(source).open(encoding="utf-8-sig") as stream:
            nodes = 0
            for line in stream:
                found = re.search(r"NODES\s*=\s*(\d+)", line, re.IGNORECASE)
                if line.lstrip().upper().startswith("ZONE ") and found:
                    nodes = int(found.group(1))
                    break
            if not nodes:
                return None
            best, seen = 0, 0
            for line in stream:
                for token in line.split():
                    best = max(best, _significant_digits(token))
                    seen += 1
                    if seen >= 3 * nodes:
                        return best if best >= _MIN_PRINTED_DIGITS else None
    except (OSError, ValueError):
        return None
    return None


def _copy_of(surface: VtkSurface, nodes: tuple[int, int], cells: tuple[int, int]) -> VtkSurface:
    """Return the nodes ``[nodes)`` and polygons ``[cells)`` of ``surface``, renumbered."""
    first, stop = cells
    offsets = surface.offsets[first : stop + 1]
    connectivity = surface.connectivity[offsets[0] : offsets[-1]]
    if connectivity.size and (connectivity.min() < nodes[0] or connectivity.max() >= nodes[1]):
        raise MalformedOutputError(
            "the VTK's periodic copies are not separable: a polygon of one copy joins "
            "nodes of another, so no copy can be matched to its native zone"
        )
    return VtkSurface(
        points=surface.points[nodes[0] : nodes[1]],
        offsets=offsets - offsets[0],
        connectivity=connectivity - nodes[0],
        point_data={
            name: values[nodes[0] : nodes[1]] for name, values in surface.point_data.items()
        },
        title=surface.title,
    )


def attach_native_strength_by_copy(
    surface: VtkSurface,
    zones: Sequence[VtkSurface],
    *,
    coordinate_tolerance: float | np.ndarray | None = None,
) -> tuple[VtkSurface, dict[str, object]]:
    """Attach the strength of one native zone per periodic copy, copy by copy.

    ``surface`` is the whole VTK, the modelled sector first and its images
    after it (RPT-080); ``zones`` are the native zones in file order, in the
    SAME frame as ``surface``: the reference frame for a caller holding two
    reference surfaces, the loads frame when the translation carries the
    native into the frame the VTK was written in
    (``_strength_in_loads_frame`` in :mod:`pyflightstream.results.surface`).
    Zone k is joined to the k-th copy of the VTK, of the zone's own node and
    polygon counts, by :func:`attach_native_strength`, so each copy
    keeps the unique coordinate and topology match. With one zone this is
    :func:`attach_native_strength` itself, record and all. The tolerance is
    resolved once, from every zone's nodes together, when none is given.

    Parameters
    ----------
    surface : VtkSurface
        The whole VTK surface, the modelled sector first and its images after.
    zones : sequence of VtkSurface
        The native zones in file order, in the same frame as ``surface``.
    coordinate_tolerance : float or numpy.ndarray, optional
        Absolute match tolerance in the surfaces' length unit, a scalar or an
        X, Y, Z array. When None it is resolved from every zone's nodes by
        :func:`native_match_tolerance`.

    Returns
    -------
    tuple of (VtkSurface, dict)
        ``surface`` with the native nodal strength attached, and the record of
        the node mapping.

    Raises
    ------
    MalformedOutputError
        If there is no zone, the zones' node and polygon counts do not add up
        to the VTK's, or a copy cannot be matched uniquely.
    """
    if len(zones) == 1:
        return attach_native_strength(surface, zones[0], coordinate_tolerance=coordinate_tolerance)
    if not zones:
        raise MalformedOutputError("No native zone to join")
    points = sum(zone.n_points for zone in zones)
    cells = sum(zone.n_cells for zone in zones)
    if surface.n_points != points or surface.n_cells != cells:
        raise MalformedOutputError(
            f"Native/VTK counts cannot form a bijection: {len(zones)} native zones hold "
            f"{points} nodes and {cells} polygons, the VTK {surface.n_points} and "
            f"{surface.n_cells}"
        )
    if coordinate_tolerance is None:
        coordinate_tolerance = native_match_tolerance(np.vstack([zone.points for zone in zones]))
    strengths: list[np.ndarray] = []
    copies: list[dict[str, object]] = []
    node, cell = 0, 0
    for zone in zones:
        piece = _copy_of(surface, (node, node + zone.n_points), (cell, cell + zone.n_cells))
        joined, mapping = attach_native_strength(
            piece, zone, coordinate_tolerance=coordinate_tolerance
        )
        strengths.append(joined.point_data[_STRENGTH])
        copies.append(mapping)
        node += zone.n_points
        cell += zone.n_cells
    data = dict(surface.point_data)
    data[_STRENGTH] = np.concatenate(strengths)
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
        # One tolerance for every copy, as each copy's own record states it.
        "coordinate_tolerance": copies[0]["coordinate_tolerance"],
        "coordinate_tolerance_by_axis": copies[0]["coordinate_tolerance_by_axis"],
        "method": (
            "one native zone per periodic copy, zone k joined to the k-th copy of the VTK "
            "(the modelled surface first, then its images); unique coordinates plus "
            "polygon-edge incidence within each copy; no interpolation"
        ),
        "periodic_copies": len(zones),
    }


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
    coordinate magnitude along that axis (:func:`native_match_tolerance`, the
    one home of the rule): a VTK written at single precision
    rounds with the coordinates' magnitude, which for a small part far from
    the origin exceeds any fraction of its extent. Ambiguous coincident
    vertices are refused; this function never averages, guesses orientation,
    or derives a strength from Cp. The resolved limits are returned in the
    mapping record as ``coordinate_tolerance_by_axis`` ([X, Y, Z], in the
    input length unit); ``coordinate_tolerance`` is their maximum.

    Parameters
    ----------
    surface : VtkSurface
        The VTK surface whose nodes receive the strength.
    native : VtkSurface
        The native surface carrying nodal ``Singularity_strength``, in the
        same frame and length unit as ``surface``.
    coordinate_tolerance : float or numpy.ndarray, optional
        Absolute match tolerance, a scalar or an X, Y, Z array in the
        surfaces' length unit. When None it is :func:`native_match_tolerance`.

    Returns
    -------
    tuple of (VtkSurface, dict)
        ``surface`` with ``Singularity_strength`` attached as point data, and
        the mapping record, including ``coordinate_tolerance_by_axis``.

    Raises
    ------
    MalformedOutputError
        If the tolerance is not a positive finite scalar or XYZ array, the
        counts do not form a bijection, the native strength is missing or
        mis-sized, a coordinate is not finite, or the match is not unique.
    """
    if coordinate_tolerance is None:
        coordinate_tolerance = native_match_tolerance(native.points)
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
