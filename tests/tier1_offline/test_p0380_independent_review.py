"""P0380-REFINE and P0380-AUDIT (FR-424, FR-426): the findings of the independent pre-tag review.

Each test reproduces one finding (IND-01 to IND-06) on a synthetic source
(tests/p0380_mesh_fixtures.py) and asserts the requirement it broke.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run import cli
from pyflightstream.workspace import refine_mesh
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
