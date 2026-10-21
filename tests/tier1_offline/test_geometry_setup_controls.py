"""Typed geometry controls; emitted settings alone do not prove native mesh repair."""

import pytest

from pyflightstream.cases import MeshImport, ReferenceData, SolverSettings
from pyflightstream.cases.workflows import _frames, _geometry, _solver_settings
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
    _geometry._open_geometry(case, script)
    frame = _frames._moment_frame(case, script)
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
    _geometry._open_geometry(_case(tmp_path), script)
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
        _geometry._open_geometry(case, Script("26.120"))


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
    _geometry._open_geometry(case, script)
    _solver_settings._settings(case, script)
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
    _solver_settings._settings(case, script)
    lines = script.render().splitlines()
    emitted = {
        line.split()[0]: float(line.split()[1])
        for line in lines
        if line.startswith(("SOLVER_SET_REF_LENGTH ", "SOLVER_SET_REF_AREA "))
    }
    assert emitted["SOLVER_SET_REF_LENGTH"] == pytest.approx(length * factor)
    assert emitted["SOLVER_SET_REF_AREA"] == pytest.approx(area * factor**2)
    assert (case.reference.area, case.reference.length) == (area, length)


# --- F5-0304: the geometry instruction refuses what it cannot build ----------


def _mesh_instruction(**extra):
    from pyflightstream.cases._geometry_instruction import GeometryInstruction, MeshSource

    fields = {
        "name": "wing",
        "outputs": ("fsm",),
        "boundaries": ("Wing",),
        "kind": "mesh",
        "mesh": MeshSource(file="wing.obj", units="METER"),
    }
    fields.update(extra)
    return GeometryInstruction(**fields)


def test_f5_0304_instruction_refuses_no_source_and_two_sources():
    """F-1296: a missing or doubled source table is a refusal, not a later assertion."""
    from pyflightstream.cases._geometry_instruction import CadSource

    with pytest.raises(ValueError, match="exactly one source table"):
        _mesh_instruction(mesh=None)
    with pytest.raises(ValueError, match="exactly one source table"):
        _mesh_instruction(cad=CadSource(file="body.igs"))


def test_f5_0304_sweep_angle_too_large_for_a_tag_is_a_refusal():
    """F-1295: a finite angle whose tag overflows raises a validation error."""
    from pyflightstream.cases._geometry_instruction import GeometrySweep

    with pytest.raises(ValueError, match="too large"):
        GeometrySweep(control_surface="AIL", angle_deg=(1e308,))


def test_f5_0304_geometry_values_must_be_finite():
    """F-039, F-040, F-041: infinite scale factors, coordinates and placements are refused."""
    from pyflightstream.cases._geometry_instruction import (
        CadBodyOperation,
        CreateBody,
        CreateSection,
    )

    inf = float("inf")
    with pytest.raises(ValueError, match="finite"):
        CadBodyOperation(op="scale", body=1, factor=inf)
    with pytest.raises(ValueError, match="finite"):
        CreateBody(shape="sphere", center_m=(inf, 0.0, 0.0), radius_m=1.0)
    with pytest.raises(ValueError, match="finite"):
        CreateSection(file="s.txt", units="METER", chord_m=inf)
    with pytest.raises(ValueError, match="finite"):
        CreateSection(file="s.txt", units="METER", chord_m=1.0, twist_deg=float("nan"))


@pytest.mark.requirement("FR-1096")
def test_f5_0304_fr1096_the_instruction_validates_boundaries_units_and_keys_before_building():
    """FR-1096: ordered boundaries, output units and source keys are refused at the model."""
    from pyflightstream._lengths import UNIT_THAT_NAMES_NO_LENGTH
    from pyflightstream.cases._geometry_instruction import (
        GeometryOperation,
        MeshSource,
    )

    assert _mesh_instruction(boundaries=("Wing", "Tail")).boundaries == ("Wing", "Tail")
    with pytest.raises(ValueError, match="empty"):
        _mesh_instruction(boundaries=())
    with pytest.raises(ValueError, match="twice"):
        _mesh_instruction(boundaries=("Wing", "Wing"))
    with pytest.raises(ValueError, match="whitespace"):
        _mesh_instruction(boundaries=("Wing Left",))
    with pytest.raises(ValueError, match="names no length"):
        _mesh_instruction(mesh=MeshSource(file="wing.obj", units=UNIT_THAT_NAMES_NO_LENGTH))
    with pytest.raises(ValueError, match="outputs"):
        _mesh_instruction(outputs=("fsm", "fsm"))
    with pytest.raises(ValueError, match="does not read"):
        GeometryOperation(op="scale", factors=(1.0, 1.0, 1.0), surface="Wing", plane="XY")
    # The boundaries are ORDERED: operations that leave a different order are refused.
    renamed = GeometryOperation(op="rename", surface="Wing", to="Blade")
    with pytest.raises(ValueError, match="names the surface"):
        _mesh_instruction(operations=(renamed,))
