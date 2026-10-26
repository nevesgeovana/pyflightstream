"""P0410-CL-EX: the four classic cases plan through both interfaces, solver-free."""

import runpy
import shutil
from pathlib import Path

import pytest

from pyflightstream.run import LocalExecutor
from pyflightstream.run.cli import main
from pyflightstream.workspace import InputArtifactError
from pyflightstream.workspace.cli import main as workspace_main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CASES = (
    ("steady-wing-polar", 3),
    ("unsteady-isolated-propeller", 1),
    ("quasi-steady-rotor", 1),
    ("mesh-refinement-campaign", 2),
)


@pytest.mark.parametrize("name,count", CASES, ids=[f"P0460-{c[0]}" for c in CASES])
def test_p0460_examples_preview_marking_and_refuse_unmarked_plan(
    tmp_path, monkeypatch, capsys, name, count
):
    def no_solver(*args, **kwargs):
        pytest.fail("A classic example's dry path launched the solver")

    monkeypatch.setattr(LocalExecutor, "run_script", no_solver)
    workspace = tmp_path / "copied-study"
    shutil.copytree(EXAMPLES / "using-CLI" / name, workspace)
    runpy.run_path(str(EXAMPLES / "using-CLI" / "prepare.py"))["prepare"](workspace)
    for mesh in (workspace / "inputs" / "geometries").glob("*.obj"):
        assert workspace_main(["geometry", "mark-boundaries", str(mesh)]) == 0
        assert not mesh.with_suffix(".fsm").exists()
    assert main(["plan", str(workspace / "matrix.fs"), "--workspace", str(workspace)]) == 2
    captured = capsys.readouterr()
    assert "mark-boundaries" in captured.out + captured.err
    api = runpy.run_path(str(EXAMPLES / "using-API" / (name.replace("-", "_") + ".py")))
    with pytest.raises(InputArtifactError, match="mark-boundaries"):
        api["dry_run"](workspace)
