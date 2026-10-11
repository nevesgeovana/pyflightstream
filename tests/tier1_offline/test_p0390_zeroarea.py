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
from pyflightstream.workspace._refine._geometry import SHARED_LAYERS, ZERO_AREA_FRACTION
from pyflightstream.workspace._refine._obj import read_obj
from pyflightstream.workspace._refine._remesh import refine_group
from pyflightstream.workspace._refine._remesh_group import shared_targets
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


def _own(points: np.ndarray, faces) -> np.ndarray:
    """Return each node's own target at factor 1: the mean length of its incident edges."""
    total, count = np.zeros(len(points)), np.zeros(len(points))
    for a, b in _edges(faces):
        total[[a, b]] += float(np.linalg.norm(points[a] - points[b]))
        count[[a, b]] += 1
    return total / np.maximum(count, 1)


def _midpoints_inserted(points: np.ndarray) -> np.ndarray:
    """Return an ordered polyline with the mid-point of each segment inserted (a refined side)."""
    new = np.empty((2 * len(points) - 1, 3))
    new[0::2] = points
    new[1::2] = 0.5 * (points[:-1] + points[1:])
    return new


#: The refined side's curve of the strip below, and the source's nodes of the rows above it.
CURVE_X = (0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0)
ROW_X = (0.0, 1.0, 3.0, 7.0)


def _refined_strip():
    """Return a strip whose bottom row is the curve of a refined side, and its rows and chain.

    Rows 1 to 3 hold the nodes ``ROW_X`` at y 1, 2 and 3. Row 1 is joined to
    the curve by fans and the rows above by split cells, so a node of row j is
    j face layers from the curve.
    """
    xs = [CURVE_X, ROW_X, ROW_X, ROW_X]
    rows, pts = [], []
    for y, row in enumerate(xs):
        rows.append(list(range(len(pts), len(pts) + len(row))))
        pts += [(x, float(y), 0.0) for x in row]
    curve, first = rows[0], rows[1]
    under = [CURVE_X.index(x) for x in ROW_X]
    faces = []
    for i in range(len(ROW_X) - 1):
        a, b = first[i], first[i + 1]
        faces += [[curve[k], curve[k + 1], a] for k in range(under[i], under[i + 1])]
        faces.append([curve[under[i + 1]], b, a])
    for lo, hi in zip(rows[1:-1], rows[2:], strict=True):
        for i in range(len(ROW_X) - 1):
            faces += [[lo[i], lo[i + 1], hi[i + 1]], [lo[i], hi[i + 1], hi[i]]]
    chain = {(curve[k], curve[k + 1]) for k in range(len(CURVE_X) - 1)}
    return np.array(pts, dtype=float), faces, rows, chain


def test_p0390_zeroarea_targets_at_the_curve_and_its_layers_follow_r1_and_r2():
    """P0390-ZEROAREA (FR-432 R1, R2, R3) every curve node, then the layers, exactly.

    The curve's nodes are spaced 0.5, 0.5, 1, 1, 2 and 2, so each takes the
    mean of its one or two incident shared edges (R1), an inserted node as any
    other. A node one face layer away takes the target of the curve node
    nearest it, found here from the coordinates, half way to its own (R2,
    ``SHARED_LAYERS`` 2); the node at x 1 takes 0.75 from the curve node
    below it, not an average of the curve nodes its faces touch. Nodes two
    layers away and farther keep their own target (not returned). The record
    is the least, the mean and the greatest curve target.
    """
    assert SHARED_LAYERS == 2
    points, faces, rows, chain = _refined_strip()
    own = _own(points, faces)
    targets, record = shared_targets(
        points, faces, ["C"] * len(faces), own=own, held=set(), chains=[chain]
    )
    r1 = [0.5, 0.5, 0.75, 1.0, 1.5, 2.0, 2.0]
    assert [targets[v] for v in rows[0]] == r1
    curve = points[rows[0]]
    for v in rows[1]:
        s = r1[int(np.argmin(np.linalg.norm(curve - points[v], axis=1)))]
        assert targets[v] == s + (own[v] - s) / 2, v
    assert targets[rows[1][1]] == 0.75 + (own[rows[1][1]] - 0.75) / 2
    assert set(targets) == set(rows[0]) | set(rows[1])
    mean = round(sum(r1) / len(r1), 12)
    assert record == {"C": {"min": 0.5, "mean": mean, "max": 2.0}}


