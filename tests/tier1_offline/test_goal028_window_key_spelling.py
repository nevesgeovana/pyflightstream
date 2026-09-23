"""Since 0.26.0 a retired window key is refused with the exact replacement spelling."""

import re

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.windows import averaging_span
from tests.tier1_offline.test_workflows import rendered, rotor_case

_SUPERSEDED_BY = {
    "WINDOW_STEPS": "LAST_ITERS_AVG",
    "WINDOW_REVOLUTIONS": "LAST_REVS_AVG",
    "WINDOW_DEGREES": "LAST_REVS_AVG",
}


@pytest.mark.parametrize("value", ["90", ""])
@pytest.mark.parametrize("key", sorted(_SUPERSEDED_BY))
def test_the_retired_key_is_refused_at_plan_with_the_replacement(key, value):
    """The old warning is a refusal, even beside a valid averaging key."""
    with pytest.raises(CampaignConfigError) as refused:
        rendered(rotor_case(**{key: value}))
    message = str(refused.value)
    assert key in message and _SUPERSEDED_BY[key] in message
    spelled = re.findall(r"last_(?:iters|revs)_avg", message, flags=re.IGNORECASE)
    assert spelled and all(word == word.upper() for word in spelled)


@pytest.mark.parametrize("key", sorted(_SUPERSEDED_BY))
def test_a_row_written_as_the_refusal_says_resolves_to_a_window(key):
    replacement = _SUPERSEDED_BY[key]
    value = "250" if replacement == "LAST_ITERS_AVG" else "1.0"
    assert averaging_span({replacement: value}, last_step=1000, per_revolution=250.0) == (751, 1000)
