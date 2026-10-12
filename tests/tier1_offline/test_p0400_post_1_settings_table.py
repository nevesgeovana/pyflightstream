"""P0400-WIDEFILL (PFS-2105.019): the wide settings table never carries the fill sentinel.

The fill reached the tidy code columns before the wide projection read them,
so a list-valued flag's ``f<id>_value`` became 999 in place of its length.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.settings_table import FLAG_IDS, settings_table
from tests.tier1_offline.test_settings_codebook import snapshot


@pytest.mark.parametrize((), [pytest.param(id="P0400-WIDEFILL")])
def test_p0400_widefill_a_list_flag_keeps_its_length():
    """P0400-WIDEFILL: SET_VORTICITY_DRAG_BOUNDARIES (an empty list) reads 0, never 999."""
    (row,) = settings_table([snapshot()], wide=True, fill=999)
    selection = FLAG_IDS["SET_VORTICITY_DRAG_BOUNDARIES"]
    assert row[f"f{selection}_value"] == 0
    assert 999 not in [value for key, value in row.items() if key.endswith("_value")]
