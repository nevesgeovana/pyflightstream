"""Tier 1: collect names each missing output, and the record carries the log's times (GOAL-024).

The test names carry ``goal024_collect_and_times`` so the goal's checker can select them.
"""

from __future__ import annotations

import pytest

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


def test_goal024_collect_and_times_the_record_carries_the_times_to_the_manifest(tmp_path):
    """The three times are IN runs.json after a collect, read from the log the job left.

    The first writing asserted that `RunRecord` declares the fields, which a
    model with the fields and a stage that never fills them passes: removing
    the three names from the collect stage's stamp left it green (the qa lens,
    2026-09-16). This drives the stage and reads the manifest.
    """
    import json

    from pyflightstream.run.collect import collect_once
    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace
    from tests.tier1_offline.test_goal024_profile_log import _work_dir
    from tests.tier1_offline.test_run_campaign import FIXTURES

    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    work = _work_dir(workspace, sim, alpha=2.0)
    (work / "loads.txt").write_text(
        (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # THE LOG ENDS WHERE THE EXPORT ENDS (0.24.0). The two fixtures are of two
    # runs, the export at iteration 312 and the log at 1575, and the assessor
    # now refuses a log that is not of the export beside it. What this case
    # asserts is unchanged; only the pairing is made one a single run writes.
    (work / "P9001-AL+000_log.txt").write_text(
        (FIXTURES / "log_residuals_26.120.txt")
        .read_text(encoding="utf-8")
        .replace("\n1575 ", "\n312 ")
        .replace("\n1574 ", "\n311 "),
        encoding="utf-8",
    )

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert not report.failed, [outcome.detail for outcome in report.failed]
    row = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))[0]
    assert row["solver_run_time_s"] == pytest.approx(841.2), row
    assert row["log_file_used"] == "P9001-AL+000_log.txt", row
    # 312 and no longer 1575: the number was the OTHER run's last iteration,
    # recorded against an export written at 312.
    assert row["iterations"] == 312 and row["residual"], row
    # The initialisation time and the step count are None on THIS log, which
    # prints neither: the field is carried as None rather than as zero, which
    # is the rule the parser states.
    assert row["solver_initialization_s"] is None, row
    assert row["time_steps"] is None, row


def test_goal024_collect_and_times_a_log_whose_markers_carry_no_page_was_not_cut():
    """The suite arm after the 0.26.0 post-log merge: a false CUT.

    RPT-055 taught the reader that a marker at the END of the log with no
    residual page is a block the solver stopped under. That is true of a log
    that prints pages. A log whose markers never carry one, the progress lines
    of this file appended to a steady history, was called cut and the assessor
    raised instead of judging. No page anywhere means no table was ever printed,
    and the verdict is simply that nothing froze.
    """
    from pyflightstream.results import frozen_time_steps

    assert frozen_time_steps(UNSTEADY_LINES) is None
    assert frozen_time_steps("Solver initialized in 1.70 seconds\n" + UNSTEADY_LINES) is None


def test_goal024_collect_and_times_a_cut_log_is_unusable_evidence_and_not_an_exception(
    tmp_path, monkeypatch
):
    """The assessor's freeze read is wrapped: a cut is FAILED_INCOMPLETE_OUTPUT."""
    import pyflightstream.run as run_module
    from pyflightstream.results import IncompleteOutputError
    from pyflightstream.workspace import RunStatus
    from tests.tier1_offline.test_run_campaign import FIXTURES, _assess_log

    def cut(_text):
        raise IncompleteOutputError(
            "time step 54 ends before its Iteration anchor; recollect the log"
        )

    monkeypatch.setattr(run_module, "frozen_time_steps", cut)
    text = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8") + UNSTEADY_LINES
    assessment = _assess_log(tmp_path, text)
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, assessment
    assert "Iteration anchor" in (assessment.error or "")
