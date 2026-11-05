"""Trefftz B on every wake sheet of a configuration (FR-452).

Pipeline role: the wake export holds the lines of every component that sheds a
wake, and the export does not say which component a line belongs to. This
module separates the lines into sheets by where their first nodes lie, cuts
each sheet at the Trefftz plane, and integrates all sheets together on the one
plane, the normalwash at every strip coming from every sheet's filaments. The
equations are those of the definitions page, The far-field family; nothing here
reads or writes a file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from pyflightstream.farfield._wake_math import (
    _first_crossings,
    _induced,
    _require_density,
)
from pyflightstream.farfield.fields import FarfieldInputError
from pyflightstream.farfield.trefftz import RUN_GAP_FACTOR, TraceResult

__all__ = [
    "CLOSURE_RTOL",
    "SheetCrossings",
    "WakeSheet",
    "sheet_crossings",
    "sheet_forces",
    "split_wake_sheets",
]

#: A closed sheet's values must sum to zero within this fraction of their
#: absolute sum, as the strengths of a full open sheet must.
CLOSURE_RTOL = 1e-4

#: A run of first nodes closes into a ring when its two ends lie within this
#: many times its largest consecutive gap, and it holds at least this many lines.
_RING_END_FACTOR = 1.5
_RING_MIN_LINES = 4


@dataclass(frozen=True, eq=False)
class WakeSheet:
    """One sheet of the export: the lines it holds, in the order the trace walks them.

    Attributes
    ----------
    index : numpy.ndarray
        Positions in the input of the sheet's lines, in walking order: from the
        end farthest from the symmetry plane to the end nearest it for an open
        sheet, around the ring from the line of smallest ``y`` for a closed one.
    closed : bool
        True where the first nodes close into a ring (a base rim).
    """

    index: np.ndarray
    closed: bool


@dataclass(frozen=True, eq=False)
class SheetCrossings:
    """Where one sheet's lines cross the plane.

    Attributes
    ----------
    y, z : numpy.ndarray
        The crossings in walking order, m.
    values : numpy.ndarray
        The exported value of each crossing's line.
    closed : bool
        Whether the sheet is a ring.
    index : numpy.ndarray
        Positions of the lines in the input.
    short : int
        How many of the sheet's lines end before the plane.
    blade : bool
        A blade ordered root to tip: accumulate inward from its free tip, without a
        closure constraint or a central strip connecting its mirror image.
    """

    y: np.ndarray
    z: np.ndarray
    values: np.ndarray
    closed: bool
    index: np.ndarray
    short: int
    blade: bool = False


def _link_components(starts: np.ndarray) -> list[np.ndarray]:
    """Group first nodes into runs of nodes that are close to one another.

    Two are linked when closer than the gap factor times the smaller of their
    nearest-neighbour distances.
    """
    n = len(starts)
    nearest = np.empty(n)
    for first in range(0, n, 64):
        block = np.linalg.norm(starts[first : first + 64, None, :] - starts[None, :, :], axis=2)
        block[np.arange(len(block)), np.arange(first, first + len(block))] = np.inf
        nearest[first : first + 64] = block.min(axis=1)
    seen = np.zeros(n, dtype=bool)
    groups = []
    for first in range(n):
        if seen[first]:
            continue
        stack, members = [first], []
        seen[first] = True
        while stack:
            k = stack.pop()
            members.append(k)
            reach = RUN_GAP_FACTOR * np.minimum(nearest[k], nearest)
            close = np.linalg.norm(starts - starts[k], axis=1) <= reach
            for j in np.flatnonzero(close & ~seen):
                seen[j] = True
                stack.append(int(j))
        groups.append(np.array(sorted(members)))
    return groups


def _path_of(starts: np.ndarray) -> tuple[list[int], float] | None:
    """Walk the minimum spanning tree of the first nodes if it is one path, else None.

    Also returns the largest gap of the tree.
    """
    n = len(starts)
    in_tree = np.zeros(n, dtype=bool)
    in_tree[0] = True
    best = np.linalg.norm(starts - starts[0], axis=1)
    parent = np.zeros(n, dtype=int)
    neighbours: list[list[int]] = [[] for _ in range(n)]
    largest = 0.0
    for _ in range(n - 1):
        best_masked = np.where(in_tree, np.inf, best)
        k = int(np.argmin(best_masked))
        neighbours[k].append(int(parent[k]))
        neighbours[int(parent[k])].append(k)
        largest = max(largest, float(best_masked[k]))
        in_tree[k] = True
        row = np.linalg.norm(starts - starts[k], axis=1)
        closer = row < best
        parent[closer] = k
        best = np.where(closer, row, best)
    if any(len(item) > 2 for item in neighbours):
        return None
    end = next(k for k in range(n) if len(neighbours[k]) == 1)
    order, previous, here = [end], -1, end
    while len(order) < n:
        here, previous = next(j for j in neighbours[here] if j != previous), here
        order.append(here)
    return order, largest


def split_wake_sheets(
    lines: Sequence[np.ndarray], values: np.ndarray, *, mirror: bool = False
) -> tuple[list[WakeSheet], list[tuple[np.ndarray, str]]]:
    """Separate the wake lines into sheets by their first nodes (FR-452).

    A sheet is a run of first nodes in which each is close to the next, close
    meaning within :data:`~pyflightstream.farfield.trefftz.RUN_GAP_FACTOR` times
    the smaller of the two nearest-neighbour distances, so a dense rim is never
    taken into a sparse trailing edge. An open sheet is walked from its end
    farthest from the symmetry plane to its end nearest it (``y`` of the first
    node; the end of a full model's sheet is the one of smaller ``y``). A run
    that closes on itself is a ring: the first nodes lie on a rim, as they do at
    a base.

    Parameters
    ----------
    lines : sequence of numpy.ndarray
        The wake lines, each ``(n_k, 3)``, from the trailing edge downstream.
    values : numpy.ndarray
        One value per line.
    mirror : bool
        The lines are one half of a mirror model, so the end nearest ``y = 0``
        is the root.

    Returns
    -------
    sheets : list of WakeSheet
        The sheets that can be traced.
    left_out : list of (numpy.ndarray, str)
        The lines of every group that cannot, with the reason.
    """
    starts = np.array([np.asarray(line, dtype=float)[0] for line in lines]).reshape(-1, 3)
    values = np.asarray(values, dtype=float)
    sheets: list[WakeSheet] = []
    left_out: list[tuple[np.ndarray, str]] = []
    if len(starts) == 0:
        return sheets, left_out
    for members in _link_components(starts) if len(starts) > 1 else [np.array([0])]:
        if len(members) < 2:
            left_out.append((members, "one line alone bounds no strip"))
            continue
        walked = _path_of(starts[members])
        if walked is None:
            left_out.append((members, "its first nodes branch, so they are not one run"))
            continue
        order, largest = walked
        path = members[np.array(order)]
        ends = float(np.linalg.norm(starts[path[0]] - starts[path[-1]]))
        if len(path) >= _RING_MIN_LINES and ends <= _RING_END_FACTOR * largest:
            span = float(np.abs(values[path]).sum())
            defect = float(values[path].sum())
            if abs(defect) > CLOSURE_RTOL * span:
                left_out.append(
                    (
                        members,
                        "its first nodes close into a ring but its values sum to "
                        f"{defect:.4g} rather than zero (their absolute sum is {span:.4g})",
                    )
                )
                continue
            at = int(np.argmin(starts[path, 1]))
            sheets.append(WakeSheet(np.roll(path, -at), True))
            continue
        if abs(starts[path[0], 1]) < abs(starts[path[-1], 1]):
            path = path[::-1]
        elif (
            abs(starts[path[0], 1]) == abs(starts[path[-1], 1])
            and starts[path[0], 2] < starts[path[-1], 2]
        ):
            path = path[::-1]
        if not mirror and starts[path[0], 1] > starts[path[-1], 1]:
            path = path[::-1]
        sheets.append(WakeSheet(path, False))
    return sheets, left_out


def sheet_crossings(
    lines: Sequence[np.ndarray], values: np.ndarray, sheet: WakeSheet, x_t: float
) -> SheetCrossings:
    """Cut one sheet's lines at their first crossing of the plane ``x = x_t``.

    Parameters
    ----------
    lines : sequence of numpy.ndarray
        Wake chains in wind axes, in metres, newest node first.
    values : numpy.ndarray
        One filament strength per chain in m^2/s.
    sheet : WakeSheet
        Indices and topology of the selected sheet.
    x_t : float
        Downstream plane position in metres.

    Returns
    -------
    SheetCrossings
        First crossings in sheet order and the count not reaching the plane.
    """
    chosen = [lines[k] for k in sheet.index]
    crossings, short, _downstream = _first_crossings(chosen, x_t)
    return SheetCrossings(
        y=crossings[:, 1],
        z=crossings[:, 2],
        values=np.asarray(values, dtype=float)[sheet.index],
        closed=sheet.closed,
        index=sheet.index,
        short=short,
    )


def _sheet_edges(
    sheet: SheetCrossings, *, mirror: bool
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, bool, np.ndarray]]:
    """Return edges, strip circulation, closed and original flags, and the image if mirrored."""
    y, z, v = sheet.y, sheet.z, sheet.values
    if sheet.blade:
        gamma = np.cumsum(v[::-1])[::-1][1:]
        out = [(y, z, gamma, False, np.ones(len(gamma), dtype=bool))]
        if mirror:
            out.append((-y, z, -gamma, False, np.zeros(len(gamma), dtype=bool)))
        return out
    if sheet.closed:
        gamma = -np.cumsum(v)
        gamma = gamma - gamma.mean()
        out = [(y, z, gamma, True, np.ones(len(gamma), dtype=bool))]
        if mirror:
            image = np.concatenate([gamma[-2::-1], gamma[-1:]])
            out.append((-y[::-1], z[::-1], image, True, np.zeros(len(gamma), dtype=bool)))
        return out
    if mirror:
        if not (np.all(y < 0.0) or np.all(y > 0.0)):
            raise FarfieldInputError("a mirrored wake needs crossings on one side of y = 0")
        positive = bool(y[0] > 0.0)
        if positive:
            y, z, v = -y[::-1], z[::-1], v[::-1]
        half = -np.cumsum(v)
        original = np.zeros(2 * len(half) - 1, dtype=bool)
        if positive:
            original[len(half) :] = True
        else:
            original[: len(half) - 1] = True
        return [
            (
                np.concatenate([y, -y[::-1]]),
                np.concatenate([z, z[::-1]]),
                np.concatenate([half, half[-2::-1]]),
                False,
                original,
            )
        ]
    closure = float(np.sum(v))
    if abs(closure) > CLOSURE_RTOL * float(np.sum(np.abs(v))):
        raise FarfieldInputError(
            "the wake strengths of a full sheet must sum to zero; they sum to "
            f"{closure:g}, so a line is missing or a strength is malformed"
        )
    return [(y, z, -np.cumsum(v)[:-1], False, np.ones(len(v) - 1, dtype=bool))]


def _filaments(gamma: np.ndarray, closed: bool) -> np.ndarray:
    """Return the circulation each edge sheds: the jump between the strips beside it."""
    if closed:
        return gamma - np.roll(gamma, 1)
    return np.diff(np.concatenate([[0.0], gamma, [0.0]]))


def sheet_forces(
    sheets: Sequence[SheetCrossings], *, rho: float, v_inf: float, mirror: bool = False
) -> TraceResult:
    """Lift, side force and induced drag of several wake sheets on one plane (FR-452).

    Each sheet's strips lie between its consecutive crossings (around the ring
    for a closed sheet); the circulation of a strip is minus the running sum of
    the exported values from the sheet's first crossing, and a ring's has its
    mean removed to make the walk's start irrelevant. Blades sum inward from their
    free tip. Mirror sheets reflect once. The normalwash at each strip comes from
    the filaments of every sheet, and

    ``L = rho V sum Gamma dy``, ``Y = -rho V sum Gamma dz``,
    ``D_i = -(rho / 2) sum Gamma v_n ds``.

    On one open sheet this is :meth:`~pyflightstream.farfield.trefftz.WakeTrace.forces`.

    Parameters
    ----------
    sheets : sequence of SheetCrossings
        The crossings of each sheet.
    rho, v_inf : float
        Density in kg/m3 and free-stream speed in m/s.
    mirror : bool
        The sheets are one half of a mirror model.

    Returns
    -------
    TraceResult
        The joint forces, the per-sheet forces (``sheet_lift``,
        ``sheet_drag_share`` under every sheet's filaments, ``sheet_drag_isolated``
        under the sheet's own) and the strips; the image of a mirrored sheet
        carries its sheet's label.

    Raises
    ------
    FarfieldInputError
        If the sheets do not form an integrable trace.
    """
    _require_density(rho)
    if not sheets:
        raise FarfieldInputError("the wake needs at least one sheet to trace")
    parts = []
    for label, sheet in enumerate(sheets):
        for ey, ez, gamma, closed, original in _sheet_edges(sheet, mirror=mirror):
            if len(gamma) < 1:
                raise FarfieldInputError("the wake needs at least two crossings to bound a strip")
            nxt = np.roll(np.arange(len(ey)), -1) if closed else np.arange(1, len(ey))
            cur = np.arange(len(ey)) if closed else np.arange(len(ey) - 1)
            parts.append(
                {
                    "label": label,
                    "ey": ey,
                    "ez": ez,
                    "gamma": gamma,
                    "shed": (
                        (-sheet.values if np.any(original) else sheet.values)
                        if sheet.blade
                        else _filaments(gamma, closed)
                    ),
                    "y": 0.5 * (ey[cur] + ey[nxt]),
                    "z": 0.5 * (ez[cur] + ez[nxt]),
                    "dy": ey[nxt] - ey[cur],
                    "dz": ez[nxt] - ez[cur],
                    "original": original,
                }
            )
    for part in parts:
        part["ds"] = np.hypot(part["dy"], part["dz"])
        if np.any(part["ds"] == 0.0):
            raise FarfieldInputError("two wake crossings coincide, so a strip has zero width")
    all_ey = np.concatenate([p["ey"] for p in parts])
    all_ez = np.concatenate([p["ez"] for p in parts])
    all_shed = np.concatenate([p["shed"] for p in parts])
    for p in parts:
        v, w = _induced(p["y"], p["z"], all_ey, all_ez, all_shed)
        own_v, own_w = _induced(p["y"], p["z"], p["ey"], p["ez"], p["shed"])
        p["vn"] = (-p["dz"] * v + p["dy"] * w) / p["ds"]
        p["vn_own"] = (-p["dz"] * own_v + p["dy"] * own_w) / p["ds"]
    labels = tuple(range(len(sheets)))
    sheet_lift = np.zeros(len(sheets))
    sheet_side = np.zeros(len(sheets))
    share = np.zeros(len(sheets))
    isolated = np.zeros(len(sheets))
    for p in parts:
        g, k = p["gamma"], p["label"]
        sheet_lift[k] += rho * v_inf * float((g * p["dy"]).sum())
        sheet_side[k] += -rho * v_inf * float((g * p["dz"]).sum())
        share[k] += -0.5 * rho * float((g * p["vn"] * p["ds"]).sum())
        isolated[k] += -0.5 * rho * float((g * p["vn_own"] * p["ds"]).sum())
    lift, side, drag = float(sheet_lift.sum()), float(sheet_side.sum()), float(share.sum())
    cat = np.concatenate
    return TraceResult(
        lift=lift,
        side_force=side,
        induced_drag=drag,
        sheets=labels,
        sheet_lift=sheet_lift,
        sheet_side_force=sheet_side,
        sheet_drag_share=share,
        sheet_drag_isolated=isolated,
        y=cat([p["y"] for p in parts]),
        z=cat([p["z"] for p in parts]),
        dy=cat([p["dy"] for p in parts]),
        dz=cat([p["dz"] for p in parts]),
        ds=cat([p["ds"] for p in parts]),
        gamma=cat([p["gamma"] for p in parts]),
        normalwash=cat([p["vn"] for p in parts]),
        sheet=cat([np.full(len(p["gamma"]), p["label"], dtype=int) for p in parts]),
        original=cat([p["original"] for p in parts]),
    )
