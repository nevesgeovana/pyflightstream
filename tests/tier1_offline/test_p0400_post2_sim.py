"""P0400-GROUPKEY: the group polars' refusals are keyed where they belong.

At the 0.40.0 base one group's failure on one point was filed under
``runs/<run id>``, the key that means no product holds the run, and a rotor
integration-group clash was recorded as a skip while every group polar,
the clashing one included, was still written.
"""

from __future__ import annotations

from types import SimpleNamespace

import pyflightstream.post._sim as sim
from pyflightstream._errors import ProductError


def test_p0400_groupkey_one_groups_failure_is_keyed_under_its_polar(monkeypatch):
    """P0400-GROUPKEY: the point is a miss of THIS group, not a refused run."""

    def refuse(*_args, **_kwargs):
        raise ProductError("no Reynolds number")

    monkeypatch.setattr(sim, "select_group_members", lambda *_args: True)
    monkeypatch.setattr(sim, "group_polar_rows", refuse)
    point = SimpleNamespace(name="AL-020", loads=SimpleNamespace(surfaces={"W": None}))
    ctx = SimpleNamespace(
        points=[point],
        conditions=[{}],
        aliases={},
        mach=0.2,
        reference=None,
        record_of={"AL-020": SimpleNamespace(run_id="camp/sim_7001/AL-020")},
        skipped={},
    )
    group_points, _conditions, rows, absent = sim._group_rows(ctx, "1", ["W"])
    assert group_points == [] and rows == []
    assert "no Reynolds number" in absent["AL-020"]
    assert not any(key.startswith("runs/") for key in ctx.skipped)


def test_p0400_groupkey_a_rotor_group_clash_writes_no_group_polar(monkeypatch):
    """P0400-GROUPKEY: a declared group disagreeing with a rotor stops every group polar."""
    drawn: list[str] = []
    monkeypatch.setattr(sim, "_group_polar", lambda _ctx, group, *_rest: drawn.append(group))
    ctx = SimpleNamespace(
        pproc=SimpleNamespace(
            products=SimpleNamespace(polars=True), groups={"PORT": ["Wing"], "1": ["all"]}
        ),
        live=SimpleNamespace(rotors={"PORT": SimpleNamespace(members=["Blade1"])}),
        window=None,
        skipped={},
        sim_id="7001",
    )
    sim._group_polars(ctx)
    assert drawn == []
    assert "No group polar of simulation '7001'" in ctx.skipped["polars/7001"]


def test_p0400_groupkey_agreeing_groups_are_all_drawn(monkeypatch):
    """P0400-GROUPKEY control: with no clash every group, the rotor's included, is drawn."""
    drawn: list[str] = []
    monkeypatch.setattr(sim, "_group_polar", lambda _ctx, group, *_rest: drawn.append(group))
    ctx = SimpleNamespace(
        pproc=SimpleNamespace(products=SimpleNamespace(polars=True), groups={"1": ["all"]}),
        live=SimpleNamespace(rotors={"PORT": SimpleNamespace(members=["Blade1"])}),
        window=None,
        skipped={},
        sim_id="7001",
    )
    sim._group_polars(ctx)
    assert drawn == ["1", "PORT"] and ctx.skipped == {}
