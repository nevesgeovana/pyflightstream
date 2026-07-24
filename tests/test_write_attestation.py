"""Tier 1 guards for the attestation writer that clears the push gate.

The writer (``.claude/hooks/write_attestation.py``) is the only sanctioned
way to stamp the record the push gate reads, so a defect here either
blocks an honest release or admits a dishonest one. The sister library
shipped this hardened writer with NO automated test of its own; this
file closes that gap for pyflightstream. Two properties matter most and
are pinned here:

- a single invocation that names several refs must cover EVERY ref's
  tip, because the release-day push (a branch and its tag together) is
  one command, and an earlier writer that stamped one ref per run lost
  the first ref when the second run overwrote it; and
- an unknown pass token must be REFUSED, not recorded, because this file
  is an audit record and the likeliest slip once refs matter is passing
  a ref where the passes belong, which would write a fabricated line
  into the one file whose whole job is being trustworthy.

Each test builds a throwaway repository with a local bare remote and
invokes the writer exactly as an operator would, by path with the real
interpreter, so nothing here touches the real checkout or attestation.
The writer is invoked with PYTHONPATH cleared, so an editable dev
install of the package cannot shadow the working-tree script and mask a
falsified guard.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

WRITER = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "write_attestation.py"
ATTESTATION = Path(".claude") / ".role_review_attestation.json"


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stripped stdout."""
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def run_writer(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the writer by path with PYTHONPATH cleared.

    Clearing PYTHONPATH matters: with the package installed editable, an
    importable shadow of the script could otherwise run in place of the
    working-tree file, and a falsified guard would look killed while the
    real file still admitted the bad input.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, str(WRITER), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def add_commit(repo: Path, name: str) -> str:
    """Add one commit and return its sha."""
    (repo / f"{name}.txt").write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


def read_attestation(repo: Path, kind: str = "review") -> dict:
    """Return the attestation entry for ``kind`` (empty dict if absent)."""
    path = repo / ATTESTATION
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get(kind, {})


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
    git(work, "branch", "-M", "main")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git(work, "fetch", "-q", "origin")
    return work


def test_a_two_ref_invocation_covers_both_tips(repo: Path) -> None:
    """The release-day push names a branch and a tag in one command.

    Both ref tips must land in ``commits``. Stamping one ref per run made
    a two-ref release unattestable, because the second run overwrote the
    first, and the gate then denied a push nothing was wrong with.
    """
    main_tip = add_commit(repo, "one")
    git(repo, "tag", "v9.9.9")  # tag sits at main's tip
    git(repo, "branch", "side")
    git(repo, "checkout", "-q", "side")
    side_tip = add_commit(repo, "sidework")
    git(repo, "checkout", "-q", "main")

    done = run_writer(repo, "review", "architect,qa", "main", "side")
    assert done.returncode == 0, done.stderr
    entry = read_attestation(repo)
    assert main_tip in entry["commits"], entry
    assert side_tip in entry["commits"], entry
    assert entry["refs"] == ["main", "side"], entry
    assert entry["passes"] == ["architect", "qa"], entry


def test_a_tag_and_branch_in_one_run_are_both_covered(repo: Path) -> None:
    """The literal release command: `write_attestation review <passes> main v9.9.9`."""
    tip = add_commit(repo, "one")
    git(repo, "tag", "v9.9.9")
    done = run_writer(repo, "release", "architect", "main", "v9.9.9")
    assert done.returncode == 0, done.stderr
    entry = read_attestation(repo, kind="release")
    # Both refs resolve to the same commit here; the point is that naming
    # the tag as a second ref does not drop the branch's coverage.
    assert tip in entry["commits"], entry
    assert entry["refs"] == ["main", "v9.9.9"], entry


def test_a_bogus_pass_token_exits_nonzero_and_writes_nothing(repo: Path) -> None:
    """An unknown pass is refused, not recorded.

    A silently mistyped audit line is worse than none, so the writer must
    fail before touching the file rather than stamp a pass name nobody
    defined.
    """
    add_commit(repo, "one")
    done = run_writer(repo, "review", "architetc", "main")  # misspelled 'architect'
    assert done.returncode != 0, done.stdout
    assert "unknown or empty passes" in done.stderr.lower() or "unknown" in (done.stderr.lower())
    # Nothing was written: a refused run must not leave a partial record.
    assert not (repo / ATTESTATION).is_file(), "a refused run wrote an attestation"


def test_a_ref_passed_where_passes_belong_is_refused(repo: Path) -> None:
    """The exact slip the passes validation exists to catch.

    Once the ref matters, the likeliest mistake is putting it in the
    passes slot. Recording ``v0.2.0`` as a pass would fabricate the audit
    line the whole mechanism depends on.
    """
    add_commit(repo, "one")
    git(repo, "tag", "v0.2.0")
    done = run_writer(repo, "review", "v0.2.0", "main")
    assert done.returncode != 0, done.stdout
    assert not (repo / ATTESTATION).is_file()


def test_no_passes_at_all_is_refused(repo: Path) -> None:
    """An empty passes list is not a valid attestation."""
    add_commit(repo, "one")
    done = run_writer(repo, "review", "", "main")
    assert done.returncode != 0, done.stdout


def test_a_valid_single_ref_run_records_head_and_passes(repo: Path) -> None:
    """The ordinary case: one ref, known passes, HEAD covered."""
    tip = add_commit(repo, "one")
    done = run_writer(repo, "review", "architect,qa,vv,tech-writer,api-designer", "main")
    assert done.returncode == 0, done.stderr
    entry = read_attestation(repo)
    assert entry["head"] == tip
    assert tip in entry["commits"]
    assert entry["passes"] == ["architect", "qa", "vv", "tech-writer", "api-designer"]


def test_an_unresolvable_ref_exits_nonzero(repo: Path) -> None:
    """A ref that does not resolve is an error, not an empty attestation."""
    add_commit(repo, "one")
    done = run_writer(repo, "review", "architect", "no-such-ref")
    assert done.returncode != 0, done.stdout


def test_a_single_ref_covers_non_tip_unpushed_ancestors(repo: Path) -> None:
    """One ref, several unpushed commits: every ancestor, not just the tip.

    This is the property the writer exists for ("Stamping only HEAD let
    unpushed ancestors ship unreviewed"), and the two-ref test above does
    not falsify it: there each asserted commit is some ref's tip. Here B
    is a NON-tip commit reachable from main but not on the remote, so a
    regression to `rev-list -n 1 ref` (tip only) drops it and this fails.
    """
    b = add_commit(repo, "b")  # unpushed ancestor
    c = add_commit(repo, "c")  # unpushed tip
    done = run_writer(repo, "review", "architect", "main")
    assert done.returncode == 0, done.stderr
    entry = read_attestation(repo)
    assert c in entry["commits"], entry
    assert b in entry["commits"], "a non-tip unpushed ancestor was dropped"


def test_the_record_stamps_the_committer_date_not_the_wall_clock(repo: Path) -> None:
    """The timestamp is the committer date (%cI), so the record is deterministic.

    A regression to a wall-clock now() would reintroduce nondeterminism
    into an audit record and otherwise ship green.
    """
    tip = add_commit(repo, "one")
    done = run_writer(repo, "review", "architect", "main")
    assert done.returncode == 0, done.stderr
    entry = read_attestation(repo)
    assert entry["commit_date"] == git(repo, "show", "-s", "--format=%cI", tip)
