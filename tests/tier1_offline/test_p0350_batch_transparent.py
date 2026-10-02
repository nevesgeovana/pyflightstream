"""FR-372: the other commands read a batched point as a point run alone (0.35.0).

P0350-BATCH-TRANSPARENT. A batch's sims live in ``sims/batch/<matrix>_b<ID>/sim_<id>/``
while its job runs, and its job scripts and descriptor in the batch folder. One test
per command of section 11 of DESIGN-0350 (``status`` is the LEDGER+ST package's). The
workspaces are hand built in the layout of IMPL-0350 sections 4.2 and 4.3, with a
control beside each refusal: the same workspace with the job's end record written.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):
# FR-372.

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pyflightstream.run import records
from pyflightstream.run._continuation import queued_points
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError
from pyflightstream.workspace import storage as storage_module
from tests.tier1_offline.test_goal035_storage import (
    _copied_paths,
    _record,
    _write,
    _write_recipe,
)
from tests.tier1_offline.test_goal035_storage import _ws as workspace_at
from tests.tier1_offline.test_p0320_b3_post_records import _from_sims_workspace
from tests.tier1_offline.test_p0320_records import _quiet, _submitted_campaign

LABEL = "mtx_b1"
SCRIPT = "BATCH-6001-6002"


def _job() -> dict[str, object]:
    return {
        "kind": "batch",
        "name": SCRIPT,
        "batch_id": 1,
        "label": LABEL,
        "dir": f"sims/batch/{LABEL}/",
        "script": f"sims/batch/{LABEL}/{SCRIPT}.txt",
        "root": "<machine path>",
        "executor": "local",
        "values": {"sim": LABEL, "point": SCRIPT},
        "order": 1,
        "points": 2,
        "receipt_sha256": "d" * 64,
    }


def _batched(sim: str, status: RunStatus) -> RunRecord:
    base = _record(sim, f"camp/sim_{sim}/AL+000", status=status)
    return base.model_copy(update={"submission": {"job": _job(), "submitted": False}})


def _batch_workspace(
    tmp_path: Path, *, ended: bool, collected: bool, name: str = "camp"
) -> CampaignWorkspace:
    """Two sims in one batch folder; 6001 recorded CONVERGED, 6002 CONVERGED or SUBMITTED."""
    workspace = workspace_at(tmp_path, name)
    folder = workspace.root / "sims" / "batch" / LABEL
    _write(folder / f"{SCRIPT}.txt", "job script")
    _write(folder / "submit.yaml", "descriptor")
    if ended:
        _write(folder / f"{SCRIPT}.end.json", "{}")
    for sim in ("6001", "6002"):
        _write(folder / f"sim_{sim}" / "datapoints" / "DP-1" / "junk.vtk", "v")
    status = RunStatus.CONVERGED if collected else RunStatus.SUBMITTED
    workspace.append_record(_batched("6001", RunStatus.CONVERGED))
    workspace.append_record(_batched("6002", status))
    return workspace


# ------------------------------------------------------------------ delete-sims


def test_delete_sims_refuses_a_sim_of_a_running_batch_naming_it_unless_forced(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command delete-sims: refused while the batch runs."""
    workspace = _batch_workspace(tmp_path, ended=False, collected=True)
    _write(workspace.sim_dir("6001") / "datapoints" / "DP-1" / "x.txt", "copy")
    with pytest.raises(WorkspaceError, match=LABEL):
        storage_module.delete_sims(workspace.root, ["6001"], apply=True)
    assert workspace.sim_dir("6001").exists(), "a refused delete removed the folder"
    entry = storage_module.delete_sims(workspace.root, ["6001"], apply=True, force=True)
    assert entry["applied"] is True and not workspace.sim_dir("6001").exists()
    assert entry["batches_left_without_sim"] == [], "6002 is still in the batch"
    assert (workspace.root / "sims" / "batch" / LABEL / "sim_6002").is_dir()


