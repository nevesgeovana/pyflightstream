"""Tier 1: a local run writes where a submitted one does, and its log is the machine's.

A workspace on a cluster can carry an HPC profile stating ``[log] export_log =
false`` beside a ``native_log``, because the solver build on that machine
aborts at ``EXPORT_LOG``. Until 0.27.0, a point run there with
``pyfs-matrix run --local`` met two defects (measured 2026-09-24):

* the profile's decision reached a SUBMITTED job only, so every local script
  still carried ``EXPORT_LOG``, the solver stopped there after every other
  export, and nothing wrote the declared log;
* one missing declared output made collection keep NOTHING: every point was
  recorded ``FAILED_INCOMPLETE_OUTPUT`` with ``outputs = []``, while its other
  exports lay uncollected in the simulation folder, and the post skipped each
  as naming no output file.

What is held here, through ``run_matrix``, the entry the command line calls,
with a stand-in for the solver that writes whatever export the script asks
for and stops, writing nothing, where the script says ``EXPORT_LOG``:

1. ``--local`` on such a machine applies the profile's decision, and the
   declared log is written from what the solver printed; when it printed
   nothing, the log is not a missing output, the record says why, and the
   point is judged from its loads export.
2. A missing declared output never strands the rest: every output that exists
   is filed in the point's folder, listed and hashed, and the error names only
   the missing ones.
3. A local point runs in its own ``datapoints/DP-<point>/``, as a submitted
   one does, so its exports are written where they are filed, even by a
   solver that dies before its log. A steady row of several points is ONE
   job over one script and keeps the simulation folder, as its submitted
   form does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream.run import CampaignErrors, LoadsAssessor, LocalExecutor
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace, RunStatus, WorkspaceError
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    make_library,
    matrix_mod,
    stage_geometry,
    workflow_registry,
)

FIXTURES = Path(__file__).parent / "fixtures"

#: A profile of such a machine: a scheduler that writes its own log, and a
#: build that aborts at EXPORT_LOG.
PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
ApplicationId = "{application_id}"
job_name      = "FTS{sim}"
workdir       = "{work_dir}"

[submit]
command = ["esub", "{descriptor_path}"]

[log]
export_log = false
native_log = "FTS{sim}.l*"
"""

#: A solver log of the loads fixture's own run: the residual history ends at
#: the iteration the export was written at (312), so the assessor reads it.
LOG = (
    (FIXTURES / "log_residuals_26.120.txt")
    .read_text(encoding="utf-8")
    .replace("\n1575 ", "\n312 ")
    .replace("\n1574 ", "\n311 ")
)

#: The stand-in for the solver. It writes every export the script names,
#: RELATIVE TO ITS WORKING DIRECTORY as the solver does, with the loads
#: export printing the incidence the script last set; at EXPORT_LOG it does
#: what argv[4] says: ``abort`` stops there with nothing written (the build of
#: such a machine), ``die`` stops there with a failing return code, ``skip``
#: goes on without writing it, ``write`` writes
#: argv[3]'s file there. It prints argv[3]'s file on standard output unless that
#: is ``-`` or the log took it.
STUB = r"""
import pathlib, re, sys
from pyflightstream.cases import EXPORT_KINDS
script, loads, printed, at_log = sys.argv[1:5]
verbs = {kind[2] for kind in EXPORT_KINDS}
text = pathlib.Path(loads).read_text(encoding="utf-8")
lines = pathlib.Path(script).read_text(encoding="utf-8").splitlines()
alpha = 2.0
for index, line in enumerate(lines):
    verb = line.split(" ")[0]
    if verb == "SOLVER_SET_AOA":
        alpha = float(line.split()[1])
    if verb == "EXPORT_LOG":
        if at_log == "abort":
            sys.exit(0)
        if at_log == "die":
            sys.exit(3)
        if at_log == "write" and printed != "-":
            pathlib.Path(lines[index + 1]).write_text(
                pathlib.Path(printed).read_text(encoding="utf-8"), encoding="utf-8"
            )
            printed = "-"
        continue
    if verb in verbs and index + 1 < len(lines):
        body = "DATA"
        if verb == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
            body = re.sub(
                r"(Angle of attack \(Deg\)\s+)\S+", lambda m: m.group(1) + f"{alpha:.3f}", text
            )
        pathlib.Path(lines[index + 1]).write_text(body, encoding="utf-8")
if printed != "-":
    sys.stdout.write(pathlib.Path(printed).read_text(encoding="utf-8"))
"""


