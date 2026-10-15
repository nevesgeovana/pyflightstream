"""P0410-CL-EX: the four classic cases plan through both interfaces, solver-free."""

import json
import runpy
import shutil
from pathlib import Path

import pytest

from pyflightstream.run import LocalExecutor, PlanStatus
from pyflightstream.run.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CASES = (
    ("steady-wing-polar", 3),
    ("unsteady-isolated-propeller", 1),
    ("quasi-steady-rotor", 1),
    ("mesh-refinement-campaign", 2),
)


@pytest.mark.parametrize("name,count", CASES, ids=[f"P0410-{c[0]}" for c in CASES])
def test_p0410_cl_ex_cli_and_api_plan_without_solver(tmp_path, monkeypatch, name, count):
    def no_solver(*args, **kwargs):
        pytest.fail("A classic example's dry path launched the solver")

    monkeypatch.setattr(LocalExecutor, "run_script", no_solver)
    workspace = tmp_path / "copied-study"
    shutil.copytree(EXAMPLES / "using-CLI" / name, workspace)
    runpy.run_path(str(EXAMPLES / "using-CLI" / "prepare.py"))["prepare"](workspace)
    assert main(["plan", str(workspace / "matrix.fs"), "--workspace", str(workspace)]) == 0
    cli_plan = json.loads((workspace / "post" / "matrix" / "plan.json").read_text())
    # Importing an API example must not parse pytest's arguments or execute a study.
    api = runpy.run_path(str(EXAMPLES / "using-API" / (name.replace("-", "_") + ".py")))
    plan = api["dry_run"](workspace)
    assert plan.campaign == cli_plan["campaign"]
    assert plan.campaign_name_from == cli_plan["campaign_name_from"]
    assert [point.run_id for point in plan.points] == [
        point["run_id"] for point in cli_plan["points"]
    ]
    assert len(plan.points) == count
    assert all(point.status == PlanStatus.READY for point in plan.points), plan.summary()
