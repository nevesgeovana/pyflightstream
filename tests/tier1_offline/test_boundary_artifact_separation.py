import pytest

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import _raw_mesh_boundary_conditions, _settings
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import InputArtifactError, read_raw_mesh_conditions


def _bind_setup_ports(case, inputs_dir):
    from pyflightstream.workspace.matrix import _bind_setup_ports as bind

    return bind(case, inputs_dir)


def _case(tmp_path, settings, variables=None):
    sidecar = tmp_path / "duct.boundaries.toml"
    sidecar.write_text('[ports]\nfeed="Inlet"\nexit="Outlet"\n[trailing_edges]\nnone=true\n')
    return SimCase(
        sim_id="9011",
        aircraft="Duct",
        recipe="steady",
        geometry=str(tmp_path / "duct.obj"),
        inventory=["Inlet", "Outlet"],
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"VELOCITY": "30", **(variables or {})},
        outputs=["point.txt"],
        solver=SolverSettings.model_validate(settings),
        raw_mesh_conditions=read_raw_mesh_conditions(sidecar),
    )


def _script():
    script = Script("26.124")
    script.declare_existing(boundaries={"Inlet": 1, "Outlet": 2})
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    return script


def test_geometry_identity_is_bound_to_setup_and_matrix_condition(tmp_path):
    case = _case(
        tmp_path,
        {
            "ports": [
                {"port": "feed", "kind": "inlet", "velocity_variable": "PORT_SPEED"},
                {"port": "exit", "kind": "outlet", "velocity_variable": "EXIT_SPEED"},
            ]
        },
        {"PORT_SPEED": "-12.5", "EXIT_SPEED": "12.5"},
    )
    case = _bind_setup_ports(case, tmp_path)
    script = _script()
    _settings(case, script)
    text = script.render()
    assert "CREATE_NEW_INLET 1 -12.5" in text
    assert "CREATE_NEW_OUTLET 2 12.5" in text
    assert text.index("CREATE_NEW_OUTLET") < text.index("SOLVER_SET_AOA")
    assert case.raw_mesh_conditions.ports == {"feed": "Inlet", "exit": "Outlet"}


def test_profile_variable_binds_and_stages_original_bytes(tmp_path):
    folder = tmp_path / "profiles"
    folder.mkdir()
    profile = folder / "feed.txt"
    payload = b"0,0,0,10\r\n0,1,0,20"
    profile.write_bytes(payload)
    case = _case(
        tmp_path,
        {
            "ports": [
                {
                    "port": "feed",
                    "kind": "inlet",
                    "velocity_variable": "PORT_SPEED",
                    "profile_variable": "PORT_PROFILE",
                }
            ]
        },
        {"PORT_SPEED": "15", "PORT_PROFILE": "feed.txt"},
    )
    bound = _bind_setup_ports(case, tmp_path)
    script = _script()
    _settings(bound, script)
    assert list(script.pending_input_files.values()) == [payload]
    assert bound.solver.ports[0].profile_sha256
    profile.write_bytes(b"changed")
    with pytest.raises(ValueError, match="profile.*changed"):
        _settings(bound, _script())


@pytest.mark.parametrize(
    "variable,value,match",
    [
        ("PORT_SPEED", None, "PORT_SPEED"),
        ("PORT_SPEED", "nan", "finite"),
        ("PORT_SPEED", "true", "number"),
        ("PORT_PROFILE", "missing.txt", "profile"),
    ],
)
def test_missing_or_invalid_matrix_condition_is_named(tmp_path, variable, value, match):
    variables = {"PORT_SPEED": "15", "PORT_PROFILE": "missing.txt"}
    if value is None:
        variables.pop(variable)
    else:
        variables[variable] = value
    ports = {"port": "feed", "kind": "inlet", "velocity_variable": "PORT_SPEED"}
    if variable == "PORT_PROFILE":
        ports["profile_variable"] = "PORT_PROFILE"
    case = _case(tmp_path, {"ports": [ports]}, variables)
    with pytest.raises(InputArtifactError, match=match):
        _bind_setup_ports(case, tmp_path)


