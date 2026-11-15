"""P0580 PSLICE tie: a blade section with two equally round ends keeps its leading edge by motion.

PFS-2262. The slicer takes the rounder end of a section for the leading edge; on a section
whose two ends are equally sharp (a lens, a flat plate) that rule has no answer and the
leading and trailing edge swapped, so the section's beta came out 180 degrees off. A tie of
the two ends now goes to the end ahead in the section's motion sense; a section with a
real round nose keeps the rounder-end rule.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pyflightstream.geometry._propeller_slice import section_parameters

ANGLE = 30.0


def lens(skew, *, angle=ANGLE, n=240):
    """A closed lens section of unit chord whose width at the ends differs by ``skew``.

    The chord runs along ``angle`` from the end at x' = 0 to the end at x' = 1. A positive
    ``skew`` makes the x' = 1 end the wider one at 5 percent of the chord.
    """
    x = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    half = 0.06 * (1 + skew * (x - 0.5)) * np.sin(np.pi * x) ** 0.9
    upper = np.column_stack((x, half))
    lower = np.column_stack((x[::-1], -half[::-1]))
    loop = np.vstack((upper[:-1], lower[:-1]))
    a = math.radians(angle)
    turn = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return 100.0 * (loop @ turn.T)


def _starts(loop):
    """The same loop from several first vertices, and reversed: the answer must not move."""
    for shift in (0, len(loop) // 5, len(loop) // 2, 3 * len(loop) // 4):
        yield np.roll(loop, shift, axis=0)
        yield np.roll(loop, shift, axis=0)[::-1]


@pytest.mark.parametrize("skew", [0.0, 0.05, -0.05])
def test_p0580_pslice_tie_leading_edge_is_the_end_ahead(skew):
    """Two ends within the tie: the section moves toward +x, so the larger-x end leads."""
    for loop in _starts(lens(skew)):
        row = section_parameters(loop, 1, 300.0, 500.0)
        # LE is the x' = 1 end, so the chord runs from the trailing edge back along the lens
        assert row["beta_deg"] == pytest.approx(ANGLE, abs=0.05)
        assert row["c_R"] == pytest.approx(100.0 / 500.0, rel=0.01)


@pytest.mark.parametrize("skew", [0.0, 0.05, -0.05])
def test_p0580_pslice_tie_follows_the_motion_sense(skew):
    """The same lens turned the other way (sense -1) puts the leading edge at the other end."""
    for loop in _starts(lens(skew)):
        row = section_parameters(loop, -1, 300.0, 500.0)
        # the plane is mirrored in x: the x' = 0 end leads, the chord runs toward (-cos, sin)
        assert row["beta_deg"] == pytest.approx(-ANGLE, abs=0.05)


@pytest.mark.parametrize("sense", [1, -1])
def test_p0580_pslice_round_nose_keeps_the_rounder_end_rule(sense):
    """Control: a real nose (a third wider than the other end, outside the tie) decides.

    The x' = 0 end is the rounder one. Moving toward -x (sense -1) it is the end ahead and
    leads by the rounder-end rule alone. Moving toward +x it trails, a pitch beyond 90 degrees
    that prop-slice does not support: the section is turned about its mid-chord (PFS-2262,
    second rule), so beta folds into (-90, 90] instead of coming out 180 degrees off.
    """
    loop = lens(-1.2)
    widths = _widths(loop)
    assert widths[0] > 3 * widths[1]
    for start in _starts(loop):
        row = section_parameters(start, sense, 300.0, 500.0)
        expected = _rounder_leads_beta(sense)
        if abs(expected) > 90:
            expected -= math.copysign(180.0, expected)
        assert row["beta_deg"] == pytest.approx(expected, abs=0.05)


def _rounder_leads_beta(sense):
    """Beta when the x' = 0 end leads: axis = te - le runs from the x' = 0 end to the x' = 1 end."""
    a = math.radians(ANGLE)
    x_axis = np.array([math.cos(a), math.sin(a)])
    x_axis[0] *= sense
    return math.degrees(math.atan2(-x_axis[1], -x_axis[0]))


def _widths(loop):
    """Width of the lens at 5 percent of the chord from each end (x' = 0 end first)."""
    a = math.radians(ANGLE)
    along = loop @ np.array([math.cos(a), math.sin(a)]) / 100.0
    across = loop @ np.array([-math.sin(a), math.cos(a)]) / 100.0
    out = []
    for lo, hi in ((0.0, 0.05), (0.95, 1.0)):
        inside = (along >= lo) & (along <= hi)
        out.append(float(np.ptp(across[inside])))
    return out


@pytest.mark.parametrize("sense, skew", [(1, -0.095), (-1, 0.095)])
def test_p0580_pslice_beta_folds_into_plus_minus_90(sense, skew):
    """Ends just outside the tie, the rounder one trailing in motion: beta stays within 90 degrees.

    The widths differ by about 8 percent of the wider, so the tie rule does not apply and the
    rounder-end rule picks the end behind in the motion; the section is then turned about its
    mid-chord so the end ahead leads, and beta is the in-range value, not 180 degrees off.
    """
    widths = _widths(lens(skew))
    assert 0.06 < abs(widths[0] - widths[1]) / max(widths) < 0.1
    for loop in _starts(lens(skew)):
        row = section_parameters(loop, sense, 300.0, 500.0)
        assert row["beta_deg"] == pytest.approx(sense * ANGLE, abs=0.05)
        assert row["c_R"] == pytest.approx(100.0 / 500.0, rel=0.01)
