"""Partial log loss in a steady job must not strand its surviving outputs."""

from pyflightstream.workspace._missing_log import absent_solver_logs


def test_one_surviving_log_does_not_hide_a_missing_sibling(tmp_path):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R1): decide log loss per point."""
    for name in ("a.txt", "b.txt", "a_log.txt"):
        (tmp_path / name).write_text("settled output", encoding="utf-8")
    assert absent_solver_logs(
        ["a.txt", "a_log.txt", "b.txt", "b_log.txt"],
        ["a_log.txt", "b_log.txt"],
        tmp_path,
    ) == ("b_log.txt",)


def test_a_missing_non_log_output_still_prevents_admission(tmp_path):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R7): partial outputs are not admitted."""
    (tmp_path / "a.txt").write_text("settled output", encoding="utf-8")
    assert (
        absent_solver_logs(
            ["a.txt", "a_log.txt", "b.txt", "b_log.txt"],
            ["a_log.txt", "b_log.txt"],
            tmp_path,
        )
        == ()
    )
