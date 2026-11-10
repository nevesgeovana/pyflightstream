"""Exact control partitions of a pinned lifting skin, with separate closure bases.

Pipeline role: pure geometry for the applied-control hand-off. Outer faces remain
iso trims of the input skin. End faces and the hinge wall share its boundary
curves by knot insertion and spline evaluation, without sampling or refitting.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.interpolate import BSpline

from pyflightstream._errors import InputValueError

from ._bspline import full_knots, split_patch, union_knots
from ._caps import _refined
from ._patch import Patch
from ._trims import Trim, iso_trim

__all__ = ["ControlPartition", "partition"]


@dataclass(frozen=True)
class ControlPartition:
    """Shared bases and the named faces of the stationary and moving pieces."""

    bases: dict[str, Patch]
    pieces: dict[str, tuple[Trim, ...]]


def _interval(patch, direction, low, high):
    """Restrict one parameter by exact knot insertion, normalizing the result."""
    if high < 1:
        patch = split_patch(patch, direction, high)[0]
    if low > 0:
        patch = split_patch(patch, direction, low / high)[1]
    return patch


def _at_v(patch, value):
    knots = full_knots(patch.knots_v, patch.multiplicities_v)
    poles = BSpline(knots, patch.controls, patch.degree_v, axis=1)(value)
    return replace(
        patch,
        controls=np.stack((poles, poles), axis=1),
        knots_v=(0.0, 1.0),
        multiplicities_v=(2, 2),
        degree_v=1,
    )


def _end(skin, lower, upper, station):
    """Loft between the exact lower and upper aft curves at a span station."""
    low = _at_v(_interval(skin, "u", 0.0, lower), station)
    high = _at_v(_interval(skin, "u", upper, 1.0), station)
    low = replace(
        low,
        controls=low.controls[::-1],
        knots_u=tuple(round(1 - k, 15) for k in low.knots_u[::-1]),
        multiplicities_u=low.multiplicities_u[::-1],
    )
    high = replace(high, knots_u=tuple(round(k, 15) for k in high.knots_u))
    common = union_knots(
        full_knots(low.knots_u, low.multiplicities_u),
        full_knots(high.knots_u, high.multiplicities_u),
    )
    low, high = _refined(low, common), _refined(high, common)
    return replace(
        low,
        family="end",
        role="end",
        controls=np.stack((low.controls[:, 0], high.controls[:, 0]), axis=1),
    )


def _wall(skin, lower, upper):
    knots = full_knots(skin.knots_u, skin.multiplicities_u)
    poles = BSpline(knots, skin.controls, skin.degree_u, axis=0)([lower, upper])
    return replace(
        skin,
        family="hinge",
        role="hinge",
        controls=poles,
        knots_u=(0.0, 1.0),
        multiplicities_u=(2, 2),
        degree_u=1,
    )


def _rectangle(trim, u, v):
    """Append a rectangular face when neither interval is empty."""
    if u[0] < u[1] and v[0] < v[1]:
        trim.append(iso_trim(f"skin_{len(trim)}", "skin", u, v, role="skin"))


def _validate(skin, lower, upper, span):
    a, b = span
    if not np.isfinite([a, b]).all() or not 0 < a < b < 1:
        raise InputValueError("control span: give finite limits 0 < start < end < 1")
    if not 0 < lower < 0.5 < upper < 1:
        raise InputValueError("control hinge: give lower < 0.5 < upper inside (0, 1)")
    if lower not in skin.knots_u or upper not in skin.knots_u:
        raise InputValueError("control hinge: both parameters must be pinned skin knots")


def partition(
    skin: Patch, *, lower: float, upper: float, span: tuple[float, float]
) -> ControlPartition:
    """Partition a pinned skin into closed stationary and aft control pieces.

    Parameters
    ----------
    skin : Patch
        One skin, lower trailing edge at u=0, leading edge at u=0.5, upper
        trailing edge at u=1. The span is v. Root and tip are closed here.
    lower, upper : float
        Pinned hinge parameters on the lower and upper sides.
    span : tuple of float
        Control limits in the skin's normalized span, strictly inside (0, 1).

    Returns
    -------
    ControlPartition
        Bases shared by exact iso trims; closures have their own bases. The
        two pieces meet at the hinge and ends. Physical gaps and deflection
        are subsequent operations, not implicit offsets of these faces.

    Raises
    ------
    InputValueError
        If the limits are nonfinite, reversed, outside the skin, or unpinned.
    """
    _validate(skin, lower, upper, span)
    a, b = span
    bases = {
        "skin": skin,
        "hinge": _wall(skin, lower, upper),
        "trailing_edge": _wall(skin, 0.0, 1.0),
    }
    main: list[Trim] = []
    moving: list[Trim] = []
    for v in ((0.0, a), (b, 1.0)):
        _rectangle(main, (0.0, 0.5), v)
        _rectangle(main, (0.5, 1.0), v)
    for u in ((lower, 0.5), (0.5, upper)):
        _rectangle(main, u, (a, b))
    for u in ((0.0, lower), (upper, 1.0)):
        _rectangle(moving, u, (a, b))
    for faces, intervals in ((main, ((0.0, a), (b, 1.0))), (moving, ((a, b),))):
        for i, v in enumerate(intervals):
            faces.append(iso_trim(f"te_{i}", "trailing_edge", (0.0, 1.0), v, "trailing_edge"))
        faces.append(iso_trim("hinge", "hinge", (0.0, 1.0), (a, b), "hinge"))
    for name, station in (("root", 0.0), ("tip", 1.0)):
        bases[name] = _end(skin, 0.5, 0.5, station)
        main.append(iso_trim(name, name, (0.0, 1.0), (0.0, 1.0), "end"))
    for name, station in (("inboard", a), ("outboard", b)):
        bases[name] = _end(skin, lower, upper, station)
        for faces in (main, moving):
            faces.append(iso_trim(name, name, (0.0, 1.0), (0.0, 1.0), "end"))
    return ControlPartition(bases, {"main": tuple(main), "control": tuple(moving)})
