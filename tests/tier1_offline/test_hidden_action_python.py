"""Native COMMAND_LINE actions must not create Python console windows."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import workflows


def test_windows_action_selects_existing_sibling_pythonw(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    console = tmp_path / "python.exe"
    windowless = tmp_path / "pythonw.exe"
    console.write_bytes(b"fixture")
    windowless.write_bytes(b"fixture")
    line = workflows.unsteady_action_command_line(str(console))
    assert line.startswith(f'"{windowless}" ')


def test_windows_action_refuses_missing_windowless_interpreter(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(ValueError, match="pythonw"):
        workflows.unsteady_action_command_line(str(tmp_path / "python.exe"))


def test_non_windows_action_keeps_explicit_interpreter(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert workflows.unsteady_action_command_line("/opt/python3").startswith('"/opt/python3" ')


@pytest.mark.skipif(sys.platform != "win32", reason="real Windows callback proof")
def test_windowless_clock_callback_writes_state_and_rescue(tmp_path):
    # GOAL033:post:checks:unsteady_rotor_walltime
    from pyflightstream.cases.workflows import (
        WALLTIME_CLOCK_PROGRAM,
        WALLTIME_CLOCK_STATE,
        WALLTIME_CLOCK_TEMPLATE,
        WALLTIME_STOP_SCRIPT,
    )

    program = tmp_path / WALLTIME_CLOCK_PROGRAM
    program.parent.mkdir()
    program.write_text(
        WALLTIME_CLOCK_TEMPLATE.format(
            sim="9001",
            state_name=Path(WALLTIME_CLOCK_STATE).name,
            stop_name=Path(WALLTIME_STOP_SCRIPT).name,
            deadline=0.0,
            stop_text="EXPORT_LOG\nrun.log\nCLOSE_FLIGHTSTREAM\n",
        ),
        encoding="utf-8",
    )
    line = workflows.walltime_clock_command_line()
    # The generated native action string has exactly two quoted arguments.
    import shlex

    args = [item.strip('"') for item in shlex.split(line, posix=False)]
    assert Path(args[0]).name.lower() == "pythonw.exe"
    result = subprocess.run(
        args,
        cwd=tmp_path,
        check=False,
        timeout=15,
        env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0
    state = json.loads((tmp_path / WALLTIME_CLOCK_STATE).read_text())
    assert state["fired"] and state["steps"] == state["stopped_at"]["step"] == 1
    assert (tmp_path / WALLTIME_STOP_SCRIPT).read_text().endswith("CLOSE_FLIGHTSTREAM\n")
