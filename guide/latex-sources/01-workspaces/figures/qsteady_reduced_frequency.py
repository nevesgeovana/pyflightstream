# Copyright (c) 2026 Geovana Neves. Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). See LICENSE-AND-AUTHORSHIP.md.  # noqa: E501
"""The 1P reduced frequency of the package's generic test blade over J and r/R.

Writes the two figures of Guide 1's quasi-steady part beside this file,
``qsteady_k_vs_J.pdf`` and ``qsteady_k_map_J_r.pdf``, and prints the numbers
the slides quote. Run it from the repository root with the package importable::

    python guide/latex-sources/01-workspaces/figures/qsteady_reduced_frequency.py

The blade is the tier-3 blade of the repository (``30_BLADE.fsm``), defined
by public shape laws (``pyflightstream.qa.geometry.BladeSpec`` with the
parameters its provenance record states): NACA 4409, tip radius 1.8288 m,
hub ratio 0.15, chord over tip radius 0.14 at the root and 0.06 at the tip,
linear in between. The chord is the blade's own law, at 60 stations.

Why not the plan's mesh estimate (``pyflightstream.cases.qsteady.blade_stations``,
the largest width of each of 20 radial bands): this blade is meshed with 12
spanwise sections, so several of the 20 bands hold only part of one section
and read a chord far below the law (0.03 m against 0.14 m at r/R 0.81). The
script prints that comparison; the estimate needs a mesh with more sections
than bands.

With ``J = V / (n D)`` and ``Omega = 2 pi n``, the reduced frequency
``k = Omega c / (2 V_rel)`` becomes::

    k = (pi c / 2R) / sqrt(J^2 + pi^2 (r/R)^2)

so it depends on the advance ratio and the chord alone, never on the speed.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pyflightstream.cases.qsteady import (
    REDUCED_FREQUENCY_LIMIT,
    REDUCED_FREQUENCY_WATCH,
    blade_stations,
    reduced_frequencies,
)
from pyflightstream.qa.geometry import BladeSpec, blade_triangles

HERE = Path(__file__).resolve().parent
#: The tier-3 blade's shape, as its provenance record
#: (tests/tier3_licensed/inputs/geometries/30_BLADE.provenance.toml) states it.
SPEC = BladeSpec(
    naca="4409",
    r_tip_m=1.8288,
    hub_ratio=0.15,
    chord_root_ratio=0.14,
    chord_tip_ratio=0.06,
    advance_ratio_design=1.7,
    beta_75_deg=45.0,
    n_chord=10,
    n_span=12,
)
#: The deck's own colours (shared/preamble-common.tex): CourseBlue, WarmGold, SoftGray.
BLUE, GOLD, GRAY = "#3333B3", "#C89B3C", "#6B7280"
ADVANCE_RATIOS = np.linspace(0.4, 3.0, 53)
STATIONS = 60


def stations() -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return the blade's radii and chords, in metres, from its chord law."""
    fractions = np.linspace(SPEC.hub_ratio, 1.0, STATIONS)
    radii = tuple(float(f) * SPEC.r_tip_m for f in fractions)
    return radii, tuple(SPEC.chord_m(float(f)) for f in fractions)


def at_advance_ratio(radii, chords, advance_ratio):
    """Return the reduced frequencies of every station at one advance ratio."""
    revs_per_s = 1.0  # any speed: k does not depend on it
    diameter = 2.0 * SPEC.r_tip_m
    return reduced_frequencies(
        radii,
        chords,
        omega_rad_s=2.0 * np.pi * revs_per_s,
        velocity_m_per_s=advance_ratio * revs_per_s * diameter,
        source="sections",
    )


def compare_the_mesh_estimate() -> None:
    """Print the plan's mesh estimate of the chord beside the blade's chord law."""
    vertices = blade_triangles(SPEC).reshape(-1, 3)
    radii, chords = blade_stations(vertices, hub=(0.0, 0.0, 0.0), axis=(1.0, 0.0, 0.0))
    print("r/R    mesh_chord_m  law_chord_m")
    for radius, chord in zip(radii, chords, strict=True):
        fraction = radius / SPEC.r_tip_m
        print(f"{fraction:5.3f}  {chord:12.4f}  {SPEC.chord_m(fraction):11.4f}")


def main() -> None:
    """Write both figures and print the numbers the slides quote."""
    radii, chords = stations()
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    rows = [at_advance_ratio(radii, chords, j) for j in ADVANCE_RATIOS]

    fig, ax = plt.subplots(figsize=(4.3, 2.9))
    ax.plot(ADVANCE_RATIOS, [r.k_max for r in rows], color=BLUE, lw=2, label="largest (root)")
    ax.plot(ADVANCE_RATIOS, [r.k_mean for r in rows], color=GOLD, lw=2, label="span-weighted mean")
    for level, style in ((REDUCED_FREQUENCY_LIMIT, "--"), (REDUCED_FREQUENCY_WATCH, ":")):
        ax.axhline(level, color=GRAY, lw=1, ls=style)
        ax.text(2.98, level + 0.003, f"k = {level:g}", color=GRAY, ha="right", va="bottom")
    ax.set_xlabel("advance ratio J")
    ax.set_ylabel("1P reduced frequency k")
    ax.set_xlim(ADVANCE_RATIOS[0], ADVANCE_RATIOS[-1])
    ax.set_ylim(0.0, None)
    ax.grid(True, color="#E5E7EB", lw=0.6)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(HERE / "qsteady_k_vs_J.pdf")
    plt.close(fig)

    span = np.linspace(SPEC.hub_ratio, 1.0, STATIONS)
    grid_j, grid_r = np.meshgrid(ADVANCE_RATIOS, span)
    chord_over_r = np.interp(grid_r * SPEC.r_tip_m, radii, chords) / SPEC.r_tip_m
    k_map = (np.pi * chord_over_r / 2.0) / np.sqrt(grid_j**2 + np.pi**2 * grid_r**2)
    fig, ax = plt.subplots(figsize=(4.3, 2.9))
    filled = ax.contourf(grid_j, grid_r, k_map, levels=12, cmap="Blues")
    lines = ax.contour(
        grid_j,
        grid_r,
        k_map,
        levels=[REDUCED_FREQUENCY_WATCH, REDUCED_FREQUENCY_LIMIT],
        colors=[GOLD, "#111827"],
        linewidths=[1.5, 1.5],
        linestyles=[":", "--"],
    )
    ax.clabel(lines, fmt=lambda v: f"k = {v:g}", fontsize=8)
    fig.colorbar(filled, ax=ax, label="k")
    ax.set_xlabel("advance ratio J")
    ax.set_ylabel("r / R")
    fig.tight_layout()
    fig.savefig(HERE / "qsteady_k_map_J_r.pdf")
    plt.close(fig)

    print("J      k_max   k_mean  span_k>0.1_%  span_k>0.05_%")
    for j in (0.6, 1.0, 1.4, 1.7, 2.2, 3.0):
        row = at_advance_ratio(radii, chords, j)
        above = 100.0 * row.span_fraction_above(REDUCED_FREQUENCY_LIMIT)
        watch = 100.0 * row.span_fraction_above(REDUCED_FREQUENCY_WATCH)
        print(f"{j:4.1f}  {row.k_max:6.3f}  {row.k_mean:6.3f}  {above:12.1f}  {watch:13.1f}")
    compare_the_mesh_estimate()


if __name__ == "__main__":
    main()
