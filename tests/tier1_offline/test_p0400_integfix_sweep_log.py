"""Tier 1, 0.40.0 integration fixes: a steady sweep point beside the sweep's shared log."""

from __future__ import annotations

from pyflightstream.run import LoadsAssessor
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal035_l1_defects import _loads, _wheel_log


def test_p0400_a_sweep_point_is_not_refused_for_the_sweeps_shared_log(tmp_path):
    """P0400-SWEEP-SHARED-LOG (PFS-2103.021): the solve-count refusal is a wheel's alone.

    A steady sweep solved in one script exports one solver log holding every
    point solved so far, so the second point's collected log holds two solves.
    The refusal of a log of another solve count, written for a quasi-steady
    wheel whose record could not be read, refused every point after the first
    of a sweep; such a point is judged by its iteration count, as before.
    """
    sim = tmp_path / "sim"
    outputs = sim / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "DP.txt").write_text(_loads(61), encoding="utf-8")
    (outputs / "DP_log.txt").write_bytes(_wheel_log((2.0e-6, 3.0e-6), (61, 61)).encode("utf-8"))
    assessment = LoadsAssessor()(None, None, sim)
    assert "holds 2" not in (assessment.error or ""), assessment.error
    assert assessment.status is not RunStatus.FAILED_INCOMPLETE_OUTPUT, assessment
