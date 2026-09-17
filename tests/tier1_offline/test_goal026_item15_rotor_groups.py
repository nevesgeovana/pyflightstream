"""Tier 1, v0.23.0 item 15: every rotor the reference declares HAS an integration group.

THE OWNER'S WORDS, 2026-09-17, once groups became named:

    "Agora que os grupos vao ser declarados por alias, cria obrigatoriamente um
    grupo de integração para cada rotor se ja nao existir."

and, on what makes it checkable:

    "T e Q sempre vai ser coletado por rotor, e' a forma que declaramos como
    alias. Então qualquer inconsistência o plan pega."

WHY IT IS NOT A CONVENIENCE. The rotor table of item 6 integrates thrust and
torque over ONE rotor's own families. If the group it integrates over is left
to a user remembering to declare it, then the coefficient and the group are two
lists kept in step by hand, and the day they drift one rotor's thrust is
reported as another's coefficient. That is the same class as a rotor turning
the wrong way: a number that looks right and is wrong.

SO THE GROUP IS CREATED FROM THE ROTOR ITSELF and the two agree by
construction. A group DECLARED under a rotor's alias whose families are not
that rotor's is the inconsistency she asked the plan to catch, and it is
refused by name rather than silently preferred one way or the other.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, RotorBlock
from pyflightstream.workspace.inputs import rotor_integration_groups


def _rotor(alias: str, blades: list[str], general: list[str] | None = None) -> RotorBlock:
    return RotorBlock(
        alias=alias,
        axis="Z",
        diameter_m=1.0,
        families_blades=blades,
        families_general=general or [],
    )


def test_a_rotor_with_no_declared_group_gets_one_made_from_its_own_families():
    """The gap is filled, and it is filled from the rotor rather than from a guess."""
    rotors = {"PUSHER": _rotor("PUSHER", ["Blade1", "Blade2"], ["Spinner"])}
    resolved = rotor_integration_groups(rotors, {})
    assert "PUSHER" in resolved, resolved
    assert set(resolved["PUSHER"]) == {"Spinner", "Blade1", "Blade2"}, resolved


def test_a_group_the_user_declared_is_never_replaced():
    """Creation fills a gap; it does not overrule what she wrote."""
    rotors = {"PUSHER": _rotor("PUSHER", ["Blade1", "Blade2"])}
    declared = {"PUSHER": ["Blade1", "Blade2"], "AIRFRAME_WET": ["Fuselage"]}
    resolved = rotor_integration_groups(rotors, declared)
    assert resolved["AIRFRAME_WET"] == ["Fuselage"], resolved
    assert set(resolved["PUSHER"]) == {"Blade1", "Blade2"}, resolved


def test_a_declared_group_under_a_rotor_alias_with_other_families_is_refused():
    """The inconsistency she asked the plan to catch, refused by name.

    Silently preferring one of the two would attribute one rotor's thrust to
    another rotor's coefficient, which is the defect this item exists to make
    impossible.
    """
    rotors = {"PUSHER": _rotor("PUSHER", ["Blade1", "Blade2"])}
    declared = {"PUSHER": ["SomeoneElsesWing"]}
    with pytest.raises(CampaignConfigError) as caught:
        rotor_integration_groups(rotors, declared)
    message = str(caught.value)
    assert "PUSHER" in message
    # BOTH SETS IN THE MESSAGE. A refusal that names only the alias sends the
    # reader back to two files to find out which half is wrong.
    assert "SomeoneElsesWing" in message, message
    assert "Blade1" in message, message


def test_every_declared_rotor_gets_one_and_a_second_rotor_is_not_forgotten():
    """Two rotors, one declared group: the other is created, not skipped."""
    rotors = {
        "PUSHER": _rotor("PUSHER", ["Blade1", "Blade2"]),
        "LIFT_L1": _rotor("LIFT_L1", ["LH_L1_B1", "LH_L1_B2"]),
    }
    resolved = rotor_integration_groups(rotors, {"PUSHER": ["Blade1", "Blade2"]})
    assert set(resolved) == {"PUSHER", "LIFT_L1"}, resolved
    assert set(resolved["LIFT_L1"]) == {"LH_L1_B1", "LH_L1_B2"}, resolved
