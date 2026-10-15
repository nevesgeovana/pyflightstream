"""P0390-COLLECT (FR-867): a record with no declared_logs reads its log names from its script.

A point submitted before 0.37.0 carries no ``submission["declared_logs"]``. Her
case: 8 of 9 declared outputs present, the log the only one absent, no field in
the record. The workspaces here are made by the package's own run (alone, or a
grouped job), the solver's files written where the job writes them with the
log deleted, the field removed from the record, and collect run as she runs it.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.run.collect import collect_once
from pyflightstream.workspace._missing_log import declared_log_names, script_log_names
from pyflightstream.workspace.manifest import RunRecord
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.support_helpers import no_sleep
from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace

MODES = ["alone", "batch"]


def _rows(root: Path) -> list[dict]:
    return _read_record_rows(root / "runs.json")


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
    workspace._replace_manifest(rows)
    return workspace


def _collect(workspace) -> dict[str, str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        collect_once(workspace, interval=0.0, sleep=no_sleep)
    return {row["run_id"]: row["status"] for row in _rows(workspace.root)}


@pytest.mark.parametrize("mode", MODES)
def test_p0390_collect_a_record_without_the_field_is_ran_missing_log(mode, tmp_path):
    """P0390-COLLECT (FR-867): the field-less point whose only absent output is its log.

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
    """P0390-COLLECT (FR-867): a record that carries the field keeps the field's names."""
    workspace = _submitted(tmp_path, mode, field=True)
    assert all(row["submission"]["declared_logs"] for row in _rows(workspace.root))
    statuses = _collect(workspace)
    assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses


@pytest.mark.parametrize("field", [True, False], ids=["field", "no-field"])
def test_p0390_collect_a_running_batch_reads_the_script_in_its_staging_folder(field, tmp_path):
    """P0390-COLLECT (FR-867): a batch still running renders its script under the batch folder.

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
    """P0390-COLLECT (FR-867): no field and no readable script means no declared log.

    The rule does not fire: the point is not RAN_MISSING_LOG and collect keeps
    waiting for its log, so it stays SUBMITTED.
    """
    workspace = _submitted(tmp_path, mode, field=False, script=False)
    statuses = _collect(workspace)
    assert "RAN_MISSING_LOG" not in set(statuses.values()), statuses
    assert set(statuses.values()) == {"SUBMITTED"}, statuses


def test_p0390_collect_one_reading_of_a_script_serves_workspace_and_run():
    """P0390-COLLECT (FR-867): the script reading lives in the workspace layer, once.

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


@pytest.mark.parametrize(
    ("field", "read"),
    [([], False), (["field_log.txt"], False), (["log_AL+000.h5"], True)],
    ids=["empty-field", "field-names-another", "field-names-it"],
)
def test_p0390_collect_the_log_line_checks_read_a_present_field_alone(field, read, tmp_path):
    """P0390-COLLECT (FR-867): collect's log-line checks take a present field's names alone.

    The job's script exports its log to ``log_AL+000.h5``, which carries a G06
    refusal line. Every collected text output is scanned for the line whatever its
    name, so the case where the declaration decides is a log under a suffix the
    scan takes for binary (``.h5``): it is read only when it is a declared log. A
    record whose field is an explicitly empty list, or names another file, has
    not declared that file a log, so the line is not read and
    the point keeps the assessor's CONVERGED; a field that names it is read and
    the point is FAILED_SCRIPT (the control). A mutant that adds the script's
    names to a present field fails the empty and the other-name cases.
    """
    from pyflightstream.workspace import RunStatus
    from tests.tier1_offline.test_collect_stage import _submitted_workspace
    from tests.tier1_offline.test_g06_actuator_disc import (
        COPY,
        PROFILE_REFUSALS,
        _log_without_residuals,
    )

    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "log_AL+000.h5"))
    rows = _rows(workspace.root)
    rows[0]["submission"]["declared_logs"] = field
    workspace._replace_manifest(rows)
    script = sim / "scripts" / "point.fs"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\n{sim / 'loads.txt'}\n\n"
        f"EXPORT_LOG\n{sim / 'log_AL+000.h5'}\n\nCLOSE_FLIGHTSTREAM\n",
        encoding="utf-8",
    )
    assert script_log_names(script.read_text(encoding="utf-8")) == ["log_AL+000.h5"]
    line = f"{PROFILE_REFUSALS[2]}{sim / COPY}"
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "log_AL+000.h5").write_bytes(_log_without_residuals(line).encode("utf-8"))

    def passed(record, sim_dir):
        return RunStatus.CONVERGED, None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = collect_once(workspace, interval=0.0, sleep=no_sleep, assessor=passed)
    (outcome,) = report.collected + report.failed
    record = outcome.record
    assert record is not None, outcome.detail
    if read:
        assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
        assert line in (record.error or ""), record.error
    else:
        assert record.status is RunStatus.CONVERGED, (record.status, record.error)
        assert record.error is None
