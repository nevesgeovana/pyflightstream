"""Spanwise spline distributions for the parametric geometry.

Pipeline role: pure numerical helper of the geometry package. One cubic
spline interpolates a quantity (chord, twist, a leading-edge offset, or the
coefficients of a section) through its control stations.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline

from pyflightstream._errors import InputValueError

__all__ = [
    "blended_section",
    "chord_spacing",
    "elevate_coefficients",
    "insert_knot",
    "planform_values",
    "spline_distribution",
]


def spline_distribution(stations, values, at):
    """Interpolate ``values`` given at ``stations`` and return value and slope at ``at``.

    A not-a-knot cubic is used for three or more stations, a straight line for
    two and a constant for one. Axis zero of ``values`` indexes the stations;
    the remaining axes may hold section coefficients. Extrapolation beyond the
    control stations is refused when there is more than one station.

    Returns
    -------
    tuple of numpy.ndarray
        The interpolated values and their first derivative with respect to the
        station coordinate, both of shape ``at.shape + values.shape[1:]``.
    """
    x, y, q = np.asarray(stations, float), np.asarray(values, float), np.asarray(at, float)
    if x.ndim != 1 or not len(x) or y.ndim < 1 or y.shape[0] != len(x):
        raise InputValueError("stations/values: inconsistent dimensions")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or not np.all(np.isfinite(q)):
        raise InputValueError("stations/values/at: finite values required")
    if len(x) == 1:
        shape = q.shape + y.shape[1:]
        return np.broadcast_to(y[0], shape).copy(), np.zeros(shape)
    if np.any(np.diff(x) <= 0):
        raise InputValueError("stations: strictly increasing values required")
    if np.any(q < x[0]) or np.any(q > x[-1]):
        raise InputValueError("at: outside control stations")
    spline = CubicSpline(x, y, axis=0, bc_type="not-a-knot", extrapolate=False)
    return spline(q), spline(q, 1)


def elevate_coefficients(coefficients, degree):
    """Degree-elevate Bernstein coefficients to ``degree`` without changing the curve."""
    a = np.asarray(coefficients, float)
    while len(a) <= degree:
        n = len(a)
        q = np.arange(1, n) / n
        a = np.r_[a[0], q * a[:-1] + (1 - q) * a[1:], a[-1]]
    return a


def insert_knot(knots, degree, points, t):
    """Insert the knot ``t`` once into a B-spline curve (Boehm); the curve does not change.

    ``knots`` is the full clamped knot vector, ``points`` the control points of shape (n, d).
    Returns the new knot vector and control points.
    """
    k, p = np.asarray(knots, float), np.asarray(points, float)
    if len(k) != len(p) + degree + 1:
        raise InputValueError("knots/points: knot count must be points + degree + 1")
    if not k[degree] < t < k[len(p)]:
        raise InputValueError("t: must lie strictly inside the parameter range")
    span = int(np.searchsorted(k, t, side="right")) - 1
    new = [p[0]]
    for i in range(1, len(p)):
        if i <= span - degree:
            new.append(p[i])
        elif i > span:
            new.append(p[i - 1])
        else:
            a = (t - k[i]) / (k[i + degree] - k[i])
            new.append(a * p[i] + (1 - a) * p[i - 1])
    new.append(p[-1])
    return np.insert(k, span + 1, t), np.array(new)


def planform_values(component, eta):
    """Return chord, leading-edge offsets and twist at normalized span ``eta``, in model units."""
    p = component["planform"]
    stations = np.array(p["control_stations"])
    span = p["span"]
    chord = p["root_chord"] + (p["tip_chord"] - p["root_chord"]) * stations
    le_x = span / 2 * stations * np.tan(np.deg2rad(p["sweep"]))
    if p["sweep_reference"] == "quarter_chord":
        le_x += (p["root_chord"] - chord) / 4
    defaults = {
        "chord": chord / span,
        "leading_edge_x": le_x / span,
        "leading_edge_z": stations / 2 * np.tan(np.deg2rad(p["dihedral"])),
        "twist": p["incidence"] + p["tip_twist"] * stations,
    }
    result = {}
    for key, values in defaults.items():
        distribution = component.get("distributions", {}).get(
            key, {"stations": stations, "values": values}
        )
        result[key] = spline_distribution(distribution["stations"], distribution["values"], eta)[0]
        if key != "twist":
            result[key] *= span
    return result


def blended_section(sections, models, eta):
    """Blend the CST coefficients and trailing-edge thickness of the sections at ``eta``."""
    return {
        key: spline_distribution(sections["eta"], [m[key] for m in models], eta)[0]
        for key in ("upper", "lower", "trailing_edge_thickness")
    }


def chord_spacing(start, end, u):
    """Map ``u`` in [0, 1] to chord fractions from ``start`` to ``end``, clustered at the nose.

    The spacing is uniform in the square root of the chord fraction, which resolves the
    leading-edge curvature with the same number of samples as the rest of the chord.
    """
    root_start, root_end = np.sqrt(start), np.sqrt(end)
    u = np.asarray(u, float)
    if np.any(u < 0) or np.any(u > 1):
        raise InputValueError("u: parameter range [0, 1] required")
    return (root_start + (root_end - root_start) * u) ** 2
