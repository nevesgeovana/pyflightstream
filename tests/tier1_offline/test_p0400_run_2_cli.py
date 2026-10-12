"""Tier 1, 0.40.0 lane run-2: the pyfs-matrix command line and its query output.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import _cli_query_point, cli
from pyflightstream.workspace import CampaignWorkspace


@pytest.mark.parametrize("seconds", ["0", "-1", "inf"])
def test_p0400_collect_interval_takes_seconds_above_zero(tmp_path, capsys, seconds):
    """P0400-COLLECT-INTERVAL (PFS-2081.28): --interval 0 or below is refused at parse time.

    Zero disables the settle check (both observations at one instant), and a
    negative value reached ``time.sleep`` mid-sweep.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    argv = ["collect", "--workspace", str(workspace.root), "--interval", seconds]
    assert cli.main(argv) == 2
    assert "interval (CLI: --interval) takes a number of seconds above 0" in capsys.readouterr().err


def test_p0400_query_alias_survives_a_campaign_named_sim_something():
    """P0400-QUERY-ALIAS (PFS-2094.032): the simulation is the run id's second last part.

    A workspace folder called ``sim_runs`` names the campaign, so the first
    ``sim_`` part of the run id is the campaign, not the simulation.
    """
    aliases = {("2006", "a+02.0_b+00.0"): "2006_1"}
    row = {"run_id": "sim_runs/sim_2006/a+02.0_b+00.0"}
    assert _cli_query_point._annotate(row, aliases)["run_id_alias"] == "2006_1"
    plain = {"run_id": "campaign/sim_2006/a+02.0_b+00.0"}
    assert _cli_query_point._annotate(plain, aliases)["run_id_alias"] == "2006_1"
