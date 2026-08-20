"""Tier 1: SIM model, campaign.toml loading, sweeps, and recipes."""

import pytest
from pydantic import ValidationError

from pyflightstream.cases import (
    ROTATION_OFFSET_KEY,
    ROTATION_SWEEP_KEY,
    Campaign,
    CampaignConfigError,
    ReferenceData,
    SimCase,
    SolverSettings,
    SweepAxis,
    geometric_sweep_values,
    load_campaign,
    multiplied_sweep,
    point_tag,
    resolve_recipe,
)

CAMPAIGN_TOML = """
[campaign]
name = "wing_steady_sweep"
fs_version = "26.120"
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
    assert campaign.fs_version == "26.120"
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


# PYFS-003, the REV-002 blocker reproduced at ecc212e.


def test_a_sweep_whose_points_share_a_tag_is_refused():
    """The review's published probe.

    Measured before the fix: point_tag({'alpha': 1.01}) and
    point_tag({'alpha': 1.04}) both returned 'a+01.0', the pre-flight
    reported [('c/sim_1/a+01.0', 'READY'), ('c/sim_1/a+01.0', 'READY')],
    and nothing refused anything. The tag ENDS the run_id, so the two
    points shared one manifest identity.

    Why refusing beats widening the tag: the tag is identity and already
    appears in every existing manifest, and any fixed precision collides at
    some spacing. Widening moves the collision, refusing removes it.
    """
    with pytest.raises(ValidationError, match="both tag as"):
        SweepAxis(type="alpha", values=[1.01, 1.04])


def test_the_collision_is_refused_for_paired_and_propeller_sweeps_too():
    """The same arithmetic applies to every axis, so the guard must too."""
    with pytest.raises(ValidationError, match="both tag as"):
        SweepAxis(type="alpha_beta", values=[(1.01, 0.0), (1.04, 0.0)])
    with pytest.raises(ValidationError, match="both tag as"):
        SweepAxis(type="advance_ratio", values=[0.81, 0.84])


def test_points_a_tenth_apart_are_still_accepted():
    """The control: the guard must refuse only what actually collides."""
    sweep = SweepAxis(type="alpha", values=[1.0, 1.1, 1.2])
    assert [point_tag(point) for point in sweep.points()] == [
        "a+01.0",
        "a+01.1",
        "a+01.2",
    ]


def test_two_cases_sharing_a_sim_id_are_refused():
    """The second half of the same finding.

    Measured before the fix: Campaign accepted two SimCases with
    sim_id="1" without complaint, so both staged into one inputs/, wrote
    into one scripts/, and collected into one raw/.
    """

    def case(sim_id):
        return SimCase(
            sim_id=sim_id,
            aircraft="TestWing",
            velocity=30.0,
            sweep=SweepAxis(type="alpha", values=[0.0]),
            recipe="pkg.mod:build",
            outputs=["loads_{point}.txt"],
        )

    with pytest.raises(ValidationError, match="more than one case with sim_id"):
        Campaign(
            name="camp",
            fs_version="26.120",
            fs_exe="x",
            sims=[case("1"), case("1")],
        )
    # the control: distinct ids are fine
    assert (
        len(
            Campaign(name="camp", fs_version="26.120", fs_exe="x", sims=[case("1"), case("2")]).sims
        )
        == 2
    )


# --- PYFS-016: the case models refuse impossible physics --------------------


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("iterations zero", {"iterations": 0}),
        ("iterations negative", {"iterations": -5}),
        ("timeout zero", {"timeout_s": 0.0}),
        ("timeout negative", {"timeout_s": -1.0}),
        ("convergence zero", {"convergence": 0.0}),
        ("convergence negative", {"convergence": -1e-5}),
        ("convergence NaN", {"convergence": float("nan")}),
        ("convergence infinite", {"convergence": float("inf")}),
        ("threads zero", {"max_threads": 0}),
        ("threads negative", {"max_threads": -2}),
    ],
)
def test_solver_settings_refuses_a_run_that_cannot_happen(label, kwargs):
    """PYFS-016. Every one of these was measured ACCEPTED at HEAD.

    The NaN convergence threshold is the one worth naming: it compares
    false against every residual, so the solver runs its whole
    iteration budget and the run is then recorded as having met a
    target it never met. That is a silent wrong number, not a crash.
    """
    with pytest.raises(ValidationError):
        SolverSettings(**kwargs)


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("area zero", {"area": 0.0, "length": 1.0}),
        ("area negative", {"area": -1.0, "length": 1.0}),
        ("area infinite", {"area": float("inf"), "length": 1.0}),
        ("area NaN", {"area": float("nan"), "length": 1.0}),
        ("length zero", {"area": 1.0, "length": 0.0}),
        ("length negative", {"area": 1.0, "length": -1.0}),
        ("velocity zero", {"area": 1.0, "length": 1.0, "velocity": 0.0}),
        ("velocity negative", {"area": 1.0, "length": 1.0, "velocity": -3.0}),
    ],
)
def test_reference_data_refuses_a_divisor_that_breaks_every_coefficient(label, kwargs):
    """PYFS-016. These are the DIVISORS of every published coefficient.

    Zero divides by zero, negative flips the sign of every coefficient
    while the run looks healthy, and infinite drives them all to zero.
    All four shapes were measured accepted at HEAD.
    """
    with pytest.raises(ValidationError):
        ReferenceData(**kwargs)


def test_the_bounds_still_admit_an_ordinary_case():
    # The control. Without it, a model that refused everything would
    # pass both tests above.
    settings = SolverSettings(iterations=500, convergence=1e-5, max_threads=4, timeout_s=1800.0)
    assert settings.iterations == 500
    reference = ReferenceData(area=1.5, length=0.4, velocity=30.0)
    assert reference.area == 1.5
    # velocity stays optional, which the sweep relies on.
    assert ReferenceData(area=1.5, length=0.4).velocity is None


# --- one sweep per case (PFS-2025.17, PFS-2025.17.02) -----------------------
#
# The DECISION: a geometric sweep does not multiply with the aerodynamic
# one. The limit is enforced at BOTH declaration moments, and this block
# covers the native one: constructing a SimCase, and loading the
# campaign.toml that holds it. The run matrix half lives in
# tests/test_matrix.py, and the two are held to one owner there.


def _case(**overrides):
    """A minimal SimCase, so each test below varies exactly one thing."""
    fields = {
        "sim_id": "9001",
        "aircraft": "TestWing",
        "sweep": SweepAxis(type="alpha", values=[0.0, 2.0, 4.0]),
        "recipe": "recipes.steady:build",
    }
    fields.update(overrides)
    return SimCase(**fields)


def test_a_geometric_sweep_beside_an_aerodynamic_one_is_refused_at_declaration():
    """The hole PFS-2025.17.02 closes: the matrix refused this, the model did not.

    A campaign.toml is a declaration door of its own. Before this
    validator a hand-written [[sim]] carrying angle_sweep_deg beside a
    multi-point sweep loaded clean, so the limit the matrix reader states
    could be walked past by writing the campaign directly, and the user
    met the consequence at run time instead.
    """
    with pytest.raises(ValidationError) as caught:
        _case(variables={ROTATION_SWEEP_KEY: "0.0,5.0,10.0"})
    message = str(caught.value)
    assert "9001" in message, "the refusal does not name the case"
    assert "alpha" in message
    assert "0.0,5.0,10.0" in message, "the refusal does not quote what was declared"
    assert "9 runs" in message, "the refusal does not say how large the grid would be"
    assert ROTATION_OFFSET_KEY in message, "the refusal names no remedy, so it only says no"
    assert "sim_id" in message, "the refusal does not name the one-case-per-geometry form"


def test_the_refusal_reaches_a_campaign_file_as_it_loads(tmp_path):
    """Loading is the declaration moment for a user who writes no Python."""
    path = tmp_path / "campaign.toml"
    path.write_text(
        CAMPAIGN_TOML + f'{ROTATION_SWEEP_KEY} = "0.0,5.0"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="asks for two sweeps at once"):
        load_campaign(path)


def test_a_fixed_offset_beside_a_sweep_is_the_accepted_form():
    """The remedy the refusal names has to actually work."""
    case = _case(variables={ROTATION_OFFSET_KEY: 5.0})
    assert case.variables[ROTATION_OFFSET_KEY] == 5.0


def test_one_angle_in_the_sweep_variable_is_still_one_sweep():
    case = _case(variables={ROTATION_SWEEP_KEY: "7.5"})
    assert case.variables[ROTATION_SWEEP_KEY] == "7.5"


def test_a_geometry_sweep_on_a_single_point_case_is_the_other_accepted_form():
    """A sweep OF the geometry: one aerodynamic point, several angles.

    This is the shape the refusal steers a user towards, one case per
    geometry, so it must not itself be refused.
    """
    case = _case(
        sweep=SweepAxis(type="alpha", values=[2.0]),
        variables={ROTATION_SWEEP_KEY: "0.0,5.0,10.0"},
    )
    assert case.sweep.values == [2.0]


def test_the_limit_does_not_depend_on_how_the_key_is_spelled():
    """A limit that fires only for one casing is one a user gets past by shouting."""
    with pytest.raises(ValidationError, match="asks for two sweeps at once"):
        _case(variables={ROTATION_SWEEP_KEY.upper(): "0.0,5.0"})


def test_a_second_casing_of_the_key_cannot_hide_behind_the_first():
    """The adversarial pass found this: two casings are two mapping entries.

    A first-match rule let a one-angle `angle_sweep_deg` stand in front of
    a three-angle `ANGLE_SWEEP_DEG`, and the whole declaration went past
    the limit reading as a single fixed rotation. Every matching key is
    pooled instead.
    """
    with pytest.raises(ValidationError, match="asks for two sweeps at once"):
        _case(
            variables={
                ROTATION_SWEEP_KEY: "5.0",
                ROTATION_SWEEP_KEY.upper(): "0.0,5.0,10.0",
            }
        )
    # And two keys each naming one angle is the same ambiguity, so it meets
    # the same refusal rather than a coin toss between them.
    with pytest.raises(ValidationError, match="asks for two sweeps at once"):
        _case(
            variables={
                ROTATION_SWEEP_KEY: "5.0",
                ROTATION_SWEEP_KEY.title(): "7.5",
            }
        )


def test_no_tag_axis_is_geometric():
    """The premise the whole decision rests on, asserted rather than assumed.

    If a geometric axis ever joins point_tag, multiplication becomes
    representable and this decision is worth reopening. Until then a
    crossed grid is N runs wearing one name, and that is why the limit is
    a refusal rather than a warning.
    """
    assert point_tag({"alpha": 2.0, "beta": 0.0}) == "a+02.0_b+00.0"
    with pytest.raises(CampaignConfigError, match="no known axis"):
        point_tag({ROTATION_OFFSET_KEY: 5.0})


def test_multiplied_sweep_reports_only_the_multiplying_shape():
    """The owner itself, at its four corners."""
    swept = SweepAxis(type="alpha", values=[0.0, 2.0])
    single = SweepAxis(type="alpha", values=[0.0])
    assert multiplied_sweep(swept, {ROTATION_SWEEP_KEY: "0.0,5.0"}) == ["0.0", "5.0"]
    assert multiplied_sweep(swept, {ROTATION_SWEEP_KEY: "5.0"}) == []
    assert multiplied_sweep(single, {ROTATION_SWEEP_KEY: "0.0,5.0"}) == []
    assert multiplied_sweep(swept, {ROTATION_OFFSET_KEY: "5.0"}) == []


def test_geometric_sweep_values_reads_what_a_case_variable_can_hold():
    """A case variable is one scalar or one string, never a list."""
    assert geometric_sweep_values({ROTATION_SWEEP_KEY: "0.0, 5.0 ,10.0"}) == [
        "0.0",
        "5.0",
        "10.0",
    ]
    assert geometric_sweep_values({ROTATION_SWEEP_KEY: 7.5}) == ["7.5"]
    assert geometric_sweep_values({ROTATION_SWEEP_KEY: " , "}) == []
    assert geometric_sweep_values({"CONFIG": "NSX"}) == []
    assert geometric_sweep_values(
        {ROTATION_SWEEP_KEY: "5.0", ROTATION_SWEEP_KEY.upper(): "7.5"}
    ) == ["5.0", "7.5"], "a second casing of the key is dropped instead of pooled"
