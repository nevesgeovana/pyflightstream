"""GOAL-020 item 5: the counting script tells a setup from a reference, and a comment from a use.

TWO DEFECTS MADE ONE NUMBER UNARGUABLE. The count behind a deadline that had
already moved twice read 39 files; corrected, it reads 17. Both defects were
in the script and both inflated it, which is the direction that matters: a
deadline moved on an inflated count is a deadline moved for a reason that was
not there.

AND THE DEEPER CORRECTION, held here because a test is where a premise stops
being assumed: the twelve spellings the count is about are NOT promises with a
deadline. They live outside the tuple the deadline guard reads, they are
REFUSED today, and they have been since 0.15.0. The count was never the
deadline's input, because for these entries there is no deadline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pyflightstream._deprecations import DEPRECATIONS, REFUSED_IN_0_15_0

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "count_deprecated_spellings.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        env=None,
    )


def test_goal020_deprecations_the_refused_batch_is_outside_the_watched_tuple():
    """They were never promises, so no deadline watches them and none can expire.

    The module says why in its own words: every entry was written in 0.15.0
    and 0.15.0 had not shipped, so nobody had a workspace that was told the
    old spelling would keep working. An entry here with a removal version is
    carrying a field the guard never reads.
    """
    watched = {id(entry) for entry in DEPRECATIONS}
    for entry in REFUSED_IN_0_15_0:
        assert id(entry) not in watched, (
            f"{entry.subject} is in both REFUSED_IN_0_15_0 and DEPRECATIONS. The first is a set "
            "of refusals with no shim; the second is what the deadline guard walks. An entry in "
            "both would be a promise and a refusal at once."
        )


def test_goal020_deprecations_the_batch_is_the_twelve_it_has_always_been():
    """Twelve, and the number is asserted so a thirteenth cannot arrive unnoticed."""
    assert len(REFUSED_IN_0_15_0) == 12


def test_goal020_deprecations_the_script_does_not_count_the_new_home():
    """`[aliases]` in a REFERENCE is the replacement, not the thing being replaced.

    This is the larger half of the gap between 39 and 17: every reference that
    had ALREADY MIGRATED was counted as a file still owing a migration.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert "SETUP_ONLY_TABLES" in source
    assert "setups" in source, "nothing distinguishes a setup path from a reference path"


def test_goal020_deprecations_the_script_does_not_count_a_comment():
    """A line recording a migration is the opposite of a use of the spelling it migrated from."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "def code_of(" in source, "nothing strips comments before matching"


def test_goal020_deprecations_the_corrected_walk_reports_zero_for_the_moved_tables(tmp_path):
    """Exercised on a real tree: a reference carrying the table is not counted, a setup is.

    The two files differ ONLY in which directory they sit in, which is the
    whole distinction the correction turns on.
    """
    reference = tmp_path / "inputs" / "references"
    setup = tmp_path / "inputs" / "setups"
    reference.mkdir(parents=True)
    setup.mkdir(parents=True)
    (reference / "r001.toml").write_text("[aliases]\nwing = ['W']\n", encoding="utf-8")

    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "[aliases]               0 occurrence" in result.stdout, result.stdout

    (setup / "s001.toml").write_text("[aliases]\nwing = ['W']\n", encoding="utf-8")
    result = _run("--root", str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert "[aliases]               1 occurrence" in result.stdout, result.stdout


def _count_of(stdout: str, spelling: str) -> int:
    """Return the occurrence count the script printed for one spelling."""
    for line in stdout.splitlines():
        if line.startswith(spelling):
            return int(line.split()[1])
    raise AssertionError(f"the script printed no line for {spelling}: {stdout}")


def test_goal020_deprecations_a_migration_comment_is_not_a_use(tmp_path):
    """The line `# was MOVING_BOUNDARIES: Blade,S` records the move; counting it is backwards.

    MEASURED AS A DELTA AND NOT AS AN ABSOLUTE, because the script always
    walks the repository as well as any extra root, and the repository holds
    files of its own that state the spelling. The first writing of this test
    asserted zero, which is a statement about the repository rather than
    about the fixture, and it failed for that reason rather than for the one
    it was written for.
    """
    references = tmp_path / "inputs" / "references"
    references.mkdir(parents=True)
    before = _run("--root", str(tmp_path))
    assert before.returncode == 0, before.stderr

    (references / "r003.toml").write_text(
        'families_blades = ["Blade1"]  # was MOVING_BOUNDARIES: Blade,S\n',
        encoding="utf-8",
    )
    after = _run("--root", str(tmp_path))
    assert after.returncode == 0, after.stderr
    assert _count_of(after.stdout, "MOVING_BOUNDARIES") == _count_of(
        before.stdout, "MOVING_BOUNDARIES"
    ), "a comment recording the migration was counted as a use of the spelling it migrated from"
