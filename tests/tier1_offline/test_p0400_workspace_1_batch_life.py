"""P0400-WSBATCH: the workspace's batch end verdict and sync rule (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run._batch_collect import job_ended
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace import _batch_life as batch_life
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE, _write_profile
from tests.tier1_offline.test_goal035_storage import _copied_paths, _record

pytestmark = pytest.mark.requirement("P0400-WSBATCH")

LABEL = "matriz_b1"


def _job(**values):
    return {
        "kind": "batch",
        "name": LABEL,
        "batch_id": 1,
        "label": LABEL,
        "dir": f"sims/batch/{LABEL}",
        "script": f"sims/batch/{LABEL}/BATCH-1-1.txt",
        "root": ".",
        "executor": "submitting",
        "values": dict(values),
        "order": 1,
        "points": 1,
        "receipt_sha256": "0" * 64,
    }


def _batch(tmp_path, *, fired: bool):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    point = workspace.root / "sims" / "batch" / LABEL / "sim_1" / "datapoints" / "DP-A"
    (point / "actions").mkdir(parents=True)
    state = {"fired": fired, "steps": 40, "stopped_at": {"step": 40}}
    (point / "actions" / "pfs_walltime_clock.json").write_text(json.dumps(state), "utf-8")
    rows = [{"sim_id": "1", "submission": {"job": _job()}}]
    return workspace, rows


def _collect_says(workspace, job):
    return job_ended(
        workspace,
        job,
        profile=None,
        observer=lambda paths: {str(p): 1 for p in paths},
        settled=lambda first, second: first == second,
        sleep=lambda seconds: None,
        interval=0.0,
    ).ended


@pytest.mark.parametrize("fired", [True, False], ids=["clock-fired", "no-evidence"])
def test_p0400_wsbatch_the_workspace_and_collect_agree_on_a_fired_clock(tmp_path, fired):
    """P0400-WSBATCH (PFS-2094.041, PFS-2094.044): a fired clock ends the batch for both layers."""
    workspace, rows = _batch(tmp_path, fired=fired)
    assert _collect_says(workspace, _job()) is fired
    running = batch_life.running_batches(workspace.root, rows)
    assert (LABEL not in running) is fired, running


@pytest.mark.parametrize(
    ("pattern", "values"),
    [
        ("FTS{sim}.o*", {}),
        ("FTS{ncpus:.2f}.o*", {"ncpus": []}),
        ("FTS{sim.missing}.o*", {"sim": "1"}),
    ],
)
def test_p0400_wsbatch_an_unformattable_end_glob_is_said(tmp_path, monkeypatch, pattern, values):
    """P0400-WSBATCH (PFS-2094.050): a glob naming a value the job did not record warns."""
    workspace, rows = _batch(tmp_path, fired=False)
    rows[0]["submission"]["job"] = _job(**values)
    if values:
        # Exercise the formatter independently of the file reader's stricter grammar.
        monkeypatch.setattr(batch_life, "_end_globs", lambda root: (pattern,))
    else:
        _write_profile(workspace, LOG_TABLE + f"job_end_files = [{json.dumps(pattern)}]\n")
    with pytest.warns(PyflightstreamWarning, match="cannot be formatted") as seen:
        running = batch_life.running_batches(workspace.root, rows)
    assert LABEL in running
    assert pattern in str(seen[0].message)


def test_p0400_wsbatch_sync_takes_every_log_by_one_rule(tmp_path):
    """P0400-WSBATCH (PFS-2087.002): a sim and a batch sim bring the same logs, any case."""
    other = CampaignWorkspace.init(tmp_path / "other")
    names = ("FlightStreamLog.txt", "fs_runtime_output.txt", "P1-A_log.txt", "solver.log")
    home, batch = other.sim_dir("1"), other.root / "sims" / "batch" / LABEL / "sim_2"
    for sim in (home, batch):
        for name in (*names, "loads.vtk"):
            target = sim / "datapoints" / "DP-A" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")
    other.append_record(_record("1", "camp/sim_1/AL+000"))
    copied = _copied_paths(tmp_path, other.root, "runs", "logs")
    for sim in ("sims/sim_1", f"sims/batch/{LABEL}/sim_2"):
        for name in names:
            assert f"{sim}/datapoints/DP-A/{name}" in copied, (sim, name, sorted(copied))
        assert f"{sim}/datapoints/DP-A/loads.vtk" not in copied
