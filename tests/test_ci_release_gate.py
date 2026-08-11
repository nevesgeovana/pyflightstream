"""Tier 1: the CI-green release gate, and the wiring that makes it run.

``.claude/hooks/ci_release_gate.py`` refuses a release-grade push while
the commit its tag names has no successful CI result on the remote. It
exists because of INC-20260810-2140-shared, where the v0.7.0 tag was
published fifteen seconds after the branch, with seven of eight CI jobs
still running and the suite red on every platform leg.

A hook body with no test is a guess. That is measurable rather than
rhetorical: two one-line edits to the body (widening the accepted
conclusions, disabling the red branch) turn every refusal into an
allowance, and without this file nothing anywhere goes red. The fixture
below is the payload recorded from the real v0.7.0 push, so the
regression these tests pin is the incident itself and not a
reconstruction of it.

Two of these tests assert things ABOUT the hook rather than IN it, and
they are the ones that matter most: a hook deleted from disk, or quietly
unwired from the tracked settings file, is a guard that cannot run, and a
guard that cannot run fails silently in exactly the way the incident did.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "ci_release_gate.py"
SETTINGS = REPO / ".claude" / "settings.json"


def _load_hook():
    """Import the hook body by path, since .claude is not a package."""
    spec = importlib.util.spec_from_file_location("ci_release_gate_under_test", HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The eight jobs of CI run 31436832528 at commit 2d754a7, the run that
#: was still going when the v0.7.0 tag was pushed. Conclusions and
#: completion instants are the recorded ones.
V070_RUNS = [
    {
        "name": "guard",
        "status": "completed",
        "conclusion": "success",
        "completed_at": "2026-08-10T22:06:00Z",
    },
    {
        "name": "types",
        "status": "completed",
        "conclusion": "success",
        "completed_at": "2026-08-10T22:06:45Z",
    },
    {
        "name": "docs",
        "status": "completed",
        "conclusion": "success",
        "completed_at": "2026-08-10T22:06:50Z",
    },
    {
        "name": "test (ubuntu-latest, 3.12)",
        "status": "completed",
        "conclusion": "failure",
        "completed_at": "2026-08-10T22:07:31Z",
    },
    {
        "name": "test (ubuntu-latest, 3.11)",
        "status": "completed",
        "conclusion": "failure",
        "completed_at": "2026-08-10T22:07:38Z",
    },
    {
        "name": "coverage",
        "status": "completed",
        "conclusion": "failure",
        "completed_at": "2026-08-10T22:08:07Z",
    },
    {
        "name": "test (windows-latest, 3.11)",
        "status": "completed",
        "conclusion": "failure",
        "completed_at": "2026-08-10T22:09:44Z",
    },
    {
        "name": "test (windows-latest, 3.12)",
        "status": "completed",
        "conclusion": "failure",
        "completed_at": "2026-08-10T22:10:21Z",
    },
]

#: The instant the v0.7.0 tag was actually pushed.
V070_TAG_INSTANT = "2026-08-10T22:06:07Z"


def test_the_hook_file_exists():
    """A guard deleted from disk is not a guard that got easier to pass."""
    assert HOOK.is_file(), (
        f"{HOOK.relative_to(REPO).as_posix()} is missing. Deleting it removes the only "
        "thing that refuses a version tag on a red commit; if that is deliberate, "
        "delete this test in the same commit and say why."
    )


def test_the_hook_is_wired_in_the_tracked_settings_file():
    """Wiring it only in settings.local.json would reach no other clone.

    That file is gitignored, so a hook wired there is absent from a fresh
    checkout and from the sister library, which is where this rule has to
    travel next.
    """
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    commands = [
        entry.get("command", "")
        for block in settings.get("hooks", {}).get("PreToolUse", [])
        for entry in block.get("hooks", [])
    ]
    assert any("ci_release_gate.py" in command for command in commands), (
        "ci_release_gate.py is not wired as a PreToolUse hook in the TRACKED "
        f"{SETTINGS.relative_to(REPO).as_posix()}. An unwired hook never runs, and "
        "nothing else would have gone red."
    )
    matchers = [
        block.get("matcher", "")
        for block in settings.get("hooks", {}).get("PreToolUse", [])
        for entry in block.get("hooks", [])
        if "ci_release_gate.py" in entry.get("command", "")
    ]
    for matcher in matchers:
        assert "Bash" in matcher and "PowerShell" in matcher, (
            f"the hook is wired on matcher {matcher!r}, which leaves one of the two "
            "shell tools ungated. A push issued through the other one is unchecked."
        )


def test_the_kit_gate_still_refuses_the_blanket_push_forms():
    """This hook is only safe in composition with the pinned kit gate.

    Alone it would allow ``--follow-tags``, which is how an unattested
    tag reached a publish workflow once. The kit gate refuses the blanket
    forms as unscopable, and this test pins that dependency rather than
    leaving it as a sentence in a docstring.
    """
    sys.path.insert(0, str(REPO / ".claude" / "hooks"))
    try:
        import role_review_gate as kit
    finally:
        sys.path.pop(0)
    source = HOOK.read_text(encoding="utf-8")
    assert "--follow-tags" in source, (
        "the hook body no longer states that it does not cover the blanket forms; "
        "that residual must stay visible to its next reader"
    )
    assert hasattr(kit, "_find_git_push") and hasattr(kit, "_release_refs"), (
        "the pinned kit gate no longer exposes the helpers this hook imports, so the "
        "two would disagree about what a release-grade push is. Re-vendor moved them: "
        "update ci_release_gate.py in the same commit."
    )


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], "absent"),
        ([{"name": "a", "status": "completed", "conclusion": "success"}], "green"),
        ([{"name": "a", "status": "completed", "conclusion": "skipped"}], "green"),
        ([{"name": "a", "status": "completed", "conclusion": "neutral"}], "green"),
        ([{"name": "a", "status": "completed", "conclusion": "failure"}], "red"),
        ([{"name": "a", "status": "completed", "conclusion": "cancelled"}], "red"),
        ([{"name": "a", "status": "completed", "conclusion": "timed_out"}], "red"),
        ([{"name": "a", "status": "completed", "conclusion": None}], "red"),
        ([{"name": "a", "status": "in_progress"}], "pending"),
        ([{"name": "a", "status": "queued"}], "pending"),
    ],
)
def test_each_conclusion_maps_to_the_right_verdict(runs, expected):
    """Only success, neutral and skipped may read as green."""
    hook = _load_hook()
    assert hook.verdict(runs)[0] == expected


def test_a_red_leg_outweighs_a_green_one():
    """One failure among many successes is a red, not a majority vote."""
    hook = _load_hook()
    kind, why = hook.verdict(V070_RUNS)
    assert kind == "red"
    assert "test (ubuntu-latest, 3.11)" in why


def test_the_verdict_at_the_instant_the_v070_tag_was_pushed_is_pending():
    """The measurement this whole hook exists for.

    At 22:06:07Z exactly one of the eight jobs had concluded. Anything
    other than a refusal here means the guard would have let the original
    push through.
    """
    hook = _load_hook()
    kind, why = hook.verdict(V070_RUNS, at=V070_TAG_INSTANT)
    assert kind == "pending", (
        "at the instant the v0.7.0 tag was pushed the verdict must be pending, so the "
        f"push is refused; got {kind!r} ({why})"
    )
    assert "guard" not in why, "the one job that had finished must not read as pending"
    assert "coverage" in why


def test_the_verdict_today_on_that_same_commit_is_red():
    """And once the run finished, the same push is refused for a second reason."""
    hook = _load_hook()
    assert hook.verdict(V070_RUNS)[0] == "red"


def test_a_commit_the_remote_has_never_seen_reads_as_absent_not_unreachable(monkeypatch):
    """Both refuse; only the advice differs, and wrong advice wastes a cycle."""
    hook = _load_hook()

    class Done:
        returncode = 1
        stdout = ""
        stderr = "gh: HTTP 422: No commit found for SHA: deadbeef"

    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: Done())
    state, detail = hook.check_runs("owner/repo", "deadbeef")
    assert state == "absent", (
        "a commit the remote has never seen must be reported as absent, so the "
        f"operator is told to push the branch; got {state!r} ({detail})"
    )


def test_an_unanswerable_query_refuses_rather_than_allowing(monkeypatch):
    """The arm that the COORD_INCIDENT_LEDGER precedent decides."""
    hook = _load_hook()

    def explode(*args, **kwargs):
        raise OSError("gh not found")

    monkeypatch.setattr(hook.subprocess, "run", explode)
    state, _ = hook.check_runs("owner/repo", "abc123")
    assert state == "unreachable"


def _drive(hook, monkeypatch, command, *, runs, capsys):
    """Run main() over one command with the network answer stubbed."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}})))
    monkeypatch.setattr(
        hook,
        "_git",
        lambda root, *args: {
            "rev-parse": str(REPO),
            "config": "https://github.com/nevesgeovana/pyflightstream.git",
            "rev-list": "2d754a740781aaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }[args[0]],
    )
    monkeypatch.setattr(hook, "check_runs", lambda slug, sha: ("ok", runs))
    with pytest.raises(SystemExit):
        hook.main()
    return capsys.readouterr().out


@pytest.mark.parametrize(
    "command",
    [
        "git push origin v0.7.0",
        "git push --quiet origin v0.7.0",
        "git push origin refs/tags/v0.7.0",
        "git push origin HEAD:refs/tags/v0.7.0",
        'bash -c "git push origin v0.7.0"',
    ],
)
def test_every_spelling_of_the_release_push_is_refused_on_a_red_commit(
    command, monkeypatch, capsys
):
    """The tag is what gets published, however the command is written."""
    hook = _load_hook()
    out = _drive(hook, monkeypatch, command, runs=V070_RUNS, capsys=capsys)
    assert out.strip(), f"the hook said nothing about {command!r}"
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny", command
    assert "ci-red" in decision["permissionDecisionReason"]


def test_a_green_commit_is_allowed(monkeypatch, capsys):
    """The guard must not be a wall: green CI publishes."""
    hook = _load_hook()
    green = [{"name": "test", "status": "completed", "conclusion": "success"}]
    out = _drive(hook, monkeypatch, "git push origin v0.7.0", runs=green, capsys=capsys)
    assert out.strip() == "", f"a green commit must pass silently, got {out!r}"


def test_a_branch_push_is_not_touched(monkeypatch, capsys):
    """Only release-grade pushes are gated; ordinary work is not slowed."""
    hook = _load_hook()
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": "git push origin main"}}))
    )
    with pytest.raises(SystemExit):
        hook.main()
    assert capsys.readouterr().out.strip() == ""


def test_a_command_that_is_not_a_push_is_not_touched(monkeypatch, capsys):
    """The hook fires on every shell command; it must be silent on almost all."""
    hook = _load_hook()
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": "pytest -q"}}))
    )
    with pytest.raises(SystemExit):
        hook.main()
    assert capsys.readouterr().out.strip() == ""
