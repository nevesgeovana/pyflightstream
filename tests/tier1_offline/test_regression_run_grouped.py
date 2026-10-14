"""Regression coverage grouped by subject."""

from __future__ import annotations

import dataclasses
import json
import shutil
import sys
from contextvars import copy_context
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import CampaignErrors, LoadsAssessor, _batch_plan, cli
from pyflightstream.run import _batch_run as batch_run
from pyflightstream.run import _campaign as campaign_module
from pyflightstream.run import matrix as _run_2_grouped_run__run_matrix
from pyflightstream.run._batch_run import _job_root, _profile_for, job_values
from pyflightstream.run._batch_split import JobSplit, job_walltime
from pyflightstream.run._grouped import read_receipt
from pyflightstream.run._plan import PlanStatus
from pyflightstream.run.matrix import run_matrix as _run_1_sweep__run_matrix
from pyflightstream.script import BrokenCommandUse, Script
from pyflightstream.workspace import CampaignWorkspace, RunStatus, WorkspaceError
from pyflightstream.workspace._batches import GroupedJob
from pyflightstream.workspace.hpc import read_hpc_profile, select_hpc_profile
from pyflightstream.workspace.inputs import InputArtifactError
from tests.support_helpers import grouped_plan_fixture as _run_2_grouped__grouped_plan_fixture
from tests.tier1_offline import test_p0350_batch_run as _run_1_batch_run__p0350
from tests.tier1_offline import test_p0350_batch_run as _run_1_grouped__p0350
from tests.tier1_offline.test_goal024_profile_log import (
    _profile_text as _run_1_batch_run___profile_text,
)
from tests.tier1_offline.test_goal035_l1_defects import _loads as _integfix_sweep_log___loads
from tests.tier1_offline.test_goal035_l1_defects import (
    _wheel_log as _integfix_sweep_log___wheel_log,
)
from tests.tier1_offline.test_matrix_run import RECIPES as _RUN_1_SWEEP__RECIPES
from tests.tier1_offline.test_matrix_run import (
    WRITES_EVERY_EXPORT as _RUN_1_SWEEP__WRITES_EVERY_EXPORT,
)
from tests.tier1_offline.test_matrix_run import CountingStub as _Run1SweepCountingStub
from tests.tier1_offline.test_matrix_run import (
    _steady_sweep_matrix as _run_1_sweep___steady_sweep_matrix,
)
from tests.tier1_offline.test_matrix_run import converged as _run_1_sweep__converged
from tests.tier1_offline.test_p0350_batch_plan import _plan as _run_2_grouped___plan
from tests.tier1_offline.test_p0350_batch_run import MATRIX as _RUN_2_GROUPED_RUN__MATRIX
from tests.tier1_offline.test_p0350_batch_run import _matrix as _run_2_grouped_run___matrix
from tests.tier1_offline.test_p0350_batch_run import _plan as _run_2_grouped_run___plan
from tests.tier1_offline.test_p0350_batch_run import _workspace as _run_2_grouped_run___workspace
from tests.tier1_offline.test_p0350_batch_split import HOUR as _RUN_1_BATCH_SPLIT__HOUR
from tests.tier1_offline.test_p0350_batch_split import _unit as _run_1_batch_split___unit


class TestIntegfixSweepLog:
    """Tier 1, 0.40.0 integration fixes: a steady sweep point beside the sweep's shared log."""

    @staticmethod
    def test_p0400_a_sweep_point_is_not_refused_for_the_sweeps_shared_log(tmp_path):
        """P0400-SWEEP-SHARED-LOG (PFS-2103.021): the solve-count refusal is a wheel's alone.

        A steady sweep solved in one script exports one solver log holding every
        point solved so far, so the second point's collected log holds two solves.
        The refusal of a log of another solve count, written for a quasi-steady
        wheel whose record could not be read, refused every point after the first
        of a sweep; such a point is judged by its iteration count, as before.
        """
        sim = tmp_path / "sim"
        outputs = sim / "outputs"
        outputs.mkdir(parents=True)
        (outputs / "DP.txt").write_text(_integfix_sweep_log___loads(61), encoding="utf-8")
        (outputs / "DP_log.txt").write_bytes(
            _integfix_sweep_log___wheel_log((2.0e-6, 3.0e-6), (61, 61)).encode("utf-8")
        )
        assessment = LoadsAssessor()(None, None, sim)
        assert "holds 2" not in (assessment.error or ""), assessment.error
        assert assessment.status is not RunStatus.FAILED_INCOMPLETE_OUTPUT, assessment


