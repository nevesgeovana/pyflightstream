"""Start a visible solver window minimized, so it does not cover the terminal.

A run that is not hidden (no ``-hidden`` flag) shows the solver's window. On
Windows it is launched with the show state SW_SHOWMINNOACTIVE (minimized, no
keyboard focus). A Qt application may ignore the start-up show state, so a
daemon thread also minimizes the top-level visible windows of the solver's
process. Hidden runs and other platforms are unchanged. Nothing here raises:
a failure leaves the window as the solver opened it.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

_LOG = logging.getLogger(__name__)

#: ShowWindow command SW_SHOWMINNOACTIVE: minimized, the active window unchanged.
SW_SHOWMINNOACTIVE = 7
#: Seconds between two looks for the solver's windows, and how long the look lasts.
POLL_S = 0.5
WATCH_LIMIT_S = 60.0


def launch_options(argv: Sequence[str], platform: str | None = None) -> dict[str, Any]:
    """Return the extra ``Popen`` keywords for this launch: a minimized start-up, or none.

    Only a Windows launch without ``-hidden`` gets a ``STARTUPINFO``.
    """
    if (platform or sys.platform) != "win32" or "-hidden" in argv:
        return {}
    info = subprocess.STARTUPINFO()  # type: ignore[attr-defined,unused-ignore]
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined,unused-ignore]
    info.wShowWindow = SW_SHOWMINNOACTIVE
    return {"startupinfo": info}


def _native_top_windows(pid: int) -> list[int]:
    """Return the handles of the visible top-level windows of ``pid`` (Windows only)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    found: list[int] = []

    @callback_type
    def visit(handle, _parameter):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(handle):
            found.append(int(handle))
        return True

    user32.EnumWindows(visit, 0)
    return found


def _native_minimize(handle: int) -> None:
    """Minimize one window without activating it (Windows only)."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow(handle, SW_SHOWMINNOACTIVE)


def minimize_once(
    pid: int,
    done: set[int],
    list_windows: Callable[[int], Sequence[int]] = _native_top_windows,
    minimize: Callable[[int], None] = _native_minimize,
) -> int:
    """Minimize each visible top-level window of ``pid`` not yet in ``done``; return how many.

    Never raises: an error is logged once at debug level and ignored.
    """
    count = 0
    try:
        for handle in list_windows(pid):
            if handle in done:
                continue
            done.add(handle)
            minimize(handle)
            count += 1
    except Exception as error:  # noqa: BLE001 - a window nicety must never fail a run
        _LOG.debug("could not minimize the solver window of pid %s: %s", pid, error)
    return count


def keep_minimized(
    process: Any,
    argv: Sequence[str],
    *,
    list_windows: Callable[[int], Sequence[int]] = _native_top_windows,
    minimize: Callable[[int], None] = _native_minimize,
    sleep: Callable[[float], None] = time.sleep,
    platform: str | None = None,
    start: bool = True,
) -> threading.Thread | None:
    """Poll for the solver's windows and minimize them; return the daemon thread, or None.

    Nothing starts for a hidden launch or off Windows. The thread looks every
    :data:`POLL_S` seconds for up to :data:`WATCH_LIMIT_S` and stops when the
    process has exited.
    """
    if (platform or sys.platform) != "win32" or "-hidden" in argv:
        return None

    def watch() -> None:
        try:
            pid = int(process.pid)
            done: set[int] = set()
            for _ in range(int(WATCH_LIMIT_S / POLL_S)):
                if process.poll() is not None:
                    return
                minimize_once(pid, done, list_windows, minimize)
                sleep(POLL_S)
        except Exception as error:  # noqa: BLE001 - never raises
            _LOG.debug("the solver window watch stopped: %s", error)

    thread = threading.Thread(target=watch, name="pyfs-minimize", daemon=True)
    if start:
        thread.start()
    return thread
