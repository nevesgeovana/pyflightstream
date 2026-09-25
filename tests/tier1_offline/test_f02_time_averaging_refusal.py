"""F02, and G25 of 0.28.0: the command that hangs 26.124 is never emitted.

The 2026-09-19 measurement (C01) is why: ``SOLVER_TIME_AVERAGING`` hangs
FlightStream 26.124 in the position the package emitted it. Until 0.28.0 the
package refused ``[time_averaging]`` at plan on every build whose record of the
command is not verified. Since 0.28.0 the package averages the per-step exports
itself (G25), so the table plans on 26.124 and the command is emitted nowhere,
not under a waiver and not on a build that verified it. Four revolutions at 10
degrees give 144 steps, so the last 54 steps (or 1.5 revolutions) are
independently 91 through 144.
"""

import sys

import pytest

from pyflightstream.cases import Campaign
from pyflightstream.cases.workflows import build_script
from pyflightstream.commands import CommandRegistry, Status, VersionStatus
from pyflightstream.run import PlanStatus, plan_campaign
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_surface_exports import _case


def test_database_records_the_measured_hang():
    record = CommandRegistry.load().commands["SOLVER_TIME_AVERAGING"].versions["26.124"]
    assert record.status is Status.BROKEN, "26.124 must record the measured hang as broken"
    assert "2026-09-19" in record.note
    assert "hang" in record.note.lower()


def test_plan_accepts_the_window_on_26124_and_the_script_never_carries_the_hang(tmp_path):
    case = _case(rotor=True, time_averaging={"last_revs": 1.5})
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(
        campaign, workspace, recipes={"unsteady_rotor": build_script}, write_plan=False
    )
    assert len(plan.points) == 1
    point = plan.points[0]
    assert point.status is PlanStatus.READY, point.error
    script = Script("26.124")
    build_script(case, script)
    assert "SOLVER_TIME_AVERAGING" not in script.render()
    assert script.surface_average_window is not None
    assert script.surface_average_window["iterations"] == [91, 144]


def test_even_a_low_level_waiver_emits_nothing_of_it():
    script = Script("26.124")
    script.allow_broken("SOLVER_TIME_AVERAGING", reason="synthetic low-level probe waiver")
    build_script(_case(rotor=True, time_averaging={"last_iters": 54}), script)
    assert "SOLVER_TIME_AVERAGING" not in script.render()
    assert script.surface_time_averaging is None


@pytest.mark.parametrize("build", ["26.122", "26.123", "26.124"])
@pytest.mark.parametrize("window", [{"last_iters": 54}, {"last_revs": 1.5}])
def test_even_a_verified_build_never_emits_it_and_the_window_is_the_packages(build, window):
    registry = CommandRegistry.load()
    entry = registry.commands["SOLVER_TIME_AVERAGING"]
    case = _case(rotor=True, time_averaging=window, formats=False)
    record = VersionStatus(
        status=Status.VERIFIED,
        report="synthetic-test-report.yaml",
        note="Synthetic per-build execution evidence for this test only.",
    )
    changed = entry.model_copy(update={"versions": {**entry.versions, build: record}})
    database = CommandRegistry(commands={**registry.commands, entry.name: changed})
    script = Script(build, registry=database)
    build_script(case, script, registry=database)
    assert "SOLVER_TIME_AVERAGING" not in script.render()
    assert script.surface_average_window is not None
    assert script.surface_average_window["iterations"] == [91, 144]
    assert "verification" not in script.surface_average_window
