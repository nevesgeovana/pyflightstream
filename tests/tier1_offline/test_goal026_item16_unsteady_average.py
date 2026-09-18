"""Tier 1, v0.23.0 item 16: the unsteady POLAR and rotor table are the plots averaged.

THE OWNER'S WORDS, 2026-09-17:

    "E sim, POLAR e [rotor table] do unsteady vai ser vir do unsteady plots fazendo a
    media similar ao per blades"

WHY THIS SENTENCE MAKES THE WHOLE RELEASE REACHABLE. It means an unsteady
point's polar is not read from some other export that a finished run might or
might not carry: it is DERIVED from the time history the run already
collected. So a workspace whose simulations are done needs no solver to
produce any of it, which is the acceptance rule of this release -- and it
becomes a property of the design rather than a hope.

NO SECOND AVERAGE IS WRITTEN, and that is the finding this item produced. The
first writing of the checker's probe asked for a `window_average` function.
`blade_passage_average` already is that function, and its own docstring says it
is "the only implementation of this average in the package ... two
implementations of one average is how two published numbers come to disagree".
So item 16 is ROUTING and a WINDOW, never a second averaging routine.

THE WINDOW IS THE ONE `per_blade` USES, anchored on the export-after-revolutions
variable, so a reader comparing a POLAR against the per-blade rows beneath it
is comparing numbers taken over the same steps.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.unsteady import blade_passage_average, converged_window


def test_the_window_is_anchored_on_the_export_after_revolutions_variable():
    """The same anchor `per_blade` uses, so the two are comparable by construction."""
    window = converged_window(first_step=1, last_step=400, steps_per_revolution=100, after_rev=2.0)
    assert window == (201, 400), window


def test_the_window_is_the_last_converged_one_and_not_the_whole_history():
    """Her reading: "faz sentido sempre olhar a ultima janela convergida".

    Averaging the whole history includes the transient, which is the part of an
    unsteady run that is not the answer.
    """
    whole = converged_window(first_step=1, last_step=400, steps_per_revolution=100, after_rev=0.0)
    late = converged_window(first_step=1, last_step=400, steps_per_revolution=100, after_rev=3.0)
    assert whole == (1, 400), whole
    assert late == (301, 400), late
    assert late[0] > whole[0]


def test_a_history_shorter_than_the_anchor_is_refused_rather_than_averaged():
    """A shorter history averaged as a whole one is an average of a run that did not finish.

    This is the same refusal `write_reduction_table` already makes about a
    window reaching past the rows a table holds, made at the moment the window
    is DERIVED rather than at the moment it is used.
    """
    with pytest.raises(ValueError) as caught:
        converged_window(first_step=1, last_step=150, steps_per_revolution=100, after_rev=3.0)
    assert "revolution" in str(caught.value).lower()


def test_there_is_exactly_one_implementation_of_the_average():
    """The guard on the fix rather than on the defect.

    If a second averaging routine ever appears beside `blade_passage_average`,
    two published numbers can disagree and nothing will say which is right.
    This asserts the package still offers ONE.
    """
    from pyflightstream.post import unsteady

    averagers = [
        name
        for name in dir(unsteady)
        if name.endswith("_average") and callable(getattr(unsteady, name))
    ]
    assert averagers == ["blade_passage_average"], averagers
    assert callable(blade_passage_average)


def test_the_stage_derives_one_window_and_hands_it_to_the_products():
    """ITEM 16 THROUGH THE STAGE, which is where "one window" is a claim at all.

    The four tests above exercise `converged_window` directly, and it had NO
    caller in the package: every one of them passed over a release where the
    polar, the rotor table and `per_blade` each took whatever window they
    happened to be given -- which is the state "one window" exists to end.

    THE POINT OF ONE WINDOW is not tidiness. A reader comparing a coefficient
    against the per-blade rows beneath it is comparing numbers from the same
    part of the run; two windows put a difference in the fourth digit that
    nobody can attribute to anything.

    The stage derives it from what the run recorded: `steps_per_revolution`
    off the reductions plan, and the export-after-revolutions anchor off the
    row. This asserts that ONE function answers for the whole simulation.
    """
    from pyflightstream.post.products import unsteady_window

    window = unsteady_window(
        reductions={"steps_per_revolution": 100},
        variables={"EXPORT_UNSTEADY_AFTER_REV": 2.0},
        first_step=1,
        last_step=400,
    )
    assert window == (201, 400), window


def test_a_simulation_that_states_no_anchor_gets_no_window():
    """`None` and not the whole history, which is the transient included.

    Averaging a run from step one mixes the transient with the answer -- the
    design error a fixture in this suite still records -- so a row that does
    not say where the transient ends gets no window rather than a wrong one.
    """
    from pyflightstream.post.products import unsteady_window

    assert (
        unsteady_window(
            reductions={"steps_per_revolution": 100},
            variables={},
            first_step=1,
            last_step=400,
        )
        is None
    )


def test_a_history_too_short_for_the_anchor_gets_no_window_rather_than_a_refusal():
    """The refusal belongs to the derivation; the STAGE writes fewer products.

    `converged_window` refuses a history shorter than its anchor, which is
    right where a caller asked for a window. At the stage a short history is an
    ordinary campaign -- a run that stopped early -- and it must cost that
    simulation its rotor table, never the polars of every other simulation
    beside it.
    """
    from pyflightstream.post.products import unsteady_window

    assert (
        unsteady_window(
            reductions={"steps_per_revolution": 100},
            variables={"EXPORT_UNSTEADY_AFTER_REV": 9.0},
            first_step=1,
            last_step=400,
        )
        is None
    )
