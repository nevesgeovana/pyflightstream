"""Plan a coupled wing before spending solver time; inspect plan.json's fsi quantities."""

import json
import math
import sys

import pytest

from pyflightstream.cases import Campaign
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import plan_campaign
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case


@pytest.mark.parametrize("stiffness_factor", [1.0, 4.0], ids=["P0410-FSI", "P0410-FSI-STIFF"])
def test_p0410_plan_reports_station_properties_and_natural_frequencies(tmp_path, stiffness_factor):
    case = steady_wing_case(tmp_path)
    cfg = case.fsi
    cfg.blade.bending_stiffness_n_m2 = [2e5 * stiffness_factor] * 9
    campaign = Campaign(name="beam", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace.init(tmp_path / "workspace")
    result = plan_campaign(campaign, workspace, recipes=workflow_registry())
    assert all(point.status == "READY" for point in result.points), [p.error for p in result.points]
    payload = json.loads(result.plan_file.read_text())
    assessment = payload["points"][0].get("fsi", {})
    assert assessment.get("station_properties", {}).get("station_radii_m") == [
        i / 2 for i in range(9)
    ]
    # Uniform cantilever: beta_1^2 sqrt(EI/(mu L^4)), independent analytic oracle.
    expected_hz = 1.875104**2 * math.sqrt(2e5 * stiffness_factor / (3 * 4**4)) / (2 * math.pi)
    assert assessment["natural_frequencies_hz"][0] == pytest.approx(expected_hz, rel=0.02)
    assert assessment["warnings"] == []
