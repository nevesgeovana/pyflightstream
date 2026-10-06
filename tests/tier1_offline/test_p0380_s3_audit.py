"""Tier 1, 0.38.0: the audit of a panel mesh, alone or against its source (FR-426, P0380-AUDIT).

Pipeline role: quality gate on :func:`pyflightstream.workspace.audit_mesh` and
``pyfs-matrix audit-mesh``. Every mesh is built here: a curved sheet of two
grid families (one in triangles, one in quadrilaterals) sharing a row of
nodes, a closed box beside it, and a trailing edge along one side. Each gate
and each relative check is shown failing on a mesh built to fail it (the
warning, the audit written, the exit status), each reported figure is shown
exceeded with no warning, and the same mesh audited against itself is the
control that passes.
"""

from __future__ import annotations

import ast
import csv
import json
import math
import warnings
from pathlib import Path

import numpy
import pytest

from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import cli
from pyflightstream.workspace import InputArtifactError, MeshAudit, audit_mesh

NX, NY = 6, 6


#: A closed box beside the sheet, outward by the right-hand rule.
def _box(length: float = 0.2) -> list[list[float]]:
    """Return the corners of a box beside the sheet, ``length`` long along x."""
    return [[x, y, z] for x in (2.0, 2.0 + length) for y in (0.5, 0.7) for z in (0.0, 0.2)]


