"""P0400-REFINELEVEL: what a level records and writes of its families and its trailing edge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import sheet_with_strips, write_source

pytest.importorskip("trimesh")


def _record(level) -> dict:
    return json.loads(next(Path(level.folder).glob("*.refine.json")).read_text(encoding="utf-8"))


def _te_rows(level) -> list[str]:
    return next(Path(level.folder).glob("*.te.txt")).read_text(encoding="utf-8").splitlines()[1:]


def test_p0400_refinelevel_a_selected_family_at_factor_one_is_in_the_specs(tmp_path):
    """P0400-REFINELEVEL (PFS-2099.007): G at 2 and T at 1 are both selected; T is kept
    unchanged, and refine.json's specs still records it with its factor (FR-433 R4)."""
    toml = "[families.G]\nfactor = 2\n[families.T]\nfactor = 1\n"
    mesh = sheet_with_strips((("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),))
    src = write_source(tmp_path / "src", "wing", mesh, refine_toml=toml)
    level = refine_mesh(src, config=src.with_suffix(".refine.toml"), out_dir=tmp_path / "out")
    record = _record(level)
    assert record["specs"]["T"]["factor"] == 1.0, record["specs"]
    assert record["specs"]["G"]["factor"] == 2.0
    assert record["families"]["T"]["method"] == "unchanged"


def test_p0400_refinelevel_a_trailing_edge_between_two_interfaces_keeps_its_point(tmp_path):
    """P0400-REFINELEVEL (PFS-2099.020): T, a one-row quadrilateral strip between the grid G
    and the strip U, is remeshed; its trailing-edge edge joins two interface nodes, and its
    point is still in the level's points file: one row per source trailing-edge edge."""
    strips = (("T", "quad", (0.03,)), ("U", "tri", (0.04, 0.05)))
    mesh = sheet_with_strips(strips)
    toml = '[families.T]\nfactor = 1\nmethod = "remesh"\n'
    src = write_source(tmp_path / "src", "wing", mesh, refine_toml=toml)
    level = refine_mesh(src, config=src.with_suffix(".refine.toml"), out_dir=tmp_path / "out")
    assert _record(level)["families"]["T"]["method"] == "remesh"
    assert len(_te_rows(level)) == len(mesh.te)
