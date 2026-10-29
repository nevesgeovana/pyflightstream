"""prepare-to-refine cuts an ANSA NASTRAN export along its FE perimeters; visual-inspect.

The export is built here: a flat sheet of 4 x 2 quadrilaterals in one property,
and a perimeter block naming the sides of the line that splits it in two 2 x 2
halves, in the layout ANSA writes (a base64 field holding a 4-byte length and
zlib data: a count, then a 32-bit element id and a 16-bit side per record).
"""

from __future__ import annotations

import base64
import json
import struct
import tomllib
import warnings
import zlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace import prepare_to_refine, refine_mesh
from pyflightstream.workspace._refine import _blocks, _nastran
from pyflightstream.workspace._refine._config import (
    FamilySpec,
    RefineRequest,
    canonical_selection,
    level_tag,
    tag_selection,
)
from tests.p0380_mesh_fixtures import Composite, face_coordinates, read_mesh, write_source

COLUMNS, ROWS = 4, 2


def _continuity_source(tmp_path, *, shape="side", factor=2, keep=False):
    """Write two synthetic families for refine_mesh(source), with only A refined."""
    points, families = [], {"A": [], "B": []}

    def vertex(x, y):
        point = (x, y, 0)
        if point not in points:
            points.append(point)
        return points.index(point)

    def cell(name, x, y, *, mixed=False):
        a, b, c, d = (vertex(x, y), vertex(x + 1, y), vertex(x + 1, y + 1), vertex(x, y + 1))
        families[name].extend([[a, b, c], [a, c, d]] if mixed else [[a, b, c, d]])

    height = 2 if shape == "both" else 6
    for x in range(2):
        for y in range(height):
            cell("A", x, y)
    if shape == "both":
        for x in range(4):
            for y in range(4):
                if x >= 2 or y >= 2:
                    cell("B", x, y)
    else:
        start, stop = (10, 12) if shape == "isolated" else (2, 8 if shape == "mixed" else 4)
        for x in range(start, stop):
            for y in range(height):
                cell("B", x, y, mixed=shape == "mixed")
    config = (
        f'[families.A]\nmethod = "grid"\nnormal_factor = {factor}\n'
        f"parallel_factor = {factor}\ngoverning_parallel = true\ngoverning_normal = true\n"
    )
    if keep:
        config += '\n[families.B]\nmethod = "keep"\n'
    return write_source(
        tmp_path / "src",
        "continuity",
        Composite(np.array(points, dtype=float), families, np.zeros((0, 3)), {}),
        refine_toml=config,
    )


def _continuity_level(source):
    """Assert the continuity contract accepts the request before checking its mesh."""
    level, error = None, None
    try:
        level = refine_mesh(source)
    except InputArtifactError as caught:
        error = str(caught)
    assert error is None, f"continuity must warn and skip, not refuse: {error}"
    assert level is not None
    return level


@pytest.mark.requirement("FR-3299")
@pytest.mark.parametrize("governing", [False, True])
@pytest.mark.parametrize(
    "shape, directions", [("side", ["parallel"]), ("both", ["parallel", "normal"])]
)
def test_p0490_continuity_undeclared_grid_changes_only_crossing_bands(
    tmp_path, shape, directions, governing
):
    """P0490-KEEP: one shared direction changes one axis; an L neighbour needs both."""
    source = _continuity_source(tmp_path, shape=shape)
    if not governing:
        config = source.with_suffix(".refine.toml")
        config.write_text(config.read_text().replace(" = true", " = false"), encoding="utf-8")
    level = _continuity_level(source)
    entry = level.report["B"]
    assert entry.get("continuity", {}).get("directions") == directions
    assert entry["continuity"]["because"] == ["A"]
    assert entry["continuity"]["bands"]
    points, families = read_mesh(level.obj)
    held = points[sorted({v for f in families["B"] for v in f})]
    if shape == "side":
        assert len(set(held[:, 0])) == 3
        assert len(set(held[:, 1])) == 13
    else:
        assert len(set(held[:, 0])) == len(set(held[:, 1])) == 7
    record = json.loads(next(p for p in level.files if p.name.endswith(".refine.json")).read_text())
    labels = {b["label"] for layout in record["layouts"] for b in layout["bands"]}
    assert set(entry["continuity"]["bands"]) <= labels
    assert "B" not in record["unchanged_grids"]


@pytest.mark.requirement("FR-3299")
@pytest.mark.parametrize("shape, factor", [("side", 1), ("isolated", 2), ("side", 2), ("both", 2)])
def test_p0490_continuity_keep_and_omitted_tables_write_the_same_mesh(tmp_path, shape, factor):
    """P0490-KEEP: explicit keep equals omission, and unaffected families are exact copies."""
    source = _continuity_source(tmp_path / "implicit", shape=shape, factor=factor)
    implicit = _continuity_level(source)
    explicit = _continuity_level(
        _continuity_source(tmp_path / "explicit", shape=shape, factor=factor, keep=True)
    )
    a, af = read_mesh(implicit.obj)
    b, bf = read_mesh(explicit.obj)
    assert a.tobytes() == b.tobytes() and af == bf
    if factor == 1 or shape == "isolated":
        before, faces = read_mesh(source)
        assert face_coordinates(a, af["B"]) == face_coordinates(before, faces["B"])
        assert implicit.report["B"]["method"] in ("copied", "unchanged")
        assert "continuity" not in implicit.report["B"]


@pytest.mark.requirement("FR-3299")
@pytest.mark.parametrize("factor", [1, 2])
@pytest.mark.parametrize("keep", [False, True])
def test_p0490_continuity_mixed_changes_only_the_neighbour_band(tmp_path, factor, keep):
    """P0490-KEEP: mixed neighbours retain every face beyond the two-layer band."""
    source = _continuity_source(tmp_path, shape="mixed", factor=factor, keep=keep)
    level = _continuity_level(source)
    before, old = read_mesh(source)
    after, new = read_mesh(level.obj)
    old_faces, new_faces = face_coordinates(before, old["B"]), face_coordinates(after, new["B"])
    if factor == 1:
        assert old_faces == new_faces
        assert "continuity" not in level.report["B"]
    else:
        assert level.report["B"].get("continuity") == {"band": "remeshed", "because": ["A"]}
        assert level.report["B"]["band"] < len(old["B"])
        assert [f for f in old_faces if min(p[0] for p in f) >= 5] == [
            f for f in new_faces if min(p[0] for p in f) >= 5
        ]


