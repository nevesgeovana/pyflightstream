"""Tier 1, 0.40.0: a built body is accepted, and the plan reads its record (FR-473).

P0400-GEOM-PLAN (PFS-2081.41). The body is built through the build's own
code with a runner standing in for the solver; the plan's judgement is the
function the matrix binding calls for every geometry a row names, and one test
drives it through ``resolve_matrix`` to show the binding reaches it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.workspace._geometry_build import apply_geometry_build, plan_geometry_build
from pyflightstream.workspace._geometry_record import judge_the_row_geometry
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import (
    MESH_INSTRUCTION,
    geometry,
    runner,
    workspace,
)

INSTRUCTION = MESH_INSTRUCTION.replace('outputs = ["fsm", "obj"]', 'outputs = ["fsm"]')


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A built, unaccepted wing: (root, folder, the built FSM)."""
    import pyflightstream.cases._geometry_emit as geometry_emit

    monkeypatch.setattr(geometry_emit, "_awaiting_evidence", lambda script, commands: ())
    root = workspace(tmp_path)
    folder = geometry(root, "wing", INSTRUCTION)
    apply_geometry_build(plan_geometry_build(folder), runner=runner())
    return root, folder, folder / "wing.fsm"


def _judge(fsm: Path, fs_build: str = "26.125") -> list[str]:
    with pytest.warns() as caught:
        judge_the_row_geometry(fsm, "9401", fs_build=fs_build, mesh_import=None)
        import warnings

        warnings.warn("control", PyflightstreamWarning, stacklevel=1)
    return [str(item.message) for item in caught if str(item.message) != "control"]


@pytest.mark.requirement("FR-473")
def test_p0400_geom_plan_an_unaccepted_body_is_warned_until_accepted(built, monkeypatch, capsys):
    """P0400-GEOM-PLAN (PFS-2081.41): R1 and R3, accept silences the warning."""
    root, folder, fsm = built
    assert any("never accepted" in text and "geometry accept wing" in text for text in _judge(fsm))
    monkeypatch.chdir(root)
    assert main(["geometry", "accept", "wing"]) == 0
    record = json.loads((folder / "wing.build.json").read_text(encoding="utf-8"))
    assert record["inspected"]["at"] and record["inspected"]["by"]
    assert _judge(fsm) == []


@pytest.mark.requirement("FR-473")
def test_p0400_geom_plan_accept_refuses_a_geometry_never_built(built, monkeypatch, capsys):
    """P0400-GEOM-PLAN (PFS-2081.41): R1, a name with no record, exit 2."""
    root, _, _ = built
    monkeypatch.chdir(root)
    assert main(["geometry", "accept", "nothing"]) == 2
    assert "Nothing was written" in capsys.readouterr().err


@pytest.mark.requirement("FR-473")
@pytest.mark.parametrize("changed", ["wing.geometry.toml", "src.obj"])
def test_p0400_geom_plan_refuses_a_body_whose_inputs_changed(built, changed):
    """P0400-GEOM-PLAN (PFS-2081.41): R2, the instruction or the source edited after the build."""
    _, folder, fsm = built
    with (folder / changed).open("a", encoding="utf-8") as handle:
        handle.write("\n# edited\n")
    with pytest.raises(
        InputArtifactError, match=f"{changed}.*Rebuild it with `pyfs-workspace geometry build wing"
    ):
        judge_the_row_geometry(fsm, "9401", fs_build="26.125", mesh_import=None)


@pytest.mark.requirement("FR-473")
def test_p0400_geom_plan_warns_on_a_resaved_body_a_failed_audit_and_another_build(built):
    """P0400-GEOM-PLAN (PFS-2081.41): R3, each warning names the row and the geometry."""
    _, folder, fsm = built
    record_path = folder / "wing.build.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["inspected"] = {"at": "now", "by": "tester"}
    record["audit"] = {
        "file": "wing.audit.json",
        "passed": False,
        "failed": ["G1 faces_of_zero_area"],
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with fsm.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    texts = _judge(fsm, fs_build="26.124")
    assert any("saved again" in text for text in texts)
    assert any("audit failed: G1 faces_of_zero_area" in text for text in texts)
    assert any("built on FS_BUILD 26.125" in text and "26.124" in text for text in texts)
    assert all("POL 9401" in text for text in texts)


@pytest.mark.requirement("FR-473")
def test_p0400_geom_plan_a_body_without_a_record_is_planned_as_before(tmp_path):
    """P0400-GEOM-PLAN (PFS-2081.41): R4, nothing is said of a GUI-saved simulation."""
    import warnings

    fsm = tmp_path / "gui.fsm"
    fsm.write_text("saved\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        judge_the_row_geometry(fsm, "1", fs_build="26.125", mesh_import=None)


@pytest.mark.requirement("FR-473")
def test_p0400_geom_plan_the_matrix_binding_reaches_the_judgement(built):
    """P0400-GEOM-PLAN (PFS-2081.41): the binding refuses a stale body."""
    from pyflightstream.workspace.matrix import resolve_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

    root, folder, fsm = built
    workspace_ = make_library(
        root.parent / "lib", register_build=("26.125", Path(sys.executable).as_posix())
    )
    target = workspace_.inputs_dir / "geometries" / "wing"
    import shutil

    shutil.copytree(folder, target)
    (target / "src.obj").write_text("changed\n", encoding="utf-8")
    row = (
        "9401 | TestGeom | GEOM | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
        "| 003 | 26.125 |  0 | 1 | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / GEOMETRY: wing.fsm"
    )
    matrix = write_matrix(root.parent / "m.fs", [row])
    with pytest.raises(InputArtifactError, match="src.obj"):
        resolve_matrix(matrix, workspace_, name="matrix", fs_version="26.125", recipes=RECIPES)
