# GEOVERSE_HEADER
# file_version: 1.1.0
# file_role: activity-failure-reporting-regressions
# last_modified_at: 2026-09-27T23:30:53.667Z
# last_modified_by: OpenAI / Codex / unknown / qa-proposal
# dependencies: [pytest, pyflightstream._progress]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Preserve failed CollectReport results and their actionable diagnostic.
# revision_source: git
"""Diagnostic storage failures must not replace the operational failure."""

from types import SimpleNamespace

import pytest

import pyflightstream._progress as progress


def test_error_log_failure_preserves_original_exception(tmp_path, monkeypatch, capsys):
    # GOAL033:logging:checks:actionable_errors
    calls = []

    def event(*args, **kwargs):
        calls.append(args)
        if len(calls) > 1:
            raise OSError("diagnostic disk full")

    monkeypatch.setattr(progress, "activity_event", event)

    @progress.workspace_activity("run")
    def fail(workspace):
        raise ValueError("solver input rejected")

    with pytest.raises(ValueError, match="solver input rejected"):
        fail(tmp_path)
    stderr = capsys.readouterr().err
    assert "diagnostic disk full" in stderr
    assert "solver input rejected" in stderr


def test_failed_records_have_failed_final_stage(tmp_path, capsys):
    # GOAL033:logging:checks:final_outcome
    import json

    @progress.workspace_activity("collect")
    def collect(workspace):
        return [SimpleNamespace(status="FAILED_TIMEOUT")]

    result = collect(tmp_path)
    assert result[0].status == "FAILED_TIMEOUT"
    events = [
        json.loads(line) for line in (tmp_path / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    assert events[-1]["event"] == "failed"
    assert "[collect] failed" in capsys.readouterr().err


def test_failed_collect_report_is_returned_and_logged_without_diagnosis(tmp_path, capsys):
    import json

    from pyflightstream.run.collect import CollectOutcome, CollectReport

    report = CollectReport(
        failed=[CollectOutcome("9001/AL+000", "FAILED", "native log is missing: solver.log")]
    )

    @progress.workspace_activity("collection")
    def collect(workspace):
        return report

    assert collect(tmp_path) is report
    events = [
        json.loads(line) for line in (tmp_path / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    assert events[-1]["event"] == "failed"
    assert "9001/AL+000" in events[-1]["message"]
    assert "native log is missing: solver.log" in events[-1]["message"]
    assert "[collection] failed" in capsys.readouterr().err


def test_failed_execution_keeps_its_existing_diagnosis(tmp_path):
    import json

    from pyflightstream.run import ExecutionResult

    result = ExecutionResult(1, 0.1, False, "native parser rejected input", "stdout detail", "")

    @progress.workspace_activity("solver")
    def execute(workspace):
        return result

    assert execute(tmp_path) is result
    events = [
        json.loads(line) for line in (tmp_path / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    assert events[-1]["event"] == "failed"
    assert events[-1]["message"] == result.diagnosis()
