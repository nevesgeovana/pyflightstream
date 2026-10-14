"""P0410: execute the release's CI-at-SHA check with synthetic GitHub replies."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml


def _workflow():
    return yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github/workflows/release.yml").read_text("utf-8")
    )


def _run(**changes):
    return {
        "id": 1,
        "run_number": 10,
        "created_at": "2026-10-14T10:00:00Z",
        "run_attempt": 1,
        "name": "ci",
        "path": ".github/workflows/ci.yml",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
    } | changes


def test_p0410_release_depends_on_main_ci_at_sha():
    jobs = _workflow()["jobs"]
    assert "gates" not in jobs
    assert "ci-at-sha" in jobs["publish"]["needs"]
    gate = jobs["ci-at-sha"]
    assert "if" not in gate
    assert gate["permissions"]["actions"] == "read"
    assert "GH_TOKEN" in gate["steps"][0]["env"]


@pytest.mark.parametrize(
    ("runs", "passes"),
    [
        ([], False),
        ([_run()], True),
        ([_run(head_sha="b" * 40)], False),
        ([_run(head_branch="dry-run/rehearsal")], False),
        ([_run(path=".github/workflows/other.yml")], False),
        ([_run(status="in_progress", conclusion=None)], False),
        ([_run(conclusion="failure")], False),
        ([_run(conclusion="cancelled")], False),
        ([_run(conclusion="skipped")], False),
        ([_run(), _run(run_attempt=2, conclusion="failure")], False),
        ([_run(run_attempt=2), _run(conclusion="failure")], True),
        ([_run(), _run(id=2, run_number=11, conclusion="failure")], False),
    ],
)
def test_p0410_ci_at_sha_fails_closed(monkeypatch, runs, passes):
    jobs = _workflow()["jobs"]
    assert "ci-at-sha" in jobs, "release must check existing main CI"
    step = jobs["ci-at-sha"]["steps"][0]
    script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    def reply(args, **kwargs):
        assert args[:4] == ["gh", "api", "--paginate", "--slurp"]
        assert "repos/owner/repo/actions/runs?head_sha=" + "a" * 40 in args[4]
        assert "branch=main" in args[4]
        return json.dumps([{"workflow_runs": runs[:1]}, {"workflow_runs": runs[1:]}])

    monkeypatch.setattr(subprocess, "check_output", reply)
    if passes:
        exec(compile(script, "release-ci-at-sha", "exec"), {})
    else:
        with pytest.raises(SystemExit) as error:
            exec(compile(script, "release-ci-at-sha", "exec"), {})
        assert error.value.code
        if not runs:
            assert "gh workflow run ci.yml --ref main" in str(error.value)


@pytest.mark.parametrize(
    ("older_conclusion", "newer_status", "newer_conclusion", "passes"),
    [
        ("failure", "completed", "success", True),
        ("success", "completed", "failure", False),
        ("success", "in_progress", None, False),
    ],
)
@pytest.mark.parametrize("tie", [False, True], ids=["run-number", "created-at-tie"])
@pytest.mark.parametrize("reverse", [False, True], ids=["old-first", "new-first"])
def test_p0410_latest_run_decides_release(
    monkeypatch, older_conclusion, newer_status, newer_conclusion, passes, tie, reverse
):
    """A failed old run must not veto a successful new dispatch at the same SHA."""
    runs = [
        _run(id=99, run_attempt=9, conclusion=older_conclusion),
        _run(
            id=2,
            run_number=10 if tie else 11,
            created_at="2026-10-14T11:00:00Z" if tie else "2026-10-14T09:00:00Z",
            status=newer_status,
            conclusion=newer_conclusion,
        ),
    ]
    test_p0410_ci_at_sha_fails_closed(monkeypatch, runs[::-1] if reverse else runs, passes)


@pytest.mark.parametrize("conclusion", ["success", "failure"])
def test_p0410_latest_run_uses_latest_attempt(monkeypatch, conclusion):
    runs = [
        _run(conclusion="failure"),
        _run(id=2, run_number=11, conclusion="failure" if conclusion == "success" else "success"),
        _run(id=2, run_number=11, run_attempt=2, conclusion=conclusion),
    ]
    test_p0410_ci_at_sha_fails_closed(monkeypatch, runs, conclusion == "success")
