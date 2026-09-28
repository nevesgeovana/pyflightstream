"""Offline CAD routing; these assertions do not establish native mesh quality or scale."""

from pathlib import Path

import pytest

from pyflightstream import cases
from pyflightstream.cases.workflows import _open_geometry
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import read_mesh_import
from tests.tier1_offline.test_workflows import steady_case


def _case(tmp_path, suffix=".igs", **options):
    path = tmp_path / ("staged" + suffix)
    path.write_text("synthetic routing placeholder", encoding="utf-8")
    spec = cases.MeshImport(units="FILE", cad=options)
    return steady_case().model_copy(
        update={
            "geometry": str(path),
            "mesh_import": spec,
            "inventory": ("Wing",),
            "inventory_source": "sidecar",
            "raw_mesh_conditions": cases.RawMeshConditions(
                trailing_edges=cases.TrailingEdgeMarking(route="detect")
            ),
        }
    )


@pytest.mark.parametrize("suffix", [".igs", ".iges"], ids=["G31", ".iges"])
def test_cad_converts_staged_input_before_mesh_conditions(tmp_path, suffix):
    # GOAL033:capability_ids:items:G31
    case = _case(tmp_path, suffix)
    script = Script("26.124")
    _open_geometry(case, script)
    lines = script.render().splitlines()
    imported = lines.index("IMPORT_CAD MEDIUM TRUE 80")
    converted = lines.index("CONVERT_CAD_TO_MESH -1")
    assert lines[imported + 1] == str(case.geometry)
    assert imported < converted < lines.index("SET_SIMULATION_LENGTH_UNITS METER")
    assert converted < lines.index("AUTO_DETECT_TRAILING_EDGES")
    assert not any(line.startswith("IMPORT ") for line in lines)


def test_cad_sidecar_options_reach_native_arguments(tmp_path):
    path = tmp_path / "part.boundaries.toml"
    path.write_text(
        '[import]\nunits="FILE"\n[import.cad]\n'
        'tessellation_density="HIGH"\nunreferenced_patches=false\n'
        "num_curvature=120\nbody_index=2\n",
        encoding="utf-8",
    )
    spec = read_mesh_import(path)
    case = _case(tmp_path).model_copy(update={"mesh_import": spec})
    script = Script("26.124")
    _open_geometry(case, script)
    assert "IMPORT_CAD HIGH FALSE 120" in script.render()
    assert "CONVERT_CAD_TO_MESH 2" in script.render()


@pytest.mark.parametrize(
    "options", [{"num_curvature": 0}, {"body_index": 0}, {"body_index": -2}, {"unrecognized": 1}]
)
def test_cad_options_refuse_invalid_values(tmp_path, options):
    with pytest.raises(ValueError):
        _case(tmp_path, **options)


def test_cad_never_silently_discards_raw_import_unit(tmp_path):
    case = _case(tmp_path)
    case = case.model_copy(
        update={"mesh_import": case.mesh_import.model_copy(update={"units": "MILLIMETER"})}
    )
    with pytest.raises(cases.CampaignConfigError, match="FILE"):
        _open_geometry(case, Script("26.124"))


def test_raw_mesh_never_silently_discards_cad_options(tmp_path):
    case = _case(tmp_path, ".stl")
    with pytest.raises(cases.CampaignConfigError, match="CAD"):
        _open_geometry(case, Script("26.124"))


def test_cad_requires_conversion_table(tmp_path):
    case = _case(tmp_path).model_copy(update={"mesh_import": cases.MeshImport(units="METER")})
    with pytest.raises(cases.CampaignConfigError, match=r"import\.cad"):
        _open_geometry(case, Script("26.124"))


def test_public_cad_example_emits_complete_workflow(tmp_path):
    import runpy

    example = Path(__file__).resolve().parents[2] / "examples" / "cad_import.py"
    main = runpy.run_path(str(example))["cad_script"]
    text = main(tmp_path / "wing.igs", ("Wing",))
    assert "IMPORT_CAD MEDIUM TRUE 80" in text
    assert "INITIALIZE_SOLVER" in text
    assert "START_SOLVER" in text


@pytest.mark.parametrize("suffix", [".step", ".stp"])
def test_unproved_step_route_is_refused_before_emission(tmp_path, suffix):
    script = Script("26.124")
    with pytest.raises(cases.CampaignConfigError, match="STEP.*IGES"):
        _open_geometry(_case(tmp_path, suffix), script)
    assert "IMPORT_CAD" not in script.render()
