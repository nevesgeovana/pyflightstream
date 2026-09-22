"""The five findings of the push-moment review of v0.25.1, each as the case that exposed it.

Three lenses read the patch that makes the post stage survive a log the solver stopped under,
and found that the patch itself published averages it had promised to refuse. Every case here is
one of theirs, written against the detector and the window judge rather than against a whole
campaign, so each states one fact.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import _frozen_window_reason
from pyflightstream.results import UnjudgeableSolve, frozen_time_steps

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


def _verdict(text: str) -> UnjudgeableSolve | None:
    """What the post stage makes of a log, without touching the filesystem."""
    unjudged: list[int] = []
    found = frozen_time_steps(text, unjudged=unjudged)
    if found is not None and not unjudged:
        return found  # a plain FrozenSolve
    if not unjudged:
        return None
    steps = tuple(sorted(set(unjudged)))
    return UnjudgeableSolve(
        first_step=min(steps if found is None else (*steps, found.first_step)),
        count=len(steps),
        steps=steps,
        frozen_from=None if found is None else found.first_step,
    )


def test_a_confirmed_freeze_does_not_discard_the_unread_steps():
    """Finding 1, found by all three lenses.

    With step 58 unread and steps 60 and 61 frozen, the verdict was the freeze
    alone, so a window of [58, 59] -- before the freeze and over a block nobody
    read -- published its average.
    """
    text = _log((57, "live"), (58, "unread"), (59, "live"), (60, "frozen"), (61, "frozen"))
    verdict = _verdict(text)
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert 58 in verdict.steps
    assert verdict.frozen_from == 60, "the freeze the read blocks prove is kept"
    assert _frozen_window_reason(verdict, (58, 59)) is not None, "an unread step was published"
    assert _frozen_window_reason(verdict, (60, 61)) is not None, "the freeze was published"
    assert _frozen_window_reason(verdict, (55, 57)) is None, "a clean window lost its average"


def test_a_frozen_step_after_an_unread_block_is_also_unread():
    """Finding 2: adjacency was tracked backward only.

    A freeze needs two consecutive frozen steps. With block 60 unread and step
    61 frozen, the streak never reached two and [61, 61] was accepted, although
    that pair is exactly what a freeze looks like.
    """
    verdict = _verdict(_log((59, "live"), (60, "unread"), (61, "frozen"), (62, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (60, 61), verdict.steps
    assert _frozen_window_reason(verdict, (61, 61)) is not None


def test_a_frozen_step_before_an_unread_block_is_also_unread():
    """The mirror of the case above, which the first patch did handle."""
    verdict = _verdict(_log((59, "live"), (60, "frozen"), (61, "unread"), (62, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (60, 61), verdict.steps


def test_the_neighbour_rule_does_not_cross_a_gap_in_the_step_numbers():
    """Finding 3: steps that are not consecutive cannot form the pair.

    A frozen step 1 followed by an unread step 3 marked BOTH, which refuses a
    window over step 1 for a pairing that cannot exist.
    """
    verdict = _verdict(_log((1, "frozen"), (3, "unread"), (4, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert verdict.steps == (3,), verdict.steps
    assert _frozen_window_reason(verdict, (1, 1)) is None


@pytest.mark.parametrize(
    ("window", "refused"),
    [((58, 58), True), ((57, 59), True), ((58, 62), True), ((59, 62), False), ((50, 57), False)],
)
def test_a_window_is_refused_exactly_when_it_touches_an_unread_step(window, refused):
    """The contract in one line, over the shapes a window can take.

    Both directions matter: refusing a window that does not touch the unread
    step costs an average nobody had reason to doubt, which is the mistake the
    first version of this patch made across a whole point.
    """
    verdict = _verdict(_log((57, "live"), (58, "unread"), (59, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert (_frozen_window_reason(verdict, window) is not None) is refused
