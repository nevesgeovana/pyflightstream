"""P0580-BC (PFS-2176 review, PFS-2249 to PFS-2257): each boundary condition has one home.

The owner's review of 2026-11-15 gave every FlightStream boundary condition one declaration.
A condition that moved is refused by name at its old home, the refusal naming the new one;
a condition with no route gained one. Each test runs the reader or the builder a user meets
and asserts what the node's acceptance sentence states.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.commands import CommandNotInVersionError


def _detect_instruction(detect: dict):
    from pyflightstream.cases._geometry_instruction import GeometryInstruction, MeshSource
    from pyflightstream.cases.mesh import TrailingEdgeMarking

    return GeometryInstruction(
        name="wing",
        outputs=("fsm",),
        boundaries=("Wing",),
        kind="mesh",
        mesh=MeshSource(file="wing.obj", units="METER"),
        trailing_edges=TrailingEdgeMarking(route="detect", **detect),
    )


def test_p0580_pfs2249_bluntness_angle_is_read_beside_the_sweep_angle(tmp_path: Path):
    """PFS-2249: ``detect = { ..., bluntness_angle = ... }`` reaches the marking in degrees."""
    from pyflightstream.workspace.sidecars import read_trailing_edges

    marking = read_trailing_edges(
        tmp_path / "wing.obj.boundaries.toml",
        {"detect": {"surfaces": ["Wing"], "sweep_angle": 30, "bluntness_angle": 120}},
    )
    assert (marking.sweep_angle_deg, marking.bluntness_angle_deg) == (30.0, 120.0)


def test_p0580_pfs2249_bluntness_angle_emits_its_command_where_the_build_has_a_row(tmp_path):
    """PFS-2249: the angle is set before the detection on a build whose row allows it."""
    from pyflightstream.cases._geometry_emit import render_geometry_script

    instruction = _detect_instruction({"detect_surfaces": ("Wing",), "bluntness_angle_deg": 120.0})
    text = render_geometry_script(
        instruction, folder=tmp_path, work=tmp_path / "partial", version="26.121"
    ).text
    lines = text.splitlines()
    blunt = next(i for i, line in enumerate(lines) if "SET_TRAILING_EDGE_BLUNTNESS_ANGLE" in line)
    detect = next(i for i, line in enumerate(lines) if "DETECT_TRAILING_EDGES_BY_SURFACE" in line)
    assert blunt < detect
    assert lines[blunt].split()[-1].startswith("120")


def _setup_refusal(tmp_path: Path, text: str) -> str:
    """Read ``text`` as setup s001 the way a row's SET cell does; return the refusal."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace.inputs import resolve_setup

    (tmp_path / "setups").mkdir(exist_ok=True)
    (tmp_path / "setups" / "s001.toml").write_text(text, encoding="utf-8")
    with pytest.raises(InputArtifactError) as refused:
        resolve_setup(tmp_path, "s001")
    return str(refused.value)


