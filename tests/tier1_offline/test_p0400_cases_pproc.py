"""Tier 1: the pproc models refuse what they cannot honour and declare what they read (0.40.0)."""

import ast
import inspect
import math

import pytest
from pydantic import ValidationError

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import CampaignConfigError, RotorBlock, acoustics, pproc
from pyflightstream.cases.pproc import (
    PprocSpec,
    ProbeCircle,
    ProbeLine,
    ProbeRectangle,
    ProbesSpec,
    SurfaceProbeSpec,
    classify_outputs,
)
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import resolve_pproc
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, steady_case

SECTIONS = {"distributions": [{"families": "all", "planes": ["XZ"]}]}
SURFACE_PROBE = {
    "name": "upper_cp",
    "parameter": "CP_FREE",
    "frame": "REFERENCE",
    "point_m": [0.25, 0.1, 0.02],
}
NORMAL_PROBES = {
    "kind": "normal",
    "parameters": ["VX"],
    "lines": [{"start": [0, 0, 0], "end": [1, 0, 0]}],
}


@pytest.mark.parametrize("kind", ["vtk", "sections"])
def test_p0400_boundary_layer_integrals_refuse_an_explicit_false_source(kind):
    """P0400-BL-SOURCES (PFS-2084.003): the product does not re-enable an export set false."""
    with pytest.raises(ValidationError) as caught:
        PprocSpec.model_validate(
            {
                "products": {"boundary_layer_integrals": True},
                "sections": SECTIONS,
                "exports": {kind: False},
            }
        )
    text = str(caught.value)
    assert "boundary_layer_integrals" in text and f"[exports] {kind} = false" in text


def test_p0400_pproc_imports_no_acoustics_inside_a_function():
    """P0400-ACOUSTIC-CYCLE (PFS-2088.001): pproc holds the suffixes, acoustics publishes them."""
    tree = ast.parse(inspect.getsource(pproc))
    imported = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and "acoustics" in node.module
    ]
    assert imported == []
    assert acoustics.is_acoustic_output is pproc.is_acoustic_output
    assert acoustics.ACOUSTIC_SIGNALS_SUFFIX == pproc.ACOUSTIC_SIGNALS_SUFFIX
    assert classify_outputs(["P_acoustic_signals.txt", "P.txt"]) == {"loads": "P.txt"}


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (ProbeLine, {"start": [math.nan, 0, 0], "end": [1, 0, 0]}),
        (
            ProbeRectangle,
            {
                "origin": [0, 0, 0],
                "along_u": [math.inf, 0, 0],
                "along_v": [0, 1, 0],
                "points_u": 2,
                "points_v": 2,
            },
        ),
        (
            ProbeCircle,
            {
                "center": [0, 0, math.nan],
                "normal": [0, 0, 1],
                "radius": 1.0,
                "points_radial": 2,
                "points_azimuth": 3,
            },
        ),
    ],
)
def test_p0400_probe_shapes_refuse_non_finite_coordinates(model, data):
    """P0400-PROBE-FINITE (PFS-2093.008): a NaN or infinite coordinate is refused."""
    with pytest.raises(ValidationError, match="finite"):
        model.model_validate(data)


@pytest.mark.parametrize("field", ["x_m", "y_m", "z_m", "diameter_m", "axis"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_p0400_rotor_refuses_non_finite_geometry(field, value):
    """P0400-ROTOR-FINITE (PFS-2093.008): rotor coordinates and shaft components are finite."""
    data = {"alias": "ROTOR", "axis": "Z", "diameter_m": 1.0, "families_blades": ["Blade1"]}
    data[field] = [value, 0, 1] if field == "axis" else value
    with pytest.raises(ValidationError, match="finite"):
        RotorBlock.model_validate(data)


def test_p0400_group_refusal_reaches_the_loader_with_the_artifact_path(tmp_path):
    """P0400-GROUPS-PATH (PFS-2100.001): the [groups] refusal names the artifact file."""
    path = tmp_path / "pproc" / "p001.toml"
    path.parent.mkdir()
    path.write_text('[groups]\ng1 = ["Wing", "Tail"]\n', encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        resolve_pproc(tmp_path, "p001")
    text = str(caught.value)
    assert str(path) in text and "member lists were removed" in text


@pytest.mark.parametrize("stated", [3, True, {"alias": "wing"}])
def test_p0400_group_that_is_not_a_string_is_refused_by_name(stated):
    """P0400-GROUPS-FORM (PFS-2100.002): no 'valid list' error on the entries that are right."""
    with pytest.raises(ValidationError) as caught:
        PprocSpec.model_validate({"groups": {"g1": "wing", "g2": stated}})
    text = str(caught.value)
    assert "'g2'" in text and "a group names ONE alias as a string" in text
    assert "valid list" not in text


def test_p0400_unsteady_surface_probes_declare_the_plots_export_with_normal_probes():
    """P0400-SURFACE-PLOTS (PFS-2105.002): the surface-probe history is in the plots export."""
    spec = PprocSpec.model_validate(
        {
            "probes": [NORMAL_PROBES],
            "surface_probes": [SURFACE_PROBE],
            "exports": {"plots": False},
        }
    )
    assert "{name}_plots.txt" in spec.outputs(True)


def test_p0400_probe_frame_written_empty_is_the_hub_frame():
    """P0400-PROBE-FRAME (PFS-2095.005): frame = "" means what the omitted key means."""
    assert ProbesSpec(frame="").frame == ProbesSpec().frame == ""
    assert ProbesSpec(frame="  ").frame == ""


def test_p0400_classify_outputs_does_not_fall_through_to_a_shorter_suffix():
    """P0400-CLASSIFY-DUPLICATE (PFS-2105.001): a second _cp.txt does not claim the loads kind."""
    assert classify_outputs(["P_cp.txt", "P2_cp.txt", "P.txt"])["loads"] == "P.txt"
    assert "loads" not in classify_outputs(["{name}_cp.txt", "{name}_wing_cp.txt"])


def test_p0400_vtk_variables_accept_every_build_and_any_case():
    """P0400-VTK-VARIABLES (PFS-2135.064): 26.125 tokens and lower case are the declared names."""
    spec = PprocSpec(vtk_variables=["C_H", "cp_reference"])
    assert spec.vtk_variables == ["C_H", "CP_REFERENCE"]
    with pytest.raises(ValidationError, match="unknown variable"):
        PprocSpec(vtk_variables=["NOT_A_VARIABLE"])
    with pytest.raises(ValidationError, match="distinct"):
        PprocSpec(vtk_variables=["CP", "cp"])


def test_p0400_surface_probe_parameter_accepts_lowercase():
    """P0400-SURFACE-TOKEN (PFS-2135.064): surface properties use the emitter's enum spelling."""
    assert (
        SurfaceProbeSpec(name="cp", parameter="cp_free", point_m=(0, 0, 0)).parameter == "CP_FREE"
    )


def test_p0400_vtk_variables_are_refused_naming_the_target_build(tmp_path):
    """P0400-VTK-BUILD (PFS-2135.064): a union token is checked when the target is known."""
    case = _with_pproc(
        steady_case(), _wb_geometry(tmp_path), pproc=PprocSpec(vtk_variables=["C_H"])
    )
    case.outputs = ["P.txt", "P.vtk"]
    with pytest.raises(CampaignConfigError, match="C_H.*26.124"):
        build_script(case, Script("26.124"))
    script = Script("26.125")
    build_script(case, script)
    assert "C_H" in script.render()
