"""Native nodal strength is matched by coordinates AND polygon topology."""

import numpy as np
import pytest

from pyflightstream.results import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.surface import (
    REFERENCE_FRAME,
    VtkSurface,
    translate_surface_exports,
    translate_vtk_surface,
    write_vtk_surface,
)


def _vtk():
    return VtkSurface(
        points=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]),
        offsets=np.array([0, 4]),
        connectivity=np.array([0, 1, 2, 3]),
        cell_data={"Cp_reference": np.array([-0.2])},
    )


def _native(path, *, strength="30 10 40 20", edges="2 4 4 1 1 3 3 2"):
    # Native node order: original nodes 2,0,3,1. Left/right lists are separate blocks.
    path.write_text(
        'TITLE="Native"\nVARIABLES="X","Y","Z","Singularity_strength"\n'
        "ZONE T=Solver, NODES=4, ELEMENTS=1, FACES=4, DATAPACKING=BLOCK, "
        "ZONETYPE=FEPolygon, NumConnectedBoundaryFaces=0, TotalNumBoundaryConnections=0\n"
        "1 0 0 1\n1 0 1 0\n0 0 0 0\n" + strength + "\n" + edges + "\n1 1 1 1\n0 0 0 0\n",
        encoding="utf-8",
    )
    return path


def test_native_node_order_is_mapped_without_averaging_cell_values(tmp_path):
    """GOAL033:post:checks:singularity_strength_source."""
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        read_native_tecplot_surface,
    )

    native = read_native_tecplot_surface(_native(tmp_path / "native.dat"))
    surface, proof = attach_native_strength(_vtk(), native)
    assert surface.point_data["Singularity_strength"].tolist() == [10.0, 20.0, 30.0, 40.0]
    assert surface.cell_data["Cp_reference"].tolist() == [-0.2]
    assert proof["matched_nodes"] == 4
    assert proof["topology_verified"] is True


def test_millimetre_rotated_float32_vtk_still_matches_native_nodes(tmp_path):
    """Q0-src-post-2: the VTK is written at single precision in a rotated loads
    frame and transformed back; the native file is double in REFERENCE. At
    hundreds of millimetres their rounding differs by ~1e-5, far above a fixed
    1e-6, so the default tolerance must scale with the geometry."""
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        read_native_tecplot_surface,
    )

    scale, offset = 250.0, np.array([400.0, -300.0, 120.0])
    native = read_native_tecplot_surface(_native(tmp_path / "native.dat"))
    native.points[:] = native.points * scale + offset
    angle = np.radians(37.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    reference = _vtk().points * scale + offset
    loads32 = (reference @ rotation.T).astype(np.float32).astype(np.float64)
    vtk = _vtk()
    vtk = VtkSurface(
        points=loads32 @ rotation,
        offsets=vtk.offsets,
        connectivity=vtk.connectivity,
        cell_data=vtk.cell_data,
    )
    assert np.max(np.abs(vtk.points - reference)) > 1e-6, "the rounding is real"
    surface, proof = attach_native_strength(vtk, native)
    assert surface.point_data["Singularity_strength"].tolist() == [10.0, 20.0, 30.0, 40.0]
    assert 1e-6 < proof["coordinate_tolerance"] < 1e-2
    # An explicit tolerance is still honoured and still refuses what it cannot resolve.
    with pytest.raises(MalformedOutputError, match="match"):
        attach_native_strength(vtk, native, coordinate_tolerance=1e-9)


@pytest.mark.parametrize(
    ("extent", "offset"),
    [
        (250.0 * np.sqrt(2.0), (400.0, -300.0, 120.0)),
        # GOAL-034 Q8 QA-3: a small part FAR from the origin. Float32 rounding
        # grows with |x| (~|x| * 6e-8), not with the extent, so 1e-6 of a
        # 100 mm extent (1e-4) is below the rounding at 1e4 mm (~6e-4).
        (100.0, (1.0e4, -1.0e4, 1.0e4)),
    ],
    ids=["extent-dominated", "offset-dominated"],
)
def test_default_tolerance_covers_float32_rounding_of_the_coordinates(tmp_path, extent, offset):
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        read_native_tecplot_surface,
    )

    scale = extent / np.sqrt(2.0)  # the unit square's diagonal is sqrt(2)
    shift = np.array(offset)
    native = read_native_tecplot_surface(_native(tmp_path / "native.dat"))
    native.points[:] = native.points * scale + shift
    angle = np.radians(37.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    reference = _vtk().points * scale + shift
    loads32 = (reference @ rotation.T).astype(np.float32).astype(np.float64)
    vtk = _vtk()
    vtk = VtkSurface(
        points=loads32 @ rotation,
        offsets=vtk.offsets,
        connectivity=vtk.connectivity,
        cell_data=vtk.cell_data,
    )
    assert np.max(np.abs(vtk.points - reference)) > 1e-6, "the rounding is real"
    surface, proof = attach_native_strength(vtk, native)
    assert surface.point_data["Singularity_strength"].tolist() == [10.0, 20.0, 30.0, 40.0]
    rounding = 4 * np.finfo(np.float32).eps * float(np.abs(native.points).max())
    assert proof["coordinate_tolerance"] == pytest.approx(max(1e-10, 1e-6 * extent, rounding))


def test_same_coordinates_with_different_polygon_edges_are_refused(tmp_path):
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        read_native_tecplot_surface,
    )

    native = read_native_tecplot_surface(_native(tmp_path / "native.dat", edges="2 1 1 4 4 3 3 2"))
    with pytest.raises(MalformedOutputError, match="topology"):
        attach_native_strength(_vtk(), native)


