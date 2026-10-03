"""P0360-BATCH-FSI-STEADY (FR-410): refuse coupled steady run types in grouped modes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.run.cli import main
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.fsi_setup import FSI_TEMPLATE
from tests.tier1_offline.test_p0351_batch_fsi import (
    _MATRIX_HEADER,
    BUILD,
    _build_coupled_inputs,
)


def _coupled_sector_inputs(root):
    """Give the quasi-steady arm one synthetic periodic blade and its structure."""
    inputs = root / "inputs"
    geometry = inputs / "geometries/coupled_wing"
    (geometry / "coupled_wing.obj").write_text(
        "o Blade1\nv 0 0 .1\nv 0 .02 .1\nv 0 0 .5\nf 1 2 3\n", encoding="utf-8"
    )
    (geometry / "coupled_wing.boundaries.toml").write_text(
        'boundaries = ["Blade1"]\n[import]\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n',
        encoding="utf-8",
    )
    (inputs / "references/r340.toml").write_text(
        "area_m2 = 1.0\nchord_m = 0.04\nspan_m = 1.0\n"
        '[rotors.PROP]\nalias = "PROP"\naxis = "X"\ndiameter_m = 1.0\n'
        'families_blades = ["Blade1", "Blade2", "Blade3"]\n'
        '[rotors.PROP.blade1]\nazimuth_deg = 0.0\nzero = "Z"\n',
        encoding="utf-8",
    )
    (inputs / "pproc/p340.toml").write_text(
        "[sections]\ncount = 5\ninclude_symmetry = false\n"
        '[[sections.distributions]]\nfamilies = ["Blade1"]\nframe = "SMRP"\n'
        'planes = ["XY"]\n',
        encoding="utf-8",
    )
    (inputs / "fsi/f340.toml").write_text(
        FSI_TEMPLATE.replace("blade_count = 2", "blade_count = 1"), encoding="utf-8"
    )


@pytest.mark.parametrize("options", [("--batch", "1"), ("--polar-sweep",)])
@pytest.mark.parametrize("run_type", ["steady", "qsteady_rotor"])
def test_p0360_gf_coupled_steady_stays_out(tmp_path, capsys, options, run_type):
    """P0360-BATCH-FSI-STEADY (FR-410): both modes cite the measured exclusion."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    root = workspace.root
    _build_coupled_inputs(root)
    # A single initialization keeps the independent double-initialization exclusion out.
    sidecar = root / "inputs/geometries/coupled_wing/coupled_wing.boundaries.toml"
    sidecar.write_text(
        'boundaries = ["Wing"]\n[import]\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n',
        encoding="utf-8",
    )
    symmetry, variables = "NONE", "FSI: f340"
    if run_type == "qsteady_rotor":
        _coupled_sector_inputs(root)
        symmetry, variables = "PERIODIC", "FSI: f340 / RPM: 1200 / PERIODIC_COPIES: 3"
    matrix = root / "gf.fs"
    row = (
        "7001 | 1 | 1 | SYNTHETIC | - | coupled | MACH:sweep, REmi:3.0, ALPHA:0.0 | "
        f"0.15,0.2 | coupled_wing.obj | r340 | s340 | p340 | {symmetry} | - | 8 | - | {BUILD} | "
        f"{run_type} | {variables}\n"
    )
    matrix.write_text(_MATRIX_HEADER + row, encoding="utf-8")
    assert main(["plan", str(matrix), "--workspace", str(root), *options]) == 0
    output = capsys.readouterr().out
    payload = json.loads((workspace.plan_dir("gf") / "plan.json").read_text("utf-8"))
    grouping = payload["grouping"]
    assert grouping["batches"] == []
    assert len(grouping["left_out"]) == 1
    left_out = grouping["left_out"][0]
    assert left_out["sim"] == "7001"
    assert left_out["reason"] == (
        "a coupled row on steady or qsteady_rotor: its coupling loop starts only after the "
        "script ends, and on 26.124 the next point of the job crashed the instance (RPT-150)"
    )
    assert "RPT-150" in output
    assert list((Path(__file__).resolve().parents[2] / "reports").glob("RPT-150_*.md"))
