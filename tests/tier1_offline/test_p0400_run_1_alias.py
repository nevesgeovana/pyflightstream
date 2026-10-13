"""Tier 1, 0.40.0 lane run-1: the run id alias ``<sim>_<index>`` (FR-395).

Every fixture is synthetic: a ``runs.json`` and ``plan.json`` written by hand, or the
two-simulation steady matrix of the 0.34.0 tests with a stub for the solver.
"""

from __future__ import annotations

import json
import warnings
from types import SimpleNamespace

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run._alias import (
    failure_alias_lines,
    planned_in_workspace,
    read_alias,
    selection_with_aliases,
    split_typed_ids,
)
from pyflightstream.run._cli_print import _alias_block
from pyflightstream.run._cli_query_point import _aliases
from pyflightstream.run._ids import narrow_to_selection, whole_sweeps
from pyflightstream.run._plan import plan_campaign
from pyflightstream.workspace.ledger import read_ledger
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_p0340_run_usability import _names, _two_simulations


def _rows(root, rows):
    (root / "runs.json").write_text(json.dumps(rows), encoding="utf-8")


def test_p0400_a_known_simulation_id_with_an_underscore_is_not_an_alias(tmp_path):
    # Verifies FR-395.
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


def test_p0400_the_failure_alias_is_the_one_every_reader_resolves(tmp_path):
    """P0400-ALIAS-ONE-READING (PFS-2094.004, PFS-2089.008): records out of sweep order.

    Alpha 0 and 4 are recorded, the matrix gains alpha 2, and the resumed run fails it. The
    failure line named ``2006_3`` from the record order while ``mark-failed``, ``show`` and
    the plan read ``2006_3`` as alpha 4. Every reader now builds its planned order with
    one function, and the failure line names ``2006_2``, which resolves back to alpha 2.
    """
    plan = {
        "points": [
            {"sim_id": "2006", "run_id": f"warm/sim_2006/{tag}"} for tag in ("A0", "A2", "A4")
        ]
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    rows = [
        {"run_id": f"warm/sim_2006/{tag}", "sim_id": "2006", "status": status}
        for tag, status in (("A0", "CONVERGED"), ("A4", "CONVERGED"), ("A2", "FAILED_EXECUTION"))
    ]
    _rows(tmp_path, rows)
    failed = SimpleNamespace(sim_id="2006", run_id="warm/sim_2006/A2")
    assert failure_alias_lines([failed], rows, tmp_path) == ["  alias 2006_2 = warm/sim_2006/A2"]
    assert split_typed_ids(["2006_2"], tmp_path) == ([], {"2006": ["A2"]})
    assert _aliases(read_ledger(tmp_path))["2006_2"] == ("2006", "A2")
    assert planned_in_workspace(tmp_path, rows) == {"2006": ["A0", "A2", "A4"]}


def test_p0400_a_plan_of_a_selection_numbers_aliases_against_the_whole_sweep(tmp_path, monkeypatch):
    """P0400-ALIAS-WHOLE-SWEEP (PFS-2094.034, PFS-2094.029): plan the third point alone.

    The plan narrowed to ``--points <third>`` printed ``5002_1`` beside it and wrote only it
    into ``plan.json``, so ``show`` and ``mark-failed`` read ``5002_1`` as the third point
    while ``run --points 5002_1`` ran the first. Given the whole sweep, the plan prints
    ``5002_3`` and ``plan.json`` carries the whole sweep for every later reader.
    """
    workspace, matrix, _stub = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        resolved = resolve_matrix(
            matrix,
            workspace,
            name="warm",
            fs_version="26.120",
            recipes={},
            ignore_missing_families=True,
        )
        whole = whole_sweeps(resolved)
        narrowed = narrow_to_selection(resolved, ["5002"], [names[2]], workspace)
        plan = plan_campaign(narrowed.campaign, workspace, matrix_path=matrix, planned_order=whole)
    assert [entry.run_id.rsplit("/", 1)[-1] for entry in plan.points] == [names[2]]
    assert _alias_block(plan, []) == [f"  5002_3  POL 5002 {names[2]}"]
    assert planned_in_workspace(workspace.root, [])["5002"] == names
    run_side = selection_with_aliases(["5002"], ["5002_3"], [], whole)
    assert run_side == (["5002"], [names[2]])
