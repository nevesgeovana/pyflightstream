# GEOVERSE_HEADER
# file_version: 1.0.0
# last_modified_at: 2026-09-27T19:37:24.103Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.cases, pyflightstream.cases.workflows]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Verify base-region arguments, ordering and build-specific names.
# revision_source: git
from pathlib import Path

import pytest

from pyflightstream.cases import RawMeshConditions, SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import _detect_base_regions, _raw_mesh_boundary_conditions
from pyflightstream.script import Script, ScriptOrderError


def case(settings, **kwargs):
    return SimCase(
        sim_id="9012",
        aircraft="Body",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        solver=settings,
        **kwargs,
    )


def test_operations_keep_base_indices_distinct_from_mesh_boundary_indices():
    setup = SolverSettings(
        base_region_operations=[
            {"operation": "create", "boundary": "Base", "model": "USER", "cp": -0.2},
            {"operation": "set_pressure", "index": 1, "model": "CUSTOM", "cp": -0.3},
            {"operation": "mark_trailing_edges", "index": "all"},
            {"operation": "select_faces", "index": 1},
            {"operation": "delete", "index": 1},
        ]
    )
    script = Script("26.124")
    script.declare_existing(boundaries={"Body": 1, "Base": 2})
    _detect_base_regions(case(setup), script)
    lines = script.render().splitlines()
    expected = [
        "CREATE_NEW_BASE_REGION 2 USER -0.2",
        "SET_BASE_REGION_CP 1 CUSTOM -0.3",
        "SET_BASE_REGION_TRAILING_EDGES -1",
        "SELECT_BASE_REGION_FACES 1",
        "DELETE_BASE_REGION 1",
    ]
    assert [line for line in lines if line in expected] == expected
    assert SolverSettings.model_validate_json(setup.model_dump_json()) == setup


@pytest.mark.parametrize(
    "operation",
    [
        {"operation": "set_pressure", "index": 1, "model": "USER", "cp": -0.3},
        {"operation": "delete", "index": "all"},
        {"operation": "create", "boundary": "Base", "model": "EMPIRICAL"},
        {"operation": "set_pressure", "index": 1, "model": "CUSTOM"},
        {"operation": "delete", "index": 1, "cp": -0.2},
        {"operation": "mark_outflow_edges", "index": 1},
        {"operation": "create", "boundary": "all", "model": "USER", "cp": -0.2},
    ],
)
def test_ambiguous_or_unsupported_base_operations_are_refused(operation):
    with pytest.raises(ValueError):
        SolverSettings(base_region_operations=[operation])


@pytest.mark.parametrize(
    "version,command",
    [
        ("26.122", "SET_OUTFLOW_TRAILING_EDGES"),
        ("26.124", "SET_OUTLET_TRAILING_EDGES"),
    ],
)
def test_outflow_base_edges_use_the_documented_name_for_the_build(version, command):
    setup = SolverSettings(
        base_region_operations=[{"operation": "mark_outflow_edges", "boundary": "all"}]
    )
    script = Script(version)
    _detect_base_regions(case(setup), script)
    assert command + " -1" in script.render()


def test_base_remesh_converts_metre_radius_and_precedes_initialization(tmp_path):
    geometry = tmp_path / "body.fsm"
    geometry.write_text("$GLOBAL_START$\n0.001\n2\n$GLOBAL_END$\n")
    setup = SolverSettings(
        base_region_operations=[
            {"operation": "create", "boundary": 1, "model": "EMPIRICAL", "cp": 0.0},
            {
                "operation": "remesh",
                "index": 1,
                "mesh": {"inner_radius_m": 0.02, "radial_faces": 4, "growth_scheme": "dual_sided"},
            },
        ]
    )
    script = Script("26.124")
    _detect_base_regions(case(setup, geometry=str(geometry)), script)
    text = script.render()
    assert text.index("CREATE_NEW_BASE_REGION") < text.index("REMESH_BASE_REGION")
    assert "INNER_RADIUS 20.0" in text
    assert "GROWTH_SCHEME 2" in text
    script.emit("SOLVER_SET_AOA", 0.0)
    with pytest.raises(ScriptOrderError):
        script.emit("REMESH_BASE_REGION", 1, 0.0, 4, "1", 1.0)


def test_detection_angle_precedes_auto_detection_and_is_not_emitted_twice(tmp_path):
    from pyflightstream.cases import TrailingEdgeMarking

    setup = SolverSettings(base_region_bending_angle_deg=25.0)
    conditions = RawMeshConditions(
        trailing_edges=TrailingEdgeMarking(route="none"), base_regions="auto"
    )
    body = case(setup, geometry=str(tmp_path / "body.obj"), raw_mesh_conditions=conditions)
    script = Script("26.124")
    with pytest.warns(UserWarning, match="no wake"):
        _raw_mesh_boundary_conditions(body, script)
    _detect_base_regions(body, script)
    text = script.render()
    assert text.count("SET_BASE_REGION_BENDING_ANGLE") == 1
    assert text.index("SET_BASE_REGION_BENDING_ANGLE 25.0") < text.index("AUTO_DETECT_BASE_REGIONS")


def test_documented_base_region_example_runs_without_a_solver():
    import runpy

    example = Path(__file__).resolve().parents[2] / "examples/base_region_setup.py"
    module = runpy.run_path(str(example))
    text = module["build_example"]()
    assert "CREATE_NEW_BASE_REGION 2 USER -0.2" in text
    assert text.index("SET_BASE_REGION_CP 1 CUSTOM -0.3") < text.index("INITIALIZE_SOLVER")


def test_outflow_marks_the_mesh_boundary_instead_of_assuming_a_base_index():
    setup = SolverSettings(
        base_region_operations=[
            {"operation": "create", "boundary": "Base", "model": "USER", "cp": -0.2},
            {"operation": "mark_outflow_edges", "boundary": "Base"},
        ]
    )
    script = Script("26.124")
    script.declare_existing(boundaries={"Body": 1, "Base": 2})
    _detect_base_regions(case(setup), script)
    assert "SET_OUTLET_TRAILING_EDGES 2" in script.render()
