# GEOVERSE_HEADER
# file_version: 1.1.1
# last_modified_at: 2026-09-27T22:14:41.161Z
# last_modified_by: OpenAI / Codex / unknown / implementation-author
# dependencies: [pyflightstream.cases.workflows, pyflightstream.fsi.nodes]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Test workspace coupling through the existing FsiConfig and driver.
# revision_source: git
"""Existing FSI selection reaches native setup, staged inputs and ordinary START.

The previous duplicate SolverSettings.aeroelastic API design and its RED receipt
are retained in GOAL-033 evidence. These tests exercise the approved existing API.
"""

import json
import math

import pytest

from pyflightstream.cases import (
    BladeDatum,
    MeshImport,
    PprocSpec,
    RawMeshConditions,
    SolverSettings,
)
from pyflightstream.cases.workflows import _script_init
from pyflightstream.fsi import nodes
from pyflightstream.run import _write_pending_files
from pyflightstream.script import Script
from tests.tier1_offline.conftest import make_uniform_blade_config
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_workflows import FIXTURE_ROTOR, rotor_case, steady_case


def coupled_case(tmp_path):
    geometry = tmp_path / "blade.obj"
    geometry.write_text("o Blade1\nv 0 0 0.2\nv 0 .1 .2\nv 0 0 1.2\nf 1 2 3\n")
    rotor = FIXTURE_ROTOR.model_copy(
        update={
            "blade1": BladeDatum(azimuth_deg=0, zero="Z"),
        }
    )
    cfg = make_uniform_blade_config(blade_count=1, omega_rad_per_s=40 * math.pi)
    cfg = cfg.model_copy(update={"time_increment_s": 0.0001})
    return rotor_case(MOVING_BOUNDARIES="Blade1", BLADES="1").model_copy(
        update={
            "geometry": str(geometry),
            "mesh_import": MeshImport(units="METER"),
            "raw_mesh_conditions": RawMeshConditions.model_validate(
                {"trailing_edges": {"route": "detect"}}
            ),
            "inventory": ["Blade1"],
            "rotors": {"ROTOR": rotor},
            "fsi": cfg,
            "pproc": PprocSpec.model_validate(
                {
                    "sections": {
                        "count": 5,
                        "distributions": [
                            {
                                "families": ["Blade1"],
                                "frame": "LOCAL_AXIS",
                                "planes": ["XY"],
                            }
                        ],
                    },
                }
            ),
        }
    )


def test_selected_fsi_wires_existing_driver_and_stages_single_source(tmp_path):
    case = coupled_case(tmp_path)
    lines, script = _lines(case)
    assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE" in lines
    assert lines.index("SET_AEROELASTIC_ITERATIONS 1") < lines.index("START_SOLVER")
    assert "EXECUTE_AEROELASTIC_ANALYSIS" not in lines
    frame = int(script.section_blocks[0]["frame_index"])
    assert f"IMPORT_AEROELASTIC_STRUCTURAL_NODES {frame} DISABLE" in lines
    run_dir = tmp_path / "run"
    hashes = _write_pending_files(script, run_dir, case=case, recorded={})
    assert {
        "config.json",
        "fsi_node_map.json",
        "fsi_family_map.json",
        "fsi_nodes.csv",
        "fsi_callback.py",
        "fsi_post.txt",
    } <= set(hashes)
    assert json.loads((run_dir / "config.json").read_text()) == case.fsi.model_dump(mode="json")
    assert nodes.load_node_map(run_dir / case.fsi.node_map_file) == (
        nodes.generate_node_layout(case.fsi)
    )
    expected = tmp_path / "expected.csv"
    nodes.write_node_file(nodes.generate_node_layout(case.fsi), expected)
    assert (run_dir / "fsi_nodes.csv").read_bytes() == expected.read_bytes()
    family_map = json.loads((run_dir / "fsi_family_map.json").read_text())
    assert family_map["families"] == [{"name": "Blade1", "count": 5, "is_blade": True}]
    post = (run_dir / "fsi_post.txt").read_text()
    assert "UPDATE_ALL_SURFACE_SECTIONS" in post
    assert "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS" in post
    assert "FS_SurfaceSection_Loads.txt" in post
    assert "from pyflightstream.fsi.cli import main" in (run_dir / "fsi_callback.py").read_text()


