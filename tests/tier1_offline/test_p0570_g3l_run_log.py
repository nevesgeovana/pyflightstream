"""0.57.0 PFS-2220 (G3L): the human-readable run log, written beside the stage records.

Written from the requirement: every run and every doe set writes ``geom-run.log`` listing each
sub-step with its inputs, checks (measured, threshold, unit, verdict), wall time and warnings, and
where the run stopped or that it completed; a set that failed has its own log and report.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.geometry._records import check_entry
from pyflightstream.workspace import _geom_run
from pyflightstream.workspace._geom_run import StageOutcome

BODY = {"components": {"FUS": {"type": "body", "length_mm": 2000.0}}}
LOG = "geom-run.log"


def _fail(context):
    return StageOutcome(
        checks=[check_entry("law.monotonic", "failed", 2.5, 1.0, unit="mm", where={"x": 3})],
        warnings=["planted warning"],
        outputs={"inputs": {"piece": "wing.igs"}},
    )


def test_p0570_g3l_a_planted_failure_is_named_in_the_log(tmp_path, monkeypatch):
    monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, "S4", _fail)
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S9")
    assert report["status"] == "failed"
    text = (tmp_path / LOG).read_text(encoding="utf-8")
    assert "package version:" in text and "configuration file:" in text
    assert "check law.monotonic: measured 2.5 mm, threshold <= 1.0 mm: FAILED" in text
    assert "stopped at sub-step S4, check law.monotonic" in text
    assert "measured 2.5, threshold 1.0" in text
    assert "inputs: " in text and "wing.igs" in text and "warning: planted warning" in text
    assert "sub-steps not reached: S5" in text and "S9" in text.split("not reached")[1]
    assert "sub-step S5" not in text.replace("not reached", "")


def test_p0570_g3l_a_passing_run_lists_every_sub_step_that_ran(tmp_path):
    report = _geom_run.run_geometry(BODY, out=tmp_path, until="S3")
    text = (tmp_path / LOG).read_text(encoding="utf-8")
    for stage in ("S0", "S1", "S2", "S3"):
        assert f"sub-step {stage} " in text
    assert "check input.valid: measured 0 refused keys, threshold <= 0 refused keys: PASSED" in text
    assert "wall " in text
    assert report["status"] == "incomplete"
    assert "result: INCOMPLETE" in text and "checks not measured" in text


def test_p0570_g3l_the_log_is_written_as_the_run_proceeds(tmp_path, monkeypatch):
    def crash(context):
        raise KeyboardInterrupt

    monkeypatch.setitem(_geom_run.STAGE_FUNCTIONS, "S2", crash)
    with pytest.raises(KeyboardInterrupt):
        _geom_run.run_geometry(BODY, out=tmp_path, until="S9")
    text = (tmp_path / LOG).read_text(encoding="utf-8")
    assert "sub-step S0 " in text and "sub-step S1 " in text and "sub-step S2 " not in text
    assert "result:" not in text


def test_p0570_g3l_a_refused_run_leaves_a_report_and_a_log(tmp_path):
    report = _geom_run.run_geometry(BODY, out=tmp_path / "o", overrides={"FUS.nope": 1})
    assert report["status"] == "refused"
    assert json.loads((tmp_path / "o" / "report.json").read_text(encoding="utf-8")) == report
    text = (tmp_path / "o" / LOG).read_text(encoding="utf-8")
    assert "result: REFUSED" in text and "unknown parameter" in text


def test_p0570_g3l_a_doe_set_that_was_refused_or_faulted_has_its_own_log(tmp_path, monkeypatch):
    sets = [{"FUS.length_mm": 2500.0}, {"FUS.nope": 1.0}]
    list(_geom_run.run_doe(BODY, sets, out=tmp_path, until="S2"))
    refused = tmp_path / "set-0002"
    assert json.loads((refused / "report.json").read_text(encoding="utf-8"))["status"] == "refused"
    assert "result: REFUSED" in (refused / LOG).read_text(encoding="utf-8")
    assert "result: INCOMPLETE" in (tmp_path / "set-0001" / LOG).read_text(encoding="utf-8")

    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_TIMEOUT", "0.01")
    out = tmp_path / "dead"
    (report,) = _geom_run.run_doe(BODY, [{"FUS.length_mm": 2500.0}], out=out, until="S2")
    assert report["stage"] == "worker"
    folder = out / "set-0001"
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["stage"] == "worker"
    text = (folder / LOG).read_text(encoding="utf-8")
    assert "stopped at sub-step worker, check worker.completed" in text
    assert "ran longer than 0.01 s" in text and "package version:" in text
