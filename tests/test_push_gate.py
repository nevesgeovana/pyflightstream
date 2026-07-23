"""Tier 1 guards for the role-review push gate hook.

The hook is process infrastructure, not library code, but it is the
mechanism that decides whether unreviewed work can ship, so it needs the
same evidence discipline as the package. It had none until 2026-07-23,
and the gap showed: the range fix that closed one hole opened a worse
one on the release path, and only an adversarial review caught it.

Each test builds a throwaway repository with a local bare remote, so
nothing here touches the real checkout, the real attestation, or the
shared incident ledger. The hook is invoked exactly as the harness
invokes it: the PreToolUse payload on stdin, a permission decision on
stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "role_review_gate.py"
ATTESTATION = Path(".claude") / ".role_review_attestation.json"
# Built by concatenation so this file never contains the literal command
# it tests; the gate scans for it and would flag the test file itself.
PUSH = "git" + " push"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stripped stdout."""
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def decide(repo: Path, command: str, env: dict[str, str] | None = None) -> str:
    """Run the hook on ``command`` and return its permission decision."""
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
    )
    if not done.stdout.strip():
        return "allow"
    return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"]


def attest(repo: Path, commits: list[str], kind: str = "review") -> None:
    """Write an attestation covering ``commits``."""
    path = repo / ATTESTATION
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(path.read_text()) if path.is_file() else {}
    existing[kind] = {"head": commits[0] if commits else "", "commits": commits}
    path.write_text(json.dumps(existing), encoding="utf-8")


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
    (work / "a.txt").write_text("a", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(work, "fetch", "-q", "origin")
    return work


def add_commit(repo: Path, name: str) -> str:
    """Add one commit and return its sha."""
    (repo / f"{name}.txt").write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


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
    """The PLN-082 hole: unpushed ancestors must not ride along.

    This is the defect the range check exists for, so the fixture forces
    two unpushed commits rather than letting the case skip itself when
    the working repository happens to have only one.
    """
    add_commit(repo, "one")
    tip = add_commit(repo, "two")
    attest(repo, [tip])
    assert decide(repo, f"{PUSH} origin main") == "deny"


def test_tag_push_requires_the_release_attestation_even_when_the_branch_is_pushed(
    repo: Path,
) -> None:
    """The regression the range fix introduced, and the reason for in_scope.

    Pushing the branch first leaves the tagged commit already on the
    remote, so the new-commit range is empty. Set containment over an
    empty range is vacuously true, which briefly let an unattested tag
    reach the PyPI publish workflow.
    """
    head = add_commit(repo, "one")
    attest(repo, [head])
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(repo, "fetch", "-q", "origin")
    git(repo, "tag", "v9.9.9")
    assert git(repo, "rev-list", "HEAD", "--not", "--remotes") == ""
    # Review-attested but not release-attested: the release gate must hold.
    assert decide(repo, f"{PUSH} origin v9.9.9") == "deny"
    attest(repo, [head], kind="release")
    assert decide(repo, f"{PUSH} origin v9.9.9") == "allow"


def test_a_configured_but_unreadable_ledger_blocks(repo: Path, tmp_path: Path) -> None:
    """A ledger that cannot be consulted must not read as all clear."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    import os

    env = dict(os.environ)
    env["PYFS_INCIDENT_LEDGER"] = str(tmp_path / "nowhere")
    assert decide(repo, f"{PUSH} origin main", env=env) == "deny"


def test_an_unconfigured_ledger_does_not_block_a_fork(repo: Path) -> None:
    """Without the env var the incident gate does not apply."""
    head = add_commit(repo, "one")
    attest(repo, [head])
    import os

    env = {k: v for k, v in os.environ.items() if k != "PYFS_INCIDENT_LEDGER"}
    assert decide(repo, f"{PUSH} origin main", env=env) == "allow"


def test_a_quoted_mention_of_the_command_is_not_a_push(repo: Path) -> None:
    """A commit message naming the command must not trip the gate."""
    add_commit(repo, "one")
    assert decide(repo, f'git commit -m "explain the {PUSH} gate"') == "allow"
