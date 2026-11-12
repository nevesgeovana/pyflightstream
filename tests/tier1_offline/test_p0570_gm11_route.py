"""P0570-GM11 round 2: FSM writer, generation record, strategy 1 driver and the mesh verb.

Synthetic meshes only; the WB acceptance runs the committed WB fixture of
``test_p0570_geometry_mesh.py`` through the kernel and is skipped without it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError, InputValueError
from pyflightstream.geometry._mesh_topology import Mesh

ROOT = Path(__file__).resolve().parents[2]
FRESH = ROOT / "tests" / "tier3_licensed" / "inputs" / "geometries" / "20_BODY.fsm"
MARKED = ROOT / "tests" / "tier3_licensed" / "inputs" / "geometries" / "11_HALFWING.fsm"


def _grid(nx=3, ny=2, *, y0=0.0, name="WING", offset=0, z=0.0):
    xyz = np.array([[i * 0.1, y0 + j * 0.2, z] for j in range(ny + 1) for i in range(nx + 1)])
    cells = [
        (
            offset + j * (nx + 1) + i,
            offset + j * (nx + 1) + i + 1,
            offset + (j + 1) * (nx + 1) + i + 1,
            offset + (j + 1) * (nx + 1) + i,
        )
        for j in range(ny)
        for i in range(nx)
    ]
    return xyz, cells, [name] * len(cells)


def _mesh(*parts):
    xyz, cells, names = [], [], []
    for p in parts:
        xyz.append(p[0])
        cells += p[1]
        names += p[2]
    points = np.vstack(xyz)
    return Mesh(points, cells, names, [1] * len(cells), np.arange(len(points)))


# ---- sub-step 9: FSM writer -------------------------------------------------------------------


def test_p0570_gm11_fsm_round_trips_mesh_and_marks_through_the_reader(tmp_path):
    """YES: quads, a triangle, two components and a marked TE read back exactly."""
    from pyflightstream._fsm import (
        boundary_names,
        boundary_owners,
        surface_mesh,
        trailing_edge_midpoints,
    )
    from pyflightstream.workspace._fsm_write import paired_triangles, write_fsm

    wing = _grid()
    body = _grid(2, 1, y0=1.0, name="FUS", offset=len(wing[0]))
    mesh = _mesh(wing, body)
    mesh.cells.append((0, 1, len(wing[0])))
    mesh.components.append("FUS")
    mesh.surfaces.append(2)
    te = [(3, 7), (7, 11)]
    out = write_fsm(tmp_path / "m.fsm", mesh, template=FRESH, trailing_edges=te)
    vertices, triangles = surface_mesh(out)
    expected, _, _, owners = paired_triangles(mesh)
    assert np.allclose(vertices, mesh.xyz, rtol=0, atol=1e-15)
    assert [tuple(t) for t in triangles] == [tuple(t) for t in expected]
    assert boundary_names(out) == ("WING", "FUS")
    assert boundary_owners(out) == tuple(1 if o == "WING" else 2 for o in owners)
    mids = {tuple(np.round((mesh.xyz[a] + mesh.xyz[b]) / 2, 12)) for a, b in te}
    assert {tuple(np.round(m, 12)) for m in trailing_edge_midpoints(out)} == mids
    # Every block other than the mesh block is the template's.
    text, fresh = out.read_text(encoding="latin-1"), FRESH.read_text(encoding="latin-1")
    assert text.split("$MESH_END$")[1] == fresh.split("$MESH_END$")[1]


def test_p0570_gm11_fsm_partners_name_each_other_across_the_diagonal():
    from pyflightstream.workspace._fsm_write import paired_triangles

    tri, partners, slots, _ = paired_triangles(_mesh(_grid(1, 1)))
    assert [tuple(t) for t in tri] == [(0, 1, 3), (0, 3, 2)]
    assert partners == [2, 1] and slots == [3, 1]


def test_p0570_gm11_fsm_refuses_by_name(tmp_path):
    """NO: a template with another mesh's TE groups, a TE off the mesh, a pentagon, overwrite."""
    from pyflightstream.workspace._fsm_write import write_fsm

    mesh = _mesh(_grid())
    with pytest.raises(InputArtifactError, match="trailing-edge group"):
        write_fsm(tmp_path / "a.fsm", mesh, template=MARKED)
    with pytest.raises(InputValueError, match="not an edge of the mesh"):
        write_fsm(tmp_path / "b.fsm", mesh, template=FRESH, trailing_edges=[(0, 11)])
    bad = Mesh(mesh.xyz, [(0, 1, 2, 3, 4)], ["WING"], [1], mesh.node_tags)
    with pytest.raises(InputValueError, match="only 3 or 4"):
        write_fsm(tmp_path / "c.fsm", bad, template=FRESH)
    (tmp_path / "d.fsm").write_text("x")
    with pytest.raises(InputArtifactError, match="exists"):
        write_fsm(tmp_path / "d.fsm", mesh, template=FRESH)
    assert not (tmp_path / "a.fsm").exists() and not (tmp_path / "b.fsm").exists()
