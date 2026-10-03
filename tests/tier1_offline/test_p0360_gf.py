"""P0360-BATCH-FSI-STEADY (FR-410): plan a coupled steady row in both grouped modes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyflightstream.run.cli import main
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_p0351_batch_fsi import (
    _MATRIX_HEADER,
    BUILD,
    _build_coupled_inputs,
)


@pytest.mark.parametrize("options", [("--batch", "1"), ("--polar-sweep",)])
def test_p0360_gf_coupled_steady_stays_out(tmp_path, capsys, options):
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
    matrix = root / "gf.fs"
    row = (
        "7001 | 1 | 1 | SYNTHETIC | - | coupled | MACH:0.15, REmi:3.0, ALPHA:sweep | "
        f"0.0,2.0 | coupled_wing.obj | r340 | s340 | p340 | NONE | - | 8 | - | {BUILD} | "
        "steady | FSI: f340\n"
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
    assert "coupled" in left_out["reason"] and "RPT-150" in left_out["reason"]
    assert "RPT-150" in output
    assert list((Path(__file__).resolve().parents[2] / "reports").glob("RPT-150_*.md"))
