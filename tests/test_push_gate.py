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
stdout. The incident-ledger variable is stripped from every hook
subprocess so the suite is hermetic; inheriting it would make every case
depend on the state of a ledger outside the repository.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "role_review_gate.py"
ATTESTATION = Path(".claude") / ".role_review_attestation.json"
LEDGER_ENV = "PYFS_INCIDENT_LEDGER"
# Built by concatenation so this file never contains the literal command
# it tests; the gate scans command text and would flag work on this file.
PUSH = "git" + " push"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stripped stdout."""
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def hook_env(ledger: str | None = None) -> dict[str, str]:
    """The environment a hook subprocess runs in.

    The incident-ledger variable is dropped unless the caller sets it, so
    the suite stays hermetic: inheriting a real ledger path would make
    every case depend on state outside the repository, and a real open
    incident would then fail tests that are not about incidents at all.
    """
    env = {k: v for k, v in os.environ.items() if k != LEDGER_ENV}
    if ledger is not None:
        env[LEDGER_ENV] = ledger
    return env


def judge(repo: Path, command: str, ledger: str | None = None) -> tuple[str, str]:
    """Run the hook on ``command`` and return (decision, reason)."""
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        cwd=repo,
        env=hook_env(ledger),
    )
    if not done.stdout.strip():
        return "allow", ""
    out = json.loads(done.stdout)["hookSpecificOutput"]
    return str(out["permissionDecision"]), str(out.get("permissionDecisionReason", ""))


def decide(repo: Path, command: str, ledger: str | None = None) -> str:
    """Run the hook on ``command`` and return its permission decision."""
    return judge(repo, command, ledger)[0]


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


def test_an_unconfigured_ledger_does_not_block_a_fork(repo: Path) -> None:
    """Without the environment variable the incident gate does not apply.

    The shared ledger is one author's local artifact. A clone that never
    configured it must still be able to push once its work is reviewed.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    assert decide(repo, f"{PUSH} origin main") == "allow"


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
    """A push that removes a remote ref is not something the gate can bless."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    decision, reason = judge(repo, f"{PUSH} origin :main")
    assert decision == "deny"
    assert "cannot determine" in reason


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
    assert "INCIDENT GATE" in reason
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
    assert "ROLE-REVIEW GATE" in reason
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
