"""Tier 1 end to end guards for the role-review push gate hook.

The hook is process infrastructure, not library code, but it is the
mechanism that decides whether unreviewed work can ship, so it needs the
same evidence discipline as the package. This file pins the DECISION the
gate makes, because the parsing can be right while the enforcement is
wrong: the range fix that closed the attest-only-the-tip hole opened a
worse one on the release path, and only an adversarial review caught it.

This suite and the hardened gate it exercises were ported inward from
the sister library, which found and reproduced six fail-open holes while
porting an earlier version of the gate the other way (an allowlist of
ref-neutral options replacing a denylist that ``--follow-tag`` slipped
through, refspec resolution on both sides of the colon, per-ref scoping,
the project-name identity, and deny messages that name the command that
clears them). The hook is process infrastructure rather than package
code, so these guards were written after the port rather than before it;
that ordering is a deliberate exception to the repository's TDD rule,
which governs the ``pyflightstream`` package.

Each test builds a throwaway repository with a local bare remote, so
nothing here touches the real checkout, the real attestation, or the
shared incident ledger. The hook is invoked exactly as the harness
invokes it: the PreToolUse payload on stdin, a permission decision on
stdout.

HOW HERMETICITY IS OBTAINED, because the mechanism inverted on
2026-08-02 and the old sentence would now be actively misleading. It
used to be enough to STRIP the incident-ledger variable from every hook
subprocess: unset meant the incident check did not apply, so an absent
variable was the neutral state. Kit 0.2.8 made an absent variable DENY,
for the reason recorded on ``test_an_unconfigured_ledger_now_denies``,
and neutral-by-absence stopped existing. Stripping the variable would
now make every allow case fail for a reason that has nothing to do with
what it tests.

So the neutral state is no longer "no ledger" but "a ledger that is
readable and reports clean", and ``hook_env`` supplies one: a stub
``check_incidents.py`` in a throwaway directory that exits 0 whatever it
is asked. The suite is hermetic in the sense that matters, which is that
it never reads the author's real ledger, and it can still express the
genuinely-absent case by passing ``ledger=UNSET``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "role_review_gate.py"
#: The kit's own fake-`gh` builder, imported from the vendored companion that
#: sits beside `ci_state.py`. Loaded by path rather than imported by name
#: because `.claude/hooks` is not a package and must not become one.
_CI_MUTATIONS = HOOK.parent / "ci_state_mutations.py"
_spec = importlib.util.spec_from_file_location("_ci_state_mutations", _CI_MUTATIONS)
assert _spec and _spec.loader, f"cannot load {_CI_MUTATIONS}"
_ci_state_mutations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ci_state_mutations)
_fake_gh = _ci_state_mutations.fake_gh
#: `gh run list --json` answers, in the CLI's own vocabulary. GREEN is the
#: suite's neutral state; the others are used by the release-path cases that
#: exist to show the CI arm refusing.
CI_GREEN = (
    '[{"status":"completed","conclusion":"success",'
    '"workflowName":"tests","databaseId":1,"url":"u1"}]'
)
CI_RUNNING = (
    '[{"status":"in_progress","conclusion":null,"workflowName":"tests","databaseId":1,"url":"u1"}]'
)
CI_RED = (
    '[{"status":"completed","conclusion":"failure",'
    '"workflowName":"tests","databaseId":1,"url":"u1"}]'
)
CI_NONE = "[]"
ATTESTATION = Path(".claude") / ".role_review_attestation.json"
# The variable the GATE reads. Renamed from PYFS_INCIDENT_LEDGER when the
# 0.2.16 body was vendored on 2026-08-02: kit 0.2.8 gave every workspace one
# name under the author decision LEDGER-ENVVAR. This constant must track the
# gate body, and until 2026-08-11 it had to be said that the analyst charter
# was a DIFFERENT artifact on a different kit row still reading the old name.
# The 0.2.11 charter closed that: nothing in this repository reads
# PYFS_INCIDENT_LEDGER any more, and CLAUDE.md dropped it. Pointing this at the
# wrong name still does not fail loudly, it makes `hook_env` stop suppressing
# the real ledger and the suite silently depends on one author's machine.
LEDGER_ENV = "COORD_INCIDENT_LEDGER"
# Built by concatenation so this file never contains the literal command
# it tests; the gate scans command text and would flag work on this file.
PUSH = "git" + " push"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stripped stdout."""
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


# Sentinel for "the variable is genuinely absent", which is now a distinct
# state from "not specified by this test" and has the opposite outcome. A
# plain None cannot carry both meanings any more.
UNSET = object()


def _clean_ledger() -> str:
    """A throwaway ledger directory whose checker always reports clean.

    Created once per session and cached. This is the NEUTRAL state for every
    case that is not about incidents: readable, answers 0, names no repository.
    Deliberately not the author's real ledger, whose contents change and whose
    open blocking entries would otherwise fail tests about refspec parsing.
    """
    global _CLEAN_LEDGER
    if _CLEAN_LEDGER is None:
        folder = Path(tempfile.mkdtemp(prefix="pyfs-clean-ledger-"))
        _CLEAN_LEDGER = stub_ledger(folder, 0, "clean")
    return _CLEAN_LEDGER


_CLEAN_LEDGER: str | None = None


