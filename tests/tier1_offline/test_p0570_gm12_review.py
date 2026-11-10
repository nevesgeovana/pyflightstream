"""Review round 9 of lanes G1 and G2 of pyfs-geom (PFS-2220): one test per finding."""

from __future__ import annotations

import pytest

from tests.geom_inputs import stations as as_stations
from tests.tier1_offline._kernel_support import kernel_or_skip


def _plain(**component):
    return {"components": {"w": {"type": "lifting_surface", **component}}}


def _need_gmsh():
    kernel_or_skip()


# R9-001: the warnings of a resolved configuration reach whoever ran the verb.


def test_r9_001_generate_reports_the_key_it_skipped(tmp_path):
    _need_gmsh()
    from pyflightstream.workspace._geometry_generate import generate_iges

    record = generate_iges(
        _plain(planform={"semispan_mm": 1000.0, "sweeep": 30.0}), tmp_path / "w.igs"
    )
    assert any("sweeep" in text for text in record["warnings"])


def test_r9_001_mesh_generated_reports_the_key_it_skipped():
    _need_gmsh()
    from pyflightstream.workspace._geometry_mesh import mesh_generated

    config = {"components": {"h": {"type": "body", "lenght": 2.0}}}
    assert any(
        "lenght" in text for text in mesh_generated(config, component="h").record["warnings"]
    )


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
                "planform": {"semispan_mm": 4500.0, "root_chord_mm": 1200.0, "tip_chord_mm": 800.0},
                "distributions": {
                    "chord": {"stations": [0.0, 1.0], "values": [1.2 * s, 0.8 * s]},
                    "leading_edge_x": {"stations": [0.0, 1.0], "values": [0.0, 0.5 * s]},
                    "leading_edge_z": {"stations": [0.0, 1.0], "values": [0.0, 0.2 * s]},
                },
            },
            "h": {
                "type": "body",
                # unit-suffixed keys ignore the [units] table, so the body stays in millimetres
                "length_mm": 8000.0,
                "sections": [
                    {
                        "at": "middle",
                        "shape": "superellipse",
                        "half_width_mm": 900.0,
                        "half_height_mm": 800.0,
                        "centre_z_mm": 100.0,
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
    return {"components": {"w": {"type": "lifting_surface", "stations": as_stations(items)}}}


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
    "eta": [0.1, 0.5],
    "cove": {"p3": {"eta": 0.1, "z_over_c": 0.0}},
}


@pytest.mark.parametrize(
    ("component", "word"),
    [
        ({"type": "body", "sections": [{"at": "middle", "radius_mm": 1000.0, "rad": 2.0}]}, "rad"),
        ({"type": "body", "area": 3.0}, "area"),
        (
            {
                "type": "body",
                "tail": {
                    "boat_tail": {"x_cut": 1.0, "base_height": 0.1, "angle_limit_deg": 9, "foo": 1}
                },
            },
            "foo",
        ),
        ({"type": "lifting_surface", "laws": {"radius": 1.0}}, "laws"),
        ({"type": "lifting_surface", "mesh_zone": {"ratio": 1.0}}, "mesh_zone"),
        (
            {
                "type": "lifting_surface",
                "stations": as_stations(
                    [
                        {"eta": 0.0, "naca": "2412", "te": 0.01},
                        {"eta": 1.0, "naca": "0012"},
                    ]
                ),
            },
            "te",
        ),
        (
            {
                "type": "lifting_surface",
                "sections": {
                    "physical": {
                        "nose_radiuss": 0.1,
                        "nose_radius": 0.0158,
                        "boat_tail_deg": 7.0,
                        "thickness_at": 0.12,
                    }
                },
            },
            "radiuss",
        ),
        (
            {
                "type": "lifting_surface",
                "engine": [{"name": "h", "eta_axis": 0.15, "half_width_mm": 1.0, "foo": 1}],
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
                "control": [{**_FOWLER, "cove": {**_FOWLER["cove"], "wall_xx": 0.7}}],
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
        "half_width_mm": 1000.0,
        "half_height_mm": 1000.0,
        "centre_z_mm": 300.0,
        "n_top": 2.0,
        "n_bottom": 2.0,
    }
    resolved = resolve_config({"components": {"h": {"type": "body", "sections": [section]}}})
    plain = unpack(resolved)["components"]["h"]["sections"][0]
    assert plain["centre_height"] == pytest.approx(0.3) and "centre_z_mm" not in plain
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


# R9-008: the gate fails a file it could measure nothing in, and every arm can say no.


def _bicubic_file(path):
    from pyflightstream.workspace._gmsh import open_kernel

    net = [[(3.0 * i / 3, 3.0 * j / 3, 0.0) for j in range(4)] for i in range(4)]
    k = open_kernel("gate")
    try:
        face = k.add_bspline_surface(
            net,
            knots_u=[0.0, 1.0],
            knots_v=[0.0, 1.0],
            mult_u=[4, 4],
            mult_v=[4, 4],
            deg_u=3,
            deg_v=3,
        )
        k.export_iges({"PANEL": [face]}, path)
    finally:
        k.close()
    return path


def test_r9_008_text_that_is_not_iges_fails_the_gate(tmp_path):
    from pyflightstream.workspace._geom_gate import check_profile

    path = tmp_path / "notes.igs"
    path.write_text("not an iges file\n", encoding="ascii")
    report = check_profile(path)
    assert not report.passed and report.failed[0].check == "profile.surfaces"


def test_r9_008_bytes_that_are_not_text_are_refused(tmp_path):
    from pyflightstream._errors import InputArtifactError
    from pyflightstream.workspace._geom_gate import check_profile

    path = tmp_path / "binary.igs"
    path.write_bytes(bytes(range(128, 255)))
    with pytest.raises(InputArtifactError, match="cannot be read"):
        check_profile(path)


def test_r9_008_a_surface_no_face_names_fails_the_gate(tmp_path):
    _need_gmsh()
    from pyflightstream._textio import write_text
    from pyflightstream.workspace._geom_gate import check_profile
    from pyflightstream.workspace._iges_write import read_iges, serialize_iges

    document = read_iges(_bicubic_file(tmp_path / "c.igs"))
    document["entities"] = [e for e in document["entities"] if e["type"] == 128]
    write_text(tmp_path / "bare.igs", serialize_iges(document), encoding="ascii")
    assert {f.check for f in check_profile(tmp_path / "bare.igs").failed} >= {"profile.surfaces"}


def test_r9_008_a_written_planar_face_is_a_bounded_bspline_face(tmp_path):
    """R21-006: the writer writes a plane as a 128 with a parameter-space outer boundary.

    A 108 cap whose 142 has no BPTR curve is read by the solver as no face (G13D record), so the
    writer no longer emits one and the gate has no entity to warn about.
    """
    _need_gmsh()
    from pyflightstream.workspace._geom_gate import check_profile
    from pyflightstream.workspace._gmsh import open_kernel
    from pyflightstream.workspace._iges_write import read_iges, unbounded_faces

    k = open_kernel("gate")
    try:
        face = k.add_planar_face([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
        k.export_iges({"CAP": [face]}, tmp_path / "cap.igs")
    finally:
        k.close()
    document = read_iges(tmp_path / "cap.igs")
    types = {e["type"] for e in document["entities"]}
    assert 108 not in types and 128 in types
    assert unbounded_faces(document) == 0
    report = check_profile(tmp_path / "cap.igs")
    assert report.passed
    assert "profile.entity" not in {f.check for f in report.findings}


def test_r9_008_a_foreign_planar_face_is_warned_as_not_observed(tmp_path):
    """R21-006: the gate's entity arm still warns on a 108 in a file the package did not write."""
    _need_gmsh()
    from pyflightstream.workspace._geom_gate import check_profile
    from pyflightstream.workspace._gmsh import open_kernel
    from pyflightstream.workspace._iges_write import read_iges

    k = open_kernel("gate")
    try:
        k.add_planar_face([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)])
        k._model()  # synchronized, then the kernel's own writer, not the package's
        k._g.write(str(tmp_path / "foreign.igs"))
    finally:
        k.close()
    assert 108 in {e["type"] for e in read_iges(tmp_path / "foreign.igs")["entities"]}
    report = check_profile(tmp_path / "foreign.igs")
    assert "profile.entity" in [f.check for f in report.findings if f.severity == "warn"]


@pytest.mark.parametrize("planted", ["u_start", "u_end", "v_start", "v_end"])
def test_r9_008_the_unclamped_arm_reads_all_four_knot_ends(tmp_path, planted):
    """The G2 arm had one planted defect, at the start of u; the other three ends were unread."""
    _need_gmsh()
    from pyflightstream._textio import write_text
    from pyflightstream.workspace._geom_gate import check_profile
    from pyflightstream.workspace._iges_write import read_iges, serialize_iges

    document = read_iges(_bicubic_file(tmp_path / "c.igs"))
    surface = next(e for e in document["entities"] if e["type"] == 128)
    index = {"u_start": 11, "u_end": 16, "v_start": 19, "v_end": 24}[planted]
    surface["parameters"][index] = "0.5"
    write_text(tmp_path / "bad.igs", serialize_iges(document), encoding="ascii")
    found = check_profile(tmp_path / "bad.igs").failed
    assert [f.check for f in found] == ["profile.unclamped"]
    assert found[0].detail.startswith(planted[0])


# R9-009: a read-back through the kernel arrives in metres, whatever the file or the import says.


def test_r9_009_a_file_in_millimetres_arrives_in_metres(tmp_path):
    _need_gmsh()
    from pyflightstream.workspace._gmsh import open_kernel, session

    path = tmp_path / "mm.igs"
    with session("raw") as gmsh:
        gmsh.model.occ.addRectangle(0, 0, 0, 8000, 2000)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    named = _bicubic_file(tmp_path / "m.igs")
    k = open_kernel("read")
    try:
        first = k.import_iges(named)
        second = k.import_iges(path)
        assert first.unit == "METER" and second.unit == "MILLIMETER"
        assert k.bbox(first.faces[0])[1][0] == pytest.approx(3.0, abs=1e-5)
        assert k.bbox(second.faces[0])[1][0] == pytest.approx(8.0, abs=1e-5)
    finally:
        k.close()


def test_r9_009_a_unit_with_no_scale_is_refused_as_the_other_reader_does(tmp_path):
    _need_gmsh()
    from pyflightstream._errors import InputArtifactError
    from pyflightstream._textio import write_text
    from pyflightstream.workspace._gmsh import open_kernel
    from pyflightstream.workspace._iges_write import read_iges, serialize_iges

    document = read_iges(_bicubic_file(tmp_path / "c.igs"))
    document["global"][13:15] = ["3", "5HSPANS"]
    write_text(tmp_path / "spans.igs", serialize_iges(document), encoding="ascii")
    k = open_kernel("read")
    try:
        with pytest.raises(InputArtifactError, match="unit"):
            k.import_iges(tmp_path / "spans.igs")
    finally:
        k.close()


_OTHER_UNIT = (
    "import sys\n"
    "import gmsh\n"
    "from pyflightstream.workspace._gmsh import open_kernel\n"
    "gmsh.initialize(readConfigFiles=False)\n"
    "gmsh.option.setNumber('General.Terminal', 0)\n"
    "gmsh.option.setString('Geometry.OCCTargetUnit', 'M')\n"
    "gmsh.model.occ.addRectangle(0, 0, 0, 1, 1)\n"
    "gmsh.model.occ.synchronize()\n"
    "gmsh.write(sys.argv[1] + '.scratch.igs')\n"
    "gmsh.model.occ.importShapes(sys.argv[1])\n"
    "gmsh.finalize()\n"
    "k = open_kernel('read')\n"
    "named = k.import_iges(sys.argv[1])\n"
    "print(k.bbox(named.faces[0])[1][0])\n"
    "k.close()\n"
)


def test_r9_009_an_import_left_in_another_unit_reads_at_true_size_not_scaled_wrong(tmp_path):
    """The process-wide reader unit survives a finalize, so an unnamed import returns another unit.

    This is how a model a thousand times off is made on this machine; the reviewed code printed
    0.003 for a surface of 3 m and exited 0. ``import_iges`` names the unit on every read, so the
    surface arrives at its true 3 m; the extent check stays as the refusal of any other drift.
    """
    _need_gmsh()
    import os
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-c", _OTHER_UNIT, str(_bicubic_file(tmp_path / "c.igs"))],
        capture_output=True,
        text=True,
        timeout=120,
        env=dict(os.environ),
    )
    assert done.returncode == 0, done.stderr
    assert float(done.stdout.strip().splitlines()[-1]) == pytest.approx(3.0, abs=1e-5)


def test_r9_009_a_size_far_from_the_stated_coordinate_is_refused(tmp_path):
    _need_gmsh()
    from pyflightstream._errors import InputArtifactError
    from pyflightstream._textio import write_text
    from pyflightstream.workspace._gmsh import open_kernel
    from pyflightstream.workspace._iges_write import read_iges, serialize_iges

    document = read_iges(_bicubic_file(tmp_path / "c.igs"))
    document["global"][19] = "3000."
    write_text(tmp_path / "off.igs", serialize_iges(document), encoding="ascii")
    k = open_kernel("read")
    try:
        with pytest.raises(InputArtifactError, match="largest coordinate"):
            k.import_iges(tmp_path / "off.igs")
    finally:
        k.close()


# R9-010: a value of the wrong form is a refusal, so a loop keeps its report.


_FULL = {
    "units": {"length": "m", "angle": "deg"},
    "aircraft": {"name": "a"},
    "acceptance": {"floor_mm": 0.5},
    "reader": {"profile": "flightstream"},
    "components": {
        "W": {
            "type": "lifting_surface",
            "version": "1.0.0",
            "attach": {"parent": "H", "station": 0.1},
            "placement": {"translation": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
            "creases": [{"at": "x", "deg": 3.0}],
            "open_findings": ["a"],
            "planform": {
                "semispan_mm": 1000.0,
                "root_chord_mm": 1000.0,
                "tip_chord_mm": 500.0,
                "breaks": [0.5],
            },
            "distributions": {"chord": {"stations": [0.0, 1.0], "values": [1.0, 0.5]}},
            "stations": as_stations(
                [
                    {"eta": 0.0, "naca": "2412"},
                    {"eta": 1.0, "cst_upper": [0.1, 0.1], "cst_lower": [-0.1, -0.1], "te": 0.0},
                ]
            ),
            "engine": [{"name": "H", "eta_axis": 0.15, "half_width_mm": 50.0}],
            "cap": {"type": "flat", "shape": {"a": 1}},
            "control": [
                {
                    "name": "f",
                    "kind": "fowler",
                    "eta": [0.1, 0.5],
                    "deflection_deg": [10.0],
                    "split_around": ["H"],
                    "cove": {"p3": {"eta": 0.1, "z_over_c": 0.0}},
                    "kinematics": [
                        {
                            "deflection_deg": 10.0,
                            "pivot_x": 0.1,
                            "pivot_z": 0.1,
                            "gap_pct": 1.0,
                            "overlap_pct": 1.0,
                        }
                    ],
                }
            ],
        },
        "H": {
            "type": "body",
            "length_mm": 3000.0,
            "tail": {"boat_tail": {"x_cut": 1.0, "base_height": 0.1, "angle_limit_deg": 25.0}},
            "sections": [{"at": "middle", "shape": "circle", "radius_mm": 300.0}],
        },
        "F": {"type": "fillet", "hosts": ["W", "H"], "patches": 5, "laws": {"radius": 1.0}},
        "B": {
            "type": "blister",
            "host": "H",
            "stations": {"x": [0.0, 1.0]},
            "profile": {"depth": 1},
        },
        "P": {"type": "propeller"},
        "Z": {"type": "wing_fuselage_fairing", "hosts": ["H", "W"]},
    },
    "dominance": [{"dominant": "W", "dominated": ["H"], "operation": "cut"}],
    "variants": {"clean": [], "cs": ["W.f"]},
    "configurations": {
        "c": {"members": ["H", {"component": "W", "version": "1.0.0"}], "variants": ["clean"]},
        "d": {"members": ["F"], "extends": "c"},
    },
}


def _places(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield (*path, key)
            yield from _places(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield (*path, index)
            yield from _places(value, (*path, index))


def test_r9_010_every_wrong_form_is_a_refusal_or_is_read():
    import copy

    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    resolve_config(copy.deepcopy(_FULL))
    crashes = []
    for place in _places(_FULL):
        for wrong in (3, "x", [1], {"a": 1}, True, None):
            data = copy.deepcopy(_FULL)
            node = data
            for key in place[:-1]:
                node = node[key]
            node[place[-1]] = wrong
            try:
                resolve_config(data)
            except InputValueError:
                pass
            except Exception as error:
                crashes.append((place, wrong, type(error).__name__))
    assert crashes == []


def test_r9_010_the_wrong_form_names_the_component():
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    with pytest.raises(InputValueError, match="components.w"):
        resolve_config({"components": {"w": {"type": "lifting_surface", "creases": 3}}})


def test_r9_010_fairing_hosts_in_the_wrong_order_are_refused_by_name():
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    with pytest.raises(InputValueError, match="hosts"):
        resolve_config(
            {
                "components": {
                    "b": {"type": "body"},
                    "w": {"type": "lifting_surface"},
                    "z": {"type": "wing_fuselage_fairing", "hosts": ["w", "b"]},
                }
            }
        )


# R9-011: a data file that holds geometry and is missing refuses; a missing original warns.


@pytest.mark.parametrize(
    "piece",
    [
        {"type": "blister", "host": "h", "sections_file": "nope.csv"}
        | {"stations": {"x": [0.0, 1.0]}, "profile": {"depth": 0.1}},
        {"type": "lifting_surface"}
        | {
            "stations": as_stations(
                [{"eta": 0.0, "file": "nope.dat"}, {"eta": 1.0, "naca": "0012"}]
            )
        },
    ],
)
def test_r9_011_a_missing_geometry_file_is_refused_by_name(piece, tmp_path):
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    with pytest.raises(InputValueError, match="file not found"):
        resolve_config({"components": {"h": {"type": "body"}, "p": piece}}, base=tmp_path)


def test_r9_011_a_missing_original_warns_and_is_not_refused(tmp_path):
    from pyflightstream.geometry.config import resolve_config

    resolved = resolve_config(
        {"components": {"h": {"type": "body", "original": "nope.igs#h"}}}, base=tmp_path
    )
    assert any("h.original" in text for text in resolved["warnings"])


# R9-012: a reference to no component warns and is skipped, as section C says.


def _reference_case():
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry.config import resolve_config

    resolved = resolve_config(
        {
            "components": {
                "h": {"type": "body"},
                "w": {
                    "type": "lifting_surface",
                    "engine": [
                        {"name": "pod", "eta_axis": 0.15, "half_width_mm": 1.0},
                        {"name": "h", "eta_axis": 0.35, "half_width_mm": 1.0},
                    ],
                    "control": [{"name": "f", "eta": [0.1, 0.5], "split_around": ["pod", "h"]}],
                },
            },
            "variants": {"cs": ["w.f", "w.nothing"]},
        }
    )
    return resolved["warnings"], unpack(resolved)


def test_r9_012_a_bound_on_no_component_warns_and_is_skipped():
    warnings, plain = _reference_case()
    # R21-009: the warning names the user's engine key, not the resolver's nacelle_bounds
    assert any(text.startswith("w.engine.name: 'pod'") for text in warnings)
    bounds = plain["components"]["w"]["sections"]["nacelle_bounds"]
    assert [b["component"] for b in bounds] == ["h"]


def test_r9_012_a_split_around_no_component_warns_and_is_skipped():
    warnings, plain = _reference_case()
    assert any("split_around" in text and "pod" in text for text in warnings)
    assert plain["components"]["w"]["control_surfaces"][0]["split_around"] == ["h"]


def test_r9_012_a_variant_entry_it_says_it_skipped_is_gone():
    warnings, plain = _reference_case()
    assert any("w.nothing" in text for text in warnings)
    assert plain["variants"]["cs"] == ["w.f"]


# R9-013: section C.7 refuses control surfaces that overlap.


def test_r9_013_two_surfaces_that_overlap_in_span_are_refused():
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    surfaces = [
        {"name": "f", "eta": [0.1, 0.5]},
        {"name": "a", "eta": [0.4, 0.9]},
    ]
    with pytest.raises(InputValueError, match="f and a overlap"):
        resolve_config(_plain(control=surfaces))
    surfaces[1]["eta"] = [0.5, 0.9]
    resolve_config(_plain(control=surfaces))


# R9-014: the laws of a fillet.


def test_r9_014_a_known_law_is_silent_and_an_unknown_one_is_named_and_gone():
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry.config import resolve_config

    resolved = resolve_config(
        {
            "aircraft": {"name": "t"},
            "components": {
                "h": {"type": "body"},
                "w": {"type": "lifting_surface"},
                "f": {"type": "fillet", "hosts": ["h", "w"], "laws": {"radius": 1.0, "foo": 2.0}},
            },
        }
    )
    assert resolved["warnings"] == ["f.laws.foo: unknown key, skipped"]
    assert unpack(resolved)["components"]["f"]["laws"] == {"radius": 1.0}


# R9-015: one geometry has one parameter_id.


def _id_of(data):
    from pyflightstream.geometry._identity import parameter_id
    from pyflightstream.geometry.config import resolve_config

    return parameter_id(resolve_config(data))


def _two_bodies(**top):
    return {"components": {"a": {"type": "body"}, "b": {"type": "body"}}, **top}


def test_r9_015_a_negative_zero_is_zero():
    def at(y):
        return {"components": {"a": {"type": "body", "placement": {"translation": [0.0, y, 0.0]}}}}

    assert _id_of(at(0.0)) == _id_of(at(-0.0))


def test_r9_015_the_order_of_members_and_of_names_carries_no_meaning():
    assert _id_of(_two_bodies(configurations={"c": ["a", "b"]})) == _id_of(
        _two_bodies(configurations={"c": ["b", "a"]})
    )
    c = {"type": "body"}

    def rows(names):
        return {
            "components": {"a": c, "b": c, "c": c},
            "dominance": [{"dominant": names, "dominated": "c"}],
        }

    assert _id_of(rows(["a", "b"])) == _id_of(rows(["b", "a"]))


def test_r9_015_an_open_finding_is_a_note_not_a_parameter():
    def body(findings):
        return {"components": {"a": {"type": "body", "open_findings": findings}}}

    assert _id_of(body(["x"])) == _id_of(body([]))


def test_r9_015_a_different_set_of_members_is_a_different_id():
    assert _id_of(_two_bodies(configurations={"c": ["a"]})) != _id_of(
        _two_bodies(configurations={"c": ["a", "b"]})
    )


# R9-016: section C.2 states the default version, and C.5's example relies on it.


def test_r9_016_the_default_component_version_is_the_design_s():
    from pyflightstream.geometry._boundary import unpack
    from pyflightstream.geometry.config import resolve_config

    plain = unpack(resolve_config({"components": {"a": {"type": "body"}}}))
    assert plain["components"]["a"]["version"] == "1.0.0"


# R9-017: a designation the generator cannot build is refused where it is read.


def test_r9_017_a_six_series_number_does_not_pass_as_five_digits():
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    items = [{"eta": 0.0, "naca": "64215"}, {"eta": 1.0, "naca": "0012"}]
    with pytest.raises(InputValueError, match="NACA64215"):
        resolve_config(_plain(stations=as_stations(items)))
    resolve_config(_plain(stations=as_stations([{"eta": 0.0, "naca": "23012"}, items[1]])))


# R9-018: two statements of the sections, one of which is ignored.


def test_r9_018_airfoils_beside_stations_are_refused_as_renamed():
    from pyflightstream._errors import InputValueError
    from pyflightstream.geometry.config import resolve_config

    # the old sections.airfoils name is refused whatever else is given, so it cannot be ignored
    with pytest.raises(InputValueError, match="sections.airfoils: renamed to stations"):
        resolve_config(
            _plain(
                sections={"airfoils": ["NACA2412", "NACA2412"]},
                stations=as_stations([{"eta": 0.0, "naca": "0012"}, {"eta": 1.0, "naca": "0012"}]),
            )
        )


# R9-020: the unavailable kernel on a real load failure, not on an error put in its place.


def test_r9_020_a_library_that_cannot_load_gives_the_named_error(tmp_path):
    import os
    import subprocess
    import sys

    (tmp_path / "gmsh.py").write_text(
        "import ctypes\nctypes.CDLL('libpyfs_not_there_r9.so')\n", encoding="ascii"
    )
    probe = (
        "from pyflightstream.extras import KernelUnavailableError\n"
        "from pyflightstream.workspace._gmsh import gmsh_module\n"
        "try:\n"
        "    gmsh_module('the test')\n"
        "except KernelUnavailableError as error:\n"
        "    print('NAMED', error.reason)\n"
    )
    import pyflightstream

    source = os.path.dirname(os.path.dirname(pyflightstream.__file__))
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": os.pathsep.join((str(tmp_path), source))},
    )
    assert done.returncode == 0, done.stderr[-400:]
    assert done.stdout.startswith("NAMED") and "libpyfs_not_there_r9" in done.stdout
