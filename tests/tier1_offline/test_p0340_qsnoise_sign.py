"""RPT-132: the exploratory study of the QS-NOISE sign (FR-337, marker P0340-QSNOISE-SIGN).

FR-337 asks for an exploratory report, RPT-132, that studies why route A of
QS-NOISE (FR-300) disagrees in sign with the unsteady acoustic reference, and
for nothing to read it: no check, gate or plan status. These tests hold the
report's front matter (``exploratory: true``), the three things it must state
(what it tested, what it found, what it could not decide), and the isolation:
no file under ``src/``, ``scripts/`` or ``tests/`` other than this one names the
report, with a planted reference as the control of the scan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STEM = "RPT-132_qsnoise-route-a-sign_2026-10-01"
REPORT = REPO / "reports" / f"{STEM}.md"
SIDECAR = REPO / "reports" / f"{STEM}.json"
#: The one identity FR-337 keeps out of the code, the scripts and the tests.
NEEDLE = b"RPT-132"
SCANNED = ("src", "scripts", "tests")
LENGTH = re.compile(r"(?i)(diameter|chord|radius|span)[^.\n]{0,40}\d+(\.\d+)?\s?(m|mm)\b")
DIMENSIONAL = re.compile(
    r"\d\s?(?:N m|N|m/s|kg/m3|rev/min|Pa|kHz|Hz|dB|mm|m|s|kg)\b"
    r"|RPM\d|\"rpm\"|_Nm?\"|delta_time_s|velocity_m_s"
)


def _front_matter(text: str) -> dict[str, str]:
    """Return the ``key: value`` lines between the opening and closing ``---``."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            return fields
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return {}


def _files_naming_the_report(root: Path, exempt: Path) -> list[str]:
    """Return every file under the scanned folders of ``root`` that names the report.

    Compiled bytecode is skipped: it holds this module's own constants.
    """
    found = []
    for top in SCANNED:
        for path in sorted((root / top).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.resolve() == exempt.resolve():
                continue
            if NEEDLE in path.read_bytes():
                found.append(path.relative_to(root).as_posix())
    return found


def test_rpt132_is_exploratory_and_states_what_it_tested_found_and_left_open_fr_337():
    """P0340-QSNOISE-SIGN, FR-337 R1: exploratory, no threshold, three statements."""
    text = REPORT.read_text(encoding="utf-8")
    fields = _front_matter(text)
    assert fields.get("exploratory") == "true", fields
    assert fields.get("report") == "RPT-132", fields
    for heading in (
        "## 3. What was tested",
        "## 4. What was found",
        "## 5. What this does not decide",
    ):
        assert heading in text, heading
    assert "sets no threshold" in text
    sidecar = json.loads(SIDECAR.read_text(encoding="utf-8"))
    assert sidecar["report"] == "RPT-132" and sidecar["exploratory"] is True
    for path in (REPORT, SIDECAR):
        body = path.read_text(encoding="utf-8")
        assert not LENGTH.search(body), path.name
        assert not DIMENSIONAL.search(body), path.name
        assert chr(0x2014) not in body and chr(0x2013) not in body, path.name


def test_the_dimensional_guard_finds_each_unit_form_and_passes_ratios_fr_337():
    """P0340-QSNOISE-SIGN, FR-337 R1: the guard's control, one planted value per unit form.

    Each planted dimensional value is found by the length or the unit pattern,
    and the nondimensional values the report does state are not.
    """
    planted = (
        "a diameter of 1.2 m",
        "a chord of 80 mm",
        "a bare 0.75 m",
        "12 N",
        "3.4 N m",
        "50 m/s",
        "1.225 kg/m3",
        "2400 rev/min",
        "101325 Pa",
        "160 Hz",
        "1.5 kHz",
        "92 dB",
        "0.02 s",
        "3 kg",
        "RPM2400",
        '"rpm"',
        'thrust_N"',
        "delta_time_s",
        "velocity_m_s",
    )
    for value in planted:
        assert LENGTH.search(value) or DIMENSIONAL.search(value), value
    for value in (
        "r/R 2.73",
        "k r 0.45",
        "15.0 deg",
        "16 samples",
        "1.00 step",
        "a gain of -0.93",
        "tip Mach 0.5",
    ):
        assert not LENGTH.search(value) and not DIMENSIONAL.search(value), value


def test_nothing_under_src_scripts_or_tests_but_this_test_names_rpt132_fr_337(tmp_path):
    """P0340-QSNOISE-SIGN, FR-337 R2: no check, gate or plan status can read RPT-132.

    The control plants the identity in a copy of the three folders: a module
    under ``src/`` and a script under ``scripts/`` are found, and a file at this
    test's own place is not, so the scan is shown to find what it looks for.
    """
    me = Path(__file__)
    assert _files_naming_the_report(REPO, me) == []

    planted = tmp_path / "tree"
    exempt = planted / me.relative_to(REPO)
    for path, text in (
        (planted / "src" / "pkg" / "gate.py", "READS = 'RPT-132'\n"),
        (planted / "scripts" / "check.txt", "see RPT-132\n"),
        (planted / "tests" / "clean.py", "nothing here\n"),
        (exempt, "the marker test names RPT-132\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    found = sorted(_files_naming_the_report(planted, exempt))
    assert found == ["scripts/check.txt", "src/pkg/gate.py"]
