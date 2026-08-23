"""commit-msg guard: the Clean-room trailer must be in the FINAL paragraph.

FR-08 asks every commit after the baseline to declare its clean-room
provenance, and `tests/test_clean_room.py` checks it with
`git interpret-trailers`, which reads the LAST PARAGRAPH of the message
and nothing else. So a message carrying the line in a paragraph of its
own, followed by any other block, has no trailer at all as far as git is
concerned.

WHY THIS RUNS AT COMMIT TIME rather than only in tier 1. The tier-1 test
walks `BASELINE..HEAD`, so it fires only once the commit is immutable,
and its own failure message prescribes a remedy that cannot work for it:
"a commit that missed it is corrected by a follow-up commit that says
so" clears a per-change check, and this one is a walk. A follow-up adds
a passing commit and leaves the failing one in the population forever.
The only exits are rewriting history, moving the baseline, or an
exemption list, and two of those weaken the guard permanently.

Measured 2026-08-09: it happened. A commit put the trailer in its own
paragraph and the co-authorship block after it, tier 1 went red on an
unpushed release commit, and the release could not be tagged until the
message was rewritten. The trap is structural rather than careless,
because two conventions collide here: the repository wants Clean-room
last, and the commit tooling appends its own trailer block at the end.
Both are satisfied by putting every trailer in ONE final paragraph,
which is what git's own trailer convention expects anyway, and this hook
is what makes the requirement arrive while the message is still
editable.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REQUIRED = "Clean-room:"

GUIDANCE = """
The Clean-room trailer must be in the LAST paragraph of the message.

`git interpret-trailers` reads only the final block, so a Clean-room
line followed by a blank line and any other block is not a trailer and
the tier-1 guard will not see it. That guard walks every commit since
the baseline, so it cannot be cleared by a follow-up commit: fixing it
afterwards means rewriting history.

Put every trailer together in one final paragraph, the Clean-room line
unwrapped on a single line of its own:

    Clean-room: emitter specified from the official manual and probe
    evidence only; no code, structure or docstrings from the AGPL
    predecessor
    Co-Authored-By: ...
    Claude-Session: ...

(the three lines above are wrapped only so this file stays inside its
own line limit; write the trailer as one line)
"""  # noqa: E501


def main() -> int:
    """Refuse a commit message whose Clean-room line is not a trailer."""
    if len(sys.argv) < 2:
        print("usage: check_clean_room_trailer.py <commit-msg-file>", file=sys.stderr)
        return 2
    # utf-8-sig, not utf-8: a message file written by a Windows editor
    # (or by PowerShell's own `Set-Content -Encoding utf8`) carries a byte
    # order mark, and a leading U+FEFF makes the first line unparseable as
    # a subject and crashes the trailer call below on the console
    # codepage. The hook must survive the tooling of the machine it runs
    # on, and this one runs on Windows.
    raw = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
    # Comment lines are stripped by git before the message is stored, so
    # they are stripped here too: a `# Clean-room:` in the template would
    # otherwise pass a check the real message fails.
    message = "\n".join(line for line in raw.splitlines() if not line.startswith("#"))
    if not message.strip():
        return 0  # an empty message aborts the commit anyway
    if REQUIRED not in message:
        print(f"{GUIDANCE}\nThe message carries no Clean-room line at all.", file=sys.stderr)
        return 1
    parsed = subprocess.run(
        ["git", "interpret-trailers", "--parse"],
        input=message,
        capture_output=True,
        text=True,
        # Named rather than left to the locale: the default is the
        # console codepage on Windows, which is cp1252 here and cannot
        # encode a message carrying anything outside it.
        encoding="utf-8",
        check=False,
        # Explicit rather than inherited, which is what the repository's
        # spawn-environment guard asks of every call under `scripts/`.
        # `os.environ.copy()` is exactly what an omitted `env=` gives, so
        # nothing about the child changes; what changes is that the
        # inheritance is a decision at this call site.
        env=os.environ.copy(),
    )
    if not re.search(rf"^{re.escape(REQUIRED)}", parsed.stdout, re.M):
        print(GUIDANCE, file=sys.stderr)
        print(
            "The line is present but git does not read it as a trailer, which is "
            "exactly what the tier-1 guard will report after the commit exists.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