def hook_env(ledger: str | object | None = None) -> dict[str, str]:
    """The environment a hook subprocess runs in.

    ``ledger`` is a path to use, ``UNSET`` to remove the variable entirely, or
    ``None`` (the default) for the clean stub above. The author's real ledger
    is never inherited in any of the three: a real open incident would fail
    tests that are not about incidents at all, which is precisely what the
    blocking entry that prompted this vendor would have done to 24 of them.
    """
    env = {k: v for k, v in os.environ.items() if k != LEDGER_ENV}
    if ledger is UNSET:
        return env
    env[LEDGER_ENV] = _clean_ledger() if ledger is None else str(ledger)
    return env


def install_gh(repo: Path, payload: str = CI_GREEN, status: int = 0) -> None:
    """Put a FAKE ``gh`` on this test's PATH, answering ``payload``.

    Reused from the vendored ``ci_state_mutations.fake_gh`` rather than
    rewritten, because the Windows half of it is not obvious and getting it
    wrong is silent: ``CreateProcess`` resolves a bare ``gh`` by appending
    ``.exe`` and nothing else, so a ``gh.bat`` is never found, every case reads
    UNKNOWN because ``gh`` is simply absent, and the case that looks like it
    passes (``gh`` exiting non-zero) passes on the not-found message instead.
    A second implementation of that would be a second place to get it wrong.

    Written INTO the repository directory, which is also the hook's cwd, and
    that is required rather than convenient: the Windows fake is a copy of this
    interpreter, so its script arrives as the first argument (the literal word
    ``run`` from ``gh run list``) and is resolved against the working
    directory. Called from ``judge`` and therefore always after the test's
    commits, so ``add_commit``'s ``git add -A`` never stages it.
    """
    _fake_gh(repo, payload, status)


def judge(
    repo: Path,
    command: str,
    ledger: str | object | None = None,
    gh: tuple[str, int] | None = None,
) -> tuple[str, str]:
    """Run the hook on ``command`` and return (decision, reason).

    ``gh`` defaults to a GREEN fake, which is the neutral state for the same
    reason ``ledger`` defaults to a clean stub: since the 0.2.18 body a
    release-grade push asks the remote what CI concluded, BEFORE it asks for
    the release attestation, and anything but GREEN denies. Without a fake, six
    tests about attestation SCOPE denied at ``[ci-unknown]`` instead, each
    passing its assertion on a message about something else, and the suite took
    137 seconds talking to a network it has no business needing. Measured on
    2026-08-11, on the run that vendored the 0.2.18 gate.
    """
    payload, status = gh if gh is not None else (CI_GREEN, 0)
    install_gh(repo, payload, status)
    env = hook_env(ledger)
    env["PATH"] = str(repo) + os.pathsep + env.get("PATH", "")
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    if not done.stdout.strip():
        return "allow", ""
    out = json.loads(done.stdout)["hookSpecificOutput"]
    return str(out["permissionDecision"]), str(out.get("permissionDecisionReason", ""))


def decide(
    repo: Path,
    command: str,
    ledger: str | object | None = None,
    gh: tuple[str, int] | None = None,
) -> str:
    """Run the hook on ``command`` and return its permission decision."""
    return judge(repo, command, ledger, gh)[0]