@pytest.mark.requirement("FR-3299")
def test_p0490_continuity_keep_factors_warn_and_are_skipped(tmp_path):
    """P0490-KEEP: a factor in a keep table warns and cannot request refinement."""
    source = _continuity_source(tmp_path, shape="isolated", keep=True)
    config = source.with_suffix(".refine.toml")
    config.write_text(config.read_text() + "factor = 9\n", encoding="utf-8")
    with pytest.warns(PyflightstreamWarning, match="keep.*skipped"):
        level = _continuity_level(source)
    before, old = read_mesh(source)
    after, new = read_mesh(level.obj)
    assert face_coordinates(after, new["B"]) == face_coordinates(before, old["B"])


@pytest.mark.requirement("FR-3299")
def test_p0490_continuity_prepare_declares_followers_and_band_comments(tmp_path):
    """P0490-KEEP: prepared followers explicitly request both governing factors."""
    prepared = prepare_to_refine(_continuity_source(tmp_path))
    text = prepared.config.read_text(encoding="utf-8")
    tables = tomllib.loads(text)["families"]
    assert tables.get("B_001_grid") == {"method": "grid_auto"}
    assert "# follows A_001_grid (parallel) and A_001_grid (normal)\n[families.B_001_grid]" in text
    assert "# leads " in text and "P1" in text and "N1" in text


def _node(i: int, j: int) -> int:
    return 1 + i + (COLUMNS + 1) * j


def _element(i: int, j: int) -> int:
    return 1 + i + COLUMNS * j


def _block(records: list[tuple[int, int]]) -> str:
    body = struct.pack(">I", len(records)) + b"".join(struct.pack(">IH", e, s) for e, s in records)
    return base64.b64encode(struct.pack(">I", len(body)) + zlib.compress(body)).decode()


def _ids_block(ids: list[int]) -> str:
    body = struct.pack(">I", len(ids)) + b"".join(struct.pack(">I", i) for i in ids)
    return base64.b64encode(struct.pack(">I", len(body)) + zlib.compress(body)).decode()


def _export(path: Path, *, wide: bool, perimeter: str | None, only: bool = False) -> Path:
    lines = ["$ANSA_VERSION;25.1.2;", "BEGIN BULK"]
    for j in range(ROWS + 1):
        for i in range(COLUMNS + 1):
            x, y = f"{1000.0 * i:.1f}", f"{1000.0 * j:.1f}"
            if wide:
                lines += [
                    f"GRID*   {_node(i, j):>16}{'':>16}{x:>16}{y:>16}*",
                    f"*       {'0.':>16}",
                ]
            else:
                lines.append(f"GRID    {_node(i, j):>8}{'':>8}{x:>8}{y:>8}{'0.':>8}")
    for j in range(ROWS):
        for i in range(COLUMNS):
            g = [_node(i, j), _node(i + 1, j), _node(i + 1, j + 1), _node(i, j + 1)]
            if wide:
                lines += [
                    f"CQUAD4* {_element(i, j):>16}{1:>16}{g[0]:>16}{g[1]:>16}*",
                    f"*       {g[2]:>16}{g[3]:>16}",
                ]
            else:
                lines.append("CQUAD4  " + "".join(f"{v:>8}" for v in (_element(i, j), 1, *g)))
    lines += ["$Sheet", "PSHELL         1       1      1."]
    if perimeter is not None:
        text = f"0;{perimeter};" + ("" if only else f"{_ids_block([1, 3])};1;{_block([])};")
        lines.append("$ANSA_FE_PERIMETER;" + text[:60])
        lines += ["$" + text[k : k + 70] for k in range(60, len(text), 70)]
    lines.append("ENDDATA")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _middle_line() -> str:
    # Side 2 of the elements in column 1 joins nodes 2 and 3: the line x = 2000 mm.
    return _block([(_element(1, j), 2) for j in range(ROWS)])


@pytest.mark.parametrize("wide", [False, True])
def test_the_families_are_cut_along_the_fe_perimeters(tmp_path: Path, wide: bool) -> None:
    source = _export(tmp_path / "sheet.nas", wide=wide, perimeter=_middle_line())
    prepared = prepare_to_refine(source)
    assert prepared.patches == {"Sheet": ["Sheet_001_grid", "Sheet_002_grid"]}
    text = prepared.obj.read_text(encoding="utf-8")
    assert text.count("\ng Sheet_00") == 2
    xs = [float(line.split()[1]) for line in text.splitlines() if line.startswith("v ")]
    assert max(xs) == pytest.approx(4.0)  # MILLIMETER written in METER


def test_without_a_perimeter_block_the_families_are_cut_at_sharp_edges(tmp_path: Path) -> None:
    source = _export(tmp_path / "flat.nas", wide=False, perimeter=None)
    with pytest.warns(PyflightstreamWarning, match="FE perimeters"):
        prepared = prepare_to_refine(source)
    assert prepared.patches == {"Sheet": ["Sheet_001_grid"]}


def test_a_block_that_does_not_read_is_warned_and_skipped(tmp_path: Path) -> None:
    source = _export(tmp_path / "bad.nas", wide=False, perimeter="AAAA!!notzlib", only=True)
    with pytest.warns(PyflightstreamWarning, match="does not read"):
        prepared = prepare_to_refine(source)
    assert prepared.patches == {"Sheet": ["Sheet_001_grid"]}


def test_the_reader_keeps_the_grid_order_and_converts_the_unit(tmp_path: Path) -> None:
    source = _export(tmp_path / "s.nas", wide=True, perimeter=_middle_line())
    read = _nastran.read_nastran(source, unit="MILLIMETER", obj_unit="MILLIMETER")
    assert read.mesh.verts[1].tolist() == [1000.0, 0.0, 0.0]
    assert list(read.mesh.families) == ["Sheet"]
    assert len(read.mesh.families["Sheet"]) == COLUMNS * ROWS
    assert read.perimeter == {(2, 7), (7, 12)}  # x = 2000 mm, vertex index = GRID id - 1


def test_nastran_reals_take_the_short_exponent() -> None:
    assert _nastran.real("1.5-3") == pytest.approx(1.5e-3)
    assert _nastran.real("-2.+4") == pytest.approx(-2.0e4)
    assert _nastran.real("3.25E+1") == pytest.approx(32.5)


