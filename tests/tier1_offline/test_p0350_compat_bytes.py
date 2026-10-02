"""Tier 1: a compat report that only corroborates leaves the chapter files byte for byte (FR-333).

Reading a chapter folds CRLF into LF, so writing back an unchanged chapter rewrote every
line end of a checkout that keeps CRLF (acoustics.yaml: 291 CR before, none after, no
change of content). The corroborate-only path must not write at all.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from pyflightstream.qa.compat import CORROBORATED, apply_compat
from tests.tier1_offline._p0340_probe_support import BUILD, COMMANDS


def _chapter_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "commands"
    shutil.copytree(COMMANDS, destination, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
    return destination


def _verified_report(tmp_path: Path) -> Path:
    document = {
        "schema": "pyflightstream-compat-report/1",
        "fs_version": BUILD,
        "date": "2026-10-02",
        "commands": {"ACOUSTIC_SOURCES": {"outcome": "verified", "detail": "planted"}},
    }
    path = tmp_path / "reports" / "compat" / "CMP-26124_2026-10-02_verified.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_a_corroborating_report_keeps_the_line_ends_of_a_crlf_chapter_fr_333(tmp_path):
    """FR-333: the corroborate-only path of apply_compat writes no byte of a CRLF chapter."""
    commands = _chapter_copy(tmp_path)
    report = _verified_report(tmp_path)
    first = apply_compat(report, repo_root=tmp_path, commands_dir=commands)
    assert [outcome for _, outcome, _ in first] == ["verified"]
    chapter = commands / "acoustics.yaml"
    crlf = chapter.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    chapter.write_bytes(crlf)
    assert crlf.count(b"\r") > 100, "the fixture chapter is CRLF"
    again = apply_compat(report, repo_root=tmp_path, commands_dir=commands)
    assert [outcome for _, outcome, _ in again] == [CORROBORATED]
    assert chapter.read_bytes() == crlf
