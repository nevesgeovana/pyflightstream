# GEOVERSE_HEADER
# file_version: 1.0.2
# last_modified_at: 2026-09-27T20:59:34.951Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.run.matrix, pyflightstream.run.collect]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""An extraction stays pending until its own output files are collected."""

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
