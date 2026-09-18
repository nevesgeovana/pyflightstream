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


def test_the_gate_reaches_the_plan_and_a_short_run_is_skipped_not_refused():
    """ITEM 9 THROUGH THE PLAN, which is where the gate is a gate at all.

    `PhaseLockedSpec.generated_for` held the comparison and had NO CALLER, so a
    pproc declaring `min_revolutions` got a phase-locked reduction whatever the
    row turned. Every test of it called the method directly.

    HER RULE HAS TWO HALVES and the second is the one a wiring gets wrong: "se a
    especificacao da matriz bater esse numero minimo, o phase_locked e gerado",
    and "nao ter o rev min nao recusa a polar, so nao gera o phase_locked". A
    short run is SKIPPED WITH A REASON, never refused -- losing a polar because
    a rotor did not turn long enough is taking a product away from a campaign
    that already happened.
    """
    from pyflightstream.cases import PhaseLockedSpec
    from pyflightstream.cases.workflows import phase_locked_gate

    gate = PhaseLockedSpec(min_revolutions=3.0, last_revolutions_avg=1.0)

    # Long enough: the reduction is planned and says nothing about being gated.
    assert phase_locked_gate(gate, revolutions=4.0) is None
    assert phase_locked_gate(gate, revolutions=3.0) is None, "AT LEAST, not more than"

    # Too short: a SKIP carrying the reason, and the numbers that decided it.
    skipped = phase_locked_gate(gate, revolutions=1.5)
    assert isinstance(skipped, dict) and "skipped" in skipped, skipped
    reason = str(skipped["skipped"])
    assert "1.5" in reason and "3" in reason, reason


def test_a_pproc_that_declares_no_gate_is_not_gated():
    """Absent is not zero and not a refusal: the reduction is planned as before.

    A pproc saying nothing about `phase_locked` got one before this release and
    gets one now, so adding the gate changes nothing for a workspace that does
    not use it.
    """
    from pyflightstream.cases.workflows import phase_locked_gate

    assert phase_locked_gate(None, revolutions=0.1) is None


def test_the_gate_takes_the_phase_locked_reduction_and_leaves_per_blade():
    """IT SKIPPED BOTH for one commit, and that takes a second product away.

    Her rule gates one reduction: "nao ter o rev min nao recusa a polar, so nao
    gera o phase_locked". `per_blade` needs ONE COMPLETE REVOLUTION, not the
    minimum a pproc asks of a phase average, and the two numbers have nothing to
    do with each other. Gating a neighbour with someone else's threshold is the
    same shape as refusing the polar -- a product taken from a campaign that
    already happened.

    The QA lens of the closing round reproduced it: with `min_revolutions=99`,
    `per_blade` came back skipped, carrying the phase-locked reason verbatim.

    THIS GOES THROUGH THE PLAN, which my two earlier cases claimed in their
    titles and did not do: they called `phase_locked_gate` directly, so neither
    could see what the plan did with its answer.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_reduce_by_rotor import transition_case

    from pyflightstream.cases import PhaseLockedSpec, PprocSpec
    from pyflightstream.cases.workflows import reduction_windows

    case = transition_case()
    gate = PhaseLockedSpec(min_revolutions=99.0, last_revolutions_avg=1.0)
    # The fixture carries no pproc, so one is built rather than copied: the
    # gate has to come from somewhere the plan reads, and that is the artifact.
    base = case.pproc if case.pproc is not None else PprocSpec()
    case = case.model_copy(update={"pproc": base.model_copy(update={"phase_locked": gate})})

    plan = reduction_windows(case)
    assert plan is not None
    for alias in ("LIFT_L1", "PUSHER"):
        entry = plan["rotors"][alias]
        assert "skipped" in entry["phase_locked"], (alias, entry["phase_locked"])
        assert "windows" in entry["per_blade"], (
            alias,
            "per_blade was gated by the phase-locked minimum, which is not its rule",
            entry["per_blade"],
        )


def test_the_gate_reaches_the_row_that_does_not_name_its_rotors():
    """THE GATE WAS ON ONE PATH OF TWO, and the one it missed is the ordinary row.

    `phase_locked_gate` was called in `_the_passages_of_one_rotor` only, which
    runs for a row that names its rotors under `rotors`. The row-level path --
    the plain single-rotor row, which is most rows -- built `plan["phase_locked"]`
    with no gate anywhere in it. The QA lens of the closing round reproduced it
    against a pproc asking for ninety-nine revolutions:

        phase_locked: {'windows': [[596, 720]], 'period_steps': 125, ...}

    A run turning about four revolutions, handed a full phase-locked reduction.
    For such a row item 9 did nothing at all, and every test of item 9 was green
    because all of them asked the gate function directly or went down the
    per-rotor path.

    THE ROW HERE STATES NO ROTORS BLOCK on purpose. That is the whole point of
    the case: it is the path the gate could not see.
    """
    from pyflightstream.cases import PhaseLockedSpec, PprocSpec, SimCase, SweepAxis
    from pyflightstream.cases.workflows import reduction_windows

    case = SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={
            "VELOCITY": "30.0",
            "RPM": "1200",
            "BLADES": "4",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
            "WINDOW_DEGREES": "90",
        },
        pproc=PprocSpec(
            phase_locked=PhaseLockedSpec(min_revolutions=99.0, last_revolutions_avg=1.0)
        ),
    )

    plan = reduction_windows(case)
    assert plan is not None
    assert "rotors" not in plan, "this case must exercise the ROW-LEVEL path, and it does not"
    assert "skipped" in plan["phase_locked"], (
        "the row-level plan built a full phase-locked reduction against a pproc asking "
        f"for 99 revolutions from a run that turns about four: {plan['phase_locked']}"
    )
    assert "99" in str(plan["phase_locked"]["skipped"]), plan["phase_locked"]
    # HER RULE'S SECOND HALF, on this path too: the gate takes the phase-locked
    # reduction and nothing else. `per_blade` needs one complete revolution,
    # which this run has, and the phase-locked minimum is not its threshold.
    #
    # THIS ASSERTION IS SATISFIED BY THE STRUCTURE AND NOT BY A DECISION, and
    # saying so is the point of the comment. A mutant that gates `per_blade`
    # here SURVIVED: the row-level path assigns `plan["per_blade"]` in both
    # branches of its own `if` at the end of the function, so anything written
    # to it earlier is overwritten and the mistake cannot be made on this path.
    # That is a stronger guarantee than a test, and it is why the mutant is dead
    # code rather than a hole in this case. The path where the mistake IS
    # reachable is the per-rotor one -- it was made there, by dropping a
    # `return` -- and the case above it is what catches that.
    assert "windows" in plan["per_blade"], (
        "per_blade was gated by the phase-locked minimum on the row-level path, "
        f"which is not its rule: {plan['per_blade']}"
    )
