"""P0400-STRICT-BOUNDARY: an absent numbered boundary is refused only by a known inventory.

The refusal of PFS-2029.25 (a cell citing Hub1 over a geometry with Hub2 and
Hub3 is refused by exact name) fired on an EMPTY inventory as well, where
nothing is known about the geometry (an offline render), and so refused every
numbered cell of every row. A known inventory that lacks the name refuses; an
empty one keeps the behaviour from before the refusal: the token selects
nothing and the caller decides.

The decision of 2026-10-12 bounds the refusal to a token cited ALONE (a matrix
cell, a bare families word, a one-word list or group). A MEMBER of a longer
list, of a group or of an alias selects its exact name only and is never
refused for lacking it: FR-320 warns and plans READY, and the alias decision of
2026-09-09 ignores a member the file lacks.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases._skipped_families import (
    declared_names_the_geometry_lacks,
    names_no_boundary_answers,
)
from pyflightstream.cases.reference_blocks import CampaignConfigError
from pyflightstream.cases.selection import resolve_alias, select_families, select_group_members

ROUTES = ["family", "list", "group", "alias"]
ALONE = ["family", "list", "group"]
SECTOR = ["Hub", "Blade1", "Blade2"]
SIX_BLADES = [f"Blade{number}" for number in range(1, 7)]


def _select(route: str, inventory: list[str]) -> object:
    if route == "group":
        return select_group_members(["Blade1"], inventory)
    if route == "alias":
        return resolve_alias("blades_a", inventory, {"blades_a": ["Blade1"]})
    selection = "Blade1" if route == "family" else ["Blade1"]
    return select_families(selection, inventory, lambda name: False)


@pytest.mark.parametrize("route", ALONE)
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


@pytest.mark.parametrize("strict", [True, False])
def test_p0400_strict_boundary_a_sector_row_list_selects_what_it_carries(strict):
    """P0400-STRICT-BOUNDARY (PFS-2029.25): six blades over a two-blade sector, no refusal.

    FR-320: a sector row lacking four blades warns and plans READY, never refuses.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert select_families(SIX_BLADES, SECTOR, lambda name: False, strict=strict) == [
            ["Blade1", "Blade2"]
        ]
        assert select_group_members(SIX_BLADES, SECTOR, strict=strict) == ["Blade1", "Blade2"]
    # FR-320 R4: the plan's warning names each lacked blade, and the refusal of
    # --ignore-missing-families false does not catch one whose family answers.
    lacked = [(None, f"Blade{number}") for number in range(3, 7)]
    assert declared_names_the_geometry_lacks(SIX_BLADES, SECTOR, {}) == lacked
    assert names_no_boundary_answers(SIX_BLADES, SECTOR, {}, lambda name: False) == []


@pytest.mark.parametrize("strict", [True, False])
def test_p0400_strict_boundary_an_alias_member_is_ignored(strict):
    """P0400-STRICT-BOUNDARY (PFS-2029.25): an alias's absent numbered member is ignored.

    The alias decision of 2026-09-09: a member the file lacks is ignored, and a
    numbered member never selects its numbered siblings, nested or not.
    """
    aliases = {"rotor": ["blades_a", "Hub"], "blades_a": SIX_BLADES}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert resolve_alias("blades_a", SECTOR, aliases) == ["Blade1", "Blade2"]
        assert select_families("rotor", SECTOR, lambda name: False, aliases, strict=strict) == [
            ["Blade1", "Blade2", "Hub"]
        ]
        assert select_group_members(["rotor"], SECTOR, aliases, strict=strict) == [
            "Blade1",
            "Blade2",
            "Hub",
        ]
        assert resolve_alias("hubs", ["Hub2", "Hub3"], {"hubs": ["Hub1"]}) == []
    assert declared_names_the_geometry_lacks("rotor", SECTOR, aliases) == [
        ("blades_a", f"Blade{number}") for number in range(3, 7)
    ]
    assert names_no_boundary_answers("rotor", SECTOR, aliases, lambda name: False) == []


def test_p0400_strict_boundary_a_list_member_never_selects_its_siblings():
    """P0400-STRICT-BOUNDARY (PFS-2029.25): ``Hub1`` beside ``Wing`` selects Wing alone."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert select_group_members(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"]) == ["Wing"]
        assert select_families(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"], bool) == [["Wing"]]
    assert declared_names_the_geometry_lacks(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"], {}) == [
        (None, "Hub1")
    ]
    assert names_no_boundary_answers(["Hub1", "Wing"], ["Hub2", "Hub3", "Wing"], {}, bool) == []
