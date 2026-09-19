"""Tier 1: exports that begin after a threshold the row states (PFS-2031.18).

The author's design of 2026-09-08, drawn in the 0.13.0 scope and written down as
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
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import WORKFLOW_KEY, build_script, workflow_registry
from pyflightstream.post.products import NOT_APPLICABLE
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
        outputs=["loads_AL+000.txt"],
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
    # F01 (0.25.0): an unsteady row samples probes through fluid plots, so it
    # neither updates nor exports probe points, per step or at the end.
    assert verbs == [
        "UPDATE_ALL_SURFACE_SECTIONS",
        "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS",
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        "EXPORT_SOLVER_ANALYSIS_TECPLOT",
        "EXPORT_ALL_SURFACE_SECTIONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
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


#: What the solver does after each action on 26.123 (RPT-041 finding 3), as
#: a stub: when the rewritten script carries the exports, the loads file it
#: names is written as ``<name>_iteration=<count>.txt`` from a fixture, the
#: count read off the counter's own state file.
STAMPING_PROGRAM = (
    "import json\n"
    "fixture = pathlib.Path(FIXTURE_PATH).read_text()\n"
    "exports = pathlib.Path('actions/pfs_unsteady_exports.txt')\n"
    "count = pathlib.Path('actions/pfs_unsteady_actions.count')\n"
    "def stamp():\n"
    "    text = exports.read_text().splitlines()\n"
    "    names = [text[i + 1] for i, line in enumerate(text) "
    "if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']\n"
    "    n = json.loads(count.read_text())['count']\n"
    "    for name in names:\n"
    "        pathlib.Path(name[:-4] + f'_iteration={n}.txt').write_text(fixture)\n"
    "for _ in range(4):\n"
    "    subprocess.run(command, shell=True, check=True)\n"
    "    stamp()\n"
)


def runs_the_counter_and_stamps_the_exports(loads_fixture: Path) -> str:
    """The stub above, and after each action the solver's own stamping (RPT-041
    finding 3): when the rewritten script carries the exports, the loads file it
    names is written as ``<name>_iteration=<count>.txt``, from ``loads_fixture``."""
    return RUNS_THE_COUNTER_FOUR_TIMES.replace(
        "[subprocess.run(command, shell=True, check=True) for _ in range(4)]",
        STAMPING_PROGRAM.replace("FIXTURE_PATH", repr(str(loads_fixture))),
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
            # The whole run, which is the window a rotorless row with none
            # was given before 0.24.0 made the key mandatory.
            "LAST_ITERS_AVG": "4",
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
    assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET\nloads_AL+000.txt" in left, left
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


@pytest.mark.parametrize(
    "stated",
    [
        pytest.param({REV: "1"}, id="one-revolution"),
        pytest.param({REV: "0.5"}, id="half-revolution"),
        pytest.param({ITER: "4"}, id="four-iterations"),
    ],
)
def test_the_program_first_exports_on_the_step_the_package_computed(tmp_path, stated):
    """The arithmetic is written twice, once in the package (``first_step``)
    and once in the emitted program (``state``), and the two can diverge
    silently. The QA lens of the 0.13.0 release measured that the revolutions
    branch of the program was executed by no test at any tier: ``reached =
    count`` and ``azimuth / 180.0`` both survived. This pins the two
    arithmetics to each other in every form a row can state."""
    from pyflightstream.cases.workflows import unsteady_export_threshold
    from pyflightstream.run._actions_counter import render_program

    threshold = unsteady_export_threshold(rotor_case(**stated))
    assert threshold is not None
    program = tmp_path / PROGRAM
    program.parent.mkdir(parents=True)
    program.write_text(render_program(threshold, interpreter=sys.executable), encoding="utf-8")
    # Loaded as a module, not run: ``main`` is behind the name guard, so no
    # file is written; ``state`` is what the solver's clock drives.
    namespace = runpy.run_path(str(program), run_name="pfs_unsteady_actions_under_test")
    state = namespace["state"]
    steps = range(1, threshold.time_iterations + 1)
    exporting = [count for count in steps if state(count)["exporting"]]
    assert exporting, "the program never exports inside the row's time loop"
    assert exporting[0] == threshold.first_step, (stated, exporting[:3], threshold)
    assert exporting == list(range(threshold.first_step, threshold.time_iterations + 1)), (
        "once reached, the export runs on every later step"
    )


# --- PFS-2031.18.01: the stamped exports of a stub run, tabled as a series ------------


def test_the_series_of_a_rotor_stub_run_agrees_with_the_counter_on_the_azimuth(tmp_path):
    """The V&V lens of REL-0140: the azimuth column against the counter's own state
    file on a rotor row (0.72 degrees a step at 1200 rev/min and 0.0001 s), not
    against a hand-written expectation. A pin, green on 5a770de: the arithmetic
    was the same by reading, and this is the measurement the lens asked for."""
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import LOADS

    fixture = tmp_path / "loads_fixture.txt"
    fixture.write_text(LOADS, encoding="utf-8")
    case = rotor_case(**{ITER: "2"}).model_copy(
        update={"sim_id": "9002", "outputs": ["loads_{point}.txt"], "point": None}
    )
    campaign = Campaign(name="camp", fs_version="26.123", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(runs_the_counter_and_stamps_the_exports(fixture)),
        workspace,
        assess=converged,
        recipes={"unsteady_rotor": workflow_registry()["unsteady_rotor"]},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED, record.error
    assert record.export_window["step_deg"] == pytest.approx(0.72), record.export_window
    state = json.loads((workspace.sim_dir("9002") / COUNT_FILE).read_text(encoding="utf-8"))
    write_campaign_products(workspace, overwrite=True)
    table = workspace.root / "post" / "products" / "series" / "loads_AL+000_loads_series.csv"
    body = [line.split(",") for line in table.read_text(encoding="utf-8").splitlines()[1:]]
    assert [int(cells[0]) for cells in body] == [2, 3, 4]
    assert float(body[-1][2]) == pytest.approx(state["azimuth_deg"])
    assert float(body[-1][1]) == pytest.approx(state["time_s"])


def test_the_series_of_a_stub_run_agrees_with_the_counter_step_for_step(tmp_path):
    """The record carries the clock the counter ran with, and the series table
    computes each step's time the way the counter's own state() does; the steps
    tabled are exactly the ones the counter exported on. RED on d908092: the
    record's window has no clock and no series folder exists."""
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import LOADS

    fixture = tmp_path / "loads_fixture.txt"
    fixture.write_text(LOADS, encoding="utf-8")
    campaign = _threshold_campaign(tmp_path, **{ITER: "2"})
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(runs_the_counter_and_stamps_the_exports(fixture)),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED, record.error
    assert record.export_window["delta_time_s"] == pytest.approx(0.01), record.export_window
    assert "step_deg" not in record.export_window, "a rotorless row has no azimuth"
    sim_dir = workspace.sim_dir("9001")
    stamped = sorted(p.name for p in sim_dir.iterdir() if "_iteration=" in p.name)
    assert stamped == [f"loads_AL+000_iteration={n}.txt" for n in (2, 3, 4)], stamped
    state = json.loads((sim_dir / COUNT_FILE).read_text(encoding="utf-8"))
    # The run wrote the products itself; the stage rewrites them from the manifest alone.
    write_campaign_products(workspace, overwrite=True)
    table = workspace.root / "post" / "products" / "series" / "loads_AL+000_loads_series.csv"
    assert table.is_file(), sorted((workspace.root / "post").rglob("*"))
    rows = table.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("STEP,time_s,azimuth_deg,"), rows[0]
    body = [line.split(",") for line in rows[1:]]
    assert [int(cells[0]) for cells in body] == [2, 3, 4]
    # The counter's last state is step 4 at 4 * DELTA_TIME; the table's last row says the same.
    assert float(body[-1][1]) == pytest.approx(state["time_s"])
    # `NA` AND NOT BLANK since 0.23.0. A row with no rotor has no azimuth,
    # and this is the exact shape the owner reported from a production
    # superfile: a column declared for the union of every run type, empty on
    # a row whose run type does not have it. Her reader cannot parse the
    # blank, and no reader can tell it from a zero.
    assert all(cells[2] == NOT_APPLICABLE for cells in body), "no rotor, no azimuth"
    assert not any(cells[2] == "" for cells in body), "a blank cell is the defect, not the fix"


