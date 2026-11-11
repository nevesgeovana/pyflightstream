"""Profile sampling and common-vector quintic fits for planar propeller sections.

Pipeline role: preserve one common chordwise parameterization before the
radial loft. The fit is checked on an independent, denser parameter lattice.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline, make_interp_spline

from pyflightstream._errors import InputValueError

from ._airfoils import cst_airfoil, normalized_naca
from ._sections import _chord_frame


def _file_sides(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            row = [float(v) for v in line.replace(",", " ").split()]
        except ValueError:
            continue
        if len(row) == 2:
            rows.append(row)
    p = np.asarray(rows, float)
    if len(p) >= 1 and np.all(p[0] >= 3) and np.all(p[0] == np.floor(p[0])):
        nu, nl = (int(v) for v in p[0])
        if len(p) != 1 + nu + nl:
            raise InputValueError("airfoil.file: Lednicer counts do not match rows")
        upper, lower = p[1 : 1 + nu], p[1 + nu :]
        if upper[0, 0] < upper[-1, 0]:
            upper = upper[::-1]
        if lower[0, 0] > lower[-1, 0]:
            lower = lower[::-1]
        p = np.vstack((upper, lower[1:]))
    return _chord_frame(p, "airfoil.file")[:2]


def _profile(spec):
    if "cst" in spec:
        c = spec["cst"]
        return lambda s: cst_airfoil(
            s * s, c["upper"], c["lower"], c["trailing_edge_thickness"], c["n1"], c["n2"]
        )
    upper, lower = (
        normalized_naca(spec["naca"], 8001)[:2] if "naca" in spec else _file_sides(spec["file"])
    )
    laws = [CubicSpline(np.sqrt(side[:, 0]), side[:, 1]) for side in (upper, lower)]
    return lambda s: tuple(np.column_stack((s * s, law(s))) for law in laws)


def _station_profile(profile, thickness, options):
    dense = np.linspace(0, 1, 4001)
    upper, lower = profile(dense)
    own = float(np.max(upper[:, 1] - lower[:, 1]))
    if own <= 0:
        raise InputValueError(
            "airfoil: upper and lower profiles are swapped or have zero thickness"
        )
    factor = thickness / own if options["thickness_from_t_c"] else 1.0
    target = 0.0 if options["trailing_edge"] == "sharp" else options.get("te_thickness")

    def points(s):
        sides = [np.array(side, copy=True) for side in profile(s)]
        for i, side in enumerate(sides):
            side[:, 1] *= factor
            if target is not None:
                end = profile(np.array([1.0]))[i][0, 1] * factor
                side[:, 1] += side[:, 0] * ((0.5 if i == 0 else -0.5) * target - end)
        return sides

    return points


def centroid(upper, lower):
    """Area centroid of the section, including its straight trailing-edge base."""
    polygon = np.vstack((upper[::-1], lower[1:]))
    q = np.roll(polygon, -1, axis=0)
    cross = polygon[:, 0] * q[:, 1] - q[:, 0] * polygon[:, 1]
    return np.sum((polygon + q) * cross[:, None], axis=0) / (3 * cross.sum())


def fitted_sections(data):
    """Return common-vector side splines, stacking coordinates and fit errors per station."""
    table, options = data["stations"], data["options"]
    profiles = {key: _profile(spec) for key, spec in data["airfoils"].items()}
    sources = [
        _station_profile(profiles[key], tc, options)
        for key, tc in zip(table["airfoil"], table["t_c"], strict=True)
    ]
    validation = np.unique(np.r_[np.linspace(0, 1, 4098), 1 - np.geomspace(2e-8, 0.029, 137)])
    reference = [source(validation) for source in sources]
    count = 33
    while True:
        s = np.unique(np.r_[np.linspace(0, 1, count), 1 - np.geomspace(1e-7, 0.03, 40)])
        fits = [tuple(make_interp_spline(s, side, k=5) for side in source(s)) for source in sources]
        errors = [
            max(
                float(np.linalg.norm(f(validation) - points, axis=1).max())
                for f, points in zip(pair, truth, strict=True)
            )
            for pair, truth in zip(fits, reference, strict=True)
        ]
        if max(errors) <= options["fit_tol_chord"] or count >= 513:
            break
        count = 2 * count - 1
    centers = [centroid(*truth) for truth in reference]
    for i, center in enumerate(centers):
        for j, key in enumerate(("x_ref", "y_ref")):
            if key in table:
                center[j] = table[key][i]
    return fits, centers, errors