class Solver(LocalExecutor):
    """Runs the stand-in in place of the solver, as the executor the run built.

    ``export_log`` is set AFTER the base class, so the stand-in carries the
    machine's decision whether the base class knows the keyword or not.
    """

    def __init__(
        self, tmp_path, *, prints=None, at_log="abort", forced_local=False, export_log=True
    ):
        super().__init__(fs_exe=sys.executable, hidden=True, forced_local=forced_local)
        self.export_log = export_log
        self.stub = tmp_path / "stub_solver.py"
        self.stub.write_text(STUB, encoding="utf-8")
        self.printed = "-"
        if prints is not None:
            self.printed = str(tmp_path / "printed.txt")
            Path(self.printed).write_text(prints, encoding="utf-8")
        self.at_log = at_log

    def _argv(self, script_path: Path) -> list[str]:
        return [
            sys.executable,
            str(self.stub),
            str(script_path),
            str(FIXTURES / "loads_steady_26.120.txt"),
            self.printed,
            self.at_log,
        ]


def _matrix(tmp_path, sweep="2.0"):
    """A workspace and a matrix holding ONE steady row at the loads fixture's state."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    header = " | ".join(matrix_mod._COLUMNS)
    row = " | ".join(
        {
            "POL": "5001",
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Wing",
            "DESCRIPTION": "LOCAL",
            "FLIGHT_CONDITION": "TASmps:30, ALTFT:0, ALPHA:sweep, BETA:0.0",
            "SWEEP_VALUES": sweep,
            "GEOMETRY": "wing_clean.fsm",
            "REF": "r003",
            "SET": "s002",
            "PPROC": "p001",
            "SYMMETRY": "NONE",
            "FS_BUILD": "26.120",
            "WORKFLOW": "steady",
            "VAR_NAMES_VALUES": "",
        }.get(name, "-")
        for name in matrix_mod._COLUMNS
    )
    path = tmp_path / "local.fs"
    path.write_text(header + "\n" + "-" * 40 + "\n" + row + "\n", encoding="utf-8")
    return workspace, path


def _run(tmp_path, monkeypatch, *, cluster, profile, prints=None, at_log="abort", sweep="2.0"):
    """Run the matrix with ``local=True`` through the executor the run builds.

    ``profile`` is the text of the workspace's one HPC profile, or None for none.
    """
    from pyflightstream.run import matrix as matrix_module

    workspace, matrix = _matrix(tmp_path, sweep=sweep)
    if profile:
        directory = workspace.inputs_dir / "hpc"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "h001.toml").write_text(profile, encoding="utf-8")
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: cluster)
    built: list[dict] = []

    def local_executor(fs_exe, hidden=True, *, forced_local=False, **machine):
        built.append({"forced_local": forced_local, **machine})
        return Solver(
            tmp_path,
            prints=prints,
            at_log=at_log,
            forced_local=forced_local,
            export_log=machine.get("export_log", True),
        )

    monkeypatch.setattr(matrix_module, "LocalExecutor", local_executor)
    try:
        run_matrix(
            matrix,
            workspace,
            name="local",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=LoadsAssessor(),
            local=True,
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    return workspace, workspace.read_manifest(), built


def _scripts(workspace) -> list[str]:
    sim = workspace.sim_dir("5001")
    return [path.read_text(encoding="utf-8") for path in sorted((sim / "scripts").glob("*.txt"))]


def _named_missing(error: str | None) -> list[str]:
    """The paths a collection error names as not produced, and nothing else it says."""
    named = (error or "").split("were not produced: ", 1)[-1].split(". A missing", 1)[0]
    return [part.strip() for part in named.split(", ") if part.strip()]


def _exports_in(folder: Path, point: str) -> list[str]:
    """The point's own exports in a folder: the files named after the point."""
    return sorted(path.name for path in folder.glob(f"{point}*") if path.is_file())


# --- 1. the machine's log decision under --local -----------------------------