# --- FR-98, GOAL-019 item 7: the wall-clock watchdog --------------------------


def test_goal019_watchdog_the_eighth_status_is_not_a_failure():
    """WALLTIME_REACHED joins the set, and its sibling already existed.

    COMPLETED_MAX_ITER is "ran to the iteration cap without converging".
    This is the same shape for the clock cap, which is why it is not a
    failure: the numbers up to that step are real and the user judges
    whether to continue.
    """
    from pyflightstream.workspace import RunStatus

    names = [status.value for status in RunStatus]
    assert "WALLTIME_REACHED" in names and "SUBMITTED" in names, names
    assert not RunStatus.WALLTIME_REACHED.value.startswith("FAILED")
    assert not RunStatus.SUBMITTED.value.startswith("FAILED")
    # The six of 0.16.0 are all still there: nothing already recorded
    # changes meaning.
    for older in (
        "CONVERGED",
        "COMPLETED_MAX_ITER",
        "FAILED_EXECUTION",
        "FAILED_SCRIPT",
        "FAILED_INCOMPLETE_OUTPUT",
        "FAILED_DIVERGED",
    ):
        assert older in names, older


def test_goal019_watchdog_the_clock_pair_registers_after_the_counter_pair():
    """Her numbering of 2026-09-12: the clock is (3) and its script is (4).

    THE ORDER IS THE DESIGN. The solver runs actions in creation order and
    cannot be told otherwise, so in each pair the python that WRITES is
    registered before the script that READS.
    """
    from pyflightstream.cases.workflows import (
        UNSTEADY_COUNTER_ACTION,
        UNSTEADY_EXPORTS_ACTION,
        WALLTIME_CLOCK_ACTION,
        WALLTIME_STOP_ACTION,
        _unsteady_actions,
    )
    from pyflightstream.script import Script

    script = Script(version="26.123")
    _unsteady_actions(script, _a_threshold(), walltime=True)
    names = [use.name for use in script.unsteady_actions]
    assert names == [
        UNSTEADY_COUNTER_ACTION,
        UNSTEADY_EXPORTS_ACTION,
        WALLTIME_CLOCK_ACTION,
        WALLTIME_STOP_ACTION,
    ], names


