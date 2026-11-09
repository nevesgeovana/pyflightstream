"""Knot insertion and splitting of the tensor-product B-spline patch.

Pipeline role: pure numerical tools of the geometry package. A skinned surface is built once and
split into patches by inserting a knot to full multiplicity, so the pieces are the same surface
as the whole, not a new fit. Parameter domains are [0, 1] in both directions, as
:func:`~pyflightstream.geometry._patch.evaluate_patch` reads them.
"""

from __future__ import annotations

import numpy as np

from pyflightstream._errors import InputValueError

from ._patch import Patch

__all__ = ["full_knots", "insert_knot", "split_patch"]

_DIRECTIONS = ("u", "v")


def full_knots(knots, multiplicities) -> np.ndarray:
    """Return the knot vector with every distinct knot repeated by its multiplicity."""
    return np.repeat(np.asarray(knots, float), np.asarray(multiplicities, int))


def _insert_once(controls, knots, degree, x):
    """Insert ``x`` once in a curve whose control points run along axis 0 (Boehm)."""
    n = len(controls)
    span = int(np.searchsorted(knots, x, side="right")) - 1
    span = min(max(span, degree), n - 1)
    out = np.empty((n + 1, *controls.shape[1:]))
    out[: span - degree + 1] = controls[: span - degree + 1]
    for i in range(span - degree + 1, span + 1):
        a = (x - knots[i]) / (knots[i + degree] - knots[i])
        out[i] = (1 - a) * controls[i - 1] + a * controls[i]
    out[span + 1 :] = controls[span:]
    return out, np.insert(knots, span + 1, x)


def _along(patch, direction):
    """Return the controls with the chosen direction first, its knots and its degree."""
    if direction == "u":
        return (
            np.asarray(patch.controls, float),
            full_knots(patch.knots_u, patch.multiplicities_u),
            patch.degree_u,
        )
    return (
        np.asarray(patch.controls, float).transpose(1, 0, 2),
        full_knots(patch.knots_v, patch.multiplicities_v),
        patch.degree_v,
    )


def _rebuilt(patch, direction, controls, knots):
    """Return ``patch`` with the chosen direction replaced by ``controls`` and ``knots``."""
    distinct, mult = np.unique(knots, return_counts=True)
    key = {"u": ("knots_u", "multiplicities_u"), "v": ("knots_v", "multiplicities_v")}[direction]
    values = {
        key[0]: tuple(float(k) for k in distinct),
        key[1]: tuple(int(m) for m in mult),
        "controls": controls if direction == "u" else controls.transpose(1, 0, 2),
    }
    fields = {**patch.__dict__, **values}
    return Patch(**fields)


def insert_knot(patch: Patch, direction: str, x: float, times: int = 1) -> Patch:
    """Return the same surface with the knot ``x`` inserted ``times`` more times.

    Parameters
    ----------
    patch : Patch
        Surface to refine.
    direction : {"u", "v"}
        Parametric direction of the insertion.
    x : float
        Parameter strictly inside (0, 1).
    times : int, optional
        Insertions to make; the multiplicity of ``x`` may not exceed the degree.

    Returns
    -------
    Patch
        A surface that evaluates to the same points as ``patch``.

    Raises
    ------
    InputValueError
        When the direction is unknown, ``x`` is not inside (0, 1) or the multiplicity would
        exceed the degree.
    """
    if direction not in _DIRECTIONS:
        raise InputValueError("direction: expected u or v")
    controls, knots, degree = _along(patch, direction)
    if not 0.0 < x < 1.0:
        raise InputValueError("x: the knot must lie strictly inside (0, 1)")
    if times < 0 or np.count_nonzero(knots == x) + times > degree:
        raise InputValueError("times: the multiplicity of a knot may not exceed the degree")
    for _ in range(times):
        controls, knots = _insert_once(controls, knots, degree, x)
    return _rebuilt(patch, direction, controls, knots)


def _clip(patch, direction, bounds, controls, knots):
    """Return a piece of a curve between two clamped knots, its parameter set to [0, 1]."""
    lo, hi = bounds
    return _rebuilt(patch, direction, controls, np.clip((knots - lo) / (hi - lo), 0.0, 1.0))


def split_patch(patch: Patch, direction: str, x: float) -> tuple[Patch, Patch]:
    """Split a patch at the parameter ``x`` of one direction into two patches of the same surface.

    The knot is inserted to full multiplicity and each half is returned with its own parameter
    set to [0, 1], so the two pieces evaluate to the original surface to rounding.

    Parameters
    ----------
    patch : Patch
        Surface to split.
    direction : {"u", "v"}
        Parametric direction to cut across.
    x : float
        Parameter strictly inside (0, 1).

    Returns
    -------
    tuple of Patch
        The piece before ``x`` and the piece after it.

    Raises
    ------
    InputValueError
        As :func:`insert_knot`.

    Examples
    --------
    >>> import numpy as np
    >>> from pyflightstream.geometry._patch import interpolate_patch
    >>> grid = np.random.default_rng(1).normal(size=(9, 7, 3))
    >>> low, high = split_patch(interpolate_patch(grid), "u", 0.5)
    >>> bool(np.allclose(low.evaluate(5)[-1], high.evaluate(5)[0]))
    True
    """
    refined = _complete(patch, direction, x)
    controls, knots, degree = _along(refined, direction)
    first = int(np.flatnonzero(knots == x)[0])
    left_knots = np.append(knots[: first + degree], x)
    left = _clip(refined, direction, (0.0, x), controls[:first], left_knots)
    right_knots = np.insert(knots[first:], 0, x)
    right = _clip(refined, direction, (x, 1.0), controls[first - 1 :], right_knots)
    return left, right


def _multiplicity(patch, direction, x) -> int:
    """Return how many times ``x`` is already a knot of the direction."""
    _, knots, _ = _along(patch, direction)
    return int(np.count_nonzero(knots == x))


def _complete(patch, direction, x):
    """Raise the multiplicity of an existing knot to the degree."""
    degree = patch.degree_u if direction == "u" else patch.degree_v
    return insert_knot(patch, direction, x, times=degree - _multiplicity(patch, direction, x))
