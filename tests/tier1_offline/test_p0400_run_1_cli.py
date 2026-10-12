"""Tier 1, 0.40.0 lane run-1: the ``pyfs-matrix`` parser (``_cli_parsers``), in process.

Synthetic workspaces; no solver runs.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import cli
from pyflightstream.run._cli_parsers import _build_parser, parsed
from pyflightstream.workspace import CampaignWorkspace, costs, hpc


def test_p0400_hpc_and_cost_file_belong_to_the_command_that_named_them(tmp_path, capsys):
    """P0400-SELECTION-PER-INVOCATION (PFS-2094.008): no leak into a later in-process command.

    ``--hpc`` and ``--cost-file`` were selected by argparse's type callable and never reset,
    so a second ``main`` in the same process ran under the first one's profile.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    argv = ["plan", str(tmp_path / "absent.fs"), "--workspace", str(workspace.root)]
    cli.main([*argv, "--hpc", "h9", "--cost-file", "c9"])
    capsys.readouterr()
    assert hpc._SELECTED_HPC.get() is None
    assert costs._SELECTED_COST_FILE.get() is None


def test_p0400_restore_reads_a_matrix_path_as_rebuild_and_post_do(tmp_path):
    """P0400-MATRIX-OPTION-FORM (PFS-2094.051): ``restore --matrix`` takes a path or a stem.

    ``rebuild`` and ``post`` read ``--matrix`` as a path and take its stem; ``restore``
    passed the text through, so a path named no archived matrix.
    """
    workspace = str(tmp_path)
    for given in ("inputs/matrices/m001.fs", "m001"):
        args = parsed(
            _build_parser(), ["restore", "plan", "--matrix", given, "--workspace", workspace]
        )
        assert args.matrix == "m001"


@pytest.mark.parametrize(
    "argv",
    [["space-in-use", "--top", "-1"], ["space-in-use", "--top", "0"], ["collect", "--rounds", "0"]],
)
def test_p0400_a_count_below_one_is_refused_naming_its_flag(tmp_path, capsys, argv):
    """P0400-COUNT-AT-LEAST-ONE (PFS-2097.009): ``--top -1`` showed all rows but one and
    mislabelled the hidden count; ``--top`` and ``--rounds`` now refuse a count below 1."""
    with pytest.raises(SystemExit) as raised:
        cli.main([*argv, "--workspace", str(tmp_path)])
    assert raised.value.code == 2
    assert f"{argv[1]} takes a whole number of at least 1" in capsys.readouterr().err
