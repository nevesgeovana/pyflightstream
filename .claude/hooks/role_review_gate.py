#!/usr/bin/env python3
r"""Mandatory role-review gate on git push (PreToolUse hook, Bash + PowerShell).

Why this exists: on 2026-07-23 the v0.3.0 release ran generic
paraphrased checks instead of invoking the specialist reviewer agents,
because "role-review" was read as a text instruction rather than the
skill that spawns the agents. Documentation alone did not prevent it.
This hook makes the protocol mechanical: a git push is blocked until an
attestation says the role-review skill (the real agents) ran for the
exact commit being pushed, and a release-grade push (a version tag or
--tags/--follow-tags) additionally requires the release attestation
(full-scope audit plus the role-review sweep of every item).

The hook cannot itself run the agents (subagents are the model's to
invoke). It blocks and tells the model what to run; the skills write
the attestation as their closing step (see write_attestation.py), so
the only way to clear the gate is to actually run them.

Design (hardened 2026-07-23 after the gate's own role review found
bypass holes in v1):
- The command is tokenized, not substring-matched, so ``git -C <path>
  push``, ``git --git-dir=... push`` and ``cd x && git push`` are all
  recognized (v1's ``\bgit\s+push\b`` missed them and failed open).
- The in-script detection is the ONLY scope filter: settings.json uses
  the bare ``Bash|PowerShell`` matcher with no ``if`` glob, because the
  permission-rule glob ``Bash(git push*)`` is prefix-anchored and would
  itself miss the compound forms above.
- Fails CLOSED: once the command looks like a git push, any error
  (unreadable stdin, missing git, unresolvable HEAD, malformed
  attestation) denies with an explanation. Only genuinely out-of-scope
  calls (not a push, not a git repo) allow silently.
- Release-grade detection reads the refs being pushed (an explicit
  ``vX...`` tag argument, or --tags/--follow-tags), NOT substrings of
  the whole command (so a branch named ``fix/v1.2.3`` is not a false
  release) and NOT tags that merely happen to sit at HEAD.

Extended 2026-07-23 after the sister library's review found two holes:

- The attestation is checked against the WHOLE range the push makes new
  (``git rev-list <target> --not --remotes``), not just the tip. v2
  compared one commit, so any commit already on the branch but not yet
  on the remote shipped unreviewed; itaca demonstrated it by pushing
  across an intermediate commit no attestation ever named (PLN-082).
- A push is denied while the shared incident ledger has an open,
  blocking incident for this repository, so no new work ships on top of
  a defect whose structural cause is still unfixed (PLN-084).

The attestation path is duplicated in write_attestation.py:ATTESTATION
and .gitignore; a rename must touch all three.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ATTESTATION = ".claude/.role_review_attestation.json"
# The incident ledger shared with the sister library. A push is denied
# while any incident is open and blocking for this repository: a defect
# is fixed at its structural cause before more work ships on top of it
# (author's decision 2026-07-23, after three failures in one session).
INCIDENT_CHECKER = Path(
    r"C:\Users\geova\OneDrive\Education\ResearchHub\shared_incidents\check_incidents.py"
)
REPO_NAME = "pyflightstream"
# A version tag argument: v followed by a digit, then version-ish
# characters (covers v0.3.0 and pre-releases like v0.3.0rc1, matching
# the release workflow's `v*` publish trigger). Anchored to the whole
# token, so a branch name like fix/v1.2.3-regression does not match.
VERSION_TAG_TOKEN = re.compile(r"^v\d[\w.\-]*$")


def _decide(decision: str, reason: str) -> None:
    """Emit a PreToolUse permission decision and exit."""
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
    """Out of scope: emit nothing, let the normal permission flow run."""
    sys.exit(0)


def _unquote(token: str) -> str:
    """Strip one layer of surrounding quotes left by shlex(posix=False)."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _find_git_push(command: str) -> tuple[bool, str | None, list[str]]:
    """Detect a git push in a possibly-compound command.

    Returns ``(is_push, git_c_path, args_after_push)``. ``git_c_path`` is
    the target of a ``-C <path>`` global option when present (so the gate
    evaluates the right repository), else None.

    The command is tokenized with ``shlex`` so quoting is respected: a
    "git push" that appears INSIDE a quoted string (for example a commit
    message that mentions the command) is a single token and never
    matches, while a real ``... && git push`` (the shell operator is its
    own token) does. On unbalanced quotes the parse fails; then, if the
    raw text contains both ``git`` and ``push`` as words, fail closed by
    treating it as a push we could not confirm safe.
    """
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        if re.search(r"\bgit\b", command) and re.search(r"\bpush\b", command):
            return True, None, []
        return False, None, []

    i = 0
    while i < len(tokens):
        exe = _unquote(tokens[i]).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if exe not in ("git", "git.exe"):
            i += 1
            continue
        # Walk global options (-C <path>, --git-dir=..., -c k=v, ...) to
        # the subcommand token.
        j = i + 1
        git_c_path: str | None = None
        while j < len(tokens):
            tok = _unquote(tokens[j])
            if tok == "-C" and j + 1 < len(tokens):
                git_c_path = _unquote(tokens[j + 1])
                j += 2
                continue
            if tok.startswith("--git-dir="):
                git_c_path = tok.split("=", 1)[1]
                j += 1
                continue
            if tok == "-c" and j + 1 < len(tokens):
                j += 2
                continue
            if tok.startswith("-"):
                j += 1
                continue
            break
        if j < len(tokens) and _unquote(tokens[j]) == "push":
            return True, git_c_path, [_unquote(t) for t in tokens[j + 1 :]]
        i = j
    return False, None, []


