"""Tier 1: two cases of one campaign may not render one stem (0.24.0).

MT-07. Every per-point product (sections, probes, plots, reductions, series)
is named by the stem of the point's loads file and carries no simulation id,
and every record of a Python-authored campaign lands in ONE products folder.
The library's default point name, `{point}`, writes the flight condition alone,
so two cases at one condition (two geometries, two post-processing artifacts)
render one stem: the second case's product archives the first one's and takes
its manifest key. The collision guard ran per case and never saw it.

The matrix command line names by `{polar}`, which carries `P<sim>-`, and is
not affected; the last test holds that.

Narrow form: the plan refuses. Carrying the simulation id in every per-point
product name would rename files a user's scripts read, and is not done here.

Expected names are written from the naming convention: a case authored with no
FLIGHT_CONDITION cell is named by its Mach number (x 1000, three digits) and
then by the axes of its point (alpha x 10, signed).
"""

from __future__ import annotations

import sys

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import PlanStatus, plan_campaign
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate
from tests.tier1_offline.test_run_campaign import steady_recipe


def _campaign(tmp_path, *, machs=(0.2, 0.2), outputs=("loads_{point}.txt",)) -> Campaign:
    """Two cases, two geometries, each one point at alpha -2 deg."""
    sims = []
    for sim_id, mach in zip(("1", "2"), machs, strict=True):
        geometry = tmp_path / f"wing_{sim_id}.fsm"
        geometry.write_bytes(b"geometry " + sim_id.encode())
        sims.append(
            SimCase(
                sim_id=sim_id,
                aircraft="TestWing",
                mach=mach,
                geometry=str(geometry),
                sweep=SweepAxis(type="alpha", values=[-2.0]),
                recipe="steady",
                outputs=list(outputs),
            )
        )
    return Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=sims)


def _plan(campaign, workspace):
    return plan_campaign(campaign, workspace, recipes={"steady": steady_recipe}, write_plan=False)


def test_goal028_rename_stems_across_cases_two_cases_at_one_condition_are_refused(tmp_path):
    """Both cases render `loads_M200AL-020.txt`, and the plan says so for both."""
    plan = _plan(_campaign(tmp_path), CampaignWorkspace(tmp_path / "camp"))

    assert [point.status for point in plan.points] == [PlanStatus.BLOCKED, PlanStatus.BLOCKED], (
        plan.summary()
    )
    for point in plan.points:
        message = str(point.error)
        assert "loads_M200AL-020.txt" in message, message
        assert "'1'" in message and "'2'" in message, message


def test_goal028_rename_stems_across_cases_two_conditions_are_two_stems(tmp_path):
    """THE CONTROL: the same two cases at two Mach numbers render two stems and plan READY."""
    plan = _plan(_campaign(tmp_path, machs=(0.2, 0.3)), CampaignWorkspace(tmp_path / "camp"))

    assert [point.status for point in plan.points] == [PlanStatus.READY, PlanStatus.READY], (
        plan.summary()
    )
    assert [point.script_name for point in plan.points] == ["M200AL-020.txt", "M300AL-020.txt"]


def test_goal028_rename_stems_across_cases_the_matrix_naming_is_not_affected(tmp_path):
    """`{polar}` carries `P<sim>-`, so one condition in two cases is still two stems."""
    workspace = CampaignWorkspace(
        tmp_path / "camp", naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )

    plan = _plan(_campaign(tmp_path, outputs=("{name}.txt",)), workspace)

    assert [point.status for point in plan.points] == [PlanStatus.READY, PlanStatus.READY], (
        plan.summary()
    )
    assert [point.script_name for point in plan.points] == [
        "P1-M200AL-020.txt",
        "P2-M200AL-020.txt",
    ]
