"""A visible solver run starts its window minimized and without focus; a hidden run is unchanged."""

import subprocess

import pytest

from pyflightstream.run import _executors
from pyflightstream.run._minimize import (
    SW_SHOWMINNOACTIVE,
    keep_minimized,
    launch_options,
    minimize_once,
)

windows_only = pytest.mark.skipif(
    not hasattr(subprocess, "STARTUPINFO"), reason="STARTUPINFO exists only on Windows"
)


@windows_only
def test_p0530_a_visible_launch_asks_for_a_minimized_no_focus_start():
    options = launch_options(["FlightStream.exe", "-script", "run.fs"], platform="win32")
    info = options["startupinfo"]
    assert info.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert info.wShowWindow == SW_SHOWMINNOACTIVE == 7


def test_p0530_a_hidden_launch_and_a_non_windows_launch_pass_nothing():
    assert launch_options(["FlightStream.exe", "-hidden", "-script", "r.fs"], "win32") == {}
    assert launch_options(["FlightStream.exe", "-script", "r.fs"], platform="linux") == {}
    assert keep_minimized(object(), ["FlightStream.exe", "-hidden"], platform="win32") is None
    assert keep_minimized(object(), ["FlightStream.exe"], platform="linux") is None


def test_p0530_the_fallback_minimizes_each_window_of_the_pid_once():
    seen, minimized = [], []

    def windows(pid):
        seen.append(pid)
        return [11, 12]

    done: set[int] = set()
    assert minimize_once(77, done, windows, minimized.append) == 2
    assert minimize_once(77, done, windows, minimized.append) == 0
    assert seen == [77, 77] and minimized == [11, 12]


def test_p0530_the_fallback_ignores_errors():
    def broken(_pid):
        raise OSError("no desktop")

    assert minimize_once(5, set(), broken, lambda _h: None) == 0

    def refuses(_handle):
        raise OSError("denied")

    assert minimize_once(5, set(), lambda _p: [1], refuses) == 0


def test_p0530_the_watch_stops_when_the_process_exits():
    class Process:
        pid = 9
        polls = 0

        def poll(self):
            self.polls += 1
            return None if self.polls < 3 else 0

    minimized = []
    thread = keep_minimized(
        Process(),
        ["FlightStream.exe"],
        list_windows=lambda _pid: [4],
        minimize=minimized.append,
        sleep=lambda _s: None,
        platform="win32",
        start=False,
    )
    assert thread is not None and thread.daemon
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    assert minimized == [4]


def test_p0530_both_popen_sites_pass_the_launch_options(tmp_path, monkeypatch):
    calls = []

    class Process:
        pid = 1
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def communicate(self, timeout=None):
            return "", ""

        def kill(self):
            pass

    def popen(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return Process()

    monkeypatch.setattr(_executors.subprocess, "Popen", popen)
    for argv in (["fs.exe", "-script", "a.fs"], ["fs.exe", "-hidden", "-script", "a.fs"]):
        _executors._run_with_progress(argv, tmp_path, 5, tmp_path / "count", None, 0)
    visible, hidden = calls
    assert ("startupinfo" in visible[1]) == hasattr(subprocess, "STARTUPINFO")
    assert "startupinfo" not in hidden[1]