def test_duplicate_coordinate_mapping_is_ambiguous_even_with_equal_counts(tmp_path):
    from pyflightstream.results.native_surface import (
        attach_native_strength,
        read_native_tecplot_surface,
    )

    native = read_native_tecplot_surface(_native(tmp_path / "native.dat"))
    native.points[0] = native.points[1]
    with pytest.raises(MalformedOutputError, match="ambiguous|bijection|match"):
        attach_native_strength(_vtk(), native)


def test_truncated_face_connectivity_is_not_accepted(tmp_path):
    from pyflightstream.results.native_surface import read_native_tecplot_surface

    path = _native(tmp_path / "native.dat")
    path.write_text(path.read_text().rsplit("0 0 0 0", 1)[0], encoding="utf-8")
    with pytest.raises(IncompleteOutputError):
        read_native_tecplot_surface(path)


def test_nonfinite_native_strength_is_refused(tmp_path):
    from pyflightstream.results.native_surface import read_native_tecplot_surface

    with pytest.raises(MalformedOutputError, match="finite"):
        read_native_tecplot_surface(_native(tmp_path / "native.dat", strength="nan 10 40 20"))


def test_translation_carries_real_strength_and_both_source_hashes(tmp_path):
    """GOAL033:capability_ids:items:G53."""
    path = write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="test")
    native = _native(tmp_path / "native.dat")
    record = translate_vtk_surface(
        path, tmp_path / "p.dat", frame=REFERENCE_FRAME, native_tecplot=native
    )
    text = (tmp_path / "p.dat").read_text()
    assert '"Singularity_strength"' in text
    assert "SOURCE_NATIVE_TECPLOT_SHA256" in text
    assert len(record["native_source_sha256"]) == 64
    assert record["nodal_variables"] == ["Singularity_strength"]
    assert record["not_carried"] == []


def test_a_loads_frame_far_from_the_origin_still_matches_its_native_nodes(tmp_path):
    """GOAL-034 Q8 CXQ8R2-1: the VTK is rounded to single precision in the LOADS
    frame; a loads frame 1e4 away rounds each coordinate by up to ~5e-4, which the
    reference-frame extent of a unit panel did not allow for."""
    from pyflightstream.results.surface import SurfaceFrame

    origin = (10000.0, 0.0, 0.0)
    reference = _vtk().points + np.array([0.1, 0.1, 0.0])
    loads = (reference - np.array(origin)).astype(np.float32).astype(float)
    assert np.abs(loads + np.array(origin) - reference).max() > 1e-5  # the rounding is real
    surface = VtkSurface(
        points=loads,
        offsets=_vtk().offsets,
        connectivity=_vtk().connectivity,
        cell_data=dict(_vtk().cell_data),
    )
    path = write_vtk_surface(tmp_path / "p.vtk", surface, title="test")
    native = tmp_path / "native.dat"
    native.write_text(
        'TITLE="Native"\nVARIABLES="X","Y","Z","Singularity_strength"\n'
        "ZONE T=Solver, NODES=4, ELEMENTS=1, FACES=4, DATAPACKING=BLOCK, "
        "ZONETYPE=FEPolygon, NumConnectedBoundaryFaces=0, TotalNumBoundaryConnections=0\n"
        "1.1 0.1 0.1 1.1\n1.1 0.1 1.1 0.1\n0 0 0 0\n30 10 40 20\n2 4 4 1 1 3 3 2\n"
        "1 1 1 1\n0 0 0 0\n",
        encoding="utf-8",
    )
    frame = SurfaceFrame(origin, REFERENCE_FRAME.axes, 2)
    record = translate_vtk_surface(path, tmp_path / "p.dat", frame=frame, native_tecplot=native)
    assert record["nodal_variables"] == ["Singularity_strength"]


