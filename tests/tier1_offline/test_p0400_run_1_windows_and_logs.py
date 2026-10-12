"""Tier 1, 0.40.0 lane run-1: the window watcher's splash rule and the G06 log scan.

Window snapshots and log files written by hand; no solver and no GUI.
"""

from __future__ import annotations

from pyflightstream.run._solver_windows import WindowDiagnostic, select_owned_dialogs
from pyflightstream.run._wake_edge_verdict import (
    ACTUATOR_PROFILE_REFUSALS,
    actuator_profile_verdict,
    collected_log_texts,
)

UNREAD = "[control text unavailable or timed out]"


def test_p0400_a_splash_whose_text_read_timed_out_still_asks_nothing():
    """P0400-SPLASH-UNREAD-TEXT (PFS-2094.017): the startup splash, its one control unread.

    The watcher wrote a placeholder into the window's text when a control read timed out,
    so the splash (class #32770, no title, one image control, no button) read as a window
    that says something and the solver was killed. What was not read is kept apart.
    """
    splash = WindowDiagnostic(
        pid=7,
        title="",
        text="",
        class_name="#32770",
        modal=True,
        controls=("Static",),
        unread=(UNREAD,),
    )
    assert select_owned_dialogs(7, [splash]) == ()
    # The control: a dialog with a button is a dialog, and what was not read is said.
    dialog = WindowDiagnostic(
        pid=7,
        title="",
        text="",
        class_name="#32770",
        modal=True,
        controls=("Static", "Button"),
        unread=(UNREAD,),
    )
    assert select_owned_dialogs(7, [dialog]) == (UNREAD,)


def test_p0400_the_g06_scan_keeps_the_refusal_lines_and_not_whole_logs(tmp_path):
    """P0400-G06-SCAN-STREAMED (PFS-2101.003): a long step export and a log with the refusal.

    Every collected .txt was read whole and every text kept in memory together; only the
    lines that carry a G06 sentence, and the line after each, are kept now, and the verdict
    reads them as it read the whole text.
    """
    filler = "".join(f"step {index} residual 1.0e-3\n" for index in range(5000))
    refusal = f"{ACTUATOR_PROFILE_REFUSALS[1]}\nC:/w/prop.txt\n"
    (tmp_path / "log.txt").write_text(filler + refusal + filler, encoding="utf-8")
    (tmp_path / "step_iteration=12.txt").write_text(filler, encoding="utf-8")
    texts = collected_log_texts(tmp_path, ["log.txt", "step_iteration=12.txt"], declared=[])
    assert texts == [refusal], [len(text) for text in texts]
    assert actuator_profile_verdict(*texts) is not None
