"""Tier 1 offline: ``pyfs-matrix mark-failed`` (FR-309).

A run that completed can be found wrong later. Its records become
FAILED_MARKED, keeping the status they had, when and why; every other record
keeps its bytes, and runs.json is archived first. Every workspace is a real
``tmp_path`` tree.
"""
# The evidence line of this requirement cites this module
# (docs/unpublished/requirements/functional-requirements.md):

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from pyflightstream.run import _record_files as records_module
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run import worse_of
from pyflightstream.run.records import RunsManifestError, mark_failed
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from pyflightstream.workspace.storage import delete_sims


def _record(sim_id: str, run_id: str, status: RunStatus) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id=sim_id,
        matrix_stem="matriz",
        fs_version_requested="26.124",
        package_version="0.33.0",
        script_sha256="c" * 64,
        raw_flag=False,
        status=status,
        outputs=[],
        script_path=None,
        inputs_sha256={},
    )


def _workspace(tmp_path: Path) -> CampaignWorkspace:
    root = tmp_path / "camp"
    workspace = CampaignWorkspace(root)
    workspace.init(root)
    for sim, point, status in (
        ("2006", "AL+000", RunStatus.CONVERGED),
        ("2006", "AL+005", RunStatus.COMPLETED_MAX_ITER),
        ("2007", "AL+000", RunStatus.SUBMITTED),
        ("2008", "AL+000", RunStatus.CONVERGED),
    ):
        folder = workspace.sim_dir(sim) / "datapoints" / "DP-1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "x.txt").write_text("data", encoding="utf-8")
        workspace.append_record(_record(sim, f"camp/sim_{sim}/{point}", status))
    return workspace


def _rows(workspace: CampaignWorkspace) -> list[dict]:
    return _read_record_rows(workspace.manifest_path)


@pytest.mark.parametrize("route", ["simulation", "run"])
def test_p0420_mark_failed_reaches_every_steady_job_point(tmp_path, route):
    from pyflightstream.run._record_files import mark_runs_failed

    workspace = _workspace(tmp_path)
    job = _record("2009", "camp/sim_2009/job", RunStatus.CONVERGED)
    job = job.model_copy(
        update={
            "points_ran": [
                {"tag": "AL+000", "status": "CONVERGED", "outputs": []},
                {"tag": "AL+005", "status": "COMPLETED_MAX_ITER", "outputs": []},
            ]
        }
    )
    workspace.append_record(job)
    if route == "simulation":
        mark_failed(workspace.root, ["2009"], reason="wrong mesh", apply=True)
    else:
        mark_runs_failed(workspace, [job.run_id], reason="wrong mesh")
    row = next(row for row in _rows(workspace) if row["run_id"] == job.run_id)
    assert row["status"] == "FAILED_MARKED"
    assert [point["status"] for point in row["points_ran"]] == ["FAILED_MARKED"] * 2
    assert [point["marked"]["from"] for point in row["points_ran"]] == [
        "CONVERGED",
        "COMPLETED_MAX_ITER",
    ]
    assert all(point["marked"]["reason"] == "wrong mesh" for point in row["points_ran"])


def test_preview_names_each_record_and_writes_nothing_fr_309(tmp_path):
    # Verifies FR-309.
    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    entry = mark_failed(workspace.root, ["2006"])
    assert entry["applied"] is False
    assert [(item["run_id"], item["from"]) for item in entry["marked"]] == [
        ("camp/sim_2006/AL+000", "CONVERGED"),
        ("camp/sim_2006/AL+005", "COMPLETED_MAX_ITER"),
    ]
    assert workspace.manifest_path.read_bytes() == before
    assert not (workspace.root / "archive").exists() or not list(
        (workspace.root / "archive").glob("runs-*.json")
    )


def test_apply_marks_keeps_the_history_and_archives_fr_309(tmp_path):
    # Verifies FR-309.
    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    untouched = [row for row in _rows(workspace) if row["sim_id"] != "2006"]
    entry = mark_failed(workspace.root, ["2006"], reason="wrong mesh", apply=True)
    assert entry["applied"] is True
    rows = _rows(workspace)
    marked = [row for row in rows if row["sim_id"] == "2006"]
    assert [row["status"] for row in marked] == ["FAILED_MARKED", "FAILED_MARKED"]
    assert [row["marked"]["from"] for row in marked] == ["CONVERGED", "COMPLETED_MAX_ITER"]
    assert {row["marked"]["reason"] for row in marked} == {"wrong mesh"}
    assert all(row["marked"]["at"] for row in marked)
    assert [row for row in rows if row["sim_id"] != "2006"] == untouched
    archived = workspace.root / entry["runs_archived_as"]
    assert archived.read_bytes() == before
    records = {record.run_id: record for record in workspace.read_manifest()}
    assert records["camp/sim_2006/AL+000"].status is RunStatus.FAILED_MARKED
    assert records["camp/sim_2008/AL+000"].status is RunStatus.CONVERGED
    assert "marked" not in records["camp/sim_2008/AL+000"].model_dump()


