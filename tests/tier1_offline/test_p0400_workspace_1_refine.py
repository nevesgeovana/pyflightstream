"""P0400-WSREFINE: the refinement request, the face order and a one-row grid.

0.40.0 lane workspace-1.

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import numpy
import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._config import RefineRequest, level_tag, resolve_request
from pyflightstream.workspace._refine._geometry import order_like
from pyflightstream.workspace._refine._grid import Grid, recover_grid, refine_grid
from pyflightstream.workspace._refine._obj import read_te
from tests.tier1_offline.test_p0380_s1_refine import _json, _left, _refused, _source, _two_tubes

pytestmark = pytest.mark.requirement("P0400-WSREFINE")


@pytest.mark.parametrize("families", [[], ()], ids=["list", "tuple"])
def test_p0400_wsrefine_an_empty_family_selection_is_refused(tmp_path, families):
    """P0400-WSREFINE (PFS-2099.005): no family selected writes no unchanged R- level."""
    src = _source(tmp_path)
    text = _refused(tmp_path, src, 2.0, families=families)
    assert "no family is selected" in text
    assert _left(tmp_path) == []


@pytest.mark.parametrize("tag", [None, "empty"])
def test_p0400_wsrefine_level_tags_refuse_an_empty_selection_even_with_a_custom_tag(tag):
    """P0400-WSREFINE (PFS-2099.005): the independent level-tag guard refuses no work."""
    with pytest.raises(InputArtifactError, match="no family is selected"):
        level_tag(RefineRequest(specs={}, tag=tag), ["G"])


def test_p0400_wsrefine_a_refinement_file_that_is_not_utf8_is_refused(tmp_path):
    """P0400-WSREFINE (PFS-2099.004): a cp1252 byte is a refusal naming the file."""
    src = _source(tmp_path)
    src.with_name("wing.refine.toml").write_bytes(b"# caf\xe9\n[families.G]\nfactor = 2\n")
    text = _refused(tmp_path, src)
    assert "wing.refine.toml" in text and "cannot be read" in text


def test_p0400_wsrefine_a_keep_first_row_only_table_names_the_fix(tmp_path):
    """P0400-WSREFINE (PFS-2093.013): the refusal says how to ask keep_first_row instead."""
    src = _source(tmp_path, refine_toml="[families.G]\nkeep_first_row = true\n")
    text = _refused(tmp_path, src)
    assert "--keep-first-row" in text and "states no factor, chordwise or spanwise" in text


def test_p0400_wsrefine_a_trailing_edge_file_that_is_not_utf8_is_refused(tmp_path):
    """P0400-WSREFINE (PFS-2099.004): the second reader refuses cp1252 by name."""
    path = tmp_path / "edge.txt"
    path.write_bytes(bytes([233]))
    with pytest.raises(InputArtifactError, match="edge.txt.*UTF-8"):
        read_te(path)


def test_p0400_wsrefine_a_selected_family_without_a_table_warns(tmp_path):
    """P0400-WSREFINE (PFS-2089.003): a copied family names the missing table."""
    src = _source(tmp_path, refine_toml="[families.G]\nfactor = 2\n")
    with pytest.warns(PyflightstreamWarning, match=r"add \[families.tail\].*give FACTOR"):
        request = resolve_request(src, ["G", "tail"])
    assert request.missing == ("tail",)


def test_p0400_wsrefine_missing_family_tables_are_recorded_beside_ignored_tables(tmp_path):
    """P0400-WSREFINE (PFS-2089.003): refine.json names copied selected families."""
    source = _two_tubes(tmp_path, "[families.A]\nfactor = 2\n")
    with pytest.warns(PyflightstreamWarning, match=r"add \[families.B\]"):
        level = refine_mesh(source)
    record = _json(level.files[2])
    assert record["missing_families_tables"] == ["B"]
    assert record["ignored_families_tables"] == []


def test_p0400_wsrefine_the_face_order_does_not_depend_on_the_length_unit():
    """P0400-WSREFINE (PFS-2099.019): faces on one source face follow its vertices, any unit."""
    length = 10000.0
    verts = numpy.array([[0.0, 0.0, 0.0], [length, 0.0, 0.0], [0.0, length, 0.0]])
    source = [[0, 1, 2]]
    near_second = numpy.array([[9850.0, 10.0, 0.0], [9950.0, 10.0, 0.0], [9900.0, 40.0, 0.0]])
    near_first = numpy.array([[1000.0, 1000.0, 0.0], [1150.0, 1000.0, 0.0], [1000.0, 1150.0, 0.0]])
    for scale in (1.0, 1.0e-4):
        pts = numpy.vstack([near_second, near_first]) * scale
        out = order_like(pts, [[0, 1, 2], [3, 4, 5]], verts * scale, source)
        assert sorted(out[0]) == [3, 4, 5], (scale, out)


def _one_row_sheet():
    """A sheet of 2 stations by 4 nodes, written row by row from station 0."""
    verts = numpy.array([[float(x), float(y), 0.0] for y in (0, 1) for x in range(4)])
    faces = [[i, i + 1, i + 5, i + 4] for i in range(3)]
    return verts, faces


def test_p0400_wsrefine_a_one_row_grid_is_written_in_its_rows_from_station_0():
    """P0400-WSREFINE (PFS-2099.018): refined spanwise, the sheet keeps its row order."""
    verts, faces = _one_row_sheet()
    grid = recover_grid(verts, faces, (3, 7))
    assert isinstance(grid, Grid), grid
    level = refine_grid(verts, faces, grid, chordwise=1.0, spanwise=2.0)
    centroids = [tuple(numpy.round(level.points[f].mean(axis=0)[:2], 6)) for f in level.faces]
    assert centroids == [
        (0.5, 0.25),
        (1.5, 0.25),
        (2.5, 0.25),
        (0.5, 0.75),
        (1.5, 0.75),
        (2.5, 0.75),
    ], centroids


def test_p0400_wsrefine_a_one_column_grid_keeps_its_forward_grid_column_sweep():
    """P0400-WSREFINE (PFS-2099.018): a missing chordwise neighbour never reverses it."""
    verts = numpy.array([[float(x), float(y), 0.0] for y in range(4) for x in (0, 1)])
    faces = [[2 * k, 2 * k + 1, 2 * k + 3, 2 * k + 2] for k in range(3)]
    grid = recover_grid(verts, faces, (1, 3, 5, 7))
    assert isinstance(grid, Grid), grid
    level = refine_grid(verts, faces, grid, chordwise=2.0, spanwise=1.0)
    centroids = [tuple(numpy.round(level.points[f].mean(axis=0)[:2], 6)) for f in level.faces]
    assert centroids == [
        (0.75, 0.5),
        (0.75, 1.5),
        (0.75, 2.5),
        (0.25, 0.5),
        (0.25, 1.5),
        (0.25, 2.5),
    ], centroids


def test_p0400_wsrefine_refine_mesh_takes_no_empty_selection_through_the_library_call(tmp_path):
    """P0400-WSREFINE (PFS-2099.005): the public call refuses before any work, by class."""
    src = _source(tmp_path)
    with pytest.raises(InputArtifactError):
        refine_mesh(src, 2.0, families=[])
