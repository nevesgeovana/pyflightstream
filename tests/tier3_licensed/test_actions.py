"""Tier 3: the unsteady actions of PFS-2031.18, run on 26.123 (row 6002, RPT-045).

Row 6002 of ``matriz_actions.fs`` is the ``unsteady`` run type on the tour's
wing with ``EXPORT_UNSTEADY_AFTER_ITER: 4`` over ``TIME_ITERATIONS: 8``. The
run layer wrote the counter program and the empty export script under the
simulation's ``actions/`` folder, the run type registered the COMMAND_LINE
action running the program and the SCRIPT action pointing at the file, and
the solver ran both after every time step. What the run left is what
design/67 said it would, and this module reads it back through the record.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.tier3_licensed.conftest import TERMINAL_OK, line

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_actions"
THRESHOLD = 4
STEPS = 8
#: The export kinds the program writes after the threshold, one file per
#: step each, stamped by the solver with the iteration.
KINDS = ("", "_cp", "_sloads", "_probes")


def _record(runs):
    return runs.one(MATRIX, "6002", alpha=2.0)


def test_the_row_ran_terminal_and_the_record_keeps_the_count(runs):
    record = _record(runs)
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == "26.123"
    assert record.action_program == "actions/pfs_unsteady_actions.py"
    assert record.action_script == "actions/pfs_unsteady_exports.txt"
    assert record.action_count == STEPS
    assert set(record.inputs_sha256) >= {record.action_program, record.action_script}
    # The script file was EMPTY when the record hashed it, before the solver
    # started: the hash of zero bytes.
    assert record.inputs_sha256[record.action_script].startswith("e3b0c44298fc1c149afb")


def test_the_two_actions_were_registered_in_order_before_the_solver(runs):
    script = runs.script(_record(runs))
    texts = script.splitlines()
    first = texts.index(line(script, "SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE"))
    second = texts.index(line(script, "SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT"))
    init = texts.index("INITIALIZE_SOLVER")
    assert first < second < init
    assert texts[first + 1].endswith('"actions/pfs_unsteady_actions.py"')
    assert texts[second + 1] == "actions/pfs_unsteady_exports.txt"


def test_the_counter_reached_the_step_count_and_the_solver_ran_it_every_step(runs, workspace):
    sim = workspace.sim_dir("6002")
    count = json.loads((sim / "actions" / "pfs_unsteady_actions.count").read_text(encoding="utf-8"))
    assert count["count"] == STEPS and count["exporting"] is True, count
    record = _record(runs)
    log = next(o for o in record.outputs if o.endswith("_log.txt"))
    text = (sim / log).read_bytes().decode("utf-8", "replace")
    assert text.count("Executed runtime command:") == STEPS
    assert text.count("Running script file: actions/pfs_unsteady_exports.txt") == STEPS


def test_the_exports_begin_at_the_threshold_and_are_stamped_by_the_solver(runs, workspace):
    sim = workspace.sim_dir("6002")
    stem = _record(runs).script_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stamped = {}
    for path in sim.iterdir():
        found = re.fullmatch(
            rf"{re.escape(stem)}(_cp|_sloads|_probes)?_iteration=(\d+)\.(txt|dat)", path.name
        )
        if found:
            stamped.setdefault(int(found.group(2)), set()).add(
                (found.group(1) or "", found.group(3))
            )
    assert sorted(stamped) == list(range(THRESHOLD, STEPS + 1)), sorted(stamped)
    for iteration, kinds in stamped.items():
        assert kinds == {
            ("", "txt"),
            ("", "dat"),
            ("_cp", "txt"),
            ("_sloads", "txt"),
            ("_probes", "txt"),
        }, (
            iteration,
            kinds,
        )


def test_the_rewritten_script_carries_the_exports_after_the_threshold(workspace):
    text = (workspace.sim_dir("6002") / "actions" / "pfs_unsteady_exports.txt").read_text(
        encoding="utf-8"
    )
    assert text.startswith("UPDATE_ALL_SURFACE_SECTIONS")
    for command in (
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        "EXPORT_SOLVER_ANALYSIS_TECPLOT",
        "EXPORT_ALL_SURFACE_SECTIONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
        "EXPORT_PROBE_POINTS",
    ):
        assert line(text, command) == command
