"""Opt-in replay of hash-bound synthetic native FSI evidence, without a solver."""

import hashlib
import json
import os
from pathlib import Path

import pytest

EXECUTABLE_SHA256 = "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65"
RECEIPTS = {
    "GOAL033_FSI_NATIVE_RECEIPT": (
        "0c502422a1fe0fcf21c2883983bd3204b3ecaf66efbebb979dfb8ead65664ab9"
    ),
    "GOAL033_FSI_STEADY_RECEIPT": (
        "3654d0b61a9b1588d202ea961a1c5b8b0b35e1aa0db68e045f756861a930d5ff"
    ),
}


def _case(name):
    key = (
        "GOAL033_FSI_STEADY_RECEIPT" if name == "steady-observed" else "GOAL033_FSI_NATIVE_RECEIPT"
    )
    location = os.environ.get(key)
    if not location:
        pytest.skip(f"set {key} to the recorded native execution receipt")
    raw = Path(location).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECEIPTS[key]
    receipt = json.loads(raw)
    assert receipt["exe_sha256"] == EXECUTABLE_SHA256
    return next(case for case in receipt["cases"] if case["name"] == name)


def _output(name, filename):
    case = _case(name)
    record = next(output for output in case["outputs"] if output["name"] == filename)
    assert Path(filename).name == filename
    raw = (Path(case["working_directory"]) / filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    assert len(raw) == record["bytes"]
    return raw.decode("utf-8")


def _block(name, filename="before.fsm"):
    text = _output(name, filename)
    assert text.count("$AEROELASTIC_START$") == text.count("$AEROELASTIC_END$") == 1
    return (
        text.split("$AEROELASTIC_START$", 1)[1]
        .split("$AEROELASTIC_END$", 1)[0]
        .strip()
        .splitlines()
    )


def _numbers(line):
    return [float(value) for value in line.split(",") if value.strip()]


def _fresh_calls(name):
    calls = json.loads(_output(name, "calls.json"))
    assert [call["call"] for call in calls] == [1, 2]
    previous = 0
    for call in calls:
        assert previous < call["post_mtime_ns"] <= call["time_ns"]
        filename = f"callback-{call['call']:04d}-loads.txt"
        raw = _output(name, filename).encode("utf-8")
        assert hashlib.sha256(raw).hexdigest() == call["post_sha256"]
        assert len(raw) == call["post_bytes"] > 0
        assert "Aerodynamic loads" in raw.decode("utf-8")
        previous = call["time_ns"]
    return calls


def test_steady_execute_consumes_two_fresh_coupling_handoffs():
    # GOAL033:setup_bc:operational_commands:EXECUTE_AEROELASTIC_ANALYSIS
    assert len(_fresh_calls("steady-observed")) == 2
    log = _output("steady-observed", "native.log")
    assert "Aeroelastic solver residual for FSI iteration-1" in log
    assert "Aeroelastic solver residual for FSI iteration-2" in log
    assert "Aeroelastic solver residual for FSI iteration-3" not in log
    case = _case("steady-observed")
    assert case["termination_reason"] == "completed-callback-observation"
    assert case["returncode"] == 1  # Planned cleanup, not normal solver exit or convergence.


def test_assigned_surface_has_a_native_vertex_mapping():
    # GOAL033:setup_bc:operational_commands:ASSIGN_AEROELASTIC_SURFACES
    before = _block("steady-observed")
    after = _block("steady-observed", "coupling-state.fsm")
    assert _numbers(before[0])[1] == 0
    assert _numbers(after[0])[1] == 410
    assert _numbers(before[140]) == [1]
    assert _numbers(after[550]) == [1]


def test_assigned_frame_two_is_preserved_for_coupling():
    # GOAL033:setup_bc:operational_commands:ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS
    before = _block("steady-observed")
    after = _block("steady-observed", "coupling-state.fsm")
    assert _numbers(before[141])[0] == _numbers(after[551])[0] == 2
    assert _numbers(after[0])[2] == 1  # One assigned coordinate system, not reference index one.


def test_imported_structural_nodes_preserve_order_and_accept_displacements():
    # GOAL033:setup_bc:operational_commands:IMPORT_AEROELASTIC_STRUCTURAL_NODES
    before = _block("steady-observed")
    after = _block("steady-observed", "coupling-state.fsm")
    assert _numbers(before[4])[3] == _numbers(after[4])[3] == 27
    maximum = 0.0
    for index in range(27):
        original = _numbers(before[5 + 5 * index])
        displaced = _numbers(after[5 + 5 * index])
        expected = 0.01 * (abs(original[1]) / 4) ** 2
        assert displaced[:2] == original[:2]
        assert displaced[2] - original[2] == pytest.approx(expected, abs=1e-14)
        maximum = max(maximum, expected)
    assert maximum == 0.01


def test_deleting_structural_nodes_removes_all_twenty_seven():
    # GOAL033:setup_bc:operational_commands:DELETE_AEROELASTIC_STRUCTURAL_NODES
    assert _numbers(_block("delete-nodes")[4])[3] == 27
    assert _numbers(_block("delete-nodes", "final.fsm")[4])[3] == 0


def test_structural_callback_runs_in_the_configured_working_directory():
    # GOAL033:setup_bc:operational_commands:SET_AEROELASTIC_WORKING_DIRECTORY
    case = _case("steady-observed")
    configured = Path(_block("steady-observed")[2])
    assert configured == Path(case["working_directory"])
    for call in _fresh_calls("steady-observed"):
        assert Path(call["cwd"]) == configured


def test_postprocessing_happens_before_each_structural_callback():
    # GOAL033:setup_bc:operational_commands:SET_AEROELASTIC_POST_PROCESSING_SCRIPT
    block = _block("steady-observed")
    assert Path(block[-2].strip()).name == "post.txt"
    first, second = _fresh_calls("steady-observed")
    assert second["post_mtime_ns"] > first["time_ns"]
    assert first["post_sha256"] != second["post_sha256"]


def test_structural_execution_command_writes_the_expected_displacement_file():
    # GOAL033:setup_bc:operational_commands:SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND
    command = _block("steady-observed")[3]
    assert "pythonw.exe" in command and "callback.py" in command
    assert len(_fresh_calls("steady-observed")) == 2
    rows = [_numbers(line) for line in _output("steady-observed", "FSIDisp.txt").splitlines()]
    assert len(rows) == 27
    assert all(row[:2] == [0, 0] and len(row) == 3 for row in rows)
    assert max(row[2] for row in rows) == 0.01


def test_coupling_iteration_count_is_applied_in_steady_mode():
    # GOAL033:setup_bc:operational_commands:SET_AEROELASTIC_ITERATIONS
    assert _numbers(_block("steady-observed")[0])[3] == 2
    assert len(_fresh_calls("steady-observed")) == 2
    assert _numbers(_block("unsteady-on")[0])[3] == 1


def test_unsteady_enable_runs_callbacks_and_disable_does_not():
    # GOAL033:setup_bc:operational_commands:SET_AEROELASTIC_COUPLING_IN_UNSTEADY
    assert _block("unsteady-on")[-3].strip() == "T"
    assert _block("unsteady-off")[-3].strip() == "F"
    assert len(_fresh_calls("unsteady-on")) == 2
    disabled = _case("unsteady-off")
    assert disabled["returncode"] == 0
    assert "calls.json" not in {item["name"] for item in disabled["outputs"]}
    assert not (Path(disabled["working_directory"]) / "calls.json").exists()
    assert _numbers(_block("unsteady-off", "final.fsm")[0])[1] == 0


def test_immediate_close_does_not_prove_steady_coupling_completion():
    case = _case("steady")
    assert case["returncode"] == 0
    assert "calls.json" not in {item["name"] for item in case["outputs"]}
    assert not (Path(case["working_directory"]) / "calls.json").exists()
    before = _block("steady")
    after = _block("steady", "final.fsm")
    assert [before[5 + i * 5] for i in range(27)] == [after[5 + i * 5] for i in range(27)]
