"""Tier 1, 0.40.0 lane run-2: ``pyfs-matrix rebuild`` refuses a simulation whole, and alone.

Each workspace is made by the package's own run and collect
(``test_p0370_s1_matrix_home.py``), then ``runs.json`` and the logs are
deleted, and rebuild is run through ``pyfs-matrix`` as she runs it.
"""

from __future__ import annotations

import json

from pyflightstream.run import _rebuild
from pyflightstream.workspace.naming import RunsManifestError
from tests.tier1_offline.test_p0370_s1_matrix_home import (
    grouped_workspace,
    pyfs,
    the_owner_s_deletions,
)


def _sims_recorded(root) -> set[str]:
    return {str(row["sim_id"]) for row in json.loads((root / "runs.json").read_text("utf-8"))}


def test_p0400_rebuild_writes_no_record_of_a_simulation_it_reports_not_recoverable(
    tmp_path, capsys
):
    """P0400-REBUILD-WHOLE (PFS-2103.028): one empty datapoint folder refuses the whole simulation.

    The first point's record had already been appended when the second
    point's empty folder refused the simulation, so the simulation was both
    REBUILT and NOT RECOVERABLE, and the resume took the second point as
    never run.
    """
    workspace = grouped_workspace(tmp_path, mode="alone")
    the_owner_s_deletions(workspace, run_zero=False)
    folders = sorted((workspace.sim_dir("7001") / "datapoints").iterdir())
    assert len(folders) == 2, folders
    for path in folders[-1].iterdir():
        if path.is_file():
            path.unlink()
    code, said = pyfs(["rebuild", "--apply"], workspace.root, capsys)
    assert "7001" in said, said
    assert "7001" not in _sims_recorded(workspace.root), said
    assert "7003" in _sims_recorded(workspace.root), said


def test_p0400_rebuild_refuses_a_simulation_whose_mark_cannot_be_kept_alone(
    tmp_path, capsys, monkeypatch
):
    """P0400-REBUILD-MARK (PFS-2095.053): a person's mark it would lose refuses that simulation.

    keep_verdict's refusal escaped the per-simulation loop and ended the
    whole rebuild.
    """
    workspace = grouped_workspace(tmp_path, mode="alone")
    the_owner_s_deletions(workspace, run_zero=False)
    real = _rebuild.keep_verdict

    def refusing(record, row):
        if str(record.get("sim_id")) == "7001":
            raise RunsManifestError("rebuild would lose marked point(s) V0300RE120AL+020")
        return real(record, row)

    monkeypatch.setattr(_rebuild, "keep_verdict", refusing)
    code, said = pyfs(["rebuild", "--apply"], workspace.root, capsys)
    assert "rebuild would lose marked point(s) V0300RE120AL+020" in said, said
    assert _sims_recorded(workspace.root) == {"7003"}, said
