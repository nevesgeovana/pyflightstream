"""Tier 1: local executor subprocess handling, without FlightStream.

A FakeSolver subclass replaces the argv with a Python one-liner, so
the subprocess mechanics (return codes, timeout, log capture, working
directory) are exercised exactly as FlightStream would exercise them.
"""

import sys
from pathlib import Path

import pytest

from pyflightstream.run import ExecutionResult, ExecutorConfigurationError, LocalExecutor


class FakeSolver(LocalExecutor):
    def __init__(self, code: str):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.code = code

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", self.code]


def test_argv_follows_the_documented_headless_mechanism(tmp_path):
    exe = tmp_path / "FlightStream.exe"
    exe.write_bytes(b"")
    executor = LocalExecutor(fs_exe=exe)
    script = Path("C:/runs/point.txt")
    argv = executor._argv(script)
    assert argv == [str(exe), "-hidden", "--script", str(script)]
    visible = LocalExecutor(fs_exe=exe, hidden=False)
    assert "-hidden" not in visible._argv(Path("point.txt"))


def test_missing_executable_fails_at_construction(tmp_path):
    with pytest.raises(ExecutorConfigurationError, match="not found"):
        LocalExecutor(fs_exe=tmp_path / "nowhere" / "FlightStream.exe")


def test_successful_run_reports_zero_and_no_log(tmp_path):
    executor = FakeSolver("print('solver done')")
    result = executor.run_script(tmp_path / "point.txt", working_dir=tmp_path)
    assert result.return_code == 0
    assert not result.failed
    assert not result.timed_out
    assert result.log_text is None
    assert "solver done" in result.stdout
    assert result.wall_time_s > 0


def test_failed_run_captures_the_hidden_mode_log(tmp_path):
    code = (
        "import pathlib, sys; "
        "pathlib.Path('FlightStreamLog.txt').write_text('Unknown command X'); "
        "sys.exit(2)"
    )
    executor = FakeSolver(code)
    result = executor.run_script(tmp_path / "point.txt", working_dir=tmp_path)
    assert result.return_code == 2
    assert result.failed
    assert "Unknown command X" in result.log_text


def test_timeout_kills_the_process_and_reports_it(tmp_path):
    executor = FakeSolver("import time; time.sleep(30)")
    result = executor.run_script(tmp_path / "point.txt", working_dir=tmp_path, timeout_s=0.5)
    assert result.timed_out
    assert result.return_code is None
    assert result.failed
    assert result.wall_time_s < 25


def test_execution_result_failed_property():
    ok = ExecutionResult(0, 1.0, False, None, "", "")
    bad = ExecutionResult(3, 1.0, False, None, "", "")
    assert not ok.failed
    assert bad.failed
