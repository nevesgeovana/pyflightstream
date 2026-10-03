"""Tier 1 offline: ``pyfs-matrix delete-sims --force`` (FR-306).

A simulation with a run still SUBMITTED is refused by ``delete-sims``; with
``--force`` it is deleted whatever the status of its records. Every workspace
is a real ``tmp_path`` tree.
"""
# The evidence line of this requirement cites this module (docs/srs/functional-requirements.md):

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pyflightstream.run import _cli_print
from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace import storage as storage_module
from pyflightstream.workspace.naming import ARCHIVE_DIR
from pyflightstream.workspace.storage import StorageError

REFUSAL = "have a run still SUBMITTED; collect it first"


def _record(sim_id: str, run_id: str, status: RunStatus) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id=sim_id,
        matrix_stem="matriz",
        fs_version_requested="26.123",
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
    for sim, status in (("6001", RunStatus.SUBMITTED), ("6002", RunStatus.CONVERGED)):
        folder = workspace.sim_dir(sim) / "datapoints" / "DP-1"
        folder.mkdir(parents=True)
        (folder / "x.txt").write_text("data", encoding="utf-8")
        workspace.append_record(_record(sim, f"camp/sim_{sim}/AL+000", status))
    products = workspace.root / "post" / "matriz"
    products.mkdir(parents=True)
    (products / "sim_6001_diag.csv").write_text("own", encoding="utf-8")
    document = {
        "products": {
            "sim_6001_diag.csv": {"sim_id": "6001", "runs": ["camp/sim_6001/AL+000"]},
        },
        "provenance": {},
    }
    (products / "products.json").write_text(json.dumps(document), encoding="utf-8")
    return workspace


def _rows(workspace: CampaignWorkspace) -> list[dict]:
    return json.loads(workspace.manifest_path.read_text(encoding="utf-8"))


def test_refused_without_force_with_the_same_text(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    with pytest.raises(StorageError) as caught:
        storage_module.delete_sims(workspace.root, ["6001"], apply=True)
    assert str(caught.value) == "sims ['6001'] have a run still SUBMITTED; collect it first"
    assert workspace.sim_dir("6001").exists()
    with pytest.raises(StorageError, match=REFUSAL):
        storage_module.delete_sims(workspace.root, ["6001"], force=False)


def test_force_preview_names_the_submitted_sim_and_changes_nothing(tmp_path, capsys):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    entry = storage_module.delete_sims(workspace.root, ["6001", "6002"], force=True)
    assert entry["applied"] is False
    assert entry["forced_submitted"] == ["6001"]
    assert workspace.sim_dir("6001").exists() and workspace.sim_dir("6002").exists()
    assert workspace.manifest_path.read_bytes() == before
    assert (workspace.root / "post" / "matriz" / "sim_6001_diag.csv").exists()
    _cli_print._print_delete_sims(entry)
    assert "sim 6001: still SUBMITTED, deleted because of --force" in capsys.readouterr().out


def test_force_apply_deletes_folder_products_records_and_records_the_call(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    entry = storage_module.delete_sims(workspace.root, ["6001"], force=True, apply=True)
    assert entry["applied"] is True
    assert not workspace.sim_dir("6001").exists()
    assert workspace.sim_dir("6002").exists()
    assert not (workspace.root / "post" / "matriz" / "sim_6001_diag.csv").exists()
    rows = _rows(workspace)
    assert not any(row.get("run_id") == "camp/sim_6001/AL+000" for row in rows)
    assert any(str(row.get("run_id")).startswith("deleted/sim_6001/") for row in rows)
    assert any(row.get("run_id") == "camp/sim_6002/AL+000" for row in rows)
    archived = list((workspace.root / ARCHIVE_DIR).glob("runs-*.json"))
    assert archived
    call = storage_module.read_storage_calls(workspace.root)[-1]
    assert call["force"] is True
    assert call["sims"][0]["statuses"] == [RunStatus.SUBMITTED.value]


def test_without_force_the_call_records_force_false(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    storage_module.delete_sims(workspace.root, ["6002"], apply=True)
    call = storage_module.read_storage_calls(workspace.root)[-1]
    assert call["force"] is False
    assert call["forced_submitted"] == []


def test_cli_force_flag_reaches_the_library(tmp_path):
    # Verifies FR-306.
    workspace = _workspace(tmp_path)
    args = ["delete-sims", "6001", "--workspace", str(workspace.root)]
    assert matrix_cli.main([*args, "--apply"]) != 0
    assert workspace.sim_dir("6001").exists()
    assert matrix_cli.main([*args, "--force", "--apply"]) == 0
    assert not workspace.sim_dir("6001").exists()


def test_mutant_ignoring_force_turns_the_check_red(tmp_path):
    # Verifies FR-306.
    source = Path(storage_module.__file__).read_text(encoding="utf-8")
    old = "    if submitted and not force:\n"
    assert source.count(old) == 1
    mutant = source.replace(old, "    if submitted:\n")
    assert mutant != source
    spec = importlib.util.spec_from_loader("storage_mutant_force", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pyflightstream.workspace"
    sys.modules["storage_mutant_force"] = module
    try:
        exec(compile(mutant, "storage_mutant_force.py", "exec"), module.__dict__)
        workspace = _workspace(tmp_path)
        with pytest.raises(Exception, match=REFUSAL):
            module.delete_sims(workspace.root, ["6001"], force=True)
        module_real = storage_module.delete_sims(workspace.root, ["6001"], force=True)
        assert module_real["forced_submitted"] == ["6001"]
    finally:
        sys.modules.pop("storage_mutant_force", None)
