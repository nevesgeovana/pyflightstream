"""A steady job keeps its per-point evidence even when it contains one point."""

from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_collect_stage import _submitted_workspace
from tests.tier1_offline.test_goal028_hpc_collect import _loads


def test_collect_single_point_job_keeps_outputs_in_as_points(tmp_path, monkeypatch):
    workspace, sim = _submitted_workspace(tmp_path, declared=("AL+000.txt",))
    record = workspace.read_manifest()[0]
    record = record.model_copy(
        update={
            "point_name": "AL+000",
            "point": {"alpha": 0.0},
            "submission": {
                **record.submission,
                "declared_by_point": {"AL+000": ["AL+000.txt"]},
                "points_by_tag": {"AL+000": {"alpha": 0.0}},
            },
            "points_ran": [{"tag": "AL+000", "point": {"alpha": 0.0}, "status": "SUBMITTED"}],
        }
    )
    completed = []
    monkeypatch.setattr(workspace, "read_manifest", lambda: [record])
    monkeypatch.setattr(workspace, "complete_submitted_record", completed.append)
    (sim / "AL+000.txt").write_text(_loads(0.0), encoding="utf-8")
    report = collect_once(workspace, interval=0, sleep=lambda _: None)
    assert len(report.collected) == 1, report.lines()
    (point,) = completed[0].as_points()
    assert point.outputs == ["datapoints/DP-AL+000/AL+000.txt"], "collected point lost its outputs"
    assert point.status is RunStatus.CONVERGED
    assert point.iterations == 312
