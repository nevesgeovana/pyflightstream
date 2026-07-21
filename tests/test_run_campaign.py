"""Tier 1: the campaign loop, end-to-end dry run without FlightStream.

A StubSolver replaces the FlightStream argv with a Python one-liner
that mimics the solver behavior needed by each scenario (write the
declared outputs, write the hidden-mode error log, or fail), so the
whole path campaign.toml model, recipe, builder, workspace, executor,
and manifest is exercised for real.
"""

import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.files import CampaignWorkspace, RunStatus
from pyflightstream.run import Assessment, CampaignErrors, LocalExecutor, run_campaign
from pyflightstream.script import helpers


class StubSolver(LocalExecutor):
    def __init__(self, code: str):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.code = code

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", self.code]


WRITES_LOADS = "import pathlib; pathlib.Path('loads.txt').write_text('LOADS')"
WRITES_NOTHING = "pass"
CRASHES_WITH_LOG = (
    "import pathlib, sys; "
    "pathlib.Path('FlightStreamLog.txt').write_text('Unknown command SPOILER'); "
    "sys.exit(2)"
)


def steady_recipe(case, script):
    script.emit("OPEN", case.geometry)
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        aoa=case.point["alpha"],
        velocity=case.velocity,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    script.emit("START_SOLVER")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads.txt")
    script.emit("CLOSE_FLIGHTSTREAM")


def broken_recipe(case, script):
    script.emit("SOLVER_SET_AOA", "not-a-number")


def converged(case, execution, sim_dir):
    return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)


def diverged(case, execution, sim_dir):
    return Assessment(status=RunStatus.FAILED_DIVERGED, error="residual grew monotonically")


def make_campaign(tmp_path, *, recipe="steady", alphas=(0.0, 2.0), outputs=("loads.txt",)):
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=list(alphas)),
        recipe=recipe,
        outputs=list(outputs),
    )
    return Campaign(name="camp", fs_version="26.12", fs_exe=sys.executable, sims=[case])


def test_dry_run_records_every_point_end_to_end(tmp_path):
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert [record.run_id for record in records] == [
        "camp/sim_9001/a+00.0",
        "camp/sim_9001/a+02.0",
    ]
    assert all(record.status is RunStatus.CONVERGED for record in records)
    assert all(record.fs_version_requested == "26.120" for record in records)
    assert records[0].iterations == 120
    assert records[0].outputs == ["raw/loads.txt"]
    assert "wing.fsm" in records[0].inputs_sha256
    assert not records[0].raw_flag
    sim = tmp_path / "camp" / "sims" / "sim_9001"
    assert (sim / "scripts" / "a+02.0.txt").is_file()
    assert "SOLVER_SET_AOA 2.0" in (sim / "scripts" / "a+02.0.txt").read_text(encoding="utf-8")
    assert "inputs" in (sim / "scripts" / "a+00.0.txt").read_text(encoding="utf-8")
    assert len(workspace.read_manifest()) == 2


def test_recipe_failure_lands_as_failed_script(tmp_path):
    campaign = make_campaign(tmp_path, recipe="broken", alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_SCRIPT") as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"broken": broken_recipe},
        )
    assert caught.value.failures[0].error.startswith("CommandArgumentError")
    assert workspace.read_manifest()[0].status is RunStatus.FAILED_SCRIPT


def test_solver_failure_lands_as_failed_execution_with_the_log(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_EXECUTION"):
        run_campaign(
            campaign,
            StubSolver(CRASHES_WITH_LOG),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.FAILED_EXECUTION
    assert "Unknown command SPOILER" in record.error


def test_missing_declared_output_lands_as_incomplete(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_INCOMPLETE_OUTPUT"):
        run_campaign(
            campaign,
            StubSolver(WRITES_NOTHING),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    assert workspace.read_manifest()[0].status is RunStatus.FAILED_INCOMPLETE_OUTPUT


def test_unresolvable_recipe_fails_every_point_loudly(tmp_path):
    campaign = make_campaign(tmp_path, recipe="no.such.module:build")
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="2 campaign point"):
        run_campaign(campaign, StubSolver(WRITES_LOADS), workspace, assess=converged)
    records = workspace.read_manifest()
    assert len(records) == 2
    assert all(record.status is RunStatus.FAILED_SCRIPT for record in records)
    assert "cannot be imported" in records[0].error


def test_diverged_assessment_is_a_failure(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_DIVERGED"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=diverged,
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert record.error == "residual grew monotonically"
