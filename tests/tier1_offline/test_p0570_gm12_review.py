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


# R9-004: a data file enters the identity by its place and its bytes, not by its path.


def _wing_of_files(first, second):
    items = [{"eta": 0.0, "file": first}, {"eta": 1.0, "file": second}]
    return {"components": {"w": {"type": "lifting_surface", "sections": {"items": items}}}}


def test_r9_004_swapped_section_files_are_two_geometries(tmp_path):
    from pyflightstream.geometry._identity import parameter_id
    from pyflightstream.geometry.config import resolve_config

    (tmp_path / "a.dat").write_text("A", encoding="ascii")
    (tmp_path / "b.dat").write_text("B", encoding="ascii")
    one = parameter_id(resolve_config(_wing_of_files("a.dat", "b.dat"), base=tmp_path))
    two = parameter_id(resolve_config(_wing_of_files("b.dat", "a.dat"), base=tmp_path))
    assert one != two


def test_r9_004_a_renamed_section_file_is_one_geometry(tmp_path):
    from pyflightstream.geometry._identity import parameter_id
    from pyflightstream.geometry.config import resolve_config

    (tmp_path / "a.dat").write_text("A", encoding="ascii")
    (tmp_path / "c.dat").write_text("A", encoding="ascii")
    (tmp_path / "b.dat").write_text("B", encoding="ascii")
    one = parameter_id(resolve_config(_wing_of_files("a.dat", "b.dat"), base=tmp_path))
    two = parameter_id(resolve_config(_wing_of_files("c.dat", "b.dat"), base=tmp_path))
    assert one == two


# R9-005: a resolved file read again measures its data files again.


def test_r9_005_a_resolved_file_follows_a_data_file_that_changed(tmp_path):
    from pyflightstream.geometry._identity import parameter_id
    from pyflightstream.geometry.config import load_config, resolve_config
    from pyflightstream.geometry.stages import write_config

    rings = tmp_path / "rings.txt"
    rings.write_text("one", encoding="ascii")
    source = {"components": {"h": {"type": "body", "rings_file": "rings.txt"}}}
    first = resolve_config(source, base=tmp_path)
    write_config(first, tmp_path / "x.toml")
    assert load_config(tmp_path / "x.toml") == first
    rings.write_text("two", encoding="ascii")
    again = load_config(tmp_path / "x.toml")
    assert parameter_id(again) != parameter_id(first)
    assert parameter_id(again) == parameter_id(resolve_config(source, base=tmp_path))
    assert any("differs" in text for text in again["warnings"])


# R9-006: an unknown key warns at every level, not only at the first.


_FOWLER = {
    "name": "f",
    "kind": "fowler",
    "eta_in": 0.1,
    "eta_out": 0.5,
    "cove": {"p3": {"eta": 0.1, "z_over_c": 0.0}},
}


@pytest.mark.parametrize(
    ("component", "word"),
    [
        ({"type": "body", "sections": [{"at": "middle", "radius": 1.0, "rad": 2.0}]}, "rad"),
        ({"type": "body", "area": 3.0}, "area"),
        (
            {
                "type": "body",
                "rear": {
                    "boat_tail": {"x_cut": 0.5, "base_height": 0.1, "angle_limit_deg": 9, "foo": 1}
                },
            },
            "foo",
        ),
        ({"type": "lifting_surface", "laws": {"radius": 1.0}}, "laws"),
        ({"type": "lifting_surface", "mesh_zone": {"ratio": 1.0}}, "mesh_zone"),
        (
            {
                "type": "lifting_surface",
                "sections": {
                    "items": [
                        {"eta": 0.0, "naca": "2412", "te": 0.01},
                        {"eta": 1.0, "naca": "0012"},
                    ]
                },
            },
            "te",
        ),
        ({"type": "lifting_surface", "sections": {"physical": {"nose_radiuss": 0.1}}}, "radiuss"),
        (
            {
                "type": "lifting_surface",
                "sections": {
                    "nacelle_bounds": [{"component": "h", "eta_in": 0.1, "eta_out": 0.2, "foo": 1}]
                },
            },
            "foo",
        ),
        (
            {
                "type": "lifting_surface",
                "distributions": {"chord": {"stations": [0.0, 1.0], "values": [1, 1], "foo": 1}},
            },
            "foo",
        ),
        (
            {
                "type": "lifting_surface",
                "control_surfaces": [{**_FOWLER, "cove": {**_FOWLER["cove"], "wall_xx": 0.7}}],
            },
            "wall_xx",
        ),
        (
            {"type": "blister", "host": "h", "stations": {"x": [0, 1]}, "profile": {"depth": 0.1}}
            | {"profile": {"depth": 0.1, "platau": 0.2}},
            "platau",
        ),
        (
            {"type": "fillet", "hosts": ["h", "w"], "mesh_zone": {"acros": 1.0}},
            "acros",
        ),
    ],
)
def test_r9_006_an_unknown_key_warns_inside_every_table(component, word):
    extra = {"w": {"type": "lifting_surface"}} if component["type"] == "fillet" else {}
    from pyflightstream.geometry.config import resolve_config

    data = {
        "aircraft": {"name": "t"},
        "components": {"c": component, "h": {"type": "body"}, **extra},
    }
    assert any(word in text for text in resolve_config(data)["warnings"])


