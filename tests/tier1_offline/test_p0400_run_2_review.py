"""P0400 regressions for the adversarial review of lane run-2."""

from pathlib import Path

import pytest

from pyflightstream.run import records
from pyflightstream.run.collect import collect_once
from tests.support_helpers import no_sleep
from tests.tier1_offline.test_additional_post import a_recorded_campaign, a_stub, extract
from tests.tier1_offline.test_p0350_batch_collect import _listing
from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace
from tests.tier1_offline.test_p0400_run_2_records import _job_workspace, _points_of
from tests.tier1_offline.test_submitted_additional_post import Scheduler


def test_p0400_mark_whole_job_after_marking_one_point(tmp_path):
    workspace = _job_workspace(tmp_path)
    records.mark_failed(workspace.root, [], points={"5001": ["AL+005"]}, reason="first", apply=True)
    result = records.mark_failed(workspace.root, ["5001"], reason="whole", apply=True)
    assert set(_points_of(workspace, "5001").values()) == {"FAILED_MARKED"}
    assert len(result["marked"]) == 2
    row = next(r for r in workspace.read_raw_manifest() if r.get("sim_id") == "5001")
    assert row["points_ran"][1]["marked"]["reason"] == "first"
    assert not records.mark_failed(workspace.root, ["5001"], apply=True)["applied"]


def test_p0400_ended_batch_moves_only_selected_simulations(tmp_path):
    workspace = grouped_workspace(tmp_path, mode="batch", collect=False)
    row = next(r for r in workspace.read_manifest() if r.sim_id == "7003")
    batch = workspace.root / row.submission["job"]["dir"]
    other = batch / "sim_7003"
    before = _listing(other)
    collect_once(workspace, sims=["7001"], interval=0, sleep=no_sleep)
    assert not (batch / "sim_7001").exists()
    assert other.is_dir(), "an unselected simulation was moved"
    assert _listing(other) == before
    assert next(r for r in workspace.read_manifest() if r.sim_id == "7003").status == "SUBMITTED"


def test_p0400_ended_batch_moves_home_after_every_point_completed(tmp_path):
    workspace = grouped_workspace(tmp_path, mode="batch", collect=False, ended=False)
    row = workspace.read_manifest()[0]
    job = row.submission["job"]
    batch = workspace.root / job["dir"]
    collect_once(workspace, interval=0, sleep=no_sleep)
    assert all(r.status != "SUBMITTED" for r in workspace.read_manifest())
    assert (batch / "sim_7001").exists()
    (batch / f"{Path(job['script']).stem}.end.json").write_text('{"return_code": 0}')
    collect_once(workspace, interval=0, sleep=no_sleep)
    assert not (batch / "sim_7001").exists()
    assert not (batch / "sim_7003").exists()


def test_p0400_pending_extraction_is_skipped_and_not_reported_launched(tmp_path):
    workspace, matrix = a_recorded_campaign(tmp_path, values="0.0")
    scheduler = Scheduler()
    _, first = extract(workspace, matrix, scheduler)
    before = workspace.read_additional()
    plans, repeated = extract(workspace, matrix, scheduler)
    assert [plan.status for plan in plans] == ["SKIPPED"]
    assert "collect" in plans[0].message
    assert repeated == []
    assert len(scheduler.invocations) == 1
    assert first[0].status == "SUBMITTED" and workspace.read_additional() == before


def test_p0400_local_extraction_cleanup_failure_keeps_completed_result(tmp_path, monkeypatch):
    workspace, matrix = a_recorded_campaign(tmp_path, values="0.0")
    real = Path.unlink

    def held(path, missing_ok=False):
        if path.name.endswith(".reopened.fsm"):
            raise PermissionError("held by another process")
        return real(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", held)
    _, completed = extract(workspace, matrix, a_stub(tmp_path))
    assert [record.status for record in completed] == ["EXTRACTED"]
    assert "could not be removed" in (completed[0].note or "")
    assert workspace.read_additional()[-1].status == "EXTRACTED"


@pytest.mark.parametrize("placeholder", ["{walltime.missing}", "{walltime[bad]}"])
def test_p0400_submit_field_access_refusal_is_a_failed_result(tmp_path, placeholder):
    from dataclasses import replace

    from pyflightstream.run import SubmittingExecutor
    from tests.tier1_offline.test_goal024_walltime import _profile

    profile = replace(_profile(tmp_path), submit=("submit", placeholder))
    executor = SubmittingExecutor(profile, values={"walltime": "4h"}, submit=False)
    script = tmp_path / "point.txt"
    script.write_text("CLOSE_FLIGHTSTREAM" + chr(10), encoding="utf-8")
    result = executor.run_script(script, tmp_path / "work")
    assert result.failed and "nothing was submitted" in result.stderr
    assert not (tmp_path / "work" / profile.descriptor_name).exists()