def _run_1_batch_run___job(
    *, batch_id: int | None, label: str, sims: tuple[str, ...]
) -> GroupedJob:
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


def _run_1_batch_run___two_profiles(tmp_path: Path) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    directory = workspace.inputs_dir / "hpc"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "a.toml").write_text(
        _run_1_batch_run___profile_text("\n[log]\nexport_log = true\n"), "utf-8"
    )
    (directory / "b.toml").write_text(_run_1_batch_run___profile_text(), "utf-8")
    return workspace


def _run_1_batch_run___failed_once(tmp_path: Path):
    """The 0.35.0 grouped workspace after a batch whose submit failed: three FAILED records."""
    workspace, profile, _ = _run_1_batch_run__p0350._workspace(
        tmp_path, submit=[sys.executable, "-c", "import sys; sys.exit(3)"]
    )
    matrix = _run_1_batch_run__p0350._matrix(tmp_path)
    _run_1_batch_run__p0350._plan(workspace, matrix, mode="batch", batch=1)
    # A job that did not launch is a failure of the run (PFS-2094.031): recorded, then raised.
    with pytest.raises(CampaignErrors):
        _run_1_batch_run__p0350._run(
            workspace, matrix, executor=_run_1_batch_run__p0350._submitting(profile)
        )
    assert [r.status for r in workspace.read_manifest()] == [RunStatus.FAILED_EXECUTION] * 3
    # The job folder is freed, as a new plan's batch would be, so the receipt admits a run.
    shutil.rmtree(workspace.root / "sims" / "batch" / f"{_run_1_batch_run__p0350.MATRIX}_b1")
    return workspace, matrix, profile


def _run_1_batch_run___refuse(*_args, **_kwargs):
    raise MatrixError("refused for the test")


class TestRun1BatchRun:
    """Tier 1, 0.40.0 lane run-1: a grouped run's profile and the placeholders of its job.

    Synthetic profiles in a fresh workspace and a hand-built job; no solver runs.
    """

    @staticmethod
    def test_p0400_a_local_grouped_run_reads_the_profile_the_plan_reads(tmp_path):
        """P0400-LOCAL-GROUPED-PROFILE (PFS-2094.027): --local honours --hpc and refuses a guess.

        Under --local the run took the first profile on disk, ``a``, while the plan resolved the
        selected ``b``, so the run's scripts exported the log the plan said they would not.
        """
        workspace = _run_1_batch_run___two_profiles(tmp_path)
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

    @staticmethod
    @pytest.mark.parametrize("where", ["plan_campaign", "_check_scheduled_builds"])
    def test_p0400_a_refused_grouped_run_supersedes_nothing(tmp_path, monkeypatch, where):
        """P0400-GROUPED-SUPERSEDE-LAST (PFS-2096.004): the pre-flight or identity check refuses.

        The FAILED records of the receipt's points were archived and taken out of runs.json
        before either check, so a refusal left the workspace changed with nothing executed.
        """
        workspace, matrix, profile = _run_1_batch_run___failed_once(tmp_path)
        before = workspace.manifest_path.read_bytes()
        monkeypatch.setattr(batch_run, where, _run_1_batch_run___refuse, raising=False)
        monkeypatch.setattr(campaign_module, "_check_scheduled_builds", _run_1_batch_run___refuse)
        with pytest.raises(MatrixError, match="refused for the test"):
            _run_1_batch_run__p0350._run(
                workspace, matrix, executor=_run_1_batch_run__p0350._submitting(profile)
            )
        assert workspace.manifest_path.read_bytes() == before

    @staticmethod
    def test_p0400_sim_and_batch_mean_one_thing_in_every_template(tmp_path):
        """P0400-JOB-PLACEHOLDERS (PFS-2088.017): ``{sim}`` the first simulation, ``{batch}`` the label.

        ``job_root`` filled ``{sim}`` with the batch label while the descriptor and ``native_log``
        filled it with the first simulation id; ``{batch}`` existed for a polar sweep in
        ``job_root`` only.
        """  # noqa: E501
        path = tmp_path / "h.toml"
        path.write_text(
            'job_root = "/scratch/{sim}/{batch}"\n' + _run_1_batch_run___profile_text(), "utf-8"
        )
        profile = read_hpc_profile(path)
        batch = _run_1_batch_run___job(batch_id=1, label="mtx_b1", sims=("2006", "2007"))
        assert _job_root(batch, Path("/w"), profile, True).as_posix() == "/scratch/2006/mtx_b1"
        assert job_values(batch, profile=profile)["sim"] == "2006"
        assert job_values(batch, profile=profile)["batch"] == "mtx_b1"
        sweep = _run_1_batch_run___job(batch_id=None, label="2006", sims=("2006",))
        assert _job_root(sweep, Path("/w"), profile, True).as_posix() == "/scratch/2006/2006"
        assert job_values(sweep, profile=profile)["batch"] == "2006"
        assert "batch_id" not in job_values(sweep, profile=profile)


