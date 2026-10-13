"""P0400-WSCLI: `pyfs-workspace` refusals (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import pytest

from pyflightstream.workspace.cli import _build_parser
from pyflightstream.workspace.cli import main as workspace_cli

pytestmark = pytest.mark.requirement("P0400-WSCLI")


def test_p0400_wscli_init_on_a_bad_root_is_a_refusal_with_exit_2(tmp_path, capsys):
    """P0400-WSCLI (PFS-2095.059): init refuses a root that is a file, like its siblings."""
    taken = tmp_path / "taken"
    taken.write_text("not a folder", encoding="utf-8")
    assert workspace_cli(["init", str(taken)]) == 2
    assert "taken" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["init", "migrate-geometries"])
def test_p0400_wscli_every_command_accepts_the_workspace_option(tmp_path, command):
    """P0400-WSCLI (PFS-2089.004): init and migrate-geometries accept --workspace."""
    args = _build_parser().parse_args([command, "--workspace", str(tmp_path)])
    assert args.workspace == str(tmp_path)


def test_p0400_wscli_two_different_campaigns_are_refused(tmp_path, capsys):
    """P0400-WSCLI (PFS-2089.004): --workspace and a different positional root, exit 2."""
    first, second = tmp_path / "a", tmp_path / "b"
    assert workspace_cli(["init", str(first), "--workspace", str(second)]) == 2
    assert "named twice" in capsys.readouterr().err
    assert not first.exists() and not second.exists()


def test_p0400_wscli_init_uses_the_named_workspace(tmp_path):
    """P0400-WSCLI (PFS-2089.004): --workspace routes init into the selected campaign."""
    target = tmp_path / "campaign"
    assert workspace_cli(["init", "--workspace", str(target)]) == 0
    assert (target / "inputs").is_dir()
