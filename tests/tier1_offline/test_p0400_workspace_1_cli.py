"""P0400-WSCLI: `pyfs-workspace` refusals (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

from pyflightstream.workspace.cli import main as workspace_cli


def test_p0400_wscli_init_on_a_bad_root_is_a_refusal_with_exit_2(tmp_path, capsys):
    """P0400-WSCLI (PFS-2095.059): init refuses a root that is a file, like its siblings."""
    taken = tmp_path / "taken"
    taken.write_text("not a folder", encoding="utf-8")
    assert workspace_cli(["init", str(taken)]) == 2
    assert "taken" in capsys.readouterr().err
