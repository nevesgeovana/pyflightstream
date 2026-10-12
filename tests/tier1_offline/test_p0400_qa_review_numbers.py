"""P0400-REVIEW-NUMBERS: saved-state evidence must match a whole numeric value.

Reproduction: fsm_gained('37') must not verify a changed value of 370.
"""

from types import SimpleNamespace

import pytest

from pyflightstream.qa.probes import fsm_gained


@pytest.mark.parametrize(
    ("token", "stored"),
    [
        ("37", "370"),
        ("37", "-37"),
        ("0.1", "10.1"),
        ("0.1", "0.1E+01"),
        ("0.1", "-1.00000000000000006E-01"),
        ("0.1", "1.00000000000000006E-010"),
    ],
)
def test_p0400_review_numbers_wrong_numeric_value_is_not_evidence(token, stored):
    artifacts = SimpleNamespace(saved_before=lambda: "old", saved_after=lambda: stored)
    assert fsm_gained(token)(artifacts) is False


@pytest.mark.parametrize("stored", ["37", "+37", "3.70000000000000000E+01", "count=37, next=5"])
def test_p0400_review_numbers_whole_value_still_verifies(stored):
    artifacts = SimpleNamespace(saved_before=lambda: "old", saved_after=lambda: stored)
    assert fsm_gained("37")(artifacts) is True
