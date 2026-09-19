"""Rename participates in the same locked, atomic manifest protocol as run/collect."""

import threading
from pathlib import Path

import pyflightstream.run.rename as rename
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_goal028_hpc_manifest_lock import _record
from tests.tier1_offline.test_goal028_rename_destinations import _old_workspace


def test_rename_does_not_lose_a_concurrent_append(tmp_path, monkeypatch):
    workspace, _ = _old_workspace(tmp_path)
    original_plan = rename._plan_record
    attempted = threading.Event()
    done = threading.Event()
    errors = []

    def append():
        try:
            attempted.set()
            CampaignWorkspace(workspace.root).append_record(_record("other/sim_1001/new"))
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()

    writer = threading.Thread(target=append)

    def plan(*args, **kwargs):
        if not attempted.is_set():
            writer.start()
            assert attempted.wait(5)
            done.wait(0.2)  # A writer without the shared lock finishes inside this pause.
        return original_plan(*args, **kwargs)

    monkeypatch.setattr(rename, "_plan_record", plan)
    try:
        rename.rename_workspace(workspace)
    finally:
        if writer.ident is not None:
            writer.join(10)
    assert not writer.is_alive() and not errors, errors
    ids = [record.run_id for record in workspace.read_manifest()]
    assert "other/sim_1001/new" in ids, "rename lost the concurrently appended run"


def test_rename_never_truncates_the_live_manifest(tmp_path, monkeypatch):
    workspace, _ = _old_workspace(tmp_path)
    original_write = Path.write_text

    def write(path, *args, **kwargs):
        assert path != workspace.manifest_path, "rename writes directly to the live manifest"
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    report = rename.rename_workspace(workspace)
    assert report.renamed_records == 1
