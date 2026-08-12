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
