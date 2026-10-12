"""Tier 1, 0.40.0 lane run-1: the run id alias ``<sim>_<index>`` (FR-395).

Every fixture is synthetic: a ``runs.json`` and ``plan.json`` written by hand, or the
two-simulation steady matrix of the 0.34.0 tests with a stub for the solver.
"""

from __future__ import annotations

import json

from pyflightstream.run._alias import read_alias, split_typed_ids


def _rows(root, rows):
    (root / "runs.json").write_text(json.dumps(rows), encoding="utf-8")


def test_p0400_a_known_simulation_id_with_an_underscore_is_not_an_alias(tmp_path):
    """P0400-ALIAS-SIM-UNDERSCORE (PFS-2094.028): ``2006_1`` beside ``2006`` names the simulation.

    Simulation ids may hold an underscore; a destroying verb read ``2006_1`` as point 1 of
    simulation 2006, so ``mark-failed --sims 2006_1`` marked the wrong simulation's point.
    """
    assert read_alias("2006_1", {"2006", "2006_1"}) is None
    assert read_alias("2006_1", {"2006"}) == ("2006", 1)
    _rows(
        tmp_path,
        [
            {"run_id": "warm/sim_2006/P1", "sim_id": "2006", "status": "CONVERGED"},
            {"run_id": "warm/sim_2006_1/P1", "sim_id": "2006_1", "status": "CONVERGED"},
        ],
    )
    assert split_typed_ids(["2006_1"], tmp_path) == (["2006_1"], {})
    assert split_typed_ids(["2006_1"], tmp_path, whole_only=True) == (["2006_1"], {})
