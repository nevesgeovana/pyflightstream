"""P0400-REFINEENTRY: refine_mesh takes its arguments as the API states them, and refuses alike."""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import sheet_with_strips, write_source

pytest.importorskip("trimesh")

WITH_T = (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),)


def _source(tmp_path: Path, strips=WITH_T) -> Path:
    return write_source(tmp_path / "src", "wing", sheet_with_strips(strips))


def test_p0400_refineentry_a_missing_obj_is_an_input_artifact_refusal(tmp_path):
    """P0400-REFINEENTRY (PFS-2085.010): a mesh path that is no file is refused as
    InputArtifactError, as audit_mesh refuses it, never a bare FileNotFoundError."""
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(tmp_path / "src" / "absent.obj", 2)
    assert "no such OBJ file" in str(caught.value)
    assert str(caught.value).endswith("Nothing was written.")
    assert list(tmp_path.iterdir()) == []


def test_p0400_refineentry_a_bare_family_name_is_one_family(tmp_path):
    """P0400-REFINEENTRY (PFS-2099.010): a string selects one whole family name."""
    src = _source(tmp_path)
    src.write_text(src.read_text("utf-8").replace("g G", "g GRID"), encoding="utf-8")
    level = refine_mesh(src, 2, families="GRID", out_dir=tmp_path / "out")
    assert level.report["GRID"]["method"] == "grid"


def test_p0400_refineentry_a_bare_file_name_goes_beside_its_folder(tmp_path):
    """P0400-REFINEENTRY (PFS-2099.009): a bare file name run in the mesh's own folder writes
    the level into the parent of that folder, the documented default, instead of refusing it
    as inside the source's folder."""
    src = _source(tmp_path)
    here = Path.cwd()
    os.chdir(src.parent)
    try:
        level = refine_mesh("wing.obj", 2, families=["G"])
    finally:
        os.chdir(here)
    assert level.folder.parent.resolve() == tmp_path.resolve()


def test_p0400_refineentry_the_rebuilt_whole_warning_points_at_the_caller(tmp_path):
    """P0400-REFINEENTRY (PFS-2099.015): the FR-431 warning is attributed to the line that
    called refine_mesh, this file, not to a line of the library."""
    src = _source(tmp_path, (("T", "tri", (0.03, 0.04)),))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        refine_mesh(src, 2, families=["G"], out_dir=tmp_path / "out")
    rebuilt = [
        w
        for w in caught
        if issubclass(w.category, PyflightstreamWarning) and "rebuilt whole" in str(w.message)
    ]
    assert len(rebuilt) == 1, [str(w.message) for w in caught]
    assert Path(rebuilt[0].filename).resolve() == Path(__file__).resolve(), rebuilt[0].filename
