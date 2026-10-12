"""Tier 1, 0.40.0 lane run-2: a grouped run whose job does not launch.

The workspace is the 0.35.0 batch-run fixture, with a submit command that exits 3.
"""

from __future__ import annotations

import sys

from pyflightstream.run import cli
from pyflightstream.run import matrix as run_matrix
from tests.tier1_offline.test_p0350_batch_run import MATRIX, _matrix, _plan, _workspace


def test_p0400_a_grouped_run_whose_job_is_refused_exits_non_zero(tmp_path, capsys, monkeypatch):
    """P0400-GROUPED-REFUSED-EXIT (PFS-2094.031): ``run --batch`` with a refused job exits 2.

    The job's points were recorded FAILED_EXECUTION and returned, not raised,
    so the command said it ran and exited 0. The machine is a cluster, so the
    run submits through the profile rather than refusing the absent local build.
    """
    monkeypatch.setattr(run_matrix, "on_a_cluster", lambda: True)
    workspace, _profile, _ = _workspace(
        tmp_path, submit=[sys.executable, "-c", "import sys; sys.exit(3)"]
    )
    matrix = _matrix(tmp_path)
    _plan(workspace, matrix, mode="batch", batch=1)
    argv = [
        "run",
        str(matrix),
        "--workspace",
        str(workspace.root),
        "--name",
        MATRIX,
        "--batch",
        "1",
        "--hpc",
        "h001",
    ]
    assert cli.main(argv) == 2
    assert "matrix run with failures" in capsys.readouterr().err
