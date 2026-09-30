"""Workspace setup controls reach the curated emitter without losing evidence."""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-150, FR-151.

import tomllib

import pytest
from pydantic import ValidationError

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import _settings
from pyflightstream.run.cli import _build_parser
from pyflightstream.script import Script


def test_plan_accepts_combinable_setup_generation_flags():
    try:
        args = _build_parser().parse_args(
            ["plan", "matrix.fs", "--setup-guidelines", "--setup-standards"]
        )
    except SystemExit:
        args = None
    assert args is not None, "plan must accept the approved setup generation flags"
    assert args.setup_guidelines and args.setup_standards


def test_full_setup_inspection_has_a_cli_entrypoint():
    try:
        args = _build_parser().parse_args(["inspect-setups", "matrix.fs"])
    except SystemExit:
        args = None
    assert args is not None, "full inspection must be discoverable as a command"
    assert args.subcommand == "inspect-setups"


def test_typed_airfoil_assignment_reaches_curated_emitter():
    try:
        solver = SolverSettings(
            airfoil_separation=[
                {"name": "Wing stall", "valarezo_criterion": True, "boundaries": "all"}
            ]
        )
    except ValidationError:
        solver = None
    assert solver is not None, "workspace setups must carry typed separation assignments"
    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["loads.txt"],
        solver=solver,
    )
    script = Script("26.123")
    _settings(case, script)
    assert "CREATE_AIRFOIL_SEPARATION" in script.render()
    record = script.solver_setup.flags["CREATE_AIRFOIL_SEPARATION"]
    assert record.emitted and record.provenance == "explicit"


@pytest.mark.parametrize("field", ["surface_roughness", "valarezo_criterion"])
def test_additional_setup_fields_are_typed(field):
    assert field in SolverSettings.model_fields


def test_generated_library_resolves_and_preserves_user_files(tmp_path):
    # GOAL033:setup_bc:checks:typed_workspace
    """GOAL033:standards:checks:preserve_edits"""
    from pyflightstream.workspace.inputs import resolve_setup
    from pyflightstream.workspace.matrix import _solver_from_setup
    from pyflightstream.workspace.setup_standards import write_setup_library

    result = write_setup_library(tmp_path, fs_version="26.123", guidelines=True, standards=True)
    assert set(result.values()) == {"created"}
    assert "SETUP_GUIDELINES.md" in result
    for name in result:
        if name.endswith(".toml"):
            artifact = resolve_setup(tmp_path / "inputs", name.removesuffix(".toml"))
            _solver_from_setup(artifact, name.removesuffix(".toml"))
    same = write_setup_library(tmp_path, fs_version="26.123", guidelines=True, standards=True)
    assert set(same.values()) == {"unchanged"}
    edited = tmp_path / "inputs" / "setups" / "s900.toml"
    edited.write_text("# my settings\niterations = 777\n", encoding="utf-8")
    repeated = write_setup_library(tmp_path, fs_version="26.123", standards=True)
    assert repeated["s900.toml"] == "preserved"
    assert tomllib.loads(edited.read_text(encoding="utf-8"))["iterations"] == 777


def test_removed_control_is_commented_with_evidence():
    from pyflightstream.workspace.setup_standards import render_standard, setup_standards

    item = next(item for item in setup_standards() if item.code == "s922")
    text = render_standard(item, "26.123")
    assert "adverse_gradient_boundary_layer" not in tomllib.loads(text)
    assert "# UNAVAILABLE: adverse_gradient_boundary_layer = true" in text
    assert "no recorded evidence" in text


def test_single_setting_studies_change_only_one_selected_key():
    from pyflightstream.workspace.setup_standards import setup_standards

    standards = setup_standards()
    by_code = {item.code: item for item in standards}
    for item in standards:
        if item.code >= "s910":
            baseline = by_code[item.baseline_code].settings
            changed = {key for key in item.settings if item.settings[key] != baseline.get(key)}
            assert len(changed) == 1, item.code


