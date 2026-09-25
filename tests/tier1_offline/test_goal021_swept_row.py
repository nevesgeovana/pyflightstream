"""PFS-2010.01.02: a swept row submits every point, each in its own datapoint folder.

On v0.18.0 a swept `unsteady_rotor` row submitted its first point and refused
the rest FAILED_SCRIPT, because every point of the row shared the simulation
folder's action program, export script and clock state, and a submission does
not wait. Each submitted point now runs in `sims/sim_<id>/datapoints/DP-<tag>/`,
the folder its outputs are filed under since 0.16.0, and the files that used to
be shared follow it.

Proved against a submitting executor that writes its descriptor and calls no
scheduler, and a fake solver that writes into each point's working directory.
Whether it holds on a real cluster is the owner's to run.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import CampaignErrors, SubmittingExecutor
from pyflightstream.run.collect import collect_once
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import PointName, RunRecord, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_goal021_inputs_absolute import BUILD, _rotor_row, _workspace
from tests.tier1_offline.test_matrix_run import (
    HPC_PROFILE,
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    StubSolver,
    _steady_sweep_matrix,
    converged,
)

TAGS = ("V0300RE120AL+000", "V0300RE120AL+020", "V0300RE120AL+040")


def _submitting(workspace, build=BUILD, text=HPC_PROFILE):
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(text, encoding="utf-8")
    return SubmittingExecutor(read_hpc_profile(profile), values={"fs_build": build}, submit=False)


def _run(workspace, matrix, executor, *, name="rotor", **extra):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return run_matrix(
            matrix,
            workspace,
            name=name,
            recipes=extra.pop("recipes", {}),
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=executor,
            **extra,
        )


def _submitted_row(tmp_path):
    workspace = _workspace(tmp_path)
    # THE EXPORT WINDOW MAKES THE ROW WRITE ITS ACTION PROGRAM, and the wall
    # clock its clock: the two files the old refusal named as shared.
    row = _rotor_row(tmp_path, extra=" / EXPORT_UNSTEADY_AFTER_REV: 1")
    records = _run(workspace, row, _submitting(workspace))
    return workspace, records


def test_goal021_swept_row_every_point_is_submitted(tmp_path):
    """The headline: three points SUBMITTED, where 0.18.0 submitted one."""
    _, records = _submitted_row(tmp_path)
    assert [record.status for record in records] == [RunStatus.SUBMITTED] * 3, [
        (record.run_id, record.status, record.error) for record in records
    ]


def test_g43_a_run_that_submits_does_not_post(tmp_path, capsys):
    """G43 of 0.28.0: a run that submits to a scheduler does not post.
    Points in a queue have no outputs yet, so the post could only print a skip per point:
    the run writes no product and no table, and one line says what was submitted and the
    command that collects and then posts."""
    capsys.readouterr()
    workspace, records = _submitted_row(tmp_path)
    assert [record.status for record in records] == [RunStatus.SUBMITTED] * 3
    said = capsys.readouterr().err
    assert "submitted 3 point(s) to the scheduler and ran 0 here" in said, said
    assert f"pyfs-matrix collect --workspace {workspace.root}" in said, said
    post = workspace.root / "post"
    written = (
        sorted(p.relative_to(post).as_posix() for p in post.rglob("*.csv")) if post.exists() else []
    )
    assert written == [], f"the run posted: {written}"


def test_g43_a_point_the_scheduler_refuses_did_not_run_here(tmp_path, capsys):
    """A submission the scheduler refuses is neither queued nor run on this machine: the
    closing line says submitted 2, ran 0 here and 1 failed before the scheduler took it,
    never "ran 1 here" (reading A29)."""
    import dataclasses

    workspace = _workspace(tmp_path)
    row = _rotor_row(tmp_path, extra=" / EXPORT_UNSTEADY_AFTER_REV: 1")
    real = _submitting(workspace)

    class RefusesTheSecond(SubmittingExecutor):
        calls = 0

        def run_script(self, script_path, working_dir, timeout_s=None):
            result = super().run_script(script_path, working_dir, timeout_s)
            RefusesTheSecond.calls += 1
            if RefusesTheSecond.calls == 2:
                return dataclasses.replace(result, return_code=1, stderr="refused by the stand-in")
            return result

    executor = RefusesTheSecond(real.profile, values=dict(real.values), submit=False)
    capsys.readouterr()
    with pytest.raises(CampaignErrors):
        _run(workspace, row, executor)
    said = capsys.readouterr().err
    assert "submitted 2 point(s) to the scheduler and ran 0 here" in said, said
    assert "1 failed before they ran" in said, said


def test_goal021_swept_row_each_point_runs_in_its_own_datapoint_folder(tmp_path):
    workspace, records = _submitted_row(tmp_path)
    sim = workspace.sim_dir("7001")
    for record, tag in zip(records, TAGS, strict=True):
        folder = sim / "datapoints" / f"DP-{tag}"
        assert Path(record.cwd) == folder, (record.run_id, record.cwd)
        assert record.submission["working_dir"] == f"datapoints/DP-{tag}", record.submission
        descriptor = Path(record.submission["descriptor"])
        assert descriptor.parent == folder, descriptor
        text = descriptor.read_text(encoding="utf-8")
        assert text.count(f'workdir: "{folder.as_posix()}"') == 1, text
    assert not (sim / "submit.yaml").exists(), "a descriptor was still written to the shared folder"


def test_goal021_swept_row_the_files_that_were_shared_are_each_points_own(tmp_path):
    """The refusal's own stated cause: the action program and the clock state."""
    workspace, _ = _submitted_row(tmp_path)
    sim = workspace.sim_dir("7001")
    for tag in TAGS:
        actions = sim / "datapoints" / f"DP-{tag}" / "actions"
        exports = (actions / "pfs_unsteady_actions.py").read_text(encoding="utf-8")
        stop = (actions / "pfs_walltime_clock.py").read_text(encoding="utf-8")
        assert exports.count(f"{tag}.txt") >= 1, f"{tag}'s action program exports another point"
        assert stop.count(f"{tag}.txt") >= 1, f"{tag}'s clock stops under another point's names"
        other = [t for t in TAGS if t != tag]
        assert not any(f"{name}.txt" in exports for name in other), exports
    assert not (sim / "actions").exists(), "the shared action folder is still written"


