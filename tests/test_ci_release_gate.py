"""Tier 1: the CI-green release gate, and the wiring that makes it run.

``.claude/hooks/ci_release_gate.py`` refuses a release-grade push while
the commit its tag names has no successful CI result on the remote. It
exists because of INC-20260810-2140-shared, where the v0.7.0 tag was
published fifteen seconds after the branch, with seven of eight CI jobs
still running and the suite red on five of the run's eight checks.

A hook body with no test is a guess. That is measurable rather than
rhetorical: two one-line edits to the body (widening the accepted
conclusions, disabling the red branch) turn every refusal into an
allowance, and without this file nothing anywhere goes red.

ABOUT THE FIXTURE, precisely, because an earlier version of this
docstring overstated it. ``V070_RUNS`` is not the recorded payload. The
real response at that commit carries 25 check runs across three
workflows; this is the eight jobs of the branch's ci run 31436832528,
with their recorded conclusions and completion instants, which are the
ones the incident turns on. The hook's ``verdict`` was run over the full
25-run payload and agrees with this subset on both questions asked here.

Three of these tests assert things ABOUT the hook rather than IN it, and
they matter most: a hook deleted from disk, quietly unwired from the
tracked settings file, or left running past its configured timeout is a
guard that cannot run, and a guard that cannot run fails silently in
exactly the way the incident did.
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
KIT = REPO / ".claude" / "hooks" / "role_review_gate.py"
SETTINGS = REPO / ".claude" / "settings.json"


def _load_hook():
    """Import the hook body by path, since .claude is not a package."""
    spec = importlib.util.spec_from_file_location("ci_release_gate_under_test", HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The eight jobs of ci run 31436832528 at commit 2d754a7, the run that
#: was still going when the v0.7.0 tag was pushed.
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
    blocks = settings.get("hooks", {}).get("PreToolUse", [])
    entries = [
        (block.get("matcher", ""), entry)
        for block in blocks
        for entry in block.get("hooks", [])
        if "ci_release_gate.py" in entry.get("command", "")
    ]
    assert entries, (
        "ci_release_gate.py is not wired as a PreToolUse hook in the TRACKED "
        f"{SETTINGS.relative_to(REPO).as_posix()}. An unwired hook never runs, and "
        "nothing else would have gone red."
    )
    for matcher, _ in entries:
        assert "Bash" in matcher and "PowerShell" in matcher, (
            f"the hook is wired on matcher {matcher!r}, which leaves one of the two "
            "shell tools ungated. A push issued through the other one is unchecked."
        )


def test_the_time_budget_fits_inside_the_configured_hook_timeout():
    """A hook killed at its timeout emits no decision, and that reads as allow.

    Every fail-closed promise in the body depends on the process living
    long enough to PRINT its refusal, so the relation between the hook's
    own budget and the harness timeout is load-bearing configuration, not
    a coincidence of two numbers in two files.
    """
    hook = _load_hook()
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    timeouts = [
        entry.get("timeout")
        for block in settings.get("hooks", {}).get("PreToolUse", [])
        for entry in block.get("hooks", [])
        if "ci_release_gate.py" in entry.get("command", "")
    ]
    assert timeouts and all(isinstance(value, int) for value in timeouts), (
        "the hook is wired without an explicit timeout, so the harness default "
        "decides whether a slow refusal becomes a silent allowance"
    )
    for configured in timeouts:
        assert hook.BUDGET_SECONDS < configured, (
            f"the hook budgets {hook.BUDGET_SECONDS}s of work under a {configured}s "
            "harness timeout. If the harness kills it first there is no deny, only "
            "silence, and silence is permission."
        )
        assert hook.GIT_TIMEOUT <= hook.BUDGET_SECONDS
        assert hook.API_TIMEOUT * hook.API_ATTEMPTS <= hook.BUDGET_SECONDS, (
            "one tag's worth of retries alone exceeds the whole budget, so the "
            "deadline check is the only thing preventing a silent timeout"
        )


def test_the_bridge_expires_when_the_kit_absorbs_the_rule():
    """The deletion must be a red test, not a step someone remembers.

    PLN-20260810-2310 says this hook, its wiring and this file are
    deleted in the SAME commit as the re-vendor that puts the rule in the
    kit gate. Nothing else points that way: every other assertion here
    fails if the bridge is REMOVED, and would keep passing forever after
    the kit made it redundant. Two hooks asking GitHub the same question
    double the rate-limit spend at a release, and this gate turns an
    unanswered query into a refusal.
    """
    kit_body = KIT.read_text(encoding="utf-8")
    assert "check-runs" not in kit_body and "check_runs" not in kit_body, (
        "the pinned kit gate now carries the CI rule, so this bridge is a second hook "
        "asking the same question. Delete .claude/hooks/ci_release_gate.py, its wiring "
        "in .claude/settings.json and this file, in the re-vendor commit "
        "(PLN-20260810-2310-ci-tag-rule-belongs-to-the-kit)."
    )


def test_the_hook_still_states_that_it_does_not_cover_the_blanket_forms():
    """The composition residual must stay visible to the next reader.

    This hook alone would allow --follow-tags. It is safe only because
    the kit gate refuses the blanket forms as unscopable, and that
    refusal is pinned by tests/test_push_gate.py, not here. What this
    asserts is narrower than its old name claimed: that the hook still
    SAYS so, and that the helpers it borrows still exist.
    """
    source = HOOK.read_text(encoding="utf-8")
    assert "--follow-tags" in source, (
        "the hook body no longer states that it does not cover the blanket forms; "
        "that residual must stay visible where the hook is read"
    )
    hook = _load_hook()
    kit = hook._load_kit()
    assert hasattr(kit, "_find_git_push") and hasattr(kit, "_release_refs"), (
        "the pinned kit gate no longer exposes the helpers this hook borrows, so the "
        "two would disagree about what a release-grade push is. A re-vendor moved "
        "them: update ci_release_gate.py in the same commit."
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


def test_a_long_job_list_is_capped_so_the_instruction_stays_readable():
    """The failure list must not bury the next action.

    The matrix grows, and this message is read at the worst moment of a
    release. Eight names then a count, one per line.
    """
    hook = _load_hook()
    many = [
        {"name": f"job-{index:02}", "status": "completed", "conclusion": "failure"}
        for index in range(20)
    ]
    kind, why = hook.verdict(many)
    assert kind == "red"
    assert "and 12 more" in why
    assert why.count("job-") == hook.MAX_NAMED_JOBS


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


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["v0.7.0"], ["v0.7.0"]),
        (["v0.7.0", "refs/tags/v0.7.0"], ["v0.7.0"]),
        (["refs/tags/v0.7.0"], ["v0.7.0"]),
        (["v0.7.0", "v0.7.1"], ["v0.7.0", "v0.7.1"]),
    ],
)
def test_a_refspec_naming_one_tag_twice_costs_one_query(tags, expected):
    """Both sides of ``v0.7.0:refs/tags/v0.7.0`` name the same tag.

    Not cosmetic: each name costs a full retry budget of remote calls,
    and two of them exceed the time this hook is allowed to take.
    """
    hook = _load_hook()
    assert hook.normalise_tags(tags) == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (["origin", "v0.7.0"], "origin"),
        (["upstream", "v0.7.0"], "upstream"),
        (["--quiet", "fork", "v0.7.0"], "fork"),
        ([], "origin"),
    ],
)
def test_the_remote_the_push_names_is_the_remote_consulted(after, expected):
    """Asking origin about a push to a fork is asking the wrong repository.

    That was the gate's only false ALLOW: with a green origin and a push
    to somewhere else, it approved a tag whose CI it had never read.
    """
    hook = _load_hook()
    assert hook.push_remote(after) == expected


def test_a_commit_the_remote_has_never_seen_reads_as_commit_absent(monkeypatch):
    """Both refuse; only the advice differs, and wrong advice wastes a cycle."""
    hook = _load_hook()

    class Done:
        returncode = 1
        stdout = ""
        stderr = "gh: HTTP 422: No commit found for SHA: deadbeef"

    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: Done())
    state, detail = hook.check_runs("owner/repo", "deadbeef", hook.time.monotonic() + 30)
    assert state == "commit-absent", (
        "a commit the remote has never seen must be reported as commit-absent, so the "
        f"operator is told to push the branch; got {state!r} ({detail})"
    )


def test_an_unauthorised_404_is_unreachable_and_not_a_missing_commit(monkeypatch):
    """404 also means a token that cannot see the repository.

    Telling that operator to push the branch is advice that cannot work,
    and it asserts a fact about their remote that was never established.
    """
    hook = _load_hook()

    class Done:
        returncode = 1
        stdout = ""
        stderr = "gh: Not Found (HTTP 404)"

    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: Done())
    state, _ = hook.check_runs("owner/repo", "abc123", hook.time.monotonic() + 30)
    assert state == "unreachable"


def test_a_truncated_page_is_unreachable_rather_than_green(monkeypatch):
    """The gate does not paginate, so a short read is an unanswered question.

    Reading 100 of 130 check runs and calling it green is a well-formed
    answer to a question nobody asked, which is the shape of the incident
    this hook exists for.
    """
    hook = _load_hook()

    class Done:
        returncode = 0
        stderr = ""
        stdout = json.dumps(
            {
                "total_count": 130,
                "check_runs": [{"name": "a", "status": "completed", "conclusion": "success"}],
            }
        )

    monkeypatch.setattr(hook.subprocess, "run", lambda *a, **k: Done())
    state, detail = hook.check_runs("owner/repo", "abc123", hook.time.monotonic() + 30)
    assert state == "unreachable"
    assert "130" in str(detail)


def test_an_unanswerable_query_refuses_rather_than_allowing(monkeypatch):
    """The arm that the COORD_INCIDENT_LEDGER precedent decides."""
    hook = _load_hook()

    def explode(*args, **kwargs):
        raise OSError("gh not found")

    monkeypatch.setattr(hook.subprocess, "run", explode)
    state, _ = hook.check_runs("owner/repo", "abc123", hook.time.monotonic() + 30)
    assert state == "unreachable"


def test_an_exhausted_deadline_refuses_rather_than_retrying_past_it(monkeypatch):
    """Running out of time must produce a refusal, never silence."""
    hook = _load_hook()
    called = []

    def never(*args, **kwargs):
        called.append(1)
        raise AssertionError("the query must not run after the deadline")

    monkeypatch.setattr(hook.subprocess, "run", never)
    state, detail = hook.check_runs("owner/repo", "abc", hook.time.monotonic() - 1)
    assert state == "unreachable"
    assert not called
    assert "out of time" in str(detail)


def _drive(hook, monkeypatch, command, *, answer, capsys, url=None):
    """Run main() over one command with git and the network stubbed."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}})))
    monkeypatch.setattr(
        hook,
        "_git",
        lambda root, *args: {
            "rev-parse": str(REPO),
            "config": url or "https://github.com/nevesgeovana/pyflightstream.git",
            "rev-list": "2d754a740781aaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }[args[0]],
    )
    monkeypatch.setattr(hook, "check_runs", lambda slug, sha, deadline: answer)
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
    """The tag is what gets published, however the command is written.

    Driven through the REAL vendored tokenizer, which is what makes the
    borrowed-helper coupling acceptable: a re-vendor that narrowed
    ``_release_refs`` without renaming it would go red here.
    """
    hook = _load_hook()
    out = _drive(hook, monkeypatch, command, answer=("ok", V070_RUNS), capsys=capsys)
    assert out.strip(), f"the hook said nothing about {command!r}"
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny", command
    assert "ci-red" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    ("answer", "tag"),
    [
        (("unreachable", "no answer"), "unreachable"),
        (("commit-absent", "HTTP 422"), "commit-absent"),
        (("ok", []), "ci-absent"),
        (("ok", [{"name": "a", "status": "queued"}]), "ci-pending"),
        (("ok", [{"name": "a", "status": "completed", "conclusion": "failure"}]), "ci-red"),
    ],
)
def test_every_refusal_arm_is_reached_through_main(answer, tag, monkeypatch, capsys):
    """Each fail-closed arm, driven end to end rather than unit-tested.

    The unreachable and absent arms ARE the fail-closed thesis, and until
    this existed a typo in one of their state comparisons would have
    shipped green.
    """
    hook = _load_hook()
    out = _drive(hook, monkeypatch, "git push origin v0.7.0", answer=answer, capsys=capsys)
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    reason = decision["permissionDecisionReason"]
    assert f"[{tag}]" in reason, f"expected [{tag}], got {reason[:120]}"


