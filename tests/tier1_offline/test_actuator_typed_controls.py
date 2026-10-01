import pytest

from pyflightstream.cases import ActuatorBlock, SolverSettings
from pyflightstream.cases.workflows._actuator import _actuator_disc
from pyflightstream.script import Script
from tests.tier1_offline.test_g06_actuator_disc import PROP, _lines, _with_disc
from tests.tier1_offline.test_workflows import steady_case


@pytest.mark.parametrize("wake", ["RIGID", "RELAXED"])
@pytest.mark.parametrize("units", ["NEWTONS", "POUNDS", "COEFFICIENT"])
def test_actuator_wake_and_thrust_units_are_explicit_typed_inputs(wake, units):
    block = ActuatorBlock(**{**PROP.model_dump(), "wake_type": wake, "thrust_units": units})
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"),
        actuators={"PROP": block},
    )
    lines, _ = _lines(case)
    assert f"SET_ACTUATOR_WAKE_TYPE 1 {wake}" in lines
    assert f"SET_PROP_ACTUATOR_THRUST 1 120.0 {units}" in lines
    assert lines.index(f"SET_ACTUATOR_WAKE_TYPE 1 {wake}") < lines.index("INITIALIZE_SOLVER")


def test_actuator_actions_follow_creation_and_track_renamed_identity(tmp_path):
    from pyflightstream.workspace.inputs import resolve_setup
    from pyflightstream.workspace.matrix import _solver_from_setup

    inputs = tmp_path / "inputs"
    (inputs / "setups").mkdir(parents=True)
    (inputs / "setups" / "s901.toml").write_text(
        '[[actuator_operations]]\nop = "rename"\nactuator = "PROP"\nname = "Renamed"\n'
        '[[actuator_operations]]\nop = "enable"\nactuator = "Renamed"\n'
        '[[actuator_operations]]\nop = "delete"\nactuator = "Renamed"\n',
        encoding="utf-8",
    )
    solver = _solver_from_setup(resolve_setup(inputs, "s901"), "s901")
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"),
        solver=solver,
    )
    lines, script = _lines(case)
    assert lines.index("SET_ACTUATOR_NAME 1 Renamed") < lines.index("DELETE_ACTUATOR 1")
    assert lines.count("ENABLE_ACTUATOR 1") == 2
    assert script.num_actuators == 0


def test_unknown_actuator_action_names_are_refused_before_mutation():
    solver = SolverSettings(actuator_operations=[{"op": "delete", "actuator": "Missing"}])
    case = _with_disc(steady_case(), solver=solver)
    script = Script("26.124")
    with pytest.raises(ValueError, match="Missing.*actuator|actuator.*Missing"):
        _actuator_disc(case, script, {}, None)
    assert "DELETE_ACTUATOR" not in script.render()


def test_legacy_disable_is_refused_on_current_build_without_emitting_action():
    solver = SolverSettings(actuator_operations=[{"op": "disable", "actuator": "PROP"}])
    case = _with_disc(
        steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"),
        solver=solver,
    )
    with pytest.raises(Exception, match="DISABLE_ACTUATOR"):
        _lines(case)


@pytest.mark.parametrize(
    "change",
    [
        {"wake_type": "AUTO"},
        {"thrust_units": "KILO-NEWTONS"},
    ],
)
def test_actuator_contract_rejects_unavailable_native_enumerations(change):
    with pytest.raises(ValueError):
        ActuatorBlock(**{**PROP.model_dump(), **change})


def test_actuator_action_refuses_foreign_arguments():
    with pytest.raises(ValueError, match="rename|name"):
        SolverSettings(actuator_operations=[{"op": "delete", "actuator": "PROP", "name": "x"}])


def test_saved_actuator_operations_use_measured_name_inventory(tmp_path):
    from tests.tier1_offline.test_g06_actuator_disc import PHYSICS_WITH_A_DISC, _saved_copy

    saved = _saved_copy(tmp_path / "saved.fsm", "PHYSICS", PHYSICS_WITH_A_DISC)
    case = _with_disc(
        steady_case(),
        geometry=str(saved),
        solver=SolverSettings(
            actuator_operations=[{"op": "rename", "actuator": "PROP", "name": "SavedRenamed"}]
        ),
    )
    script = Script("26.124")
    _actuator_disc(case, script, {}, None)
    assert "SET_ACTUATOR_NAME 1 SavedRenamed" in script.render()
    assert script.num_actuators == 1


def test_saved_actuator_missing_physics_is_not_an_empty_inventory(tmp_path):
    saved = tmp_path / "placeholder.fsm"
    saved.write_text("placeholder", encoding="utf-8")
    case = _with_disc(
        steady_case(),
        geometry=str(saved),
        solver=SolverSettings(actuator_operations=[{"op": "delete", "actuator": "PROP"}]),
    )
    script = Script("26.124")
    with pytest.raises(ValueError, match="readable saved physics inventory"):
        _actuator_disc(case, script, {}, None)
    assert "DELETE_ACTUATOR" not in script.render()