@pytest.mark.parametrize("table", ["inlets", "outlets"])
def test_unreleased_sidecar_port_conditions_have_a_corrective_error(tmp_path, table):
    path = tmp_path / "duct.boundaries.toml"
    path.write_text(f'[[{table}]]\nboundary="Inlet"\nvelocity=10\n')
    with pytest.raises(InputArtifactError, match="setup.*MATRIX"):
        read_raw_mesh_conditions(path)


def test_unknown_port_and_duplicate_surface_are_refused(tmp_path):
    case = _case(
        tmp_path,
        {"ports": [{"port": "missing", "kind": "inlet", "velocity_variable": "SPEED"}]},
        {"SPEED": "10"},
    )
    with pytest.raises(InputArtifactError, match="missing"):
        _bind_setup_ports(case, tmp_path)
    case = _case(
        tmp_path,
        {
            "ports": [
                {"port": "feed", "kind": "inlet", "velocity_variable": "SPEED"},
                {"port": "feed", "kind": "outlet", "velocity_variable": "SPEED"},
            ]
        },
        {"SPEED": "10"},
    )
    with pytest.raises(InputArtifactError, match="more than once"):
        _bind_setup_ports(case, tmp_path)


def test_outlet_profile_is_refused_by_the_setup_model():
    with pytest.raises(ValueError, match="outlet profile"):
        SolverSettings(
            ports=[
                {
                    "port": "exit",
                    "kind": "outlet",
                    "velocity_variable": "SPEED",
                    "profile_variable": "PROFILE",
                }
            ]
        )


def test_false_application_choices_emit_no_detection_or_clear(tmp_path):
    case = _case(
        tmp_path,
        {
            "apply_trailing_edges": False,
            "apply_wake_termination": False,
            "apply_base_regions": False,
        },
    )
    case = case.model_copy(
        update={
            "raw_mesh_conditions": case.raw_mesh_conditions.model_copy(
                update={"trailing_edges": None, "wake_termination": "auto", "base_regions": "auto"}
            )
        }
    )
    script = _script()
    before = script.render()
    _raw_mesh_boundary_conditions(case, script)
    assert script.render() == before


def test_saved_fsm_port_indices_are_not_assumed_empty(tmp_path):
    case = _bind_setup_ports(
        _case(
            tmp_path,
            {"ports": [{"port": "feed", "kind": "inlet", "velocity_variable": "SPEED"}]},
            {"SPEED": "10"},
        ),
        tmp_path,
    )
    case = case.model_copy(update={"geometry": str(tmp_path / "saved.fsm")})
    with pytest.raises(ValueError, match="saved.*port.*indices"):
        _settings(case, _script())


def test_geometry_port_map_survives_reading_without_conditions(tmp_path):
    path = tmp_path / "duct.boundaries.toml"
    path.write_text('[ports]\nfeed="Inlet"\n')
    conditions = read_raw_mesh_conditions(path)
    assert conditions is not None, "the geometric port map must not be dropped"
    assert conditions.ports == {"feed": "Inlet"}