def test_visual_inspect_writes_the_pdf_and_counts_the_marked_points(tmp_path: Path) -> None:
    from pyflightstream.workspace._visual_inspect import marked_points, visual_inspect

    source = _export(tmp_path / "sheet.nas", wide=False, perimeter=_middle_line())
    prepared = prepare_to_refine(source)
    te = tmp_path / "sheet.te.txt"
    te.write_text("METER\n4.0,0.5,0.0\n4.0,1.5,0.0\n9.0,9.0,9.0\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pdf = visual_inspect(prepared.obj, te=[te], mesh_unit="METER", dpi=60)
    assert pdf.read_bytes()[:5] == b"%PDF-"
    from pyflightstream.workspace._visual_inspect import (
        Scene,
        patch_colors,
        read_obj,
        read_points_file,
    )

    mesh = read_obj(prepared.obj)
    names = list(mesh.patches)
    colors, _ = patch_colors(names, None)
    marked = marked_points(Scene(mesh, names, colors, None), [read_points_file(te, "METER")])
    assert marked.points == [0, 2] or marked.points == [2, 0]
    assert marked.total_points == 3
    assert marked.on_no_patch == 1


def test_visual_inspect_png_writes_the_views_page_and_one_file_per_view(tmp_path: Path) -> None:
    from pyflightstream.workspace import visual_inspect

    prepared = prepare_to_refine(
        _export(tmp_path / "sheet.nas", wide=False, perimeter=_middle_line())
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pdf = visual_inspect(prepared.obj, mesh_unit="METER", dpi=40, png=True)
    pngs = sorted(path.name for path in pdf.parent.glob(f"{pdf.stem}*.png"))
    views = [f"{pdf.stem}.{view}.png" for view in ("front", "iso", "side", "top")]
    assert pngs == sorted([f"{pdf.stem}.png", *views])
    assert all((pdf.parent / name).read_bytes()[:4] == b"\x89PNG" for name in pngs)


def test_a_segment_of_another_layout_does_not_discard_the_side_block() -> None:
    body = struct.pack(">I", 1) + struct.pack(">IH", 7, 2)
    good = base64.b64encode(struct.pack(">I", len(body)) + zlib.compress(body)).decode()
    raw = base64.b64encode(b"\x00\x00\x00\x08rawbytes").decode()
    assert _nastran.decode_sides("PART_NAME_LONG;" + raw + ";" + good) == [(7, 2)]


def _captured_points(tmp_path: Path, **units: str) -> list:
    from pyflightstream.workspace._visual_inspect import load_points

    nodes = tmp_path / "n.txt"
    nodes.write_text("#  Id, Name, X, Y, Z\n1, a, 1000.0, 0.0, 0.0\n", encoding="utf-8")
    points = load_points([nodes], [], **units)
    return [float(v) for v in points[0].xyz[0]]


def test_length_unit_names_are_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "u").mkdir()
    (tmp_path / "l").mkdir()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        upper = _captured_points(tmp_path / "u", mesh_unit="METER", points_unit="MILLIMETER")
        lower = _captured_points(tmp_path / "l", mesh_unit="meter", points_unit="millimeter")
    assert lower == upper == pytest.approx([1.0, 0.0, 0.0])


def test_an_unknown_unit_warns_and_draws_the_points_as_written(tmp_path: Path) -> None:
    with pytest.warns(PyflightstreamWarning, match="(?i)furlong"):
        xyz = _captured_points(tmp_path, mesh_unit="METER", points_unit="furlong")
    assert xyz == [1000.0, 0.0, 0.0]


def test_an_unknown_nastran_unit_warns_and_reads_the_mesh_unscaled(tmp_path: Path) -> None:
    from pyflightstream.workspace import visual_inspect

    source = _export(tmp_path / "sheet.nas", wide=False, perimeter=_middle_line())
    with pytest.warns(PyflightstreamWarning, match="(?i)furlong"):
        pdf = visual_inspect(source, nastran_unit="furlong", dpi=40)
    assert pdf.read_bytes()[:5] == b"%PDF-"


def test_a_latin1_obj_keeps_distinct_group_names_and_warns(tmp_path: Path) -> None:
    from pyflightstream.workspace._visual_inspect import read_obj

    obj = tmp_path / "latin.obj"
    obj.write_bytes(b"v 0 0 0\nv 1 0 0\nv 0 1 0\ng wing\xe9\nf 1 2 3\ng wing\xe8\nf 1 2 3\n")
    with pytest.warns(PyflightstreamWarning, match="not UTF-8"):
        mesh = read_obj(obj)
    assert len(mesh.patches) == 2


def test_a_malformed_obj_line_is_skipped_and_counted_not_raised(tmp_path: Path) -> None:
    from pyflightstream.workspace._visual_inspect import read_obj

    obj = tmp_path / "bad.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 1 x 0\nf 1 2 3\nf 1 2 q\nf 1 2 4\n")
    with pytest.warns(PyflightstreamWarning, match=r"3 line\(s\)"):
        mesh = read_obj(obj)
    assert [len(f) for f in mesh.patches.values()] == [1]


def test_the_nodes_and_te_flags_can_repeat() -> None:
    from pyflightstream.workspace.cli import _build_parser

    args = _build_parser().parse_args(
        ["geometry", "visual-inspect", "wing.obj", "--te", "a", "--te", "b", "--nodes", "n", "m"]
    )
    assert [str(x) for x in args.te] == ["a", "b"]
    assert [str(x) for x in args.nodes] == ["n", "m"]


def test_visual_inspect_names_the_nastran_unit_unit_as_prepare_to_refine_does() -> None:
    from pyflightstream.workspace.cli import _build_parser

    parser = _build_parser()
    for verb in ("visual-inspect", "prepare-to-refine"):
        args = parser.parse_args(["geometry", verb, "wing.nas", "--unit", "METER"])
        assert args.unit == "METER", verb
    with pytest.raises(SystemExit):
        parser.parse_args(["geometry", "visual-inspect", "wing.nas", "--nastran-unit", "METER"])


def test_fr3298_prepare_marks_one_governing_patch_per_touching_group(tmp_path):
    """FR-3298: one governing grid patch per touching group; the other grids are left out."""
    import tomllib

    from pyflightstream.workspace._refine._prepare import prepare_to_refine

    src = tmp_path / "plate.obj"
    lines = []
    for j in range(3):
        for i in range(7):
            lines.append(f"v {i:.1f} {j:.1f} 0.0")
    lines.append("g A")
    for j in range(2):
        for i in range(3):
            a = j * 7 + i + 1
            lines.append(f"f {a} {a + 1} {a + 8} {a + 7}")
    lines.append("g B")
    for j in range(2):
        for i in range(3, 6):
            a = j * 7 + i + 1
            lines.append(f"f {a} {a + 1} {a + 8} {a + 7}")
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    prepared = prepare_to_refine(src, visual_inspect=True)
    assert prepared.inspect == tmp_path / "plate_patches.inspect.pdf"
    pdf = prepared.inspect.read_bytes()
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 2
    assert len(prepared.governing) == 1
    table = tomllib.loads(prepared.config.read_text(encoding="utf-8"))["families"]
    governing = [
        n for n, t in table.items() if t.get("governing_parallel") and t.get("governing_normal")
    ]
    grids = [p for ps in prepared.patches.values() for p in ps if p.endswith("_grid")]
    assert len(grids) == 2 and len(governing) == 1
    assert all(table[g] == {"method": "grid_auto"} for g in grids if g not in governing)


