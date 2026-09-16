"""Tier 1: every FLIGHT_CONDITION variable sweeps (0.21.0, GOAL-024 arm 4).

Until 0.20.x a row could vary the two angles and the advance ratio, and a row
writing ``sweep`` against a Mach number was refused naming those three. The
rule always licensed any key of the cell; this is the release that implements
it.

A SWEPT FLOW VARIABLE IS RESOLVED PER POINT, and that is what these tests
measure rather than the plan's list of names alone: a Mach sweep whose points
all carry the first point's velocity would produce distinct names over
identical runs, which is worse than the refusal it replaces.

The test names carry ``goal024_sweep_any_variable`` so the goal's checker can
select them.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.matrix import MatrixError, read_matrix, to_campaign
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix
from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix

#: The axes a configuration declares, so a row may state a body rate.
AXES = '\n[body_axes]\nroll = "X"\npitch = "Y"\nyaw = "Z"\n'


def _plan(workspace, matrix):
    return plan_matrix(
        matrix,
        workspace,
        name="swept",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


def _resolved(workspace, matrix):
    """Bind the matrix to the workspace's library, which is what a plan does first."""
    from pyflightstream.workspace.matrix import resolve_matrix

    return resolve_matrix(
        matrix,
        workspace,
        name="swept",
        fs_version="26.120",
        recipes=RECIPES,
    )


def _names(workspace, matrix) -> list[str]:
    plan = _plan(workspace, matrix)
    assert not plan.blocked, plan.summary()
    return [point.run_id.rsplit("/", 1)[-1] for point in plan.points]


def test_goal024_sweep_any_variable_a_mach_sweep_plans_and_names_its_points(tmp_path):
    """MACH:sweep: three points, three names, the Mach number in each."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.1,0.2,0.3",
    )
    assert _names(workspace, matrix) == [
        "M100RE230AL+000",
        "M200RE230AL+000",
        "M300RE230AL+000",
    ]


def test_goal024_sweep_any_variable_a_reynolds_sweep_plans_and_names_its_points(tmp_path):
    """REmi:sweep, the constraint that solves for density: three points, three names."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:sweep, ALPHA:0.0",
        values="2.3,4.6",
    )
    assert _names(workspace, matrix) == ["M200RE230AL+000", "M200RE460AL+000"]