def test_delete_sims_removes_the_sim_inside_an_ended_batch_and_reports_the_empty_batch(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command delete-sims: finds sims/batch/*/sim_<id>."""
    workspace = _batch_workspace(tmp_path, ended=True, collected=True)
    folder = workspace.root / "sims" / "batch" / LABEL
    assert not workspace.sim_dir("6001").exists()
    one = storage_module.delete_sims(workspace.root, ["6001"], apply=True)
    assert not (folder / "sim_6001").exists() and (folder / "sim_6002").is_dir()
    assert one["batches_left_without_sim"] == []
    both = storage_module.delete_sims(workspace.root, ["6002"], apply=False)
    assert both["batches_left_without_sim"] == [f"sims/batch/{LABEL}/"], "the preview said nothing"
    storage_module.delete_sims(workspace.root, ["6002"], apply=True)
    assert not (folder / "sim_6002").exists()
    assert (folder / f"{SCRIPT}.txt").is_file(), "the job's own files are not the sim's to delete"
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert {row.get("deleted_sim") for row in raw} >= {"6001", "6002"}


# ------------------------------------------------------------------ sync


def test_sync_carries_the_batch_tree_at_the_levels_that_carry_sim_files(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command sync: sims/batch/** travels by level."""
    other = _batch_workspace(tmp_path, ended=True, collected=True, name="other")
    folder = other.root / "sims" / "batch" / LABEL
    _write(folder / "sim_6001" / "scripts" / "point.fs", "s")
    _write(folder / "sim_6001" / "datapoints" / "DP-1" / "run_log.txt", "l")
    _write(folder / "sim_6001" / "datapoints" / "DP-1" / "case.fsm", "f")
    _write(folder / f"{SCRIPT}.job-log.txt", "log")
    prefix = f"sims/batch/{LABEL}"
    runs = _copied_paths(tmp_path, other.root, "runs", "bt_runs")
    assert f"{prefix}/{SCRIPT}.txt" in runs and f"{prefix}/{SCRIPT}.job-log.txt" in runs
    assert f"{prefix}/sim_6001/scripts/point.fs" in runs
    assert f"{prefix}/sim_6001/datapoints/DP-1/run_log.txt" in runs
    assert (
        f"{prefix}/submit.yaml" not in runs
        and f"{prefix}/sim_6001/datapoints/DP-1/case.fsm" not in runs
    )
    fsm = _copied_paths(tmp_path, other.root, "fsm", "bt_fsm")
    assert f"{prefix}/sim_6001/datapoints/DP-1/case.fsm" in fsm
    assert f"{prefix}/submit.yaml" not in fsm
    everything = _copied_paths(tmp_path, other.root, "all", "bt_all")
    assert f"{prefix}/submit.yaml" in everything
    assert f"{prefix}/sim_6002/datapoints/DP-1/junk.vtk" in everything


# ------------------------------------------------------------------ post --from-sims


def test_post_from_sims_skips_the_job_scripts_of_a_polar_sweep_and_a_batch(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command post --from-sims: job scripts are no export."""
    workspace = _from_sims_workspace(tmp_path)
    before, refused_before = records.assemble_records(workspace.root, "matriz")
    assert before
    sim = workspace.sim_dir("6001")
    (sim / "FULL-POLAR.txt").write_text("OPEN_SOLVER\n", encoding="utf-8")
    (sim / "BATCH-6001-6002.txt").write_text("OPEN_SOLVER\n", encoding="utf-8")
    after, refused_after = records.assemble_records(workspace.root, "matriz")
    assert refused_after == refused_before
    assert [r.run_id for r in after] == [r.run_id for r in before]
    assert [r.outputs for r in after] == [r.outputs for r in before]


# ------------------------------------------------------------------ free-space


def test_free_space_keeps_the_job_scripts_and_a_running_batch(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command free-space: scripts kept, running batch skipped."""
    workspace = workspace_at(tmp_path, "scripts")
    sim = workspace.sim_dir("6101")
    for name in ("FULL-POLAR.txt", "BATCH-6101-6102.txt", "notes.txt"):
        _write(sim / name, "x")
    workspace.append_record(_record("6101", "camp/sim_6101/AL+000"))
    _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".txt"]\n')
    storage_module.free_space(workspace.root, "m001", apply=True)
    assert (sim / "FULL-POLAR.txt").is_file() and (sim / "BATCH-6101-6102.txt").is_file()
    assert not (sim / "notes.txt").exists(), "the control: an ordinary .txt is still freed"

    running = _batch_workspace(tmp_path, ended=False, collected=True, name="running")
    ended = _batch_workspace(tmp_path, ended=True, collected=True, name="ended")
    for workspace in (running, ended):
        _write(workspace.sim_dir("6001") / "datapoints" / "DP-1" / "junk.vtk", "v")
        _write_recipe(workspace, "m001", '[[delete_extensions]]\nextensions = [".vtk"]\n')
        storage_module.free_space(workspace.root, "m001", apply=True)
    held = running.sim_dir("6001") / "datapoints" / "DP-1" / "junk.vtk"
    freed = ended.sim_dir("6001") / "datapoints" / "DP-1" / "junk.vtk"
    assert held.is_file(), "free-space freed a sim whose batch is still running"
    assert not freed.exists(), "the control: the same sim of an ended batch is freed"
    assert (running.root / "sims" / "batch" / LABEL / "sim_6001").is_dir()


# ------------------------------------------------------------------ run --force-rerun


def test_run_force_rerun_is_refused_for_a_sim_of_a_running_batch_naming_the_batch(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command run --force-rerun: refused, batch named."""
    running = _batch_workspace(tmp_path, ended=False, collected=True, name="running")
    manifest = {r.run_id: r for r in running.read_manifest()}
    with pytest.raises(WorkspaceError, match=f"batch {LABEL}"):
        queued_points(running, manifest, ["camp/sim_6001/AL+000"])
    ended = _batch_workspace(tmp_path, ended=True, collected=False, name="ended")
    manifest = {r.run_id: r for r in ended.read_manifest()}
    assert queued_points(ended, manifest, ["camp/sim_6001/AL+000"]) == []
    assert queued_points(ended, manifest, ["camp/sim_6002/AL+000"]) == ["camp/sim_6002/AL+000"]


# ------------------------------------------------------------------ mark-failed


def test_mark_failed_finds_a_sim_inside_a_running_batch_and_leaves_its_sibling(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command mark-failed: the sim is in sims/batch/*/."""
    workspace = _batch_workspace(tmp_path, ended=False, collected=False)
    assert not workspace.sim_dir("6002").exists(), "the sim lives only in the batch folder"
    done = records.mark_failed(workspace.root, ["6002"], reason="the job died", apply=True)
    assert [item["sim_id"] for item in done["marked"]] == ["6002"]
    status = {r.sim_id: r.status for r in workspace.read_manifest()}
    assert status["6002"] is RunStatus.FAILED_MARKED and status["6001"] is RunStatus.CONVERGED


# ------------------------------------------------------------------ rebuild


def test_rebuild_reads_a_batch_point_as_submitted_never_as_run_locally(tmp_path):
    """P0350-BATCH-TRANSPARENT (FR-372), command rebuild: the descriptor is in the job folder."""
    workspace, _matrix, job = _submitted_campaign(tmp_path)
    _quiet(workspace.root / "sims")
    alone = records.rebuild(workspace.root, all_sims=True, out="runs-alone.json")["records"]
    assert alone[0]["submission"] is not None, "the control: a point run alone is submitted"
    sim = workspace.sim_dir(job.sim_id)
    descriptor = next(sim.rglob("submit.yaml"))
    folder = workspace.root / "sims" / "batch" / LABEL
    (folder / f"sim_{job.sim_id}").mkdir(parents=True)
    shutil.move(descriptor, folder / "submit.yaml")
    moved = records.rebuild(workspace.root, all_sims=True, out="runs-batch.json")["records"]
    assert moved[0]["submission"] is not None, "a batch point was read as run locally"
    assert moved[0]["submission"]["submitted"] is True
