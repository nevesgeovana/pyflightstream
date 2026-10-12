"""Tier 1: the CCS control-surface range refusal names the form the plan accepts (0.40.0)."""

import pytest
from pydantic import ValidationError

from pyflightstream.cases._ccs import CcsControlSurface


def test_p0400_ccs_parametric_range_refusal_names_span_fractions():
    """P0400-CCS-REMEDY (PFS-2100.008): never steer to space = "REAL", which the plan refuses."""
    with pytest.raises(ValidationError) as caught:
        CcsControlSurface(
            name="AIL",
            v0=2.0,
            v1=3.6,
            u0=0.25,
            u1=0.25,
            hinge_height=0.5,
            angle_deg=20.0,
            slot_gap_pct=1.0,
        )
    text = str(caught.value)
    assert "fractions of the span between 0 and 1" in text
    assert 'write space = "REAL"' not in text
    assert CcsControlSurface.__doc__ is not None and "unsupported" in CcsControlSurface.__doc__
