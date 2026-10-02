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
from pathlib import Path

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


@pytest.mark.parametrize("build", ["26.120", "26.121"])
@pytest.mark.parametrize("row", sorted(ROWS))
def test_fr314_a_build_without_actions_registers_nothing_the_control(row, build):
    requirement = "FR-314"
    script = Script(build)
    build_script(ROWS[row][0](), script)
    assert ACTION_HEAD not in script.render(), requirement


@pytest.mark.parametrize("build", ["26.120", "26.121"])
def test_fr314_a_per_step_export_on_a_build_without_actions_is_refused(build):
    """As before 0.33.0: the threshold asks an action the build cannot run."""
    from pyflightstream.cases.workflows import BuildCapabilityError

    requirement = "FR-314"
    with pytest.raises(BuildCapabilityError, match=ACTION_HEAD):
        build_script(rotor_case(EXPORT_UNSTEADY_AFTER_REV="1"), Script(build))
    assert requirement


#: The sha256 of the goldens as v0.32.0 committed them, recorded from the tag.
GOLDENS_0320 = Path(__file__).parent / "fixtures" / "goldens_v0320_sha256.json"
REPO = Path(__file__).resolve().parents[2]
#: The counter's registration, the only lines FR-314 adds to a script (R4).
COUNTER_REGISTRATION = re.compile(
    r"^SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter\n"
    r'"[^"\n]+" "actions/pfs_unsteady_actions\.py"\n\n',
    re.MULTILINE,
)
#: The goldens FR-314 changes: every unsteady run type on every build that
#: documents the action, and the tier-3 scripts of rows without per-step export.
CHANGED_GOLDENS = {
    *(
        f"tests/tier1_offline/goldens/workflows/{kind}__{form}__{build}.txt"
        for kind in ("unsteady", "unsteady_rotor")
        for form in ("bare", "full", "resolved")
        for build in ("26.122", "26.123", "26.124")
    ),
    "tests/tier3_licensed/goldens/matriz_builds/P7002-M144RE438AL+000BE+000.txt",
    "tests/tier3_licensed/goldens/matriz_mesh/P4105-M100RE230AL+020.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8001-M100RE230AL+000BE+000.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8002-M100RE230AL+000BE+000J+060.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8002-M100RE230AL+000BE+000J+080.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8003-M100RE230AL+000BE+000J+060.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8003-M100RE230AL+000BE+000J+080.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8004-M100RE230AL+000BE+000.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8005-M100RE230AL+000BE+000.txt",
    "tests/tier3_licensed/goldens/matriz_vocab/P8006-M100RE230AL+000BE+000.txt",
}


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _restore_fr51_block(name: str, text: str) -> str | None:
    """The text with the block FR-51 (0.33.1) removes put back, or None when it does not apply.

    FR-51 drops "SET_PLOT_TYPE SECTIONS_CP / SAVE_PLOT_TO_FILE / <stem>_plot_cp_sections.txt /
    blank line" from a row whose script cuts no section. The block is restored right after the
    loads plot block, all four lines and nothing else, so a golden that differs from v0.32.0 by
    anything beside that removal still fails its digest.
    """
    if "NEW_SURFACE_SECTION_DISTRIBUTION" in text:
        return None
    stem = Path(name).stem
    anchor = f"SET_PLOT_TYPE LOADS\nSAVE_PLOT_TO_FILE\n{stem}_plot_loads.txt\n\n"
    if text.count(anchor) != 1 or "SECTIONS_CP" in text:
        return None
    block = f"SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n{stem}_plot_cp_sections.txt\n\n"
    return text.replace(anchor, anchor + block)


def _golden_classes(record: dict) -> tuple[set, set]:
    """The goldens that differ from v0.32.0 by the counter, and by the FR-51 removal."""
    requirement = "FR-314"
    changed, fr51 = set(), set()
    for name, digest in sorted(record["digests"].items()):
        text = "\n".join((REPO / name).read_text(encoding="utf-8").splitlines())
        if _sha(text) == digest:
            continue
        stripped, found = COUNTER_REGISTRATION.subn("", text)
        if found == 0:
            # No counter: the only other admitted difference is the FR-51 removal.
            restored = _restore_fr51_block(name, text)
            assert restored is not None, (requirement, name, found)
            assert _sha(restored) == digest, (requirement, name, "differs beyond the FR-51 removal")
            fr51.add(name)
            continue
        assert found == 1, (requirement, name, found)
        assert _sha(stripped) == digest, (requirement, name, "differs beyond the counter")
        changed.add(name)
    return changed, fr51


#: The goldens FR-51 (0.33.1) changes: a row whose script cuts no section no longer plots them.
FR51_GOLDENS = {"tests/tier3_licensed/goldens/matriz/P1021-M100RE230AL+000.txt"}


def test_fr314_every_golden_differs_from_0320_only_by_the_counter_registration():
    """R4, against the goldens of v0.32.0 by their recorded digests.

    Every unsteady tier-1 golden and every tier-3 golden is either the bytes
    v0.32.0 committed, or those bytes with exactly one counter registration
    added. The set of the second kind is every unsteady run type on 26.122 to
    26.124 and the ten tier-3 scripts of rows without per-step export. The
    one other admitted difference is the FR-51 removal of the sections plot
    block from a script that cuts no section (0.33.1). The control: a changed
    golden, the counter kept, does not match its digest.
    """
    requirement = "FR-314"
    record = json.loads(GOLDENS_0320.read_text(encoding="utf-8"))
    assert record["tag"] == "v0.32.0" and len(record["digests"]) == 134, record.keys()
    changed, fr51 = _golden_classes(record)
    assert changed == CHANGED_GOLDENS, (requirement, changed ^ CHANGED_GOLDENS)
    assert fr51 == FR51_GOLDENS, (requirement, fr51 ^ FR51_GOLDENS)


def test_fr314_the_fr51_removal_is_admitted_whole_and_alone():
    """Controls: a second change beside the removal, or part of the block, fails."""
    requirement = "FR-314"
    record = json.loads(GOLDENS_0320.read_text(encoding="utf-8"))
    (name,) = sorted(FR51_GOLDENS)
    digest = record["digests"][name]
    text = "\n".join((REPO / name).read_text(encoding="utf-8").splitlines())
    restored = _restore_fr51_block(name, text)
    assert restored is not None and _sha(restored) == digest, requirement
    # A second extra change beside the removal.
    planted = text.replace("EXPORT_LOG\n", "EXPORT_LOG\nEXPORT_LOG\n", 1)
    assert planted != text
    again = _restore_fr51_block(name, planted)
    assert again is not None and _sha(again) != digest, requirement
    # Only part of the block removed: one of its four lines is left in the golden.
    stem = Path(name).stem
    loads = f"SAVE_PLOT_TO_FILE\n{stem}_plot_loads.txt\n\n"
    partial = text.replace(loads, loads + "SET_PLOT_TYPE SECTIONS_CP\n", 1)
    assert partial != text
    assert _restore_fr51_block(name, partial) is None, requirement
    # A script that cuts a section never takes the allowance.
    cutting = text + "NEW_SURFACE_SECTION_DISTRIBUTION\n"
    assert _restore_fr51_block(name, cutting) is None, requirement


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
    # What is removed is the counter's registration and nothing else: the
    # three lines the golden record below proves are all 0.33.0 adds.
    assert re.fullmatch(r'"[^"]+" "actions/pfs_unsteady_actions\.py"', lines[at + 1]), lines
    assert lines[at + 2] == "" and ACTION_HEAD not in "\n".join(lines[at + 3 :]), lines
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
