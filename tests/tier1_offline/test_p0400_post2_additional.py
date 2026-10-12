"""P0400-DIGEST: the additional post hashes a saved simulation once per post.

At the 0.40.0 base every extraction re-hashed its point's saved simulation, so
several extractions of one point hashed the same file again on every post.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pyflightstream.post._additional as additional
from pyflightstream._digest import file_sha256


def _pair(tmp_path):
    saved = tmp_path / "point.fsm"
    saved.write_bytes(b"saved simulation")
    digest = file_sha256(saved)
    workspace = SimpleNamespace(
        sim_dir=lambda _sim: tmp_path, changed_extraction_file=lambda _extraction: None
    )
    extraction = SimpleNamespace(run_id="r", fsm="point.fsm", fsm_sha256=digest, sim_id="1")
    point = SimpleNamespace(outputs_sha256={"point.fsm": digest})
    return saved, workspace, extraction, point


def test_p0400_digest_two_extractions_of_one_point_hash_it_once(tmp_path, monkeypatch):
    """P0400-DIGEST: one post's cache answers the second extraction of one file."""
    saved, workspace, extraction, point = _pair(tmp_path)
    calls: list[object] = []
    monkeypatch.setattr(
        additional, "file_sha256", lambda path: calls.append(path) or file_sha256(path)
    )
    digests: dict = {}
    for _ in range(2):
        assert additional._current_extraction(workspace, extraction, point, digests) is None
    assert len(calls) == 1


def test_p0400_digest_a_changed_file_is_hashed_again(tmp_path, monkeypatch):
    """P0400-DIGEST: a file whose size or mtime changed is not answered from the cache."""
    saved, workspace, extraction, point = _pair(tmp_path)
    digests: dict = {}
    assert additional._current_extraction(workspace, extraction, point, digests) is None
    saved.write_bytes(b"another simulation, saved since")
    os.utime(saved, ns=(1, 1))
    reason = additional._current_extraction(workspace, extraction, point, digests)
    assert reason is not None and "stale" in reason
