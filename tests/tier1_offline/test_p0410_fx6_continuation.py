"""Coupled continuation cannot establish compatible structural initialization offline."""

import pytest

from pyflightstream.cases.fsi_workspace import validate_workspace_fsi
from pyflightstream.script import Script
from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case


def test_p0410_coupled_continuation_refuses_before_emission(tmp_path):
    case = steady_wing_case(tmp_path)
    script = Script(version="26.125")
    before = script.render()
    with pytest.raises(ValueError, match="compatible structural state and section order"):
        validate_workspace_fsi(case, script, workflow="steady", continuation=True)
    assert script.render() == before
