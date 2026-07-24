"""Tier 1: SIM model, campaign.toml loading, sweeps, and recipes."""

import pytest
from pydantic import ValidationError

from pyflightstream.cases import (
    Campaign,
    SimCase,
    SolverSettings,
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
outputs = ["loads_{point}.txt"]
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
    resolved = resolve_recipe("tests.test_cases:protocol_recipe")
    assert resolved.__name__ == protocol_recipe.__name__


def protocol_recipe(case, script) -> None:
    """A recipe of the shape the campaign loop calls."""


def loose_recipe(workdir):
    """The pre-protocol shape everyone arriving from a driver script has."""


@pytest.mark.parametrize(
    ("recipe", "accepted"),
    [
        (lambda case, script: None, True),
        (lambda *args: None, True),  # variadic: the loop can call it
        (lambda case, script, extra=None: None, True),
        (lambda workdir: None, False),  # the loose builder
        (lambda a, b, c: None, False),
        (lambda **kwargs: None, False),
        (lambda case, script, *, tol: None, False),  # unfillable keyword
    ],
)
def test_check_recipe_accepts_what_the_loop_can_call(recipe, accepted):
    from pyflightstream.cases import check_recipe

    if accepted:
        check_recipe("m:f", recipe)
    else:
        with pytest.raises(ValueError, match="does not satisfy the ScriptRecipe protocol"):
            check_recipe("m:f", recipe)


def test_check_recipe_passes_what_it_cannot_inspect():
    from pyflightstream.cases import check_recipe

    # print has no readable signature; the library does not refuse what
    # it cannot inspect, it lets the loop's own TypeError speak.
    check_recipe("builtins:print", print)


def test_resolve_recipe_refuses_the_loose_builder_signature():
    # Called by the loop this raises a bare TypeError once per point,
    # after the pre-flight already accepted the campaign; refusing at
    # resolution names the protocol once, before anything runs.
    with pytest.raises(
        ValueError,
        match=r"does not satisfy the ScriptRecipe protocol: the campaign loop calls "
        r"build\(case, script\) -> None, and this one takes \(workdir\)",
    ):
        resolve_recipe("tests.test_cases:loose_recipe")


# --- the solver's own on/off vocabulary in the settings fields --------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [("DISABLE", False), ("ENABLE", True), ("disable", False), (" Enable ", True)],
)
def test_settings_toggles_read_the_solver_vocabulary(written, expected):
    # A settings preset carried over from the solver writes the flags in
    # the solver's words, and mixes them with plain booleans in the same
    # file; both forms mean the same thing and are stored as bools.
    settings = SolverSettings(viscous_coupling=written, forced_iterations=True)
    assert settings.viscous_coupling is expected
    assert settings.forced_iterations is True


def test_a_settings_toggle_outside_both_vocabularies_is_refused_by_name():
    with pytest.raises(ValidationError, match=r"viscous_coupling"):
        SolverSettings(viscous_coupling="MAYBE")
    with pytest.raises(ValidationError, match=r"True or False, or the solver's own"):
        SolverSettings(viscous_coupling="MAYBE")


@pytest.mark.parametrize("value", ["true", "yes", "on", "1", "off", 1, 0])
def test_settings_toggles_refuse_the_lax_bool_forms(value):
    # Narrower than pydantic's lax coercion on purpose: the settings
    # field accepts exactly what the helper keyword it mirrors accepts,
    # so the same file cannot mean one thing in a preset and another in
    # a call.
    with pytest.raises(ValidationError, match="True or False, or the solver's own"):
        SolverSettings(viscous_coupling=value)
