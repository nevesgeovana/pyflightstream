"""Tier 1, 0.40.0 lane run-1: the plan's cost estimate (FR-82).

A fresh workspace with hand-written records; no solver runs.
"""

from __future__ import annotations

import pytest

from pyflightstream.run._plan import _recorded_costs, estimate_point_cost
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline import test_p0350_run_id_alias as alias_tests
from tests.tier1_offline.test_plan_cost import saved_simulation, steady_case


def test_p0400_the_estimate_learns_nothing_from_a_run_that_did_not_end(tmp_path):
    # Verifies FR-82.
    """P0400-COST-SAMPLES (PFS-2094.014): a fast failure and a run stopped by its clock.

    Every record with a wall time was a sample, so a FAILED_EXECUTION after one second, a
    WALLTIME_REACHED at the clock and a person's FAILED_MARKED moved the estimate, against
    restore-and-rebuild.md. The control is the CONVERGED run alone: 10 s, one sample.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    for tag, status, seconds in (
        ("A0", RunStatus.CONVERGED, 10.0),
        ("A1", RunStatus.FAILED_EXECUTION, 1.0),
        ("A2", RunStatus.WALLTIME_REACHED, 600.0),
        ("A3", RunStatus.FAILED_MARKED, 5.0),
        ("A4", RunStatus.RAN_MISSING_LOG, 50.0),
    ):
        record = alias_tests._record("2006", f"warm/sim_2006/{tag}", status=status)
        workspace.append_record(
            record.model_copy(update={"wall_time_s": seconds, "recipe": "steady"})
        )
    samples = _recorded_costs(workspace)
    assert [row["run_id"] for row in samples] == ["warm/sim_2006/A0"]
    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    estimate = estimate_point_cost(
        steady_case(geometry), run_id="run/a", recorded=samples, steps_by_run={}
    )
    assert estimate.samples == 1
    assert estimate.seconds == pytest.approx(10.0)
