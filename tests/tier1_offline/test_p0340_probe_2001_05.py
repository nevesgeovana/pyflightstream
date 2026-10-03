"""Tier 1: the surface-sections, CCS-wing and boundary-layer commands are probed (FR-334).

Marker P0340-PROBE-2001-05, arm CN of GOAL-039, package QA-SPECS. The three commands of
PFS-2001.05 are EXPORT_SURFACE_SECTIONS, NEW_CCS_WING_CONTROL_SURFACE and
VOLUME_SECTION_BOUNDARY_LAYER. The licensed verdicts are the session's (the run of FR-333,
RPT-126); here each has a catalog entry that builds, the control surface is emitted in the
ten-argument PARAMETRIC form that round 2 completed, and each recorded status follows the
report of the run, with a planted mismatch and a planted missing reason as controls.
"""

from __future__ import annotations

import pytest

from pyflightstream.qa import specs
from tests.tier1_offline._p0340_probe_support import (
    RUN_LABEL_CN,
    build_script,
    chapter_rows,
    run_report,
    status_on,
    target_line,
    verdict_mismatches,
    verdicts_of,
)

#: Each command with the build the probe runs it on: the first two exist on 26.124; the
#: boundary-layer toggle was dropped from the manual at 26.120, so 26.101 is the last
#: build whose database holds it and a 26.124 run records it removed.
THREE = (
    ("EXPORT_SURFACE_SECTIONS", "26.124"),
    ("NEW_CCS_WING_CONTROL_SURFACE", "26.124"),
    ("VOLUME_SECTION_BOUNDARY_LAYER", "26.101"),
)
REASON_MIN_CHARS = 20


@pytest.mark.parametrize(("command", "build"), THREE)
def test_each_of_the_three_has_a_catalog_entry_that_builds_fr_334(command, build):
    """FR-334 R1, marker P0340-PROBE-2001-05: a catalog entry whose script emits the command."""
    assert command in specs.PROBE_SPECS
    assert target_line(command, build).startswith(command)
    assert f"PYFS_PROBE_END_{command}" in build_script(command, build)


def test_the_control_surface_is_emitted_in_the_ten_argument_parametric_form_fr_334():
    """FR-334 R1, marker P0340-PROBE-2001-05: the form RPT-097 completed, not the REAL form."""
    tokens = target_line("NEW_CCS_WING_CONTROL_SURFACE").split(" ")[1:]
    assert len(tokens) == 10
    assert tokens[-2:] == ["PARAMETRIC", "Y"]


def test_the_section_export_probe_reads_the_folder_because_the_manual_names_no_file_fr_334():
    """FR-334 R1, marker P0340-PROBE-2001-05: the one-section export has no file argument."""
    row = chapter_rows()["EXPORT_SURFACE_SECTIONS"]
    assert [arg["name"] for arg in row["args"]] == ["index"]
    entry = specs.PROBE_SPECS["EXPORT_SURFACE_SECTIONS"]
    assert "folder" in entry.effect_note
    assert entry.prelude is not None, "the working folder is listed when the script is built"


@pytest.mark.requirement("FR-333")
def test_each_status_equals_the_verdict_the_runs_report_records_fr_334():
    """FR-334 R2, marker P0340-PROBE-2001-05: the database follows the report of the run.

    Before the licensed run commits ``CMP-26124_<date>_qa-promote.yaml`` the two commands of
    26.124 are as they were and the toggle has no 26.124 row; afterwards every status equals the
    verdict its line records.
    """
    names = [name for name, _ in THREE]
    statuses = {name: status_on(name) for name in names}
    report = run_report(RUN_LABEL_CN)
    if report is None:
        assert statuses == {
            "EXPORT_SURFACE_SECTIONS": "documented",
            "NEW_CCS_WING_CONTROL_SURFACE": "documented",
            "VOLUME_SECTION_BOUNDARY_LAYER": None,
        }
        return
    verdicts = verdicts_of(report)
    assert verdict_mismatches(verdicts, statuses, names) == []


def test_a_planted_mismatch_is_found_for_the_three_fr_334():
    """FR-334 R2, marker P0340-PROBE-2001-05: the control of the status check."""
    report = {"NEW_CCS_WING_CONTROL_SURFACE": {"outcome": "verified"}}
    assert verdict_mismatches(report, {"NEW_CCS_WING_CONTROL_SURFACE": "documented"}, list(report))
    assert not verdict_mismatches(
        report, {"NEW_CCS_WING_CONTROL_SURFACE": "verified"}, list(report)
    )


def _unreasoned(entry: dict, build: str = "26.124") -> bool:
    """Whether a refused command keeps its emitted form with no stated reason (FR-334 R3)."""
    row = entry["versions"].get(build)
    if not isinstance(row, dict) or row.get("status") not in ("broken", "removed"):
        return False
    return len(str(row.get("note") or "")) < REASON_MIN_CHARS


def test_a_command_the_solver_refuses_carries_a_reason_fr_334():
    """FR-334 R3, marker P0340-PROBE-2001-05: broken or removed on 26.124 states why."""
    rows = chapter_rows()
    assert not [name for name, _ in THREE if _unreasoned(rows[name])]


def test_a_planted_refusal_without_a_reason_is_found_fr_334():
    """FR-334 R3, marker P0340-PROBE-2001-05: the control of the reason check."""
    planted = {"versions": {"26.124": {"status": "broken", "note": "x"}}}
    assert _unreasoned(planted)
    planted["versions"]["26.124"]["note"] = "the solver refused the form on its arguments"
    assert not _unreasoned(planted)