def test_bad_build_generates_no_files(tmp_path):
    from pyflightstream.workspace.setup_standards import write_setup_library

    with pytest.raises(ValueError):
        write_setup_library(tmp_path, fs_version="made-up", guidelines=True, standards=True)
    assert not (tmp_path / "inputs").exists()


def test_typed_boundary_controls_reach_setup_phase():
    # GOAL033:setup_bc:checks:emitted_commands
    assert "trailing_edge_types" in SolverSettings.model_fields
    solver = SolverSettings(
        trailing_edge_types={1: "STANDARD"},
        disabled_wake_trailing_edges=[2],
        leading_edge_wake_boundaries=[1],
        mark_wake_termination_nodes=True,
    )
    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["loads.txt"],
        solver=solver,
    )
    script = Script("26.123")
    _settings(case, script)
    text = script.render()
    assert "SET_TRAILING_EDGE_TYPE 1 STANDARD" in text
    assert "DISABLE_WAKE_NODES_ON_TRAILING_EDGE 2" in text
    assert "DETECT_LEADING_EDGES_WAKES_BY_SURFACE" in text
    assert text.index("MARK_WAKE_TERMINATION_NODES") < text.index("SOLVER_SET_ITERATIONS")


def test_explicit_no_trailing_edge_is_preserved_and_emits_no_detection(tmp_path):
    # GOAL033:capability_ids:items:G17
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.cases import RawMeshConditions
    from pyflightstream.cases.workflows import _raw_mesh_boundary_conditions
    from pyflightstream.workspace.inputs import InputArtifactError, _read_trailing_edges

    try:
        marking = _read_trailing_edges(tmp_path / "body.boundaries.toml", {"none": True})
    except InputArtifactError:
        marking = None
    assert marking is not None, "a blunt body can explicitly declare no trailing edge"
    assert marking.route == "none"
    case = SimCase(
        sim_id="9001",
        aircraft="Body",
        recipe="steady",
        geometry=str(tmp_path / "body.stl"),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["loads.txt"],
        raw_mesh_conditions=RawMeshConditions(trailing_edges=marking),
    )
    script = Script("26.124")
    with pytest.warns(PyflightstreamWarning, match="no wake"):
        _raw_mesh_boundary_conditions(case, script)
    assert "TRAILING" not in script.render()
    assert case.model_dump()["raw_mesh_conditions"]["trailing_edges"]["route"] == "none"


def test_rotor_shedding_matrix_key_is_refused_without_changing_helper():
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import build_script, rotor_relaxed_trailing_edges

    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30", "ROTOR_SHEDDING": "AZIMUTH"},
        outputs=["loads.txt"],
    )
    with pytest.raises(CampaignConfigError, match="ROTOR_SHEDDING.*every matrix workflow"):
        build_script(case, Script("26.124"))
    assert rotor_relaxed_trailing_edges(case, ["0.5;0.1;0.9"]) == ["0.5;0.1;0.9;1"]


def test_multiple_actuator_records_have_independent_speed_and_loading():
    # GOAL033:capability_ids:items:G21
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import _actuator_disc, _the_actuator_the_row_names
    from pyflightstream.script import helpers

    case = SimCase(
        sim_id="9001",
        aircraft="Twin",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={
            "VELOCITY": "30",
            "ACTUATOR": "{ACTUATOR: Left / ACTUATOR_RPM: 2000 / ACTUATOR_THRUST: 100}, "
            "{ACTUATOR: Right / ADVANCE_RATIO: 0.5 / ACTUATOR_THRUST: 200}",
        },
        outputs=["loads.txt"],
        actuators={
            "Left": {"frame": "MRP", "axis": "X", "tip_radius_m": 1, "hub_radius_m": 0},
            "Right": {"frame": "MRP", "axis": "X", "tip_radius_m": 2, "hub_radius_m": 0},
        },
    )
    try:
        discs = _the_actuator_the_row_names(case)
    except CampaignConfigError:
        discs = None
    assert isinstance(discs, tuple) and len(discs) == 2
    assert [disc.rpm for disc in discs] == [2000, 900]
    assert [disc.thrust for disc in discs] == [100, 200]
    script = Script("26.124")
    frame = helpers.coordinate_frame(
        script, name="MRP", origin=(0, 0, 0), x_axis=(1, 0, 0), y_axis=(0, 1, 0)
    )
    _actuator_disc(case, script, {"MRP": frame}, discs)
    assert script.render().count("CREATE_NEW_ACTUATOR") == 2


