"""P0400-CW-EXPORTS: the end-of-run export block and the solver log it may write.

0.40.0 item PFS-2096.003: LOG_OUTPUT's overwrite guard knew only the loads
table's position, so a log pointed at the VTK was written over it.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script

OUTPUTS = ["loads_a.txt", "surf_a.vtk", "loads_a_log.txt"]


def _steady(log_output: str) -> SimCase:
    return SimCase(
        sim_id="7002",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=OUTPUTS,
        variables={"WORKFLOW": "steady", "VELOCITY": "30.0", "LOG_OUTPUT": log_output},
        point={"alpha": 0.0},
    )


def test_p0400_cw_exports_a_log_pointed_at_the_vtk_is_refused():
    """P0400-CW-EXPORTS (PFS-2096.003): position 2 is the VTK this block already exports."""
    requirement = "P0400-CW-EXPORTS"
    with pytest.raises(CampaignConfigError, match="already exports 'surf_a.vtk' there") as refusal:
        build_script(_steady("2"), Script("26.124"))
    assert str(refusal.value), requirement


def test_p0400_cw_exports_a_log_pointed_at_its_own_entry_is_exported():
    """P0400-CW-EXPORTS (PFS-2096.003), control: position 3 is the log's own entry."""
    requirement = "P0400-CW-EXPORTS"
    script = Script("26.124")
    build_script(_steady("3"), script)
    lines = script.render().splitlines()
    assert "EXPORT_LOG" in lines, requirement
    assert lines[lines.index("EXPORT_LOG") + 1] == "loads_a_log.txt"
