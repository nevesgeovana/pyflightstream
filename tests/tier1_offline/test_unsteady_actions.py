"""Tier 1: exports that begin after a threshold the row states (PFS-2031.18).

Her design of 2026-09-08, drawn in the 0.13.0 scope and written down as
GeoversePlan design 67: a row of an unsteady run type states
``EXPORT_UNSTEADY_AFTER_REV`` or ``EXPORT_UNSTEADY_AFTER_ITER``, the run
type registers two unsteady solver actions, a ``COMMAND_LINE`` running a
counter program the run layer writes and a ``SCRIPT`` pointing at a file
that program rewrites, and from the step the count reaches the threshold
the file carries the export of every per-step output the row's pproc set
declares. The solver stamps each export with the iteration (RPT-041).

What this module drives: the refusals of the two keys, the two
registration lines in creation order, the program run four times by the
real interpreter in a temporary folder, and the run record after a stub
solver that runs the registered command line itself. No solver runs; what
the solver does with the two actions is measured by the tier-3 row 6002
of ``tests/tier3_licensed/matriz_actions.fs``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import WORKFLOW_KEY, build_script, workflow_registry
from pyflightstream.run import run_campaign
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "workspace-and-workflows.md"

REV = "EXPORT_UNSTEADY_AFTER_REV"
ITER = "EXPORT_UNSTEADY_AFTER_ITER"
PROGRAM = "actions/pfs_unsteady_actions.py"
SCRIPT_FILE = "actions/pfs_unsteady_exports.txt"
COUNT_FILE = "actions/pfs_unsteady_actions.count"


def steady_case(**variables) -> SimCase:
    return SimCase(
        sim_id="7002",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=["loads_a+00.0.txt"],
        variables={WORKFLOW_KEY: "steady", "VELOCITY": "30.0", **variables},
        point={"alpha": 0.0},
    )


# --- the refusals ----------------------------------------------------------------


def test_a_row_stating_both_thresholds_is_refused_naming_both():
    case = unsteady_case(**{REV: "1", ITER: "4"})
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, Script("26.123"))
    message = str(refused.value)
    assert REV in message and ITER in message, message
    assert "7003" in message


@pytest.mark.parametrize("key", [REV, ITER])
def test_a_steady_row_stating_a_threshold_is_refused(key):
    case = steady_case(**{key: "2"})
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, Script("26.123"))
    message = str(refused.value)
    assert key in message, message
    assert "time loop" in message, message


def test_an_unsteady_row_stating_revolutions_is_refused_naming_the_rotor_clock():
    case = unsteady_case(**{REV: "1"})
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, Script("26.123"))
    message = str(refused.value)
    assert REV in message and ITER in message, message
    assert "rotor" in message, message


def test_a_threshold_beyond_the_run_is_refused_naming_both_numbers():
    case = unsteady_case(**{ITER: "481"})
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, Script("26.123"))
    message = str(refused.value)
    assert "481" in message and "480" in message, message


# --- the two lines, in order, and the program's constants ---------------------------


def _action_lines(rendered: str) -> list[tuple[str, str]]:
    lines = rendered.splitlines()
    return [
        (line, lines[index + 1])
        for index, line in enumerate(lines)
        if line.startswith("SET_NEW_UNSTEADY_SOLVER_ACTION")
    ]


def test_a_rotor_row_stating_revolutions_registers_the_two_actions_in_order():
    case = rotor_case(**{REV: "1"})
    script = Script("26.123")
    build_script(case, script)
    rendered = script.render()
    actions = _action_lines(rendered)
    assert [head.split()[1] for head, _ in actions] == ["COMMAND_LINE", "SCRIPT"], rendered
    command_line, script_path = actions[0][1], actions[1][1]
    assert command_line == f'"{sys.executable}" "{PROGRAM}"', command_line
    assert script_path == SCRIPT_FILE
    # Registered before the solver is initialized, as the probe row registered them.
    assert rendered.index("SET_NEW_UNSTEADY_SOLVER_ACTION") < rendered.index("INITIALIZE_SOLVER")
    # The SCRIPT file is parked EMPTY for the run layer to write.
    assert script.pending_action_scripts == {SCRIPT_FILE: ""}


def test_a_row_stating_no_threshold_registers_no_action():
    script = Script("26.123")
    build_script(rotor_case(), script)
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" not in script.render()
    assert script.pending_action_scripts == {}


def test_the_program_the_run_layer_writes_carries_the_step_degrees_and_the_threshold():
    from pyflightstream.cases.workflows import unsteady_export_threshold
    from pyflightstream.run._actions_counter import render_program

    # rotor_case: 1200 rev/min and a step of 0.0001 s, so 0.72 degrees per
    # step and 500 steps per revolution; one revolution is step 500 of 720.
    threshold = unsteady_export_threshold(rotor_case(**{REV: "1"}))
    assert threshold is not None
    assert threshold.stated_form == "revolutions"
    assert threshold.stated_value == 1.0
    assert threshold.step_deg == pytest.approx(0.72)
    assert threshold.rpm == 1200.0
    assert threshold.first_step == 500
    program = render_program(threshold, interpreter=sys.executable)
    assert "STEP_DEG = 0.72" in program, program
    assert "THRESHOLD_FORM = 'revolutions'" in program, program
    assert "THRESHOLD = 1.0" in program, program
    assert "RPM = 1200.0" in program, program
    assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nloads_a+00.0.txt" in threshold.exports
    # The exports are the per-step kinds of the row's outputs and nothing else:
    # this row declares a loads table only, so the file carries one export.
    assert threshold.exports.count("EXPORT_") == 1, threshold.exports


def test_the_per_step_exports_are_read_from_the_export_set_and_update_before_exporting():
    """A row declaring the whole set exports five kinds per step: the saved
    simulation, the plots file and the log are the whole run and stay at the
    end; sections, sectional loads and probes are updated before they are
    exported, which is the rule the end-of-run block already follows."""
    from pyflightstream.cases import default_outputs
    from pyflightstream.cases.workflows import unsteady_export_threshold

    names = [name.format(name="p") for name in default_outputs(unsteady=True)]
    case = unsteady_case(**{ITER: "2"}).model_copy(update={"outputs": names})
    threshold = unsteady_export_threshold(case)
    assert threshold is not None
    lines = threshold.exports.splitlines()
    verbs = [line for line in lines if line and not line.startswith("p")]
    assert verbs == [
        "UPDATE_ALL_SURFACE_SECTIONS",
        "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS",
        "UPDATE_PROBE_POINTS",
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        "EXPORT_SOLVER_ANALYSIS_TECPLOT",
        "EXPORT_ALL_SURFACE_SECTIONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
        "EXPORT_PROBE_POINTS",
    ], lines
    assert "SAVEAS" not in threshold.exports
    assert "EXPORT_LOG" not in threshold.exports
    assert "UNSTEADY_SOLVER_EXPORT_PLOTS" not in threshold.exports


# --- the program itself, driven by the real interpreter ---------------------------


def test_the_program_leaves_the_script_empty_until_the_count_reaches_the_threshold(tmp_path):
    from pyflightstream.cases.workflows import unsteady_export_threshold
    from pyflightstream.run._actions_counter import render_program

    case = unsteady_case(**{ITER: "4", "TIME_ITERATIONS": "8", "DELTA_TIME": "0.01"})
    threshold = unsteady_export_threshold(case)
    assert threshold is not None
    program = tmp_path / PROGRAM
    program.parent.mkdir(parents=True)
    program.write_text(render_program(threshold, interpreter=sys.executable), encoding="utf-8")
    script_file = tmp_path / SCRIPT_FILE
    script_file.write_text("", encoding="utf-8")
    count_file = tmp_path / COUNT_FILE

    seen = []
    for _ in range(4):
        # Run exactly as the solver runs a COMMAND_LINE action on 26.123:
        # from the simulation folder, with no arguments (RPT-041).
        run = subprocess.run(
            [sys.executable, PROGRAM],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            # The solver hands the action no environment of its own (RPT-041
            # fact 4), and the spawn ratchet asks every test to say which
            # environment a child gets: the ambient one, deliberately.
            env=os.environ.copy(),
        )
        assert run.returncode == 0, run.stderr
        seen.append(script_file.read_text(encoding="utf-8"))
    assert seen[:3] == ["", "", ""], seen
    assert seen[3] == threshold.exports, seen[3]
    state = json.loads(count_file.read_text(encoding="utf-8"))
    assert state["count"] == 4
    assert state["exporting"] is True


# --- the record after a stub run ----------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# The stub solver honors the loads export of the main script, then runs the
# registered COMMAND_LINE action four times from the simulation folder,
# exactly the line the script carries, which is how the solver runs it.
RUNS_THE_COUNTER_FOUR_TIMES = (
    "import pathlib, subprocess, sys; "
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
    "[pathlib.Path(lines[i + 1]).write_text('LOADS') "
    "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']; "
    "command = [lines[i + 1] for i, line in enumerate(lines) "
    "if line.startswith('SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE')][0]; "
    "[subprocess.run(command, shell=True, check=True) for _ in range(4)]"
)


def _threshold_campaign(tmp_path, **variables) -> Campaign:
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_{point}.txt"],
        variables={
            WORKFLOW_KEY: "unsteady",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.01",
            "TIME_ITERATIONS": "4",
            **variables,
        },
    )
    return Campaign(name="camp", fs_version="26.123", fs_exe=sys.executable, sims=[case])


def test_the_record_after_a_stub_run_carries_the_count_and_the_two_staged_files(tmp_path):
    campaign = _threshold_campaign(tmp_path, **{ITER: "4"})
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(RUNS_THE_COUNTER_FOUR_TIMES),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED, record.error
    sim_dir = workspace.sim_dir("9001")
    assert record.action_program == PROGRAM
    assert record.action_script == SCRIPT_FILE
    assert record.action_count == 4
    assert record.inputs_sha256[PROGRAM] == _sha256(sim_dir / PROGRAM)
    # The hash of the SCRIPT file is the hash of the EMPTY file the run
    # layer wrote, and the file the solver left is the rewritten one.
    assert record.inputs_sha256[SCRIPT_FILE] == hashlib.sha256(b"").hexdigest()
    left = (sim_dir / SCRIPT_FILE).read_text(encoding="utf-8")
    assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nloads_a+00.0.txt" in left, left
    assert _sha256(sim_dir / SCRIPT_FILE) != record.inputs_sha256[SCRIPT_FILE]


def test_a_second_point_of_the_same_case_starts_its_count_again(tmp_path):
    """Every point of a case runs in the same simulation folder; the count
    file of the first point would carry the second point's threshold past
    before its first step unless the run layer removed it."""
    campaign = _threshold_campaign(tmp_path, **{ITER: "4"})
    campaign.sims[0].sweep = SweepAxis(type="alpha", values=[0.0, 2.0])
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(RUNS_THE_COUNTER_FOUR_TIMES),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    assert [record.action_count for record in records] == [4, 4]


def test_a_run_without_a_threshold_records_none_for_the_three_fields(tmp_path):
    campaign = _threshold_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    from tests.tier1_offline.test_run_campaign import WRITES_LOADS

    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED, record.error
    assert (record.action_program, record.action_script, record.action_count) == (None,) * 3
    assert not (workspace.sim_dir("9001") / "actions").exists()


# --- the worked example on the page is the one this module builds -------------------


def test_the_worked_example_on_the_page_builds_to_the_lines_it_shows():
    text = PAGE.read_text(encoding="utf-8")
    cell = re.search(
        r"^(VELOCITY: 30\.0 / RPM: 1200 / .*EXPORT_UNSTEADY_AFTER_REV: 2)$", text, re.M
    )
    assert cell, "the page shows no VAR_NAMES_VALUES cell stating EXPORT_UNSTEADY_AFTER_REV"
    variables = dict(
        (key.strip(), value.strip())
        for key, value in (item.split(":", 1) for item in cell.group(1).split(" / "))
    )
    # The cell replaces every clock and window key the hand-built case carries.
    overrides: dict[str, str | None] = dict.fromkeys(
        ("DELTA_TIME", "TIME_ITERATIONS", "WINDOW_DEGREES")
    )
    overrides.update(variables)
    case = rotor_case(**overrides)
    script = Script("26.123")
    build_script(case, script)
    rendered = script.render().replace(sys.executable, "<python>")
    shown = re.search(r"```text\n(SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE[^`]*)```", text)
    assert shown, "the page shows no registration lines"
    assert shown.group(1).strip() in rendered, rendered
    # And the arithmetic the page states beside it.
    from pyflightstream.cases.workflows import unsteady_export_threshold

    threshold = unsteady_export_threshold(case)
    assert threshold is not None
    assert threshold.first_step == 72 and threshold.time_iterations == 108
    assert "step 72" in text and "108" in text