def _binding_refusal(settings: dict) -> str:
    """Bind ``settings`` as a preset a matrix row names; return the refusal."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace._matrix_binding import _solver_from_setup
    from pyflightstream.workspace.inputs import SetupArtifact

    with pytest.raises(InputArtifactError) as refused:
        _solver_from_setup(SetupArtifact(settings=settings), "s001")
    return str(refused.value)


def _python_refusal(**settings) -> str:
    from pyflightstream.cases import SolverSettings

    with pytest.raises(ValueError) as refused:
        SolverSettings(**settings)
    return str(refused.value)


@pytest.mark.parametrize("key", ["physics_auto_trailing_edges", "physics_auto_wake_nodes"])
def test_p0580_pfs2250_physics_switches_are_refused_naming_the_detection(tmp_path, key):
    """PFS-2250: each PHYSICS switch is refused by name, naming the boundaries-file detection."""
    for said in (
        _setup_refusal(tmp_path, f"{key} = true\n"),
        _binding_refusal({key: True}),
        _python_refusal(**{key: False}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert '[trailing_edges] detect = "auto"' in said, said
        assert '[wake_termination] detect = "auto"' in said, said


def test_p0580_pfs2251_sonic_velocity_is_refused_naming_the_air_state(tmp_path):
    """PFS-2251: the speed of sound follows from the air state; the key is refused at read."""
    key = "sonic_velocity_m_per_s"
    for said in (
        _setup_refusal(tmp_path, f"{key} = 340.0\n"),
        _binding_refusal({key: 340.0}),
        _python_refusal(**{key: 340.0}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert "air state" in said and "flight-condition columns" in said, said


def test_p0580_pfs2255_setup_symmetry_loads_is_refused_naming_the_column(tmp_path):
    """PFS-2255: the half or full loads are the SYMMETRY_LOADS column only."""
    key = "symmetry_loads"
    for said in (
        _setup_refusal(tmp_path, f"{key} = true\n"),
        _binding_refusal({key: False}),
        _python_refusal(**{key: True}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert "SYMMETRY_LOADS column" in said, said


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("valarezo_separation_boundaries", ["RotorRig"]),
        ("crossflow_separation_boundaries", ["RotorRig"]),
    ],
)
@pytest.mark.parametrize("build", ["26.101", "26.127"])
def test_p0580_pfs2257_per_mechanism_keys_are_refused_on_later_builds(key, value, build):
    """PFS-2257: on a build with no row for the list, the key is refused naming the models."""
    from pyflightstream.cases import CampaignConfigError, SolverSettings
    from tests.tier1_offline.test_workflows import rendered, steady_case

    case = steady_case().model_copy(update={"solver": SolverSettings(**{key: value})})
    with pytest.raises(CampaignConfigError) as refused:
        rendered(case, build)
    said = str(refused.value)
    assert key in said and build in said, said
    assert "airfoil_separation" in said and "stratford_bulk_separation" in said, said


@pytest.mark.parametrize("build", ["26.101", "26.127"])
def test_p0580_pfs2257_axial_families_are_refused_on_later_builds(tmp_path, build):
    """PFS-2257: the axial list, whose names resolve first (FR-988), is refused by the build."""
    from pyflightstream.cases import CampaignConfigError, SolverSettings
    from tests.tier1_offline.test_goal031_g08_glossary_claims import _over_wing
    from tests.tier1_offline.test_workflows import rendered

    case = _over_wing(tmp_path).model_copy(
        update={"solver": SolverSettings(axial_separation_families=["Body"])}
    )
    with pytest.raises(CampaignConfigError, match="axial_separation_families") as refused:
        rendered(case, build)
    assert build in str(refused.value) and "axial_vortex_separation" in str(refused.value)


def test_p0580_pfs2257_per_mechanism_keys_still_emit_on_26100():
    """PFS-2257: the build that carries the per-mechanism list keeps the key."""
    from pyflightstream.cases import SolverSettings
    from tests.tier1_offline.test_workflows import rendered, steady_case

    case = steady_case().model_copy(
        update={"solver": SolverSettings(valarezo_separation_boundaries=[1])}
    )
    assert "SET_VALAREZO_SEPARATION_BOUNDARIES" in rendered(case, "26.100")


def test_p0580_pfs2256_setup_thin_boundaries_is_refused_naming_the_boundaries_file(tmp_path):
    """PFS-2256: the setup key is refused by name, naming the boundaries file."""
    key = "thin_boundaries"
    for said in (
        _setup_refusal(tmp_path, f'{key} = ["Wing"]\n'),
        _binding_refusal({key: ["Wing"]}),
        _python_refusal(**{key: "all"}),
    ):
        assert key in said and "no longer accepted" in said, said
        assert "boundaries file" in said, said


def test_p0580_pfs2256_the_boundaries_file_marks_a_boundary_thin(tmp_path):
    """PFS-2256: ``thin_boundaries`` of the boundaries file is read and emits the command."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace.sidecars import read_thin_boundaries
    from tests.tier1_offline.test_goal031_g08_glossary_claims import _over_wing
    from tests.tier1_offline.test_workflows import rendered

    sidecar = tmp_path / "wing.fsm.boundaries.toml"
    sidecar.write_text('boundaries = ["RotorRig"]\nthin_boundaries = ["RotorRig"]\n', "utf-8")
    assert read_thin_boundaries(sidecar) == ("RotorRig",)
    sidecar.write_text('boundaries = ["RotorRig"]\nthin_boundaries = []\n', "utf-8")
    assert read_thin_boundaries(sidecar) == ()
    sidecar.write_text('boundaries = ["RotorRig"]\n', "utf-8")
    assert read_thin_boundaries(sidecar) is None
    sidecar.write_text('thin_boundaries = "RotorRig"\n', "utf-8")
    with pytest.raises(InputArtifactError, match="list of boundary names"):
        read_thin_boundaries(sidecar)
    wing = _over_wing(tmp_path).model_copy(update={"boundaries_file": str(sidecar)})
    sidecar.write_text('thin_boundaries = ["Body"]\n', "utf-8")
    assert "SET_THIN_BOUNDARIES 1\n2\n" in rendered(wing, "26.124")
    sidecar.write_text("thin_boundaries = []\n", "utf-8")
    assert "DELETE_THIN_BOUNDARIES" in rendered(wing, "26.124")
    sidecar.write_text('boundaries = ["Wing", "Body", "Base"]\n', "utf-8")
    assert "THIN_BOUNDARIES" not in rendered(wing, "26.124")


