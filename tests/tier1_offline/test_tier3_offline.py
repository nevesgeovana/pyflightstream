"""The one offline control tier 1 keeps over the tier-3 workspace (GOAL-012,
PFS-2031.06).

Tier 3 is a campaign workspace run on a licensed solver. A clone with no seat
can still tell its matrices are sound: every matrix plans with the package to
READY on every active point, and every script the builders render equals its
golden under ``tests/tier3_licensed/goldens``. A change in the package that
moves one of those scripts is seen here, on the row it moves, before any seat
is spent.

``python -m tests.tier3_licensed.offline --write`` regenerates the goldens
when a script is meant to move.
"""

from __future__ import annotations

import pytest

from tests.tier3_licensed import offline

MATRICES = offline.matrices()


def test_the_tier3_workspace_has_matrices():
    assert MATRICES, "tests/tier3_licensed holds no matrix"


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_every_tier3_matrix_plans_ready(matrix):
    count, rendered = offline.render(matrix)
    assert count >= 1
    assert len(rendered) == count, "a ready point rendered no script"


@pytest.mark.parametrize("matrix", MATRICES, ids=[m.name for m in MATRICES])
def test_every_tier3_script_equals_its_golden(matrix):
    count, absent, differ = offline.compare(matrix)
    assert not absent, (
        f"{len(absent)} of {count} scripts have no golden: {absent[:4]}; regenerate with "
        "python -m tests.tier3_licensed.offline --write"
    )
    assert not differ, (
        f"{len(differ)} of {count} scripts differ from their golden: {differ[:4]}; a moved "
        "script is either a defect or a golden to regenerate, and the diff says which"
    )
