# GEOVERSE_HEADER
# file_version: 1.0.1
# file_role: activity-failure-reporting-regressions
# last_modified_at: 2026-09-27T20:59:34.947Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pytest, pyflightstream._progress]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
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
