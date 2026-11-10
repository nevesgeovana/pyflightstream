"""0.57.0 item 3 (L3, G3): the verbs of the parametric pipeline.

``run``, ``identify``, ``check`` and ``schema`` are driven through the ``pyfs-geom`` entry point
and ``mesh-generated`` through ``pyfs-workspace geometry``. The refusals and the schema need no
kernel; the pipeline run skips where the optional ``gmsh`` extra is absent.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from pyflightstream._errors import NotApplicableWarning
from pyflightstream.geometry._boundary import export_schema
from pyflightstream.run._cli_geometry import GEOMETRY_VERBS
from pyflightstream.run.geom_cli import main as geom_main
from pyflightstream.workspace.cli import main
from tests.tier1_offline._kernel_support import kernel_or_skip
from tests.tier1_offline.test_p0570_geometry_component import lifting

WING = """
[components.WING]
type = "lifting_surface"
[[components.WING.stations]]
eta = 0.0
section = {kind = "naca", code = "0012"}
[components.WING.planform]
sref_m2 = 0.24
aspect_ratio = 6.0
taper = 0.5
le_sweep_deg = 15.0
"""


#: The exit codes of a run that wrote its IGES with no check failed: accepted, or
#: incomplete while stages of the table are not built (R18-001).
WRITTEN = (0, 3)


def cli(args, capsys):
    capsys.readouterr()
    try:
        code = main(["geometry", *map(str, args)])
    except SystemExit as error:
        code = error.code
    out = capsys.readouterr()
    return code, out.out, out.err


def geom(args, capsys):
    """Run ``pyfs-geom`` and return the exit code, standard output and standard error."""
    capsys.readouterr()
    try:
        code = geom_main(list(map(str, args)))
    except SystemExit as error:
        code = error.code
    out = capsys.readouterr()
    return code, out.out, out.err


def generated(config, folder, capsys, *, until="S11"):
    """Run the pipeline to the export stage; return the code, the report, stderr and the IGES."""
    code, out, err = geom(["run", config, "--out", folder, "--until", until], capsys)
    report = record_of(out) if "{" in out else {}
    return code, report, err, report.get("outputs", {}).get("iges")


def record_of(stdout):
    """The JSON record the verb printed on standard output."""
    return json.JSONDecoder().raw_decode(stdout[stdout.index("{") :])[0]


def test_p0570_the_group_lists_mesh_generated_and_the_moved_verbs_left_it(capsys):
    assert "mesh-generated" in GEOMETRY_VERBS
    assert not {"generate", "identify", "check", "schema"} & set(GEOMETRY_VERBS)
    assert geom(["generate", "x.toml", "--out", "y"], capsys)[0] == 2


def test_p0570_the_public_stage_modules_define_what_they_export():
    """A new module is deep (arch_metrics G1), so these two hold real definitions."""
    from pyflightstream.geometry import stages
    from pyflightstream.workspace import geometry_pipeline

    assert stages.write_config.__module__ == stages.__name__
    assert stages.verify_pins.__module__ == stages.__name__
    assert geometry_pipeline.identify_lifting_surface.__module__ == geometry_pipeline.__name__
    assert geometry_pipeline.LiftingIdentification.__module__ == geometry_pipeline.__name__


def test_p0570_schema_prints_the_exported_schema_and_writes_it(tmp_path, capsys):
    target = tmp_path / "schema.json"
    code, out, _ = geom(["schema", "--out", target], capsys)
    assert code == 0
    assert record_of(out) == export_schema()
    assert json.loads(target.read_text(encoding="utf-8")) == export_schema()


def test_p0570_schema_validates_a_record_and_checks_its_pins(tmp_path, capsys):
    data = lifting()
    path = tmp_path / "wing.record.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out, _ = geom(["schema", "--validate", path], capsys)
    assert code == 0
    result = record_of(out)
    assert result["component"] == "WING_A"
    assert result["pins_checked"] is False
    code, out, _ = geom(["schema", "--validate", path, "--asset-root", tmp_path], capsys)
    assert code == 1  # the pinned files are not there
    problems = record_of(out)["pin_problems"]
    assert "original/wing.igs: missing" in problems
    (tmp_path / "original").mkdir()
    payload = b"source"
    (tmp_path / "original" / "wing.igs").write_bytes(payload)
    assert hashlib.sha256(payload).hexdigest() != data["source_iges"]["sha256"]
    code, out, _ = geom(["schema", "--validate", path, "--asset-root", tmp_path], capsys)
    assert code == 1
    assert "original/wing.igs: SHA-256 differs from the pin" in record_of(out)["pin_problems"]


def test_p0570_schema_refuses_a_record_that_breaks_the_contract(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    code, out, err = geom(["schema", "--validate", path], capsys)
    assert code == 2
    assert "component record" in err
    code, _, err = geom(["schema", "--asset-root", tmp_path], capsys)
    assert code == 2
    assert "--validate" in err


def test_p0570_check_refuses_a_missing_chord_before_any_kernel_work(tmp_path, capsys):
    code, _, err = geom(["check", tmp_path / "a.igs", tmp_path / "b.igs"], capsys)
    assert code == 2
    assert "--chord-m" in err
    code, _, err = geom(
        ["check", tmp_path / "a.igs", tmp_path / "b.igs", "--stations-m", "0", "1"], capsys
    )
    assert code == 2
    assert "both" in err


def test_r6_check_refuses_a_count_below_one_and_a_face_it_does_not_have(tmp_path, capsys):
    """R6-007: a count of 0 and a face past the end were tracebacks, -1 was reported excluded."""
    kernel_or_skip()
    config = tmp_path / "wing.toml"
    config.write_text(WING, encoding="utf-8")
    code, _, err, igs = generated(config, tmp_path / "gen", capsys)
    assert code in WRITTEN, err
    base = ["check", igs, igs, "--chord-m", 0.27, "--reverse-count", 5, "--edge-count", 11]
    code, _, err = geom([*base, "--forward-count", 0], capsys)
    assert code == 2
    assert "forward_count" in err
    for face in (999, -1):
        code, _, err = geom([*base, "--forward-count", 5, "--exclude-face", face], capsys)
        assert code == 2
        assert f"face {face} does not exist" in err


def test_r6_a_flag_the_verb_will_not_use_is_warned(tmp_path, capsys):
    """R6-010: --chord-m beside the stations and --out beside --validate were silently dropped."""
    missing = tmp_path / "none.json"
    with pytest.warns(NotApplicableWarning, match="--out"):
        assert geom(["schema", "--validate", missing, "--out", tmp_path / "s.json"], capsys)[0] == 2
    a, b = tmp_path / "a.igs", tmp_path / "b.igs"
    flags = ["--chord-m", 1.0, "--stations-m", 0, 1, "--chords-m", 1.0, 0.5]
    with pytest.warns(NotApplicableWarning, match="--chord-m"):
        assert geom(["check", a, b, *flags], capsys)[0] == 2


def test_p0570_run_refuses_a_configuration_with_an_unknown_tip_cap_kind(tmp_path, capsys):
    config = tmp_path / "bad.toml"
    config.write_text(WING + '[components.WING.cap]\ntype = "spiky"\n', encoding="utf-8")
    code, report, err, igs = generated(config, tmp_path / "bad", capsys)
    assert code == 2
    assert err.strip() and report["status"] == "refused" and igs is None
    assert not list((tmp_path / "bad").glob("*.igs"))


def test_p0570_identify_check_and_mesh_a_generated_wing_through_the_verbs(tmp_path, capsys):
    kernel_or_skip()
    pytest.importorskip("contourpy")
    config = tmp_path / "wing.toml"
    config.write_text(WING, encoding="utf-8")
    code, report, err, igs = generated(config, tmp_path / "gen", capsys)
    assert code in WRITTEN, err
    assert report["outputs"]["faces"] == {"WING": 15}

    rebuilt = tmp_path / "found.toml"
    result = tmp_path / "found.json"
    code, out, err = geom(
        [
            "identify", igs, "WING", "--stations", 41, "--grid", 97,
            "--config-out", rebuilt, "--out", result,
        ],
        capsys,
    )  # fmt: skip
    assert code == 0, err
    found = record_of(out)
    assert found["accepted"] is True
    assert found["planform"]["span_m"] == pytest.approx(1.2, abs=2e-3)
    assert json.loads(result.read_text(encoding="utf-8"))["component"] == "WING"

    # the configuration identify wrote is one the run verb reads
    code, _, err, again = generated(rebuilt, tmp_path / "again", capsys)
    assert code in WRITTEN, err

    code, out, err = geom(
        [
            "check", again, igs, "--chord-m", 0.27, "--forward-count", 9,
            "--reverse-count", 9, "--edge-count", 21,
        ],
        capsys,
    )  # fmt: skip
    assert code == 0, err
    assert record_of(out)["accepted"] is True
    code, out, _ = geom(
        [
            "check", again, igs, "--chord-m", 0.27, "--forward-count", 9,
            "--reverse-count", 9, "--edge-count", 21, "--profile", "nobody",
        ],
        capsys,
    )  # fmt: skip
    assert code == 2

    obj = tmp_path / "wing.obj"
    code, out, err = cli(["mesh-generated", config, "--obj", obj, "--component", "WING"], capsys)
    assert code == 0, err
    assert record_of(out)["obj"] == str(obj)
    assert "WING" in obj.read_text(encoding="utf-8")


def test_p0570_run_applies_the_reader_profile_gate_to_what_it_wrote(tmp_path, capsys, monkeypatch):
    """A clean file prints no finding; a planted one is a warning; a solid fails S11, no file.

    The defects are planted in the file the kernel writes, so the real gate reads a real file.
    """
    gmsh = kernel_or_skip()
    import re

    # The plant patches the kernel in this process, so S11 runs here, not in a worker (R18-003).
    monkeypatch.setenv("PYFLIGHTSTREAM_GMSH_ISOLATE", "0")
    config = tmp_path / "wing.toml"
    config.write_text(WING, encoding="utf-8")
    code, report, err, _ = generated(config, tmp_path / "clean", capsys)
    assert code in WRITTEN, err
    assert not [w for w in report["warnings"] if "reader profile" in w]

    real_write = gmsh.write

    def planting(edit):
        def write(path):
            real_write(path)
            with open(path, encoding="ascii", newline="") as handle:
                text = handle.read()
            with open(path, "w", encoding="ascii", newline="") as handle:
                handle.write(edit(text))

        return write

    def quadratic(text):
        return re.sub(r"(?m)^(\s*128,\d+,\d+,)3,3,", r"\g<1>2,2,", text, count=1)

    def solid(text):
        return re.sub(r"(?m)^( {5})128 ", r"\g<1>186 ", text, count=1)

    monkeypatch.setattr(gmsh, "write", planting(quadratic))
    code, report, err, _ = generated(config, tmp_path / "planted", capsys)
    assert code in WRITTEN, err
    assert any("reader profile, profile.degree" in w for w in report["warnings"])

    monkeypatch.setattr(gmsh, "write", planting(solid))
    code, report, _, igs = generated(config, tmp_path / "solid", capsys)
    assert code == 1
    assert (report["stage"], report["check"]) == ("S11", "profile.surfaces_only")
    assert "186" in report["message"] and igs is None
    assert not list((tmp_path / "solid").glob("*.igs"))


BSPLINE_ITEM = (
    '{eta = 0.0, section = {kind = "bspline", degree = 1, knots = [0.0, 0.0, 0.5, 1.0, 1.0], '
    "poles = [[1.0, -0.001], [0.0, 0.0], [1.0, 0.001]]}}"
)


def test_r16_001_run_refuses_a_bspline_section_item_it_cannot_build_yet(tmp_path, capsys):
    """The schema accepts ``{eta, bspline}``; the generator of this version names it, no crash."""
    config = tmp_path / "bspline.toml"
    config.write_text(
        '[components.W]\ntype = "lifting_surface"\n'
        "planform = {sref_m2 = 9.0, aspect_ratio = 9.0, taper = 0.6}\n"
        f'stations = [{BSPLINE_ITEM}, {{eta = 1.0, section = {{kind = "naca", code = "0012"}}}}]\n',
        encoding="utf-8",
    )
    code, report, err, igs = generated(config, tmp_path / "bspline", capsys)
    assert code == 2
    assert "sections.items" not in err and "stations[eta=0].section.kind" in err
    assert "bspline" in err
    assert igs is None and not list((tmp_path / "bspline").glob("*.igs"))
