"""P0390-ZEROAREA (FR-432): a family rebuilt at factor 1 beside a refined side takes its spacing.

Every source is synthetic: the cambered sheet grid ``G`` of
tests/p0380_mesh_fixtures.py and ``C``, a curved cap of triangles closing G's
tip station, its rows bent a quarter turn about the chord (a quarter
cylinder). G is refined at factor 2 and C is rebuilt at factor 1, stated
``factor = 1``, ``method = "remesh"``, or as the band of an unselected
neighbour (FR-425 R3).

The measurement the box asks for first was made on this fixture and on its
variants (a quarter or half cylinder, a dome of shrinking rows, a flat zipper
cap and a dome closing a wing tube, a section thinned to 0.5 percent, 2 to 6
cap rows, 24 and 48 nodes, factors 2, 3 and 4, stated and band): the 0.38.0
target gave no face under ``ZERO_AREA_FRACTION * size**2`` on any of them,
so the defect of the multi-component mesh was not reproduced synthetically.
What 0.38.0 did give on every one is the mechanism: the faces of C beside the
curve kept C's own length, two to five times the new shared edges, so the
tests below hold the rule itself. The edges of C crossing from the curve are
as long as the shared edges (a ratio of at most 1.5, against 1.9 to 5.3 on
0.38.0), the targets at and near the curve are the shared spacing graded
over two face layers, and ``refine.json`` records the target taken.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine import _obj, _remesh
from pyflightstream.workspace._refine._geometry import ZERO_AREA_FRACTION
from tests.p0380_mesh_fixtures import (
    Composite,
    face_coordinates,
    read_mesh,
    sheet_with_strips,
    write_source,
)

pytest.importorskip("trimesh")

STATED = '[families.G]\nfactor = 2\n[families.C]\nfactor = 1\nmethod = "remesh"\n'
#: The largest median ratio of a crossing edge of C to a shared edge the rule allows.
CROSS_RATIO = 1.5


def sheet_with_cap(rows: int = 3, sweep_deg: float = 90.0, radius: float = 0.1) -> Composite:
    """Return the sheet grid ``G`` and ``C``, a cap of triangles bent about the tip's chord.

    Row ``j`` of the cap is the tip section moved by ``radius`` along a
    quarter circle in the y-z plane, ``j / rows`` of ``sweep_deg``; each cell
    is split along a diagonal that alternates.
    """
    base = sheet_with_strips(())
    tip = list(base.rows["G"][-1])
    section = base.verts[tip]
    verts = [base.verts]
    count = len(base.verts)
    cap_rows = [tip]
    y0 = float(section[0, 1])
    for j in range(1, rows + 1):
        angle = np.radians(sweep_deg) * j / rows
        row = section.copy()
        row[:, 1] = y0 + radius * np.sin(angle)
        row[:, 2] = section[:, 2] + radius * (1.0 - np.cos(angle))
        verts.append(row)
        cap_rows.append(list(range(count, count + len(row))))
        count += len(row)
    faces = []
    for j in range(rows):
        lo, hi = cap_rows[j], cap_rows[j + 1]
        for i in range(len(lo) - 1):
            a, b, c, d = lo[i], lo[i + 1], hi[i + 1], hi[i]
            faces += [[a, b, c], [a, c, d]] if (i + j) % 2 else [[a, b, d], [b, c, d]]
    families = {**base.families, "C": faces}
    return Composite(np.vstack(verts), families, base.te, {**base.rows, "C": cap_rows})


def _edges(faces) -> set[tuple[int, int]]:
    return {(min(a, b), max(a, b)) for f in faces for a, b in zip(f, f[1:] + f[:1], strict=True)}


def _record(level) -> dict:
    return json.loads(next(Path(level.folder).glob("*.refine.json")).read_text(encoding="utf-8"))


def _source(tmp_path: Path, name: str, mesh: Composite, toml: str | None = None) -> Path:
    return write_source(tmp_path / name, "wing", mesh, refine_toml=toml)


def _polyline_spacing(points: np.ndarray) -> np.ndarray:
    """Return, at each node of an ordered polyline, the mean length of its one or two segments."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    out = np.empty(len(points))
    out[0], out[-1] = seg[0], seg[-1]
    out[1:-1] = 0.5 * (seg[:-1] + seg[1:])
    return out


