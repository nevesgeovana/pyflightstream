"""Tier 1: `{mach}` in a naming template is the Mach number of the POINT (0.24.0).

TEMPLATE-MACH-STUCK. The run loop handed the naming template the Mach number
of the SIMULATION-level case, and the template never looked at the point, so
on a Mach sweep a custom template `{mach}_{point}` rendered the row's first
Mach number on every point: `0.1_M100...` and then `0.1_M200...`, a file name
contradicting itself. The matrix default (`{polar}`) and the library default
(`{point}`) render no `{mach}` and were never affected.

The expected names are written from the two conventions involved: `{mach}` is a
float rendered compactly (`0.1`, `0.2`), and the point name writes Mach x 1000
in three digits (`M100`, `M200`).
"""

from __future__ import annotations

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.naming import NamingTemplate
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import RECIPES


def _script_names(tmp_path, *, condition: str, values: str, template: str) -> list[str]:
    """Plan a one-row matrix under ``template`` and return the script name of each point."""
    workspace, matrix = _matrix(
        tmp_path,
        condition=condition,
        values=values,
        workflow="unsteady",
        cell="DELTA_TIME: 0.01 / TIME_ITERATIONS: 8",
    )
    workspace = CampaignWorkspace(workspace.root, naming=NamingTemplate(point_name=template))
    plan = plan_matrix(
        matrix,
        workspace,
        name="named",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )
    assert not plan.blocked, plan.summary()
    return [str(point.script_name) for point in plan.points]


def test_goal028_rename_template_mach_is_the_points_own_on_a_mach_sweep(tmp_path):
    """Two points of a Mach sweep, two Mach numbers in their names."""
    names = _script_names(
        tmp_path,
        condition="MACH:sweep, REmi:2.3, ALPHA:0.0",
        values="0.1,0.2",
        template="{mach}_{point}",
    )

    assert names == ["0.1_M100RE230AL+000.txt", "0.2_M200RE230AL+000.txt"], names


def test_goal028_rename_template_mach_is_the_rows_on_a_sweep_of_something_else(tmp_path):
    """THE CONTROL: where the point carries no Mach number, `{mach}` is the row's."""
    names = _script_names(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="-2.0,0.0",
        template="{mach}_{point}",
    )

    assert names == ["0.2_M200RE230AL-020.txt", "0.2_M200RE230AL+000.txt"], names


def test_goal028_rename_template_mach_the_template_itself_reads_the_point():
    """The rule sits in the template, so every caller of it gets the point's Mach number."""
    template = NamingTemplate(point_name="{mach}_{point}")

    rendered = template.render_point(
        campaign="c", sim="1", point={"MACH": 0.2}, mach=0.1, name="M200"
    )
    output = template.render_output(
        "loads_{mach}.txt", campaign="c", sim="1", point={"MACH": 0.2}, mach=0.1
    )

    assert rendered == "0.2_M200", rendered
    assert output == "loads_0.2.txt", output
