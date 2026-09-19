"""The plan policy and MRP declaration reader each have one home."""

import copy

import pytest

from pyflightstream.cases import PhaseLockedSpec, PprocSpec, windows
from pyflightstream.post.products import global_frame_plot_groups


@pytest.mark.parametrize(
    "gate, last, span, expected",
    [
        (
            PhaseLockedSpec(min_revolutions=4, last_revolutions_avg=2),
            30,
            (21, 30),
            {
                "skipped": (
                    "the row turns 3.0 revolution(s) over the whole run and the pproc asks "
                    "for at least 4.0 before a phase-locked reduction is generated. The "
                    "polar is unaffected: a short run means no phase-locked reduction, "
                    "never a refused product."
                ),
                "min_revolutions": 4.0,
                "revolutions_turned": 3.0,
            },
        ),
        (
            PhaseLockedSpec(min_revolutions=4, last_revolutions_avg=2),
            40,
            (31, 40),
            {
                "windows": [[21, 40]],
                "shape": "azimuthal",
                "revolutions": 2.0,
                "steps_per_revolution": 10.0,
                "window_from": (
                    "the last 2 revolution(s) of PROP, which the pproc's [phase_locked] "
                    "table states as last_revolutions_avg; the mean is taken at each "
                    "azimuth across them"
                ),
            },
        ),
        (
            None,
            40,
            (31, 40),
            {
                "windows": [[31, 35], [36, 40]],
                "period_steps": 5,
                "window_from": "the row's window cut into blade passages of PROP, 5 steps each",
            },
        ),
        (
            None,
            40,
            (38, 40),
            {
                "skipped": (
                    "the window 38 to 40 holds 3 steps, fewer than one blade passage of "
                    "PROP, which is 5 steps"
                ),
            },
        ),
    ],
)
def test_phase_locked_policy(gate, last, span, expected):
    assert hasattr(windows, "phase_locked_plan"), "phase-locked policy has no single entry point"
    assert (
        windows.phase_locked_plan(
            gate, last_step=last, per_revolution=10, who="PROP", span=span, period=5
        )
        == expected
    )


@pytest.mark.parametrize("last", [30, 40])
def test_replan_alone_preserves_the_recorded_gate(last):
    entry = (
        {"skipped": "below the minimum", "min_revolutions": 4.0, "revolutions_turned": 3.0}
        if last == 30
        else {
            "windows": [[21, 40]],
            "shape": "azimuthal",
            "revolutions": 2.0,
            "steps_per_revolution": 10.0,
        }
    )
    plan = {
        "time_iterations": last,
        "steps_per_revolution": 10,
        "period_steps": 5,
        "time_average": {"windows": [[1, last]]},
        "phase_locked": entry,
    }
    original = copy.deepcopy(plan)
    result = windows.replan(plan, {"LAST_ITERS_AVG": 5})
    assert result["phase_locked"] == entry, "replan overwrote the recorded phase-locked gate"
    assert plan == original


@pytest.mark.parametrize("name, expected", [("TOTAL", ("TOTAL",)), ("LOAD_{family}", ())])
def test_mrp_reader_agrees_with_run_and_post(tmp_path, name, expected):
    from tests.tier1_offline.test_goal028_uns_axes import _plot_names, _script_of

    plots = {
        "parameters": ["FX", "FY", "FZ", "MX", "MY", "MZ"],
        "groups": [{"name": name, "frame": "MRP", "families": "each" if "{" in name else "all"}],
    }
    pproc = PprocSpec.model_validate({"plots": plots})
    emitted = _plot_names(_script_of(tmp_path, plots))
    assert "FX_MRP_TOTAL" not in emitted
    assert global_frame_plot_groups(pproc) == expected
    from pyflightstream.cases import global_frame_plot_declarations

    assert tuple(group.name for group in global_frame_plot_declarations(pproc)) == (name,)


def test_planner_calls_policy_once_per_rotor(monkeypatch):
    from pyflightstream.cases.workflows import reduction_windows
    from tests.tier1_offline.test_reduce_by_rotor import transition_case

    assert hasattr(windows, "phase_locked_plan"), "phase-locked policy has no single entry point"
    original = windows.phase_locked_plan
    calls = []

    def policy(*args, **kwargs):
        calls.append(kwargs["who"])
        return original(*args, **kwargs)

    monkeypatch.setattr(windows, "phase_locked_plan", policy)
    reduction_windows(transition_case())
    assert calls == ["LIFT_L1", "PUSHER"]


@pytest.mark.parametrize("operation", ["replan", "regate"])
def test_post_calls_policy_once_per_rotor(monkeypatch, operation):
    assert hasattr(windows, "phase_locked_plan"), "phase-locked policy has no single entry point"
    original = windows.phase_locked_plan
    calls = []

    def policy(*args, **kwargs):
        calls.append(kwargs["who"])
        return original(*args, **kwargs)

    monkeypatch.setattr(windows, "phase_locked_plan", policy)
    plan = {
        "time_iterations": 40,
        "steps_per_revolution": 10,
        "time_average": {"windows": [[31, 40]]},
        "rotors": {
            "FAST": {
                "steps_per_revolution": 10,
                "period_steps": 5,
                "phase_locked": {"windows": [[31, 35], [36, 40]]},
            },
            "SLOW": {
                "steps_per_revolution": 20,
                "period_steps": 10,
                "phase_locked": {"windows": [[31, 40]]},
            },
        },
    }
    gate = PhaseLockedSpec(min_revolutions=3, last_revolutions_avg=2)
    saved = copy.deepcopy(plan)
    if operation == "replan":
        result = windows.replan(plan, {"LAST_ITERS_AVG": 5}, gate=gate)
    else:
        result = windows.regate(plan, gate)
    assert calls == ["FAST", "SLOW"]
    assert result["rotors"]["FAST"]["phase_locked"]["windows"] == [[21, 40]]
    assert result["rotors"]["SLOW"]["phase_locked"]["revolutions_turned"] == 2.0
    assert "skipped" in result["rotors"]["SLOW"]["phase_locked"]
    assert plan == saved