@pytest.fixture(scope="module")
def cap(tmp_path_factory):
    """Return the cap's group, its local curve ids and the refined tip row (midpoints inserted)."""
    mesh = sheet_with_cap()
    tip = mesh.rows["G"][-1]
    obj = _obj.read_obj(write_source(tmp_path_factory.mktemp("cap"), "wing", mesh))
    group = _remesh._group(obj, ["C"])
    local = {v: i for i, v in enumerate(group.ids)}
    old = obj.verts[tip]
    new = np.empty((2 * len(old) - 1, 3))
    new[0::2] = old
    new[1::2] = 0.5 * (old[:-1] + old[1:])
    return group, [local[v] for v in tip], new


def test_p0390_zeroarea_target_at_the_curve_is_the_shared_spacing(cap):
    """P0390-ZEROAREA (FR-432 R1) a node on the shared curve takes the new shared edges' length."""
    group, ids, new = cap
    targets, record = _remesh._shared_targets(group, {"C": 1.0}, [(ids, new)])
    expected = _polyline_spacing(new)[0::2]
    own = _remesh._targets(group, {"C": 1.0})[ids]
    assert np.all(own > 1.5 * expected), "the fixture must make the 0.38.0 target differ"
    np.testing.assert_allclose(targets[ids], expected, rtol=1e-12)
    assert record == {
        "C": {
            "min": round(expected.min(), 12),
            "mean": round(float(expected.mean()), 12),
            "max": round(expected.max(), 12),
        }
    }


def test_p0390_zeroarea_target_returns_to_its_own_over_two_layers(cap):
    """P0390-ZEROAREA (FR-432 R2) the target is graded over two face layers, with no step."""
    assert _remesh.SHARED_LAYERS == 2
    group, ids, new = cap
    targets, _ = _remesh._shared_targets(group, {"C": 1.0}, [(ids, new)])
    own = _remesh._targets(group, {"C": 1.0})
    at = dict(zip(ids, _polyline_spacing(new)[0::2], strict=True))
    near: dict[int, list[float]] = {}
    for f in group.faces:
        hit = [at[v] for v in f if v in at]
        for v in f if hit else ():
            if v not in at:
                near.setdefault(v, []).extend(hit)
    assert near, "the fixture has a first layer"
    for v, values in near.items():
        s = sum(values) / len(values)
        assert min(s, own[v]) <= targets[v] <= max(s, own[v])
        assert targets[v] == pytest.approx(s + 0.5 * (own[v] - s), rel=1e-12)
    farther = [v for v in range(len(group.verts)) if v not in at and v not in near]
    assert farther, "the fixture has nodes two layers away"
    np.testing.assert_array_equal(targets[farther], own[farther])


def test_p0390_zeroarea_no_shared_curve_keeps_the_targets_of_0380(cap):
    """P0390-ZEROAREA (FR-432 R4) with no shared curve the targets are those of 0.38.0, exactly."""
    group, _, _ = cap
    targets, record = _remesh._shared_targets(group, {"C": 1.0}, [])
    np.testing.assert_array_equal(targets, _remesh._targets(group, {"C": 1.0}))
    assert record == {}


