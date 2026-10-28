"""P0490-GOVERNING: governing choices distinguish automatic level destinations."""

from dataclasses import replace

from pyflightstream.workspace._refine._config import (
    FamilySpec,
    RefineRequest,
    canonical_selection,
    level_tag,
    tag_selection,
)


def test_p0490_governing_changes_a_short_level_tag():
    """P0490-GOVERNING (FR-3298): swapping the leader cannot reuse one level folder."""
    first = RefineRequest(
        specs={"A": FamilySpec(factor=2, governing=True), "B": FamilySpec(factor=3)}
    )
    second = replace(
        first, specs={"A": FamilySpec(factor=2), "B": FamilySpec(factor=3, governing=True)}
    )
    assert canonical_selection(first, ["A", "B"]) != canonical_selection(second, ["A", "B"])
    assert level_tag(first, ["A", "B"]) != level_tag(second, ["A", "B"])
    assert tag_selection(first, ["A", "B"]) == ["A", "B"]


def test_p0490_grid_auto_tags_include_the_leaders_directional_factors():
    """P0490-GOVERNING: inherited factors and grid_auto participate in the hash."""
    first = RefineRequest(
        specs={
            "A": FamilySpec(chordwise=2, spanwise=3, governing=True),
            "B": FamilySpec(method="grid_auto"),
        }
    )
    second = replace(first, specs={**first.specs, "A": replace(first.specs["A"], spanwise=4)})
    assert level_tag(first, ["A", "B"]) != level_tag(second, ["A", "B"])
    assert tag_selection(first, ["A", "B"]) == ["A", "B"]
    explicit = replace(first, tag="named")
    assert level_tag(explicit, ["A", "B"]) == "named"
    assert tag_selection(explicit, ["A", "B"]) is None
    plain = RefineRequest(specs={"A": FamilySpec(factor=2), "B": FamilySpec(factor=2)})
    assert level_tag(plain, ["A", "B"]) == "R2"
