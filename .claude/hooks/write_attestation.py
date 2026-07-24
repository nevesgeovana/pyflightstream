#!/usr/bin/env python3
"""Write the role-review or release attestation that clears the push gate.

Usage:
    python .claude/hooks/write_attestation.py review <passes> [<ref> ...]
    python .claude/hooks/write_attestation.py release <passes> [<ref> ...]

<ref> is each branch, tag, or commit being attested, defaulting to
HEAD. Pass every ref the push names. The gate scopes by ref while this
script once scoped by HEAD alone, so a tag sitting behind HEAD was
denied with a message naming a command that could not clear it, and a
two-ref push could not be attested at all because the second run
overwrote the first.

<passes> is a comma-separated list of the reviewer passes that actually
ran (architect,qa,vv,tech-writer,api-designer). It is required and
validated: an unknown token is refused rather than recorded, because
this file is an audit record and a silently mistyped one is worse than
none. The attestation stamps every resolved ref together with every
commit not yet on a remote, which is the range the next push would make
new; the git-push gate (role_review_gate.py) allows the push only while
that list covers every commit in scope, including the refs themselves.

Run this ONLY after the specialist agents have actually run and their
findings are fixed or registered. Stamping without running the agents
defeats the protocol this file exists to enforce. The ``passes`` field
is an audit annotation, not an enforced gate input: the gate checks
only that an attestation covers the pushed range, so the honesty of
the passes list rests on the operator, not the mechanism.

The record's timestamp is the committer date of the first commit the
attestation covers, normally the first resolved ref
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
KNOWN_PASSES = ("architect", "qa", "vv", "tech-writer", "api-designer")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()


def main() -> int:
    """Stamp the resolved ref into the attestation for the given kind."""
    usage = f"usage: write_attestation.py {'|'.join(KINDS)} <{','.join(KNOWN_PASSES)}> [<ref> ...]"
    if len(sys.argv) < 3 or sys.argv[1] not in KINDS:
        print(usage, file=sys.stderr)
        return 2
    kind = sys.argv[1]
    passes = [p.strip() for p in sys.argv[2].split(",") if p.strip()]
    unknown = [p for p in passes if p not in KNOWN_PASSES]
    if not passes or unknown:
        # The likeliest slip is passing the ref here, now that the ref
        # matters. Recording it as a pass would put a fabricated audit
        # line in the one file whose whole job is being trustworthy.
        print(
            f"unknown or empty passes {unknown or ['(none given)']}; expected a "
            f"comma-separated subset of {list(KNOWN_PASSES)}. "
            "A ref goes in the third argument.\n" + usage,
            file=sys.stderr,
        )
        return 2

    refs = sys.argv[3:] or ["HEAD"]

    top = _git(Path.cwd(), "rev-parse", "--show-toplevel")
    if not top:
        print("not a git repository", file=sys.stderr)
        return 1
    root = Path(top)
    # The commits this attestation covers: for every named ref, the ref
    # itself plus everything reachable from it that is not yet on any
    # remote, which is exactly what the next push would make newly
    # available. Stamping only HEAD let unpushed ancestors ship
    # unreviewed, and stamping one ref made a two-ref push unattestable
    # because the second run overwrote the first.
    commits: list[str] = []
    for ref in refs:
        tip = _git(root, "rev-list", "-n", "1", ref)
        if not tip:
            print(f"could not resolve {ref}", file=sys.stderr)
            return 1
        listed = _git(root, "rev-list", tip, "--not", "--remotes")
        commits.extend(c for c in listed.splitlines() if c)
        commits.append(tip)
    commits = list(dict.fromkeys(commits))
    head = commits[0]
    # Stamp the first resolved ref's committer date (%cI): deterministic,
    # no wall-clock dependency.
    when = _git(root, "show", "-s", "--format=%cI", head)

    att_path = root / ATTESTATION
    try:
        att = json.loads(att_path.read_text(encoding="utf-8")) if att_path.is_file() else {}
    except (json.JSONDecodeError, ValueError, OSError):
        att = {}

    entry: dict[str, object] = {
        "head": head,
        "commits": commits,
        "refs": refs,
        "passes": passes,
    }
    if when:
        entry["commit_date"] = when
    att[kind] = entry

    att_path.parent.mkdir(parents=True, exist_ok=True)
    att_path.write_text(json.dumps(att, indent=2) + "\n", encoding="utf-8")
    print(
        f"{kind} attestation written for {' '.join(refs)}, covering "
        f"{len(commits)} commit(s) (passes: {', '.join(passes)})"
    )
    if len(commits) > 1:
        print(
            "  NOTE: more than one commit is unpushed, so the review had to "
            "cover the whole range, not just the tip. If it did not, "
            "re-review before pushing.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
