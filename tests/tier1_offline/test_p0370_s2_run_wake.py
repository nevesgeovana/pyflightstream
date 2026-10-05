"""Tier 1: the run length of an unsteady rotor row from a target wake length (FR-422).

A row of ``unsteady_rotor`` may state ``RUN_WAKE_LENGTH_R: L`` with one of
``DELTA_THETA`` or ``DELTA_TIME``; its ``TIME_ITERATIONS`` is then
``ceil(L R Omega / (V_ax dtheta))``, the conversion and the axial velocity rule
that size ``wake_termination_length``. Every reader of the clock reads the
resolved count: the script, the plan, the record, the export threshold and the
averaging window (FR-415 R6). No solver runs.

The hand figures: the rotor below has ``diameter_m`` 3.6576, so R = 1.8288 m; it
turns 1200 rev/min (Omega = 40 pi rad/s) at 30 m/s. At ``DELTA_THETA: 10`` a step
is pi / 18 rad, so Omega / dtheta = 720 per second and 36 steps make a turn; at
``DELTA_TIME: 0.0001`` Omega / dtheta = 1 / dt = 1e4 per second.
"""

from __future__ import annotations

import json
import math
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    FluidState,
    RotorBlock,
    SimCase,
    SolverSettings,
    SweepAxis,
)
from pyflightstream.cases.workflows import (
    WORKFLOW_KEY,
    build_script,
    reduction_windows,
    rotor_time_stepping,
    time_steps_of,
    unsteady_export_threshold,
    workflow_registry,
)
from pyflightstream.cases.workflows._freestream import wake_termination_of
from pyflightstream.run import CampaignErrors, PlanStatus
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import Script
from tests.support_helpers import rotor_row, rotor_workspace

KEY = "RUN_WAKE_LENGTH_R"
RADIUS_M = 3.6576 / 2.0

_ROTOR = RotorBlock(
    alias="ROTOR",
    x_m=0.1,
    y_m=0.2,
    z_m=0.3,
    axis="X",
    rpm_sign=1,
    diameter_m=3.6576,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _row(**overrides: str | None) -> SimCase:
    """A rotor row asking a wake of 4 radii at ten degrees a step, and no other run length."""
    variables: dict[str, str] = {
        WORKFLOW_KEY: "unsteady_rotor",
        "VELOCITY": "30.0",
        "RPM": "1200",
        "ROTOR_AXIS": "X",
        "BLADES": "4",
        "DELTA_THETA": "10",
        KEY: "4",
        "LAST_REVS_AVG": "0.25",
    }
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        rotors={_ROTOR.alias: _ROTOR},
    )


def _air(velocity: float) -> FluidState:
    return FluidState(
        velocity_m_per_s=velocity,
        density_kg_m3=1.225,
        pressure_pa=101325.0,
        temperature_k=288.15,
        viscosity_pa_s=1.789e-5,
        sonic_velocity_m_per_s=340.29,
        source="isa",
    )


def _at(velocity: str, **settings: object) -> SimCase:
    """The row at ``velocity`` in sea-level air, with these setup keys."""
    return _row(VELOCITY=velocity).model_copy(
        update={"fluid": _air(float(velocity)), "solver": SolverSettings(**settings)}
    )


def _hand(length: float, per_second: float, v_ax: float) -> int:
    """FR-422 by hand: n = ceil(L R Omega / (V_ax dtheta)), Omega / dtheta given per second."""
    return math.ceil(round(length * RADIUS_M * per_second / v_ax, 9))


def _built(case: SimCase) -> tuple[list[str], Script]:
    script = Script("26.124")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script.render().splitlines(), script


def _march(lines: list[str]) -> list[str]:
    """The SET_SOLVER_UNSTEADY block's argument lines."""
    start = lines.index("SET_SOLVER_UNSTEADY")
    return lines[start + 1 : start + 3]


# --- the step count ----------------------------------------------------------


