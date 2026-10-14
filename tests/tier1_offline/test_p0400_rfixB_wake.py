# ruff: noqa: N999
"""The short-wake fixture has 161 connected strands, not the retired 159."""

import pytest

from tests.tier1_offline.test_regression_farfield_products import (
    TestFfproofPost as _TestFfproofPost,
)

short_wake_proof = _TestFfproofPost.test_p0400_ffproof_a_short_wake_posts_the_b_row_na


@pytest.mark.requirement("FR-452")
def test_p0400_rfixb_short_wake_topology_and_warning(tmp_path):
    """P0400-RFIXB-WAKE: execute the explicit topology and written warning assertions."""
    short_wake_proof(tmp_path)
