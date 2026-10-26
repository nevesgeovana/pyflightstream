import pytest

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._solver_settings import _settings
from pyflightstream.script import Script


def _case(**kwargs):
    return SimCase(
        sim_id="9011",
        aircraft="Duct",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["point.txt"],
        **kwargs,
    )


@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0440_relaxed_trailing_edge_override(build):
    """PFS-2149: RELAXED uses the build-validated trailing-edge setter."""
    try:
        setup = SolverSettings(trailing_edge_types={1: "RELAXED"})
    except ValueError as error:
        pytest.fail(f"the documented RELAXED override was refused: {error}")
    script = Script(build)
    _settings(_case(solver=setup), script)
    assert "SET_TRAILING_EDGE_TYPE 1 RELAXED" in script.render()


def test_p0440_bare_termination_key_refers_to_explicit_file():
    from pyflightstream.cases import CampaignConfigError

    with pytest.raises(CampaignConfigError, match=r"\[wake_termination\] file"):
        _settings(_case(solver=SolverSettings(mark_wake_termination_nodes=True)), Script("26.124"))


def _port_script():
    script = Script("26.124")
    script.declare_existing(boundaries={"Inlet": 1, "Outlet": 2, "Wall": 3})
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    return script


def test_outlet_profile_is_refused_because_no_official_command_exists():
    with pytest.raises(ValueError, match="outlet profile has no documented native command"):
        SolverSettings(ports=[{"port": "exit", "kind": "outlet", "profile_variable": "P"}])


def test_proximity_and_remove_initialization_are_emitted_before_initialize():
    settings = SolverSettings(
        proximal_boundaries=["Wing"], remove_initialization=True, delete_transition_trips=[3, 1]
    )
    case = _case(solver=settings)
    script = Script("26.124")
    script.declare_existing(boundaries={"Wing": 2})
    _settings(case, script)
    text = script.render()
    assert "DELETE_TRANSITION_TRIP 3" in text
    assert text.index("DELETE_TRANSITION_TRIP 3") < text.index("DELETE_TRANSITION_TRIP 1")
    assert "REMOVE_INITIALIZATION" in text
    assert "SOLVER_PROXIMAL_BOUNDARIES 1\n2" in text
    assert "INITIALIZE_SOLVER" not in text


def test_clear_vorticity_drag_is_explicit_and_reaches_after_solve(meter_geometry):
    case = _case(
        geometry=str(meter_geometry),
        inventory=["Wing"],
        solver=SolverSettings(clear_vorticity_drag_boundaries=True),
    )
    script = Script("26.124")
    build_script(case, script)
    text = script.render()
    assert text.index("START_SOLVER") < text.index("DELETE_VORTICITY_DRAG_BOUNDARIES")
    assert text.index("DELETE_VORTICITY_DRAG_BOUNDARIES") < text.index(
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    )


def test_clear_vorticity_drag_cannot_compete_with_an_explicit_selection():
    with pytest.raises(ValueError, match="cannot be combined with vorticity_drag_families"):
        SolverSettings(clear_vorticity_drag_boundaries=True, vorticity_drag_families=["Wing"])


def test_all_proximity_boundaries_expand_the_declared_inventory():
    script = Script("26.124")
    script.declare_existing(boundaries={"Wing": 1, "Tail": 2})
    _settings(_case(solver=SolverSettings(proximal_boundaries="all")), script)
    lines = script.render().splitlines()
    at = lines.index("SOLVER_PROXIMAL_BOUNDARIES 2")
    assert [int(value) for value in " ".join(lines[at + 1 :]).split()] == [1, 2]


def test_explicit_port_deletions_preserve_declared_indices_and_order():
    settings = SolverSettings(delete_inlets=[2, 1], delete_outlets=[1])
    script = Script("26.124")
    _settings(_case(solver=settings), script)
    lines = script.render().splitlines()
    deletes = [line for line in lines if line.startswith(("DELETE_INLET", "DELETE_OUTLET"))]
    assert deletes == ["DELETE_INLET 2", "DELETE_INLET 1", "DELETE_OUTLET 1"]
    assert lines.index(deletes[-1]) < lines.index("SOLVER_SET_AOA 0.0")


def test_remesh_port_command_can_follow_the_command_that_creates_its_port():
    script = Script("26.124")
    script.declare_existing(boundaries={"Port": 1})
    script.emit("CREATE_NEW_INLET", 1, 10.0)
    script.emit(
        "REMESH_INLET", inlet=1, inner_radius=0.0, elements=4, growth_scheme="1", growth_rate=1.2
    )


def test_port_remesh_stays_forbidden_after_initialization_settings():
    from pyflightstream.script import ScriptOrderError

    script = Script("26.124")
    script.emit("SOLVER_SET_AOA", 0.0)
    with pytest.raises(ScriptOrderError):
        script.emit(
            "REMESH_INLET",
            inlet=1,
            inner_radius=0.0,
            elements=4,
            growth_scheme="1",
            growth_rate=1.2,
        )