# ------------------------------------- FR-3298 governing families: governing-r1 cases


def _layout(specs):
    verts = np.array([(x, y, 0) for x in range(10) for y in range(3)], dtype=float)
    families = {}
    for name, start, end in (("A", 0, 4), ("B", 4, 6), ("C", 6, 9)):
        families[name] = [
            [x * 3 + y, (x + 1) * 3 + y, (x + 1) * 3 + y + 1, x * 3 + y + 1]
            for x in range(start, end)
            for y in range(2)
        ]
    if "D" in specs:
        # A corner connects the layout without adding D to the A/B/C shared band.
        verts = np.vstack([verts, [(9, 3, 0), (10, 2, 0), (10, 3, 0)]])
        families["D"] = [[29, 31, 32, 30]]
    grids = {
        n: _blocks.recover_family(
            verts, fs, {v for f in fs for v in f if verts[v, 1] == (2 if n == "D" else 0)}
        )
        for n, fs in families.items()
    }
    assert all(not isinstance(g, str) for g in grids.values())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        layouts, late = _blocks.plan(
            verts, families, grids, specs, {n: set() for n in families}, where="plates"
        )
    assert late == []
    return layouts["A"], [str(w.message) for w in caught]


@pytest.mark.requirement("FR-3300")
def test_p0490_continuity_band_labels_are_stable_and_name_the_dominant_arc():
    """P0490-LABELS: source-order leads and their first arcs number each direction."""

    def planned():
        return _layout(
            {
                "A": FamilySpec(factor=2, governing_parallel=True),
                "B": FamilySpec(factor=3, governing_normal=True),
                "C": FamilySpec(factor=1),
            }
        )[0]

    first, second = planned(), planned()
    labels = getattr(first, "labels", {})
    assert set(labels) == set(range(len(first.blocks.arcs))), "the planner must label every band"
    assert labels == second.labels and first.leads == second.leads
    bands = _blocks.arc_bands(first.blocks, labels)
    assert len(set(labels.values())) == len(set(bands.values()))
    for arc, label in labels.items():
        lead, dominant = first.leads[label]
        mine = {a for p in first.patches_of(lead) for a, _ in first.blocks.sides[p]}
        assert dominant == min(a for a in mine if labels[a] == label)
        assert labels[dominant] == label
        assert all(labels[a] == label for a in labels if bands[a] == bands[arc])
    for prefix in ("P", "N"):
        ordered = sorted(
            (label for label in first.leads if label.startswith(prefix)),
            key=lambda label: (first.names.index(first.leads[label][0]), first.leads[label][1]),
        )
        assert ordered == [f"{prefix}{i}" for i in range(1, len(ordered) + 1)]


@pytest.mark.requirement("FR-3300")
def test_p0490_continuity_json_records_label_direction_lead_and_count(tmp_path):
    """P0490-LABELS: the written record retains the planner's band identifiers."""
    source = _topology_source(tmp_path)
    level = refine_mesh(source)
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    bands = json.loads(record.read_text(encoding="utf-8"))["layouts"][0]["bands"]
    assert bands and all("label" in band and "count" in band for band in bands)
    for band in bands:
        assert band["label"].startswith("P" if band["direction"] == "parallel" else "N")
        assert band["lead"] in ("A", "B")
        assert band["dominant_arc"] in band["arcs"]
        assert band["count"] > 0


@pytest.mark.requirement("FR-3300")
def test_p0490_continuity_dominant_arc_supplies_the_selected_directional_count():
    """P0490-LABELS: conflicting local directions retain the count-setting arc."""
    points = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (2, 0, 0), (2, 1, 0)])
    blocks = _blocks.Blocks(
        arcs=((2, 3), (0, 1), (0, 2), (1, 3), (1, 4), (3, 5)),
        sides=(
            ((1, False), (0, False), (2, False), (3, False)),
            ((1, False), (2, False), (4, False), (5, False)),
        ),
        patches=(np.array([[0, 1], [2, 3]]), np.array([[0, 2], [4, 5]])),
        cells=(np.array([[0]]), np.array([[1]])),
        te_arcs=frozenset(),
    )
    layouts, late = _blocks.plan(
        points,
        {"B": [[0, 1, 3, 2], [0, 2, 5, 4]]},
        {"B": blocks},
        {"B": FamilySpec(chordwise=3, spanwise=2, governing_normal=True)},
        {"B": {(0, 1)}},
        where="conflicting patches",
    )
    assert not late
    layout = layouts["B"]
    assert hasattr(layout, "labels"), "the planner must retain its band labels"
    assert layout.counts[0] == 3
    lead, dominant = layout.leads[layout.labels[0]]
    assert lead == "B" and dominant != 0
    assert any(
        told[dominant].direction == "normal"
        for told in layout.directions.values()
        if dominant in told
    )


def test_p0490_a_shared_band_crosses_three_families_with_one_count():
    """P0490-GOVERNING (FR-3298): opposite sides and shared arcs propagate A's count."""
    layout, messages = _layout(
        {
            "A": FamilySpec(factor=2, governing=True),
            "B": FamilySpec(factor=3),
            "C": FamilySpec(factor=4),
        }
    )
    assert layout.names == ("A", "B", "C")
    shared = set(a for a, _ in layout.blocks.sides[0]) & set(a for a, _ in layout.blocks.sides[1])
    assert len(shared) == 1
    bands = _blocks.arc_bands(layout.blocks, range(len(layout.blocks.arcs)))
    shared_band = bands[next(iter(shared))]
    assert {layout.counts[a] for a, band in bands.items() if band == shared_band} == {4}
    for sides in layout.blocks.sides:
        a, b, c, d = (layout.counts[arc] for arc, _ in sides)
        assert a == b and c == d
    for name in ("B", "C"):
        message = next(m for m in messages if f"family {name} follows A" in m)
        assert "on 1 band(s)" in message, message


def test_p0490_declared_family_leads_larger_grid_auto_and_warning_explains_override():
    """P0490-GOVERNING (FR-3298): a grid_auto offer never outranks a declared offer."""
    layout, messages = _layout(
        {
            "A": FamilySpec(factor=2, method="grid_auto"),
            "B": FamilySpec(factor=3),
            "C": FamilySpec(factor=4, method="grid_auto"),
            "D": FamilySpec(factor=2, governing=True),
        }
    )
    shared = set(a for a, _ in layout.blocks.sides[0]) & set(a for a, _ in layout.blocks.sides[1])
    assert {layout.counts[a] for a in shared} == {6}
    message = next(m for m in messages if "family A follows B" in m)
    assert 'method = "grid"' in message and "factors" in message, message


