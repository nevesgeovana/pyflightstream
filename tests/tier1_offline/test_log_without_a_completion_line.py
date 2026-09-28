"""A 26.124 log that ends without a converged or completed line is judged, not refused.

Measured on 26.124 (the owner's research campaign, 2026-09-28): an unsteady
native log ends with ``Unsteady solver run time: N minutes.``, the saved
simulation and exported files, and ``Script run complete.`` lines, and carries
no ``converged``, ``completed`` or ``simulation complete`` line anywhere. A
checker outside the package required such a line and could never pass on a
real log. Every reader in the package that judges a run from its log text was
read for the same assumption (0.30.0): the residual history
(``parse_residual_history``, ``reads_as_residual_history``,
``collected_solver_log``), the times (``parse_log_times``), the frozen-solve
reading (``frozen_time_steps``) and ``LoadsAssessor``. None requires a
completion line; this pins it, so a future reader that starts requiring one
fails here.
"""

from __future__ import annotations

import re

from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_run_campaign import FIXTURES, _assess_log

#: The tail of a 26.124 unsteady log as the solver prints it (measured).
TAIL_26124 = (
    "\n \nUnsteady solver run time: 5.78 minutes.\n \n"
    "Simulation file saved to following location:\n \nP9901.fsm\n \n\n \n"
    "Data written to external text file:\n \nP9901.txt\n \n\n \n"
    "Script run complete.\n \n"
)


def _log() -> str:
    history = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8")
    # The fixture's own tail is 26.120's; the 26.124 tail replaces it.
    text = history[: history.index("Unsteady solver run time")] + TAIL_26124
    assert not re.search(r"converged|completed|simulation complete", text, re.I), (
        "the fixture must carry no completion line, or it does not pin the shape"
    )
    return text


def test_the_assessor_judges_a_log_that_ends_in_script_run_complete(tmp_path):
    assessment = _assess_log(tmp_path, _log())
    assert assessment.status is RunStatus.CONVERGED, (assessment.status, assessment.error)
    assert assessment.iterations == 1575
    assert assessment.solver_run_time_s == 5.78 * 60.0


def test_every_log_reader_reads_that_log(tmp_path):
    from pyflightstream.results import frozen_time_steps, parse_residual_history
    from pyflightstream.run._wake_edge_verdict import (
        collected_solver_log,
        reads_as_residual_history,
    )

    text = _log()
    (tmp_path / "P_log.txt").write_text(text, encoding="utf-8")
    assert parse_residual_history(text)[-1].iteration == 1575
    assert reads_as_residual_history(tmp_path / "P_log.txt")
    assert collected_solver_log(tmp_path, ["P_log.txt"], None) == text
    assert frozen_time_steps(text) is None
