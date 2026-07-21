"""Tier 1: drift diff judgment and report writing (no solver)."""

import pytest
import yaml

from pyflightstream.qa.drift import diff_runs, write_drift_report
from pyflightstream.qa.physics import PHYSICS_CASES, CaseResult, PhysicsRun, Verdict


def physics_run(version, metrics, error=None, case_id="PHY-01"):
    return PhysicsRun(
        version=version,
        fs_exe_name=f"fs_{version.replace('.', '')}.exe",
        package_version="0.0.1.dev0",
        results=(
            CaseResult(
                case_id=case_id,
                title=PHYSICS_CASES[case_id].title,
                geometry="stub",
                metrics=metrics,
                error=error,
            ),
        ),
        solver_identity=(f"Flightstream version {version}, build test",),
    )


def test_identical_runs_pass_with_zero_deltas():
    metrics = {"CL_a4": 0.337, "CL_a0": -0.0004}
    drift = diff_runs(physics_run("26.100", metrics), physics_run("26.120", metrics))
    result = drift.results[0]
    assert all(metric.delta == 0.0 for metric in result.metrics.values())
    assert all(metric.verdict is Verdict.PASS for metric in result.metrics.values())
    assert drift.verdict_counts()["pass"] == 2


def test_bands_center_on_the_baseline_value():
    # CL_a4 declares rel 0.02/0.05: 3% off is WARN, 8% off is FAIL.
    drift = diff_runs(
        physics_run("26.100", {"CL_a4": 0.337}),
        physics_run("26.120", {"CL_a4": 0.337 * 1.03}),
    )
    assert drift.results[0].metrics["CL_a4"].verdict is Verdict.WARN
    drift = diff_runs(
        physics_run("26.100", {"CL_a4": 0.337}),
        physics_run("26.120", {"CL_a4": 0.337 * 1.08}),
    )
    assert drift.results[0].metrics["CL_a4"].verdict is Verdict.FAIL


def test_undeclared_metric_gets_no_invented_band():
    drift = diff_runs(
        physics_run("26.100", {"mystery": 1.0}),
        physics_run("26.120", {"mystery": 5.0}),
    )
    assert drift.results[0].metrics["mystery"].verdict is Verdict.NO_REFERENCE


def test_case_error_on_either_version_propagates():
    drift = diff_runs(
        physics_run("26.100", {}, error="solver run failed"),
        physics_run("26.120", {"CL_a4": 0.337}),
    )
    result = drift.results[0]
    assert result.error is not None
    assert "26.100" in result.error
    assert result.metrics == {}


def test_drift_report_pair_and_no_overwrite(tmp_path):
    metrics = {"CL_a4": 0.337}
    drift = diff_runs(physics_run("26.100", metrics), physics_run("26.120", {"CL_a4": 0.339}))
    yaml_path, md_path = write_drift_report(drift, tmp_path, date="2026-07-21")
    document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert document["schema"] == "pyflightstream-drift-report/1"
    body = document["cases"]["PHY-01"]["metrics"]["CL_a4"]
    assert body["delta"] == pytest.approx(0.002)
    assert body["verdict"] == "pass"
    markdown = md_path.read_text(encoding="utf-8")
    assert "26.100 versus 26.120" in markdown
    assert "| CL_a4 | 0.33700 | 0.33900 | +0.00200 |" in markdown
    with pytest.raises(FileExistsError, match="never"):
        write_drift_report(drift, tmp_path, date="2026-07-21")
