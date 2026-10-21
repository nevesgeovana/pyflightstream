"""The reader of the solver's wake export, ``<name>_wakes.vtk`` (FR-1023).

Pipeline role: parses the wake lines the surface VTK export writes beside the
surface when ``SET_VTK_EXPORT_VARIABLES`` states the wake: VTK legacy ASCII
polydata of POINTS, two-point LINES and one cell scalar,
``Normalized_Vorticity``. The segments chain into one wake line per
trailing-edge node, each line carrying one value, constant along it; the value
is the circulation shed by that wake line. Trefftz B of
the far-field family reads it (:mod:`pyflightstream.farfield.trefftz`).

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
        frame) downstream.
    values : numpy.ndarray
        One value per line, :data:`WAKE_VALUE`.
    """

    lines: tuple[np.ndarray, ...]
    values: np.ndarray


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
        return np.asarray(tokens, dtype=dtype)
    except ValueError as error:
        raise MalformedOutputError(
            f"the wake export's {what} holds a value that is no number"
        ) from error


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
    scale = float(np.max(np.abs(values))) if values.size else 0.0
    lines: list[np.ndarray] = []
    line_values: list[float] = []
    for chain in _chains(segments, len(points)):
        chain_values = values[chain]
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
