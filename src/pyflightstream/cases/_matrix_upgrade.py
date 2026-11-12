"""Current matrix code rewrites and refusal of earlier layouts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream.cases._matrix_layouts import (
    _COLUMNS,
    _LAYOUT_0_9_0,
    _LAYOUT_0_11_0,
    _LAYOUT_0_15_0,
    _LAYOUT_0_56_0,
    _LEGACY_COLUMNS_15,
    _LEGACY_COLUMNS_16,
    CODE_COLUMNS,
    UNSTATED_CELL,
    MatrixError,
)


def _peel_terminator(line: bytes) -> tuple[bytes, bytes]:
    """Split one line into its body and its line terminator."""
    for terminator in (b"\r\n", b"\n", b"\r"):
        if line.endswith(terminator):
            return line[: -len(terminator)], terminator
    return line, b""


def _header_names(parts: list[bytes]) -> tuple[str, ...]:
    return tuple(cell.strip().decode("utf-8", "replace") for cell in parts)


def _refuse_an_earlier_layout(header: tuple[str, ...], path: object) -> None:
    """Refuse layouts older than the supported migration baseline."""
    if header in (
        _LEGACY_COLUMNS_15,
        _LEGACY_COLUMNS_16,
        _LAYOUT_0_9_0,
        _LAYOUT_0_11_0,
        _LAYOUT_0_15_0,
    ):
        raise MatrixError(
            f"{path}: expected current matrix columns {', '.join(_COLUMNS)}; "
            "this layout predates 0.38.0. Use an older package to reach 0.38.0, "
            "then pyfs-workspace migrate. See docs/upgrading.md."
        )


_GEOMETRY_PAIR = re.compile(rb"(^|/)(\s*GEOMETRY\s*:\s*)([^/|\s]+)")


#: The SWEEP_TYPE codes the fold above knows, to the FLIGHT_CONDITION key
#: each becomes. FROZEN WITH THE LAYOUT IT CONVERTS and it does not grow.
#: The current reader has no corresponding code table: it reads the explicit
#: condition keys, so this conversion table is independent of that reader.
_SWEEP_CODE_KEYS = {"AL": "ALPHA", "BE": "BETA"}


#: The two free-cell keys that have dedicated columns, so the upgrade
#: must move them out of the cell rather than leave one fact in two homes.
_KEYS_THAT_BECAME_COLUMNS = ("GEOMETRY", "SYMMETRY")


def _pad_like(value: str, width: int, *, first: bool = False) -> bytes:
    """One cell, padded to the width its header needs, never narrower.

    THE FIRST CELL OF A LINE CARRIES NO LEADING SPACE, because no matrix
    ever written here does: a row begins at column zero with its POL. The
    first draft padded it like every other cell and every tier-1 test that
    finds its row with ``line.startswith("9005")`` stopped finding it,
    which is how a one-character difference in a converter surfaces.
    """
    padded = value.ljust(max(width, len(value)))
    return ((padded if first else " " + padded) + " ").encode("utf-8")


def _retag_cell(cell: bytes, mapping: Mapping[str, str]) -> tuple[bytes, str | None]:
    """Return one rewritten cell and the old id it carried, or None.

    Padding is preserved where it can be: the leading run of spaces is
    kept as it is, and a longer id eats trailing spaces down to one, so
    a matrix whose columns line up still lines up afterwards. Where
    there is not enough padding the cell simply grows, which is a wider
    column rather than a wrong one.
    """
    old = cell.strip().decode("utf-8", "replace")
    new = mapping.get(old)
    if new is None or new == old:
        # An id mapped to itself rebuilds the same cell: it is not a change,
        # and the per-column count of changed cells must not include it.
        return cell, None
    leading = cell[: len(cell) - len(cell.lstrip(b" "))]
    trailing = cell[len(cell.rstrip(b" ")) :]
    grew = len(new) - len(old)
    if grew > 0 and len(trailing) > 1:
        trailing = trailing[: max(1, len(trailing) - grew)]
    return leading + new.encode("utf-8") + trailing, old


def _check_the_mapping(mapping: Mapping[str, Mapping[str, str]]) -> None:
    """Refuse a mapping that names a foreign column or an id that would corrupt the matrix."""
    unknown = sorted(set(mapping) - set(CODE_COLUMNS))
    if unknown:
        raise MatrixError(
            f"column(s) {', '.join(unknown)} carry no input-library id; the columns "
            f"this rewrite touches are {', '.join(CODE_COLUMNS)}."
        )
    for column, ids in mapping.items():
        for old_id, new_id in ids.items():
            if not new_id or new_id != new_id.strip() or re.search(r"[\s|]", new_id):
                raise MatrixError(
                    f"the replacement id {new_id!r} for {old_id!r} in column {column} is "
                    "empty or holds whitespace or the cell separator, so writing it would "
                    "corrupt the matrix; nothing was rewritten."
                )


def rewrite_codes(
    path: str | Path,
    mapping: Mapping[str, Mapping[str, str]],
    *,
    in_place: bool = False,
) -> tuple[bytes, dict[str, int]]:
    """Rewrite the REF, SET and PPROC cells of a matrix, byte for byte.

    Every other cell, separator, comment rule and line ending survives
    unchanged, and EVERY data row is rewritten, active or not: a row
    whose RUN flag is 0 today is a row somebody flips to 1 tomorrow, and
    leaving its cell behind is exactly the half-resolving state the
    kind-letter rule exists to end (PFS-2009.03).

    Works on BYTES rather than through :func:`read_matrix`, because the reader replaces undecodable
    bytes, drops the dashed rule and strips every cell, so a converter
    built on it hands back a file the user cannot diff against the one
    they had.

    Parameters
    ----------
    path : str or Path
        The matrix to rewrite. Read as bytes and not decoded.
    mapping : mapping of str to mapping of str to str
        Per column, old id to new id; the keys are
        :data:`CODE_COLUMNS`. A column absent from the mapping, or a
        cell whose id the column's mapping does not carry, is left
        exactly as it is.
    in_place : bool
        Write the rewritten bytes back over ``path``. Keyword-only and
        False by default, so nothing is rewritten unless it is asked
        for.

    Returns
    -------
    tuple of bytes and dict
        The rewritten file, and how many cells changed per column. The
        count is what lets a caller refuse a migration that silently
        matched nothing.

    Raises
    ------
    MatrixError
        The header does not name the verified layout, a data row holds
        the wrong number of cells, or no line carries a cell separator.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import rewrite_codes
    >>> text, counts = rewrite_codes(       # doctest: +SKIP
    ...     "matrix.fs", {"REF": {"003": "r003"}}, in_place=True
    ... )
    """
    _check_the_mapping(mapping)
    source = str(path)
    data = Path(path).read_bytes()
    indices = {name: _COLUMNS.index(name) for name in CODE_COLUMNS if name in mapping}
    layout: tuple[str, ...] = _COLUMNS
    counts = {name: 0 for name in indices}
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            names = tuple(cell.strip().decode("utf-8", "replace") for cell in parts)
            if names not in (_COLUMNS, _LAYOUT_0_56_0):
                raise MatrixError(
                    f"{source} is not a run matrix at the verified layout: its header "
                    f"names {', '.join(names)} and the layout this rewrite reads names "
                    f"{', '.join(_COLUMNS)}. Upgrade it first if it predates a column."
                )
            layout = names
            indices = {name: layout.index(name) for name in CODE_COLUMNS if name in mapping}
            rebuilt.append(line)
            continue
        row_number += 1
        if len(parts) != len(layout):
            raise MatrixError(
                f"data row {row_number} of {source} holds {len(parts)} cells against "
                f"the {len(layout)} verified columns, so this rewrite cannot say "
                "which cell carries which id; repair the row first."
            )
        for name, index in indices.items():
            parts[index], changed = _retag_cell(parts[index], mapping[name])
            if changed is not None:
                counts[name] += 1
        rebuilt.append(b"|".join(parts) + terminator)
    if not header_seen:
        raise MatrixError(f"{source} holds no matrix content: no line carries a cell separator")
    rewritten = b"".join(rebuilt)
    if in_place:
        _textio.write_bytes(path, rewritten)
    return rewritten, counts


#: The cell width of the column 0.57.0 added: the heading's own, so the rewritten file lines up.
_ROUTE_WIDTH = len("MESH_ROUTE")


def upgrade_layout_bytes(data: bytes) -> tuple[bytes, int]:
    """Rewrite every 0.56.0 matrix header in ``data`` to the current layout, byte for byte.

    The column MESH_ROUTE is inserted after GEOMETRY in the header and, unstated, in every
    row and rule line that follows it, so each other cell, separator, comment and line ending
    survives as written. A text that holds several tables (a documentation page) is
    rewritten table by table, and a table already at the current layout is left alone.

    Parameters
    ----------
    data : bytes
        The file, or the page, as bytes.

    Returns
    -------
    tuple of bytes and int
        The rewritten bytes, and how many lines changed (a header counts as one).
    """
    at = _LAYOUT_0_56_0.index("GEOMETRY") + 1
    rebuilt: list[bytes] = []
    changed = 0
    inside = False
    compact = False
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        names = _header_names(parts)
        if names == _COLUMNS:
            inside = False
        elif names == _LAYOUT_0_56_0:
            inside = True
            # A header written without padding (the examples') gets a column without it.
            compact = parts[at - 1] == parts[at - 1].strip()
            parts.insert(at, b"MESH_ROUTE" if compact else b" MESH_ROUTE ")
            changed += 1
            line = b"|".join(parts) + terminator
        elif inside and len(parts) == len(_LAYOUT_0_56_0):
            if set(body.strip()) <= set(b"-:+| \t"):
                parts.insert(at, b"-" * (_ROUTE_WIDTH + (0 if compact else 2)))
            elif compact:
                parts.insert(at, UNSTATED_CELL.encode("utf-8"))
            else:
                parts.insert(at, _pad_like(UNSTATED_CELL, _ROUTE_WIDTH))
            changed += 1
            line = b"|".join(parts) + terminator
        rebuilt.append(line)
    return b"".join(rebuilt), changed


def upgrade_matrix_layout(path: str | Path, *, in_place: bool = False) -> tuple[bytes, int]:
    """Rewrite one file from the 0.56.0 matrix layout to the current one.

    Parameters
    ----------
    path : str or Path
        The matrix. Read as bytes, so no cell, comment or line ending is altered.
    in_place : bool
        Write the result back over ``path``. False previews.

    Returns
    -------
    tuple of bytes and int
        The rewritten file and the number of lines changed; zero means the file was not at
        the 0.56.0 layout and is returned as it was.
    """
    original = Path(path).read_bytes()
    rewritten, changed = upgrade_layout_bytes(original)
    if in_place and changed:
        _textio.write_bytes(path, rewritten)
    return rewritten, changed
