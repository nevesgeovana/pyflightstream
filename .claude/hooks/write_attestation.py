# ITACA / pyflightstream shared process kit
# kit-version: 0.2.15
# artifact: write_attestation.py
# body-sha256: 6c70a673f88d0eebffcdbc048e90db7e1f064ec6af0e49d0b75b517435f982ec
# canonical-source: itaca. No divergence between the copies. 0.2.15 adds ATTEST-SCOPE, the per-pass commit scope and the uncovered-commit list, from lane ITA-2G declaring against itself that two of its commits carried no lens while the record said only which passes ran. The gate's input is unchanged: it reads commits and refs and has never read passes, so no allow or deny decision moves. See coordination/DESIGN_HUB-11_kit_batch.md item 5.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
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
ran, drawn from KNOWN_PASSES below. It is required and validated: an
unknown token is refused rather than recorded, because this file is an
audit record and a silently mistyped one is worse than
none.

A pass may carry its own SCOPE, as ``name@<range>``, and this is the
0.2.15 addition::

    write_attestation.py review "architect@6950c0b..053dd98,\\
        qa@6950c0b..053dd98,vv@053dd98..a9d7a99" HEAD

WHY, and it was declared by a lane against itself rather than found.
Until 0.2.15 this file recorded WHICH PASSES RAN and never WHICH
COMMITS EACH COVERED, so an attestation naming three lenses over
twelve commits read as three lenses over twelve commits. Lane ITA-2G
ran architect, QA and V&V over one range and a second V&V over the
closure commit, and two further commits carried NO LENS AT ALL: a
one-line pytest marker and a verbatim restoration of the author's own
files. Its handoff said so in prose, and the machine-readable record
next to it did not. A record that reads as covering more than it did is
the failure this whole file exists to avoid.

So a scoped pass records the commits it actually covered, and the
writer reports the commits that NO pass covers. It does NOT refuse
them: ITA-2G's two uncovered commits were a correct, deliberate
decision, and a writer that refused it would make the honest record
unwritable, which is how a record starts being worked around. The
uncovered list is printed loudly and stored, so the fact is in the file
rather than in a handoff someone has to find.

BACKWARD COMPATIBLE, deliberately. A bare ``<passes>`` list, with no
``@``, means exactly what it means today: every named pass covers every
commit the attestation covers. A consumer that has not re-vendored its
skills is not broken by re-vendoring this file.

The attestation stamps every resolved ref together with every
commit not yet on a remote, which is the range the next push would make
new; the git-push gate (role_review_gate.py) allows the push only while
that list covers every commit in scope, including the refs themselves.

Run this ONLY after the specialist agents have actually run and their
findings are fixed or registered. Stamping without running the agents
defeats the protocol this file exists to enforce. The ``passes`` field
is an audit annotation, not an enforced gate input: the gate checks
only that an attestation covers the pushed range, so the honesty of
the passes list rests on the operator, not the mechanism.