def test_p0490_prepare_declares_isolated_grid_beside_three_touching_grids(tmp_path):
    """P0490-GOVERNING (FR-3298): touching followers are explicit grid_auto tables."""
    source = tmp_path / "plates.obj"
    lines = [f"v {x} {y} 0" for x in range(15) for y in range(3)]
    for name, start, end in (("A", 0, 2), ("B", 2, 5), ("C", 5, 9), ("D", 12, 14)):
        lines.append(f"g {name}")
        for x in range(start, end):
            for y in range(2):
                a = x * 3 + y + 1
                lines.append(f"f {a} {a + 3} {a + 4} {a + 1}")
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    prepared = prepare_to_refine(source)
    tables = tomllib.loads(prepared.config.read_text(encoding="utf-8"))["families"]
    a, b, c, d = (prepared.patches[n][0] for n in "ABCD")
    assert tables[a]["governing_parallel"] is True
    assert tables[c]["governing_normal"] is True
    assert tables[b] == {"method": "grid_auto"}
    assert d in tables, "the isolated grid must retain its own factor table"
    assert tables[d] == {"method": "grid", "factor": 1.0}
    level = refine_mesh(prepared.obj)
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    report = json.loads(record.read_text(encoding="utf-8"))["families"]
    assert report[b]["provenance"] == {f"propagated_from:{a}": 2, f"propagated_from:{c}": 2}


@pytest.mark.parametrize("declared", [False, True])
def test_p0490_governing_does_not_refine_an_unselected_isolated_grid(tmp_path, declared):
    """P0490-GOVERNING (FR-916): selecting A leaves isolated B unchanged."""
    verts = np.array([(x, y, 0) for x in (0, 1, 4, 5) for y in (0, 1)], dtype=float)
    families = {"A": [[0, 2, 3, 1]], "B": [[4, 6, 7, 5]]}
    mesh = Composite(verts, families, np.zeros((0, 3)), {})
    source = write_source(
        tmp_path / "src",
        "plates",
        mesh,
        refine_toml='[families.A]\nmethod = "grid"\nfactor = 2\ngoverning = true\n'
        + ("[families.B]\nfactor = 3\n" if declared else ""),
    )
    level = refine_mesh(source, families=["A"])
    out, faces = read_mesh(level.obj)
    assert face_coordinates(out, faces["B"]) == face_coordinates(verts, families["B"])
    assert level.report["B"]["method"] == "copied"
    assert len(faces["A"]) == 4


def test_p0490_governing_changes_a_short_level_tag():
    """P0490-GOVERNING (FR-3298): swapping the leader cannot reuse one level folder."""
    first = RefineRequest(
        specs={"A": FamilySpec(factor=2, governing=True), "B": FamilySpec(factor=3)}
    )
    second = replace(
        first, specs={"A": FamilySpec(factor=2), "B": FamilySpec(factor=3, governing=True)}
    )
    assert canonical_selection(first, ["A", "B"]) != canonical_selection(second, ["A", "B"])
    assert level_tag(first, ["A", "B"]) != level_tag(second, ["A", "B"])
    assert tag_selection(first, ["A", "B"]) == ["A", "B"]


def test_p0490_grid_auto_tags_include_the_leaders_directional_factors():
    """P0490-GOVERNING: inherited factors and grid_auto participate in the hash."""
    first = RefineRequest(
        specs={
            "A": FamilySpec(chordwise=2, spanwise=3, governing=True),
            "B": FamilySpec(method="grid_auto"),
        }
    )
    second = replace(first, specs={**first.specs, "A": replace(first.specs["A"], spanwise=4)})
    assert level_tag(first, ["A", "B"]) != level_tag(second, ["A", "B"])
    assert tag_selection(first, ["A", "B"]) == ["A", "B"]
    explicit = replace(first, tag="named")
    assert level_tag(explicit, ["A", "B"]) == "named"
    assert tag_selection(explicit, ["A", "B"]) is None
    plain = RefineRequest(specs={"A": FamilySpec(factor=2), "B": FamilySpec(factor=2)})
    assert level_tag(plain, ["A", "B"]) == "R2"


def test_govr1_q02_governing_on_grid_auto_is_warned_and_skipped():
    """FR-3298 (GOVR1-Q02): a grid_auto family has no factors of its own to lead with."""
    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.workspace._refine._config import grid_auto_spec

    with pytest.warns(PyflightstreamWarning, match="cannot lead; governing is skipped"):
        spec = grid_auto_spec("[families.G]", {"method": "grid_auto"}, governing=True)
    assert spec.method == "grid_auto" and not spec.governing


@pytest.mark.parametrize("count", [21, 41, 121])
def test_patch_pdf_legend_stays_inside_its_column(tmp_path, monkeypatch, count):
    """GOVR2-001: long names and many patches must not clip the page's legend."""
    from matplotlib.backends.backend_pdf import PdfPages

    from pyflightstream.workspace._visual_inspect import BOTTOM, RIGHT, TOP, patches_pdf

    source = tmp_path / "patches.obj"
    names = [f"MainSurface_{i:03d}_grid" for i in range(count)]
    lines = ["v 0 0 0", "v 1 0 0", "v 1 1 0", "v 0 1 0"]
    for name in names:
        lines += [f"g {name}", "f 1 2 3 4"]
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    save = PdfPages.savefig
    pages = []

    def checked_save(pdf, fig, **kwargs):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        legend = fig.legends[0]
        bounds = legend.get_window_extent(renderer).transformed(fig.transFigure.inverted())
        width, height = fig.get_size_inches()
        assert (width - RIGHT) / width <= bounds.x0 < bounds.x1 <= 1 - 0.1 / width
        assert BOTTOM / height <= bounds.y0 < bounds.y1 <= 1 - TOP / height
        labels = [t.get_text() for t in legend.get_texts()]
        assert labels == [f"{names[0]}  (GOVERNING PARALLEL, GOVERNING NORMAL)", *names[1:]]
        for ax in fig.axes[:4]:
            assert sum("GOVERNING" in t.get_text() for t in ax.texts) == 1
            assert any("GOVERNING PARALLEL\nGOVERNING NORMAL" in t.get_text() for t in ax.texts)
        pages.append(fig)
        return save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", checked_save)
    target = patches_pdf(
        source, {"MainSurface": names}, {names[0]: (True, True)}, tmp_path / "patches.pdf", dpi=40
    )
    assert target.read_bytes().startswith(b"%PDF")
    assert len(pages) == 1


