"""Missing per-step actions add a status warning, never an invented solver failure."""

import json

import pytest

from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_collect_stage import _submitted_workspace


@pytest.mark.parametrize("count", [None, 0])
def test_collect_keeps_converged_with_explicit_missing_step_warning(tmp_path, count):
    # GOAL033:capability_ids:items:R17
    workspace, sim = _submitted_workspace(tmp_path)
    record = workspace.read_manifest()[0].model_copy(
        update={
            "action_program": "scripts/counter.py",
            "action_count": count,
            "export_window": {"first_step": 1, "time_iterations": 5},
        }
    )
    workspace.manifest_path.write_text(json.dumps([record.model_dump(mode="json")]))
    (sim / "loads.txt").write_text("final loads retained")
    (sim / "run_log.txt").write_text("final log retained")
    result = collect_once(
        workspace,
        interval=0,
        sleep=lambda _seconds: None,
        assessor=lambda _record, _folder: (RunStatus.CONVERGED, None),
    )
    assert not result.failed
    completed = workspace.read_manifest()[0]
    assert completed.status == RunStatus.CONVERGED
    warnings = getattr(completed, "warnings", [])
    assert warnings and "per-step" in warnings[0]
    assert "WARNING" in "\n".join(result.lines())
    assert any((sim / name).read_text() == "final loads retained" for name in completed.outputs)