@pytest.mark.parametrize(
    "tag",
    ["unreachable", "commit-absent", "ci-absent", "ci-pending", "ci-red", "wiring", "gate"],
)
def test_every_refusal_names_an_action(tag):
    """A refusal that describes a problem and stops is how workarounds start."""
    source = HOOK.read_text(encoding="utf-8")
    assert f"[{tag}]" in source, f"the {tag} arm has gone; update this test with it"


def test_a_non_github_remote_is_refused_rather_than_guessed(monkeypatch, capsys):
    """A remote this gate cannot read is an unknown, and unknowns deny."""
    hook = _load_hook()
    out = _drive(
        hook,
        monkeypatch,
        "git push origin v0.7.0",
        answer=("ok", []),
        capsys=capsys,
        # A non-GitHub https remote rather than the ssh spelling: the ssh
        # form reads as an email address to tests/test_house_style.py,
        # and it exercises the same branch.
        url="https://gitlab.com/owner/repo.git",
    )
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "[wiring]" in decision["permissionDecisionReason"]


def test_a_green_commit_is_allowed(monkeypatch, capsys):
    """The guard must not be a wall: green CI publishes."""
    hook = _load_hook()
    green = [{"name": "test", "status": "completed", "conclusion": "success"}]
    out = _drive(hook, monkeypatch, "git push origin v0.7.0", answer=("ok", green), capsys=capsys)
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


def test_loading_the_kit_does_not_leave_sys_path_mutated():
    """This body is imported inside a long pytest session.

    A permanently prepended hooks directory can shadow any later
    top-level import, and this workspace already owns an incident about
    two copies of one module in sys.modules.
    """
    hook = _load_hook()
    before = list(sys.path)
    hook._load_kit()
    assert sys.path == before, "loading the pinned gate changed sys.path and left it changed"
