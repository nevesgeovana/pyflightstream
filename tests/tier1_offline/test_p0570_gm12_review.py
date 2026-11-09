"""Review round 9 of lanes G1 and G2 of pyfs-geom (PFS-2220): one test per finding."""

from __future__ import annotations

import pytest


def _plain(**component):
    return {"components": {"w": {"type": "lifting_surface", **component}}}


def _need_gmsh():
    try:
        import gmsh  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("gmsh is not usable here")


# R9-001: the warnings of a resolved configuration reach whoever ran the verb.


def test_r9_001_generate_reports_the_key_it_skipped(tmp_path):
    _need_gmsh()
    from pyflightstream.workspace._geometry_generate import generate_iges

    record = generate_iges(_plain(planform={"span": 2.0, "sweeep": 30.0}), tmp_path / "w.igs")
    assert any("sweeep" in text for text in record["warnings"])


def test_r9_001_mesh_generated_reports_the_key_it_skipped(monkeypatch):
    _need_gmsh()
    from pyflightstream.workspace import _geometry_mesh

    monkeypatch.setattr(_geometry_mesh, "_mesh_component", lambda *a: (None, {}))
    monkeypatch.setattr(_geometry_mesh, "load_mesh_controls", lambda c: {"lifting_surface": {}})
    monkeypatch.setattr(_geometry_mesh, "add_occ_patch", lambda *a: 1, raising=False)
    config = _plain(planform={"span": 2.0, "sweeep": 30.0})
    result = _geometry_mesh.mesh_generated(config, component="w")
    assert any("sweeep" in text for text in result.record["warnings"])


# R9-002: a misspelt key of the units table leaves the file in metres, so it must warn.


def test_r9_002_a_misspelt_units_key_warns():
    from pyflightstream.geometry.config import resolve_config

    resolved = resolve_config({"units": {"lenght": "mm"}, "components": {"a": {"type": "body"}}})
    assert any("units.lenght" in text for text in resolved["warnings"])
