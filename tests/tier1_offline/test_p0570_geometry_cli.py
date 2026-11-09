"""0.57.0 item 3 (L3): the ``pyfs-workspace geometry`` verbs of the parametric pipeline.

``generate``, ``identify``, ``check``, ``mesh-generated`` and ``schema`` are driven through the
real entry point. The refusals and the schema need no kernel; the pipeline run skips where the
optional ``gmsh`` extra is absent.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from pyflightstream.geometry._boundary import export_schema
from pyflightstream.run._cli_geometry import GEOMETRY_VERBS
from pyflightstream.workspace.cli import main
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


def test_p0570_generate_refuses_a_configuration_with_an_unknown_parameter(tmp_path, capsys):
    config = tmp_path / "bad.toml"
    config.write_text(WING + "[components.WING.planform.nonsense]\nvalue = 1\n", encoding="utf-8")
    out = tmp_path / "bad.igs"
    code, _, err = cli(["generate", config, "--out", out], capsys)
    assert code == 2
    assert err.strip()
    assert not out.exists()


def test_p0570_identify_check_and_mesh_a_generated_wing_through_the_verbs(tmp_path, capsys):
    pytest.importorskip("gmsh", reason="needs the optional extra: gmsh")
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