def test_a_loads_frame_far_along_x_does_not_widen_the_match_along_z(tmp_path):
    """GOAL-034 Q8 CXQ8R4-1: one scalar tolerance carried the X rounding of a
    loads frame 1e6 away to every axis (about 0.48), so a native surface moved
    0.25 along Z still matched and lent its strength. The tolerance is per axis."""
    from pyflightstream.results.surface import SurfaceFrame

    origin = (1_000_000.0, 0.0, 0.0)
    reference = _vtk().points + np.array([0.1, 0.1, 0.0])
    loads = (reference - np.array(origin)).astype(np.float32).astype(float)
    surface = VtkSurface(
        points=loads,
        offsets=_vtk().offsets,
        connectivity=_vtk().connectivity,
        cell_data=dict(_vtk().cell_data),
    )
    path = write_vtk_surface(tmp_path / "p.vtk", surface, title="test")
    native = tmp_path / "native.dat"
    native.write_text(
        'TITLE="Native"\nVARIABLES="X","Y","Z","Singularity_strength"\n'
        "ZONE T=Solver, NODES=4, ELEMENTS=1, FACES=4, DATAPACKING=BLOCK, "
        "ZONETYPE=FEPolygon, NumConnectedBoundaryFaces=0, TotalNumBoundaryConnections=0\n"
        "1.1 0.1 0.1 1.1\n1.1 0.1 1.1 0.1\n0.25 0.25 0.25 0.25\n30 10 40 20\n"
        "2 4 4 1 1 3 3 2\n1 1 1 1\n0 0 0 0\n",
        encoding="utf-8",
    )
    frame = SurfaceFrame(origin, REFERENCE_FRAME.axes, 2)
    with pytest.raises(MalformedOutputError, match="missing or ambiguous"):
        translate_vtk_surface(path, tmp_path / "p.dat", frame=frame, native_tecplot=native)


def test_a_loads_frame_far_along_x_does_not_accept_a_shift_along_x(tmp_path):
    """GOAL-034 Q8 CXQ8R5-1: the per-axis allowance was four float32 epsilons of
    the largest loads coordinate (about 0.48 at 1e6), so a native surface moved
    0.25 along X still matched. Float32 steps by 0.0625 there; the allowance is
    now the spacing of the written coordinates, and the shift is refused."""
    from pyflightstream.results.surface import SurfaceFrame

    origin = (1_000_000.0, 0.0, 0.0)
    reference = _vtk().points + np.array([0.1, 0.1, 0.0])
    loads = (reference - np.array(origin)).astype(np.float32).astype(float)
    surface = VtkSurface(
        points=loads,
        offsets=_vtk().offsets,
        connectivity=_vtk().connectivity,
        cell_data=dict(_vtk().cell_data),
    )
    path = write_vtk_surface(tmp_path / "p.vtk", surface, title="test")
    native = tmp_path / "native.dat"
    native.write_text(
        'TITLE="Native"\nVARIABLES="X","Y","Z","Singularity_strength"\n'
        "ZONE T=Solver, NODES=4, ELEMENTS=1, FACES=4, DATAPACKING=BLOCK, "
        "ZONETYPE=FEPolygon, NumConnectedBoundaryFaces=0, TotalNumBoundaryConnections=0\n"
        "1.35 0.35 0.35 1.35\n1.1 0.1 1.1 0.1\n0 0 0 0\n30 10 40 20\n"
        "2 4 4 1 1 3 3 2\n1 1 1 1\n0 0 0 0\n",
        encoding="utf-8",
    )
    frame = SurfaceFrame(origin, REFERENCE_FRAME.axes, 2)
    with pytest.raises(MalformedOutputError, match="missing or ambiguous"):
        translate_vtk_surface(path, tmp_path / "p.dat", frame=frame, native_tecplot=native)


