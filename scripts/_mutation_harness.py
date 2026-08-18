"""Shared harness for the mutation batteries under ``scripts/``.

Extracted on 2026-08-11 after a second battery was written from scratch
and re-introduced three defects the first one had already paid for and
documented in its own comments: it executed at import with no ``main``
guard, it destroyed the previous backup before taking a new one (so a
run killed mid-mutant made the mutation the new "original" and restored
it permanently), and it built its backup path as ``REPO / ".git"``,
which is a FILE in a linked worktree, where this workspace parks
reviewer agents by standing practice.

That is the class. A battery declares its mutant table and nothing
else; parking, recovery, the git directory and the interpreter live
here once.

Nothing in ``src/`` imports this, and nothing here imports ``src``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: The interpreter RUNNING this, never a guessed path. A hardcoded
#: ``.venv/Scripts/python.exe`` is Windows-only and wrong on any
#: checkout whose environment lives elsewhere, and the failure arrives
#: per mutant, after the tree is already mutated.
PYTHON = Path(sys.executable)


def _git_dir() -> Path:
    """Return the git directory of this checkout, worktree or not."""
    done = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        # Explicit, and identical to the inherited default: git needs
        # the ambient environment to find its own configuration.
        env=os.environ.copy(),
    )
    resolved = done.stdout.strip()
    return Path(resolved) if resolved else REPO / ".git"


#: Where an in-flight mutant's ORIGINAL bytes are parked, so a run that
#: is killed can be undone by the NEXT one. A ``finally`` does not
#: survive a SIGKILL, and this workspace has an incident about a review
#: process dying with mutations left in the tree (PLN-20260806-1400).
BACKUP = _git_dir() / "mutation-backup"


def slot(path: Path) -> Path:
    """Return the backup file for one repository path."""
    return BACKUP / path.relative_to(REPO).as_posix().replace("/", "%")


def park(path: Path, original: bytes) -> None:
    """Record a file's original bytes before it is mutated."""
    BACKUP.mkdir(parents=True, exist_ok=True)
    slot(path).write_bytes(original)


def unpark(path: Path) -> None:
    """Forget a recorded original, the mutation having been undone."""
    slot(path).unlink(missing_ok=True)


def recover() -> list[str]:
    """Undo any mutation a previous run was killed in the middle of.

    Called FIRST, before anything is mutated, and a caller that gets a
    non-empty answer refuses to continue: a battery that starts from a
    mutated tree measures the wrong tree.
    """
    if not BACKUP.is_dir():
        return []
    restored: list[str] = []
    for parked_slot in sorted(BACKUP.iterdir()):
        target = (REPO / parked_slot.name.replace("%", "/")).resolve()
        if REPO.resolve() not in target.parents:
            # A recovery tool that can write outside the tree it is
            # recovering is a worse problem than the one it solves.
            restored.append(f"{parked_slot.name} (REFUSED: resolves outside the repository)")
            continue
        parked = parked_slot.read_bytes()
        if parked:
            target.write_bytes(parked)
            restored.append(target.relative_to(REPO).as_posix())
        else:
            target.unlink(missing_ok=True)
            restored.append(f"{target.relative_to(REPO).as_posix()} (deleted)")
        parked_slot.unlink()
    return restored


#: pytest's exit codes. 1 is a test FAILING, which is the only one that
#: means a guard denied. 2 is a collection or internal error, 3 an
#: interrupt, 4 a usage error and 5 "no tests were selected"; every one of
#: those is non-zero and none of them is a kill.
_PYTEST_FAILED = 1
_PYTEST_NO_TESTS = 5


def verdict(test: str, timeout_s: float = 900.0) -> tuple[str, str]:
    """Run one test selection and classify the outcome in THREE values.

    Returns ``("KILLED" | "SURVIVED" | "INCONCLUSIVE", tail)``.

    WHY THREE AND NOT TWO. Four batteries written on 2026-08-17 read a
    kill off ``returncode != 0``. pytest exits 1 on a failure, 2 on a
    collection or import error, 4 on a usage error and 5 when the
    selection matched no test; three of those four are not a guard
    denying, and all four were counted as kills, after which the battery
    printed "N of N mutants killed" and exited 0. A mutant that stops the
    suite from importing proves nothing about the guard, and a selector
    that matches nothing proves less. The pattern is lifted from
    ``prove_evidence_guards.py``, which had it from the start and whose
    docstring is where this reasoning was already written down.

    NO TESTS SELECTED IS ITS OWN TRAP and is why the numeric code is read
    rather than only the summary text: a battery whose test id drifts
    selects nothing, and an empty run prints no "failed" and no "passed".

    Parameters
    ----------
    test : str
        A pytest node id or file path.
    timeout_s : float
        Bound on the child. A timeout is INCONCLUSIVE and is reported
        rather than retried.
    """
    argv = [str(PYTHON), "-m", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"]
    try:
        done = subprocess.run(
            argv,
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return "INCONCLUSIVE", f"timed out after {timeout_s:.0f}s"
    out = done.stdout + done.stderr
    tail = " | ".join(line for line in out.splitlines()[-3:] if line.strip())
    if done.returncode == _PYTEST_NO_TESTS:
        return "INCONCLUSIVE", f"no test matched {test!r}: {tail}"
    if done.returncode == _PYTEST_FAILED and " failed" in out:
        return "KILLED", tail
    if done.returncode == 0 and " passed" in out:
        return "SURVIVED", tail
    return "INCONCLUSIVE", f"exit {done.returncode}: {tail}"


def apply_mutant(path: Path, live: str, stale: str) -> bytes:
    """Return ``path``'s bytes with ONE occurrence of ``live`` replaced.

    Two properties, both of which a battery has silently lost here.

    THE ANCHOR IS ASSERTED PRESENT AND UNIQUE. A mutant whose anchor has
    drifted replaces nothing, so the battery measures the UNMUTATED tree
    and reports SURVIVED or, worse, reports a kill it did not earn. This
    happened three times on 2026-08-17 alone: twice when a formatter
    reflowed an anchored line, and once when ``git show HEAD:<path>`` was
    used as the anchor and stopped being the pre-fix text the moment the
    fix was committed.

    LINE ENDINGS ARE TRANSLATED ONTO THE TARGET. Two files in this
    repository are CRLF on disk, and a line-feed anchor matches nothing
    in them, which is the same vacuous pass wearing a different hat.

    Raises
    ------
    SystemExit
        If the anchor is absent or appears more than once, or if the
        replacement leaves the file unchanged.
    """
    original = path.read_bytes()
    text = original.decode("utf-8")
    if "\r\n" in text:
        live = live.replace("\n", "\r\n")
        stale = stale.replace("\n", "\r\n")
    found = text.count(live)
    if found != 1:
        raise SystemExit(
            f"{path}: the anchor appears {found} times, expected exactly 1. A mutant "
            f"that replaces nothing measures the unmutated tree: {live.strip()[:70]!r}"
        )
    mutated = text.replace(live, stale).encode("utf-8")
    if mutated == original:
        raise SystemExit(f"{path}: the mutant is byte-identical to the tree, so it mutates nothing")
    return mutated
