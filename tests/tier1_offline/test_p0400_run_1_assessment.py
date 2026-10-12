"""Tier 1, 0.40.0 lane run-1: the collect's assessor (FR-434 on a quasi-steady wheel).

The wheel fixture of the 0.30.0 tests: a log of one solve per clocking, each loads
export written at its solve's last iteration, a requested limit of 500.
"""

from __future__ import annotations

from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal035_l1_defects import _clocked_wheel


def test_p0400_a_wheel_clocking_at_its_iteration_limit_is_max_iter_reached(tmp_path):
    """P0400-WHEEL-MAX-ITER (PFS-2103.018, PFS-2103.020): two clockings, one stopped at 500.

    A one-clocking point with the same evidence is MAX_ITER_REACHED (FR-434); the clocking
    path folded the solves without FR-434 and recorded COMPLETED_MAX_ITER. The point and
    the clocking now carry MAX_ITER_REACHED, the requested limit and the note naming it.
    """
    case, sim = _clocked_wheel(tmp_path, (4.0e-5, 3.0e-6), (500, 61))
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
    assert assessment.iterations_requested == 500
    verdicts = assessment.clocking_verdicts
    assert verdicts is not None
    assert [(v["index"], v["status"]) for v in verdicts] == [
        (1, "MAX_ITER_REACHED"),
        (0, "CONVERGED"),
    ]
    assert "iteration limit (500)" in str(verdicts[0]["note"])
    assert "clocking 1" in (assessment.residual_note or "")


def test_p0400_a_wheel_short_of_its_limit_keeps_completed_max_iter(tmp_path):
    """P0400-WHEEL-MAX-ITER (PFS-2103.020): the control, a clocking unsettled at 400 of 500."""
    case, sim = _clocked_wheel(tmp_path, (4.0e-5, 3.0e-6), (400, 61))
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
    assert assessment.iterations_requested is None
