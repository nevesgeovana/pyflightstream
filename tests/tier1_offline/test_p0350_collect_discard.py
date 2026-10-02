"""P0350-COLLECT-DISCARD (FR-400): restart clock-stopped points through a grouped plan."""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import SubmittingExecutor
from pyflightstream.run._batch_run import run_grouped_matrix
from pyflightstream.run.cli import main
from pyflightstream.run.collect import collect_and_post
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_matrix_run import HPC_PROFILE
from tests.tier1_offline.test_matrix_run import converged as run_converged
from tests.tier1_offline.test_p0350_batch_collect import (
    STATE,
)
from tests.tier1_offline.test_p0350_batch_collect import (
    _converged as converged,
)
from tests.tier1_offline.test_p0350_batch_collect import (
    _workspace as grouped_workspace,
)
from tests.tier1_offline.test_p0350_batch_plan import _fixture as plan_fixture
from tests.tier1_offline.test_p0350_batch_plan import _plan as grouped_plan


def clock_workspace(tmp_path):
    """Build the existing grouped fixture with the first point's clock fired."""
    workspace, job_dir, _ = grouped_workspace(tmp_path, "polar_sweep")
    actions = job_dir / "datapoints" / "DP-AL+000" / "actions"
    actions.mkdir()
    (actions / "pfs_walltime_clock.json").write_text(json.dumps(STATE), encoding="utf-8")
    return workspace


def record(run_id, sim="2006", status=RunStatus.WALLTIME_REACHED):
    """Make a terminal record with no grouped submission metadata."""
    return RunRecord(
        run_id=run_id,
        sim_id=sim,
        status=status,
        fs_version_requested="26.123",
        package_version="0.35.0.dev0",
        script_sha256="c" * 64,
        raw_flag=False,
        matrix_stem="rotor",
        recipe="unsteady_rotor",
    )


def collect_cli(workspace, *options):
    """Collect without post or real-time waits through the public CLI."""
    return main(
        [
            "collect",
            "--workspace",
            str(workspace.root),
            "--interval",
            "0",
            "--no-post",
            *options,
        ]
    )


def test_off_by_default(tmp_path, capsys):
    """P0350-COLLECT-DISCARD (FR-400): without the switch a stopped point stays recorded."""
    workspace = clock_workspace(tmp_path)
    report = collect_and_post(workspace, interval=0, assessor=converged)
    first, sibling = workspace.read_manifest()
    assert first.status is RunStatus.WALLTIME_REACHED
    assert sibling.status is RunStatus.CONVERGED
    assert "discarded_by" not in first.model_dump(mode="json")
    before = workspace.manifest_path.read_bytes()
    assert collect_cli(workspace) == 0
    assert workspace.manifest_path.read_bytes() == before
    assert not report.discarded
    assert "discarded WALLTIME_REACHED" not in capsys.readouterr().out


def test_discard_is_per_point_and_keeps_outputs(tmp_path):
    """P0350-COLLECT-DISCARD (FR-400): discard one stopped point and retain its sibling."""
    workspace = clock_workspace(tmp_path)
    report = collect_and_post(workspace, interval=0, assessor=converged, discard_walltime=True)
    first, sibling = workspace.read_manifest()
    assert first.status is RunStatus.FAILED_MARKED
    assert first.marked["from"] == "WALLTIME_REACHED"
    assert first.marked["at"] and first.marked["reason"] == "collect --discard-walltime"
    assert first.discarded_by == "collect --discard-walltime"
    assert sibling.status is RunStatus.CONVERGED and sibling.marked is None
    assert first.stopped_at == STATE["stopped_at"]
    assert (workspace.sim_dir("2006") / "datapoints/DP-AL+000/P2006-AL+000.txt").is_file()
    assert report.lines()[-1] == (
        f"discarded WALLTIME_REACHED: sim 2006 {first.run_id} "
        f"(stopped at {STATE['stopped_at']}); a grouped plan runs it again"
    )
    archived = list((workspace.root / "archive").glob("runs-*.json"))
    assert len(archived) == 1
    previous = json.loads(archived[0].read_text(encoding="utf-8"))
    assert previous[0]["status"] == "WALLTIME_REACHED"
    assert workspace.read_raw_manifest()[1] == previous[1]


def test_earlier_collect_is_discarded_once_by_cli(tmp_path, capsys):
    """P0350-COLLECT-DISCARD (FR-400): a later collect discards an earlier clock stop once."""
    workspace = clock_workspace(tmp_path)
    collect_and_post(workspace, interval=0, assessor=converged)
    assert collect_cli(workspace, "--discard-walltime") == 0
    first, _ = workspace.read_manifest()
    assert first.status is RunStatus.FAILED_MARKED
    expected = (
        f"discarded WALLTIME_REACHED: sim 2006 {first.run_id} "
        f"(stopped at {STATE['stopped_at']}); a grouped plan runs it again"
    )
    assert expected in capsys.readouterr().out
    before = workspace.manifest_path.read_bytes()
    assert collect_cli(workspace, "--discard-walltime") == 0
    assert workspace.manifest_path.read_bytes() == before
    assert "discarded WALLTIME_REACHED" not in capsys.readouterr().out


