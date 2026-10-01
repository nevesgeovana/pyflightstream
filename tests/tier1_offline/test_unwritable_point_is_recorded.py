"""A point whose files cannot be written is a recorded failure, and the run goes on (0.30.0).

Measured on an HPC workspace on a network share (0.28.0, 2026-09-28): a J
sweep of ten planned points recorded six, the scripts of points 7 to 10 were
never written, and nothing recorded them. The cause is not proved; the
leading hypothesis is an ``OSError`` from a network write of the point's
script, its input files or its state, which nothing on the run path caught
and which ended the run. Now such a point is recorded (FAILED_SCRIPT, the
cause in its ``error``) and the next point runs.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import CampaignErrors, run_campaign
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_run_campaign import (
    WRITES_LOADS,
    StubSolver,
    converged,
    make_campaign,
    steady_recipe,
)

ALPHAS = tuple(float(value) for value in range(10))


def _run_with_a_refused_write(tmp_path, monkeypatch, *, target: str, refused: int = 7):
    campaign = make_campaign(tmp_path, alphas=ALPHAS)
    workspace = CampaignWorkspace(tmp_path / "camp")
    calls = {"n": 0}
    if target == "script":
        real = workspace.write_script

        def refusing(sim_id, name, text):
            calls["n"] += 1
            if calls["n"] == refused:
                raise PermissionError(13, "The network share refused the write", name)
            return real(sim_id, name, text)

        monkeypatch.setattr(workspace, "write_script", refusing)
    else:
        import pyflightstream.run._pending as pending_module

        real_pending = pending_module._write_pending_files

        def refusing_pending(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == refused:
                raise OSError(5, "Input/output error on the share")
            return real_pending(*args, **kwargs)

        monkeypatch.setattr(pending_module, "_write_pending_files", refusing_pending)
    with pytest.raises(CampaignErrors) as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    return workspace, caught.value


@pytest.mark.parametrize("target", ["script", "pending"])
def test_a_refused_write_on_the_seventh_of_ten_points_leaves_ten_records(
    tmp_path, monkeypatch, target
):
    workspace, errors = _run_with_a_refused_write(tmp_path, monkeypatch, target=target)
    manifest = workspace.read_manifest()
    assert len(manifest) == 10, [record.run_id for record in manifest]
    statuses = [record.status for record in manifest]
    assert statuses[6] is RunStatus.FAILED_SCRIPT
    assert statuses[:6] + statuses[7:] == [RunStatus.CONVERGED] * 9
    failed = manifest[6]
    assert "OSError" in failed.error or "PermissionError" in failed.error, failed.error
    assert "before the solver started" in failed.error
    assert failed.point == {"alpha": 6.0}
    assert [record.run_id for record in errors.failures] == [failed.run_id]
    # The points after it RAN: their scripts exist.
    scripts = sorted(path.name for path in (workspace.sim_dir("9001") / "scripts").iterdir())
    assert len([name for name in scripts if name.endswith(".txt")]) == (
        9 if target == "script" else 10
    )
