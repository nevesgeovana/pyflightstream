"""P0400-RESULTS: the results tables of 0.40.0 (lane results)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.results import (
    parse_run_loads,
    sweep_table,
)
from pyflightstream.results import tables as tables_module
from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
from tests.tier1_offline.test_p0400_results_loads_support import STEADY, TRUNCATED, _one_run
from tests.tier1_offline.test_tables import read_fixture

pytestmark = pytest.mark.requirement("P0400-RESULTS-TABLES")


def test_p0400_results_a_truncated_loads_spreadsheet_is_refused_not_skipped(tmp_path):
    """P0400-RESULTS (PFS-2105.025, PFS-2081.24): the truncation is named, not 'no loads'."""
    workspace, record = _one_run(
        tmp_path,
        ("AL+020", "loads.txt", TRUNCATED),
        ("AL+020", "probes.txt", read_fixture("probe_points_26.120.txt")),
    )
    with pytest.raises(IncompleteOutputError):
        parse_run_loads(workspace, record)
    with pytest.warns(PyflightstreamWarning, match="loads of run 'camp/sim_9001/AL\\+020' could"):
        table = sweep_table(workspace, require_loads=False)
    assert table["run_id"].tolist() == ["camp/sim_9001/AL+020"]
    assert "CL" not in table.columns, "no coefficient was read off the truncated file"


def test_p0400_results_a_file_that_is_no_loads_spreadsheet_is_still_skipped(tmp_path):
    """P0400-RESULTS (PFS-2105.025): control, a probe export beside the loads is no refusal."""
    workspace, record = _one_run(
        tmp_path,
        ("AL+020", "loads.txt", STEADY),
        ("AL+020", "probes.txt", read_fixture("probe_points_26.120.txt")),
    )
    assert parse_run_loads(workspace, record).total["CL"] == pytest.approx(0.4308)


def test_p0400_results_a_malformed_loads_spreadsheet_is_refused_not_skipped(tmp_path):
    """P0400-RESULTS-TABLES (PFS-2105.025): duplicated totals are loads errors."""
    lines = STEADY.splitlines(keepends=True)
    total = next(line for line in lines if line.strip().startswith("Total,"))
    duplicated = STEADY.replace(total, total + total)
    workspace, record = _one_run(tmp_path, ("AL+020", "loads.txt", duplicated))
    with pytest.raises(MalformedOutputError, match="Total"):
        parse_run_loads(workspace, record)


def test_p0400_results_auto_detection_reads_only_the_loads_spreadsheet_whole(tmp_path, monkeypatch):
    """P0400-RESULTS (PFS-2085.007): outputs that fail the head check are never read whole."""
    workspace, record = _one_run(
        tmp_path,
        ("AL+020", "loads.txt", STEADY),
        ("AL+020", "surface.vtk", "# vtk DataFile Version 3.0\n" + "0 0 0\n" * 5000),
        ("AL+020", "probes.txt", read_fixture("probe_points_26.120.txt")),
    )
    read: list[str] = []
    original = tables_module._read_output

    def recorded(sim_dir, name, record):
        read.append(Path(name).name)
        return original(sim_dir, name, record)

    monkeypatch.setattr(tables_module, "_read_output", recorded)
    parse_run_loads(workspace, record)
    assert read == ["loads.txt"]
