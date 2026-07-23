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

        review = att.get("review") or {}
        if review.get("head") != target:
            _decide(
                "deny",
                "ROLE-REVIEW GATE: no role-review attestation for the commit being pushed "
                f"({target[:12]}). Run the role-review skill (the specialist agents: architect, "
                "QA, V&V, tech writer, API designer as applicable) over the pushed range, fix or "
                "register every finding, and let the skill write the attestation. Do NOT "
                "paraphrase the review as manual checks. If you amended or rebased since "
                "attesting, the commit changed: re-review the new range and re-attest. Then push.",
            )

        if is_release:
            release = att.get("release") or {}
            if release.get("head") != target:
                _decide(
                    "deny",
                    "RELEASE GATE: this is a release-grade push (a version tag or --tags) but "
                    f"there is no release attestation for {target[:12]}. Run the release skill "
                    "end to end (full-scope audit plus the role-review sweep of every item), "
                    "which writes the release attestation, before tagging or pushing the release.",
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