def test_an_unknown_simulation_is_refused_before_any_write_fr_309(tmp_path):
    # Verifies FR-309.
    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(RunsManifestError, match="simulation\\(s\\) 9999; nothing was marked"):
        mark_failed(workspace.root, ["2006", "9999"], apply=True)
    assert workspace.manifest_path.read_bytes() == before


def test_a_record_already_marked_is_left_as_it_is_fr_309(tmp_path):
    # Verifies FR-309.
    workspace = _workspace(tmp_path)
    mark_failed(workspace.root, ["2006"], reason="first", apply=True)
    after_first = workspace.manifest_path.read_bytes()
    entry = mark_failed(workspace.root, ["2006"], reason="second", apply=True)
    assert entry["marked"] == [] and len(entry["already"]) == 2
    assert workspace.manifest_path.read_bytes() == after_first


def test_a_deleted_simulation_record_is_never_marked_fr_309(tmp_path):
    # Verifies FR-309. delete-sims leaves a tombstone row naming the simulation it
    # retired; marking the same id, run again after the deletion, marks the live
    # record only and leaves the tombstone as it was.
    workspace = _workspace(tmp_path)
    delete_sims(workspace.root, ["2008"], apply=True)
    tombstones = [row for row in _rows(workspace) if row.get("deleted_sim") == "2008"]
    assert len(tombstones) == 1
    workspace.append_record(_record("2008", "camp/sim_2008/AL+010", RunStatus.CONVERGED))
    entry = mark_failed(workspace.root, ["2008"], apply=True)
    assert [item["run_id"] for item in entry["marked"]] == ["camp/sim_2008/AL+010"]
    rows = {row["run_id"]: row for row in _rows(workspace)}
    assert rows["camp/sim_2008/AL+010"]["status"] == "FAILED_MARKED"
    assert rows[tombstones[0]["run_id"]] == tombstones[0]


def test_a_simulation_that_is_only_deleted_is_refused_fr_309(tmp_path):
    # Verifies FR-309. Its records are all retired, so there is nothing to mark.
    workspace = _workspace(tmp_path)
    delete_sims(workspace.root, ["2008"], apply=True)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(RunsManifestError, match="simulation\\(s\\) 2008; nothing was marked"):
        mark_failed(workspace.root, ["2008"], apply=True)
    assert workspace.manifest_path.read_bytes() == before


def test_a_marked_record_is_a_failure_to_every_reader_fr_309(tmp_path):
    # Verifies FR-309.
    assert RunStatus.FAILED_MARKED.startswith("FAILED")
    assert worse_of(RunStatus.FAILED_DIVERGED, RunStatus.FAILED_MARKED) is RunStatus.FAILED_MARKED
    workspace = _workspace(tmp_path)
    mark_failed(workspace.root, ["2007"], apply=True)
    entry = delete_sims(workspace.root, ["2007"], apply=True)
    assert entry["applied"] is True
    assert not workspace.sim_dir("2007").exists()


