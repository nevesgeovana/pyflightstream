"""Tier 1: a run that imports trailing edges checks the solver's own count.

G02 (RPT-061, RPT-065). The wake-edge import marks an edge whose mid-point
lies within its tolerance of a point in the file, and for a point that
matches no edge it marks nothing and says nothing: no error, no count.
Initialisation does not add the edges detection would find, so a run whose
file matched nothing reaches the solve with no trailing edge. The one
statement the solver makes is ``N trailing edges imported for boundary
<name>`` in its log, so a run that imported a file compares that N with the
number of points it wrote, and records FAILED_SCRIPT when they differ.

The node file is parked on the script by the marking helper and written by
the run before the solver starts; its digest joins the record's inputs.

The runs below go through ``run_campaign`` with a stand-in for the solver,
a Python script that reads the node file the script names, writes the
declared export and writes the log a case asks for, so the whole path from
recipe to record is the shipped one.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import Assessment, CampaignErrors, LocalExecutor, run_campaign
from pyflightstream.run.collect import collect_once
from pyflightstream.script import helpers
from pyflightstream.workspace import CampaignWorkspace, RunStatus

#: The sixteen trailing-edge mid-points of the tier-3 straight wing, which is
#: the case the solver's line was read on: 16 imported for boundary Wing.
MIDPOINTS = [(1.0, -3.75 + 0.5 * k, 0.0) for k in range(16)]

#: What 26.124 wrote around the import line in the log of that run: lines end in
#: CR LF and a NUL sits alone on a line between them.
LOG_AROUND = (
    "Opening the simulation\r\n\x00\r\n{line}\r\n\x00\r\n\r\n\x00\r\nSolver initialized\r\n"
)

#: The stand-in for the solver. It finds the import line in the script it is
#: handed, reads the node file on the line after it and writes what it read
#: beside the script (proof that the file existed when the solver started),
#: writes every export the script asks for, and writes the log the case asks
#: for, when it asks for one.
STUB = """
import pathlib, sys
script = pathlib.Path(sys.argv[1])
lines = script.read_text(encoding="utf-8").splitlines()
here = pathlib.Path.cwd()
for index, line in enumerate(lines):
    if line.startswith("IMPORT_WAKE_EDGES_FROM_FILE"):
        node = pathlib.Path(lines[index + 1])
        (here / "node_file_seen.txt").write_text(node.read_text(encoding="utf-8"), encoding="utf-8")
    if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
        pathlib.Path(lines[index + 1]).write_text("LOADS", encoding="utf-8")
log = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
if log != "NO LOG":
    (here / "FlightStreamLog.txt").write_text(log, encoding="utf-8", newline="")
"""


class StubSolver(LocalExecutor):
    """Runs the stand-in above in place of the solver, with the log it is to write."""

    def __init__(self, stub: Path, log: Path):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.stub = stub
        self.log = log

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, str(self.stub), str(script_path), str(self.log)]


def wake_recipe(case, script):
    """A steady point that marks its trailing edge from a file of 16 mid-points."""
    script.emit("OPEN", case.geometry)
    helpers.mark_wake_edges(
        script,
        edge_type="STANDARD",
        tolerance=0.0001,
        units="METER",
        node_file=str(Path(case.geometry).with_suffix(".wake_nodes.txt")),
        midpoints=MIDPOINTS,
    )
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        aoa=case.point["alpha"],
        velocity=case.velocity,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


def converged(case, execution, sim_dir):
    return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)


def _run(tmp_path, log: str):
    """Run one point of the wake recipe on 26.124 with the log the solver is to write."""
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[2.0]),
        recipe="wake",
        outputs=["loads_{point}.txt"],
    )
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    log_file = tmp_path / "log_to_write.txt"
    log_file.write_text(log, encoding="utf-8", newline="")
    workspace = CampaignWorkspace(tmp_path / "camp")
    try:
        run_campaign(
            campaign,
            StubSolver(stub, log_file),
            workspace,
            assess=converged,
            recipes={"wake": wake_recipe},
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return record, tmp_path / "camp" / "sims" / "sim_9001"


def test_a_run_whose_log_counts_fewer_edges_than_the_points_written_is_refused(tmp_path):
    """16 points written and 15 edges imported: one point matched no edge and the
    solver said nothing about it, so the run is FAILED_SCRIPT, naming both
    numbers, whatever the assessor made of the loads."""
    record, _ = _run(
        tmp_path, LOG_AROUND.format(line="15 trailing edges imported for boundary Wing")
    )
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert "16" in record.error and "15" in record.error, record.error
    assert "Wing" in record.error


def test_a_run_whose_log_counts_every_point_keeps_the_assessor_s_status(tmp_path):
    """The control: the same run with the solver logging all 16 is CONVERGED."""
    record, _ = _run(
        tmp_path, LOG_AROUND.format(line="16 trailing edges imported for boundary Wing")
    )
    assert record.status is RunStatus.CONVERGED, record.error
    assert record.error is None


def test_a_log_with_no_import_line_is_a_file_that_marked_nothing(tmp_path):
    """No import line is what a file that matched no edge produces, so it is 0
    imported against 16 written; a detection line is not an import and does not
    count."""
    record, _ = _run(tmp_path, LOG_AROUND.format(line="16 trailing edges marked on surface Wing"))
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert "16" in record.error and " 0 " in record.error, record.error


def test_a_run_with_no_log_cannot_say_whether_its_file_marked_anything(tmp_path):
    """Without a log the one statement the solver makes is unread, so the run is
    FAILED_INCOMPLETE_OUTPUT rather than a converged record of an unmarked wake."""
    record, _ = _run(tmp_path, "NO LOG")
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, (record.status, record.error)
    assert "log" in record.error


def test_the_node_file_is_written_before_the_solver_and_hashed(tmp_path):
    """The node file the helper parked is on disk when the solver starts, with the
    measured layout, and its digest is among the record's inputs."""
    record, sim = _run(
        tmp_path, LOG_AROUND.format(line="16 trailing edges imported for boundary Wing")
    )
    seen = (sim / "node_file_seen.txt").read_text(encoding="utf-8").splitlines()
    assert seen[:3] == ["16", "0,0,0", "1.0,-3.75,0.0"], seen
    assert len(seen) == 18
    node_file = next(sim.rglob("wing.wake_nodes.txt"))
    digest = hashlib.sha256(node_file.read_bytes()).hexdigest()
    assert record.inputs_sha256["wing.wake_nodes.txt"] == digest


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        (LOG_AROUND.format(line="16 trailing edges imported for boundary Wing"), {"Wing": 16}),
        (
            "8 trailing edges imported for boundary Wing\n"
            "8 trailing edges imported for boundary Wing\n"
            "1 trailing edge imported for boundary Tail Plane\n",
            {"Wing": 16, "Tail Plane": 1},
        ),
        ("16 trailing edges marked on surface Wing\n", {}),
        ("", {}),
    ],
)
def test_imported_trailing_edges_reads_the_import_line_and_not_the_detection_line(log, expected):
    """The parser sums the import lines per boundary, through the NUL bytes and
    CR LF endings the solver writes, and does not count detection's line."""
    from pyflightstream.results import imported_trailing_edges

    assert imported_trailing_edges(log) == expected


