"""Scale, pitch and stack sections, then interpolate their poles radially.

Pipeline role: pure surface construction. Skew rotates the section frame and
rake translates it aft. Neither operation wraps a section onto a cylinder.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.interpolate import make_interp_spline

from ._patch import Patch
from ._propeller_input import axes, offsets
from ._propeller_sections import fitted_sections


@dataclass(frozen=True)
class PropellerGeometry:
    """Numerical surface patches and measurements, with lengths in mm."""

    patches: tuple[Patch, ...]
    info: dict


def _surface(controls, tu, tv, du, dv, family):
    ku, mu = np.unique(tu, return_counts=True)
    kv, mv = np.unique(tv, return_counts=True)
    return Patch(
        family,
        np.asarray(controls),
        tuple(ku),
        tuple(kv),
        tuple(mu),
        tuple(mv),
        du,
        dv,
        role=family,
    )


def section_placement(points, center, r, chord, beta, skew, rake, data):
    """Place section points by the documented scale, pitch, skew, rake sequence."""
    origin, radial, thrust, velocity = axes(data)
    theta, angle = np.deg2rad([skew, beta])
    br = np.cos(theta) * radial - np.sin(theta) * velocity
    tr = np.sin(theta) * radial + np.cos(theta) * velocity
    chord_axis = -np.cos(angle) * tr - np.sin(angle) * thrust
    normal = -np.sin(angle) * tr + np.cos(angle) * thrust
    radius = data["propeller"]["radius"]
    local = (np.asarray(points) - center) * chord * radius
    return (
        origin
        + radius * (r * br - rake * thrust)
        + local[:, :1] * chord_axis
        + local[:, 1:] * normal
    )


def blade_geometry(data):
    """Build the blade through every defining section with a cubic C2 radial loft."""
    table, options, prop = data["stations"], data["options"], data["propeller"]
    fits, centers, errors = fitted_sections(data)
    radial = np.asarray(table["r_R"], float)
    beta = np.asarray(table["beta_deg"], float)
    offset = prop["pitch_setting"] - float(
        make_interp_spline(radial, beta)(prop["pitch_reference_r_R"])
    )
    beta += offset
    skew, rake = offsets(data)
    rows = [[], []]
    stacking = []
    for i, r in enumerate(radial):
        args = (centers[i], r, table["c_R"][i], beta[i], skew[i], rake[i], data)
        stacking.append(section_placement(np.array([centers[i]]), *args)[0])
        for j in (0, 1):
            rows[j].append(section_placement(fits[i][j].c, *args))
    if "root_extension_r_R" in options:
        inner = options["root_extension_r_R"]
        delta = (inner - radial[0]) * prop["radius"]
        _, br, _, tr = axes(data)
        br = np.cos(np.deg2rad(skew[0])) * br - np.sin(np.deg2rad(skew[0])) * tr
        for side in rows:
            side.insert(0, side[0] + delta * br)
        stacking.insert(0, stacking[0] + delta * br)
        radial = np.r_[inner, radial]
    poles = [make_interp_spline(radial, side, k=3) for side in rows]
    tu, tv = fits[0][0].t, poles[0].t
    patches = [
        _surface(p.c.transpose(1, 0, 2), tu, tv, 5, 3, role)
        for p, role in zip(poles, ("upper", "lower"), strict=True)
    ]
    if options["trailing_edge"] != "sharp":
        te = np.stack((patches[1].controls[-1], patches[0].controls[-1]), axis=0)
        patches.append(_surface(te, [0, 0, 1, 1], tv, 1, 3, "trailing_edge"))
    for end, key in ((0, "root_cap"), (-1, "tip")):
        if options[key] == "planar":
            cap = np.stack((patches[1].controls[:, end], patches[0].controls[:, end]), axis=1)
            patches.append(_surface(cap, tu, [0, 0, 1, 1], 5, 1, key))
    return PropellerGeometry(
        tuple(patches),
        {
            "r_R": radial.tolist(),
            "beta_deg": beta.tolist(),
            "pitch_offset_deg": offset,
            "skew_deg": skew.tolist(),
            "rake_x_R": rake.tolist(),
            "section_fit": errors,
            "stacking_mm": np.asarray(stacking).tolist(),
        },
    )


def rotor_geometry(data, blade):
    """Rotate copies about the shaft in its declared sense, without refitting."""
    origin, radial, _, velocity = axes(data)
    shaft = np.cross(radial, velocity)
    cross = np.array([[0, -shaft[2], shaft[1]], [shaft[2], 0, -shaft[0]], [-shaft[1], shaft[0], 0]])
    patches = []
    for i in range(data["propeller"]["blades"]):
        angle = 2 * np.pi * i / data["propeller"]["blades"]
        rotation = np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross
        for patch in blade.patches:
            net = (patch.controls - origin) @ rotation.T + origin
            patches.append(replace(patch, controls=net, family=f"blade_{i + 1}_{patch.family}"))
    return PropellerGeometry(tuple(patches), dict(blade.info))
