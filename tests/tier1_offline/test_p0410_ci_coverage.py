"""P0420: push CI stays uninstrumented; the frozen release suite owns the floor."""

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_p0420_push_ci_has_no_coverage_measurement():
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text("utf-8"))
    config = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    assert "coverage" not in ci["jobs"]
    for token in ("--cov", "coverage run", "coverage report", "coverage xml"):
        assert token not in str(ci["jobs"])
        assert token not in config["tool"]["pytest"]["ini_options"]["addopts"]


def test_p0420_release_floor_is_configured_without_a_coverage_job():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    coverage = config["tool"]["coverage"]
    assert coverage["run"]["source"] == ["pyflightstream"]
    assert coverage["run"]["branch"] is True
    assert 0 < coverage["report"]["fail_under"] <= 100
    release = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text("utf-8"))
    assert "coverage" not in release["jobs"]


def test_p0420_contributors_find_the_frozen_suite_coverage_gate():
    guide = (ROOT / "CONTRIBUTING.md").read_text("utf-8")
    assert "suite-full" in guide
    assert "--cov" in guide
    assert "[tool.coverage.report]" in guide
    assert "runs on the version tag against the built wheel" not in guide


def test_p0420_release_wheel_tests_run_without_duplicate_coverage():
    release = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text("utf-8"))
    for token in ("--cov", "COVERAGE_ARGS", "coverage run", "coverage report", "coverage xml"):
        assert token not in str(release["jobs"])
    artifact = release["jobs"]["test-artifact"]
    assert artifact["strategy"]["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    tier1 = next(
        step for step in artifact["steps"] if step.get("name") == "Tier 1 tests against the wheel"
    )
    assert tier1["env"]["PYFLIGHTSTREAM_TEST_INSTALLED"] == "1"
    assert tier1["run"].strip() == "pytest -n auto -o pythonpath="
    assert "if" not in tier1
