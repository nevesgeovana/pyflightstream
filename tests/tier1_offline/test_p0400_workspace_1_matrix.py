"""P0400-WSMATRIX: the POLs a workspace already claims (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import pytest

from pyflightstream.workspace.matrix import PolChange, renumber_repeated_pols
from tests.tier1_offline.test_goal021_matrix_ids import _matrix, _workspace, row

pytestmark = pytest.mark.requirement("P0400-WSMATRIX")


def test_p0400_wsmatrix_a_compacted_simulation_claims_its_pol(tmp_path):
    """P0400-WSMATRIX (PFS-2085.020): sims/sim_<id>.zip is evidence, and a new POL passes it."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8001, run=0)])
    (workspace.root / "sims").mkdir(parents=True, exist_ok=True)
    (workspace.root / "sims" / "sim_9800.zip").write_bytes(b"PK")
    changes = renumber_repeated_pols(matrix, workspace)
    assert changes == [PolChange(row_number=2, old="8001", new="9801")], changes


def test_p0400_wsmatrix_a_batch_simulation_claims_its_pol(tmp_path):
    """P0400-WSMATRIX (PFS-2085.020): sims/batch/<label>/sim_<id> claims its id too."""
    workspace = _workspace(tmp_path)
    matrix = _matrix(workspace.root, "planned.fs", [row(8001), row(8001, run=0)])
    (workspace.root / "sims" / "batch" / "planned_b1" / "sim_9900").mkdir(parents=True)
    changes = renumber_repeated_pols(matrix, workspace)
    assert changes == [PolChange(row_number=2, old="8001", new="9901")], changes
