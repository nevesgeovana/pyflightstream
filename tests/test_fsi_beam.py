"""Tier 1: WP3 beam builder against clamped uniform beam analytics.

Verification per DLV-007 Section 7: tip deflection, tip rotation, and
the first flap and torsion frequencies of a clamped uniform beam must
match the closed forms within 1 percent. Analytic sources:

* Static cantilever under uniform load: tip deflection w L^4 / (8 EI)
  and tip slope w L^3 / (6 EI); Gere and Goodno, "Mechanics of
  Materials", 8th ed., Appendix H.
* Tip twist under uniform distributed torque: m L^2 / (2 GJ); torsion
  of a clamped-free uniform shaft, same reference, Chapter 3.
* First flap frequency (1.8751)^2 sqrt(EI / (mu L^4)); Blevins,
  "Formulas for Natural Frequency and Mode Shape", 1979, Table 8-1.
* First torsion frequency (pi / 2) sqrt(GJ / (I_theta L^2)) with
  I_theta = I1 + I2; Blevins, Table 8-17.
"""

import math

import pytest
from conftest import make_uniform_blade_config

from pyflightstream.fsi import beam
from pyflightstream.fsi.beam import station_name

EI = 120.0
GJ = 40.0
MU = 2.0
I1 = 1.0e-3
I2 = 2.0e-4
ROOT = 0.2
TIP = 1.2
L = TIP - ROOT


@pytest.fixture
def cfg():
    return make_uniform_blade_config(
        n_stations=21,
        root_radius_m=ROOT,
        tip_radius_m=TIP,
        mass_per_length_kg_per_m=MU,
        bending_stiffness_n_m2=EI,
        torsion_stiffness_n_m2=GJ,
        inertia_major_kg_m=I1,
        inertia_minor_kg_m=I2,
    )


def test_static_flap_matches_cantilever_analytics(cfg):
    load = 3.0  # uniform distributed flap load [N/m]
    model = beam.build_beam_model(cfg)
    n = len(cfg.blade.station_radii_m)
    beam.apply_station_loads(model, cfg, flap_load_n_per_m=[load] * n)
    beam.solve_static(model)
    solution = beam.extract_solution(model, cfg)

    tip_deflection = solution.flap_deflection_m[-1]
    assert tip_deflection == pytest.approx(load * L**4 / (8.0 * EI), rel=0.01)

    tip_slope = model.nodes[station_name(n - 1)].RZ["structural"]
    assert tip_slope == pytest.approx(load * L**3 / (6.0 * EI), rel=0.01)


def test_static_twist_matches_shaft_analytics(cfg):
    torque = 0.7  # uniform distributed torque [N m / m]
    model = beam.build_beam_model(cfg)
    n = len(cfg.blade.station_radii_m)
    beam.apply_station_loads(model, cfg, torsion_moment_n_m_per_m=[torque] * n)
    beam.solve_static(model)
    solution = beam.extract_solution(model, cfg)

    assert solution.elastic_twist_rad[-1] == pytest.approx(torque * L**2 / (2.0 * GJ), rel=0.01)
    # No flap load was applied: bending stays numerically zero.
    assert abs(solution.flap_deflection_m[-1]) < 1.0e-12


def test_first_flap_and_torsion_frequencies_within_1_percent(cfg):
    model = beam.build_beam_model(cfg)
    beam.solve_static(model)  # assigns the global DOF numbering
    modal = beam.modal_frequencies(model, cfg, n_modes=6)

    omega_flap_exact = 1.8751**2 * math.sqrt(EI / (MU * L**4))
    omega_torsion_exact = (math.pi / 2.0) * math.sqrt(GJ / ((I1 + I2) * L**2))

    first_flap = next(
        f
        for f, kind in zip(modal.frequencies_rad_per_s, modal.kinds, strict=True)
        if kind == "flap"
    )
    first_torsion = next(
        f
        for f, kind in zip(modal.frequencies_rad_per_s, modal.kinds, strict=True)
        if kind == "torsion"
    )
    assert first_flap == pytest.approx(omega_flap_exact, rel=0.01)
    assert first_torsion == pytest.approx(omega_torsion_exact, rel=0.01)


def test_uncoupled_uniform_blade_modes_are_pure(cfg):
    model = beam.build_beam_model(cfg)
    beam.solve_static(model)
    modal = beam.modal_frequencies(model, cfg, n_modes=4)
    for kind, fraction in zip(modal.kinds, modal.flap_mass_fractions, strict=True):
        assert fraction > 0.99 if kind == "flap" else fraction < 0.01


def test_stiffness_scale_factor_scales_frequencies(cfg):
    stiff = cfg.model_copy(update={"stiffness_scale_factor": 4.0})
    model = beam.build_beam_model(cfg)
    beam.solve_static(model)
    model_stiff = beam.build_beam_model(stiff)
    beam.solve_static(model_stiff)
    f_base = beam.modal_frequencies(model, cfg, n_modes=1).frequencies_rad_per_s[0]
    f_stiff = beam.modal_frequencies(model_stiff, stiff, n_modes=1).frequencies_rad_per_s[0]
    # omega scales with sqrt(EI): factor 4 in stiffness doubles it.
    assert f_stiff == pytest.approx(2.0 * f_base, rel=1.0e-6)
