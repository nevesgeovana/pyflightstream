"""NEGATIVE-ALTITUDE-UNNAMEABLE: the refusal says what is true.

The flight-condition resolver accepts an altitude below sea level; it is the
point NAME that writes ALT without a sign. The field stays unsigned, so no
existing name moves, and only the sentence is corrected.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, name_field


def test_a_negative_altitude_is_refused_by_the_name_and_not_by_the_flight_condition() -> None:
    with pytest.raises(CampaignConfigError) as refusal:
        name_field("ALTFT", -500.0)
    sentence = str(refusal.value)
    # The false claim: the flight condition CAN hold a negative altitude.
    assert "not a value the flight condition can hold" not in sentence
    # The true one: the limit is the point name's.
    assert "point name" in sentence
    assert "cannot carry a negative ALTFT" in sentence


def test_a_positive_altitude_keeps_its_name() -> None:
    # The control: nothing about an existing name moved.
    assert name_field("ALTFT", 10000.0) == "ALT10000"
