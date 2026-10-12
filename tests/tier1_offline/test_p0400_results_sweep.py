"""P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

from __future__ import annotations

import math

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.results import (
    sweep_table,
)
from tests.tier1_offline.test_tables import build_sweep_workspace

pytestmark = pytest.mark.requirement("P0400-RESULTS-TABLES")


def test_p0400_results_one_unreadable_record_does_not_abort_the_sweep(tmp_path):
    """P0400-RESULTS (PFS-2095.025): a deleted output keeps its row, NaN, warned by run id."""
    workspace = build_sweep_workspace(tmp_path)
    steady = next(r for r in workspace.read_manifest() if r.run_id == "camp/sim_9001/AL+020")
    (workspace.sim_dir(steady.sim_id) / steady.outputs[0]).unlink()
    with pytest.warns(PyflightstreamWarning, match="loads of run 'camp/sim_9001/AL\\+020' could"):
        table = sweep_table(workspace, require_loads=False)
    assert table["run_id"].tolist() == [
        "camp/sim_9001/AL+020",
        "camp/sim_9001/AL+000",
        "camp/sim_9001/AL+040",
    ]
    assert math.isnan(table["CL"].iloc[0]) and not math.isnan(table["CL"].iloc[1])
    with pytest.raises(FileNotFoundError):
        sweep_table(workspace, require_loads=True)
