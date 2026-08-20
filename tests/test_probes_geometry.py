"""Tier 1: geometry gate of the probe planner, and its export register.

Pipeline role: quality gate on the two things the probe planner decides
before any solver sees it. The GEOMETRY half (culling, band refinement,
standoff, row order) is the older one. The EXPORT half is PFS-2011.02:
the solver writes one file per exported path, so a script that emits two
exports to one path produced two identical lines and one surviving file,
with nothing in the script, the record or the manifest saying which of
the two surveys the file holds. That is the class PYFS-005 records.

The refusal lives on the script's register rather than on the file
system, because at script-build time nothing exists to test: the file is
written later, by the solver, on another machine. It has to name BOTH
call sites, and this module holds the cases that reach it through
:func:`pyflightstream.probes.emit_probe_export`, the entry point a probe
planner actually calls.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.exceptions import CommandArgumentError
from pyflightstream.probes import (
    AxisSpec,
    FrameDefinition,
    PlanarProbeGrid,
    PlannedProbes,
    RefinementBand,
    emit_probe_export,
)
from pyflightstream.probes.geometry import (
    GeometryEngineMissingError,
    OpenMeshError,
    apply_geometry_gate,
    load_surface_mesh,
)
from pyflightstream.script import Script, helpers

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


def test_standoff_margin_culls_the_wall_hugging_probes():
    # Midplane axis points are -1, -0.6, -0.2, 0.2, 0.6, 1 against the
    # unit cube: outside nodes with in-plane clearance below 0.15 are
    # the twelve at (+-0.6, |y| <= 0.6) and (+-0.2, +-0.6), whose
    # distances are 0.1 or 0.1*sqrt(2).
    planned = apply_geometry_gate(midplane_grid(), mesh_path=CUBE, standoff=0.15)
    assert planned.report.base_culled == 4
    assert planned.report.base_standoff_culled == 12
    assert planned.report.standoff == 0.15
    assert planned.report.kept == 20
    assert len(planned.points) == 20
    kept_xy = np.abs(planned.points[:, :2])
    clearance = np.linalg.norm(np.maximum(kept_xy - 0.5, 0.0), axis=1)
    assert np.all(clearance >= 0.15)


def test_standoff_without_a_mesh_is_refused():
    with pytest.raises(ValueError, match="measured from the surface"):
        apply_geometry_gate(midplane_grid(), standoff=0.1)


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


# --- the export register: two calls, one path (PFS-2011.02) ----------------


def test_the_probe_planner_refuses_one_export_path_twice():
    """Two exports to one path meant the second silently replaced the first.

    Nothing existed to test at script-build time, which is why this
    surface needed a register rather than a file check: the script
    rendered two identical lines and the collision happened later, inside
    the solver, with nothing recording that only one file survived.
    """
    script = Script(version="26.120")
    emit_probe_export(script, "survey.csv")

    with pytest.raises(CommandArgumentError) as refused:
        emit_probe_export(script, "survey.csv", update=False)

    assert "survey.csv" in str(refused.value), "the refusal does not name the colliding path"
    assert script.render().count("EXPORT_PROBE_POINTS") == 1, (
        "the refused call still emitted its export line, so the script would carry the "
        "collision it was refused for"
    )


def test_the_refusal_names_the_entry_point_the_earlier_call_used():
    """Both call sites, and the earlier one by the name it was written as.

    ``helpers.export_probes`` stamps the register with its own name, so a
    collision between two calls made through ``emit_probe_export`` used
    to report a function the caller's code never mentions. A refusal
    naming a call site that does not exist is worse than one naming none:
    it sends the reader to look for a line that is not there.
    """
    script = Script(version="26.120")
    emit_probe_export(script, "survey.csv")

    with pytest.raises(CommandArgumentError) as refused:
        emit_probe_export(script, "survey.csv", update=False)

    assert "from emit_probe_export" in str(refused.value), (
        "the refusal names an entry point the caller did not use; the earlier call "
        "site must be named as it was written"
    )


def test_the_two_entry_points_share_one_register():
    """The register is on the SCRIPT, so mixing entry points still collides.

    A planner that emits through this layer and a hand-written line that
    calls the helper directly are two call sites of one script, and the
    solver still writes one file for the path they share.
    """
    script = Script(version="26.120")
    emit_probe_export(script, "survey.csv")

    with pytest.raises(CommandArgumentError, match="already exports"):
        helpers.export_probes(script, "survey.csv", update=False)

    other = Script(version="26.120")
    helpers.export_probes(other, "survey.csv")
    with pytest.raises(CommandArgumentError) as refused:
        emit_probe_export(other, "survey.csv", update=False)
    assert "from export_probes" in str(refused.value), (
        "the helper's own call site stopped being named once this layer re-stamped "
        "the register; the earlier site is whichever entry point wrote it"
    )


def test_two_different_export_paths_still_emit_twice():
    """The control: distinct paths are the ordinary survey.

    The second call passes ``update=False`` because UPDATE_PROBE_POINTS
    is an ANALYSIS-phase command and EXPORT_PROBE_POINTS an EXPORT-phase
    one, so refreshing again after an export runs the script backwards
    and the phase order refuses it. Refresh once, export several times is
    the real shape of the usage this control protects.
    """
    script = Script(version="26.120")
    emit_probe_export(script, "survey_upstream.csv")
    emit_probe_export(script, "survey_wake.csv", update=False)
    assert script.render().count("EXPORT_PROBE_POINTS") == 2
