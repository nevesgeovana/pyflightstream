"""P0400-WSRENAME: the numbered group product migration reads products only.

0.40.0 lane workspace-1.

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import pytest

from pyflightstream.workspace import _make_dir_link, rename_group_products, unmapped_group_numbers

pytestmark = pytest.mark.requirement("P0400-WSRENAME")


def _workspace(tmp_path):
    polars = tmp_path / "post" / "matriz" / "polars"
    polars.mkdir(parents=True)
    (polars / "P0001-M150_g01.csv").write_text("one\n", encoding="utf-8")
    profile = tmp_path / "inputs" / "profiles" / "blade_g1.csv"
    profile.parent.mkdir(parents=True)
    profile.write_text("r,c\n", encoding="utf-8")
    solver = tmp_path / "sims" / "sim_1" / "datapoints" / "DP-A" / "loads_g01.dat"
    solver.parent.mkdir(parents=True)
    solver.write_text("x\n", encoding="utf-8")
    return polars, profile, solver


def test_p0400_wsrename_inputs_and_simulations_are_never_renamed(tmp_path):
    """P0400-WSRENAME (PFS-2096.012): a row's PROFILE and a solver file keep their names."""
    polars, profile, solver = _workspace(tmp_path)
    assert unmapped_group_numbers(tmp_path, {}) == {1: [polars / "P0001-M150_g01.csv"]}
    moved = rename_group_products(tmp_path, {1: "PUSHER"})
    assert [item.after for item in moved] == [polars / "P0001-M150_PUSHER.csv"]
    assert profile.is_file() and solver.is_file()


def test_p0400_wsrename_a_linked_folder_is_not_walked_twice(tmp_path):
    """P0400-WSRENAME (PFS-2096.012): a junction to the products plans each file once."""
    polars, _, _ = _workspace(tmp_path)
    _make_dir_link(polars, tmp_path / "post" / "linked")
    moved = rename_group_products(tmp_path, {1: "PUSHER"}, dry_run=True)
    assert [item.before for item in moved] == [polars / "P0001-M150_g01.csv"]
