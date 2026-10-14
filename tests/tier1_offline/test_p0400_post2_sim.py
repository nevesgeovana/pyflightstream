"""P0400-GROUPKEY: a rotor integration-group clash writes no group polar.

At the 0.40.0 base a rotor integration-group clash was recorded as a skip
while every group polar, the clashing one included, was still written.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import pyflightstream.post._sim as sim


def test_p0400_groupkey_a_rotor_group_clash_writes_no_group_polar(monkeypatch):
    """P0400-GROUPKEY: a declared group disagreeing with a rotor stops every group polar."""
    drawn: list[str] = []
    monkeypatch.setattr(sim, "_group_polar", lambda _ctx, group, *_rest, **_kw: drawn.append(group))
    ctx = SimpleNamespace(
        pproc=SimpleNamespace(
            products=SimpleNamespace(polars=True), groups={"PORT": ["Wing"], "1": ["all"]}
        ),
        live=SimpleNamespace(rotors={"PORT": SimpleNamespace(members=["Blade1"])}),
        window=None,
        points=[],
        skipped={},
        sim_id="7001",
    )
    sim._group_polars(ctx)
    assert drawn == []
    assert "No group polar of simulation '7001'" in ctx.skipped["polars/7001"]


def test_p0400_groupkey_agreeing_groups_are_all_drawn(monkeypatch):
    """P0400-GROUPKEY control: with no clash every group, the rotor's included, is drawn."""
    from pyflightstream.results import parse_loads
    from tests.tier1_offline.test_post_products import LOADS

    drawn: list[str] = []
    # `instant` is the keyword the instant group polars of PFS-2105.011 pass.
    monkeypatch.setattr(sim, "_group_polar", lambda _ctx, group, *_rest, **_kw: drawn.append(group))
    ctx = SimpleNamespace(
        pproc=SimpleNamespace(products=SimpleNamespace(polars=True), groups={"1": ["all"]}),
        live=SimpleNamespace(rotors={"PORT": SimpleNamespace(members=["Blade1"])}),
        window=None,
        points=[],
        skipped={},
        sim_id="7001",
    )
    sim._group_polars(ctx)
    assert drawn == ["1", "PORT"] and ctx.skipped == {}
    instant_groups = {}
    monkeypatch.setattr(
        sim,
        "_group_polar",
        lambda _ctx, group, *_rest, **kw: instant_groups.update({group: kw.get("instant")}),
    )
    ctx.points = [SimpleNamespace(name="P", loads=parse_loads(LOADS), vorticity_selection=None)]
    ctx.record_of = {"P": SimpleNamespace(recipe="unsteady")}
    with pytest.warns(sim.PyflightstreamWarning, match="LAST TIME STEP"):
        sim._group_polars(ctx)
    assert instant_groups == {"1": True, "PORT": True}
