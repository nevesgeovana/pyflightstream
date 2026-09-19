"""A rotor's surfaces are resolved as its loads are, never by exact membership.

The independent review of GitHub main (GH-1): a rotor stating `Spinner` and `blade1`
against an export naming `Spinner` and `Blade1` kept only `Spinner`, so a plot group
over the spinner alone was taken for the rotor's whole history. The expected set is
the one `rotor_shaft_loads` integrates, which resolves through the package's group
resolver and compares without case.
"""

from __future__ import annotations

from types import SimpleNamespace

from pyflightstream.post.products import _rotor_surfaces_carried

SURFACES = {"Spinner": {}, "Blade1": {}, "Blade2": {}, "Wing": {}}


def test_a_family_named_in_another_case_is_carried():
    # `spinner` is no exact name, so the resolver reads it as the family `spinner`,
    # which the export carries as `Spinner`; exact membership lost it.
    rotor = SimpleNamespace(families_general=["spinner"], families_blades=["Blade1"])
    assert _rotor_surfaces_carried(rotor, SURFACES, None) == ["Spinner", "Blade1"]


def test_a_family_label_carries_every_member_and_nothing_else():
    rotor = SimpleNamespace(families_general=["Spinner"], families_blades=["Blade"])
    assert _rotor_surfaces_carried(rotor, SURFACES, None) == ["Spinner", "Blade1", "Blade2"]


def test_an_alias_carries_what_it_names():
    rotor = SimpleNamespace(families_general=["Spinner"], families_blades=["blades"])
    carried = _rotor_surfaces_carried(rotor, SURFACES, {"blades": ["Blade1", "Blade2"]})
    assert carried == ["Spinner", "Blade1", "Blade2"]
