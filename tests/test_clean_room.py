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

#: The trailer by which a LATER commit declares on behalf of an EARLIER
#: one that missed its own. Its value is the missed commit's hash.
#:
#: WHY IT EXISTS. Until 2026-08-24 this module's own failure message,
#: CONTRIBUTING.md and .claude/hooks/check_trailer_policy.py all told the
#: reader the same thing: "a commit that missed it is corrected by a
#: follow-up commit that says so". None of them could accept one. The
#: check below is a WALK over BASELINE..HEAD, and a follow-up ADDS a
#: commit to that range without removing the failing one, so the
#: prescribed remedy left the guard exactly as red as it found it. The
#: only exits were rewriting history, moving the baseline, or an
#: exemption list, and two of those weaken the guard permanently.
#:
#: Measured twice before it was believed: once on 2026-08-09, when a
#: release commit could not be tagged until its message was rewritten,
#: and again on 2026-08-24, when 83db2f2 turned CI red on main and no
#: follow-up could clear it.
#:
#: This makes the printed remedy true instead of false. It is an
#: exemption, and it is deliberately the IN-BAND kind: the declaration
#: lives in the history it is about, carries the full declaration text
#: rather than a waiver token, names the commit it covers, and is signed
#: by its own author and date exactly as a first-hand declaration is. An
#: allowlist file would have been none of those things.
FOLLOW_UP_TRAILER = "Clean-room-for"


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


def _trailer_values(commit: str, key: str = TRAILER) -> list[str]:
    """Return the values of one trailer key on one commit, via git.

    Git's own trailer parser rather than a line scan over the message,
    and the difference is not cosmetic: this guard failed on its own
    first commit because that message QUOTES the trailer in its body to
    explain it, wrapped across three lines, and a scan for the first
    line starting with the key found the quoted fragment. Git knows a
    trailer is a key-value line in the LAST paragraph, which is exactly
    the distinction the scan was missing.
    """
    result = _git(
        "log", "-1", f"--format=%(trailers:key={key},valueonly,separator=%x1f)", commit
    )
    assert result.returncode == 0, f"cannot read the trailers of {commit}"
    return [value.strip() for value in result.stdout.strip().split("\x1f") if value.strip()]


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


def _resolve(rev: str) -> str | None:
    """The full hash of ``rev``, or None if git cannot resolve it."""
    result = _git("rev-parse", "--verify", f"{rev}^{{commit}}")
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(earlier: str, later: str) -> bool:
    return _git("merge-base", "--is-ancestor", earlier, later).returncode == 0


