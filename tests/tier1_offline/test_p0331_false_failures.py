"""Tier 1: the two false FAILED_INCOMPLETE_OUTPUT verdicts that 0.33.1 removes.

Both were measured offline on the recorded outputs of complete steady points
(the replay of 2026-10-01), and both exist in 0.32.0 and 0.33.0 alike.

The first, here: a steady row's points run as ONE job in one solver session,
and each point's ``EXPORT_LOG`` writes the session's log so far, so the log of
point k holds k solves with the iteration counter starting again at 1 for each.
The package read as the log only a file holding ONE solve, so from point 2 on
no log was read, the trailing-edge count of a row importing its edges from a
file could not be checked, and a converged point was recorded
FAILED_INCOMPLETE_OUTPUT with its log on disk. The log the stand-in writes for
point 2 is the recorded one of such a job on 26.124 (the licence lines dropped
and the script path neutral): 8 trailing edges imported, a solve of 28
iterations, then one of 25.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-55 (amended 0.33.1).

from __future__ import annotations

import sys
from pathlib import Path

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import Assessment, CampaignErrors, LocalExecutor
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_raw_mesh_conditions import (
    FILE_ROUTE,
    MIDPOINTS,
    RECIPES,
    ROW,
    WITH_LOG,
    _library,
    _named_node_file,
    _points_in,
    _points_text,
    write_matrix,
)

FIXTURES = Path(__file__).parent / "fixtures"

#: The recorded log of point 2 of a steady job: two solves, one import line.
TWO_SOLVES = FIXTURES / "log_steady_job_two_solves_26.124.txt"

#: The stand-in for the solver of a steady job. It writes the loads table the
#: script asks for and, at the k-th EXPORT_LOG, the k-th log it is handed: the
#: session's log as it stood after k solves, which is what the solver writes.
JOB_STUB = """
import pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
logs = [pathlib.Path(name).read_text(encoding="utf-8") for name in sys.argv[2:]]
exported = 0
for index, line in enumerate(lines):
    if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
        pathlib.Path(lines[index + 1]).write_text("LOADS", encoding="utf-8")
    if line == "EXPORT_LOG":
        text = logs[min(exported, len(logs) - 1)]
        pathlib.Path(lines[index + 1]).write_text(text, encoding="utf-8")
        exported += 1
"""


class _JobSolver(LocalExecutor):
    """Runs the stand-in above with the logs it writes, in order."""

    def __init__(self, stub: Path, logs: list[Path]):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.stub, self.logs = stub, logs

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, str(self.stub), str(script_path), *map(str, self.logs)]


def _names_no_log(case, execution, sim_dir):
    """A converged verdict that does not say which file it read as the log."""
    return Assessment(status=RunStatus.CONVERGED, iterations=25, residual=None)


def _steady_job_of_two_points(tmp_path):
    """Run a two-point steady job importing 8 trailing edges; return its workspace and record."""
    workspace = _library(tmp_path, FILE_ROUTE, points=_points_text(MIDPOINTS[:8]))
    text = TWO_SOLVES.read_text(encoding="utf-8")
    first = text.index("Angle of attack (Deg)")
    logs = [tmp_path / "log_after_one_solve.txt", tmp_path / "log_after_two_solves.txt"]
    logs[0].write_text(text[: text.index("Angle of attack (Deg)", first + 1)], encoding="utf-8")
    logs[1].write_text(text, encoding="utf-8")
    stub = tmp_path / "job_stub.py"
    stub.write_text(JOB_STUB, encoding="utf-8")
    row = ROW.format(build="26.124", outputs=WITH_LOG, geometry="wing.stl", tail="")
    matrix = write_matrix(tmp_path / "job.fs", [row.replace("| AL | 0.0 |", "| AL | 0.0,2.0 |")])
    try:
        run_matrix(
            matrix,
            workspace,
            name="matrix",
            default_fs_version="26.124",
            recipes=RECIPES,
            assess=_names_no_log,
            executor=_JobSolver(stub, logs),
            recipe_registry=workflow_registry(),
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return workspace, record


def test_point_2_of_a_steady_job_reads_its_cumulative_log_and_converges(tmp_path):
    # P0331-SWEEP-LOG (FR-55, amended 0.33.1): point 2's collected _log.txt
    # holds two solves, so the one-solve content rule finds no log; the point's
    # single collected _log.txt is then its log, its "8 trailing edges imported"
    # line meets the wake_edge_points the script wrote, and the point keeps its
    # CONVERGED verdict.
    text = TWO_SOLVES.read_text(encoding="utf-8")
    assert text.count("8 trailing edges imported for boundary Wing") == 1, "the fixture moved"
    assert "\n28 " in text and "\n1 " in text, "the fixture lost its counter reset"
    workspace, record = _steady_job_of_two_points(tmp_path)
    wake_edge_points = len(_points_in(_named_node_file(workspace, record)))
    assert wake_edge_points == 8, wake_edge_points
    statuses = [entry["status"] for entry in record.points_ran]
    assert len(statuses) == 2, record.points_ran
    assert statuses == [RunStatus.CONVERGED.value, RunStatus.CONVERGED.value], (
        statuses,
        record.error,
    )
    assert "no solver log was read" not in (record.error or ""), record.error
