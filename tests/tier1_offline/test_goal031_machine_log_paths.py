"""Tier 1: the machine's log decision reaches every script and every collection.

A cluster's HPC profile stating ``[log] export_log = false`` says the solver
build on that machine aborts at ``EXPORT_LOG``, whether a job is submitted or
run on the machine. 0.27.0 carried the decision to the point path; more paths
met the same build without it:

A. the additional post, whose extraction scripts exported the log whether it
   ran with ``--local`` or was planned for a submission, and the build-identity
   pre-flight, whose sentinel script exports a log to read the build from;
B. the collection of a submitted steady job of several points, which waited
   for a log per point while the scheduler writes ONE log for the job, so a
   ``collect --watch`` never finished.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pyflightstream.results import VersionMismatchWarning
from pyflightstream.run import (
    ExecutionResult,
    ExecutorConfigurationError,
    LoadsAssessor,
    LocalExecutor,
    SubmittingExecutor,
    check_solver_identity,
)
from pyflightstream.run.collect import collect_and_post
from pyflightstream.run.matrix import run_matrix
from pyflightstream.versions import resolve
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_goal031_local_run_log import (
    FIXTURES,
    LOG,
    PROFILE,
    STUB,
    _matrix,
)
from tests.tier1_offline.test_matrix_run import RECIPES, CountingStub, workflow_registry

# --- A. the build-identity pre-flight ----------------------------------------


class _Machine(LocalExecutor):
    """A local executor on a machine whose build aborts at EXPORT_LOG, printing ``printed``.

    It keeps every script it is handed, so a test reads what the pre-flight asked.
    """

    def __init__(self, printed: str = "", *, export_log: bool = False):
        super().__init__(fs_exe=sys.executable, hidden=True, forced_local=True)
        self.export_log = export_log
        self.printed = printed
        self.scripts: list[str] = []

    def run_script(self, script_path, working_dir, timeout_s=None):
        self.scripts.append(Path(script_path).read_text(encoding="utf-8"))
        return ExecutionResult(
            return_code=0,
            wall_time_s=0.01,
            timed_out=False,
            log_text=None,
            stdout=self.printed,
            stderr="",
        )


def test_the_identity_pre_flight_exports_no_log_where_the_machine_cannot(tmp_path):
    """No EXPORT_LOG in the sentinel script, and a warning naming the profile, never a failure."""
    machine = _Machine()
    with pytest.warns(VersionMismatchWarning) as warned:
        check_solver_identity(machine, resolve("26.120"), tmp_path)
    (script,) = machine.scripts
    assert "EXPORT_LOG" not in script.splitlines(), script
    said = " ".join(str(item.message) for item in warned)
    assert "export_log = false" in said and "HPC profile" in said, said


def test_the_identity_pre_flight_reads_the_build_the_solver_printed(tmp_path):
    """Without the log, a build the solver printed still identifies the installation."""
    machine = _Machine("FlightStream version 26.1, build #7012026\n")
    with pytest.raises(ExecutorConfigurationError, match="7012026"):
        check_solver_identity(machine, resolve("26.121"), tmp_path)
    assert "EXPORT_LOG" not in machine.scripts[0].splitlines()


def test_the_identity_pre_flight_still_exports_the_log_where_the_machine_can(tmp_path):
    """The control: a machine that writes its log is asked exactly as before."""
    machine = _Machine(export_log=True)
    with pytest.warns(VersionMismatchWarning):
        check_solver_identity(machine, resolve("26.120"), tmp_path)
    assert "EXPORT_LOG" in machine.scripts[0].splitlines()


# --- A. the additional post ---------------------------------------------------


def _recorded_campaign_on_the_cluster(tmp_path, monkeypatch):
    """A recorded campaign whose workspace now carries the profile, on a cluster."""
    from pyflightstream.run import matrix as matrix_module
    from tests.tier1_offline.test_additional_post import a_recorded_campaign

    workspace, matrix = a_recorded_campaign(tmp_path)
    directory = workspace.inputs_dir / "hpc"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "h001.toml").write_text(PROFILE, encoding="utf-8")
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: True)
    return workspace, matrix


def _aborting_extractor(tmp_path, printed):
    """The stand-in extraction solver: every export the script names, stopping at EXPORT_LOG."""
    from tests.tier1_offline.test_additional_post import LOADS, SLOADS

    table = tmp_path / "aborting_exports.json"
    table.write_text(
        json.dumps(
            {"EXPORT_SOLVER_ANALYSIS_SPREADSHEET": LOADS, "EXPORT_SURFACE_SECTIONAL_LOADS": SLOADS}
        ),
        encoding="utf-8",
    )
    code = (
        "import json, pathlib, sys\n"
        "from pyflightstream.cases import EXPORT_KINDS\n"
        f"table = json.loads(pathlib.Path({str(table)!r}).read_text(encoding='utf-8'))\n"
        "verbs = {kind[2] for kind in EXPORT_KINDS}\n"
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines()\n"
        "for i, line in enumerate(lines):\n"
        "    verb = line.split(' ')[0]\n"
        "    if verb == 'EXPORT_LOG':\n"
        "        sys.exit(0)\n"
        "    if verb in verbs and i + 1 < len(lines):\n"
        "        pathlib.Path(lines[i + 1]).write_text(table.get(verb, 'DATA'))\n"
        f"sys.stdout.write({printed!r})\n"
    )
    return CountingStub(code)


def _extract_locally(tmp_path, monkeypatch, *, printed=""):
    from pyflightstream.run import matrix as matrix_module
    from tests.tier1_offline.test_additional_post import BUILD

    workspace, matrix = _recorded_campaign_on_the_cluster(tmp_path, monkeypatch)
    built: list[dict] = []

    def local_executor(fs_exe, hidden=True, *, forced_local=False, **machine):
        built.append({"forced_local": forced_local, **machine})
        stub = _aborting_extractor(tmp_path, printed)
        stub.forced_local = forced_local
        stub.export_log = machine.get("export_log", True)
        return stub

    monkeypatch.setattr(matrix_module, "LocalExecutor", local_executor)
    plans, records = matrix_module.run_additional_post(
        matrix, workspace, default_fs_version=BUILD, local=True
    )
    scripts = sorted((workspace.root / "sims").rglob("scripts/additional/p002/*.txt"))
    return workspace, plans, records, [p.read_text(encoding="utf-8") for p in scripts]


def test_an_additional_post_under_local_exports_no_log_on_such_a_machine(tmp_path, monkeypatch):
    """The extraction scripts leave EXPORT_LOG out, and every extraction completes.

    The solver printed nothing, so the declared log is not required, and the
    record's note says why it has none.
    """
    workspace, plans, records, scripts = _extract_locally(tmp_path, monkeypatch)
    assert [plan.status for plan in plans] == ["READY"] * 2, [plan.message for plan in plans]
    assert scripts and all("EXPORT_LOG" not in text.splitlines() for text in scripts)
    assert [record.status for record in records] == ["EXTRACTED"] * 2, [
        record.error for record in records
    ]
    for record in records:
        assert not any(name.endswith("_log.txt") for name in record.outputs), record.outputs
        assert record.note and "export_log = false" in record.note, record.note


def test_an_additional_post_writes_the_printed_output_as_its_log(tmp_path, monkeypatch):
    """What the solver printed becomes the declared log, listed and hashed."""
    workspace, _, records, _ = _extract_locally(tmp_path, monkeypatch, printed=LOG)
    for record in records:
        assert record.status == "EXTRACTED", record.error
        (log,) = [name for name in record.outputs if name.endswith("_log.txt")]
        written = workspace.sim_dir(record.sim_id) / log
        assert written.read_text(encoding="utf-8") == LOG
        assert log in record.outputs_sha256
        assert record.note and "captured" in record.note, record.note


def test_an_additional_post_planned_for_a_submission_exports_no_log(tmp_path, monkeypatch):
    """Without --local the plan is still built for this machine's build."""
    from pyflightstream.run.matrix import plan_additional_post
    from tests.tier1_offline.test_additional_post import BUILD

    workspace, matrix = _recorded_campaign_on_the_cluster(tmp_path, monkeypatch)
    plans = plan_additional_post(matrix, workspace, default_fs_version=BUILD)
    ready = [plan for plan in plans if plan.status == "READY"]
    assert ready, [plan.message for plan in plans]
    for plan in ready:
        assert "EXPORT_LOG" not in (plan.script_text or "").splitlines(), plan.script_text


