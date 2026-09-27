# GEOVERSE_HEADER
# file_version: 1.0.3
# file_role: walltime-observed-stop-regressions
# last_modified_at: 2026-09-27T19:34:52.345Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pytest, pyflightstream.run]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Test actual stop evidence and complete rescue termination.
# revision_source: git
"""A firing marker cannot claim a stop when subsequent callbacks exist."""

import json

from pyflightstream.run import _walltime_stop


def test_callbacks_after_clock_fired_do_not_claim_stopped_step(tmp_path):
    state = tmp_path / "clock.json"
    state.write_text(
        json.dumps({"fired": True, "steps": 93, "stopped_at": {"step": 13, "elapsed_s": 8.35}})
    )
    assert _walltime_stop(state) is None


def test_clock_stop_uses_matching_actual_callback_count(tmp_path):
    state = tmp_path / "clock.json"
    state.write_text(
        json.dumps({"fired": True, "steps": 13, "stopped_at": {"step": 13, "elapsed_s": 8.35}})
    )
    assert _walltime_stop(state) == {"step": 13, "elapsed_s": 8.35}


def test_rescue_closes_solver_after_all_declared_exports():
    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.cases.workflows import walltime_stop_text
    from pyflightstream.run import workflow_conventions_for

    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_{point}.txt", "loads_{point}_plots.txt"],
        point={"alpha": 0.0},
        variables={"VELOCITY": "30.0", "DELTA_TIME": "0.01", "TIME_ITERATIONS": "4"},
    )
    text = walltime_stop_text(case, workflow_conventions_for(case), version="26.122")
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert any(line.startswith("EXPORT_") for line in lines)
    assert lines[-1] == "CLOSE_FLIGHTSTREAM"
    assert "STOP" not in lines
