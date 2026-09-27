# GEOVERSE_HEADER
# file_version: 1.0.1
# last_modified_at: 2026-09-27T20:50:55.323Z
# last_modified_by: OpenAI / Codex / unknown / implementation-agent
# dependencies: [pyflightstream.post.boundary_layer, pyflightstream.cases.ProductsSpec]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Bind existing behavioral acceptance tests to exact GOAL-033 obligations.
# revision_source: git
"""Boundary-layer section data retain original cell association."""

import numpy as np
import pytest
from pydantic import ValidationError

from pyflightstream.cases import ProductsSpec
from pyflightstream.post._tables import ProductError
from pyflightstream.post.boundary_layer import sample_boundary_layer
from pyflightstream.results import SurfaceSection
from pyflightstream.results.surface import REFERENCE_FRAME, SurfaceFrame, VtkSurface


def _surface():
    return VtkSurface(
        points=np.array(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0]], dtype=float
        ),
        offsets=np.array([0, 4, 8]),
        connectivity=np.array([0, 1, 2, 3, 1, 4, 5, 2]),
        cell_data={
            "BL_displacement_thickness": np.array([0.04, 0.08]),
            "BL_momentum_thickness": np.array([0.02, 0.03]),
            "BL_shape_factor": np.array([2.0, 8 / 3]),
            "BL_Thickness": np.array([0.2, 0.4]),
            "Boundary_Index": np.array([7.0, 19.0]),
        },
    )


def _section(points):
    values = np.zeros((len(points), 20))
    values[:, 1:4] = points
    return SurfaceSection(index=1, edges=len(points), values=values)


def test_two_public_flags_are_distinct_and_off_by_default():
    product = ProductsSpec()
    assert product.boundary_layer_integrals is False
    assert product.boundary_layer_velocity_profile is False
    assert ProductsSpec(boundary_layer_integrals=True).boundary_layer_integrals


def test_profile_request_never_silently_becomes_integrals():
    # GOAL033:post:checks:bl_profiles
    # GOAL033:capability_ids:items:G52
    with pytest.raises(ValidationError, match="boundary_layer_velocity_profile.*unavailable"):
        ProductsSpec(boundary_layer_integrals=True, boundary_layer_velocity_profile=True)


def test_cut_samples_keep_cell_values_and_shared_edge_incidence():
    result = sample_boundary_layer(
        _surface(),
        [_section([[0.5, 0.5, 0], [1, 0.5, 0]])],
        surface_frame=REFERENCE_FRAME,
        section_frames={1: REFERENCE_FRAME},
    )
    assert [row["CELL_ID"] for row in result.rows] == [0, 0, 1]
    assert [row["INCIDENT_CELLS"] for row in result.rows] == [1, 2, 2]
    assert [row["BL_displacement_thickness"] for row in result.rows] == [0.04, 0.04, 0.08]
    assert [row["Boundary_Index"] for row in result.rows] == [7.0, 7.0, 19.0]
    assert "Transition_marker" in result.missing_fields
    assert result.rows[0]["Transition_marker"] is None


def test_coordinates_transform_but_thickness_is_never_rescaled():
    frame = SurfaceFrame(origin=(10, 0, 0), axes=((0, 1, 0), (-1, 0, 0), (0, 0, 1)))
    surface = _surface()
    result = sample_boundary_layer(
        surface, [_section([[0.5, 0.5, 0]])], surface_frame=frame, section_frames={1: frame}
    )
    assert [result.rows[0][axis] for axis in ("X", "Y", "Z")] == [9.5, 0.5, 0.0]
    assert result.rows[0]["BL_Thickness"] == 0.2


def test_missing_section_placement_is_explicit():
    with pytest.raises(ProductError, match="section 1.*placement"):
        sample_boundary_layer(
            _surface(),
            [_section([[0.5, 0.5, 0]])],
            surface_frame=REFERENCE_FRAME,
            section_frames={},
        )


def test_unmatched_sample_is_not_given_nearest_cell_values():
    with pytest.raises(ProductError, match="section 1.*sample 1.*no incident"):
        sample_boundary_layer(
            _surface(),
            [_section([[0.5, 0.5, 1]])],
            surface_frame=REFERENCE_FRAME,
            section_frames={1: REFERENCE_FRAME},
        )


def test_vtk_with_no_boundary_layer_data_is_named_unavailable():
    surface = _surface()
    surface.cell_data.clear()
    with pytest.raises(ProductError, match="no boundary-layer"):
        sample_boundary_layer(
            surface,
            [_section([[0.5, 0.5, 0]])],
            surface_frame=REFERENCE_FRAME,
            section_frames={1: REFERENCE_FRAME},
        )


def _whole_product_fixture(tmp_path, monkeypatch):
    from pyflightstream.results import parse_surface_sections
    from pyflightstream.results.surface import write_vtk_surface
    from tests.tier1_offline.test_f07_section_distributions import _workspace
    from tests.tier1_offline.test_field_frames import _motion

    workspace, record = _workspace(tmp_path, monkeypatch)
    pproc = workspace.resolve_pproc("p001")
    pproc.products.boundary_layer_integrals = True
    sections = parse_surface_sections((workspace.sim_dir("7001") / "AL-020_cp.txt").read_text())
    cut_points = np.concatenate([section.positions for section in sections.sections])
    vertices = np.concatenate(
        [np.array([point, point + [1e-4, 0, 0], point + [0, 0, 1e-4]]) for point in cut_points]
    )
    count = len(cut_points)
    thickness = (np.arange(count) + 1) * 1e-10
    surface = VtkSurface(
        points=vertices - np.array([4.5, 0.0, 0.0]),
        offsets=np.arange(count + 1) * 3,
        connectivity=np.arange(count * 3),
        cell_data={"BL_displacement_thickness": thickness},
    )
    write_vtk_surface(
        workspace.sim_dir("7001") / "AL-020.vtk",
        surface,
        title="Synthetic BL cells around recorded-format cut coordinates",
    )
    record.outputs.append("AL-020.vtk")
    record.frame_motions = {4: _motion()}
    for block in record.sections_layout:
        block.update(frame_index=4, loads_frame_index=4)
    return workspace, record, thickness


