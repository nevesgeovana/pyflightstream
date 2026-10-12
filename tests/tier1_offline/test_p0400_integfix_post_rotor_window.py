"""P0400-ROTORWINDOW: each rotor of a rotor table is averaged over its own turns.

At the 0.40.0 base the rotor table averaged every rotor of a row over the row's
window, which is counted on the clock rotor, so a second rotor at another speed
was averaged over a non-integer number of its own revolutions while its
per-blade and per-revolution reductions were cut on its own clock (FR-68;
PFS-2088.013, PFS-2081.30).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pyflightstream.post import _rotor_plan

#: Clock rotor PUSH at 100 steps a turn, LIFT at 150; the run ends at step 1000.
_PLAN = {
    "time_iterations": 1000,
    "steps_per_revolution": 100,
    "rotors": {"PUSH": {"steps_per_revolution": 100}, "LIFT": {"steps_per_revolution": 150}},
}


def _ctx(tmp_path, variables, row_span=(801, 1000)):
    return SimpleNamespace(
        windows={"AL-000": row_span},
        window=row_span,
        by_run={"r1": SimpleNamespace(reductions=_PLAN)},
        sources={"AL-000": ["r1"]},
        matrix_row=SimpleNamespace(variables=variables),
        plots={"AL-000": tmp_path / "no_plots_table.csv"},
    )


def _span_used(ctx, alias):
    """The window the averaging reads, as its refusal names it (no plots table here)."""
    point = SimpleNamespace(name="AL-000")
    newtons, reason, _group = _rotor_plan._averaged_rotor_newtons(ctx, point, alias, [])
    assert newtons is None
    return reason.rsplit("over steps ", 1)[1]


@pytest.mark.parametrize(("alias", "span"), [("PUSH", "801 to 1000"), ("LIFT", "701 to 1000")])
def test_p0400_rotorwindow_last_revs_avg_counts_each_rotors_own_turns(tmp_path, alias, span):
    """P0400-ROTORWINDOW (PFS-2088.013): 2 turns are 200 steps of PUSH and 300 of LIFT."""
    assert _span_used(_ctx(tmp_path, {"LAST_REVS_AVG": "2"}), alias) == span


def test_p0400_rotorwindow_last_iters_avg_is_the_same_steps_for_every_rotor(tmp_path):
    """P0400-ROTORWINDOW control: a count of iterations does not depend on the rotor."""
    ctx = _ctx(tmp_path, {"LAST_ITERS_AVG": "200"})
    assert {_span_used(ctx, alias) for alias in ("PUSH", "LIFT")} == {"801 to 1000"}


def test_p0400_rotorwindow_the_entry_states_each_points_window_of_the_rotor(tmp_path):
    """P0400-ROTORWINDOW (PFS-2088.013): the manifest's windows are this rotor's own."""
    ctx = _ctx(tmp_path, {"LAST_REVS_AVG": "2"})
    assert _rotor_plan._rotor_windows(ctx, "LIFT") == {"AL-000": (701, 1000)}
    assert _rotor_plan._rotor_windows(ctx, "PUSH") == {"AL-000": (801, 1000)}
