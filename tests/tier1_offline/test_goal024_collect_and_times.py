"""Tier 1: collect names each missing output, and the record carries the log's times (GOAL-024).

The test names carry ``goal024_collect_and_times`` so the goal's checker can select them.
"""

from __future__ import annotations

from pyflightstream.run.collect import collect_once
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace


def test_goal024_collect_and_times_a_waiting_point_names_every_missing_output(tmp_path):
    """Of eight declared outputs the one that never arrives is named, not only counted."""
    declared = ("loads.txt", "run_log.txt", "run_plots.txt")
    workspace, sim = _submitted_workspace(tmp_path, declared=declared)
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    detail = report.waiting[0].detail
    assert detail.startswith("2 of 3 declared output(s) not there yet: "), detail
    assert "run_log.txt" in detail and "run_plots.txt" in detail
    assert "loads.txt," not in detail and not detail.endswith("loads.txt")


# ---------------------------------------------------------------- the log's times --

#: Lines as FlightStream prints them in an unsteady log (26.123, measured on
#: this machine 2026-09-15); the step lines carry the total after the slash.
UNSTEADY_LINES = (
    "Solver initialized in 1.70 seconds\n"
    "Solving unsteady time-step iteration (1/54)...\n"
    "Solving unsteady time-step iteration (54/54)...\n"
    "Unsteady solver run time: 5.56 minutes.\n"
)

#: A steady row solving two angles in one job prints two run times; the point's
#: own is the latest.
STEADY_LINES = (
    "Solver initialized in .92 seconds\n"
    "Solver run time: .0907167 minutes.\n"
    "Solver run time: .0824833 minutes.\n"
)


def test_goal024_collect_and_times_the_unsteady_log_gives_its_run_time_initialization_and_steps():
    from pyflightstream.results import parse_log_times

    times = parse_log_times(UNSTEADY_LINES)
    assert times.solver_run_time_s == 5.56 * 60.0
    assert times.solver_initialization_s == 1.70
    assert times.time_steps == 54


def test_goal024_collect_and_times_a_steady_log_reads_the_latest_run_time_and_no_steps():
    from pyflightstream.results import parse_log_times

    times = parse_log_times(STEADY_LINES)
    assert times.solver_run_time_s == 0.0824833 * 60.0
    assert times.solver_initialization_s == 0.92
    assert times.time_steps is None


def test_goal024_collect_and_times_a_log_without_the_lines_reports_none_and_not_zero():
    from pyflightstream.results import parse_log_times

    times = parse_log_times("Running script...\n")
    assert (times.solver_run_time_s, times.solver_initialization_s, times.time_steps) == (
        None,
        None,
        None,
    )


def test_goal024_collect_and_times_the_verdict_read_from_a_log_carries_its_times(tmp_path):
    """The assessor that reads the residuals stamps the same log's times on its verdict."""
    from tests.tier1_offline.test_run_campaign import FIXTURES, _assess_log

    text = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8") + UNSTEADY_LINES
    assessment = _assess_log(tmp_path, text)
    assert assessment.solver_run_time_s == 5.56 * 60.0
    assert assessment.solver_initialization_s == 1.70
    assert assessment.time_steps == 54


def test_goal024_collect_and_times_the_record_carries_the_times_to_the_manifest():
    """RunRecord holds the three fields, so a collected or local verdict reaches runs.json."""
    from pyflightstream.workspace import RunRecord

    for field in ("solver_run_time_s", "solver_initialization_s", "time_steps", "residual_note"):
        assert field in RunRecord.model_fields, field
