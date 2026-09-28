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


def test_additional_post_plans_and_records_report_the_failed_extraction(tmp_path):
    """Q0 CX-8: additional-post returns ``(plans, records)``.

    The decorator counted the top-level members of the tuple, two lists with no
    status, so a failed extraction logged ``finished`` with ``outcomes={}``.
    """
    import json

    plans = [SimpleNamespace(status="PLANNED")]
    records = [SimpleNamespace(status="FAILED_EXECUTION")]

    @progress.workspace_activity("additional-post")
    def extract(workspace):
        return plans, records

    assert extract(tmp_path) == (plans, records)
    events = [
        json.loads(line) for line in (tmp_path / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    assert events[-1]["event"] == "failed"
    assert events[-1]["outcomes"] == {"FAILED_EXECUTION": 1}


def _unwritable_log(monkeypatch):
    def event(*args, **kwargs):
        raise PermissionError("activity.log.jsonl is read-only")

    monkeypatch.setattr(progress, "activity_event", event)


def test_an_unwritable_log_does_not_replace_a_stage_result(tmp_path, monkeypatch, capsys):
    """Q0-src-other-1: "Log one stage without changing its result".

    The started and finished writes sat inside the stage's own try, so a log
    that could not be written stopped the stage before it ran, or turned a
    finished solver run into a PermissionError.
    """
    _unwritable_log(monkeypatch)
    ran = []

    @progress.workspace_activity("solver", "working_dir")
    def run_script(working_dir):
        ran.append(True)
        return "SOLVER-RESULT"

    assert run_script(tmp_path) == "SOLVER-RESULT"
    assert ran == [True]
    assert "could not persist diagnostic" in capsys.readouterr().err


def test_an_unwritable_log_does_not_stop_a_progress_line(tmp_path, capsys):
    """GOAL-034 Q8 CXQ8-1: the run's own progress line went to the unguarded
    writer, so an unwritable log still aborted a campaign, even when quiet.

    The log is made unwritable for real (a directory where the file goes), so
    the test does not depend on which name a module imported.
    """
    from pyflightstream.run import _say

    (tmp_path / "logs" / "activity.log.jsonl").mkdir(parents=True)

    @progress.workspace_activity("run")
    def stage(workspace):
        _say("point 1 of 1 done", quiet=True)
        return "STAGE-RESULT"

    assert stage(tmp_path) == "STAGE-RESULT"
    assert "could not persist diagnostic" in capsys.readouterr().err


def test_a_raising_diagnosis_does_not_replace_a_stage_result(tmp_path):
    import json

    class Report:
        failed = True

        def diagnosis(self):
            raise RuntimeError("report is malformed")

    report = Report()

    @progress.workspace_activity("collection")
    def collect(workspace):
        return report

    assert collect(tmp_path) is report
    events = [
        json.loads(line) for line in (tmp_path / "logs/activity.log.jsonl").read_text().splitlines()
    ]
    assert events[-1]["event"] == "failed"
    assert "diagnosis unavailable: report is malformed" in events[-1]["message"]


def test_an_unwritable_log_does_not_fail_a_batch(tmp_path, monkeypatch):
    _unwritable_log(monkeypatch)
    with progress.activity_stage("translation", requested=1) as outcome:
        outcome.update(translated=1)
    assert outcome == {"translated": 1}