def test_goal024_sweep_any_variable_an_altitude_sweep_plans_and_names_its_points(tmp_path):
    """ALTFT:sweep, which moves the pressure and the temperature with it."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, ALTFT:sweep, ALPHA:0.0",
        values="0,10000",
    )
    assert _names(workspace, matrix) == ["M200ALT00000AL+000", "M200ALT10000AL+000"]


def test_goal024_sweep_any_variable_each_point_carries_its_own_resolved_state(tmp_path):
    """The half that matters: the points differ in the FLOW, not only in the name.

    A Mach sweep at a fixed Reynolds number moves the velocity AND the density,
    because the Reynolds number is what fixes the density. Resolving the row
    once would give every point the first point's numbers, and the names would
    still come out distinct: that is the defect this asserts against.
    """
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.1,0.3",
    )
    (case,) = _resolved(workspace, matrix).campaign.sims
    states = [case.point_states[key] for key in sorted(case.point_states)]
    assert len(states) == 2, case.point_states
    # The Mach number a state carries is the RESOLVED one, taken against the
    # speed of sound of that state, so it is the stated value to within the
    # arithmetic and not the stated string.
    assert [state.mach for state in states] == pytest.approx([0.1, 0.3])
    velocities = [state.fluid.velocity_m_per_s for state in states]
    assert velocities[1] > velocities[0] * 2.5, velocities
    densities = [state.fluid.density_kg_m3 for state in states]
    assert densities[0] > densities[1] * 2.5, (
        f"at a held Reynolds number the density falls as the velocity rises; got {densities}"
    )
    # The case the run hands the builder is the case AT the point, so what the
    # script carries is the point's own state and not the row's.
    from pyflightstream.cases import case_at_point

    at_fast = case_at_point(case, {"MACH": 0.3, "alpha": 0.0})
    at_slow = case_at_point(case, {"MACH": 0.1, "alpha": 0.0})
    assert at_fast.mach == pytest.approx(0.3)
    assert at_slow.mach == pytest.approx(0.1)
    assert at_fast.flight_condition["MACH"] == 0.3
    assert at_slow.flight_condition["MACH"] == 0.1
    assert at_fast.fluid.velocity_m_per_s > at_slow.fluid.velocity_m_per_s * 2.5


def test_goal024_sweep_any_variable_the_emitted_script_states_the_point_s_own_flow(tmp_path):
    """Through the workflow: the fluid block of each script carries that point's numbers."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.1,0.3",
    )
    # A ROW THAT SWEEPS THE FLOW IS ONE JOB PER POINT: the air state is a setup
    # command the solver takes before it is initialised, so a warm sweep cannot
    # carry two of them. Each point therefore has its own script, and what is
    # asserted is that each states its own air.
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import (
        WRITES_EVERY_EXPORT,
        CountingStub,
        converged,
    )

    run_matrix(
        matrix,
        workspace,
        name="swept",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    scripts = sorted((workspace.sim_dir("3207") / "scripts").glob("*.txt"))
    assert [path.stem for path in scripts] == [
        "P3207-M100RE230AL+000",
        "P3207-M300RE230AL+000",
    ], scripts
    slow_text, fast_text = (path.read_text(encoding="utf-8") for path in scripts)
    slow = float(_every_value(slow_text, "SOLVER_SET_VELOCITY")[0])
    fast = float(_every_value(fast_text, "SOLVER_SET_VELOCITY")[0])
    assert fast > slow * 2.5, (slow, fast)
    # The DENSITY moves with it, because the Reynolds number is held and it is
    # the density that solves for it.
    slow_rho = float(_every_value(slow_text, "DENSITY")[0])
    fast_rho = float(_every_value(fast_text, "DENSITY")[0])
    assert slow_rho > fast_rho * 2.5, (slow_rho, fast_rho)


def _every_value(text: str, command: str) -> list[str]:
    """Return the value of every occurrence of ``command`` in a script.

    The emitter writes some commands with their value on the same line
    (``SOLVER_SET_VELOCITY 34.029``) and some with it on the next, so both
    shapes are read here rather than one of them being assumed.
    """
    lines = [line.strip() for line in text.splitlines()]
    values = []
    for index, line in enumerate(lines):
        head, _, tail = line.partition(" ")
        if head != command:
            continue
        if tail:
            values.append(tail.strip())
        elif index + 1 < len(lines):
            values.append(lines[index + 1])
    if not values:
        raise AssertionError(f"{command} is not in the script")
    return values


def test_goal024_sweep_any_variable_a_key_outside_the_cell_is_still_refused_by_name(tmp_path):
    """Widening the set is not opening it: a key the cell has no meaning for is refused."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:0.0",
        values="1,2",
    )
    text = matrix.read_text(encoding="utf-8")
    matrix.write_text(text.replace("REmi:2.3", "NOT_A_KEY:sweep"), encoding="utf-8")
    with pytest.raises(MatrixError, match="NOT_A_KEY"):
        read_matrix(matrix)


def test_goal024_sweep_any_variable_a_row_still_sweeps_one_variable(tmp_path):
    """Two swept keys are refused by name, as they were before the set widened."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:sweep, REmi:sweep, ALPHA:0.0",
        values="0.1,0.2",
    )
    with pytest.raises(MatrixError, match="MACH, REmi"):
        read_matrix(matrix)


def test_goal024_sweep_any_variable_a_campaign_written_in_python_sweeps_them_too(tmp_path):
    """The library takes the same axes: the matrix is one door into the sweep, not the only one."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.1,0.2",
    )
    campaign = to_campaign(
        matrix,
        name="swept",
        fs_version="26.120",
        fs_exe="C:/fs/FS.exe",
        recipes=RECIPES,
        require_outputs=False,
    )
    (case,) = campaign.sims
    assert case.sweep.type == "MACH"
    assert [point["MACH"] for point in case.sweep.points()] == [0.1, 0.2]


def test_goal024_sweep_any_variable_a_body_rate_sweeps_too(tmp_path):
    """A rate is a variable of the cell like any other, so it sweeps like any other.

    The cluster's own case: hold the flow, vary the pull-up. The points differ
    in the FREE STREAM rather than in the air, so each is named for its rate.
    """
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:0.0, pitch_rate:sweep",
        values="0.0,4.0",
    )
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + AXES, encoding="utf-8")
    assert _names(workspace, matrix) == ["M200RE230AL+000Q+000", "M200RE230AL+000Q+040"]
