"""Exercise bounded native window reads without opening a desktop window."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

from pyflightstream.run import _solver_windows as windows


def test_p0400_review_native_timeout_does_not_turn_a_splash_into_a_dialog(monkeypatch):
    """P0400-REVIEW-NATIVE-SPLASH: the native reader itself must preserve unread text."""
    pid = 7

    def owner(_handle, pointer):
        pointer._obj.value = pid
        return 1

    def class_name(handle, buffer, _length):
        buffer.value = "#32770" if handle == 1 else "Static"
        return len(buffer.value)

    native = SimpleNamespace(
        EnumWindows=Mock(side_effect=lambda callback, parameter: callback(1, parameter)),
        EnumChildWindows=Mock(
            side_effect=lambda handle, callback, parameter: callback(2, parameter)
        ),
        GetWindowThreadProcessId=Mock(side_effect=owner),
        IsWindowVisible=Mock(return_value=True),
        IsWindowEnabled=Mock(return_value=False),
        GetWindow=Mock(return_value=3),
        GetWindowTextW=Mock(return_value=0),
        GetClassNameW=Mock(side_effect=class_name),
        SendMessageTimeoutW=Mock(return_value=0),
    )
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: native, raising=False)
    monkeypatch.setattr(
        ctypes, "WINFUNCTYPE", lambda *args: lambda callback: callback, raising=False
    )
    snapshots = windows._native_windows(pid)
    assert len(snapshots) == 1
    assert windows.select_owned_dialogs(pid, snapshots) == ()
    assert snapshots[0].text == ""
    native.SendMessageTimeoutW.assert_called_once()
