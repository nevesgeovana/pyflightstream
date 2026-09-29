"""Tier 1: the fixed-wing and quasi-steady-rotor coupling steps share one step body."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pyflightstream.fsi import driver


def test_both_steady_routes_go_through_the_one_shared_step(monkeypatch):
    # P0310-A2-STEP
    calls: list[dict[str, object]] = []
    sentinel = object()

    def shared(run_dir, cfg, state, **kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(driver, "_steady_coupling_step", shared)
    cfg = SimpleNamespace(omega_rad_per_s=10.0)
    assert driver._fixed_wing_step(Path("run"), cfg, None) is sentinel
    assert driver._quasi_steady_rotor_step(Path("run"), cfg, None) is sentinel
    assert [call["phase"] for call in calls] == [
        driver.FIXED_WING_PHASE,
        driver.QUASI_STEADY_ROTOR_PHASE,
    ]
    # The structural solve is the variation point: one callable per route, distinct.
    solves = [call["solve"] for call in calls]
    assert all(callable(solve) for solve in solves) and solves[0] is not solves[1]
    # Only the wing holds the export to a configured time increment.
    assert [call["check_time_increment"] for call in calls] == [True, False]