def test_p0390_zeroarea_the_curve_spacing_reads_the_shared_edges_not_proximity():
    """P0390-ZEROAREA (FR-432 R1) a bent curve: each node averages the shared edges it ends.

    The curve runs (0, 0), (1, 0), (1, 1), (0, 0.1): its last node is 0.1
    from its first, which is no edge of it, so a spacing read from the
    nearest nodes would give both 0.1. Each node takes the mean of the curve
    edges it ends. Control: the two ends are indeed that close.
    """
    curve = np.array([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 0.1, 0.0)])
    apex = np.array([(0.5, -0.5, 0.0), (1.5, 0.5, 0.0), (0.5, 1.2, 0.0)])
    points = np.vstack([curve, apex])
    faces = [[k, k + 1, 4 + k] for k in range(3)]
    chain = {(0, 1), (1, 2), (2, 3)}
    targets, _ = shared_targets(
        points, faces, ["C"] * 3, own=_own(points, faces), held=set(), chains=[chain]
    )
    last = float(np.linalg.norm(curve[3] - curve[2]))
    assert [targets[v] for v in range(4)] == [1.0, 1.0, (1.0 + last) / 2, last]
    assert float(np.linalg.norm(curve[3] - curve[0])) == pytest.approx(0.1)


def test_p0390_zeroarea_no_shared_curve_sets_no_target():
    """P0390-ZEROAREA (FR-432 R4) with no shared curve no target changes and nothing is recorded."""
    points, faces, _, _ = _refined_strip()
    own = _own(points, faces)
    assert shared_targets(points, faces, ["C"] * len(faces), own=own, held=set(), chains=[]) == (
        {},
        {},
    )


def _spacing_record(spacing: np.ndarray) -> dict:
    return {
        "min": round(float(spacing.min()), 12),
        "mean": round(float(spacing.mean()), 12),
        "max": round(float(spacing.max()), 12),
    }


def test_p0390_zeroarea_inserted_curve_nodes_are_recorded_with_their_spacing(tmp_path):
    """P0390-ZEROAREA (FR-432 R1, R3) a refined side's inserted nodes take and record their spacing.

    The cap C is remeshed at factor 1 beside G's tip row refined with a
    mid-point inserted in each segment (the row's spacing is nonuniform).
    The targets are set once the interface holds the new nodes, so the
    record is over every new curve node, the inserted ones included: the
    least, mean and greatest of the mean incident new shared edge. Measured
    first: C's own targets at the curve are over 1.5 times the new spacing.
    """
    mesh = sheet_with_cap()
    tip = mesh.rows["G"][-1]
    obj = read_obj(write_source(tmp_path, "wing", mesh))
    new = _midpoints_inserted(obj.verts[tip])
    spacing = _polyline_spacing(new)
    own = _own(mesh.verts, mesh.families["C"])[tip]
    assert np.all(own > 1.5 * spacing[0::2]), "the fixture must make the 0.38.0 target differ"
    done = refine_group(obj, ["C"], (), {"C": 1.0}, conform=[(tip, new)], shared=[(tip, new)])
    assert done.info["shared_edge_target_m"] == {"C": _spacing_record(spacing)}


def test_p0390_zeroarea_a_family_at_2_beside_a_kept_curve_takes_its_spacing(tmp_path):
    """P0390-ZEROAREA (FR-432 R5) a cap refined alone at 2 takes the spacing its grid keeps.

    G is not selected, so it keeps its tip row; C, refined at factor 2,
    takes at that curve the mean of the kept shared edges incident to each
    node, recorded under C, and its level passes G1 with no face of zero
    area. Control: C's own target at the curve, half its incident edges, is
    not the kept spacing.
    """
    mesh = sheet_with_cap()
    tip = mesh.rows["G"][-1]
    obj = read_obj(write_source(tmp_path / "unit", "wing", mesh))
    spacing = _polyline_spacing(obj.verts[tip])
    own = _own(mesh.verts, mesh.families["C"])[tip] / 2.0
    assert not np.allclose(own, spacing)
    done = refine_group(obj, ["C"], (), {"C": 2.0})
    assert done.info["shared_edge_target_m"] == {"C": _spacing_record(spacing)}
    src = _source(tmp_path, "alone", mesh)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        level = refine_mesh(src, 2, families=["C"], out_dir=tmp_path / "o")
    entry = _record(level)["families"]["C"]
    assert entry["shared_edge_target_m"] == _spacing_record(spacing)
    gate = next(item for item in level.audit.gates if item.name == "G1")
    assert gate.values["faces_of_zero_area"] == 0 and gate.verdict == "pass"


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
        assert entry["method"] == "unchanged" and {"band", "faces"} <= set(entry)
    else:
        assert entry["method"] == ("remesh" if how == "stated" else "rebuilt_whole")
    taken = entry["shared_edge_target_m"]
    assert taken["min"] == pytest.approx(min(means), rel=1e-6)
    assert taken["max"] == pytest.approx(max(means), rel=1e-6)
    assert taken["mean"] == pytest.approx(sum(means) / len(means), rel=1e-9)
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
