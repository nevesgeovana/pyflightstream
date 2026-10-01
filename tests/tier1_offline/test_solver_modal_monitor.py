"""An owned modal records its text and fails only the process we launched."""

import subprocess

from pyflightstream.run import _executors as run
from pyflightstream.run._solver_windows import _native_windows, owned_solver_dialogs


def test_owned_modal_terminates_solver_and_preserves_diagnostic(tmp_path, monkeypatch):
    # GOAL033:logging:checks:blocking_window_refusal
    # GOAL033:capability_ids:items:G38
    class Process:
        pid = 4321
        returncode = 0
        calls = 0
        killed = False

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("fake-solver", timeout)
            return "solver output", "solver stderr"

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = Process()
    monkeypatch.setattr(run.subprocess, "Popen", lambda *_args, **_kwargs: process)
    observed = []

    def dialogs(pid):
        observed.append(pid)
        return ("FlightStream Error\nThe requested command cannot run",)

    monkeypatch.setattr(run, "_owned_solver_dialogs", dialogs, raising=False)
    result = run._run_with_progress(["fake"], tmp_path, 5, tmp_path / "count", 2, 1)
    assert process.killed, "the solver must not continue or wait forever behind its modal"
    assert observed == [4321]
    assert result[0] != 0 and result[3] is False
    assert "The requested command cannot run" in result[2]
    log = tmp_path / "pyfs-modal-error.log"
    assert "pid=4321" in log.read_text()
    assert "The requested command cannot run" in log.read_text()


def test_an_unwritable_modal_log_and_a_closed_stderr_keep_the_failed_result(tmp_path, monkeypatch):
    """GOAL-034 Q8 CXQ8R4-2: the modal report wrote its log and stderr unguarded,
    so a log that could not be written replaced the failed-execution result."""
    import io
    import sys

    class Process:
        pid = 4321
        returncode = 0
        calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("fake-solver", timeout)
            return "solver output", "solver stderr"

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(run.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(
        run, "_owned_solver_dialogs", lambda pid: ("FlightStream Error\nblocked",), raising=False
    )
    (tmp_path / "pyfs-modal-error.log").mkdir()  # the log cannot be opened for append
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(sys, "stderr", closed)
    result = run._run_with_progress(["fake"], tmp_path, 5, tmp_path / "count", 2, 1)
    assert result[0] == -9 and result[3] is False
    assert "blocked" in result[2]


def test_modal_selection_never_accepts_another_process_or_normal_window():
    from pyflightstream.run._solver_windows import WindowDiagnostic, select_owned_dialogs

    windows = [
        WindowDiagnostic(12, "Error", "other application", "#32770"),
        WindowDiagnostic(34, "FlightStream", "normal main window", "MainWindow"),
        WindowDiagnostic(34, "hidden dialog", "not visible", "#32770", visible=False),
        WindowDiagnostic(34, "FlightStream error", "owned failure", "CustomWindow"),
        WindowDiagnostic(34, "Solver notice", "owned modal", "#32770"),
        WindowDiagnostic(34, "Solver", "custom modal", "CustomWindow", modal=True),
    ]
    assert select_owned_dialogs(34, windows) == (
        "FlightStream error\nowned failure",
        "Solver notice\nowned modal",
        "Solver\ncustom modal",
    )
    assert select_owned_dialogs(0, windows) == ()


def test_owned_solver_dialogs_reads_no_windows_off_windows(monkeypatch):
    """GOAL-034 Q8 QA8-1: the os.name guard at owned_solver_dialogs' own entry.

    Both tests above replace run._owned_solver_dialogs itself, so no tier-1
    test previously called owned_solver_dialogs or _native_windows and their
    non-Windows guards could be deleted with no tier-1 test failing. This
    machine may itself be Windows, so the proof is not "no windows came
    back" (true either way here); it is that ``_native_windows`` -- which
    would report a window if reached -- is never reached at all.
    """
    import pyflightstream.run._solver_windows as solver_windows

    def would_be_native(pid):
        return [solver_windows.WindowDiagnostic(pid, "Error", "would be read on Windows", "#32770")]

    monkeypatch.setattr(solver_windows, "_native_windows", would_be_native)
    monkeypatch.setattr(solver_windows.os, "name", "posix")
    assert owned_solver_dialogs(123) == ()


def test_native_windows_reads_no_windows_off_win32(monkeypatch):
    """GOAL-034 Q8 QA8-1: the sys.platform guard at _native_windows' own entry.

    This machine may itself be Windows, so the proof is not "the returned
    list is empty" (a real, harmless pid 123 would give that either way);
    it is that ``ctypes.WinDLL``, which the guarded code would call, is
    never reached.
    """
    import ctypes

    import pyflightstream.run._solver_windows as solver_windows

    def must_not_be_reached(*_args, **_kwargs):
        raise AssertionError("ctypes.WinDLL must not be reached off win32")

    monkeypatch.setattr(ctypes, "WinDLL", must_not_be_reached, raising=False)
    monkeypatch.setattr(solver_windows.sys, "platform", "linux")
    assert _native_windows(123) == []

    monkeypatch.setattr(solver_windows.sys, "platform", "linux")
    assert _native_windows(123) == []