def stub_ledger(folder: Path, exit_code: int, message: str) -> str:
    """Write a fake check_incidents.py that exits with ``exit_code``.

    The real ledger lives outside the repository, so the only way to
    exercise the branch that matters (a checker that runs and reports a
    blocking incident) is to stand one up here. Without this the gate
    could be disabled entirely and the suite would stay green.
    """
    folder.mkdir(parents=True, exist_ok=True)
    checker = folder / "check_incidents.py"
    checker.write_text(
        f"import sys\nprint({message!r} + ' ' + sys.argv[1])\nsys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return str(folder)


def attest(repo: Path, commits: list[str], kind: str = "review") -> None:
    """Write an attestation covering ``commits`` (bypassing the writer)."""
    path = repo / ATTESTATION
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    existing[kind] = {"head": commits[0] if commits else "", "commits": commits}
    path.write_text(json.dumps(existing), encoding="utf-8")


def add_commit(repo: Path, name: str) -> str:
    """Add one commit and return its sha."""
    (repo / f"{name}.txt").write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


def _pushed(repo: Path) -> list[str]:
    """The commits a push from ``repo`` would make new."""
    listed = git(repo, "rev-list", "HEAD", "--not", "--remotes")
    return [c for c in listed.splitlines() if c]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one pushed commit and a local bare remote."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "T")
    # Pin push.default so the baseline (a bare `push origin` resolves to the
    # current branch) does not depend on the developer's global git config;
    # a machine set to push.default=matching would otherwise flip the
    # unscopable-bare-push tests.
    git(work, "config", "push.default", "simple")
    (work / "a.txt").write_text("a", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    # Name the branch, so a test that pushes "main" by name pushes a ref
    # that exists locally. git init picks master or main depending on the
    # installation, and the gate now resolves the named ref.
    git(work, "branch", "-M", "main")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(work, "fetch", "-q", "origin")
    return work


def test_unattested_push_is_denied(repo: Path) -> None:
    """A new commit with no attestation never ships."""
    add_commit(repo, "one")
    assert decide(repo, f"{PUSH} origin main") == "deny"


def test_attested_range_is_allowed(repo: Path) -> None:
    """An attestation covering every new commit clears the gate."""
    first = add_commit(repo, "one")
    second = add_commit(repo, "two")
    attest(repo, [second, first])
    assert decide(repo, f"{PUSH} origin main") == "allow"


def test_attesting_only_the_tip_is_denied(repo: Path) -> None:
    """The sister library's review found this: no free rides for ancestors.

    The fixture forces two unpushed commits rather than letting the case
    skip itself when the repository happens to hold only one, because
    the previous evidence for this gate was a script whose main case
    could skip itself and still report all clear.
    """
    add_commit(repo, "one")
    tip = add_commit(repo, "two")
    attest(repo, [tip])
    assert decide(repo, f"{PUSH} origin main") == "deny"


@pytest.mark.parametrize("spec", ["v9.9.9", "HEAD:refs/tags/v9.9.9"])
def test_tag_push_needs_the_release_attestation_when_the_branch_is_pushed(
    repo: Path, spec: str
) -> None:
    """The regression the range fix introduced, and the reason for in_scope.

    Pushing the branch first leaves the tagged commit already on the
    remote, so the range of new commits is empty. Set containment over
    an empty range is vacuously true, which briefly let an unattested
    tag reach the PyPI publish workflow. Both this exact incident
    condition and the ``HEAD:refs/tags/vX`` refspec form (the two shapes
    named in INC-20260724-0839) are exercised together here.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(repo, "fetch", "-q", "origin")
    git(repo, "tag", "v9.9.9")
    assert git(repo, "rev-list", "HEAD", "--not", "--remotes") == ""
    # Review-attested but not release-attested: the release gate holds.
    assert decide(repo, f"{PUSH} origin {spec}") == "deny", spec
    attest(repo, [head], kind="release")
    assert decide(repo, f"{PUSH} origin {spec}") == "allow", spec


def test_a_configured_but_unreadable_ledger_blocks(repo: Path, tmp_path: Path) -> None:
    """A ledger that cannot be consulted must not read as all clear."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin main", ledger=str(tmp_path / "nowhere")) == ("deny")


def test_an_unconfigured_ledger_now_denies(repo: Path) -> None:
    """Without the environment variable the push is REFUSED, not waved through.

    This test asserted the opposite until 2026-08-02, and the inversion is the
    substance of the kit 0.2.8 promotion rather than a detail of it. The old
    contract reasoned that the shared ledger is one author's local artifact, so
    a clone that never configured it should still be able to push once its work
    was reviewed. That reasoning is about a FORK, and it was applied to the
    variable being absent, which is a different question with the same symptom.

    What it cost, measured at the coordination level and not hypothesized: the
    repository that WRITES the incidents derived a ledger variable name that
    had never existed, unset read as does-not-apply, and it pushed past a
    blocking incident of its own authorship. Of the three workspaces, the gate
    stopped two and the silence was in the one with the most to lose.

    So the rule is now that a guard may not read its own missing configuration
    as permission. The remedy for a genuine fork is to export the variable at a
    ledger it can read, which is one line and is named in the deny text; the
    remedy for the old behaviour was nothing, because nothing was reported.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=UNSET)
    assert decision == "deny"
    assert LEDGER_ENV in reason, reason


def test_a_trailing_command_does_not_defeat_the_gate(repo: Path) -> None:
    """``push; echo done`` reaches the remote, so it must be recognized.

    ``shlex(posix=False)`` leaves ``push;`` as a single token, and the
    v1 comparison against ``"push"`` missed it. That failed open on the
    most natural way to type a push followed by anything else.
    """
    add_commit(repo, "one")
    assert decide(repo, f"{PUSH} origin main; echo done") == "deny"


def test_a_quoted_mention_of_the_command_is_not_a_push(repo: Path) -> None:
    """A commit message naming the command must not trip the gate."""
    add_commit(repo, "one")
    assert decide(repo, f'git commit -m "explain the {PUSH} gate"') == "allow"


def test_a_heredoc_commit_that_mentions_the_push_is_not_a_push(repo: Path) -> None:
    """A commit message written as a heredoc body that names the push must allow.

    ``_strip_heredocs`` removes the heredoc body before tokenizing, so a
    commit that documents a push is not misread as one. The regex that
    finds the heredoc opener carried a stray control byte that made it
    match nothing, so the stripper was dead and every heredoc commit
    naming the push was falsely denied (INC-20260724-0912). All three
    delimiter forms are exercised.
    """
    add_commit(repo, "one")
    for opener, closer in (("<<'MSG'", "MSG"), ("<<MSG", "MSG"), ('<<"MSG"', "MSG")):
        cmd = f"git commit -F- {opener}\ndocument the {PUSH} gate\n{closer}"
        assert decide(repo, cmd) == "allow", opener


# INC-20260802-1450-shared. Kept as a table rather than three separate
# functions because the point is the CLASS: every one of these is two lines of
# ordinary shell with no heredoc in it anywhere, and the label is what a
# failure prints.
UNTERMINATED_OPENER_CASES = [
    (
        "a message naming <<EOF, then a real push on the next line",
        f'git commit -m "see the <<EOF form"\n{PUSH} origin main',
    ),
    (
        "the same with the opener inside a -m and a trailing &&",
        f'git commit -m "about <<HEREDOC" && \\\n{PUSH} origin main',
    ),
    (
        "a << that is not a heredoc at all, then a real push",
        f'git commit -m "a << b"\n{PUSH} origin main',
    ),
]


@pytest.mark.parametrize("label,command", UNTERMINATED_OPENER_CASES, ids=lambda v: v[:40])
def test_an_unterminated_heredoc_opener_does_not_swallow_a_real_push(
    repo: Path, label: str, command: str
) -> None:
    """A heredoc opener that never terminates must strip NOTHING.

    INC-20260802-1450-shared, and it is the worst shape this mechanism has: a
    FAIL-OPEN. ``_strip_heredocs`` removes heredoc bodies before tokenizing so
    that a commit message merely describing a push does not read as one. Its
    opener pattern matched anywhere in a line, including inside a quoted commit
    message, and when no matching delimiter line ever arrived it dropped every
    remaining line. The real push on the next line went with them, and the gate
    returned without requiring an attestation, reading the ledger, or checking
    for a release tag. Not a weaker refusal: no refusal.

    Measured here against the deployed 0.2.4 body before it was replaced, all
    three cases returned NO DECISION AT ALL while the control below denied.

    The structural rule the fix encodes, and the reason this test asserts on
    every branch rather than sampling one: stripping can only ever REMOVE
    tokens from what is scanned, so for an input the stripper does not
    understand there is exactly one safe direction, and it is to strip nothing.
    Do not weaken this to "the parse fails and the raw-text fallback catches
    it". That fallback is not a net. ``shlex.split(posix=False)`` does not
    raise on every unbalanced quote (given ``git commit -m @'`` it returns
    ``@'`` as an ordinary token and parses on), so a stripping bug produces a
    CLEAN parse with the push missing from it and nothing downstream notices.
    """
    decision, reason = judge(repo, command)
    assert decision == "deny", (
        f"{label}: the gate returned {decision!r} on a command containing a "
        "real push. An empty decision here is the fail-open, not an allow."
    )
    assert reason, f"{label}: denied with no reason text"


def test_the_control_for_the_unterminated_opener_cases_denies(repo: Path) -> None:
    """A bare unattested push denies, so the cases above can see a deny at all.

    Without this the three above are unfalsifiable: a harness that could never
    produce a deny would pass them for the wrong reason. This is the same
    control that was measured alongside the red run.
    """
    add_commit(repo, "one")
    assert decide(repo, f"{PUSH} origin main") == "deny"


def test_a_terminated_heredoc_does_not_hide_a_push_after_it(repo: Path) -> None:
    """Stripping stops at the delimiter, so a push AFTER the body is still seen.

    The companion pin to the allow case above. Together they bound the fix from
    both sides: an unterminated opener must strip nothing, and a terminated one
    must strip exactly its own body and no more. A fix that satisfied only the
    fail-open could have been written by disabling the stripper entirely, and
    this is the assertion that would have caught it.
    """
    add_commit(repo, "one")
    cmd = f"git commit -F- <<MSG\na message\nMSG\n{PUSH} origin main"
    assert decide(repo, cmd) == "deny"


def test_a_dash_c_push_from_outside_the_repo_is_recognized(repo: Path, tmp_path: Path) -> None:
    """`git -C <repo> push` run from a non-repo cwd must still be gated.

    The gate resolves the repository from the -C global option, not only
    from the working directory, so a push issued from elsewhere cannot
    slip past it.
    """
    add_commit(repo, "one")
    outside = tmp_path / "outside"
    outside.mkdir()
    cmd = f"git -C {repo.as_posix()} " + "push origin main"
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=outside,
        env=hook_env(),
    )
    out = json.loads(done.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_an_unbalanced_quote_naming_git_and_push_fails_closed(repo: Path) -> None:
    """A command shlex cannot parse must fail closed when it looks like a push.

    On unbalanced quotes the tokenizer gives up; if the raw text still
    carries both ``git`` and ``push`` as words, the gate treats it as a
    push it could not confirm safe rather than allowing it through.
    """
    add_commit(repo, "one")
    cmd = "git " + 'push origin "main'  # unterminated quote
    assert decide(repo, cmd) == "deny"


def test_a_named_branch_is_scoped_by_that_branch_not_by_head(repo: Path) -> None:
    """Pushing a ref that is not HEAD must be judged on that ref.

    Scoping from HEAD let a branch carrying unattested commits ship
    whenever HEAD happened to be attested, which is the same free ride
    for unreviewed work that the range check exists to stop.
    """
    head = add_commit(repo, "one")
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    add_commit(repo, "unreviewed")
    git(repo, "checkout", "-q", "main")
    attest(repo, [head])
    assert git(repo, "rev-parse", "HEAD") == head
    assert decide(repo, f"{PUSH} origin side") == "deny"
    assert decide(repo, f"{PUSH} origin side:main") == "deny"


def test_a_push_the_gate_cannot_scope_is_denied(repo: Path) -> None:
    """--all, --mirror and --tags send refs the gate cannot enumerate.

    Offline there is no way to tell which tags the remote already has, so
    the honest answer is to refuse and ask for the ref by name. Allowing
    would be a guard discharging its assertion by not making one:
    --follow-tags is the ordinary release command, and it published an
    unattested tag while the suite stayed green.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    attest(repo, [head], kind="release")
    for form in ("--all", "--mirror", "--tags", "--follow-tags"):
        decision, reason = judge(repo, f"{PUSH} {form} origin")
        assert decision == "deny", form
        assert "cannot determine" in reason, form


def test_a_deletion_refspec_is_denied(repo: Path) -> None:
    """A push that removes a remote ref is not something the gate can bless.

    v0.2.2 reframes it as a policy stop: a deletion's scope IS resolvable, so
    it no longer shares the "cannot determine scope" wrapper. It is tagged
    [policy], with the honest reason.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin :main")
    assert decision == "deny"
    assert "role-review gate: [policy]" in reason
    assert "deletes a published remote ref" in reason
    assert "guesses at its own scope" not in reason


def test_an_open_blocking_incident_denies(repo: Path, tmp_path: Path) -> None:
    """The branch the incident gate exists for, driven by a real checker.

    Only the unreachable-ledger path was covered before, so the whole
    incident gate could be deleted with the suite green.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    ledger = stub_ledger(tmp_path / "ledger", 1, "INC-1 open and blocking for")
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=ledger)
    assert decision == "deny"
    # v0.2.0 folded the three divergent prefixes ("INCIDENT GATE:",
    # "RELEASE GATE:", "ROLE-REVIEW GATE:") into one "role-review gate:"
    # voice with a bracketed sub-kind.
    assert "role-review gate: [incident]" in reason
    assert "INC-1 open and blocking for" in reason
    # The two failure classes have opposite remedies and must not share
    # a message: this one is a real incident, not an unreadable ledger.
    assert "incident-analyst" in reason
    assert "could not be consulted" not in reason


def test_a_clean_ledger_allows(repo: Path, tmp_path: Path) -> None:
    """A checker that reports no blocking incident must not block."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    ledger = stub_ledger(tmp_path / "ledger", 0, "clean for")
    assert decide(repo, f"{PUSH} origin main", ledger=ledger) == "allow"


def test_the_incident_query_uses_the_project_name(repo: Path, tmp_path: Path) -> None:
    """The queried identity must survive a clone into a renamed directory.

    Taking it from the folder name meant a clone named anything else
    queried an unknown repository, got a clean answer, and shipped.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    (repo / "pyproject.toml").write_text('[project]\nname = "pyflightstream"\n', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pyproject")
    attest(repo, _pushed(repo))
    ledger = stub_ledger(tmp_path / "ledger", 1, "queried")
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=ledger)
    assert decision == "deny"
    assert "queried pyflightstream" in reason, reason


def test_the_deny_names_the_range_to_review(repo: Path) -> None:
    """The reason must carry the command that clears it, not just a complaint.

    A reader who follows the role-review skill default reviews the last
    commit, which is the wrong scope for this denial and re-arms the gate.
    """
    add_commit(repo, "one")
    tip = add_commit(repo, "two")
    decision, reason = judge(repo, f"{PUSH} origin main")
    assert decision == "deny"
    assert "role-review gate: [review]" in reason
    assert f"{tip} --not --remotes" in reason, reason


def test_the_fail_closed_reason_does_not_offer_to_disable_the_gate() -> None:
    """A confused gate must not hand over its own bypass as a remedy.

    The fail-closed message is read by an agent under time pressure. It
    once offered turning the hook off through /hooks as a co-equal
    option, next to actually fixing the problem.
    """
    text = HOOK.read_text(encoding="utf-8")
    assert "via /hooks" not in text
    assert "disable the hook" not in text


def test_settings_json_wires_the_hook() -> None:
    """A hook nobody invokes is not a guard.

    Every other test here runs the script by path, so the suite passed
    identically with the registration deleted, the matcher narrowed, or
    the path drifted.
    """
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    wired = [
        hook
        for entry in entries
        for hook in entry.get("hooks", [])
        if "role_review_gate.py" in hook.get("command", "")
    ]
    assert wired, "no PreToolUse hook invokes role_review_gate.py"
    matchers = [
        entry["matcher"]
        for entry in entries
        if any("role_review_gate.py" in h.get("command", "") for h in entry["hooks"])
    ]
    assert any("Bash" in m and "PowerShell" in m for m in matchers), matchers


@pytest.mark.parametrize(
    "form",
    ["--follow-tag", "--tag", "--mirro", "--al", "--delet", "--prune"],
)
def test_an_abbreviated_blanket_option_is_still_refused(repo: Path, form: str) -> None:
    """Git accepts any unambiguous prefix of a long option.

    A refusal keyed on exact spellings moved the hole rather than
    closing it: `--follow-tag` runs, and it published an unattested tag
    four keystrokes short of the spelling the gate knew.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    attest(repo, [head], kind="release")
    decision, reason = judge(repo, f"{PUSH} {form} origin main")
    assert decision == "deny", form
    assert "cannot determine" in reason, form


@pytest.mark.parametrize(
    "option",
    ["-u", "--force-with-lease", "-q", "--atomic", "--dry-run", "-o ci.skip"],
)
def test_an_ordinary_option_does_not_block_an_attested_push(repo: Path, option: str) -> None:
    """The positive control the refusal needs.

    Widening the refusal is the natural fix for the abbreviation hole,
    and without this the suite cannot tell a correct widening from a
    gate that blocks every real push.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} {option} origin main") == "allow", option


