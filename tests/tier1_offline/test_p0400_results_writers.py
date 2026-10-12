"""P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

from __future__ import annotations

import pytest

from pyflightstream.results import (
    parse_loads,
    to_csv,
    to_table,
    write_table,
)
from pyflightstream.results.core import MalformedOutputError
from tests.tier1_offline.test_p0400_results_loads_support import STEADY

pytestmark = pytest.mark.requirement("P0400-RESULTS-TABLES")


def test_p0400_results_to_csv_can_refuse_to_overwrite(tmp_path):
    """P0400-RESULTS (PFS-2096.030): to_csv offers the choice write_table offers."""
    report = parse_loads(STEADY)
    target = to_csv(report, tmp_path / "loads.csv")
    before = target.read_bytes()
    with pytest.raises(MalformedOutputError, match="already exists"):
        to_csv(report, target)
    with pytest.raises(MalformedOutputError, match="already exists"):
        write_table(to_table(report), target)
    assert target.read_bytes() == before
    assert to_csv(report, target, overwrite=True) == target
    assert write_table(to_table(report), target, overwrite=True) == target
