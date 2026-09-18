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
