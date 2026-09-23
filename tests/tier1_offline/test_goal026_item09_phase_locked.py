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

# ITEM 9 IS 0.24.0 SCOPE, by the owner's decision of 2026-09-18: "vamos deixar o
# phase-locked para a 24". With items 10 and 11 already moved, this completes the
# rule she wrote into the goal -- "itens 9, 10 e 11 sobem juntos ou nenhum" --
# from the side where NONE of the three ships, so 0.23.0 adds no pproc table at
# all and a pproc written for 0.22.0 binds unchanged.
#
# THESE CASES ARE SKIPPED AND NOT ONE IS DELETED. Several of them found real
# defects today and the findings are worth more than the feature: the gate did
# not exist on the row-level path at all, and where it existed it counted the
# EXPORTED WINDOW rather than what the row turned, so a campaign turning six
# revolutions and exporting the last one failed a minimum of two it had met.
# Both fixes stay in the code; what waits is the `[phase_locked]` TABLE that
# lets a pproc ask for them, and the azimuthal shape she defined -- the mean at
# each azimuth across several revolutions, which the current reduction does not
# compute.
#
# The marker expires by itself: the field returning to `PprocSpec` in 0.24.0
# turns these red until the behaviour is wired, which is what they are for.
#
# 0.24.0: THE MARKER IS GONE, here and on the four equation and glossary cases
# below. Measured with the markers removed and nothing restored: 19 failed, 13
# passed across this file and its two siblings. The three tables are back on
# `PprocSpec` and each is CONSUMED by a campaign step, which
# `test_goal028_pproc_tables.py` holds through the command line.


#: What 0.23.0's pproc spec SHIPS, and what it must NOT carry.
#:
#: The rule was "the three tables are present together or absent together",
#: because `extra="forbid"` means an artifact written for this release is
#: REFUSED by an install carrying only part of them. On 2026-09-18 the owner
#: moved items 10 and 11 to 0.24.0, so the rule is now satisfied by the two
#: being ABSENT. The property is unchanged; which side of it holds is not.
#:
#: 0.24.0: THE REQUIREMENT MOVED AGAIN, AND SO DID THE SIDE THAT HOLDS. All three
#: ship in this release, so the rule is satisfied by the three being PRESENT
#: together and nothing is deferred. The assertion below is unchanged; what it
#: is handed is not. `DEFERRED` stays, empty, so the next table that is declared
#: before it is implemented has a place to be named.
SHIPPED = ("phase_locked", "equations", "glossary")
DEFERRED: tuple[str, ...] = ()


def test_the_pproc_spec_carries_this_release_and_not_the_next_one():
    """The atomicity itself, asserted rather than remembered.

    `extra="forbid"` means a half shipment turns her artifact into one an
    install refuses, so this is a property of the release and not of one item.

    THE SIDE OF THE PROPERTY CHANGED WHEN SHE MOVED ITEMS 10 AND 11 to 0.24.0
    on 2026-09-18. The absence is asserted rather than assumed, and that is the
    stronger half now: both fields were declared here while NOTHING consumed
    them, so a user could have written `[equations]` into a pproc, had the file
    accepted, and got no coefficient out of it. A refusal names the key; silent
    acceptance names nothing.
    """
    fields = set(PprocSpec.model_fields)
    missing = [name for name in SHIPPED if name not in fields]
    assert not missing, f"the pproc spec is missing {missing}, which this release ships"
    early = [name for name in DEFERRED if name in fields]
    assert not early, (
        f"the pproc spec carries {early}, which a later release ships. Declaring a table the "
        "release does not IMPLEMENT lets a user write it and get nothing back"
    )


def test_phase_locked_is_optional_and_absent_by_default():
    """A pproc that says nothing about it declares no gate; its reduction is ungated."""
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


def test_a_pproc_saying_nothing_about_phase_locked_still_loads():
    """It is OPTIONAL. Adding it may not refuse every pproc she already has.

    This also asserted `equations == {}` and `glossary == {}`; those fields left
    the spec with items 10 and 11 on 2026-09-18, and asking a model for a field
    it does not declare would raise here rather than measure anything.
    """
    spec = PprocSpec()
    assert spec.phase_locked is None


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

    from pyflightstream.cases import PhaseLockedSpec, PprocSpec
    from pyflightstream.cases.workflows import reduction_windows
    from tests.tier1_offline.test_reduce_by_rotor import transition_case

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
            "LAST_REVS_AVG": "0.25",
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


def test_the_gate_counts_the_run_and_not_the_exported_window():
    """THE CASE THAT DISCRIMINATES, and without it the fix is unproved.

    HER WORDS SETTLE IT, 2026-09-17: "Se a especificacao da matriz bater esse
    numero minimo, o phase_locked e gerado". The MATRIX SPECIFICATION is the
    run -- `DELTA_THETA` and `REVOLUTIONS`, or `RPM` and the seconds -- and the
    exported window is a different number entirely.

    THE ARITHMETIC OF THIS CASE, which is why it can tell the two apart:

        RPM 1200, DELTA_TIME 0.0001   ->   500 solver steps per revolution
        TIME_ITERATIONS 720           ->   the RUN turns 1.44 revolutions
        LAST_REVS_AVG 0.25            ->   the WINDOW holds 0.25 of one

    So at `min_revolutions = 1.0` the two readings disagree by the verdict, not
    by a digit: counting the run GENERATES the reduction, counting the window
    SKIPS it. Every other case in this file has the two readings agreeing, which
    is exactly why none of them caught this.

    A campaign that turns six revolutions and exports the last one is the real
    shape of the defect: it was read as turning one, and failed a minimum of two
    it had comfortably met.
    """
    from pyflightstream.cases import PhaseLockedSpec, PprocSpec, SimCase, SweepAxis
    from pyflightstream.cases.workflows import reduction_windows

    def plan_at(minimum: float):
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
                "LAST_REVS_AVG": "0.25",
            },
            pproc=PprocSpec(
                phase_locked=PhaseLockedSpec(min_revolutions=minimum, last_revolutions_avg=0.1)
            ),
        )
        plan = reduction_windows(case)
        assert plan is not None
        return plan

    # THE RUN TURNS 1.44, so a minimum of one is MET and the reduction exists.
    # Under the window reading this row holds 0.25 of a revolution and would be
    # skipped, so this single assertion is the whole discrimination.
    generated = plan_at(1.0)["phase_locked"]
    assert "windows" in generated, (
        "the gate skipped a run that turns 1.44 revolutions against a minimum of 1.0, "
        f"which means it counted the 0.25-revolution export window instead: {generated}"
    )

    # AND IT STILL REFUSES WHAT IT SHOULD, so the assertion above is not
    # satisfied by a gate that stopped gating: a refusal test alone is met by a
    # constant, and so is an acceptance test alone.
    skipped = plan_at(2.0)["phase_locked"]
    assert "skipped" in skipped, f"the run turns 1.44 revolutions and 2.0 were asked for: {skipped}"
    assert "1.44" in str(skipped["skipped"]), (
        "the skip states a number that is not what the row turned; a message naming the "
        f"window would read 0.25 here: {skipped['skipped']}"
    )
