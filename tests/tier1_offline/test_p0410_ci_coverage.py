"""P0410: coverage instruments one existing artifact test invocation on tags."""

from pathlib import Path

import yaml


def test_p0410_coverage_only_in_release_artifact_tests():
    root = Path(__file__).resolve().parents[2] / ".github/workflows"
    ci = yaml.safe_load((root / "ci.yml").read_text("utf-8"))
    release = yaml.safe_load((root / "release.yml").read_text("utf-8"))
    assert "coverage" not in ci["jobs"]
    assert "--cov" not in str(ci["jobs"])
    steps = release["jobs"]["test-artifact"]["steps"]
    tests = [step for step in steps if "pytest -n auto" in step.get("run", "")]
    assert len(tests) == 1
    step = tests[0]
    flags = step["env"]["COVERAGE_ARGS"]
    assert "startsWith(github.ref, 'refs/tags/v')" in flags
    assert "matrix.os == 'ubuntu-latest'" in flags
    assert "--cov --cov-branch" in flags
    assert "|| ''" in flags
    assert "--cov-fail-under" not in flags
    assert "$COVERAGE_ARGS" in step["run"]
    assert "-o pythonpath=" in step["run"]
    assert step["env"]["PYFLIGHTSTREAM_TEST_INSTALLED"] == "1"
    assert all(
        "--cov" not in str(job) for name, job in release["jobs"].items() if name != "test-artifact"
    )
