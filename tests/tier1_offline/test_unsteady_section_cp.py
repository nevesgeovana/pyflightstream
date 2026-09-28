"""Unsteady Cp plots are final products and never repeated per STEP."""

from pyflightstream.cases import PprocSpec
from pyflightstream.cases.workflows import WorkflowConventions, action_export_lines, build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import unsteady_case


def test_sections_enable_unsteady_cp_plot_by_default():
    spec = PprocSpec.model_validate(
        {"sections": {"distributions": [{"families": "all", "planes": ["XZ"]}]}}
    )
    assert "{name}_plot_cp_sections.txt" in spec.outputs(unsteady=True)


def test_unsteady_cp_plot_is_saved_after_march_once():
    case = unsteady_case().model_copy(
        update={"outputs": ["P.txt", "P_plot_cp_sections.txt", "P_log.txt"]}
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    assert lines.count("SET_PLOT_TYPE SECTIONS_CP") == 1
    assert lines.index("START_SOLVER") < lines.index("SET_PLOT_TYPE SECTIONS_CP")
    assert lines.index("UPDATE_ALL_SURFACE_SECTIONS") < lines.index("SET_PLOT_TYPE SECTIONS_CP")


def test_cp_plot_is_in_final_rescue_and_absent_per_step():
    # GOAL033:capability_ids:items:G54
    case = unsteady_case().model_copy(update={"outputs": ["P.txt", "P_plot_cp_sections.txt"]})
    per_step = action_export_lines(WorkflowConventions(), case, version="26.124")
    final = action_export_lines(WorkflowConventions(), case, version="26.124", whole_run=True)
    assert "SET_PLOT_TYPE SECTIONS_CP" not in per_step
    assert "SET_PLOT_TYPE SECTIONS_CP" in final
