"""Tier 1: geometry gate of the probe planner (culling, band refinement)."""

import sys
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.probes import (
    AxisSpec,
    FrameDefinition,
    PlanarProbeGrid,
    PlannedProbes,
    RefinementBand,
)
from pyflightstream.probes.geometry import (
    GeometryEngineMissingError,
    OpenMeshError,
    apply_geometry_gate,
    load_surface_mesh,
)

CUBE = Path(__file__).parent / "fixtures" / "cube.obj"


def midplane_grid() -> PlanarProbeGrid:
    # The z = 0 plane cuts the unit cube; nodes at +-0.2 fall inside.
    return PlanarProbeGrid(
        frame=FrameDefinition(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=AxisSpec(start=-1.0, stop=1.0, spacing=0.4),
        v=AxisSpec(start=-1.0, stop=1.0, spacing=0.4),
    )


def test_cube_fixture_is_watertight():
    mesh = load_surface_mesh(CUBE)
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(1.0)


def test_culling_discards_exactly_the_points_inside_the_body():
    planned = apply_geometry_gate(midplane_grid(), mesh_path=CUBE)
    # Axis points are -1, -0.6, -0.2, 0.2, 0.6, 1: the 2x2 block at
    # +-0.2 lies strictly inside the cube on the z = 0 midplane.
    assert planned.report.base_total == 36
    assert planned.report.base_culled == 4
    assert planned.report.kept == 32
    assert len(planned.points) == 32
    assert not any(
        (abs(p[0]) < 0.5) and (abs(p[1]) < 0.5) and (abs(p[2]) < 0.5) for p in planned.points
    )


def test_gate_without_mesh_keeps_everything():
    planned = apply_geometry_gate(midplane_grid())
    assert planned.report.base_culled == 0
    assert planned.report.mesh_path is None
    assert len(planned.points) == 36


def test_band_refinement_adds_fine_nodes_only_near_the_surface():
    # Plane z = 0.6 hovers 0.1 above the cube top face: with band
    # distance 0.15 exactly the four cells over the face are flagged
    # (their centers see 0.1; every other center is farther than 0.15).
    grid = PlanarProbeGrid(
        frame=FrameDefinition(
            origin=(0.0, 0.0, 0.6), x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)
        ),
        u=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        v=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        refinement=RefinementBand(distance=0.15, factor=2),
    )
    planned = apply_geometry_gate(grid, mesh_path=CUBE)
    # 2x2 flagged block: 5x5 fine lattice minus the 3x3 base nodes.
    assert planned.report.base_total == 25
    assert planned.report.base_culled == 0
    assert planned.report.refined_added == 16
    assert planned.report.refined_culled == 0
    assert planned.report.band_distance == 0.15
    refined = planned.points[25:]
    assert len(refined) == 16
    assert np.all(np.abs(refined[:, :2]) <= 0.5 + 1e-12)
    assert np.all(refined[:, 2] == 0.6)
    # Fine spacing is the base spacing over the factor.
    unique_x = np.unique(np.round(refined[:, 0], 12))
    assert np.diff(unique_x) == pytest.approx(np.full(len(unique_x) - 1, 0.25))


def test_refinement_without_a_mesh_is_refused():
    grid = PlanarProbeGrid(
        frame=FrameDefinition(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        v=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        refinement=RefinementBand(distance=0.1, factor=2),
    )
    with pytest.raises(ValueError, match="measured from the surface"):
        apply_geometry_gate(grid)


def test_open_mesh_is_refused_with_the_physical_cause(tmp_path):
    open_mesh = tmp_path / "open.obj"
    open_mesh.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3\nf 1 3 4\n",
        encoding="utf-8",
    )
    with pytest.raises(OpenMeshError, match="not watertight"):
        load_surface_mesh(open_mesh)


def test_missing_engine_names_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "trimesh", None)
    with pytest.raises(GeometryEngineMissingError, match=r"\[geom\]"):
        load_surface_mesh(CUBE)


def test_planned_probes_serialization_round_trip():
    planned = apply_geometry_gate(midplane_grid(), mesh_path=CUBE)
    clone = PlannedProbes.from_json(planned.to_json())
    assert clone.grid == planned.grid
    assert clone.report == planned.report
    assert np.allclose(clone.points, planned.points)


def test_verify_positions_enforces_the_row_order_contract():
    planned = apply_geometry_gate(midplane_grid(), mesh_path=CUBE)
    # Round-tripped through the export's four-digit mantissa format.
    exported = np.asarray([[float(f"{c:.4e}") for c in row] for row in planned.points])
    planned.verify_positions(exported)
    with pytest.raises(ValueError, match="does not belong to this plan"):
        planned.verify_positions(exported[:-1])
    shuffled = np.random.default_rng(0).permutation(exported)
    with pytest.raises(ValueError, match="row order contract is broken"):
        planned.verify_positions(shuffled)
