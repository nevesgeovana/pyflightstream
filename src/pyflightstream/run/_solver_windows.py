"""Bounded, read-only capture of a local solver's modal diagnostics.

Only windows belonging to the exact launched PID are inspected. No button is
pressed and no window is dismissed. The executor owns the process lifetime.
Non-Windows hosts return no windows. Standard dialogs and titled error windows
are covered; this is not an assertion that every custom GUI can be recognized.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowDiagnostic:
    """A window snapshot, retaining process ownership for a second check."""

    pid: int
    title: str
    text: str
    class_name: str
    visible: bool = True
    modal: bool = False


def select_owned_dialogs(pid: int, windows: Iterable[WindowDiagnostic]) -> tuple[str, ...]:
    """Select visible modal/error snapshots belonging to exactly ``pid``."""
    return tuple(
        "\n".join(part for part in (window.title, window.text) if part)
        or "solver dialog contains no readable text"
        for window in windows
        if pid > 0
        and window.pid == pid
        and window.visible
        and (
            window.modal
            or window.class_name == "#32770"
            or re.search(r"\b(error|fatal|exception)\b", window.title, re.I)
        )
    )


def owned_solver_dialogs(pid: int) -> tuple[str, ...]:
    """Read standard dialogs and error windows of this PID on Windows."""
    if os.name != "nt" or pid <= 0:
        return ()
    return select_owned_dialogs(pid, _native_windows(pid))


def _native_windows(pid: int) -> list[WindowDiagnostic]:
    """Enumerate exact-owned windows with bounded cross-process text reads."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindowEnabled.argtypes = [wintypes.HWND]
    user32.IsWindowEnabled.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    for name in ("GetWindowTextW", "GetClassNameW"):
        function = getattr(user32, name)
        function.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        function.restype = ctypes.c_int
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    windows: list[WindowDiagnostic] = []

    def belongs(handle):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        return owner.value == pid

    @callback_type
    def visit(handle, _parameter):
        if not belongs(handle) or not user32.IsWindowVisible(handle):
            return True
        title = ctypes.create_unicode_buffer(4096)
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(handle, title, len(title))
        user32.GetClassNameW(handle, class_name, len(class_name))
        owner = user32.GetWindow(handle, 4)  # GW_OWNER
        modal = bool(owner and belongs(owner) and not user32.IsWindowEnabled(owner))
        snapshot = WindowDiagnostic(pid, title.value, "", class_name.value, modal=modal)
        if not select_owned_dialogs(pid, [snapshot]):
            return True
        texts: list[str] = []
        visited = 0

        @callback_type
        def child(control, _parameter):
            nonlocal visited
            if not belongs(control):
                return True
            visited += 1
            if visited > 32:
                texts.append("[remaining controls omitted after 32 bounded reads]")
                return False
            buffer = ctypes.create_unicode_buffer(4096)
            result = ctypes.c_size_t()
            # GetWindowText does not read another process's control text.
            # WM_GETTEXT with SMTO_ABORTIFHUNG|BLOCK keeps this read bounded.
            ok = user32.SendMessageTimeoutW(
                control,
                0x000D,
                len(buffer),
                ctypes.addressof(buffer),
                0x0003,
                100,
                ctypes.byref(result),
            )
            if not ok:
                texts.append("[control text unavailable or timed out]")
            elif buffer.value and buffer.value not in texts:
                texts.append(buffer.value)
            return True

        user32.EnumChildWindows(handle, child, 0)
        windows.append(
            WindowDiagnostic(pid, title.value, "\n".join(texts), class_name.value, modal=modal)
        )
        return True

    if not user32.EnumWindows(visit, 0):
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
    return windows
