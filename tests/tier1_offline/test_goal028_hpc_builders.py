"""Two builder findings on the cluster's run path.

EXPORT-LOG-FLAG-BYPASS
    A profile stating ``export_log = false`` governs EVERY branch that emits
    ``EXPORT_LOG``. The flag was read only where a row names its log through
    ``LOG_OUTPUT``; a row whose outputs carry a ``_log.txt`` name, which is
    what every matrix row gets by default, still emitted the command, and the
    machine that states the flag aborts at it after the queue wait.
CONTINUATION-SECTIONS-BLOCKED
    A row whose post-processing artifact declares section distributions can be
    continued. The distributions are in the saved simulation the continuation
    reopens, so its script emits none of them, and does not refuse for want of
    the frames they were measured in.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    EXPORT_LOG_VARIABLE,
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    build_script,
)
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row, _workspace
from tests.tier1_offline.test_goal021_swept_row import _run, _submitting
from tests.tier1_offline.test_matrix_run import HPC_PROFILE
from tests.tier1_offline.test_workflows import (
    _wb_geometry,
    _with_pproc,
    rendered,
    unsteady_case,
)

LOG_TABLE = '\n[log]\nexport_log = false\nnative_log = "FTS{sim}.l*"\n'


# ------------------------------------------------------ EXPORT-LOG-FLAG-BYPASS


def _case(export_log: str | None, *, names_its_log: bool) -> SimCase:
    variables = {"VELOCITY": "68.058"}
    if names_its_log:
        variables["LOG_OUTPUT"] = "2"
    if export_log is not None:
        variables[EXPORT_LOG_VARIABLE] = export_log
    return SimCase(
        sim_id="9001",
        aircraft="WB",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        geometry="10_WING.fsm",
        outputs=["P9001-AL+000.txt", "P9001-AL+000_log.txt"],
        variables=variables,
    )


def _verbs(case: SimCase) -> list[str]:
    script = Script(version="26.123")
    build_script(case, script)
    return script.render().splitlines()


@pytest.mark.parametrize("names_its_log", [False, True])
def test_export_log_false_removes_the_command_on_either_route(names_its_log):
    lines = _verbs(_case("false", names_its_log=names_its_log))
    assert "EXPORT_LOG" not in lines, "the machine that aborts at EXPORT_LOG was handed one"
    # Nothing else moved: the loads export is still there.
    assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET" in lines


@pytest.mark.parametrize("names_its_log", [False, True])
def test_a_case_that_states_nothing_still_exports_its_log(names_its_log):
    assert "EXPORT_LOG" in _verbs(_case(None, names_its_log=names_its_log))


def test_a_matrix_row_submitted_through_such_a_profile_carries_no_export_log(tmp_path):
    workspace = _workspace(tmp_path)
    records = _run(
        workspace,
        _rotor_row(tmp_path, sweep="0.0"),
        _submitting(workspace, text=HPC_PROFILE + LOG_TABLE),
    )
    assert [record.status for record in records] == [RunStatus.SUBMITTED], [
        (record.run_id, record.status, record.error) for record in records
    ]
    script = workspace.sim_dir("7001") / records[0].script_path
    lines = script.read_text(encoding="utf-8").splitlines()
    assert "EXPORT_LOG" not in lines
    # The row still declares its log: it is collected with it and judged by it.
    declared = records[0].submission["declared_outputs"]
    assert any(str(name).endswith("_log.txt") for name in declared), declared


# ----------------------------------------------- CONTINUATION-SECTIONS-BLOCKED

DISTRIBUTION_VERB = "NEW_SURFACE_SECTION_DISTRIBUTION"


def _sections_case(tmp_path) -> SimCase:
    # The wing-body geometry carries the families W and B, and the artifact
    # declares section distributions over them.
    case = _with_pproc(unsteady_case(), _wb_geometry(tmp_path))
    assert case.pproc is not None and case.pproc.sections.distributions
    return case


def test_the_full_march_of_a_sections_row_declares_its_distributions(tmp_path):
    # The control: this is a case the builder does emit distributions for.
    assert DISTRIBUTION_VERB in rendered(_sections_case(tmp_path), "26.123").splitlines()


def test_a_row_whose_artifact_declares_sections_can_be_continued(tmp_path):
    case = _sections_case(tmp_path)
    saved = str(tmp_path / "archive" / "stopped.fsm")
    continuing = case.model_copy(
        update={
            "variables": {
                **case.variables,
                # What the row states, and the two facts the run layer resolves
                # for it from the record of the stopped run.
                "RESTART": "{FINISH_PENDING}",
                RESTART_FROM_VARIABLE: saved,
                RESTART_ITERATIONS_VARIABLE: "230",
            }
        }
    )
    try:
        lines = rendered(continuing, "26.123").splitlines()
    except CampaignConfigError as refusal:
        pytest.fail(f"the continuation of a sections row was refused: {refusal}")
    # It reopens the saved state with its initialisation, which carries the
    # distributions ...
    assert lines[lines.index("OPEN") + 1] == saved
    assert lines[lines.index("OPEN") + 2] == "LOAD_SOLVER_INITIALIZATION ENABLE"
    # ... so it creates none of them again ...
    assert DISTRIBUTION_VERB not in lines
    # ... and marches only what is still owed.
    assert any("230" in line for line in lines)