@pytest.mark.parametrize(
    "spec",
    ["v9.9.9:v9.9.9", "refs/tags/v9.9.9:refs/tags/v9.9.9", "HEAD:refs/tags/v9.9.9"],
)
def test_a_tag_written_as_a_refspec_is_still_release_grade(repo: Path, spec: str) -> None:
    """The form a blocked operator reaches for next.

    Release classification matched the whole token, so a colon refspec
    scoped correctly, passed the review gate, and skipped the release
    attestation for a syntax git treats as equivalent.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "tag", "v9.9.9")
    assert decide(repo, f"{PUSH} origin {spec}") == "deny", spec
    attest(repo, [head], kind="release")
    assert decide(repo, f"{PUSH} origin {spec}") == "allow", spec


def test_a_configured_push_refspec_makes_a_bare_push_unscopable(repo: Path) -> None:
    """`git push origin` does not always mean the current branch.

    Under push.default=matching, or with remote.<name>.push configured,
    a bare push sends every matching branch while the gate scoped HEAD
    alone, so unattested commits on any other branch shipped.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin") == "allow"
    git(repo, "config", "push.default", "matching")
    decision, reason = judge(repo, f"{PUSH} origin")
    assert decision == "deny"
    assert "cannot determine" in reason
    git(repo, "config", "push.default", "simple")
    git(repo, "config", "remote.origin.push", "refs/heads/*:refs/heads/*")
    assert decide(repo, f"{PUSH} origin") == "deny"


