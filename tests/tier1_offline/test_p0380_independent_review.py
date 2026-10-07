"""P0380-REFINE and P0380-AUDIT (FR-424, FR-426): the findings of the independent pre-tag review.

Each test reproduces one finding (IND-01 to IND-06) on a synthetic source
(tests/p0380_mesh_fixtures.py) and asserts the requirement it broke.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.run import cli
from pyflightstream.workspace import audit_mesh, refine_mesh
from pyflightstream.workspace._refine._grid import Grid, recover_grid, refine_grid
from tests.p0380_mesh_fixtures import (
    Composite,
    Fixture,
    body_of_revolution,
    sheet_with_strips,
    tube_pole_quads,
    tube_zipper,
    write_source,
)


def _source(folder: Path, stem: str = "wing", refine_toml: str | None = None) -> Path:
    """Write the cambered sheet grid ``G`` as ``folder/<stem>.obj`` and return its path."""
    return write_source(folder, stem, sheet_with_strips((), te=True), refine_toml=refine_toml)


def _tree(folder: Path) -> dict[str, bytes]:
    """Return every file under ``folder`` by its relative path, with its bytes."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def _sentinel(folder: Path) -> dict[str, bytes]:
    """Plant an unrelated file in ``folder`` and return the tree to compare later."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "keep.txt").write_bytes(b"not the refinement's")
    return _tree(folder)


# ------------------------------------------------- IND-01 owned folders only


@pytest.mark.parametrize("suffix", [".partial", ".previous"])
def test_ind01_a_source_in_a_reserved_name_is_never_removed(tmp_path, suffix):
    """P0380-REFINE (FR-424 R5, IND-01): a source inside ``<level>.partial`` or ``.previous`` stays.

    The source sits in ``study/wing_R1<suffix>/``, so its default level is
    ``study/wing_R1`` and the reserved staging or backup name is the source's
    own folder. Refining at factor 1 (and again with ``overwrite``, which
    moves the first level aside) writes the level and leaves the source's
    folder byte for byte. Control: the level is written.
    """
    src = _source(tmp_path / "study" / f"wing_R1{suffix}")
    before = _tree(src.parent)
    level = refine_mesh(src, 1.0)
    assert level.folder == tmp_path / "study" / "wing_R1" and level.obj.is_file()
    assert src.parent.is_dir() and _tree(src.parent) == before
    level = refine_mesh(src, 1.0, overwrite=True)
    assert level.obj.is_file() and _tree(src.parent) == before


@pytest.mark.parametrize("overwrite", [False, True])
def test_ind01_unrelated_reserved_folders_are_kept_and_the_run_leaves_none(tmp_path, overwrite):
    """P0380-REFINE (FR-424 R5, IND-01): unrelated ``.partial`` and ``.previous`` folders stay.

    Both hold a file the refinement did not write. A run (and with
    ``overwrite`` a run replacing an existing level) keeps both byte for byte
    and leaves no folder of its own beside the level. Control: the level is
    published, and with ``overwrite`` a file planted in the old level is gone.
    """
    src = _source(tmp_path / "src")
    partial = _sentinel(tmp_path / "wing_R2.partial")
    previous = _sentinel(tmp_path / "wing_R2.previous")
    if overwrite:
        refine_mesh(src, 2.0)
        (tmp_path / "wing_R2" / "planted.txt").write_bytes(b"x")
    level = refine_mesh(src, 2.0, overwrite=overwrite)
    assert level.obj.is_file() and not (level.folder / "planted.txt").exists()
    assert _tree(tmp_path / "wing_R2.partial") == partial
    assert _tree(tmp_path / "wing_R2.previous") == previous
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["src", "wing_R2", "wing_R2.partial", "wing_R2.previous"]


def test_ind01_a_failed_publish_removes_only_its_own_folder(tmp_path):
    """P0380-REFINE (FR-424 R5, IND-01): a failed publish keeps every folder it did not make.

    The level's path is occupied by a file, so the publish fails after the
    level was written and audited. The occupying file and the unrelated
    reserved folders are kept and the run's own staging folder is gone.
    """
    src = _source(tmp_path / "src")
    partial = _sentinel(tmp_path / "wing_R2.partial")
    previous = _sentinel(tmp_path / "wing_R2.previous")
    (tmp_path / "wing_R2").write_bytes(b"occupied")
    with pytest.raises(OSError):
        refine_mesh(src, 2.0, overwrite=True)
    assert (tmp_path / "wing_R2").read_bytes() == b"occupied"
    assert _tree(tmp_path / "wing_R2.partial") == partial
    assert _tree(tmp_path / "wing_R2.previous") == previous
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["src", "wing_R2", "wing_R2.partial", "wing_R2.previous"]


def test_ind01_a_level_holding_the_source_is_refused_before_any_work(tmp_path, capsys):
    """P0380-REFINE (FR-424 R5, R11, IND-01): ``overwrite`` never replaces the source's folder.

    The source is ``study/wing_R2/inner/wing.obj`` and ``out_dir`` is
    ``study``, so the level ``study/wing_R2`` holds the source's folder. Both
    routes refuse before writing and the source's tree is kept.
    """
    src = _source(tmp_path / "study" / "wing_R2" / "inner")
    before = _tree(tmp_path / "study")
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, 2.0, out_dir=tmp_path / "study", overwrite=True)
    text = str(caught.value)
    assert "holds the source's folder" in text and text.endswith("Nothing was written.")
    code = cli.main(["refine", str(src), "2", "--out-dir", str(tmp_path / "study"), "--overwrite"])
    assert code == 2 and text in capsys.readouterr().err
    assert _tree(tmp_path / "study") == before


def test_ind01_a_level_inside_the_sources_folder_is_refused(tmp_path):
    """P0380-REFINE (FR-424 R5, R11, IND-01): nothing is written into the source's folder.

    ``out_dir`` is the source's own folder; the refinement is refused and
    the folder is kept byte for byte.
    """
    src = _source(tmp_path / "src")
    before = _tree(src.parent)
    with pytest.raises(InputArtifactError, match="lies inside the source's folder") as caught:
        refine_mesh(src, 2.0, out_dir=src.parent)
    assert str(caught.value).endswith("Nothing was written.")
    assert _tree(src.parent) == before


@pytest.mark.parametrize("tag", ["../up", "a/b", "a\\b", "..", "."])
def test_ind01_a_tag_that_is_not_one_folder_name_is_refused(tmp_path, tag):
    """P0380-REFINE (FR-424 R3, R5, IND-01): ``[refine] tag`` names one folder beside the source's.

    A tag holding a path separator, or ``.`` or ``..``, is refused naming the
    file, the table and the key. Control: ``fine`` writes ``wing_fine``.
    """
    escaped = tag.replace("\\", "\\\\")
    src = _source(tmp_path / "src", refine_toml=f'[refine]\ntag = "{escaped}"\n')
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, 2.0)
    text = str(caught.value)
    assert f"{src.with_suffix('.refine.toml')} [refine] tag" in text
    assert "one folder name" in text and text.endswith("Nothing was written.")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]
    src.with_suffix(".refine.toml").write_bytes(b'[refine]\ntag = "fine"\n')
    assert refine_mesh(src, 2.0).folder == tmp_path / "wing_fine"


# --------------------------------------------- IND-02 each cap face's own start


def _recovered(fx: Fixture) -> Grid:
    grid = recover_grid(fx.verts, fx.faces, fx.te)
    assert isinstance(grid, Grid), grid
    return grid


def _same_faces(points, faces, fx: Fixture) -> bool:
    """Return whether the level's faces are the source's, in order and vertex for vertex."""
    return len(faces) == len(fx.faces) and all(
        np.array_equal(points[f], fx.verts[g]) for f, g in zip(faces, fx.faces, strict=True)
    )


def _rotated(face: list[int], by: int = 1) -> list[int]:
    return face[by:] + face[:by]


def test_ind02_a_fan_triangle_rotated_alone_keeps_its_start_at_factor_one():
    """P0380-REFINE (FR-424 R7, IND-02): at factor 1 one rotated fan triangle keeps its own start.

    The tube's fan triangles start at the pole, except one that starts at a
    ring node. The level at factor 1 equals the source face for face and
    vertex for vertex. Control: the source unchanged passes the same check.
    """
    fx = tube_pole_quads()
    plain = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=1.0, spanwise=1.0)
    assert _same_faces(plain.points, plain.faces, fx)
    fan = fx.lateral + 5
    assert fx.faces[fan][0] == fx.pole
    fx.faces[fan] = _rotated(fx.faces[fan])
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=1.0, spanwise=1.0)
    assert _same_faces(level.points, level.faces, fx)


def test_ind02_mixed_cap_rotations_interleaved_with_lateral_faces_are_kept_at_factor_one():
    """P0380-REFINE (FR-424 R7, IND-02): zipper caps of mixed starts, in among the lateral faces.

    One cap quad and one cap triangle start one vertex later than the other
    cap faces, and one cap face is moved between two lateral cells. At
    factor 1 every face, cap faces included, is the source's in order and
    starts at the source face's start vertex.
    """
    fx = tube_zipper()
    caps = list(range(fx.lateral, len(fx.faces)))
    quad = next(p for p in caps if len(fx.faces[p]) == 4)
    tri = next(p for p in caps if len(fx.faces[p]) == 3)
    fx.faces[quad] = _rotated(fx.faces[quad])
    fx.faces[tri] = _rotated(fx.faces[tri], 2)
    moved = fx.faces.pop(caps[-1])
    fx.faces.insert(fx.lateral // 2, moved)
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=1.0, spanwise=1.0)
    assert _same_faces(level.points, level.faces, fx)


def test_ind02_above_factor_one_each_fan_triangle_starts_like_its_nearest_source_triangle():
    """P0380-REFINE (FR-424 R7, IND-02): a cap face starts as its nearest source face does.

    The first 8 of the 24 fan triangles start at a ring node and the other 16
    at the pole. At factor 2 the 48 new fan triangles follow the source
    triangle nearest to each: about a third start at a ring node, where a
    majority rule would start all 48 at the pole.
    """
    fx = tube_pole_quads()
    for p in range(fx.lateral, fx.lateral + 8):
        fx.faces[p] = _rotated(fx.faces[p])
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=2.0, spanwise=2.0)
    pole = len(level.points) - 1
    fans = [f for f in level.faces if pole in f]
    assert len(fans) == 48
    ring_first = sum(f[0] != pole for f in fans)
    assert 14 <= ring_first <= 18, ring_first


# ------------------------------------- IND-03 counts a tube's caps can carry


@pytest.mark.parametrize(
    ("make", "factor", "said"),
    [
        (tube_zipper, 1 / 24, "1 interval(s) on each half"),
        (tube_zipper, 0.05, "1 interval(s) on each half"),
        (tube_zipper, 0.1, "1 interval(s) on each half"),
        (tube_pole_quads, 1 / 24, "2 node(s) around"),
        (tube_pole_quads, 0.07, "2 node(s) around"),
    ],
    ids=["zipper-1/m", "zipper-0.05", "zipper-0.1", "pole-1/m", "pole-0.07"],
)
def test_ind03_a_coarsening_the_caps_cannot_carry_is_refused(make, factor, said):
    """P0380-REFINE (FR-424 R1, R11, IND-03): too few nodes around a tube is refused, not a crash.

    The factor passes the 1/m limit of 24 intervals, but leaves a zipper
    section one interval per half (its end caps need two) or a pole tube two
    nodes around (a section needs three). The refusal names the family, the
    direction and the value and ends "Nothing was written.".
    """
    fx = make()
    with pytest.raises(InputArtifactError) as caught:
        refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=factor, spanwise=1.0, family="B")
    text = str(caught.value)
    assert text.startswith(f"family B: the chordwise factor is {factor:g}, ")
    assert said in text and text.endswith("Nothing was written.")


@pytest.mark.parametrize(
    ("make", "factor", "nodes"),
    [(tube_zipper, 2 / 12, 4), (tube_pole_quads, 3 / 24, 4)],
    ids=["zipper-2/half", "pole-3/n"],
)
def test_ind03_the_smallest_accepted_coarsening_builds_valid_caps(make, factor, nodes):
    """P0380-REFINE (FR-424 R1, IND-03): just above the limit the tube is coarsened.

    Control of the refusal: the smallest factor the message asks for builds
    the section's nodes and closes the ends with faces of distinct nodes.
    """
    fx = make()
    level = refine_grid(fx.verts, fx.faces, _recovered(fx), chordwise=factor, spanwise=1.0)
    assert level.report["grid"].endswith(f"x{nodes}")
    assert all(len(set(f)) == len(f) for f in level.faces)


def test_ind03_a_smooth_tube_of_two_nodes_around_is_refused_by_both_routes(tmp_path, capsys):
    """P0380-REFINE (FR-424 R1, R11, IND-03): a smooth tube keeps three nodes around.

    The body has 24 nodes around; chordwise 2/24 leaves two, which
    ``refine_mesh`` and ``pyfs-matrix refine`` refuse before any work with the
    same text. Control: 3/24 writes the level.
    """
    body = body_of_revolution(pole=True)
    mesh = Composite(body.verts, {"S": body.faces}, np.zeros((0, 3)), {})
    src = write_source(tmp_path / "src", "body", mesh)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, chordwise=2 / 24)
    text = str(caught.value)
    assert "family S: the chordwise factor is 0.0833333, " in text
    assert "2 node(s) around" in text and text.endswith("Nothing was written.")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]
    code = cli.main(["refine", str(src), "--chordwise", str(2 / 24)])
    assert code == 2 and text in capsys.readouterr().err
    assert refine_mesh(src, chordwise=3 / 24).obj.is_file()


# ------------------------------------------ IND-04 and IND-05 malformed inputs


def _both_commands_refuse(capsys, src: Path, said: str) -> None:
    """Assert ``refine`` and ``audit-mesh`` exit 2 printing ``said``, writing nothing."""
    before = _tree(src.parent.parent)
    for argv in (["refine", str(src), "2"], ["audit-mesh", str(src)]):
        capsys.readouterr()
        assert cli.main(argv) == 2, argv
        err = capsys.readouterr().err
        assert said in err and "Nothing was written." in err, err
    assert _tree(src.parent.parent) == before


TRIANGLE = ["v 0 0 0", "v 1 0 0", "v 0 1 0", "g S", "f 1 2 3"]


def _lines(lines: list[str]) -> bytes:
    """Return the lines as a text file's bytes, each ended by a line feed."""
    return "".join(f"{line}\n" for line in lines).encode("utf-8")