def test_whole_post_writes_raw_bl_values_with_full_float_precision(tmp_path, monkeypatch):
    # GOAL033:post:checks:bl_integrals
    # GOAL033:capability_ids:items:G51
    from pyflightstream.post.products import read_csv_table
    from tests.tier1_offline.test_f07_section_distributions import _post

    workspace, record, expected = _whole_product_fixture(tmp_path, monkeypatch)
    out, manifest = _post(workspace)
    relative = "sections/AL-020_boundary_layer.csv"
    assert relative in manifest["products"], manifest["skipped"]
    _, rows = read_csv_table(out / relative)
    assert rows
    for row in rows:
        assert float(row["BL_displacement_thickness"]) == expected[int(row["CELL_ID"])]
    proof = manifest["products"][relative]
    assert proof["cell_index_base"] == 0
    assert proof["coordinate_unit"] == "METER"
    assert "BL_Thickness" in proof["unavailable_fields"]
    assert "AL-020.vtk" in proof["source_sha256"]
    assert (out / "sections/AL-020_cp_wing.csv").exists()


def test_missing_frame_proof_skips_only_the_bl_product(tmp_path, monkeypatch):
    from tests.tier1_offline.test_f07_section_distributions import _post

    workspace, record, _ = _whole_product_fixture(tmp_path, monkeypatch)
    record.frame_motions = None
    out, manifest = _post(workspace)
    relative = "sections/AL-020_boundary_layer.csv"
    assert "placement/motion proof" in manifest["skipped"][relative]
    assert not (out / relative).exists()
    assert (out / "sections/AL-020_cp_wing.csv").exists()


def test_requested_bl_adds_its_vtk_and_cut_source_exports():
    from pyflightstream.cases import PprocSpec

    spec = PprocSpec.model_validate(
        {
            "products": {"boundary_layer_integrals": True},
            "sections": {"distributions": [{"families": "all", "planes": ["XZ"]}]},
            "exports": {"vtk": False, "sections": False},
        }
    )
    assert "{name}.vtk" in spec.outputs(False)
    assert "{name}_cp.txt" in spec.outputs(False)
    from pyflightstream.cases.workflows import additional_outputs

    assert "point.vtk" in additional_outputs(spec, stem="point", unsteady=False)


def test_documented_bl_example_executes_and_keeps_tiny_values(tmp_path):
    import csv
    import runpy
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "examples" / "boundary_layer_sections.py"
    target = tmp_path / "example.csv"
    assert runpy.run_path(str(example))["main"]([str(target)]) == 0
    with target.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [float(row["BL_displacement_thickness"]) for row in rows] == [1e-9, 2e-9]
    assert [row["INCIDENT_CELLS"] for row in rows] == ["2", "2"]


def test_invalid_recorded_count_is_a_named_bl_skip(tmp_path, monkeypatch):
    from tests.tier1_offline.test_f07_section_distributions import _post

    workspace, record, _ = _whole_product_fixture(tmp_path, monkeypatch)
    record.sections_layout[0]["count"] = "1"
    _, manifest = _post(workspace)
    assert "positive integer count" in manifest["skipped"]["sections/AL-020_boundary_layer.csv"]


def test_bl_builder_records_exact_integer_section_and_loads_frames(tmp_path):
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, unsteady_case

    case = _with_pproc(unsteady_case(LAST_ITERS_AVG="480"), _wb_geometry(tmp_path))
    case.pproc.products.boundary_layer_integrals = True
    case.outputs = [name.format(name="point") for name in case.pproc.outputs(True)]
    script = Script("26.120")
    build_script(case, script)
    assert script.section_blocks
    for block in script.section_blocks:
        assert block["frame_index"] == script.frames_by_name[block["frame"]]
        assert block["loads_frame_index"] == script.loads_frame


def test_cut_inside_a_warped_native_quad_keeps_its_original_cell():
    surface = _surface()
    surface.points[2, 2] = 0.1
    # Point on the chord through the quad edges in the y=0.5 section plane.
    result = sample_boundary_layer(
        surface,
        [_section([[0.25, 0.5, 0.0125]])],
        surface_frame=REFERENCE_FRAME,
        section_frames={1: REFERENCE_FRAME},
        section_normals={1: (0, 1, 0)},
    )
    assert result.rows[0]["CELL_ID"] == 0
    assert result.rows[0]["BL_Thickness"] == 0.2


def test_warped_quad_does_not_accept_a_point_only_inside_its_bounding_box():
    surface = _surface()
    surface.points[2, 2] = 0.1
    with pytest.raises(ProductError, match="no incident"):
        sample_boundary_layer(
            surface,
            [_section([[0.25, 0.5, 0.05]])],
            surface_frame=REFERENCE_FRAME,
            section_frames={1: REFERENCE_FRAME},
            section_normals={1: (0, 1, 0)},
        )