def test_a_multi_ref_push_scopes_every_ref(repo: Path) -> None:
    """The release-day form: branch and tag in one command."""
    head = add_commit(repo, "one")
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    unattested = add_commit(repo, "unreviewed")
    git(repo, "checkout", "-q", "main")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin main side")
    assert decision == "deny"
    assert unattested[:12] in reason


def test_a_deletion_deny_does_not_prescribe_pushing_the_ref(repo: Path) -> None:
    """A fix that cannot reach the goal is not a fix.

    Telling a user who wants to remove a remote ref to push one by name
    is unactionable, and every unscopable case shared that one sentence.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    _, reason = judge(repo, f"{PUSH} origin :main")
    assert "author decision" in reason
    assert "Push the branch or tag by name" not in reason


def test_the_deny_range_command_is_one_git_can_run(repo: Path) -> None:
    """A synthesized `<oldest>^..<tip>` dies on a root commit.

    The reason must print the expression the gate itself computed, not
    a range reconstructed from list positions.
    """
    add_commit(repo, "one")
    _, reason = judge(repo, f"{PUSH} origin main")
    assert "--not --remotes" in reason
    assert "^.." not in reason


def test_an_unreadable_incident_file_gets_the_repair_remedy(repo: Path, tmp_path: Path) -> None:
    """The two incident classes must stay separable from checker output."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    ledger = stub_ledger(tmp_path / "ledger", 1, "UNREADABLE header in INC-2 for")
    decision, reason = judge(repo, f"{PUSH} origin main", ledger=ledger)
    assert decision == "deny"
    assert "could not be consulted" in reason
    assert "incident-analyst" not in reason


