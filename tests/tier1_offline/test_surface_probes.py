"""Surface-probe declarations; native sampling semantics require separate evidence."""

import pytest
from pydantic import ValidationError

from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._probes import _pproc_probes
from pyflightstream.script import Script
from tests.tier1_offline.test_g05_volume_section import _steady
from tests.tier1_offline.test_workflows import unsteady_case


def _request(**overrides):
    return {
        "name": "upper_cp",
        "parameter": "CP_FREE",
        "frame": "REFERENCE",
        "point_m": [0.25, 0.1, 0.02],
        **overrides,
    }


@pytest.mark.parametrize(
    "parameter",
    [
        "CP_FREE",
        "CP_REF",
        "BL_MOMENTUM_THICKNESS",
        "BL_DISPLACEMENT_THICKNESS",
        "BL_TOTAL_THICKNESS",
        "BL_SHAPE_FACTOR",
        "BL_SKIN_FRICTION",
        "BL_TRANSITION_MARKER",
    ],
)
def test_surface_probe_retains_exact_native_parameter(parameter):
    request = PprocSpec.model_validate({"surface_probes": [_request(parameter=parameter)]})
    assert request.surface_probes[0].parameter == parameter
    assert request.probes == []
    assert request.model_dump()["surface_probes"][0]["point_m"] == (0.25, 0.1, 0.02)


@pytest.mark.parametrize(
    "change,match",
    [
        ({"parameter": "CP"}, "surface probe parameter"),
        ({"name": "upper cp"}, "surface probe name"),
        ({"point_m": [float("nan"), 0, 0]}, "finite"),
    ],
)
def test_surface_probe_refuses_ambiguous_or_invalid_requests(change, match):
    with pytest.raises(ValidationError, match=match):
        PprocSpec.model_validate({"surface_probes": [_request(**change)]})


def test_surface_probe_names_are_unique():
    with pytest.raises(ValidationError, match="surface probe names.*unique"):
        PprocSpec.model_validate({"surface_probes": [_request(), _request()]})


@pytest.mark.parametrize("unit,factor", [("METER", 1), ("MILLIMETER", 1000)])
def test_surface_probe_declares_coordinate_contract_and_separate_identity(unit, factor):
    pproc = PprocSpec.model_validate({"surface_probes": [_request()]})
    case = unsteady_case().model_copy(update={"pproc": pproc})
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    _pproc_probes(case, script, {"REFERENCE": 1}, unsteady=True, analysis=False)
    row = next(
        line
        for line in script.render().splitlines()
        if line.startswith("NEW_UNSTEADY_SOLVER_SURFACE_PROBE ")
    )
    words = row.split()
    assert words[1:4] == ["SURFACE_upper_cp", "CP_FREE", "1"]
    assert list(map(float, words[4:])) == pytest.approx([v * factor for v in (0.25, 0.1, 0.02)])
    assert script.probe_field_layout == []
    assert script.probe_points == []
    assert script.surface_probe_layout[0]["plot_name"] == "SURFACE_upper_cp"
    assert script.surface_probe_layout[0]["frame_index"] == 1
    assert script.surface_probe_layout[0]["parameter"] == "CP_FREE"
    assert script.surface_probe_layout[0]["point_m"] == [0.25, 0.1, 0.02]
    assert script.surface_probe_layout[0]["coordinate_contract"] == "named-frame-native-length"


def test_surface_probes_build_before_initialization_and_require_history_export():
    pproc = PprocSpec.model_validate({"surface_probes": [_request()], "exports": {"plots": False}})
    outputs = [name.replace("{name}", "P") for name in pproc.outputs(unsteady=True)]
    assert "P_plots.txt" in outputs
    case = unsteady_case().model_copy(update={"pproc": pproc, "outputs": outputs})
    script = Script("26.124")
    build_script(case, script)
    text = script.render()
    assert (
        text.index("UNSTEADY_SOLVER_DELETE_ALL_PLOTS")
        < text.index("NEW_UNSTEADY_SOLVER_SURFACE_PROBE")
        < text.index("INITIALIZE_SOLVER")
    )
    assert "UNSTEADY_SOLVER_EXPORT_PLOTS" in text
    assert len(script.surface_probe_layout) == 1


