"""P0400-GROUPKEY: one group's polar failure on a point is keyed under that polar.

At the 0.40.0 base a group whose polar rows could not be built for one point
filed the failure under ``runs/<run id>``, the key that means no product holds
the run. The point is a miss of THAT group's polar, ``polars/<file>#<point>``,
as the absent-surface case already was; a point failing every group gives one
such skip per group, never a whole-run refusal (PFS-2088.012).
"""

from __future__ import annotations

from types import SimpleNamespace

import pyflightstream.post._sim as sim
from pyflightstream._errors import ProductError


def _ctx() -> SimpleNamespace:
    point = SimpleNamespace(name="AL-020", loads=SimpleNamespace(surfaces={"W": None}))
    return SimpleNamespace(
        points=[point],
        conditions=[{}],
        aliases={},
        mach=0.2,
        reference=None,
        record_of={"AL-020": SimpleNamespace(run_id="camp/sim_7001/AL-020")},
        skipped={},
    )


def test_p0400_groupkey_one_groups_failure_is_keyed_under_its_polar(monkeypatch):
    """P0400-GROUPKEY (PFS-2088.012): the point is a miss of THIS group, not a refused run."""

    def refuse(*_args, **_kwargs):
        raise ProductError("no Reynolds number")

    monkeypatch.setattr(sim, "select_group_members", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(sim, "group_polar_rows", refuse)
    ctx = _ctx()
    group_points, _conditions, rows, absent = sim._group_rows(ctx, "1", ["W"])
    assert group_points == [] and rows == []
    assert "no Reynolds number" in absent["AL-020"]
    assert not any(key.startswith("runs/") for key in ctx.skipped)


def test_p0400_groupkey_a_point_failing_every_group_is_skipped_per_group(monkeypatch):
    """P0400-GROUPKEY (PFS-2088.012): each group records its own miss; none overwrites another."""

    def refuse(_points, families, **_kwargs):
        raise ProductError(f"group {families[0]} has no Reynolds number")

    monkeypatch.setattr(sim, "select_group_members", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(sim, "group_polar_rows", refuse)
    ctx = _ctx()
    reasons = {group: sim._group_rows(ctx, group, [group])[3] for group in ("WING", "TAIL")}
    assert "group WING" in reasons["WING"]["AL-020"]
    assert "group TAIL" in reasons["TAIL"]["AL-020"]
    assert ctx.skipped == {}
