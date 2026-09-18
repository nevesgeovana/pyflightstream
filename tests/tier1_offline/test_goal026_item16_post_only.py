"""Tier 1, v0.23.0 item 16: the averaging window is POST-ONLY.

THE OWNER'S ACCEPTANCE RULE FOR THE WHOLE RELEASE, in her own words:

    "eu ja tenho simulacoes prontas, quero refazer so o pproc, e isso inclui
     Windows e HPC. Item que exige re-run nao esta pronto." -- 2026-09-18

Item 16 shipped failing it, and the independent review of `main` found that
(L6-06, 2026-09-18). `_stated_window` reads the window off the RUN RECORD,
which `reduction_windows` wrote when the point EXECUTED. So:

- editing `LAST_REVS_AVG` in the matrix and running only `post` changed
  nothing -- the record still held the window the run was given; and
- a record written before 0.23.0 carries no `window_stated` flag at all, so
  `_stated_window` returned None and the polar silently fell back to the
  native last-time-step export.

Neither said anything. She would have re-run the post stage, opened the file,
and read an average over a window she had not asked for.

SHE SETTLED THE DIRECTION, 2026-09-18: recompute it in the post stage, and the
MATRIX WINS THE RECORD.

IT COSTS NO RE-RUN, which is the whole point. The plan already writes
`steps_per_revolution` and `time_iterations` beside the window it derived, so a
count of revolutions has a length in solver steps and the run has a last step.
That is everything the derivation needs; nothing here reads the solver, the
geometry or the script.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.products import _matrix_window, _stated_window


class _Row:
    """A matrix row as the post stage meets it: variables and nothing else."""

    def __init__(self, **variables):
        self.variables = {key: str(value) for key, value in variables.items()}


class _Record:
    """A run record carrying only the reduction plan the post stage reads."""

    def __init__(self, **plan):
        self.reductions = dict(plan)


def _ran(*, last=1000, per_revolution=250, window=(751, 1000), stated=True):
    """A record of a run that turned a rotor 4 revolutions in 1000 steps."""
    return _Record(
        window_stated=stated,
        time_iterations=last,
        steps_per_revolution=per_revolution,
        time_average={"windows": [list(window)], "window_from": "last_revs_avg"},
    )


def test_editing_the_matrix_changes_the_window_with_no_re_run():
    """THE DEFECT, stated as the thing she would have done.

    The run executed with one revolution of averaging, so the record holds
    751-1000. She now wants three. She edits the matrix and runs POST only.
    """
    record = _ran(window=(751, 1000))
    assert _stated_window(record) == (751, 1000), "the fixture must hold the RUN's window"

    asked = _matrix_window(_Row(LAST_REVS_AVG="3.0"), record)
    assert asked == (251, 1000), (
        "three revolutions of 250 steps ending at step 1000 is 251-1000; the "
        f"record's own window is 751-1000 and must not win: {asked}"
    )


def test_a_record_written_before_the_release_still_gets_the_window():
    """The half that is worse, because it produces a DIFFERENT KIND of file.

    A pre-0.23.0 record carries no `window_stated`, so `_stated_window` returns
    None and the polar comes from the native export -- one instant of a cycle,
    in a file that looks exactly like an averaged one.
    """
    old = _ran(stated=False)
    assert _stated_window(old) is None, "the fixture must be a pre-0.23.0 record"

    assert _matrix_window(_Row(LAST_REVS_AVG="1.0"), old) == (751, 1000), (
        "a simulation she already has must reduce from its matrix without a re-run"
    )


def test_iterations_are_taken_as_steps_and_revolutions_through_the_clock():
    """The two keys resolve through different halves of the recorded clock.

    `last_iters_avg` is already a count of steps. `last_revs_avg` is a count of
    REVOLUTIONS and needs `steps_per_revolution` to have a length at all.
    """
    record = _ran()
    assert _matrix_window(_Row(LAST_ITERS_AVG="100"), record) == (901, 1000)
    assert _matrix_window(_Row(LAST_REVS_AVG="2.0"), record) == (501, 1000)


def test_a_fractional_revolution_is_a_window_and_not_a_rounding_error():
    """Her decision: `last_revs_avg` TAKES A FLOAT."""
    assert _matrix_window(_Row(LAST_REVS_AVG="0.5"), _ran()) == (876, 1000)
    assert _matrix_window(_Row(LAST_REVS_AVG="1.5"), _ran()) == (626, 1000)


def test_a_window_longer_than_the_run_is_the_whole_run_and_never_before_it():
    """A window reaching past step one would ask for history that does not exist."""
    assert _matrix_window(_Row(LAST_REVS_AVG="99"), _ran()) == (1, 1000)


def test_revolutions_without_a_rotor_rate_resolve_to_nothing_rather_than_a_guess():
    """A count of revolutions has NO LENGTH IN STEPS without the rate.

    `_averaging_window` refuses this by name at plan time. Here the record
    simply cannot answer, and the fallback to what the run recorded is right --
    never a default window invented at post time.
    """
    no_clock = _Record(window_stated=True, time_iterations=1000)
    assert _matrix_window(_Row(LAST_REVS_AVG="1.0"), no_clock) is None


def test_both_keys_together_resolve_to_nothing_rather_than_picking_one():
    """`_averaging_window` refuses the pair at plan time and names both.

    Reaching it HERE can only mean a matrix edited after the run, so this falls
    through to what the record states rather than silently preferring one.
    """
    assert _matrix_window(_Row(LAST_REVS_AVG="1.0", LAST_ITERS_AVG="100"), _ran()) is None


@pytest.mark.parametrize(
    "variables",
    [
        {},
        {"LAST_REVS_AVG": "-"},
        {"LAST_REVS_AVG": ""},
        {"LAST_REVS_AVG": "0"},
        {"LAST_REVS_AVG": "-2"},
        {"LAST_ITERS_AVG": "not a number"},
    ],
)
def test_a_row_that_states_no_usable_key_falls_through_to_the_record(variables):
    """Including the unstated cell, which every matrix she already has writes.

    None here is not a failure: it is the post stage saying the MATRIX asked for
    nothing, so the window the run recorded stands.
    """
    assert _matrix_window(_Row(**variables), _ran()) is None


def test_a_malformed_record_costs_this_product_and_never_the_stage():
    """The rule every reader in this module follows: return None, never raise."""
    for record in (
        _Record(),
        _Record(time_iterations="many"),
        _Record(time_iterations=0),
        object(),
    ):
        assert _matrix_window(_Row(LAST_REVS_AVG="1.0"), record) is None


def test_no_matrix_row_is_not_a_window():
    """A simulation the stage cannot tie to a row reduces as it was run."""
    assert _matrix_window(None, _ran()) is None
