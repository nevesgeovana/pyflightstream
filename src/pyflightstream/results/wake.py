"""The reader of the solver's wake export, ``<name>_wakes.vtk`` (FR-1023).

Pipeline role: parses the wake lines the surface VTK export writes beside the
surface when ``SET_VTK_EXPORT_VARIABLES`` states the wake: VTK legacy ASCII
polydata of POINTS, two-point LINES and one cell scalar,
``Normalized_Vorticity``. The segments chain into one wake line per
trailing-edge node, each line carrying one value, constant along it; the value
is read as the circulation shed by that wake line (FR-1023; the reading is
not measured in a committed solver report). Trefftz B of
the far-field family reads it (:mod:`pyflightstream.farfield.trefftz`).

A rotor's wake is written as a vortex lattice per blade (26.125): trailing
filaments of one node per time step, joined in every row but the trailing-edge
row by shed segments that carry the mean of the trailing values beside them, so
an interior node joins four segments. Such a component is read as one line per
trailing filament, from its trailing-edge node downstream, valued by its
segment at the trailing edge; the shed segments are dropped. Components without
a node of more than two segments are read as lines, as above.

Refused, as every reader refuses (FR-16, FR-17): a file whose counts do not add
up, a file that ends inside a block it declared, polygons (a surface is not a
wake), a segment that is not two points, a chain that branches or closes, and a
value that changes along one line. Empty polygon blocks and the exported
point-coordinate scalars are accepted; connected node indices preserve both
mirror halves and collapsed lines.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import islice

import numpy as np

from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError

__all__ = ["WAKE_VALUE", "WakeExport", "parse_wake_export"]

#: The cell scalar of the wake export that carries each line's value.
WAKE_VALUE = "Normalized_Vorticity"

#: How far two segments of one line may differ in value and still be one
#: value: relative to the largest magnitude of the file, the round-off of its
#: printed digits.
_CONSTANT_RTOL = 1e-6


@dataclass(frozen=True, eq=False)
class WakeExport:
    """The wake lines of one export.

    Attributes
    ----------
    lines : tuple of numpy.ndarray
        One ``(n_k, 3)`` array of node coordinates per wake line, ordered from
        the node with the smallest x (the trailing edge, x aft in the export
        frame) downstream; a lattice filament runs from its trailing-edge node.
    values : numpy.ndarray
        One value per line, :data:`WAKE_VALUE`, in the sign of the line reading:
        the line is a filament of strength ``-value`` from its first node.
    blades : numpy.ndarray or None
        The lattice (one blade's wake) each line belongs to, ``-1`` for a line
        read as a line; None when the export holds no lattice.
    """

    lines: tuple[np.ndarray, ...]
    values: np.ndarray
    blades: np.ndarray | None = None


def _tokens(rows: Iterator[str], count: int, what: str) -> list[str]:
    out: list[str] = []
    while len(out) < count:
        try:
            row = next(rows)
        except StopIteration:
            raise IncompleteOutputError(
                f"the wake export declares {count} value(s) for {what} and ends after "
                f"{len(out)}; it is truncated"
            ) from None
        out.extend(row.split())
    if len(out) != count:
        raise MalformedOutputError(
            f"the wake export's {what} block holds {len(out)} values where it declares {count}"
        )
    return out


def _required_line(rows: Iterator[str], what: str) -> str:
    """Read a required header line, distinguishing EOF from malformed content."""
    try:
        return next(rows)
    except StopIteration:
        raise IncompleteOutputError(
            f"the wake export ends before its {what}; it is truncated"
        ) from None


def _numbers(tokens: list[str], what: str, dtype: type) -> np.ndarray:
    try:
        array: np.ndarray = np.asarray(tokens, dtype=dtype)
    except (ValueError, OverflowError) as error:
        raise MalformedOutputError(
            f"the wake export's {what} holds a value that is no number"
        ) from error
    if array.dtype.kind == "f" and not bool(np.all(np.isfinite(array))):
        raise MalformedOutputError(
            f"the wake export's {what} holds a value that is not finite (nan or inf)"
        )
    return array


def _chains(segments: np.ndarray, n_points: int) -> list[list[int]]:
    """Chain two-point segments into lines; return each line as segment indices in order."""
    touching: dict[int, list[int]] = {}
    for index, (a, b) in enumerate(segments.tolist()):
        touching.setdefault(a, []).append(index)
        touching.setdefault(b, []).append(index)
    if any(len(cells) > 2 for cells in touching.values()):
        raise MalformedOutputError("a wake line branches: a node joins more than two segments")
    seen = np.zeros(len(segments), dtype=bool)
    chains: list[list[int]] = []
    for node, cells in touching.items():
        if len(cells) != 1 or seen[cells[0]]:
            continue
        chain: list[int] = []
        current_node, current = node, cells[0]
        while True:
            seen[current] = True
            chain.append(current)
            a, b = segments[current]
            current_node = int(b) if int(a) == current_node else int(a)
            following = [cell for cell in touching[current_node] if not seen[cell]]
            if not following:
                break
            current = following[0]
        chains.append(chain)
    if not seen.all():
        raise MalformedOutputError("a wake line closes on itself; a wake line has two ends")
    return chains


def parse_wake_export(text: str) -> WakeExport:
    r"""Read the wake lines of a ``<name>_wakes.vtk`` export.

    Parameters
    ----------
    text : str
        The file's text.

    Returns
    -------
    WakeExport
        The lines, each from its upstream end, and their values.

    Raises
    ------
    MalformedOutputError
        If the file is not ASCII polydata of two-point lines with the
        :data:`WAKE_VALUE` cell scalar, a count or an index contradicts the
        file, a chain branches or closes, or a value changes along one line.
    IncompleteOutputError
        If the file is empty or ends before a required header, block or value.

    Examples
    --------
    >>> text = (
    ...     "# vtk DataFile Version 3.0\nwakes\nASCII\nDATASET POLYDATA\n"
    ...     "POINTS 3 float\n0 0 0\n1 0 0\n2 0 0\nLINES 2 6\n2 0 1\n2 1 2\n"
    ...     "CELL_DATA 2\nSCALARS Normalized_Vorticity float 1\nLOOKUP_TABLE default\n"
    ...     "0.5\n0.5\n"
    ... )
    >>> wake = parse_wake_export(text)
    >>> len(wake.lines), wake.lines[0].shape, wake.values.tolist()
    (1, (3, 3), [0.5])
    """
    rows = iter(text.splitlines())
    head = [line.strip() for line in islice(rows, 4)]
    if not text.strip():
        raise IncompleteOutputError("the wake export's VTK header is truncated")
    if not head[0].lower().startswith("# vtk datafile"):
        raise MalformedOutputError("the wake export does not open with a VTK legacy header")
    if len(head) < 4:
        raise IncompleteOutputError("the wake export's VTK header is truncated")
    if head[2].upper() != "ASCII" or head[3].upper() != "DATASET POLYDATA":
        raise MalformedOutputError("the wake export is not ASCII POLYDATA")
    points, segments, values = _blocks(rows)
    if not bool(np.all(np.isfinite(values))) or not bool(np.all(np.isfinite(points))):
        raise MalformedOutputError(
            "the wake export holds a point or a value that is not finite (NaN or infinity); "
            "a NaN strength would pass the constancy check and feed the far-field products"
        )
    segments = _shared_nodes(points, segments, values)
    if len(segments) and np.bincount(segments.ravel()).max() > 2:
        return _mixed_export(points, segments, values)
    return _chain_export(points, segments, values)


def _chain_export(points: np.ndarray, segments: np.ndarray, values: np.ndarray) -> WakeExport:
    """Read independent wake lines, one value constant along each (the wing layout)."""
    lines: list[np.ndarray] = []
    line_values: list[float] = []
    for chain in _chains(segments, len(points)):
        chain_values = values[chain]
        # The tolerance is the line's own: a file-wide scale would let a weak
        # line change sign beside a strong one and report its first value.
        scale = float(np.max(np.abs(chain_values)))
        if np.any(np.abs(chain_values - chain_values[0]) > _CONSTANT_RTOL * scale):
            raise MalformedOutputError(
                f"the wake value changes along one line (from {chain_values.min()!r} to "
                f"{chain_values.max()!r}); a wake line carries one value"
            )
        lines.append(_ordered_nodes(points, segments, chain))
        line_values.append(float(chain_values[0]))
    return WakeExport(lines=tuple(lines), values=np.asarray(line_values))


def _read_points(rows: Iterator[str], words: list[str]) -> np.ndarray:
    count = _counts(words, 1)[0]
    return _numbers(_tokens(rows, 3 * count, "POINTS"), "POINTS", float).reshape(count, 3)


def _read_lines(rows: Iterator[str], words: list[str]) -> np.ndarray:
    cells, size = _counts(words, 2)
    if size != 3 * cells:
        raise MalformedOutputError(
            f"the wake export's LINES state {cells} segments in {size} values; a wake "
            "segment is two points, three values each"
        )
    flat = _numbers(_tokens(rows, size, "LINES"), "LINES", np.int64).reshape(cells, 3)
    if np.any(flat[:, 0] != 2):
        raise MalformedOutputError("a wake segment holds other than two points")
    return flat[:, 1:]


def _read_values(rows: Iterator[str], words: list[str], segments: np.ndarray | None) -> np.ndarray:
    count = _counts(words, 1)[0]
    if segments is None or count != len(segments):
        raise MalformedOutputError(
            f"the wake export declares CELL_DATA {words[1]} for "
            f"{0 if segments is None else len(segments)} segments"
        )
    scalar = _required_line(rows, "CELL_DATA SCALARS block").split()
    if len(scalar) < 3 or scalar[0].upper() != "SCALARS":
        raise MalformedOutputError("the wake export's CELL_DATA holds no SCALARS block")
    if scalar[1] != WAKE_VALUE:
        raise MalformedOutputError(
            f"the wake export's cell scalar is {scalar[1]!r}, not {WAKE_VALUE!r}"
        )
    if len(scalar) > 3 and scalar[3] != "1":
        raise MalformedOutputError(
            f"the wake export's {WAKE_VALUE} scalar states {scalar[3]} components; a wake "
            "line carries one value, so the block would be read at the wrong width"
        )
    table = next(rows, "").strip()
    tokens: list[str] = [] if table.upper().startswith("LOOKUP_TABLE") else table.split()
    tokens += _tokens(rows, len(segments) - len(tokens), WAKE_VALUE)
    return _numbers(tokens, WAKE_VALUE, float)


#: The blocks no wake export writes, each refused with the reason it is not a wake.
_REFUSED_BLOCKS = {
    "POLYGONS": "a wake export carries lines alone, and a file with polygons is a surface",
    "VERTICES": "a wake export carries lines alone",
    "TRIANGLE_STRIPS": "a wake export carries lines alone",
}


def _point_data(rows: Iterator[str], words: list[str], points: np.ndarray | None) -> None:
    """Consume the solver's redundant X, Y and Z point scalars, checking their counts."""
    count = _counts(words, 1)[0]
    if points is None or count != len(points):
        raise MalformedOutputError("the wake export's POINT_DATA count differs from POINTS")
    for name in ("X", "Y", "Z"):
        scalar = _required_line(rows, f"POINT_DATA {name} scalar").split()
        if len(scalar) < 3 or scalar[:2] != ["SCALARS", name]:
            raise MalformedOutputError(f"the wake export's POINT_DATA needs the {name} scalar")
        if len(scalar) > 3 and scalar[3] != "1":
            raise MalformedOutputError(f"the wake export's {name} scalar needs one component")
        if (
            not _required_line(rows, f"{name} scalar LOOKUP_TABLE")
            .strip()
            .upper()
            .startswith("LOOKUP_TABLE")
        ):
            raise MalformedOutputError(f"the wake export's {name} scalar needs LOOKUP_TABLE")
        _numbers(_tokens(rows, len(points), name), name, float)


def _counts(words: list[str], number: int) -> list[int]:
    """Validate a block's nonnegative integer counts before consuming its payload."""
    if len(words) < number + 1:
        raise IncompleteOutputError(
            f"the wake export's {words[0]} header is truncated; it needs {number} count(s)"
        )
    try:
        counts = [int(value) for value in words[1 : number + 1]]
    except ValueError as error:
        raise MalformedOutputError(
            f"the wake export's {words[0]} header needs nonnegative integer counts"
        ) from error
    if any(value < 0 for value in counts):
        raise MalformedOutputError(
            f"the wake export's {words[0]} header needs nonnegative integer counts"
        )
    return counts


def _blocks(rows: Iterator[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read the POINTS, LINES and CELL_DATA blocks; refuse every other."""
    points: np.ndarray | None = None
    segments: np.ndarray | None = None
    values: np.ndarray | None = None
    for raw in rows:
        words = raw.split()
        if not words:
            continue
        keyword = words[0].upper()
        if (
            (keyword == "POINTS" and points is not None)
            or (keyword == "LINES" and segments is not None)
            or (keyword == "CELL_DATA" and values is not None)
        ):
            raise MalformedOutputError(
                f"the wake export holds a second {keyword} block; the later one would "
                "silently replace the earlier and reassign its values to other geometry"
            )
        if keyword == "POINTS":
            points = _read_points(rows, words)
        elif keyword == "LINES":
            segments = _read_lines(rows, words)
        elif keyword == "CELL_DATA":
            values = _read_values(rows, words, segments)
        elif keyword == "POLYGONS" and words[1:] == ["0", "0"]:
            continue
        elif keyword == "POINT_DATA":
            _point_data(rows, words, points)
        elif keyword in _REFUSED_BLOCKS:
            raise MalformedOutputError(
                f"the wake export carries {keyword}; {_REFUSED_BLOCKS[keyword]}, not a wake"
            )
        else:
            raise MalformedOutputError(
                f"the wake export carries {words[0]!r}, which no wake export writes"
            )
    return _complete_blocks(points, segments, values)


def _complete_blocks(
    points: np.ndarray | None, segments: np.ndarray | None, values: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the three blocks once all were read and the segments name only known nodes."""
    if points is None or segments is None or values is None:
        missing = [
            name
            for name, block in (("POINTS", points), ("LINES", segments), ("cell values", values))
            if block is None
        ]
        raise IncompleteOutputError(
            f"the wake export ends before {', '.join(missing)}; it is truncated"
        )
    if len(segments) and (segments.min() < 0 or segments.max() >= len(points)):
        raise MalformedOutputError(f"a wake segment names a node outside the {len(points)} points")
    return points, segments, values


def _shared_nodes(points: np.ndarray, segments: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Re-index segments so a node written twice at one position is one node.

    Only nodes of segments that carry the same value are joined: a wake line
    carries one value, so segments of different values are different lines.
    """
    # Connected node indices are authoritative. Coalescing by position would
    # fuse the two root lines of a mirror export and erase collapsed segments.
    # The older disconnected-segment layout needs coordinate stitching only
    # when every node belongs to exactly one segment.
    if len(segments) and np.bincount(segments.ravel()).max() > 1:
        return segments
    flat = segments.ravel()
    keyed = np.column_stack([points[flat], np.repeat(values, 2)])
    _, first, canonical = np.unique(keyed, axis=0, return_index=True, return_inverse=True)
    shared = flat[first][np.asarray(canonical).reshape(-1)].reshape(-1, 2)
    if np.any(shared[:, 0] == shared[:, 1]):
        raise MalformedOutputError("a wake segment joins a node to itself")
    return shared


def _neighbours(segments: np.ndarray, n_points: int) -> list[list[int]]:
    out: list[list[int]] = [[] for _ in range(n_points)]
    for a, b in segments.tolist():
        out[a].append(b)
        out[b].append(a)
    return out


def _sweep(neighbours: list[list[int]], front: list[int]) -> np.ndarray:
    """Return each node's segment distance from ``front`` (-1 where none reaches)."""
    distance = np.full(len(neighbours), -1, dtype=np.int64)
    distance[front] = 0
    while front:
        following: list[int] = []
        for node in front:
            for other in neighbours[node]:
                if distance[other] < 0:
                    distance[other] = distance[node] + 1
                    following.append(other)
        front = following
    return distance


def _components(neighbours: list[list[int]]) -> np.ndarray:
    """Return a component label per node (-1 for a node no segment names)."""
    label = np.full(len(neighbours), -1, dtype=np.int64)
    for seed, joined in enumerate(neighbours):
        if joined and label[seed] < 0:
            label[_sweep(neighbours, [seed]) >= 0] = seed
    return label


def _mixed_export(points: np.ndarray, segments: np.ndarray, values: np.ndarray) -> WakeExport:
    """Read a file holding wake lattices (rotor blades), with any wing lines beside them.

    A component with a node that joins more than two segments is a lattice; every
    other component is read as independent lines, as a wing export is.
    """
    neighbours = _neighbours(segments, len(points))
    label = _components(neighbours)
    degree = np.array([len(joined) for joined in neighbours])
    in_lattice = np.isin(label[segments[:, 0]], np.unique(label[degree > 2]))
    chains = (
        _chain_export(points, segments[~in_lattice], values[~in_lattice])
        if np.any(~in_lattice)
        else WakeExport(lines=(), values=np.zeros(0))
    )
    lattice = _lattice_export(points, segments[in_lattice], values[in_lattice], label)
    owners = lattice.blades if lattice.blades is not None else np.zeros(0, dtype=np.int64)
    return WakeExport(
        lines=chains.lines + lattice.lines,
        values=np.concatenate([chains.values, lattice.values]),
        blades=np.concatenate([np.full(len(chains.lines), -1, dtype=np.int64), owners]),
    )


def _lattice_export(
    points: np.ndarray, segments: np.ndarray, values: np.ndarray, label: np.ndarray
) -> WakeExport:
    """Read wake lattices: one line per trailing filament, valued at the trailing edge.

    A lattice is written row by row in time. Its trailing-edge nodes join one
    segment each (the newest row has no shed segment; the bound vortex is on the
    blade), and a node's row is its segment distance from them. A trailing
    (streamwise) segment joins rows k and k + 1 of one spanwise station; a shed
    (spanwise) segment joins two stations within one row and carries the mean of
    the trailing values beside it, so it is dropped. Each trailing filament is
    one line from its trailing-edge node downstream, valued by its segment at the
    trailing edge: the loading of the exported step (older segments carry earlier
    steps, down to zero at the start-up end). Each lattice (``label``, one
    connected component) is one blade.

    The value is signed by the direction its segment is written: a value ``g``
    on a segment written from the trailing edge downstream is the line value
    ``g``; one written towards the trailing edge (as 26.125 writes rotor
    lattices) is ``-g``. Measured on the r1w export (POL 4701, step 144): the
    axial spacing of the wake rows near the disk gives an induced velocity of
    1.406 m/s, and the Biot-Savart velocity of the filaments read this way is
    1.405 m/s (least-squares scale 0.949, correlation 0.991); the opposite sign
    gives -1.405 m/s.
    """
    neighbours = _neighbours(segments, len(points))
    rows = _sweep(neighbours, [node for node, joined in enumerate(neighbours) if len(joined) == 1])
    if np.any(rows[segments.ravel()] < 0):
        raise MalformedOutputError(
            "a wake line branches: a node joins more than two segments, and the lattice "
            "has no trailing-edge row from which its filaments could be read"
        )
    trailing = rows[segments[:, 0]] != rows[segments[:, 1]]
    kept, kept_values = segments[trailing], values[trailing]
    lines: list[np.ndarray] = []
    line_values: list[float] = []
    owners: list[int] = []
    for chain in _chains(kept, len(points)):
        nodes = np.unique(kept[chain].ravel())
        nodes = nodes[np.argsort(rows[nodes], kind="stable")]
        newest = min(chain, key=lambda cell: int(rows[kept[cell]].min()))
        head, tail = (int(node) for node in kept[newest])
        downstream = 1.0 if rows[head] < rows[tail] else -1.0
        lines.append(points[nodes])
        line_values.append(downstream * float(kept_values[newest]))
        owners.append(int(label[nodes[0]]))
    _, blades = np.unique(np.asarray(owners, dtype=np.int64), return_inverse=True)
    return WakeExport(
        lines=tuple(lines),
        values=np.asarray(line_values),
        blades=np.asarray(blades, dtype=np.int64).reshape(-1),
    )


def _ordered_nodes(points: np.ndarray, segments: np.ndarray, chain: list[int]) -> np.ndarray:
    """Return the coordinates of one chain's nodes, from the upstream end (smallest x)."""
    nodes = [int(segments[chain[0]][0]), int(segments[chain[0]][1])]
    if len(chain) > 1 and nodes[0] in (int(segments[chain[1]][0]), int(segments[chain[1]][1])):
        nodes.reverse()
    for cell in chain[1:]:
        a, b = int(segments[cell][0]), int(segments[cell][1])
        nodes.append(b if a == nodes[-1] else a)
    coords = points[nodes]
    return coords[::-1] if coords[-1, 0] < coords[0, 0] else coords
