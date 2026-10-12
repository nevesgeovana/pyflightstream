"""Tier 1, 0.40.0 lane run-2: the judgement of a quasi-steady wheel solved at several clockings.

The wheel is the one the GOAL-035 tests build: a two-clocking point as its
run leaves it, its record, its loads exports and its one log of two solves.
"""

from __future__ import annotations

from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal035_l1_defects import _clocked_wheel
from tests.tier1_offline.test_goal036_qsteady_record import _spoiled


def test_p0400_a_wheel_clocking_at_its_iteration_limit_is_max_iter_reached(tmp_path):
    """P0400-QS-ITERLIMIT (PFS-2103.002): FR-434 R1 holds for a wheel's clockings.

    Clocking 0 stops at the requested 500 iterations unsettled (9e-3 against
    the limit 1e-5); the clocking path skipped the promotion and the point
    stayed COMPLETED_MAX_ITER.
    """
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 9.0e-3), rows=(500, 500))
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
    assert assessment.iterations_requested == 500
    verdicts = {v["index"]: v["status"] for v in assessment.clocking_verdicts or []}
    assert sorted(verdicts.values()) == ["CONVERGED", "MAX_ITER_REACHED"], verdicts


def test_p0400_a_wheel_whose_record_is_spoiled_is_not_converged(tmp_path):
    """P0400-QS-SPOILED-RECORD (PFS-2103.021): its log of two solves is not 'no log'.

    With the record unreadable, the log of two solves did not read as a log
    of one, so the point was recorded CONVERGED from its iteration count with
    its unsettled clocking never read.
    """
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 9.0e-3))
    (sim / "outputs" / "DP_qsteady.json").write_text(_spoiled("schema_version", 2))
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, assessment.status
    assert "DP_log.txt holds 2" in (assessment.error or "")
