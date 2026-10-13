# ruff: noqa: N999
"""A reusable setup selects Blade1 and skips Blade2 on a one-blade sector."""

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases._setup_link import family_indices
from pyflightstream.script import Script


@pytest.mark.requirement("FR-435")
@pytest.mark.parametrize("strict", [False, True])
def test_p0400_rfixb_sector_list_uses_missing_family_policy(strict):
    """P0400-RFIXB-SETUP: a numbered list member retains the list's context."""
    case = SimCase(
        sim_id="1",
        aircraft="Rotor",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"IGNORE_MISSING_FAMILIES": "false" if strict else "true"},
    )
    script = Script("26.124")
    script.declare_existing(boundaries={"Blade1": 1})

    def resolve():
        return family_indices(
            case,
            script,
            ["Blade1", "Blade2"],
            keyword="analysis_boundaries",
            preset_key="analysis_families",
            dropped="every boundary is analysed",
        )

    if strict:
        with pytest.raises(CampaignConfigError, match="ignore_missing_families"):
            resolve()
    else:
        assert resolve() == [1]