@pytest.mark.parametrize(("logged", "expected_status"), [(15, "FAILED_SCRIPT"), (16, "CONVERGED")])
def test_a_collected_job_is_held_to_the_count_its_submission_recorded(
    tmp_path, monkeypatch, logged, expected_status
):
    """A submitted job is judged when it is collected, not when it is sent: its
    submission records the points its script imported, and the log the assessor
    read among the collected outputs is held to that number, as the local path
    holds a point the moment its solver returns."""
    import json

    from pyflightstream.run import collect as collect_module
    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

    workspace, sim = _submitted_workspace(tmp_path)
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    raw[0]["submission"]["wake_edge_points"] = 16
    workspace.manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    line = f"{logged} trailing edges imported for boundary Wing"
    (sim / "run_log.txt").write_text(LOG_AROUND.format(line=line), encoding="utf-8", newline="")
    monkeypatch.setattr(
        collect_module,
        "assessment_of_collected",
        lambda record, sim_dir: Assessment(
            status=RunStatus.CONVERGED, iterations=120, log_file_used="run_log.txt"
        ),
    )
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    (outcome,) = report.collected + report.failed
    assert outcome.record is not None
    assert str(outcome.record.status) == expected_status, outcome.record.error
    if expected_status == "FAILED_SCRIPT":
        assert "16" in outcome.record.error and "15" in outcome.record.error


def _residual_log(line: str) -> str:
    """A recorded 26.120 solver log with ``line`` printed before its residual table."""
    fixture = Path(__file__).parent / "fixtures" / "log_residuals_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    anchor = "script.txt\n"
    assert anchor in text, "the fixture no longer carries the line the import is put after"
    return text.replace(anchor, f"{anchor}\n{line}\n", 1)


@pytest.mark.parametrize(
    ("logged", "expected_status"),
    [(16, "CONVERGED"), (15, "FAILED_SCRIPT"), (None, "FAILED_INCOMPLETE_OUTPUT")],
    ids=["every-point-imported", "one-point-dropped", "no-log-collected"],
)
def test_a_collected_job_judged_by_a_custom_assessor_is_held_to_the_count(
    tmp_path, logged, expected_status
):
    """The assessor a caller passes to collect answers ``(status, error)`` and names
    no file. The count is read from the collected log found the way the package's
    own assessor finds it, among the collected outputs, so a log carrying all 16
    keeps the caller's verdict, one carrying 15 is FAILED_SCRIPT, and a job that
    collected no log is FAILED_INCOMPLETE_OUTPUT."""
    import json

    from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

    declared = ("loads.txt", "run_log.txt") if logged is not None else ("loads.txt",)
    workspace, sim = _submitted_workspace(tmp_path, declared=declared)
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    raw[0]["submission"]["wake_edge_points"] = 16
    workspace.manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    if logged is not None:
        line = f"{logged} trailing edges imported for boundary Wing"
        (sim / "run_log.txt").write_text(_residual_log(line), encoding="utf-8")

    def the_caller_s(record, sim_dir):
        return RunStatus.CONVERGED, None

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=the_caller_s)
    (outcome,) = report.collected + report.failed
    assert outcome.record is not None, outcome.detail
    assert str(outcome.record.status) == expected_status, outcome.record.error
    if expected_status == "CONVERGED":
        assert outcome.record.error is None, outcome.record.error
    elif expected_status == "FAILED_SCRIPT":
        assert "16" in outcome.record.error and "15" in outcome.record.error
    else:
        assert "no solver log was read" in outcome.record.error, outcome.record.error