def test_goal021_swept_row_collect_files_each_point_in_place(tmp_path):
    """The collector waits in each point's folder and files its outputs there."""
    workspace, records = _submitted_row(tmp_path)
    sim = workspace.sim_dir("7001")
    for record, tag in zip(records, TAGS, strict=True):
        folder = sim / "datapoints" / f"DP-{tag}"
        for name in record.submission["declared_outputs"]:
            (folder / name).write_text(f"written by the job of {tag}", encoding="utf-8")

    def accept(record, _sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(workspace, interval=0.0, sleep=lambda _s: None, assessor=accept)
    assert len(report.collected) == 3, report.lines()
    completed = {record.run_id: record for record in workspace.read_manifest()}
    for tag in TAGS:
        record = completed[f"rotor/sim_7001/{tag}"]
        assert record.status is RunStatus.CONVERGED, record.status
        assert record.outputs, record
        assert all(name.startswith(f"datapoints/DP-{tag}/") for name in record.outputs), (
            record.outputs
        )
        for name in record.outputs:
            assert (sim / name).read_text(encoding="utf-8") == f"written by the job of {tag}"


def test_goal021_swept_row_collect_still_refuses_another_points_folder(tmp_path):
    """In place means THIS point's folder; a file in a sibling's folder is not its evidence."""
    from pyflightstream.workspace import WorkspaceError

    workspace, records = _submitted_row(tmp_path)
    sim = workspace.sim_dir("7001")
    sibling = sim / "datapoints" / "DP-V0300RE120AL+020" / "stray.txt"
    sibling.write_text("not V0300RE120AL+000's", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        workspace.collect_outputs("7001", [sibling], datapoint=PointName("V0300RE120AL+000"))
    assert sibling.is_file(), "a refused collection moved the file anyway"


def test_goal021_swept_row_a_second_submission_in_the_same_invocation_is_not_refused(tmp_path):
    """The hold lifted on this path: no record carries the old refusal."""
    _, records = _submitted_row(tmp_path)
    assert not [r for r in records if r.error and "already has" in r.error], [
        r.error for r in records
    ]


def test_goal021_swept_row_a_local_point_runs_in_its_datapoint_folder(tmp_path):
    """0.27.0: a local point runs where a submitted one does, its own datapoint folder.

    It ran in the simulation folder until then, and a point whose run or
    collection failed left its exports in the folder every point shares.
    """
    workspace = _workspace(tmp_path)
    stub = CountingStub(WRITES_EVERY_EXPORT)
    try:
        records = _run(workspace, _rotor_row(tmp_path, sweep="0.0"), stub)
    except CampaignErrors:
        records = workspace.read_manifest()
    assert records, "the local run recorded nothing"
    folder = workspace.sim_dir("7001") / "datapoints" / f"DP-{records[0].point_name}"
    assert Path(records[0].cwd) == folder, records[0].cwd


def test_goal021_swept_row_the_steady_job_still_runs_in_the_simulation_folder(tmp_path):
    """The swept-steady path is ONE job over its row, and keeps its folder and its refusal."""
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    records = _run(
        workspace,
        matrix,
        # A steady row states no wall clock and no processor count, so the
        # profile asks for neither.
        _submitting(
            workspace,
            build="26.120",
            text="\n".join(
                line
                for line in HPC_PROFILE.splitlines()
                if not line.startswith(("walltime ", "ncpus "))
            )
            + "\n",
        ),
        name="warm",
        recipes=RECIPES,
        default_fs_version="26.120",
    )
    assert len(records) == 1 and records[0].status is RunStatus.SUBMITTED, records
    assert Path(records[0].cwd) == workspace.sim_dir("5001"), records[0].cwd
    assert Path(records[0].submission["descriptor"]).parent == workspace.sim_dir("5001")


#: Where a stopped run of 0.28.0 records its loads frame, here the reference
#: frame at the origin. A continuation writes its Tecplot in that frame, and
#: one of a run that recorded none is refused (G45; test_ghmain0280_c32).
REFERENCE_TRANSLATION = {
    "vtk": "V0300RE120AL+000.vtk",
    "dat": "V0300RE120AL+000.dat",
    "frame": {
        "frame": 1,
        "origin": [0.0, 0.0, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    },
}


def _stopped(workspace, tag="V0300RE120AL+000"):
    folder = workspace.sim_dir("7001") / "datapoints" / f"DP-{tag}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{tag}.fsm").write_text("a stopped march", encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id=f"rotor/sim_7001/{tag}",
            sim_id="7001",
            point={"alpha": 0.0},
            status=RunStatus.WALLTIME_REACHED,
            matrix_stem="rotor",
            fs_version_requested=BUILD,
            package_version="0.28.0",
            script_sha256="c" * 64,
            raw_flag=False,
            outputs=[f"datapoints/DP-{tag}/{tag}.fsm"],
            export_window={"time_iterations": 720},
            stopped_at={"step": 250},
            surface_translations=[REFERENCE_TRANSLATION],
        )
    )


def _restart_row(tmp_path):
    return _rotor_row(tmp_path, sweep="0.0", extra=" / RESTART: {FINISH_PENDING}")


def test_goal021_swept_row_restart_runs_under_the_campaign_that_recorded_the_stop(tmp_path):
    """The owner's call: 0.18.0 refused this row as a fork, or skipped it as done."""
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    records = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert len(records) == 1, [(r.run_id, r.status, r.error) for r in records]
    assert "/r" in records[0].run_id and records[0].run_id.endswith("/V0300RE120AL+000"), records[
        0
    ].run_id
    assert records[0].status is RunStatus.SUBMITTED, (records[0].status, records[0].error)


def test_goal021_swept_row_restart_opens_the_archived_copy_by_absolute_path(tmp_path):
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    records = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    script = workspace.sim_dir("7001") / records[0].script_path
    lines = script.read_text(encoding="utf-8").splitlines()
    opened = lines[lines.index("OPEN") + 1]
    assert Path(opened).is_absolute(), opened
    assert Path(opened).is_file(), f"the continuation opens {opened}, which does not exist"
    assert "archive" in Path(opened).parts, opened


def test_goal021_swept_row_a_finished_continuation_is_not_continued_again(tmp_path):
    """Running the matrix again after the continuation completed runs nothing."""
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    submitted = workspace.read_manifest()[-1]
    workspace.complete_submitted_record(
        submitted.model_copy(update={"status": RunStatus.CONVERGED})
    )
    again = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert again == [], [(r.run_id, r.status) for r in again]


def _failed_continuation(tmp_path):
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    submitted = workspace.read_manifest()[-1]
    workspace.complete_submitted_record(
        submitted.model_copy(update={"status": RunStatus.FAILED_EXECUTION})
    )
    return workspace


def test_goal021_swept_row_a_failed_continuation_is_refused_by_name_not_skipped(tmp_path):
    """The quality and V&V lenses, closing round: it returned [] and said nothing."""
    from pyflightstream.cases.matrix import MatrixError

    workspace = _failed_continuation(tmp_path)
    before = len(workspace.read_manifest())
    # THE PRE-FLIGHT REFUSES IT, naming the failed run, before anything runs.
    with pytest.raises(MatrixError) as raised:
        _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    message = str(raised.value)
    assert message.count("as FAILED_EXECUTION") == 1, message
    assert message.count("A failed continuation is not retried") == 1, message
    assert len(workspace.read_manifest()) == before, "a refused point still recorded a run"


def test_goal021_swept_row_plan_reports_a_failed_continuation_as_blocked(tmp_path):
    from pyflightstream.run import PlanStatus
    from pyflightstream.run.matrix import plan_matrix

    workspace = _failed_continuation(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_matrix(
            _restart_row(tmp_path),
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
    statuses = [point.status for point in plan.points]
    assert statuses == [PlanStatus.BLOCKED], statuses
    assert plan.points[0].error.count("A failed continuation is not retried") == 1


def test_goal021_swept_row_a_point_is_not_submitted_over_its_own_leftover_output(tmp_path):
    """The interface lens: in-place collection is safe only if no leftover can be claimed."""
    workspace = _workspace(tmp_path)
    folder = workspace.sim_dir("7001") / "datapoints" / "DP-V0300RE120AL+000"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "V0300RE120AL+000.txt").write_text("an earlier run's evidence", encoding="utf-8")
    with pytest.raises(CampaignErrors):
        _run(workspace, _rotor_row(tmp_path, sweep="0.0"), _submitting(workspace))
    record = workspace.read_manifest()[-1]
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, record.status
    assert record.error.count("V0300RE120AL+000.txt") == 1, record.error
    assert not (folder / "submit.yaml").exists(), "the point was handed to the scheduler anyway"


def test_goal021_swept_row_a_working_dir_outside_the_datapoints_is_refused(tmp_path):
    """The architecture and interface lenses: the field comes from a file someone can edit."""
    workspace, records = _submitted_row(tmp_path)
    first = records[0]
    submission = {**first.submission, "working_dir": "../../../elsewhere"}
    workspace.complete_submitted_record(first.model_copy(update={"submission": submission}))
    report = collect_once(workspace, interval=0.0, sleep=lambda _s: None)
    failed = [o for o in report.failed if o.run_id == first.run_id]
    assert len(failed) == 1, report.lines()
    assert failed[0].detail.count("does not resolve to a datapoint folder") == 1, failed[0].detail


def _files_of(folder):
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("executor", ["submitting", "local"])
def test_goal021_swept_row_a_queued_point_is_not_submitted_again_under_another_campaign(
    tmp_path, executor
):
    """The independent reviews: the folder carries no campaign name, so the job was clobbered,
    through the point's folder (a submission, then 9o: a local run) and through the
    simulation's staged inputs, which are prepared before any point. A simulation holds one
    campaign's queued work: refused before anything is prepared, whatever the executor."""
    from pyflightstream.exceptions import WorkspaceError

    workspace, records = _submitted_row(tmp_path)
    sim = workspace.sim_dir("7001")
    before = _files_of(sim)
    manifest_before = [record.run_id for record in workspace.read_manifest()]
    row = _rotor_row(tmp_path, sweep="0.0", extra=" / EXPORT_UNSTEADY_AFTER_REV: 1")
    runner = _submitting(workspace) if executor == "submitting" else StubSolver(WRITES_EVERY_EXPORT)
    with pytest.raises(
        WorkspaceError, match=r"holds another campaign's work in a scheduler's queue"
    ):
        _run(workspace, row, runner, name="another")
    assert [record.run_id for record in workspace.read_manifest()] == manifest_before
    assert _files_of(sim) == before, "the queued job's folder was written by the refused campaign"


def test_goal021_swept_row_a_new_point_does_not_restage_under_a_queued_job(tmp_path):
    """The independent reading 9p: the same campaign adds a point to a simulation whose
    other points are still queued, after the geometry changed. Staging would replace the
    copy the queued jobs open when they start, under the digests their records keep; the
    staged-input check read only the recorded points of the new request, which named none.
    Refused before anything is prepared, naming the queued job."""
    from pyflightstream.exceptions import WorkspaceError

    workspace, records = _submitted_row(tmp_path)
    (geometry,) = (workspace.inputs_dir / "geometries").rglob("wing_clean.fsm")
    geometry.write_bytes(geometry.read_bytes() + b"\n")
    manifest_before = [record.run_id for record in workspace.read_manifest()]
    row = _rotor_row(tmp_path, sweep="6.0", extra=" / EXPORT_UNSTEADY_AFTER_REV: 1")
    with pytest.raises(WorkspaceError, match=r"still in a scheduler's queue") as refused:
        _run(workspace, row, StubSolver(WRITES_EVERY_EXPORT))
    assert any(record.run_id in str(refused.value) for record in records), refused.value
    assert [record.run_id for record in workspace.read_manifest()] == manifest_before


def test_goal021_swept_row_staging_does_not_retarget_the_inputs_of_a_queued_job(tmp_path):
    """The independent reading 9r: the queued points were staged from the library's own
    folder, and a new row of the same campaign and simulation names a geometry kept in its
    own folder (geometries/wing_other/). Staging would re-point the inputs junction there,
    swapping every file the queued jobs open, whatever its name. Refused before anything
    is prepared; the inputs folder presents what it did."""
    from pyflightstream.exceptions import WorkspaceError

    workspace, records = _submitted_row(tmp_path)
    inputs = workspace.sim_dir("7001") / "inputs"
    (geometry,) = (workspace.inputs_dir / "geometries").rglob("wing_clean.fsm")
    other = workspace.inputs_dir / "geometries" / "wing_other" / "wing_other.fsm"
    other.parent.mkdir()
    other.write_bytes(geometry.read_bytes())
    presented = (inputs.resolve(), _files_of(inputs))
    manifest_before = [record.run_id for record in workspace.read_manifest()]
    row = _rotor_row(tmp_path, sweep="6.0", extra=" / EXPORT_UNSTEADY_AFTER_REV: 1")
    row.write_text(
        row.read_text(encoding="utf-8").replace("wing_clean.fsm", "wing_other.fsm"),
        encoding="utf-8",
    )
    with pytest.raises(WorkspaceError, match=r"opens this simulation's inputs"):
        _run(workspace, row, StubSolver(WRITES_EVERY_EXPORT))
    assert [record.run_id for record in workspace.read_manifest()] == manifest_before
    assert (inputs.resolve(), _files_of(inputs)) == presented, "the queued jobs' inputs changed"
    # The dry run itself: the geometry the queued points staged changes nothing.
    assert workspace.staging_would_change("7001", [geometry]) is None
    assert workspace.staging_would_change("7001", [other]) is not None


@pytest.mark.parametrize("spelling", ["wing.fsm", "WING.FSM", "Wing.Fsm"])
def test_goal021_swept_row_the_staged_input_check_reads_the_name_the_file_system_sees(
    tmp_path, spelling
):
    """The independent reading 9q: the record keys the queued point's geometry as
    `wing.fsm`, and a new point names a revised source `WING.FSM`, which staging writes
    onto the same file on Windows. The digest is found by the folded name, so the new
    spelling is refused as the old one is; the same bytes under any spelling are not."""
    from types import SimpleNamespace

    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.run import _staged_inputs_conflict

    source = tmp_path / "models" / spelling
    source.parent.mkdir()
    source.write_bytes(b"the revised geometry")
    queued = RunRecord.model_construct(
        run_id="camp/sim_9001/AL+000",
        sim_id="9001",
        status=RunStatus.SUBMITTED,
        inputs_sha256={"wing.fsm": "0" * 64},
    )
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[2.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
        geometry=str(source),
    )
    manifest = {queued.run_id: queued}
    campaign = SimpleNamespace(name="camp")
    refusal = _staged_inputs_conflict(
        campaign, case, None, manifest, [queued.run_id], {queued.run_id}
    )
    assert refusal is not None and "still in a scheduler's queue" in refusal, refusal

    from pyflightstream._digest import file_sha256

    same = queued.model_copy(update={"inputs_sha256": {"wing.fsm": file_sha256(source)}})
    assert (
        _staged_inputs_conflict(
            campaign, case, None, {same.run_id: same}, [same.run_id], {same.run_id}
        )
        is None
    )


def test_goal021_swept_row_a_queued_point_is_not_force_rerun(tmp_path):
    """A point of the same campaign still in a queue: redoing it would archive the record its
    job will be collected into and write where the job writes. Refused, nothing archived."""
    from pyflightstream.exceptions import WorkspaceError

    workspace, records = _submitted_row(tmp_path)
    sim = workspace.sim_dir("7001")
    before = _files_of(sim)
    manifest_before = [record.run_id for record in workspace.read_manifest()]
    row = _rotor_row(tmp_path, extra=" / EXPORT_UNSTEADY_AFTER_REV: 1")
    with pytest.raises(WorkspaceError, match=r"still in a scheduler's queue"):
        _run(
            workspace,
            row,
            StubSolver(WRITES_EVERY_EXPORT),
            force_rerun=[records[0].run_id],
        )
    assert [record.run_id for record in workspace.read_manifest()] == manifest_before
    assert not list((workspace.root / "archive").glob("runs-*.json")), "the manifest was archived"
    assert _files_of(sim) == before


def test_goal021_swept_row_an_output_in_a_subfolder_of_the_point_is_collected(tmp_path):
    workspace, _ = _submitted_row(tmp_path)
    folder = workspace.sim_dir("7001") / "datapoints" / "DP-V0300RE120AL+000"
    (folder / "out").mkdir()
    (folder / "out" / "loads.txt").write_text("written in a subfolder", encoding="utf-8")
    collected = workspace.collect_outputs(
        "7001",
        [folder / "out" / "loads.txt"],
        datapoint=PointName("V0300RE120AL+000"),
        ran_in_datapoint=True,
    )
    assert collected == ["datapoints/DP-V0300RE120AL+000/loads.txt"], collected
    assert (folder / "loads.txt").read_text(encoding="utf-8") == "written in a subfolder"


def test_goal021_swept_row_an_archived_file_is_never_collected_in_place(tmp_path):
    from pyflightstream.workspace import WorkspaceError

    workspace, _ = _submitted_row(tmp_path)
    folder = workspace.sim_dir("7001") / "datapoints" / "DP-V0300RE120AL+000"
    archived = folder / "archive" / "20260914-100000" / "loads.txt"
    archived.parent.mkdir(parents=True)
    archived.write_text("an earlier run's evidence", encoding="utf-8")
    with pytest.raises(WorkspaceError):
        workspace.collect_outputs(
            "7001", [archived], datapoint=PointName("V0300RE120AL+000"), ran_in_datapoint=True
        )
    assert archived.is_file()
