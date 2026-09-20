"""F02: the 2026-09-19 hang is a planning refusal, not solver work.

The licensed comparison on 26.124 is the refusal oracle. Synthetic evidence
isolates the per-build gate; four revolutions at 10 degrees give 144 steps,
so the last 54 steps (or 1.5 revolutions) are independently 91 through 144.
"""

import sys

import pytest

from pyflightstream.cases import Campaign, CampaignConfigError
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


def test_plan_refuses_26124_and_names_the_hang_and_recovery(tmp_path):
    case = _case(rotor=True, time_averaging={"last_revs": 1.5})
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(
        campaign, workspace, recipes={"unsteady_rotor": build_script}, write_plan=False
    )
    assert len(plan.points) == 1
    point = plan.points[0]
    assert point.status is PlanStatus.BLOCKED, "[time_averaging] must be refused at plan"
    for token in ("26.124", "SOLVER_TIME_AVERAGING", "2026-09-19", "hang", "instant", "verified"):
        assert token in point.error, f"planning refusal must include {token!r}: {point.error}"
    assert workspace.read_manifest() == []
    assert list((workspace.sim_dir(case.sim_id) / "scripts").iterdir()) == []


def test_refusal_precedes_emission_even_with_a_low_level_waiver():
    script = Script("26.124")
    script.allow_broken("SOLVER_TIME_AVERAGING", reason="synthetic low-level probe waiver")
    before = script.render()
    with pytest.raises(CampaignConfigError, match="26.124"):
        build_script(_case(rotor=True, time_averaging={"last_iters": 54}), script)
    assert script.render() == before, "the refusal must precede the first command"


@pytest.mark.parametrize("build", ["26.122", "26.123", "26.124"])
@pytest.mark.parametrize("window", [{"last_iters": 54}, {"last_revs": 1.5}])
def test_only_verified_build_status_allows_the_window_to_emit(build, window):
    registry = CommandRegistry.load()
    entry = registry.commands["SOLVER_TIME_AVERAGING"]
    case = _case(rotor=True, time_averaging=window, formats=False)

    def script_with_status(status):
        record = VersionStatus(
            status=status,
            report="synthetic-test-report.yaml" if status is Status.VERIFIED else None,
            note="Synthetic per-build execution evidence for this test only.",
        )
        changed = entry.model_copy(update={"versions": {**entry.versions, build: record}})
        database = CommandRegistry(commands={**registry.commands, entry.name: changed})
        return Script(build, registry=database), database

    unverified, database = script_with_status(Status.DOCUMENTED)
    with pytest.raises(CampaignConfigError, match=build):
        build_script(case, unverified, registry=database)

    verified, database = script_with_status(Status.VERIFIED)
    build_script(case, verified, registry=database)
    text = verified.render()
    assert "SOLVER_TIME_AVERAGING ENABLE 91 144" in text
    assert text.index("SOLVER_TIME_AVERAGING") < text.index("INITIALIZE_SOLVER")
    assert verified.surface_time_averaging["iterations"] == [91, 144]