def test_stamped_step_never_borrows_final_native_strength(tmp_path):
    write_vtk_surface(tmp_path / "p_iteration=3.vtk", _vtk(), title="step")
    _native(tmp_path / "native.dat")
    records = translate_surface_exports(
        tmp_path,
        [
            {
                "vtk": "p.vtk",
                "dat": "p.dat",
                "native_tecplot": "native.dat",
                "frame": REFERENCE_FRAME.record(),
            }
        ],
    )
    assert not (tmp_path / "p_iteration=3.dat").exists()
    assert any("native_iteration=3.dat" in p for p in records[0]["problems"])


def test_existing_translation_with_changed_native_bytes_is_not_claimed_current(tmp_path):
    write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="step")
    native = _native(tmp_path / "native.dat")
    request = [
        {
            "vtk": "p.vtk",
            "dat": "p.dat",
            "native_tecplot": "native.dat",
            "frame": REFERENCE_FRAME.record(),
        }
    ]
    first = translate_surface_exports(tmp_path, request)
    assert first[0]["written"] == ["p.dat"]
    before = (tmp_path / "p.dat").read_bytes()
    _native(native, strength="300 100 400 200")
    second = translate_surface_exports(tmp_path, request)
    assert second[0]["written"] == []
    assert second[0]["problems"]
    assert (tmp_path / "p.dat").read_bytes() == before


def test_native_source_is_internal_tracked_and_emitted_once():
    from pyflightstream.cases import classify_outputs
    from pyflightstream.cases.workflows import build_script, with_tecplot_source
    from tests.tier1_offline.test_workflows import steady_case

    outputs = with_tecplot_source(["p.txt", "p.dat", "p.vtk"])
    assert outputs.count("p_native_tecplot.dat") == 1
    assert with_tecplot_source(outputs) == outputs
    assert classify_outputs(list(reversed(outputs)))["tecplot"] == "p.dat"
    case = steady_case().model_copy(update={"outputs": outputs})
    from pyflightstream.script import Script

    script = Script("26.124")
    build_script(case, script)
    text = script.render()
    assert text.count("EXPORT_SOLVER_ANALYSIS_TECPLOT") == 1
    assert "p_native_tecplot.dat" in text
    assert script.surface_translations[0]["native_tecplot"] == "p_native_tecplot.dat"


def test_old_record_native_suffix_is_not_reclassified():
    from pyflightstream.cases import classify_outputs

    assert classify_outputs(["p_native_tecplot.dat"], package_version="0.28.0") == {
        "tecplot": "p_native_tecplot.dat"
    }


def test_existing_native_translation_requires_content_proof_not_just_headers(tmp_path):
    write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="step")
    _native(tmp_path / "native.dat")
    request = [
        {
            "vtk": "p.vtk",
            "dat": "p.dat",
            "native_tecplot": "native.dat",
            "frame": REFERENCE_FRAME.record(),
        }
    ]
    first = translate_surface_exports(tmp_path, request)
    assert first[0]["written"] == ["p.dat"]
    # A fresh request has no cached artifact hash. Retain headers but truncate data.
    path = tmp_path / "p.dat"
    text = path.read_text()
    path.write_text(text[: text.index("ZONE")], encoding="utf-8")
    damaged = path.read_bytes()
    second = translate_surface_exports(tmp_path, request)
    assert second[0]["written"] == []
    assert second[0]["problems"]
    assert path.read_bytes() == damaged


def test_valid_existing_translation_reconstructs_missing_artifact_proof(tmp_path):
    write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="step")
    _native(tmp_path / "native.dat")
    request = [
        {
            "vtk": "p.vtk",
            "dat": "p.dat",
            "native_tecplot": "native.dat",
            "frame": REFERENCE_FRAME.record(),
        }
    ]
    translate_surface_exports(tmp_path, request)
    recovered = translate_surface_exports(tmp_path, request)[0]
    assert recovered["written"] == ["p.dat"]
    assert len(recovered["artifacts"]["p.dat"]["output_sha256"]) == 64


