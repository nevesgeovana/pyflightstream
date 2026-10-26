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

import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import Assessment, CampaignErrors, LocalExecutor, run_campaign
from pyflightstream.script import helpers
from pyflightstream.workspace import CampaignWorkspace, RunStatus

#: The sixteen trailing-edge mid-points of the tier-3 straight wing, which is
#: the case the solver's line was read on: 16 imported for boundary Wing.
MIDPOINTS = [(1.0, -3.75 + 0.5 * k, 0.0) for k in range(16)]


def test_p0440_custom_recipe_is_planned_without_a_run_type():
    """PFS-2124.020: a custom recipe keeps the pre-wave-1 reduction contract."""
    from pyflightstream.cases.workflows import planned_wake

    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        recipe="tests.tier1_offline.test_matrix:a_recipe_named_in_the_cell",
        sweep=SweepAxis(type="alpha", values=[2.0]),
    )
    assert planned_wake(case) is None


def test_p0440_registered_workflow_still_selects_reduction_windows():
    """A WORKFLOW-only case uses the same windows as its registered recipe."""
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import reduction_windows

    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        recipe="unsteady",
        sweep=SweepAxis(type="alpha", values=[2.0]),
        variables={"DELTA_TIME": "0.01", "TIME_ITERATIONS": "10", "LAST_ITERS_AVG": "4"},
    )
    selected = case.model_copy(
        update={"recipe": None, "variables": {**case.variables, "matrix_workflow": "unsteady"}}
    )
    assert reduction_windows(selected) == reduction_windows(case)
    assert reduction_windows(selected)["time_average"]["windows"] == [[7, 10]]
    conflict = selected.model_copy(update={"recipe": "steady"})
    with pytest.raises(CampaignConfigError, match="disagree"):
        reduction_windows(conflict)


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
        node_file=str(
            Path(script.working_dir or ".")
            / Path(case.geometry).with_suffix(".wake_nodes.txt").name
        ),
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


def _residual_log(line: str) -> str:
    """A recorded 26.120 solver log with ``line`` printed before its residual table."""
    fixture = Path(__file__).parent / "fixtures" / "log_residuals_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    anchor = "script.txt\n"
    assert anchor in text, "the fixture no longer carries the line the import is put after"
    return text.replace(anchor, f"{anchor}\n{line}\n", 1)
