"""Tier 1: the vendored ``ci_state.py`` still answers, and still can fail.

``ci_state.py`` arrived on 2026-08-11 with the 0.2.18 push gate, which RUNS it
as a subprocess on a release-grade push and treats its absence as a refusal
rather than a skip. It is the body that decides what CI concluded about one
commit, in four states, with the rule that UNKNOWN is never green.

This file is the same shape as ``test_plan_checker.py`` and
``test_skill_invocation.py``: a vendored checker is only as good as the
companion that proves it, and a checker shipped without its mutations is what
the kit's own review lens once refused a promotion for. The companion places a
REAL fake ``gh`` executable on PATH and drives the real CLI, so the subprocess
layer is under test rather than a stubbed function; it then applies each mutant
to a copy of the body and re-runs every case, so a case that does not
discriminate fails the run.

Every mutant in that companion is a way to FAIL OPEN, which is the only failure
direction that matters here: a checker that says GREEN when it does not know
turns a push nobody verified into a lane that reports itself closed. That is
``INC-20260802-1450-shared``, a gate that failed open, which this project has
already paid for once.

The gate side of the same rule (the refusal itself, at the push boundary) is
pinned separately in ``tests/test_push_gate.py``. Neither file covers the
other's half, and neither covers the gate's three unreached arms (``OSError``,
``TimeoutExpired``, budget exhaustion), which the kit's own companion prints as
unreached on every run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CI_STATE = REPO / ".claude" / "hooks" / "ci_state.py"
CI_STATE_MUTATIONS = REPO / ".claude" / "hooks" / "ci_state_mutations.py"


def test_ci_state_is_vendored_beside_the_gate() -> None:
    """Absent, this body makes every release-grade push deny with [ci-config].

    The gate's ``_ci_state_body`` looks beside itself FIRST and then walks a
    short list of vendor directories. Vendoring it anywhere else would still
    work and would still be wrong: the pair belongs together, and the itaca
    lane that vendored the gate without this file spent the difference finding
    out that a missing file reads as a gate defect.
    """
    assert CI_STATE.is_file(), f"{CI_STATE} is missing; the 0.2.18 gate refuses without it"
    assert CI_STATE_MUTATIONS.is_file(), "the checker is vendored without its guard evidence"


def test_the_ci_state_guard_evidence_still_holds() -> None:
    """Run the vendored companion: every case holds and every mutant dies."""
    done = subprocess.run(
        [sys.executable, str(CI_STATE_MUTATIONS)],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert done.returncode == 0, f"ci_state guard evidence failed:\n{done.stdout}\n{done.stderr}"
    # The companion asserts each mutation anchor is PRESENT before applying it,
    # and says so in its own output. Asserting the sentence keeps a run that
    # applied no mutant at all from passing as one that applied them.
    assert "each asserted present before it is applied" in done.stdout, done.stdout
    assert "Every case holds and every mutant is denied." in done.stdout, done.stdout
