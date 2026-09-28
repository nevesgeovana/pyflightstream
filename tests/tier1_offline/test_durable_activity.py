"""A real campaign call leaves durable stage context beside its workspace."""

import json

import pytest

from pyflightstream.run import run_campaign
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_run_campaign import (
    WRITES_LOADS,
    StubSolver,
    converged,
    make_campaign,
    steady_recipe,
)


@pytest.mark.parametrize(
    "stage",
    [
        # Each case id names the obligation its stage's assertions prove.
        pytest.param("preparation", id="prepare"),
        pytest.param("solver", id="solver"),
        pytest.param("post", id="pproc"),
        pytest.param("persistent-detail", id="persistent_detail"),
    ],
)
def test_campaign_records_stages_and_final_outcomes(tmp_path, stage):
    # GOAL033:logging:checks:prepare
    # GOAL033:logging:checks:solver
    # GOAL033:logging:checks:pproc
    # GOAL033:logging:checks:persistent_detail
    workspace = CampaignWorkspace(tmp_path / "campaign")
    run_campaign(
        make_campaign(tmp_path, alphas=(0.0,)),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        preflight=False,
    )
    path = workspace.root / "logs" / "activity.log.jsonl"
    assert path.is_file(), "campaign has no durable activity log"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert any(e["stage"] == "run" and e["event"] == "started" for e in events)
    assert any(e["stage"] == "solver" and e["event"] == "started" for e in events)
    end = next(e for e in reversed(events) if e["stage"] == "run" and e["event"] == "finished")
    assert end["outcomes"] == {"CONVERGED": 1}
    assert all(e["timestamp"] for e in events)
    assert (workspace.root / "logs" / "activity.log").is_file()

    if stage == "persistent-detail":
        detail = (workspace.root / "logs" / "activity.log").read_text(encoding="utf-8")
        assert "CONVERGED" in detail and "solver" in detail and "run" in detail
    else:
        observed = [event for event in events if event["stage"] == stage]
        assert {event["event"] for event in observed} >= {"started", "finished"}
        assert all(event["duration_s"] >= 0 for event in observed if event["event"] == "finished")
