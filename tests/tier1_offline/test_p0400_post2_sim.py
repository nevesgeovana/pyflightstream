"""P0400-GROUPKEY: a rotor integration-group clash writes no group polar.

At the 0.40.0 base a rotor integration-group clash was recorded as a skip
while every group polar, the clashing one included, was still written.
"""

from __future__ import annotations

from types import SimpleNamespace

import pyflightstream.post._sim as sim


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
