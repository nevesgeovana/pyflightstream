"""Tier 1, 0.58.0 PFS-2235 (FR-3795): an averaging window spans whole blade passages.

Written from the approved design page (section 7.3). The rotor fixture turns at
1200 rev/min with a 0.0001 s step: 500 steps per revolution, four blades, so a
passage is 125 steps.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows._reductions import require_whole_passages
from tests.tier1_offline.test_reduce_by_rotor import LIFTER, PUSHER, transition_case
from tests.tier1_offline.test_workflows import rendered, rotor_case


@pytest.mark.parametrize(("revs", "passages"), [("0.125", "0.496"), ("0.625", "2.496")])
def test_p0580_l4_a_window_of_a_fractional_number_of_passages_is_refused(revs, passages):
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG=revs))
    text = str(refused.value)
    assert f"POL `7001`: the averaging window `LAST_REVS_AVG = {revs[:5].rstrip('0')}`" in text
    assert f"spans `{passages}` blade passages" in text
    assert "whole number of passages, at least one" in text
    assert "`4` blades" in text and "`125` steps per passage" in text


def test_p0580_l4_the_message_names_the_nearest_valid_window():
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG="0.625"))
    assert "The nearest valid window is `LAST_REVS_AVG = 0.5` (`2` passages, `250` steps)." in str(
        refused.value
    )
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG=None, LAST_ITERS_AVG="312"))
    assert "The nearest valid window is `LAST_ITERS_AVG = 250` (`2` passages, `250` steps)." in str(
        refused.value
    )


def test_p0580_l4_under_one_passage_is_refused_with_one_passage_as_the_nearest():
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(rotor_case(LAST_REVS_AVG="0.125"))
    assert "`LAST_REVS_AVG = 0.25` (`1` passages, `125` steps)" in str(refused.value)


@pytest.mark.parametrize("revs", ["0.25", "0.75"])
def test_p0580_l4_one_and_three_passages_are_accepted(revs):
    require_whole_passages(rotor_case(LAST_REVS_AVG=revs))


def test_p0580_l4_the_plan_refuses_the_row_when_its_script_is_built():
    with pytest.raises(CampaignConfigError, match="whole number of passages"):
        rendered(rotor_case(LAST_REVS_AVG="0.625"))
    assert "SOLVER" in rendered(rotor_case(LAST_REVS_AVG="0.75")).upper()


def test_p0580_l4_a_row_with_no_window_key_is_not_judged_here():
    require_whole_passages(rotor_case(LAST_REVS_AVG=None))


def test_p0580_l4_a_row_with_two_rotors_names_only_the_rotor_that_fails():
    """Both rotors turn 500 steps a revolution: four blades give 125, three give 166.67."""
    pusher = PUSHER.model_copy(update={"families_blades": ["PH1", "PH2", "PH3"]})
    lifter = LIFTER.model_copy(update={"families_blades": ["L1", "L2", "L3", "L4"]})
    case = transition_case(
        rotors={"LIFT_L1": lifter, "PUSHER": pusher},
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "1200"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "1200"},
        ],
    )
    quarter = case.model_copy(update={"variables": {**case.variables, "LAST_REVS_AVG": "0.25"}})
    with pytest.raises(CampaignConfigError) as refused:
        require_whole_passages(quarter)
    text = str(refused.value)
    assert "rotor `PUSHER`" in text and "LIFT_L1" not in text
    assert "`3` blades" in text
    assert "`LAST_REVS_AVG = 0.333333` (`1` passages, `167` steps)" in text
    # THE CONTROL: a whole revolution is whole passages of both rotors.
    whole = case.model_copy(update={"variables": {**case.variables, "LAST_REVS_AVG": "1.0"}})
    require_whole_passages(whole)
