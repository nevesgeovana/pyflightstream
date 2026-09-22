"""The five findings of the push-moment review of v0.25.1, each as the case that exposed it.

Three lenses read the patch that makes the post stage survive a log the solver stopped under,
and found that the patch itself published averages it had promised to refuse. Every case here is
one of theirs, written against the detector and the window judge rather than against a whole
campaign, so each states one fact.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import (
    _frozen_window_reason,
    _window_the_reduction_reads,
    freeze_of_log,
)
from pyflightstream.results import UnjudgeableSolve

LIVE = "+5.5597573E-4      \t+5.6313020E-4"
DEAD = "+0.0000000E+0      \t+0.0000000E+0"
HEADER = (
    "Iteration                      Res. Vel.                 Res. Pres.\n"
    "------------------------------------------------------------------\n"
)
RULE = "------------------------------------------------------------------\n"


def _block(step: int, kind: str) -> str:
    """One time-step block: live, frozen, or stopped under its header (unreadable)."""
    out = [f"Solving unsteady time-step iteration ({step}/72)..."]
    if kind == "unread":
        # the solver printed the header and stopped: rows never arrived, and the
        # table has no closing rule
        out.append(HEADER.rstrip("\n"))
        return "\n".join(out) + "\n"
    rows = [LIVE, LIVE, LIVE] if kind == "live" else [LIVE, DEAD, DEAD]
    out.append(HEADER.rstrip("\n"))
    out += [f"{100 * step + i}               \t{row}      \t-3.7E-5" for i, row in enumerate(rows)]
    out.append(RULE.rstrip("\n"))
    return "\n".join(out) + "\n"


def _log(*steps: tuple[int, str]) -> str:
    return "".join(_block(step, kind) for step, kind in steps)


@pytest.fixture
def verdict_of(tmp_path):
    """Ask THE PRODUCTION HELPER, through a real file.

    The first version of this module rebuilt `freeze_of_log`'s logic here, so
    reverting the helper left every case green: a test that cannot fail is not
    a test (the closing round, 2026-09-22).
    """
    written = [0]

    def ask(text: str):
        written[0] += 1
        path = tmp_path / f"log{written[0]}.txt"
        path.write_text(text, encoding="utf-8")
        return freeze_of_log(path)

    return ask


def test_a_confirmed_freeze_does_not_discard_the_unread_steps(verdict_of):
    """Finding 1, found by all three lenses.

    With step 58 unread and steps 60 and 61 frozen, the verdict was the freeze
    alone, so a window of [58, 59] -- before the freeze and over a block nobody
    read -- published its average.
    """
    text = _log((57, "live"), (58, "unread"), (59, "live"), (60, "frozen"), (61, "frozen"))
    verdict = verdict_of(text)
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert 58 in verdict.steps
    assert verdict.frozen_from == 60, "the freeze the read blocks prove is kept"
    assert _frozen_window_reason(verdict, (58, 59)) is not None, "an unread step was published"
    assert _frozen_window_reason(verdict, (60, 61)) is not None, "the freeze was published"
    assert _frozen_window_reason(verdict, (55, 57)) is None, "a clean window lost its average"


def test_a_frozen_step_after_an_unread_block_is_also_unread(verdict_of):
    """Finding 2: adjacency was tracked backward only.

    A freeze needs two consecutive frozen steps. With block 60 unread and step
    61 frozen, the streak never reached two and [61, 61] was accepted, although
    that pair is exactly what a freeze looks like.
    """
    verdict = verdict_of(_log((59, "live"), (60, "unread"), (61, "frozen"), (62, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (60, 61), verdict.steps
    assert _frozen_window_reason(verdict, (61, 61)) is not None


def test_a_frozen_step_before_an_unread_block_is_also_unread(verdict_of):
    """The mirror of the case above, which the first patch did handle."""
    verdict = verdict_of(_log((59, "live"), (60, "frozen"), (61, "unread"), (62, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (60, 61), verdict.steps


def test_the_neighbour_rule_does_not_cross_a_gap_in_the_step_numbers(verdict_of):
    """Finding 3: steps that are not consecutive cannot form the pair.

    A frozen step 1 followed by an unread step 3 marked BOTH, which refuses a
    window over step 1 for a pairing that cannot exist.
    """
    verdict = verdict_of(_log((1, "frozen"), (3, "unread"), (4, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (3,), verdict.steps
    assert _frozen_window_reason(verdict, (1, 1)) is None


@pytest.mark.parametrize(
    ("window", "refused"),
    [((58, 58), True), ((57, 59), True), ((58, 62), True), ((59, 62), False), ((50, 57), False)],
)
def test_a_window_is_refused_exactly_when_it_touches_an_unread_step(verdict_of, window, refused):
    """The contract in one line, over the shapes a window can take.

    Both directions matter: refusing a window that does not touch the unread
    step costs an average nobody had reason to doubt, which is the mistake the
    first version of this patch made across a whole point.
    """
    verdict = verdict_of(_log((57, "live"), (58, "unread"), (59, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert (_frozen_window_reason(verdict, window) is not None) is refused


def test_an_unread_block_does_not_reach_across_a_restart(verdict_of):
    """The closing round's first fix, measured by the lens that asked for it.

    A log can hold two attempts, and a restarted one prints its step numbers
    again from the beginning. Comparing against "the last unread step" rather
    than the block immediately before then marked a frozen step of the second
    attempt unread because a step of the same number in the first could not be
    read, and refused a window nothing had contaminated.
    """
    verdict = verdict_of(_log((1, "unread"), (1, "live"), (2, "frozen"), (3, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (1,), verdict.steps
    assert _frozen_window_reason(verdict, (2, 2)) is None, "a clean window lost its average"


def test_a_phase_locked_window_is_judged_over_the_steps_it_reads(verdict_of):
    """GH-1 of the independent review of GitHub main, 2026-09-22.

    A phase-locked average interpolates at fractional moments, one per blade,
    each an offset inside one revolution before blade one, so `np.interp` reads
    the integer steps bracketing each moment. A window declared [95, 200] with
    53 steps per revolution reads step 94. The reader made step 94 unread and
    changed its plotted value: the published average moved and the manifest
    stated [95, 200] with no skip.
    """
    verdict = verdict_of(_log((93, "live"), (94, "unread"), (95, "live"), (96, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (94,), verdict.steps
    declared = (95, 200)
    # the window as declared does not contain step 94, and a reduction that
    # reads only its own steps keeps its product
    assert _frozen_window_reason(verdict, declared) is None
    # but the phase-locked reduction reads one revolution earlier, and THAT
    # window is what must be judged
    reads = _window_the_reduction_reads("phase_locked", {"steps_per_revolution": 53.0}, declared)
    assert reads[0] <= 94, reads
    assert _frozen_window_reason(verdict, reads) is not None, "an unread step fed the average"


def test_a_reduction_that_reads_only_its_own_steps_is_judged_over_them(verdict_of):
    """The other side: widening the judged window for everything would cost averages.

    A time average reads the steps it states, so its judged window is its own;
    a phase-locked one without a recorded revolution cannot be widened either,
    and says so by keeping its declared window.
    """
    declared = (95, 200)
    per_revolution = {"steps_per_revolution": 53.0}
    assert _window_the_reduction_reads("time_average", per_revolution, declared) == (95, 200)
    assert _window_the_reduction_reads("phase_locked", {}, declared) == (95, 200)
