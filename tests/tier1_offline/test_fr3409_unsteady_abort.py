"""FR-3409: a run whose solver logged that its unsteady march was aborted is FAILED_EXECUTION.

Measured on 26.127 (the pyfs-debugging register, row 7163 of 2026-10-30): the action
program could not execute at the first step, the solver logged the abort and saved its
outputs, and the steady initialization's residual table, converged, made the assessor
read CONVERGED; the post then wrote products from a march of one step. The line is the
one statement of it, so it decides, as the actuator profile's lines do (G06).
"""

from __future__ import annotations

import pytest

from pyflightstream.run._wake_edge_verdict import (
    UNSTEADY_ABORT,
    log_verdict,
    unsteady_abort_verdict,
    with_log_verdict,
)
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_g06_actuator_disc import _run_a_profile_row, _solver_log

#: The three lines the solver wrote on 26.127, after its wake grid lines.
ABORT_LINES = (
    'Unsteady solver action runtime command ("pythonw.exe" "actions/pfs_unsteady_actions.py")'
    " failed to execute!\nError code:            0\n" + UNSTEADY_ABORT
)


def _aborted_log(_line: str | None) -> str:
    """The committed solver log, its residual table converged, with the abort after it."""
    return _solver_log(ABORT_LINES)


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_fr3409_a_run_whose_log_says_the_march_was_aborted_is_failed_execution(tmp_path, values):
    """End to end through run_matrix: the assessor says CONVERGED, the log says aborted, and
    the record is FAILED_EXECUTION with the line quoted."""
    record, _, _ = _run_a_profile_row(tmp_path, values=values, refused=False, log_form=_aborted_log)
    assert record.status is RunStatus.FAILED_EXECUTION, (record.status, record.error)
    assert UNSTEADY_ABORT in record.error, record.error
    assert "Run the point again" in record.error, record.error


def test_fr3409_the_control_without_the_line_stays_converged(tmp_path):
    """The same row and the same log without the abort is CONVERGED, so the line decides."""
    record, _, _ = _run_a_profile_row(tmp_path, values="0.0", refused=False)
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)


@pytest.mark.parametrize("aborted", [True, False], ids=["aborted", "control"])
def test_fr3409_a_collected_point_whose_log_says_the_march_was_aborted_is_failed_execution(
    tmp_path, aborted
):
    """A submitted point is judged at collect: the abort in its collected log makes it
    FAILED_EXECUTION over the assessor's CONVERGED, and the same log without it stays CONVERGED."""
    from pyflightstream.run.collect import collect_once
    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

    workspace, sim = _submitted_workspace(tmp_path)
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    log = _solver_log(ABORT_LINES) if aborted else _solver_log(None)
    (sim / "run_log.txt").write_bytes(log.encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=passed)
    (outcome,) = report.collected + report.failed
    assert outcome.record is not None, outcome.detail
    if not aborted:
        assert outcome.record.status is RunStatus.CONVERGED, outcome.record.error
        return
    assert outcome.record.status is RunStatus.FAILED_EXECUTION, (
        outcome.record.status,
        outcome.record.error,
    )
    assert UNSTEADY_ABORT in outcome.record.error, outcome.record.error


def test_fr3409_the_line_is_read_through_the_nul_a_hidden_export_writes():
    """A hidden-mode log puts a NUL alone on the line after every line; the line is still read."""
    assert unsteady_abort_verdict(None, "", _aborted_log(None)) is not None
    assert unsteady_abort_verdict(_solver_log(None)) is None


def test_fr3409_an_abort_does_not_hide_a_failure_already_recorded():
    """A run already failed keeps its own status and error: the verdict applies only over a pass."""
    verdict = log_verdict(_aborted_log(None))
    assert verdict is not None and verdict[0] is RunStatus.FAILED_EXECUTION
    assert with_log_verdict(RunStatus.FAILED_DIVERGED, "diverged", verdict) == (
        RunStatus.FAILED_DIVERGED,
        "diverged",
    )
    status, error = with_log_verdict(RunStatus.CONVERGED, None, verdict)
    assert status is RunStatus.FAILED_EXECUTION and UNSTEADY_ABORT in (error or "")
