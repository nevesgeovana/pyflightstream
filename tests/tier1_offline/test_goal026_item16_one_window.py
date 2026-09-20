"""Tier 1, v0.23.0 item 16: ONE averaging window, stated on the matrix row.

THE OWNER'S WORDS, 2026-09-18:

    "fica na matriz e e input obrigatorio de unsteady_rotor, para unsteady
    apenas, fica last_iters_avg. Eu quero isso na matriz por conversar
    diretamente com setup temporal."

    "a media per_blade usa a mesma info de last_revs e last_iters que o unsteady
    plots"

WHY IT IS ON THE ROW. The window converses with the TEMPORAL SETUP, and
`DELTA_TIME`, `TIME_ITERATIONS` and `RPM` are all on the same row. A window in
the pproc would sit apart from the quantities that give it a length.

THE WORD THAT DOES THE WORK IS "INFO". `last_revs_avg` is a COUNT OF
REVOLUTIONS, not a range of steps, and that is what lets one instruction serve a
row turning two rotors at two speeds: each converts the count with its OWN
revolution. Reading it as a range instead would impose one rotor's turn on the
other, which is the defect FR-68 exists against -- and which a test in
`test_reduce_by_rotor.py` caught when this was first wired that way.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows import reduction_windows


def _rotor_row(**overrides):
    """A rotor row with the retired export window CLEARED unless a case sets one.

    `WINDOW_DEGREES` is on the fixture by default, and it is the key item 16
    retires, so a case that does not say otherwise gets a row stating none of
    the three retired spellings. A case that DOES pass one is testing the
    migration and keeps it.
    """
    from tests.tier1_offline.test_workflows import rotor_case

    return rotor_case(**{"WINDOW_DEGREES": None, **overrides})


@pytest.mark.parametrize("revs", ["0.5", "1.0", "3.0"])
def test_every_product_of_the_point_shares_the_window_at_every_value(revs):
    """THE PROPERTY AT MORE THAN ONE VALUE, which is what makes it a property.

    The case below asserts the same equality at `1.0` alone -- and ONE
    REVOLUTION IS EXACTLY THE VALUE AT WHICH THE OLD BEHAVIOUR AND THE NEW ONE
    COINCIDE, because `per_blade` used to derive this rotor's last complete
    revolution. A mutant reverting `per_blade` to its own derivation SURVIVED
    the whole tier-1 suite, and the QA lens of the release round measured what
    it would have published:

        revs   time_average      per_blade
        0.5    [[471, 720]]      [[221, 720]]
        3.0    [[  1, 720]]      [[221, 720]]

    At three revolutions the polar averages 720 steps while `per_blade` averages
    500, and every test was green. These three values discriminate.
    """
    plan = reduction_windows(_rotor_row(LAST_REVS_AVG=revs))
    assert plan is not None
    assert plan["time_average"]["windows"] == plan["per_blade"]["windows"], (
        revs,
        plan["time_average"]["windows"],
        plan["per_blade"]["windows"],
    )


def test_an_old_window_key_warns_that_it_is_on_a_clock():
    """A PROMISE REGISTERED AND NEVER SPOKEN IS A DEADLINE NOBODY IS TOLD ABOUT.

    The three `WINDOW_*` retirements were defined and carried into
    `DEPRECATIONS`, which satisfies the ledger guard and starts the countdown to
    0.26.0 -- and nothing warned, so a user would have met the removal rather
    than the notice. This repository has recorded that exact defect before, by
    name, about `ROW_MOVING_BOUNDARIES`; the QA lens of the release round
    measured it again here.
    """
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        reduction_windows(_rotor_row(WINDOW_DEGREES="90"))
    spoken = [str(item.message) for item in caught]
    assert any("WINDOW_DEGREES" in text and "0.27.0" in text for text in spoken), spoken
    # THE REPLACEMENT IS NAMED, because a notice that does not say what to write
    # instead sends the reader to the source to find out. NAMED AS THE ROW MUST
    # SPELL IT (0.24.0, MC-04): this asserted the lower-case `last_revs_avg`,
    # which is the spelling the matrix does NOT read -- the next case of this
    # file writes the key as `LAST_REVS_AVG`, and a row written in lower case is
    # refused or ignored. The expectation encoded the defect and is corrected.
    assert any("LAST_REVS_AVG" in text for text in spoken), spoken
    assert not any("last_revs_avg" in text for text in spoken), spoken


def test_a_new_key_beats_an_old_one_and_the_row_is_told_which_answered():
    """The precedence existed only as a code comment; nothing asserted it."""
    plan = reduction_windows(_rotor_row(WINDOW_DEGREES="90", LAST_REVS_AVG="1.0"))
    assert plan is not None
    assert plan["time_average"]["windows"] == [[221, 720]], plan["time_average"]
    assert "LAST_REVS_AVG" in plan["time_average"]["window_from"], plan["time_average"]


def test_the_row_states_the_window_and_every_product_of_the_point_shares_it():
    """ONE WINDOW, and the assertion is that the two are the SAME object of steps.

    `per_blade` derived its own window before this item -- the last complete
    revolution -- which agreed with the row only when the row asked for exactly
    one revolution and disagreed the moment it asked for half or for three. Two
    windows put a difference in the fourth digit that no reader can attribute to
    anything.
    """
    plan = reduction_windows(_rotor_row(LAST_REVS_AVG="1.0"))
    assert plan is not None
    assert plan["time_average"]["windows"] == plan["per_blade"]["windows"], plan
    assert plan["time_average"]["windows"] == [[221, 720]], (
        "one revolution of a 500-step rotor, ending at the run's last step"
    )


@pytest.mark.parametrize(
    ("revs", "expected"),
    [("0.5", [[471, 720]]), ("1.0", [[221, 720]]), ("1.25", [[96, 720]])],
)
def test_the_window_accepts_a_float_number_of_revolutions(revs, expected):
    """SHE STATED THE FLOAT EXPLICITLY: "aqui aceitando float".

    One and a half revolutions is a window a reader can mean, and rounding it to
    two would silently average over a third more history than the row asked for.
    The three cases here are chosen so that a truncating implementation gives a
    different answer for each.
    """
    plan = reduction_windows(_rotor_row(LAST_REVS_AVG=revs))
    assert plan is not None
    assert plan["time_average"]["windows"] == expected, plan["time_average"]


def test_a_window_longer_than_the_run_is_the_whole_run_and_not_a_refusal():
    """A row asking for more history than it has asked for everything it has.

    Refusing there would cost her the products of a campaign that already
    happened, over an arithmetic edge -- which is the one thing her acceptance
    rule forbids: "eu ja tenho simulacoes prontas, quero refazer so o pproc".
    """
    plan = reduction_windows(_rotor_row(LAST_REVS_AVG="9.0"))
    assert plan is not None
    assert plan["time_average"]["windows"] == [[1, 720]], plan["time_average"]


def test_one_instruction_gives_each_rotor_its_own_steps():
    """THE CASE THAT DISTINGUISHES A COUNT FROM A RANGE, and it is item 16 meeting FR-68.

    Two rotors at two speeds have revolutions of different LENGTHS. Reading
    `last_revs_avg` as a range of steps would hand both the same span, which is
    one rotor's turn imposed on the other; reading it as a COUNT hands each its
    own. The two spans below must therefore DIFFER, and each must be that
    rotor's own revolution.
    """
    from tests.tier1_offline.test_reduce_by_rotor import transition_case

    case = transition_case()
    case = case.model_copy(update={"variables": {**case.variables, "LAST_REVS_AVG": "1.0"}})
    plan = reduction_windows(case)
    assert plan is not None

    spans = {}
    for alias in ("LIFT_L1", "PUSHER"):
        block = plan["rotors"][alias]
        (first, last) = block["per_blade"]["windows"][0]
        spans[alias] = last - first + 1
        assert spans[alias] == pytest.approx(round(block["steps_per_revolution"]), abs=1), (
            alias,
            "one revolution of THIS rotor, in its own steps",
            block["per_blade"]["windows"],
            block["steps_per_revolution"],
        )
    assert spans["LIFT_L1"] != spans["PUSHER"], (
        "both rotors got the same span, so the count was read as a range and one "
        f"rotor's turn was imposed on the other: {spans}"
    )


def test_revolutions_and_iterations_are_two_ways_to_say_one_window_and_both_is_refused():
    """A row stating both has not said which it means, and guessing would be a number.

    The same shape as `resume` against `force_rerun`: two keys asking for
    opposite-but-overlapping things are refused together rather than resolved by
    precedence nobody wrote down.
    """
    from pyflightstream.cases import CampaignConfigError

    with pytest.raises(CampaignConfigError, match="two ways to say one window"):
        reduction_windows(_rotor_row(LAST_REVS_AVG="1.0", LAST_ITERS_AVG="100"))


def test_a_row_that_states_neither_keeps_the_answer_it_has_always_had():
    """THE MIGRATION, asserted rather than hoped for.

    Her acceptance rule governs this item like every other: a matrix written
    before 0.23.0 must bind and produce what it produced. Such a row states no
    averaging key, so the retired `WINDOW_*` spellings still answer and
    `per_blade` still takes the last complete revolution.
    """
    plan = reduction_windows(_rotor_row())
    assert plan is not None
    assert "windows" in plan["time_average"], plan["time_average"]
    assert plan["per_blade"]["windows"] == [[221, 720]], plan["per_blade"]