def test_the_identity_ignores_other_tables_and_inline_comments(repo: Path, tmp_path: Path) -> None:
    """A prefix match on a raw line is not a TOML parser."""
    head = add_commit(repo, "one")
    (repo / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "wrong"\n\n[project]\nname = "pyflightstream"  # published\n',
        encoding="utf-8",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pyproject")
    attest(repo, [*_pushed(repo), head])
    ledger = stub_ledger(tmp_path / "ledger", 1, "queried")
    _, reason = judge(repo, f"{PUSH} origin main", ledger=ledger)
    assert "queried pyflightstream\n" in reason or "queried pyflightstream " in reason, reason


def test_a_bare_push_resolves_the_remote_it_would_actually_use(repo: Path) -> None:
    """`git push` with no remote does not always mean origin.

    Git resolves branch.<current>.pushRemote, then remote.pushDefault,
    then branch.<current>.remote, then origin. Reading the config for
    `origin` alone closed the push.default half of this hole and left
    the remote-selection half open.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "remote", "add", "upstream", str(repo.parent / "remote.git"))
    git(repo, "config", "branch.main.remote", "upstream")
    git(repo, "config", "remote.upstream.push", "refs/heads/*:refs/heads/*")
    decision, reason = judge(repo, PUSH)
    assert decision == "deny"
    assert "cannot determine" in reason


def test_the_review_deny_tells_a_non_head_push_to_pass_the_ref(repo: Path) -> None:
    """The review check runs first, so it is where the loop happens.

    The release deny carries the "pass the ref" instruction, but a
    review denial on a ref behind HEAD is reached first, and the skill's
    documented invocation stamps HEAD again: push, deny, re-attest,
    deny.
    """
    add_commit(repo, "one")
    _, reason = judge(repo, f"{PUSH} origin main")
    assert "write_attestation.py review" in reason
    assert "stamps HEAD by default" in reason


def test_the_deny_range_covers_every_ref_it_refused(repo: Path) -> None:
    """Naming targets[0] understated the scope on a multi-ref push."""
    head = add_commit(repo, "one")
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    add_commit(repo, "unreviewed")
    git(repo, "checkout", "-q", "main")
    attest(repo, [head])
    _, reason = judge(repo, f"{PUSH} origin main side")
    side = git(repo, "rev-parse", "side")
    assert side in reason


def test_the_review_deny_names_the_ref_that_is_behind_head(repo: Path) -> None:
    """The loop only happens when the pushed ref is not HEAD.

    An earlier test pushed `main` while main was HEAD, so the deny could
    name HEAD unconditionally and still pass: the scenario in its own
    name was never exercised.
    """
    behind = add_commit(repo, "one")
    git(repo, "tag", "v0.1.0")
    add_commit(repo, "two")
    assert git(repo, "rev-parse", "v0.1.0") == behind
    assert git(repo, "rev-parse", "HEAD") != behind
    _, reason = judge(repo, f"{PUSH} origin v0.1.0")
    assert "write_attestation.py review" in reason
    # Naming HEAD here is the loop: the writer would stamp HEAD, which
    # does not cover the tag, and the same denial repeats.
    assert "<passes,that,ran> v0.1.0" in reason, reason


# ---------------------------------------------------------------------------
# v0.2.0/0.2.1 gate, vendored from the shared process kit. These encode the
# NEW contract, so they would fail on the pre-vendor gate: they are written
# failing-test-first per the structural-fix rule, alongside the gate they
# exercise.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("force", ["-f", "--force"])
def test_bare_force_is_denied_as_author_only(repo: Path, force: str) -> None:
    """Unconditional force rewrites published history, which no attestation
    covers (author call, 2026-07-24).

    It denies even when the range is fully attested: the refusal is on
    policy, not scope, so review cannot license it.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} {force} origin main")
    assert decision == "deny", force
    assert "rewrites published history" in reason, reason
    assert "--force-with-lease" in reason, reason


