"""Apply must act on the manifest read while holding the lock."""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from pyflightstream.run import _mark_converged as marking
from pyflightstream.run.records import manifest_lock
from pyflightstream.workspace.naming import RunsManifestError
from pyflightstream.workspace.record_document import encode_rows


def test_p0430_w012_mark_checks_recorded_loads_digest(tmp_path):
    from pyflightstream._digest import file_sha256
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace(tmp_path)
    sim = workspace.sim_dir("1")
    sim.mkdir(parents=True)
    path = sim / "A.txt"
    path.write_text("original", encoding="utf-8")
    row = dict(
        sim_id="1",
        run_id="campaign/sim_1/A",
        status="RAN_MISSING_LOG",
        outputs=["A.txt"],
        outputs_sha256={"A.txt": file_sha256(path)},
    )
    manifest = tmp_path / "runs.json"
    manifest.write_text(json.dumps(encode_rows([row])), encoding="utf-8")
    assert not marking.mark_converged(tmp_path, ["1"], reason="reviewed")["refused"]
    path.write_text("replaced", encoding="utf-8")
    assert marking.mark_converged(tmp_path, ["1"], reason="reviewed")["refused"]
    row.pop("outputs_sha256")
    manifest.write_text(json.dumps(encode_rows([row])), encoding="utf-8")
    assert not marking.mark_converged(tmp_path, ["1"], reason="reviewed")["refused"]


def test_p0430_w012_same_second_marks_preserve_both_archives(tmp_path, monkeypatch):
    import datetime

    class FrozenDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 21, 12, 0, 0, tzinfo=tz)

    sim = tmp_path / "sims" / "sim_1"
    sim.mkdir(parents=True)
    rows = []
    for name in ("A", "B"):
        (sim / f"{name}.txt").write_text("loads", encoding="utf-8")
        rows.append(
            dict(
                sim_id="1",
                run_id=f"campaign/sim_1/{name}",
                point_name=name,
                status="RAN_MISSING_LOG",
                outputs=[f"{name}.txt"],
            )
        )
    manifest = tmp_path / "runs.json"
    manifest.write_text(json.dumps(encode_rows(rows)), encoding="utf-8")
    original = manifest.read_bytes()
    monkeypatch.setattr(datetime, "datetime", FrozenDateTime)
    first = marking.mark_converged(tmp_path, ["1"], points=["A"], reason="reviewed", apply=True)
    intermediate = manifest.read_bytes()
    second = marking.mark_converged(tmp_path, ["1"], points=["B"], reason="reviewed", apply=True)
    assert first["runs_archived_as"] != second["runs_archived_as"]
    assert (tmp_path / first["runs_archived_as"]).read_bytes() == original
    assert (tmp_path / second["runs_archived_as"]).read_bytes() == intermediate


@pytest.mark.parametrize("new_status", ["SUBMITTED", "FAILED_MARKED", "CONVERGED"])
def test_apply_rechecks_the_locked_plan(tmp_path, new_status):
    """P0370-S1-MARK-CONVERGED (FR-868, FR-869): lock-time changes govern the write."""
    sim = tmp_path / "sims" / "sim_1"
    sim.mkdir(parents=True)
    (sim / "A.txt").write_text("loads", encoding="utf-8")
    row = {
        "sim_id": "1",
        "run_id": "campaign/sim_1/A",
        "status": "RAN_MISSING_LOG",
        "outputs": ["A.txt"],
    }
    manifest = tmp_path / "runs.json"
    manifest.write_text(json.dumps(encode_rows([row])), encoding="utf-8")
    changed = json.dumps(encode_rows([{**row, "status": new_status}])).encode()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with manifest_lock(tmp_path):
            future = pool.submit(
                marking.mark_converged, tmp_path, ["1"], reason="reviewed", apply=True
            )
            deadline = time.monotonic() + 5
            while not _writer_is_waiting() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert _writer_is_waiting(), "mark-converged never waited for the manifest lease"
            manifest.write_bytes(changed)
        if new_status != "CONVERGED":
            with pytest.raises(RunsManifestError, match="nothing was written"):
                future.result(timeout=5)
        else:
            result = future.result(timeout=5)
    if new_status == "CONVERGED":
        assert not result["applied"] and not result["marked"]
        assert result["already"] == [row["run_id"]]
    assert manifest.read_bytes() == changed
    assert not (tmp_path / "archive").exists()


def _writer_is_waiting():
    for frame in sys._current_frames().values():
        names = []
        while frame is not None:
            names.append(frame.f_code.co_name)
            frame = frame.f_back
        if "mark_converged" in names and "_manifest_lock" in names:
            return True
    return False
