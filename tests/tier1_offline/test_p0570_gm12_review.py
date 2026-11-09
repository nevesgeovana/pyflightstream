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


# R9-003: a file in millimetres and the same file in metres resolve to the same numbers.


def _resolved_in(scale, declared):
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry.config import resolve_config

    s = scale
    data = {
        "components": {
            "w": {
                "type": "lifting_surface",
                "planform": {"span": 9 * s, "root_chord": 1.2 * s, "tip_chord": 0.8 * s},
                "distributions": {
                    "chord": {"stations": [0.0, 1.0], "values": [1.2 * s, 0.8 * s]},
                    "leading_edge_x": {"stations": [0.0, 1.0], "values": [0.0, 0.5 * s]},
                    "leading_edge_z": {"stations": [0.0, 1.0], "values": [0.0, 0.2 * s]},
                },
            },
            "h": {
                "type": "body",
                "length": 8 * s,
                "sections": [
                    {
                        "at": "middle",
                        "shape": "superellipse",
                        "width": 0.9 * s,
                        "height": 0.8 * s,
                        "centre_height": 0.1 * s,
                        "n_top": 2.0,
                        "n_bottom": 2.0,
                    }
                ],
            },
            "p": {
                "type": "blister",
                "host": "h",
                "stations": {"x": [1 * s, 2 * s]},
                "profile": {"depth": 0.1 * s, "plateau": 0.2 * s},
            },
        },
        "dominance": [{"dominant": "w", "dominated": "h", "tolerance_m": 5e-5}],
    }
    if declared:
        data["units"] = {"length": declared}
    return unpack(resolve_config(data))


def test_r9_003_every_length_converts_from_millimetres():
    metres, millimetres = _resolved_in(1.0, None), _resolved_in(1000.0, "mm")
    for name in ("w", "h", "p"):
        assert _close(millimetres["components"][name], metres["components"][name])


def test_r9_003_a_key_that_names_its_unit_is_not_converted():
    assert _resolved_in(1000.0, "mm")["dominance"][0]["tolerance_m"] == 5e-5


def test_r9_003_the_values_of_a_twist_law_convert_from_radians():
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry.config import resolve_config

    law = {"stations": [0.0, 1.0], "values": [0.1, 0.0]}
    resolved = resolve_config(
        {
            "units": {"angle": "rad"},
            "components": {"w": {"type": "lifting_surface", "distributions": {"twist": law}}},
        }
    )
    values = unpack(resolved)["components"]["w"]["distributions"]["twist"]["values"]
    assert values[0] == pytest.approx(5.729578, rel=1e-6)


def test_r9_003_a_contact_angle_in_degrees_survives_a_file_in_radians():
    from pyflightstream.geometry.config import resolve_config

    resolved = resolve_config(
        {
            "units": {"angle": "rad"},
            "components": {"a": {"type": "body"}, "b": {"type": "body"}},
            "dominance": [{"dominant": "a", "dominated": "b", "contact_deg": 10.0}],
        }
    )
    assert resolved["dominance"][0]["contact_deg"]["value"] == 10.0


def test_r9_003_a_ratio_table_and_a_section_ratio_stay_ratios():
    from pyflightstream.geometry._boundary import unit_for
    from pyflightstream.geometry.config import resolve_config

    pod = {
        "type": "blister",
        "host": "h",
        "stations": {"x": [0.1, 0.2], "of": "host_length"},
        "profile": {"depth": 0.1, "of": "host_length"},
    }
    resolved = resolve_config(
        {"units": {"length": "mm"}, "components": {"h": {"type": "body"}, "p": pod}}
    )
    assert resolved["components"]["p"]["stations"]["x"]["value"] == [0.1, 0.2]
    assert unit_for("w.sections.physical.nose_radius") == "1"
    assert unit_for("w.control_surfaces.nose.radius") == "1"
    assert unit_for("z.width") == "1"


def _close(a, b):
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float):
        return a == pytest.approx(b, rel=1e-12, abs=1e-12)
    return a == b