@pytest.mark.parametrize(
    ("line", "text", "said"),
    [
        (1, "v bad 0 0", "a vertex whose coordinate 'bad' is not a number"),
        (2, "v 1 0 0x", "a vertex whose coordinate '0x' is not a number"),
        (1, "v nan 0 0", "a vertex whose coordinate 'nan' is not finite"),
        (3, "v 0 inf 0", "a vertex whose coordinate 'inf' is not finite"),
        (2, "v 1e999 0 0", "a vertex whose coordinate '1e999' is not finite"),
        (5, "f 1 2 x", "a face whose vertex index 'x' is not an integer"),
        (5, "f 1 2.0 3", "a face whose vertex index '2.0' is not an integer"),
        (5, "f 1 2 9", "a face with fewer than three vertices or a missing vertex"),
    ],
    ids=["word", "trailing-text", "nan", "inf", "overflow", "word-index", "float-index", "range"],
)
def test_ind04_a_malformed_obj_is_refused_naming_file_and_line(tmp_path, capsys, line, text, said):
    """P0380-REFINE and P0380-AUDIT (FR-424 R11, FR-426 R1, IND-04): a bad OBJ line is a refusal.

    A coordinate that is not a number or not finite, and a face index that is
    not an integer or names no vertex, is refused as InputArtifactError
    naming the file and the line, ending "Nothing was written."; the function
    and both commands refuse it (exit 2) and nothing is written. Control:
    the well-formed triangle is audited.
    """
    folder = tmp_path / "src"
    folder.mkdir()
    src = folder / "tri.obj"
    src.write_bytes(_lines(TRIANGLE))
    assert audit_mesh(src).passed
    src.with_suffix(".audit.json").unlink()
    lines = list(TRIANGLE)
    lines[line - 1] = text
    src.write_bytes(_lines(lines))
    for call in (lambda: refine_mesh(src, 2.0), lambda: audit_mesh(src)):
        with pytest.raises(InputArtifactError) as caught:
            call()
        message = str(caught.value)
        assert message.startswith(f"{src}: line {line} is {said}"), message
        assert message.endswith("Nothing was written.")
    _both_commands_refuse(capsys, src, f"{src}: line {line} is {said}")