def test_a_local_run_on_a_machine_that_aborts_at_export_log_emits_no_export_log(
    tmp_path, monkeypatch
):
    """The profile's `export_log = false` is the MACHINE's, whether a job is submitted or not."""
    workspace, records, built = _run(
        tmp_path, monkeypatch, cluster=True, profile=PROFILE, prints=LOG
    )
    assert built and all(entry.get("export_log") is False for entry in built), built
    (script,) = _scripts(workspace)
    assert "EXPORT_LOG" not in script.splitlines(), "the script still exports the log"
    (record,) = records
    assert record.executor is not None and record.executor.get("forced_local") is True


def test_the_log_of_such_a_run_is_what_the_solver_printed(tmp_path, monkeypatch):
    """No scheduler writes the log of a local run, so the run writes what it captured.

    The captured text is a real residual history ending at the export's
    iteration, so the point is judged BY it, as a submitted point is judged by
    the log its scheduler wrote.
    """
    workspace, records, _ = _run(tmp_path, monkeypatch, cluster=True, profile=PROFILE, prints=LOG)
    (record,) = records
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    log = next(name for name in record.outputs if name.endswith("_log.txt"))
    written = workspace.sim_dir("5001") / log
    assert written.read_text(encoding="utf-8") == LOG
    assert record.log_file_used == Path(log).name
    assert log in record.outputs_sha256
    assert record.residual_note and "captured" in record.residual_note, record.residual_note


def test_with_nothing_printed_the_log_is_not_a_missing_output(tmp_path, monkeypatch):
    """The machine cannot write a log locally, and the solver printed nothing.

    The point is judged from its loads export, as any point that exports no
    log is, and the record says why it has no log rather than calling the
    point incomplete.
    """
    workspace, records, _ = _run(tmp_path, monkeypatch, cluster=True, profile=PROFILE, prints=None)
    (record,) = records
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert record.error is None
    assert not any(name.endswith("_log.txt") for name in record.outputs), record.outputs
    assert record.log_file_used is None
    note = record.residual_note or ""
    assert "export_log = false" in note and "--local" in note, note
    assert record.outputs and set(record.outputs) == set(record.outputs_sha256)


def test_a_machine_that_writes_its_log_keeps_export_log_under_local(tmp_path, monkeypatch):
    """The control: a profiled cluster whose profile says nothing about the log.

    The script exports the log, the solver writes it, and it is the log the
    point is judged by, with no note: nothing here was the package's doing.
    """
    from tests.tier1_offline.test_matrix_run import HPC_PROFILE

    workspace, records, built = _run(
        tmp_path, monkeypatch, cluster=True, profile=HPC_PROFILE, prints=LOG, at_log="write"
    )
    assert built and all(entry.get("export_log", True) is True for entry in built), built
    (script,) = _scripts(workspace)
    assert "EXPORT_LOG" in script.splitlines()
    (record,) = records
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert record.log_file_used and record.residual_note is None


# --- 2 and 3. a missing output strands nothing; a local point runs in its folder


def test_a_missing_log_strands_no_other_output_of_a_local_point(tmp_path, monkeypatch):
    """A plain local run whose solver stops at EXPORT_LOG, writing no log.

    The log is genuinely missing here (a machine with no profile writes its
    own), so the point is FAILED_INCOMPLETE_OUTPUT; every other export is
    filed in the point's own folder, listed and hashed, and the error names the
    log alone. Nothing of the point is left in the simulation folder.
    """
    workspace, records, _ = _run(tmp_path, monkeypatch, cluster=False, profile=None)
    (record,) = records
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, (record.status, record.error)
    sim = workspace.sim_dir("5001")
    folder = sim / "datapoints" / f"DP-{record.point_name}"
    assert _exports_in(sim, record.point_name) == [], "the solver wrote into the simulation folder"
    written = _exports_in(folder, record.point_name)
    assert written and not any(name.endswith("_log.txt") for name in written), written
    assert sorted(Path(name).name for name in record.outputs) == written
    assert set(record.outputs) == set(record.outputs_sha256)
    assert [Path(name).name for name in _named_missing(record.error)] == [
        f"{record.point_name}_log.txt"
    ], record.error