@pytest.mark.parametrize(
    "step, per_second",
    [({"DELTA_THETA": "10"}, 720.0), ({"DELTA_THETA": None, "DELTA_TIME": "0.0001"}, 1e4)],
    ids=["DELTA_THETA", "DELTA_TIME"],
)
def test_p0370_s2_the_count_is_the_hand_value_and_the_script_marches_it(step, per_second):
    """P0370-S2-RUN-WAKE (FR-422): TIME_ITERATIONS = ceil(L R Omega / (V_ax dtheta)).

    4 * 1.8288 * 720 / 30 = 175.56, so 176 steps at ten degrees a step;
    4 * 1.8288 * 1e4 / 30 = 2438.4, so 2439 at 0.0001 s. Rounded UP, so the wake
    kept at V_ax is never shorter than L.
    """
    requirement = "FR-422"
    case = _row(**step)
    expected = _hand(4.0, per_second, 30.0)
    assert expected == {720.0: 176, 1e4: 2439}[per_second], expected
    stepping = rotor_time_stepping(case)
    assert stepping.time_iterations == expected, (requirement, stepping)
    assert time_steps_of(case) == expected, requirement
    lines, _ = _built(case)
    assert _march(lines)[0] == f"TIME_ITERATIONS {expected}", (requirement, _march(lines))


@pytest.mark.parametrize("length", ["4", "2.5", "7.3"])
def test_p0370_s2_the_count_equals_wake_termination_of_for_the_same_length(length):
    """P0370-S2-RUN-WAKE (FR-422): one function sizes both, so the run length of L radii is
    the wake termination of L radii, step for step, on the same clock."""
    requirement = "FR-422"
    case = _row(**{KEY: length}).model_copy(
        update={"solver": SolverSettings(wake_termination_length=float(length))}
    )
    stepping = rotor_time_stepping(case)
    termination = wake_termination_of(case, stepping)
    assert termination.steps == stepping.time_iterations, (requirement, termination, stepping)
    assert termination.run_steps == stepping.time_iterations, requirement
    assert stepping.time_iterations == _hand(float(length), 720.0, 30.0), requirement


def test_p0370_s2_a_stated_thrust_convects_the_run_length_at_zero_speed():
    """P0370-S2-RUN-WAKE (FR-422): the induced velocity source. At V_inf = 0 the setup's
    wake_termination_thrust_n gives V_ax = sqrt(T / (2 rho pi R^2)), the rule of FR-323."""
    requirement = "FR-422"
    v_i = math.sqrt(1000.0 / (2.0 * 1.225 * math.pi * RADIUS_M**2))
    stepping = rotor_time_stepping(_at("0.0", wake_termination_thrust_n=1000.0))
    assert stepping.time_iterations == _hand(4.0, 720.0, v_i), (requirement, stepping)
    assert stepping.run_wake is not None
    assert stepping.run_wake.rule == "induced_velocity", requirement
    assert stepping.run_wake.v_ax_m_s == pytest.approx(v_i), requirement


# --- the refusals ------------------------------------------------------------


@pytest.mark.parametrize("other", [{"TIME_ITERATIONS": "720"}, {"REVOLUTIONS": "3"}])
def test_p0370_s2_a_second_run_length_is_refused_naming_both(other):
    """P0370-S2-RUN-WAKE (FR-422 R1): the key beside TIME_ITERATIONS or REVOLUTIONS is
    refused, naming both keys and the remedy (remove one)."""
    requirement = "FR-422"
    with pytest.raises(CampaignConfigError) as refused:
        _built(_row(**other))
    message = str(refused.value)
    (name,) = other
    assert KEY in message and name in message, (requirement, message)
    assert "Remove" in message and "RPT-" not in message, (requirement, message)


