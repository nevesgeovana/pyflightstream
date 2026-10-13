"""Continuation thresholds must be reached by the continued march's local counter."""

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import unsteady_export_threshold
from pyflightstream.run._actions_counter import render_program
from tests.tier1_offline.test_restart_continuation import SAVED, _continuing_case

pytestmark = pytest.mark.requirement("P0400-LAST6-CONTINUATION")


def _case(key, value, offset=250, owed=150):
    return _continuing_case(
        "{FINISH_PENDING}",
        RESTART_FROM=SAVED,
        RESTART_ITERATIONS=str(owed),
        RESTART_STEP_OFFSET=str(offset),
        **{key: str(value)},
    )


def test_p0400_last6_some_owed_count_reaches_last_iter_threshold(tmp_path):
    threshold = unsteady_export_threshold(_case("EXPORT_UNSTEADY_LAST_ITER", 100), version="26.124")
    scope = {"__file__": str(tmp_path / "counter.py"), "__name__": "counter"}
    exec(compile(render_program(threshold, interpreter="python"), "counter.py", "exec"), scope)
    assert any(scope["state"](count)["exporting"] for count in range(1, 151)), "P0400-LAST6-OWED"
    assert threshold.first_step == 51


@pytest.mark.parametrize(
    "key,value,first",
    [
        ("EXPORT_UNSTEADY_LAST_ITER", 100, 51),
        ("EXPORT_UNSTEADY_AFTER_ITER", 300, 50),
    ],
)
def test_p0400_last6_last_and_after_iter_are_rebased(key, value, first):
    threshold = unsteady_export_threshold(_case(key, value), version="26.124")
    assert threshold.first_step == first, "P0400-LAST6-REBASE"
    assert threshold.time_iterations == 150
    assert threshold.program_value == first


def test_p0400_last6_threshold_in_the_completed_span_is_refused():
    with pytest.raises(CampaignConfigError, match="already"):
        unsteady_export_threshold(_case("EXPORT_UNSTEADY_AFTER_ITER", 200), version="26.124")


def test_p0400_last6_additional_run_last_window_ends_at_the_new_end():
    case = _case("EXPORT_UNSTEADY_LAST_ITER", 50, offset=400, owed=120)
    case.variables["RESTART"] = "{ADDITIONAL_ITERS=120}"
    threshold = unsteady_export_threshold(case, version="26.124")
    assert threshold.first_step == 71, "P0400-LAST6-ADDITIONAL"


def test_p0400_last6_legacy_chain_sums_its_predecessor_steps(tmp_path):
    from pyflightstream.run._continuation import _continued_step_offset
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_restart_continuation import _stopped_record

    workspace = CampaignWorkspace.init(tmp_path / "chain")
    root = _stopped_record()
    child = root.model_copy(
        update={
            "run_id": "camp/sim_9001/rfirst/AL+000",
            "continues": root.run_id,
            "stopped_at": {"step": 20},
        }
    )
    workspace.append_record(root)
    workspace.append_record(child)
    assert _continued_step_offset(workspace, child) == 270, "P0400-LAST6-CHAIN"


def test_p0400_last6_resolved_offset_reaches_the_planned_counter(tmp_path):
    from pyflightstream.cases import Campaign
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.run import plan_campaign
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_restart_continuation import _stopped_record

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    previous = _stopped_record()
    workspace.append_record(previous)
    saved = workspace.sim_dir("9001") / previous.outputs[0]
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"saved")
    case = _continuing_case("{FINISH_PENDING}", EXPORT_UNSTEADY_LAST_ITER="100")
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe="solver.exe", sims=[case])
    seen = []

    def recipe(case, script):
        seen.append(unsteady_export_threshold(case, version=script.version))
        build_script(case, script)

    plan = plan_campaign(campaign, workspace, recipes={"unsteady": recipe}, write_plan=False)
    assert not plan.blocked, "P0400-LAST6-PLAN-OFFSET"
    assert seen[0].step_offset == 250
    assert seen[0].first_step == 51


def test_p0400_last6_rebased_step_is_written_to_the_run_record(tmp_path):
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.run._actions_counter import stage_counter
    from pyflightstream.script import Script

    case = _case("EXPORT_UNSTEADY_LAST_ITER", 100)
    script = Script("26.124")
    build_script(case, script)
    for name, text in script.pending_action_scripts.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    fields = stage_counter(tmp_path, script, case, "26.124", {})
    assert fields["export_window"]["first_step"] == 51, "P0400-LAST6-PERSISTED-REBASE"
    assert fields["export_window"]["time_iterations"] == 150
    assert fields["export_window"]["step_offset"] == 250
