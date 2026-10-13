"""Tier 1, 0.40.0 lane run-1: collect over the points of a grouped job (FR-369).

Hand-built workspaces of the 0.35.0 batch collect tests; no solver runs.
"""

from __future__ import annotations

from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import RunStatus
from tests.support_helpers import no_sleep as _no_sleep
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE, _write_profile
from tests.tier1_offline.test_p0350_batch_collect import (
    _converged,
    _cumulative,
    _status,
    _workspace,
)


def test_p0400_a_point_the_job_never_started_fails_under_export_log_false(tmp_path):
    """P0400-NOT-STARTED-NATIVE-LOG (PFS-2103.023): the job's shared log is not the point's file.

    With ``export_log = false`` the job's native log exists for every point once the job
    started, and it counted as the never-started point's own file, so FR-369 never fired.
    """
    workspace, job_dir, _ = _workspace(tmp_path, "batch", written=("AL+000",))
    _write_profile(workspace, LOG_TABLE)
    own = job_dir / "sim_2006" / "datapoints" / "DP-AL+000" / "P2006-AL+000.cumulative-log.txt"
    own.unlink()
    (job_dir / "FTSmtx_b1.l3714205").write_bytes(_cumulative(1).encode())
    (job_dir / "BATCH-2006-2006.end.json").write_bytes(b'{"returncode": 0}\n')
    collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    second = _status(workspace, "AL+020")
    assert second.status is RunStatus.FAILED_EXECUTION, second.status
    assert second.error == "the job BATCH-2006-2006 ended before this point started"
    assert _status(workspace, "AL+000").status is RunStatus.CONVERGED
