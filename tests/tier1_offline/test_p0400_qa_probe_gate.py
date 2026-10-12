"""P0400-PROBEGATE: what the probe geometry gate asks of the mesh, and what it records.

PFS-2088.007: culling without a mesh is refused rather than culling nothing.
PFS-2097.007, PFS-2100.010: the watertight check follows ``cull``; the refusal's
own remedy works through ``mesh_path``, and a band asks no containment without it.
PFS-2097.008: an open mesh passed as an object is refused when the gate culls.
PFS-2103.001: ``mesh`` and ``mesh_path`` together are refused.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import pyflightstream.probes.geometry as gate
from pyflightstream.probes import AxisSpec, FrameDefinition, PlanarProbeGrid, RefinementBand
from pyflightstream.probes.errors import ProbeGeometryError
from pyflightstream.probes.geometry import OpenMeshError, apply_geometry_gate, load_surface_mesh

pytest.importorskip("trimesh")

CUBE = Path(__file__).parent / "fixtures" / "cube.obj"
BOTTOM_FACE = ("f 1 3 2", "f 1 4 3")


def _open_box(tmp_path: Path) -> Path:
    """The unit cube with its bottom face removed: open, so containment is undefined."""
    lines = CUBE.read_text(encoding="utf-8").splitlines()
    path = tmp_path / "open_box.obj"
    path.write_text("\n".join(x for x in lines if x not in BOTTOM_FACE) + "\n", encoding="utf-8")
    return path


def _grid(*, z: float = 0.0, band: RefinementBand | None = None) -> PlanarProbeGrid:
    return PlanarProbeGrid(
        frame=FrameDefinition(origin=(0.0, 0.0, z), x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        v=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        refinement=band,
    )


def test_p0400_probegate_cull_without_a_mesh_is_refused():
    """P0400-PROBEGATE (PFS-2088.007) the default cull=True with no mesh refuses."""
    with pytest.raises(ProbeGeometryError, match="cull=False"):
        apply_geometry_gate(_grid())
    assert apply_geometry_gate(_grid(), cull=False).report.base_culled == 0


def test_p0400_probegate_the_open_mesh_remedy_works_through_mesh_path(tmp_path):
    """P0400-PROBEGATE (PFS-2097.007, PFS-2100.010) follow the refusal's remedy and it runs."""
    box = _open_box(tmp_path)
    with pytest.raises(OpenMeshError) as refused:
        apply_geometry_gate(_grid(), mesh_path=box, standoff=0.1)
    assert "cull=False" in str(refused.value), str(refused.value)
    planned = apply_geometry_gate(_grid(), mesh_path=box, cull=False, standoff=0.1)
    assert planned.report.base_culled == 0
    assert planned.report.base_standoff_culled > 0
    assert planned.report.mesh_path == str(box)


def test_p0400_probegate_a_band_without_cull_asks_no_containment(tmp_path, monkeypatch):
    """P0400-PROBEGATE (PFS-2097.007) without culling the band flags by distance alone."""
    mesh = load_surface_mesh(_open_box(tmp_path), require_watertight=False)

    def no_containment(mesh, points):
        raise AssertionError("containment was asked of a mesh the gate never checked")

    monkeypatch.setattr(gate, "_inside", no_containment)
    planned = apply_geometry_gate(
        _grid(z=0.6, band=RefinementBand(distance=0.15, factor=2)), mesh, cull=False
    )
    assert planned.report.refined_added == 16
    assert np.all(planned.points[25:, 2] == 0.6)


def test_p0400_probegate_an_open_mesh_object_is_refused_when_culling(tmp_path):
    """P0400-PROBEGATE (PFS-2097.008) an open box passed as mesh= with cull=True refuses."""
    mesh = load_surface_mesh(_open_box(tmp_path), require_watertight=False)
    assert not mesh.is_watertight
    with pytest.raises(OpenMeshError, match="not watertight"):
        apply_geometry_gate(_grid(), mesh)


def test_p0400_probegate_mesh_and_mesh_path_together_are_refused():
    """P0400-PROBEGATE (PFS-2103.001) the report never names a file the gate did not load."""
    mesh = load_surface_mesh(CUBE)
    with pytest.raises(ProbeGeometryError, match="not both"):
        apply_geometry_gate(_grid(), mesh, mesh_path=CUBE)
    assert apply_geometry_gate(_grid(), mesh).report.mesh_path is None
    assert apply_geometry_gate(_grid(), mesh_path=CUBE).report.mesh_path == str(CUBE)