@pytest.mark.parametrize(
    "change, message",
    [
        ({"solver": SolverSettings(simulation_length_unit="MILLIMETER")}, "METER"),
        ({"pproc": PprocSpec()}, "section"),
    ],
)
def test_unproved_workspace_inputs_are_refused(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        _lines(coupled_case(tmp_path).model_copy(update=change))


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("omega_rad_per_s", 0.0, "positive|zero"),
        ("omega_rad_per_s", 1.0, "omega|speed"),
        ("time_increment_s", 0.02, "time|clock"),
        ("blade_count", 2, "blade count"),
        ("node_map_file", "config.json", "collision|reserved"),
    ],
)
def test_inconsistent_structural_inputs_are_refused(tmp_path, field, value, message):
    case = coupled_case(tmp_path)
    case = case.model_copy(update={"fsi": case.fsi.model_copy(update={field: value})})
    with pytest.raises(ValueError, match=message):
        _lines(case)


def test_steady_selection_is_named_refusal(tmp_path):
    case = steady_case().model_copy(update={"fsi": coupled_case(tmp_path).fsi})
    with pytest.raises(ValueError, match="unsteady"):
        _lines(case)


def test_duplicate_sections_do_not_silently_choose_first(tmp_path):
    case = coupled_case(tmp_path)
    distribution = case.pproc.sections.distributions[0]
    pproc = case.pproc.model_copy(deep=True)
    pproc.sections.distributions.append(distribution)
    with pytest.raises(ValueError, match="section|unique"):
        _lines(case.model_copy(update={"pproc": pproc}))


def test_unproved_continuation_refuses_before_initializing(tmp_path):
    case = coupled_case(tmp_path)
    script = Script("26.124")
    with pytest.raises(ValueError, match="continuation"):
        _script_init(case, script, None, frames=None, reopens_a_saved_state=True)
    assert "INITIALIZE_SOLVER" not in script.render()


def test_no_fsi_preserves_existing_run_without_callback(tmp_path):
    case = coupled_case(tmp_path).model_copy(update={"fsi": None})
    lines, script = _lines(case)
    assert not any("AEROELASTIC" in line for line in lines)
    assert not any(name.startswith("fsi_") for name in script.pending_input_files)


def test_saved_fsm_section_order_is_not_guessed(tmp_path):
    case = coupled_case(tmp_path)
    saved = tmp_path / "existing.fsm"
    saved.write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n")
    case = case.model_copy(
        update={"geometry": str(saved), "mesh_import": None, "raw_mesh_conditions": None}
    )
    with pytest.raises(ValueError, match="inherited.*section|saved.*section"):
        _lines(case)


@pytest.mark.parametrize("kind", ["wrong-plane", "wrong-frame", "extra-rotor"])
def test_ambiguous_or_incompatible_mapping_has_no_callback(tmp_path, kind):
    case = coupled_case(tmp_path)
    if kind == "extra-rotor":
        other = FIXTURE_ROTOR.model_copy(update={"alias": "OTHER"})
        case = case.model_copy(update={"rotors": {**case.rotors, "OTHER": other}})
    else:
        pproc = case.pproc.model_copy(deep=True)
        if kind == "wrong-plane":
            pproc.sections.distributions[0].planes = ["XZ"]
        else:
            pproc.sections.distributions[0].frame = "ROTOR_SMRP"
        case = case.model_copy(update={"pproc": pproc})
    script = Script("26.124")
    from pyflightstream.cases.workflows import build_script

    with pytest.raises(ValueError):
        build_script(case, script)
    assert "fsi_callback.py" not in script.pending_input_files
    assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY" not in script.render()


def test_pending_node_input_collision_is_refused_before_coupling(tmp_path):
    from pyflightstream.cases.workflows import build_script

    script = Script("26.124")
    script._pending_input_files["FSI_NODES.CSV"] = "user-owned contents"
    with pytest.raises(ValueError, match="collision"):
        build_script(coupled_case(tmp_path), script)
    assert script.pending_input_files["FSI_NODES.CSV"] == "user-owned contents"
    assert "SET_AEROELASTIC_COUPLING_IN_UNSTEADY" not in script.render()
