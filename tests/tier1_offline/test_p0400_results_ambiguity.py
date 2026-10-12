"""P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

from __future__ import annotations

import pytest

from pyflightstream.results import (
    parse_run_loads,
)
from pyflightstream.results.tables import AmbiguousLoadsError
from tests.tier1_offline.test_p0400_results_loads_support import STEADY, _one_run

pytestmark = pytest.mark.requirement("P0400-RESULTS-TABLES")


def test_p0400_results_loads_file_naming_two_outputs_is_ambiguous(tmp_path):
    """P0400-RESULTS (PFS-2105.045): two outputs share the base name; both are named."""
    workspace, record = _one_run(
        tmp_path, ("AL+020", "loads.txt", STEADY), ("AL+000", "loads.txt", STEADY)
    )
    with pytest.raises(AmbiguousLoadsError) as caught:
        parse_run_loads(workspace, record, loads_file="loads.txt")
    for name in record.outputs:
        assert name in str(caught.value)
