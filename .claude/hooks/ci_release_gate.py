#!/usr/bin/env python3
"""Refuse a release-grade push while CI has not gone green on its commit.

This repository's own incident, INC-20260810-2140-shared. Sixteen commits
went to main in one push and the v0.7.0 tag went out fifteen seconds
later, while seven of eight CI jobs were still running. CI was not blind:
it was red on all four platform legs over an unguarded optional import,
and it said so three minutes after the tag had already been published.
Nothing published, because release.yml binds publish to its gates, but
the tag boundary is the one that cannot be retracted.

The requirement already existed, as prose, in the release skill's
pause point 4 ("Annotated tag; push with CI green"), and prose decayed on
the schedule prose decays on. Measured gap between the branch CI run and
the tag: v0.4.0 fourteen minutes, v0.5.0 forty one, v0.6.0 thirteen
seconds, v0.7.0 fifteen. v0.6.0 shipped on the same violation and got
away with it because CI happened to be green.

WHY THIS IS A SECOND HOOK AND NOT AN EDIT TO THE OTHER ONE.
``role_review_gate.py`` beside this file is a hash-pinned vendored body
(kit 0.2.16, pinned by ``tests/test_kit_drift.py``) and cannot be
corrected here; the sister library carries the identical bytes. The
permanent home of this rule is the coordination kit, and when the kit
absorbs it this file is deleted in the same re-vendor commit. Until then
a repository-owned hook ships the rule today, the precedent being
``check_clean_room_trailer.py``, which is tracked and not in the
manifest. Two PreToolUse hooks both run and either can deny, so the
composition is strictly stronger than the kit gate alone.

It does NOT re-implement push parsing. It IMPORTS the pinned gate and
uses its hardened tokenizer, so the two can never disagree about what a
release-grade push is. If that import fails on anything resembling a
push, this hook denies: a gate that cannot parse the command is not a
gate that may allow it.

ONE THING THIS HOOK DOES NOT DO, stated here because a reader will
otherwise assume it. It does not refuse the blanket forms
(``--tags``, ``--follow-tags``, ``--all``, ``--mirror``). The kit gate
refuses those as unscopable, and this hook is only safe in composition
with it: alone, it would let ``--follow-tags`` carry a tag past every
check below. ``tests/test_ci_release_gate.py`` asserts that composition
rather than trusting this paragraph.

FAIL CLOSED ON EVERY UNKNOWN. Red, pending, absent and unreachable all
deny; only the operator-facing text differs. The reasoning is the one
CLAUDE.md already records for ``COORD_INCIDENT_LEDGER``: a guard that
reads its own missing information as permission is not a guard. The
usual objection to failing closed on a NETWORK question does not apply
here, and the difference is worth stating rather than glossing: the
guarded action is itself a push to that remote, so it needs the same
network and the same credentials this query needs. There is no state in
which the push would succeed and the question could not be asked. The
ledger rule had to accept a real cost to fail closed; this one has none.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PREFIX = "ci-release gate:"

#: Conclusions that are not a failure. ``neutral`` and ``skipped`` are
#: how a check reports that it did not apply, which is not a red.
GOOD = frozenset({"success", "neutral", "skipped"})

#: Retries before an unanswered query becomes a refusal. A flake should
#: not block a release; three silences are not a flake.
API_ATTEMPTS = 3

#: What the remote says when it has never seen the commit at all. Both
#: mean absent rather than unreachable, and the distinction is only in
#: the message: a person who pushed no branch needs different advice
#: from one whose network is down.
_NO_SUCH_COMMIT = ("HTTP 422", "HTTP 404", "No commit found", "Not Found")


def _decide(decision: str, reason: str) -> None:
    """Emit a PreToolUse decision and stop."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _allow_silently() -> None:
    """Say nothing and let the command through."""
    sys.exit(0)


def _git(root: Path, *args: str) -> str:
    """Run one git command in ``root`` and return its stdout, or empty."""
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except (OSError, ValueError):
        return ""
    return done.stdout.strip()


