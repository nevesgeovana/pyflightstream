"""Tier 1: WP4 centrifugal loads, inner iteration, and Southwell check.

Verification per DLV-007 Section 7: the frequency sweep versus Omega
must reproduce a straight line in omega_n^2 versus Omega^2, with a
plausible Southwell coefficient (about 1.1 to 1.3 for the first flap
mode, near 1 for the first torsion mode of a thin blade). The torsion
expectation for the propeller moment linearization alone is
S = (I1 - I2) / (I1 + I2).
"""

import pytest
from conftest import make_uniform_blade_config

from pyflightstream.fsi import beam, centrifugal

MU = 2.0
I1 = 1.0e-3
I2 = 2.0e-5  # thin section: I2 << I1 puts the torsion Southwell near 1
ROOT = 0.0
TIP = 1.0


def make_cfg(omega_rad_per_s=0.0, n_stations=15):
    return make_uniform_blade_config(
        n_stations=n_stations,
        root_radius_m=ROOT,
        tip_radius_m=TIP,
        mass_per_length_kg_per_m=MU,
        inertia_major_kg_m=I1,
        inertia_minor_kg_m=I2,
        omega_rad_per_s=omega_rad_per_s,
    )


@pytest.fixture(scope="module")
def campbell():
    """One shared rotor speed sweep (Gate 1 data) for the module."""
    omegas = [0.0, 20.0, 40.0, 60.0, 80.0]
    return centrifugal.campbell_sweep(make_cfg(), omegas, n_modes=6)


def test_axial_tension_matches_closed_form():
    cfg = make_cfg(omega_rad_per_s=50.0)
    tension = centrifugal.axial_tension(cfg)
    radii = cfg.blade.station_radii_m
    omega_sq = 50.0**2
    for r, n_r in zip(radii, tension, strict=True):
        exact = 0.5 * MU * omega_sq * (TIP**2 - r**2)
        assert n_r == pytest.approx(exact, rel=1.0e-12, abs=1.0e-9)
    assert tension[-1] == 0.0


def test_solver_internal_tension_matches_analytic_root_value():
    """FSI-R05: the P-Delta model must build N(r) from the distributed load."""
    cfg = make_cfg(omega_rad_per_s=50.0)
    model = beam.build_beam_model(cfg)
    beam.apply_station_loads(
        model, cfg, axial_load_n_per_m=centrifugal.axial_load_distribution(cfg)
    )
    beam.solve_static(model, p_delta=True)
    root_axial = model.members["B000"].axial(0.0, "structural")
    exact_root_tension = centrifugal.axial_tension(cfg)[0]
    assert abs(root_axial) == pytest.approx(exact_root_tension, rel=0.01)


def test_propeller_moment_drives_toward_flat_pitch():
    cfg = make_cfg(omega_rad_per_s=100.0)
    pitched = cfg.model_copy(deep=True)
    pitched.blade.geometric_pitch_deg = [15.0] * len(cfg.blade.station_radii_m)
    result = centrifugal.solve_rotating_static(pitched)
    # Positive pitch, restoring moment: the elastic twist is nose down.
    assert result.solution.elastic_twist_rad[-1] < 0.0
    assert result.twist_residual_rad < 1.0e-6
    # FSI-R11: the structural nonlinearity converges in a few solves.
    # This synthetic case is deliberately severe (1.6 deg of elastic
    # twist); realistic stiffness ratios settle in 2 to 3.
    assert 2 <= result.inner_solves <= 6


def test_frequencies_rise_with_rotor_speed(campbell):
    for kind in ("flap", "torsion"):
        track = campbell.family_track(kind)
        assert all(b > a for a, b in zip(track, track[1:], strict=False)), kind


def test_southwell_flap_straight_line_and_coefficient(campbell):
    track = campbell.family_track("flap")
    omega_0, coefficient, r_squared = centrifugal.southwell_fit(campbell.omegas_rad_per_s, track)
    assert r_squared > 0.999
    # Plan plausibility band about 1.1 to 1.3 for the first flap mode of
    # a uniform blade; asserted with margin against discretization.
    assert 1.0 < coefficient < 1.4
    # The Southwell line is an approximation: the fitted intercept sits
    # within a few percent of the true rest frequency, not on top of it.
    assert omega_0 == pytest.approx(track[0], rel=0.05)


def test_southwell_torsion_near_inertia_ratio(campbell):
    track = campbell.family_track("torsion")
    _, coefficient, r_squared = centrifugal.southwell_fit(campbell.omegas_rad_per_s, track)
    assert r_squared > 0.999
    expected = (I1 - I2) / (I1 + I2)
    assert coefficient == pytest.approx(expected, rel=0.05)


def test_southwell_fit_rejects_short_sweeps():
    with pytest.raises(ValueError, match="three sweep points"):
        centrifugal.southwell_fit([0.0, 10.0], [27.0, 28.0])
