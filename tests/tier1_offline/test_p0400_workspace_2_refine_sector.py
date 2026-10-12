"""P0400-REFINESECTOR: a periodic sector's cut is never resampled by an undecided factor."""

from __future__ import annotations

import numpy
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from pyflightstream.workspace._refine._periodic import find_cuts, match_level
from tests.tier1_offline.test_p0380_s4_sector import PERIODIC, SIX, _cells, _wedge, _write

pytest.importorskip("trimesh")


def _body(axial: float, circumferential: float) -> str:
    return (
        f"[families.W]\naxial = {axial}\ncircumferential = {circumferential}\n"
        "axis = [0.0, 0.0, 1.0]\n"
    )


def test_p0400_refinesector_a_body_stretched_unlike_on_a_cut_is_refused(tmp_path):
    """P0400-REFINESECTOR (PFS-2099.023): a sector of a cylinder at axial 1 and
    circumferential 3 is refused before any work, naming both factors, where its cut was
    resampled by max(axial, circumferential) = 3 along the axis."""
    source = _write(tmp_path, _wedge(na=6, nz=6), PERIODIC + _body(1, 3))
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(source)
    message = str(caught.value)
    assert "axial 1 and circumferential 3" in message and "[periodic]" in message, message
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]


def test_p0400_refinesector_a_body_stretched_alike_still_refines(tmp_path):
    """P0400-REFINESECTOR (PFS-2099.023): equal factors leave one factor for the cut; refined."""
    source = _write(tmp_path, _wedge(na=6, nz=6), PERIODIC + _body(2, 2))
    assert refine_mesh(source).obj.is_file()


def test_p0400_refinesector_a_finely_spaced_open_edge_beside_a_cut_is_not_the_cut():
    """P0400-REFINESECTOR (PFS-2099.022): the wedge's open arcs are spaced 0.3 degrees beside
    each cut, closer to the cut's corner than a quarter of its first segment. The arc's node is
    no cut node: the level (here the source itself) matches its cuts node for node, where the
    distance rule took the arc's node at 0.3 degrees on one cut and at 59.7 on the other and
    refused a sector that matches."""
    theta = numpy.radians([0.0, 0.3, 10.0, 20.0, 30.0, 40.0, 50.0, 59.7, 60.0])
    z = 0.5 * (1.0 - numpy.cos(numpy.pi * numpy.arange(6) / 5))
    t, h = numpy.meshgrid(theta, z)
    verts = numpy.column_stack([numpy.cos(t).ravel(), numpy.sin(t).ravel(), h.ravel()])
    na = len(theta) - 1
    faces = {"W": _cells(na, [(i, j) for j in range(5) for i in range(na)])}
    size = float(numpy.linalg.norm(verts.max(axis=0) - verts.min(axis=0)))
    cuts = find_cuts(verts, faces, SIX, size=size, where="wedge")
    level, report = match_level(verts, faces, cuts, SIX, source=verts, size=size, where="wedge")
    assert report is not None and report["level_distance"] <= 1e-9 * size, report
    assert report["pairs"][0]["level_nodes"] == [6, 6], report
