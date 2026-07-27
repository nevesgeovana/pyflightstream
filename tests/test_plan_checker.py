"""Tier 1: the vendored kit plan checker stays proven by its mutation test.

``check_plan_kit.py`` is the shared kit plan-ledger validator (Option C: the
strict guards plus the union vocabulary, with the legacy-id grandfather
exemption). A validator is only trustworthy if it can still FAIL the case it
exists to catch, so the kit ships a mutation companion that breaks an entry
each way and confirms the checker rejects it. Founding failure number two of
this whole ledger scheme was a validator that could not fail (a CSV reader
that tolerated malformed rows), so running the mutation test in CI is the
guard on the guard.

The companion resolves the checker as a sibling file (kit 0.2.2 de-hardcoded
the absolute coordination path that previously stopped it running here), so
it exercises the VENDORED copy under .claude/tools, and its fixtures are built
in the OS temp dir, never under _private. Both files are pinned byte-for-byte
by tests/test_kit_drift.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLAN_MUTATIONS = REPO / ".claude" / "tools" / "check_plan_kit_mutations.py"
PLAN_CHECKER = REPO / ".claude" / "tools" / "check_plan_kit.py"


def test_the_plan_checker_can_still_fail() -> None:
    """Every guard in the kit plan checker must reject a broken entry."""
    done = subprocess.run(
        [sys.executable, str(PLAN_MUTATIONS)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, (
        "the kit plan checker failed its mutation test (a guard could not fail "
        f"the case it exists to catch):\n{done.stdout}\n{done.stderr}"
    )


def _run_checker(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PLAN_CHECKER), str(target)],
        capture_output=True,
        text=True,
    )


def test_a_path_that_does_not_resolve_fails_loud(tmp_path: Path) -> None:
    """A missing ledger directory exits non-zero and says so.

    The `plan` skill anchors the ledger path on CLAUDE_PROJECT_DIR precisely
    because a mistyped or stale path must not read as a clean ledger. That
    argument depends on this exit code, and nothing asserted it until the
    2026-07-27 migration moved trees out of `_private/`.
    """
    done = _run_checker(tmp_path / "nowhere")
    assert done.returncode == 1, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    assert "not a directory" in (done.stdout + done.stderr)


def test_an_empty_ledger_directory_exits_zero_and_says_it_checked_nothing(
    tmp_path: Path,
) -> None:
    """An empty directory exits 0. This pins a WEAKNESS, not a guarantee.

    A checker aimed at a directory that exists but holds no entries reports
    success while validating nothing, which is the exact failure mode the
    2026-07-27 migration made reachable: a tree can now move out from under a
    configured path. The sister library registered the same defect
    independently the same day.

    The test asserts the CURRENT contract so a re-vendor cannot change it
    silently. If the kit later decides an empty ledger should exit non-zero,
    this test is the thing that must change with it, deliberately.
    """
    done = _run_checker(tmp_path)
    assert done.returncode == 0, f"stdout={done.stdout!r} stderr={done.stderr!r}"
    assert "no entries" in (done.stdout + done.stderr), (
        "an empty ledger must at least SAY it checked nothing; silence here "
        "would be indistinguishable from a clean ledger"
    )
