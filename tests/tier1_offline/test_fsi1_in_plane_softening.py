"""Tier 1: the in-plane centrifugal softening of the flap (FSI-1 of 0.30.0).

The flap degree of freedom lies along the section normal, which the node
embedding turns by the blade angle beta. A flap w therefore moves the
section by w sin(beta) in the rotor plane, where the centrifugal field pulls
it outward, and the flap load gains mu Omega^2 sin^2(beta) w. The oracle is an
independent hand integration of the cantilever (a fine grid, the moment
integral with the centrifugal tension as a P-Delta term and the softening as
a load, solved by fixed-point iteration), written from its equations on a
synthetic blade; it shares no code with the package.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-172.

import math

import numpy as np
import pytest

from pyflightstream.fsi import centrifugal
from pyflightstream.fsi.config import BladeProperties, FsiConfig

STATIONS = np.linspace(0.41, 1.80, 16)
OMEGA = 49.55
# A solid metal propeller blade's orders of magnitude: heavy and stiff at the
# root, light and flexible at the tip, strongly pitched inboard.
PITCH_DEG = np.linspace(68.0, 37.0, len(STATIONS))
MU = np.linspace(50.0, 4.0, len(STATIONS))
EI = np.geomspace(7.0e5, 1.4e3, len(STATIONS))
FLAP_LOAD = 250.0 + 150.0 * (STATIONS - STATIONS[0]) / (STATIONS[-1] - STATIONS[0])


def _config() -> FsiConfig:
    n = len(STATIONS)
    blade = BladeProperties(
        station_radii_m=list(STATIONS),
        chord_m=[0.1] * n,
        mass_per_length_kg_per_m=list(MU),
        # A section with no propeller moment and a torsionally stiff beam, so
        # the elastic twist the oracle leaves out stays zero in the package.
        inertia_major_kg_m=[1.0e-6] * n,
        inertia_minor_kg_m=[1.0e-6] * n,
        bending_stiffness_n_m2=list(EI),
        torsion_stiffness_n_m2=[1.0e6] * n,
        elastic_axis_offset_chordwise_m=[0.0] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=list(PITCH_DEG),
    )
    return FsiConfig(blade_count=1, omega_rad_per_s=OMEGA, blade=blade)


def _hand_tip_flap(*, soften: bool) -> float:
    """The hand integration: clamp at the first station, EI constant per bay."""
    x = np.linspace(STATIONS[0], STATIONS[-1], 2801)
    bay = np.clip(np.searchsorted(STATIONS, x, side="right") - 1, 0, len(STATIONS) - 2)
    ei = 0.5 * (EI[bay] + EI[bay + 1])
    q = np.interp(x, STATIONS, FLAP_LOAD)
    mu = np.interp(x, STATIONS, MU)
    tension_load = mu * OMEGA**2 * x
    softening = mu * OMEGA**2 * np.sin(np.radians(np.interp(x, STATIONS, PITCH_DEG))) ** 2

    def integral_from(values: np.ndarray, i: int) -> float:
        return float(np.trapezoid(values[i:], x[i:]))

    def cumulative(values: np.ndarray) -> np.ndarray:
        out = np.zeros_like(values)
        out[1:] = np.cumsum(0.5 * (values[1:] + values[:-1]) * np.diff(x))
        return out

    w = np.zeros_like(x)
    for _ in range(400):
        load = q + (softening * w if soften else 0.0)
        moment = np.array(
            [
                integral_from(load * (x - x[i]), i) - integral_from(tension_load * (w - w[i]), i)
                for i in range(len(x))
            ]
        )
        w_new = cumulative(cumulative(moment / ei))
        if np.max(np.abs(w_new - w)) < 1e-13:
            return float(w_new[-1])
        w = w_new
    raise AssertionError("the hand integration did not converge")


@pytest.fixture(scope="module")
def hand():
    return {"tension": _hand_tip_flap(soften=False), "softened": _hand_tip_flap(soften=True)}


def _package_tip_flap() -> float:
    result = centrifugal.solve_rotating_static(_config(), flap_load_n_per_m=list(FLAP_LOAD))
    assert result.converged
    return result.solution.flap_deflection_m[-1]


def test_softening_coefficient_is_mu_omega_squared_sin_squared_pitch():
    # P0300-FSI1-SOFTENING
    coefficients = centrifugal.in_plane_softening_coefficients(_config())
    for k, mu, beta in zip(coefficients, MU, PITCH_DEG, strict=True):
        assert k == pytest.approx(mu * OMEGA**2 * math.sin(math.radians(beta)) ** 2, rel=1e-12)


def test_softening_raises_the_tip_flap_as_the_hand_integration_does(hand, monkeypatch):
    # P0300-FSI1-SOFTENING
    softened = _package_tip_flap()
    monkeypatch.setattr(
        centrifugal,
        "in_plane_softening_coefficients",
        lambda cfg: [0.0] * len(cfg.blade.station_radii_m),
    )
    tension_only = _package_tip_flap()
    expected = hand["softened"] / hand["tension"] - 1.0
    measured = softened / tension_only - 1.0
    # The term is not a rounding: a few percent of tip flap on this blade.
    assert expected > 0.015
    assert measured == pytest.approx(expected, abs=0.001)
    # And the two solutions are the same beam: the package's tension-only tip
    # matches the hand integration's within the discretisation.
    assert tension_only == pytest.approx(hand["tension"], rel=0.005)


def test_no_pitch_no_softening():
    cfg = _config()
    flat = cfg.model_copy(deep=True)
    flat.blade.geometric_pitch_deg = [0.0] * len(STATIONS)
    assert centrifugal.in_plane_softening_coefficients(flat) == [0.0] * len(STATIONS)
