"""Tier 1: load_campaign refuses every malformed file with CampaignConfigError (0.40.0)."""

import pytest

from pyflightstream.cases import CampaignConfigError, load_campaign

CAMPAIGN_TOML = """
[campaign]
name = "wing_steady_sweep"
fs_version = "26.120"
fs_exe = 'C:/FlightStream/FlightStream.exe'

[[sim]]
sim_id = "9001"
aircraft = "TestWing"
description = "steady polar"
reynolds = 4.38e6
mach = 0.1441
sweep = {type = "alpha", values = [0.0, 2.0]}
recipe = "recipes.steady_polar:build"
outputs = ["loads_{point}.txt"]
"""


def test_p0400_sims_key_in_campaign_table_is_refused_by_name(tmp_path):
    """P0400-SIMS-KEY (PFS-2095.001): [campaign] sims names the [[sim]] form, not a TypeError."""
    path = tmp_path / "campaign.toml"
    path.write_text(
        CAMPAIGN_TOML.replace('name = "wing', 'sims = []\nname = "wing'), encoding="utf-8"
    )
    with pytest.raises(CampaignConfigError, match=r"'sims'.*\[\[sim\]\] entry per case"):
        load_campaign(path)


def test_p0400_validator_refusal_arrives_as_campaign_config_error(tmp_path):
    """P0400-VALIDATION (PFS-2081.31): a model refusal is the documented CampaignConfigError."""
    path = tmp_path / "campaign.toml"
    path.write_text(
        CAMPAIGN_TOML.replace("[0.0, 2.0]}", "[0.0, 2.0], held = {mach = 0.2}}"),
        encoding="utf-8",
    )
    with pytest.raises(
        CampaignConfigError, match=r"does not load(.|\n)*not a point axis"
    ) as caught:
        load_campaign(path)
    assert str(path) in str(caught.value), "the refusal does not name the file"


def test_p0400_toml_syntax_error_arrives_as_campaign_config_error(tmp_path):
    """P0400-TOML-SYNTAX (PFS-2085.001): a TOMLDecodeError is re-raised naming path and line."""
    path = tmp_path / "campaign.toml"
    path.write_text(CAMPAIGN_TOML + "broken = \n", encoding="utf-8")
    with pytest.raises(CampaignConfigError, match=r"does not load.*line 16") as caught:
        load_campaign(path)
    assert str(path) in str(caught.value), "the refusal does not name the file"
