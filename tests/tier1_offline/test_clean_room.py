"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


TRAILER = "Clean-room"


DECLARATION = (
    "emitter specified from the official manual and probe evidence only; "
    "no code, structure or docstrings from the AGPL predecessor"
)


BASELINE = "259a7d1650ce240d6ab2b7ecb6482fc6b8efc303"


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
    result = _git("log", "-1", f"--format=%(trailers:key={key},valueonly,separator=%x1f)", commit)
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


_A, _B, _C = "a" * 40, "b" * 40, "c" * 40


_RANGE = [_C, _B, _A]


def _fake_history(monkeypatch, trailers):
    """Drive the real _follow_up_declarations over a fake graph.

    The three git primitives are replaced rather than the function under
    test, so the rules themselves are what runs.
    """
    monkeypatch.setattr(
        "tests.tier1_offline.test_clean_room._trailer_values",
        lambda commit, key=TRAILER: trailers.get(commit, {}).get(key, []),
    )
    monkeypatch.setattr(
        "tests.tier1_offline.test_clean_room._resolve", lambda rev: rev if len(rev) == 40 else None
    )
    # In the fake graph a is oldest and c is newest, so "earlier is an
    # ancestor of later" is just string order on the sentinels.
    monkeypatch.setattr(
        "tests.tier1_offline.test_clean_room._is_ancestor", lambda earlier, later: earlier < later
    )


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
    monkeypatch.setattr("tests.tier1_offline.test_clean_room._commits_under_review", lambda: _RANGE)
    with pytest.raises(AssertionError) as raised:
        test_every_commit_since_the_baseline_declares_its_provenance()
    message = str(raised.value)
    assert FOLLOW_UP_TRAILER in message, (
        "the failure message does not name the follow-up mechanism, so a "
        "reader is again told to do something that will not work"
    )


def test_an_unreachable_baseline_fails_rather_than_reporting_nothing(monkeypatch):
    """The failure mode this repository keeps registering.

    In CI an unreachable baseline means a shallow checkout. Returning an
    empty range there would pass every assertion while examining no
    commit at all, so the range command asserts on its own exit code and
    the message names fetch-depth.
    """
    monkeypatch.setattr(
        "tests.tier1_offline.test_clean_room._git",
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