def test_grid_auto_governing_reference_matches_file_parsing(tmp_path):
    """GOVR2-002: the reference must state the adopted grid_auto governing exception."""
    from pyflightstream.workspace._refine._config import resolve_request

    mesh = tmp_path / "sheet.obj"
    mesh.with_suffix(".refine.toml").write_text(
        '[families.G]\nmethod = "grid_auto"\ngoverning = true\n', encoding="utf-8"
    )
    with pytest.warns(PyflightstreamWarning, match="cannot lead; governing is skipped"):
        request = resolve_request(mesh, ["G", "Other"])
    assert request.specs == {"G": FamilySpec(method="grid_auto")}
    reference = Path(__file__).resolve().parents[2] / "docs/mesh/reference.md"
    row = next(
        line
        for line in reference.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `[families.<name>]` | `governing` |")
    )
    assert '"grid_auto"' in row and "warned and skipped" in row


def _topology_source(tmp_path, *, corner=False, ring=False):
    """Synthetic plates: refine_mesh(source) must transfer directions through curves."""
    points, families = [], {}

    def vertex(x, y):
        point = (x, y, 0)
        if point not in points:
            points.append(point)
        return points.index(point)

    def plate(name, xs, ys):
        families[name] = [
            [vertex(x, y), vertex(u, y), vertex(u, v), vertex(x, v)]
            for x, u in zip(xs, xs[1:], strict=False)
            for y, v in zip(ys, ys[1:], strict=False)
        ]

    if ring:
        plate("A", [-1, 0, 1], [-1, 0, 1])
        edge = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
        for side, name in enumerate("BCDE"):
            families[name] = [
                [
                    vertex(s * x, s * y),
                    vertex(s * u, s * v),
                    vertex((s + 1) * u, (s + 1) * v),
                    vertex((s + 1) * x, (s + 1) * y),
                ][::-1]
                for s in (1, 2)
                for (x, y), (u, v) in list(zip(edge, edge[1:] + edge[:1], strict=True))[
                    side * 2 : side * 2 + 2
                ]
            ]
    else:
        plate("A", [0, 1, 2], list(range(7)))
        plate("B", [2, 7, 12], list(range(7)))
        if corner:
            plate("C", [0, -1, -2], [6, 7, 8])
    mesh = Composite(np.array(points, dtype=float), families, np.zeros((0, 3)), {})
    return write_source(
        tmp_path / "src",
        "topology",
        mesh,
        refine_toml='[families.A]\nmethod = "grid"\nnormal_factor = 2\n'
        "parallel_factor = 3\ngoverning = true\n"
        + "".join(f'\n[families.{n}]\nmethod = "grid_auto"\n' for n in families if n != "A"),
    )


@pytest.mark.requirement("FR-3298")
def test_p0490_topology_follower_uses_governing_directions(tmp_path):
    source = _topology_source(tmp_path)
    level = refine_mesh(source)
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    report = json.loads(record.read_text(encoding="utf-8"))["families"]
    assert report["B"]["blocks"] == [{"rows": [2, 4], "columns": [6, 18]}]
    assert report["B"]["grid_auto"]["directions"] == "from A"


@pytest.mark.requirement("FR-3298")
@pytest.mark.parametrize("reason", ["conflict", "unlinked"])
def test_p0490_topology_fallback_warns_and_records_own_reference(tmp_path, reason):
    source = _topology_source(tmp_path, ring=reason == "conflict", corner=reason == "unlinked")
    name = "B" if reason == "conflict" else "C"
    with pytest.warns(PyflightstreamWarning, match=f"family {name}.*{reason}"):
        level = refine_mesh(source)
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    report = json.loads(record.read_text(encoding="utf-8"))["families"]
    assert report[name]["grid_auto"]["directions"] == f"own reference: {reason}"
    assert set(report[name].get("provenance", {})) == {f"own_orientation_{reason}"}
    assert level.report[name]["method"] == "grid"
    config = source.with_suffix(".refine.toml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(f'[families.{name}]\nmethod = "grid_auto"\n', "")
        + f'\n[families.{name}]\nmethod = "grid"\nnormal_factor = 2\nparallel_factor = 3\n',
        encoding="utf-8",
    )
    own = refine_mesh(source, out_dir=tmp_path / "own")
    assert level.report[name]["blocks"] == own.report[name]["blocks"]


@pytest.mark.requirement("FR-3298")
def test_p0490_topology_prepare_declares_corner_only_patch(tmp_path):
    source = _topology_source(tmp_path, corner=True)
    with pytest.warns(PyflightstreamWarning, match="C_001_grid.*unlinked"):
        prepared = prepare_to_refine(source)
    text = prepared.config.read_text(encoding="utf-8")
    tables = tomllib.loads(text)["families"]
    assert tables["A_001_grid"]["governing_parallel"] is True
    assert tables["B_001_grid"]["governing_normal"] is True
    assert tables["C_001_grid"] == {"method": "grid", "factor": 1.0}
    assert "# not a follower of A_001_grid, B_001_grid: unlinked\n[families.C_001_grid]" in text


@pytest.mark.requirement("FR-3298")
def test_p0490_planner_factors_do_not_cross_a_mixed_bridge(tmp_path):
    """P0490-PLANNER R2: each follower takes the governing factors of its grid layout."""
    points, families = [], {}

    def vertex(x, y):
        point = (x, y, 0)
        if point not in points:
            points.append(point)
        return points.index(point)

    def plate(name, xs):
        families[name] = [
            [vertex(x, y), vertex(u, y), vertex(u, y + 1), vertex(x, y + 1)]
            for x, u in zip(xs, xs[1:], strict=False)
            for y in range(6)
        ]

    plate("A", [0, 1, 2])
    plate("B", [2, 7, 12])
    plate("C", [30, 40, 50])
    plate("D", [50, 51, 52])
    families["bridge_mixed"] = [[vertex(12, 6), vertex(30, 6), vertex(20, 8)]]
    mesh = Composite(np.array(points, dtype=float), families, np.zeros((0, 3)), {})
    source = write_source(
        tmp_path / "src",
        "groups",
        mesh,
        refine_toml='[families.A]\nmethod = "grid"\nnormal_factor = 2\n'
        'parallel_factor = 3\ngoverning = true\n[families.C]\nmethod = "grid"\n'
        "normal_factor = 4\nparallel_factor = 5\ngoverning = true\n"
        '[families.B]\nmethod = "grid_auto"\n[families.D]\nmethod = "grid_auto"\n'
        "[families.bridge_mixed]\nfactor = 1\n",
    )
    level = refine_mesh(source)
    assert level.report["B"]["grid_auto"]["follows"] == "A"
    assert level.report["B"]["grid_auto"]["factors"] == [2, 3]
    assert level.report["D"]["grid_auto"]["follows"] == "C"
    assert level.report["D"]["grid_auto"]["factors"] == [4, 5]


