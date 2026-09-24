"""OPS-2011.01.03 (RPT-063, FR-42): the emitted body-rate sense, scored against recorded probes.

A row states a body rate in flight-mechanics signs. What the package emits for
it is a free-stream line; what the solver does with that line was measured on
a licensed build and recorded, with the line each point emitted, in two
tracked evidence files: RPT-052 (pitch) and RPT-060 (roll and yaw). This test
builds the line the package emits TODAY for +40 deg/s, looks that exact line
up in the recorded probes, and asserts the solver's response has the sign
flight mechanics gives the rate:

- roll: positive p lowers the right wing, so the meshed LEFT wing (y < 0,
  group g02 of RPT-060, "the wing (the meshed y < 0 half)") loses lift;
- yaw: positive r moves the nose right, so the left wing advances and gains lift;
- pitch: positive q is nose up, so the airframe gains lift (CL_q > 0).

Only the sign is used, never the magnitude: the yaw response is not symmetric
(RPT-060 records +0.0089 against -0.0139 and does not explain it).

ROLL AND YAW ARE EXPECTED TO FAIL until the per-axis sign fix of this release
(G13): RPT-060 measured them emitted reversed. They carry strict xfail marks,
so the fix, when it lands, must remove them (an unexpected pass is a failure).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from tests.tier1_offline.test_goal024_freestream_rotation import (
    _free_stream,
    _rate_matrix,
    _script,
)

ROOT = Path(__file__).resolve().parents[2]
RPT052 = ROOT / "reports" / "probes" / "RPT-052_2026-09-15_evidence.yaml"
RPT060 = ROOT / "reports" / "probes" / "RPT-060_2026-09-23_evidence.yaml"
RATE = 40.0


def _key(line: str) -> tuple[str, float]:
    """(axis, rev/min) of a recorded `SET_FREESTREAM ROTATION <frame> <axis> <rpm>` line."""
    words = line.split()
    return words[3], round(float(words[4]), 9)


def _recorded_responses() -> dict[tuple[str, float], float]:
    """Each recorded free-stream rotation, mapped to the lift increment it produced."""
    responses: dict[tuple[str, float], float] = {}
    roll_yaw = yaml.safe_load(RPT060.read_text(encoding="utf-8"))
    for point in roll_yaw["points"]:
        if not point["free_stream"].startswith("SET_FREESTREAM ROTATION"):
            continue
        sim = point["run_id"].split("/")[1].removeprefix("sim_")
        # g02 is the wing, the meshed y < 0 half: the LEFT wing.
        responses[_key(point["free_stream"])] = float(
            roll_yaw["increments_over_4201"][sim]["g02"]["CLB"]
        )
    pitch = yaml.safe_load(RPT052.read_text(encoding="utf-8"))
    airframe = {
        entry["table"].split("-")[0].removeprefix("P"): float(entry["CLB"])
        for entry in pitch["coefficients"]
        if entry["table"].endswith("_g01.csv")
    }
    for sim, line in pitch["free_stream_line_per_simulation"].items():
        number = sim.removeprefix("sim_")
        if line.startswith("SET_FREESTREAM ROTATION"):
            responses[_key(line)] = airframe[number] - airframe["4101"]
    return responses


RESPONSES = _recorded_responses()
REVERSED = pytest.mark.xfail(strict=True, reason="RPT-060: roll and yaw emitted reversed until G13")


def test_the_probe_map_holds_both_senses_of_roll_and_yaw_and_one_of_pitch():
    """The lookup cannot silently shrink: every line the tests below need is recorded."""
    rpm = round(RATE * 60.0 / 360.0, 9)
    for key in (("X", rpm), ("X", -rpm), ("Z", rpm), ("Z", -rpm), ("Y", rpm)):
        assert key in RESPONSES, f"no recorded probe for the free-stream rotation {key}"


@pytest.mark.parametrize(
    "rate_key,axis,expected_sign",
    [
        pytest.param("roll_rate", "X", -1.0, id="roll", marks=REVERSED),
        pytest.param("pitch_rate", "Y", +1.0, id="pitch"),
        pytest.param("yaw_rate", "Z", +1.0, id="yaw", marks=REVERSED),
    ],
)
def test_the_emitted_rotation_is_the_one_the_probe_recorded_producing_that_rate(
    tmp_path, rate_key, axis, expected_sign
):
    workspace, matrix = _rate_matrix(
        tmp_path, condition=f"MACH:0.2, REmi:2.3, ALPHA:sweep, {rate_key}:{RATE}"
    )
    words = _free_stream(_script(workspace, matrix))
    assert words[:2] == ["SET_FREESTREAM", "ROTATION"], words
    assert words[3] == axis, words
    key = (words[3], round(float(words[4]), 9))
    assert key in RESPONSES, (
        f"the package emits {' '.join(words)}, a free-stream line no probe recorded; "
        "re-measure on a licensed build before changing the sign"
    )
    response = RESPONSES[key]
    assert math.copysign(1.0, response) == expected_sign, (
        f"+{RATE} deg/s of {rate_key} emits {' '.join(words[3:])}, and the solver answered a "
        f"lift increment of {response:+.5f}: the flow of the opposite rate"
    )