def test_an_additional_post_off_the_cluster_still_exports_its_log(tmp_path, monkeypatch):
    """The control: the same workspace on a machine that is not the cluster."""
    from pyflightstream.run import matrix as matrix_module
    from pyflightstream.run.matrix import plan_additional_post
    from tests.tier1_offline.test_additional_post import BUILD

    workspace, matrix = _recorded_campaign_on_the_cluster(tmp_path, monkeypatch)
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: False)
    plans = plan_additional_post(matrix, workspace, default_fs_version=BUILD)
    ready = [plan for plan in plans if plan.status == "READY"]
    assert ready and all("EXPORT_LOG" in (plan.script_text or "").splitlines() for plan in ready)


# --- B. a submitted steady job of several points -----------------------------


def _no_sleep(_seconds: float) -> None:
    """The clock, injected: the watch's rounds are counted, not waited."""


def _submitted_steady_job(tmp_path, *, native=LOG):
    """Submit a three-point steady row on such a machine, then do what its scheduler does.

    The job runs its one script in the simulation folder, where the stand-in
    writes every point's exports (no point exports a log: the script carries
    no EXPORT_LOG), and the scheduler writes its own log of the job there.
    """
    workspace, matrix = _matrix(tmp_path, sweep="-2.0,0.0,2.0")
    directory = workspace.inputs_dir / "hpc"
    directory.mkdir(parents=True, exist_ok=True)
    profile = directory / "h001.toml"
    profile.write_text(PROFILE, encoding="utf-8")
    run_matrix(
        matrix,
        workspace,
        name="local",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=LoadsAssessor(),
        executor=SubmittingExecutor(
            read_hpc_profile(profile), values={"fs_build": "26.120"}, submit=False
        ),
    )
    (job,) = workspace.read_manifest()
    assert job.status is RunStatus.SUBMITTED, (job.status, job.error)
    sim = workspace.sim_dir("5001")
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(stub),
            str(sim / str(job.script_path)),
            str(FIXTURES / "loads_steady_26.120.txt"),
            "-",
            "abort",
        ],
        cwd=sim,
        check=True,
    )
    (sim / "FTS5001.l4242").write_text(native, encoding="utf-8")
    return workspace, job


