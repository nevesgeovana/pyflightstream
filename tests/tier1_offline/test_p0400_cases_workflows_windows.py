"""Regression evidence for public and per-rotor averaging windows."""

import pytest

from pyflightstream.cases import windows as recorded_windows
from pyflightstream.cases.workflows import (
    ExportWindow,
    export_window,
    reduction_plan,
    reduction_windows,
)
from tests.tier1_offline.test_reduce_by_rotor import transition_case


def test_p0400_cw_windows_each_rotors_passages_use_its_own_span():
    """P0400-CW-WINDOWS (PFS-2088.011): both passage products use that rotor's turns."""
    requirement = "P0400-CW-WINDOWS"
    case = transition_case()
    case.variables["LAST_REVS_AVG"] = "1"
    plan = reduction_windows(case)
    assert plan is not None, requirement
    pusher = plan["rotors"]["PUSHER"]
    span = pusher["per_blade"]["windows"][0]
    windows = pusher["phase_locked"]["windows"]
    assert windows[0][0] == span[0], requirement
    assert windows[-1][1] <= span[1]
    assert span == [54, 720]


def test_p0400_cw_windows_public_window_clamps_like_the_live_window():
    """P0400-CW-WINDOWS (PFS-2098.002): the public window agrees with recorded reductions."""
    requirement = "P0400-CW-WINDOWS"
    window = export_window(steps=1000, time_iterations=720)
    assert window.window_steps() == (1, 720), requirement
    assert window.steps == 720
    assert window.stated_value == 1000.0


def test_p0400_cw_windows_each_rotors_legacy_fallback_is_its_own_turn():
    """P0400-CW-WINDOWS (PFS-2088.011): an absent averaging key keeps one physical turn."""
    requirement = "P0400-CW-WINDOWS"
    plan = reduction_windows(transition_case())
    pusher = plan["rotors"]["PUSHER"]
    assert pusher["per_blade"]["windows"] == [[54, 720]], requirement
    assert pusher["phase_locked"]["windows"][0][0] == 54


def test_p0400_cw_windows_the_public_reduction_plan_clamps_too():
    """P0400-CW-WINDOWS (PFS-2098.002): the public plan accepts the live path's window."""
    requirement = "P0400-CW-WINDOWS"
    from tests.tier1_offline.test_p0400_cases_workflows_reductions import _row

    case = _row(LAST_REVS_AVG="100")
    assert reduction_plan(case).window.window_steps() == (1, 288), requirement


def test_p0400_cw_windows_a_public_window_uses_the_case_clock():
    """P0400-CW-WINDOWS (PFS-2098.002): a non-clock rotor cannot supply the row's clock."""
    requirement = "P0400-CW-WINDOWS"
    case = transition_case()
    case.variables.update({"LAST_REVS_AVG": "2"})
    public = ExportWindow.from_case(case)
    live = reduction_windows(case)
    assert public.window_steps() == tuple(live["time_average"]["windows"][0]), requirement
    assert public.steps_per_revolution == pytest.approx(live["steps_per_revolution"])


def _fractional_row():
    from tests.tier1_offline.test_p0400_cases_workflows_reductions import _row

    case = _row(DELTA_THETA="10", REVOLUTIONS="4", LAST_REVS_AVG="4")
    block = case.rotors["ROTOR"].model_copy(
        update={"families_blades": [f"Blade{number}" for number in range(1, 8)]}
    )
    return case.model_copy(update={"rotors": {"ROTOR": block}})


def test_p0400_cw_windows_fractional_passages_do_not_accumulate_rounding():
    """P0400-CW-WINDOWS (PFS-2081.19): passage boundaries follow physical turns."""
    requirement = "P0400-CW-WINDOWS"
    case = _fractional_row()
    # Seven passages complete one 36-step turn, without rounding each to five.
    plan = reduction_windows(case)
    cut = plan["phase_locked"]["windows"]
    assert cut[:4] == [[1, 5], [6, 10], [11, 15], [16, 20]], requirement
    assert cut[6][1] == 36
    assert cut[13][1] == 72
    assert cut[20][1] == 108


def test_p0400_cw_windows_post_replanning_keeps_the_rotors_own_span():
    """P0400-CW-WINDOWS (PFS-2088.011): post must not overwrite the rotor's span."""
    requirement = "P0400-CW-WINDOWS"
    case = transition_case()
    case.variables["LAST_REVS_AVG"] = "1"
    plan = reduction_windows(case)
    fresh = recorded_windows.replan(plan, case.variables)
    pusher = fresh["rotors"]["PUSHER"]
    assert pusher["phase_locked"]["windows"][0][0] == 54, requirement
    assert pusher["per_blade"]["windows"] == [[54, 720]]


def test_p0400_cw_windows_post_replanning_preserves_fractional_passages():
    """P0400-CW-WINDOWS (PFS-2081.19): replanning cannot round the passage period."""
    requirement = "P0400-CW-WINDOWS"
    case = _fractional_row()
    fresh = recorded_windows.replan(reduction_windows(case), case.variables)
    assert fresh["phase_locked"]["windows"][6][1] == 36, requirement
    assert fresh["phase_locked"]["windows"][13][1] == 72
