"""A stopped grouped job still has an unavailable solver log."""

import json

import pytest

from pyflightstream.cases.workflows import WALLTIME_CLOCK_STATE
from pyflightstream.run._batch_collect import clock_stop_update
from pyflightstream.workspace import RunRecord, RunStatus


@pytest.mark.parametrize("status", [RunStatus.RAN_MISSING_LOG, RunStatus.COMPLETED_MAX_ITER])
def test_clock_evidence_does_not_replace_missing_log_status(tmp_path, status):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R1, R3): keep status and retain the stop step."""
    record = RunRecord(
        run_id="campaign/sim_1/A",
        sim_id="1",
        fs_version_requested="26.124",
        package_version="0.37.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=RunStatus.SUBMITTED,
        submission={"job": {}},
    )
    stopped = {"step": 30, "elapsed_s": 41.5}
    (tmp_path / WALLTIME_CLOCK_STATE).parent.mkdir(parents=True)
    (tmp_path / WALLTIME_CLOCK_STATE).write_text(
        json.dumps({"fired": True, "steps": 30, "stopped_at": stopped}), encoding="utf-8"
    )
    update = clock_stop_update(record, tmp_path, status)
    expected = status if status is RunStatus.RAN_MISSING_LOG else RunStatus.WALLTIME_REACHED
    assert update == {"status": expected, "stopped_at": stopped}
