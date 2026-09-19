"""B07 and B10: refuse ambiguous headings and explain steady probe parameters at plan."""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import Campaign, PprocSpec
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import plan_campaign
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_workflows import (
    _wb_geometry,
    _with_pproc,
    steady_case,
    unsteady_case,
)


@pytest.mark.parametrize(
    "column",
    [
        "ALPHA",
        "BETA",
        "MACH",
        "RE",
        "VINF",
        "VREF",
        "ALT",
        "RHO",
        "TEMP",
        "MU",
        "J",
        "SREF",
        "CREF",
        "BREF",
        "REDUCTION",
        "ROTOR",
        "WINDOW",
        "FIRST_STEP",
        "LAST_STEP",
        "STEPS",
        "XMOM",
        "YMOM",
        "ZMOM",
    ],
)
def test_b07_reserved_reduction_heading_is_refused_at_validation(column):
    with pytest.raises(ValidationError) as refused:
        PprocSpec(names={"FX_ROTOR": column})
    assert "FX_ROTOR" in str(refused.value) and column in str(refused.value)
    assert "reserved" in str(refused.value)


def test_b07_noncolliding_reduction_heading_passes_validation():
    assert PprocSpec(names={"FX_ROTOR": "THRUST"}).names == {"FX_ROTOR": "THRUST"}


@pytest.mark.parametrize("unsteady, parameters", [(False, ["MACH"]), (True, ["MACH"]), (False, [])])
def test_b10_plan_warns_only_for_enabled_steady_probe_parameters(tmp_path, unsteady, parameters):
    pproc = PprocSpec(
        probes=[
            {
                "frame": "MRP",
                "parameters": parameters,
                "points": 2,
                "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
            }
        ]
    )
    case = _with_pproc(
        (unsteady_case if unsteady else steady_case)(), _wb_geometry(tmp_path), pproc
    )
    workspace = CampaignWorkspace.init(tmp_path / "plan")
    campaign = Campaign(name="probe_plan", fs_version="26.120", fs_exe="unused.exe", sims=[case])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_campaign(
            campaign, workspace=workspace, recipes=workflow_registry(), write_plan=False
        )
    assert not plan.blocked, plan.summary()
    messages = [
        str(w.message)
        for w in caught
        if issubclass(w.category, PyflightstreamWarning) and "does not filter" in str(w.message)
    ]
    if not unsteady and parameters:
        assert messages, "plan did not warn that steady probe parameters do not filter the export"
        assert all("[[probes]] entry 1" in message and "MRP" in message for message in messages)
    else:
        assert not messages
