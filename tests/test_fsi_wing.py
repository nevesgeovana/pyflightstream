"""Tier 1: the generic wing as a clamped beam at Omega = 0.

Static aeroelastic response of the project's synthetic NACA 0012 wing
(chord 1 m, span 8 m) under the prescribed elliptical lift of the
steady polar design point (30 m/s, sea level, alpha 6 deg with the
measured slope 4.83/rad). The structural prescription in conftest is
sized for reasonable numbers: tip deflection near 3 percent of the
half span, nose-up tip twist near half a degree, first bending mode
near 3 Hz. Cross-checks run against independent unit-load and torque
quadratures on the same sampled distributions.
"""

import math

import numpy as np
import pytest
from conftest import (
    WING_CHORD_M,
    WING_EA_ARM_FRACTION,
    WING_EI_N_M2,
    WING_GJ_N_M2,
    WING_HALF_SPAN_M,
    WING_I1_KG_M,
    WING_I2_KG_M,
    WING_MU_KG_PER_M,
    elliptical_lift_distribution,
    make_wing_config,
)

from pyflightstream.fsi import beam

RHO_KG_M3 = 1.225
VELOCITY_M_S = 30.0
ALPHA_DEG = 6.0
CL_SLOPE_PER_RAD = 4.83  # measured on 26.120 (steady polar example, HND-016)
WING_AREA_M2 = 8.0


def _design_point_half_lift() -> float:
    q = 0.5 * RHO_KG_M3 * VELOCITY_M_S**2
    cl = CL_SLOPE_PER_RAD * math.radians(ALPHA_DEG)
    return 0.5 * q * WING_AREA_M2 * cl


def _solved_wing():
    cfg = make_wing_config()
    radii = cfg.blade.station_radii_m
    lift = elliptical_lift_distribution(list(radii), _design_point_half_lift(), WING_HALF_SPAN_M)
    torsion = [WING_EA_ARM_FRACTION * WING_CHORD_M * value for value in lift]
    model = beam.build_beam_model(cfg)
    beam.apply_station_loads(model, cfg, flap_load_n_per_m=lift, torsion_moment_n_m_per_m=torsion)
    beam.solve_static(model)
    return cfg, lift, torsion, beam.extract_solution(model, cfg)


def _unit_load_tip_deflection(radii, load, ei) -> float:
    """Independent tip deflection by the unit-load method.

    delta_tip = integral of M(x) (L - x) / EI dx with M(x) the bending
    moment of the piecewise-linear sampled load, on a fine grid.
    Source: standard unit-load (virtual work) method, Gere and Goodno,
    "Mechanics of Materials", 8th ed., Chapter 9.
    """
    fine = np.linspace(radii[0], radii[-1], 8001)
    q = np.interp(fine, radii, load)
    length = radii[-1]
    moment = np.zeros_like(fine)
    for i, x in enumerate(fine):
        outboard = fine >= x
        moment[i] = np.trapezoid(q[outboard] * (fine[outboard] - x), fine[outboard])
    return float(np.trapezoid(moment * (length - fine), fine) / ei)


def test_tip_deflection_reasonable_and_cross_checked():
    cfg, lift, _, solution = _solved_wing()
    tip = solution.flap_deflection_m[-1]
    # Reasonableness band agreed for the case: 2 to 4 percent of the
    # half span, targeted at about 3 percent.
    assert 0.02 * WING_HALF_SPAN_M < tip < 0.04 * WING_HALF_SPAN_M
    analytic = _unit_load_tip_deflection(list(cfg.blade.station_radii_m), lift, WING_EI_N_M2)
    assert tip == pytest.approx(analytic, rel=0.01)


def test_tip_twist_nose_up_and_cross_checked():
    cfg, _, torsion, solution = _solved_wing()
    tip_twist = solution.elastic_twist_rad[-1]
    # Lift at the AC ahead of the EA twists the wing nose up.
    assert tip_twist > 0.0
    assert 0.3 < math.degrees(tip_twist) < 0.8
    # The lumped-torque model has an exact discrete answer:
    # theta_tip = sum(m_i trib_i r_i) / GJ.
    radii = list(cfg.blade.station_radii_m)
    tributary = beam.tributary_lengths(radii)
    discrete = (
        sum(m * t * r for m, t, r in zip(torsion, tributary, radii, strict=True)) / WING_GJ_N_M2
    )
    assert tip_twist == pytest.approx(discrete, rel=1.0e-6)


def test_wing_frequencies_plausible():
    cfg = make_wing_config()
    model = beam.build_beam_model(cfg)
    beam.solve_static(model)
    modal = beam.modal_frequencies(model, cfg, n_modes=4)
    first = {}
    for f, kind in zip(modal.frequencies_rad_per_s, modal.kinds, strict=True):
        first.setdefault(kind, f / (2.0 * math.pi))
    # Light-aircraft orders of magnitude: bending a few Hz, torsion
    # an order above, and the closed forms of the uniform cantilever.
    assert 2.0 < first["flap"] < 4.0
    assert 10.0 < first["torsion"] < 20.0
    flap_exact = (
        1.8751**2
        * math.sqrt(WING_EI_N_M2 / (WING_MU_KG_PER_M * WING_HALF_SPAN_M**4))
        / (2.0 * math.pi)
    )
    torsion_exact = (
        (math.pi / 2.0)
        * math.sqrt(WING_GJ_N_M2 / ((WING_I1_KG_M + WING_I2_KG_M) * WING_HALF_SPAN_M**2))
        / (2.0 * math.pi)
    )
    assert first["flap"] == pytest.approx(flap_exact, rel=0.01)
    assert first["torsion"] == pytest.approx(torsion_exact, rel=0.01)
