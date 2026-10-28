"""identify-te maps only quad families by default; --all-families maps every one.

A blade meshed in quadrilaterals with its tip cap a tria family of its own: the
cap's rearmost line is the tip contour, which is not a trailing edge.
"""

from __future__ import annotations

import warnings

import numpy as np

from pyflightstream.workspace.wake_edges import (
    quad_families,
    write_trailing_edges_identified,
)
from tests.tier1_offline.test_p0491_te_twisted_tip import STATIONS, _blade


def _obj(tmp_path):
    """Write the blade's quads as family Blade and its tip cap's triangles as family Tip."""
    verts, faces, trailing, n = _blade()
    quads = [f for f in faces if len(f) == 4]
    trias = [f for f in faces if len(f) == 3]
    lines = [f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in verts]
    for name, group in (("Blade", quads), ("Tip", trias)):
        lines.append(f"g {name}")
        lines += ["f " + " ".join(str(i + 1) for i in face) for face in group]
    path = tmp_path / "rotor.obj"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, verts, trailing


def _points(path):
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return np.asarray([[float(c) for c in row.split(",")] for row in rows])


def test_a_tria_tip_family_is_left_out_of_the_trailing_edges_by_default(tmp_path):
    path, verts, trailing = _obj(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_trailing_edges_identified(path)
    assert any("Tip is not a quad family" in str(w.message) for w in caught)
    expected = np.asarray([(verts[a] + verts[b]) / 2 for a, b in trailing])
    got = _points(path.with_name("rotor.te.txt"))
    assert len(got) == len(trailing) == STATIONS - 1
    assert np.allclose(np.sort(got, axis=0), np.sort(expected, axis=0))
    listed = path.with_name("rotor.nodes.txt").read_text(encoding="utf-8")
    assert "Tip" not in listed


def test_all_families_maps_the_tip_family_too(tmp_path):
    path, _, trailing = _obj(tmp_path)
    write_trailing_edges_identified(path, all_families=True)
    assert len(_points(path.with_name("rotor.te.txt"))) > len(trailing)
    assert "Tip" in path.with_name("rotor.nodes.txt").read_text(encoding="utf-8")


def test_a_named_family_is_taken_as_named(tmp_path):
    path, _, _ = _obj(tmp_path)
    write_trailing_edges_identified(path, None, ["Tip"])
    assert path.with_name("rotor.Tip.te.txt").is_file()


def test_a_quad_family_may_close_with_a_few_triangles():
    quads = [[0, 1, 2, 3]] * 97
    assert quad_families({"Q": quads + [[0, 1, 2]] * 3, "T": [[0, 1, 2]] * 10}) == ["Q"]
    assert quad_families({"M": quads[:80] + [[0, 1, 2]] * 20}) == []
