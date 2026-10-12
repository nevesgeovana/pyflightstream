"""P0400-REDSKIP: the reduction stage records its skips under the files it would write.

At the 0.40.0 base a recorded window holding a non-number was cast outside the
guarded block, so it ended the whole post; and a per-revolution read failure of a
plan with a rotors block was keyed under the single-rotor file name that plan
never writes.
"""

from __future__ import annotations

from pyflightstream.post._reduction_stage import (
    _judged_reduction_windows,
    _ReductionProducts,
    _write_point_revolutions,
)


def _ctx(tmp_path, plan):
    return _ReductionProducts(
        plots_table=tmp_path / "absent_plots.csv",
        plan=plan,
        out=tmp_path,
        runs=[],
        target=lambda path: path,
        written=[],
        written_names={},
        skipped={},
        condition=None,
        reference=None,
        rotor_facts=None,
        names=None,
        frozen=None,
        pol=None,
        stem="P1",
    )


def test_p0400_redskip_a_malformed_window_is_a_skip_of_its_reduction(tmp_path):
    """P0400-REDSKIP: a window holding a non-number is a named skip, not an abort."""
    ctx = _ctx(tmp_path, {})
    relative = "probes/P1_time_average.csv"
    entry = {"windows": [["ten", 20]]}
    assert _judged_reduction_windows(ctx, "time_average", entry, relative, None) is None
    assert "not whole numbers" in ctx.skipped[relative]


def test_p0400_redskip_per_revolution_failure_is_keyed_per_rotor(tmp_path):
    """P0400-REDSKIP: a rotors plan records the read failure under each rotor's file."""
    plan = {"rotors": {"PROP": {"steps_per_revolution": 36}, "TAIL": {"steps_per_revolution": 24}}}
    ctx = _ctx(tmp_path, plan)
    _write_point_revolutions(ctx, None)
    assert sorted(ctx.skipped) == [
        "probes/P1_per_revolution_PROP.csv",
        "probes/P1_per_revolution_TAIL.csv",
    ]


def test_p0400_redskip_single_rotor_failure_keeps_its_file_name(tmp_path):
    """P0400-REDSKIP control: a phase-locked plan keeps the single-rotor name."""
    ctx = _ctx(tmp_path, {"phase_locked": {}, "steps_per_revolution": 36})
    _write_point_revolutions(ctx, None)
    assert list(ctx.skipped) == ["probes/P1_per_revolution.csv"]
