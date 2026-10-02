"""Tier 1: the T1 probe specifications re-measured by tier 2 on 26.124 (FR-342, RPT-127).

The run's compatibility report is committed as ``reports/probes/RPT-127_<date>_evidence.yaml``,
byte for byte the report the run wrote (FlightStream 26.124, build 8172026, far field 5). It is
not under ``reports/compat/``: a report there obliges the command database to follow it, and that
promotion (FR-342 R3) is owed to 0.35.0, so these tests do not require it. They read RPT-127's
front matter against the outcomes the committed report records for the three commands that
26.124 holds, with a planted mismatch as the control of the comparison.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "reports"
PROBES = REPORTS / "probes"
#: The four entries of qa/_spec_t1.py less SURFACE_ROTATE, which no 26.124 view holds.
ON_26124 = ("ROTATE_SURFACE", "SET_NEW_UNSTEADY_SOLVER_ACTION", "SET_WAKE_TERMINATION_TIME_STEPS")
OUTCOMES = ("verified", "broken", "removed", "unprobed")


def _front_matter(number: int) -> tuple[Path, dict[str, str]]:
    found = sorted(REPORTS.glob(f"RPT-{number}_*.md"))
    if not found:
        pytest.fail(f"RPT-{number} is not in reports/: its native run owes it")
    lines = found[0].read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in lines[1:]:
        pytest.fail(f"{found[0].name} opens with no front matter between two '---' lines")
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    return found[0], fields


def _evidence() -> tuple[Path, dict]:
    """Return RPT-127's committed run report and its parsed document, or fail naming it."""
    found = sorted(PROBES.glob("RPT-127_*_evidence.yaml"))
    if len(found) != 1:
        pytest.fail(f"reports/probes/ holds {len(found)} RPT-127 evidence files, not one")
    return found[0], yaml.safe_load(found[0].read_text(encoding="utf-8"))


def recorded_outcomes(document: dict) -> dict[str, str | None]:
    """The outcome the run's report records for each command of the set that 26.124 holds."""
    commands = document.get("commands") or {}
    return {n: (commands.get(n) or {}).get("outcome") for n in ON_26124}


def mismatches(stated: dict[str, str], recorded: dict[str, str | None]) -> list[str]:
    """Each command whose verdict the report states otherwise than the run recorded, or not."""
    return [
        f"{n}: stated {stated.get(f'tier2_{n.lower()}')!r}, recorded {recorded.get(n)!r}"
        for n in ON_26124
        if stated.get(f"tier2_{n.lower()}") != recorded.get(n)
    ]


def test_rpt127_states_the_tier_2_verdict_the_run_recorded_for_each_command_fr_342():
    """P0340-T1-PROBE-SPECS, FR-342 R3: RPT-127 carries the three verdicts the run recorded."""
    report, fields = _front_matter(127)
    path, document = _evidence()
    assert document["fs_version"] == "26.124", path.name
    assert any("build #8172026" in line for line in document["solver_identity"]), path.name
    recorded = recorded_outcomes(document)
    assert set(recorded.values()) <= set(OUTCOMES), recorded
    assert "SURFACE_ROTATE" not in document["commands"], "no 26.124 view holds SURFACE_ROTATE"
    assert mismatches(fields, recorded) == [], report.name


def test_rpt127_names_the_digest_of_the_report_it_commits_fr_342():
    """P0340-T1-PROBE-SPECS, FR-342 R3: the report promoted in 0.35.0 is the one RPT-127 read.

    The digest is taken over LF line ends, so a checkout that rewrites them reads the same.
    """
    report, _ = _front_matter(127)
    path, _ = _evidence()
    digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert digest in report.read_text(encoding="utf-8"), (
        f"{report.name} does not name the SHA-256 of {path.name} ({digest})"
    )


def test_a_planted_verdict_mismatch_is_found_fr_342():
    """P0340-T1-PROBE-SPECS, FR-342 R3: the control of the comparison."""
    document = {"commands": {n: {"outcome": "verified"} for n in ON_26124}}
    recorded = recorded_outcomes(document)
    stated = {f"tier2_{n.lower()}": "verified" for n in ON_26124}
    assert mismatches(stated, recorded) == []
    stated["tier2_rotate_surface"] = "unprobed"
    assert mismatches(stated, recorded) == [
        "ROTATE_SURFACE: stated 'unprobed', recorded 'verified'"
    ]
    del stated["tier2_set_wake_termination_time_steps"]
    assert len(mismatches(stated, recorded)) == 2
    del document["commands"]["ROTATE_SURFACE"]
    assert recorded_outcomes(document)["ROTATE_SURFACE"] is None