def test_a_steady_job_of_several_points_files_what_it_wrote_when_a_log_is_missing(
    tmp_path, monkeypatch
):
    """The one-job sweep keeps the simulation folder, as its submitted form does.

    A solver that writes no log leaves every point incomplete, and each point's
    other exports are still filed under its own datapoint folder, listed on its
    entry and hashed on the job.
    """
    workspace, records, _ = _run(
        tmp_path, monkeypatch, cluster=False, profile=None, at_log="skip", sweep="-2.0,0.0,2.0"
    )
    (job,) = records
    assert job.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, (job.status, job.error)
    sim = workspace.sim_dir("5001")
    for entry in job.points_ran:
        assert _exports_in(sim, entry["tag"]) == [], "exports were left in the simulation folder"
        folder = sim / "datapoints" / f"DP-{entry['tag']}"
        written = _exports_in(folder, entry["tag"])
        assert written, (entry["tag"], sorted(p.name for p in sim.rglob("*")))
        assert sorted(Path(name).name for name in entry.get("outputs", [])) == written, entry
    assert job.outputs and set(job.outputs) == set(job.outputs_sha256)


def test_a_steady_job_on_a_machine_that_aborts_at_export_log_is_judged_by_its_loads(
    tmp_path, monkeypatch
):
    """The one-job sweep under --local on such a machine: no log is missing.

    The job's printed output is the whole job's and no single point's, so no
    point's log is written from it; each point is judged from its loads export
    and the job says why none has a log.
    """
    workspace, records, _ = _run(
        tmp_path, monkeypatch, cluster=True, profile=PROFILE, sweep="-2.0,0.0,2.0"
    )
    (job,) = records
    assert job.status is RunStatus.CONVERGED, (job.status, job.error)
    assert all(entry["status"] == "CONVERGED" for entry in job.points_ran), job.points_ran
    note = job.residual_note or ""
    assert "export_log = false" in note, note


# --- 2. the collection primitive ---------------------------------------------


def test_collection_files_every_output_that_exists_and_names_only_the_missing(tmp_path):
    """The workspace's own collection, called as every run calls it."""
    from pyflightstream.workspace import MissingOutputsError, PointName

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    sim = workspace.create_sim("9001")
    (sim / "P9001-AL+000.txt").write_text("LOADS", encoding="utf-8")
    (sim / "P9001-AL+000.dat").write_text("TECPLOT", encoding="utf-8")
    declared = [sim / "P9001-AL+000.txt", sim / "P9001-AL+000.dat", sim / "P9001-AL+000_log.txt"]
    with pytest.raises(WorkspaceError) as caught:
        workspace.collect_outputs("9001", declared, datapoint=PointName("AL+000"))
    error = caught.value
    assert isinstance(error, MissingOutputsError)
    assert error.collected == [
        "datapoints/DP-AL+000/P9001-AL+000.txt",
        "datapoints/DP-AL+000/P9001-AL+000.dat",
    ]
    assert error.missing == [str(sim / "P9001-AL+000_log.txt")]
    assert _named_missing(str(error)) == [str(sim / "P9001-AL+000_log.txt")]
    assert sorted(p.name for p in (sim / "datapoints" / "DP-AL+000").iterdir()) == [
        "P9001-AL+000.dat",
        "P9001-AL+000.txt",
    ]
    assert not (sim / "P9001-AL+000.txt").exists()


# --- 1. a file-route row on such a machine, run locally -----------------------


def _wake_recipe_with_a_log(case, script):
    """A steady point that imports its trailing edges from a file and exports its log.

    The log export honours the case's ``EXPORT_LOG`` as the run types do, which
    is where the machine's decision reaches the script.
    """
    from pyflightstream.cases.workflows import EXPORT_LOG_VARIABLE
    from pyflightstream.script import helpers
    from tests.tier1_offline.test_run_wake_edge_count import MIDPOINTS

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
    if str(case.variables.get(EXPORT_LOG_VARIABLE, "true")).lower() != "false":
        script.emit("EXPORT_LOG", case.outputs[1])
    script.emit("CLOSE_FLIGHTSTREAM")


