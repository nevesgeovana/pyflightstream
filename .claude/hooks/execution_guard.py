# ITACA / pyflightstream shared process kit
# kit-version: 0.2.22
# artifact: execution_guard.py
# body-sha256: 2ebfc38bd69cf625971385834c05f0b189d1121ce78d324a950c568cc32ccf5b
# canonical-source: BUILT for the kit 2026-08-11 (BRF-079 step 2). A PreToolUse guard for the two shell shapes that have actually corrupted files or produced a false green in these repositories: a status-bearing command whose exit code is read through a pipe, and a heredoc carrying a backslash or a non-printable byte. Deliberately NOT a blanket heredoc ban: 12 tracked files across the three trees carry heredocs and the kit fixed a heredoc defect at 0.2.1 by correcting rather than forbidding, and a guard that fires on ordinary use is one people learn to work around.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""PreToolUse guard for two shell shapes with a measured history here.

WHY THIS EXISTS AND WHY IT IS NARROW. `BRF-079` read the /insights report
of 2026-08-11, which recommended banning heredocs outright and banning
piped exit-status reads. The ban was narrowed before it became a guard,
on this project's own reasoning at kit 0.2.9: a guard that fires on
ordinary use is a guard people learn to work around. Measured at the
time: twelve tracked files across the three repositories carry heredocs,
`git commit -F -` is ordinary, and the kit already fixed a heredoc defect
at 0.2.1 by CORRECTING rather than forbidding.

So this guard refuses exactly two shapes, both mechanically decidable
without judging intent:

ARM 1, THE PIPED STATUS. A command from ``STATUS_BEARING`` piped into a
line filter (``head``, ``tail``, ``wc``). A pipeline's exit status is the
LAST element's, not the checker's, so a red suite read through ``| tail``
reports green. The general rule cannot be automated, because a hook
cannot know whether a status matters. This arm does not try: it carries a
list of commands whose status ALWAYS matters, which is why the list is
short and why adding to it is a decision rather than a convenience. The
remedy is in the message: run it unpiped, or capture to a file and read
the status from the process.

ARM 2, THE CORRUPTING HEREDOC. A heredoc whose body carries a backslash
or a non-printable byte. This is the shape that mangled files here, not
heredocs as such. A QUOTED delimiter (``<<'EOF'``) disables shell
expansion and is exempt from the backslash half, since that is the form
that survives; the control-byte half applies to both, because no quoting
protects a parser from a stray ``\\x01``.

WHAT IT DOES NOT COVER, stated so it is not read as wider than it is. It
sees one command string at a time, so it cannot catch a status discarded
across two tool calls. It does not inspect files the command reads or
writes. And it judges no other pipeline: ``grep``, ``jq`` and the rest
lose a status exactly as ``tail`` does, and are not listed, because the
measured failures were the filters above and a list grown by imagination
is the allowlist failure the 2026-07-23 review already rejected once.

Exit codes: this is a hook, so it always exits 0 and speaks through the
PreToolUse JSON contract. Silence means out of scope.

Usage (as a PreToolUse hook, payload on stdin):
    execution_guard.py