def test_inlet_outlet_ownership_preserves_order_and_normal_velocity(tmp_path):
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.cases import RawMeshConditions
    from pyflightstream.cases.workflows import _raw_mesh_boundary_conditions, _settings
    from pyflightstream.workspace.inputs import read_raw_mesh_conditions
    from pyflightstream.workspace.matrix import _bind_setup_ports

    assert "ports" in RawMeshConditions.model_fields
    sidecar = tmp_path / "duct.boundaries.toml"
    sidecar.write_text(
        'boundaries = ["Inlet", "Outlet"]\n[trailing_edges]\nnone = true\n'
        '[ports]\nfeed = "Inlet"\nexit = "Outlet"\n',
        encoding="utf-8",
    )
    conditions = read_raw_mesh_conditions(sidecar)
    assert conditions.ports == {"feed": "Inlet", "exit": "Outlet"}
    case = SimCase(
        sim_id="9001",
        aircraft="Duct",
        recipe="steady",
        geometry=str(tmp_path / "duct.obj"),
        inventory=["Inlet", "Outlet"],
        raw_mesh_conditions=conditions,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "10", "FEED_VELOCITY": "-10", "EXIT_VELOCITY": "10"},
        solver={
            "ports": [
                {"port": "feed", "kind": "inlet"},
                {"port": "exit", "kind": "outlet"},
            ]
        },
        outputs=["loads.txt"],
    )
    case = _bind_setup_ports(case, tmp_path)
    assert case.solver.ports[0].velocity == -10.0
    assert case.solver.ports[1].velocity == 10.0
    script = Script("26.124")
    script.declare_existing(boundaries={"Inlet": 1, "Outlet": 2})
    with pytest.warns(PyflightstreamWarning, match="no wake"):
        _raw_mesh_boundary_conditions(case, script)
    _settings(case, script)
    text = script.render()
    assert text.index("CREATE_NEW_INLET") < text.index("CREATE_NEW_OUTLET")
    assert "-10.0" in text and "10.0" in text


@pytest.mark.parametrize("workflow", ["steady", "unsteady_rotor"], ids=["steady", "G35"])
def test_rotor_shedding_refused_by_registered_builder_guard(workflow):
    # GOAL033:capability_ids:items:G35
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import _refuse_unregistered_keys

    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"matrix_workflow": workflow, "ROTOR_SHEDDING": "AZIMUTH"},
    )
    with pytest.raises(CampaignConfigError, match="ROTOR_SHEDDING.*every matrix workflow"):
        _refuse_unregistered_keys(case, workflow)


def test_inspection_uses_resolved_setup_id_row_threads_and_shared_summary():
    from pyflightstream.workspace.setup_inspection import (
        inspect_case_setup,
        setup_inspection_summary,
    )

    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"matrix_set": "s901", "NCPUS": "4"},
        solver={"viscous_coupling": True, "iterations": 42},
        aliases={"wing": ["Wing"]},
    )
    result = inspect_case_setup(case, "26.124")
    assert result["setup"] == "s901"
    assert result["settings"]["max_threads"]["value"] == 4
    assert result["settings"]["max_threads"]["provenance"] == "matrix row"
    assert result["settings"]["iterations"]["provenance"] == "setup"
    assert result["aliases"] == {"wing": ["Wing"]}
    summary = setup_inspection_summary([result])
    assert "viscous_coupling=True" in summary and "aliases: wing" in summary


