# GEOVERSE_HEADER_BEGIN
# file_version: "1.0.6"
# file_role: geometry-setup-control-regressions
# last_modified_at: "2026-09-27T21:32:22.011Z"
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.cases, pyflightstream.script]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: "Use the canonical campaign sims collection in the workspace reference test."
# revision_source: git
# GEOVERSE_HEADER_END
"""Typed geometry controls; emitted settings alone do not prove native mesh repair."""

import pytest

from pyflightstream.cases import MeshImport, ReferenceData, SolverSettings, workflows
from pyflightstream.script import Script
from tests.tier1_offline.test_cad_import import _case


@pytest.mark.parametrize("unit,factor", [("METER", 1), ("MILLIMETER", 1000)])
@pytest.mark.parametrize("route", ["cad", "mesh", "saved"])
def test_geometry_controls_precede_detection_and_dimensional_frames(tmp_path, unit, factor, route):
    case = _case(tmp_path).model_copy(
        update={
            "reference": ReferenceData(
                area=2.0,
                length=3.0,
                moment_point_m=(0.25, -0.1, 0.02),
            )
        }
    )
    if route == "mesh":
        case = case.model_copy(
            update={
                "geometry": str(tmp_path / "wing.obj"),
                "mesh_import": MeshImport(units="METER"),
            }
        )
    elif route == "saved":
        path = tmp_path / "wing.fsm"
        path.write_text("$GLOBAL_START$\n1.0\n5\n$GLOBAL_END$\n")
        case = case.model_copy(
            update={"geometry": str(path), "mesh_import": None, "raw_mesh_conditions": None}
        )
    case = case.model_copy(
        update={
            "solver": SolverSettings(
                simulation_length_unit=unit,
                vertex_merge_tolerance_m=0.0002,
                geometric_edge_bluntness_angle_deg=123.0,
            )
        }
    )
    script = Script("26.124")
    workflows._open_geometry(case, script)
    frame = workflows._moment_frame(case, script)
    text = script.render()
    unit_line = f"SET_SIMULATION_LENGTH_UNITS {unit}"
    assert text.count(unit_line) == 1
    assert f"SET_VERTEX_MERGE_TOLERANCE {0.0002 * factor:g}" in text
    assert "SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE 123" in text
    assert "SET_TRAILING_EDGE_BLUNTNESS_ANGLE" not in text
    assert text.index(unit_line) < text.index("CREATE_NEW_COORDINATE_SYSTEM")
    if route != "saved":
        assert text.index("SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE") < text.index(
            "AUTO_DETECT_TRAILING_EDGES"
        )
    else:
        assert text.index("OPEN") < text.index("DISABLE") < text.index(unit_line)
    assert script.frame_placements[frame].origin == pytest.approx(
        tuple(value * factor for value in case.reference.moment_point_m)
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"simulation_length_unit": "OTHER"},
        {"simulation_length_unit": "CENTIMETER"},
        {"vertex_merge_tolerance_m": -0.1},
        {"vertex_merge_tolerance_m": float("nan")},
        {"geometric_edge_bluntness_angle_deg": 44.9},
        {"geometric_edge_bluntness_angle_deg": 179.1},
    ],
)
def test_geometry_settings_refuse_unmeasured_units_and_invalid_bounds(settings):
    with pytest.raises(ValueError):
        SolverSettings(**settings)


def test_unstated_geometry_controls_preserve_existing_cad_script(tmp_path):
    script = Script("26.124")
    workflows._open_geometry(_case(tmp_path), script)
    text = script.render()
    assert text.count("SET_SIMULATION_LENGTH_UNITS METER") == 1
    assert "SET_VERTEX_MERGE_TOLERANCE" not in text
    assert "SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE" not in text


def test_geometric_bluntness_does_not_silently_use_legacy_command(tmp_path):
    case = _case(tmp_path).model_copy(
        update={
            "solver": SolverSettings(
                geometric_edge_bluntness_angle_deg=90,
            )
        }
    )
    with pytest.raises(Exception, match="SET_GEOMETRIC_EDGE_BLUNTNESS_ANGLE"):
        workflows._open_geometry(case, Script("26.120"))


@pytest.mark.parametrize("unit,factor", [("METER", 1), ("MILLIMETER", 1000)])
def test_runtime_speeds_are_si_but_authored_reference_dimensions_remain_native(
    tmp_path, unit, factor
):
    case = _case(tmp_path).model_copy(
        update={
            "reference": ReferenceData(
                area=2.0,
                length=3.0,
                moment_point_m=(0.25, -0.1, 0.02),
            )
        }
    )
    case = case.model_copy(
        update={
            "solver": SolverSettings(simulation_length_unit=unit, reference_velocity_m_per_s=47.5),
            "variables": {**case.variables, "VELOCITY": "30"},
        }
    )
    script = Script("26.124")
    workflows._open_geometry(case, script)
    workflows._settings(case, script)
    lines = script.render().splitlines()
    emitted = {
        line.split()[0]: float(line.split()[1])
        for line in lines
        if line.startswith(
            (
                "SOLVER_SET_VELOCITY ",
                "SOLVER_SET_REF_VELOCITY ",
                "SOLVER_SET_REF_LENGTH ",
                "SOLVER_SET_REF_AREA ",
            )
        )
    }
    assert emitted["SOLVER_SET_VELOCITY"] == pytest.approx(30 * factor)
    assert emitted["SOLVER_SET_REF_VELOCITY"] == pytest.approx(47.5 * factor)
    assert emitted["SOLVER_SET_REF_LENGTH"] == pytest.approx(case.reference.length)
    assert emitted["SOLVER_SET_REF_AREA"] == pytest.approx(case.reference.area)


@pytest.mark.parametrize("unit,factor", [("METER", 1), ("MILLIMETER", 1000)])
def test_workspace_reference_si_is_explicit_and_converts_at_effective_unit(tmp_path, unit, factor):
    from tests.tier1_offline.test_matrix_run import _resolve_the_fixture, make_library

    resolved = _resolve_the_fixture(make_library(tmp_path))
    case = resolved.campaign.sims[0]
    assert case.reference.normalization_units == "SI"
    area, length = case.reference.area, case.reference.length
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    workflows._settings(case, script)
    lines = script.render().splitlines()
    emitted = {
        line.split()[0]: float(line.split()[1])
        for line in lines
        if line.startswith(("SOLVER_SET_REF_LENGTH ", "SOLVER_SET_REF_AREA "))
    }
    assert emitted["SOLVER_SET_REF_LENGTH"] == pytest.approx(length * factor)
    assert emitted["SOLVER_SET_REF_AREA"] == pytest.approx(area * factor**2)
    assert (case.reference.area, case.reference.length) == (area, length)
