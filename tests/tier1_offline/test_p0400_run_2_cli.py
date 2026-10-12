"""Tier 1, 0.40.0 lane run-2: the pyfs-matrix command line and its query output.

Every fixture is synthetic.
"""

from __future__ import annotations

from pyflightstream.run import _cli_query_point


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