def test_p0580_pfs2256_a_matrix_row_binds_the_thin_boundaries_of_its_geometry(tmp_path):
    """PFS-2256: a row's script marks what its geometry's boundaries file marks thin."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES
    from tests.tier1_offline.test_p0390_r02 import BUILD, WING_BODY, study

    workspace, path = study(tmp_path, models=(WING_BODY,))
    sidecar = workspace.inputs_dir / "geometries" / "wb.fsm.boundaries.toml"
    sidecar.write_text(
        'boundaries = ["Wing", "Body", "Base"]\nthin_boundaries = ["Wing"]\n', "utf-8"
    )
    resolved = resolve_matrix(path, workspace, name="study", fs_version=BUILD, recipes=RECIPES)
    case = resolved.campaign.sims[0]
    assert case.boundaries_file is not None and Path(case.boundaries_file).name == sidecar.name
    script = Script(BUILD)
    build_script(case.model_copy(update={"point": {"alpha": 0.0}}), script)
    assert "SET_THIN_BOUNDARIES 1\n1\n" in script.render()
    sidecar.write_text('boundaries = ["Wing", "Body", "Base"]\nthin_boundaries = "Wing"\n', "utf-8")
    with pytest.raises(InputArtifactError, match="thin_boundaries"):
        resolve_matrix(path, workspace, name="study", fs_version=BUILD, recipes=RECIPES)


@pytest.mark.parametrize("listed", ["[]", '["Base"]'])
def test_p0580_pfs2252_pproc_base_regions_is_refused_naming_the_one_home(tmp_path, listed):
    """PFS-2252: the pproc key is refused at read and from Python, naming its homes."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.cases import PprocSpec
    from pyflightstream.workspace.inputs import resolve_pproc

    (tmp_path / "pproc").mkdir()
    (tmp_path / "pproc" / "p001.toml").write_text(
        f'base_regions = {listed}\n[groups]\nWING = "wing"\n', encoding="utf-8"
    )
    with pytest.raises(InputArtifactError) as refused:
        resolve_pproc(tmp_path, "p001")
    with pytest.raises(ValueError) as from_python:
        PprocSpec(base_regions=["Base"])
    for said in (str(refused.value), str(from_python.value)):
        assert "base_regions of a pproc is no longer accepted" in said, said
        assert "[base_regions.<family>]" in said and "BASE_REGIONS column" in said, said
        assert "legacy groups-artifact" not in said, said


@pytest.mark.parametrize("build", ["26.122", "26.127"])
def test_p0580_pfs2249_bluntness_angle_is_refused_on_a_build_with_no_row(tmp_path, build):
    """PFS-2249: 26.122 removed the command and 26.127 has no row, so the build refuses it."""
    from pyflightstream.cases._geometry_emit import render_geometry_script

    instruction = _detect_instruction({"bluntness_angle_deg": 120.0})
    with pytest.raises(CommandNotInVersionError, match="SET_TRAILING_EDGE_BLUNTNESS_ANGLE"):
        render_geometry_script(
            instruction, folder=tmp_path, work=tmp_path / "partial", version=build
        )