def test_surface_probes_refuse_steady_instead_of_silently_omitting_history():
    pproc = PprocSpec.model_validate({"surface_probes": [_request()]})
    with pytest.raises(CampaignConfigError, match="surface_probes.*unsteady"):
        build_script(_steady(pproc), Script("26.124"))


def test_surface_plot_csv_preserves_native_values_and_column_identity(tmp_path):
    from pyflightstream.post.products import read_csv_table, write_plots_table
    from tests.tier1_offline.test_post_products import PLOTS_HEADER

    text = (
        PLOTS_HEADER + "Time-step,SURFACE_upper_cp,SURFACE_upper_theta,CL_all\n"
        "1,-0.125,0.001,0.5\n2,-0.25,0.002,0.75\n" + "-" * 60 + "\n     Force Units: Coefficients\n"
    )
    target = tmp_path / "surface.csv"
    write_plots_table(target, text, pol="9001")
    columns, rows = read_csv_table(target)
    assert columns == ("POL", "Time-step", "SURFACE_upper_cp", "SURFACE_upper_theta", "CL_all")
    values = [
        [float(row[index]) for index in ("SURFACE_upper_cp", "SURFACE_upper_theta", "CL_all")]
        for row in rows
    ]
    assert values == [
        [-0.125, 0.001, 2.0],
        [-0.25, 0.002, 3.0],
    ]


@pytest.mark.parametrize(
    "parameter",
    [
        "BL_MOMENTUM_THICKNESS",
        "BL_DISPLACEMENT_THICKNESS",
        "BL_TOTAL_THICKNESS",
        "BL_SHAPE_FACTOR",
        "BL_SKIN_FRICTION",
        "BL_TRANSITION_MARKER",
    ],
)
def test_surface_bl_probe_refuses_measured_cp_fallback(parameter):
    request = PprocSpec.model_validate({"surface_probes": [_request(parameter=parameter)]})
    case = unsteady_case().model_copy(update={"pproc": request})
    script = Script("26.124")
    with pytest.raises(CampaignConfigError, match=parameter + ".*CP_FREE.*RPT-083"):
        _pproc_probes(case, script, {"REFERENCE": 1}, unsteady=True, analysis=False)
    assert "NEW_UNSTEADY_SOLVER_SURFACE_PROBE" not in script.render()
    assert script.surface_probe_layout == []


def test_public_native_surface_fixture_preserves_observable_and_unit_limits():
    import json
    from pathlib import Path

    path = Path(__file__).parent / "data/native_surface_probe_samples.json"
    fixture = json.loads(path.read_text())
    assert fixture["solver"]["build"] == 8172026
    assert fixture["source_geometry"]["sha256"] == (
        "c6e719b921fe4396c89870b513c0e84f714a089699ee5562775d465d376ad599"
    )
    series = {row["name"]: row for row in fixture["series"]}
    assert len(series) == 56 and fixture["steps"] == [1, 2, 3, 4, 5, 6]
    for row in series.values():
        assert len(row["meter"]) == 6
        assert row["meter"] == row["millimeter"]
    for cell in (193, 217):
        for frame in ("REFERENCE", "G61_FIXED_Z90"):
            prefix = f"SURFACE_NATIVE_{cell}_{frame}_"
            cp = series[prefix + "CP_FREE"]["meter"]
            assert any(value < 0 for value in cp)
            assert cp != series[prefix + "CP_REF"]["meter"]
            assert cp != series[prefix + "VX"]["meter"]
            for parameter in (
                "BL_MOMENTUM_THICKNESS",
                "BL_DISPLACEMENT_THICKNESS",
                "BL_TOTAL_THICKNESS",
                "BL_SHAPE_FACTOR",
                "BL_SKIN_FRICTION",
                "BL_TRANSITION_MARKER",
            ):
                assert series[prefix + parameter]["meter"] == cp
