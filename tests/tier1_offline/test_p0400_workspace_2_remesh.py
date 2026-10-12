"""P0400-REMESHRECORD: a remesh group's record is strict JSON."""

from __future__ import annotations

import json

import pytest

from pyflightstream.workspace._refine._obj import read_obj
from pyflightstream.workspace._refine._remesh import refine_group

pytest.importorskip("trimesh")


def test_p0400_remeshrecord_a_group_of_curve_edges_only_records_null(tmp_path):
    """P0400-REMESHRECORD (PFS-2099.014): a group whose every edge is a curve has no edge ratio;
    its record says null, which json.dumps(allow_nan=False) writes, instead of NaN."""
    obj = tmp_path / "one.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng A\nf 1 2 3\n", encoding="utf-8")
    done = refine_group(read_obj(obj), ["A"], set(), 1.0)
    assert done.info["edge_ratio_median"] is None
    json.dumps(done.info, allow_nan=False)
