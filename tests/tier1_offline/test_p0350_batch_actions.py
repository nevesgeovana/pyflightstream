"""The action programs of a grouped job: one counter and one clock for all (FR-354 to FR-371).

The programs are rendered and RUN with this interpreter in a temporary job
folder, one invocation per solver step, as the solver runs them: their own
process, no package on the path, no argument. Nothing here launches the solver.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    WALLTIME_CLOCK_PROGRAM,
    WALLTIME_CLOCK_STATE,
    WALLTIME_STOP_SCRIPT,
    register_unsteady_actions,
)
from pyflightstream.cases.workflows._batch_actions import (
    JOB_CURRENT,
    JOB_PROGRESS,
    JOB_SCHEDULE,
    job_schedule,
    render_job_clock_program,
    render_job_counter_program,
)
from pyflightstream.cases.workflows._batch_script import JobPoint, registration_block
from pyflightstream.script import Script

BUILD = "26.124"
#: The programs run as the solver runs them: their own interpreter, no package on the path.
ENV = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}


@pytest.mark.parametrize("exports", [False, True])
@pytest.mark.parametrize("walltime", [False, True])
def test_p0350_actions_fr354_registration_block_is_the_emitters(exports, walltime):
    """P0350-BATCH-ACTIONS-ONCE (FR-354): the job's block is the one emitter's lines."""
    script = Script(BUILD)
    register_unsteady_actions(script, True if exports else None, walltime=walltime)
    block = registration_block(BUILD, exports=exports, walltime=walltime)
    assert block == script.render()
    heads = [line.split()[2] for line in block.splitlines() if line.startswith("SET_NEW_UNSTEADY")]
    expected = ["pfs_unsteady_counter"] + ["pfs_unsteady_exports"] * exports
    expected += ["pfs_walltime_clock", "pfs_walltime_stop"] * walltime
    assert heads == expected


def _job_points(job: Path, steps: tuple[int, ...], first: tuple[int | None, ...]) -> list[JobPoint]:
    """Points of a job in ``job/dp<i>``, each exporting ``P<i>.txt`` and saving ``P<i>.fsm``."""
    points = []
    for index, (count, threshold) in enumerate(zip(steps, first, strict=True), start=1):
        points.append(
            JobPoint(
                run_id=f"mtx/sim_9000/DP-{index}",
                sim_id="9000",
                point_name=f"DP-{index}",
                text="",
                datapoint_dir=job / f"dp{index}",
                outputs=(f"P{index}.fsm", f"P{index}.txt", f"P{index}_log.txt"),
                action_exports=""
                if threshold is None
                else f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nP{index}.txt\n",
                first_export_step=threshold,
                stop_text=(
                    f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nP{index}.txt\n"
                    f"EXPORT_LOG\nP{index}_log.txt\nCLOSE_FLIGHTSTREAM\n"
                ),
                time_steps=count,
            )
        )
    return points


def _stage(job: Path, points: list[JobPoint], *, deadline_s: float | None) -> None:
    """Write the schedule and both programs where the job's registrations point."""
    (job / "actions").mkdir(parents=True)
    schedule = job_schedule(points, deadline_s=deadline_s)
    (job / JOB_SCHEDULE).write_text(json.dumps(schedule), encoding="utf-8")
    total = int(schedule["total_steps"])  # type: ignore[call-overload]
    counter = render_job_counter_program(total_steps=total, interpreter=sys.executable)
    (job / UNSTEADY_ACTION_PROGRAM).write_text(counter, encoding="utf-8")
    clock = render_job_clock_program(interpreter=sys.executable)
    (job / WALLTIME_CLOCK_PROGRAM).write_text(clock, encoding="utf-8")


