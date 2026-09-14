"""GOAL-020 item 4: RESTART continues a march the wall clock stopped.

HER MEASUREMENT OF 2026-09-13 is what the whole item rests on: the solver
DOES resume an unsteady march from a saved file, picking up where it stopped
and running the new iteration count it is given. Until that was known, the
release before this one REFUSED the key by name, because building either of
the two possible features without knowing which one the solver implements
would have built one of them wrong.

What these tests hold is the part a grep cannot see. That the refusal is gone
is one line. That a continuation OPENS THE SAVED FILE WITH THE STATE LOADED,
and marches the REMAINDER rather than the row's original count, is the
difference between continuing and starting over with a better initial
condition, and a user cannot see that difference in the numbers afterwards.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    WORKFLOW_KEY,
    build_script,
    continuation_of,
    parse_restart,
    restart_iterations,
)
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace

SAVED = "datapoints/DP-a+00.0/archive/20260914-010000/point.fsm"


def _continuing_case(restart: str, **variables) -> SimCase:
    return SimCase(
        sim_id="9001",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_a+00.0.txt", "run_a+00.0_log.txt"],
        variables={
            WORKFLOW_KEY: "unsteady",
            "VELOCITY": "30.0",
            "TIME_ITERATIONS": "400",
            "DELTA_TIME": "0.001",
            RESTART_VARIABLE: restart,
            **variables,
        },
        point={"alpha": 0.0},
    )


# ------------------------------------------------------- the three forms live


@pytest.mark.parametrize(
    "written",
    ["{FINISH_PENDING}", "{ADDITIONAL_ITERS=120}", "{ADDITIONAL_REVS=2}"],
)
def test_goal020_restart_all_three_forms_still_parse(written):
    """The parser was built a release before the builder; all three forms land at 0.18.0."""
    request = parse_restart(_continuing_case(written))
    assert request is not None


def test_goal020_restart_finish_pending_subtracts_what_the_run_reached():
    """FINISH_PENDING is the remainder, which is the whole reason the key exists."""
    request = parse_restart(_continuing_case("{FINISH_PENDING}"))
    record = {"export_window": {"time_iterations": 400}, "stopped_at": {"step": 250}}
    assert restart_iterations(request, record) == 150


def test_goal020_restart_additional_iters_is_the_count_it_states():
    request = parse_restart(_continuing_case("{ADDITIONAL_ITERS=120}"))
    assert restart_iterations(request, {"export_window": {}, "stopped_at": {"step": 250}}) == 120


def test_goal020_restart_additional_revs_becomes_steps_through_the_azimuthal_step():
    request = parse_restart(_continuing_case("{ADDITIONAL_REVS=2}"))
    record = {"export_window": {"step_deg": 10.0}, "stopped_at": {"step": 250}}
    assert restart_iterations(request, record) == 72


def test_goal020_restart_finish_pending_refuses_a_record_that_cannot_say():
    """A record that does not say what the row asked for has nothing to subtract from."""
    request = parse_restart(_continuing_case("{FINISH_PENDING}"))
    with pytest.raises(CampaignConfigError) as refused:
        restart_iterations(request, {"export_window": {}, "stopped_at": {"step": 250}})
    assert "does not say how many time steps" in str(refused.value)


# ------------------------------------------------------------- the build path


def test_goal020_restart_the_refusal_that_named_0_18_0_is_gone():
    """0.18.0 is the release that REMOVES the refusal, not one that keeps it."""
    import pyflightstream.cases.workflows as workflows

    assert not hasattr(workflows, "_refuse_a_restart_that_nothing_runs")


def test_goal020_restart_opens_the_saved_simulation_with_the_state_loaded():
    """ENABLE, always. A DISABLE here would silently march the row from a mesh again."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()
    assert "OPEN" in text
    assert SAVED in text
    open_block = text[text.index("OPEN") : text.index("OPEN") + 200]
    assert "ENABLE" in open_block, "a continuation that does not load the stored state is not one"


def test_goal020_restart_marches_the_remainder_and_not_the_rows_original_count():
    """The row asks for 400; the continuation owes 120, and the script says 120."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()
    assert "120" in text
    # The row's own count must NOT be what the solver is told to march.
    assert "\n400\n" not in text


def test_goal020_restart_imports_no_mesh_and_declares_no_boundaries():
    """Everything the saved file carries is a line this script does not emit."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()
    assert "IMPORT" not in text
    assert "CREATE_NEW_COORDINATE_SYSTEM" not in text


def test_goal020_restart_refuses_a_row_with_nothing_to_continue():
    """A continuation needs a recorded run that STOPPED; the row alone cannot say which."""
    case = _continuing_case("{ADDITIONAL_ITERS=120}")
    with pytest.raises(CampaignConfigError) as refused:
        continuation_of(case)
    message = str(refused.value)
    assert "nothing resolved the run it continues" in message
    assert "recorded run that STOPPED" in message


def test_goal020_restart_an_ordinary_row_is_not_a_continuation():
    case = SimCase(
        sim_id="9002",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_a+00.0.txt"],
        variables={WORKFLOW_KEY: "unsteady", "VELOCITY": "30.0", "TIME_ITERATIONS": "400"},
        point={"alpha": 0.0},
    )
    assert continuation_of(case) is None


# --------------------------------------------------------- the archive it owes


def test_goal020_restart_archives_what_it_replaces_under_a_day_and_hour_stamp(tmp_path):
    """HER DECISION, and the clause that decided the shape: there can be more than one restart."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    folder = workspace.sim_dir("9001") / "datapoints" / "DP-a+00.0"
    folder.mkdir(parents=True)
    (folder / "loads.txt").write_text("the stopped run", encoding="utf-8")

    first = workspace.archive_datapoint(
        "9001", {"alpha": 0.0}, stamp=datetime(2026, 9, 14, 1, 0, 0)
    )
    assert first is not None
    assert first.name == "20260914-010000"
    assert (first / "loads.txt").read_text(encoding="utf-8") == "the stopped run"
    assert [p.name for p in folder.iterdir()] == ["archive"]

    # A SECOND CONTINUATION, which is why the stamp is there at all.
    (folder / "loads.txt").write_text("the first continuation", encoding="utf-8")
    second = workspace.archive_datapoint(
        "9001", {"alpha": 0.0}, stamp=datetime(2026, 9, 14, 2, 0, 0)
    )
    assert second is not None and second.name == "20260914-020000"
    assert (second / "loads.txt").read_text(encoding="utf-8") == "the first continuation"
    # BOTH are still there, in order, which a flat folder could not have done.
    stamps = sorted(p.name for p in (folder / "archive").iterdir())
    assert stamps == ["20260914-010000", "20260914-020000"]


def test_goal020_restart_archiving_nothing_is_not_an_error(tmp_path):
    """A first run of a point has no previous outputs; that is ordinary, not a mistake."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    assert workspace.archive_datapoint("9001", {"alpha": 0.0}) is None
