"""The five findings of the push-moment review of v0.25.1, each as the case that exposed it.

Three lenses read the patch that makes the post stage survive a log the solver stopped under,
and found that the patch itself published averages it had promised to refuse. Every case here is
one of theirs, written against the detector and the window judge rather than against a whole
campaign, so each states one fact.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.cases.windows import AZIMUTHAL
from pyflightstream.post.products import (
    _frozen_window_reason,
    freeze_of_log,
)
from pyflightstream.post.products import (
    _window_the_reduction_reads as _reducer_steps,
)
from pyflightstream.post.unsteady import TimestepSeries
from pyflightstream.results import UnjudgeableSolve


def _window_the_reduction_reads(name, entry, window, plotted, plan=None):
    """Keep the older endpoint cases on the reducer's new exact-set interface."""
    plan = plan or {}
    steps = np.asarray(plotted or list(range(window[0], window[1] + 1)))
    columns = ["CL_TOTAL", *[f"CL_{family}" for family in plan.get("blade_families", [])]]
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={column: steps[:, None] for column in columns},
        sources=(),
    )
    read = _reducer_steps(
        name,
        entry,
        window,
        series,
        columns,
        plan.get("blades", 0),
        {"families": plan.get("blade_families", []), "rpm": plan.get("rpm", 1)},
    )
    return min(read), max(read)


#: A plan whose second blade sits at a fraction of a step behind blade one: with
#: 53 steps per revolution and two blades the offset is 26.5, so every sample of
#: that blade is read from the two plotted steps around it. A whole-step offset
#: reads no step outside the window at all, which is what the third independent
#: reading of GitHub main measured and what these cases had wrong.
INTERPOLATING = {"blades": 2, "blade_families": ["Blade1", "Blade2"], "rpm": 7585.0}

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
    # and the azimuthal reduction is judged over the steps its samples are read
    # from. EVERY AZIMUTH IS SAMPLED, not only the last: with 53 steps per
    # revolution, two blades and two revolutions the rows are steps 95 to 200,
    # and the row at azimuth 121 reads blade two at 94.5 -- so step 94 IS read,
    # from the plotted steps 94 and 95. Deriving this from the extremes alone
    # gave 95 twice, and both times it was wrong.
    dense = list(range(1, 201))
    entry = {"steps_per_revolution": 53.0, "revolutions": 2.0, "shape": AZIMUTHAL}
    reads = _window_the_reduction_reads("phase_locked", entry, declared, dense, INTERPOLATING)
    assert reads == (94, 200), reads
    assert _frozen_window_reason(verdict, reads) is not None, "an unread step fed the average"


def test_a_reduction_that_reads_only_its_own_steps_is_judged_over_them(verdict_of):
    """The other side: widening the judged window for everything would cost averages.

    A time average reads the steps it states, so its judged window is its own;
    a phase-locked one without a recorded revolution cannot be widened either,
    and says so by keeping its declared window.
    """
    declared = (95, 200)
    per_revolution = {"steps_per_revolution": 53.0}
    dense = list(range(1, 201))
    assert _window_the_reduction_reads("time_average", per_revolution, declared, dense) == (
        95,
        200,
    )
    assert _window_the_reduction_reads("phase_locked", {}, declared, ()) == (95, 200)


