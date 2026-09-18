"""Tier 1, v0.23.0 items 9, 10 and 11: the three pproc tables that ship together.

THEY ARE ONE SHIPMENT AND THIS FILE IS ONE FILE FOR THAT REASON. `PprocSpec`
declares ``extra="forbid"``, so a pproc artifact written for this release is
REFUSED by an install carrying only some of them. Shipping two of three does
not degrade gracefully; it makes her files unreadable by the version that
almost has the feature.

ITEM 9, `phase_locked`, her words of 2026-09-17:

    "Phase_locked vira um pproc opcional e no arquivo de pproc o usuário fala o
    número mínimo de revs total e revs usadas para media. Se a especifica'cao
    da matriz bater esse número mínimo, o phase_locked 'e gerado"
    "Escreve last_revolutions_avg e lembra que o critério 'e o min_revolutions.
    Sendo igual ou maior, o phase-locked 'e gerado"
    "E não ter o rev min não recusa a polar, s'o não gera o phase_locked"

ITEM 10, `equations`:

    "no pproc, essas possíveis equações customizadas tambem precisam avisar
    quais famílias de malha elas são aplicaveis"
    "nas equações, não vamos aceitar apontar famílias, eles so podem apontar
    alias pois assim todos os coefs ficaram com _<alias>"
    "as equações precisam de alias para saber a familia ... deixa meshes_alias
    e frame como inputs da equations"

ITEM 11, the generated guides:

    "Dentro da pasta pproc de inputs, eu quero gerar um arquivo com todas as
    variáveis definições e um guia de como escrever equações customizadas,
    renomear, etc"
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyflightstream.cases import PprocSpec

ATOMIC = ("phase_locked", "equations", "glossary")


def test_the_three_tables_are_present_together():
    """The atomicity itself, asserted rather than remembered.

    `extra="forbid"` means a half shipment turns her artifact into one an
    install refuses, so this is a property of the release and not of one item.
    """
    fields = set(PprocSpec.model_fields)
    missing = [name for name in ATOMIC if name not in fields]
    assert not missing, f"the pproc spec carries only part of the shipment; missing {missing}"


def test_phase_locked_is_optional_and_absent_by_default():
    """A pproc that says nothing about it gets no phase-locked reduction."""
    spec = PprocSpec()
    assert spec.phase_locked is None


def test_the_gate_is_min_revolutions_and_the_comparison_is_at_least():
    """Her words: "sendo igual ou maior, o phase-locked 'e gerado"."""
    spec = PprocSpec(phase_locked={"min_revolutions": 5, "last_revolutions_avg": 2})
    assert spec.phase_locked.generated_for(revolutions=5.0) is True
    assert spec.phase_locked.generated_for(revolutions=5.5) is True
    assert spec.phase_locked.generated_for(revolutions=4.999) is False


def test_averaging_over_more_revolutions_than_the_minimum_is_refused():
    """A reduction cannot average over more history than it required to exist."""
    with pytest.raises(ValidationError):
        PprocSpec(phase_locked={"min_revolutions": 2, "last_revolutions_avg": 5})


def test_an_equation_points_at_an_alias_and_never_at_a_family():
    """Her rule, and the reason for it: every coefficient then carries `_<alias>`."""
    spec = PprocSpec(
        equations={"CTX": {"expression": "CT * 2", "meshes_alias": "PUSHER", "frame": "BODY"}}
    )
    assert spec.equations["CTX"].meshes_alias == "PUSHER"
    assert spec.equations["CTX"].frame == "BODY"


def test_an_equation_that_names_a_mesh_family_is_refused_by_name():
    """ "não vamos aceitar apontar famílias". Refused, and the refusal says why."""
    with pytest.raises(ValidationError) as caught:
        PprocSpec(
            equations={
                "CTX": {"expression": "CT * 2", "families": ["Blade1"], "meshes_alias": "PUSHER"}
            }
        )
    assert "famil" in str(caught.value).lower() or "extra" in str(caught.value).lower()


def test_an_equation_with_no_alias_is_refused():
    """Without an alias the derived coefficient has no `_<alias>` to carry."""
    with pytest.raises(ValidationError):
        PprocSpec(equations={"CTX": {"expression": "CT * 2", "frame": "BODY"}})


def test_the_glossary_is_a_table_the_user_can_extend():
    """She asked whether the package needs one and whether she can add to it."""
    spec = PprocSpec(glossary={"CT": "thrust coefficient, T / (rho n^2 D^4)"})
    assert spec.glossary["CT"].startswith("thrust coefficient")


def test_a_pproc_saying_nothing_about_any_of_the_three_still_loads():
    """The three are OPTIONAL. Adding them may not refuse every pproc she has."""
    spec = PprocSpec()
    assert spec.phase_locked is None
    assert spec.equations == {}
    assert spec.glossary == {}
