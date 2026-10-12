"""Tier 1, 0.40.0 lane run-2: the grouped plan, split, run and collect (--batch, --polar-sweep).

The workspaces are the grouped-plan fixture the 0.35.0 tests share.
"""

from __future__ import annotations

import dataclasses

from pyflightstream.run import _batch_plan
from pyflightstream.run._plan import PlanStatus
from tests.support_helpers import grouped_plan_fixture
from tests.tier1_offline.test_p0350_batch_plan import _plan


def test_p0400_a_polar_with_a_blocked_point_is_left_out_by_name(tmp_path, monkeypatch):
    """P0400-GROUPED-BLOCKED (PFS-2094.005): the polar is named among the left out.

    A grouped job holds a polar whole, so one blocked point keeps its READY
    siblings from running too; the polar was dropped without a word.
    """
    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("2h", "2h"), sweep="0.0,2.0")
    real = _batch_plan.plan_matrix

    def one_blocked(*args, **kwargs):
        plan = real(*args, **kwargs)
        points = list(plan.points)
        first = next(i for i, entry in enumerate(points) if entry.sim_id == "7001")
        points[first + 1] = dataclasses.replace(
            points[first + 1], status=PlanStatus.BLOCKED, error="a planted block"
        )
        return dataclasses.replace(plan, points=type(plan.points)(points))

    monkeypatch.setattr(_batch_plan, "plan_matrix", one_blocked)
    plan = _plan(workspace, matrix, batch=2)
    left = {item["sim"]: item["reason"] for item in plan.grouping.left_out}
    assert "7001" in left, plan.grouping.left_out
    assert "BLOCKED" in left["7001"] and "polar whole" in left["7001"]
    assert all("7001" not in job.sims for job in plan.grouping.jobs)