def test_p0490_planner_governing_is_resolved_per_direction(tmp_path):
    """P0490-PLANNER: A leads parallel, C leads normal, and B inherits both factors."""
    from pyflightstream.workspace._refine._config import resolve_request

    source = tmp_path / "plates.obj"
    source.with_suffix(".refine.toml").write_text(
        "[families.A]\nfactor = 2\ngoverning_parallel = true\n"
        '[families.B]\nmethod = "grid_auto"\n'
        "[families.C]\nfactor = 4\ngoverning_normal = true\n",
        encoding="utf-8",
    )
    request = None
    try:
        request = resolve_request(source, ["A", "B", "C"])
    except InputArtifactError:
        pass
    assert request is not None, "directional governing keys must be accepted"
    layout, _ = _layout(request.specs)
    shared = set(a for a, _ in layout.blocks.sides[0]) & set(a for a, _ in layout.blocks.sides[1])
    assert {layout.counts[a] for a in shared} == {8}
    assert request.specs["B"].directions == (4, 2)
    records = [d for p in layout.patches_of("B") for d in layout.directions[p].values()]
    assert {(d.direction, d.source_family) for d in records} == {("parallel", "A"), ("normal", "C")}


def test_p0490_planner_legacy_governing_warns_and_means_both(tmp_path):
    """P0490-PLANNER: the earlier spelling remains accepted as both directions."""
    from pyflightstream.workspace._refine._config import resolve_request

    source = tmp_path / "plates.obj"
    source.with_suffix(".refine.toml").write_text(
        "[families.A]\nfactor = 2\ngoverning = true\n",
        encoding="utf-8",
    )
    with pytest.warns(PyflightstreamWarning, match="earlier spelling"):
        request = resolve_request(source, ["A", "B"])
    assert getattr(request.specs["A"], "leads", ()) == (True, True)
    assert "B" not in request.specs


def test_p0490_prepare_short_rearmost_line_refines_its_own_toml(tmp_path):
    """P0490-PLANNER R1: the written reference cannot certify this sheet as a grid."""
    widths = [2, 4, 6, 8, 10, 10, 10, 8, 6, 4, 2]
    points = np.array([(i * widths[j] / 2, j, 0) for j in range(11) for i in range(3)])
    faces = [
        [j * 3 + i, j * 3 + i + 1, (j + 1) * 3 + i + 1, (j + 1) * 3 + i]
        for j in range(10)
        for i in range(2)
    ]
    source = write_source(
        tmp_path / "src", "short_reference", Composite(points, {"A": faces}, np.zeros((0, 3)), {})
    )
    prepared = prepare_to_refine(source)
    assert prepared.patches["A"] == ["A_001_grid"]
    error = None
    try:
        level = refine_mesh(prepared.obj)
    except InputArtifactError as caught:
        error = str(caught)
    assert error is None, f"prepare's own TOML must refine without refusal: {error}"
    assert level.obj.is_file()


def test_p0490_prepare_tube_touching_sheet_refines_its_own_toml(tmp_path):
    """P0490-PLANNER R3: a tube excluded from the sheet's layout is declared auto."""
    from tests.p0380_mesh_fixtures import body_of_revolution

    body = body_of_revolution()
    points = body.verts.copy()
    points[:, :2] = points[:, :2] @ np.array(
        [[np.cos(0.2), -np.sin(0.2)], [np.sin(0.2), np.cos(0.2)]]
    )
    corner = int(np.argmin(points[:, 0]))
    origin, sheet = points[corner].copy(), [corner]
    for j in range(3):
        for i in range(3):
            if i or j:
                sheet.append(len(points))
                points = np.vstack([points, origin + [-i, j, 0]])
    faces = [
        [sheet[j * 3 + i], sheet[j * 3 + i + 1], sheet[(j + 1) * 3 + i + 1], sheet[(j + 1) * 3 + i]]
        for j in range(2)
        for i in range(2)
    ]
    source = write_source(
        tmp_path / "src",
        "tube_sheet",
        Composite(points, {"A": faces, "B": body.faces}, np.zeros((0, 3)), {}),
    )
    prepared = prepare_to_refine(source, max_angle=0)
    error = None
    try:
        level = refine_mesh(prepared.obj)
    except InputArtifactError as caught:
        error = str(caught)
    assert error is None, f"prepare must not demand an unjoinable tube grid: {error}"
    tables = tomllib.loads(prepared.config.read_text(encoding="utf-8"))["families"]
    assert tables["B_001_grid"]["method"] == "auto"
    assert level.obj.is_file()
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    report = json.loads(record.read_text(encoding="utf-8"))["families"]
    assert report["A_001_grid"]["directions"] == {"parallel": 0, "normal": 0}
    assert report["A_001_grid"]["provenance"] == {}


@pytest.mark.parametrize("corner", [False, True])
def test_p0490_planner_json_records_directions_provenance_and_band_leads(tmp_path, corner):
    """P0490-PLANNER: JSON retains arc direction counts, their origins and each band's lead."""
    source = _topology_source(tmp_path, corner=corner)
    level = refine_mesh(source)
    record = next(p for p in level.files if p.name.endswith(".refine.json"))
    report = json.loads(record.read_text(encoding="utf-8"))
    families = report["families"]
    for name in ("A", "B"):
        assert families[name].get("directions") == {"parallel": 2, "normal": 2}
    assert families["A"].get("provenance") == {"longest_side": 4}
    assert families["B"].get("provenance") == {"propagated_from:A": 4}
    if corner:
        assert families["C"].get("directions") == {"parallel": 2, "normal": 2}
        assert families["C"].get("provenance") == {"own_orientation_unlinked": 4}
    layouts = report.get("layouts", [])
    assert len(layouts) == 1
    assert layouts[0]["families"] == ["A", "B", *(["C"] if corner else [])]
    bands = layouts[0]["bands"]
    assert any(
        b["lead"] == "A" and b["direction"] == "parallel" and len(b["arcs"]) == 3 for b in bands
    )
    assert all(b["lead"] in layouts[0]["families"] and b["arcs"] for b in bands)
    arcs = [a for band in bands for a in band["arcs"]]
    assert len(arcs) == len(set(arcs)), "each layout arc belongs to exactly one reported band"


def test_p0490_visual_prepare_has_patches_then_direction_colors(tmp_path, monkeypatch):
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.colors import to_rgba

    pages = []
    save = PdfPages.savefig

    def capture(pdf, fig, **kwargs):
        texts = [t.get_text() for legend in fig.legends for t in legend.get_texts()]
        colors = [
            tuple(c) for ax in fig.axes[:4] for c in ax.collections for c in c.get_edgecolors()
        ]
        pages.append((texts, colors))
        return save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", capture)
    source = _export(tmp_path / "sheet.nas", wide=False, perimeter=_middle_line())
    prepared = prepare_to_refine(source, visual_inspect=True)
    assert len(pages) == 2 * len(prepared.patches)
    texts, colors = pages[1]
    assert "parallel" in texts and "normal" in texts
    assert to_rgba("#0072b2") in colors and to_rgba("#d55e00") in colors


