"""Tier 1: assert_records_close and infinite values (P0400-RECORDS-INF, PFS-2102.016).

Pipeline role: quality gate on :mod:`pyflightstream.testing`. An infinite
expected value made the tolerance band infinite (or nan when rtol is 0), so
``inf > inf`` let a finite or wrong-signed actual through. Only the same
infinity agrees with an infinity.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.testing import assert_records_close

INF = math.inf


@pytest.mark.parametrize("rtol", [1.0e-6, 0.0])
@pytest.mark.parametrize(
    ("actual", "expected"),
    [(1.0, INF), (-INF, INF), (INF, -INF), (INF, 1.0), (0.0, -INF)],
)
def test_p0400_records_inf_refuses_a_different_value(actual, expected, rtol):
    """P0400-RECORDS-INF: a finite or opposite-signed value never matches an infinity."""
    with pytest.raises(AssertionError, match=r"1 of 1 values violate"):
        assert_records_close({"CL": actual}, {"CL": expected}, rtol=rtol)


@pytest.mark.parametrize("rtol", [1.0e-6, 0.0])
@pytest.mark.parametrize("value", [INF, -INF])
def test_p0400_records_inf_accepts_the_same_infinity(value, rtol):
    """P0400-RECORDS-INF: the same infinity on both sides agrees."""
    assert_records_close({"CL": value}, {"CL": value}, rtol=rtol)
