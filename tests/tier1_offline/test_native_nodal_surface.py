# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.5
# artifact_id: native-nodal-surface-tests
# last_modified_at: 2026-09-27T20:51:23.503Z
# last_modified_by: OpenAI / Codex / unknown / primary-agent
# dependencies: [pytest; numpy; pyflightstream]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Bind native nodal source and translated provenance to release obligations.
# revision_source: git
# GEOVERSE_HEADER_END
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
