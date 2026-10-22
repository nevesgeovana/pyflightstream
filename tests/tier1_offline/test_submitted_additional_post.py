"""An extraction stays pending until its own output files are collected."""

from types import SimpleNamespace

from pyflightstream.run import ExecutorConfigurationError
from pyflightstream.run.collect import collect_once
from tests.tier1_offline.test_additional_post import a_recorded_campaign, a_stub, extract
from tests.tier1_offline.test_matrix_run import CountingStub


class Scheduler(CountingStub):
    def __init__(self):
        super().__init__("pass")
        self.bound = []

    def bind_point(self, values, *, replace=False):
        self.bound.append(dict(values))

    def submission_record(self):
        return {"submitted": True, "scheduler_id": "fake-23"}


def test_submitted_extraction_waits_then_collects_without_mutating_original(tmp_path):
    # GOAL033:post:checks:submitted_collection
    # GOAL033:logging:checks:collection
    # GOAL033:capability_ids:items:G23
    workspace, matrix = a_recorded_campaign(tmp_path, values="0.0")
    original_manifest = workspace.manifest_path.read_bytes()
    scheduler = Scheduler()
    try:
        _, records = extract(workspace, matrix, scheduler)
    except ExecutorConfigurationError as error:
        raise AssertionError(f"submitted additional post remains refused: {error}") from error
    record = records[0]
    plans, repeated = extract(workspace, matrix, scheduler)
    assert repeated == [] and len(scheduler.invocations) == 1
    assert [plan.reason for plan in plans] == ["EXTRACTION_SUBMITTED"]
    assert record.status == "SUBMITTED"
    assert record.declared_outputs and not record.outputs
    assert scheduler.bound[0]["sim"] == record.sim_id
    folder = workspace.sim_dir(record.sim_id) / record.working_dir
    copies = list(folder.glob("*.reopened.fsm"))
    assert len(copies) == 1
    waiting = collect_once(workspace, interval=0, sleep=lambda _: None)
    assert len(waiting.waiting) == 1 and not waiting.collected
    a_stub(tmp_path).run_script(
        workspace.sim_dir(record.sim_id) / record.script_path, working_dir=folder
    )
    report = collect_once(workspace, interval=0, sleep=lambda _: None)
    assert len(report.collected) == 1 and not report.failed
    completed = workspace.read_additional()[-1]
    assert completed.status == "EXTRACTED"
    assert completed.outputs and completed.outputs_sha256
    assert not copies[0].exists()
    assert workspace.manifest_path.read_bytes() == original_manifest
    again = collect_once(workspace, interval=0, sleep=lambda _: None)
    assert not again.collected and not again.waiting

    import json

    events = [
        json.loads(line)
        for line in (workspace.root / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    observed = [event for event in events if event["stage"] == "collection"]
    assert {event["event"] for event in observed} >= {"started", "finished"}
    assert all(event["duration_s"] >= 0 for event in observed if event["event"] == "finished")


def test_a_translation_problem_refuses_the_extraction_and_keeps_the_copy(tmp_path, monkeypatch):
    """Q0 CX-4: an existing .dat whose provenance changed is not an extraction.

    The translation reports the problem; collection checked only that the
    declared files existed, recorded EXTRACTED and deleted the private copy.
    """
    # 0.40.0 (PFS-2103.008): the completion is the one the local path shares
    # (run._additional); the refusal is recorded FAILED_EXECUTION there.
    from pyflightstream.run import _additional
    from pyflightstream.workspace import ExtractionStatus

    sim_dir = tmp_path / "sim"
    folder = sim_dir / "work"
    folder.mkdir(parents=True)
    (folder / "surface.dat").write_text("stale", encoding="utf-8")
    from tests.tier1_offline.test_regression_results_readers import (
        _RESULTS_SURFACE__TRANSLATIONS as TRANSLATIONS,
    )
    from tests.tier1_offline.test_regression_results_readers import _RESULTS_SURFACE__VTK as VTK

    (folder / "surface.vtk").write_text(VTK, encoding="utf-8")
    copy = folder / "point.reopened.fsm"
    copy.write_text("private copy", encoding="utf-8")
    record = SimpleNamespace(
        surface_translations=TRANSLATIONS,
        declared_outputs=["surface.dat"],
        model_dump=lambda: {"sim_id": "1"},
    )
    problem = "surface.dat is preserved: source, frame or output provenance changed"
    monkeypatch.setattr(
        _additional,
        "translate_surface_exports",
        lambda where, translations: [{**translations[0], "written": [], "problems": [problem]}],
    )
    recorded = []
    monkeypatch.setattr(
        _additional,
        "record_additional_extraction",
        lambda workspace, base, **kw: (
            recorded.append(kw) or SimpleNamespace(status=kw["status"], outputs=[])
        ),
    )
    workspace = SimpleNamespace(sim_dir=lambda sim_id: sim_dir)
    _additional.finish_extraction(workspace, record, (sim_dir, folder, tmp_path / "o.fsm", copy))
    assert [kw["status"] for kw in recorded] == [ExtractionStatus.FAILED_EXECUTION], recorded
    assert "provenance changed" in recorded[0]["error"]
    assert copy.is_file(), "the private simulation copy was deleted after a failed translation"


def test_submitted_is_documented_as_pending_and_not_a_workspace_attribute():
    """Q0-src-workspace-2 (a)(b): a stray class attribute and a wrong doc comment."""
    import ast
    import pathlib

    from pyflightstream.workspace import CampaignWorkspace, ExtractionStatus, manifest

    assert "SUBMITTED" not in vars(CampaignWorkspace)
    # The class keeps its public module (pyflightstream.workspace, AD-15) while it is defined in
    # workspace/manifest.py, so inspect.getsource cannot find it on Python 3.12: read it here.
    text = pathlib.Path(manifest.__file__).read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.parse(text).body
        if isinstance(n, ast.ClassDef) and n.name == "ExtractionStatus"
    )
    source = ast.get_source_segment(text, node) or ""
    before_submitted = source.split('SUBMITTED = "SUBMITTED"', 1)[0].rstrip().splitlines()[-1]
    assert "written and hashed" not in before_submitted
    assert "written and hashed" in source.split('EXTRACTED = "EXTRACTED"', 1)[0].splitlines()[-2]
    assert "Terminal status" not in (ExtractionStatus.__doc__ or "")


def test_p0430_x_f_0548_a_placeholder_an_extraction_cannot_fill_is_a_refusal(tmp_path, monkeypatch):
    """X-F-0548: a valid profile placeholder outside {sim} and {point} refuses, never a KeyError."""
    import pytest

    from pyflightstream.run import _additional
    from pyflightstream.workspace import WorkspaceError

    profile = SimpleNamespace(job_end_files=("{work_dir}/done.*",), native_log=None)
    monkeypatch.setattr(_additional, "resolve_hpc_profile", lambda _inputs: profile)
    workspace = SimpleNamespace(inputs_dir=tmp_path)
    record = SimpleNamespace(point_name="p", sim_id="2001", submission={})
    with pytest.raises(WorkspaceError, match="work_dir"):
        _additional.extraction_job_end(workspace, record, tmp_path)


def test_x_f_0556_a_retry_in_the_same_second_keeps_the_earlier_extraction_archive(tmp_path):
    """The folder archive never overwrites files of an archive with the same stamp."""
    from pyflightstream.run._additional import ARCHIVE_DIR, _archive_extraction_folder

    folder = tmp_path / "extraction"
    folder.mkdir()
    (folder / "forces.csv").write_text("first", encoding="utf-8")
    _archive_extraction_folder(folder, "r20261021-120000")
    (folder / "forces.csv").write_text("second", encoding="utf-8")
    _archive_extraction_folder(folder, "r20261021-120000")
    archive = folder / ARCHIVE_DIR
    assert (archive / "r20261021-120000" / "forces.csv").read_text(encoding="utf-8") == "first"
    assert (archive / "r20261021-120000.2" / "forces.csv").read_text(encoding="utf-8") == "second"
    assert [child.name for child in folder.iterdir()] == [ARCHIVE_DIR]


def test_last_a_file_error_while_completing_an_extraction_is_retried(tmp_path, monkeypatch):
    """X-F-0569: a transient OSError recorded a final FAILED_EXECUTION that no sweep revisits."""
    from pyflightstream.run import collect as collect_module

    workspace, matrix = a_recorded_campaign(tmp_path, values="0.0")
    scheduler = Scheduler()
    _, records = extract(workspace, matrix, scheduler)
    record = records[0]
    folder = workspace.sim_dir(record.sim_id) / record.working_dir
    a_stub(tmp_path).run_script(
        workspace.sim_dir(record.sim_id) / record.script_path, working_dir=folder
    )
    real = collect_module.finish_extraction
    calls = []

    def locked(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("the output is held open by another process")
        return real(*args, **kwargs)

    monkeypatch.setattr(collect_module, "finish_extraction", locked)
    first = collect_once(workspace, interval=0, sleep=lambda _: None)
    assert not first.failed and not first.collected
    assert len(first.waiting) == 1 and "file error" in first.waiting[0].detail
    assert workspace.read_additional()[-1].status == "SUBMITTED"
    second = collect_once(workspace, interval=0, sleep=lambda _: None)
    assert len(second.collected) == 1 and not second.failed
    assert workspace.read_additional()[-1].status == "EXTRACTED"
