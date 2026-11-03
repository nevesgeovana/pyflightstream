"""Tier 1: restore and sync hold the post's lock on products.json (PFS-2186.14, REL-R3-004)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from pyflightstream import _textio
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run.records import restore
from pyflightstream.workspace.storage import sync_workspaces
from tests.tier1_offline.test_goal035_storage import _sync_pair
from tests.tier1_offline.test_p0320_fx1_restore_archive import _post_workspace


def _a_post_holding(manifest, held, release, failed):
    """A thread that holds the lock as a post does, until ``release`` is set."""

    def hold():
        try:
            with _textio.exclusive(manifest, wait=5.0) as handle:
                assert handle is not None
                held.set()
                release.wait(5.0)
                handle.seek(0)
                document = json.loads(handle.read().decode("utf-8"))
                document["products"]["polars/P_by_the_post.csv"] = {"sim_id": "7010"}
                _textio.replace_content(handle, json.dumps(document, indent=1) + "\n")
        except BaseException as error:  # pragma: no cover - reported by the test
            failed.append(error)

    thread = threading.Thread(target=hold)
    thread.start()
    assert held.wait(5.0)
    return thread


@pytest.mark.requirement("FR-3500")
def test_p0540_restore_products_waits_for_the_posts_lock(tmp_path):
    """PFS-2186.14: the restore applies after the post's write, not around it."""
    workspace = _post_workspace(tmp_path)
    write_campaign_products(workspace, overwrite=True)
    manifest = workspace.products_dir(None) / "products.json"
    first = manifest.read_bytes()
    manifest.write_text(json.dumps({"marker": "second", "products": {}}), encoding="utf-8")
    write_campaign_products(workspace, overwrite=True, archive=True)
    held, release, failed = threading.Event(), threading.Event(), []
    post = _a_post_holding(manifest, held, release, failed)
    threading.Timer(0.5, release.set).start()
    started = time.monotonic()
    done = restore(workspace.root, "products", matrix="products", apply=True)
    post.join()
    assert not failed, failed
    assert time.monotonic() - started >= 0.4, "the restore did not wait for the lock"
    assert done["applied"] is True
    assert b"second" in manifest.read_bytes()
    assert first


@pytest.mark.requirement("FR-3500")
def test_p0540_restore_products_warns_and_skips_when_the_lock_stays_held(tmp_path, monkeypatch):
    """PFS-2186.14: a lock held past the wait is warned, the file is left as it was."""
    workspace = _post_workspace(tmp_path)
    write_campaign_products(workspace, overwrite=True)
    manifest = workspace.products_dir(None) / "products.json"
    manifest.write_text(json.dumps({"marker": "second", "products": {}}), encoding="utf-8")
    write_campaign_products(workspace, overwrite=True, archive=True)
    current = manifest.read_bytes()
    monkeypatch.setattr(_textio, "LOCK_WAIT", 0.3)
    held, release, failed = threading.Event(), threading.Event(), []
    post = _a_post_holding(manifest, held, release, failed)
    try:
        with pytest.warns(PyflightstreamWarning, match="stayed locked") as caught:
            done = restore(workspace.root, "products", matrix="products", apply=True)
    finally:
        release.set()
        post.join()
    assert done["applied"] is False
    assert not failed, failed
    assert b"P_by_the_post" in manifest.read_bytes() or manifest.read_bytes() == current
    # REL-K-013: the remedy is the restore again; a post would not bring the archive back.
    said = " ".join(str(item.message) for item in caught)
    assert "run the restore again" in said and "post the matrix again" not in said


@pytest.mark.requirement("FR-3500")
def test_p0540_restore_of_a_missing_products_archives_nothing(tmp_path):
    """REL-K-005: the lock creates the absent file, and that empty file is no archived copy."""
    workspace = _post_workspace(tmp_path)
    write_campaign_products(workspace, overwrite=True)
    manifest = workspace.products_dir(None) / "products.json"
    write_campaign_products(workspace, overwrite=True, archive=True)
    before = sorted(path for path in workspace.root.rglob("products.json") if path != manifest)
    manifest.unlink()
    done = restore(workspace.root, "products", matrix="products", apply=True)
    assert done["applied"] is True and done["archived_as"] is None
    assert json.loads(manifest.read_text(encoding="utf-8"))
    after = sorted(path for path in workspace.root.rglob("products.json") if path != manifest)
    assert after == before, "an empty products.json entered the archive"
    # The newest archive is still a document, so a second restore has something to read.
    assert restore(workspace.root, "products", matrix="products")["same"] is True


def _synced_pair(tmp_path):
    main, other = _sync_pair(tmp_path, "locks")
    manifest = main.root / "post" / "m" / "products.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"products": {"old": {}}}) + "\n", encoding="utf-8")
    brought = other.root / "post" / "m" / "products.json"
    brought.parent.mkdir(parents=True)
    brought.write_text(json.dumps({"products": {"x": {}}}) + "\n", encoding="utf-8")
    return main, manifest


@pytest.mark.requirement("FR-3500")
def test_p0540_sync_copy_of_products_waits_for_the_posts_lock(tmp_path):
    """PFS-2186.14: the sync's copy of post/ rewrites products.json under the lock."""
    main, manifest = _synced_pair(tmp_path)
    held, release, failed = threading.Event(), threading.Event(), []
    post = _a_post_holding(manifest, held, release, failed)
    threading.Timer(0.5, release.set).start()
    started = time.monotonic()
    sync_workspaces(main.root, "post", apply=True, overwrite=True)
    post.join()
    assert not failed, failed
    assert time.monotonic() - started >= 0.4, "the copy did not wait for the lock"
    assert json.loads(manifest.read_text(encoding="utf-8")) == {"products": {"x": {}}}


@pytest.mark.requirement("FR-3500")
def test_p0540_sync_copy_of_products_keeps_the_bytes_it_checked(tmp_path):
    """REL-K-006: the copy is byte for byte, so the digest it checked is the target's."""
    main, manifest = _synced_pair(tmp_path)
    (brought,) = [path for path in tmp_path.rglob("products.json") if path != manifest]
    payload = b'{\r\n "products": {"x": {}}\r\n}\r\n'
    brought.write_bytes(payload)
    sync_workspaces(main.root, "post", apply=True, overwrite=True)
    assert manifest.read_bytes() == payload


@pytest.mark.requirement("FR-3500")
def test_p0540_sync_copy_of_products_is_warned_and_skipped_when_the_lock_stays_held(
    tmp_path, monkeypatch
):
    """PFS-2186.14: past the wait the sync warns and leaves that file as it was."""
    main, manifest = _synced_pair(tmp_path)
    monkeypatch.setattr(_textio, "LOCK_WAIT", 0.3)
    held, release, failed = threading.Event(), threading.Event(), []
    post = _a_post_holding(manifest, held, release, failed)
    try:
        with pytest.warns(PyflightstreamWarning, match="stayed locked"):
            sync_workspaces(main.root, "post", apply=True, overwrite=True)
    finally:
        release.set()
        post.join()
    assert not failed, failed
    assert "x" not in json.loads(manifest.read_text(encoding="utf-8"))["products"]
