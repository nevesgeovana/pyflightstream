"""FR-313: the plan warns, never refuses, when an unsteady row's geometry carries saved actions.

Parametrized over the two unsteady run types and over a clean, a dirty and an
unreadable geometry: the plan is written and returns the same rows and the
same exit status in every case, the warning names the row, the geometry, each
saved action and the ``--clean`` command where the file carries actions, says
unreadable where it cannot be read, and is absent where it is clean.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.cli import main
from pyflightstream.run.matrix import plan_matrix
from tests.tier1_offline.test_fsm_saved_actions import ACTIONS, CLOCK, _saved_simulation
from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row, _workspace

GEOMETRIES = {
    "clean": {"actions": []},
    "dirty": {"actions": ACTIONS},
    "unreadable": {"actions": ACTIONS, "count": 3},
}
ROTOR_VARIABLES = "VELOCITY: 30.0 / RPM: 1200 / ROTOR_AXIS: X / BLADES: 4 / DELTA_TIME: 0.0001"
UNSTEADY_VARIABLES = "VELOCITY: 30.0 / DELTA_TIME: 0.01 / TIME_ITERATIONS: 40 / LAST_ITERS_AVG: 4"


def _planned(tmp_path: Path, run_type: str, geometry: str):
    workspace = _workspace(tmp_path)
    matrix = _rotor_row(tmp_path, sweep="0.0")
    if run_type == "unsteady":
        text = matrix.read_text(encoding="utf-8")
        start = text.index(ROTOR_VARIABLES)
        text = text[:start] + UNSTEADY_VARIABLES + "\n"
        text = text.replace("| unsteady_rotor |", "| unsteady       |")
        matrix.write_text(text, encoding="utf-8")
    (staged,) = (workspace.inputs_dir / "geometries").rglob("wing_clean.fsm")
    _saved_simulation(staged, **GEOMETRIES[geometry])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = plan_matrix(
            matrix,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
        )
    said = [str(item.message) for item in caught]
    return workspace, matrix, plan, said, staged


@pytest.mark.parametrize("geometry", sorted(GEOMETRIES))
@pytest.mark.parametrize("run_type", ["unsteady", "unsteady_rotor"])
def test_fr313_the_plan_warns_and_writes_the_same_plan(run_type, geometry, tmp_path):
    requirement = "FR-313"
    _, _, plan, said, staged = _planned(tmp_path / geometry, run_type, geometry)
    _, _, control, _, _ = _planned(tmp_path / "control", run_type, "clean")
    rows = [(point.sim_id, point.run_id, point.status) for point in plan.points]
    assert rows == [(p.sim_id, p.run_id, p.status) for p in control.points], requirement
    assert plan.plan_file is not None and plan.plan_file.is_file(), "the plan is written"
    about = [text for text in said if staged.name in text and "action" in text]
    if geometry == "clean":
        assert about == [], (requirement, said)
        return
    assert len(about) == 1, (requirement, said)
    text = about[0]
    assert "row(s) 7001" in text, text
    if geometry == "dirty":
        assert "pfs_walltime_clock [COMMAND_LINE]" in text and CLOCK in text, text
        assert "pfs_walltime_stop [SCRIPT]" in text, text
        assert f"pyfs-matrix inventory {staged} --clean" in text, text
    else:
        assert "cannot be read" in text, text


@pytest.mark.parametrize("geometry", sorted(GEOMETRIES))
def test_fr313_the_command_exits_as_the_clean_plan_does(geometry, tmp_path, capsys):
    """R4: never a refusal on this account; the exit status is the clean geometry's."""
    requirement = "FR-313"
    codes = {}
    for index, case in enumerate(("clean", geometry)):
        workspace, matrix, _, _, _ = _planned(tmp_path / f"{index}-{case}", "unsteady", case)
        codes[case] = main(["plan", str(matrix), "--workspace", str(workspace.root)])
    err = capsys.readouterr().err
    assert codes[geometry] == codes["clean"] != 2, (requirement, codes, err)
