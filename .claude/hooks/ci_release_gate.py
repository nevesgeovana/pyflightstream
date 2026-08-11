#!/usr/bin/env python3
"""Refuse a release-grade push while CI has not gone green on its commit.

This repository's own incident, INC-20260810-2140-shared. Sixteen commits
went to main in one push and the v0.7.0 tag went out fifteen seconds
later, while seven of eight CI jobs were still running. CI was not blind:
it was red on the four platform legs and on coverage, and it said so
after the tag had already been published. Nothing reached PyPI, because
release.yml binds publish to its gates, but the tag boundary is the one
that cannot be retracted.

The requirement already existed as prose in the release skill, and prose
decayed on the schedule prose decays on. The per-release measurements
live once, in that skill's pause point 4, rather than being copied here.

WHY THIS IS A SECOND HOOK AND NOT AN EDIT TO THE OTHER ONE.
``role_review_gate.py`` beside this file is a hash-pinned vendored body
and cannot be corrected here; the sister library carries the identical
bytes. The permanent home of this rule is the coordination kit
(PLN-20260810-2310), and when the kit absorbs it this file is deleted in
the same re-vendor commit. Until then a repository-owned hook ships the
rule today, the precedent being ``check_clean_room_trailer.py``. Two
PreToolUse hooks both run and either can deny.

It does NOT re-implement push parsing. It loads the pinned gate and uses
its hardened tokenizer, so the two cannot disagree about what a
release-grade push is. If that load fails on anything resembling a push,
this hook denies.

WHAT IT DOES NOT COVER, so the coverage is not overread. It does not
refuse the blanket forms (``--tags``, ``--follow-tags``, ``--all``,
``--mirror``); the kit gate refuses those as unscopable and this hook is
only safe in composition with it. It cannot see a push issued outside
the agent's tool calls, a tag created through the GitHub API or the web
UI, or a push made by a script it cannot tokenize. It is wired on the
Bash and PowerShell tools, so a third command-running tool would be
outside it. It reads the check-runs API and not the commit-status API,
so an externally posted required status is invisible. And a tag matching
``release.yml``'s ``v*`` trigger but not the gate's stricter version
pattern (``vNext``, say) publishes without being release-grade to either
hook. Those belong to the kit promotion's design note, because no
PreToolUse hook can close them. One route that WAS closeable is closed:
``push.followTags`` is read and refused, since a config setting is not a
flag and the kit gate's allowlist only sees flags.

FAIL CLOSED ON EVERY UNKNOWN. Red, pending, absent and unreachable all
deny; only the operator-facing text differs. The reasoning is the one
CLAUDE.md already records for ``COORD_INCIDENT_LEDGER``: a guard that
reads its own missing information as permission is not a guard. The
usual objection to failing closed on a NETWORK question does not apply,
and the difference is worth stating: the guarded action is itself a push
to that remote, so it needs the same network and credentials this query
needs. There is no state in which the push would succeed and the
question could not be asked.

The one unknown a hook can produce itself is running out of time, and it
is the dangerous one, because a hook killed at its timeout emits no
decision at all and the command proceeds. So the whole run is bounded
well inside the timeout configured in ``.claude/settings.json``: every
subprocess is capped, the retry loop and the per-tag loop both check the
deadline, and running out of it is an explicit refusal rather than a
silence. The budget is asserted against that file by
``tests/test_ci_release_gate.py`` rather than left as two numbers that
happen to agree.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

PREFIX = "ci-release gate:"

#: Conclusions that are not a failure. ``neutral`` and ``skipped`` are
#: how a check reports that it did not apply.
GOOD = frozenset({"success", "neutral", "skipped"})

#: The whole hook, including every retry and every local git call, must
#: finish inside this. Kept well under the hook timeout in
#: .claude/settings.json, because being killed is the one failure mode
#: that reads as permission.
BUDGET_SECONDS = 55.0

#: Per-subprocess ceilings, both inside the budget above.
GIT_TIMEOUT = 10.0
API_TIMEOUT = 15.0

#: Retries before an unanswered query becomes a refusal. A flake should
#: not block a release; three silences are not a flake.
API_ATTEMPTS = 3

#: How many failing job names a refusal prints before summarising. The
#: matrix grows, and an uncapped list buries the instruction under the
#: diagnosis at the moment it is least likely to be read carefully.
#:
#: Sized ABOVE the current job count on purpose. At eight it was exactly
#: the size of the matrix that produced the incident, so the worst case,
#: everything red, was the one that got truncated to save a single line.
MAX_NAMED_JOBS = 12

#: How much raw remote error text a refusal will quote. Same reasoning:
#: the arm that can carry the longest diagnosis is the one that most
#: needs its instruction to stay visible.
MAX_DETAIL_CHARS = 240

#: What the remote says when it has never seen the commit. Distinguished
#: from an authorization or slug problem, which also answers 404 and
#: needs completely different advice.
_NO_SUCH_COMMIT = ("HTTP 422", "No commit found")

#: The sentence every refusal a releaser cannot fix must end with. Taken
#: from the kit gate, because inventing a workaround is what a blocked
#: operator does when no escalation is stated.
_ESCALATE = (
    "If the gate itself is broken, stop and tell the author: turning it off to ship "
    "is an author decision, not a workaround."
)


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


def _load_kit():
    """Load the pinned role-review gate as a library, by path.

    By path rather than by mutating ``sys.path``: this body is imported
    by its own test inside a long pytest session, and a permanently
    prepended hooks directory can shadow a later top-level import.
    """
    path = Path(__file__).resolve().parent / "role_review_gate.py"
    spec = importlib.util.spec_from_file_location("_pinned_role_review_gate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the pinned gate at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    """Run one git command in ``root`` and return its stdout, or empty.

    Bounded, unlike an earlier version: three unbounded local calls ran
    before the first bounded remote one, so a stalled credential helper
    could hang the hook past its timeout, and past its timeout reads as
    permission.
    """
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


#: Options that take a SEPARATE value, so the token after them is not
#: the remote. `-o ci.skip origin v0.7.0` read `ci.skip` as the remote
#: and denied with advice about `git remote -v`, which is a false deny
#: pointing somewhere useless.
_OPTIONS_WITH_VALUES = frozenset(
    {"-o", "--push-option", "--repo", "--receive-pack", "--exec", "--force-with-lease"}
)


def push_remote(args_after_push: list[str]) -> str:
    """Return the remote a push names, defaulting to origin.

    The first positional argument after ``push`` is the remote. Reading
    it matters: asking about origin while the push targets a fork is a
    question about a different repository, and answering that one green
    was the only false allow this gate could produce.

    Quotes are stripped, because the kit tokenizer this hook borrows
    unquotes and this function did not, so ``git push "origin" v0.7.0``
    looked up a remote whose name included the quotes. It failed closed,
    but the two disagreeing at all defeats the reason for borrowing.
    """
    skip_next = False
    for token in args_after_push:
        if skip_next:
            skip_next = False
            continue
        if token in _OPTIONS_WITH_VALUES:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token.strip("\"'")
    return "origin"


def deletes_a_ref(args_after_push: list[str]) -> bool:
    """Whether every ref this push names is being DELETED.

    A deletion publishes nothing, so the CI question does not apply to
    it, and refusing it would block the recovery path this gate itself
    creates: the first thing anyone does after being stopped here is
    remove the bad tag. The refspec form is a leading colon or an empty
    source side, and ``--delete`` names the refs positionally.
    """
    tokens = [token.strip("\"'") for token in args_after_push]
    if any(token in ("--delete", "-d") for token in tokens):
        return True
    specs = [token for token in tokens[1:] if not token.startswith("-")]
    return bool(specs) and all(spec.startswith(":") for spec in specs)


def tag_targets(args_after_push: list[str], tags: list[str]) -> dict[str, str]:
    """Map each tag this push publishes to the local commit-ish it carries.

    A refspec publishes its SOURCE side under its destination name, so
    ``HEAD:refs/tags/v0.8.0`` puts HEAD there. Resolving the tag name
    locally instead reads a different commit when one exists under that
    name, and nothing when it does not: a false allow and a false deny
    from the same line.
    """
    targets = {tag: tag for tag in tags}
    specs = [token.strip("\"'").lstrip("+") for token in args_after_push[1:]]
    for spec in specs:
        if ":" not in spec:
            continue
        source, _, destination = spec.partition(":")
        name = destination.rsplit("/", 1)[-1]
        if name in targets and source:
            targets[name] = source
    return targets


def normalise_tags(tags: list[str]) -> list[str]:
    """Strip refs/tags/ and de-duplicate, preserving order.

    ``origin v0.7.0:refs/tags/v0.7.0`` names one tag twice, and each name
    would otherwise cost a full retry budget of remote calls.
    """
    seen: list[str] = []
    for tag in tags:
        short = tag.rsplit("/", 1)[-1] if tag.startswith("refs/tags/") else tag
        if short not in seen:
            seen.append(short)
    return seen


def check_runs(slug: str, sha: str, deadline: float) -> tuple[str, object]:
    """Ask the remote for the check runs recorded at one commit.

    Parameters
    ----------
    slug : str
        ``owner/repo`` on GitHub.
    sha : str
        The full commit hash to ask about.
    deadline : float
        A ``time.monotonic()`` instant after which to stop retrying.

    Returns
    -------
    tuple of (str, object)
        ``("ok", runs)``, ``("commit-absent", detail)`` when the remote
        has never seen the commit, or ``("unreachable", detail)`` when
        the question could not be asked or was answered incompletely.
        Never turns an unanswered question into an empty success.

    Notes
    -----
    A payload whose ``check_runs`` is not a list can still raise, and
    ``main`` catches that into a ``[gate]`` refusal. This function is not
    exception-free; it is answer-free-safe, which is the property that
    matters.
    """
    last = ""
    for _ in range(API_ATTEMPTS):
        if time.monotonic() >= deadline:
            return "unreachable", f"out of time after {last or 'no answer yet'}"
        try:
            done = subprocess.run(
                ["gh", "api", f"repos/{slug}/commits/{sha}/check-runs?per_page=100"],
                capture_output=True,
                text=True,
                check=False,
                timeout=API_TIMEOUT,
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            last = f"{type(error).__name__}: {error}"
            continue
        if done.returncode != 0:
            last = (done.stderr or done.stdout).strip()[:400]
            if any(marker in last for marker in _NO_SUCH_COMMIT):
                return "commit-absent", last
            continue
        try:
            payload = json.loads(done.stdout)
        except (json.JSONDecodeError, ValueError) as error:
            last = f"the remote did not return JSON ({error})"
            continue
        runs = payload.get("check_runs", [])
        total = payload.get("total_count", len(runs))
        if isinstance(total, int) and total > len(runs):
            # A truncated page is an unanswered question, not a green
            # one: the red job could be the one past the cut.
            return "unreachable", (
                f"the remote reports {total} check runs and returned {len(runs)}; "
                "this gate does not paginate, so the rest were never read"
            )
        return "ok", runs
    return "unreachable", last or "no answer"


def _summarise(names: list[str]) -> str:
    """One job per line, capped, so the instruction after it stays visible."""
    ordered = sorted(names)
    shown = ordered[:MAX_NAMED_JOBS]
    text = "\n    " + "\n    ".join(shown)
    if len(ordered) > len(shown):
        text += f"\n    and {len(ordered) - len(shown)} more"
    return text


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
        reconstructed from recorded timestamps rather than guessed. Used
        by the tests to replay the v0.7.0 push; ``main`` never passes it,
        so that branch is deliberately test-only and should not be read
        as protecting a live path.

    Returns
    -------
    tuple of (str, str)
        One of ``green``, ``red``, ``pending`` or ``absent``, and a
        human-readable detail naming the jobs responsible.

    Notes
    -----
    Green means every check run that EXISTS is good. There is no notion
    of an expected job set here, so a second workflow that has not been
    queued yet cannot be distinguished from one that will never run. The
    window is seconds in this repository and both workflows fire on the
    same event, which is why the residual is stated rather than closed.
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
        return "red", _summarise(bad)
    if pending:
        return "pending", _summarise(pending)
    return "green", f"{len(runs)} check run(s), all successful"


def main() -> None:
    """Evaluate the CI-green release gate against a PreToolUse payload."""
    deadline = time.monotonic() + BUDGET_SECONDS
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
        command = (tool_input or {}).get("command", "") if isinstance(tool_input, dict) else ""
        command = command if isinstance(command, str) else ""
    except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
        # A payload shape this hook does not understand is not a push it
        # can judge, but it must not crash: a hook that exits non-zero
        # without a decision is a non-blocking error, and the command
        # proceeds. Four malformed shapes reached that path before this.
        _allow_silently()

    try:
        kit = _load_kit()
        is_push, git_c, after = kit._find_git_push(command)
        if is_push and not after:
            # The kit's own fail-closed sentinel: it returns no arguments
            # when its tokenizer could not parse the command, and its
            # comment calls that "a push we could not confirm safe".
            # Reading that as "no tags, therefore allow" turns the other
            # gate's refusal into this one's permission.
            _decide(
                "deny",
                f"{PREFIX} [wiring] the pinned role-review gate could not tokenize this "
                "command, which it reports as a push it cannot confirm safe. This gate "
                "cannot tell whether it names a version tag, so it refuses. Rewrite the "
                f"command so it parses, and push the tag by name. {_ESCALATE}",
            )
        if is_push and deletes_a_ref(after):
            # A deletion publishes nothing, so the CI question does not
            # apply, and denying it would block the recovery path this
            # gate creates. Whether a published ref may be deleted at all
            # is the kit gate's call, not this one's.
            _allow_silently()
        tags = normalise_tags(kit._release_refs(after)) if is_push else []
    except Exception as error:  # noqa: BLE001 - the whole point is to fail closed
        if "git" in command and "push" in command:
            _decide(
                "deny",
                f"{PREFIX} [wiring] the pinned role-review gate could not be used to "
                f"parse this command ({type(error).__name__}: {error}), so whether it "
                "is a release-grade push is unknown. Failing closed. If the kit gate "
                "was re-vendored and its helpers renamed, update this hook with it. "
                f"{_ESCALATE}",
            )
        _allow_silently()

    if not is_push or not tags:
        _allow_silently()

    try:
        root = Path(_git(Path(git_c) if git_c else Path.cwd(), "rev-parse", "--show-toplevel"))
        remote = push_remote(after)
        # pushurl FIRST. git pushes there when it is set, and reading
        # `url` instead asks GitHub about the fetch remote: the identical
        # false allow that reading `origin` unconditionally produced,
        # wearing a different config key.
        url = _git(root, "config", "--get", f"remote.{remote}.pushurl") or _git(
            root, "config", "--get", f"remote.{remote}.url"
        )
        slug = url.rstrip("/").removesuffix(".git").split("github.com")[-1].lstrip(":/")
        if "github.com" not in url or slug.count("/") != 1:
            _decide(
                "deny",
                f"{PREFIX} [wiring] the remote {remote!r} resolves to {url!r}, which "
                "this gate cannot read as a GitHub owner and repository, so CI could "
                "not be consulted at all.\n\n"
                "Check `git remote -v` and `git config --get-regexp remote.*.pushurl`. "
                f"{_ESCALATE}",
            )
        targets = tag_targets(after, tags)

        # A tag refspec carried by configuration rather than by the
        # command line. The kit gate refuses the blanket FLAGS, and a
        # config setting is not a flag, so `git push origin main` can
        # publish an annotated tag with no tag token for either hook to
        # see. One bounded local call closes the one route that needs no
        # unusual operator behaviour.
        if _git(root, "config", "--get", "push.followTags").lower() == "true":
            _decide(
                "deny",
                f"{PREFIX} [config] push.followTags is true in this repository, so an "
                "ordinary branch push can publish an annotated tag with no tag named "
                "on the command line, which neither this gate nor the role-review gate "
                "can scope. Unset it (`git config --unset push.followTags`) and push "
                "the tag by name, which is what the release checklist asks for anyway.",
            )

        for tag in tags:
            if time.monotonic() >= deadline:
                _decide(
                    "deny",
                    f"{PREFIX} [gate] ran out of its {BUDGET_SECONDS:.0f}s budget "
                    f"before reaching {tag}. Failing closed: a hook killed by the "
                    "harness emits no decision at all, and no decision is treated as "
                    "permission. Push one tag at a time, or investigate what is slow. "
                    f"{_ESCALATE}",
                )
            commitish = targets.get(tag, tag)
            sha = _git(root, "rev-list", "-n", "1", commitish)
            if not sha:
                _decide(
                    "deny",
                    f"{PREFIX} [no-such-tag] {commitish!r}, which this push would "
                    f"publish as {tag}, does not resolve in this repository, so there "
                    "is no commit whose CI could be read.\n\n"
                    "Check the spelling, or create the tag locally before pushing it.",
                )
            state, detail = check_runs(slug, sha, deadline)
            if state == "unreachable":
                _decide(
                    "deny",
                    f"{PREFIX} [unreachable] CI could not be consulted for {tag} "
                    f"({sha[:12]}) on {slug}.\n\n"
                    "Run `gh auth status`, fix what it reports, then retry. This push "
                    "needs the same network and credentials the query does, so there "
                    "is no offline case this refusal is costing you. "
                    f"{_ESCALATE}\n\n"
                    f"The remote said: {str(detail)[:MAX_DETAIL_CHARS]}",
                )
            if state == "commit-absent":
                _decide(
                    "deny",
                    f"{PREFIX} [commit-absent] {slug} has never seen {sha[:12]}, the "
                    f"commit {tag} names.\n\n"
                    "Push the branch first and let CI run on it. A tag whose commit "
                    "the remote does not have is a release nobody has tested.",
                )

            kind, why = verdict(detail if isinstance(detail, list) else [])
            if kind == "red":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-red] {tag} points at {sha[:12]}, whose CI FAILED on "
                    f"the remote:{why}\n\n"
                    "Fix the failure, push the branch, wait for CI to finish, move the "
                    "tag onto the green commit, then push the tag. Fixing CI means a "
                    "new commit, which re-arms the role-review gate: re-run both "
                    "attestations naming the tag before pushing it.\n"
                    f"Read the failures: https://github.com/{slug}/commit/{sha}/checks",
                )
            if kind == "pending":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-pending] {tag} points at {sha[:12]}, whose CI has "
                    f"not concluded:{why}\n\n"
                    "This is the state this gate exists for: a tag is public and "
                    "triggers the release workflow, and an unfinished run is not a "
                    "green one. Wait for it to finish, then push the tag.\n"
                    f"Watch it: https://github.com/{slug}/commit/{sha}/checks",
                )
            if kind == "absent":
                _decide(
                    "deny",
                    f"{PREFIX} [ci-absent] {slug} has {sha[:12]} but reports no check "
                    "run for it at all.\n\n"
                    f"Run `gh run list --commit {sha}` (the FULL hash; the API filter "
                    "does not match an abbreviation, so a short one always returns "
                    "nothing and would appear to confirm this refusal). If that is "
                    "genuinely empty, no run was created for this ref: the workflow "
                    "may not trigger on it, or Actions may be disabled for the "
                    f"repository. Neither is fixed by pushing again. {_ESCALATE}\n"
                    f"Look at https://github.com/{slug}/actions",
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
            f"({type(error).__name__}: {error}).\n\n"
            "Failing closed, because the alternative is publishing a tag on an "
            f"unknown state. Resolve the error, then push. {_ESCALATE}",
        )


if __name__ == "__main__":
    main()
