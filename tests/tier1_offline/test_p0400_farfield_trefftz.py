"""P0400-TREFFTZA (FR-451): the discrete trace of the section loads, on analytic loadings.

Every loading is written here in closed form: an elliptic circulation at
uniform stations (the strip centres a section distribution has), the same at
cosine stations, a uniform circulation (two tip filaments), and two sheets at
two heights. The expected numbers are computed in the test from the formula,
never read back from the code under test. The post-side clauses (the lift
density from the section forces, the named skips, the files) are in
``test_p0400_farfield_products.py``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.farfield import (
    FarfieldInputError,
    strip_edges,
    trace_coefficients,
    trace_forces,
)

RHO = 1.2
V = 30.0
SPAN = 10.0
G0 = 5.0
Q = 0.5 * RHO * V * V


def _uniform_stations(per_side: int, span: float = SPAN) -> np.ndarray:
    """``2 n`` stations at the centres of ``2 n`` equal strips across the span."""
    h = (span / 2.0) / per_side
    return -span / 2.0 + h * (np.arange(2 * per_side) + 0.5)


def _elliptic(y: np.ndarray, span: float = SPAN, peak: float = G0) -> np.ndarray:
    return peak * np.sqrt(1.0 - (2.0 * y / span) ** 2)


def _efficiency(lift: float, drag: float, span: float = SPAN) -> float:
    """``e = L^2 / (pi q b^2 D)``, the span efficiency of a planar wing of span ``b``."""
    return lift * lift / (math.pi * Q * span * span * drag)


@pytest.mark.requirement("FR-451")
@pytest.mark.parametrize(("per_side", "bias_pct"), [(40, 1.05), (80, 0.52), (160, 0.26)])
def test_p0400_trefftza_an_elliptic_loading_shows_the_measured_strip_bias(per_side, bias_pct):
    """P0400-TREFFTZA (FR-451 R3): E_T exceeds 1 by the definitions page's bias, halving."""
    y = _uniform_stations(per_side)
    result = trace_forces(y, np.zeros_like(y), _elliptic(y), rho=RHO, v_inf=V)
    e = _efficiency(result.lift, result.induced_drag)
    assert 100.0 * (e - 1.0) == pytest.approx(bias_pct, abs=0.02)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_the_station_rule_is_not_the_far_field_rule():
    """P0400-TREFFTZA (FR-451 R3): edges at the end stations shorten the span by one spacing.

    The control of the mutant "the station rule used for the trace": with the
    integrated sectional loads' rule the traced span is one spacing short, the
    end filaments sit on the end stations, and the bias of the test above is not
    met (the trace is not even finite).
    """
    y = _uniform_stations(40)
    extended = strip_edges(y, ends="extended")
    station = strip_edges(y, ends="station")
    spacing = y[1] - y[0]
    assert extended[0] == pytest.approx(-SPAN / 2.0) and extended[-1] == pytest.approx(SPAN / 2.0)
    assert (station[-1] - station[0]) == pytest.approx(SPAN - spacing)
    wrong = trace_forces(y, np.zeros_like(y), _elliptic(y), rho=RHO, v_inf=V, ends="station")
    e = _efficiency(wrong.lift, wrong.induced_drag)
    assert not abs(100.0 * (e - 1.0) - 1.05) <= 0.1


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_a_uniform_circulation_is_two_tip_filaments():
    """P0400-TREFFTZA (FR-451 R3, R6): lift rho V Gamma b exactly, drag of the two filaments."""
    y = _uniform_stations(20)
    gamma = np.full_like(y, G0)
    result = trace_forces(y, np.zeros_like(y), gamma, rho=RHO, v_inf=V)
    assert result.lift == pytest.approx(RHO * V * G0 * SPAN, rel=1e-14)
    # Closed form: the two filaments at +-b/2 shed +Gamma (left) and -Gamma
    # (right); the downwash at the lifting line, positive down, is
    # (1/4 pi) sum dGamma / (y - e) and the drag rho sum Gamma w dy.
    dy = SPAN / len(y)
    w = (G0 / (4.0 * math.pi)) * (1.0 / (y + SPAN / 2.0) - 1.0 / (y - SPAN / 2.0))
    expected = RHO * float(np.sum(G0 * w * dy))
    assert result.induced_drag == pytest.approx(expected, rel=1e-12)
    assert result.downwash == pytest.approx(w, rel=1e-12)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_a_mirrored_half_span_equals_the_full_span():
    """P0400-TREFFTZA (FR-451 R5): the mirror rebuilds the full sheet, no root filament."""
    y = _uniform_stations(40)
    z = 0.02 * np.abs(y)
    gamma = _elliptic(y)
    full = trace_forces(y, z, gamma, rho=RHO, v_inf=V)
    right = y > 0.0
    half = trace_forces(y[right], z[right], gamma[right], rho=RHO, v_inf=V, mirror=True)
    assert half.lift == pytest.approx(full.lift, rel=1e-12)
    assert half.induced_drag == pytest.approx(full.induced_drag, rel=1e-12)
    assert half.original.sum() == right.sum()
    left = trace_forces(y[~right], z[~right], gamma[~right], rho=RHO, v_inf=V, mirror=True)
    assert left.induced_drag == pytest.approx(full.induced_drag, rel=1e-12)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_a_half_trace_not_mirrored_is_not_the_full_span():
    """P0400-TREFFTZA (FR-451 R5): the control of the mutant "the mirror skipped"."""
    y = _uniform_stations(40)
    right = y > 0.0
    full = trace_forces(y, np.zeros_like(y), _elliptic(y), rho=RHO, v_inf=V)
    half = trace_forces(y[right], np.zeros(right.sum()), _elliptic(y)[right], rho=RHO, v_inf=V)
    assert half.induced_drag != pytest.approx(full.induced_drag / 2.0, rel=1e-3)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_a_straddling_half_model_is_refused():
    """P0400-TREFFTZA (FR-451 R5): stations on both sides cannot say which half was meant."""
    y = np.array([-0.5, 0.5, 1.5, 2.5])
    with pytest.raises(FarfieldInputError, match="straddle"):
        trace_forces(y, np.zeros_like(y), np.ones_like(y), rho=RHO, v_inf=V, mirror=True)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_cosine_stations_converge_to_the_elliptic_efficiency():
    """P0400-TREFFTZA (FR-451 R3): uneven stations converge to e = 1 as they double."""
    errors = []
    for per_side in (20, 40, 80, 160):
        theta = (np.arange(2 * per_side) + 0.5) * math.pi / (2 * per_side)
        y = -SPAN / 2.0 * np.cos(theta)
        result = trace_forces(y, np.zeros_like(y), _elliptic(y), rho=RHO, v_inf=V)
        errors.append(abs(_efficiency(result.lift, result.induced_drag) - 1.0))
    assert all(b < 0.6 * a for a, b in zip(errors, errors[1:], strict=False)), errors
    assert errors[-1] < 0.005


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_family_shares_add_up_and_isolated_values_are_each_alone():
    """P0400-TREFFTZA (FR-451 R7): the share of the total and the family alone, both."""
    wing_y = _uniform_stations(40)
    tail_y = _uniform_stations(10, span=3.0)
    y = np.concatenate([wing_y, tail_y])
    z = np.concatenate([np.zeros_like(wing_y), np.full_like(tail_y, 0.6)])
    gamma = np.concatenate([_elliptic(wing_y), _elliptic(tail_y, 3.0, -0.8)])
    sheets = np.concatenate([np.zeros(len(wing_y), int), np.ones(len(tail_y), int)])
    both = trace_forces(y, z, gamma, rho=RHO, v_inf=V, sheets=sheets)
    assert both.sheet_drag_share.sum() == pytest.approx(both.induced_drag, rel=1e-14)
    wing = trace_forces(wing_y, np.zeros_like(wing_y), _elliptic(wing_y), rho=RHO, v_inf=V)
    tail = trace_forces(
        tail_y, np.full_like(tail_y, 0.6), _elliptic(tail_y, 3.0, -0.8), rho=RHO, v_inf=V
    )
    assert both.sheet_drag_isolated[0] == pytest.approx(wing.induced_drag, rel=1e-12)
    assert both.sheet_drag_isolated[1] == pytest.approx(tail.induced_drag, rel=1e-12)
    interference = both.induced_drag - both.sheet_drag_isolated.sum()
    assert abs(interference) > 1e-6 * both.induced_drag
    assert both.sheet_drag_share[0] != pytest.approx(both.sheet_drag_isolated[0], rel=1e-6)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_the_trace_follows_the_quarter_chord_height():
    """P0400-TREFFTZA (FR-451 R4): a dihedral sheet is traced in (y, z), with side force zero."""
    y = _uniform_stations(40)
    z = 0.1 * np.abs(y)
    result = trace_forces(y, z, _elliptic(y), rho=RHO, v_inf=V)
    flat = trace_forces(y, np.zeros_like(y), _elliptic(y), rho=RHO, v_inf=V)
    assert result.side_force == pytest.approx(0.0, abs=1e-9 * result.lift)
    assert result.induced_drag != pytest.approx(flat.induced_drag, rel=1e-6)


@pytest.mark.requirement("FR-451")
def test_p0400_trefftza_the_coefficients_and_the_na_rules():
    """P0400-TREFFTZA (FR-451 R6; FR-456 R5): q SREF normalisation, E_T NA at zero drag."""
    c = trace_coefficients(120.0, 3.0, 4.0, q=Q, s_ref=8.0, b_ref=10.0)
    assert c["CL_T"] == pytest.approx(120.0 / (Q * 8.0))
    assert c["CY_T"] == pytest.approx(3.0 / (Q * 8.0))
    assert c["AR"] == pytest.approx(12.5)
    assert c["E_T"] == pytest.approx(c["CL_T"] ** 2 / (math.pi * 12.5 * c["CDI_T"]))
    assert math.isnan(trace_coefficients(1.0, 0.0, 0.0, q=Q, s_ref=8.0, b_ref=10.0)["E_T"])
    assert math.isnan(trace_coefficients(1.0, 0.0, 1.0, q=Q, s_ref=0.0, b_ref=10.0)["CL_T"])
