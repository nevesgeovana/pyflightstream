from hashlib import sha256

import pytest

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._geometry import _setup_ports
from pyflightstream.cases.workflows._solver_settings import _settings
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import read_raw_mesh_conditions
from pyflightstream.workspace.matrix import _bind_setup_ports


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


def _port_case(tmp_path, *, inlet=True, outlet=False, profile=True, remesh=False):
    sidecar = tmp_path / "duct.boundaries.toml"
    sidecar.write_text('[ports]\nfeed="Inlet"\nexit="Outlet"\n')
    folder = tmp_path / "profiles"
    folder.mkdir(exist_ok=True)
    path = folder / "inlet-profile.txt"
    path.write_bytes(b"0,1\r\n1,2\r\n")
    entries = []
    if inlet:
        entries.append({"port": "feed", "kind": "inlet", "velocity_variable": "INLET_SPEED"})
        if profile:
            entries[-1]["profile_variable"] = "INLET_PROFILE"
    if outlet:
        entries.append({"port": "exit", "kind": "outlet", "velocity_variable": "OUTLET_SPEED"})
    if remesh:
        entries[-1]["remesh"] = {
            "inner_radius_m": 0,
            "radial_faces": 4,
            "growth_scheme": "successive",
            "growth_rate": 1.2,
        }
    case = _case(
        geometry=str(tmp_path / "duct.obj"),
        inventory=["Inlet", "Outlet", "Wall"],
        raw_mesh_conditions=read_raw_mesh_conditions(sidecar),
        solver=SolverSettings(ports=entries),
    )
    case = case.model_copy(
        update={
            "variables": {
                "VELOCITY": "30",
                "INLET_SPEED": "-10",
                "OUTLET_SPEED": "10",
                "INLET_PROFILE": "inlet-profile.txt",
            }
        }
    )
    return _bind_setup_ports(case, tmp_path), path


def _port_script():
    script = Script("26.124")
    script.declare_existing(boundaries={"Inlet": 1, "Outlet": 2, "Wall": 3})
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    return script


def test_inlet_profile_is_bound_and_staged_without_reinterpreting_file_format(tmp_path):
    case, profile = _port_case(tmp_path)
    script = _port_script()
    _setup_ports(case, script)
    text = script.render()
    assert "CREATE_NEW_INLET 1 -10.0" in text
    assert "SET_INLET_CUSTOM_PROFILE 1" in text
    assert text.index("CREATE_NEW_INLET") < text.index("SET_INLET_CUSTOM_PROFILE")
    assert list(script.pending_input_files.values()) == [profile.read_bytes()]
    assert case.solver.ports[0].profile_sha256


def test_outlet_profile_is_refused_because_no_official_command_exists():
    with pytest.raises(ValueError, match="outlet profile has no documented native command"):
        SolverSettings(ports=[{"port": "exit", "kind": "outlet", "profile_variable": "P"}])


def test_profile_changed_after_binding_is_refused(tmp_path):
    case, profile = _port_case(tmp_path)
    profile.write_bytes(b"changed")
    with pytest.raises(ValueError, match="profile.*changed"):
        _setup_ports(case, _port_script())


def test_inlet_profile_pending_writer_preserves_and_hashes_exact_bytes(tmp_path):
    from pyflightstream.run import _write_pending_files

    case, profile = _port_case(tmp_path)
    script = _port_script()
    _setup_ports(case, script)
    work = tmp_path / "point"
    work.mkdir()
    hashes = _write_pending_files(script, work, case=case, recorded={})
    (name,) = script.pending_input_files
    assert (work / name).read_bytes() == profile.read_bytes()
    assert hashes[name] == sha256(profile.read_bytes()).hexdigest()


def test_a_boundary_cannot_be_assigned_twice_and_silently_renumber_ports(tmp_path):
    case, _ = _port_case(tmp_path)
    case = case.model_copy(
        update={"solver": case.solver.model_copy(update={"ports": case.solver.ports * 2})}
    )
    with pytest.raises(ValueError, match="assigned more than once"):
        _setup_ports(case, _port_script())


def test_port_remesh_follows_creation_and_precedes_custom_profile(tmp_path):
    case, _ = _port_case(tmp_path, remesh=True)
    script = _port_script()
    _setup_ports(case, script)
    text = script.render()
    assert text.index("CREATE_NEW_INLET") < text.index("REMESH_INLET")
    assert text.index("REMESH_INLET") < text.index("SET_INLET_CUSTOM_PROFILE")
    assert "INLET 1" in text and "ELEMENTS 4" in text


@pytest.mark.parametrize("with_inlet, expected_index", [(True, 2), (False, 1)])
def test_outlet_remesh_uses_combined_created_port_sequence(tmp_path, with_inlet, expected_index):
    case, _ = _port_case(tmp_path, inlet=with_inlet, outlet=True, profile=False, remesh=True)
    script = _port_script()
    _setup_ports(case, script)
    lines = script.render().splitlines()
    at = lines.index("REMESH_OUTLET")
    assert lines[at + 1] == f"OUTLET {expected_index}"
    assert "CREATE_NEW_OUTLET 2 10.0" in lines


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