@pytest.mark.parametrize("safe", ["--force-with-lease", "--force-if-includes"])
def test_safe_force_variants_ride_the_attestation_path(repo: Path, safe: str) -> None:
    """The safe force variants refuse on their own when the remote moved, so
    they stay on the normal attestation path rather than being refused as
    author-only. An attested push with one must clear the gate.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} {safe} origin main") == "allow", safe


def test_a_shell_wrapped_push_is_detected(repo: Path) -> None:
    """``bash -c "git push"`` runs a real push inside a quoted token whose
    basename is the shell, not git.

    The pre-v0.2.0 gate looked only for a git executable and failed OPEN on
    this; v0.2.0 recognizes the wrapper by shell family and recurses on the
    inner command.
    """
    add_commit(repo, "one")
    assert decide(repo, f'bash -c "{PUSH} origin main"') == "deny"


def test_a_nested_shell_wrapped_push_is_detected(repo: Path) -> None:
    """A single nesting must not defeat the gate: recursion is bounded but
    deeper than one level.
    """
    add_commit(repo, "one")
    cmd = 'bash -c "bash -c ' + "'" + f"{PUSH} origin main" + "'" + '"'
    assert decide(repo, cmd) == "deny"


def test_the_heredoc_stripper_removes_the_body() -> None:
    """Independent liveness guard for INC-20260724-0912, re-forked by the
    0.2.0 kit body and fixed in 0.2.1.

    A stray control byte inside the heredoc-opener regex made the stripper
    match nothing. The neighbouring
    test_a_heredoc_commit_that_mentions_the_push_is_not_a_push pins the
    end-to-end DECISION; this one asserts the underlying property directly on
    `_strip_heredocs`, so a dead stripper fails even if some other path
    happened to reach the same allow. It imports the vendored hook module by
    path.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gate_under_test", HOOK)
    gate = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(gate)
    cmd = f"git commit -F- <<'MSG'\ndocument the {PUSH} gate\nMSG"
    stripped = gate._strip_heredocs(cmd)
    assert stripped != cmd, "the stripper did nothing: the opener regex is dead"
    assert "document the" not in stripped, "the heredoc body survived stripping"
    assert gate._find_git_push(cmd)[0] is False, "a stripped heredoc must not read as a push"


def test_a_commit_only_on_another_remote_is_still_in_scope_for_origin(
    repo: Path, tmp_path: Path
) -> None:
    """v0.2.0 scopes the pushed range to the TARGET remote.

    The pushed range is `<tip> --not --remotes=<remote>` for a known remote,
    not the bare `--not --remotes`. So an ancestor already on a DIFFERENT
    remote is no longer treated as already-shipped to origin: it stays in
    scope and must be attested. Bare `--remotes` would exclude it and let it
    reach origin unreviewed.
    """
    other = tmp_path / "other.git"
    subprocess.run(["git", "init", "--bare", "-q", str(other)], check=True)
    git(repo, "remote", "add", "other", str(other))
    ancestor = add_commit(repo, "ancestor")
    tip = add_commit(repo, "tip")
    # Publish only the ancestor to the OTHER remote, never to origin.
    git(repo, "push", "-q", "other", f"{ancestor}:refs/heads/main")
    git(repo, "fetch", "-q", "other")
    # Attest only the tip; the ancestor is covered by no attestation.
    attest(repo, [tip])
    decision, reason = judge(repo, f"{PUSH} origin main")
    assert decision == "deny"
    assert ancestor[:12] in reason, (
        "an ancestor present only on another remote must count as in-scope for a push to origin"
    )


def test_a_multi_tag_release_deny_names_every_tag(repo: Path) -> None:
    """The release deny must name ALL version tags being pushed.

    A multi-tag push that reported only the first tag left the writer command
    short, so a second tag stayed uncovered and the same denial repeated. The
    review gate is satisfied here (the commit is review-attested) so control
    reaches the release check, which must list both tags.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])  # review only, no release attestation
    git(repo, "tag", "v9.9.8")
    git(repo, "tag", "v9.9.9")
    decision, reason = judge(repo, f"{PUSH} origin v9.9.8 v9.9.9")
    assert decision == "deny"
    assert "v9.9.8" in reason and "v9.9.9" in reason, reason
    assert "role-review gate: [release]" in reason


def test_the_final_allow_writes_one_observability_line(repo: Path) -> None:
    """A passing gate must not be indistinguishable from an absent one.

    The final all-checks-passed allow prints one stderr line naming the repo
    and the in-scope count, while staying a silent (non-``allow``) permission
    outcome so it does not auto-approve and bypass the normal permission flow.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"{PUSH} origin main"}}),
        capture_output=True,
        text=True,
        cwd=repo,
        env=hook_env(),
    )
    assert done.stdout.strip() == "", "the final allow must stay a silent permission outcome"
    assert "role-review gate: evaluated and ALLOWED" in done.stderr, done.stderr


