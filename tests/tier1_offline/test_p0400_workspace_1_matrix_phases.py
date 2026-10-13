"""P0400-WSPHASES: a flat rotor row's named origin and its row setup keys (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_matrix_run import _flat_rotor_matrix, make_library, stage_geometry

pytestmark = pytest.mark.requirement("P0400-WSPHASES")


def test_p0400_wsphases_a_named_origin_keeps_the_row_setup_keys_out_of_the_variables(tmp_path):
    """P0400-WSPHASES (PFS-2095.029): the bound origin does not put FR-316 keys back."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    (workspace.inputs_dir / "reference_points.toml").write_text(
        "[ARP]\nx_m = 2.0\n\n[ERP1]\nx_m = 4.5\ny_m = 0.0\nz_m = 0.0\n", encoding="utf-8"
    )
    stage_geometry(workspace, "rotor.fsm")
    matrix = _flat_rotor_matrix(tmp_path, "ERP1")
    text = matrix.read_text(encoding="utf-8")
    matrix.write_text(
        text.replace("/ REVOLUTIONS: 0.5", "/ REVOLUTIONS: 0.5 / viscous_coupling: ENABLE"),
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        resolved = resolve_matrix(matrix, workspace, name="flat", fs_version="26.120", recipes={})
    case = resolved.campaign.sims[0]
    assert case.variables["ROTOR_ORIGIN"] == "4.5,0.0,0.0"
    assert case.variables["ROTOR_ORIGIN_POINT"] == "ERP1"
    assert "viscous_coupling" not in case.variables, sorted(case.variables)
    assert case.solver.viscous_coupling is True
