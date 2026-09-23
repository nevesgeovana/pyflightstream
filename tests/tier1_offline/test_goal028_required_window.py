"""An unsteady row states its averaging window, or the plan refuses it (MC-02).

The definitions page: the window "fica na matriz e e input obrigatorio". 0.23.0
did not refuse. A row without the key planned and ran, and at post took the
STEADY route: group polars off the last time step under the steady names, beside
a time average over a window the package had defaulted, nothing marking either.

Since 0.26.0 a new plan accepts only LAST_REVS_AVG or LAST_ITERS_AVG.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import _require_the_averaging_window


def _case(recipe: str, **variables: str) -> SimCase:
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        recipe=recipe,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables=variables,
    )


def test_a_rotor_row_with_no_window_is_refused_naming_the_key_and_an_example():
    with pytest.raises(CampaignConfigError) as refused:
        _require_the_averaging_window(_case("unsteady_rotor", RPM="1200"), "unsteady_rotor")
    text = str(refused.value)
    assert "7001" in text and "LAST_REVS_AVG" in text and "LAST_REVS_AVG: 0.5" in text


def test_a_rotorless_row_is_pointed_at_the_iterations_key():
    with pytest.raises(CampaignConfigError) as refused:
        _require_the_averaging_window(_case("unsteady"), "unsteady")
    assert "LAST_ITERS_AVG: 100" in str(refused.value)


@pytest.mark.parametrize(
    "variables",
    [
        {"LAST_REVS_AVG": "0.5"},
        {"LAST_ITERS_AVG": "100"},
    ],
)
def test_a_row_that_states_a_current_window_key_is_accepted(variables):
    _require_the_averaging_window(_case("unsteady_rotor", **variables), "unsteady_rotor")


# --- THROUGH THE PUBLIC PLANNER (release review of 0.24.0, QA-Q1) ----------------
#
# Every case above calls the private helper. The review deleted BOTH of its call
# sites in a scratch copy and 526 tests stayed green: nothing planned a windowless
# row the way a campaign does. These two build the script, which is what a plan is.


def test_a_windowless_rotorless_row_is_refused_when_its_script_is_built():
    from tests.tier1_offline.test_workflows import rendered, unsteady_case

    with pytest.raises(CampaignConfigError) as refused:
        rendered(unsteady_case(LAST_ITERS_AVG=None))
    assert "LAST_ITERS_AVG" in str(refused.value) and "7003" in str(refused.value)
    # THE CONTROL: the same row stating its window builds.
    assert "SOLVER" in rendered(unsteady_case()).upper()


def test_a_windowless_rotor_row_is_refused_when_its_script_is_built():
    from tests.tier1_offline.test_workflows import rendered, rotor_case

    with pytest.raises(CampaignConfigError) as refused:
        rendered(rotor_case(LAST_REVS_AVG=None))
    assert "LAST_REVS_AVG" in str(refused.value)
    assert "SOLVER" in rendered(rotor_case()).upper()


@pytest.mark.parametrize("key", ["WINDOW_STEPS", "WINDOW_REVOLUTIONS", "WINDOW_DEGREES"])
def test_a_retired_window_cannot_satisfy_the_required_window(key):
    """A former accepted spelling must now fail with the key to write."""
    with pytest.raises(CampaignConfigError, match=key + ".*LAST_"):
        _require_the_averaging_window(_case("unsteady_rotor", **{key: "1"}), "unsteady_rotor")
