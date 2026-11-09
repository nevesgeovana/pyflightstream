"""Tip caps and the root fillet of a lifting surface.

Pipeline role: pure numerical stage of the geometry package. The tip cap
closes the wing tip (flat, rounded, ridged or none); the root fillet blends
the skin into a host surface given as a signed distance and a unit normal.
The ridged cap is a superellipse rounding whose start, ridge height and
exponent follow a profile given per chord station.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from pyflightstream._errors import InputValueError

from ._airfoils import cst_airfoil
from ._distributions import blended_section, chord_spacing, planform_values
from ._lifting import section_models, thickness_station
from ._patch import Patch, interpolate_patch

__all__ = [
    "CAP_NOSE_LENGTH",
    "CAP_NOSE_RATIO",
    "CAP_TE_TAPER",
    "cap_patch_grids",
    "cap_plane_grids",
    "cap_rates",
    "cap_taper",
    "cap_to_space",
    "contour_segment",
    "coons_grid",
    "fillet_arc",
    "fillet_contact",
    "junction_normal",
    "map_cap_grid",
    "ridge_arc",
    "ridge_cross",
    "ridge_profile",
    "ridged_cap_grids",
    "root_fillet",
    "rounded_cap_grids",
    "tip_cap",
    "wing_contour_normal",
    "wing_contour_point",
]


def contour_segment(section, maximum, index, u):
    """Six oriented boundary curves, beginning at the leading edge."""
    u = np.asarray(u)
    if index in (0, 1, 4, 5):
        a, b, side = [
            (0, maximum, 0),
            (maximum, 1, 0),
            (0, 0, 0),
            (0, 0, 0),
            (1, maximum, 1),
            (maximum, 0, 1),
        ][index]
        x = chord_spacing(a, b, u)
        return cst_airfoil(
            x, section["upper"], section["lower"], section["trailing_edge_thickness"]
        )[side]
    te = section["trailing_edge_thickness"]
    z = (1 - u) * te / 2 if index == 2 else -u * te / 2
    return np.stack((np.ones_like(u), z), axis=-1)


def coons_grid(bottom, top, left, right):
    """Return the Coons blend of four boundary curves, minus the bilinear corner term."""
    u, v = (
        np.linspace(0, 1, len(bottom))[:, None, None],
        np.linspace(0, 1, len(left))[None, :, None],
    )
    ruled = (
        (1 - v) * bottom[:, None] + v * top[:, None] + (1 - u) * left[None, :] + u * right[None, :]
    )
    bilinear = (
        (1 - u) * (1 - v) * bottom[0]
        + u * (1 - v) * bottom[-1]
        + (1 - u) * v * top[0]
        + u * v * top[-1]
    )
    return ruled - bilinear


def cap_plane_grids(section, maximum):
    """Return the planar grids of a flat tip cap: six edge strips and three interior patches."""
    u, v = np.linspace(0, 1, 49), np.linspace(0, 1, 9)
    up, low = cst_airfoil(
        maximum, section["upper"], section["lower"], section["trailing_edge_thickness"]
    )
    centre = (up + low) / 2
    outer = [contour_segment(section, maximum, i, u) for i in range(6)]
    inner = [0.55 * edge + 0.45 * centre for edge in outer]
    annulus = [
        (1 - v[None, :, None] ** 2) * edge[:, None] + v[None, :, None] ** 2 * inside[:, None]
        for edge, inside in zip(outer, inner, strict=True)
    ]
    interior = []
    for i in (0, 2, 4):
        first, second = inner[i], inner[i + 1]
        bottom = (1 - u[:, None]) * centre + u[:, None] * first[0]
        left = (1 - u[:, None]) * centre + u[:, None] * second[-1]
        interior.append(coons_grid(bottom, second[::-1], left, first))
    return annulus + interior


def map_cap_grid(component, grid):
    """Place a planar section-frame cap grid (x, z in unit chord) in model space."""
    return cap_to_space(component, grid[..., 0], grid[..., 1], np.zeros_like(grid[..., 0]))


CAP_TE_TAPER = (
    0.03  # chord fraction over which the rounded-cap ridge falls to the trailing-edge base plane
)
CAP_NOSE_RATIO = 0.3  # ridge height at the leading-edge point as a fraction of the cap length
CAP_NOSE_LENGTH = (
    0.15  # chord fraction over which the ridge rises from the nose height to the cap length
)


def cap_to_space(component, x, z, extension, rates=(0.0, 0.0)):
    """Map section (x, z) and a spanwise extension, all in unit chord, to model space."""
    p = planform_values(component, 1.0)
    angle, chord = np.deg2rad(p["twist"]), p["chord"]
    dx, dz = (x - 0.25) * chord, z * chord
    return np.stack(
        (
            p["leading_edge_x"]
            + 0.25 * chord
            + dx * np.cos(angle)
            + dz * np.sin(angle)
            + rates[0] * chord * extension,
            component["planform"]["span"] / 2 + chord * extension,
            p["leading_edge_z"]
            - dx * np.sin(angle)
            + dz * np.cos(angle)
            + rates[1] * chord * extension,
        ),
        axis=-1,
    )


def rounded_cap_grids(component, section, maximum, chord_count=49, across_count=17):
    """Four ridge patches of the rounded tip cap: upper fore, upper aft, lower fore, lower aft.

    Across the local thickness the cap is a half ellipse of shape exponent e: the
    spanwise extension is r(x)*sin(phi)**e with z = middle +- half*cos(phi). The
    ridge height r is the cap length (multiple times the half thickness at the
    maximum-thickness station of the tip section), constant along the chord and
    falling smoothly to zero over the last CAP_TE_TAPER of the chord, so the
    finite trailing-edge thickness is closed on the base plane. Patches continue
    the chordwise splits of the skin and meet on the ridge. Each is a true
    quadrilateral: the rim side lies on the skin tip edge, the radial sides are
    half ellipses and the fourth side is the ridge, which stands above the
    leading-edge point so no side has zero length.
    """
    upper_max, lower_max = cst_airfoil(
        maximum, section["upper"], section["lower"], section["trailing_edge_thickness"]
    )
    length = (upper_max[1] - lower_max[1]) / 2 * component["tip_cap"]["length"]
    exponent = component["tip_cap"]["exponent"]
    u, v = np.linspace(0, 1, chord_count), np.linspace(0, 1, across_count)
    grids = []
    for a, b, side in [(0, maximum, 1), (maximum, 1, 1), (0, maximum, -1), (maximum, 1, -1)]:
        x = chord_spacing(a, b, u)
        upper, lower = cst_airfoil(
            x, section["upper"], section["lower"], section["trailing_edge_thickness"]
        )
        middle, half = (upper[:, 1] + lower[:, 1]) / 2, (upper[:, 1] - lower[:, 1]) / 2
        s = np.clip((x - (1 - CAP_TE_TAPER)) / CAP_TE_TAPER, 0, 1)
        rise = np.clip(1 - x / CAP_NOSE_LENGTH, 0, 1)
        ridge = length * (1 - (3 * s**2 - 2 * s**3)) * (1 - (1 - CAP_NOSE_RATIO) * rise**2)
        phi = np.pi / 2 * (v if side > 0 else 1 - v)
        z = middle[:, None] + side * half[:, None] * np.cos(phi)[None, :]
        extension = ridge[:, None] * np.sin(phi)[None, :] ** exponent
        grids.append(cap_to_space(component, np.repeat(x[:, None], len(v), 1), z, extension))
    return grids


def cap_rates(component):
    """Planform rates at the tip per unit of spanwise extension.

    Returns (chord loss, leading-edge sweep, leading-edge rise).

    The cap sections follow the extended planform: the leading edge continues its sweep and rise and
    the trailing edge continues the taper.
    """
    inner = 1 - 1e-3
    a, b = (planform_values(component, eta) for eta in (inner, 1.0))
    run = 1e-3 * component["planform"]["span"] / 2
    return (
        float((a["chord"] - b["chord"]) / run),
        float((b["leading_edge_x"] - a["leading_edge_x"]) / run),
        float((b["leading_edge_z"] - a["leading_edge_z"]) / run),
    )


def cap_taper(component):
    """Chord loss per unit of spanwise extension at the tip."""
    return cap_rates(component)[0]


def ridge_profile(profile, x):
    """Return start of the rounding, ridge height and exponent at chord fractions ``x``.

    Interpolation is PCHIP in the square root of the chord fraction; heights are in chord units.
    """
    knots, s = np.sqrt(profile["stations"]), np.sqrt(np.asarray(x, float))
    return tuple(
        PchipInterpolator(knots, profile[key])(s) for key in ("start", "ridge", "exponent")
    )


def ridge_arc(start, ridge, exponent, half, count):
    """Superellipse from the end of the straight rim (start, +half) to the ridge (ridge, 0).

    Arrays over chord stations. Returns (stations, count, 2) of (spanwise, vertical offset from the
    camber point), both in chord units: |z/half|**n + |(e-start)/(ridge-start)|**n = 1.
    """
    phi = np.linspace(0, np.pi / 2, count)[None, :]
    n = np.asarray(exponent)[:, None]
    e = np.asarray(start)[:, None] + (np.asarray(ridge) - np.asarray(start))[:, None] * np.sin(
        phi
    ) ** (2 / n)
    z = np.asarray(half)[:, None] * np.cos(phi) ** (2 / n)
    return np.stack((e, z), axis=-1)


def ridge_cross(start, ridge, exponent, half, count=33, fine=400):
    """Return the rim-to-ridge cross curve, a straight rim then an arc, at equal arc length.

    The result has shape (stations, count, 2).
    """
    arc = ridge_arc(start, ridge, exponent, half, fine)
    out = np.empty((len(arc), count, 2))
    for i, a in enumerate(arc):
        line = np.stack(
            (np.linspace(0, start[i], 40, endpoint=False), np.full(40, half[i])), axis=-1
        )
        curve = np.concatenate((line, a))
        length = np.concatenate(([0.0], np.cumsum(np.linalg.norm(np.diff(curve, axis=0), axis=1))))
        target = np.linspace(0, length[-1], count)
        out[i] = np.stack([np.interp(target, length, curve[:, k]) for k in range(2)], axis=-1)
    return out


def ridged_cap_grids(component, section, maximum, chord_count=49, across_count=65):
    """Return four cap patches (upper, lower, fore, aft of the thickness station) and two closures.

    The tip section is extended straight to the start of the rounding, then closed by a superellipse
    whose spanwise reach, start and exponent follow the identified profile. The ridge lies on the
    camber line. The closures are the planar slivers at the trailing edge, each a four-sided patch
    (rim half, rim line, arc, camber line).
    """
    profile = component["tip_cap"]["profile"]
    taper, sweep, rise = cap_rates(component)
    grids = []
    for a, b, side in [(0, maximum, 1), (maximum, 1, 1), (0, maximum, -1), (maximum, 1, -1)]:
        u = np.linspace(0, 1, chord_count)
        x = chord_spacing(a, b, u)
        upper, lower = cst_airfoil(
            x, section["upper"], section["lower"], section["trailing_edge_thickness"]
        )
        middle, half = (upper[:, 1] + lower[:, 1]) / 2, (upper[:, 1] - lower[:, 1]) / 2
        start, ridge, exponent = ridge_profile(profile, x)
        cross = ridge_cross(start, ridge, exponent, half, across_count)
        if side < 0:
            cross = cross[:, ::-1]
        z = middle[:, None] + side * cross[..., 1]
        grids.append(
            (
                "tip_cap",
                cap_to_space(
                    component,
                    np.repeat(x[:, None], across_count, 1) * (1 - taper * cross[..., 0]),
                    z,
                    cross[..., 0],
                    (sweep, rise),
                ),
            )
        )
    upper, lower = cst_airfoil(
        np.array([1.0]), section["upper"], section["lower"], section["trailing_edge_thickness"]
    )
    middle, half = float((upper[0, 1] + lower[0, 1]) / 2), float((upper[0, 1] - lower[0, 1]) / 2)
    start, ridge, exponent = (float(v[0]) for v in ridge_profile(profile, [1.0]))
    arc = ridge_arc([start], [ridge], [exponent], [half], 65)[0]
    for side in (1, -1):
        bottom = np.stack((np.linspace(0, ridge, 65), np.zeros(65)), axis=-1)
        top = np.stack((np.linspace(0, start, 65), np.full(65, half)), axis=-1)
        left = np.stack((np.zeros(65), np.linspace(0, half, 65)), axis=-1)
        right = arc[::-1]
        plane = coons_grid(bottom, top, left, right)
        e, z = plane[..., 0], middle + side * plane[..., 1]
        grids.append(
            ("tip_te_closure", cap_to_space(component, 1 - taper * e, z, e, (sweep, rise)))
        )
    return grids


def cap_patch_grids(component, section, maximum):
    """[(family, grid)] of the whole tip cap in model space; flat caps keep the planar layout."""
    kind = component["tip_cap"]["kind"]
    if kind == "none":
        return []
    if kind == "ridged":
        return ridged_cap_grids(component, section, maximum)
    if kind == "rounded":
        return [("tip_cap", grid) for grid in rounded_cap_grids(component, section, maximum)]
    return [
        ("tip_cap", map_cap_grid(component, grid)) for grid in cap_plane_grids(section, maximum)
    ]


def tip_cap(component) -> list[Patch]:
    """Return the tip cap of a lifting-surface component as bicubic patches.

    The list is empty for the kind ``none``.

    Parameters
    ----------
    component : dict
        Resolved lifting-surface component, whose ``tip_cap`` entry names the kind.

    Returns
    -------
    list of Patch
        The cap patches; empty when the kind is ``none``.
    """
    if component["tip_cap"]["kind"] == "none":
        return []
    models = section_models(component["sections"])
    section = blended_section(component["sections"], models, 1.0)
    maximum = thickness_station(component, models, 1.0)
    return [
        interpolate_patch(grid, family=family)
        for family, grid in cap_patch_grids(component, section, maximum)
    ]


def wing_contour_point(component, models, maximum, index, u, eta):
    """Return the model-space point of a contour segment at parameter ``u`` and span ``eta``."""
    section = blended_section(component["sections"], models, eta)
    point = contour_segment(section, maximum, index, np.asarray(u))
    p = planform_values(component, eta)
    angle, chord = np.deg2rad(p["twist"]), p["chord"]
    dx, dz = (point[0] - 0.25) * chord, point[1] * chord
    return np.array(
        [
            p["leading_edge_x"] + 0.25 * chord + dx * np.cos(angle) + dz * np.sin(angle),
            component["planform"]["span"] / 2 * eta,
            p["leading_edge_z"] - dx * np.sin(angle) + dz * np.cos(angle),
        ]
    )


def wing_contour_normal(component, models, maximum, index, u, eta):
    """Return the unit surface normal of a contour segment at parameter ``u`` and span ``eta``."""

    def point(a, b):
        return wing_contour_point(component, models, maximum, index, a, b)

    tangent = point(min(1.0, u + 1e-5), eta) - point(max(0.0, u - 1e-5), eta)
    spanwise = point(u, min(1.0, eta + 1e-5)) - point(u, max(0.0, eta - 1e-5))
    normal = np.cross(tangent, spanwise)
    return normal / np.linalg.norm(normal)


def junction_normal(component, models, maximum, index, u, eta):
    """Return the contour normal, averaged with the neighbour segment at a segment end."""
    normal = wing_contour_normal(component, models, maximum, index, u, eta)
    if u in (0.0, 1.0):
        other = ((index - 1) % 6, 1.0) if u == 0 else ((index + 1) % 6, 0.0)
        normal += wing_contour_normal(component, models, maximum, other[0], other[1], eta)
        normal /= np.linalg.norm(normal)
    return normal


def fillet_contact(component, models, maximum, index, u, radius, host_distance):
    """Find the root contact point and normal where a ball of ``radius`` touches the host."""

    def normal(eta):
        return junction_normal(component, models, maximum, index, u, eta)

    def point(eta):
        return wing_contour_point(component, models, maximum, index, u, eta)

    def equation(eta):
        return host_distance(point(eta) + radius * normal(eta)) - radius

    eta = brentq(equation, 0, 1, xtol=1e-14)
    return point(eta), normal(eta)


def fillet_arc(point, normal, radius, v, host_normal):
    """Return the fillet arc from the contact point to the host, sampled at ``v`` in [0, 1]."""
    angle = np.arccos(np.clip(normal @ host_normal, -1, 1))
    direction = (
        np.sin((1 - v) * angle)[:, None] * normal + np.sin(v * angle)[:, None] * host_normal
    ) / np.sin(angle)
    return point + radius * normal - radius * direction


def root_fillet(
    component, host_distance=lambda p: p[1], host_normal=lambda p: np.array([0.0, 1.0, 0.0])
):
    """Fillet a supplied host surface given by distance and outward unit normal.

    Host functions must represent signed Euclidean distance and its gradient.
    Their default is the plane y=0. No host is read from an original geometry.
    """
    models = section_models(component["sections"])
    section = blended_section(component["sections"], models, 0.0)
    maximum = thickness_station(component, models, 0.0)
    u, v = np.linspace(0, 1, 49), np.linspace(0, 1, 9)
    patches = []
    for i in range(6):
        grid = []
        for station in u:
            x = contour_segment(section, maximum, i, np.asarray(station))[0]
            radius = float(np.interp(x, [0, maximum, 1], component["root_fillet"]["radii"]))
            if radius <= 0:
                raise InputValueError("root_fillet.radii: enabled fillet requires positive radii")
            point, normal = fillet_contact(
                component, models, maximum, i, station, radius, host_distance
            )
            centre = point + radius * normal
            grid.append(fillet_arc(point, normal, radius, v, host_normal(centre)))
        patches.append(interpolate_patch(grid, family="root_fillet"))
    return patches
