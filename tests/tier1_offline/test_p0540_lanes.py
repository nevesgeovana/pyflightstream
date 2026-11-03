"""Tier 1: the small items of 0.54.0 (PFS-2186.11, .16): two lanes on one workspace, low items."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace._links import is_reparse
from tests.tier1_offline.test_goal031_local_run_log import _matrix

DRIVER = Path(__file__).with_name("_p0540_lane_driver.py")
REPO = Path(__file__).parents[2]


@pytest.mark.requirement("FR-3509")
def test_p0540_finished_by_refusal_names_the_valid_values(tmp_path):
    """PFS-2186.16: the refusal says which values the option takes, not only that it is wrong."""
    from pyflightstream._errors import InputValueError
    from pyflightstream.run._plan_report import visual_inspect

    with pytest.raises(InputValueError) as caught:
        visual_inspect(tmp_path, [], finished_by="polars", name="fig")
    text = str(caught.value)
    assert "'polars'" in text and "'products'" in text and "'sims'" in text
    assert "--finished-by" in text


@pytest.mark.requirement("FR-3509")
def test_p0540_turned_about_is_in_the_script_package_all():
    """PFS-2186.16: a name the rotor workflow imports from the package is a listed public name."""
    import pyflightstream.script as script

    assert "turned_about" in script.__all__
    assert script.turned_about((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 90.0) == pytest.approx(
        (0.0, 1.0, 0.0), abs=1e-12
    )


def _lane(mode: str, workspace: CampaignWorkspace, matrix: Path, stub: Path, *sims: str):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO), str(REPO / "src")])}
    return subprocess.Popen(
        [sys.executable, str(DRIVER), mode, str(workspace.root), str(matrix), str(stub), *sims],
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


@pytest.mark.requirement("FR-3501")
def test_p0540_two_sims_lanes_run_at_once_on_one_workspace_and_one_plan(tmp_path):
    """PFS-2186.11: `run --sims A` and `run --sims B` as two processes share one workspace.

    One plan is written; each lane runs its own simulation; the records, the sweep table and
    the products of both survive; the plan is not rewritten; no input is copied.
    """
    workspace, matrix = _matrix(tmp_path)
    lines = matrix.read_text(encoding="utf-8").splitlines()
    matrix.write_text("\n".join([*lines, lines[-1].replace("5001", "5002")]) + "\n", "utf-8")
    plan = _lane("plan", workspace, matrix, tmp_path / "stub")
    assert plan.communicate()[0] is not None and plan.returncode == 0
    plan_file = workspace.root / "post" / "local" / "plan.json"
    planned = plan_file.read_bytes()
    first = _lane("run", workspace, matrix, tmp_path / "stub_a", "5001")
    second = _lane("run", workspace, matrix, tmp_path / "stub_b", "5002")
    outputs = [first.communicate()[0], second.communicate()[0]]
    assert (first.returncode, second.returncode) == (0, 0), outputs
    assert plan_file.read_bytes() == planned, "a lane rewrote the plan"
    records = CampaignWorkspace.open(workspace.root).read_manifest()
    assert sorted((record.sim_id, record.status) for record in records) == [
        ("5001", RunStatus.CONVERGED),
        ("5002", RunStatus.CONVERGED),
    ]
    with (workspace.root / "post" / "local" / "campaign_sweep.csv").open(encoding="utf-8") as fh:
        assert sorted(row["POL"] for row in csv.DictReader(fh)) == ["5001", "5002"]
    products = json.loads((workspace.root / "post" / "local" / "products.json").read_text("utf-8"))
    for pol in ("5001", "5002"):
        assert any(f"polars/P{pol}-" in name for name in products["products"]), pol
    for pol in ("5001", "5002"):
        inputs = workspace.sim_dir(pol) / "inputs"
        assert is_reparse(inputs) or inputs.is_symlink(), f"inputs of {pol} were copied"
