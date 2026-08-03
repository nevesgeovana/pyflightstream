"""Tier 1: every commit under review declares its clean-room provenance.

FR-08 says the emitter's clean-room provenance "is verified by the
contribution attestation recorded per change". Measured on 2026-07-28
and unchanged until this module: 200 commits, 0 `Signed-off-by`
trailers, no per-change attestation of any kind, versioned or
otherwise. The requirement's evidence line named a mechanism that had
never existed (review finding PYFS-021, hub brief BRF-047).

The author chose route A on 2026-08-03: make the named mechanism exist,
rather than reword FR-08 to promise less. So each commit carries a
trailer declaring what FR-08 claims, and this test asserts it.

WHAT THIS PROVES, and the limit is the point rather than a caveat.
Nothing can prove the absolute negative "the AGPL predecessor was never
read". What a process CAN preserve is a DECLARATION and an auditable
record of who made it: the trailer is the declaration, the commit's
author and date are the record. That is the honest frame, and FR-08's
evidence line now names a mechanism that is really there.

Why the check is not retroactive: the 200 commits before the baseline
carry no trailer, and adding one to them would mean rewriting history
to manufacture a declaration nobody made. The baseline is written down
below with the date, so the boundary is a fact rather than a gap.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: The trailer key, and the declaration its value must carry. Both
#: pinned: a trailer whose value degraded to "yes" would satisfy a
#: presence check while declaring nothing.
TRAILER = "Clean-room"
DECLARATION = (
    "emitter specified from the official manual and probe evidence only; "
    "no code, structure or docstrings from the AGPL predecessor"
)

#: The commit this convention starts AFTER. Everything reachable from
#: HEAD and not from this commit must declare. Chosen as the tip at the
#: moment the convention landed (2026-08-03), so the first declaring
#: commit is the one that introduced this file and is itself checked.
BASELINE = "259a7d1650ce240d6ab2b7ecb6482fc6b8efc303"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def _commits_under_review() -> list[str]:
    """Commit hashes from the baseline to HEAD, newest first."""
    result = _git("rev-list", f"{BASELINE}..HEAD")
    assert result.returncode == 0, (
        f"git could not list commits since the clean-room baseline {BASELINE[:7]} "
        f"(exit {result.returncode}: {result.stderr.strip()}).\n\n"
        "In CI this means the checkout is SHALLOW and the baseline is not in it: "
        "set `fetch-depth: 0` on actions/checkout for the job that runs pytest. "
        "This test fails rather than skips, because a provenance guard that "
        "reports nothing when it cannot run reports green."
    )
    commits = [line for line in result.stdout.split() if line]
    assert commits, (
        f"no commit is reachable from HEAD and not from the baseline "
        f"{BASELINE[:7]}, so this guard would examine nothing and pass.\n\n"
        "Either HEAD is the baseline (nothing to review, which is not a state "
        "this repository pushes from), or the checkout is shallow: set "
        "`fetch-depth: 0` on actions/checkout for the job that runs pytest."
    )
    return commits


def _trailer_values(commit: str) -> list[str]:
    """Return the Clean-room trailer values of one commit, via git.

    Git's own trailer parser rather than a line scan over the message,
    and the difference is not cosmetic: this guard failed on its own
    first commit because that message QUOTES the trailer in its body to
    explain it, wrapped across three lines, and a scan for the first
    line starting with the key found the quoted fragment. Git knows a
    trailer is a key-value line in the LAST paragraph, which is exactly
    the distinction the scan was missing.
    """
    result = _git(
        "log", "-1", f"--format=%(trailers:key={TRAILER},valueonly,separator=%x1f)", commit
    )
    assert result.returncode == 0, f"cannot read the trailers of {commit}"
    return [value.strip() for value in result.stdout.strip().split("") if value.strip()]


def _subject(commit: str) -> str:
    result = _git("log", "-1", "--format=%s", commit)
    return result.stdout.strip()


def test_the_baseline_is_a_commit_in_this_history():
    """Guard the guard: a baseline nobody can resolve checks nothing.

    A mistyped or rewritten baseline would make the range empty or the
    range command fail, and an empty range passes every assertion below
    without examining anything.
    """
    result = _git("cat-file", "-e", f"{BASELINE}^{{commit}}")
    assert result.returncode == 0, (
        f"the clean-room baseline {BASELINE} is not a commit in this repository. "
        "It is a fixed point in history and never changes; if history was "
        "rewritten, that is the thing to investigate, not this constant."
    )


def _classify(values: list[str]) -> str:
    """Verdict for one commit's trailer values: ok, missing or degraded.

    Factored out so both branches can be exercised directly. A mutation
    pass showed why: disabling the presence check still turned the suite
    red, through the value check, because a commit with no trailer also
    has no MATCHING trailer. Two branches that a mutation cannot tell
    apart are two branches only one of which is really tested.
    """
    if not values:
        return "missing"
    if not any(" ".join(value.split()) == DECLARATION for value in values):
        return "degraded"
    return "ok"


def test_the_classification_separates_absent_from_weakened():
    """Each verdict on its own input, which mutation could not isolate."""
    assert _classify([]) == "missing"
    assert _classify(["yes"]) == "degraded"
    assert _classify(["from the manual"]) == "degraded"
    assert _classify([DECLARATION]) == "ok"
    # Git folds a wrapped trailer; the comparison collapses whitespace,
    # so a message that wrapped the declaration still declares it.
    folded = DECLARATION.replace(" ", chr(10) + "  ", 1)
    assert _classify([folded]) == "ok"


def test_an_unreachable_baseline_fails_rather_than_reporting_nothing(monkeypatch):
    """The failure mode this repository keeps registering.

    In CI an unreachable baseline means a shallow checkout. Returning an
    empty range there would pass every assertion while examining no
    commit at all, so the range command asserts on its own exit code and
    the message names fetch-depth.
    """
    monkeypatch.setattr(
        "test_clean_room._git",
        lambda *args: subprocess.CompletedProcess(args, 128, "", "fatal: bad object"),
    )
    with pytest.raises(AssertionError, match="fetch-depth"):
        _commits_under_review()


def test_every_commit_since_the_baseline_declares_its_provenance():
    """The mechanism FR-08's evidence line names, made to exist.

    Runs over the commits a push would make new, which is the same range
    the role-review attestation covers, so the declaration and the
    review cover the same work.
    """
    missing = []
    degraded = []
    for commit in _commits_under_review():
        values = _trailer_values(commit)
        verdict = _classify(values)
        if verdict == "missing":
            missing.append(f"{commit[:7]} {_subject(commit)[:60]}")
        elif verdict == "degraded":
            degraded.append(f"{commit[:7]} {values[0][:90]}")
    assert not missing, (
        f"these commits carry no {TRAILER} trailer:\n  " + "\n  ".join(missing) + "\n\n"
        f"Every commit after {BASELINE[:7]} declares its clean-room provenance "
        "(FR-08). Add this as the last paragraph of the commit message:\n\n"
        f"    {TRAILER}: {DECLARATION}\n\n"
        "Amending is banned in this repository, so a commit that missed it is "
        "corrected by a follow-up commit that says so."
    )
    assert not degraded, (
        f"these commits carry a {TRAILER} trailer whose value is not the declared "
        "text, so they declare something narrower than FR-08 claims:\n  " + "\n  ".join(degraded)
    )


def test_the_declaration_says_what_fr08_says():
    """The trailer text and the requirement are one claim.

    Without this the declaration could drift into something weaker while
    every commit still carried a trailer and the test still passed.
    """
    requirement = (REPO / "docs" / "srs" / "functional-requirements.md").read_text(encoding="utf-8")
    start = requirement.index('!!! requirement "FR-08 ')
    body = requirement[start : requirement.index("\n!!! requirement", start + 10)]
    # Collapsed, because the requirement is hard-wrapped: "official
    # manual" spans a line break in FR-08's own text, and the phrase
    # check below read that as the phrase being absent.
    body = " ".join(body.split())
    assert TRAILER in body, (
        f"FR-08 does not name the {TRAILER} trailer, so its evidence line points at "
        "a mechanism this test invented on its own"
    )
    # One operand each. Written as `A or B` this loop could not fail:
    # all three phrases are literal substrings of DECLARATION, so the
    # left operand was true on every iteration and `body` was never
    # consulted. The test claimed to stop FR-08's prose drifting away
    # from the trailer and was satisfied entirely by the trailer.
    for phrase in ("official manual", "probe evidence", "AGPL"):
        assert phrase.lower() in body.lower(), (
            f"FR-08's text no longer says {phrase!r}, so the requirement and the "
            "trailer have drifted apart"
        )
        assert phrase.lower() in DECLARATION.lower(), (
            f"the declared trailer no longer says {phrase!r}"
        )
    # And the trailer contributors are told to write must be the one the
    # guard enforces, or the suite rejects a correctly followed procedure.
    contributing = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert DECLARATION in contributing, (
        "CONTRIBUTING.md quotes a different declaration from the one this "
        "guard enforces, so a contributor who follows it would be refused"
    )
