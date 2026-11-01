"""Bounded, read-only capture of a local solver's modal diagnostics.

Only windows belonging to the exact launched PID are inspected. No button is
pressed and no window is dismissed. The executor owns the process lifetime.
Non-Windows hosts return no windows. Standard dialogs and titled error windows
are covered; this is not an assertion that every custom GUI can be recognized.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WindowDiagnostic:
    """A window snapshot, retaining process ownership for a second check."""

    pid: int
    title: str
    text: str
    class_name: str
    visible: bool = True
    modal: bool = False
    #: Window classes of the controls inside (``Button``, ``Static``, ...),
    #: read with the text; empty when they were not read.
    controls: tuple[str, ...] = ()
    #: What could NOT be read (a control whose text read timed out, controls left
    #: unread past the bound), kept apart from ``text`` so that a window busy
    #: starting up is not taken for one that says something (PFS-2094.017).
    unread: tuple[str, ...] = ()


#: FlightStream 26.124's GUI startup splash asks nothing: it is a modal
#: class #32770 window with no title, readable text or button, one image
#: control and a 700x525 extent. It closes itself after about two seconds.
#: Spare this splash; a title, readable text or button identifies a dialog.
def asks_nothing(window: WindowDiagnostic) -> bool:
    """Say whether a window has no title, no readable text and no button."""
    return (
        not window.title.strip()
        and not window.text.strip()
        and not any(name.lower() == "button" for name in window.controls)
    )


def _could_be_a_dialog(pid: int, window: WindowDiagnostic) -> bool:
    return (
        pid > 0
        and window.pid == pid
        and window.visible
        and bool(
            window.modal
            or window.class_name == "#32770"
            or re.search(r"\b(error|fatal|exception)\b", window.title, re.I)
        )
    )


def select_owned_dialogs(pid: int, windows: Iterable[WindowDiagnostic]) -> tuple[str, ...]:
    """Select visible modal/error snapshots belonging to exactly ``pid``.

    A window that asks nothing (:func:`asks_nothing`) is not selected.
    """
    return tuple(
        "\n".join(part for part in (window.title, window.text, *window.unread) if part)
        or "solver dialog contains no readable text"
        for window in windows
        if _could_be_a_dialog(pid, window) and not asks_nothing(window)
    )


def select_spared_windows(pid: int, windows: Iterable[WindowDiagnostic]) -> tuple[str, ...]:
    """Describe the windows the watcher spared because they ask nothing."""
    return tuple(
        f"class {window.class_name}, no title, no text, no button; controls "
        f"{', '.join(window.controls) or 'none'}"
        for window in windows
        if _could_be_a_dialog(pid, window) and asks_nothing(window)
    )


def spared_solver_windows(pid: int) -> tuple[str, ...]:
    """Describe this PID's windows the watcher spares because they ask nothing."""
    if os.name != "nt" or pid <= 0:
        return ()
    return select_spared_windows(pid, _native_windows(pid))


def owned_solver_dialogs(pid: int) -> tuple[str, ...]:
    """Read standard dialogs and error windows of this PID on Windows."""
    if os.name != "nt" or pid <= 0:
        return ()
    return select_owned_dialogs(pid, _native_windows(pid))


def _declare_user32_signatures(user32: Any, callback_type: Any) -> None:
    """Declare the argument and result types of the user32 calls the window walk makes."""
    import ctypes
    from ctypes import wintypes

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


def _native_windows(pid: int) -> list[WindowDiagnostic]:
    """Enumerate exact-owned windows with bounded cross-process text reads."""
    # The platform check is written the way the type checker narrows it: on a
    # non-Windows host the Windows-only ctypes names below do not exist.
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _declare_user32_signatures(user32, callback_type)
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
        if not _could_be_a_dialog(pid, snapshot):
            return True
        texts: list[str] = []
        unread: list[str] = []
        controls: list[str] = []
        visited = 0

        @callback_type
        def child(control, _parameter):
            nonlocal visited
            if not belongs(control):
                return True
            visited += 1
            if visited > 32:
                unread.append("[remaining controls omitted after 32 bounded reads]")
                return False
            kind = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(control, kind, len(kind))
            controls.append(kind.value)
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
                if "[control text unavailable or timed out]" not in unread:
                    unread.append("[control text unavailable or timed out]")
            elif buffer.value and buffer.value not in texts:
                texts.append(buffer.value)
            return True

        user32.EnumChildWindows(handle, child, 0)
        windows.append(
            WindowDiagnostic(
                pid,
                title.value,
                "\n".join(texts),
                class_name.value,
                modal=modal,
                controls=tuple(controls),
                unread=tuple(unread),
            )
        )
        return True

    if not user32.EnumWindows(visit, 0):
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
    return windows


# _minimize.py merged here
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
