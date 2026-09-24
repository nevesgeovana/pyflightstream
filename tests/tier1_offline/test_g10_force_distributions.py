"""Tier 1: the force distribution is an opt-in export kind (0.27.0, G10).

The decision, held by a test on each of its links:

* ``[exports] force_distributions = true`` declares ``<point>_force_distributions.txt``
  on every run type; absent or false, nothing is declared, as for VTK and CSV;
* the script exports every surface to the point's name with the command's own
  grammar (the path on the next line, then ``SURFACES -1``);
* the file is saved once, at the end of the run: never by the per-step action
  of an unsteady row, and always by its wall-clock rescue;
* the file is collected and hashed, and its name is never claimed as the loads
  table.
"""

from __future__ import annotations

import re

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import PprocSpec, classify_outputs
from pyflightstream.cases.workflows import (
    WorkflowConventions,
    action_export_lines,
    build_script,
    workflow_registry,
)
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)
from tests.tier1_offline.test_workflows import rotor_case, steady_case, unsteady_case

NAME = "{name}_force_distributions.txt"
OPTED_IN = {"exports": {"force_distributions": True}}
MAKERS = {"steady": steady_case, "unsteady": unsteady_case, "unsteady_rotor": rotor_case}


def _declared(stem: str, unsteady: bool) -> list[str]:
    outputs = PprocSpec.model_validate(OPTED_IN).outputs(unsteady=unsteady)
    return [name.replace("{name}", stem) for name in outputs]


def test_g10_force_distributions_is_an_opt_in_export_kind():
    """Declared on both run families when asked for, and on neither by default."""
    for unsteady in (False, True):
        assert NAME in PprocSpec.model_validate(OPTED_IN).outputs(unsteady=unsteady), unsteady
        assert NAME not in PprocSpec().outputs(unsteady=unsteady), unsteady
        stated_off = PprocSpec.model_validate({"exports": {"force_distributions": False}})
        assert NAME not in stated_off.outputs(unsteady=unsteady), unsteady


@pytest.mark.parametrize("workflow", sorted(MAKERS))
def test_g10_an_opted_in_row_exports_every_surface_to_the_points_name(workflow):
    """The command's grammar, on 26.124: the path on its own line, then every surface."""
    stem = "P7001-M100AL+000"
    case = MAKERS[workflow]().model_copy(
        update={"outputs": _declared(stem, workflow.startswith("unsteady"))}
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    at = [
        index
        for index, line in enumerate(lines)
        if line == "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS"
    ]
    assert len(at) == 1, f"{workflow}: {len(at)} force-distribution exports"
    assert lines[at[0] + 1 : at[0] + 3] == [f"{stem}_force_distributions.txt", "SURFACES -1"], (
        workflow,
        lines[at[0] : at[0] + 4],
    )
    assert lines.index("START_SOLVER") < at[0] < lines.index("CLOSE_FLIGHTSTREAM"), workflow


def test_g10_classify_never_hands_the_distribution_to_the_loads_kind():
    """Its name ends in .txt, and the loads table is still the point's own .txt."""
    for names in (
        ["P_force_distributions.txt", "P.txt"],
        ["P.txt", "P_force_distributions.txt"],
    ):
        claimed = classify_outputs(names)
        assert claimed.get("loads") == "P.txt", (names, claimed)
        assert claimed.get("force_distributions") == "P_force_distributions.txt", (names, claimed)


@pytest.mark.parametrize("workflow", ["unsteady", "unsteady_rotor"])
def test_g10_the_per_step_action_carries_no_force_distribution(workflow):
    """Saved once, at the end: absent per step, present in the wall-clock rescue."""
    case = MAKERS[workflow]().model_copy(update={"outputs": _declared("P", True)})
    per_step = action_export_lines(WorkflowConventions(), case, version="26.124")
    rescue = action_export_lines(WorkflowConventions(), case, whole_run=True, version="26.124")
    assert "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS" not in per_step, per_step
    at = rescue.index("EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS")
    assert rescue[at + 1 : at + 3] == ["P_force_distributions.txt", "SURFACES -1"], rescue


def test_g10_the_distribution_file_is_collected_and_hashed(tmp_path):
    """The file lands in its point's folder and the record hashes the file on disk."""
    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="-2.0,0.0"
    )
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n\n[exports]\nforce_distributions = true\n', encoding="utf-8"
    )
    records = run_matrix(
        matrix,
        workspace,
        name="distributions",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert records, "the row ran no point"
    saved = []
    for record in records:
        assert record.status is RunStatus.CONVERGED, record.error
        for name in record.outputs:
            if not str(name).endswith("_force_distributions.txt"):
                continue
            assert re.fullmatch(
                r"datapoints/DP-(?P<tag>[^/]+)/P3207-(?P=tag)_force_distributions\.txt", name
            ), name
            on_disk = workspace.sim_dir("3207") / name
            assert record.outputs_sha256[name] == file_sha256(on_disk), name
            saved.append(name)
    assert len(saved) == 2, f"two points and the records name {saved}"