@pytest.mark.parametrize(
    "step", [{"DELTA_TIME": "0.0001"}, {"DELTA_THETA": None}], ids=["both", "neither"]
)
def test_p0370_s2_both_steps_or_neither_is_refused_naming_the_two(step):
    """P0370-S2-RUN-WAKE (FR-422): the key needs exactly one of DELTA_THETA or DELTA_TIME."""
    requirement = "FR-422"
    with pytest.raises(CampaignConfigError) as refused:
        rotor_time_stepping(_row(**step))
    message = str(refused.value)
    assert "DELTA_THETA" in message and "DELTA_TIME" in message, (requirement, message)
    assert "one of the two" in message, (requirement, message)


@pytest.mark.parametrize("value", ["0", "-2"])
def test_p0370_s2_a_length_that_is_not_positive_is_refused_naming_the_key(value):
    """P0370-S2-RUN-WAKE (FR-422): a wake length is a positive number of rotor radii."""
    requirement = "FR-422"
    with pytest.raises(CampaignConfigError) as refused:
        rotor_time_stepping(_row(**{KEY: value}))
    message = str(refused.value)
    assert KEY in message and "positive" in message, (requirement, message)


def test_p0370_s2_zero_free_stream_without_a_thrust_is_refused_naming_the_remedy():
    """P0370-S2-RUN-WAKE (FR-422 R2): the free-stream source at zero speed. V_ax = 0 is no
    length; the refusal names both remedies, the thrust in the setup or REVOLUTIONS, and the
    revolution cap that bounds the wake termination is not offered (R5)."""
    requirement = "FR-422"
    with pytest.raises(CampaignConfigError) as refused:
        rotor_time_stepping(_at("0.0"))
    message = str(refused.value)
    assert "wake_termination_thrust_n" in message and "setup" in message, (requirement, message)
    assert "REVOLUTIONS" in message, (requirement, message)
    assert "revolutions_cap" not in message and "RPT-" not in message, (requirement, message)


def test_p0370_s2_a_thrust_with_no_fluid_density_is_refused_naming_the_remedy():
    """P0370-S2-RUN-WAKE (FR-422 R2): the induced-velocity source cannot be evaluated with no
    density; the refusal names the flight condition or REVOLUTIONS, not the revolution cap."""
    requirement = "FR-422"
    case = _at("0.0", wake_termination_thrust_n=1000.0).model_copy(update={"fluid": None})
    with pytest.raises(CampaignConfigError) as refused:
        rotor_time_stepping(case)
    message = str(refused.value)
    assert "flight condition" in message and "REVOLUTIONS" in message, (requirement, message)
    assert "revolutions_cap" not in message, (requirement, message)


def test_p0370_s2_a_rotor_with_no_known_radius_is_refused_naming_the_remedy():
    """P0370-S2-RUN-WAKE (FR-422): a length in radii needs the rotor's radius."""
    requirement = "FR-422"
    case = _row().model_copy(update={"rotors": {}})
    with pytest.raises(CampaignConfigError) as refused:
        rotor_time_stepping(case)
    message = str(refused.value)
    assert "diameter_m" in message and "REVOLUTIONS" in message, (requirement, message)


def test_p0370_s2_a_count_that_is_no_finite_number_is_refused_not_overflowed():
    """P0370-S2-RUN-WAKE (FR-422): a free stream so slow the quotient overflows is refused
    by name, never with an OverflowError."""
    requirement = "FR-422"
    with pytest.raises(CampaignConfigError) as refused:
        rotor_time_stepping(_row(VELOCITY="1e-310"))
    assert KEY in str(refused.value), (requirement, str(refused.value))


