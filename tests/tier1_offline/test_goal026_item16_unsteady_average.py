"""Tier 1: the averaging window item 16 rests on, asserted on the function a stage calls.

THIS FILE PINNED `post.unsteady.converged_window` UNTIL 0.24.0 (CR-05), a
function no product called and whose rule was the OPPOSITE of the shipped one:
it discarded the FIRST ``after_rev`` revolutions and kept everything after,
where the products keep the LAST revolutions or iterations the matrix row
states. A mutant of the shipped rule was therefore caught by nothing here. The
function is deleted and these cases drive `post.products._matrix_window`, which
is what `write_products` calls, down to `cases.windows.averaging_span`.

THE EXPECTED WINDOWS ARE THE CONVENTION'S, worked by hand: the window is
inclusive, counted in solver steps from 1, ends at the run's last step and is
exactly as long as the row states. One revolution of 100 steps ending at step
400 is steps 301 to 400, which is 100 steps; 300 to 400 would be 101, and 101
to 400 is what discarding the first revolution gives.

WHAT STAYS is the rule that the package holds exactly ONE implementation of the
average: item 16 is a window and a routing, never a second averaging routine.
"""

from __future__ import annotations

from pyflightstream.post.products import _matrix_window
from pyflightstream.post.unsteady import blade_passage_average


class _Row:
    """A matrix row as the post stage meets it: variables and nothing else."""

    def __init__(self, **variables):
        self.variables = {key: str(value) for key, value in variables.items()}


class _Record:
    """A run record carrying only the clock the post stage reads."""

    def __init__(self, *, last, per_revolution):
        self.reductions = {"time_iterations": last, "steps_per_revolution": per_revolution}


def test_the_window_keeps_the_last_revolutions_and_not_what_follows_the_first():
    """Four revolutions of 100 steps; the row asks for the last ONE.

    Keeping the last revolution is 301-400. Discarding the first revolution,
    the rule the deleted function held, is 101-400.
    """
    window = _matrix_window(_Row(LAST_REVS_AVG="1.0"), _Record(last=400, per_revolution=100))
    assert window == (301, 400), window


def test_the_window_is_exactly_as_long_as_the_row_states():
    """Inclusive at both ends: `last - first + 1` IS the stated length.

    The off-by-one that starts one step early averages 101 steps under a row
    that says 100, and nothing in the product would show it.
    """
    for stated, steps in (("100", 100), ("1", 1), ("37", 37)):
        first, last = _matrix_window(
            _Row(LAST_ITERS_AVG=stated), _Record(last=400, per_revolution=None)
        )
        assert last == 400, (stated, first, last)
        assert last - first + 1 == steps, (stated, first, last)


def test_a_longer_window_reaches_further_back_and_still_ends_at_the_last_step():
    """More revolutions move the FIRST step earlier; the last step does not move."""
    record = _Record(last=400, per_revolution=100)
    one = _matrix_window(_Row(LAST_REVS_AVG="1.0"), record)
    three = _matrix_window(_Row(LAST_REVS_AVG="3.0"), record)
    assert one == (301, 400), one
    assert three == (101, 400), three
    assert three[0] < one[0] and three[1] == one[1]


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