@pytest.mark.parametrize(
    ("rows", "row", "said"),
    [
        (["1,2", "3,4", "5,6"], 2, "2 number(s)"),
        (["1,2"], 2, "2 number(s)"),
        (["1,2,3,4", "5,6,7,8"], 2, "4 number(s)"),
        (["0.5,0,0", "1,2"], 3, "2 number(s)"),
        (["0.5,0,0", "1,2,nan"], 3, "a number that is not finite"),
        (["0.5,0,0", "1,x,0"], 3, "a word that is not a number"),
    ],
    ids=["two-columns", "one-short-row", "four-columns", "ragged", "nan", "word"],
)
def test_ind05_each_trailing_edge_row_holds_three_numbers(tmp_path, capsys, rows, row, said):
    """P0380-REFINE and P0380-AUDIT (FR-424 R11, FR-426 R2 G4, IND-05): x,y,z on every row.

    A points file whose rows hold two or four numbers, or a word, or a number
    that is not finite, is refused naming the file and the row before any
    work, by the function and both commands, and is never reshaped into other
    points. Control: the fixture's own points file is accepted.
    """
    src = _source(tmp_path / "src")
    te = src.with_name("wing.te.txt")
    assert audit_mesh(src).passed
    src.with_suffix(".audit.json").unlink()
    te.write_bytes(_lines(["METER", *rows]))
    for call in (lambda: refine_mesh(src, 2.0), lambda: audit_mesh(src)):
        with pytest.raises(InputArtifactError) as caught:
            call()
        message = str(caught.value)
        assert message.startswith(f"{te}: line {row} ") and said in message, message
        assert message.endswith("Nothing was written.")
    _both_commands_refuse(capsys, src, f"{te}: line {row} ")


