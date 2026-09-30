"""RPT-097 and RPT-098: the reports of licensed rounds 2 and 3 of 0.32.0 (package FX2).

They are read by the GOAL-037 L1 arm (report on 26.124 with the executable hash)
and by the owner's rule that only nondimensional values of a blade or geometry
are stated. These tests hold the same lines offline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STEMS = {
    "RPT-097": "RPT-097_ccs-confirmation-round-2-on-26124_2026-09-30",
    "RPT-098": "RPT-098_acoustic-chain-wake-and-surface-removal-round-3-on-26124_2026-09-30",
}
EXE_SHA = "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65"
LENGTH = re.compile(r"(?i)(diameter|chord|radius|span)[^.\n]{0,40}\d+(\.\d+)?\s?(m|mm)\b")
DIMENSIONAL = re.compile(
    r"\d\s?(?:N m|N|m/s|kg/m3|rev/min)\b|RPM\d|\"rpm\"|_Nm?\"|delta_time_s|velocity_m_s"
)


def _paths(report: str) -> tuple[Path, Path]:
    stem = STEMS[report]
    return REPO / "reports" / f"{stem}.md", REPO / "reports" / f"{stem}.json"


@pytest.mark.parametrize("report", sorted(STEMS))
def test_the_report_names_the_release_the_build_and_the_hash(report):
    md, sidecar = _paths(report)
    text = md.read_text(encoding="utf-8")
    assert "26.124" in text and "8172026" in text and EXE_SHA in text
    assert re.search(r"(?<![\d.])0\.32(?![\d])", text)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["report"] == report and data["executable_sha256"] == EXE_SHA
    assert "## What these rounds do not establish" in text or (
        "## What this round does not establish" in text
    )
    assert data["not_established"]


def test_rpt097_says_which_ccs_items_are_confirmed_and_which_is_not():
    md, sidecar = _paths("RPT-097")
    text = md.read_text(encoding="utf-8")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    verdicts = {item["id"]: item["verdict"] for item in data["items"]}
    for confirmed in (
        "CCS1-WING",
        "CCS1-FUSELAGE",
        "CCS1-REVOLUTION",
        "CCS2-PARAMETRIC",
        "G35-AXIAL",
        "G35-AZIMUTH",
    ):
        assert verdicts[confirmed] == "confirmed", confirmed
        assert confirmed in text
    assert verdicts["CCS2-REAL"] == "not confirmed"
    lowered = text.lower()
    assert "confirmed" in lowered and "not confirmed" in lowered
    assert "PARAMETRIC" in text and "REAL" in text
    assert "FAILED_EXECUTION" in text and "RPT-097" in text
    assert "the two saves differ" in lowered or "two saved simulations differ" in lowered


def test_rpt098_names_the_chain_the_g4_comparison_and_the_g9_inventory():
    md, sidecar = _paths("RPT-098")
    text = md.read_text(encoding="utf-8")
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    for word in ("COMPUTE_ACOUSTIC_SIGNALS", "EXPORT_ACOUSTIC_SIGNALS", "unsteady_rotor"):
        assert word in text, word
    for word in ("DISABLE", "ENABLE", "absent"):
        assert word in text, word
    assert "Body, Base, Blade2" in text and "index 3" in text
    assert "COMPLETED_MAX_ITER" in text and "3301" in text
    assert "not a G9 defect" in text
    assert data["not_established"]


@pytest.mark.parametrize("report", sorted(STEMS))
def test_the_reports_state_no_length_no_dimensional_value_and_no_dash(report):
    for path in _paths(report):
        text = path.read_text(encoding="utf-8")
        assert not LENGTH.search(text), path.name
        assert not DIMENSIONAL.search(text), path.name
        assert chr(0x2014) not in text and chr(0x2013) not in text, path.name
        assert "1.8288" not in text and "XPROP" not in text, path.name


def test_the_reports_are_indexed_and_carry_no_requirement_in_the_changelog():
    index = (REPO / "reports" / "README.md").read_text(encoding="utf-8")
    fragment = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    for report, stem in STEMS.items():
        assert f"[{report}]({stem}.md)" in index
        assert f"reports/{report}" in fragment
        assert f"(no requirement: licensed report {report}" in fragment
