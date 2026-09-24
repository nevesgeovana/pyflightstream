"""Tier 1: the saved simulation's trailing-edge rows, read as edge mid-points.

Pipeline role: quality gate on the instrument the licensed trailing-edge
runs are measured with (RPT-061, RPT-065). A saved simulation records
which mesh edges carry a trailing edge as per-face flags, one row per
edge slot of a triangle; this reader turns those flags into the
mid-points of the edges they name, which is the form the wake-edge
import reads.

WHY THE COMMITTED FILES ARE THE ORACLE. The two saved simulations read
here were written by the solver itself, with its own detection applied:
``10_WING.fsm`` is a straight wing whose trailing edge sits at x = 1,
z = 0 with one mesh edge every half metre of its 8 m span, so its
sixteen mid-points are known by construction, and ``30_BLADE.fsm`` is a
twisted blade whose twelve were counted by the solver. A reader that
returned the wrong slot, or the end vertices, is scored against the
solver's own record rather than against a fixture written here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._fsm import MeshReadError, surface_mesh, trailing_edge_midpoints

#: The tier-3 library of saved simulations, each admitted by its provenance
#: record (tests/tier1_offline/test_house_style.py, SYNTHETIC_LIBRARY).
_LIBRARY = Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries"


def _flag_row_lines(text: str) -> list[int]:
    """The 0-based line numbers of the mesh block's five T/F rows."""
    lines = text.split("\n")
    return [
        index
        for index, line in enumerate(lines)
        if line.strip()
        and {token.strip() for token in line.split(",") if token.strip()} <= {"T", "F"}
        and len(line) > 100
    ]


def test_the_saved_trailing_edge_rows_name_the_edges_by_their_midpoints(tmp_path):
    """INSTR. On the wing, the sixteen mid-points (1.0, -3.75 + 0.5 k, 0.0);
    on the blade, the twelve the solver's detection stored; and a wing whose
    third T/F row is cleared still gives the sixteen, because every edge is
    flagged from both of its faces and the fourth row carries the other side.
    """
    wing = trailing_edge_midpoints(_LIBRARY / "10_WING.fsm")
    assert len(wing) == 16, wing
    assert all(abs(x - 1.0) <= 1e-12 and abs(z) <= 1e-12 for x, _, z in wing), wing
    ys = [y for _, y, _ in wing]
    assert ys == pytest.approx([-3.75 + 0.5 * k for k in range(16)], abs=1e-12)
    assert wing == tuple(sorted(wing)), "the mid-points come back sorted"

    blade = trailing_edge_midpoints(_LIBRARY / "30_BLADE.fsm")
    assert len(blade) == 12, blade
    assert len(set(blade)) == 12

    text = (_LIBRARY / "10_WING.fsm").read_text(encoding="utf-8")
    rows = _flag_row_lines(text)
    assert len(rows) == 5, rows
    lines = text.split("\n")
    third = lines[rows[2]]
    assert " T" in third, "the fixture's third T/F row must carry flags before it is cleared"
    lines[rows[2]] = third.replace("T", "F")
    cleared = tmp_path / "10_WING_row3_cleared.fsm"
    cleared.write_text("\n".join(lines), encoding="utf-8")
    assert trailing_edge_midpoints(cleared) == wing


def test_the_surface_mesh_is_the_block_s_triangles_and_vertices():
    """The wing's block states 816 faces over 410 vertices; every face is a
    triangle of 0-based vertex indices, and every trailing-edge mid-point is
    the mid-point of an edge of one of those faces."""
    vertices, faces = surface_mesh(_LIBRARY / "10_WING.fsm")
    assert (len(vertices), len(faces)) == (410, 816)
    assert all(len(face) == 3 for face in faces)
    assert min(min(face) for face in faces) == 0
    assert max(max(face) for face in faces) == 409
    edge_midpoints = set()
    for face in faces:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            first, second = vertices[face[a]], vertices[face[b]]
            edge_midpoints.add(tuple((p + q) / 2 for p, q in zip(first, second, strict=True)))
    assert set(trailing_edge_midpoints(_LIBRARY / "10_WING.fsm")) <= edge_midpoints


def test_a_block_that_does_not_hold_its_shape_is_refused(tmp_path):
    """A face that is not a triangle, a T/F row count other than five, and a
    row shorter than the face count are each refused by name, rather than a
    trailing edge being read from a block this reader does not know."""
    text = (_LIBRARY / "10_WING.fsm").read_text(encoding="utf-8")
    lines = text.split("\n")
    rows = _flag_row_lines(text)

    quad = list(lines)
    marker = quad.index("$MESH_START$")
    per_face = marker + 1 + 2 + 1 + 3 + 1 + 1  # count lines, the one record, face count, id row
    assert quad[per_face].startswith("3,3,3")
    quad[per_face] = "4" + quad[per_face][1:]
    path = tmp_path / "quad.fsm"
    path.write_text("\n".join(quad), encoding="utf-8")
    with pytest.raises(MeshReadError, match="triangle"):
        trailing_edge_midpoints(path)

    four = [line for index, line in enumerate(lines) if index != rows[4]]
    path = tmp_path / "four_rows.fsm"
    path.write_text("\n".join(four), encoding="utf-8")
    with pytest.raises(MeshReadError, match="five"):
        trailing_edge_midpoints(path)

    short = list(lines)
    short[rows[3]] = short[rows[3]].rsplit(",", 2)[0]
    path = tmp_path / "short_row.fsm"
    path.write_text("\n".join(short), encoding="utf-8")
    with pytest.raises(MeshReadError, match="816"):
        trailing_edge_midpoints(path)

    path = tmp_path / "no_block.fsm"
    path.write_text("not a saved simulation\n", encoding="utf-8")
    with pytest.raises(MeshReadError, match="no mesh block"):
        trailing_edge_midpoints(path)
