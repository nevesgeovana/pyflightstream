"""Tier 1: the public testing assertions and their quantified reports.

Pipeline role: quality gate on :mod:`pyflightstream.testing`. The
assertions follow the golden philosophy split (exact ASCII for
scripts, tolerances for numeric records) and their failure messages
carry statistics; both facts are pinned here.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.testing import assert_records_close, assert_scripts_equal

# --- assert_records_close ---------------------------------------------------


def test_records_close_passes_within_tolerance():
    assert_records_close({"CL": 0.5000001, "CDi": 0.01}, {"CL": 0.5, "CDi": 0.01}, rtol=1e-6)


def test_records_close_reports_count_keys_and_worst_offender():
    with pytest.raises(
        AssertionError,
        match=r"polar: 2 of 3 values violate rtol=1e-09, atol=0.*CDi, CMy.*Worst "
        r"offender 'CMy': actual 0\.2 against expected 0\.1, deviation 1\.000e-01",
    ):
        assert_records_close(
            {"CL": 0.5, "CDi": 0.011, "CMy": 0.2},
            {"CL": 0.5, "CDi": 0.010, "CMy": 0.1},
            rtol=1e-9,
            label="polar",
        )


def test_records_close_refuses_differing_key_sets_before_comparing():
    with pytest.raises(
        AssertionError,
        match=r"key sets differ.*missing from actual: \['CDi'\].*unexpected in "
        r"actual: \['CDo'\]",
    ):
        assert_records_close({"CL": 1.0, "CDo": 0.1}, {"CL": 1.0, "CDi": 0.1})


def test_records_close_atol_floor_covers_zero_crossings():
    assert_records_close({"CMy": 1.0e-12}, {"CMy": 0.0}, atol=1.0e-9)
    with pytest.raises(AssertionError, match="1 of 1"):
        assert_records_close({"CMy": 1.0e-6}, {"CMy": 0.0}, atol=1.0e-9)


def test_records_close_treats_nan_pairs_as_agreeing_and_mixed_as_violating():
    assert_records_close({"x": math.nan}, {"x": math.nan})
    with pytest.raises(AssertionError, match="1 of 1"):
        assert_records_close({"x": math.nan}, {"x": 1.0})


# --- assert_scripts_equal ---------------------------------------------------


def test_scripts_equal_passes_on_identical_text():
    assert_scripts_equal("OPEN a.fsm\nSTART_SOLVER\n", "OPEN a.fsm\nSTART_SOLVER\n")


def test_scripts_equal_reports_first_line_and_total_count():
    with pytest.raises(
        AssertionError,
        match=r"golden: 2 differing line\(s\).*first difference at line 2: actual "
        r"'SET_AOA 4\.0' against expected 'SET_AOA 2\.0'",
    ):
        assert_scripts_equal(
            "OPEN a.fsm\nSET_AOA 4.0\nSTART_SOLVER X\n",
            "OPEN a.fsm\nSET_AOA 2.0\nSTART_SOLVER\n",
            label="golden",
        )


def test_scripts_equal_names_a_pure_length_difference():
    with pytest.raises(
        AssertionError,
        match=r"agree up to line 1 and then one of them ends",
    ):
        assert_scripts_equal("OPEN a.fsm\n", "OPEN a.fsm\nSTART_SOLVER\n")


def test_scripts_equal_names_an_endings_only_difference():
    """CRLF or trailing-newline drift is named, not reported as zero diffs."""
    with pytest.raises(AssertionError, match="only in line endings or a trailing newline"):
        assert_scripts_equal("OPEN a.fsm\nSTART_SOLVER", "OPEN a.fsm\nSTART_SOLVER\n")
    with pytest.raises(AssertionError, match="only in line endings or a trailing newline"):
        assert_scripts_equal("OPEN a.fsm\r\nSTART_SOLVER\r\n", "OPEN a.fsm\nSTART_SOLVER\n")
