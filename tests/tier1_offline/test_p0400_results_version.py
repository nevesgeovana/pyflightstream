"""P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

from __future__ import annotations

import pytest

from pyflightstream.results import (
    VersionMismatchWarning,
    parse_run_loads,
    sweep_table,
)
from tests.tier1_offline.test_p0400_results_loads_support import STEADY, _one_run

pytestmark = pytest.mark.requirement("P0400-RESULTS-TABLES")


@pytest.mark.parametrize("requested", ["unstated", "99.999", "26.12"])
def test_p0400_results_an_unresolvable_requested_version_still_yields_the_loads(
    tmp_path, requested
):
    """P0400-RESULTS (PFS-2095.024): 'unstated' warns and keeps the coefficients."""
    workspace, record = _one_run(
        tmp_path, ("AL+020", "loads.txt", STEADY), fs_version_requested=requested
    )
    with pytest.warns(VersionMismatchWarning, match="could not be resolved"):
        table = sweep_table(workspace)
    assert table["CL"].tolist() == [pytest.approx(0.4308)]
    with pytest.warns(VersionMismatchWarning, match="could not be resolved"):
        loads = parse_run_loads(workspace, record, loads_file="loads.txt")
    assert loads.fs_version_reported == "26.1"
    assert loads.total["CL"] == pytest.approx(0.4308)
