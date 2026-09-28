"""Tier 1 offline: the watcher spares a window that asks nothing (0.30.0).

MEASURED, not assumed: FlightStream 26.124 launched with its GUI (a matrix row
stating HIDDEN 0) shows for about two seconds a startup splash, class #32770,
modal over its main window (class ChimeraMain, which the watcher never
selected), with no title, no readable text, one Static image control and no
button (the no-solve probe of 2026-09-28, 700x525). Until 0.30.0 the watcher
killed every such run within 2 s as "solver dialog contains no readable text".
The owner chose, on 2026-09-28, to spare exactly that window and nothing else:
a title, any readable text or any button still makes a window a dialog.
"""

from __future__ import annotations

from pyflightstream.run._solver_windows import (
    WindowDiagnostic,
    asks_nothing,
    select_owned_dialogs,
    select_spared_windows,
)

PID = 4242

#: The window the probe recorded, as the watcher reads it.
SPLASH = WindowDiagnostic(PID, "", "", "#32770", modal=True, controls=("Static",))


def test_the_measured_splash_asks_nothing_and_is_spared():
    assert asks_nothing(SPLASH)
    assert select_owned_dialogs(PID, [SPLASH]) == ()
    assert select_spared_windows(PID, [SPLASH]) == (
        "class #32770, no title, no text, no button; controls Static",
    )


def test_a_textless_window_with_a_button_is_still_a_dialog():
    stuck = WindowDiagnostic(PID, "", "", "#32770", modal=True, controls=("Static", "Button"))
    assert select_owned_dialogs(PID, [stuck]) == ("solver dialog contains no readable text",)
    assert select_spared_windows(PID, [stuck]) == ()


def test_a_titled_or_texted_dialog_is_still_a_dialog():
    titled = WindowDiagnostic(PID, "FlightStream", "", "#32770", modal=True)
    texted = WindowDiagnostic(PID, "", "Failed to read file", "#32770", modal=True)
    unreadable = WindowDiagnostic(
        PID, "", "[control text unavailable or timed out]", "#32770", modal=True
    )
    assert select_owned_dialogs(PID, [titled, texted, unreadable]) == (
        "FlightStream",
        "Failed to read file",
        "[control text unavailable or timed out]",
    )


def test_the_splash_of_another_process_is_neither_selected_nor_spared():
    other = WindowDiagnostic(PID + 1, "", "", "#32770", modal=True, controls=("Static",))
    assert select_owned_dialogs(PID, [other]) == ()
    assert select_spared_windows(PID, [other]) == ()


def test_the_rule_is_what_spares_the_splash(monkeypatch):
    """MUTANT: without the asks-nothing rule the splash is killed again."""
    import pyflightstream.run._solver_windows as windows

    monkeypatch.setattr(windows, "asks_nothing", lambda window: False)
    assert windows.select_owned_dialogs(PID, [SPLASH]) == (
        "solver dialog contains no readable text",
    )
