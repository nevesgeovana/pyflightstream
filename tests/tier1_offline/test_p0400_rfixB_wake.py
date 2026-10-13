# ruff: noqa: N999
"""The short-wake fixture has 161 connected strands, not the retired 159."""

import pytest

from tests.tier1_offline.test_p0400_ffproof_post import (
    test_p0400_ffproof_a_short_wake_posts_the_b_row_na as short_wake_proof,
)


@pytest.mark.requirement("FR-452")
def test_p0400_rfixb_short_wake_topology_and_warning(tmp_path):
    """P0400-RFIXB-WAKE: execute the explicit topology and written warning assertions."""
    short_wake_proof(tmp_path)
