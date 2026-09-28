"""Offline dimensional behavior; these tests do not claim native solver operation."""

from types import SimpleNamespace

import pytest

from pyflightstream._fsm import MeshReadError, saved_length_unit
from pyflightstream.cases import (
    FrameSpec,
    ProbeLine,
    ProbeRectangle,
    ProbesSpec,
    ReferenceData,
    RotorBlock,
    workflows,
)
from pyflightstream.script import Script, helpers


def _case():
    return SimpleNamespace(
        sim_id="units",
        geometry=None,
        variables={},
        rotors={},
        motions=[],
        pproc_id="p001",
        reference=ReferenceData(
            area=1.0,
            length=1.0,
            moment_point_m=(0.25, -0.1, 0.02),
            rotor_position_m=(0.5, 0.2, -0.03),
        ),
    )


@pytest.mark.parametrize("unit,factor", [("METER", 1), ("MILLIMETER", 1000)])
@pytest.mark.parametrize(
    "which,point",
    [
        ("_moment_frame", (0.25, -0.1, 0.02)),
        ("_rotor_frame", (0.5, 0.2, -0.03)),
    ],
)
def test_reference_origins_are_metres(unit, factor, which, point):
    # GOAL033:capability_ids:items:G34
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    index = getattr(workflows, which)(_case(), script)
    assert script.frame_placements[index].origin == pytest.approx(tuple(v * factor for v in point))


@pytest.mark.parametrize("unsteady", [False, True])
def test_probe_metres_become_native_coordinates_once(unsteady):
    case = _case()
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    frame = workflows._moment_frame(case, script)
    probes = ProbesSpec(
        frame="MRP",
        parameters=["VELOCITY"],
        points=2,
        lines=[ProbeLine(start=(0.1, 0.0, 0.0), end=(0.2, 0.0, 0.0))],
    )
    workflows._emit_one_probe_table(case, script, {"MRP": frame}, probes, 0, unsteady=unsteady)
    assert script.probe_points[0][1:4] == pytest.approx((100.0, 0.0, 0.0))
    placed = workflows._in_the_reference_frame(case, script, frame, "MRP", [100.0, 0.0, 0.0])
    assert placed == pytest.approx((350.0, -100.0, 20.0))


@pytest.mark.parametrize("head,expected", [("1.0\n5", "METER"), ("1.0E-03\n2", "MILLIMETER")])
def test_measured_saved_unit_heads(tmp_path, head, expected):
    # GOAL033:capability_ids:items:G32
    path = tmp_path / "measured.fsm"
    path.write_text("$GLOBAL_START$\n" + head + "\n$GLOBAL_END$\n")
    assert saved_length_unit(path) == expected


@pytest.mark.parametrize("head", ["0.01\n3", "0.001\n5", "nan\n2"])
def test_unmeasured_or_inconsistent_heads_stay_refused(tmp_path, head):
    path = tmp_path / "unknown.fsm"
    path.write_text("$GLOBAL_START$\n" + head + "\n$GLOBAL_END$\n")
    with pytest.raises(MeshReadError, match="global block"):
        saved_length_unit(path)


@pytest.mark.parametrize("unit,value", [("METER", 0.25), ("MILLIMETER", 250.0)])
def test_origin_commands_keep_the_ledger_in_native_units(unit, value):
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    frame = helpers.coordinate_frame(
        script,
        name="FRAME",
        origin=(0.0, 0.0, 0.0),
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
    )
    script.emit("SET_COORDINATE_SYSTEM_ORIGIN", frame=frame, x=value, y=0, z=0, units=unit)
    assert script.frame_placements[frame].origin == pytest.approx((250.0, 0.0, 0.0))


def test_saved_unit_metadata_also_controls_later_origin_commands(tmp_path):
    geometry = tmp_path / "millimetres.fsm"
    geometry.write_text("$GLOBAL_START$\n0.001\n2\n$GLOBAL_END$\n")
    case = _case()
    case.geometry = geometry
    script = Script("26.124")
    frame = workflows._moment_frame(case, script)
    assert script.simulation_length_unit == "MILLIMETER"
    assert script.frame_placements[frame].origin == pytest.approx((250.0, -100.0, 20.0))
    script.emit("SET_COORDINATE_SYSTEM_ORIGIN", frame=frame, x=0.35, y=0, z=0, units="METER")
    assert script.frame_placements[frame].origin == pytest.approx((350.0, 0.0, 0.0))


def test_declared_rotor_and_custom_frame_origins_use_metres():
    case = _case()
    case.rotors = {
        "PROP": RotorBlock(
            alias="PROP",
            axis="Z",
            diameter_m=2.0,
            families_blades=["BLADE"],
            x_m=0.4,
            y_m=-0.3,
            z_m=0.2,
        )
    }
    case.frames = [FrameSpec(name="CUSTOM", origin=(0.1, 0.2, 0.3))]
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    rotor = workflows._rotor_frame(case, script)
    frame = workflows._setup_frames(case, script)["CUSTOM"]
    assert script.frame_placements[rotor].origin == pytest.approx((400.0, -300.0, 200.0))
    assert script.frame_placements[frame].origin == pytest.approx((100.0, 200.0, 300.0))


def test_legacy_rotor_origin_variable_retains_its_native_unit_contract():
    case = _case()
    case.variables = {"ROTOR_ORIGIN": "2,3,4"}
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    frame = workflows._rotor_frame(case, script)
    assert script.frame_placements[frame].origin == (2.0, 3.0, 4.0)


def test_new_simulation_drops_the_previous_saved_unit_provenance():
    script = Script("26.124")
    script.record_opened_length_unit("MILLIMETER")
    script.emit("NEW_SIMULATION")
    assert script.simulation_length_unit is None


@pytest.mark.parametrize("unit,factor", [("METER", 1), ("MILLIMETER", 1000)])
@pytest.mark.parametrize("shape", ["line", "rectangle"])
def test_fluid_plot_vertices_are_si_but_recorded_positions_remain_native(unit, factor, shape):
    case = _case()
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    frame = workflows._moment_frame(case, script)
    geometry = (
        {"lines": [ProbeLine(start=(0.1, 0.2, 0.3), end=(0.2, 0.2, 0.3))]}
        if shape == "line"
        else {
            "rectangles": [
                ProbeRectangle(
                    origin=(0.1, 0.2, 0.3),
                    along_u=(0.2, 0.2, 0.3),
                    along_v=(0.1, 0.3, 0.3),
                    points_u=2,
                    points_v=2,
                )
            ]
        }
    )
    probes = ProbesSpec(frame="MRP", parameters=["VX"], points=2, **geometry)
    workflows._emit_one_probe_table(case, script, {"MRP": frame}, probes, 0, unsteady=True)
    emitted = [line for line in script.render().splitlines() if line.startswith("VERTEX ")]
    assert tuple(map(float, emitted[0].split()[1:])) == pytest.approx((0.1, 0.2, 0.3))
    assert script.probe_points[0][1:4] == pytest.approx((0.1 * factor, 0.2 * factor, 0.3 * factor))