def test_public_native_surface_example_preserves_association_and_provenance(tmp_path):
    import runpy
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "examples" / "surface_with_native_strength.py"
    translate = runpy.run_path(str(example))["translate_with_native"]
    vtk = write_vtk_surface(tmp_path / "p.vtk", _vtk(), title="example")
    native = _native(tmp_path / "native.dat")
    result = translate(vtk, native, tmp_path / "translated.dat", REFERENCE_FRAME.record())
    assert result["location"] == "mixed nodal and cell-centred"
    assert result["node_mapping"]["topology_verified"]
    assert len(result["source_sha256"]) == len(result["native_source_sha256"]) == 64


def test_cached_frame_identity_preserves_full_precision(tmp_path):
    from pyflightstream.results.surface import SurfaceFrame

    original = SurfaceFrame((123456.1, 0.0, 0.0), REFERENCE_FRAME.axes, 2)
    changed = SurfaceFrame((123456.4, 0.0, 0.0), REFERENCE_FRAME.axes, 2)
    assert original.describe() == changed.describe()
    surface = _vtk()
    surface.points[:, 0] -= original.origin[0]
    write_vtk_surface(tmp_path / "p.vtk", surface, title="frame precision")
    _native(tmp_path / "native.dat")
    request = [
        {
            "vtk": "p.vtk",
            "dat": "p.dat",
            "native_tecplot": "native.dat",
            "frame": original.record(),
        }
    ]
    first = translate_surface_exports(tmp_path, request)
    assert first[0]["written"] == ["p.dat"]
    before = (tmp_path / "p.dat").read_bytes()
    first[0]["frame"] = changed.record()
    second = translate_surface_exports(tmp_path, first)
    assert second[0]["written"] == []
    assert any("frame" in issue for issue in second[0]["problems"])
    assert (tmp_path / "p.dat").read_bytes() == before


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("NODES=4", "NODES=4.5"),
        ("ELEMENTS=1", "ELEMENTS=1.5"),
        ("FACES=4", "FACES=4.5"),
        ("NumConnectedBoundaryFaces=0", "NumConnectedBoundaryFaces=0.5"),
        ("TotalNumBoundaryConnections=0", "TotalNumBoundaryConnections=0.5"),
    ],
)
def test_fractional_native_counts_are_not_truncated(tmp_path, original, replacement):
    from pyflightstream.results.native_surface import read_native_tecplot_surface

    source = _native(tmp_path / "fractional.dat")
    source.write_text(source.read_text().replace(original, replacement), encoding="utf-8")
    with pytest.raises(MalformedOutputError, match="invalid count"):
        read_native_tecplot_surface(source)


def test_measured_native_export_preserves_node_values():
    import hashlib
    import json
    from pathlib import Path

    from pyflightstream.results.native_surface import read_native_tecplot_surface

    fixtures = Path(__file__).parent / "fixtures"
    source = fixtures / "native_surface_synthetic.dat"
    metadata = json.loads((fixtures / "native_surface_synthetic.json").read_text())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == metadata["fixture_sha256"]
    surface = read_native_tecplot_surface(source)
    assert (surface.n_points, surface.n_cells) == (1054, 1138)
    assert surface.point_data["Singularity_strength"][[0, 527, 1053]].tolist() == [
        50.29516345644496,
        46.41945086248663,
        -22.56217052422124,
    ]
    assert surface.points[[0, 527, 1053]].tolist() == [
        [0.0, 0.0, 0.0],
        [4.0, 0.4330127019, -0.25],
        [4.563620977, 0.007028180246488963, 0.274320000000013],
    ]
    assert not surface.cell_data


@pytest.mark.parametrize("cut", ["empty", "header", "zone", "payload", "connectivity"])
def test_measured_native_export_truncation_is_incomplete(tmp_path, cut):
    from pathlib import Path

    from pyflightstream.results.native_surface import read_native_tecplot_surface

    source = Path(__file__).parent / "fixtures" / "native_surface_synthetic.dat"
    data = source.read_bytes()
    zone_start = data.index(b"ZONE ")
    limits = {
        "empty": 0,
        "header": zone_start,
        "zone": data.index(b"\n", zone_start) + 1,
        "payload": len(data) // 2,
        "connectivity": data.rfind(b"\n", 0, len(data) - 1),
    }
    incomplete = tmp_path / "incomplete.dat"
    incomplete.write_bytes(data[: limits[cut]])
    with pytest.raises(IncompleteOutputError, match="Native Tecplot ends"):
        read_native_tecplot_surface(incomplete)