def test_p0370_s2_the_key_on_a_run_type_turning_nothing_is_refused_at_plan(tmp_path):
    """P0370-S2-RUN-WAKE (FR-422): the key is the rotor type's; an ``unsteady`` row stating it
    is refused at plan by the row-key guard, naming the run type that reads it."""
    requirement = "FR-422"
    workspace = rotor_workspace(tmp_path)
    matrix = rotor_row(tmp_path)
    text = matrix.read_text(encoding="utf-8").replace("unsteady_rotor |", "unsteady       |")
    for before, after in (
        ("RPM: 1200 / ROTOR_AXIS: X / ", ""),
        ("LAST_REVS_AVG: 0.25", "LAST_ITERS_AVG: 100 / RUN_WAKE_LENGTH_R: 4"),
    ):
        assert before in text, (before, text)
        text = text.replace(before, after)
    matrix.write_text(text, encoding="utf-8")
    plan = _plan(workspace, matrix)
    errors = " ".join(str(entry.error) for entry in plan.points)
    assert all(entry.status is PlanStatus.BLOCKED for entry in plan.points), (requirement, errors)
    assert KEY in errors and "unsteady_rotor" in errors, (requirement, errors)


# --- the plan and the record -------------------------------------------------


def _wake_workspace(tmp_path, extra: str = " / RUN_WAKE_LENGTH_R: 4"):
    """The rotor workspace with a rotor diameter of 1.2 m on its reference, and its row.

    At 30 m/s and 0.0001 s a step, 4 R = 4 * 0.6 / (30 * 1e-4) = 800 steps, and 60 /
    (1200 * 1e-4) = 500 steps make a turn, so 1.6 revolutions.
    """
    workspace = rotor_workspace(tmp_path)
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(
        "rotor_diameter_m = 1.2\n" + reference.read_text(encoding="utf-8"), encoding="utf-8"
    )
    matrix = rotor_row(tmp_path, sweep="0.0", extra=extra)
    if extra:
        text = matrix.read_text(encoding="utf-8")
        assert " / TIME_ITERATIONS: 720" in text
        matrix.write_text(text.replace(" / TIME_ITERATIONS: 720", "", 1), encoding="utf-8")
    return workspace, matrix


def _plan(workspace, matrix):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return plan_matrix(
            matrix, workspace, name="rotor", recipes={}, recipe_registry=workflow_registry()
        )


def test_p0370_s2_the_plan_prints_the_resolved_count_and_revolutions(tmp_path):
    """P0370-S2-RUN-WAKE (FR-422 R3): the plan prints the length, the steps, the revolutions
    and V_ax with its rule for the point, and plan.json carries them."""
    requirement = "FR-422"
    workspace, matrix = _wake_workspace(tmp_path)
    plan = _plan(workspace, matrix)
    (entry,) = plan.points
    assert entry.status is PlanStatus.READY, (requirement, entry.error)
    summary = plan.summary()
    line = f"{entry.run_id}: run length RUN_WAKE_LENGTH_R = 4 R: 800 steps, 1.6 revolution(s), "
    assert line + "V_ax 30 m/s (free_stream)" in summary, (requirement, summary)
    written = json.loads(
        (workspace.plan_dir(matrix.stem) / "plan.json").read_text(encoding="utf-8")
    )
    (point,) = written["points"]
    assert point["run_wake_length"]["time_iterations"] == 800, (requirement, point)
    assert point["run_wake_length"]["rule"] == "free_stream", (requirement, point)


def test_p0370_s2_a_row_without_the_key_plans_as_before_the_control(tmp_path):
    """P0370-S2-RUN-WAKE (FR-422 R4): no line, and plan.json carries no new key."""
    requirement = "FR-422"
    workspace, matrix = _wake_workspace(tmp_path, extra="")
    plan = _plan(workspace, matrix)
    assert "run length" not in plan.summary(), (requirement, plan.summary())
    written = json.loads(
        (workspace.plan_dir(matrix.stem) / "plan.json").read_text(encoding="utf-8")
    )
    assert all("run_wake_length" not in point for point in written["points"]), requirement


