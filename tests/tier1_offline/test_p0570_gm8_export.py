"""PFS-2220 export checks and distance regression, from the lane acceptance.

Reproduction: measure a point on a unit plane whose v domain is [0, 10000].
Its distance must stay below 1e-9 of the model size near a parameter bound.
"""

import json
from dataclasses import replace

import numpy as np
import pytest

from pyflightstream.workspace._geom_gate import _Surface
from pyflightstream.workspace._iges_write import read_iges
from tests.tier1_offline._kernel_support import kernel_or_skip


@pytest.mark.parametrize("u", [0.001, 0.999], ids=["P0570-low-bound", "P0570-high-bound"])
def test_p0570_anisotropic_surface_distance(u):
    values = [128, 1, 1, 1, 1, 0, 0, 1, 0, 0]
    values += [0, 0, 1, 1, 0, 0, 10000, 10000]
    values += [1, 1, 1, 1]
    values += [0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]
    values += [0, 1, 0, 10000]
    surface = _Surface([str(v) for v in values])
    point = np.array([u, 0.12345, 0.0])
    assert surface.distance(point) < 1e-9 * np.sqrt(2)


@pytest.mark.parametrize("preference", [1, 3], ids=["P0570-default", "P0570-either"])
def test_p0570_written_boundaries_carry_both_curves(tmp_path, preference):
    kernel_or_skip()
    from pyflightstream.workspace._gmsh import open_kernel

    kernel = open_kernel("export regression")
    try:
        face = kernel.add_planar_face(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
        )
        path = tmp_path / "piece.igs"
        if preference == 3:
            with pytest.warns(UserWarning, match="IGES.PREF: 3 .*PREF 1 is written instead"):
                kernel.export_iges({"plate": [face]}, path, preference=preference)
        else:
            kernel.export_iges({"plate": [face]}, path, preference=preference)
        document = read_iges(path)
        by_id = {e["id"]: e for e in document["entities"]}
        boundaries = [e for e in document["entities"] if e["type"] == 142]
        assert boundaries
        for boundary in boundaries:
            values = boundary["parameters"]
            assert values[5] == "1"
            assert int(values[3]) in by_id
            assert int(values[4]) in by_id
            assert by_id[int(values[3])]["d1"][8][4:6] == "05"
        read = kernel.inspect_file(path, None)
        assert len(read.areas) == 1
        assert read.areas[0] == pytest.approx(1.0, rel=1e-6)
    finally:
        kernel.close()


@pytest.mark.parametrize("gap", [0.0, 0.00013], ids=["P0570-control", "P0570-cap-edge-gap"])
def test_p0570_cap_boundary_check_reaches_run_log(tmp_path, monkeypatch, gap):
    from pyflightstream.geometry import resolve_config, stages
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry._caps import lifting_model
    from pyflightstream.workspace.geometry_pipeline import run_geometry

    raw = {"components": {"main": {"type": "lifting_surface", "cap": {"type": "rounded"}}}}
    component = unpack(resolve_config(raw))["components"]["main"]
    model = lifting_model(component)
    corner = model.caps["tip_cap_corner"]
    controls = np.array(corner.controls, copy=True)
    # Move the whole side except its skin-rim endpoint: the rim-only check misses this gap.
    controls[0, 1:, 2] += gap
    caps = {**model.caps, "tip_cap_corner": replace(corner, controls=controls)}
    model = replace(model, caps=caps)
    monkeypatch.setattr(stages, "lifting_model", lambda *args, **kwargs: model, raising=False)
    report = run_geometry(raw, out=tmp_path, until="S8")
    if gap:
        assert report["status"] == "failed"
        assert (report["stage"], report["check"]) == ("S8", "closure.cap_edge_gap")
    else:
        checks = json.loads((tmp_path / "S8.json").read_text(encoding="utf-8"))["checks"]
        found = [c for c in checks if c["id"] == "closure.cap_edge_gap"]
        assert found and found[0]["status"] == "passed"
    assert "closure.cap_edge_gap" in (tmp_path / "geom-run.log").read_text(encoding="utf-8")
