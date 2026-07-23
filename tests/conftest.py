"""Shared tier 1 fixtures: registry hygiene and the FSI synthetic blades.

Registry hygiene (D1d adoption of the 2026-07-23 library review,
pyvista conftest discipline): every module-level registry or cached
mutable default a test could touch is snapshotted before each test and
restored after it, so a mutating test can never leak state into its
neighbors. The snapshot list below is the inventory of such state; a
new module-level registry joins it in the same commit that creates it.

Synthetic blades generated here are the only blade definitions in the
repository (DLV-007 Sections 1 and 8): real blade property sets are
research data and never enter Git (NFR-08). The uniform blade has
closed-form clamped-beam answers, which the WP3 and WP4 benchmarks
compare against.
"""

import pytest

from pyflightstream import versions as _versions
from pyflightstream.cases import matrix as _matrix
from pyflightstream.commands import CommandRegistry
from pyflightstream.fsi.config import BladeProperties, FsiConfig
from pyflightstream.qa import physics as _physics
from pyflightstream.qa import specs as _specs
from pyflightstream.script import entities as _entities
from pyflightstream.script import solver_setup as _solver_setup


def _mutable_module_state() -> list[dict]:
    """Enumerate every module-level mutable registry or cached default.

    The list is the single inventory of test-mutable module state:
    public case and spec registries, private derived mappings, and the
    mutable objects held by the two lru caches (the loaded command
    database and the manual-edition map), which would otherwise carry a
    test's mutation for the rest of the session.
    """
    return [
        _physics.PHYSICS_CASES,
        _physics.SMI_CASES,
        _specs.PROBE_SPECS,
        _solver_setup._SPEC_BY_COMMAND,
        _matrix._SWEEP_CODES,
        _entities._NOUNS,
        # Cached mutable objects: the cache keeps returning the same
        # dict, so an in-place mutation outlives the test that made it.
        CommandRegistry.load().commands,
        _versions.manual_editions(),
    ]


@pytest.fixture(autouse=True)
def _restore_module_registries():
    """Snapshot and restore the module registries around every test."""
    live = _mutable_module_state()
    saved = [dict(state) for state in live]
    yield
    for state, snapshot in zip(live, saved, strict=True):
        if state != snapshot:
            state.clear()
            state.update(snapshot)


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


# Structural prescription of the project's generic wing (the synthetic
# NACA 0012 of qa.geometry: chord 1 m, span 8 m, AR 8) as a clamped
# semi-wing beam, sized so the static response at the steady polar
# design point is reasonable for a light aircraft wing: EI gives about
# 3 percent of the half span in tip deflection, GJ about half a degree
# of nose-up tip twist through the AC to EA arm, and the mass numbers
# put the first bending mode near 3 Hz. All values synthetic.
WING_HALF_SPAN_M = 4.0
WING_CHORD_M = 1.0
WING_EI_N_M2 = 6.0e4
WING_GJ_N_M2 = 3.0e4
WING_MU_KG_PER_M = 8.0
WING_I1_KG_M = 0.45
WING_I2_KG_M = 0.05
WING_EA_ARM_FRACTION = 0.15  # AC at 25 percent chord, EA at 40 percent


def make_wing_config(n_stations: int = 21) -> FsiConfig:
    """Build the generic wing semi-span as an FsiConfig at Omega = 0.

    With Omega = 0 the blade machinery reduces to a classic clamped
    cantilever wing: no centrifugal tension, no propeller moment; the
    CG offsets are inert and left zero. blade_count 2 stands for the
    two half wings, solved once by symmetry.
    """
    n = n_stations
    step = WING_HALF_SPAN_M / (n - 1)
    radii = [i * step for i in range(n)]
    blade = BladeProperties(
        station_radii_m=radii,
        chord_m=[WING_CHORD_M] * n,
        mass_per_length_kg_per_m=[WING_MU_KG_PER_M] * n,
        inertia_major_kg_m=[WING_I1_KG_M] * n,
        inertia_minor_kg_m=[WING_I2_KG_M] * n,
        bending_stiffness_n_m2=[WING_EI_N_M2] * n,
        torsion_stiffness_n_m2=[WING_GJ_N_M2] * n,
        elastic_axis_offset_chordwise_m=[0.0] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[0.0] * n,
    )
    return FsiConfig(blade_count=2, omega_rad_per_s=0.0, blade=blade)


def elliptical_lift_distribution(
    radii: list[float], half_wing_lift_n: float, half_span_m: float
) -> list[float]:
    """Sample the elliptical lift distribution at the stations [N/m].

    L'(y) = L0 sqrt(1 - (y / L)^2) with L0 = 4 W / (pi L), so the
    distribution integrates to the half-wing lift W over the half span.
    """
    import math

    peak = 4.0 * half_wing_lift_n / (math.pi * half_span_m)
    return [peak * math.sqrt(max(0.0, 1.0 - (r / half_span_m) ** 2)) for r in radii]
