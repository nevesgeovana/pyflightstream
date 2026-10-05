"""The sweeper keeps the drag labels observed in each build's export."""

from pathlib import Path

import numpy as np
import pytest

from pyflightstream.results import MalformedOutputError, parse_sweep_spreadsheet, to_table

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_simcenter_sweeper_keeps_every_printed_column():
    """P0370-S10-SIMCENTER-HEADERS (FR-423): the observed sweep header and all values survive."""
    text = (FIXTURES / "s10_26125/sweep_26.125.txt").read_text(encoding="utf-8")
    report = parse_sweep_spreadsheet(text, requested_version="26.125")
    assert report.columns == (
        "AOA (deg)",
        "Beta (deg)",
        "Velocity (m/sec)",
        "Cx",
        "Cy",
        "Cz",
        "CL",
        "CDp",
        "CDv",
        "CMx",
        "CMy",
        "CMz",
    )
    np.testing.assert_array_equal(
        report.values, [[2.0, 0.0, 30.0, 0.1, 0.2, 0.3, 0.4, 0.05, 0.006, 0.7, 0.8, 0.9]]
    )
    frame = to_table(report)
    assert frame["CDp"].tolist() == [0.05]
    assert frame["CDv"].tolist() == [0.006]
    assert "CDi" not in frame and "CDo" not in frame


def test_the_legacy_sweeper_still_keeps_its_original_columns():
    """P0370-S10-SIMCENTER-HEADERS (FR-423): the recorded legacy export is unchanged."""
    text = (FIXTURES / "sweeper_spreadsheet_26.123.txt").read_text(encoding="utf-8")
    report = parse_sweep_spreadsheet(text)
    assert report.columns[7:9] == ("CDi", "CDo")
    np.testing.assert_array_equal(report.field("CDi"), [-0.0125, -0.0082, 0.0046])
    np.testing.assert_array_equal(report.field("CDo"), [0.0, 0.0, 0.0])


@pytest.mark.parametrize("replacement", ["CDp, CDo", "CDp, CDp", "CDp, other"])
def test_an_unobserved_sweep_layout_is_still_refused(replacement):
    """P0370-S10-SIMCENTER-HEADERS (FR-423): recognizing a new split does not unpin the table."""
    text = (FIXTURES / "s10_26125/sweep_26.125.txt").read_text(encoding="utf-8")
    with pytest.raises(MalformedOutputError):
        parse_sweep_spreadsheet(text.replace("CDp, CDv", replacement))
