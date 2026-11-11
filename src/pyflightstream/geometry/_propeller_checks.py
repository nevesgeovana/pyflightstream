"""Measured numerical checks and classical integral measures of a propeller.

Pipeline role: report source fits, placement, loft and edge closure without a
kernel. Written trim curves and sewn topology are checked by workspace stages.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import BSpline, CubicSpline

from ._propeller_input import axes
from ._records import check_entry


def measured(name, value, limit, unit="", *, bound="max", note=""):
    within = value <= limit if bound == "max" else value >= limit
    return check_entry(
        name,
        "passed" if within else "failed",
        float(value),
        float(limit),
        unit=unit,
        bound=bound,
        note=note,
    )


def evaluate(patch, u, v):
    """Evaluate matching lists of patch parameters, with no resampling or fitting."""
    net = patch.controls
    bu = BSpline(
        np.repeat(patch.knots_u, patch.multiplicities_u), np.eye(net.shape[0]), patch.degree_u
    )
    bv = BSpline(
        np.repeat(patch.knots_v, patch.multiplicities_v), np.eye(net.shape[1]), patch.degree_v
    )
    return np.einsum("...i,...j,ijc->...c", bu(u), bv(v), net)


def boundary_counts(patches, tolerance=1e-6):
    """Count unmatched and multiply shared nondegenerate exact patch edges in mm."""
    edges = []
    for patch in patches:
        u = np.linspace(patch.knots_u[0], patch.knots_u[-1], 129)
        v = np.linspace(patch.knots_v[0], patch.knots_v[-1], 129)
        for points in (
            evaluate(patch, u, v[0]),
            evaluate(patch, u, v[-1]),
            evaluate(patch, u[0], v),
            evaluate(patch, u[-1], v),
        ):
            if np.max(np.linalg.norm(points - points[0], axis=1)) > tolerance:
                edges.append(points)
    counts = []
    for i, edge in enumerate(edges):
        count = sum(
            min(
                np.max(np.linalg.norm(edge - other, axis=1)),
                np.max(np.linalg.norm(edge - other[::-1], axis=1)),
            )
            <= tolerance
            for other in edges[i + 1 :]
        )
        if not any(
            min(
                np.max(np.linalg.norm(edge - other, axis=1)),
                np.max(np.linalg.norm(edge - other[::-1], axis=1)),
            )
            <= tolerance
            for other in edges[:i]
        ):
            counts.append(1 + count)
    return int(sum(n == 1 for n in counts)), int(sum(n > 2 for n in counts))


def design_report(data, blade):
    """Return classical disk solidity, activity factor, pitch and measured geometry checks."""
    table, prop, info = data["stations"], data["propeller"], blade.info
    r = np.asarray(table["r_R"])
    chord = CubicSpline(r, table["c_R"])
    beta = CubicSpline(r, table["beta_deg"])
    shift = prop["pitch_setting"] - beta(prop["pitch_reference_r_R"])
    beta_ref = float(beta(prop["pitch_reference_r_R"]) + shift)
    # Six point Gauss integrates the degree-six product chord(r) r^3 exactly on each bay.
    nodes, weights = np.polynomial.legendre.leggauss(6)
    integral = 0.0
    for a, b in zip(r, r[1:], strict=False):
        x = (a + b) / 2 + (b - a) * nodes / 2
        integral += (b - a) / 2 * np.sum(weights * chord(x) * x**3)
    af = float(1e5 / 32 * integral)
    disk = float(prop["blades"] * chord.integrate(r[0], r[-1]) / np.pi)
    origin, radial, thrust, velocity = axes(data)
    # Measure a defining station; a skewed loft need not stay planar between stations.
    station = int(np.argmin(np.abs(r - prop["pitch_reference_r_R"])))
    eta = r[station]
    theta = np.deg2rad(info["skew_deg"][station])
    tr = np.sin(theta) * radial + np.cos(theta) * velocity
    br = np.cos(theta) * radial - np.sin(theta) * velocity
    upper, lower = blade.patches[:2]
    le, te = evaluate(upper, 0, eta), evaluate(upper, 1, eta)
    leads = float((le - te) @ tr)
    bulge = float((evaluate(upper, 0.55, eta) - evaluate(lower, 0.55, eta)) @ thrust)
    plane = max(
        abs(float((evaluate(p, u, eta) - origin) @ br) - prop["radius"] * eta)
        for p in (upper, lower)
        for u in (0, 0.31, 1)
    )
    free, triple = boundary_counts(blade.patches)
    expected_free = (2 + (not info["sharp_te"])) * sum(
        data["options"][key] == "none" for key in ("root_cap", "tip")
    )
    checks = [
        measured(
            "propeller.section_fit",
            max(info["section_fit"]),
            data["options"]["fit_tol_chord"],
            "chord",
        ),
        measured("propeller.section_plane", plane, 1e-8, "mm"),
        measured("propeller.handedness", int(leads <= 0) + int(bulge <= 0), 0, "violations"),
        measured("propeller.solidity", disk, 0, bound="min", note="positive disk area ratio"),
        measured("propeller.activity_factor", af, 0, bound="min"),
        measured("propeller.beta_reference", abs(beta_ref - prop["pitch_setting"]), 1e-10, "deg"),
        measured(
            "propeller.beta_0p7R",
            float(beta(0.7) + shift),
            -90,
            "deg",
            bound="min",
            note="beta from plane; upper bound checked at input",
        ),
        measured("propeller.closure", abs(free - expected_free) + triple, 0, "edges"),
    ]
    return {
        "ok": all(c["status"] == "passed" for c in checks),
        "checks": checks,
        "section_fit": {"max_err_chord": max(info["section_fit"])},
        "pitch": {"beta_at_reference_deg": beta_ref, "beta_0p7R_deg": float(beta(0.7) + shift)},
        "solidity": {
            "disk": disk,
            "local_0p7R": float(prop["blades"] * chord(0.7) / (2 * np.pi * 0.7)),
        },
        "activity_factor": {"per_blade": af, "total": prop["blades"] * af},
        "handedness": {
            "ok": leads > 0 and bulge > 0,
            "omega_axis": np.cross(radial, velocity).tolist(),
            "le_leads_rotation": leads > 0,
            "suction_faces_thrust": bulge > 0,
        },
        "closure": {
            "free_edges": free,
            "expected_open_edges": int(expected_free),
            "triple_edges": triple,
        },
        "stacking": {"skew_deg": info["skew_deg"], "rake_x_R": info["rake_x_R"]},
    }
