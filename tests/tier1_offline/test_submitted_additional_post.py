"""An extraction stays pending until its own output files are collected."""

from types import SimpleNamespace

import pytest

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
    _, repeated = extract(workspace, matrix, scheduler)
    assert repeated[0].status == "SUBMITTED" and len(scheduler.invocations) == 1
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
    import pyflightstream.run.collect as collect
    import pyflightstream.run.matrix as run_matrix
    from pyflightstream.workspace import ExtractionStatus, WorkspaceError

    sim_dir = tmp_path / "sim"
    folder = sim_dir / "work"
    folder.mkdir(parents=True)
    (folder / "surface.dat").write_text("stale", encoding="utf-8")
    copy = folder / "point.reopened.fsm"
    copy.write_text("private copy", encoding="utf-8")
    record = SimpleNamespace(
        surface_translations=[{"vtk": "surface.vtk", "dat": "surface.dat"}],
        declared_outputs=["surface.dat"],
        model_dump=lambda: {},
    )
    problem = "surface.dat is preserved: source, frame or output provenance changed"
    monkeypatch.setattr(
        collect,
        "translate_surface_exports",
        lambda where, translations: [{**translations[0], "written": [], "problems": [problem]}],
    )
    recorded = []
    monkeypatch.setattr(
        run_matrix,
        "record_additional_extraction",
        lambda workspace, base, **kw: (
            recorded.append(kw)
            or SimpleNamespace(status=ExtractionStatus.EXTRACTED, outputs=kw["outputs"])
        ),
    )
    with pytest.raises(WorkspaceError, match="provenance changed"):
        collect._finish_additional(None, record, (sim_dir, folder, tmp_path / "o.fsm", copy))
    assert not recorded, "a failed translation was recorded as an extraction"
    assert copy.is_file(), "the private simulation copy was deleted after a failed translation"


def test_submitted_is_documented_as_pending_and_not_a_workspace_attribute():
    """Q0-src-workspace-2 (a)(b): a stray class attribute and a wrong doc comment."""
    import inspect

    from pyflightstream.workspace import CampaignWorkspace, ExtractionStatus

    assert "SUBMITTED" not in vars(CampaignWorkspace)
    source = inspect.getsource(ExtractionStatus)
    before_submitted = source.split('SUBMITTED = "SUBMITTED"', 1)[0].rstrip().splitlines()[-1]
    assert "written and hashed" not in before_submitted
    assert "written and hashed" in source.split('EXTRACTED = "EXTRACTED"', 1)[0].splitlines()[-2]
    assert "Terminal status" not in (ExtractionStatus.__doc__ or "")
