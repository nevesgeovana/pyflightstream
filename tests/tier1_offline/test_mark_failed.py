"""Tier 1 offline: ``pyfs-matrix mark-failed`` (FR-309).

A run that completed can be found wrong later. Its records become
FAILED_MARKED, keeping the status they had, when and why; every other record
keeps its bytes, and runs.json is archived first. Every workspace is a real
``tmp_path`` tree.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):
# FR-309.

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pyflightstream.run import cli as matrix_cli
from pyflightstream.run import records as records_module
from pyflightstream.run import worse_of
from pyflightstream.run.records import RunsManifestError, mark_failed
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
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
    return json.loads(workspace.manifest_path.read_text(encoding="utf-8"))


def test_preview_names_each_record_and_writes_nothing_fr_309(tmp_path):
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
    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(RunsManifestError, match="simulation\\(s\\) 9999; nothing was marked"):
        mark_failed(workspace.root, ["2006", "9999"], apply=True)
    assert workspace.manifest_path.read_bytes() == before


def test_a_record_already_marked_is_left_as_it_is_fr_309(tmp_path):
    workspace = _workspace(tmp_path)
    mark_failed(workspace.root, ["2006"], reason="first", apply=True)
    after_first = workspace.manifest_path.read_bytes()
    entry = mark_failed(workspace.root, ["2006"], reason="second", apply=True)
    assert entry["marked"] == [] and len(entry["already"]) == 2
    assert workspace.manifest_path.read_bytes() == after_first


def test_a_marked_record_is_a_failure_to_every_reader_fr_309(tmp_path):
    assert RunStatus.FAILED_MARKED.startswith("FAILED")
    assert worse_of(RunStatus.FAILED_DIVERGED, RunStatus.FAILED_MARKED) is RunStatus.FAILED_MARKED
    workspace = _workspace(tmp_path)
    mark_failed(workspace.root, ["2007"], apply=True)
    entry = delete_sims(workspace.root, ["2007"], apply=True)
    assert entry["applied"] is True
    assert not workspace.sim_dir("2007").exists()


def test_cli_marks_through_the_library_fr_309(tmp_path, capsys):
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
    source = Path(records_module.__file__).read_text(encoding="utf-8")
    old = '            row["status"] = str(RunStatus.FAILED_MARKED)\n'
    assert source.count(old) == 1
    mutant = source.replace(old, "")
    assert mutant != source
    spec = importlib.util.spec_from_loader("records_mutant_mark", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pyflightstream.run"
    sys.modules["records_mutant_mark"] = module
    try:
        exec(compile(mutant, "records_mutant_mark.py", "exec"), module.__dict__)
        workspace = _workspace(tmp_path)
        module.mark_failed(workspace.root, ["2006"], apply=True)
        statuses = {row["status"] for row in _rows(workspace) if row["sim_id"] == "2006"}
        assert statuses != {"FAILED_MARKED"}
        mark_failed(workspace.root, ["2006"], apply=True)
        statuses = {row["status"] for row in _rows(workspace) if row["sim_id"] == "2006"}
        assert statuses == {"FAILED_MARKED"}
    finally:
        sys.modules.pop("records_mutant_mark", None)
