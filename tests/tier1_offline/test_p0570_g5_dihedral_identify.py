"""0.57.0 item PFS-2221: a wing with dihedral identified and rebuilt through the verbs.

The cuts of identify are normal to the tilted span axis, while the end planes of a mirrored
wing (the symmetry plane and the tip) are vertical. The configuration written by identify must
therefore place the root on the symmetry plane and the tip on the end plane, not at the
extreme of the span coordinate of the skin.
"""

from __future__ import annotations

import json
import math

import pytest

from pyflightstream.run.geom_cli import main
from tests.tier1_offline._kernel_support import kernel_or_skip

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
dihedral = {dihedral}
"""


def cli(args, capsys):
    capsys.readouterr()
    try:
        code = main(list(map(str, args)))
    except SystemExit as error:
        code = error.code
    out = capsys.readouterr()
    return code, out.out, out.err


def generate(config, folder, capsys):
    """Run the pipeline to the export stage and return the IGES it wrote."""
    code, out, err = cli(["run", config, "--out", folder, "--until", "S11"], capsys)
    assert code == 0, err
    return record_of(out)["outputs"]["iges"]


def record_of(stdout):
    return json.JSONDecoder().raw_decode(stdout[stdout.index("{") :])[0]


@pytest.mark.parametrize("dihedral", [6.0, -6.0])
def test_p0570_pfs2221_identify_places_the_root_and_tip_on_the_end_planes(
    tmp_path, capsys, dihedral
):
    kernel_or_skip()
    pytest.importorskip("contourpy")
    config = tmp_path / "wing.toml"
    config.write_text(WING.format(dihedral=dihedral), encoding="utf-8")
    igs = generate(config, tmp_path / "gen", capsys)
    rebuilt = tmp_path / "found.toml"
    result = tmp_path / "found.json"
    code, _, err = cli(
        ["identify", igs, "WING", "--stations", 41, "--grid", 97,
         "--config-out", rebuilt, "--out", result],
        capsys,
    )  # fmt: skip
    assert code == 0, err
    import tomllib

    comp = tomllib.loads(rebuilt.read_text(encoding="utf-8"))["components"]["WING"]
    place = comp["placement"]["translation"]["value"]
    plan = comp["planform"]
    assert place[1] == pytest.approx(0.0, abs=2e-4)  # root on the symmetry plane y = 0
    assert plan["span"]["value"] == pytest.approx(1.2, abs=3e-4)  # tip on y = span / 2
    assert plan["dihedral"]["value"] == pytest.approx(dihedral, abs=0.01)
    assert place[2] == pytest.approx(0.0, abs=2e-4)
    assert math.isfinite(plan["root_chord"]["value"])
    assert plan["root_chord"]["value"] == pytest.approx(0.266667, abs=1e-4)


def test_p0570_pfs2221_the_rebuilt_dihedral_wing_passes_check(tmp_path, capsys):
    kernel_or_skip()
    pytest.importorskip("contourpy")
    config = tmp_path / "wing.toml"
    config.write_text(WING.format(dihedral=6.0), encoding="utf-8")
    igs = generate(config, tmp_path / "gen", capsys)
    rebuilt = tmp_path / "found.toml"
    code, _, err = cli(
        ["identify", igs, "WING", "--stations", 41, "--grid", 97, "--config-out", rebuilt], capsys
    )
    assert code == 0, err
    again = generate(rebuilt, tmp_path / "again", capsys)
    code, out, err = cli(
        ["check", again, igs, "--chord-m", 0.27, "--forward-count", 21,
         "--reverse-count", 21, "--edge-count", 21],
        capsys,
    )  # fmt: skip
    assert record_of(out)["accepted"] is True, out[-600:]
    assert code == 0, err


def test_r14_001_a_rounded_tip_cap_does_not_move_the_tip_of_a_dihedral_wing(tmp_path, capsys):
    """The extreme sample of a rounded cap is not the end plane: the span stays the wing's."""
    kernel_or_skip()
    pytest.importorskip("contourpy")
    config = tmp_path / "wing.toml"
    text = WING.format(dihedral=6.0) + '[components.WING.tip_cap]\nkind = "rounded"\n'
    config.write_text(text, encoding="utf-8")
    igs = generate(config, tmp_path / "gen", capsys)
    rebuilt = tmp_path / "found.toml"
    code, _, err = cli(
        ["identify", igs, "WING", "--stations", 41, "--grid", 97, "--config-out", rebuilt], capsys
    )
    assert code == 0, err
    import tomllib

    comp = tomllib.loads(rebuilt.read_text(encoding="utf-8"))["components"]["WING"]
    assert comp["placement"]["translation"]["value"][1] == pytest.approx(0.0, abs=2e-4)
    assert comp["planform"]["span"]["value"] == pytest.approx(1.2, abs=4e-3)
