"""Read the omitted exponent marker observed in the 26.125 probe campaign.

The fixture is a byte cut of one solver export of that campaign;
``fixtures/s10_26125/PROVENANCE.md`` names the file, its sha256 and the one
line changed.
"""

from pathlib import Path

import pytest

from pyflightstream.results import MalformedOutputError, parse_number, parse_probe_points, to_table


def test_probe_subnormal_fields_do_not_discard_the_export():
    """P0370-S10-SIMCENTER-HEADERS (FR-423): preserve all columns, including tiny printed fields."""
    path = Path(__file__).parent / "fixtures/s10_26125/probe_exponents_26.125.txt"
    report = parse_probe_points(path.read_text(encoding="utf-8"), "26.125")
    assert report.values.shape == (1, 16)
    assert report.field("momentum_thickness")[0] == float("0.2964e-322")
    assert report.field("thickness")[0] == float("0.5305e-314")
    assert report.field("momentum_thickness")[0] > 0
    frame = to_table(report)
    assert set(report.columns) <= set(frame.columns)
    assert frame["thickness"].tolist() == [float("0.5305e-314")]


@pytest.mark.parametrize("token", ["0.2964-322", "-0.5305-314", "+0.1234+100"])
def test_three_digit_exponents_keep_their_sign_and_value(token):
    """P0370-S10-SIMCENTER-HEADERS (FR-423): the omitted E leaves the signed exponent intact."""
    assert parse_number(token) == float(token[:-4] + "e" + token[-4:])


@pytest.mark.parametrize("token", ["1-2", "1.0-2", "1.0--123", "0.1-123junk", "1-123"])
def test_non_solver_number_spellings_still_refuse(token):
    """P0370-S10-SIMCENTER-HEADERS (FR-423): do not interpret expressions or truncated exponents."""
    with pytest.raises(MalformedOutputError):
        parse_number(token)
