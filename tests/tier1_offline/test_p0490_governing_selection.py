"""P0490-GOVERNING: an explicit selection bounds implicit grid_auto families."""

import numpy as np
import pytest

from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import Composite, face_coordinates, read_mesh, write_source


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
