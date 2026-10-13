"""P0400-WSQUERY: the point card's evidence and archives (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import hashlib
from zipfile import ZipFile

import pytest

from pyflightstream.workspace.ledger import point_card
from tests.tier1_offline.test_p0350_query_history import RUN, _record, _write

pytestmark = pytest.mark.requirement("P0400-WSQUERY")

POINT = "sims/sim_2006/datapoints/DP-A0"


def _card_workspace(tmp_path, *outputs: str):
    _write(tmp_path / "runs.json", [_record(outputs=list(outputs), point_name="A0")])
    return tmp_path


def _evidence(card, name):
    (item,) = [row for row in card["evidence"] if row["path"].endswith(name)]
    return item


def test_p0400_wsquery_a_binary_output_is_named_by_size_and_digest(tmp_path):
    """P0400-WSQUERY (PFS-2101.004): a binary export prints no decoded garbage."""
    payload = bytes(range(256)) * 300
    target = tmp_path / POINT / "surface.dat"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    card = point_card(_card_workspace(tmp_path, "datapoints/DP-A0/surface.dat"), RUN)
    item = _evidence(card, "surface.dat")
    assert item["last_lines"] == [] and item["binary"] is True
    assert item["bytes"] == len(payload)
    assert item["sha256"] == hashlib.sha256(payload).hexdigest()


def test_p0400_wsquery_binary_bytes_without_a_nul_are_not_decoded(tmp_path):
    """P0400-WSQUERY (PFS-2101.004): invalid UTF-8 is summarized without decoded garbage."""
    payload = bytes([255]) * 72000
    target = tmp_path / POINT / "surface.dat"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    card = point_card(_card_workspace(tmp_path, "datapoints/DP-A0/surface.dat"), RUN)
    item = _evidence(card, "surface.dat")
    assert item["last_lines"] == []
    assert item["sha256"] == hashlib.sha256(payload).hexdigest()


def test_p0400_wsquery_a_long_text_file_shows_its_last_lines(tmp_path):
    """P0400-WSQUERY (PFS-2101.004): the last five lines come from the tail alone."""
    target = tmp_path / POINT / "P2006-A0_log.txt"
    target.parent.mkdir(parents=True)
    target.write_text("".join(f"iteration {n}\n" for n in range(20000)), encoding="utf-8")
    card = point_card(_card_workspace(tmp_path), RUN)
    item = _evidence(card, "P2006-A0_log.txt")
    assert item["last_lines"] == [f"iteration {n}" for n in range(19995, 20000)]
    assert "binary" not in item


def test_p0400_wsquery_text_evidence_does_not_read_the_whole_file(tmp_path, monkeypatch):
    """P0400-WSQUERY (PFS-2101.004): show never calls the whole-file text reader."""
    target = tmp_path / POINT / "iterations.log"
    target.parent.mkdir(parents=True)
    target.write_text("step\n" * 20000, encoding="utf-8")
    real = type(target).read_text

    def guarded(path, *args, **kwargs):
        assert path != target, "evidence was read whole"
        return real(path, *args, **kwargs)

    monkeypatch.setattr(type(target), "read_text", guarded)
    card = point_card(_card_workspace(tmp_path), RUN)
    assert _evidence(card, target.name)["last_lines"] == ["step"] * 5


def test_p0400_wsquery_a_binary_zip_member_has_a_streamed_digest(tmp_path):
    """P0400-WSQUERY (PFS-2101.004): compacted evidence has the same binary summary."""
    payload = bytes(range(256)) * 300
    (tmp_path / "sims").mkdir()
    with ZipFile(tmp_path / "sims/sim_2006.zip", "w") as archive:
        archive.writestr("datapoints/DP-A0/surface.dat", payload)
    card = point_card(_card_workspace(tmp_path, "datapoints/DP-A0/surface.dat"), RUN)
    item = _evidence(card, "surface.dat")
    assert item["last_lines"] == []
    assert item["bytes"] == len(payload)
    assert item["sha256"] == hashlib.sha256(payload).hexdigest()


def test_p0400_wsquery_a_point_card_lists_only_its_own_archives(tmp_path):
    """P0400-WSQUERY (PFS-2094.020): the archives of A01 and A0_b are not A0's."""
    for folder in ("DP-A0", "DP-A01", "DP-A0_b+05"):
        archived = tmp_path / "sims/sim_2006/datapoints" / folder / "archive/20261001/x.txt"
        archived.parent.mkdir(parents=True)
        archived.write_text("x\n", encoding="utf-8")
    card = point_card(_card_workspace(tmp_path), RUN)
    archives = card["chain"]["archives"]
    assert archives and all("/DP-A0/archive/" in path for path in archives), archives
