"""Matrix selections determine build refusals and solver window mode."""

import pytest

from pyflightstream.run import matrix
from tests.tier1_offline.test_matrix_cli import WORKFLOW_FIXTURE, make_planned_workspace

pytestmark = pytest.mark.requirement("P0400-LAST6-SELECTION")


@pytest.mark.parametrize("selection", [{"sims": ["7002"]}, {"points": ["7002_1"]}])
def test_p0400_last6_unselected_silent_row_does_not_refuse_plan(tmp_path, selection):
    workspace = make_planned_workspace(tmp_path)
    path = tmp_path / "selected.fs"
    path.write_text(
        WORKFLOW_FIXTURE.read_text(encoding="utf-8").replace("| 26.120   |", "|          |", 1),
        encoding="utf-8",
    )
    plan = matrix.plan_matrix(path, workspace, name="selected", recipes={}, **selection)
    assert {point.sim_id for point in plan.points} == {"7002"}, "P0400-LAST6-SELECT-BUILD"


def test_p0400_last6_hidden_is_decided_by_selected_cases(tmp_path, monkeypatch):
    from pyflightstream.cases import Campaign, SimCase, SweepAxis
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.matrix import ResolvedMatrix

    case = SimCase(
        sim_id="7002",
        aircraft="Rig",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"matrix_hidden": True},
    )
    resolved = ResolvedMatrix(
        campaign=Campaign(name="selected", fs_version="26.124", fs_exe="solver.exe", sims=[case])
    )
    monkeypatch.setattr(matrix, "on_a_cluster", lambda: False)
    seen = []
    monkeypatch.setattr(
        matrix, "LocalExecutor", lambda exe, **kwargs: seen.append(kwargs) or object()
    )
    path = tmp_path / "matrix.fs"
    lines = WORKFLOW_FIXTURE.read_text(encoding="utf-8").splitlines()
    cells = lines[2].split("|")
    cells[1] = " 0 "
    lines[2] = "|".join(cells)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    matrix._campaign_executor(CampaignWorkspace.init(tmp_path / "camp"), resolved, path)
    assert seen[0]["hidden"] is True, "P0400-LAST6-SELECT-HIDDEN"
