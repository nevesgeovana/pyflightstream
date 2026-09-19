"""The averaging window has ONE resolver, asked per point and per rotor (0.24.0).

THE DEFECT (PO-01), as the owner would meet it. 0.23.0 made the matrix win the
record for the averaging window, and that fix had exactly one call site: it fed
the unsteady POLAR. The three reductions written beside the plots table took
their windows from the run record, frozen when the point executed. So she edits
``LAST_ITERS_AVG``, runs ``pyfs-matrix post``, and the polar averages the new
window while ``<point>_time_average.csv`` in the same folder averages the old
one, and the manifest says both are the row's window. Her rule is that a
post-processing choice never needs a solver re-run.

The window was also resolved ONCE per simulation, off the first record, and
applied to every point. That is right only while every point shares one clock.

Every expected window below is ARITHMETIC ON THE ROW AND THE CLOCK, written out
in the test, never a value read off the resolver.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases import windows

#: A run of 1000 steps turning a rotor at 250 steps per revolution, four blades
#: on the flat path, with a second rotor block at 500 steps per revolution.
PLAN = {
    "window_stated": True,
    "time_iterations": 1000,
    "steps_per_revolution": 250.0,
    "blades": 4,
    "time_average": {"windows": [[751, 1000]], "window_from": "as the run stated it"},
    "rotors": {
        "LIFT": {
            "blades": 5,
            "rpm": 2400.0,
            "steps_per_revolution": 250.0,
            "period_steps": 50,
            "phase_locked": {"windows": [[751, 800]], "period_steps": 50, "window_from": "run"},
            "per_blade": {"windows": [[751, 1000]], "period_steps": 50, "window_from": "run"},
        },
        "PUSHER": {
            "blades": 2,
            "rpm": 1200.0,
            "steps_per_revolution": 500.0,
            "period_steps": 250,
            "phase_locked": {"windows": [[751, 1000]], "period_steps": 250, "window_from": "run"},
            "per_blade": {"windows": [[501, 1000]], "period_steps": 250, "window_from": "run"},
        },
    },
    "phase_locked": {"skipped": "the row names its rotors"},
    "per_blade": {"skipped": "the row names its rotors"},
}


def test_the_span_is_the_last_revolutions_of_the_clock_or_the_last_iterations():
    # 2 revolutions of 250 steps ending at step 1000 is 501 to 1000.
    assert windows.averaging_span({"LAST_REVS_AVG": "2"}, last_step=1000, per_revolution=250.0) == (
        501,
        1000,
    )
    # Half a revolution is 125 steps: 876 to 1000. It takes a float.
    assert windows.averaging_span(
        {"LAST_REVS_AVG": "0.5"}, last_step=1000, per_revolution=250.0
    ) == (876, 1000)
    assert windows.averaging_span(
        {"LAST_ITERS_AVG": "100"}, last_step=1000, per_revolution=None
    ) == (901, 1000)
    # Longer than the run is the whole run, never before step one.
    assert windows.averaging_span(
        {"LAST_REVS_AVG": "99"}, last_step=1000, per_revolution=250.0
    ) == (1, 1000)


@pytest.mark.parametrize(
    "variables",
    [
        {},
        {"LAST_REVS_AVG": "-"},
        {"LAST_REVS_AVG": "0"},
        {"LAST_ITERS_AVG": "nope"},
        {"LAST_REVS_AVG": "1", "LAST_ITERS_AVG": "10"},
    ],
)
def test_a_row_that_states_no_usable_key_resolves_to_nothing(variables):
    assert windows.averaging_span(variables, last_step=1000, per_revolution=250.0) is None
    assert windows.replan(PLAN, variables) is None


def test_revolutions_without_a_clock_resolve_to_nothing_rather_than_a_guess():
    assert (
        windows.averaging_span({"LAST_REVS_AVG": "1"}, last_step=1000, per_revolution=None) is None
    )


def test_replanning_moves_every_window_of_the_point_and_each_rotor_by_its_own_turn():
    plan = windows.replan(PLAN, {"LAST_REVS_AVG": "2"})
    assert plan is not None
    # The row's span is the CLOCK's: 2 x 250 steps.
    assert plan["time_average"]["windows"] == [[501, 1000]]
    assert plan["window_stated"] is True
    # LIFT turns 250 steps per revolution: two turns are 500 steps, 501 to 1000,
    # and the row's span cut into its 50-step passages is ten of them.
    lift = plan["rotors"]["LIFT"]
    assert lift["per_blade"]["windows"] == [[501, 1000]]
    assert lift["phase_locked"]["windows"][0] == [501, 550]
    assert lift["phase_locked"]["windows"][-1] == [951, 1000]
    assert len(lift["phase_locked"]["windows"]) == 10
    # PUSHER turns 500 steps per revolution: ITS two turns are the whole run,
    # which is FR-68 and the reason the span is a count of turns, not of steps.
    pusher = plan["rotors"]["PUSHER"]
    assert pusher["per_blade"]["windows"] == [[1, 1000]]
    assert pusher["phase_locked"]["windows"] == [[501, 750], [751, 1000]]
    # The flat keys keep their pointer: the row still names its rotors.
    assert "skipped" in plan["phase_locked"]


def test_replanning_never_touches_the_record_it_was_handed():
    before = json.dumps(PLAN, sort_keys=True)
    windows.replan(PLAN, {"LAST_REVS_AVG": "3"})
    assert json.dumps(PLAN, sort_keys=True) == before, "a record is never rewritten"


def test_a_window_shorter_than_one_passage_is_a_named_skip_and_not_an_empty_table():
    plan = windows.replan(PLAN, {"LAST_ITERS_AVG": "100"})
    assert plan is not None
    # 100 steps hold two 50-step passages of LIFT and no 250-step one of PUSHER.
    assert plan["rotors"]["LIFT"]["phase_locked"]["windows"] == [[901, 950], [951, 1000]]
    assert "skipped" in plan["rotors"]["PUSHER"]["phase_locked"]
    assert "250" in plan["rotors"]["PUSHER"]["phase_locked"]["skipped"]
    # Iterations are already steps, the same number for every rotor.
    assert plan["rotors"]["PUSHER"]["per_blade"]["windows"] == [[901, 1000]]


def test_two_points_with_two_clocks_get_two_windows_from_one_row():
    """THE PER-POINT HALF. One row, LAST_REVS_AVG 1, two points whose rotors turn
    at different rates under one DELTA_TIME: 250 and 125 steps per revolution.
    0.23.0 resolved the window off the first record and gave both 751 to 1000.
    """
    fast = {**PLAN, "steps_per_revolution": 125.0, "rotors": {}}
    slow = {**PLAN, "rotors": {}}
    row = {"LAST_REVS_AVG": "1"}
    assert windows.replan(slow, row)["time_average"]["windows"] == [[751, 1000]]
    assert windows.replan(fast, row)["time_average"]["windows"] == [[876, 1000]]


# ---------------------------------------------------------------- the STAGE


_MATRIX_HEAD = (
    "POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION "
    "| SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS "
    "| WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n"
)


def _matrix(window: str) -> str:
    return _MATRIX_HEAD + (
        "7001 | 0 | 1 | RIG | - | ROTOR_UNSTEADY | MACH:0.2, ALPHA:sweep, BETA:0 | -2 "
        "| 05_NX.fsm | r001 | s001 | p001 | - | - | - | - | 26.120 | unsteady "
        f"| DELTA_TIME: 0.001 / TIME_ITERATIONS: 8 / {window}\n"
    )


def _posted(tmp_path, window: str) -> dict:
    """Post ONE recorded workspace under a matrix stating ``window``; return the manifest."""
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import RunRecord
    from tests.tier1_offline.test_post_products import _unsteady_workspace

    plan = {
        "window_stated": True,
        "time_iterations": 8,
        "steps_per_revolution": None,
        "blades": None,
        "time_average": {"windows": [[5, 8]], "window_from": "LAST_ITERS_AVG = 4 at run time"},
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan, recipe="unsteady")
    # The same record, now tied to a matrix that is on disk beside the runs.
    manifest = workspace.root / "runs.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))
    container = records["runs"] if isinstance(records, dict) else records
    container[0]["matrix_stem"] = "matriz"
    manifest.write_text(json.dumps(records), encoding="utf-8")
    assert RunRecord.model_validate(container[0]).matrix_stem == "matriz"
    (workspace.root / "matriz.fs").write_text(_matrix(window), encoding="utf-8")
    import warnings as _warnings

    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    said = [str(w.message) for w in caught if "averaging window" in str(w.message)]
    # The run recorded steps 5 to 8. A matrix that still says four is silent; one
    # that says anything else is SAID, naming both windows.
    if "AVG: 4" in window:
        assert not said, said
    else:
        assert len(said) == 1 and "5 to 8" in said[0], said
    return json.loads(
        (workspace.root / "post" / "matriz" / "products.json").read_text(encoding="utf-8")
    )


def test_editing_the_window_in_the_matrix_moves_the_reductions_with_no_re_run(tmp_path):
    ran = _posted(tmp_path / "as_run", "LAST_ITERS_AVG: 4")
    edited = _posted(tmp_path / "edited", "LAST_ITERS_AVG: 6")
    key = "probes/AL-020_time_average.csv"
    # 8 steps, the last 4 are 5 to 8; the last 6 are 3 to 8.
    assert ran["products"][key]["windows"] == [[5, 8]]
    assert edited["products"][key]["windows"] == [[3, 8]], (
        "the matrix states six iterations and the reduction still averages the four "
        "the RUN recorded: a post-processing choice needed a solver re-run"
    )
