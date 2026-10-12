"""P0400-SYNCNOTES: a sync merge never imports the other workspace's delete-sims notes."""

from __future__ import annotations

from pyflightstream.workspace._verdicts import DELETED_SIM_KEY, merge_runs


def test_p0400_syncnotes_a_deletion_note_of_the_other_workspace_is_not_merged():
    """P0400-SYNCNOTES (PFS-2103.038): the other workspace deleted sim 7 and left its note;
    main still holds sim 7's record, so the merge keeps that record, adds no note and
    reports the note as not applied."""
    live = {"run_id": "campaign/sim_7/a", "sim_id": 7, "status": "CONVERGED"}
    note = {
        "run_id": "deleted/sim_7/20261012T120000",
        DELETED_SIM_KEY: 7,
        "deleted_at": "2026-10-12T12:00:00",
        "deleted_run_ids": ["campaign/sim_7/a"],
        "note": "this simulation id belonged to a simulation deleted by pyfs-matrix delete-sims",
    }
    merged, added, replaced, conflicts = merge_runs([live], [note], prefer_other=False)
    assert merged == [live]
    assert added == [] and replaced == []
    assert [c["run_id"] for c in conflicts] == [note["run_id"]]
    assert "delete-sims note" in conflicts[0]["reason"]
