"""The lifting surface: planform, section blending and skin patches.

Pipeline role: pure numerical stage of the geometry package. A resolved
lifting-surface component (plain values, metres and degrees) becomes six skin
patches per spanwise bay: upper and lower, fore and aft of the maximum
thickness, and the two halves of the finite trailing-edge base.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar

from ._airfoils import cst_airfoil, naca_to_cst
from ._distributions import (
    blended_section,
    chord_spacing,
    elevate_coefficients,
    planform_values,
)
from ._patch import Patch, interpolate_patch, patch_layout

__all__ = [
    "lifting_patch_grid",
    "lifting_surface",
    "planform_metrics",
    "section_models",
    "section_points",
    "thickness_station",
]


def section_models(sections):
    """Fit a CST model to each section airfoil of a lifting surface at one common degree."""
    models = [
        naca_to_cst(
            name,
            degree=sections["degree"],
            trailing_edge_thickness=sections["trailing_edge_thickness"],
        )
        for name in sections["airfoils"]
    ]
    degree = max(model["degree"] for model in models)
    return [
        {
            **model,
            "upper": elevate_coefficients(model["upper"], degree).tolist(),
            "lower": elevate_coefficients(model["lower"], degree).tolist(),
            "degree": degree,
        }
        for model in models
    ]


def section_points(component, models, eta, x, side):
    """Return model-space points of the blended section at ``eta`` for chord fractions ``x``."""
    section = blended_section(component["sections"], models, eta)
    upper, lower = cst_airfoil(
        x, section["upper"], section["lower"], section["trailing_edge_thickness"]
    )
    local = upper if side == "upper" else lower
    p = planform_values(component, eta)
    angle = np.deg2rad(p["twist"])
    chord = p["chord"]
    dx, dz = (local[..., 0] - 0.25) * chord, local[..., 1] * chord
    xx = p["leading_edge_x"] + 0.25 * chord + dx * np.cos(angle) + dz * np.sin(angle)
    zz = p["leading_edge_z"] - dx * np.sin(angle) + dz * np.cos(angle)
    yy = np.full_like(xx, component["planform"]["span"] / 2 * eta)
    return np.stack((xx, yy, zz), axis=-1)


def thickness_station(component, models, eta):
    """Return the chord fraction of maximum thickness of the blended section at ``eta``."""
    section = blended_section(component["sections"], models, eta)

    def objective(x):
        upper, lower = cst_airfoil(
            x, section["upper"], section["lower"], section["trailing_edge_thickness"]
        )
        return float(lower[1] - upper[1])

    return float(minimize_scalar(objective, bounds=(0.01, 0.9), method="bounded").x)


def lifting_patch_grid(component, models, layout, chord_count=49, span_count=9):
    """Sample the grid of one skin patch family over its span bay, shape (chord, span, 3)."""
    u = np.linspace(0, 1, chord_count)
    grid = []
    for eta in np.linspace(*layout["bay"], span_count):
        family = layout["family"]
        if family.startswith("trailing_"):
            upper = section_points(component, models, eta, np.array([1.0]), "upper")[0]
            lower = section_points(component, models, eta, np.array([1.0]), "lower")[0]
            fraction = u / 2 if family == "trailing_upper" else (1 + u) / 2
            points = (1 - fraction[:, None]) * upper + fraction[:, None] * lower
        else:
            side, region = family.split("_")
            mid = thickness_station(component, models, eta)
            a, b = (0, mid) if region == "fore" else (mid, 1)
            x = chord_spacing(a, b, u)
            points = section_points(component, models, eta, x, side)
        grid.append(points)
    return np.stack(grid, axis=1)


def lifting_surface(component) -> list[Patch]:
    """Return the skin of a lifting-surface component as bicubic patches.

    Parameters
    ----------
    component : dict
        Resolved lifting-surface component (plain values, metres and degrees).

    Returns
    -------
    list of Patch
        The skin patches, six families per spanwise bay.
    """
    models = section_models(component["sections"])
    layout = patch_layout(component["sections"]["eta"], component["planform"]["breaks"])
    return [
        interpolate_patch(
            lifting_patch_grid(component, models, entry),
            family=entry["family"],
            bay=(entry["bay"][0], entry["bay"][1]),
        )
        for entry in layout
    ]


def planform_metrics(component):
    """Return the planform area and mean aerodynamic chord by quadrature of the chord."""

    def chord(eta):
        return float(planform_values(component, eta)["chord"])

    integral = quad(chord, 0, 1, epsabs=1e-11)[0]
    return {
        "area": component["planform"]["span"] * integral,
        "mac": quad(lambda eta: chord(eta) ** 2, 0, 1, epsabs=1e-11)[0] / integral,
    }