def test_default_mode_and_sims_scope(tmp_path, capsys):
    """P0350-COLLECT-DISCARD (FR-400): default-mode records obey the same simulation scope."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(workspace.root)
    workspace.append_record(record("camp/sim_2006/a"))
    workspace.append_record(record("camp/sim_2007/a", "2007"))
    outside = workspace.read_raw_manifest()[1]
    assert collect_cli(workspace, "--discard-walltime", "--sims", "2006") == 0
    first, other = workspace.read_manifest()
    assert first.status is RunStatus.FAILED_MARKED and first.submission is None
    assert other.status is RunStatus.WALLTIME_REACHED
    assert workspace.read_raw_manifest()[1] == outside
    out = capsys.readouterr().out
    assert "sim 2006 camp/sim_2006/a (stopped at ?); a grouped plan runs it again" in out
    assert "discarded WALLTIME_REACHED: sim 2007" not in out


def test_grouped_plan_and_run_archive_the_discarded_point(tmp_path, capsys):
    """P0350-COLLECT-DISCARD (FR-400): a new batch prepares the point from the start."""
    workspace, matrix = plan_fixture(tmp_path, walltimes=("1h",), sweep="0.0,2.0")
    first, sibling = grouped_plan(workspace, matrix, batch=1).points
    workspace.append_record(record(first.run_id, first.sim_id))
    workspace.append_record(record(sibling.run_id, sibling.sim_id, RunStatus.CONVERGED))
    point_name = first.run_id.rsplit("/", 1)[-1]
    output = workspace.sim_dir(first.sim_id) / "datapoints" / f"DP-{point_name}" / "old.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"interrupted outputs")
    assert collect_cli(workspace, "--discard-walltime") == 0
    assert output.read_bytes() == b"interrupted outputs"
    assert (
        main(
            [
                "plan",
                str(matrix),
                "--workspace",
                str(workspace.root),
                "--batch",
                "1",
                "--name",
                "rotor",
            ]
        )
        == 0
    )
    payload = json.loads((workspace.plan_dir("rotor") / "plan.json").read_text(encoding="utf-8"))
    assert payload["grouping"]["batches"][0]["points"] == [first.run_id]
    profile = workspace.inputs_dir / "hpc/h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(HPC_PROFILE, encoding="utf-8")
    executor = SubmittingExecutor(
        read_hpc_profile(profile), values={"fs_build": "26.123"}, submit=False
    )
    prepared = run_grouped_matrix(
        matrix,
        workspace,
        mode="batch",
        batch=1,
        name="rotor",
        recipes={},
        recipe_registry=workflow_registry(),
        assess=run_converged,
        executor=executor,
        resume=True,
    )
    assert [entry.run_id for entry in prepared] == [first.run_id], capsys.readouterr().out
    assert prepared[0].status is RunStatus.SUBMITTED and prepared[0].restart is None
    archives = list((output.parent / "archive").glob("*/old.txt"))
    assert len(archives) == 1 and archives[0].read_bytes() == b"interrupted outputs"
    archived_rows = [
        row
        for path in (workspace.root / "archive").glob("runs-*.json")
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]
    assert any(
        row["run_id"] == first.run_id and row["status"] == "FAILED_MARKED" for row in archived_rows
    )


@pytest.mark.parametrize("earlier", [False, True])
def test_discard_precedes_post(tmp_path, earlier):
    """P0350-COLLECT-DISCARD (FR-400): post sees discarded records from this or an older pass."""
    workspace = clock_workspace(tmp_path)
    if earlier:
        collect_and_post(workspace, interval=0, assessor=converged)
    seen = []

    def post(ws, matrix):
        seen.append((matrix, [entry.status for entry in ws.read_manifest()]))

    collect_and_post(
        workspace,
        interval=0,
        assessor=converged,
        discard_walltime=True,
        post_matrix=post,
    )
    assert seen == [("mtx", [RunStatus.FAILED_MARKED, RunStatus.CONVERGED])]


def test_watch_discards_after_each_pass(tmp_path):
    """P0350-COLLECT-DISCARD (FR-400): every watch pass discards newly stopped records."""
    workspace = clock_workspace(tmp_path)
    waiting = record("camp/sim_2006/waiting", status=RunStatus.SUBMITTED).model_copy(
        update={"submission": {"declared_outputs": ["never.txt"]}}
    )
    workspace.append_record(waiting)
    waits = []

    def sleep(seconds):
        if seconds == 1:
            assert workspace.read_manifest()[0].status is RunStatus.FAILED_MARKED
            waits.append(seconds)
            workspace.append_record(record("camp/sim_2006/later"))

    report = collect_and_post(
        workspace,
        interval=0,
        assessor=converged,
        discard_walltime=True,
        watch=True,
        rounds=2,
        watch_interval=1,
        sleep=sleep,
    )
    assert waits == [1]
    assert [entry.run_id for entry in report.discarded] == [
        "camp/sim_2006/AL+000",
        "camp/sim_2006/later",
    ]
    assert workspace.read_manifest()[-1].status is RunStatus.FAILED_MARKED


def test_help_explains_default_mode_rerun(capsys):
    """P0350-COLLECT-DISCARD (FR-400): help names the switch and both rerun modes."""
    with pytest.raises(SystemExit) as stop:
        main(["collect", "--help"])
    assert stop.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--discard-walltime" in out
    assert "a default-mode plan needs --force-rerun" in out
    assert "A grouped plan takes it again from the start automatically" in out