def test_p0580_one_aircraft_declaration_plans_a_wing_off_mesh_ready(tmp_path):
    """One set names Wing, Fuselage, Tail and a rotor; the row lacks Wing only."""
    from pyflightstream.run import PlanStatus
    from tests.tier1_offline.test_p0390_r02 import REFERENCE, ROTOR, planned, status_of, study

    reference = REFERENCE + ROTOR
    setup = """iterations = 20
analysis_families = ["Wing", "Fuselage", "Tail", "PUSHER"]
vorticity_drag_families = ["Wing", "Fuselage", "PUSHER"]
viscous_excluded = ["Wing", "Fuselage"]
proximal_boundaries = ["Wing", "Fuselage"]
leading_edge_wake_boundaries = ["Wing", "Fuselage"]
[[airfoil_separation]]
name = "aircraft"
boundaries = ["Wing", "Fuselage", "Tail"]
valarezo_criterion = true
"""
    names = ["Fuselage", "Tail", "Spinner", "Prop1", "Prop2"]
    workspace, matrix = study(
        tmp_path,
        reference=reference,
        setup=setup,
        pproc='[groups]\nAIRCRAFT = "all"\n',
        models=(("2001", "wing_off.fsm", names), ("2002", "full.fsm", ["Wing", *names])),
        rows={},
    )
    sidecar = workspace.inputs_dir / "geometries" / "wing_off.fsm.boundaries.toml"
    import json

    sidecar.write_text(
        "boundaries = "
        + json.dumps(["Wing", *names])
        + '\nthin_boundaries = ["Wing", "Fuselage"]\n',
        encoding="utf-8",
    )
    plan, said = planned(workspace, matrix)
    assert status_of(plan) == {"2001": {PlanStatus.READY}, "2002": {PlanStatus.READY}}, (
        plan.summary()
    )
    skipped = [text for text in said if "'Wing'" in text and "skipped" in text]
    assert skipped and all("'2001'" in text and "'2002'" not in text for text in skipped), said


@pytest.mark.parametrize(
    "key",
    [
        "analysis_families",
        "vorticity_drag_families",
        "viscous_excluded",
        "proximal_boundaries",
        "leading_edge_wake_boundaries",
    ],
)
def test_p0580_a_setting_naming_only_an_absent_family_emits_no_selection(tmp_path, key):
    from pyflightstream.cases import SolverSettings
    from tests.tier1_offline.test_goal031_g08_glossary_claims import _over_wing
    from tests.tier1_offline.test_workflows import rendered

    case = _over_wing(tmp_path).model_copy(update={"solver": SolverSettings(**{key: ["Tail"]})})
    text = rendered(case, "26.124")
    command = {
        "analysis_families": "SET_SOLVER_ANALYSIS_BOUNDARIES",
        "vorticity_drag_families": "SET_VORTICITY_DRAG_BOUNDARIES",
        "viscous_excluded": "VISCOUS_EXCLUDED_BOUNDARIES",
        "proximal_boundaries": "SOLVER_PROXIMAL_BOUNDARIES",
        "leading_edge_wake_boundaries": "DETECT_LEADING_EDGES_WAKES_BY_SURFACE",
    }[key]
    assert command not in text


@pytest.mark.parametrize("present", [False, True])
def test_p0580_surface_transforms_skip_an_absent_alias_member(tmp_path, present):
    from pyflightstream.cases import ReferenceData
    from tests.tier1_offline.test_goal031_g08_glossary_claims import _over_wing
    from tests.tier1_offline.test_workflows import rendered

    case = _over_wing(tmp_path).model_copy(
        update={
            "reference": ReferenceData(area=1.0, length=1.0, moment_point_m=(0, 0, 0)),
            "aliases": {"model": ["Tail", "Body"] if present else ["Tail"]},
            "rotations": [{"ALIAS": "model", "ANGLE": "3", "AXIS": "MRP-Y"}],
            "translations": [{"ALIAS": "model", "DISTANCE": "0.1", "AXIS": "MRP-X"}],
        }
    )
    text = rendered(case, "26.124")
    assert ("TRANSLATE_SURFACE_IN_FRAME" in text) is present
    assert ("ROTATE_SURFACE " in text) is present


@pytest.mark.parametrize("present", [False, True])
def test_p0580_rotary_motion_skips_absent_families_without_a_zero_boundary_motion(
    tmp_path, present
):
    from tests.tier1_offline.test_goal031_g08_glossary_claims import _on_wing
    from tests.tier1_offline.test_workflows import rendered, rotor_case

    case = _on_wing(
        tmp_path, rotor_case(BLADES=None, MOVING_BOUNDARIES="Tail, Body" if present else "Tail")
    )
    text = rendered(case, "26.124")
    assert ("SET_MOTION_BOUNDARIES" in text) is present


def test_p0580_filtering_preserves_the_order_of_mixed_names_and_positions(tmp_path):
    from pyflightstream.cases import SolverSettings
    from tests.tier1_offline.test_goal031_g08_glossary_claims import _over_wing
    from tests.tier1_offline.test_workflows import rendered

    case = _over_wing(tmp_path).model_copy(
        update={
            "solver": SolverSettings(viscous_excluded=["Wing", 3, "Tail", "Body"]),
        }
    )
    lines = rendered(case, "26.124").splitlines()
    at = lines.index("SET_VISCOUS_EXCLUDED_BOUNDARIES 3")
    assert [int(value) for value in lines[at + 1].replace(",", " ").split()] == [1, 3, 2]