def test_r9_006_a_misspelt_member_version_warns():
    from pyflightstream.geometry.config import resolve_config

    resolved = resolve_config(
        {
            "components": {"a": {"type": "body"}},
            "configurations": {"c": {"members": [{"component": "a", "verion": "9.9.9"}]}},
        }
    )
    assert any("verion" in text for text in resolved["warnings"])


def test_r9_006_z_c_of_the_design_reaches_the_body():
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry.config import resolve_config

    section = {
        "at": "middle",
        "shape": "superellipse",
        "width": 1.0,
        "height": 1.0,
        "z_c": 0.3,
        "n_top": 2.0,
        "n_bottom": 2.0,
    }
    resolved = resolve_config({"components": {"h": {"type": "body", "sections": [section]}}})
    plain = unpack(resolved)["components"]["h"]["sections"][0]
    assert plain["centre_height"] == 0.3 and "z_c" not in plain
    wrapped = resolved["components"]["h"]["sections"][0]["centre_height"]
    assert wrapped["source"] == "given"


# R9-007: no stage record says passed without a limit, or against its own numbers.


def _stage(**override):
    from pyflightstream.geometry._records import check_entry, stage_record

    fields = {
        "package_version": "0.57.0",
        "inputs_id": "abc",
        "parameter_id": "abc",
        "checks": [check_entry("a.b", "passed", 1.0, 2.0)],
    }
    return stage_record("S7", "split", **{**fields, **override})


def test_r9_007_a_raw_check_cannot_pass_with_no_limit():
    from pyflightstream._errors import InputValueError

    with pytest.raises(InputValueError, match="measured and limit"):
        _stage(checks=[{"id": "a.b", "status": "passed"}])


def test_r9_007_passed_above_a_maximum_is_refused_and_a_minimum_is_stated():
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry._records import check_entry

    with pytest.raises(InputValueError, match="contradicts"):
        check_entry("a.b", "passed", 5.0, 1.0)
    with pytest.raises(InputValueError, match="contradicts"):
        check_entry("a.b", "failed", 0.5, 1.0)
    assert check_entry("a.b", "passed", 5.0, 1.0, bound="min")["bound"] == "min"
    with pytest.raises(InputValueError, match="contradicts"):
        check_entry("a.b", "passed", 0.5, 1.0, bound="min")


@pytest.mark.parametrize(
    ("change", "word"),
    [
        ({"status": "passed", "checks": []}, "status"),
        ({"package_version": ""}, "package_version"),
        ({"inputs_id": None}, "inputs_id"),
    ],
)
def test_r9_007_validation_refuses_a_record_that_contradicts_itself(change, word):
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry._records import validate_stage_record

    with pytest.raises(InputValueError, match=word):
        validate_stage_record({**_stage(), **change})


def test_r9_007_a_failed_stage_cannot_be_written_as_passed(tmp_path):
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry._records import check_entry, write_record

    record = _stage(checks=[check_entry("a.b", "failed", 3.0, 2.0)])
    with pytest.raises(InputValueError, match="status"):
        write_record(tmp_path / "s.json", {**record, "status": "passed"})
    assert not (tmp_path / "s.json").exists()
