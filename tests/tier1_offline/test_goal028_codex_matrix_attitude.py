"""Conflicting attitude declarations must not be resolved by silent overwrite."""

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix
from tests.tier1_offline.test_goal024_point_name import _matrix


@pytest.mark.parametrize("angle", ["ALPHA", "BETA"])
def test_attitude_in_two_cells_is_refused(tmp_path, angle):
    other = "BETA" if angle == "ALPHA" else "ALPHA"
    _, matrix = _matrix(
        tmp_path,
        condition=f"MACH:0.2, {other}:sweep, {angle}:3",
        values="0",
        cell=f"{angle}:9",
    )
    with pytest.raises(MatrixError, match=angle):
        read_matrix(matrix)