def check_runs(slug: str, sha: str) -> tuple[str, object]:
    """Ask the remote for the check runs recorded at one commit.

    Parameters
    ----------
    slug : str
        ``owner/repo`` on GitHub.
    sha : str
        The full commit hash to ask about.

    Returns
    -------
    tuple of (str, object)
        ``("ok", runs)`` with the list of check-run dicts, or
        ``("absent", detail)`` when the remote has never seen the commit,
        or ``("unreachable", detail)`` when the question could not be
        asked. Never raises, and never turns an unanswered question into
        an empty success.
    """
    last = ""
    for _ in range(API_ATTEMPTS):
        try:
            done = subprocess.run(
                ["gh", "api", f"repos/{slug}/commits/{sha}/check-runs?per_page=100"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            last = f"{type(error).__name__}: {error}"
            continue
        if done.returncode != 0:
            last = (done.stderr or done.stdout).strip()[:400]
            if any(marker in last for marker in _NO_SUCH_COMMIT):
                return "absent", last
            continue
        try:
            return "ok", json.loads(done.stdout).get("check_runs", [])
        except (json.JSONDecodeError, ValueError) as error:
            last = f"the remote did not return JSON ({error})"
    return "unreachable", last or "no answer"


def verdict(runs: list, at: str = "") -> tuple[str, str]:
    """Classify a check-runs payload.

    Pure, so the decision can be unit-tested without a network.

    Parameters
    ----------
    runs : list
        Check-run dictionaries as the GitHub API returns them.
    at : str, optional
        An ISO instant. When given, a run that completed after it counts
        as still running, which is how the state at a past moment is
        reconstructed from recorded timestamps rather than guessed.

    Returns
    -------
    tuple of (str, str)
        One of ``green``, ``red``, ``pending`` or ``absent``, and a
        human-readable detail naming the jobs responsible.
    """
    if not runs:
        return "absent", "the remote reports no check run at all for this commit"
    pending: list[str] = []
    bad: list[str] = []
    for run in runs:
        name = run.get("name", "unnamed")
        status = run.get("status")
        completed = run.get("completed_at") or ""
        if at and (status != "completed" or not completed or completed > at):
            pending.append(f"{name} (still running at {at})")
            continue
        if status != "completed":
            pending.append(f"{name} ({status})")
            continue
        if (run.get("conclusion") or "") not in GOOD:
            bad.append(f"{name} -> {run.get('conclusion')}")
    if bad:
        return "red", "; ".join(sorted(bad))
    if pending:
        return "pending", "; ".join(sorted(pending))
    return "green", f"{len(runs)} check run(s), all successful"


def main() -> None:
    """Evaluate the CI-green release gate against a PreToolUse payload."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow_silently()
    command = (payload.get("tool_input") or {}).get("command", "") or ""

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import role_review_gate as kit

        is_push, git_c, after = kit._find_git_push(command)
        tags = kit._release_refs(after) if is_push else []
    except Exception as error:  # noqa: BLE001 - the whole point is to fail closed
        if "git" in command and "push" in command:
            _decide(
                "deny",
                f"{PREFIX} [wiring] the pinned role-review gate could not be used to "
                f"parse this command ({type(error).__name__}: {error}), so whether it "
                "is a release-grade push is unknown. Failing closed. If the kit gate "
                "was re-vendored and its helpers renamed, this hook must move with it.",
            )
        _allow_silently()

    if not is_push or not tags:
        _allow_silently()

    try:
        root = Path(_git(Path(git_c) if git_c else Path.cwd(), "rev-parse", "--show-toplevel"))
        url = _git(root, "config", "--get", "remote.origin.url")
        slug = url.rstrip("/").removesuffix(".git").split("github.com")[-1].lstrip(":/")
        if slug.count("/") != 1:
            _decide(
                "deny",
                f"{PREFIX} [wiring] could not read an owner and a repository from "
                f"remote.origin.url ({url!r}), so CI could not be consulted at all.",
            )

        for tag in tags:
            sha = _git(root, "rev-list", "-n", "1", tag)
            if not sha:
                _decide(
                    "deny",
                    f"{PREFIX} [wiring] the tag {tag!r} does not resolve in this "
                    "repository, so there is no commit whose CI could be read.",
                )
            state, detail = check_runs(slug, sha)
            if state == "unreachable":
                _decide(
                    "deny",
                    f"{PREFIX} [unreachable] CI could not be consulted for {tag} "
                    f"({sha[:12]}) after {API_ATTEMPTS} attempts: {detail}. Refusing "
                    "rather than assuming. A tag is public and triggers the release "
                    "workflow; if the GitHub CLI is missing or unauthenticated, fix "
                    "that and retry. This push needs the same network the query does, "
                    "so there is no offline case this refusal is costing you.",
                )
            if state == "absent":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-absent] the remote has never seen {sha[:12]}, the "
                    f"commit {tag} names ({detail}). Push the branch first and let CI "
                    "run on it. A tag whose commit the remote does not have is a "
                    "release nobody has tested.",
                )

            kind, why = verdict(detail if isinstance(detail, list) else [])
            if kind == "red":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-red] {tag} points at {sha[:12]}, whose CI FAILED on "
                    f"the remote: {why}. A version tag is public and triggers the "
                    "release workflow. Fix the failure, push the branch, wait for CI "
                    "to go green, move the tag onto the green commit, then push it.",
                )
            if kind == "pending":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-pending] {tag} points at {sha[:12]}, whose CI has "
                    f"not concluded: {why}. This is the v0.7.0 failure exactly: the "
                    "tag went out fifteen seconds after the branch, with seven of "
                    "eight jobs still running. Wait for the run to finish, then push "
                    "the tag.",
                )
            if kind == "absent":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-absent] {tag} points at {sha[:12]} and the remote "
                    f"has no CI result for it: {why}. Push the branch first and let "
                    "CI run. A tag whose commit CI has never seen is a release nobody "
                    "tested.",
                )

        print(
            f"{PREFIX} CI is green at every tagged commit ({', '.join(tags)})",
            file=sys.stderr,
        )
        _allow_silently()
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - fail closed, never silently allow
        _decide(
            "deny",
            f"{PREFIX} [gate] the CI check could not be evaluated "
            f"({type(error).__name__}: {error}). Failing closed, because the "
            "alternative is publishing a tag on an unknown state.",
        )


if __name__ == "__main__":
    main()
