"""Tier 1, 0.40.0 lane run-1: what a point's record says, and what reconstruct reads back.

A campaign run with the stub solver of the run tests; no solver runs.
"""

from __future__ import annotations

import hashlib

from pyflightstream.run import reconstruct, run_campaign
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_run_campaign import (
    WRITES_LOADS,
    StubSolver,
    converged,
    make_campaign,
    steady_recipe,
)


def test_p0400_reconstruct_finds_an_inherited_probe_layout_where_it_lives(tmp_path):
    """P0400-RECONSTRUCT-PROBE-LAYOUT (PFS-2103.027): a key with a folder part.

    A continuation that inherits a probe field layout records it under
    ``profiles/<sim>_probe_points.csv``, relative to the simulation folder; reconstruct
    looked for it in the point's own folder and called it missing while it was on disk.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    record = workspace.read_manifest()[0]
    layout = workspace.sim_dir("9001") / "profiles" / "9001_probe_points.csv"
    layout.parent.mkdir(parents=True, exist_ok=True)
    layout.write_text("x,y,z\n0,0,0\n", encoding="utf-8")
    key = "profiles/9001_probe_points.csv"
    digest = hashlib.sha256(layout.read_bytes()).hexdigest()
    record = record.model_copy(update={"inputs_sha256": {**record.inputs_sha256, key: digest}})
    rebuilt = reconstruct(record, workspace=workspace)
    assert rebuilt.verified[f"inputs/{key}"] == "match", rebuilt.verified
    assert rebuilt.faithful
