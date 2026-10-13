"""Tier 1: the command database rows the licensed runs of 2026-10-12 moved (RPT-166).

PFS-2135.060, .061 and .066 each named rows the evidence contradicted: names the
solver refuses still documented, so the emitter wrote them; a start time
recorded broken from a probe artifact; a bulk separation model inherited by two
builds whose editions no longer print it. These tests hold the rows as the runs
and the editions left them, through the emitter a user meets.
"""

from __future__ import annotations

import pytest

from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.script import BrokenCommandError, Script

FSI_PAIR = ("SET_MOTION_FSI_EXECUTABLE", "SET_MOTION_FSI_STRUCTURAL_NODES")
FSI_ARGS = {
    "SET_MOTION_FSI_EXECUTABLE": (1, "DISABLE", "ENABLE", "solver.exe"),
    "SET_MOTION_FSI_STRUCTURAL_NODES": (1, "nodes.txt"),
}


@pytest.mark.parametrize("build", ("26.100", "26.101", "26.120", "26.124", "26.125"))
@pytest.mark.parametrize("command", FSI_PAIR)
def test_p0400_probes_the_fsi_motion_pair_is_refused_where_measured(build, command):
    """P0400-PROBES-FSIPAIR: PFS-2135.061, the pair the solver refuses is never written."""
    script = Script(build)
    script.emit("CREATE_NEW_MOTION", "6DOF")
    with pytest.raises(CommandNotInVersionError, match="MEASURED REMOVED 2026-10-12"):
        script.emit(command, *FSI_ARGS[command])
    row = CommandRegistry.load().commands[command].versions[build]
    assert row.report and "2026-10-12" in row.report
    assert "Candidate broken" not in (CommandRegistry.load().commands[command].notes or "")


def test_p0400_probes_the_valarezo_erase_of_the_manual_is_refused():
    """P0400-PROBES-VALAREZO: PFS-2135.061, the 26.100 name the solver does not answer to."""
    with pytest.raises(CommandNotInVersionError, match="removed"):
        Script("26.100").emit("DELETE_VALAREZO_CRITERION_BOUNDARIES")


@pytest.mark.parametrize("build", ("26.120", "26.124", "26.125"))
def test_p0400_probes_the_start_time_runs_where_measured(build):
    """P0400-PROBES-STARTTIME: PFS-2135.066, verified on a 6DOF motion from the 2026-10-12 runs."""
    script = Script(build)
    script.emit("CREATE_NEW_MOTION", "6DOF")
    script.emit("SET_MOTION_START_TIME", 1, 0.05)
    assert "SET_MOTION_START_TIME 1 0.05" in script.render()
    row = CommandRegistry.load().commands["SET_MOTION_START_TIME"].versions[build]
    assert row.status == "verified" and "2026-10-12" in (row.report or "")


def test_p0400_probes_the_start_time_of_26122_is_its_own_row():
    """P0400-PROBES-STARTTIME-26122: 26.122 answers from its edition, not from 26.120."""
    row = CommandRegistry.load().commands["SET_MOTION_START_TIME"].versions["26.122"]
    assert row.status == "documented" and "SRC-750" in (row.note or "")


def test_p0400_probes_a_report_applies_again_after_its_removal_was_edited(tmp_path):
    """P0400-PROBES-REAPPLY: a removal edited deliberately from a report corroborates on re-apply.

    apply-compat refuses a removal over a row citing an edition page and asks for
    the row to be edited deliberately; once it was, from that same report, the
    refusal stopped the report's every other command from being promoted.
    """
    import shutil
    from pathlib import Path

    from pyflightstream.qa.compat import CORROBORATED, apply_compat

    root = Path(__file__).resolve().parents[2]
    commands = tmp_path / "src" / "pyflightstream" / "commands"
    shutil.copytree(root / "src" / "pyflightstream" / "commands", commands)
    name = "CMP-26124_2026-10-12_gap-probes.yaml"
    (tmp_path / "reports" / "compat").mkdir(parents=True)
    shutil.copy(root / "reports" / "compat" / name, tmp_path / "reports" / "compat" / name)
    report = tmp_path / "reports" / "compat" / name
    promotions = apply_compat(report, repo_root=tmp_path, commands_dir=commands)
    outcomes = {name: status for name, status, _ in promotions}
    assert outcomes["SET_MOTION_FSI_EXECUTABLE"] == CORROBORATED
    assert outcomes["SET_OFF_BODY_STREAMLINE_LENGTH"] == CORROBORATED


def test_p0400_probes_the_bulk_separation_model():
    """P0400-PROBES-BULK: PFS-2135.060, broken where run, removed where the edition drops it."""
    with pytest.raises(BrokenCommandError, match="CREATE_CYLINDRICAL_BULK_SEPARATION"):
        Script("26.120").emit("CREATE_BULK_SEPARATION", "B", "CYLINDRICAL", -1, 0.5)
    for build in ("26.121", "26.122"):
        with pytest.raises(CommandNotInVersionError, match="CREATE_CYLINDRICAL_BULK_SEPARATION"):
            Script(build).emit("CREATE_BULK_SEPARATION", "B", "CYLINDRICAL", -1, 0.5)
