"""The grouped plan: receipt, table, pristine geometry and the polars left out (FT-PLAN).

``pyfs-matrix plan --batch N`` and ``--polar-sweep`` plan the matrix, group its unsteady polars,
and write the decision into ``plan.json`` as ``grouping``. The fixtures are the synthetic rotor
rig of the matrix tests; recorded wall times come from a COMPLETED record in the manifest so the
cost fit has a sample.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases.workflows import WORKFLOW_KEY, workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run._batch_plan import eligibility, grouping_table_lines, plan_grouped_matrix
from pyflightstream.run._plan import PlanStatus
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import RunRecord, RunStatus
from tests.tier1_offline.test_fsm_saved_actions import ACTIONS, _saved_simulation
from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row, _workspace
from tests.tier1_offline.test_restart_continuation import _continuing_case

KEYS_OF_034 = {
    "campaign",
    "campaign_name_from",
    "fs_version",
    "package_version",
    "build_groups",
    "setup_inspections",
    "points",
    "matrix_sha256",
    "accept_unregistered_build",
}
JOB_KEYS = {
    "name",
    "batch_id",
    "label",
    "dir",
    "script",
    "sims",
    "points",
    "fs_build",
    "ncpus",
    "estimate_s",
    "estimate_basis",
    "fallback_points",
    "unestimated_points",
    "overheads_s",
    "factor",
    "margin_s",
    "walltime_s",
    "walltime_written",
    "walltime_source",
    "fits",
    "shortfall_s",
}
RECEIPT_KEYS = {
    "schema",
    "mode",
    "requested",
    "selection",
    "batch_count",
    "batches",
    "left_out",
    "total_estimate_s",
    "longest_estimate_s",
    "max_walltime_s",
    "warnings",
}
ROW_FORM = "| 8     | 1h       |"


def _fixture(tmp_path: Path, walltimes=("BEST", "BEST", "BEST"), sweep="0.0,2.0,4.0"):
    """A workspace and a matrix of one unsteady rotor polar per walltime cell."""
    workspace = _workspace(tmp_path)
    matrix = _rotor_row(tmp_path, sweep=sweep)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    assert ROW_FORM in row
    rows = [
        row.replace("7001", str(7001 + index)).replace(ROW_FORM, f"| 8     | {cell:<8} |")
        for index, cell in enumerate(walltimes)
    ]
    matrix.write_text("\n".join([header, rule, *rows]) + "\n", encoding="utf-8")
    return workspace, matrix


def _sample(workspace, seconds: float = 720.0, campaign: str = "rotor") -> None:
    """One COMPLETED unsteady point of 720 steps: the fit then has a rate of seconds/720."""
    workspace.append_record(
        RunRecord(
            run_id=f"{campaign}/sim_7001/V0300RE120AL+000",
            sim_id="7001",
            fs_version_requested="26.123",
            package_version="0.35.0.dev0",
            script_sha256="c" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
            recipe="unsteady_rotor",
            wall_time_s=seconds,
        )
    )


def _plan(workspace, matrix, *, mode="batch", batch=2, **extra):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return plan_grouped_matrix(
            matrix,
            workspace,
            mode=mode,
            batch=batch,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            **extra,
        )


def test_p0350_plan_fr365_the_receipt_holds_every_field(tmp_path):
    """P0350-BATCH-RECEIPT (FR-365):
    ``plan --batch 2`` writes every key of the receipt and keeps the old ones."""
    workspace, matrix = _fixture(tmp_path)
    _sample(workspace)
    plan = _plan(workspace, matrix)
    payload = json.loads(plan.plan_file.read_text(encoding="utf-8"))
    assert set(payload) == KEYS_OF_034 | {"grouping"}
    grouping = payload["grouping"]
    assert set(grouping) == RECEIPT_KEYS
    assert grouping["schema"] == "pyfs-grouping/1" and grouping["mode"] == "batch"
    assert grouping["requested"] == 2 and grouping["batch_count"] == 2
    assert grouping["left_out"] == []
    for job in grouping["batches"]:
        assert set(job) == JOB_KEYS
        assert job["walltime_source"] == "BEST" and job["walltime_written"].endswith("m")
        assert job["estimate_s"] > 0 and job["fits"] is True
    first = grouping["batches"][0]
    assert first["batch_id"] == 1 and first["label"] == "rotor_b1"
    assert first["dir"] == "sims/batch/rotor_b1/"
    assert first["script"] == "sims/batch/rotor_b1/BATCH-7001-7001.txt"
    # the 720 s sample is a rate of 1 s per step, so a 720-step point is 720 s, three points of
    # one polar: start + the sum + the re-initialisations between its points
    assert first["sims"] == ["7001"] and len(first["points"]) == 3
    assert first["estimate_s"] == pytest.approx(2.0 + 3 * 720.0 + 0.08 * 2)
    assert grouping["total_estimate_s"] == pytest.approx(
        sum(job["estimate_s"] for job in grouping["batches"])
    )
    assert plan.grouping is not None and not plan.blocked


def test_p0350_plan_fr362_failed_points_are_pending_again(tmp_path):
    """P0350-BATCH-SPLIT (FR-362): a FAILED point is pending again for a grouped plan."""
    workspace, matrix = _fixture(tmp_path, walltimes=("1h", "1h"))
    assert workspace.read_manifest() == []
    control = _plan(workspace, matrix, batch=1)
    assert not control.blocked
    assert [job.sims for job in control.grouping.jobs] == [("7001", "7002")]
    assert control.grouping.left_out == ()
    for point in control.points:
        workspace.append_record(
            RunRecord(
                run_id=point.run_id,
                sim_id=point.sim_id,
                fs_version_requested="26.123",
                package_version="0.35.0.dev0",
                script_sha256="c" * 64,
                raw_flag=False,
                status=(
                    RunStatus.FAILED_EXECUTION if point.sim_id == "7001" else RunStatus.CONVERGED
                ),
                recipe="unsteady_rotor",
            )
        )
    plan = _plan(workspace, matrix, batch=1)
    assert not plan.blocked
    assert [job.sims for job in plan.grouping.jobs] == [("7001",)]
    assert plan.grouping.jobs[0].points == tuple(
        point.run_id for point in control.points if point.sim_id == "7001"
    )
    assert plan.grouping.left_out == ({"sim": "7002", "reason": "every point is already recorded"},)


def test_p0350_plan_fr362_the_table(tmp_path):
    """P0350-BATCH-TABLE (FR-362):
    one row per job and a total line; a polar sweep one row per polar."""
    workspace, matrix = _fixture(tmp_path)
    _sample(workspace)
    lines = grouping_table_lines(_plan(workspace, matrix).grouping)
    assert lines[0].split() == [
        "batch",
        "id",
        "sims",
        "cpus",
        "points",
        "estimate",
        "walltime",
        "source",
    ]
    rows = [line for line in lines if line.split()[0].startswith("rotor_b")]
    assert len(rows) == 2
    totals = [line for line in lines if line.lstrip().startswith("total")]
    assert len(totals) == 1 and "longest job" in totals[0]
    sweep = _plan(workspace, matrix, mode="polar_sweep", batch=None)
    assert sweep.grouping.requested is None
    sweep_lines = grouping_table_lines(sweep.grouping)
    assert len([line for line in sweep_lines if line.split()[0] == "FULL-POLAR"]) == 3
    assert [job.batch_id for job in sweep.grouping.jobs] == [None, None, None]
    assert [job.script for job in sweep.grouping.jobs][0] == "sims/sim_7001/FULL-POLAR.txt"


def test_p0350_plan_fr378_a_geometry_with_saved_actions_is_refused(tmp_path):
    """P0350-BATCH-PRISTINE-FSM (FR-378): saved solver actions BLOCK the grouped plan.

    A clean file passes.

    The control is the same workspace with the geometry saved without actions: it plans READY.
    The default plan of the dirty file still only warns, as FR-313 says.
    """
    workspace, matrix = _fixture(tmp_path / "dirty", walltimes=("2h",), sweep="0.0")
    (staged,) = (workspace.inputs_dir / "geometries").rglob("wing_clean.fsm")
    _saved_simulation(staged, ACTIONS)
    plan = _plan(workspace, matrix, batch=1)
    assert plan.blocked and all(entry.status is PlanStatus.BLOCKED for entry in plan.points)
    error = str(plan.blocked[0].error)
    assert staged.name in error and "pfs_walltime_clock" in error
    assert f"pyfs-matrix inventory {staged} --clean" in error
    assert plan.grouping.jobs == ()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        default = plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )
    assert not default.blocked and default.grouping is None
    clean_workspace, clean_matrix = _fixture(tmp_path / "clean", walltimes=("2h",), sweep="0.0")
    (clean,) = (clean_workspace.inputs_dir / "geometries").rglob("wing_clean.fsm")
    _saved_simulation(clean, [])
    control = _plan(clean_workspace, clean_matrix, batch=1)
    assert not control.blocked and len(control.grouping.jobs) == 1


def test_p0350_plan_fr379_left_out_polars_are_named(tmp_path):
    """P0350-BATCH-TABLE (FR-379): warm steady and RESTART rows are named with their reasons.

    The warm steady row (``COLD_START`` false; a cold steady row joins since 0.35.1, FR-403)
    is a real row of the matrix and is left out of the receipt; the RESTART row is judged by
    ``eligibility`` on its case. An acoustic row joins since 0.35.1 (FR-406,
    ``test_p0351_batch_acoustic.py``). The default plan of the same matrix carries no
    ``grouping`` key.
    """
    workspace, matrix = _fixture(tmp_path, walltimes=("1h", "1h"), sweep="0.0")
    text = matrix.read_text(encoding="utf-8").replace("unsteady_rotor |", "steady         |", 1)
    text = text.replace("LAST_REVS_AVG: 0.25", "LAST_REVS_AVG: 0.25 / COLD_START: false", 1)
    matrix.write_text(text, encoding="utf-8")
    plan = _plan(workspace, matrix, batch=2)
    assert [item["sim"] for item in plan.grouping.left_out] == ["7001"]
    assert "COLD_START false" in plan.grouping.left_out[0]["reason"]
    assert [job.sims for job in plan.grouping.jobs] == [("7002",)]
    restart = _continuing_case("{FINISH_PENDING}")
    assert "RESTART" in str(eligibility(restart, workspace=workspace, version="26.124"))
    plain = _continuing_case("{FINISH_PENDING}").model_copy(
        update={"variables": {WORKFLOW_KEY: "unsteady"}}
    )
    assert eligibility(plain, workspace=workspace, version="26.124") is None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        default = plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )
    assert "grouping" not in json.loads(default.plan_file.read_text(encoding="utf-8"))


def test_p0350_plan_fr364_best_refused_in_the_default_mode(tmp_path):
    """P0350-BATCH-WALLTIME (FR-364):
    a BEST row plans BLOCKED by name in the default mode; ``4h`` plans READY."""
    workspace, matrix = _fixture(tmp_path / "best", walltimes=("BEST",), sweep="0.0")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )
    assert [str(entry.status) for entry in plan.points] == ["BLOCKED"]
    assert "BEST asks the package for the walltime" in str(plan.points[0].error)
    assert "batch (CLI: --batch)" in str(plan.points[0].error)
    assert "polar_sweep (CLI: --polar-sweep)" in str(plan.points[0].error)
    workspace, matrix = _fixture(tmp_path / "four", walltimes=("4h",), sweep="0.0")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        control = plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )
    assert [str(entry.status) for entry in control.points] == ["READY"]


def test_p0350_plan_fr364_best_is_priced_in_the_grouped_mode(tmp_path):
    """P0350-BATCH-WALLTIME (FR-364, FR-377):
    BEST rows plan READY grouped, priced from the fit and the profile."""
    workspace, matrix = _fixture(tmp_path, walltimes=("BEST",), sweep="0.0,2.0")
    _sample(workspace, seconds=7200.0)
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        'application_id = "FS"\nmax_walltime = "01:00:00"\n[submit]\ncommand = ["echo"]\n'
        '[descriptor.fields]\nncpus = "{ncpus}"\n',
        encoding="utf-8",
    )
    plan = _plan(workspace, matrix, batch=1)
    (job,) = plan.grouping.jobs
    assert not plan.blocked
    assert job.walltime_source == "max_walltime" and job.walltime_s == 3600
    assert job.fits is False and job.shortfall_s and job.shortfall_s > 0
    assert any("larger --batch n" in text for text in plan.grouping.warnings)
    assert plan.grouping.max_walltime_s == 3600


def _profile(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "h001.toml"
    path.write_text(
        f'application_id = "FS"\n{extra}\n[submit]\ncommand = ["echo"]\n'
        '[descriptor.fields]\nncpus = "{ncpus}"\n',
        encoding="utf-8",
    )
    return path


def test_p0350_hpc_fr377_max_walltime_and_job_root(tmp_path):
    """P0350-BATCH-WALLTIME (FR-377):
    ``48:00:00`` reads 172800 s; ``2d`` and ``48h`` are refused by name."""
    from pyflightstream.workspace import InputArtifactError
    from pyflightstream.workspace.inputs import read_hpc_profile

    profile = read_hpc_profile(_profile(tmp_path, 'max_walltime = "48:00:00"'))
    assert profile.max_walltime_s == 172800 and profile.job_root == "{work_dir}"
    scratch = read_hpc_profile(_profile(tmp_path, 'job_root = "/scratch/{batch}"'))
    assert scratch.job_root == "/scratch/{batch}" and scratch.max_walltime_s is None
    for bad in ('max_walltime = "2d"', 'max_walltime = "48h"', 'max_walltime = "00:00:00"'):
        with pytest.raises(InputArtifactError, match="max_walltime"):
            read_hpc_profile(_profile(tmp_path, bad))
    with pytest.raises(InputArtifactError, match="job_root"):
        read_hpc_profile(_profile(tmp_path, 'job_root = "/scratch/{node}"'))
    with pytest.raises(InputArtifactError, match="walltime_max"):
        read_hpc_profile(_profile(tmp_path, 'walltime_max = "48:00:00"'))


def test_p0350_plan_fr362_the_command_line_prints_the_table(tmp_path, capsys):
    """P0350-BATCH-TABLE (FR-362): ``plan --batch 2`` prints a row per job and the total."""
    from pyflightstream.run.cli import main

    workspace, matrix = _fixture(tmp_path)
    _sample(workspace, campaign="camp")
    code = main(["plan", str(matrix), "--workspace", str(workspace.root), "--batch", "2"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "rotor_b1" in out and "rotor_b2" in out and "longest job" in out
    grouping = json.loads((workspace.plan_dir("rotor") / "plan.json").read_text("utf-8"))[
        "grouping"
    ]
    assert grouping["batch_count"] == 2