# --------------------------------------------- IND-06 --csv names no input


def _csv_case(tmp_path: Path) -> tuple[Path, Path]:
    """Return a mesh and a copy of it as its source, each with its points and boundaries."""
    src = _source(tmp_path / "src")
    shutil.copytree(src.parent, tmp_path / "level")
    level = tmp_path / "level" / "wing.obj"
    (tmp_path / "level" / "wing.boundaries.toml").write_bytes(
        _lines(['boundaries = ["G"]', "[trailing_edges]", 'file = "pts.txt"'])
    )
    (tmp_path / "level" / "wing.te.txt").rename(tmp_path / "level" / "pts.txt")
    return level, src


@pytest.mark.parametrize(
    "target",
    [
        "level/wing.obj",
        "level/wing.audit.json",
        "level/wing.boundaries.toml",
        "level/pts.txt",
        "src/wing.obj",
        "src/wing.te.txt",
        "src/wing.boundaries.toml",
        "level/../level/wing.obj",
        "link.obj",
    ],
    ids=[
        "mesh",
        "audit-json",
        "mesh-boundaries",
        "named-points",
        "against",
        "against-points",
        "against-boundaries",
        "spelled-otherwise",
        "hard-link",
    ],
)
def test_ind06_csv_naming_a_file_the_audit_reads_or_writes_is_refused(tmp_path, capsys, target):
    """P0380-AUDIT (FR-426 R1, IND-06): ``--csv`` never overwrites an input or the audit JSON.

    The mesh, the source given by ``--against``, their boundaries and points
    files, the audit JSON, a path spelled otherwise and a hard link to the
    mesh are each refused before the audit runs: exit 2, the refusal names
    the file, and every file is kept byte for byte with no audit written.
    Control: a CSV elsewhere is written and the command exits 0.
    """
    level, src = _csv_case(tmp_path)
    if target == "link.obj":
        try:
            os.link(level, tmp_path / "link.obj")
        except OSError:
            pytest.skip("hard links are not available here")
    before = _tree(tmp_path)
    csv = tmp_path / target
    capsys.readouterr()
    code = cli.main(["audit-mesh", str(level), "--against", str(src), "--csv", str(csv)])
    err = capsys.readouterr().err
    assert code == 2, err
    said = [line for line in err.splitlines() if line.startswith(f"{csv}: --csv names ")]
    assert len(said) == 1 and said[0].endswith("Nothing was written."), err
    assert _tree(tmp_path) == before
    code = cli.main(
        ["audit-mesh", str(level), "--against", str(src), "--csv", str(tmp_path / "f.csv")]
    )
    assert code == 0 and (tmp_path / "f.csv").is_file()


