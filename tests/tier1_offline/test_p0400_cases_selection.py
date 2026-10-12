"""Tier 1: families selection reads `all` alike everywhere and refuses retired words (0.40.0)."""

from typing import NoReturn, get_type_hints

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.selection import (
    select_families,
    select_group_members,
    warn_a_selector_that_guesses,
)

INVENTORY = ["Wing", "Fuselage", "Blade1", "Blade2"]


def _is_blade(name):
    return name.startswith("Blade")


@pytest.mark.parametrize("selection", [["all"], ["Wing", "all"]])
def test_p0400_all_in_a_families_list_selects_every_surface(selection):
    """P0400-ALL-IN-LIST (PFS-2104.002, PFS-2085.012): `all` in a list is not a family name."""
    assert select_families(selection, INVENTORY, _is_blade) == [INVENTORY]
    assert select_group_members(["all"], INVENTORY) == INVENTORY
    # The bare word keeps the command's own every-boundary form.
    assert select_families("all", INVENTORY, _is_blade) == [[]]


def test_p0400_the_retired_selector_reader_is_declared_to_never_return():
    """P0400-SELECTOR-REFUSES (PFS-2095.063): it refuses, so nothing after it is selection code."""
    assert get_type_hints(warn_a_selector_that_guesses)["return"] is NoReturn
    assert warn_a_selector_that_guesses.__doc__.startswith("Refuse")
    for word in ("airframe", "blades"):
        with pytest.raises(CampaignConfigError, match="no longer accepted"):
            select_families(word, INVENTORY, _is_blade)
        with pytest.raises(CampaignConfigError, match="no longer accepted"):
            select_families(["Wing", word], INVENTORY, _is_blade)
