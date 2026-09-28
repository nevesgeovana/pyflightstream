"""Opt-in replay of recorded native observations; no solver or private payload is bundled."""

import hashlib
import json
import os
from pathlib import Path

import pytest

RECEIPT_SHA256 = "328411cacd8f2ff346248b9339cda5540f2ec0912d76ce568aaed6c1a91df1e5"
EXECUTABLE_SHA256 = "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65"


def _artifact(case_name, suffix):
    location = os.environ.get("GOAL033_SETUP_NATIVE_RECEIPT")
    if not location:
        pytest.skip("set GOAL033_SETUP_NATIVE_RECEIPT to the recorded native execution receipt")
    raw = Path(location).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECEIPT_SHA256
    receipt = json.loads(raw)
    assert receipt["exe_sha256"] == EXECUTABLE_SHA256
    case = next(item for item in receipt["cases"] if item["name"] == case_name)
    output = next(item for item in case["outputs"] if item["name"] == case_name + suffix)
    data = (Path(case["working_directory"]) / output["name"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == output["sha256"]
    return data.decode("utf-8")


def _block(text, section):
    return (
        text.split(f"${section}_START$", 1)[1].split(f"${section}_END$", 1)[0].strip().splitlines()
    )


@pytest.mark.parametrize(
    "setting,section,index,before,after",
    [
        ("laminar_separation", "SOLVER", 41, "F", "T"),
        ("additional_wake_relaxation", "WAKE", 7, "F", "T"),
        ("wake_on_wake_induction", "WAKE", 9, "F", "T"),
        ("mesh_induced_wake_velocity", "SOLVER", 40, "F", "T"),
        ("unsteady_pressure_and_kutta", "SOLVER", 15, "F", "T"),
        ("wake_numerical_relaxation", "WAKE", 11, ".250", ".750"),
        ("wake_decay_constant_per_m", "WAKE", 12, ".150", ".450"),
    ],
)
def test_native_setter_changes_its_saved_field_only(setting, section, index, before, after):
    # GOAL033:setup_bc:operational_commands:LAMINAR_SEPARATION
    # GOAL033:setup_bc:operational_commands:ADDITIONAL_WAKE_RELAXATION_ITERATION
    # GOAL033:setup_bc:operational_commands:SET_WAKE_ON_WAKE_INDUCTION
    # GOAL033:setup_bc:operational_commands:SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY
    # GOAL033:setup_bc:operational_commands:SOLVER_UNSTEADY_PRESSURE_AND_KUTTA
    # GOAL033:setup_bc:operational_commands:SET_WAKE_NUMERICAL_RELAXATION
    # GOAL033:setup_bc:operational_commands:SET_WAKE_DECAY_CONSTANT
    first = _block(_artifact(f"wake-state-{setting}-0", ".fsm"), section)
    second = _block(_artifact(f"wake-state-{setting}-1", ".fsm"), section)
    assert len(first) == len(second)
    changes = [
        (i, a.strip(), b.strip())
        for i, (a, b) in enumerate(zip(first, second, strict=True))
        if a != b
    ]
    assert changes == [(index, before, after)]


def test_native_reference_reset_tracks_later_freestream():
    # GOAL033:setup_bc:operational_commands:DISABLE_SOLVER_REF_VELOCITY
    held = _block(_artifact("ref-held", ".fsm"), "SOLVER")
    reset = _block(_artifact("ref-reset", ".fsm"), "SOLVER")
    follow = _block(_artifact("ref-reset-follow", ".fsm"), "SOLVER")
    assert float(held[29]) == pytest.approx(47.513)
    assert held[33].strip() == "T"
    assert float(reset[29]) == float(reset[21]) == 30
    assert reset[33].strip() == "F"
    assert float(follow[29]) == float(follow[21]) == 40
    assert follow[33].strip() == "F"


def test_native_mach_and_velocity_routes_agree_within_measured_two_ppm():
    # GOAL033:setup_bc:operational_commands:SOLVER_SET_MACH_NUMBER
    velocity = _block(_artifact("resolved-velocity-route", ".fsm"), "SOLVER")
    mach = _block(_artifact("resolved-mach-route", ".fsm"), "SOLVER")
    expected = 44.23821844339157
    assert float(velocity[21]) == pytest.approx(expected, rel=1e-13)
    assert float(mach[21]) == pytest.approx(expected, rel=2e-6)
    assert float(mach[21]) != float(velocity[21])  # Preserve the measured rounding discrepancy.
    assert float(mach[29]) == float(velocity[29])  # Reference normalization is unchanged.
    assert _artifact("resolved-mach-route", "-settings.txt") == _artifact(
        "resolved-velocity-route", "-settings.txt"
    )


def test_native_evidence_identifies_the_measured_build_in_exported_settings():
    # GOAL033:setup_bc:build_checks:26.124
    settings = _artifact("resolved-mach-route", "-settings.txt")
    assert "Flightstream version 26.1, build #8172026" in settings
    assert "Current solver iteration number:            0" in settings


def test_unobserved_rotor_blending_is_not_promoted_to_operational_evidence():
    assert _artifact("wake-state-rotor_induced_velocity_blending-0", ".fsm") == _artifact(
        "wake-state-rotor_induced_velocity_blending-1", ".fsm"
    )
