"""Tier 1, 0.42.0 P2-1b: the trailing-edge points file, the none route and the mesh audit's inputs.

Pipeline role: guards on :mod:`pyflightstream.workspace._refine` (FR-424, FR-426, FR-937).
Every mesh is a strip of two quadrilaterals whose trailing edge is the edge
at x = 2; each defect is shown refused beside a control that is accepted.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.workspace import MeshAudit, audit_mesh, refine_mesh
from pyflightstream.workspace._refine._obj import read_obj, read_te, te_file, te_route

OBJ = "v 0 0 0\nv 1 0 0\nv 2 0 0\nv 0 1 0\nv 1 1 0\nv 2 1 0\ng W\nf 1 2 5 4\nf 2 3 6 5\n"


def _mesh(folder: Path, te_rows: list[str] | None = None, boundaries: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    obj = folder / "w.obj"
    obj.write_text(OBJ, encoding="utf-8")
    if te_rows is not None:
        (folder / "w.te.txt").write_text("\n".join(te_rows) + "\n", encoding="utf-8")
    if boundaries:
        (folder / "w.boundaries.toml").write_text(boundaries, encoding="utf-8")
    return obj


def _g4(obj: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        audit = audit_mesh(obj)
    return next(g for g in audit.gates if g.name == "G4"), audit


# ---------------------------------------------------------------- PFS-2130.065


def test_p0420_a_points_file_without_its_unit_line_is_refused_before_a_point_is_read(tmp_path):
    """PFS-2130.065: a first row that is not a unit is refused, not read as a lost point."""
    lost = tmp_path / "lost.te.txt"
    lost.write_text("2,0.5,0\n2,0.6,0\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"lost\.te\.txt.*not a length unit.*METER"):
        read_te(lost)
    ok = tmp_path / "ok.te.txt"
    ok.write_text(" millimeter \n2,0.5,0\n2,0.6,0\n", encoding="utf-8")
    unit, points = read_te(ok)
    assert unit == "millimeter" and len(points) == 2


# ---------------------------------------------------------------- PFS-2130.067


def test_p0420_read_obj_refuses_a_missing_mesh_as_the_audit_does(tmp_path):
    """PFS-2130.067: read_obj, refine_mesh and audit_mesh refuse a missing path alike."""
    for path in (tmp_path / "nope.obj", tmp_path):
        with pytest.raises(InputArtifactError, match="no such OBJ file"):
            read_obj(path)
        with pytest.raises(InputArtifactError, match="no such OBJ file"):
            refine_mesh(path, 2)
        with pytest.raises(InputArtifactError, match="no such OBJ file"):
            audit_mesh(path)
    assert read_obj(_mesh(tmp_path / "ok")).families["W"]


# ---------------------------------------------------------------- PFS-2119.063


def test_p0420_none_true_stops_a_te_txt_beside_the_mesh_being_read(tmp_path):
    """PFS-2119.063: ``none = true`` carries in the route and te_file returns None for it."""
    rows = ["METER", "2,0.5,0"]
    stale = _mesh(tmp_path / "stale", rows, 'boundaries = ["W"]\n\n[trailing_edges]\nnone = true\n')
    assert te_route(stale).none and te_file(stale) is None
    g4, _ = _g4(stale)
    assert g4.values["points"] == 0
    control = _mesh(tmp_path / "control", rows, 'boundaries = ["W"]\n')
    assert not te_route(control).none and te_file(control) == control.with_suffix(".te.txt")
    assert _g4(control)[0].values["points"] == 1
    assert ("its trailing-edge points file", stale.with_suffix(".te.txt")) not in (
        MeshAudit.files_read(stale)
    )


# ---------------------------------------------------------------- PFS-2130.068


def test_p0420_g4_fails_two_points_on_one_mesh_edge(tmp_path):
    """PFS-2130.068: a duplicated row is two points on one edge and fails the gate."""
    once = _mesh(tmp_path / "once", ["METER", "2,0.5,0"])
    g4, _ = _g4(once)
    assert g4.values["points_sharing_an_edge"] == 0 and g4.verdict == "pass"
    twice = _mesh(tmp_path / "twice", ["METER", "2,0.5,0", "2,0.5,0"])
    g4, audit = _g4(twice)
    assert g4.values["points"] == 2 and g4.values["points_on_edges"] == 2
    assert g4.values["points_sharing_an_edge"] == 1
    assert g4.verdict == "fail" and not audit.passed


# ---------------------------------------------------------------- PFS-2123.004


def test_p0420_files_read_is_the_list_the_audit_refuses_by_and_write_csv_guards_it(tmp_path):
    """PFS-2123.004: one list; write_csv refuses a file the audit reads or wrote."""
    obj = _mesh(tmp_path / "m", ["METER", "2,0.5,0"], 'boundaries = ["W"]\n')
    record = obj.with_name("w.refine.json")
    record.write_text("{}", encoding="utf-8")
    read = MeshAudit.files_read(obj)
    assert ("its refinement record", record) in read
    _, audit = _g4(obj)
    for _, path in [*read, ("the audit JSON", audit.path)]:
        if path.exists():
            before = path.read_bytes()
            with pytest.raises(InputArtifactError, match="Nothing was written"):
                audit.write_csv(path)
            assert path.read_bytes() == before
    out = tmp_path / "figures.csv"
    assert audit.write_csv(out) == out and out.is_file()


# ---------------------------------------------------------------- PFS-2119.062


def test_p0420_a_sheet_with_no_trailing_edge_is_refused_for_that_reason():
    """PFS-2119.062: a sheet needs a trailing edge; the refusal says so, not 'not a grid line'."""
    from pyflightstream.workspace._refine._grid import recover_grid
    from tests.p0380_mesh_fixtures import sheet_quads

    sheet = sheet_quads()
    said = recover_grid(sheet.verts, sheet.faces, set())
    assert isinstance(said, str) and said.startswith("a sheet needs a trailing edge")
    assert "only a smooth tube is recovered without one" in said
    # the control: with its trailing edge the same sheet is a grid
    assert not isinstance(recover_grid(sheet.verts, sheet.faces, sheet.te), str)


# ---------------------------------------------------------------- F-305 F-330

_TOL = 1e-9  # DUPLICATE_FRACTION of a unit size


def test_p0430_f305_weld_follows_the_tolerance_not_a_rounding_grid(tmp_path):
    """F-305: nodes closer than the tolerance weld across a bin edge; farther ones stay apart."""
    size = float(numpy.hypot(3.0, 1.0))  # the diagonal of the two families' bounding box

    def level_nodes(name: str, offset) -> int:
        # W is the strip of OBJ; X is a quadrilateral whose first node sits at W's node
        # (2, 0, 0) displaced by `offset`, in a family of its own (no shared node index)
        folder = tmp_path / name
        folder.mkdir()
        x0 = numpy.array([2.0, 0.0, 0.0]) + numpy.asarray(offset) * size * _TOL
        rows = [r for r in OBJ.splitlines() if r.startswith("v ")]
        rows += ["v {!r} {!r} {!r}".format(*map(float, x0)), "v 3 0 0", "v 3 1 0", "v 2.5 1 0"]
        text = "\n".join([*rows, "g W", "f 1 2 5 4", "f 2 3 6 5", "g X", "f 7 8 9 10"]) + "\n"
        (folder / "w.obj").write_text(text, encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            level = refine_mesh(folder / "w.obj", 2, out_dir=tmp_path / f"out_{name}")
        return len(read_obj(level.obj).verts)

    welded = level_nodes("near", [0.02, 0.0, 0.0])  # 0.02 tolerances apart
    apart = level_nodes("far", [0.98] * 3)  # 1.7 tolerances apart
    assert apart == welded + 1


def test_p0430_f330_fixed_side_nodes_follow_the_tolerance():
    """F-330: the fixed-side cut nodes keep distinct nodes and drop coincident ones by distance."""
    from pyflightstream.workspace._refine._config import Periodic
    from pyflightstream.workspace._refine._periodic import CutPair, plan_conform

    periodic = Periodic(axis=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0), copies=4)
    size = float(numpy.hypot(2.0, 2.0))  # the diagonal of the used vertices' bounding box

    def slave_nodes(gap: float) -> int:
        # M is fixed, S is remeshed: S's cut is rebuilt on the quarter-turn image of M's cut
        # nodes, whose last two nodes lie `gap` tolerances apart
        eps = gap * _TOL * size
        verts = numpy.array(
            [
                [1.0, 0, 0], [2.0, 0, 0], [2.0 + eps, 0, 0], [1.0, 1.0, 0.0],
                [0, 1.0, 0], [0, 2.0, 0], [0, 2.0 + eps, 0], [-1.0, 1.0, 0.0],
            ]
        )  # fmt: skip
        families = {"M": [[0, 1, 3], [1, 2, 3]], "S": [[4, 5, 7], [5, 6, 7]]}
        cut = CutPair((0, 1, 2), (4, 5, 6), 1, 0.0, (("M",), ("S",)))
        planned = plan_conform(verts, families, [cut], periodic, remeshed={"S": 1.0}, grids={})
        ((_, nodes),) = planned["S"]
        return len(nodes)

    assert slave_nodes(0.02) == 2  # coincident within the tolerance: one node
    assert slave_nodes(1.7) == 3  # farther apart than the tolerance: two nodes


# ---------------------------------------------------------------- F-331 X-F-0435


def test_p0430_f331_an_interior_edge_between_two_fixed_nodes_stays_free():
    """F-331: an interior edge is not frozen because both its nodes are shared outside."""
    from pyflightstream.workspace._refine._geometry import edge_faces
    from pyflightstream.workspace._refine._obj import ObjMesh
    from pyflightstream.workspace._refine._remesh import refine_group

    verts = numpy.array(
        [[0.0, 0, 0], [1, 0, 0], [0.5, 1, 0], [0.5, -1, 0], [-1, 0, 0], [-1, 1, 0], [2, 0, 0],
         [2, 1, 0]]
    )  # fmt: skip
    # W is remeshed; O shares W's nodes 0 and 1 (each by one face) and is left alone
    mesh = ObjMesh(verts, {"W": [[0, 1, 2], [1, 0, 3]], "O": [[0, 4, 5], [1, 6, 7]]})
    result = refine_group(mesh, ["W"], (), 2.0)
    assert result.info["curve_edges"] == {"boundary": 4}  # the four outer edges, not the interior
    ends = [
        int(numpy.flatnonzero(numpy.linalg.norm(result.points - verts[v], axis=1) < 1e-12)[0])
        for v in (0, 1)
    ]
    # the interior edge (0, 1) was split at factor 2, which it could not be if it were frozen
    assert (min(ends), max(ends)) not in edge_faces(result.families["W"])


def test_p0430_x_f0435_the_remesh_target_ignores_the_fan_diagonal_of_a_quad():
    """X-F-0435: a unit square's target is its side, not an average with the diagonal."""
    from pyflightstream.workspace._refine._geometry import edge_faces
    from pyflightstream.workspace._refine._obj import ObjMesh
    from pyflightstream.workspace._refine._remesh import refine_group

    square = numpy.array([[0.0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
    result = refine_group(ObjMesh(square, {"W": [[0, 1, 2, 3]]}), ["W"], (), 2.0)
    edges = list(edge_faces(result.families["W"]))
    lengths = [float(numpy.linalg.norm(result.points[a] - result.points[b])) for a, b in edges]
    # target 0.5 (the side over the factor); the diagonal averaged in would give 0.54 and a
    # mean edge of 0.55, measured 0.499 without it
    assert numpy.mean(lengths) == pytest.approx(0.5, abs=0.03)


# ---------------------------------------------------------------- FR-936


def test_p0430_fr936_the_level_keeps_the_identity_of_the_source_open_loop(tmp_path):
    """FR-936: the level's one open loop is the source's outline, corners and edges, no hole."""
    from pyflightstream.workspace._refine._geometry import boundary_loops

    obj = _mesh(tmp_path / "loop", ["METER", "2,0.5,0"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        level = refine_mesh(obj, 2)
    mesh = read_obj(level.obj)
    loops = boundary_loops([f for fs in mesh.families.values() for f in fs])
    assert len(loops) == 1
    pts = mesh.verts[loops[0]]
    on_outline = (
        numpy.isclose(pts[:, 0], 0) | numpy.isclose(pts[:, 0], 2)
        | numpy.isclose(pts[:, 1], 0) | numpy.isclose(pts[:, 1], 1)
    )  # fmt: skip
    assert on_outline.all()
    corners = {(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)}
    assert corners <= {(round(float(x), 9), round(float(y), 9)) for x, y, _ in pts}


# ---------------------------------------------------------------- F-1584


def test_p0430_f1584_the_text_a_refusal_offers_for_a_value_is_valid_toml(tmp_path):
    """F-1584: an inline table is offered in TOML, not JSON, syntax, and parses to the value."""
    import tomllib

    from tests.tier1_offline.test_p0390_firstrow import Composite, _tube_source, write_source

    lens = _tube_source(sharp_le=True)
    ring = 6 * 48 + 48
    body_edge = 0.5 * (lens.verts[ring + 12] + lens.verts[ring + 13])
    mesh = Composite(lens.verts, lens.families, body_edge[None, :], {})
    toml = (
        "[families.Wing]\nspanwise = 2.0\nkeep_first_row = true\n"
        "trailing_edge_direction = [1.0, 0.0, 0.0]\n"
    )
    src = write_source(tmp_path / "lens", "wing", mesh, refine_toml=toml)
    side = src.with_name("wing.boundaries.toml")
    # the detect route spelled as a table header: no `detect =` text a rewrite could replace
    side.write_text(
        side.read_text(encoding="utf-8").replace('file = "wing.te.txt"', "").rstrip()
        + '\n[trailing_edges.detect]\nsurfaces = ["Wing"]\n[import]\nunits = "METER"\n',
        encoding="utf-8",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        with pytest.raises(InputArtifactError, match="cannot be rewritten") as caught:
            refine_mesh(src, out_dir=tmp_path / "out")
    offered = str(caught.value).split("state it as ", 1)[1].split(" and run again", 1)[0]
    assert tomllib.loads(offered)["detect"] == {"surfaces": ["Wing"]}


# ---------------------------------------------------------------- F-1517


def test_p0430_f1517_an_obj_that_is_not_utf8_is_refused_not_merged_by_replacement(tmp_path):
    """F-1517: family labels differing only in a non-UTF-8 byte are not merged into one."""
    bad = tmp_path / "bad.obj"
    bad.write_bytes(b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\ng W\xe9a\nf 1 2 3\ng W\xe9b\nf 1 3 4\n")
    with pytest.raises(InputArtifactError, match=r"bad\.obj.*not UTF-8"):
        read_obj(bad)
    good = tmp_path / "good.obj"
    good.write_bytes(bad.read_bytes().replace(b"\xe9", "é".encode()))
    assert sorted(read_obj(good).families) == ["Wéa", "Wéb"]


def test_fr_1620_the_workflow_reader_refuses_a_missing_or_unsupported_unit(tmp_path):
    """FR-1620: no coordinate is used when the length-unit line is missing or unsupported."""
    from pyflightstream.workspace.wake_edges import read_trailing_edge_points

    for name, text in (
        ("none", "2,0.5,0\n2,0.6,0\n"),
        ("other", "OTHER\n2,0.5,0\n"),
        ("word", "furlongs\n2,0.5,0\n"),
    ):
        path = tmp_path / f"{name}.te.txt"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(InputArtifactError, match="unit"):
            read_trailing_edge_points(path)


@pytest.mark.parametrize(
    "table,key",
    [
        ({"file": "a.te.txt", "tolerance": 10**400}, "tolerance"),
        ({"detect": {"surfaces": ["Wing"], "sweep_angle": 10**400}}, "sweep_angle"),
    ],
)
def test_f1541_f1542_an_oversized_integer_is_a_named_refusal(tmp_path, table, key):
    """An integer too large for a float is the documented refusal, never an OverflowError."""
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace.sidecars import read_trailing_edges

    with pytest.raises(InputArtifactError, match=key):
        read_trailing_edges(tmp_path / "a.boundaries.toml", table)
