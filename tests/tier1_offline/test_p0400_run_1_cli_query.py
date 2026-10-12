"""Tier 1, 0.40.0 lane run-1: the query verbs ``status`` and ``show``, in process.

Synthetic workspaces and records; no solver runs.
"""

from __future__ import annotations

from pyflightstream.run import cli
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline import test_p0350_run_id_alias as alias_tests


def test_p0400_status_additional_refuses_the_selection_it_does_not_read(tmp_path, capsys):
    """P0400-STATUS-ADDITIONAL-SELECTION (PFS-2094.030): ``--sims`` with ``--additional``.

    The register listing read no selection and printed it whole, silently; the selection
    flags are now refused by name, and the listing alone still runs.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    root = str(workspace.root)
    code = cli.main(["status", "--additional", "--sims", "2006", "--failed", "--workspace", root])
    err = capsys.readouterr().err
    assert code == 2 and "--sims, --failed" in err and "--additional" in err
    assert cli.main(["status", "--additional", "--workspace", root]) == 0


def test_p0400_show_names_the_point_it_cannot_find(tmp_path, capsys):
    """P0400-SHOW-UNKNOWN-POINT (PFS-2100.005, PFS-2100.006): ``show 2006 --point NOPE``.

    The refusal read ``run (CLI: --run): '' names no effective recorded point``, naming a
    flag show does not take and an empty string. It now names the simulation and the point
    typed, and lists the simulation's points with their aliases.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    for tag in ("AL+000", "AL+020"):
        workspace.append_record(alias_tests._record("2006", f"warm/sim_2006/{tag}"))
    root = str(workspace.root)
    code = cli.main(["show", "2006", "--point", "NOPE", "--workspace", root])
    err = capsys.readouterr().err
    assert code == 1
    assert "'2006'" in err and "'NOPE'" in err and "--run" not in err, err
    assert "AL+000 (2006_1)" in err and "AL+020 (2006_2)" in err, err
    assert cli.main(["show", "2006", "--point", "AL+020", "--workspace", root]) == 0