def _git(root: Path, *args: str) -> str:
    """Run git in ``root``; empty string on any failure (caller decides)."""
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        ).stdout.strip()
    except (OSError, ValueError):
        return ""


def _pushed_commits(root: Path, target: str) -> list[str]:
    """List the commits this push would make newly available on the remote.

    ``git rev-list <target> --not --remotes`` is everything reachable
    from the target that no remote-tracking ref already has. That is the
    real range a push moves, and it needs no refspec parsing, so
    ``git push``, ``git push origin main``, ``git push origin HEAD:main``
    and a tag push are all handled the same way.

    Empty means the remote already has everything: nothing new ships.
    """
    listed = _git(root, "rev-list", target, "--not", "--remotes")
    return [c for c in listed.splitlines() if c]


def _blocking_incidents() -> tuple[bool, str]:
    """Ask the shared ledger whether an open incident blocks this repo.

    Returns ``(blocked, detail)``. A missing checker is NOT treated as
    "nothing is wrong": the ledger is part of the protocol, so if it
    cannot be consulted the gate says so and blocks, the same way it
    fails closed everywhere else.
    """
    if not INCIDENT_CHECKER.is_file():
        return True, f"the incident checker is missing at {INCIDENT_CHECKER}"
    try:
        done = subprocess.run(
            [sys.executable, str(INCIDENT_CHECKER), REPO_NAME],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return True, f"the incident checker could not run ({type(error).__name__}: {error})"
    if done.returncode == 0:
        return False, ""
    return True, (done.stdout.strip() or done.stderr.strip() or "checker reported a blocking state")


def _is_release_push(args_after_push: list[str], root: Path) -> tuple[bool, str | None]:
    """Classify a push as release-grade from the refs it names.

    Release-grade if the args carry --tags/--follow-tags or an explicit
    version-tag argument. Returns ``(is_release, tagged_commit)`` where
    tagged_commit is the commit an explicit version tag resolves to (so
    the gate checks the attestation against the tag's target, not HEAD),
    or None when the release-ness comes from --tags with no explicit tag.
    """
    for tok in args_after_push:
        if tok in ("--tags", "--follow-tags"):
            return True, None
        if VERSION_TAG_TOKEN.match(tok):
            commit = _git(root, "rev-list", "-n", "1", tok)
            return True, (commit or None)
    return False, None


def main() -> None:
    """Evaluate the push gate on the PreToolUse payload from stdin."""
    # Out-of-scope calls (not a push, not a repo) allow silently; once a
    # push is recognized, every failure path denies (fail closed).
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Cannot read the command: if this hook fired at all it was on a
        # tool call, but with no command we cannot confirm a push, so stay
        # out of the way rather than block unrelated tools.
        _allow_silently()

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    is_push, git_c_path, args_after_push = _find_git_push(command)
    if not is_push:
        _allow_silently()

    try:
        base = Path(git_c_path) if git_c_path else Path.cwd()
        top = _git(base, "rev-parse", "--show-toplevel")
        if not top:
            # Looks like a git push but no repo resolves: fail closed.
            _decide(
                "deny",
                "role-review gate: this looks like a git push but no git repository "
                f"resolves from {base}. Run it from inside the repo (or fix the -C path); "
                "the gate must be able to check the role-review attestation before a push.",
            )
        root = Path(top)

        head = _git(root, "rev-parse", "HEAD")
        if not head:
            _decide(
                "deny",
                "role-review gate: could not read HEAD (no commits yet, or a detached or "
                "corrupt checkout). Make at least one commit and confirm `git rev-parse HEAD` "
                "succeeds from the repo root, then push.",
            )

        is_release, tagged_commit = _is_release_push(args_after_push, root)
        # The commit the attestation must cover: an explicit version tag's
        # target when pushing one, else the working-tree tip (HEAD).
        target = tagged_commit or head

        att_path = root / ATTESTATION
        try:
            att = json.loads(att_path.read_text(encoding="utf-8")) if att_path.is_file() else {}
        except (json.JSONDecodeError, ValueError, OSError):
            att = {}

        # An open blocking incident stops every push, before the review
        # question is even asked: no new work ships on top of a defect
        # whose structural cause is still unfixed.
        blocked, detail = _blocking_incidents()
        if blocked:
            _decide(
                "deny",
                "INCIDENT GATE: the shared incident ledger reports something that blocks a push "
                f"from {REPO_NAME}:\n{detail}\n"
                "Fix the incident at its structural cause, give it a guard and the evidence that "
                "the guard blocks the original failure, and set its status to fixed in "
                f"{INCIDENT_CHECKER.parent}. Marking it non-blocking to get past this gate is the "
                "failure this protocol exists to prevent; if it genuinely cannot reach a user or "
                "a repository, say so in blocking_reason and let the author decide.",
            )

        # The attestation must cover EVERY commit the push makes new, not
        # just the tip: checking the tip alone let unpushed ancestors ship
        # unreviewed (PLN-082).
        pushed = _pushed_commits(root, target)
        review = att.get("review") or {}
        covered = set(review.get("commits") or ([review["head"]] if review.get("head") else []))
        missing = [c for c in pushed if c not in covered]
        if missing:
            listed = ", ".join(c[:12] for c in missing[:8])
            more = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
            _decide(
                "deny",
                f"ROLE-REVIEW GATE: {len(missing)} of the {len(pushed)} commit(s) this push would "
                f"make new are not covered by any role-review attestation: {listed}{more}. "
                "Run the role-review skill (the specialist agents: architect, QA, V&V, tech "
                "writer, API designer as applicable) over the WHOLE pushed range, not only the "
                "tip, fix or register every finding, and let the skill write the attestation. Do "
                "NOT paraphrase the review as manual checks. If you amended or rebased since "
                "attesting, the commits changed: re-review and re-attest. Then push.",
            )

        if is_release:
            release = att.get("release") or {}
            rel_covered = set(
                release.get("commits") or ([release["head"]] if release.get("head") else [])
            )
            rel_missing = [c for c in pushed if c not in rel_covered]
            if rel_missing:
                _decide(
                    "deny",
                    "RELEASE GATE: this is a release-grade push (a version tag or --tags) but the "
                    f"release attestation does not cover {len(rel_missing)} of the {len(pushed)} "
                    "commit(s) being released. Run the release skill end to end (full-scope audit "
                    "plus the role-review sweep of every item), which writes the release "
                    "attestation over the whole range, before tagging or pushing the release.",
                )

        # Attestation covers the pushed commit: let the normal permission
        # flow proceed.
        _allow_silently()
    except Exception as error:  # noqa: BLE001 - a gate must fail closed
        _decide(
            "deny",
            "role-review gate: the gate could not be evaluated for this push "
            f"({type(error).__name__}: {error}). Failing closed. Resolve the error, or "
            "temporarily disable the hook via /hooks if it is the gate itself that is broken, "
            "then push.",
        )


if __name__ == "__main__":
    main()