def test_p0490_visual_dominant_label_is_bold_and_framed(tmp_path, monkeypatch):
    import inspect
    from types import SimpleNamespace

    from matplotlib.backends.backend_pdf import PdfPages

    from pyflightstream.workspace._visual_inspect import patches_pdf

    assert "layouts" in inspect.signature(patches_pdf).parameters
    source = tmp_path / "sheet.obj"
    source.write_text("v 0 0 0\nv 2 0 0\nv 2 1 0\nv 0 1 0\ng A\nf 1 2 3 4\n")
    layout = SimpleNamespace(
        names=("A",),
        owner=(0,),
        blocks=SimpleNamespace(arcs=((0, 1), (1, 2), (2, 3), (3, 0))),
        directions={
            0: {
                a: _blocks.ArcDirection("parallel" if a % 2 == 0 else "normal", "A", "longest_side")
                for a in range(4)
            }
        },
        labels={0: "P1", 1: "N1", 2: "P1", 3: "N1"},
        leads={"P1": ("A", 0), "N1": ("A", 1)},
    )
    captured = []
    save = PdfPages.savefig

    def capture(pdf, fig, **kwargs):
        captured.append([t for ax in fig.axes[:4] for t in ax.texts])
        return save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", capture)
    patches_pdf(
        source,
        {"A": ["A"]},
        {"A": (True, True)},
        tmp_path / "out.pdf",
        layouts={"A": layout},
        dpi=40,
    )
    labels = [t for t in captured[1] if t.get_text() in {"P1", "N1"}]
    assert len(labels) == 16
    assert sum(t.get_fontweight() == "bold" and t.get_bbox_patch() is not None for t in labels) == 8
    assert sum(t.get_fontweight() == "normal" and t.get_bbox_patch() is None for t in labels) == 8


def test_p0490_visual_refine_writes_pdf_beside_level(tmp_path):
    import inspect

    assert "visual_inspect" in inspect.signature(refine_mesh).parameters
    (tmp_path / "source").mkdir()
    source = _export(tmp_path / "source/sheet.nas", wide=False, perimeter=_middle_line())
    prepared = prepare_to_refine(source)
    level = refine_mesh(prepared.obj, 2, out_dir=tmp_path / "levels", visual_inspect=True)
    pdf = level.folder / f"{level.folder.name}.inspect.pdf"
    assert pdf in level.files and pdf.read_bytes().startswith(b"%PDF")
    assert level.audit.path.is_file() and level.report


def test_p0490_visual_strict_factor_refusal_has_pdf_and_location(tmp_path):
    (tmp_path / "source").mkdir()
    source = _export(tmp_path / "source/sheet.nas", wide=False, perimeter=_middle_line())
    prepared = prepare_to_refine(source)
    levels = tmp_path / "levels"
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(prepared.obj, 0.01, out_dir=levels, force_factors=False)
    pdf = prepared.obj.with_name(prepared.obj.stem + ".refine-refusal.pdf")
    assert pdf.is_file()
    assert str(caught.value).endswith(f"A diagnostic PDF: {pdf}.")
    assert caught.value.where["families"]
    assert not levels.exists()


def test_p0490_visual_refusal_uses_structured_locations(tmp_path, monkeypatch):
    from matplotlib.backends.backend_pdf import PdfPages

    from pyflightstream.workspace import _inspect_pages as pages
    from pyflightstream.workspace._visual_inspect import Mesh

    source = tmp_path / "mesh.obj"
    mesh = Mesh(
        source,
        np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
        {"A": [[0, 1, 2]], "B": [[0, 2, 1]]},
    )
    error = InputArtifactError(
        "A name in prose does not select a family",
        where={"families": ["B"], "nodes": [1], "points": [[0.5, 0.5, 0.0]]},
    )
    seen = []
    save = PdfPages.savefig

    def capture(pdf, fig, **kwargs):
        seen.append(fig.axes[0].collections)
        return save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", capture)
    pages.patches_pdf(
        mesh, {"all": ["A", "B"]}, {}, tmp_path / "locations.pdf", refusal=error, dpi=40
    )
    surfaces = seen[0][0].get_facecolors()
    assert sum(c[3] == 0.4 for c in surfaces) == 1
    assert sum(c[0] > c[1] and c[3] == 1 for c in surfaces) == 1
    points = seen[0][-1]
    np.testing.assert_array_equal(points.get_offsets(), [[0.5, 0.5], [2.0, 0.0]])
    np.testing.assert_array_equal(points.get_facecolors(), [[1.0, 0.0, 0.0, 1.0]])


def test_p0490_visual_drawing_failure_preserves_original_refusal(tmp_path, monkeypatch):
    from matplotlib.backends.backend_pdf import PdfPages

    (tmp_path / "source").mkdir()
    source = _export(tmp_path / "source/sheet.nas", wide=False, perimeter=_middle_line())
    prepared = prepare_to_refine(source)

    def fail(*args, **kwargs):
        raise RuntimeError("drawing failed")

    monkeypatch.setattr(PdfPages, "savefig", fail)
    with (
        pytest.warns(UserWarning, match="could not write the diagnostic PDF"),
        pytest.raises(InputArtifactError) as caught,
    ):
        refine_mesh(prepared.obj, 0.01, force_factors=False, out_dir=tmp_path / "levels")
    assert "below 1/" in str(caught.value)
    assert "A diagnostic PDF" not in str(caught.value)
    assert not (tmp_path / "levels").exists()


def test_p0490_visual_refine_annotations_come_from_saved_record(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from matplotlib.backends.backend_pdf import PdfPages

    from pyflightstream.workspace._inspect_pages import refined_pdf

    vertices = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    work = SimpleNamespace(
        mesh=SimpleNamespace(verts=vertices, families={"A": [[0, 1, 2]], "B": [[0, 2, 1]]}),
        bands={},
        parts={},
        specs={},
        layouts={},
        te_unit="METER",
    )
    record = tmp_path / "level.refine.json"
    record.write_text(
        json.dumps(
            {
                "components": {"All": ["A", "B"]},
                "families": {
                    "A": {"continuity": {"directions": ["normal"]}},
                    "B": {"band": 7},
                },
            }
        ),
        encoding="utf-8",
    )
    texts = []
    save = PdfPages.savefig

    def capture(pdf, fig, **kwargs):
        texts.extend(t.get_text() for t in fig.texts)
        return save(pdf, fig, **kwargs)

    monkeypatch.setattr(PdfPages, "savefig", capture)
    pdf = refined_pdf(work, tmp_path / "level.obj", record)
    assert pdf.is_file()
    assert any("A: continuity" in t and "normal" in t for t in texts)
    assert any("B: continuity remeshed band (7 source faces)" in t for t in texts)
