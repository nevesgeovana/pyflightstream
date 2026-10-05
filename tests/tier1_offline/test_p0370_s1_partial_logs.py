"""Partial log loss in a steady job must not strand its surviving outputs."""

import json

from pyflightstream.workspace._missing_log import absent_solver_logs
from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace, pyfs


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


def test_a_steady_job_missing_a_point_output_is_not_admitted(tmp_path, capsys):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R7): collect waits and names the missing output.

    A steady job of two points whose logs never came back, and the second
    point's loads file gone too: collect admits neither point as
    RAN_MISSING_LOG, and says which output it waits for. The control puts the
    file back and the same collect admits both.
    """
    workspace = grouped_workspace(
        tmp_path / "ws", mode="alone", logs=False, collect=False, sims=("7002",)
    )
    (lost,) = workspace.root.rglob("V0300RE120AL+020.txt")
    kept = lost.read_bytes()
    lost.unlink()
    code, said = pyfs(["collect", "--no-post"], workspace.root, capsys)
    assert code != 0, said
    waiting = [line for line in said.splitlines() if "WAITING" in line]
    assert len(waiting) == 1 and "V0300RE120AL+020.txt" in waiting[0], said
    rows = json.loads(workspace.manifest_path.read_text("utf-8"))
    points = [entry["status"] for row in rows for entry in row.get("points_ran") or [row]]
    assert points == ["SUBMITTED", "SUBMITTED"], points
    # The control: the same files with the output back are admitted.
    lost.write_bytes(kept)
    code, said = pyfs(["collect", "--no-post"], workspace.root, capsys)
    assert code == 0, said
    rows = json.loads(workspace.manifest_path.read_text("utf-8"))
    points = [entry["status"] for row in rows for entry in row.get("points_ran") or [row]]
    assert points == ["RAN_MISSING_LOG", "RAN_MISSING_LOG"], points
