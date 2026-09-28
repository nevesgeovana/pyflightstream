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
    from pyflightstream.cases import workflows
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import steady_case

    fixed = {"motion_index": None, "trajectory": {"kind": "fixed"}}
    monkeypatch.setattr(
        Script, "frame_motions", property(lambda self: {1: fixed, 2: UNKNOWN_MOTION})
    )
    monkeypatch.setattr(workflows, "_body_vertices_m", lambda case: ((0, -2, 0), (1, 2, 0)))
    script = Script("26.124")
    script.custom_field_extent_m = (-3, 3, -1, 1)
    with pytest.warns(UserWarning, match="coverage is not checked"):
        workflows._finish_custom_field_coverage(steady_case(), script)
    assert script.custom_field_coverage is not None
    assert script.custom_field_coverage["state"] == "unknown"


def test_actual_emitted_translation_reaches_final_workflow_coverage(monkeypatch):
    # GOAL033:capability_ids:items:G50
    from pyflightstream.cases import workflows
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
    monkeypatch.setattr(workflows, "_body_vertices_m", lambda case: ((0, -1, -1), (1, 1, 1)))
    with pytest.warns(UserWarning, match="conservative transformed-body"):
        workflows._finish_custom_field_coverage(steady_case(), script)
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