"""

from __future__ import annotations

import json
import re
import sys

PREFIX = "execution guard: "

# Commands whose exit status ALWAYS matters. Short by design: every entry
# is a thing that answers red or green, and the guard's precision comes
# from the list being about status rather than about danger.
STATUS_BEARING = (
    "pytest",
    "mypy",
    "ruff",
    "git push",
)

# Script-shaped members of the same class, matched on the basename so a
# path prefix does not defeat them.
STATUS_BEARING_PATTERNS = (
    re.compile(r"\bcheck_[\w.\-]*\.py\b"),
    re.compile(r"\b[\w.\-]*_mutations\.py\b"),
    re.compile(r"\bverify_[\w.\-]*\.py\b"),
)

# The line filters that discard a status, in BOTH shells this guard is
# wired for. Deliberately not extended to every filter that would: see the
# docstring and the named gap below.
#
# 0.2.22 ADDS THE POWERSHELL HALF, routed by itaca as ITC-20260811-2250 and
# reproduced by importing the vendored body. At 0.2.20 the pattern was
# `head|tail|wc` alone while the hook's matcher was `Bash|PowerShell`, so on
# a repository whose primary shell IS PowerShell the guard refused nothing it
# could express: `pytest -q | Select-Object -Last 5` returned no offence and
# `pytest -q | tail -5` did. A guard armed on one half of its own matcher is
# worse to reason about than one whose scope is stated, because its silence
# reads as a pass.
#
# PowerShell is case-insensitive, so its alternatives carry an inline flag
# while the bash ones stay case-sensitive, which is what each shell actually
# does.
#
# THE NAMED GAP, stated so it is falsifiable rather than discovered: in
# PowerShell EVERY terminal cmdlet owns `$?`, so `| Out-String` and
# `| ForEach-Object` discard a status exactly as `Select-Object` does. They
# are NOT listed, for two reasons that are recorded rather than assumed. They
# do not drop lines, so an operator reading the output still sees all of it;
# and `$LASTEXITCODE` survives a PowerShell pipeline, so the native status is
# still recoverable, which is not true of `$?` in bash. If that reasoning
# turns out to be wrong, this is the line to change.
_BASH_FILTERS = r"(?:head|tail|wc)"
_PS_FILTERS = r"(?i:Select-Object|Measure-Object|select|measure)"
LINE_FILTERS = re.compile(rf"\|\s*(?:{_BASH_FILTERS}|{_PS_FILTERS})\b")

# ``<<`` or ``<<-`` then an optionally quoted delimiter.
HEREDOC_OPEN = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

# Anything outside printable ASCII plus tab, newline and carriage return.
CONTROL_BYTE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


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


def _is_status_bearing(segment: str) -> str | None:
    """Return the matched status-bearing token in this pipeline segment."""
    for name in STATUS_BEARING:
        if re.search(r"(?<![\w.\-])" + re.escape(name) + r"(?![\w.\-])", segment):
            return name
    for pattern in STATUS_BEARING_PATTERNS:
        found = pattern.search(segment)
        if found:
            return found.group(0)
    return None


def _without_data_spans(command: str) -> str:
    """Blank heredoc bodies and quoted spans, keeping every offset valid.

    FOUND BY USING THIS GUARD, twice within its first hour, and both were
    false positives rather than catches. Arm 1 scanned the raw string, so
    a checker NAMED AS DATA counted as a command upstream of any later
    filter. First: a logbook entry describing `verify_hub.py` being
    piped, written into a heredoc, in a command that separately ended
    with `| head -2`. Second: `grep -n "run:.*pytest" file | head -20`,
    where `pytest` is the SEARCH PATTERN and nothing runs it.

    They are one class. A command name inside a heredoc body, a quoted
    search pattern or a commit message is text being handled, not a
    process being started. Both spans are blanked before arm 1 looks.

    THE MISS THIS BUYS, and it is deliberate: a quoted path to an
    executable (`python "kit/check_x.py" | tail`) is blanked too and will
    not be caught. That is accepted because a false POSITIVE gets a guard
    switched off, which is this kit's own reasoning at 0.2.9, and because
    a quoted executable path piped into a filter is rarer here than a
    checker named in a pattern or a message.

    Spans are replaced with spaces rather than removed so every offset
    the caller slices on still refers to the same position.

    0.2.22 SPLITS THE MASK OUT of this function so ARM 2 can use it too.
    See `_data_mask`; the string this returns is unchanged.
    """
    mask = _data_mask(command)
    return "".join(" " if mask[i] else ch for i, ch in enumerate(command))


def _data_mask(command: str) -> list[bool]:
    """True at every offset that is DATA rather than a command position.

    EXTRACTED AT 0.2.22 BECAUSE ARM 2 NEEDED IT AND DID NOT HAVE IT.
    itaca routed `ITC-20260811-2250`'s sibling, `ITC-20260811-2240`: arm 1
    called `_without_data_spans` before scanning and arm 2 called nothing,
    so a heredoc opener merely NAMED inside an already-quoted heredoc body
    was parsed as a real opener and refused. Reproduced with a control: the
    same quoted heredoc WITHOUT the opener spelled in its body was silent,
    so the refusal turned on prose and not on a shell construct.

    THAT INSTANCE WAS WORSE THAN THE THREE BEFORE IT, which is why it was
    fixed rather than documented. The other three are answered by quoting
    the offending token, and the guard's own text says so. This one is
    already inside the strongest quoting the shell offers, so the operator
    had NO remedy at all. A guard with no remedy is worse than a missing
    guard, because it teaches people to route around guards.

    Newlines are never marked, so the line-anchored searches that find a
    heredoc terminator still see the line structure they need.

    An unterminated quote marks to the end of the string, which is the
    conservative direction for both arms: the guard sees less and denies
    less, and it never denies on text it failed to parse.
    """
    mask = [False] * len(command)

    for opener in HEREDOC_OPEN.finditer(command):
        rest = command[opener.end():]
        end = re.search(
            r"^\s*" + re.escape(opener.group(2)) + r"\s*$", rest, re.M
        )
        stop = opener.end() + (end.start() if end else len(rest))
        for i in range(opener.end(), stop):
            if command[i] != "\n":
                mask[i] = True

    quote = None
    for i, ch in enumerate(command):
        if quote is None:
            if ch in "'\"":
                quote = ch
        elif ch == quote:
            quote = None
            mask[i] = True
            continue
        if quote is not None and command[i] != "\n":
            mask[i] = True

    return mask


def piped_status_offence(command: str) -> str | None:
    """A status-bearing command whose status is discarded by a filter.

    Only the text BEFORE the filter is examined for the checker, so a
    filter that merely appears later in an unrelated pipeline does not
    implicate an earlier command it does not consume. Heredoc bodies are
    blanked first, along with quoted spans: both are DATA being handled,
    not processes being started. See _without_data_spans.
    """
    scannable = _without_data_spans(command)
    match = LINE_FILTERS.search(scannable)
    if not match:
        return None
    upstream = scannable[: match.start()]
    name = _is_status_bearing(upstream)
    if not name:
        return None
    return name


def heredoc_offence(command: str) -> str | None:
    """A heredoc body carrying a backslash or a non-printable byte.

    The delimiter's quoting decides the backslash half only. A quoted
    delimiter (``<<'PY'``) disables expansion, which is the form that
    survives, so a backslash inside it is not the failure this arm was
    built from. No quoting protects a downstream parser from a control
    byte, so that half applies to every heredoc.

    AN OPENER THAT SITS INSIDE A DATA SPAN IS NOT AN OPENER. Added at
    0.2.22 for `ITC-20260811-2240`: this arm used to scan the raw string,
    so `<<EOF` spelled inside an already-quoted heredoc body counted as a
    real opener and the arm refused a command containing no such heredoc.
    Only the OPENER's position is tested against the mask; the body is
    still read from the raw command, because a real heredoc's body is
    exactly what this arm exists to inspect.
    """
    mask = _data_mask(command)
    for opener in HEREDOC_OPEN.finditer(command):
        if mask[opener.start()]:
            continue
        quoted = bool(opener.group(1))
        delimiter = opener.group(2)
        rest = command[opener.end():]
        end = re.search(r"^\s*" + re.escape(delimiter) + r"\s*$", rest, re.M)
        body = rest[: end.start()] if end else rest
        if CONTROL_BYTE.search(body):
            return f"a non-printable byte inside the <<{delimiter} body"
        if not quoted and "\\" in body:
            return (
                f"a backslash inside the unquoted <<{delimiter} body, which "
                f"the shell will consume"
            )
    return None


def main() -> None:
    """Evaluate the two arms on the PreToolUse payload from stdin."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # A payload this guard cannot read is not a violation it can
        # assert. It stays silent rather than denying, because unlike the
        # push gate this guard protects against a mistake and not against
        # an irreversible act, so failing closed here would block ordinary
        # work on a parsing problem of its own.
        _allow_silently()

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    if not command.strip():
        _allow_silently()

    name = piped_status_offence(command)
    if name:
        _decide(
            "deny",
            PREFIX
            + f"[piped-status] `{name}` is piped into a line filter, so the "
            "exit status you read back is the filter's and not the "
            "checker's. A red suite reports green this way, and it has. Run "
            "it unpiped, or redirect to a file and read the status from the "
            "process.",
        )

    why = heredoc_offence(command)
    if why:
        _decide(
            "deny",
            PREFIX
            + f"[heredoc-content] {why}. Heredocs are fine and are not what "
            "this refuses; content that a shell rewrites on its way through "
            "one is. Author this with Write or Edit instead.",
        )

    _allow_silently()


if __name__ == "__main__":
    main()
