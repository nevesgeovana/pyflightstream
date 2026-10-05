"""Apply must act on the manifest read while holding the lock."""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from pyflightstream.run import _mark_converged as marking
from pyflightstream.run.records import manifest_lock
from pyflightstream.workspace.naming import RunsManifestError


@pytest.mark.parametrize("new_status", ["SUBMITTED", "FAILED_MARKED", "CONVERGED"])
def test_apply_rechecks_the_locked_plan(tmp_path, new_status):
    """P0370-S1-MARK-CONVERGED (FR-414 R1, R2): lock-time changes govern the write."""
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
    manifest.write_text(json.dumps([row]), encoding="utf-8")
    changed = json.dumps([{**row, "status": new_status}]).encode()

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
