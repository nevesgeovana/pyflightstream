"""An unsteady row states its averaging window, or the plan refuses it (MC-02).

The definitions page: the window "fica na matriz e e input obrigatorio". 0.23.0
did not refuse. A row without the key planned and ran, and at post took the
STEADY route: group polars off the last time step under the steady names, beside
a time average over a window the package had defaulted, nothing marking either.

ONLY A NEW PLAN IS REFUSED. A row that still states a retired `WINDOW_*` key
satisfies the rule until 0.26.0, because a matrix already written must keep
planning.
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
        {"WINDOW_REVOLUTIONS": "1"},
        {"WINDOW_STEPS": "36"},
        {"WINDOW_DEGREES": "90"},
    ],
)
def test_a_row_that_states_a_window_in_any_spelling_that_still_binds_is_accepted(variables):
    _require_the_averaging_window(_case("unsteady_rotor", **variables), "unsteady_rotor")
