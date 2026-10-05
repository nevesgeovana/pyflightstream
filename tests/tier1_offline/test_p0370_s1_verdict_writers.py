"""Steady job point verdicts survive record reconstruction and sync."""

import copy
import json

import pytest

from pyflightstream.run._mark_converged import keep_verdict, person_verdicts
from pyflightstream.workspace._verdicts import merge_runs


def _marked_job():
    return {
        "run_id": "campaign/sim_1/sweep",
        "status": "RAN_MISSING_LOG",
        "points_ran": [
            {
                "tag": "A",
                "status": "CONVERGED",
                "marked": {
                    "from": "RAN_MISSING_LOG",
                    "at": "2026-10-05",
                    "reason": "reviewed",
                    "verdict": "CONVERGED",
                },
            },
            {"tag": "B", "status": "RAN_MISSING_LOG"},
        ],
    }


def test_rebuild_keeps_each_steady_point_verdict(tmp_path):
    """P0370-S1-MARK-CONVERGED (FR-414 R4): nested marks survive rebuild."""
    original = _marked_job()
    manifest = tmp_path / "runs.json"
    manifest.write_text(json.dumps([original]), encoding="utf-8")
    computed = copy.deepcopy(original)
    computed["status"] = "COMPLETED_MAX_ITER"
    for point in computed["points_ran"]:
        point.pop("marked", None)
        point["status"] = "COMPLETED_MAX_ITER"
    kept = keep_verdict(computed, person_verdicts(manifest).get(original["run_id"]))
    assert kept["points_ran"][0]["marked"] == original["points_ran"][0]["marked"]
    assert kept["points_ran"][0]["status"] == "CONVERGED"
    assert kept["points_ran"][1]["status"] == "COMPLETED_MAX_ITER"
    assert kept["status"] == "COMPLETED_MAX_ITER"


@pytest.mark.parametrize("change", ["drop", "reason", "status"])
def test_sync_refuses_to_replace_a_steady_point_verdict(change):
    """P0370-S1-MARK-CONVERGED (FR-414 R4): prefer-other cannot erase a mark."""
    original = _marked_job()
    incoming = copy.deepcopy(original)
    point = incoming["points_ran"][0]
    if change == "drop":
        point.pop("marked")
    elif change == "reason":
        point["marked"]["reason"] = "different verdict"
    else:
        point["status"] = "FAILED_EXECUTION"
    merged, added, replaced, conflicts = merge_runs([original], [incoming], True)
    assert merged == [original]
    assert not added and not replaced
    assert conflicts[0]["run_id"] == original["run_id"]


def test_sync_refuses_changed_top_level_verdict():
    """P0370-S1-MARK-CONVERGED (FR-414 R4): a present mark is not proof it survived."""
    original = _marked_job()
    original.update(original.pop("points_ran")[0])
    incoming = {**original, "status": "FAILED_EXECUTION"}
    merged, _, replaced, conflicts = merge_runs([original], [incoming], True)
    assert merged == [original] and not replaced and conflicts
