"""P0400-STRICT-BOUNDARY: an absent numbered boundary is refused only by a known inventory.

The refusal of PFS-2029.25 (a cell citing Hub1 over a geometry with Hub2 and
Hub3 is refused by exact name) fired on an EMPTY inventory as well, where
nothing is known about the geometry (an offline render), and so refused every
numbered cell of every row. A known inventory that lacks the name refuses; an
empty one keeps the behaviour from before the refusal: the token selects
nothing and the caller decides.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases.reference_blocks import CampaignConfigError
from pyflightstream.cases.selection import resolve_alias, select_families, select_group_members

ROUTES = ["family", "list", "group", "alias"]


def _select(route: str, inventory: list[str]) -> object:
    if route == "group":
        return select_group_members(["Blade1"], inventory)
    if route == "alias":
        return resolve_alias("blades_a", inventory, {"blades_a": ["Blade1"]})
    selection = "Blade1" if route == "family" else ["Blade1"]
    return select_families(selection, inventory, lambda name: False)


@pytest.mark.parametrize("route", ROUTES)
def test_p0400_strict_boundary_known_inventory_refuses(route):
    """P0400-STRICT-BOUNDARY (PFS-2029.25): a known inventory lacking Blade1 refuses it."""
    with pytest.raises(CampaignConfigError, match=r"Blade1.*Blade2.*Blade3"):
        _select(route, ["Blade2", "Blade3", "Hub"])


@pytest.mark.parametrize("route", ROUTES)
def test_p0400_strict_boundary_empty_inventory_is_not_refused(route):
    """P0400-STRICT-BOUNDARY (PFS-2029.25): an empty inventory is unknown, not lacking."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = _select(route, [])
    assert result == []


def test_p0400_strict_boundary_a_position_is_not_a_numbered_name():
    """P0400-STRICT-BOUNDARY (PFS-2029.25): ``1`` is a position, never refused as a name."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert select_group_members(["1"], ["Blade1", "S", "N"]) == []


def test_p0400_strict_boundary_a_name_under_another_case_is_that_name():
    """P0400-STRICT-BOUNDARY (PFS-2029.25): ``blade1`` over ``Blade1`` selects it, as names_of."""
    assert select_group_members(["blade1"], ["Blade1", "Hub"]) == ["Blade1"]