def test_the_interpolation_support_is_the_history_and_not_a_revolution(verdict_of):
    """The re-read of GitHub main, 2026-09-22, measured this bound wrong BOTH ways.

    A revolution is neither necessary nor sufficient. On a history that plots
    every step, a window of [95, 200] reads step 94 and nothing earlier, so
    refusing it for an unread step 93 costs an average the arithmetic never
    touches. On a sparse history -- steps 1, then 95 to 200 -- the same window
    reaches step 1, which a one-revolution bound leaves outside and publishes.
    """
    dense = list(range(1, 201))
    sparse = [1, *range(95, 201)]
    entry = {"steps_per_revolution": 53.0, "revolutions": 2.0, "shape": AZIMUTHAL}
    reads = _window_the_reduction_reads("phase_locked", entry, (95, 200), dense, INTERPOLATING)
    assert reads == (94, 200), "the row at azimuth 121 reads blade two at 94.5"
    # the same samples on a history that plots nothing between 1 and 95: the
    # bracket below 94.5 is then step 1, which no revolution-wide bound finds
    assert _window_the_reduction_reads("phase_locked", entry, (95, 200), sparse, INTERPOLATING) == (
        1,
        200,
    )

    # the consequence, through the judge: the declared window is clean, the
    # support is not
    verdict = verdict_of(_log((92, "live"), (93, "unread"), (94, "live"), (95, "live")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    assert _frozen_window_reason(verdict, (95, 200)) is None, "the declared window is clean"
    assert _frozen_window_reason(verdict, reads) is None, "step 93 is outside the support"


def test_a_passage_series_is_not_widened_because_it_does_not_interpolate():
    """The QA lens, 2026-09-22: my support fix refused clean passage averages.

    The planner writes a passage series when the pproc declares no
    `[phase_locked]` table, and that product averages the steps of each passage
    and reads nothing else. Widening its window refused passages whose mean does
    not move whatever the unread step holds -- measured: passages [58,59] and
    [60,61] with step 59 unread, and the second mean 60.5 either way.
    """
    dense = list(range(1, 201))
    passages = {"steps_per_revolution": 53.0}  # no shape: the legacy series
    assert _window_the_reduction_reads(
        "phase_locked", passages, (60, 61), dense, INTERPOLATING
    ) == (60, 61)
    # AND WHERE THE AZIMUTHS REACH BELOW THE DECLARED WINDOW, the azimuthal one
    # is judged over them: three steps per revolution put the final revolution
    # at steps 59 to 61, and blade two reads 58.5 at the row of azimuth 60, so
    # the support opens at the plotted step below it.
    azimuthal = {"steps_per_revolution": 3.0, "revolutions": 1.0, "shape": AZIMUTHAL}
    reads = _window_the_reduction_reads("phase_locked", azimuthal, (60, 61), dense, INTERPOLATING)
    assert reads == (58, 61), reads


def test_the_support_takes_the_plotted_step_above_the_window_too(verdict_of):
    """The QA lens, 2026-09-22: I fixed the lower bracket and left the upper one.

    Interpolation reads the plotted steps on EITHER side of each moment. With
    steps 1, 95 ... 199, 201 plotted and a window of [95, 200], the moment at
    200 is bracketed by 199 and 201, so step 201 feeds the average -- and the
    record stated [95, 200] with no skip. Changing only that value by 1000
    moved the step-200 coefficient from 173.5 to 423.5.
    """
    entry = {"steps_per_revolution": 53.0, "revolutions": 2.0, "shape": AZIMUTHAL}
    gapped = [1, *range(95, 200), 201]
    # the UPPER bracket is what this case is about: the history stops at 199 and
    # resumes at 201, so the sample at 200 is read from 199 and 201. Below, the
    # sample at 94.5 brackets down to step 1, since nothing between is plotted.
    assert _window_the_reduction_reads("phase_locked", entry, (95, 200), gapped, INTERPOLATING) == (
        1,
        201,
    )
    # a history that plots the window's end reads nothing beyond it
    ends_at_window = list(range(94, 201))
    assert _window_the_reduction_reads(
        "phase_locked", entry, (95, 200), ends_at_window, INTERPOLATING
    ) == (94, 200)
    verdict = verdict_of(_log((199, "live"), (201, "unread")))
    assert isinstance(verdict, UnjudgeableSolve), verdict
    reads = _window_the_reduction_reads("phase_locked", entry, (95, 200), gapped, INTERPOLATING)
    assert _frozen_window_reason(verdict, reads) is not None, "a step above the window was read"


def test_every_azimuth_is_sampled_and_not_only_the_last_step():
    """The QA lens, 2026-09-22, on what the sample bracketing still missed.

    The reducer writes one row per step of the final revolution and each blade
    samples EVERY one of them. Taking `last - offset` alone reached only the
    last row's samples: with three steps per revolution and two blades, the row
    at azimuth 60 reads 58.5, and an unread step 58 fed the published average
    while the guard reported the window unchanged.
    """
    entry = {"steps_per_revolution": 3.0, "revolutions": 1.0, "shape": AZIMUTHAL}
    dense = list(range(1, 62))
    reads = _window_the_reduction_reads("phase_locked", entry, (59, 61), dense, INTERPOLATING)
    assert reads == (58, 61), reads


def test_a_per_rotor_reduction_is_judged_by_that_rotors_blades():
    """The same lens: the blades of a per-rotor plan live under its alias.

    Reading the top level returned no blade offset at all, so a four-blade
    rotor was judged as though it had one blade and an unread step its samples
    reach went unnoticed.
    """
    from pyflightstream.post.products import _the_plan_of_a_reduction

    plan = {
        "rotors": {
            "PUSHER": {
                "blades": 4,
                "blade_families": ["B1", "B2", "B3", "B4"],
                "rpm": 2200.0,
            }
        }
    }
    own = _the_plan_of_a_reduction(plan, "PUSHER")
    assert own == plan["rotors"]["PUSHER"], own
    assert _the_plan_of_a_reduction(plan, None) is plan, "a row-level reduction keeps the row's"

    entry = {"steps_per_revolution": 3.0, "revolutions": 1.0, "shape": AZIMUTHAL}
    dense = list(range(1, 62))
    assert _window_the_reduction_reads("phase_locked", entry, (59, 61), dense, own) == (58, 61)
    assert _window_the_reduction_reads("phase_locked", entry, (59, 61), dense, plan) == (59, 61), (
        "the top level states no blades, and a judge that reads it sees one blade"
    )
