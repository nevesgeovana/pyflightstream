"""P0400-WS3-SETUP: setup standards evidence and the setup library writer."""

from __future__ import annotations

from pathlib import Path

from pyflightstream.workspace.setup_standards import setup_entry_evidence, write_setup_library


def test_p0400_alias_build_reports_the_canonical_rows_evidence():
    """P0400-SETUP-ALIAS (PFS-2094.025): a build named by alias reads its canonical version row."""
    available, evidence = setup_entry_evidence("wake_relaxation", "26.0")
    assert available
    assert "build 26.000: documented" in evidence, evidence
    assert "no recorded evidence" not in evidence
    assert setup_entry_evidence("wake_relaxation", "26.0") == setup_entry_evidence(
        "wake_relaxation", "26.000"
    )


def test_p0400_existing_non_utf8_user_file_is_preserved(tmp_path: Path):
    """P0400-SETUP-CP1252 (PFS-2095.033): a cp1252 user file is reported preserved, not decoded."""
    destination = tmp_path / "inputs" / "setups"
    destination.mkdir(parents=True)
    user_file = destination / "SETUP_GUIDELINES.md"
    original = "Notes on the création of my standards\n".encode("cp1252")
    user_file.write_bytes(original)
    result = write_setup_library(tmp_path, fs_version="26.124", guidelines=True)
    assert result == {"SETUP_GUIDELINES.md": "preserved"}
    assert user_file.read_bytes() == original
    again = write_setup_library(tmp_path / "fresh", fs_version="26.124", guidelines=True)
    assert again == {"SETUP_GUIDELINES.md": "created"}
    twice = write_setup_library(tmp_path / "fresh", fs_version="26.124", guidelines=True)
    assert twice == {"SETUP_GUIDELINES.md": "unchanged"}
