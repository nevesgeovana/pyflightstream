"""Tier 1: SIM model, campaign.toml loading, sweeps, and recipes."""

import pytest
from pydantic import ValidationError

from pyflightstream.cases import (
    Campaign,
    SimCase,
    SweepAxis,
    load_campaign,
    point_tag,
    resolve_recipe,
)

CAMPAIGN_TOML = """
[campaign]
name = "wing_steady_sweep"
fs_version = "26.12"
fs_exe = 'C:\\FlightStream\\26.12\\FlightStream.exe'

[[sim]]
sim_id = "9001"
aircraft = "TestWing"
description = "steady polar"
reynolds = 4.38e6
mach = 0.1441
sweep = {type = "alpha_beta", values = [[0.0, 0.0], [2.0, 0.0]]}
recipe = "recipes.steady_polar:build"
outputs = ["loads.txt"]
[sim.variables]
advance_ratio = 1.7
symmetry = "PERIODIC 6"
"""


def test_load_campaign_reads_the_sad_shape(tmp_path):
    path = tmp_path / "campaign.toml"
    path.write_text(CAMPAIGN_TOML, encoding="utf-8")
    campaign = load_campaign(path)
    assert campaign.name == "wing_steady_sweep"
    assert campaign.fs_version == "26.12"
    case = campaign.sims[0]
    assert case.sim_id == "9001"
    assert case.variables["symmetry"] == "PERIODIC 6"
    assert list(case.sweep.points()) == [
        {"alpha": 0.0, "beta": 0.0},
        {"alpha": 2.0, "beta": 0.0},
    ]


def test_load_campaign_without_campaign_table_is_didactic(tmp_path):
    path = tmp_path / "campaign.toml"
    path.write_text("[[sim]]\nsim_id = '1'\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"no \[campaign\] table"):
        load_campaign(path)


def test_unregistered_fs_version_fails_at_load():
    with pytest.raises(ValidationError, match="fs_version"):
        Campaign(name="c", fs_version="99.999", fs_exe="C:/fs.exe", sims=[])


def test_sweep_points_per_axis_type():
    assert list(SweepAxis(type="alpha", values=[-2.0, 0.0]).points()) == [
        {"alpha": -2.0},
        {"alpha": 0.0},
    ]
    assert list(SweepAxis(type="advance_ratio", values=[1.7]).points()) == [{"advance_ratio": 1.7}]


def test_sweep_values_must_match_the_axis_type():
    with pytest.raises(ValidationError, match="scalar values"):
        SweepAxis(type="alpha", values=[[0.0, 1.0]])
    with pytest.raises(ValidationError, match="pairs"):
        SweepAxis(type="alpha_beta", values=[2.0])


def test_point_tag_is_stable_and_signed():
    assert point_tag({"alpha": 2.0, "beta": 0.0}) == "a+02.0_b+00.0"
    assert point_tag({"alpha": -4.0}) == "a-04.0"
    assert point_tag({"advance_ratio": 1.7}) == "j+01.7"
    with pytest.raises(ValueError, match="no known axis"):
        point_tag({"mystery": 1.0})


def test_sim_case_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="extra"):
        SimCase(
            sim_id="1",
            aircraft="w",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            recipe="m:f",
            not_a_field=True,
        )


def test_resolve_recipe_validates_the_reference_form():
    with pytest.raises(ValueError, match="package.module:function"):
        resolve_recipe("just_a_name")
    with pytest.raises(ValueError, match="cannot be imported"):
        resolve_recipe("no.such.module:build")
    with pytest.raises(ValueError, match="does not name a callable"):
        resolve_recipe("pyflightstream.cases:CAMPAIGN_CONSTANT")
    assert resolve_recipe("pyflightstream.cases:load_campaign") is load_campaign
