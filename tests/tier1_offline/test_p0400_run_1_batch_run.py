"""Tier 1, 0.40.0 lane run-1: a grouped run's profile and the placeholders of its job.

Synthetic profiles in a fresh workspace and a hand-built job; no solver runs.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.run import _batch_run as batch_run
from pyflightstream.run import _campaign as campaign_module
from pyflightstream.run._batch_run import _job_root, _profile_for, job_values
from pyflightstream.run._campaign import CampaignErrors
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace._batches import GroupedJob
from pyflightstream.workspace.hpc import read_hpc_profile, select_hpc_profile
from pyflightstream.workspace.inputs import InputArtifactError
from tests.tier1_offline import test_p0350_batch_run as p0350
from tests.tier1_offline.test_goal024_profile_log import _profile_text


def _job(*, batch_id: int | None, label: str, sims: tuple[str, ...]) -> GroupedJob:
    return GroupedJob(
        name="BATCH-2006-2007" if batch_id else "FULL-POLAR",
        batch_id=batch_id,
        label=label,
        dir=f"sims/batch/{label}" if batch_id else f"sims/sim_{label}",
        script="job.txt",
        sims=sims,
        points=(),
        fs_build="26.124",
        ncpus=8,
        estimate_s=None,
        estimate_basis="",
        fallback_points=(),
        unestimated_points=(),
        overheads_s={},
        factor=1.25,
        margin_s=0.0,
        walltime_s=None,
        walltime_written="",
        walltime_source="none",
        fits=True,
        shortfall_s=None,
    )


def _two_profiles(tmp_path: Path) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    directory = workspace.inputs_dir / "hpc"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "a.toml").write_text(_profile_text("\n[log]\nexport_log = true\n"), "utf-8")
    (directory / "b.toml").write_text(_profile_text(), "utf-8")
    return workspace


def test_p0400_a_local_grouped_run_reads_the_profile_the_plan_reads(tmp_path):
    """P0400-LOCAL-GROUPED-PROFILE (PFS-2094.027): --local honours --hpc and refuses a guess.

    Under --local the run took the first profile on disk, ``a``, while the plan resolved the
    selected ``b``, so the run's scripts exported the log the plan said they would not.
    """
    workspace = _two_profiles(tmp_path)
    inner = SimpleNamespace(forced_local=True)
    with pytest.raises(InputArtifactError, match="holds 2 profiles"):
        _profile_for(workspace, inner)
    select_hpc_profile("b")
    try:
        profile = _profile_for(workspace, inner)
    finally:
        select_hpc_profile(None)
    assert profile == read_hpc_profile(workspace.inputs_dir / "hpc" / "b.toml")
    assert profile is not None and profile.export_log is False


def _failed_once(tmp_path: Path):
    """The 0.35.0 grouped workspace after a batch whose submit failed: three FAILED records."""
    workspace, profile, _ = p0350._workspace(
        tmp_path, submit=[sys.executable, "-c", "import sys; sys.exit(3)"]
    )
    matrix = p0350._matrix(tmp_path)
    p0350._plan(workspace, matrix, mode="batch", batch=1)
    with pytest.raises(CampaignErrors):
        p0350._run(workspace, matrix, executor=p0350._submitting(profile))
    assert [r.status for r in workspace.read_manifest()] == [RunStatus.FAILED_EXECUTION] * 3
    # The job folder is freed, as a new plan's batch would be, so the receipt admits a run.
    shutil.rmtree(workspace.root / "sims" / "batch" / f"{p0350.MATRIX}_b1")
    return workspace, matrix, profile


def _refuse(*_args, **_kwargs):
    raise MatrixError("refused for the test")


@pytest.mark.parametrize("where", ["plan_campaign", "_check_scheduled_builds"])
def test_p0400_a_refused_grouped_run_supersedes_nothing(tmp_path, monkeypatch, where):
    """P0400-GROUPED-SUPERSEDE-LAST (PFS-2096.004): the pre-flight or identity check refuses.

    The FAILED records of the receipt's points were archived and taken out of runs.json
    before either check, so a refusal left the workspace changed with nothing executed.
    """
    workspace, matrix, profile = _failed_once(tmp_path)
    before = workspace.manifest_path.read_bytes()
    monkeypatch.setattr(batch_run, where, _refuse, raising=False)
    monkeypatch.setattr(campaign_module, "_check_scheduled_builds", _refuse)
    with pytest.raises(MatrixError, match="refused for the test"):
        p0350._run(workspace, matrix, executor=p0350._submitting(profile))
    assert workspace.manifest_path.read_bytes() == before


def test_p0400_sim_and_batch_mean_one_thing_in_every_template(tmp_path):
    """P0400-JOB-PLACEHOLDERS (PFS-2088.017): ``{sim}`` the first simulation, ``{batch}`` the label.

    ``job_root`` filled ``{sim}`` with the batch label while the descriptor and ``native_log``
    filled it with the first simulation id; ``{batch}`` existed for a polar sweep in
    ``job_root`` only.
    """
    path = tmp_path / "h.toml"
    path.write_text('job_root = "/scratch/{sim}/{batch}"\n' + _profile_text(), "utf-8")
    profile = read_hpc_profile(path)
    batch = _job(batch_id=1, label="mtx_b1", sims=("2006", "2007"))
    assert _job_root(batch, Path("/w"), profile, True).as_posix() == "/scratch/2006/mtx_b1"
    assert job_values(batch, profile=profile)["sim"] == "2006"
    assert job_values(batch, profile=profile)["batch"] == "mtx_b1"
    sweep = _job(batch_id=None, label="2006", sims=("2006",))
    assert _job_root(sweep, Path("/w"), profile, True).as_posix() == "/scratch/2006/2006"
    assert job_values(sweep, profile=profile)["batch"] == "2006"
    assert "batch_id" not in job_values(sweep, profile=profile)