What the kit 0.2.6 vocabulary bump does, stated exactly, because the
temptation is to read it as more. Until 0.2.6 the tuple below held five
tokens and no numerical pass could be RECORDED, so none was required,
so none ran; two independent reviews then found blockers whose
numerical share had never been re-derived by anyone. Adding
``numerical-analyst`` and ``integration-reviewer`` removes a MECHANICAL
bar and nothing else. A recordable pass is still not a required pass:
this file records what the operator says ran, the gate still never
reads the field, and neither token makes a lens fire. What changed is
only that the honest answer became expressible.

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
# The audit vocabulary. CLOSED, exact-match, and permanent: validation is
# `p not in KNOWN_PASSES`, so whatever is spelled here is the spelling every
# attestation ever written is read back with. Lowercase and hyphenated
# throughout, and each token names the ROLE that ran the pass rather than the
# agent file carrying it (`architect`, not `architecture-reviewer`).
#
# The two 0.2.6 additions, and why each is spelled this way:
# - `numerical-analyst` names the author's non-delegable seat exactly as the
#   coordination charter names it. Bare `numerical` was rejected: it is an
#   adjective, and in an audit record for libraries whose test tiers are
#   numbered it reads as "numerical tests ran", which is a different claim.
# - `integration-reviewer` deliberately KEEPS the `-reviewer` suffix and so
#   breaks the role-not-agent pattern above, for one reason: the role has no
#   one-word name, and bare `integration` would read as integration TESTING.
#   Ambiguity is cheapest to remove here and permanent everywhere else.
KNOWN_PASSES = (
    "architect",
    "qa",
    "vv",
    "tech-writer",
    "api-designer",
    "numerical-analyst",
    "integration-reviewer",
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()


def main() -> int:
    """Stamp the resolved ref into the attestation for the given kind."""
    usage = (
        f"usage: write_attestation.py {'|'.join(KINDS)} "
        f"<{','.join(KNOWN_PASSES)}> [<ref> ...]\n"
        "       a pass may carry its own scope as name@<range>, "
        "for example qa@6950c0b..053dd98"
    )
    if len(sys.argv) < 3 or sys.argv[1] not in KINDS:
        print(usage, file=sys.stderr)
        return 2
    kind = sys.argv[1]
    # `name` or `name@<range>`. The scope half is optional per pass, so a
    # mixed list is legal and means what it reads as: the scoped passes
    # cover their ranges and the bare ones cover everything.
    scopes: dict[str, str] = {}
    passes: list[str] = []
    for token in sys.argv[2].split(","):
        token = token.strip()
        if not token:
            continue
        name, sep, rng = token.partition("@")
        name = name.strip()
        passes.append(name)
        if sep:
            if not rng.strip():
                print(f"pass {name!r} carries an empty scope after '@'; "
                      "give a revision range, or drop the '@'.",
                      file=sys.stderr)
                return 2
            scopes[name] = rng.strip()
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
    # REFUSE WHILE TRACKED FILES CARRY UNCOMMITTED CHANGES. Kit 0.2.9, from
    # INC-20260729-2355-itaca: a reviewer agent holding Bash restored tracked
    # files with git while a lane held uncommitted review fixes, silently
    # reverting two of nine files. The attestation written next would have been
    # TRUE when written and FALSE about the tree it covered, which is the one
    # failure this file cannot survive: it records that findings were fixed,
    # over commits that no longer contain the fixes.
    #
    # UNTRACKED PATHS DO NOT REFUSE, and that boundary is deliberate rather than
    # lenient. An untracked file is in no commit this attestation covers, so it
    # cannot be a reviewed fix that went missing, which is the failure mode.
    # Refusing on untracked would also make the guard unusable in any repository
    # that legitimately carries scratch, and a guard routinely worked around is
    # worse than none. They are reported so the operator sees what is excluded.
    status = _git(root, "status", "--porcelain")
    lines = [line for line in status.splitlines() if line.strip()]
    tracked_dirty = [line for line in lines if not line.startswith("??")]
    if tracked_dirty:
        shown = "\n  ".join(tracked_dirty[:20])
        more = "" if len(tracked_dirty) <= 20 else (
            f"\n  ... and {len(tracked_dirty) - 20} more"
        )
        print(
            f"refusing to write an attestation: {len(tracked_dirty)} tracked "
            "path(s) carry uncommitted changes, so this record would cover "
            "commits that do not contain them.\n  "
            f"{shown}{more}\n"
            "Commit or stash them, then attest. Untracked paths are exempt and "
            "are not listed here.",
            file=sys.stderr,
        )
        return 1
    untracked = [line for line in lines if line.startswith("??")]
    if untracked:
        print(
            f"note: {len(untracked)} untracked path(s) present. They are in no "
            "commit this attestation covers and are deliberately not blocking.",
            file=sys.stderr,
        )
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
        att = (
            json.loads(att_path.read_text(encoding="utf-8"))
            if att_path.is_file()
            else {}
        )
    except (json.JSONDecodeError, ValueError, OSError):
        att = {}

    # Per-pass scope, and the commits no pass covers. Resolved against the
    # SAME `commits` list the gate reads, so the two can never describe
    # different ranges. A range that reaches commits already on a remote is
    # kept in the pass's own record and ignored for the coverage arithmetic:
    # reviewing more than the push makes new is not an error.
    pass_scope: dict[str, list[str]] = {}
    for name in passes:
        if name not in scopes:
            pass_scope[name] = list(commits)
            continue
        listed = _git(root, "rev-list", scopes[name])
        resolved = [c for c in listed.splitlines() if c]
        if not resolved:
            print(f"could not resolve the scope {scopes[name]!r} for pass "
                  f"{name!r}", file=sys.stderr)
            return 1
        pass_scope[name] = resolved
    covered = {c for scope in pass_scope.values() for c in scope}
    uncovered = [c for c in commits if c not in covered]

    entry: dict[str, object] = {
        "head": head,
        "commits": commits,
        "refs": refs,
        "passes": passes,
        "pass_scope": pass_scope,
        "uncovered": uncovered,
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
    if uncovered:
        # Printed rather than refused. Two commits carrying no lens was a
        # correct call once and will be again; what was wrong was that the
        # record did not say so.
        shown = "\n  ".join(uncovered[:20])
        more = "" if len(uncovered) <= 20 else (
            f"\n  ... and {len(uncovered) - 20} more"
        )
        print(
            f"  NOTE: {len(uncovered)} commit(s) in this attestation are "
            "covered by NO pass:\n  "
            f"{shown}{more}\n"
            "  That is recorded in the attestation's `uncovered` field. If "
            "it was deliberate, say why in the handoff; if it was not, "
            "review them and attest again.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