@pytest.mark.parametrize("how", ["stated", "rebuilt", "band"])
def test_p0390_zeroarea_level_takes_the_spacing_and_records_it(tmp_path, how):
    """P0390-ZEROAREA (FR-432 R1, R3) C beside G at 2 meshes to the shared spacing; G1 passes.

    C is stated at factor 1 (``stated``), rebuilt whole by FR-431 as an
    unselected cap two rows deep (``rebuilt``), or the band of an unselected
    cap three rows deep (``band``). A rebuilt family records the target taken
    at the curve; an unchanged neighbour keeps the record of FR-425 R3.
    """
    mesh = sheet_with_cap(rows=2 if how == "rebuilt" else 3)
    if how == "stated":
        src = _source(tmp_path, how, mesh, STATED)
        level = refine_mesh(src, config=src.with_suffix(".refine.toml"), out_dir=tmp_path / "o")
    else:
        src = _source(tmp_path, how, mesh)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            level = refine_mesh(src, 2, families=["G"], out_dir=tmp_path / "o")
    verts, fams = read_mesh(level.obj)
    curve = {v for f in fams["G"] for v in f} & {v for f in fams["C"] for v in f}
    edges = _edges(fams["C"])
    shared = [(a, b) for a, b in edges if a in curve and b in curve]
    cross = [(a, b) for a, b in edges if (a in curve) != (b in curve)]

    def length(e):
        return float(np.linalg.norm(verts[e[0]] - verts[e[1]]))

    ratio = np.median([length(e) for e in cross]) / np.median([length(e) for e in shared])
    assert ratio <= CROSS_RATIO, f"crossing edges {ratio:.2f} times the shared ones"
    per_node: dict[int, list[float]] = {}
    for e in shared:
        for v in e:
            per_node.setdefault(v, []).append(length(e))
    means = [sum(x) / len(x) for x in per_node.values()]
    entry = _record(level)["families"]["C"]
    if how == "band":
        assert set(entry) == {"method", "band", "faces"}, "FR-425 R3's record is unchanged"
    else:
        assert entry["method"] == ("remesh" if how == "stated" else "rebuilt_whole")
        taken = entry["shared_edge_target_m"]
        assert taken["min"] == pytest.approx(min(means), rel=1e-6)
        assert taken["max"] == pytest.approx(max(means), rel=1e-6)
        assert taken["min"] <= taken["mean"] <= taken["max"]
    gate = next(item for item in level.audit.gates if item.name == "G1")
    assert gate.verdict == "pass"
    assert gate.values["faces_of_zero_area"] == 0
    used = sorted({v for fs in fams.values() for f in fs for v in f})
    size = float(np.linalg.norm(np.ptp(verts[used], axis=0)))
    p = verts[np.array(fams["C"])]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    assert int((area < ZERO_AREA_FRACTION * size**2).sum()) == 0


def test_p0390_zeroarea_control_whole_mesh_at_factor_2(tmp_path):
    """P0390-ZEROAREA (FR-432 R3 control) the whole-mesh refine at 2 writes no zero-area face."""
    src = _source(tmp_path, "whole", sheet_with_cap())
    level = refine_mesh(src, 2, out_dir=tmp_path / "o")
    gate = next(item for item in level.audit.gates if item.name == "G1")
    assert gate.values["faces_of_zero_area"] == 0
    assert gate.verdict == "pass"
    assert "shared_edge_target_m" not in _record(level)["families"]["C"], "C is at factor 2"


def test_p0390_zeroarea_family_sharing_no_curve_is_unchanged(tmp_path):
    """P0390-ZEROAREA (FR-432 R4) a factor-1 family with no curve on a refined side is unchanged."""
    strips = (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)), ("U", "tri", (0.1, 0.1)))
    mesh = sheet_with_strips(strips)
    tail = '[families.U]\nfactor = 1\nmethod = "remesh"\n'
    beside = _source(tmp_path, "beside", mesh, "[families.G]\nfactor = 2\n" + tail)
    alone = _source(tmp_path, "alone", mesh, "[families.G]\nfactor = 1\n" + tail)
    refined = refine_mesh(beside, config=beside.with_suffix(".refine.toml"), out_dir=tmp_path / "a")
    control = refine_mesh(alone, config=alone.with_suffix(".refine.toml"), out_dir=tmp_path / "b")
    assert "shared_edge_target_m" not in _record(refined)["families"]["U"]
    v1, f1 = read_mesh(refined.obj)
    v2, f2 = read_mesh(control.obj)
    assert face_coordinates(v1, f1["U"]) == face_coordinates(v2, f2["U"])
