"""P0400-FCSIGNS: a flight condition's speed and Reynolds number are refused with the wrong sign."""

from __future__ import annotations

import pytest

from pyflightstream.workspace.flight_condition import (
    FlightConditionError,
    resolve_flight_condition,
)


@pytest.mark.parametrize(
    ("stated", "cell"),
    [
        ({"MACH": 0.2, "REmi": -5.5}, "REmi:-5.5"),
        ({"MACH": 0.2, "REmi": 0.0}, "REmi:0"),
        ({"MACH": -0.2}, "MACH:-0.2"),
        ({"TASmps": -50.0}, "TASmps:-50"),
    ],
)
def test_p0400_fcsigns_a_negative_speed_or_nonpositive_reynolds_is_refused(stated, cell):
    """P0400-FCSIGNS (PFS-2097.013): REmi <= 0 and a negative MACH or TASmps are refused
    naming the POL and the cell, never resolved into a zero or negative density or speed."""
    with pytest.raises(FlightConditionError) as caught:
        resolve_flight_condition(stated, pol="P7", reference_length_m=1.0)
    message = str(caught.value)
    assert "POL P7" in message and cell in message, message


@pytest.mark.parametrize("stated", [{"MACH": 0.0}, {"TASmps": 0.0}])
def test_p0400_fcsigns_hover_stays_legal(stated):
    """P0400-FCSIGNS (PFS-2097.013): zero speed is hover and is not refused."""
    state = resolve_flight_condition(stated, pol="P7", reference_length_m=1.0)
    assert state.velocity_m_per_s == 0.0
