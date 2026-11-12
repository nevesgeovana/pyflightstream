"""Scale the node coordinates of a FlightStream .fsm mesh block, every other byte kept (PFS-2222).

Pipeline role: the ``.fsm`` half of ``pyfs-workspace geometry scale``, called by
:mod:`pyflightstream.workspace.scale`. A saved simulation is text; the mesh block between
``$MESH_START$`` and ``$MESH_END$`` ends with the line ``0``, the node count ``n`` alone on a line
and then three rows of ``n`` comma-separated numbers, the x, y and z of every node (the layout
:func:`pyflightstream._fsm.surface_mesh` reads). Only those three rows are rewritten: each number
becomes ``c + factor * (p - c)`` in the 17-digit exponent form the solver writes, with its leading
space and the row's line ending kept. Faces, boundaries, flags, the other blocks and every other
line stay byte for byte.
"""

from __future__ import annotations

import math
import re

from pyflightstream._errors import InputValueError

__all__ = ["scale_fsm_nodes"]

_NUMBER = re.compile(rb"^[+-]?\d+(\.\d*)?([EeDd][+-]?\d+)?$")
_ROWS = 3


def _numbers(line: bytes) -> list[bytes] | None:
    """Return the comma-separated numbers of a row, or None when any token is not a number."""
    tokens = [t.strip() for t in line.strip().split(b",") if t.strip()]
    return tokens if tokens and all(_NUMBER.match(t) for t in tokens) else None


def _node_rows(lines: list[bytes]) -> int:
    """Return the index of the x row of the one node block inside the mesh block."""
    begin = next((i for i, ln in enumerate(lines) if ln.strip() == b"$MESH_START$"), None)
    if begin is None:
        raise InputValueError(
            "scale: the .fsm holds no mesh block ($MESH_START$), so there are no node "
            "coordinates to scale. Give a saved simulation that carries its mesh; no file was "
            "written."
        )
    end = next((i for i, ln in enumerate(lines) if ln.strip() == b"$MESH_END$"), len(lines))
    found = []
    for i in range(begin + 2, end - _ROWS):
        count = lines[i].strip()
        if not count.isdigit() or int(count) < 1 or lines[i - 1].strip() != b"0":
            continue
        rows = [_numbers(lines[i + 1 + k]) for k in range(_ROWS)]
        if all(r is not None and len(r) == int(count) for r in rows):
            found.append(i + 1)
    if len(found) != 1:
        raise InputValueError(
            f"scale: the mesh block of the .fsm holds {len(found)} places that look like the "
            "node count followed by its x, y and z rows, and exactly one is needed. Give a "
            "saved simulation whose mesh block is complete; no file was written."
        )
    return found[0]


def _scale_row(line: bytes, factor: float, centre: float) -> tuple[bytes, list[float], list[float]]:
    """Return one coordinate row scaled about ``centre``, and its numbers before and after."""
    ending = b"\r" if line.endswith(b"\r") else b""
    old: list[float] = []
    new: list[float] = []
    pieces = []
    tokens = line[: len(line) - len(ending)].split(b",")
    # A row written with a sign slot (a space before every positive number) keeps it.
    padded = any(t.strip() and t[:1] == b" " and t.strip()[:1] != b"-" for t in tokens)
    for token in tokens:
        body = token.strip()
        if not body:
            pieces.append(token)
            continue
        value = float(body.replace(b"D", b"E").replace(b"d", b"e"))
        moved = centre + factor * (value - centre)
        if not math.isfinite(moved):
            raise InputValueError(
                f"scale: a node coordinate is not finite after scaling by {factor!r}. Use a "
                "smaller factor; no file was written."
            )
        lead = token[: len(token) - len(token.lstrip())]
        if padded and body[:1] != b"-":
            lead = lead[:-1]
        text = ("% .17E" if padded else "%.17E") % moved
        pieces.append(lead + text.encode() + token[len(token.rstrip()) :])
        old.append(value)
        new.append(moved)
    return b",".join(pieces) + ending, old, new


def scale_fsm_nodes(
    data: bytes, factor: float, about: tuple[float, ...]
) -> tuple[bytes, list[list[float]], list[list[float]]]:
    """Return the scaled .fsm bytes and the x, y, z rows before and after.

    Parameters
    ----------
    data : bytes
        The whole .fsm file.
    factor : float
        The positive uniform multiplier.
    about : tuple of float
        The scale centre ``x, y, z``.

    Returns
    -------
    tuple
        The new bytes, and the three coordinate rows before and after, as lists of floats.

    Raises
    ------
    InputValueError
        The file has no mesh block, no single node block, or a coordinate leaves the finite
        range; nothing is written.
    """
    lines = data.split(b"\n")
    start = _node_rows(lines)
    before: list[list[float]] = []
    after: list[list[float]] = []
    for axis in range(_ROWS):
        lines[start + axis], old, new = _scale_row(lines[start + axis], factor, about[axis])
        before.append(old)
        after.append(new)
    return b"\n".join(lines), before, after