def _run(job: Path, program: str) -> None:
    """One invocation, from another working directory: paths come from the program's folder."""
    subprocess.run([sys.executable, str(job / program)], cwd=job.parent, env=ENV, check=True)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p0350_actions_fr355_fr371_the_counter_reindexes_each_point(tmp_path):
    """P0350-BATCH-RECORDS (FR-371), P0350-BATCH-ACTIONS-ONCE (FR-355): each point's own count.

    Three points of 45, 24 and 24 steps (Test 3's counts): the job count is
    93, each point's own count file holds its own steps, ``JOB_CURRENT`` is
    rewritten at each point's first step, and the exports script holds point
    i's absolute exports exactly from its own first export step. Control: a
    mapping by the job count would export point 2 from its first step (job
    count 46 is past its threshold of 20), and the file is empty there.
    """
    job = tmp_path / "job"
    points = _job_points(job, (45, 24, 24), (40, 20, None))
    _stage(job, points, deadline_s=None)
    assert "TIME_ITERATIONS = 93" in (job / UNSTEADY_ACTION_PROGRAM).read_text(encoding="utf-8")
    exports = job / UNSTEADY_ACTION_SCRIPT
    seen_current = []
    count = 0
    for index, point in enumerate(points, start=1):
        for step in range(1, point.time_steps + 1):
            _run(job, UNSTEADY_ACTION_PROGRAM)
            count += 1
            if step == 1:
                current = _read(job / JOB_CURRENT)
                seen_current.append((current["point"], current["run_id"]))
                if index == 2:
                    assert count >= 20 and exports.read_text(encoding="utf-8") == "", "control"
            wanted = point.first_export_step is not None and step >= point.first_export_step
            expected = (
                f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\n{point.datapoint_dir / f'P{index}.txt'}\n"
            )
            assert exports.read_text(encoding="utf-8") == (expected if wanted else ""), (
                index,
                step,
            )
        (point.datapoint_dir / f"P{index}.fsm").write_bytes(b"saved")
    assert _read(job / UNSTEADY_ACTION_COUNT) == {"count": 93}
    for point in points:
        assert _read(point.datapoint_dir / UNSTEADY_ACTION_COUNT) == {"count": point.time_steps}
    assert seen_current == [(i, p.run_id) for i, p in enumerate(points, start=1)]
    progress = _read(job / JOB_PROGRESS)
    assert progress["point"] == 3 and progress["step"] == 24 and progress["job_count"] == 93
    assert progress["mismatch"] is False


@pytest.mark.parametrize("saved", [False, True])
def test_p0350_actions_fr355_the_check_flags_a_missing_fsm(tmp_path, saved):
    """P0350-BATCH-ACTIONS-ONCE (FR-355): point 1's missing save is flagged at point 2's start."""
    job = tmp_path / "job"
    points = _job_points(job, (2, 2), (None, None))
    _stage(job, points, deadline_s=None)
    _run(job, UNSTEADY_ACTION_PROGRAM)
    _run(job, UNSTEADY_ACTION_PROGRAM)
    if saved:
        (points[0].datapoint_dir / "P1.fsm").write_bytes(b"saved")
    _run(job, UNSTEADY_ACTION_PROGRAM)
    _run(job, UNSTEADY_ACTION_PROGRAM)
    progress = _read(job / JOB_PROGRESS)
    assert progress["mismatch"] is (not saved)
    if not saved:
        [found] = progress["mismatches"]
        assert (found["previous"], found["point"]) == (1, 2)


def test_p0350_actions_fr370_the_clock_stops_the_current_point(tmp_path):
    """P0350-BATCH-RECORDS (FR-370): the deadline reached in point 2 stops point 2.

    The stop script holds point 2's absolute stop text, ending in
    ``CLOSE_FLIGHTSTREAM``; point 2's own clock state stopped at its own
    step; points 1 and 3 hold no stop. The job's start is moved back by
    rewriting its state file before point 2's second step.
    """
    job = tmp_path / "job"
    points = _job_points(job, (3, 3, 3), (None, None, None))
    _stage(job, points, deadline_s=1000.0)
    stop = job / WALLTIME_STOP_SCRIPT
    for index, point in enumerate(points, start=1):
        for step in range(1, point.time_steps + 1):
            if (index, step) == (2, 2):
                state = _read(job / WALLTIME_CLOCK_STATE)
                state["started_at"] = time.time() - 5000.0
                (job / WALLTIME_CLOCK_STATE).write_text(json.dumps(state), encoding="utf-8")
            _run(job, UNSTEADY_ACTION_PROGRAM)
            _run(job, WALLTIME_CLOCK_PROGRAM)
            if (index, step) == (2, 2):
                text = stop.read_text(encoding="utf-8")
                assert text.endswith("CLOSE_FLIGHTSTREAM\n")
                assert f"{point.datapoint_dir / 'P2.txt'}\n" in text
                assert str(point.datapoint_dir / "P2.cumulative-log.txt") in text
            elif (index, step) < (2, 2):
                assert stop.read_text(encoding="utf-8") == ""
    own = [_read(p.datapoint_dir / WALLTIME_CLOCK_STATE) for p in points]
    assert own[1]["fired"] is True and own[1]["stopped_at"]["step"] == 2
    assert "stopped_at" not in own[0] and "stopped_at" not in own[2]
    assert own[0]["steps"] == 3 and own[2]["steps"] == 3
    whole = _read(job / WALLTIME_CLOCK_STATE)
    assert whole["fired"] is True and whole["stopped_at"]["point"] == 2
