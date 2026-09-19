"""B08: a manifest lease belongs to a writer, not to a creation timestamp."""

import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

import pyflightstream.workspace as workspace_mod
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError


def test_slow_live_writer_is_not_displaced_after_thirty_seconds(tmp_path, monkeypatch):
    workspace = CampaignWorkspace(tmp_path)
    monkeypatch.setattr(workspace_mod, "MANIFEST_LOCK_TIMEOUT_S", 0.03)
    now = time.time()
    with workspace._manifest_lock():
        monkeypatch.setattr(workspace_mod.time, "time", lambda: now + 31)
        with pytest.raises(WorkspaceError, match="NOT written"):
            with CampaignWorkspace(tmp_path)._manifest_lock():
                pass


def test_dead_local_owner_is_recovered_without_waiting_for_age(tmp_path, monkeypatch):
    workspace = CampaignWorkspace(tmp_path)
    # env= ON EVERY SPAWN (the repository guard): a child that inherits the
    # whole environment carries whatever the runner set, and this one only
    # needs to exist and exit so its pid is a DEAD one.
    env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    child = subprocess.Popen([sys.executable, "-c", "pass"], env=env)
    assert child.wait(timeout=10) == 0
    lock = tmp_path / "runs.json.lock"
    lock.write_text(json.dumps({"pid": child.pid, "host": socket.gethostname(), "token": "dead"}))
    monkeypatch.setattr(workspace_mod, "MANIFEST_LOCK_TIMEOUT_S", 0.03)
    try:
        with workspace._manifest_lock():
            assert lock.exists()
    except WorkspaceError:
        pytest.fail("a dead local owner was not recovered while its lock was fresh")
    assert not lock.exists()


def test_release_keeps_another_owners_lock(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    lock = tmp_path / "runs.json.lock"
    replacement = json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "token": "other"})
    with workspace._manifest_lock():
        lock.write_text(replacement, encoding="utf-8", newline="\n")
    assert lock.exists(), "release deleted another owner's lock"
    assert lock.read_text(encoding="utf-8") == replacement


def test_live_holder_renews_its_timestamp(tmp_path, monkeypatch):
    workspace = CampaignWorkspace(tmp_path)
    lock = tmp_path / "runs.json.lock"
    renewed = threading.Event()
    real_utime = os.utime

    def observe(path, *args, **kwargs):
        result = real_utime(path, *args, **kwargs)
        if path == lock:
            renewed.set()
        return result

    monkeypatch.setattr(workspace_mod, "MANIFEST_LOCK_RENEW_S", 0.01, raising=False)
    monkeypatch.setattr(workspace_mod.os, "utime", observe)
    with workspace._manifest_lock():
        assert renewed.wait(timeout=1), "live holder did not renew its lock timestamp"
        owner = json.loads(lock.read_text(encoding="utf-8"))
        assert owner["pid"] == os.getpid()
        assert owner["host"] == socket.gethostname()
        assert owner["token"]
