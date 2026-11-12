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


# ---- section 5 acceptance and followers with shared-curve discovery ----------------------------

_KERNEL = {
    "inverted_count": 0,
    "source_distance_max_m": 1e-9,
    "source_distance_tolerance_m": 5e-4,
    "spacing_rules": {"failures": []},
}


def _controls(follows=("WING",)):
    return {
        "defaults": {"quality": {"max_aspect": 8.0, "max_skew_deg": 50.0}},
        "components": {
            "WING": {"role": "primary", "follows": []},
            "FAIR": {"role": "follower", "follows": list(follows)},
        },
    }


N_PSI, N_PHI = 8, 8


def _two_part_mesh(*, conforming=True):
    """A half torus cut by y = 0: free edges only on the symmetry plane, all quads.

    WING holds the first half of the big circle and FAIR the second; they share the ring at
    its middle node to node, or (not conforming) FAIR carries its own copy of that ring.
    """
    psi = np.linspace(0.0, np.pi, N_PSI + 1)
    phi = np.linspace(0.0, 2 * np.pi, N_PHI, endpoint=False)
    xyz = [
        [(3 + np.cos(f)) * np.cos(p), (3 + np.cos(f)) * np.sin(p), np.sin(f)]
        for p in psi
        for f in phi
    ]
    xyz = np.array(xyz)
    xyz[np.abs(xyz[:, 1]) < 1e-12, 1] = 0.0
    half = N_PSI // 2
    copy = len(xyz)
    if not conforming:
        xyz = np.vstack([xyz, xyz[half * N_PHI : (half + 1) * N_PHI] + [0.0, 0.0, 1e-3]])

    def node(i, j, owner):
        if owner == "FAIR" and i == half and not conforming:
            return copy + j % N_PHI
        return i * N_PHI + j % N_PHI

    cells, names = [], []
    for i in range(N_PSI):
        owner = "WING" if i < half else "FAIR"
        for j in range(N_PHI):
            cells.append(
                (
                    node(i, j, owner),
                    node(i + 1, j, owner),
                    node(i + 1, j + 1, owner),
                    node(i, j + 1, owner),
                )
            )
            names.append(owner)
    surfaces = [1 if n == "WING" else 2 for n in names]
    return Mesh(xyz, cells, names, surfaces, np.arange(len(xyz)))


def _by_id(checks):
    return {c["check"] if "check" in c else c["id"]: c for c in checks}


def test_p0570_gm11_shared_curves_are_discovered_on_the_realized_mesh():
    from pyflightstream.workspace._geometry_mesh_s1 import shared_curves

    ring = set(range(N_PSI // 2 * N_PHI, (N_PSI // 2 + 1) * N_PHI))
    edges = shared_curves(_two_part_mesh())[("FAIR", "WING")]
    assert len(edges) == N_PHI and {v for e in edges for v in e} == ring
    assert shared_curves(_two_part_mesh(conforming=False)) == {}


def test_p0570_gm11_follower_shares_a_curve_with_each_neighbour_yes_no():
    """YES: welded follower of WING. NO: a copied ring (no shared curve), an absent neighbour."""
    from pyflightstream.workspace._geometry_mesh_s1 import follower_checks

    yes = follower_checks(_two_part_mesh(), _controls())
    assert [c["status"] for c in yes] == ["passed"]
    gap = follower_checks(_two_part_mesh(conforming=False), _controls())
    assert gap[0]["status"] == "failed" and gap[0]["where"]["missing_neighbours"] == ["WING"]
    other = follower_checks(_two_part_mesh(), _controls(("WING", "FUS")))
    assert other[0]["where"]["missing_neighbours"] == ["FUS"]


def test_p0570_gm11_acceptance_table_yes_no():
    """YES: a conforming structured mesh passes every row. NO: each planted defect fails its row."""
    from pyflightstream.workspace._geometry_mesh_s1 import acceptance_checks

    mesh = _two_part_mesh()
    checks = _by_id(acceptance_checks(mesh, _KERNEL, _controls(), {"FAIR": {}}))
    expected = {
        "mesh.inverted",
        "mesh.degenerate",
        "mesh.quality.aspect",
        "mesh.quality.skew",
        "mesh.node_to_node",
        "mesh.free_edges",
        "mesh.triangles.region",
        "mesh.triangles.fraction",
        "mesh.irregular_nodes",
        "mesh.spacing_laws",
        "mesh.source_distance",
        "mesh.follower.shared_curves",
    }
    assert set(checks) == expected
    assert all(c["status"] in {"passed", "skipped"} for c in checks.values()), checks
    assert checks["mesh.triangles.fraction"]["status"] == "skipped"
    # A triangle on the primary lifting surface.
    tri = _two_part_mesh()
    a, b, c, d = tri.cells[0]
    tri.cells[0:1] = [(a, b, c), (a, c, d)]
    tri.components.insert(0, "WING")
    tri.surfaces.insert(0, 1)
    bad = _by_id(acceptance_checks(tri, _KERNEL, _controls(), {"FAIR": {}}))
    assert bad["mesh.triangles.region"]["status"] == "failed"
    # A stretched cell beyond max_aspect, a free edge off y = 0, a spacing failure.
    stretched = _two_part_mesh()
    stretched.xyz[N_PHI + 3] *= [40.0, 40.0, 1.0]
    bad = _by_id(
        acceptance_checks(
            stretched, {**_KERNEL, "spacing_rules": {"failures": [1]}}, _controls(), {"FAIR": {}}
        )
    )
    assert bad["mesh.quality.aspect"]["status"] == "failed"
    assert bad["mesh.spacing_laws"]["status"] == "failed"
    gap = _by_id(acceptance_checks(_two_part_mesh(conforming=False), _KERNEL, _controls(), {}))
    assert gap["mesh.free_edges"]["status"] == "failed"
    over = _two_part_mesh()
    over.cells.append(over.cells[0])
    over.components.append("WING")
    over.surfaces.append(1)
    assert (
        _by_id(acceptance_checks(over, _KERNEL, _controls(), {}))["mesh.node_to_node"]["status"]
        == "failed"
    )


def test_p0570_gm11_irregular_node_inside_a_structured_surface_is_counted():
    from pyflightstream.workspace._geometry_mesh_s1 import acceptance_checks

    mesh = _two_part_mesh()
    centre = N_PHI + 1  # an interior node of the wing half
    cells = [
        c for c in mesh.cells if centre in c and mesh.components[mesh.cells.index(c)] == "WING"
    ]
    first = cells[0]
    i = first.index(centre)
    split = (
        [first[i], first[(i + 1) % 4], first[(i + 2) % 4]],
        [first[i], first[(i + 2) % 4], first[(i + 3) % 4]],
    )
    k = mesh.cells.index(first)
    mesh.cells[k : k + 1] = [tuple(split[0]), tuple(split[1])]
    mesh.components.insert(k, "WING")
    mesh.surfaces.insert(k, 1)
    checks = _by_id(acceptance_checks(mesh, _KERNEL, _controls(), {"WING": {}, "FAIR": {}}))
    assert checks["mesh.irregular_nodes"]["status"] == "passed"  # inside a transition component
    checks = _by_id(acceptance_checks(mesh, _KERNEL, _controls(), {"FAIR": {}}))
    assert checks["mesh.irregular_nodes"]["status"] == "failed"
