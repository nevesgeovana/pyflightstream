# GEOVERSE_HEADER
# file_version: 1.0.5
# file_role: paired-native-surface-average-tests
# last_modified_at: 2026-09-27T20:59:34.971Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.post.surfaces, test_native_nodal_surface]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""Nodal strength follows its own time history, never the final export."""

import numpy as np
import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post.surfaces import average_surface_exports
from pyflightstream.results.surface import REFERENCE_FRAME, write_vtk_surface
from tests.tier1_offline.test_native_nodal_surface import _native, _vtk


def _pair(tmp_path):
    vtk = {
        step: write_vtk_surface(tmp_path / f"p_iteration={step}.vtk", _vtk(), title="test")
        for step in (6, 7, 8)
    }
    native = {
        step: _native(
            tmp_path / f"n_iteration={step}.dat",
            strength=" ".join(str(v * step) for v in (30, 10, 40, 20)),
        )
        for step in (6, 7, 8)
    }
    return vtk, native


def test_average_uses_each_matching_native_step_and_both_hashes(tmp_path):
    # GOAL033:post:checks:averages
    # GOAL033:capability_ids:items:G55
    vtk, native = _pair(tmp_path)
    result = average_surface_exports(
        vtk, window=(7, 8), frame=REFERENCE_FRAME, native_exports=native
    )
    np.testing.assert_array_equal(
        result.surface.point_data["Singularity_strength"], np.array([10, 20, 30, 40]) * 7.5
    )
    np.testing.assert_array_equal(result.surface.cell_data["Cp_reference"], [-0.2])
    assert set(result.inputs) == {
        p.as_posix() for step in (7, 8) for p in (vtk[step], native[step])
    }
    assert result.steps == (7, 8)


def test_missing_native_step_does_not_borrow_final_strength(tmp_path):
    vtk, native = _pair(tmp_path)
    del native[7]
    _native(tmp_path / "n.dat", strength="300 100 400 200")
    with pytest.raises(ProductError, match="native.*7|7.*native"):
        average_surface_exports(vtk, window=(7, 8), frame=REFERENCE_FRAME, native_exports=native)


def test_native_topology_must_match_at_every_selected_step(tmp_path):
    vtk, native = _pair(tmp_path)
    _native(native[7], edges="2 1 1 4 4 3 3 2")
    with pytest.raises(ProductError, match="topology"):
        average_surface_exports(vtk, window=(7, 8), frame=REFERENCE_FRAME, native_exports=native)


def test_moving_coordinate_scalars_keep_last_step_geometry(tmp_path):
    from dataclasses import replace

    exports = {}
    for step in (7, 8):
        surface = _vtk()
        points = surface.points + np.array([0, step, 0])
        surface = replace(
            surface,
            points=points,
            point_data={a: points[:, i] for i, a in enumerate(("X", "Y", "Z"))},
        )
        exports[step] = write_vtk_surface(tmp_path / f"s{step}.vtk", surface, title="moving")
    result = average_surface_exports(exports, window=(7, 8), frame=REFERENCE_FRAME)
    np.testing.assert_array_equal(result.surface.point_data["Y"], result.surface.points[:, 1])


def test_walltime_average_refuses_unfinalized_native_mean(tmp_path):
    from types import SimpleNamespace

    from pyflightstream.post.surfaces import write_point_surface_average

    record = SimpleNamespace(
        surface_average_window={"iterations": [2, 3]},
        surface_translations=[],
        point_name="P",
        run_id="run/P",
        stopped_at={"step": 16},
    )
    skipped = {}
    files, entries = write_point_surface_average(
        tmp_path,
        sim_dir=tmp_path,
        record=record,
        out=tmp_path / "out",
        target=lambda p: p,
        skipped=skipped,
    )
    assert files == [] and entries == {}
    assert "WALLTIME" in skipped["surfaces/P_time_average.dat"]
    assert "native average" in skipped["surfaces/P_time_average.dat"]
    assert not (tmp_path / "out").exists()
