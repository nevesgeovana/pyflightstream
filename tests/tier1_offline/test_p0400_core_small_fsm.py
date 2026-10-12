"""P0400-FSMTOKEN (PFS-2104.001): a boundary token that differs from a label only in case names it.

``blade_1`` against ``Blade_1, Blade_2, Blade_3`` used to fail the
case-sensitive exact test and fall through to the family reading, which
returned all three blades. A case-folded exact match is now tried before the
family, so the token answers that one surface.
"""

from __future__ import annotations

from pyflightstream._fsm import names_of, resolve_family

BLADES = ["Hub", "Blade_1", "Blade_2", "Blade_3"]


def test_p0400_fsmtoken_case_differs_selects_the_one_surface() -> None:
    """P0400-FSMTOKEN: a case-folded exact match wins over the family."""
    assert names_of("blade_1", BLADES) == ["Blade_1"]
    assert names_of("BLADE_2", BLADES) == ["Blade_2"]
    assert resolve_family("blade_3", {name: i for i, name in enumerate(BLADES, 1)}) == (4,)


def test_p0400_fsmtoken_family_word_and_exact_label_still_resolve() -> None:
    """P0400-FSMTOKEN: the family word still selects the family, an exact label itself."""
    assert names_of("blade", BLADES) == ["Blade_1", "Blade_2", "Blade_3"]
    assert names_of("Blade", BLADES) == ["Blade_1", "Blade_2", "Blade_3"]
    assert names_of("Blade_2", BLADES) == ["Blade_2"]
    assert names_of("hub", BLADES) == ["Hub"]
    assert names_of("Wing_1", BLADES) == []
