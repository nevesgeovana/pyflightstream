"""P0400-COVERAGE: a harmonic is fitted only where the azimuths go round the circle.

At the 0.40.0 base fit_harmonics chose 1P and 2P from the count of distinct
azimuths alone, so five samples 0.1 deg apart on a constant load returned finite
amplitudes of order 1e5.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.post.harmonics import fit_harmonics


def test_p0400_coverage_crowded_azimuths_leave_both_harmonics_none():
    """P0400-COVERAGE: five samples 0.1 deg apart fit H0 alone and say why."""
    psi = [0.0, 0.1, 0.2, 0.3, 0.4]
    noise = [0.0, 1e-6, -1e-6, 2e-6, 0.0]
    fit = fit_harmonics(psi, [1.0 + e for e in noise])
    assert fit.distinct == 5
    assert (fit.h1_amp, fit.h1_phase_deg, fit.h2_amp, fit.h2_phase_deg) == (None,) * 4
    assert fit.h0 == pytest.approx(1.0, abs=1e-5)
    assert fit.reason is not None and "1P term and above" in fit.reason


def test_p0400_coverage_a_full_circle_five_point_fit_is_unchanged():
    """P0400-COVERAGE control: five azimuths round the circle still fit 1P and 2P."""
    psi = [0.0, 72.0, 144.0, 216.0, 288.0]
    load = [
        2.0 + 0.5 * math.cos(math.radians(p - 30.0)) + 0.25 * math.cos(math.radians(2 * p - 40.0))
        for p in psi
    ]
    fit = fit_harmonics(psi, load)
    assert fit.h0 == pytest.approx(2.0)
    assert (fit.h1_amp, fit.h1_phase_deg) == (pytest.approx(0.5), pytest.approx(30.0))
    assert (fit.h2_amp, fit.h2_phase_deg) == (pytest.approx(0.25), pytest.approx(40.0))
    assert getattr(fit, "reason", None) is None