# ------------------------------------------ IND-07 when the audit warns, said


REPO = Path(__file__).resolve().parents[2]


def _known_limitations() -> str:
    """Return the Known limitations of the CHANGELOG's 0.38.0 entry."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    entry = text[text.index("## [0.38.0]") :]
    entry = entry[: entry.index("## [", 5)]
    return entry[entry.index("### Known limitations") :]


def test_ind07_the_limitations_say_when_the_audit_warns_and_never_by_construction():
    """P0380-AUDIT (FR-426 R3, FR-428, IND-07): a warning comes from a figure above its limit.

    The 0.38.0 Known limitations, the mesh how-to and reference, and the
    FR-428 evidence no longer say that a stretched body or a quad-dominant
    level warns by construction or on every level; the limitations state the
    limits of FR-426 R3 and ask the reader to read the reported values.
    """
    pages = {
        "CHANGELOG.md": _known_limitations(),
        "docs/mesh/how-to.md": (REPO / "docs/mesh/how-to.md").read_text(encoding="utf-8"),
        "docs/mesh/reference.md": (REPO / "docs/mesh/reference.md").read_text(encoding="utf-8"),
        "docs/srs/functional-requirements.md": (
            REPO / "docs/srs/functional-requirements.md"
        ).read_text(encoding="utf-8"),
    }
    for name, text in pages.items():
        flat = " ".join(text.split())
        for claim in ("warns by construction", "warns on every level", "by construction; the"):
            assert claim not in flat, (name, claim)
    limits = " ".join(pages["CHANGELOG.md"].split())
    assert "the source's plus 0.05" in limits and "read the reported values" in limits


def test_ind07_a_paired_square_mesh_passes_the_relative_checks(tmp_path):
    """P0380-AUDIT (FR-426 R3, IND-07): quad-dominant is not a warning by construction.

    Two right triangles per square of a planar grid, paired into the square
    quadrilaterals, lower the skewness (0.25 to 0) and keep every area ratio
    at 1: the audit against the triangulated source passes every gate and
    check with no warning. Control: the same quads with one square moved off
    the plane fail the warp check.
    """
    import warnings

    nodes = [f"v {x} {y} 0" for y in range(3) for x in range(3)]

    def at(x: int, y: int) -> int:
        return 3 * y + x + 1

    squares = [
        (at(x, y), at(x + 1, y), at(x + 1, y + 1), at(x, y + 1)) for y in range(2) for x in range(2)
    ]
    tris = [f"f {a} {b} {c}" for a, b, c, d in squares] + [
        f"f {a} {c} {d}" for a, b, c, d in squares
    ]
    quads = [f"f {a} {b} {c} {d}" for a, b, c, d in squares]
    (tmp_path / "src").mkdir()
    (tmp_path / "lvl").mkdir()
    source = tmp_path / "src" / "plate.obj"
    level = tmp_path / "lvl" / "plate.obj"
    source.write_bytes(_lines([*nodes, "g S", *tris]))
    level.write_bytes(_lines([*nodes, "g S", *quads]))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        audit = audit_mesh(level, against=source)
    assert audit.passed
    nodes[at(2, 2) - 1] = "v 2 2 0.5"
    level.write_bytes(_lines([*nodes, "g S", *quads]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bent = audit_mesh(level, against=source)
    assert any(i.name == "warp" and not i.passed for i in bent.checks)


def _failing_renames(monkeypatch, fail_put_back):
    """Make the publish rename fail, and with ``fail_put_back`` the put-back too."""
    real = Path.rename

    def rename(self, target):
        target = Path(target)
        moving_staging = self.parent.name.startswith("wing_R2.partial-") and self.name == "wing_R2"
        putting_back = self.name.endswith(".previous") and target.name == "wing_R2"
        if moving_staging or (fail_put_back and putting_back):
            raise OSError("simulated rename failure")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", rename)


def test_ind01_a_failed_publish_puts_the_previous_level_back(tmp_path, monkeypatch):
    """P0380-REFINE (FR-424 R5, IND-01): the old level survives a publish that fails.

    An existing level is set aside, the rename of the new one fails, and the
    old level is back at its path byte for byte, with no folder of the run
    left. Control: without the failure the level is replaced.
    """
    src = _source(tmp_path / "src")
    refine_mesh(src, 2.0)
    (tmp_path / "wing_R2" / "planted.txt").write_bytes(b"old")
    old = _tree(tmp_path / "wing_R2")
    _failing_renames(monkeypatch, fail_put_back=False)
    with pytest.raises(OSError):
        refine_mesh(src, 2.0, overwrite=True)
    assert _tree(tmp_path / "wing_R2") == old
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src", "wing_R2"]
    monkeypatch.undo()
    refine_mesh(src, 2.0, overwrite=True)
    assert not (tmp_path / "wing_R2" / "planted.txt").exists()


def test_ind01_a_level_that_cannot_be_put_back_is_kept_and_named(tmp_path, monkeypatch):
    """P0380-REFINE (FR-424 R5, IND-01): when the old level cannot be put back, it is not removed.

    Both the publish and the put-back fail: the run's folder is kept with the
    old level inside it, byte for byte, and a warning names where it is.
    """
    src = _source(tmp_path / "src")
    refine_mesh(src, 2.0)
    (tmp_path / "wing_R2" / "planted.txt").write_bytes(b"old")
    old = _tree(tmp_path / "wing_R2")
    _failing_renames(monkeypatch, fail_put_back=True)
    with pytest.warns(PyflightstreamWarning, match="put back"), pytest.raises(OSError):
        refine_mesh(src, 2.0, overwrite=True)
    kept = [p for p in tmp_path.iterdir() if p.name.startswith("wing_R2.partial-")]
    assert len(kept) == 1 and _tree(kept[0] / "wing_R2.previous") == old
