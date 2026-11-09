"""0.57.0 item 3 (L3): the ``pyfs-workspace geometry`` verbs of the parametric pipeline.

``generate``, ``identify``, ``check``, ``mesh-generated`` and ``schema`` are driven through the
real entry point. The refusals and the schema need no kernel; the pipeline run skips where the
optional ``gmsh`` extra is absent.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from pyflightstream._errors import NotApplicableWarning
from pyflightstream.geometry._boundary import export_schema
from pyflightstream.run._cli_geometry import GEOMETRY_VERBS
from pyflightstream.workspace.cli import main
from tests.tier1_offline._kernel_support import kernel_or_skip
from tests.tier1_offline.test_p0570_geometry_component import lifting

WING = """
[components.WING]
type = "lifting_surface"
[components.WING.sections]
airfoils = ["NACA0012"]
[components.WING.planform]
span = 1.2
aspect_ratio = 6.0
taper = 0.5
sweep = 15.0
"""


def cli(args, capsys):
    capsys.readouterr()
    try:
        code = main(["geometry", *map(str, args)])
    except SystemExit as error:
        code = error.code
    out = capsys.readouterr()
    return code, out.out, out.err


def record_of(stdout):
    """The JSON record the verb printed on standard output."""
    return json.JSONDecoder().raw_decode(stdout[stdout.index("{") :])[0]


def test_p0570_the_group_lists_every_parametric_verb():
    assert {"generate", "identify", "check", "mesh-generated", "schema"} <= set(GEOMETRY_VERBS)


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
    code, out, _ = cli(["schema", "--out", target], capsys)
    assert code == 0
    assert record_of(out) == export_schema()
    assert json.loads(target.read_text(encoding="utf-8")) == export_schema()


def test_p0570_schema_validates_a_record_and_checks_its_pins(tmp_path, capsys):
    data = lifting()
    path = tmp_path / "wing.record.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out, _ = cli(["schema", "--validate", path], capsys)
    assert code == 0
    result = record_of(out)
    assert result["component"] == "WING_A"
    assert result["pins_checked"] is False
    code, out, _ = cli(["schema", "--validate", path, "--asset-root", tmp_path], capsys)
    assert code == 1  # the pinned files are not there
    problems = record_of(out)["pin_problems"]
    assert "original/wing.igs: missing" in problems
    (tmp_path / "original").mkdir()
    payload = b"source"
    (tmp_path / "original" / "wing.igs").write_bytes(payload)
    assert hashlib.sha256(payload).hexdigest() != data["source_iges"]["sha256"]
    code, out, _ = cli(["schema", "--validate", path, "--asset-root", tmp_path], capsys)
    assert code == 1
    assert "original/wing.igs: SHA-256 differs from the pin" in record_of(out)["pin_problems"]


def test_p0570_schema_refuses_a_record_that_breaks_the_contract(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    code, out, err = cli(["schema", "--validate", path], capsys)
    assert code == 2
    assert "component record" in err
    code, _, err = cli(["schema", "--asset-root", tmp_path], capsys)
    assert code == 2
    assert "--validate" in err


def test_p0570_check_refuses_a_missing_chord_before_any_kernel_work(tmp_path, capsys):
    code, _, err = cli(["check", tmp_path / "a.igs", tmp_path / "b.igs"], capsys)
    assert code == 2
    assert "--chord-m" in err
    code, _, err = cli(
        ["check", tmp_path / "a.igs", tmp_path / "b.igs", "--stations-m", "0", "1"], capsys
    )
    assert code == 2
    assert "both" in err


def test_r6_check_refuses_a_count_below_one_and_a_face_it_does_not_have(tmp_path, capsys):
    """R6-007: a count of 0 and a face past the end were tracebacks, -1 was reported excluded."""
    kernel_or_skip()
    config = tmp_path / "wing.toml"
    config.write_text(WING, encoding="utf-8")
    igs = tmp_path / "wing.igs"
    assert cli(["generate", config, "--out", igs], capsys)[0] == 0
    base = ["check", igs, igs, "--chord-m", 0.27, "--reverse-count", 5, "--edge-count", 11]
    code, _, err = cli([*base, "--forward-count", 0], capsys)
    assert code == 2
    assert "forward_count" in err
    for face in (999, -1):
        code, _, err = cli([*base, "--forward-count", 5, "--exclude-face", face], capsys)
        assert code == 2
        assert f"face {face} does not exist" in err


def test_r6_a_flag_the_verb_will_not_use_is_warned(tmp_path, capsys):
    """R6-010: --chord-m beside the stations and --out beside --validate were silently dropped."""
    missing = tmp_path / "none.json"
    with pytest.warns(NotApplicableWarning, match="--out"):
        assert cli(["schema", "--validate", missing, "--out", tmp_path / "s.json"], capsys)[0] == 2
    a, b = tmp_path / "a.igs", tmp_path / "b.igs"
    flags = ["--chord-m", 1.0, "--stations-m", 0, 1, "--chords-m", 1.0, 0.5]
    with pytest.warns(NotApplicableWarning, match="--chord-m"):
        assert cli(["check", a, b, *flags], capsys)[0] == 2


def test_p0570_generate_refuses_a_configuration_with_an_unknown_tip_cap_kind(tmp_path, capsys):
    config = tmp_path / "bad.toml"
    config.write_text(WING + '[components.WING.tip_cap]\nkind = "spiky"\n', encoding="utf-8")
    out = tmp_path / "bad.igs"
    code, _, err = cli(["generate", config, "--out", out], capsys)
    assert code == 2
    assert err.strip()
    assert not out.exists()


def test_p0570_identify_check_and_mesh_a_generated_wing_through_the_verbs(tmp_path, capsys):
    kernel_or_skip()
    pytest.importorskip("contourpy")
    config = tmp_path / "wing.toml"
    config.write_text(WING, encoding="utf-8")
    igs = tmp_path / "wing.igs"
    code, out, err = cli(["generate", config, "--out", igs], capsys)
    assert code == 0, err
    assert record_of(out)["faces"] == {"WING": 15}

    rebuilt = tmp_path / "found.toml"
    result = tmp_path / "found.json"
    code, out, err = cli(
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

    again = tmp_path / "again.igs"  # the configuration identify wrote is one generate reads
    code, out, err = cli(["generate", rebuilt, "--out", again], capsys)
    assert code == 0, err

    code, out, err = cli(
        [
            "check", again, igs, "--chord-m", 0.27, "--forward-count", 9,
            "--reverse-count", 9, "--edge-count", 21,
        ],
        capsys,
    )  # fmt: skip
    assert code == 0, err
    assert record_of(out)["accepted"] is True
    code, out, _ = cli(
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


def test_p0570_generate_runs_the_reader_profile_gate_on_what_it_wrote(
    tmp_path, capsys, monkeypatch
):
    """A clean file prints no finding; a planted one is a warning; a solid refuses, no file.

    The defects are planted in the file the kernel writes, so the real gate reads a real file.
    """
    gmsh = kernel_or_skip()
    import re

    config = tmp_path / "wing.toml"
    config.write_text(WING, encoding="utf-8")
    clean = tmp_path / "clean.igs"
    code, out, err = cli(["generate", config, "--out", clean], capsys)
    assert code == 0, err
    assert not [w for w in record_of(out)["warnings"] if "reader profile" in w]

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
    planted = tmp_path / "planted.igs"
    code, out, err = cli(["generate", config, "--out", planted], capsys)
    assert code == 0, err
    assert any("reader profile, profile.degree" in w for w in record_of(out)["warnings"])

    monkeypatch.setattr(gmsh, "write", planting(solid))
    refused = tmp_path / "solid.igs"
    code, _, err = cli(["generate", config, "--out", refused], capsys)
    assert code == 2
    assert "186" in err
    assert not refused.exists()
