"""The sweeper keeps the drag labels observed in each build's export.

The 26.125 fixture is a byte cut of one solver export of the 26.125 probe
campaign; ``fixtures/s10_26125/PROVENANCE.md`` names the file, its sha256 and
the one line changed.
"""

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
        report.values,
        [
            [
                2.0,
                0.0,
                30.0,
                0.1487,
                -0.1829,
                -0.0034,
                -0.0086,
                0.1473,
                0.0012,
                0.1919,
                0.1738,
                0.0038,
            ]
        ],
    )
    frame = to_table(report)
    assert frame["CDp"].tolist() == [0.1473]
    assert frame["CDv"].tolist() == [0.0012]
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


@pytest.mark.parametrize("replacement", ["CDp, CDo", "CDp, other", "CDv, CDp"])
def test_an_unmatched_sweep_header_names_both_accepted_layouts(replacement):
    """P0370-S10-SIMCENTER-HEADERS (FR-423): the refusal lists the CDi/CDo and CDp/CDv layouts."""
    text = (FIXTURES / "s10_26125/sweep_26.125.txt").read_text(encoding="utf-8")
    with pytest.raises(MalformedOutputError) as refused:
        parse_sweep_spreadsheet(text.replace("CDp, CDv", replacement))
    said = str(refused.value)
    assert "one of 2 layouts" in said, said
    assert "'CL', 'CDi', 'CDo', 'CMx'" in said and "'CL', 'CDp', 'CDv', 'CMx'" in said, said
