"""LOG-OVERRIDES-COMPLETENESS: a residual does not excuse an unfinished or foreign solve.

Two rules, both about what a solver log may decide:

- A steady run told to run ALL its iterations that stopped early is an
  unfinished solve. The log branch returned its verdict before that check was
  reached, so exporting a log turned the refusal into an accepted status.
- A log is evidence of the export beside it only when both end at the same
  iteration. An export of iteration 312 was judged by the residual a log
  printed at iteration 1575.

The fixtures are the recorded pair of this tree: the steady export stops at
312 of 500, the unsteady one at 1575, and the log ends at 1575 with a final
velocity residual of 9.6e-8 under the export's convergence limit.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_run_campaign import FIXTURES, make_collected

_FORCED_OFF = "Force solver to run all iterations           F"
_FORCED_ON = "Force solver to run all iterations           T"


def _steady(forced: bool) -> str:
    text = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    assert _FORCED_OFF in text
    return text.replace(_FORCED_OFF, _FORCED_ON) if forced else text


def _log(*, ends_at: int = 1575, final_velocity: str = "+9.6000000E-8") -> str:
    text = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8")
    assert text.count("\n1575 ") == 1 and text.count("\n1574 ") == 1
    text = text.replace("+9.6000000E-8", final_velocity)
    return text.replace("\n1575 ", f"\n{ends_at} ").replace("\n1574 ", f"\n{ends_at - 1} ")


def _assess(tmp_path, loads: str, log: str):
    sim_dir = make_collected(tmp_path, "", text=loads)
    make_collected(tmp_path, "", name="log.txt", text=log)
    return LoadsAssessor("loads.txt")(None, None, sim_dir)


def test_a_forced_run_that_stopped_early_is_unfinished_whatever_its_log_says(tmp_path):
    # The residual is far above any limit: the log said COMPLETED_MAX_ITER.
    assessment = _assess(
        tmp_path, _steady(forced=True), _log(ends_at=312, final_velocity="+9.6000000E-2")
    )
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "forced iterations" in (assessment.error or "")
    assert "312" in (assessment.error or "") and "500" in (assessment.error or "")


def test_a_forced_run_that_stopped_early_is_unfinished_even_under_a_converged_log(tmp_path):
    assessment = _assess(tmp_path, _steady(forced=True), _log(ends_at=312))
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "forced iterations" in (assessment.error or "")


def test_a_log_that_ends_at_another_iteration_is_not_evidence_of_this_export(tmp_path):
    assessment = _assess(tmp_path, _steady(forced=False), _log(ends_at=1575))
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    message = assessment.error or ""
    assert "312" in message and "1575" in message
    assert "log.txt" in message
    # No residual is reported for a judgment that was not made.
    assert assessment.residual is None


def test_a_log_that_ends_where_the_export_ends_still_decides_on_the_residual(tmp_path):
    converged = _assess(tmp_path / "a", _steady(forced=False), _log(ends_at=312))
    assert converged.status is RunStatus.CONVERGED
    assert converged.residual == pytest.approx(9.6e-8)
    assert converged.iterations == 312

    limited = _assess(
        tmp_path / "b", _steady(forced=False), _log(ends_at=312, final_velocity="+9.6000000E-2")
    )
    assert limited.status is RunStatus.COMPLETED_MAX_ITER
    assert limited.residual == pytest.approx(9.6e-2)


def test_the_recorded_unsteady_pair_is_judged_as_it_was(tmp_path):
    unsteady = (FIXTURES / "loads_unsteady_26.120.txt").read_text(encoding="utf-8")
    assessment = _assess(tmp_path, unsteady, _log())
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.residual == pytest.approx(9.6e-8)
    assert assessment.iterations == 1575
