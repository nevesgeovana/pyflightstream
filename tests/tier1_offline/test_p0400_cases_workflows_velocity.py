"""A resolved flight condition cannot silently ignore a VELOCITY cell."""

import pytest

from tests.tier1_offline.test_goal024_point_name import _matrix, _plan


def test_p0400_cw_velocity_a_matrix_row_warns_about_its_ignored_cell(tmp_path):
    """P0400-CW-VELOCITY (PFS-2093.001): TASmps/MACH supplies the planned velocity."""
    requirement = "P0400-CW-VELOCITY"
    workspace, matrix = _matrix(
        tmp_path,
        condition="TASmps:50.0, REmi:2.3, ALPHA:sweep",
        values="0.0",
        cell="VELOCITY: 30.0",
    )
    with pytest.warns(UserWarning, match="VELOCITY.*TASmps/MACH"):
        plan = _plan(workspace, matrix)
    assert not plan.blocked, (requirement, plan.summary())
