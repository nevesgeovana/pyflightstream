"""P0440-INVENTORY (FR-348, FR-919): a level's boundaries file states its own faces and digest.

A boundaries file written by the package for an OBJ without one carries the
mesh's inventory, ``mesh_faces``, ``boundary_faces`` and ``mesh_sha256``,
of that OBJ. The level's boundaries file is the source's with the values a
level changes rewritten, and these three are the LEVEL's: counted in the
level's OBJ as written, in the level's boundaries order after the
``[components]`` merge, and its sha256. The source is synthetic
(tests/p0380_mesh_fixtures.py): the sheet grid G, the triangle strips T and U.
"""

from __future__ import annotations

import hashlib
import tomllib

from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace.sidecars import ensure_inventory, obj_face_counts
from tests.p0380_mesh_fixtures import sheet_with_strips, write_source

STRIPS = (("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)), ("U", "tri", (0.1, 0.1)))
KEYS = ("mesh_faces", "boundary_faces", "mesh_sha256")


def _boundaries(folder) -> dict:
    return tomllib.loads((folder / f"{folder.name}.boundaries.toml").read_text(encoding="utf-8"))


def test_the_levels_boundaries_file_states_the_levels_faces_and_sha256(tmp_path):
    """P0440-INVENTORY (FR-348): refined at 2, the level states its own three values.

    The level's ``mesh_faces`` is the face count of its OBJ, ``boundary_faces``
    the count of each of its boundaries (Wing, the merged G and T, then U)
    and ``mesh_sha256`` the sha256 of its OBJ's bytes, each different from
    the source's. Control: a source boundaries file without the inventory
    gives a level boundaries file without it.
    """
    toml = '[components]\nWing = ["G", "T"]\n'
    mesh = sheet_with_strips(STRIPS)
    src = write_source(tmp_path / "src", "wing", mesh, boundaries=False, refine_toml=toml)
    source = tomllib.loads(ensure_inventory(src).read_text(encoding="utf-8"))
    assert all(key in source for key in KEYS), source
    level = refine_mesh(src, 2.0, families=["G", "T"])
    got = _boundaries(level.folder)
    counts = obj_face_counts(level.obj)
    assert got["boundaries"] == ["Wing", "U"]
    assert got["boundary_faces"] == list(counts) and len(counts) == 2
    assert got["mesh_faces"] == sum(counts) != source["mesh_faces"]
    assert got["mesh_sha256"] == hashlib.sha256(level.obj.read_bytes()).hexdigest()
    assert got["mesh_sha256"] != source["mesh_sha256"]
    assert got["boundary_faces"] != source["boundary_faces"]
    # The header comment names the OBJ's sha256 too: the level's, and the source's nowhere.
    header = "# the OBJ's sha256 was "
    assert f"{header}{source['mesh_sha256']}" in src.with_name("wing.boundaries.toml").read_text(
        encoding="utf-8"
    )
    text = (level.folder / f"{level.folder.name}.boundaries.toml").read_text(encoding="utf-8")
    assert f"{header}{got['mesh_sha256']}" in text and source["mesh_sha256"] not in text
    plain = write_source(tmp_path / "plain" / "src", "wing", mesh, refine_toml=toml)
    level = refine_mesh(plain, 2.0, families=["G", "T"])
    assert not any(key in _boundaries(level.folder) for key in KEYS)