_BOX_FACES = [
    [0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
    [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3],
]  # fmt: skip


def _node(i: int, j: int) -> int:
    """Return the index of the sheet node at column i and row j."""
    return i * (NY + 1) + j


class Mesh:
    """A synthetic mesh: vertices, families of 0-based faces, and the trailing-edge edges."""

    def __init__(self, xs=None, plane=False, box=0.2) -> None:
        xs = numpy.linspace(0.0, 1.0, NX + 1) if xs is None else numpy.asarray(xs, dtype=float)
        rows = []
        for x in xs:
            for j in range(NY + 1):
                t = j / NY
                rows.append(
                    [x, 0.0, 0.2 + t] if plane else [x, 0.2 + t, 0.05 * math.sin(math.pi * x)]
                )
        self.verts = numpy.array(rows + _box(box), dtype=float)
        a, b = [], []
        for i in range(NX):
            for j in range(NY):
                v00, v10 = _node(i, j), _node(i + 1, j)
                v11, v01 = _node(i + 1, j + 1), _node(i, j + 1)
                if j < NY // 2:
                    a += [[v00, v10, v11], [v00, v11, v01]]
                else:
                    b.append([v00, v10, v11, v01])
        box = len(rows)
        self.families = {"A": a, "B": b, "Pod": [[box + k for k in f] for f in _BOX_FACES]}
        self.te = [(_node(NX, j), _node(NX, j + 1)) for j in range(NY)]

    def add_vertex(self, point) -> int:
        """Append a vertex and return its index."""
        self.verts = numpy.vstack([self.verts, numpy.asarray(point, dtype=float)])
        return len(self.verts) - 1

    def te_points(self) -> numpy.ndarray:
        """Return the mid-point of every trailing-edge edge, at this mesh's coordinates."""
        return numpy.array([0.5 * (self.verts[p] + self.verts[q]) for p, q in self.te])

    def write(self, folder: Path, stem: str, *, te_points=None) -> Path:
        """Write ``<stem>.obj`` and ``<stem>.te.txt`` in ``folder`` and return the OBJ."""
        folder.mkdir(parents=True, exist_ok=True)
        lines = [f"v {x!r} {y!r} {z!r}" for x, y, z in self.verts.tolist()]
        for name, faces in self.families.items():
            lines.append(f"g {name}")
            lines += ["f " + " ".join(str(v + 1) for v in f) for f in faces]
        obj = folder / f"{stem}.obj"
        obj.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        points = self.te_points() if te_points is None else te_points
        rows = ["METER"] + [f"{x!r},{y!r},{z!r}" for x, y, z in points.tolist()]
        (folder / f"{stem}.te.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        return obj


def _pair(tmp_path: Path, level: Mesh, source: Mesh | None = None, **write) -> tuple[Path, Path]:
    """Write a source (the base mesh unless given) and a level; return both OBJ paths."""
    src = (source or Mesh()).write(tmp_path / "src", "wing")
    out = level.write(tmp_path / "wing_R2", "wing_R2", **write)
    return out, src


def _audit(level: Path, source: Path | None = None, **kw) -> tuple[MeshAudit, list[str]]:
    """Audit and return the audit with the text of every package warning it raised."""
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        audit = audit_mesh(level, against=source, **kw)
    return audit, [str(w.message) for w in seen if issubclass(w.category, PyflightstreamWarning)]


def _item(audit: MeshAudit, name: str, family: str = "(whole mesh)"):
    """Return the one gate or check of that name and family."""
    found = [i for i in audit.gates + audit.checks if i.name == name and i.family == family]
    assert len(found) == 1, (name, family, [i.line() for i in audit.gates + audit.checks])
    return found[0]


def _assert_fails(audit: MeshAudit, said: list[str], name: str, family: str, text: str) -> None:
    """Assert the item failed, the audit failed, was written, and a warning names it."""
    item = _item(audit, name, family)
    assert item.verdict == "fail", item.line()
    assert not audit.passed
    written = json.loads(audit.path.read_text(encoding="utf-8"))
    assert written["passed"] is False and written["schema_version"] == 1
    assert any(name in w and family in w and text in w for w in said), said


def test_a_level_equal_to_its_source_passes_every_gate_and_check(tmp_path):
    """P0380-AUDIT (FR-426 R1, R2, R3): the control: the source against itself passes, no warning.

    Every gate is judged (G6 with the triangle family named as a grid at factor 1), the
    closed box yields its positive volume, and the audit is written beside the level.
    """
    level, src = _pair(tmp_path, Mesh())
    audit, said = _audit(level, src, unchanged_grids=["A"])
    assert audit.passed and said == []
    assert [i.verdict for i in audit.gates] == ["pass"] * len(audit.gates)
    assert {i.name for i in audit.gates} == {"G1", "G2", "G3", "G4", "G5", "G6"}
    assert _item(audit, "G2", "Pod").values["enclosed_volume"] > 0
    assert _item(audit, "G4").values == {
        "points": NY, "points_on_edges": NY, "chains": 1, "source_chains": 1
    }  # fmt: skip
    assert _item(audit, "G5", "A and B").values["shared_nodes"] == NX + 1
    assert {i.verdict for i in audit.checks} <= {"pass", "not judged"}
    assert audit.path == level.with_name("wing_R2.audit.json")
    written = json.loads(audit.path.read_text(encoding="utf-8"))
    assert written["schema_version"] == 1 and written["passed"] is True
    assert written["mesh"] == "wing_R2.obj" and written["source"] == "wing.obj"
    assert set(written["figures"]) == {"A", "B", "Pod", "(whole mesh)"}


def _nonmanifold(m: Mesh) -> None:
    v00, v11 = _node(2, 1), _node(3, 2)
    apex = m.add_vertex(0.5 * (m.verts[v00] + m.verts[v11]) + [0.0, 0.0, 0.3])
    m.families["A"].append([v00, v11, apex])


def _duplicate(m: Mesh) -> None:
    twin = m.add_vertex(m.verts[_node(0, 0)])
    m.families["A"].append([twin, m.add_vertex([-0.3, 0.0, 0.0]), m.add_vertex([-0.3, 0.1, 0.0])])


def _zero_area(m: Mesh) -> None:
    m.families["A"].append([m.add_vertex([5.0 + d, 5.0, 5.0]) for d in (0.0, 0.5, 1.0)])


@pytest.mark.parametrize(
    ("plant", "value"),
    [
        (_nonmanifold, "edges_of_more_than_two_faces 1"),
        (_duplicate, "node_pairs_at_one_position 1"),
        (_zero_area, "faces_of_zero_area 1"),
    ],
)
def test_g1_fails_on_each_of_its_three_defects(tmp_path, plant, value):
    """P0380-AUDIT (FR-426 R1, R2 G1, R5): an edge of three faces, two nodes at one position,
    a face of zero area each fail G1, against the source and alone; the audit is written."""
    m = Mesh()
    plant(m)
    level, src = _pair(tmp_path, m)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G1", "(whole mesh)", value)
    alone, said = _audit(level)
    _assert_fails(alone, said, "G1", "(whole mesh)", value)


def test_g2_fails_on_a_flipped_face_and_on_an_inward_closed_family(tmp_path):
    """P0380-AUDIT (FR-426 R2 G2, R5): a face whose neighbours run the other way fails G2 on the
    whole mesh; a closed family turned inside out fails G2 on that family, alone too."""
    m = Mesh()
    m.families["A"][14] = m.families["A"][14][::-1]
    level, src = _pair(tmp_path, m)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G2", "(whole mesh)", "neighbours_of_opposite_orientation 3")
    inward = Mesh()
    inward.families["Pod"] = [f[::-1] for f in inward.families["Pod"]]
    level, src = _pair(tmp_path / "pod", inward)
    alone, said = _audit(level)
    _assert_fails(alone, said, "G2", "Pod", "enclosed_volume -")
    assert _item(alone, "G2").verdict == "pass"


def test_g3_fails_on_a_new_hole_and_on_a_hole_moved_elsewhere(tmp_path):
    """P0380-AUDIT (FR-426 R2 G3, FR-425 R5, R5): a level that opens a hole fails G3 by count;
    a level whose hole is not the source's opening fails by matching; alone, G3 is reported."""
    m = Mesh()
    del m.families["A"][14]  # cell (2, 1): every node of it is inside the sheet
    level, src = _pair(tmp_path, m)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G3", "(whole mesh)", "open_loops 2, source_open_loops 1")
    alone, said = _audit(level)
    assert _item(alone, "G3").verdict == "not judged" and alone.passed and said == []
    moved = Mesh()
    del moved.families["B"][4]  # cell (1, 4), far from cell (2, 1)
    level, src = _pair(tmp_path / "moved", moved, source=m)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G3", "(whole mesh)", "unmatched_loops 2")
    assert _item(audit, "G3").values["open_loops"] == 2


def test_g4_fails_on_a_point_off_every_edge_and_on_a_split_chain(tmp_path):
    """P0380-AUDIT (FR-426 R2 G4, R5): a trailing-edge point off every mesh edge fails G4, alone
    too; a points file whose chains are not the source's in number fails G4 against it."""
    m = Mesh()
    off = m.te_points()
    off[2, 2] += 0.01
    level, src = _pair(tmp_path, m, te_points=off)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G4", "(whole mesh)", f"points {NY}, points_on_edges {NY - 1}")
    alone, said = _audit(level)
    _assert_fails(alone, said, "G4", "(whole mesh)", f"points_on_edges {NY - 1}")
    split = numpy.delete(m.te_points(), 2, axis=0)
    level, src = _pair(tmp_path / "split", Mesh(), te_points=split)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G4", "(whole mesh)", "chains 2, source_chains 1")


def test_g4_reads_the_points_file_the_sidecar_names_and_refuses_a_missing_one(tmp_path):
    """P0380-AUDIT (FR-426 R2 G4): the points file is the one ``[trailing_edges] file`` names;
    a named file that does not exist is refused, and nothing is written."""
    level, src = _pair(tmp_path, Mesh())
    level.with_suffix(".te.txt").rename(level.with_name("edge.te.txt"))
    sidecar = level.with_name("wing_R2.boundaries.toml")
    sidecar.write_text('[trailing_edges]\nfile = "edge.te.txt"\n', encoding="utf-8")
    audit, _ = _audit(level, src)
    assert _item(audit, "G4").values["points_on_edges"] == NY and audit.passed
    audit.path.unlink()
    sidecar.write_text('[trailing_edges]\nfile = "gone.te.txt"\n', encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"gone\.te\.txt.*Nothing was written\."):
        audit_mesh(level, against=src)
    assert not audit.path.exists()


def test_g5_fails_when_two_families_no_longer_share_their_nodes(tmp_path):
    """P0380-AUDIT (FR-426 R2 G5, R5): families that shared nodes in the source and share none in
    the level fail G5 on that pair; alone, G5 is reported and not judged."""
    m = Mesh()
    seam = {_node(i, NY // 2) for i in range(NX + 1)}
    twins = {v: m.add_vertex(m.verts[v]) for v in sorted(seam)}
    m.families["B"] = [[twins.get(v, v) for v in f] for f in m.families["B"]]
    m.te = [(twins.get(p, p), q) for p, q in m.te]
    level, src = _pair(tmp_path, m)
    audit, said = _audit(level, src)
    _assert_fails(audit, said, "G5", "A and B", f"shared_nodes 0, source_shared_nodes {NX + 1}")
    alone, _ = _audit(level)
    assert _item(alone, "G5").verdict == "not judged"


def test_g6_fails_when_a_factor_one_grid_family_moves_or_reorders(tmp_path):
    """P0380-AUDIT (FR-426 R2 G6, FR-424 R7, R5): a grid family named as unchanged fails G6 when
    one node moves by 1e-6 or its faces change order; unnamed or alone, G6 is not judged."""
    moved = Mesh()
    moved.verts[_node(2, 1)] += [0.0, 0.0, 1e-6]
    level, src = _pair(tmp_path, moved)
    audit, said = _audit(level, src, unchanged_grids=["A"])
    _assert_fails(audit, said, "G6", "A", "differing_faces 6")
    unnamed, _ = _audit(level, src)
    assert _item(unnamed, "G6").verdict == "not judged"
    alone, _ = _audit(level, unchanged_grids=["A"])
    assert _item(alone, "G6").verdict == "not judged"
    reordered = Mesh()
    reordered.families["A"] = reordered.families["A"][::-1]
    level, src = _pair(tmp_path / "order", reordered)
    audit, said = _audit(level, src, unchanged_grids=["A"])
    _assert_fails(audit, said, "G6", "A", "faces 36, source_faces 36")


def _sheared() -> Mesh:
    m = Mesh()
    for i in range(1, NX, 2):
        for j in range(NY + 1):
            m.verts[_node(i, j), 1] += 0.4 / NY
    return m


def _warped() -> Mesh:
    m = Mesh()
    for i in range(NX + 1):
        for j in range(NY + 1):
            m.verts[_node(i, j), 2] += 0.05 * ((i + j) % 2)
    return m


def _graded() -> Mesh:
    steps = 3.0 ** numpy.arange(NX)
    return Mesh(xs=numpy.concatenate([[0.0], numpy.cumsum(steps) / steps.sum()]))


@pytest.mark.parametrize(
    ("build", "check", "family"),
    [(_sheared, "skewness", "A"), (_warped, "warp", "B"), (_graded, "growth", "A")],
)
def test_each_relative_check_fails_on_a_mesh_built_to_fail_it(tmp_path, build, check, family):
    """P0380-AUDIT (FR-426 R1, R3, R5): a sheared grid fails the skewness check, a warped one the
    warp check, a graded one the size-growth check, per family and on the whole mesh, each a
    warning naming both 95th percentiles; alone, the check is reported and not judged."""
    level, src = _pair(tmp_path, build())
    audit, said = _audit(level, src)
    for where in (family, "(whole mesh)"):
        _assert_fails(audit, said, check, where, "p95 ")
        item = _item(audit, check, where)
        assert item.values["p95"] > item.values["limit"]
    assert any(f"source_p95 {_said(_item(audit, check, family).values['source_p95'])}" in w
               for w in said)  # fmt: skip
    alone, said = _audit(level)
    assert {i.verdict for i in alone.checks} == {"not judged"} and said == []


def _said(value: float) -> str:
    return f"{value:.6g}"


def test_the_relative_limits_are_the_margin_and_the_floors_of_r3(tmp_path):
    """P0380-AUDIT (FR-426 R3): skewness at most the source's plus 0.05; warp and growth at most
    the larger of the source's and 10 degrees, and of the source's and 2; the percentile is the
    95th with linear interpolation between ranks."""
    level, src = _pair(tmp_path, _graded())
    audit, _ = _audit(level, src)
    base = _item(audit, "skewness", "A").values
    assert base["limit"] == pytest.approx(base["source_p95"] + 0.05)
    growth = _item(audit, "growth", "A").values
    assert growth["limit"] == max(growth["source_p95"], 2.0) == 2.0
    warp = _item(audit, "warp", "B").values
    assert warp["limit"] == max(warp["source_p95"], 10.0)
    m = Mesh()
    m.verts[: (NX + 1) * (NY + 1), 2] += numpy.random.default_rng(0).uniform(
        -0.02, 0.02, (NX + 1) * (NY + 1)
    )
    aspects = []
    for f in m.families["A"]:
        p = m.verts[f]
        e = numpy.linalg.norm(numpy.roll(p, -1, axis=0) - p, axis=1)
        aspects.append(e.max() / e.min())
    alone, _ = _audit(m.write(tmp_path / "alone", "alone"))
    linear = numpy.percentile(aspects, 95, method="linear")
    assert linear != numpy.percentile(aspects, 95, method="nearest")
    assert alone.figures["A"]["aspect_p95"] == pytest.approx(linear, rel=1e-12)


def test_size_growth_across_a_corner_is_not_a_size_jump(tmp_path):
    """P0380-AUDIT (FR-426 R3): the size growth is read across edges whose dihedral is below 30
    degrees only, so a long box whose sides are ten times its ends grows by 1, and its growth
    check passes against a cube (its skewness check is the one that fails)."""
    level, src = _pair(tmp_path, Mesh(box=2.0))
    audit, said = _audit(level, src)
    assert audit.figures["Pod"]["growth_p95"] == pytest.approx(1.0)
    assert _item(audit, "growth", "Pod").verdict == "pass"
    assert not [w for w in said if "growth" in w]


def _slender() -> Mesh:
    return Mesh(xs=[0.0, 0.2, 0.4, 0.6, 0.8, 0.999, 1.0], plane=True)


def test_each_reported_figure_exceeded_gives_its_figure_and_no_warning(tmp_path):
    """P0380-AUDIT (FR-426 R4, R5): a mesh in the plane y = 0 whose last column at the trailing
    edge is a thousandth wide exceeds every reported figure (aspect above 50, the
    pre-processor's thresholds, the face quality ratio above 2, trailing-edge triangles above
    50, faces on y = 0); against itself and alone it passes, with each figure and no warning."""
    level, src = _pair(tmp_path, _slender(), source=_slender())
    for audit, said in (_audit(level, src), _audit(level)):
        assert audit.passed and said == []
        whole = audit.figures["(whole mesh)"]
        assert whole["aspect_max"] > 50 and whole["aspect_over_50"] > 0
        # Only the thousandth-wide column breaks a threshold: its triangles in A, its quads in B.
        slim_triangles, slim_quads = 2 * (NY // 2), NY - NY // 2
        assert whole["aspect_over_8"] == whole["aspect_over_50"] == slim_triangles + slim_quads
        assert whole["tri_min_angle_under_30_degrees"] == slim_triangles
        assert whole["skewness_over_0p5"] == slim_triangles
        assert whole["quad_min_angle_under_45_degrees"] == whole["warp_over_10_degrees"] == 0
        assert whole["quality_ratio_over_2"] > 0 and whole["quality_ratio_p95"] is not None
        # Each trailing-edge edge has one face: a triangle in A, a quadrilateral in B.
        assert whole["trailing_edge_triangles_aspect_over_50"] == NY // 2
        assert audit.figures["B"]["trailing_edge_triangles_aspect_over_50"] == 0
        assert whole["faces_on_y0_plane"] == 2 * NX * (NY // 2) + NX * (NY - NY // 2)
        assert audit.figures["Pod"]["faces_on_y0_plane"] == 0
        written = json.loads(audit.path.read_text(encoding="utf-8"))
        assert written["figures"]["(whole mesh)"]["aspect_over_50"] == whole["aspect_over_50"]


def test_without_a_source_only_g1_g2_and_g4_are_judged(tmp_path):
    """P0380-AUDIT (FR-426 R5): alone, G1, G2 and G4 carry a verdict and G3, G5, G6 and every
    relative check are reported; the audit names no source."""
    audit, said = _audit(Mesh().write(tmp_path, "wing"))
    verdicts = {(i.name, i.family): i.verdict for i in audit.gates}
    assert {k for k, v in verdicts.items() if v != "not judged"} == {
        ("G1", "(whole mesh)"), ("G2", "(whole mesh)"), ("G2", "Pod"), ("G4", "(whole mesh)")
    }  # fmt: skip
    assert {i.verdict for i in audit.checks} == {"not judged"}
    assert audit.source is None and audit.passed and said == []
    assert json.loads(audit.path.read_text(encoding="utf-8"))["source"] is None


def _run(*argv: str) -> tuple[int, list[str]]:
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        code = cli.main(list(argv))
    return code, [str(w.message) for w in seen if issubclass(w.category, PyflightstreamWarning)]


def test_the_command_exits_0_when_every_gate_and_check_passes_and_writes_the_csv(tmp_path, capsys):
    """P0380-AUDIT (FR-426 R1): ``audit-mesh OBJ --against SOURCE --csv FILE`` exits 0, prints
    the summary and the files written, and the CSV holds one row per family and figure."""
    level, src = _pair(tmp_path, Mesh())
    table = tmp_path / "audit.csv"
    code, said = _run("audit-mesh", str(level), "--against", str(src), "--csv", str(table))
    out = capsys.readouterr().out
    assert code == 0 and said == []
    assert "every gate and check passed" in out and str(level.with_suffix(".audit.json")) in out
    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    figures = json.loads(level.with_name("wing_R2.audit.json").read_text(encoding="utf-8"))
    expected = sum(len(v) for v in figures["figures"].values())
    assert rows[0] == ["family", "figure", "value"] and len(rows) == 1 + expected
    assert {r[0] for r in rows[1:]} == {"A", "B", "Pod", "(whole mesh)"}
    assert (
        b"\r" not in table.read_bytes()
        and b"\r" not in level.with_name("wing_R2.audit.json").read_bytes()
    )


def test_the_command_exits_1_when_a_gate_fails_and_still_writes_the_audit(tmp_path, capsys):
    """P0380-AUDIT (FR-426 R1): a level that opens a hole exits 1 with the warning naming G3,
    the family and both values, and the audit is written."""
    m = Mesh()
    del m.families["A"][14]
    level, src = _pair(tmp_path, m)
    code, said = _run("audit-mesh", str(level), "--against", str(src))
    assert code == 1
    assert any("G3 failed on (whole mesh): open_loops 2, source_open_loops 1" in w for w in said)
    assert "the audit FAILED" in capsys.readouterr().out
    assert json.loads(level.with_name("wing_R2.audit.json").read_text())["passed"] is False


def test_the_command_exits_2_on_a_refusal_and_writes_nothing(tmp_path, capsys):
    """P0380-AUDIT (FR-426 R1): a missing OBJ, an OBJ with no face, a missing source and a CSV in
    a folder that does not exist each exit 2 with the refusal, and no audit is written."""
    level, src = _pair(tmp_path, Mesh())
    empty = tmp_path / "empty.obj"
    empty.write_text("v 0 0 0\n", encoding="utf-8")
    cases = [
        ([str(tmp_path / "none.obj")], "none.obj: no such OBJ file"),
        ([str(empty)], "the file holds no face"),
        ([str(level), "--against", str(tmp_path / "gone.obj")], "gone.obj: no such OBJ file"),
        ([str(level), "--csv", str(tmp_path / "no" / "a.csv")], "--csv names a folder"),
    ]
    for argv, refusal in cases:
        code, _ = _run("audit-mesh", *argv)
        err = capsys.readouterr().err
        assert code == 2 and refusal in err and "Nothing was written." in err, (argv, err)
    assert not list(tmp_path.rglob("*.audit.json"))


def test_the_command_reaches_the_audit_only_through_the_public_function():
    """P0380-AUDIT (FR-426, FR-424 R14): no module of ``run`` imports the refinement package; the
    mesh verbs import ``audit_mesh`` from ``pyflightstream.workspace``."""
    run = Path(cli.__file__).parent
    imported = {}
    for module in sorted(run.glob("*.py")):
        names = set()
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names |= {f"{node.module}.{alias.name}" for alias in node.names}
            elif isinstance(node, ast.Import):
                names |= {alias.name for alias in node.names}
        imported[module.name] = names
    assert not [m for m, names in imported.items() if any("._refine" in n for n in names)]
    assert [m for m, names in imported.items() if "pyflightstream.workspace.audit_mesh" in names]
