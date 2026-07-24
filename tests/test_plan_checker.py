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
