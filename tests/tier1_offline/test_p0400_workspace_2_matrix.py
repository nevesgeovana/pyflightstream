"""P0400-RENUMBER: the refusal to move a row with runs names a remedy that clears it."""

from __future__ import annotations

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace.matrix import renumber_repeated_pols
from tests.tier1_offline.test_goal021_matrix_ids import _matrix, _workspace, row


def test_p0400_renumber_the_printed_remedy_clears_the_refusal(tmp_path):
    """P0400-RENUMBER (PFS-2100.017): planned.fs has runs of POL 8001, which other.fs also
    states. The refusal names other.fs and its --update-ids, not archiving (which leaves the
    records); doing what it prints lets planned.fs keep 8001 with nothing to move."""
    workspace = _workspace(tmp_path)
    planned = _matrix(workspace.root, "planned.fs", [row(8001)])
    other = _matrix(workspace.root, "other.fs", [row(8001)])
    workspace.append_record(
        RunRecord(
            run_id="p/sim_8001/a-02.0",
            sim_id="8001",
            point={"alpha": -2.0},
            matrix_stem="planned",
            fs_version_requested="26.120",
            package_version="0.40.0",
            script_sha256="0" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    with pytest.raises(MatrixError) as raised:
        renumber_repeated_pols(planned, workspace, in_place=True)
    message = str(raised.value)
    assert "pyfs-matrix plan other.fs --update-ids" in message, message
    assert "archive the simulation" not in message, message
    moved = renumber_repeated_pols(other, workspace, in_place=True)
    assert [change.old for change in moved] == ["8001"]
    assert renumber_repeated_pols(planned, workspace, in_place=True) == []
