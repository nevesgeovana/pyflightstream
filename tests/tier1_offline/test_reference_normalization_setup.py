"""Reference normalization choices must reach exactly the requested native route."""

import pytest

from pyflightstream.cases import SolverSettings
from pyflightstream.cases.workflows._solver_settings import _settings
from pyflightstream.script import Script
from tests.tier1_offline.test_boundary_setup_coverage import _case


@pytest.mark.parametrize(
    "settings, expected",
    [
        ({"reference_mach": 0.2}, "SOLVER_SET_REF_MACH_NUMBER 0.2"),
        ({"disable_reference_velocity": True}, "DISABLE_SOLVER_REF_VELOCITY"),
    ],
)
def test_explicit_reference_route_replaces_default_reference_velocity(settings, expected):
    script = Script("26.124")
    _settings(_case(solver=SolverSettings(**settings)), script)
    lines = script.render().splitlines()
    assert expected in lines
    assert not any(line.startswith("SOLVER_SET_REF_VELOCITY ") for line in lines)
    assert "SOLVER_SET_VELOCITY 30.0" in lines


@pytest.mark.parametrize(
    "settings",
    [
        {"reference_mach": 0.2, "reference_velocity_m_per_s": 40},
        {"reference_mach": 0.2, "disable_reference_velocity": True},
        {"reference_velocity_m_per_s": 40, "disable_reference_velocity": True},
    ],
)
def test_competing_reference_normalizations_are_refused(settings):
    with pytest.raises(ValueError, match="one reference normalization"):
        SolverSettings(**settings)


def test_unstated_reference_route_preserves_existing_freestream_normalization():
    script = Script("26.124")
    _settings(_case(solver=SolverSettings()), script)
    assert "SOLVER_SET_REF_VELOCITY 30.0" in script.render()
    assert "DISABLE_SOLVER_REF_VELOCITY" not in script.render()


@pytest.mark.parametrize("value", [0, -0.1, float("inf"), float("nan")])
def test_reference_mach_is_finite_and_positive(value):
    with pytest.raises(ValueError):
        SolverSettings(reference_mach=value)


def _resolved_mach_case(**updates):
    import math

    from pyflightstream.cases import FluidState

    sound = math.sqrt(1.4 * 101325.0 / 1.2)
    fluid = FluidState(
        velocity_m_per_s=0.1 * sound,
        density_kg_m3=1.2,
        pressure_pa=101325,
        temperature_k=101325 / (1.2 * 287.05287),
        viscosity_pa_s=1.8e-5,
        sonic_velocity_m_per_s=sound,
        heat_capacity_ratio=1.4,
        source="synthetic",
    )
    case = _case(
        mach=0.1,
        velocity=0.1 * sound,
        fluid=fluid,
        solver=SolverSettings(freestream_input="mach"),
    )
    return case.model_copy(update=updates)


def test_mach_route_uses_the_same_resolved_condition_without_velocity_setter():
    from pyflightstream.cases.workflows._freestream import _fluid

    case = _resolved_mach_case()
    script = Script("26.124")
    _fluid(case, script)
    _settings(case, script)
    lines = script.render().splitlines()
    assert "SOLVER_SET_MACH_NUMBER 0.1" in lines
    assert not any(line.startswith("SOLVER_SET_VELOCITY ") for line in lines)
    assert any(line.startswith("SOLVER_SET_REF_VELOCITY ") for line in lines)


@pytest.mark.parametrize(
    "change",
    [
        {"mach": None},
        {"fluid": None},
        {"mach": 0.2},
        {"velocity": 5.0},
    ],
)
def test_mach_route_refuses_missing_or_inconsistent_resolved_state(change):
    # GOAL033:setup_bc:checks:no_silent_unsupported
    with pytest.raises(ValueError, match="freestream_input='mach'"):
        _settings(_resolved_mach_case(**change), Script("26.124"))


def test_mach_route_refuses_inconsistent_pinned_sound_speed():
    case = _resolved_mach_case()
    changed = case.fluid.model_copy(update={"sonic_velocity_m_per_s": 500.0})
    case = case.model_copy(update={"fluid": changed, "velocity": 50.0})
    with pytest.raises(ValueError, match="sound speed"):
        _settings(case, Script("26.124"))


def test_mach_route_refuses_a_conflicting_explicit_sonic_override():
    case = _resolved_mach_case()
    case.solver.sonic_velocity_m_per_s = 500.0
    with pytest.raises(ValueError, match="sonic_velocity_m_per_s changes the sound speed"):
        _settings(case, Script("26.124"))


def test_freestream_route_default_and_inspection_value_are_explicit():
    assert SolverSettings().model_dump()["freestream_input"] == "velocity"
    assert _resolved_mach_case().solver.model_dump()["freestream_input"] == "mach"
    with pytest.raises(ValueError):
        SolverSettings(freestream_input="both")


def test_mach_route_refuses_inconsistent_emitted_temperature():
    case = _resolved_mach_case()
    changed = case.fluid.model_copy(update={"temperature_k": 400.0})
    case = case.model_copy(update={"fluid": changed})
    with pytest.raises(ValueError, match="emitted temperature and gamma"):
        _settings(case, Script("26.124"))
