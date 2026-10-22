"""Tier 1: the command database states the measured arity of the two CCS export commands (FR-335).

Marker P0340-ARITY-2003-06, arm CN of GOAL-039, package QA-SPECS. EXPORT_FUSELAGE_CCS_FILE and
EXPORT_REVOLVE_CCS_FILE are emitted with the six arguments of the manual's signature heading
(the parameter table documents four). The licensed probe writes the file each command names and
RPT-126 states the arity measured; here the database arity, the emitted line and the probe's
reading of the file agree on six, and once the run's report states an arity it must equal that
one, with a planted mismatch as the control.
"""

from __future__ import annotations

import re

import pytest

from pyflightstream.qa import specs
from tests.tier1_offline._p0340_probe_support import (
    RUN_LABEL_CN,
    artifacts_in,
    chapter_rows,
    run_report,
    target_line,
    verdicts_of,
)

EXPORTS = ("EXPORT_FUSELAGE_CCS_FILE", "EXPORT_REVOLVE_CCS_FILE")
#: ``arity of N`` or ``N arguments``; the bare word followed by any digits also read a report id
#: (``arity is undetermined (RPT-126 ...)`` stated an arity of 126).
ARITY_WORDS = re.compile(r"\barity\s+(?:of\s+)?(\d+)\b|\b(\d+)\s+arguments\b", re.IGNORECASE)


def database_arity(command: str) -> int:
    """Count the arguments the database emits for a command, the file path left out."""
    args = chapter_rows()[command]["args"]
    return len([arg for arg in args if arg["name"] != "file"])


def emitted_arity(command: str) -> int:
    """Count the arguments of the probe's emitted line, the file path on the next line left out."""
    return len(target_line(command).split(" ")) - 1


def stated_arity(detail: str) -> int | None:
    """Read the arity a report's verdict line states, None when it states none."""
    found = ARITY_WORDS.search(detail or "")
    return int(found.group(1) or found.group(2)) if found else None


def arity_mismatch(detail: str, emitted: int) -> bool:
    """Whether a stated arity differs from the emitted one (a line stating none cannot differ)."""
    stated = stated_arity(detail)
    return stated is not None and stated != emitted


@pytest.mark.parametrize("command", EXPORTS)
def test_the_database_and_the_emitted_line_agree_on_the_arity_fr_335(command):
    """FR-335, marker P0340-ARITY-2003-06: the emitter writes as many arguments as the entry."""
    assert command in specs.PROBE_SPECS
    assert database_arity(command) == emitted_arity(command) == 6


@pytest.mark.parametrize("command", EXPORTS)
def test_the_arity_equals_the_one_the_runs_report_records_fr_335(command):
    """FR-335 and FR-335, marker P0340-ARITY-2003-06: the arity the report states is emitted.

    On 26.124 the written file did not separate the arities, so the committed report states
    that no count is claimed; the test asserts that statement positively, and an arity stated
    by a later report must equal the emitted one.
    """
    report = run_report(RUN_LABEL_CN)
    assert report is not None, "the committed report of the arity arm is missing"
    detail = verdicts_of(report)[command].get("detail", "")
    if stated_arity(detail) is None:
        assert "no count of arguments is claimed" in detail, detail
    else:
        assert not arity_mismatch(detail, emitted_arity(command))


def test_a_planted_arity_mismatch_is_found_fr_335():
    """FR-335, marker P0340-ARITY-2003-06: the control of the arity check."""
    assert arity_mismatch("the file was written with an arity of 4", 6)
    assert not arity_mismatch("the file was written with an arity of 6", 6)
    assert not arity_mismatch("no arity stated", 6)
    assert arity_mismatch("the file was written with 4 arguments", 6)
    # A report id in the sentence is not an arity (PFS-2135.010).
    undetermined = "the arity is undetermined (RPT-126 states the five forms)"
    assert stated_arity(undetermined) is None
    assert not arity_mismatch(undetermined, 6)


@pytest.mark.parametrize("command", EXPORTS)
def test_the_probe_judges_the_file_the_command_writes_fr_335(command, tmp_path):
    """FR-335, marker P0340-ARITY-2003-06: absent or empty is broken, a written file verified."""
    entry = specs.PROBE_SPECS[command]
    name = "fuselage_export.csv" if "FUSELAGE" in command else "revolve_export.csv"
    assert entry.assert_effect(artifacts_in(tmp_path)) is False
    (tmp_path / name).write_text("", encoding="utf-8")
    assert entry.assert_effect(artifacts_in(tmp_path)) is False
    (tmp_path / name).write_text("Component;X\nCrossSection;0;0;0\n", encoding="utf-8")
    assert entry.assert_effect(artifacts_in(tmp_path)) is True
    assert "2 lines" in entry.observe(artifacts_in(tmp_path))


def test_the_export_reading_never_quotes_the_numbers_of_the_file_fr_335(tmp_path):
    """FR-335, marker P0340-ARITY-2003-06: the evidence line states size and first line only."""
    (tmp_path / "fuselage_export.csv").write_text("Component;X\n1.0;2.0;3.0\n", encoding="utf-8")
    said = specs.PROBE_SPECS["EXPORT_FUSELAGE_CCS_FILE"].observe(artifacts_in(tmp_path))
    assert "2.0" not in said and "bytes" in said and "Component;X" in said
