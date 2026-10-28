"""prepare-to-refine cuts an ANSA NASTRAN export along its FE perimeters; visual-inspect.

The export is built here: a flat sheet of 4 x 2 quadrilaterals in one property,
and a perimeter block naming the sides of the line that splits it in two 2 x 2
halves, in the layout ANSA writes (a base64 field holding a 4-byte length and
zlib data: a count, then a 32-bit element id and a 16-bit side per record).
"""

from __future__ import annotations

import base64
import struct
import warnings
import zlib
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import prepare_to_refine
from pyflightstream.workspace._refine import _nastran

COLUMNS, ROWS = 4, 2


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
    governing = [n for n, t in table.items() if t.get("governing")]
    grids = [p for ps in prepared.patches.values() for p in ps if p.endswith("_grid")]
    assert len(grids) == 2 and len(governing) == 1
    assert [g for g in grids if g not in table] == [g for g in grids if g not in governing]
