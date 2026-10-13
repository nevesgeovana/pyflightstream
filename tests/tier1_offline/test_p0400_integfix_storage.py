"""Tier 1, 0.40.0 integration fixes: storage's free-space through the command line.

A synthetic workspace and recipe; no solver runs.
"""

from __future__ import annotations

from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace import storage as storage_module
from tests.tier1_offline.test_free_space_list import _record, _write


def test_p0400_free_space_prints_a_delete_extensions_refusal(tmp_path, capsys):
    """P0400-EXT-SUBMITTED-PRINT (PFS-2093.006): the refused simulation is printed.

    delete_extensions records a simulation with a SUBMITTED run as refused, as the
    other two modes do, and the command line printed the other two modes' refusals
    only, so the preview said nothing of the simulation it left alone.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(workspace.root)
    _write(workspace.sim_dir("4601") / "datapoints" / "DP-1" / "a.vtk", "v" * 10)
    workspace.append_record(_record("4601").model_copy(update={"status": RunStatus.SUBMITTED}))
    recipe = workspace.root / storage_module.MANAGEMENT_DIR / "m001.toml"
    _write(recipe, '[[delete_extensions]]\nextensions = [".vtk"]\n')
    capsys.readouterr()
    code = matrix_cli.main(["free-space", "m001", "--workspace", str(workspace.root)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "refused sim 4601: a run is still SUBMITTED" in out, out