class TestRun1BatchSplit:
    """Tier 1, 0.40.0 lane run-1: the wall clock of a grouped job (FR-364).

    Hand-built polar units; no plan and no solver.
    """

    @staticmethod
    def test_p0400_a_row_with_no_cell_and_no_best_is_not_budgeted_at_zero() -> None:
        # Verifies FR-364.
        """P0400-JOB-WALLTIME-UNSTATED (PFS-2094.006): one row states 2h, the other nothing.

        The sum covered the stated row alone, so the job's 2h bounded the other row's point
        too, silently. The job now asks the profile's limit and names the row, or is refused
        naming it where the profile states no limit.
        """
        stated = _run_1_batch_split___unit(
            "2001",
            1,
            0.0,
            seconds=(_RUN_1_BATCH_SPLIT__HOUR,),
            cell_s=2 * _RUN_1_BATCH_SPLIT__HOUR,
            cell_text="2h",
            best=False,
        )
        bare = _run_1_batch_split___unit(
            "2002", 2, 0.0, seconds=(_RUN_1_BATCH_SPLIT__HOUR,), best=False
        )
        job = JobSplit((stated, bare))
        seconds, source, _, _, warnings, refusal = job_walltime(
            job, 2 * _RUN_1_BATCH_SPLIT__HOUR, max_walltime_s=5 * _RUN_1_BATCH_SPLIT__HOUR
        )
        assert (seconds, source, refusal) == (5 * _RUN_1_BATCH_SPLIT__HOUR, "max_walltime", None)
        assert any("2002" in line and "max_walltime" in line for line in warnings), warnings
        seconds, _, _, _, _, refusal = job_walltime(
            job, 2 * _RUN_1_BATCH_SPLIT__HOUR, max_walltime_s=None
        )
        assert seconds is None
        assert refusal is not None and "2002" in refusal and "2001" in refusal


class TestRun1Grouped:
    """Tier 1, 0.40.0 lane run-1: the grouped run gate reads the plan's grouping block.

    The grouped workspace of the 0.35.0 tests, its receipt then spoiled by hand; no solver runs.
    """

    @staticmethod
    @pytest.mark.parametrize(
        "block",
        [{"schema": "pyfs-grouping/9"}, {"schema": "pyfs-grouping/1"}, "a sentence"],
        ids=["foreign-schema", "missing-keys", "not-a-table"],
    )
    def test_p0400_a_malformed_grouping_block_is_a_refusal_not_a_traceback(tmp_path, block):
        """P0400-GROUPING-UNREADABLE (PFS-2095.049): a spoiled ``grouping`` block in plan.json.

        The gate caught only OSError, ValueError and AttributeError around the JSON and read the
        block outside the try, so another schema, a missing key or a non-table block crashed the
        run with ValueError, KeyError or TypeError. It is now refused: plan it again.
        """
        workspace, profile, _ = _run_1_grouped__p0350._workspace(tmp_path)
        matrix = _run_1_grouped__p0350._matrix(tmp_path)
        _run_1_grouped__p0350._plan(workspace, matrix, mode="batch", batch=1)
        plan_file = workspace.plan_dir(_run_1_grouped__p0350.MATRIX) / "plan.json"
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
        payload["grouping"] = block
        plan_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        assert read_receipt(workspace, _run_1_grouped__p0350.MATRIX) is None
        with pytest.raises(MatrixError, match="no readable grouping"):
            _run_1_grouped__p0350._run(
                workspace, matrix, executor=_run_1_grouped__p0350._submitting(profile)
            )