def test_goal019_watchdog_the_clock_pair_takes_one_and_two_when_alone():
    """ "When the other two exist", in her words, and when they do not.

    A row that states no export threshold registers no counter pair at
    all, so the clock pair is (1) and (2). The positions are what the row
    asks for rather than fixed numbers.
    """
    from pyflightstream.cases.workflows import (
        WALLTIME_CLOCK_ACTION,
        WALLTIME_STOP_ACTION,
        _unsteady_actions,
    )
    from pyflightstream.script import Script

    script = Script(version="26.123")
    _unsteady_actions(script, None, walltime=True)
    assert [use.name for use in script.unsteady_actions] == [
        WALLTIME_CLOCK_ACTION,
        WALLTIME_STOP_ACTION,
    ]


def test_goal019_watchdog_the_clock_fires_once_and_says_where_it_stopped(tmp_path):
    """The program itself, run the way the solver runs it: once per step.

    IT KEEPS ITS OWN STATE because the solver hands an action nothing. And
    it fires ONCE: a second firing would append a second copy of every
    export line into the file the solver is about to read.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from pyflightstream.cases.workflows import (
        WALLTIME_CLOCK_STATE,
        WALLTIME_CLOCK_TEMPLATE,
        WALLTIME_STOP_SCRIPT,
        WALLTIME_STOP_VERB,
    )

    actions = tmp_path / "actions"
    actions.mkdir()
    program = actions / "clock.py"
    program.write_text(
        WALLTIME_CLOCK_TEMPLATE.format(
            sim="9001",
            state_name=Path(WALLTIME_CLOCK_STATE).name,
            stop_name=Path(WALLTIME_STOP_SCRIPT).name,
            deadline=0.0,
            stop_text=f"EXPORT_LOG\nrun.log\n{WALLTIME_STOP_VERB}\n",
        ),
        encoding="utf-8",
    )
    stop = actions / Path(WALLTIME_STOP_SCRIPT).name
    stop.write_text("", encoding="utf-8")

    # env= ON PURPOSE, which the repository's spawn ratchet asks for: a
    # child that inherits the whole environment is the defect it counts.
    # This program reads nothing from it, so an empty one is the honest
    # answer rather than a filtered copy.
    for _ in range(3):
        done = subprocess.run(
            [sys.executable, str(program)],
            check=False,
            env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        )
        assert done.returncode == 0, done

    state = json.loads((actions / Path(WALLTIME_CLOCK_STATE).name).read_text(encoding="utf-8"))
    assert state["fired"] is True
    assert state["steps"] == 3, state
    assert state["stopped_at"]["step"] == 1, (
        "the clock fired more than once, so the stop file holds a repeated export block"
    )
    assert stop.read_text(encoding="utf-8").count(WALLTIME_STOP_VERB) == 1


def test_goal019_watchdog_the_margin_lives_in_the_setup(tmp_path):
    """Her decision: the wall clock is the ROW's and the margin is the SETUP's.

    A margin is how much time to leave for the exports, which is the same
    question on every platform and does not vary with the row; a wall
    clock does.
    """
    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.cases.workflows import WALLTIME_MARGIN_DEFAULT_S, walltime_margin_s

    bare = SimCase(
        sim_id="9001",
        aircraft="Rig",
        recipe="unsteady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
    )
    assert walltime_margin_s(bare) == float(WALLTIME_MARGIN_DEFAULT_S)
    assert WALLTIME_MARGIN_DEFAULT_S == 1200, "her number of 2026-09-12 is twenty minutes"


def _a_threshold():
    """One export threshold, built the way a row states it."""
    from pyflightstream.cases.workflows import UnsteadyExportThreshold

    return UnsteadyExportThreshold(
        stated_form="EXPORT_UNSTEADY_AFTER_ITER",
        stated_value=4.0,
        first_step=4,
        time_iterations=10,
        step_deg=None,
        delta_time_s=0.001,
        rpm=None,
        exports=(("log", "_log.txt", "EXPORT_LOG"),),
    )


def test_goal019_watchdog_restart_reads_the_three_forms_and_refuses_a_fourth():
    """FR-96: RESTART says how to continue a run the clock stopped.

    ONE SEPARATOR, and her message spelled two. The equals is taken for
    both, because the colon is already the key/value separator of the free
    cell and nesting it inside braces reads as a second pair.
    """
    import pytest

    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.cases.workflows import (
        RESTART_ADDITIONAL_REVS,
        RESTART_FINISH_PENDING,
        parse_restart,
    )
    from pyflightstream.exceptions import CampaignConfigError

    def row(cell):
        return SimCase(
            sim_id="9001",
            aircraft="Rig",
            recipe="unsteady_rotor",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            variables={"RESTART": cell},
        )

    assert parse_restart(row("{FINISH_PENDING}")).form == RESTART_FINISH_PENDING
    assert parse_restart(row("{ADDITIONAL_ITERS=120}")).value == 120
    assert parse_restart(row("{ADDITIONAL_REVS=2}")).form == RESTART_ADDITIONAL_REVS
    assert parse_restart(row("{ADDITIONAL_REVS=2}")).value == 2

    empty = SimCase(
        sim_id="9001",
        aircraft="Rig",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
    )
    assert parse_restart(empty) is None, "a row stating none asks for nothing"

    with pytest.raises(CampaignConfigError, match="not one of"):
        parse_restart(row("{CARRY_ON}"))
    with pytest.raises(CampaignConfigError, match="takes no number"):
        parse_restart(row("{FINISH_PENDING=3}"))
    with pytest.raises(CampaignConfigError, match="states no number"):
        parse_restart(row("{ADDITIONAL_ITERS}"))
    with pytest.raises(CampaignConfigError, match="adds nothing"):
        parse_restart(row("{ADDITIONAL_ITERS=0}"))


def test_goal019_watchdog_finish_pending_subtracts_what_the_run_reached():
    """The clause that makes stopped_at load-bearing.

    FINISH_PENDING has nothing to subtract from unless the record says
    where the run stopped, which is why the program that stops it writes
    that number down before the solver goes away.
    """
    import pytest

    from pyflightstream.cases.workflows import (
        RESTART_ADDITIONAL_REVS,
        RestartRequest,
        restart_iterations,
    )
    from pyflightstream.exceptions import CampaignConfigError

    record = {
        "stopped_at": {"step": 430, "elapsed_s": 7200.0},
        "export_window": {"time_iterations": 720, "step_deg": 15.0},
    }
    pending = RestartRequest(form="FINISH_PENDING", value=None)
    assert restart_iterations(pending, record) == 290, "720 asked, 430 reached"

    revs = RestartRequest(form=RESTART_ADDITIONAL_REVS, value=2)
    assert restart_iterations(revs, record) == 48, "two turns at fifteen degrees a step"

    with pytest.raises(CampaignConfigError, match="does not say how many time steps"):
        restart_iterations(pending, {"stopped_at": {"step": 430}})
    with pytest.raises(CampaignConfigError, match="nothing to finish"):
        restart_iterations(
            pending,
            {"stopped_at": {"step": 720}, "export_window": {"time_iterations": 720}},
        )


def test_goal019_watchdog_the_record_of_a_watched_run_carries_its_clock(tmp_path):
    """A row that states WALLTIME leaves a record that says what it was.

    FOUND BY THE FIRST REAL RUN OF pfs0170, not by a test. The run stage
    had written `walltime_s` and `walltime_margin_s` into the record since
    the watchdog landed, and `RunRecord` forbids extra keys, so the first
    rotor point that stated a WALLTIME died at the manifest with the
    solver's work already done. Every case here went through the builders
    and none went through the record.

    BOTH NUMBERS ARE WRITTEN because neither can be recovered afterwards:
    the row may have been edited since, and the margin has a default, so a
    record that says only WALLTIME_REACHED cannot say what it reached.
    """
    from tests.tier1_offline.test_post_products import LOADS

    fixture = tmp_path / "loads_fixture.txt"
    fixture.write_text(LOADS, encoding="utf-8")
    campaign = _threshold_campaign(tmp_path, **{ITER: "2", "WALLTIME": "1h"})
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(runs_the_counter_and_stamps_the_exports(fixture)),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED, record.error
    assert record.walltime_s == 3600.0, f"the record says its wall clock was {record.walltime_s!r}"
    assert record.walltime_margin_s == 1200.0, (
        "the margin the setup left for the exports is not in the record, so a "
        "WALLTIME_REACHED run cannot say how much time it was given to write them"
    )
    # And the record READS BACK, which is the half that was broken: the
    # manifest is written and validated on the way in.
    assert workspace.read_manifest()[0].walltime_s == 3600.0


def test_goal019_watchdog_a_row_with_no_wall_clock_records_none(tmp_path):
    """The control. Every steady row and every unsteady row before 0.17.0.

    A field that is always filled would be a field that says nothing, and
    a default of zero would read as a clock that had already run out.
    """
    from tests.tier1_offline.test_post_products import LOADS

    fixture = tmp_path / "loads_fixture.txt"
    fixture.write_text(LOADS, encoding="utf-8")
    campaign = _threshold_campaign(tmp_path, **{ITER: "2"})
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(runs_the_counter_and_stamps_the_exports(fixture)),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    assert records[0].walltime_s is None
    assert records[0].walltime_margin_s is None


def _conventions_for(outputs):
    """The rendered conventions of one unsteady point, with these output names."""
    from pyflightstream.cases import SimCase, SweepAxis
    from pyflightstream.run import workflow_conventions_for

    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=list(outputs),
        point={"alpha": 0.0},
        variables={
            WORKFLOW_KEY: "unsteady",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.01",
            "TIME_ITERATIONS": "4",
        },
    )
    return case, workflow_conventions_for(case)


def test_goal019_watchdog_the_rescue_exports_update_before_it_exports(tmp_path):
    """The outputs a stopped run leaves are the ONLY outputs it leaves.

    FOUND BY THE V&V LENS, 2026-09-13. This block was written as its own
    loop and omitted the three update commands its two sibling emitters
    both emit, so a rescued run's sections, sectional-loads and probe
    files carried the state BEFORE the stop rather than at it, silently,
    under a record saying the numbers up to that step are real. The
    codebase states the reason two functions away: an export of sections
    nobody updated is an export of the previous state.
    """
    from pyflightstream.cases.workflows import WALLTIME_STOP_VERB, walltime_stop_text

    case, conventions = _conventions_for(
        ["loads_{point}.txt", "loads_{point}_cp.txt", "loads_{point}_probes.txt"]
    )
    text = walltime_stop_text(case, conventions)
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]

    for command in (
        "UPDATE_ALL_SURFACE_SECTIONS",
        "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS",
    ):
        assert command in lines, f"the rescue exports without {command}: {lines}"
        assert lines.index(command) < min(
            index for index, line in enumerate(lines) if line.startswith("EXPORT_")
        ), f"{command} comes after an export, so the export is of the previous state"
    # F01 (0.25.0): this unsteady row samples its probes through fluid plots, so
    # the rescue neither updates nor exports probe points.
    assert "UPDATE_PROBE_POINTS" not in lines, lines
    assert "EXPORT_PROBE_POINTS" not in lines, lines
    assert lines[-1] == WALLTIME_STOP_VERB, lines
    assert lines.count(WALLTIME_STOP_VERB) == 1, lines


def test_goal019_watchdog_the_rescue_claims_its_names_the_way_the_reader_does(tmp_path):
    """A _cp.txt declared before a .txt is the sections file, not the loads file.

    FOUND BY THE V&V LENS. The loop claimed names by a bare endswith in
    EXPORT_KINDS declaration order, and loads carries `.txt` while
    sections carries `_cp.txt`, so the longer suffix never got a chance:
    the rescue emitted EXPORT_SOLVER_ANALYSIS_SPREADSHEET with the
    sections file name. `classify_outputs` exists for exactly this and
    says so in its own docstring.
    """
    from pyflightstream.cases.workflows import walltime_stop_text

    case, conventions = _conventions_for(["loads_{point}_cp.txt", "loads_{point}.txt"])
    lines = walltime_stop_text(case, conventions).splitlines()
    pairs = {
        lines[index]: lines[index + 1]
        for index, line in enumerate(lines)
        if line.startswith("EXPORT_") and index + 1 < len(lines)
    }
    spreadsheet = next((name for verb, name in pairs.items() if "SPREADSHEET" in verb), None)
    assert spreadsheet is not None, pairs
    assert not spreadsheet.endswith("_cp.txt"), (
        f"the loads spreadsheet is being exported under {spreadsheet}, which is the "
        "sections file: the wrong content under the wrong name, in the one export set "
        "a stopped run gets"
    )


def test_goal019_watchdog_the_rescue_and_the_counter_export_the_same_lines(tmp_path):
    """One implementation, measured rather than promised.

    The two actions that export from inside a run must write the same
    thing, or the one that fires rarely is the one that is wrong.
    """
    from pyflightstream.cases.workflows import (
        WALLTIME_STOP_VERB,
        _per_step_exports,
        walltime_stop_text,
    )

    case, conventions = _conventions_for(
        ["loads_{point}.txt", "loads_{point}_cp.txt", "loads_{point}_probes.txt"]
    )
    counter = [line for line in _per_step_exports(conventions, case).splitlines() if line]
    rescue = [
        line
        for line in walltime_stop_text(case, conventions).splitlines()
        if line and not line.startswith("#") and line != WALLTIME_STOP_VERB
    ]
    assert rescue == counter, (
        "the rescue and the per-step action no longer write the same exports, which is "
        "the divergence one function exists to make impossible"
    )


def test_goal019_watchdog_the_rescue_writes_the_whole_run_exports_too(tmp_path):
    """GEO-047-C08: the rescue lost the exports it exists for, on the same day.

    Sharing one function with the per-step action was the right fix for a
    real divergence, and the shared function drops the simulation file,
    the plots table and the log because a PER-STEP action must: a
    simulation file written every time step is not a per-step export. The
    rescue is the opposite case, the LAST thing a stopped run does, and it
    needs them most. A row declaring a plots export and a log got neither.
    """
    from pyflightstream.cases.workflows import (
        WALLTIME_STOP_VERB,
        _per_step_exports,
        walltime_stop_text,
    )

    case, conventions = _conventions_for(
        [
            "loads_{point}.txt",
            "loads_{point}_cp.txt",
            "loads_{point}_plots.txt",
            "loads_{point}_log.txt",
        ]
    )
    rescue = walltime_stop_text(case, conventions)
    assert "EXPORT_LOG" in rescue, rescue
    assert any("PLOTS" in line for line in rescue.splitlines()), rescue
    assert rescue.rstrip().endswith(WALLTIME_STOP_VERB)

    # AND THE PER-STEP ACTION STILL DROPS THEM, which is the other half:
    # one function, two answers, and the switch is what says which.
    per_step = _per_step_exports(conventions, case)
    assert "EXPORT_LOG" not in per_step, (
        "the per-step action exports the log every time step, which is not a per-step "
        "export and is the reason the whole-run kinds are dropped there"
    )
    assert not any("PLOTS" in line for line in per_step.splitlines())