def test_full_inspection_and_saved_plan_share_the_same_resolved_records(tmp_path, capsys):
    # GOAL033:capability_ids:items:PFS-2029.24
    import json
    from pathlib import Path

    from pyflightstream.run.cli import main
    from tests.tier1_offline.test_matrix_cli import _workflow_plan_args, make_planned_workspace

    workspace = make_planned_workspace(tmp_path)
    argv = _workflow_plan_args(workspace)
    argv[0] = "inspect-setups"
    assert main(argv) == 0
    full = json.loads(capsys.readouterr().out)
    assert full and all(row["setup"] for row in full)
    argv[0] = "plan"
    assert main(argv) == 0
    output = capsys.readouterr().out
    # 0.31.0 (P0310-CONSOLE-BLOCKS): each row heads its own lines in the block
    # "Solver setup per case".
    block = output.split("\nSolver setup per case\n", 1)[1].split("\n\n", 1)[0]
    assert all(f"  POL {row['sim_id']} (FlightStream {row['build']}" in block for row in full)
    plan_file = workspace.plan_dir(Path(argv[1]).stem) / "plan.json"
    saved = json.loads(plan_file.read_text(encoding="utf-8"))
    assert saved["setup_inspections"] == full


def test_multiple_profile_inputs_survive_the_pending_input_writer(tmp_path):
    from pyflightstream.cases.workflows import _actuator_disc, _the_actuator_the_row_names
    from pyflightstream.run import _write_pending_files
    from pyflightstream.script import helpers

    profiles = {}
    for stem in ("left", "right"):
        path = tmp_path / (stem + ".txt")
        path.write_text("0.2,0.0\n0.6,100.0\n1.0,0.0\n", encoding="utf-8")
        profiles[stem] = str(path)
    case = SimCase(
        sim_id="9001",
        aircraft="Twin",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={
            "VELOCITY": "30",
            "ACTUATOR": "{ACTUATOR: Left / ACTUATOR_RPM: 2000 / PROFILE: left}, "
            "{ACTUATOR: Right / ACTUATOR_RPM: 1500 / PROFILE: right}",
        },
        actuator_profiles=profiles,
        actuators={
            name: {"frame": "MRP", "axis": "X", "tip_radius_m": 1, "hub_radius_m": 0.2, "blades": 2}
            for name in ("Left", "Right")
        },
    )
    script = Script("26.124")
    script.working_dir = tmp_path
    frame = helpers.coordinate_frame(
        script, name="MRP", origin=(0, 0, 0), x_axis=(1, 0, 0), y_axis=(0, 1, 0)
    )
    _actuator_disc(case, script, {"MRP": frame}, _the_actuator_the_row_names(case))
    hashes = _write_pending_files(script, tmp_path, case=case, recorded={})
    assert len(hashes) == 2
    assert all((tmp_path / name).is_file() for name in hashes)
    assert {name.split(".")[0] for name in hashes} == {"left", "right"}


def test_synthetic_duct_import_emits_ports_after_geometry(tmp_path):
    # GOAL033:capability_ids:items:G07
    import hashlib
    from pathlib import Path

    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.cases.workflows import _open_geometry
    from pyflightstream.workspace.inputs import read_raw_mesh_conditions
    from pyflightstream.workspace.matrix import _bind_setup_ports
    from tests.tier3_licensed.duct import write_duct_obj

    fixture = write_duct_obj(tmp_path / "duct.obj")
    # The whole file, and separately its geometry lines. Only the leading comment
    # changed when the private provenance header left the generator (GOAL-034):
    # the geometry lines hash as they did for the measured fixture, 5d9f45af...
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == (
        "3a5b243a5b04de61c107ba69a0b3c39c7998a1337c0f83c4414245f79248f6ee"
    )
    geometry = b"".join(
        line for line in fixture.read_bytes().splitlines(keepends=True) if not line.startswith(b"#")
    )
    assert hashlib.sha256(geometry).hexdigest() == (
        "4bfdbd210f29b7795e875612e85371440e95e904f93cc352457ccc4fc547fb70"
    )
    # The sidecar is a tier-1 fixture (GEO-060 B2, CX-7), so this offline test
    # reads no file of the licensed tier; the generator is only imported.
    source = Path(__file__).parent / "fixtures" / "duct.boundaries.toml"
    fixture.with_suffix(".boundaries.toml").write_bytes(source.read_bytes())
    case = SimCase(
        sim_id="9001",
        aircraft="Duct",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        geometry=str(fixture),
        inventory=["Inlet", "Outlet", "Wall"],
        mesh_import={"units": "METER"},
        solver=SolverSettings(
            ports=[{"port": "feed", "kind": "inlet"}, {"port": "exit", "kind": "outlet"}]
        ),
        variables={"VELOCITY": "30", "FEED_VELOCITY": "-10", "EXIT_VELOCITY": "10"},
        raw_mesh_conditions=read_raw_mesh_conditions(fixture.with_suffix(".boundaries.toml")),
    )
    case = _bind_setup_ports(case, tmp_path)
    script = Script("26.124")
    with pytest.warns(PyflightstreamWarning, match="no wake"):
        _open_geometry(case, script)
    _settings(case, script)
    emitted = script.render()
    assert (
        emitted.index("IMPORT")
        < emitted.index("CREATE_NEW_INLET")
        < emitted.index("CREATE_NEW_OUTLET")
    )