_RUN_1_SWEEP__USE = BrokenCommandUse(
    command="AIR_ALTITUDE",
    version="26.120",
    source_version="26.120",
    report="RPT-000",
    reason="reproducing a run made before the defect",
)


_RUN_1_SWEEP__WAIVED = _RUN_1_SWEEP__USE.model_dump(mode="json")


class TestRun1Sweep:
    """Tier 1, 0.40.0 lane run-1: a steady row's one-job record carries what a point's does.

    The warm steady row of the 0.19.0 tests, run with the counting stub; no solver runs.
    """

    @staticmethod
    def test_p0400_a_steady_job_record_carries_its_waivers_and_its_staging(tmp_path, monkeypatch):
        """P0400-JOB-RECORD-PROVENANCE (PFS-2103.026): waived_commands and staged_as on a job.

        The job path wrote ``waived_commands: []`` whatever its script waived and never wrote
        ``staged_as``; the point path filled both. Both paths now take them from one helper.
        """
        monkeypatch.setattr(Script, "waived_commands", property(lambda self: (_RUN_1_SWEEP__USE,)))
        workspace, matrix = _run_1_sweep___steady_sweep_matrix(tmp_path)
        (record,) = _run_1_sweep__run_matrix(
            matrix,
            workspace,
            name="warm",
            default_fs_version="26.120",
            recipes=_RUN_1_SWEEP__RECIPES,
            recipe_registry=workflow_registry(),
            assess=_run_1_sweep__converged,
            executor=_Run1SweepCountingStub(_RUN_1_SWEEP__WRITES_EVERY_EXPORT),
        )
        assert len(record.points_ran or []) == 3, "the row ran as one job"
        assert [dict(use) for use in record.waived_commands] == [_RUN_1_SWEEP__WAIVED]
        mode, reason = workspace.staged_as("5001")
        assert mode is not None
        assert (record.staged_as, record.staged_as_reason) == (mode, reason)


