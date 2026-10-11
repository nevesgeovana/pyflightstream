"""P0390-COLLECT (FR-413 R8): a record with no declared_logs reads its log names from its script.

A point submitted before 0.37.0 carries no ``submission["declared_logs"]``. Her
case: 8 of 9 declared outputs present, the log the only one absent, no field in
the record. The workspaces here are made by the package's own run (alone, or a
grouped job), the solver's files written where the job writes them with the
log deleted, the field removed from the record, and collect run as she runs it.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.run.collect import collect_once
from pyflightstream.workspace._missing_log import declared_log_names, script_log_names
from pyflightstream.workspace.manifest import RunRecord
from tests.support_helpers import no_sleep
from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace

MODES = ["alone", "batch"]


def _rows(root: Path) -> list[dict]:
    return json.loads((root / "runs.json").read_text("utf-8"))


def _submitted(tmp_path: Path, mode: str, *, field: bool, script: bool = True, ended: bool = True):
    """A workspace of SUBMITTED points whose log is absent, the field kept or removed."""
    workspace = grouped_workspace(tmp_path, mode=mode, logs=False, collect=False, ended=ended)
    rows = _rows(workspace.root)
    assert {row["status"] for row in rows} == {"SUBMITTED"}, [row["status"] for row in rows]
    for row in rows:
        if not field:
            row["submission"].pop("declared_logs")
        if not script:
            for found in (workspace.root / "sims").rglob(Path(row["script_path"]).name):
                found.unlink()
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return workspace


def _collect(workspace) -> dict[str, str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        collect_once(workspace, interval=0.0, sleep=no_sleep)
    return {row["run_id"]: row["status"] for row in _rows(workspace.root)}


@pytest.mark.parametrize("mode", MODES)
def test_p0390_collect_a_record_without_the_field_is_ran_missing_log(mode, tmp_path):
    """P0390-COLLECT (FR-413 R8): the field-less point whose only absent output is its log.

    Her case: every declared output present but the script's log, no
    ``declared_logs`` in the record, alone and grouped: RAN_MISSING_LOG alone,
    collect never waiting on it. A mutant that reads only the field leaves the
    point SUBMITTED.
    """
    workspace = _submitted(tmp_path, mode, field=False)
    rows = _rows(workspace.root)
    assert all("declared_logs" not in row["submission"] for row in rows)
    for row in rows:
        declared = row["submission"]["declared_outputs"]
        assert any(name.endswith("_log.txt") for name in declared), declared
    statuses = _collect(workspace)
    assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses


@pytest.mark.parametrize("mode", MODES)
def test_p0390_collect_the_field_present_control(mode, tmp_path):
    """P0390-COLLECT (FR-413 R8): a record that carries the field keeps the field's names."""
    workspace = _submitted(tmp_path, mode, field=True)
    assert all(row["submission"]["declared_logs"] for row in _rows(workspace.root))
    statuses = _collect(workspace)
    assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses


@pytest.mark.parametrize("field", [True, False], ids=["field", "no-field"])
def test_p0390_collect_a_running_batch_reads_the_script_in_its_staging_folder(field, tmp_path):
    """P0390-COLLECT (FR-413 R8): a batch still running renders its script under the batch folder.

    The script of a running batch's point is not yet in ``sims/``; with the
    field removed the names come from the staging copy, so the point whose log
    is absent is RAN_MISSING_LOG exactly as when the field is kept. A mutant
    that reads the simulation folder only leaves the field-less point SUBMITTED.
    """
    workspace = _submitted(tmp_path, "batch", field=field, ended=False)
    statuses = _collect(workspace)
    assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses


@pytest.mark.parametrize("mode", MODES)
def test_p0390_collect_neither_field_nor_script_keeps_waiting(mode, tmp_path):
    """P0390-COLLECT (FR-413 R8): no field and no readable script means no declared log.

    The rule does not fire: the point is not RAN_MISSING_LOG and collect keeps
    waiting for its log, so it stays SUBMITTED.
    """
    workspace = _submitted(tmp_path, mode, field=False, script=False)
    statuses = _collect(workspace)
    assert "RAN_MISSING_LOG" not in set(statuses.values()), statuses
    assert set(statuses.values()) == {"SUBMITTED"}, statuses


def test_p0390_collect_one_reading_of_a_script_serves_workspace_and_run():
    """P0390-COLLECT (FR-413 R8): the script reading lives in the workspace layer, once.

    The run layer's helper is the workspace function itself, and a record
    without the field reads the names off the script, a record with it the field.
    """
    from pyflightstream.run import _wake_edge_verdict

    assert _wake_edge_verdict.script_log_names is script_log_names
    text = "EXPORT_LOG\nC:\\job\\P1_log.txt\nOTHER\n"
    assert script_log_names(text) == ["P1_log.txt"]
    assert script_log_names(None) == []
    bare = RunRecord.model_construct(run_id="r", submission={}, script_path="s.txt")
    assert declared_log_names(bare, None) == []
    kept = RunRecord.model_construct(
        run_id="r", submission={"declared_logs": ["a_log.txt"]}, script_path=None
    )
    assert declared_log_names(kept, None) == ["a_log.txt"]