def test_matrix_binds_two_actuator_profile_stems(tmp_path):
    from pyflightstream.run import PlanStatus
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_g06_actuator_disc import (
        AS_SAVED,
        RECIPES,
        _plan,
        _profile_workspace,
    )

    cell = (
        "ACTUATOR: {ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct}, "
        "{ACTUATOR: OTHER / ACTUATOR_RPM: 1800 / PROFILE: twin_ct}"
    )
    workspace, matrix, first = _profile_workspace(tmp_path, cell)
    second = first.with_name("twin_ct.txt")
    second.write_bytes(AS_SAVED)
    ref = workspace.inputs_dir / "references/r003.toml"
    ref.write_text(
        ref.read_text(encoding="utf-8")
        + '\n[OTHER]\nkind = "actuator"\nframe = "MRP"\naxis = "X"\n'
        "tip_radius_m = 1.0\nhub_radius_m = 0.2\nblades = 3\n",
        encoding="utf-8",
    )
    resolved = resolve_matrix(matrix, workspace, name="two", fs_version="26.124", recipes=RECIPES)
    case = resolved.campaign.sims[0]
    assert case.actuator_profiles == {
        "prop_ct": str(first.resolve()),
        "twin_ct": str(second.resolve()),
    }
    plan = _plan(workspace, matrix)
    assert all(point.status == PlanStatus.READY for point in plan.points)


def test_inspection_resolves_symmetry_override_and_keeps_invalid_rows_inspectable():
    from pyflightstream.workspace.setup_inspection import inspect_case_setup

    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        solver={"symmetry_loads": False},
        variables={"SYMMETRY_LOADS": "TRUE", "NCPUS": "bad"},
    )
    result = inspect_case_setup(case, "26.124")
    assert result["settings"]["symmetry_loads"]["value"] is True
    assert result["settings"]["symmetry_loads"]["provenance"] == "matrix row"
    assert result["settings"]["max_threads"]["value"] is None
    assert "NCPUS" in result["settings"]["max_threads"]["error"]


def test_every_generated_standard_states_five_farfield_layers():
    # Owner rule of 2026-09-19: farfield_layers = 5 in the setup of every run.
    # The command database documents 1..5 (SRC-003 p.344); no study may vary it.
    from pyflightstream.workspace.setup_standards import render_standard, setup_standards

    for standard in setup_standards():
        data = tomllib.loads(render_standard(standard, "26.124"))
        assert data.get("farfield_layers") == 5, standard.code


def test_generated_guidelines_keep_spaces_in_page_references():
    # Q0-src-workspace-9: 'and536-544', 'and9', 'FlightStream26.0' were printed.
    import re

    from pyflightstream.workspace.setup_standards import render_guidelines

    text = render_guidelines("26.124")
    assert not re.findall(r"\band\d|FlightStream\d", text)


def test_solver_settings_refuse_farfield_layers_outside_the_documented_range():
    with pytest.raises(ValidationError):
        SolverSettings(farfield_layers=8)
    assert SolverSettings(farfield_layers=5).farfield_layers == 5