class TestRun2Grouped:
    """Tier 1, 0.40.0 lane run-2: the grouped plan, split, run and collect (--batch, --polar-sweep).

    The workspaces are the grouped-plan fixture the 0.35.0 tests share.
    """

    @staticmethod
    def test_p0400_a_batch_simulation_completed_while_the_job_ran_is_moved_home(tmp_path):
        """P0400-BATCH-MOVE-ALL (PFS-2103.022): every simulation of an ended batch goes home.

        7001's points complete from copies while the job runs; when the job ends
        only the simulations with a SUBMITTED record were moved, so 7001's batch
        copy stayed for good.
        """
        import warnings
        from pathlib import Path

        from pyflightstream.run.collect import collect_once
        from pyflightstream.workspace import RunStatus
        from tests.support_helpers import no_sleep
        from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace

        workspace = grouped_workspace(tmp_path, mode="batch", collect=False, ended=False)
        (record,) = [r for r in workspace.read_manifest() if r.sim_id == "7003"]
        job = (record.submission or {})["job"]
        batch_sim = workspace.root / job["dir"] / "sim_7003"
        held = {
            path: path.read_bytes() for path in batch_sim.rglob("*.txt") if "_" not in path.name
        }
        assert held, "the fixture writes 7003's loads in its batch folder"
        for path in held:
            path.unlink()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            collect_once(workspace, interval=0.0, sleep=no_sleep)
            statuses = {r.sim_id: r.status for r in workspace.read_manifest()}
            assert statuses["7001"] is not RunStatus.SUBMITTED, statuses
            assert statuses["7003"] is RunStatus.SUBMITTED, statuses
            for path, body in held.items():
                path.write_bytes(body)
            end = workspace.root / job["dir"] / f"{Path(job['script']).stem}.end.json"
            end.write_text('{"return_code": 0}', encoding="utf-8")
            collect_once(workspace, interval=0.0, sleep=no_sleep)
        assert not (workspace.root / job["dir"] / "sim_7001").exists()
        assert not batch_sim.exists()

    @staticmethod
    def test_p0400_job_walltime_prices_a_row_that_states_no_walltime():
        """P0400-JOB-WALLTIME (PFS-2094.007): a row with no WALLTIME is priced, not added as 0 s.

        Beside a BEST polar the job asked no wall clock at all; beside a cell row
        its five points added nothing, with no warning.
        """
        from pyflightstream.run._batch_split import JobSplit, job_walltime
        from tests.tier1_offline.test_p0350_batch_split import _unit

        best = _unit("7001", 1, 0.0, points=2, seconds=(100.0, 100.0))
        silent = _unit("7002", 2, 0.0, points=5, best=False, seconds=(None,) * 5)
        seconds, source, _fits, _short, warnings, refusal = job_walltime(
            JobSplit((best, silent)), None, max_walltime_s=None
        )
        assert seconds is None and refusal is not None and "m/sim_7002/p0" in refusal
        cell = _unit("7003", 1, 0.0, cell_s=600.0, cell_text="10m", best=False, seconds=(None,))
        seconds, source, _fits, _short, warnings, refusal = job_walltime(
            JobSplit((cell, silent)), None, max_walltime_s=7200.0
        )
        assert (seconds, source, refusal) == (7200, "max_walltime", None)
        assert any("m/sim_7002/p4" in line for line in warnings), warnings

    @staticmethod
    def test_p0400_a_polar_with_a_blocked_point_is_left_out_by_name(tmp_path, monkeypatch):
        """P0400-GROUPED-BLOCKED (PFS-2094.005): the polar is named among the left out.

        A grouped job holds a polar whole, so one blocked point keeps its READY
        siblings from running too; the polar was dropped without a word.
        """
        workspace, matrix = _run_2_grouped__grouped_plan_fixture(
            tmp_path, walltimes=("2h", "2h"), sweep="0.0,2.0"
        )
        real = _batch_plan.plan_matrix

        def one_blocked(*args, **kwargs):
            plan = real(*args, **kwargs)
            points = list(plan.points)
            first = next(i for i, entry in enumerate(points) if entry.sim_id == "7001")
            points[first + 1] = dataclasses.replace(
                points[first + 1], status=PlanStatus.BLOCKED, error="a planted block"
            )
            return dataclasses.replace(plan, points=type(plan.points)(points))

        monkeypatch.setattr(_batch_plan, "plan_matrix", one_blocked)
        plan = _run_2_grouped___plan(workspace, matrix, batch=2)
        left = {item["sim"]: item["reason"] for item in plan.grouping.left_out}
        assert "7001" in left, plan.grouping.left_out
        assert "BLOCKED" in left["7001"] and "polar whole" in left["7001"]
        assert all("7001" not in job.sims for job in plan.grouping.jobs)


class TestRun2GroupedRun:
    """Tier 1, 0.40.0 lane run-2: a grouped run whose job does not launch.

    The workspace is the 0.35.0 batch-run fixture, with a submit command that exits 3.
    """

    @staticmethod
    def test_p0400_a_grouped_run_whose_job_is_refused_exits_non_zero(tmp_path, capsys, monkeypatch):
        """P0400-GROUPED-REFUSED-EXIT (PFS-2094.031): ``run --batch`` with a refused job exits 2.

        The job's points were recorded FAILED_EXECUTION and returned, not raised,
        so the command said it ran and exited 0. The machine is a cluster, so the
        run submits through the profile rather than refusing the absent local build.
        """
        monkeypatch.setattr(_run_2_grouped_run__run_matrix, "on_a_cluster", lambda: True)
        workspace, _profile, _ = _run_2_grouped_run___workspace(
            tmp_path, submit=[sys.executable, "-c", "import sys; sys.exit(3)"]
        )
        from pyflightstream.run import matrix as matrix_module

        monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: True)
        matrix = _run_2_grouped_run___matrix(tmp_path)
        _run_2_grouped_run___plan(workspace, matrix, mode="batch", batch=1)
        argv = [
            "run",
            str(matrix),
            "--workspace",
            str(workspace.root),
            "--name",
            _RUN_2_GROUPED_RUN__MATRIX,
            "--batch",
            "1",
            "--hpc",
            "h001",
        ]
        assert copy_context().run(cli.main, argv) == 2
        said = capsys.readouterr().err
        assert "matrix run with failures" in said, said
        recorded = workspace.read_manifest()
        assert recorded and {row.status.value for row in recorded} == {"FAILED_EXECUTION"}
        assert all("not launched" in (row.error or "") for row in recorded)