def test_cli_marks_through_the_library_fr_309(tmp_path, capsys):
    # Verifies FR-309.
    workspace = _workspace(tmp_path)
    args = ["mark-failed", "--sims", "[2006,2008]", "--workspace", str(workspace.root)]
    assert matrix_cli.main(args) == 0
    out = capsys.readouterr().out
    assert "would mark FAILED_MARKED: sim 2008 camp/sim_2008/AL+000 (was CONVERGED)" in out
    assert "preview: nothing was written" in out
    assert matrix_cli.main([*args, "--reason", "bad wake", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "marked FAILED_MARKED: sim 2006 camp/sim_2006/AL+005 (was COMPLETED_MAX_ITER)" in out
    assert "runs.json as it was: archive/runs-" in out
    assert {row["status"] for row in _rows(workspace) if row["sim_id"] != "2007"} == {
        "FAILED_MARKED"
    }
    assert (
        matrix_cli.main(["mark-failed", "--sims", "9999", "--workspace", str(workspace.root)]) == 2
    )
    assert "9999" in capsys.readouterr().err


def test_mutant_leaving_the_status_turns_the_check_red_fr_309(tmp_path):
    # Verifies FR-309.
    source = Path(records_module.__file__).read_text(encoding="utf-8")
    # Both status writes of the marking (PFS-2103.010 marks each point, then the
    # record takes its worst point's status): a record is its own one unit, so
    # leaving one write alone still marks it.
    mutant = source
    for old in (
        '        unit["status"] = str(RunStatus.FAILED_MARKED)\n',
        '    row["status"] = str(worst)\n',
    ):
        assert source.count(old) == 1, old
        mutant = mutant.replace(old, "")
    assert mutant != source
    spec = importlib.util.spec_from_loader("records_mutant_mark", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pyflightstream.run"
    sys.modules["records_mutant_mark"] = module
    try:
        exec(compile(mutant, "records_mutant_mark.py", "exec"), module.__dict__)
        workspace = _workspace(tmp_path)
        module.mark_runs_failed(
            workspace, [row["run_id"] for row in _rows(workspace) if row["sim_id"] == "2006"]
        )
        statuses = {row["status"] for row in _rows(workspace) if row["sim_id"] == "2006"}
        assert statuses != {"FAILED_MARKED"}
        mark_failed(workspace.root, ["2006"], apply=True)
        statuses = {row["status"] for row in _rows(workspace) if row["sim_id"] == "2006"}
        assert statuses == {"FAILED_MARKED"}
    finally:
        sys.modules.pop("records_mutant_mark", None)


def test_pfs_2126_033_mark_runs_failed_refuses_an_unknown_run_id_naming_it(tmp_path):
    """PFS-2126.033: as mark_failed refuses a simulation it does not know, nothing is marked."""
    from pyflightstream.run._record_files import RecordsError, mark_runs_failed

    workspace = _workspace(tmp_path)
    known = _rows(workspace)[0]["run_id"]
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(RecordsError, match=r"camp/sim_nope/AL\+000"):
        mark_runs_failed(workspace, [known, "camp/sim_nope/AL+000"])
    assert workspace.manifest_path.read_bytes() == before


def test_p0430_apply_rereads_and_archives_under_the_records_lock_fr_514(tmp_path):
    # Verifies FR-514: a competing writer holding the records lock keeps the mark waiting,
    # and the archive taken afterwards holds the row that writer added.
    import threading
    import time

    from pyflightstream.run._record_files import manifest_lock

    workspace = _workspace(tmp_path)
    outcome: dict = {}

    def mark() -> None:
        outcome["entry"] = mark_failed(workspace.root, ["2006"], apply=True)

    with manifest_lock(workspace.root):
        rows = _rows(workspace)
        added = dict(next(row for row in rows if row["sim_id"] == "2008"))
        added.update(sim_id="2010", run_id="camp/sim_2010/AL+000")
        worker = threading.Thread(target=mark)
        worker.start()
        time.sleep(0.6)
        assert worker.is_alive() and "entry" not in outcome
        workspace._replace_manifest([*rows, added])
    worker.join(timeout=60)
    assert not worker.is_alive()
    archived = _read_record_rows(workspace.root / outcome["entry"]["runs_archived_as"])
    assert "camp/sim_2010/AL+000" in {row["run_id"] for row in archived}
    final = _rows(workspace)
    assert "camp/sim_2010/AL+000" in {row["run_id"] for row in final}
    assert {row["status"] for row in final if row["sim_id"] == "2006"} == {"FAILED_MARKED"}


def test_p0430_the_mark_keeps_prior_status_reason_and_an_iso_time_fr_3154(tmp_path):
    # Verifies FR-3154.
    import datetime as dt

    workspace = _workspace(tmp_path)
    mark_failed(workspace.root, ["2007"], reason="mesh swapped", apply=True)
    row = next(row for row in _rows(workspace) if row["sim_id"] == "2007")
    assert row["status"] == "FAILED_MARKED"
    assert row["marked"]["from"] == "SUBMITTED" and row["marked"]["reason"] == "mesh swapped"
    stamp = dt.datetime.fromisoformat(row["marked"]["at"])
    assert stamp.tzinfo is not None
    mark_failed(workspace.root, ["2007"], reason="again", apply=True)
    again = next(row for row in _rows(workspace) if row["sim_id"] == "2007")
    assert again["marked"] == row["marked"]