@pytest.mark.parametrize("other", ["TIME_ITERATIONS: 720", "REVOLUTIONS: 2"])
def test_p0370_s2_a_second_run_length_is_blocked_at_plan_naming_both(tmp_path, other):
    """P0370-S2-RUN-WAKE (FR-422 R1): at plan, through the matrix, the point is BLOCKED with
    the refusal naming both keys."""
    requirement = "FR-422"
    workspace, matrix = _wake_workspace(tmp_path, extra=f" / RUN_WAKE_LENGTH_R: 4 / {other}")
    plan = _plan(workspace, matrix)
    (entry,) = plan.points
    assert entry.status is PlanStatus.BLOCKED, requirement
    assert KEY in str(entry.error) and other.split(":")[0] in str(entry.error), entry.error


def test_p0370_s2_the_run_record_states_the_rule_the_velocity_and_the_count(tmp_path):
    """P0370-S2-RUN-WAKE (FR-422 R3): a point run through the workflow records the length,
    the rule, V_ax and the resulting time_iterations in the solver-flag snapshot. The stub
    solver writes nothing, so the point fails for its outputs; the snapshot is in the part
    of the record every point carries."""
    from tests.tier1_offline.test_matrix_run import StubSolver, converged

    requirement = "FR-422"
    workspace, matrix = _wake_workspace(tmp_path)
    with warnings.catch_warnings(), pytest.raises(CampaignErrors):
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            matrix,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=StubSolver("pass"),
        )
    (record,) = workspace.read_manifest()
    assert record.solver_setup is not None, (requirement, record.error)
    derived = record.solver_setup["derived"]
    assert derived["run_wake_length"] == "4 R", derived
    assert derived["run_wake_rule"] == "free_stream", derived
    assert float(derived["run_wake_v_ax_m_s"]) == pytest.approx(30.0), derived
    assert derived["run_wake_time_iterations"] == "800", derived


def test_p0370_s2_a_row_without_the_key_records_no_run_length_the_control():
    """P0370-S2-RUN-WAKE (FR-422 R4): a REVOLUTIONS row's snapshot carries no run_wake entry."""
    requirement = "FR-422"
    _, script = _built(_row(**{KEY: None, "REVOLUTIONS": "3"}))
    assert script.solver_setup is not None
    assert not any(key.startswith("run_wake") for key in script.solver_setup.derived), requirement


# --- FR-415 R6: the windows read the resolved count --------------------------


def test_p0370_s2_an_export_threshold_reads_the_resolved_count():
    """P0370-S2-RUN-WAKE (FR-422 R3, FR-415 R6): 176 steps of 36 a turn; the last revolution
    exports steps 141 to 176 and the last 10 steps 167 to 176, both counted back from the
    resolved count."""
    requirement = "FR-422"
    last_rev = unsteady_export_threshold(_row(EXPORT_UNSTEADY_LAST_REV="1"))
    assert last_rev is not None
    assert (last_rev.time_iterations, last_rev.first_step) == (176, 141), (requirement, last_rev)
    last_iter = unsteady_export_threshold(_row(EXPORT_UNSTEADY_LAST_ITER="10"))
    assert last_iter is not None
    assert (last_iter.time_iterations, last_iter.first_step) == (176, 167), requirement
    after = unsteady_export_threshold(_row(EXPORT_UNSTEADY_AFTER_ITER="176"))
    assert after is not None and after.first_step == 176, requirement
    with pytest.raises(CampaignConfigError) as refused:
        unsteady_export_threshold(_row(EXPORT_UNSTEADY_LAST_ITER="177"))
    assert "176" in str(refused.value), (requirement, str(refused.value))


def test_p0370_s2_the_averaging_window_reads_the_resolved_count():
    """P0370-S2-RUN-WAKE (FR-422 R3, FR-415 R6): LAST_REVS_AVG 0.25 of 36 steps is 9 steps,
    the last 9 of the resolved 176: steps 168 to 176."""
    requirement = "FR-422"
    windows = reduction_windows(_row())
    assert windows is not None
    assert windows["time_iterations"] == 176, (requirement, windows)
    assert windows["time_average"]["windows"] == [[168, 176]], (requirement, windows)