def test_the_deny_bracket_taxonomy_matches_the_remedy_class(repo: Path, tmp_path: Path) -> None:
    """v0.2.2 gave every deny path a bracketed sub-kind matching its remedy.

    The two POLICY stops whose scope is fully resolvable (unconditional force,
    ref deletion) are [policy], no longer sharing the scope wrapper that
    stated a cause the code knew was false. A genuinely unresolvable option is
    [scope]. A misconfigured/unreadable ledger is [ledger] (fix config/infra),
    distinct from a real open incident's [incident] (run the analyst). No
    allow/deny decision changed; only the message taxonomy.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])

    _, force = judge(repo, f"{PUSH} --force origin main")
    assert "role-review gate: [policy]" in force

    _, deletion = judge(repo, f"{PUSH} origin :main")
    assert "role-review gate: [policy]" in deletion

    _, unknown = judge(repo, f"{PUSH} --frobnicate origin main")
    assert "role-review gate: [scope]" in unknown

    _, ledger = judge(repo, f"{PUSH} origin main", ledger=str(tmp_path / "nowhere"))
    assert "role-review gate: [ledger]" in ledger

    # A non-repo working directory: the "looks like a push but no repo" stop.
    outside = tmp_path / "outside"
    outside.mkdir()
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": f"{PUSH} origin main"}}),
        capture_output=True,
        text=True,
        cwd=outside,
        env=hook_env(),
    )
    repo_deny = json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "role-review gate: [repo]" in repo_deny


# ---------------------------------------------------------------------------
# The CI-green release arm (kit 0.2.18).
#
# These cases exist because this repository DELETED its own bridge hook
# (.claude/hooks/ci_release_gate.py) in the commit that vendored the 0.2.18
# body. The deletion is only defensible if the replacement is proven HERE, on
# this repository's own tree, rather than trusted because the kit says so. Each
# case below drives the real hook end to end with a fake `gh` answering in the
# CLI's own vocabulary.
#
# WHAT THESE DO NOT COVER, printed rather than implied: the gate has three arms
# no case here reaches (OSError, TimeoutExpired, and CI budget exhaustion).
# They are named in the kit's own companion as unreached and are not counted as
# covered by anything in this file.
# ---------------------------------------------------------------------------


def _release_ready(repo: Path) -> str:
    """A repository whose only remaining obstacle to a tag push is CI."""
    head = add_commit(repo, "one")
    git(repo, "tag", "v9.9.9")
    attest(repo, [head])
    attest(repo, [head], kind="release")
    return head


@pytest.mark.parametrize(
    ("label", "payload", "status", "bracket"),
    [
        ("CI still running", CI_RUNNING, 0, "[ci-running]"),
        ("CI failed", CI_RED, 0, "[ci-red]"),
        ("no run at all for the sha", CI_NONE, 0, "[ci-unknown]"),
        ("gh itself failing", "HTTP 401: Bad credentials", 1, "[ci-unknown]"),
    ],
)
def test_a_release_grade_push_is_refused_unless_ci_concluded_successfully(
    repo: Path, label: str, payload: str, status: int, bracket: str
) -> None:
    """Unconcluded, red, absent and unreadable CI all DENY a version tag.

    This is the rule the v0.7.0 tag was published past: it went out fifteen
    seconds after its branch, with CI still running and then red. Both
    attestations are in place in every case here, so nothing but the CI answer
    can be doing the refusing.

    ABSENT and UNREADABLE deny on the same reasoning as the incident ledger: a
    guard that reads its own missing information as permission is not a guard.
    """
    _release_ready(repo)
    decision, reason = judge(repo, f"{PUSH} origin v9.9.9", gh=(payload, status))
    assert decision == "deny", f"{label}: {reason}"
    assert bracket in reason, f"{label}: {reason}"
    assert "v9.9.9" in reason, reason


def test_a_release_grade_push_goes_through_when_ci_is_green(repo: Path) -> None:
    """The negative control. Without it the four refusals above prove only
    that this gate denies release-grade pushes, which any broken gate does.
    """
    _release_ready(repo)
    assert decide(repo, f"{PUSH} origin v9.9.9", gh=(CI_GREEN, 0)) == "allow"


def test_an_ordinary_branch_push_never_asks_ci(repo: Path) -> None:
    """The CI arm fires on a VERSION TAG and on nothing else.

    A gate that asked on every push would spend a rate limit and a network
    round trip on the ninety-nine pushes out of a hundred that publish
    nothing. Driven with `gh` answering RED: an ordinary push must still be
    allowed, which it can only be if the arm was never entered.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin main", gh=(CI_RED, 0)) == "allow"


def test_the_configured_hook_timeout_exceeds_the_gates_own_ci_budget() -> None:
    """A hook the harness kills emits no decision, and no decision is an ALLOW.

    Rescued from the deleted bridge test, which asserted exactly this about
    itself, and it is the one assertion of that file that did not become
    redundant: the kit body carries its own CI_BUDGET_SECONDS and its own
    comment saying a consumer whose hook timeout sits below it "has a gate that
    can fail open on a slow network", while the number that decides it lives in
    THIS repository's settings and cannot be asserted from the kit.

    Measured on arrival: the settings said 30 and the vendored 0.2.18 body
    budgets 50, so taking the gate without touching the wiring would have
    shipped exactly that hole.
    """
    settings = json.loads((HOOK.parents[1] / "settings.json").read_text(encoding="utf-8"))
    configured = [
        hook.get("timeout")
        for entry in settings["hooks"]["PreToolUse"]
        for hook in entry.get("hooks", [])
        if "role_review_gate.py" in hook.get("command", "")
    ]
    assert configured and all(t is not None for t in configured), (
        "the gate is wired with no explicit timeout, so it inherits the "
        "harness default and this assertion cannot be made at all"
    )
    source = HOOK.read_text(encoding="utf-8")
    budget = next(
        float(line.split("=", 1)[1].strip())
        for line in source.splitlines()
        if line.startswith("CI_BUDGET_SECONDS")
    )
    for timeout in configured:
        assert budget < float(timeout), (
            f"the gate budgets {budget}s of CI work under a {timeout}s harness "
            "timeout. If the harness kills it first there is no deny, only "
            "silence, and silence is permission."
        )
