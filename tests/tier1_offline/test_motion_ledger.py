"""Offline contract tests; synthetic timing is not native motion evidence."""

import math

import pytest

from pyflightstream.script import Script, helpers


def placed_script():
    script = Script("26.124")
    script.emit("NEW_SIMULATION")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.declare_existing(boundaries={"Blade": 1})
    hub = helpers.coordinate_frame(
        script,
        name="Hub",
        origin=(4.5, 0, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
    )
    moving = helpers.coordinate_frame(
        script,
        name="Moving",
        origin=(4.5, 0.2, 0),
        x_axis=(1, 0, 0),
        y_axis=(0, 1, 0),
    )
    return script, hub, moving


def test_explicit_fixed_frame_has_named_reference_basis():
    script, _, moving = placed_script()
    record = script.frame_motions[moving]
    assert record["state"] == "known"
    assert record["origin_native"] == [4.5, 0.2, 0]
    assert record["x_axis"] == [1, 0, 0]
    assert record["trajectory"]["kind"] == "fixed"


def test_late_attachment_keeps_center_axis_but_not_invented_timing():
    script, hub, moving = placed_script()
    helpers.rotary_motion(
        script,
        frame=hub,
        axis="X",
        rpm=-800,
        boundaries=[1],
        moving_frames=[moving],
    )
    helpers.unsteady_solver(script, time_iterations=6, delta_time=0.00625)
    record = script.frame_motions[moving]
    assert record["state"] == "unknown"
    assert "not measured" in record["reason"]
    assert record["trajectory"]["center_native"] == [4.5, 0, 0]
    assert record["trajectory"]["axis_reference"] == [1, 0, 0]
    assert record["trajectory"]["omega_rad_s"] is None
    assert record["attached_boundaries"] == [1]
    assert script.frame_motions[hub]["trajectory"]["kind"] == "fixed"


def test_raw_motion_never_leaves_a_local_frame_known_fixed():
    script, _, moving = placed_script()
    script.raw("SET_MOTION_MOVING_FRAMES 1 -1")
    assert script.frame_motions[moving]["state"] == "unknown"
    assert "raw" in script.frame_motions[moving]["reason"]
    assert script.frame_motions[1]["state"] == "known"


def test_all_frame_attachment_is_explicitly_unknown():
    script, hub, moving = placed_script()
    helpers.rotary_motion(script, frame=hub, axis="X", rpm=800, moving_frames="all")
    record = script.frame_motions[moving]
    assert record["state"] == "unknown"
    assert "all-frame" in record["reason"]


def test_snapshot_is_detached_from_internal_state():
    script, _, moving = placed_script()
    record = script.frame_motions
    record[moving]["origin_native"][0] = 999
    assert script.frame_motions[moving]["origin_native"][0] == 4.5


def test_exact_solver_identity_is_required_for_synthetic_timing(monkeypatch):
    from pyflightstream.script import motion

    digest = "a" * 64
    monkeypatch.setitem(
        motion._ROTARY_PROOFS,
        ("26.124", "METER", digest),
        {
            "fs_build": "synthetic",
            "signed_rpm_factor": 1,
            "step_time_origin": 1,
            "evidence": {"kind": "synthetic unit-test fixture only"},
        },
    )
    script, hub, moving = placed_script()
    helpers.rotary_motion(
        script,
        frame=hub,
        axis="X",
        rpm=-800,
        boundaries=[1],
        moving_frames=[moving],
    )
    helpers.unsteady_solver(script, time_iterations=6, delta_time=0.00625)
    assert script.frame_motions[moving]["state"] == "unknown"
    script.bind_native_solver_identity(executable_sha256=digest, build="other")
    assert script.frame_motions[moving]["state"] == "unknown"
    script.bind_native_solver_identity(executable_sha256=digest, build="synthetic")
    record = script.frame_motions[moving]
    assert record["state"] == "known"
    assert record["trajectory"]["omega_rad_s"] == pytest.approx(-800 * math.pi / 30)
    assert record["trajectory"]["step_time_origin"] == 1


def test_saved_timing_resolution_keeps_original_and_refuses_other_executable(monkeypatch):
    from pyflightstream.script import motion

    digest = "b" * 64
    monkeypatch.setitem(
        motion._ROTARY_PROOFS,
        ("26.124", "METER", digest),
        {
            "fs_build": "synthetic",
            "signed_rpm_factor": -1,
            "step_time_origin": 0,
            "evidence": {"kind": "synthetic unit-test fixture only"},
        },
    )
    script, hub, moving = placed_script()
    helpers.rotary_motion(
        script,
        frame=hub,
        axis="X",
        rpm=-800,
        boundaries=[1],
        moving_frames=[moving],
    )
    helpers.unsteady_solver(script, time_iterations=6, delta_time=0.00625)
    original = script.frame_motions[moving]
    wrong = motion.resolve_frame_motion(
        original, solver_identity={"fs_exe_sha256": "c" * 64, "fs_build": "synthetic"}
    )
    assert wrong["state"] == "unknown"
    resolved = motion.resolve_frame_motion(
        original, solver_identity={"fs_exe_sha256": digest, "fs_build": "synthetic"}
    )
    assert original["state"] == "unknown"
    assert original["trajectory"]["omega_rad_s"] is None
    assert resolved["state"] == "known"
    assert resolved["trajectory"]["omega_rad_s"] == pytest.approx(800 * math.pi / 30)
    assert resolved["proof"]["timing"]["fs_exe_sha256"] == digest
    delayed = {**original, "trajectory": {**original["trajectory"], "start_time_s": 1.0}}
    assert (
        motion.resolve_frame_motion(
            delayed, solver_identity={"fs_exe_sha256": digest, "fs_build": "synthetic"}
        )["state"]
        == "unknown"
    )


def test_zero_angle_turn_preserves_complete_placement():
    script, hub, moving = placed_script()
    before = script.frame_motions[moving]
    script.emit(
        "ROTATE_COORDINATE_SYSTEM",
        frame=moving,
        rotation_frame=hub,
        rotation_axis="X",
        angle=0.0,
    )
    after = script.frame_motions[moving]
    assert after["origin_native"] == before["origin_native"]
    assert after["x_axis"] == before["x_axis"]
    assert after["y_axis"] == before["y_axis"]
    assert after["z_axis"] == before["z_axis"]
    assert after["state"] == "known"


def test_measured_timing_is_bound_to_executable_build_and_unit():
    from pyflightstream.script.motion import resolve_frame_motion

    script, hub, moving = placed_script()
    helpers.rotary_motion(script, frame=hub, axis="X", rpm=-800, moving_frames=[moving])
    helpers.unsteady_solver(script, time_iterations=6, delta_time=0.00625)
    original = script.frame_motions[moving]
    identity = {
        "fs_exe_sha256": "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65",
        "fs_build": "8172026",
    }
    resolved = resolve_frame_motion(original, solver_identity=identity)
    assert resolved["state"] == "known"
    assert resolved["trajectory"]["step_time_origin"] == 0
    assert resolved["trajectory"]["omega_rad_s"] == pytest.approx(-800 * math.pi / 30)
    assert original["state"] == "unknown"
    millimeter = {**original, "length_unit": "MILLIMETER"}
    resolved_mm = resolve_frame_motion(millimeter, solver_identity=identity)
    assert resolved_mm["state"] == "known"
    assert resolved_mm["trajectory"]["step_time_origin"] == 0
    assert resolved_mm["trajectory"]["omega_rad_s"] == pytest.approx(-800 * math.pi / 30)
    unmeasured = {**original, "length_unit": "INCH"}
    assert resolve_frame_motion(unmeasured, solver_identity=identity)["state"] == "unknown"
    delayed = {**original, "trajectory": {**original["trajectory"], "start_time_s": 1}}
    assert resolve_frame_motion(delayed, solver_identity=identity)["state"] == "unknown"
    other = {**identity, "fs_build": "other"}
    assert resolve_frame_motion(original, solver_identity=other)["state"] == "unknown"