def _follow_up_declarations(commits: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map each covered commit to the commit that declared for it.

    Returns the map and a list of REFUSALS. Every rule below exists to
    stop this mechanism becoming the weaker thing it was chosen over:

    * a declaring commit must itself declare, or an undeclared commit
      could launder another one;
    * the value must resolve to a real commit, so a typo is refused
      rather than silently covering nothing while looking like it does;
    * the target must be INSIDE the range under review, so a follow-up
      cannot appear to cover history the walk never examines;
    * the declarer must come AFTER its target, because a declaration
      made before the work it describes is not a declaration; and
    * a commit may not name itself, which declares nothing and would
      read as though it did.
    """
    population = set(commits)
    covered: dict[str, str] = {}
    refusals: list[str] = []
    for commit in commits:
        targets = _trailer_values(commit, FOLLOW_UP_TRAILER)
        if not targets:
            continue
        if _classify(_trailer_values(commit)) != "ok":
            refusals.append(
                f"{commit[:7]} declares for another commit but does not declare for "
                f"itself; a commit that has not made the {TRAILER} declaration cannot "
                "make it on someone else's behalf"
            )
            continue
        for target in targets:
            resolved = _resolve(target)
            if resolved is None:
                refusals.append(
                    f"{commit[:7]} names {target!r} in its {FOLLOW_UP_TRAILER} trailer "
                    "and git cannot resolve it to a commit"
                )
            elif resolved == commit:
                refusals.append(
                    f"{commit[:7]} names ITSELF in its {FOLLOW_UP_TRAILER} trailer; a "
                    f"commit declares for itself with {TRAILER} alone"
                )
            elif resolved not in population:
                refusals.append(
                    f"{commit[:7]} declares for {resolved[:7]}, which is not in "
                    f"{BASELINE[:7]}..HEAD; this guard examines only that range, so "
                    "the declaration would cover nothing while appearing to"
                )
            elif not _is_ancestor(resolved, commit):
                refusals.append(
                    f"{commit[:7]} declares for {resolved[:7]}, which is not an "
                    "ancestor of it; a follow-up declaration comes AFTER the commit "
                    "it corrects"
                )
            else:
                covered[resolved] = commit
    return covered, refusals


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


#: A fake three-commit range for the follow-up tests. Newest first, the
#: order _commits_under_review returns. "b" is the commit that missed
#: its trailer; "c" is the later commit that can declare for it.
_A, _B, _C = "a" * 40, "b" * 40, "c" * 40
_RANGE = [_C, _B, _A]


def _fake_history(monkeypatch, trailers):
    """Drive the real _follow_up_declarations over a fake graph.

    The three git primitives are replaced rather than the function under
    test, so the rules themselves are what runs.
    """
    monkeypatch.setattr(
        "test_clean_room._trailer_values",
        lambda commit, key=TRAILER: trailers.get(commit, {}).get(key, []),
    )
    monkeypatch.setattr(
        "test_clean_room._resolve", lambda rev: rev if len(rev) == 40 else None
    )
    # In the fake graph a is oldest and c is newest, so "earlier is an
    # ancestor of later" is just string order on the sentinels.
    monkeypatch.setattr("test_clean_room._is_ancestor", lambda earlier, later: earlier < later)


def test_a_follow_up_declaration_covers_the_commit_it_names(monkeypatch):
    """The accepting direction: the remedy the guard prints now works."""
    _fake_history(
        monkeypatch,
        {
            _A: {TRAILER: [DECLARATION]},
            _B: {},  # missed its trailer
            _C: {TRAILER: [DECLARATION], FOLLOW_UP_TRAILER: [_B]},
        },
    )
    covered, refusals = _follow_up_declarations(_RANGE)
    assert refusals == []
    assert covered == {_B: _C}


@pytest.mark.parametrize(
    ("name", "trailers", "expected"),
    [
        (
            "a declarer that has not declared for itself",
            {_C: {FOLLOW_UP_TRAILER: [_B]}},
            "does not declare for itself",
        ),
        (
            "a declarer whose own trailer is degraded",
            {_C: {TRAILER: ["yes"], FOLLOW_UP_TRAILER: [_B]}},
            "does not declare for itself",
        ),
        (
            "a value git cannot resolve",
            {_C: {TRAILER: [DECLARATION], FOLLOW_UP_TRAILER: ["nonsense"]}},
            "cannot resolve it to a commit",
        ),
        (
            "a commit naming itself",
            {_C: {TRAILER: [DECLARATION], FOLLOW_UP_TRAILER: [_C]}},
            "names ITSELF",
        ),
        (
            "a target outside the range under review",
            {_C: {TRAILER: [DECLARATION], FOLLOW_UP_TRAILER: ["d" * 40]}},
            "is not in",
        ),
        (
            "a declaration made BEFORE the commit it covers",
            {
                _A: {TRAILER: [DECLARATION], FOLLOW_UP_TRAILER: [_C]},
                _C: {TRAILER: [DECLARATION]},
            },
            "is not an ancestor of it",
        ),
    ],
)
def test_a_follow_up_declaration_is_refused_when_it_is_not_one(
    monkeypatch, name, trailers, expected
):
    """The refusing direction, one rule per case.

    Written as one case per rule rather than one test with six
    assertions, because a single test passes as soon as the FIRST rule
    fires and the other five are then never really exercised. This
    repository has paid for that shape before.
    """
    _fake_history(monkeypatch, trailers)
    covered, refusals = _follow_up_declarations(_RANGE)
    assert covered == {}, f"{name} should cover nothing"
    assert any(expected in refusal for refusal in refusals), (
        f"{name}: no refusal mentioned {expected!r}; got {refusals}"
    )


def test_the_printed_remedy_names_the_mechanism_that_exists(monkeypatch):
    """The guard against this whole class of defect recurring.

    The reason this module needed changing at all was that its own
    failure text prescribed a remedy the code could not accept. So the
    text is asserted against the code: whatever the message tells a
    reader to write, the trailer key it names must be the one the walk
    actually consults.
    """
    _fake_history(monkeypatch, {_A: {}, _B: {}, _C: {}})
    monkeypatch.setattr("test_clean_room._commits_under_review", lambda: _RANGE)
    with pytest.raises(AssertionError) as raised:
        test_every_commit_since_the_baseline_declares_its_provenance()
    message = str(raised.value)
    assert FOLLOW_UP_TRAILER in message, (
        "the failure message does not name the follow-up mechanism, so a "
        "reader is again told to do something that will not work"
    )
    assert "follow-up commit cannot remove" in message, (
        "the message no longer explains WHY a plain follow-up does not clear "
        "a walk, which is the misunderstanding that produced this defect"
    )


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
    commits = _commits_under_review()
    covered, refusals = _follow_up_declarations(commits)
    assert not refusals, (
        f"these {FOLLOW_UP_TRAILER} declarations were refused:\n  "
        + "\n  ".join(refusals)
        + "\n\nA follow-up declaration is held to the same standard as a "
        "first-hand one, or it would be the weaker mechanism this one was "
        "chosen over."
    )

    missing = []
    degraded = []
    for commit in commits:
        if commit in covered:
            # Declared for by a later commit. The declaration is in the
            # history, names this commit, and carries the full text.
            continue
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
        "Amending is banned in this repository. This check is a WALK over "
        f"{BASELINE[:7]}..HEAD, so a follow-up commit cannot remove the commit "
        "above from the population; instead, make the declaration ON ITS "
        "BEHALF, in the last paragraph of a later commit:\n\n"
        f"    {FOLLOW_UP_TRAILER}: <the full hash above>\n"
        f"    {TRAILER}: {DECLARATION}\n\n"
        "The declaring commit must itself declare, and must come after the "
        "commit it covers."
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
