"""Tier 1, 0.40.0 lane run-1: the wall clock of a grouped job (FR-364).

Hand-built polar units; no plan and no solver.
"""

from __future__ import annotations

from pyflightstream.run._batch_split import JobSplit, job_walltime
from tests.tier1_offline.test_p0350_batch_split import HOUR, _unit


def test_p0400_a_row_with_no_cell_and_no_best_is_not_budgeted_at_zero() -> None:
    """P0400-JOB-WALLTIME-UNSTATED (PFS-2094.006): one row states 2h, the other nothing.

    The sum covered the stated row alone, so the job's 2h bounded the other row's point
    too, silently. The job now asks the profile's limit and names the row, or is refused
    naming it where the profile states no limit.
    """
    stated = _unit("2001", 1, 0.0, seconds=(HOUR,), cell_s=2 * HOUR, cell_text="2h", best=False)
    bare = _unit("2002", 2, 0.0, seconds=(HOUR,), best=False)
    job = JobSplit((stated, bare))
    seconds, source, _, _, warnings, refusal = job_walltime(job, 2 * HOUR, max_walltime_s=5 * HOUR)
    assert (seconds, source, refusal) == (5 * HOUR, "max_walltime", None)
    assert any("2002" in line and "max_walltime" in line for line in warnings), warnings
    seconds, _, _, _, _, refusal = job_walltime(job, 2 * HOUR, max_walltime_s=None)
    assert seconds is None
    assert refusal is not None and "2002" in refusal and "2001" in refusal