def test_complete_matrix_binding_keeps_one_setup_and_distinct_port_conditions(tmp_path):
    from pyflightstream.cases.matrix import _COLUMNS
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.matrix import resolve_matrix

    workspace = CampaignWorkspace.init(tmp_path / "campaign")
    inputs = workspace.inputs_dir
    (inputs / "references" / "r001.toml").write_text("area_m2=1\nchord_m=1\nspan_m=1\n")
    (inputs / "setups" / "s001.toml").write_text(
        "apply_trailing_edges=true\napply_wake_termination=false\napply_base_regions=false\n"
        '[[ports]]\nport="feed"\nkind="inlet"\n'
        '[[ports]]\nport="exit"\nkind="outlet"\n'
    )
    (inputs / "pproc" / "p001.toml").write_text('[groups]\nBody="all"\n')
    geometry = inputs / "geometries" / "duct.obj"
    geometry.write_text("v 0 0 0\nv 0 1 0\nv 0 0 1\no Inlet\nf 1 2 3\no Outlet\nf 3 2 1\n")
    geometry.with_suffix(".boundaries.toml").write_text(
        'boundaries=["Inlet", "Outlet"]\n[import]\nunits="METER"\n'
        '[trailing_edges]\nnone=true\n[ports]\nfeed="Inlet"\nexit="Outlet"\n'
    )
    rows = []
    for pol, speed in (("9011", 12.5), ("9012", 25.0)):
        row = dict.fromkeys(_COLUMNS, "-")
        row.update(
            POL=pol,
            HIDDEN="0",
            RUN="1",
            AIRCRAFT="Duct",
            GEOMETRY="duct.obj",
            REF="r001",
            SET="s001",
            PPROC="p001",
            WORKFLOW="steady",
            SWEEP_VALUES="0",
            FLIGHT_CONDITION="TASmps:30, ALTFT:0, ALPHA:sweep, BETA:0",
            VAR_NAMES_VALUES=f"FEED_VELOCITY:{-speed} / EXIT_VELOCITY:{speed}",
        )
        rows.append(" | ".join(row[key] for key in _COLUMNS))
    matrix = workspace.root / "ports.fs"
    matrix.write_text(" | ".join(_COLUMNS) + "\n" + "\n".join(rows) + "\n")
    resolved = resolve_matrix(
        matrix,
        workspace,
        name="ports",
        fs_version="26.124",
        recipes={},
        fs_exe="C:/unused/FlightStream.exe",
    )
    assert len(resolved.campaign.sims) == 2
    for case, speed in zip(resolved.campaign.sims, (12.5, 25.0), strict=True):
        script = Script("26.124")
        with pytest.warns(UserWarning, match="no wake"):
            build_script(case, script)
        assert f"CREATE_NEW_INLET 1 {-speed}" in script.render()
        assert f"CREATE_NEW_OUTLET 2 {speed}" in script.render()
        assert case.solver.ports[0].velocity_variable == "FEED_VELOCITY"


def test_setup_rejects_inline_condition_or_surface_values():
    from pyflightstream.workspace.inputs import SetupArtifact
    from pyflightstream.workspace.matrix import _solver_from_setup

    for field, value in (("velocity", 10), ("boundary", "Inlet"), ("profile", "p.txt")):
        with pytest.raises(InputArtifactError, match="MATRIX"):
            _solver_from_setup(
                SetupArtifact(
                    settings={"ports": [{"port": "feed", "kind": "inlet", field: value}]}
                ),
                "s001",
            )


def test_each_application_choice_is_independent_and_false_never_clears(tmp_path):
    case = _case(
        tmp_path,
        {"apply_trailing_edges": False, "apply_wake_termination": True, "apply_base_regions": True},
    )
    case = case.model_copy(
        update={
            "raw_mesh_conditions": case.raw_mesh_conditions.model_copy(
                update={"wake_termination": "auto", "base_regions": "auto"}
            )
        }
    )
    script = _script()
    _raw_mesh_boundary_conditions(case, script)
    text = script.render()
    assert "AUTO_DETECT_WAKE_TERMINATION_NODES" in text
    assert "AUTO_DETECT_BASE_REGIONS" in text
    assert "AUTO_DETECT_TRAILING_EDGES" not in text
    assert "DELETE_" not in text


def test_saved_fsm_with_disabled_definitions_is_opened_without_redefinition(tmp_path):
    from pyflightstream.cases.workflows import _open_geometry

    case = _case(
        tmp_path,
        {
            "apply_trailing_edges": False,
            "apply_wake_termination": False,
            "apply_base_regions": False,
        },
    )
    geometry = tmp_path / "saved.fsm"
    geometry.write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n")
    case = case.model_copy(update={"geometry": str(geometry)})
    script = Script("26.124")
    _open_geometry(case, script)
    text = script.render()
    assert "OPEN" in text
    assert "DETECT_" not in text
    assert "DELETE_" not in text


def test_disabled_trailing_edge_definition_does_not_read_an_unused_points_file(tmp_path):
    from pyflightstream.cases import MeshImport
    from pyflightstream.workspace.matrix import _raw_mesh_conditions_of

    geometry = tmp_path / "duct.obj"
    geometry.write_text("unused")
    geometry.with_suffix(".boundaries.toml").write_text('[trailing_edges]\nfile="missing.te.txt"\n')
    conditions = _raw_mesh_conditions_of(
        geometry,
        "9011",
        MeshImport(units="METER"),
        SolverSettings(apply_trailing_edges=False),
    )
    assert conditions.trailing_edges.points_m == ()
