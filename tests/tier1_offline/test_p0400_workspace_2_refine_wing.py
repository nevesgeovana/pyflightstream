"""P0400-REFINEWING: a wing of two sheets sharing their trailing and leading edges, on a root.

The synthetic source: ``U`` and ``L``, the upper and lower surfaces of a
wing, each a sheet grid of five stations by nine chordwise nodes clustered
at the trailing edge (x = 1, column 0); they share the trailing-edge and the
leading-edge lines node for node. ``F``, a band of another component, closes
the root station of both. The trailing-edge points file lists the trailing
edge once, the edges U and L share.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy
import pytest

from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import Composite, face_coordinates, read_mesh, write_source

pytest.importorskip("trimesh")

#: Chordwise positions from the trailing edge (column 0) to the leading edge.
X = (1.0, 0.995, 0.98, 0.94, 0.8, 0.6, 0.35, 0.12, 0.0)
#: Spanwise stations; the root is y = 0.
Y = (0.0, 0.25, 0.5, 0.75, 1.0)


def _thickness(x: float) -> float:
    return 0.3 * x**0.5 * (1.0 - x)


def wing(*, root: bool = True) -> Composite:
    """Return the two-sheet wing, with the root band F when ``root``."""
    n, k = len(X), len(Y)
    verts: list[tuple[float, float, float]] = []
    upper: dict[tuple[int, int], int] = {}
    lower: dict[tuple[int, int], int] = {}
    for s, y in enumerate(Y):
        for i, x in enumerate(X):
            upper[s, i] = len(verts)
            verts.append((x, y, _thickness(x)))
        for i, x in enumerate(X):
            if i in (0, n - 1):
                lower[s, i] = upper[s, i]
            else:
                lower[s, i] = len(verts)
                verts.append((x, y, -_thickness(x)))
    families: dict[str, list[list[int]]] = {"U": [], "L": []}
    for s in range(k - 1):
        for i in range(n - 1):
            families["U"].append(
                [upper[s, i], upper[s, i + 1], upper[s + 1, i + 1], upper[s + 1, i]]
            )
            families["L"].append(
                [lower[s, i], lower[s + 1, i], lower[s + 1, i + 1], lower[s, i + 1]]
            )
    if root:
        ring = [upper[0, i] for i in range(n)] + [lower[0, i] for i in range(n - 2, 0, -1)]
        below = []
        for v in ring:
            x, _, z = verts[v]
            below.append(len(verts))
            verts.append((x, -0.2, z))
        families["F"] = [
            [ring[j], below[j], below[(j + 1) % len(ring)], ring[(j + 1) % len(ring)]]
            for j in range(len(ring))
        ]
    points = numpy.asarray(verts, dtype=float)
    column = [upper[s, 0] for s in range(k)]
    te = 0.5 * (points[column[:-1]] + points[column[1:]])
    return Composite(points, families, te, {})


def _source(tmp_path: Path, mesh: Composite) -> Path:
    return write_source(tmp_path / "src", "wing", mesh)


def _te_rows(level) -> list[tuple[float, ...]]:
    lines = next(Path(level.folder).glob("*.te.txt")).read_text(encoding="utf-8").splitlines()
    return [tuple(round(float(c), 6) for c in row.split(",")) for row in lines[1:]]


def _gate(level, name: str):
    return next(item for item in level.audit.gates if item.name == name)


def test_p0400_refinewing_a_factor_one_grid_leaves_its_neighbour_byte_identical(tmp_path):
    """P0400-REFINEWING (PFS-2099.008): U at factor 1 keeps every node, so L, which shares its
    trailing and leading edges, is copied face for face; a root node of U beside the
    trailing-edge corner is no node of the shared trailing edge."""
    mesh = wing()
    level = refine_mesh(_source(tmp_path, mesh), 1, families=["U"], out_dir=tmp_path / "out")
    verts, families = read_mesh(level.obj)
    assert level.report["L"] == {"method": "copied"}, level.report["L"]
    assert face_coordinates(verts, families["L"]) == face_coordinates(
        mesh.verts.round(9), mesh.families["L"]
    )


def test_p0400_refinewing_a_factor_two_grid_welds_to_its_neighbours(tmp_path):
    """P0400-REFINEWING (PFS-2099.008): U at factor 2; L and F take U's new nodes on the curves
    they share and nothing else, so the level passes G1 and G3 (no crack, no edge of three)."""
    level = refine_mesh(_source(tmp_path, wing()), 2, families=["U"], out_dir=tmp_path / "out")
    assert _gate(level, "G1").verdict == "pass", _gate(level, "G1")
    assert _gate(level, "G3").verdict == "pass", _gate(level, "G3")


def test_p0400_refinewing_a_trailing_edge_two_families_hold_is_written_once(tmp_path):
    """P0400-REFINEWING (PFS-2099.016, PFS-2099.024): U refined chordwise only keeps its
    trailing-edge nodes and L is copied; both hold the trailing-edge edges, and the level's
    points file names each edge once, one row per source row."""
    mesh = wing(root=False)
    level = refine_mesh(_source(tmp_path, mesh), chordwise=2, families=["U"], out_dir=tmp_path)
    rows = _te_rows(level)
    assert len(rows) == len(set(rows)) == len(mesh.te), rows
    assert json.loads(next(level.folder.glob("*.refine.json")).read_text("utf-8"))


def test_p0400_refinewing_a_sheet_trailing_edge_is_detected_across_its_families(tmp_path):
    """P0400-REFINEWING (PFS-2099.017): no points file; the boundaries file routes U's
    trailing edge to detection and U keeps its root row. U's trailing edge is a boundary of
    U, sharp only with L's faces beside it; measured on every family's faces it is found."""
    mesh = wing()
    mesh = Composite(mesh.verts, mesh.families, numpy.zeros((0, 3)), {})
    toml = (
        "[families.U]\nspanwise = 2.0\nkeep_first_row = true\n"
        "trailing_edge_direction = [1.0, 0.0, 0.0]\n"
    )
    src = write_source(tmp_path / "src", "wing", mesh, refine_toml=toml)
    sidecar = src.with_name("wing.boundaries.toml")
    text = sidecar.read_text(encoding="utf-8")
    sidecar.write_text(
        text + '\n[import]\nunits = "METER"\n[trailing_edges]\ndetect = { surfaces = ["U"] }\n',
        "utf-8",
    )
    level = refine_mesh(src, out_dir=tmp_path / "out")
    entry = level.report["U"]
    assert entry["trailing_edge"] == "detected" and entry["kept_rows"] == ["station 0"], entry
    rows = _te_rows(level)
    assert rows and all(row[0] == 1.0 for row in rows), rows


@pytest.mark.requirement("FR-430")
def test_p0400_bgtests2_detected_trailing_edges_require_mesh_units(tmp_path):
    """PFS-2099.006: detection cannot label unknown mesh coordinates as metres."""
    from pyflightstream._errors import InputArtifactError

    mesh = wing()
    mesh = Composite(mesh.verts, mesh.families, numpy.zeros((0, 3)), {})
    src = _source(tmp_path, mesh)
    src.with_suffix(".boundaries.toml").write_text(
        '[trailing_edges]\ndetect = { surfaces = ["U"] }\n', encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match=r"\[import\].*units"):
        refine_mesh(src, spanwise=2, families=["U"], keep_first_row=["U"])


@pytest.mark.requirement("FR-432")
@pytest.mark.parametrize("unit", ["MILLIMETER", None])
def test_p0400_bgtests2_shared_edge_targets_state_their_units(tmp_path, unit):
    """PFS-2099.011: native lengths become metres only with a declared conversion."""
    from tests.p0380_mesh_fixtures import sheet_with_strips

    mesh = sheet_with_strips((("T", "tri", (0.03, 0.04, 0.05, 0.065, 0.08)),))
    src = _source(tmp_path, mesh)
    sidecar = src.with_suffix(".boundaries.toml")
    if unit is not None:
        sidecar.write_text(
            sidecar.read_text("utf-8") + f'\n[import]\nunits = "{unit}"\n', encoding="utf-8"
        )
    te = src.with_suffix(".te.txt")
    te.write_text(te.read_text("utf-8").replace("METER", unit or "METER"), encoding="utf-8")
    level = refine_mesh(src, 2, families=["G"])
    entry = level.report["T"]
    if unit is None:
        assert "shared_edge_target_m" not in entry
        assert entry["shared_edge_target_mesh_units"]["max"] > 0
    else:
        assert 0 < entry["shared_edge_target_m"]["max"] < 0.001


@pytest.mark.requirement("FR-426")
def test_p0400_bgtests2_remesh_preserves_only_listed_trailing_edges(tmp_path):
    """PFS-2099.021: four TE vertices do not make all four sides trailing edges."""
    points = numpy.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
    te = numpy.array([[0.5, 0, 0], [0.5, 1, 0]])
    src = write_source(
        tmp_path / "src",
        "plate",
        Composite(points, {"A": [[0, 1, 2, 3]]}, te, {}),
        refine_toml='[families.A]\nfactor = 1\nmethod = "remesh"\n',
    )
    level = refine_mesh(src)
    assert sorted(_te_rows(level)) == sorted(map(tuple, te.tolist()))


@pytest.mark.requirement("FR-426")
def test_p0400_bgtests2_assembled_grid_and_copied_family_share_one_trailing_edge(tmp_path):
    """PFS-2099.016 and PFS-2099.024: assembly deduplicates a grid part and its copied neighbour."""
    from types import SimpleNamespace

    from pyflightstream.workspace._refine._level import _assemble

    mesh = wing(root=False)
    selected = {"U": object()}
    work = SimpleNamespace(
        names=["U", "L"],
        parts={"U": (mesh.verts, {"U": mesh.families["U"]}, mesh.te)},
        specs=selected,
        request=SimpleNamespace(specs=selected),
        te_points=mesh.te,
        fam_v={name: {v for face in faces for v in face} for name, faces in mesh.families.items()},
        mesh=SimpleNamespace(verts=mesh.verts, families=mesh.families),
        scale=float(numpy.linalg.norm(numpy.ptp(mesh.verts, axis=0))),
        bands={},
    )
    _, _, midpoints = _assemble(work)
    assert len(midpoints) == len(mesh.te)
    assert sorted(map(tuple, midpoints.tolist())) == sorted(map(tuple, mesh.te.tolist()))
