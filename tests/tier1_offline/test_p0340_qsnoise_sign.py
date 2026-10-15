"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


STEM = "RPT-132_qsnoise-route-a-sign_2026-10-01"


REPORT = REPO / "reports" / f"{STEM}.md"


SIDECAR = REPO / "reports" / f"{STEM}.json"


LENGTH = re.compile(r"(?i)(diameter|chord|radius|span)[^.\n]{0,40}\d+(\.\d+)?\s?(m|mm)\b")


DIMENSIONAL = re.compile(
    r"\d\s?(?:N m|N|m/s|kg/m3|rev/min|Pa|kHz|Hz|dB|mm|m|s|kg)\b"
    r"|RPM\d|\"rpm\"|_Nm?\"|delta_time_s|velocity_m_s"
)


def test_the_dimensional_guard_finds_each_unit_form_and_passes_ratios_fr_337():
    """P0340-QSNOISE-SIGN, FR-337: the guard's control, one planted value per unit form.

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
