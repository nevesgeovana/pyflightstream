"""FR-314: every unsteady row registers the step counter, count-only without per-step exports.

Until 0.32.0 the counter was registered only on a row asking for per-step
exports, so the progress bar of a local run (FR-129), which reads the count,
showed nothing on a long unsteady run without them. These tests build every
unsteady run type, a continuation included, on the builds that document the
unsteady solver action, run the count-only program with the real interpreter,
and read the local-run bar off it. A build that documents no action (26.120)
is the control: it registers nothing, as before. What the solver does with a
counter on such a row is owed by the licensed round of FR-314 (R5).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from pyflightstream.cases import SimCase
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    build_script,
    unsteady_counter_steps,
    unsteady_export_threshold,
)
from pyflightstream.run._actions_counter import render_count_program, render_program
from pyflightstream.script import Script
from tests.tier1_offline.test_g43_local_log import _Advancing, _point_folder
from tests.tier1_offline.test_restart_continuation import SAVED, _continuing_case
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case

ACTION_HEAD = "SET_NEW_UNSTEADY_SOLVER_ACTION"
#: The counter program runs as the solver runs it: its own interpreter, no package on the path.
ENV = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}


def _continuation() -> SimCase:
    return _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )


#: Every unsteady run type, a continuation included (R1), with the steps its
#: script marches.
ROWS = {
    "unsteady": (unsteady_case, 480),
    "unsteady_rotor": (rotor_case, 720),
    "continuation": (_continuation, 120),
}


def _actions(rendered: str) -> list[tuple[str, str]]:
    lines = rendered.splitlines()
    return [(line, lines[i + 1]) for i, line in enumerate(lines) if line.startswith(ACTION_HEAD)]


@pytest.mark.parametrize("build", ["26.123", "26.124"])
@pytest.mark.parametrize("row", sorted(ROWS))
def test_fr314_every_unsteady_row_without_export_registers_the_counter_alone(row, build):
    requirement = "FR-314"
    make, steps = ROWS[row]
    case = make()
    assert unsteady_export_threshold(case) is None, "the row asks no per-step export"
    script = Script(build)
    build_script(case, script)
    rendered = script.render()
    actions = _actions(rendered)
    assert [head.split()[1] for head, _ in actions] == ["COMMAND_LINE"], (requirement, rendered)
    assert actions[0][1].endswith(f'"{UNSTEADY_ACTION_PROGRAM}"'), actions
    # R2: no exports action, no parked exports file.
    assert UNSTEADY_ACTION_SCRIPT not in rendered
    assert script.pending_action_scripts == {}
    # The label stays what the row asks: a single march with a counter that counts.
    assert script.march_strategy == "single_march", requirement
    assert unsteady_counter_steps(case) == steps


@pytest.mark.parametrize("row", sorted(ROWS))
def test_fr314_a_build_without_actions_registers_nothing_the_control(row):
    requirement = "FR-314"
    script = Script("26.120")
    build_script(ROWS[row][0](), script)
    assert ACTION_HEAD not in script.render(), requirement


def test_fr314_a_row_with_per_step_export_registers_the_pair_as_before():
    """The counter and its exports script, in that order and nothing more (R4)."""
    requirement = "FR-314"
    script = Script("26.123")
    build_script(rotor_case(EXPORT_UNSTEADY_AFTER_REV="1"), script)
    rendered = script.render()
    actions = _actions(rendered)
    assert [head.split()[1] for head, _ in actions] == ["COMMAND_LINE", "SCRIPT"], requirement
    assert actions[1][1] == UNSTEADY_ACTION_SCRIPT
    assert script.pending_action_scripts == {UNSTEADY_ACTION_SCRIPT: ""}


def test_fr314_the_count_only_program_counts_and_writes_nothing_else(tmp_path):
    """Run by the real interpreter three times, as the solver would after three steps.

    The control is the threshold program run the same way, which rewrites the
    exports file the count-only program never writes.
    """
    requirement = "FR-314"
    counting = tmp_path / "counting" / "actions"
    counting.mkdir(parents=True)
    (counting / "pfs_unsteady_actions.py").write_text(
        render_count_program(5, interpreter=sys.executable), encoding="utf-8"
    )
    for _ in range(3):
        subprocess.run(
            [sys.executable, str(counting / "pfs_unsteady_actions.py")], check=True, env=ENV
        )
    state = json.loads((counting / "pfs_unsteady_actions.count").read_text(encoding="utf-8"))
    assert state == {"count": 3}, requirement
    assert sorted(p.name for p in counting.iterdir()) == [
        "pfs_unsteady_actions.count",
        "pfs_unsteady_actions.py",
    ], requirement
    control = tmp_path / "control" / "actions"
    control.mkdir(parents=True)
    threshold = unsteady_export_threshold(unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="1"))
    assert threshold is not None
    (control / "pfs_unsteady_actions.py").write_text(
        render_program(threshold, interpreter=sys.executable), encoding="utf-8"
    )
    subprocess.run([sys.executable, str(control / "pfs_unsteady_actions.py")], check=True, env=ENV)
    assert (control / "pfs_unsteady_exports.txt").is_file(), "the control writes the exports"


def test_fr314_the_local_run_bar_reads_the_count_only_program(tmp_path, capsys):
    """FR-129's bar, driven by a stand-in solver advancing the count to 30."""
    requirement = "FR-314"
    work, script = _point_folder(tmp_path, with_program=False)
    (work / "actions" / "pfs_unsteady_actions.py").write_text(
        render_count_program(30, interpreter=sys.executable), encoding="utf-8"
    )
    result = _Advancing(progress_every=10).run_script(script, work, timeout_s=120)
    said = capsys.readouterr().err
    steps = re.findall(r"\[[#.]{20}\] step (\d+)/30 \(\d+%\)", said)
    assert len(steps) >= 2, (requirement, said)
    assert result.return_code == 0


def test_fr314_a_stopped_run_recorded_without_the_counter_still_recovers_its_frame(tmp_path):
    """Parity with 0.32.0: a row it recorded without the counter continues under 0.33.0.

    The frame recovery of a stopped run compares the recorded script with the
    row rebuilt now; the counter this release adds places nothing, so a
    script without it is the same setup. The control is the same script with a
    scientific line changed, which is still refused.
    """
    import json

    from pyflightstream._digest import file_sha256
    from tests.tier1_offline.test_g58_frame_recovery import _old_run, _resolve

    requirement = "FR-314"
    workspace, case, record, shadow = _old_run(tmp_path)
    script = workspace.sim_dir("9001") / record.script_path
    lines = script.read_text(encoding="utf-8").split("\n")
    at = lines.index("SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter")
    del lines[at : at + 3]
    script.write_text("\n".join(lines), encoding="utf-8")
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows[0]["script_sha256"] = file_sha256(script)
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    result = _resolve(workspace, case)
    assert result["recovered_frame"] == shadow.loads_frame_record(), requirement
    changed = [line.replace("SOLVER_MINIMUM_CP -100", "SOLVER_MINIMUM_CP -99") for line in lines]
    assert changed != lines, "the control changes a scientific line"
    script.write_text("\n".join(changed), encoding="utf-8")
    rows[0]["script_sha256"] = file_sha256(script)
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(Exception, match="native setup changed"):
        _resolve(workspace, case)