class TestRun1ReviewGrouped:
    """Grouped retries must retain evidence when a campaign scheduling guard refuses."""

    @staticmethod
    def test_p0400_review_grouped_queue_refusal_preserves_failed_records(tmp_path):
        """P0400-REVIEW-GROUPED: a foreign queued point refuses before supersession."""
        workspace, matrix, profile = _run_1_batch_run___failed_once(tmp_path)
        original = workspace.read_manifest()[0]
        workspace.append_record(
            original.model_copy(
                update={"run_id": "foreign/sim_7001/queued", "status": RunStatus.SUBMITTED}
            )
        )
        before = workspace.manifest_path.read_bytes()
        with pytest.raises(WorkspaceError, match="queue"):
            _run_1_batch_run__p0350._run(
                workspace, matrix, executor=_run_1_batch_run__p0350._submitting(profile)
            )
        assert workspace.manifest_path.read_bytes() == before

    @staticmethod
    @pytest.mark.parametrize("resume", [False, True])
    def test_p0400_review_grouped_retry_still_runs_after_the_guards_pass(tmp_path, resume):
        """P0400-REVIEW-GROUPED: deferring supersession must not skip the failed points."""
        workspace, matrix, profile = _run_1_batch_run___failed_once(tmp_path)
        ids = [record.run_id for record in workspace.read_manifest()]
        records = _run_1_batch_run__p0350.run_grouped_matrix(
            matrix,
            workspace,
            mode="batch",
            batch=1,
            name=_run_1_batch_run__p0350.MATRIX,
            recipes={},
            recipe_registry=_run_1_batch_run__p0350.workflow_registry(),
            executor=_run_1_batch_run__p0350._submitting(profile, submit=False),
            assess=_run_1_batch_run__p0350.converged,
            resume=resume,
        )
        assert [record.run_id for record in records] == ids
        assert all(record.status is RunStatus.SUBMITTED for record in records)
        assert [record.run_id for record in workspace.read_manifest()] == ids

    @staticmethod
    @pytest.mark.parametrize("resume", [False, True])
    def test_p0400_review_grouped_partial_retry_preserves_unfailed_points(tmp_path, resume):
        """P0400-REVIEW-GROUPED: retry neither removes nor reruns a completed sibling."""
        workspace, matrix, profile = _run_1_batch_run___failed_once(tmp_path)
        rows = workspace.read_raw_manifest()
        rows[0]["status"] = RunStatus.CONVERGED.value
        workspace._replace_manifest(rows)
        before = workspace.manifest_path.read_bytes()
        keywords = dict(
            mode="batch",
            batch=1,
            name=_run_1_batch_run__p0350.MATRIX,
            recipes={},
            recipe_registry=_run_1_batch_run__p0350.workflow_registry(),
            executor=_run_1_batch_run__p0350._submitting(profile, submit=False),
            assess=_run_1_batch_run__p0350.converged,
            resume=resume,
        )
        if not resume:
            with pytest.raises(WorkspaceError):
                _run_1_batch_run__p0350.run_grouped_matrix(matrix, workspace, **keywords)
            assert workspace.manifest_path.read_bytes() == before
        else:
            records = _run_1_batch_run__p0350.run_grouped_matrix(matrix, workspace, **keywords)
            assert {record.run_id for record in records} == {row["run_id"] for row in rows[1:]}
            assert workspace.read_raw_manifest()[0] == rows[0]
