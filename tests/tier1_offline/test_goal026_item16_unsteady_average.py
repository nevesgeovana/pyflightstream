"""Tier 1, v0.23.0 item 16: the one unsteady window, DERIVED HERE AND NOT DELIVERED.

READ THIS FIRST, because the file's title claimed the opposite until a closing
round measured it. **Item 16 did not ship in 0.23.0.** The window is derived and
no product calls it: the polar still reads the native loads export, and the
rotor table is built from that export's surfaces rather than from the plots. The
tests below hold the DERIVATION to the right rule, which is worth having, and the
last test in the file is the guard that stops the change log claiming more than
that. What blocks the wiring is a question to the owner, not code: `QUESTION-0230`.

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
variable, so that a reader comparing a POLAR against the per-blade rows beneath
it WOULD BE comparing numbers taken over the same steps. That is the design and
it is the tense this sentence now carries: no reader gets that yet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream.post.unsteady import blade_passage_average, converged_window

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "pyflightstream"
_CHANGELOG = _ROOT / "CHANGELOG.md"

#: A CALL, not a mention: the name followed by an open parenthesis. The
#: definition line `def unsteady_window(` matches this too and is excluded by
#: the `def ` prefix rather than by excluding its file, so a second definition
#: anywhere would still be seen.
_CALL = re.compile(r"(?<!def )\bunsteady_window\s*\(")


def _production_callers() -> list[str]:
    """Every line under `src/` that CALLS `unsteady_window`, as `path:line`."""
    found = []
    for path in sorted(_SRC.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _CALL.search(line):
                found.append(f"{path.relative_to(_ROOT).as_posix()}:{number}")
    return found


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


def test_one_function_derives_the_window_from_what_the_run_recorded():
    """THE DERIVATION ONLY. Nothing in the package calls it, and the name said otherwise.

    THIS TEST WAS CALLED `test_the_stage_derives_one_window_and_hands_it_to_the_products`
    AND ITS ASSERTION IS UNCHANGED. Only the name and this docstring moved,
    because only they were wrong: they claimed the window reached the products,
    and the single assertion below calls one function and compares a tuple.
    Nothing was weakened to make anything pass -- the assertion passed before
    and passes now, which is precisely the problem a name like that one hides.

    The old docstring said the four tests above "passed over a release where the
    polar, the rotor table and `per_blade` each took whatever window they
    happened to be given", as though this test had ended that. It had not:
    `unsteady_window` has no caller either, which the guard below now measures
    rather than describes.

    THE POINT OF ONE WINDOW is not tidiness. A reader comparing a coefficient
    against the per-blade rows beneath it is comparing numbers from the same
    part of the run; two windows put a difference in the fourth digit that
    nobody can attribute to anything. That is still the right rule, and the
    derivation below is still the right derivation. It is just not delivered.
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


def test_the_change_log_says_item_16_is_wired_exactly_when_it_is():
    """THE GUARD ON THE FALSE CLAIM, and it is two-way by construction.

    WHAT WENT WRONG. The change log's 0.23.0 section said "An unsteady POLAR and
    rotor table are the plots averaged over the same window `per_blade` uses".
    Three things in that one sentence were false: the polar still reads the
    native loads export, the rotor table is built from that export's surfaces
    and not from the plots at all, and `unsteady_window` -- the function the
    sentence rests on -- HAS NO CALLER, so nothing is averaged over any window.
    A closing round found it by grepping for the caller rather than the
    definition, which is this estate's own rule for measuring delivery.

    WHY A TEST AND NOT A CORRECTION. Correcting the sentence fixes this
    instance; it does nothing about the next one. The failure mode is that the
    prose and the wiring drift apart in EITHER direction, so this measures both
    and fails on either:

        no caller + the change log claims delivery  -> the defect that shipped
        a caller  + the change log still says NOT WIRED -> stale in the other
                                                           direction, and the
                                                           reader is told a
                                                           capability is absent
                                                           when it is there

    So whoever wires item 16 is failed by this test until they say so in the
    change log, and whoever writes the claim is failed until the wiring exists.
    It is deliberately NOT a test that item 16 is unfinished: it pins the two
    statements to each other, and it goes green on the day the item lands.
    """
    callers = _production_callers()
    text = _CHANGELOG.read_text(encoding="utf-8")
    claims_unwired = "The one unsteady window is DERIVED and is NOT YET WIRED" in text

    if callers:
        assert not claims_unwired, (
            "the change log still says the one unsteady window is NOT YET WIRED, and "
            f"these production lines call it: {callers}. Item 16 landed and the entry "
            "that told the reader it had not is now the false sentence."
        )
    else:
        assert claims_unwired, (
            "nothing under src/ calls `unsteady_window`, so no product is averaged over "
            "the one window -- and the change log does not say so. A change log entry "
            "describing an uncalled function reads to every user as a delivered "
            "capability. Either wire it or say it is not wired."
        )
