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


def _row(sim_id: str, geometry: Path | None, run_type: str = "unsteady", **variables):
    """A real row of the plan: a continuation when it names what it continues."""
    from pyflightstream.cases.workflows import WORKFLOW_KEY
    from tests.tier1_offline.test_restart_continuation import _continuing_case

    case = _continuing_case("{ADDITIONAL_ITERS=120}", **variables)
    return case.model_copy(
        update={
            "sim_id": sim_id,
            "geometry": None if geometry is None else str(geometry),
            "variables": {**case.variables, WORKFLOW_KEY: run_type},
        }
    )


def _warned(rows) -> list[str]:
    from pyflightstream.cases.workflows import WORKFLOW_KEY
    from pyflightstream.workspace._geometry_clean import warn_saved_actions_of_unsteady_rows

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warn_saved_actions_of_unsteady_rows(rows, WORKFLOW_KEY)
    return [str(item.message) for item in caught]


def test_fr313_one_warning_per_geometry_names_every_row_that_opens_it(tmp_path):
    """R2: two rows on one dirty file give ONE warning naming both; a clean file gives none."""
    requirement = "FR-313"
    dirty = _saved_simulation(tmp_path / "shared.fsm", ACTIONS)
    clean = _saved_simulation(tmp_path / "clean.fsm", [])
    said = _warned(
        [_row("7001", dirty), _row("7002", dirty, "unsteady_rotor"), _row("7003", clean)]
    )
    assert len(said) == 1, (requirement, said)
    assert said[0].startswith("row(s) 7001, 7002: shared.fsm carries 2"), said
    assert "7003" not in said[0]


def test_fr313_a_continuation_of_an_unsteady_row_is_read(tmp_path):
    """R1: a row that continues a saved unsteady run opens its geometry too."""
    from pyflightstream.cases.workflows import RESTART_FROM_VARIABLE, RESTART_ITERATIONS_VARIABLE

    requirement = "FR-313"
    dirty = _saved_simulation(tmp_path / "wing.fsm", ACTIONS)
    row = _row(
        "9001", dirty, **{RESTART_FROM_VARIABLE: "P9001-AL+000", RESTART_ITERATIONS_VARIABLE: "120"}
    )
    assert row.variables[RESTART_FROM_VARIABLE], "the row is a continuation"
    said = _warned([row])
    assert len(said) == 1 and "row(s) 9001" in said[0], (requirement, said)


@pytest.mark.parametrize("run_type", ["steady", "polar", ""])
def test_fr313_a_row_that_is_not_unsteady_is_not_read_the_control(run_type, tmp_path):
    """R5 and the control of R1: the same dirty file under a row with no time loop warns nothing."""
    requirement = "FR-313"
    dirty = _saved_simulation(tmp_path / "wing.fsm", ACTIONS)
    assert _warned([_row("7001", dirty)]) != [], "the control: the unsteady row warns"
    assert _warned([_row("7001", dirty, run_type)]) == [], (requirement, run_type)


def test_fr313_a_raw_mesh_or_a_row_with_no_geometry_is_not_read(tmp_path):
    """R5: only a saved simulation carries actions; a raw mesh is never opened for them."""
    requirement = "FR-313"
    mesh = tmp_path / "wing.stl"
    mesh.write_text("solid wing\nendsolid wing\n", encoding="utf-8")
    assert _warned([_row("7001", mesh), _row("7002", None)]) == [], requirement
