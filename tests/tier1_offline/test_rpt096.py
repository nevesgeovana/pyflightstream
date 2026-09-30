"""RPT-096: the report of licensed probe round 1 of 0.32.0 (package R1).

The report is read by the GOAL-037 L1 arm (probe round on 26.124 with the
executable hash) and by the owner's rule that only nondimensional values of a
blade or geometry are stated. These tests hold the same lines offline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STEM = "RPT-096_probe-round-1-on-26124_2026-09-30"
MD = REPO / "reports" / f"{STEM}.md"
SIDECAR = REPO / "reports" / f"{STEM}.json"

EXE_SHA = "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65"
#: The L1 arm's own pattern for a length of a blade or geometry with a unit.
LENGTH = re.compile(r"(?i)(diameter|chord|radius|span)[^.\n]{0,40}\d+(\.\d+)?\s?(m|mm)\b")
#: The 0.31 reports' guard for a dimensional value of a propeller or its run.
DIMENSIONAL = re.compile(
    r"\d\s?(?:N m|N|m/s|kg/m3|rev/min)\b|RPM\d|\"rpm\"|_Nm?\"|delta_time_s|velocity_m_s"
)
PROBES = (
    "B0_baseline",
    "C0_ccs_import_file",
    "C1_ccs_wing",
    "C2_ccs_wing_subdiv",
    "C3_ccs_wing_control",
    "C4_ccs_fuselage",
    "C5_ccs_revolve",
    "G35a_relaxed_te_axial",
    "G35b_relaxed_te_azimuth",
    "D1_delete_surfaces",
    "W1_wake_stab_disable",
    "A0_acoustic_sources_off",
    "A1_acoustic_chain",
)


def test_rpt096_names_the_build_the_hash_and_the_release():
    text = MD.read_text(encoding="utf-8")
    assert "26.124" in text and "8172026" in text and EXE_SHA in text
    assert re.search(r"(?<![\d.])0\.32(?![\d])", text)
    for word in ("probe", "ACOUSTIC", "CCS", "DELETE_SURFACES", "DISABLE"):
        assert word in text, word


def test_rpt096_has_one_row_per_probe_and_its_sidecar_agrees():
    text = MD.read_text(encoding="utf-8")
    data = json.loads(SIDECAR.read_text(encoding="utf-8"))
    assert data["report"] == "RPT-096"
    assert data["executable_sha256"] == EXE_SHA
    assert [p["id"] for p in data["probes"]] == list(PROBES)
    for probe in PROBES:
        assert probe in text, probe
    for row in data["probes"]:
        assert row["verdict"] and row["moved"] and row["evidence"], row["id"]


def test_rpt096_records_the_refusal_and_states_what_it_does_not_establish():
    text = MD.read_text(encoding="utf-8")
    data = json.loads(SIDECAR.read_text(encoding="utf-8"))
    control = next(p for p in data["probes"] if p["id"] == "C3_ccs_wing_control")
    assert "refus" in control["verdict"].lower()
    assert "NEW_CCS_WING_CONTROL_SURFACE" in text
    assert "## What this round does not establish" in text
    assert data["not_established"]
    lowered = text.lower()
    assert "direction" in lowered and "observer time" in lowered


def test_rpt096_states_no_length_and_no_dimensional_value_of_a_blade():
    for path in (MD, SIDECAR):
        text = path.read_text(encoding="utf-8")
        assert not LENGTH.search(text), path.name
        assert not DIMENSIONAL.search(text), path.name
        assert chr(0x2014) not in text and chr(0x2013) not in text, path.name


def test_rpt096_is_indexed_where_the_tree_indexes_reports():
    index = (REPO / "reports" / "README.md").read_text(encoding="utf-8")
    assert f"[RPT-096]({STEM}.md)" in index
    # Before the integration the entry is the R1 fragment; scripts/assemble_changelog.py
    # then folds it into the change log's [Unreleased] section and deletes the fragment.
    fragment_path = REPO / "changelog.d" / "R1.md"
    if fragment_path.is_file():
        fragment = fragment_path.read_text(encoding="utf-8")
    else:
        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        fragment = changelog.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert "reports/RPT-096" in fragment


def test_rpt096_totals_count_readings_and_the_report_says_so():
    """The runner's 14 verified are (probe, command) readings; 11 commands are distinct."""
    text = MD.read_text(encoding="utf-8")
    totals = json.loads(SIDECAR.read_text(encoding="utf-8"))["totals"]
    assert totals["commands_verified"] == 14
    assert totals["distinct_commands_verified"] == 11
    assert "14 verified readings of 11 distinct commands" in text
    assert "14 commands verified" not in text
    assert f"{totals['commands_unprobed']} accepted and unprobed readings" in text
    assert f"{totals['commands_broken']} broken" in text


def test_rpt096_stays_the_probe_report_and_not_a_ccs_or_acoustic_confirmation():
    """The L1 arm counts a 0.32 report with these words as a confirmation."""
    for path in (MD, SIDECAR):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?i)confirm", text), path.name
        assert "unsteady_rotor" not in text, path.name
