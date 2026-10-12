"""P0400-RESULTS: the shared parsers of the results package (PFS-2095.048)."""

from __future__ import annotations

import pytest

from pyflightstream.results.core import MalformedOutputError, parse_count, parse_number


@pytest.mark.parametrize("token", ["nan", "inf", "-Infinity", "NaN"])
def test_p0400_results_parse_count_refuses_a_non_finite_value(token):
    """P0400-RESULTS (PFS-2095.048): a printed NaN or infinity is a malformed count, not a crash."""
    with pytest.raises(MalformedOutputError, match="Total iterations"):
        parse_count(token, label="Total iterations")


@pytest.mark.parametrize("token", ["1_000", "1_0.5", "+2_5E-3"])
def test_p0400_results_parse_number_refuses_a_digit_separator(token):
    """P0400-RESULTS (PFS-2095.048): Python's '1_000' is not a form the solver prints."""
    with pytest.raises(MalformedOutputError, match="not a solver-printed number"):
        parse_number(token)


def test_p0400_results_parse_number_still_reads_the_solver_forms():
    """P0400-RESULTS (PFS-2095.048): control, the documented forms still parse."""
    assert parse_number(".000") == 0.0
    assert parse_number("4380000.") == 4380000.0
    assert parse_number("1.000E-05") == 1e-05
    assert parse_number("0.2964-322") == float("0.2964e-322")
    assert parse_count("312", label="Total iterations") == 312
