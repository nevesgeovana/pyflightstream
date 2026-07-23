#!/usr/bin/env python3
"""Write the role-review or release attestation that clears the push gate.

Usage:
    python .claude/hooks/write_attestation.py review <passes>
    python .claude/hooks/write_attestation.py release <passes>

<passes> is a comma-separated list of the reviewer passes that actually
ran (architect,qa,vv,tech-writer,api-designer). The attestation stamps
the current HEAD; the git-push gate (role_review_gate.py) allows the
push only while the stamped head equals the commit being pushed.

Run this ONLY after the specialist agents have actually run and their
findings are fixed or registered. Stamping without running the agents
defeats the protocol this file exists to enforce. The ``passes`` field
is an audit annotation, not an enforced gate input: the gate checks
only that an attestation covers the pushed commit, so the honesty of
the passes list rests on the operator, not the mechanism.

The record's timestamp is the HEAD commit's committer date
(``git show -s --format=%cI``), so it is deterministic and free of any
wall clock; if unavailable it is omitted. No network, no third-party
deps. The attestation path is duplicated in role_review_gate.py and
.gitignore; a rename must touch all three.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ATTESTATION = ".claude/.role_review_attestation.json"
KINDS = ("review", "release")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()


def main() -> int:
    """Stamp the current HEAD into the attestation for the given kind."""
    if len(sys.argv) < 2 or sys.argv[1] not in KINDS:
        print(
            f"usage: write_attestation.py {'|'.join(KINDS)} <comma,separated,passes>",
            file=sys.stderr,
        )
        return 2
    kind = sys.argv[1]
    passes = [p.strip() for p in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if p.strip()]

    top = _git(Path.cwd(), "rev-parse", "--show-toplevel")
    if not top:
        print("not a git repository", file=sys.stderr)
        return 1
    root = Path(top)
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        print("could not resolve HEAD", file=sys.stderr)
        return 1
    # The commits this attestation covers: everything reachable from HEAD
    # that is not yet on any remote, which is exactly what the next push
    # would make newly available. Stamping only HEAD let unpushed
    # ancestors ship unreviewed (PLN-082): the gate compares this list
    # against the range the push actually moves.
    listed = _git(root, "rev-list", head, "--not", "--remotes")
    commits = [c for c in listed.splitlines() if c] or [head]
    # Stamp the HEAD commit's committer date (%cI): deterministic, no
    # wall-clock dependency.
    when = _git(root, "show", "-s", "--format=%cI", head)

    att_path = root / ATTESTATION
    try:
        att = json.loads(att_path.read_text(encoding="utf-8")) if att_path.is_file() else {}
    except (json.JSONDecodeError, ValueError, OSError):
        att = {}

    entry: dict[str, object] = {"head": head, "commits": commits}
    if when:
        entry["commit_date"] = when
    if passes:
        entry["passes"] = passes
    att[kind] = entry

    att_path.parent.mkdir(parents=True, exist_ok=True)
    att_path.write_text(json.dumps(att, indent=2) + "\n", encoding="utf-8")
    print(
        f"{kind} attestation written for {head[:12]}, covering {len(commits)} unpushed commit(s)"
        + (f" (passes: {', '.join(passes)})" if passes else "")
    )
    if len(commits) > 1:
        print(
            "  NOTE: more than one commit is unpushed, so the review had to cover the whole "
            "range, not just the tip. If it did not, re-review before pushing.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
