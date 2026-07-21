"""Shared tier 1 fixtures: synthetic blade definitions for the FSI suite.

Synthetic blades generated here are the only blade definitions in the
repository (DLV-007 Sections 1 and 8): real blade property sets are
research data and never enter Git (NFR-08). The uniform blade has
closed-form clamped-beam answers, which the WP3 and WP4 benchmarks
compare against.
"""

import pytest

from pyflightstream.fsi.config import BladeProperties, FsiConfig


def make_uniform_blade_config(
    n_stations: int = 11,
    root_radius_m: float = 0.2,
    tip_radius_m: float = 1.2,
    chord_m: float = 0.1,
    mass_per_length_kg_per_m: float = 2.0,
    bending_stiffness_n_m2: float = 120.0,
    torsion_stiffness_n_m2: float = 40.0,
    inertia_major_kg_m: float = 1.0e-3,
    inertia_minor_kg_m: float = 2.0e-4,
    omega_rad_per_s: float = 0.0,
    blade_count: int = 2,
) -> FsiConfig:
    """Build a uniform synthetic blade with analytically known answers.

    The blade is a clamped uniform beam of length L = tip - root with
    constant EI, GJ, and mu, zero elastic axis and CG offsets, and zero
    geometric pitch, so tip deflection, tip rotation, and the first
    modal frequencies have textbook closed forms.
    """
    n = n_stations
    step = (tip_radius_m - root_radius_m) / (n - 1)
    radii = [root_radius_m + i * step for i in range(n)]
    blade = BladeProperties(
        station_radii_m=radii,
        chord_m=[chord_m] * n,
        mass_per_length_kg_per_m=[mass_per_length_kg_per_m] * n,
        inertia_major_kg_m=[inertia_major_kg_m] * n,
        inertia_minor_kg_m=[inertia_minor_kg_m] * n,
        bending_stiffness_n_m2=[bending_stiffness_n_m2] * n,
        torsion_stiffness_n_m2=[torsion_stiffness_n_m2] * n,
        elastic_axis_offset_chordwise_m=[0.0] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[0.0] * n,
    )
    return FsiConfig(
        blade_count=blade_count,
        omega_rad_per_s=omega_rad_per_s,
        blade=blade,
    )


@pytest.fixture
def uniform_blade_config() -> FsiConfig:
    """Default uniform synthetic blade (see make_uniform_blade_config)."""
    return make_uniform_blade_config()
