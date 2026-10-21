import pytest


def envelope(points, operations=(), motions=()):
    from pyflightstream.cases.field_coverage import spatial_envelope

    return spatial_envelope(points, operations, motions)


def operation(name, **arguments):
    return {
        "command": name,
        "arguments": arguments,
        "length_unit": "METER",
        "frame": {"origin": [0, 0, 0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "boundary_count": 1,
    }


def test_translated_body_coverage_uses_emitted_placement():
    # GOAL033:scope:G50
    op = operation("TRANSLATE_SURFACE_IN_FRAME", surface=1, x=0, y=20, z=-3, units="METER")
    bounds, notes = envelope([(0, -1, -1), (1, 1, 1)], [op])
    assert bounds == pytest.approx((19, 21, -4, -2))


def test_partial_translation_keeps_a_conservative_union():
    op = operation("TRANSLATE_SURFACE_IN_FRAME", surface=1, x=0, y=20, z=0, units="METER")
    op["boundary_count"] = 2
    bounds, notes = envelope([(0, -1, -1), (1, 1, 1)], [op])
    assert bounds == pytest.approx((-1, 21, -1, 1))
    assert any("conservative" in note for note in notes)


def test_rotation_envelope_cannot_report_initial_flat_z_extent():
    op = operation("ROTATE_SURFACE", frame=1, axis="X", angle=90, surfaces=-1)
    bounds, notes = envelope([(0, -2, 0), (1, 2, 0)], [op])
    assert bounds[2:] == pytest.approx((-2, 2))


def test_full_rotor_envelope_does_not_need_step_timing():
    motion = {
        "length_unit": "METER",
        "motion_index": 1,
        "attached_boundaries": [1],
        "trajectory": {
            "kind": "constant_rotation",
            "center_native": [4.5, 0, 0],
            "axis_reference": [1, 0, 0],
            "emitted_rpm": -800,
        },
    }
    bounds, notes = envelope([(4.5, -2, 0), (4.5, 2, 0)], motions=[motion])
    assert bounds == pytest.approx((-2, 2, -2, 2))


def test_mm_frame_origin_and_translation_convert_once():
    op = operation("TRANSLATE_SURFACE_IN_FRAME", surface=1, x=0, y=20000, z=0, units="MILLIMETER")
    op["length_unit"] = "MILLIMETER"
    bounds, notes = envelope([(0, -1, -1), (1, 1, 1)], [op])
    assert bounds == pytest.approx((19, 21, -1, 1))


def test_unknown_transform_refuses_a_coverage_claim():
    with pytest.raises(ValueError, match="unsupported"):
        envelope([(0, -1, -1), (1, 1, 1)], [operation("MIRROR_SURFACE")])


#: Q0 CX-5: what the motion ledger records for a frame an all-frame rotary
#: attachment moves: no motion index, and a trajectory of unknown kind.
UNKNOWN_MOTION = {
    "length_unit": "METER",
    "motion_index": None,
    "state": "unknown",
    "reason": "A motion has implicit or all-frame attachments.",
    "trajectory": {"kind": "unknown", "center_native": None, "axis_reference": None},
}


def test_unknown_motion_refuses_a_coverage_claim():
    # Q0 CX-5: `motion_index=None` read as "no motion", so an unknown X-axis
    # rotation of a body spanning y=+-2, z=0 kept a zero Z extent.
    with pytest.raises(ValueError, match="unknown moving-frame trajectory"):
        envelope([(0, -2, 0), (1, 2, 0)], motions=[UNKNOWN_MOTION])


def test_unknown_motion_reaches_the_workflow_coverage_check(monkeypatch):
    # Q0 CX-5: the workflow returned before the envelope whenever no frame
    # carried a motion index, so the unknown motion was never looked at.
    from pyflightstream.cases.workflows import _freestream
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import steady_case

    fixed = {"motion_index": None, "trajectory": {"kind": "fixed"}}
    monkeypatch.setattr(
        Script, "frame_motions", property(lambda self: {1: fixed, 2: UNKNOWN_MOTION})
    )
    monkeypatch.setattr(_freestream, "_body_vertices_m", lambda case: ((0, -2, 0), (1, 2, 0)))
    script = Script("26.124")
    script.custom_field_extent_m = (-3, 3, -1, 1)
    with pytest.warns(UserWarning, match="coverage is not checked"):
        _freestream._finish_custom_field_coverage(steady_case(), script)
    assert script.custom_field_coverage is not None
    assert script.custom_field_coverage["state"] == "unknown"


def test_p0430_f400_a_raw_command_on_a_stationary_row_invalidates_the_coverage(monkeypatch):
    # F-400: the stationary early return used to skip the raw-command check.
    from pyflightstream.cases.workflows import _freestream
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import steady_case

    script = Script("26.124")
    script.custom_field_extent_m = (-3, 3, -1, 1)
    script.raw_flag = True
    monkeypatch.setattr(_freestream, "_body_vertices_m", lambda case: ((0, -2, 0), (1, 2, 0)))
    with pytest.warns(UserWarning, match="coverage is not checked"):
        _freestream._finish_custom_field_coverage(steady_case(), script)
    assert script.custom_field_coverage["state"] == "unknown"
    assert "raw commands" in script.custom_field_coverage["reason"]


def test_actual_emitted_translation_reaches_final_workflow_coverage(monkeypatch):
    # GOAL033:capability_ids:items:G50
    from pyflightstream.cases.workflows import _freestream
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import steady_case

    script = Script("26.124")
    script.declare_existing(boundaries={"Wing": 1})
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit(
        "TRANSLATE_SURFACE_IN_FRAME",
        surface=1,
        frame=1,
        x=0,
        y=20,
        z=0,
        units="METER",
        split_vertices="DISABLE",
    )
    script.custom_field_extent_m = (-2, 2, -2, 2)
    monkeypatch.setattr(_freestream, "_body_vertices_m", lambda case: ((0, -1, -1), (1, 1, 1)))
    with pytest.warns(UserWarning, match="conservative transformed-body"):
        _freestream._finish_custom_field_coverage(steady_case(), script)
    record = script.custom_field_coverage
    assert record["state"] == "envelope-exceeds-grid"
    assert record["body_envelope_yz_m"] == pytest.approx((19, 21, -1, 1))
    assert script.surface_operations[0]["arguments"]["y"] == 20


def test_open_resets_predecessor_custom_field_coverage():
    from pyflightstream.script import Script

    script = Script("26.124")
    script.custom_field_extent_m = (-2, 2, -2, 2)
    script.custom_field_coverage = {"state": "covered"}
    script.emit("NEW_SIMULATION")
    assert script.custom_field_extent_m is None
    assert script.custom_field_coverage is None


def test_f5_0102_f019_a_far_point_still_sweeps_its_radius():
    """F-019: a point 1e9 m along the axis and 1 m off it sweeps a circle of radius 1."""
    motion = {
        "length_unit": "METER",
        "motion_index": 1,
        "attached_boundaries": [1],
        "trajectory": {
            "kind": "constant_rotation",
            "center_native": [0, 0, 0],
            "axis_reference": [1, 0, 0],
            "emitted_rpm": 100,
        },
    }
    bounds, _ = envelope([(1e9, 1.0, 0.0)], motions=[motion])
    assert bounds == pytest.approx((-1, 1, -1, 1))


def test_f5_0102_f024_the_far_field_lattice_sits_on_the_rotor_origin_the_row_states():
    """F-024: a row stating ROTOR_ORIGIN moves the hub the lattice is laid on."""
    from pyflightstream.cases._farfield_spec import LatticeShape
    from pyflightstream.cases.workflows._farfield import _rotor_placement
    from tests.tier1_offline.test_workflows import FIXTURE_ROTOR, rotor_case

    shape = LatticeShape(rotor=FIXTURE_ROTOR.alias)
    block_hub = _rotor_placement(rotor_case(), shape)[2]
    assert list(block_hub) == pytest.approx(
        [FIXTURE_ROTOR.x_m, FIXTURE_ROTOR.y_m, FIXTURE_ROTOR.z_m]
    )
    stated = rotor_case(ROTOR_ORIGIN="1.0,2.0,3.0")
    assert list(_rotor_placement(stated, shape)[2]) == pytest.approx([1.0, 2.0, 3.0])
    # the stated origin is in the simulation unit: 1000 of them to the metre
    assert list(_rotor_placement(stated, shape, 1000.0)[2]) == pytest.approx([0.001, 0.002, 0.003])


def test_f5_0102_f025_the_plane_extent_follows_the_emitted_translation(tmp_path):
    """F-025: a body translated downstream by an emitted operation reaches further."""
    from types import SimpleNamespace

    import numpy as np

    from pyflightstream.cases.workflows._farfield import _extent_m

    mesh = tmp_path / "body.obj"
    mesh.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\nf 1 2 4\nf 1 3 4\nf 2 3 4\n")
    case = SimpleNamespace(geometry=str(mesh))
    direction = np.array([1.0, 0.0, 0.0])
    assert _extent_m(case, direction, 1.0, SimpleNamespace(surface_operations=[])) == 1.0
    move = {
        "command": "TRANSLATE_SURFACE_IN_FRAME",
        "arguments": {"surface": -1, "x": 5.0, "y": 0.0, "z": 0.0, "units": "METER"},
        "length_unit": "METER",
        "frame": {"origin": [0, 0, 0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
        "boundary_count": 1,
    }
    placed = SimpleNamespace(surface_operations=[move])
    assert _extent_m(case, direction, 1.0, placed) == pytest.approx(6.0)
    unknown = SimpleNamespace(surface_operations=[{**move, "command": "SOMETHING_ELSE"}])
    assert _extent_m(case, direction, 1.0, unknown) is None
