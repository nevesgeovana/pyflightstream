"""Tier 1: the calibration interpolates its phase as an angle and writes valid TOML (0.40.0)."""

import math

from pyflightstream.cases.corrections import CalibrationRow, calibration_text, parse_calibration


def _phase_at(phases, j):
    rows = [
        CalibrationRow("THRUST", 0.5, 0.0, 0.0, 0.0, 1.0, 1.0, phases[0]),
        CalibrationRow("THRUST", 0.7, 0.0, 0.0, 0.0, 1.0, 1.0, phases[1]),
    ]
    return parse_calibration(calibration_text("table", rows)).lookup("THRUST", {"J": j})


def test_p0400_phase_straddling_the_wrap_interpolates_through_zero():
    """P0400-PHASE-WRAP (PFS-2081.18): 350 and 10 degrees meet at 0, not at 180."""
    phase = _phase_at((350.0, 10.0), 0.6).coefficients[3]
    assert math.isclose(math.cos(math.radians(phase)), 1.0, abs_tol=1e-9), phase
    quarter = _phase_at((350.0, 10.0), 0.55).coefficients[3]
    assert math.isclose(quarter % 360.0, 355.0, abs_tol=1e-9), quarter


def test_p0400_phase_within_half_a_turn_interpolates_as_plain_numbers():
    """P0400-PHASE-WRAP (PFS-2081.18): a cell with no wrap gives exactly what it gave before."""
    assert _phase_at((10.0, 30.0), 0.6).coefficients[3] == 0.5 * 10.0 + 0.5 * 30.0
    assert _phase_at((-10.0, 10.0), 0.6).coefficients[3] == 0.0


def test_p0400_calibration_text_escapes_control_characters():
    """P0400-CALIBRATION-TOML (PFS-2095.040): a newline or tab in free text reads back unchanged."""
    row = CalibrationRow("THRUST", 0.6, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0)
    text = calibration_text(
        "sector_offset", [row], source_run_id="run\t1", description='line1\nline2 "q" \\ \x01'
    )
    read = parse_calibration(text)
    assert read.description == 'line1\nline2 "q" \\ \x01'
    assert read.source_run_id == "run\t1"
