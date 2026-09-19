"""RESTART-FAILURE-NOT-RECORDED and the run half of CONTINUATION-REBIND.

Every attempted point's terminal failure is durably recorded and reaches the
campaign's failure report; and a continuation's record names the run it
continues, so a reader of the manifest can tell a chain from two runs.

The pre-flight refuses a continuation that cannot start before anything runs,
so the execution branch is reached by a caller of ``run_campaign`` directly, or
when the workspace changes between the plan and the run. The second is what
these tests arrange: the plan is answered as unblocked, and the saved
simulation is gone by the time the point executes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pyflightstream.run import CampaignErrors
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_goal021_inputs_absolute import _workspace
from tests.tier1_offline.test_goal021_swept_row import (
    _restart_row,
    _run,
    _stopped,
    _submitting,
)

TAG = "V0300RE120AL+000"
STOPPED_RUN = f"rotor/sim_7001/{TAG}"


def _saved_simulation(workspace):
    return workspace.sim_dir("7001") / "datapoints" / f"DP-{TAG}" / f"{TAG}.fsm"


def _continues(record):
    # Read off the serialised row, which is what a manifest reader holds.
    return record.model_dump(mode="json").get("continues")


def _plan_that_blocks_nothing(monkeypatch):
    monkeypatch.setattr(
        "pyflightstream.run.matrix.plan_campaign",
        lambda *args, **kwargs: SimpleNamespace(blocked=[]),
    )


def test_a_continuation_that_cannot_start_is_recorded_and_reported(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    _saved_simulation(workspace).unlink()
    _plan_that_blocks_nothing(monkeypatch)
    before = [record.run_id for record in workspace.read_manifest()]
    assert before == [STOPPED_RUN]

    with pytest.raises(CampaignErrors) as raised:
        _run(workspace, _restart_row(tmp_path), _submitting(workspace))

    # Reported: the campaign's failure report names the point.
    assert TAG in str(raised.value)
    # Recorded: one more row, FAILED_SCRIPT, of this point, under an id of its own.
    after = workspace.read_manifest()
    assert len(after) == 2, [(r.run_id, r.status) for r in after]
    failed = after[-1]
    assert failed.status is RunStatus.FAILED_SCRIPT
    assert failed.run_id != STOPPED_RUN
    assert failed.run_id.endswith(f"/{TAG}")
    assert failed.sim_id == "7001"
    assert "saved" in (failed.error or "")
    # The stopped run's row is carried as written.
    assert after[0].status is RunStatus.WALLTIME_REACHED


def test_a_recorded_refusal_does_not_block_the_continuation_once_its_cause_is_fixed(
    tmp_path, monkeypatch
):
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    saved = _saved_simulation(workspace)
    text = saved.read_text(encoding="utf-8")
    saved.unlink()
    _plan_that_blocks_nothing(monkeypatch)
    with pytest.raises(CampaignErrors):
        _run(workspace, _restart_row(tmp_path), _submitting(workspace))

    # The refusal named its remedy: restore the file. Doing so must be enough.
    saved.write_text(text, encoding="utf-8")
    records = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert [record.status for record in records] == [RunStatus.SUBMITTED], [
        (record.run_id, record.status, record.error) for record in records
    ]
    assert _continues(records[0]) == STOPPED_RUN


def test_a_continuation_record_names_the_run_it_continues(tmp_path):
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    records = _run(workspace, _restart_row(tmp_path), _submitting(workspace))
    assert len(records) == 1
    assert _continues(records[0]) == STOPPED_RUN
    # And it is in the manifest, which is what the products stage reads.
    on_disk = {record.run_id: record for record in workspace.read_manifest()}
    assert _continues(on_disk[records[0].run_id]) == STOPPED_RUN
    assert _continues(on_disk[STOPPED_RUN]) is None


def test_a_point_that_continues_nothing_says_so(tmp_path):
    from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row

    workspace = _workspace(tmp_path)
    records = _run(workspace, _rotor_row(tmp_path, sweep="0.0"), _submitting(workspace))
    assert records and all(_continues(record) is None for record in records)
