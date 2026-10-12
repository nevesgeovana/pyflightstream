"""Tier 1, 0.40.0: the mesh operations of the instruction file, as emitted (FR-474).

P0400-GEOM-P1OPS (PFS-2081.13). Each kind is emitted by the typed emitter in
the reference frame, its surface cited by its position at its own step; the
names it states are the names after it. The commands are unprobed, so these
are offline goldens of the emitted lines; the build refuses to run them until
a licensed probe verifies them (FR-471 R9).
"""

from __future__ import annotations

import hashlib

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace._geometry_build import plan_geometry_build
from tests.tier1_offline.test_p0400_geometry_build import geometry, workspace


def _script(tmp_path, boundaries: str, operations: str) -> list[str]:
    root = workspace(tmp_path)
    folder = geometry(
        root,
        "rotor",
        f'fs_build = "26.125"\nboundaries = {boundaries}\n[mesh]\nfile = "src.obj"\n'
        f'units = "METER"\n\n' + operations + "[trailing_edges]\nnone = true\n",
    )
    plan = plan_geometry_build(folder)
    return [line for line in plan.variants[0].script.text.splitlines() if line]


def _between(lines: list[str]) -> list[str]:
    start = lines.index("CLEAR") + 1
    end = next(i for i, line in enumerate(lines) if line.startswith("EXPORT_SURFACE_MESH"))
    return lines[start:end]


@pytest.mark.requirement("FR-474")
def test_p0400_geom_p1ops_copies_cite_the_surface_and_count_the_original(tmp_path):
    """P0400-GEOM-P1OPS (PFS-2081.13): R1, circular and linear copies."""
    lines = _script(
        tmp_path,
        '["Wing", "W2", "W3", "W4"]',
        '[[operations]]\nop = "circular_copy"\nsurface = "Wing"\naxis = "X"\ncount = 3\n'
        'angle_deg = 120.0\nnames = ["W2", "W3"]\n'
        '[[operations]]\nop = "linear_copy"\nsurface = "W3"\ncount = 2\nvector = [0.0, 1.0, 0.0]\n'
        'names = ["W4"]\n',
    )
    assert _between(lines) == [
        "SURFACE_CIRCULAR_COPY_PASTE 1 1 1 3 120.0",
        "SURFACE_LINEAR_COPY_PASTE 3 2 1 METER 0.0 1.0 0.0",
    ]


@pytest.mark.requirement("FR-474")
def test_p0400_geom_p1ops_cut_fill_and_clean(tmp_path):
    """P0400-GEOM-P1OPS (PFS-2081.13): R2 and R3, the cut replaces the surface by its parts."""
    lines = _script(
        tmp_path,
        '["Nose", "Body"]',
        '[[operations]]\nop = "cut"\nsurface = "Wing"\nplane = "YZ"\noffset = 0.5\n'
        'names = ["Nose", "Body"]\n'
        '[[operations]]\nop = "fill_holes"\nsurface = "Body"\n'
        '[[operations]]\nop = "delete_degenerate_faces"\n',
    )
    assert _between(lines) == [
        "SURFACE_CUT_BY_PLANE",
        "FRAME 1",
        "PLANE YZ",
        "OFFSET 0.5",
        "SURFACE 1",
        "SURFACE_AUTO_HOLE_FILL 2",
        "DELETE_DEGENERATE_FACES",
    ]


@pytest.mark.requirement("FR-474")
def test_p0400_geom_p1ops_extract_selects_then_creates_on_consecutive_lines(tmp_path):
    """P0400-GEOM-P1OPS (PFS-2081.13): R4, a restricted extraction and a deletion."""
    lines = _script(
        tmp_path,
        '["Wing", "Tip"]',
        '[[operations]]\nop = "extract_faces"\nsurface = "Wing"\nquantity = "Y"\nmin = 3.0\n'
        'name = "Tip"\n\n'
        '[[operations]]\nop = "delete_faces"\nquantity = "AREA"\nmax = 1e-9\n',
    )
    assert _between(lines) == [
        "SURFACE_SELECT_BY_ID 1",
        "SURFACE_SELECT_BY_THRESHOLD",
        "FRAME 1",
        "THRESHOLD Y",
        "MIN_VALUE 3.0",
        "MAX_VALUE 0.0",
        "RANGE ABOVE_MIN",
        "SUBSET SELECTED_FACES",
        "CREATE_NEW_SURFACE_FROM_SELECTION",
        "SURFACE_SELECT_BY_THRESHOLD",
        "FRAME 1",
        "THRESHOLD AREA",
        "MIN_VALUE 0.0",
        "MAX_VALUE 1e-09",
        "RANGE BELOW_MAX",
        "SUBSET ALL_FACES",
        "DELETE_SELECTED_FACES",
    ]


@pytest.mark.requirement("FR-474")
def test_p0400_geom_p1ops_node_moves_are_pinned_to_the_mesh(tmp_path):
    """P0400-GEOM-P1OPS (PFS-2081.13): R5, the pin holds, and a changed mesh is refused."""
    from tests.tier1_offline.test_p0400_geometry_build import wing_obj

    probe = wing_obj(tmp_path / "probe.obj")
    digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    operation = (
        f'[[operations]]\nop = "transform_nodes"\nmesh_sha256 = "{digest}"\nnodes = [3, 4]\n'
        "vector = [0.0, 0.0, 0.002]\n"
    )
    lines = _script(tmp_path / "a", '["Wing"]', operation)
    assert _between(lines) == [
        "SELECT_MESH_NODE 3",
        "SELECT_MESH_NODE 4",
        "TRANSFORM_SELECTED_NODES 1 TRANSLATION 0.0 0.0 0.002",
    ]
    stale = operation.replace(digest, "0" * 64)
    with pytest.raises(InputArtifactError, match="pinned to the mesh sha256 0000"):
        _script(tmp_path / "b", '["Wing"]', stale)


REFUSED = [
    (
        "names count",
        '["Wing", "W2"]',
        'op = "circular_copy"\nsurface = "Wing"\naxis = "X"\ncount = 3\nangle_deg = 120.0\n'
        'names = ["W2"]\n\n',
        "creates 2",
    ),
    (
        "solved quantity",
        '["Wing", "T"]',
        'op = "extract_faces"\nquantity = "CP"\nmin = 0.0\nname = "T"\n',
        "solved quantity",
    ),
    (
        "no range",
        '["Wing", "T"]',
        'op = "extract_faces"\nquantity = "X"\nname = "T"\n',
        "min, max or both",
    ),
    ("absent surface", '["Wing"]', 'op = "fill_holes"\nsurface = "Hub"\n', "Hub"),
    ("every surface", '["Wing"]', 'op = "fill_holes"\nsurface = "all"\n', 'no "all" form'),
]


@pytest.mark.requirement("FR-474")
@pytest.mark.parametrize(
    ("label", "boundaries", "operation", "words"), REFUSED, ids=[c[0] for c in REFUSED]
)
def test_p0400_geom_p1ops_refusals_name_the_operation(
    tmp_path, label, boundaries, operation, words
):
    """P0400-GEOM-P1OPS (PFS-2081.13): R6, refused before any solver starts."""
    with pytest.raises(InputArtifactError, match=words):
        _script(tmp_path, boundaries, "[[operations]]\n" + operation)
