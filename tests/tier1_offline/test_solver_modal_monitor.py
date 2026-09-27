# GEOVERSE_HEADER
# file_version: 1.0.1
# last_modified_at: 2026-09-27T20:59:34.956Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.run]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""An owned modal records its text and fails only the process we launched."""

import subprocess

from pyflightstream import run


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
