"""P0400-ROTORINPUTS: rotor input refusals name a remedy that works, and aliases fold case."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pyflightstream.cases import CampaignConfigError
from pyflightstream.workspace.inputs import RotorReference, rotor_integration_groups


def test_p0400_rotorinputs_the_retired_facts_refusal_names_rpm_sign():
    """P0400-ROTORINPUTS (PFS-2100.020): the remedy names rpm_sign on the reference's rotor
    block and RPM as a magnitude, not the sign of RPM, which a row is refused for."""
    with pytest.raises(ValidationError) as caught:
        RotorReference.model_validate({"n_blades": 3, "rotation": "cw"})
    message = " ".join(str(caught.value).split())
    assert "rpm_sign on a rotor block of the reference" in message, message
    assert "RPM is a magnitude" in message, message
    assert "sign of RPM" not in message, message


def test_p0400_rotorinputs_a_group_in_another_case_is_the_rotors_and_is_checked():
    """P0400-ROTORINPUTS (PFS-2104.049): a declared `pusher` for rotor PUSHER is checked against
    the rotor's families and no second group `PUSHER` is added."""
    rotors = {"PUSHER": SimpleNamespace(members=["B1", "B2"])}
    agreed = rotor_integration_groups(rotors, {"pusher": ["b1", "b2"]})
    assert agreed == {"pusher": ["b1", "b2"]}
    with pytest.raises(CampaignConfigError, match="'pusher'"):
        rotor_integration_groups(rotors, {"pusher": ["WING"]})