def test_collect_files_a_steady_job_whose_scheduler_logs_the_job_once(tmp_path):
    """A bounded watch collects the job: it waits for no log a point cannot have.

    Three rounds is the bound; the scheduler's log and every point's export
    are on disk before the first, so a collector still waiting after the third
    is one that waits forever.
    """
    workspace, job = _submitted_steady_job(tmp_path)
    report = collect_and_post(
        workspace, watch=True, rounds=3, interval=0.0, watch_interval=0.0, sleep=_no_sleep
    )
    assert not report.waiting, [outcome.detail for outcome in report.waiting]
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.lines()
    (collected,) = workspace.read_manifest()
    assert collected.status is RunStatus.CONVERGED, (collected.status, collected.error)
    sim = workspace.sim_dir("5001")
    job_log = f"{Path(str(job.script_path)).stem}_log.txt"
    assert (sim / job_log).read_text(encoding="utf-8") == LOG
    for entry in collected.points_ran:
        assert entry["status"] == "CONVERGED", entry
        assert entry.get("outputs") and not any(
            name.endswith("_log.txt") for name in entry["outputs"]
        ), entry
        note = str(entry.get("residual_note") or "")
        assert "scheduler" in note and job_log in note, note
    for point in collected.as_points():
        assert point.residual_note and job_log in point.residual_note, point.residual_note


def test_a_steady_job_that_imported_trailing_edges_is_held_to_the_job_s_log(tmp_path):
    """The one import line is the job's, so every point is held to the scheduler's log."""
    from tests.tier1_offline.test_run_wake_edge_count import LOG_AROUND

    for line, expected in (
        ("16 trailing edges imported for boundary Wing", "CONVERGED"),
        ("15 trailing edges imported for boundary Wing", "FAILED_SCRIPT"),
    ):
        root = tmp_path / expected
        root.mkdir()
        workspace, _ = _submitted_steady_job(root, native=LOG_AROUND.format(line=line))
        rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
        rows[0]["submission"]["wake_edge_points"] = 16
        workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        collect_and_post(
            workspace, watch=True, rounds=3, interval=0.0, watch_interval=0.0, sleep=_no_sleep
        )
        (collected,) = workspace.read_manifest()
        assert [entry["status"] for entry in collected.points_ran] == [expected] * 3, (
            line,
            collected.error,
        )
