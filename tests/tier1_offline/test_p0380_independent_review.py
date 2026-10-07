"""P0380-REFINE and P0380-AUDIT (FR-424, FR-426): the findings of the independent pre-tag review.

Each test reproduces one finding (IND-01 to IND-06) on a synthetic source
(tests/p0380_mesh_fixtures.py) and asserts the requirement it broke.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run import cli
from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import sheet_with_strips, write_source


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
