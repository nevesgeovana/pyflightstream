"""P0400-CW-CLOCK: the clock of an unsteady row, as its threshold, counter and rescue read it.

0.40.0 items PFS-2089.006 (the renderers take the case's build, never a
literal), PFS-2104.031 and PFS-2104.039 (the wall-clock rescue asks the
end-of-run block's two questions about the log) and PFS-2104.003 (the
threshold and the counter take the clock CLOCK_MOTION names) and PFS-2095.041
(a threshold on any steady run type is refused as one).
"""

from __future__ import annotations

import inspect

import pytest

from pyflightstream.cases import CampaignConfigError, ReferenceData, RotorBlock, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    WorkflowConventions,
    action_export_lines,
    unsteady_counter_steps,
    unsteady_export_threshold,
    walltime_clock_program,
    walltime_stop_text,
)
from pyflightstream.cases.workflows._export_first_step import refuse_threshold_on_a_steady_run
from pyflightstream.cases.workflows._freestream import rotor_row_stepping


def _unsteady(outputs: list[str], **variables: str) -> tuple[SimCase, WorkflowConventions]:
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=outputs,
        point={"alpha": 0.0},
        variables={
            "WORKFLOW": "unsteady",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.001",
            "TIME_ITERATIONS": "100",
            "LAST_ITERS_AVG": "10",
            "WALLTIME": "4h",
            **variables,
        },
    )
    return case, WorkflowConventions(outputs=tuple(outputs))


@pytest.mark.parametrize(
    "renderer",
    [
        action_export_lines,
        unsteady_export_threshold,
        walltime_clock_program,
        walltime_stop_text,
    ],
)
def test_p0400_cw_clock_the_renderers_take_the_build_and_never_default_it(renderer):
    """P0400-CW-CLOCK (PFS-2089.006): `version` is required; 26.120 documents no action."""
    requirement = "P0400-CW-CLOCK"
    version = inspect.signature(renderer).parameters["version"]
    assert version.default is inspect.Parameter.empty, requirement
    assert version.kind is inspect.Parameter.KEYWORD_ONLY


def test_p0400_cw_clock_the_rescue_writes_no_log_where_the_machine_turns_it_off():
    """P0400-CW-CLOCK (PFS-2104.031, PFS-2104.039): EXPORT_LOG false reaches the rescue too.

    The run layer sets EXPORT_LOG false on the point case of a machine that
    aborts at the command, and the rescue still wrote it there.
    """
    requirement = "P0400-CW-CLOCK"
    outputs = ["loads_a.txt", "loads_a_log.txt"]
    case, conventions = _unsteady(outputs, EXPORT_LOG="false")
    text = walltime_stop_text(case, conventions, version="26.124")
    assert "EXPORT_LOG" not in text, (requirement, text)
    assert "loads_a.txt" in text
    on, conventions = _unsteady(outputs)
    assert "EXPORT_LOG\nloads_a_log.txt" in walltime_stop_text(on, conventions, version="26.124")


def test_p0400_cw_clock_the_rescue_writes_a_log_output_log_by_position():
    """P0400-CW-CLOCK (PFS-2104.031): a LOG_OUTPUT log not named *_log.txt was left out."""
    requirement = "P0400-CW-CLOCK"
    outputs = ["loads_a.txt", "solver_run.out"]
    case, conventions = _unsteady(outputs, LOG_OUTPUT="2")
    lines = walltime_stop_text(case, conventions, version="26.124").splitlines()
    assert lines[lines.index("EXPORT_LOG") + 1] == "solver_run.out", (requirement, lines)
    off, conventions = _unsteady(outputs, LOG_OUTPUT="2", EXPORT_LOG="false")
    assert "EXPORT_LOG" not in walltime_stop_text(off, conventions, version="26.124")


LIFTER = RotorBlock(
    alias="LIFT_L1",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="Z",
    diameter_m=1.2,
    families_general=["LH_L1"],
    families_blades=[f"LIFT_L1_B{number}" for number in range(1, 5)],
)
PUSHER = RotorBlock(
    alias="PUSHER",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="Z",
    diameter_m=1.8,
    families_general=["PH"],
    families_blades=[f"PUSHER_B{number}" for number in range(1, 4)],
)


def _two_speeds(**variables: str) -> SimCase:
    return SimCase(
        sim_id="9201",
        aircraft="WORK",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        rotors={"LIFT_L1": LIFTER, "PUSHER": PUSHER},
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "DELTA_THETA": "10",
            "REVOLUTIONS": "2",
            "LAST_REVS_AVG": "1",
            "CLOCK_MOTION": "PUSHER",
            **variables,
        },
        motions=[
            {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2200"},
            {"MOVING_BC_ALIAS": "PUSHER", "RPM": "900"},
        ],
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
        point={"alpha": 0.0},
    )


def test_p0400_cw_clock_the_threshold_and_counter_take_the_clock_motion():
    """P0400-CW-CLOCK (PFS-2104.003): CLOCK_MOTION names the slower rotor, and it owns the clock.

    The threshold took the fastest rotor's clock, so its delta_time_s was the
    lifter's ten degrees while the script's SET_SOLVER_UNSTEADY was the pusher's.
    """
    requirement = "P0400-CW-CLOCK"
    case = _two_speeds(EXPORT_UNSTEADY_AFTER_ITER="1")
    builder = rotor_row_stepping(case)
    assert builder.delta_time_s == pytest.approx(10.0 / (6.0 * 900.0)), requirement
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold is not None
    assert threshold.delta_time_s == builder.delta_time_s
    assert threshold.step_deg == pytest.approx(10.0)
    assert threshold.time_iterations == builder.time_iterations == 72
    assert unsteady_counter_steps(case) == builder.time_iterations


@pytest.mark.parametrize(
    "key", ["EXPORT_UNSTEADY_AFTER_ITER", "EXPORT_UNSTEADY_LAST_ITER", "EXPORT_UNSTEADY_AFTER_REV"]
)
def test_p0400_cw_clock_a_threshold_on_the_quasi_steady_rotor_is_refused_as_steady(key):
    """P0400-CW-CLOCK (PFS-2095.041): qsteady_rotor has no time loop, and the refusal says so.

    It fell through to refusals about an unsteady clock, or about a run type
    that "turns nothing", which a quasi-steady rotor does not.
    """
    requirement = "P0400-CW-CLOCK"
    case, _ = _unsteady(["loads_a.txt"], **{key: "1"})
    with pytest.raises(
        CampaignConfigError, match="names the qsteady_rotor run type, which has no"
    ) as refusal:
        refuse_threshold_on_a_steady_run(case, key, "qsteady_rotor")
    assert str(refusal.value), requirement