def _file_route_point(tmp_path, *, prints):
    """Run one file-route point on 26.124 with the executor --local builds on such a machine."""
    from pyflightstream.cases import Campaign, SimCase, SweepAxis
    from pyflightstream.run import run_campaign
    from tests.tier1_offline.test_run_wake_edge_count import converged

    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[2.0]),
        recipe="wake",
        outputs=["loads_{point}.txt", "loads_{point}_log.txt"],
    )
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    solver = Solver(tmp_path, prints=prints, forced_local=True, export_log=False)
    try:
        run_campaign(
            campaign, solver, workspace, assess=converged, recipes={"wake": _wake_recipe_with_a_log}
        )
    except CampaignErrors:
        pass
    (record,) = workspace.read_manifest()
    return record


def test_a_file_route_point_with_nothing_printed_is_recorded_with_the_machine_s_reason(tmp_path):
    """The imported count is read from the log, and this machine wrote none locally.

    Never silently accepted: the point is FAILED_INCOMPLETE_OUTPUT, and the
    error says it is the machine that could not write the log, not the row
    that forgot to declare one.
    """
    record = _file_route_point(tmp_path, prints=None)
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, (record.status, record.error)
    assert "export_log = false" in (record.error or ""), record.error
    assert "16" in (record.error or ""), record.error


def test_a_file_route_point_whose_solver_printed_the_count_is_held_to_it(tmp_path):
    """The captured text becomes the declared log, and the count is read from it by name."""
    from tests.tier1_offline.test_run_wake_edge_count import LOG_AROUND

    printed = LOG_AROUND.format(line="16 trailing edges imported for boundary Wing")
    record = _file_route_point(tmp_path, prints=printed)
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert any(name.endswith("_log.txt") for name in record.outputs), record.outputs


# --- 3. a local point runs in its own datapoint folder ------------------------


def test_a_local_point_writes_in_its_datapoint_folder_even_when_the_solver_dies(
    tmp_path, monkeypatch
):
    """The solver dies before its log: nothing is collected, and nothing is in the sim root.

    The point runs with its datapoint folder as the working directory, as a
    submitted point does, so its relative exports are WRITTEN there; a run
    that fails before collection leaves them where they belong rather than in
    the folder every point of the row shares.
    """
    workspace, records, _ = _run(tmp_path, monkeypatch, cluster=False, profile=None, at_log="die")
    (record,) = records
    assert record.status is RunStatus.FAILED_EXECUTION, (record.status, record.error)
    sim = workspace.sim_dir("5001")
    folder = sim / "datapoints" / f"DP-{record.point_name}"
    assert record.cwd is not None and Path(record.cwd) == folder, record.cwd
    assert _exports_in(sim, record.point_name) == [], "the solver wrote into the simulation folder"
    written = _exports_in(folder, record.point_name)
    assert f"{record.point_name}.txt" in written, written


def test_a_steady_job_of_several_points_runs_in_the_simulation_folder(tmp_path, monkeypatch):
    """ONE script writes every point's files, so the job keeps the folder they share.

    Its submitted form does the same: a steady row is one job, submitted from
    the simulation folder, and collection files each point's outputs.
    """
    workspace, records, _ = _run(
        tmp_path, monkeypatch, cluster=False, profile=None, at_log="skip", sweep="-2.0,0.0,2.0"
    )
    (job,) = records
    assert job.cwd is not None and Path(job.cwd) == workspace.sim_dir("5001"), job.cwd


def test_profiles_that_disagree_about_the_log_are_refused_under_local(tmp_path, monkeypatch):
    """Which of two profiles is this machine is not a guess to make about its log."""
    from pyflightstream.run import matrix as matrix_module
    from pyflightstream.workspace import InputArtifactError
    from tests.tier1_offline.test_matrix_run import HPC_PROFILE

    workspace, matrix = _matrix(tmp_path)
    directory = workspace.inputs_dir / "hpc"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "h001.toml").write_text(PROFILE, encoding="utf-8")
    (directory / "h002.toml").write_text(HPC_PROFILE, encoding="utf-8")
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: True)
    with pytest.raises(InputArtifactError) as caught:
        run_matrix(
            matrix,
            workspace,
            name="local",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=LoadsAssessor(),
            local=True,
        )
    message = str(caught.value)
    assert "h001.toml: export_log = false" in message, message
    assert "h002.toml: export_log = true" in message, message
    assert not workspace.manifest_path.exists(), "a refused run recorded a point"
