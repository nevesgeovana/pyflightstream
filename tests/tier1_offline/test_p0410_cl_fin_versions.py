"""P0410-CL-FIN: development versions retain release deadline ordering."""

import pytest

from tests.tier1_offline.test_regression_workspace_reachability import _reach_guard___version


@pytest.mark.parametrize("suffix", ["dev0", "dev12"])
def test_p0410_cl_fin_reach_deadlines_accept_development_versions(suffix):
    assert _reach_guard___version(f"0.41.0.{suffix}") < _reach_guard___version("0.41.0")
    assert _reach_guard___version(f"0.41.0.{suffix}") < _reach_guard___version("0.42.0")
