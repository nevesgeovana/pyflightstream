"""MANIFEST-LOST-UPDATE: two writers on one manifest keep both changes.

A collection watcher completes records while another process submits, and two
campaigns have run against one workspace. Each writer read the manifest,
changed its copy and replaced the file, through one shared temporary name, so
the slower writer silently undid the faster one.

The interleaving is arranged, not raced: writer A reads the manifest and then
holds still while writer B is given every chance to do its whole write.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError


def _record(run_id: str, status: RunStatus = RunStatus.CONVERGED) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id="1001",
        fs_version_requested="26.120",
        package_version="0.24.0",
        script_sha256="a" * 64,
        raw_flag=False,
        status=status,
    )


def _interleave(root: Path, first, second) -> list[BaseException]:
    """Run ``first`` so that it pauses after READING, and ``second`` inside the pause."""
    has_read = threading.Event()
    second_is_done = threading.Event()
    errors: list[BaseException] = []

    class PausesAfterReading(CampaignWorkspace):
        def read_raw_manifest(self):
            raw = super().read_raw_manifest()
            has_read.set()
            # Long enough for the other writer to finish if nothing stops it,
            # short enough that a writer that IS stopped costs one second.
            second_is_done.wait(timeout=1.0)
            return raw

    def run_first():
        try:
            first(PausesAfterReading(root))
        except BaseException as error:
            errors.append(error)

    def run_second():
        try:
            assert has_read.wait(timeout=10.0)
            second(CampaignWorkspace(root))
        except BaseException as error:
            errors.append(error)
        finally:
            second_is_done.set()

    threads = [threading.Thread(target=run_first), threading.Thread(target=run_second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30.0)
    assert not any(thread.is_alive() for thread in threads), "a writer never came back"
    return errors


def test_two_appends_that_overlap_both_survive(tmp_path):
    root = tmp_path / "ws"
    CampaignWorkspace(root).append_record(_record("camp/sim_1001/seed"))
    errors = _interleave(
        root,
        lambda workspace: workspace.append_record(_record("camp/sim_1001/A")),
        lambda workspace: workspace.append_record(_record("camp/sim_1001/B")),
    )
    assert errors == []
    run_ids = sorted(record.run_id for record in CampaignWorkspace(root).read_manifest())
    assert run_ids == ["camp/sim_1001/A", "camp/sim_1001/B", "camp/sim_1001/seed"]


def test_a_completion_that_overlaps_an_append_keeps_both(tmp_path):
    root = tmp_path / "ws"
    CampaignWorkspace(root).append_record(_record("camp/sim_1001/Q", RunStatus.SUBMITTED))
    errors = _interleave(
        root,
        lambda workspace: workspace.complete_submitted_record(_record("camp/sim_1001/Q")),
        lambda workspace: workspace.append_record(_record("camp/sim_1001/B")),
    )
    assert errors == []
    statuses = {r.run_id: r.status for r in CampaignWorkspace(root).read_manifest()}
    assert statuses == {
        "camp/sim_1001/Q": RunStatus.CONVERGED,
        "camp/sim_1001/B": RunStatus.CONVERGED,
    }


def test_an_append_that_overlaps_a_completion_keeps_both(tmp_path):
    root = tmp_path / "ws"
    CampaignWorkspace(root).append_record(_record("camp/sim_1001/Q", RunStatus.SUBMITTED))
    errors = _interleave(
        root,
        lambda workspace: workspace.append_record(_record("camp/sim_1001/A")),
        lambda workspace: workspace.complete_submitted_record(_record("camp/sim_1001/Q")),
    )
    assert errors == []
    statuses = {r.run_id: r.status for r in CampaignWorkspace(root).read_manifest()}
    assert statuses == {
        "camp/sim_1001/Q": RunStatus.CONVERGED,
        "camp/sim_1001/A": RunStatus.CONVERGED,
    }


def test_the_temporary_file_is_this_process_s_own(tmp_path, monkeypatch):
    replaced: list[str] = []
    real = Path.replace

    def spy(self, target):
        replaced.append(self.name)
        return real(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    workspace = CampaignWorkspace(tmp_path / "ws")
    workspace.append_record(_record("camp/sim_1001/Q", RunStatus.SUBMITTED))
    workspace.complete_submitted_record(_record("camp/sim_1001/Q"))
    assert len(replaced) == 2, replaced
    for name in replaced:
        assert str(os.getpid()) in name, f"{name} is a name two processes would share"


def test_a_refused_write_releases_the_manifest(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "ws")
    workspace.append_record(_record("camp/sim_1001/A"))
    with pytest.raises(WorkspaceError):
        workspace.append_record(_record("camp/sim_1001/A"))
    # The refusal must not leave the manifest held: the next write goes through.
    workspace.append_record(_record("camp/sim_1001/B"))
    assert len(workspace.read_manifest()) == 2
    leftovers = sorted(p.name for p in workspace.root.iterdir() if p.name != "runs.json")
    assert [name for name in leftovers if name.startswith("runs.json")] == []


def test_a_lock_a_killed_process_left_does_not_hold_the_manifest_for_ever(tmp_path):
    import pyflightstream.workspace as workspace_mod

    workspace = CampaignWorkspace(tmp_path / "ws")
    workspace.root.mkdir(parents=True)
    lock = workspace.root / "runs.json.lock"
    lock.write_text("4242", encoding="utf-8")
    long_ago = lock.stat().st_mtime - 10 * workspace_mod.MANIFEST_LOCK_STALE_S
    os.utime(lock, (long_ago, long_ago))
    workspace.append_record(_record("camp/sim_1001/A"))
    assert [record.run_id for record in workspace.read_manifest()] == ["camp/sim_1001/A"]
    assert not lock.exists()


def test_a_manifest_that_stays_held_refuses_and_writes_nothing(tmp_path, monkeypatch):
    import pyflightstream.workspace as workspace_mod

    monkeypatch.setattr(workspace_mod, "MANIFEST_LOCK_TIMEOUT_S", 0.2)
    workspace = CampaignWorkspace(tmp_path / "ws")
    workspace.append_record(_record("camp/sim_1001/A"))
    lock = workspace.root / "runs.json.lock"
    lock.write_text("4242", encoding="utf-8")  # held, and fresh
    with pytest.raises(WorkspaceError) as refusal:
        workspace.append_record(_record("camp/sim_1001/B"))
    assert "runs.json.lock" in str(refusal.value)
    assert "NOT written" in str(refusal.value)
    assert [record.run_id for record in workspace.read_manifest()] == ["camp/sim_1001/A"]
    # Another writer's lock is not this writer's to remove.
    assert lock.exists()
