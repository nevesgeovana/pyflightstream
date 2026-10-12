"""Tier 1, 0.40.0 lane run-2: mark-converged on the points of a steady job.

Every fixture is synthetic.
"""

from __future__ import annotations

from pyflightstream.run.records import mark_converged
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_mark_failed import _record, _workspace


def test_p0400_mark_converged_judges_a_job_point_by_its_own_loads(tmp_path):
    """P0400-MARK-CONVERGED-OWN-LOADS (PFS-2103.029): a job point that collected nothing is refused.

    The check fell back to the job row's outputs, every other point's files,
    and accepted the point on the first point's loads export.
    """
    workspace = _workspace(tmp_path)
    sim = workspace.sim_dir("5001")
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "P5001-AL+000.txt").write_text("loads", encoding="utf-8")
    ran = [
        {"tag": "AL+000", "status": "CONVERGED", "outputs": ["P5001-AL+000.txt"]},
        {"tag": "AL+005", "status": "FAILED_INCOMPLETE_OUTPUT"},
    ]
    job = _record("5001", "camp/sim_5001/sweep", RunStatus.FAILED_INCOMPLETE_OUTPUT)
    workspace.append_record(
        job.model_copy(update={"points_ran": ran, "outputs": ["P5001-AL+000.txt"]})
    )
    entry = mark_converged(workspace.root, ["5001"], reason="read by hand", points=["AL+005"])
    assert entry["marked"] == []
    assert "loads export is not on disk" in entry["refused"]["camp/sim_5001/AL+005"]
