"""Tier 1: steady and quasi-steady polars join the grouped jobs (FR-403, 0.35.1).

Marker P0351-BATCH-STEADY (FR-403). No solver runs here. The matrix is the
synthetic rotor rig of the matrix tests: its steady row 7002 (two points) and a
copy of it, 7004, at other incidences, or sweeping the Reynolds number (a flow
state, whose points differ before ``SOLVER_SET_AOA``); the mixed matrix adds
the unsteady rotor row 7001. A steady point after an unsteady one in one instance is not measured,
so the plan splits the two kinds into jobs of their own. Inside a steady job a
later point of a polar is restated from ``SOLVER_SET_AOA`` after
``REMOVE_INITIALIZATION``, and the first point of a later polar after
``NEW_SIMULATION``, exactly as an unsteady job restates its points; a later
point that differs before that anchor reopens its geometry after
``NEW_SIMULATION`` too.

The collect test runs the job through a stand-in solver that writes every save
and export target the script names, the loads table at the point's incidence,
and the cumulative log a real instance writes: one solve per point, the
re-initialisation marker before every point but the first. The same points run
alone through the same stand-in are the control.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import WORKFLOW_KEY, build_script, workflow_registry
from pyflightstream.cases.workflows._batch_script import (
    JobPoint,
    JobPolar,
    assemble_job,
    job_point,
    refuse_a_second_initialization,
)
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run._batch_plan import eligibility, plan_grouped_matrix
from pyflightstream.run._batch_split import PolarUnit, split_polars
from pyflightstream.run.collect import collect_once
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_matrix_run import FIXTURES
from tests.tier1_offline.test_p0350_batch_run import (
    BUILD,
    MATRIX,
    StubSolver,
    _neutral,
    _run,
    _submitting,
    _workspace,
    converged,
)
from tests.tier1_offline.test_p0350_batch_script import relative_paths
from tests.tier1_offline.test_restart_continuation import _continuing_case
from tests.tier1_offline.test_workflows import _wb_geometry, _with_pproc, steady_case, unsteady_case

#: The points of the two steady polars, in the order a job runs them.
POINTS = (
    ("7002", "V0300RE120AL+000"),
    ("7002", "V0300RE120AL+020"),
    ("7004", "V0300RE120AL+000"),
    ("7004", "V0300RE120AL+040"),
)
#: The transitions of the job's points after its first: 7004 at other incidences, or
#: sweeping the Reynolds number, whose second point differs in its fluid.
TRANSITIONS = {
    False: ["REMOVE_INITIALIZATION", "NEW_SIMULATION", "REMOVE_INITIALIZATION"],
    True: ["REMOVE_INITIALIZATION", "NEW_SIMULATION", "NEW_SIMULATION"],
}
#: The batch folder of the steady job, relative to the workspace root.
HOME = f"sims/batch/{MATRIX}_b1/"
#: The recorded log of a steady job on 26.124, the source of one synthetic solve.
TWO_SOLVES = FIXTURES / "log_steady_job_two_solves_26.124.txt"
MARKER = "Solution cleared. Initialization removed."


@pytest.mark.parametrize("steady", [True, False], ids=["steady", "unsteady"])
@pytest.mark.parametrize("polar_count", [1, 2])
def test_p0351_restated_sections_are_created_once(tmp_path, steady, polar_count):
    """P0351-BATCH-STEADY (FR-403); P0350-BATCH-SAME-POLAR (FR-352): sections persist.

    Ten one-section distributions are created on each polar's first point.
    Reinitialisation keeps their exports without creating them again; a fresh
    simulation creates its own ten. The real workflow emits every command.
    """
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 1,
                "distributions": [
                    {"families": ["W"], "frame": "MRP", "planes": ["XZ"]} for _ in range(10)
                ],
            }
        }
    )
    case = _with_pproc(steady_case() if steady else unsteady_case(), _wb_geometry(tmp_path), pproc)
    polars = []
    for sim in range(1, polar_count + 1):
        points = []
        for alpha in (0, 2):
            stem = f"P{sim}-AL{alpha}"
            point_case = case.model_copy(
                update={
                    "sim_id": str(sim),
                    "point": {"alpha": float(alpha)},
                    "outputs": [f"{stem}.txt", f"{stem}_cp.txt", f"{stem}_sloads.txt"],
                }
            )
            script = Script(BUILD)
            build_script(point_case, script)
            points.append(
                job_point(
                    point_case,
                    run_id=f"m/sim_{sim}/{stem}",
                    text=script.render(),
                    datapoint_dir=tmp_path / str(sim) / stem,
                    version=BUILD,
                )
            )
        polars.append(JobPolar(str(sim), tuple(points)))
    job = assemble_job(polars, kind="batch", version=BUILD, job_log=None, job_dir=tmp_path)
    lines = job.text.splitlines()
    for index, block in enumerate(job.blocks):
        mine = lines[block.first_line - 1 : block.last_line]
        assert mine.count("NEW_SURFACE_SECTION_DISTRIBUTION") == (10 if index % 2 == 0 else 0)
        assert mine.count("NUM_SECTIONS 1") == (10 if index % 2 == 0 else 0)
        assert any(line.startswith("EXPORT_ALL_SURFACE_SECTIONS") for line in mine)
        assert any(line.startswith("EXPORT_SURFACE_SECTIONAL_LOADS") for line in mine)
        if index:
            assert mine[0] == ("NEW_SIMULATION" if index % 2 == 0 else "REMOVE_INITIALIZATION")


def _placed(row: str) -> str:
    """Give a fixture row the staged geometry, eight processors, a wall clock and the build."""
    for before, after in (
        ("| -        | r003", "| wing_clean.fsm | r003"),
        ("| -     | -        | 26.120", f"| 8     | 10m      | {BUILD}"),
    ):
        assert before in row, (before, row)
        row = row.replace(before, after)
    return row


def _matrix(tmp_path: Path, *, unsteady: bool = False, flow: bool = False) -> Path:
    """Steady 7002 (0 and 2 deg) and 7004 (0 and 4 deg, or REmi 1.2 and 1.5 with ``flow``).

    With ``unsteady``, the rotor row 7001 first.
    """
    header, rule, *rows = (
        (FIXTURES / "workflow_rotor_matrix.fs").read_text(encoding="utf-8").splitlines()
    )
    steady = _placed(next(row for row in rows if row.startswith("7002")))
    assert "| 0.0,2.0        |" in steady and "REmi:1.20, ALPHA:sweep" in steady, steady
    other = steady.replace("7002 ", "7004 ", 1).replace("0.0,2.0 ", "0.0,4.0 ")
    if flow:
        other = other.replace("REmi:1.20, ALPHA:sweep", "REmi:sweep, ALPHA:0.0").replace(
            "0.0,4.0 ", "1.2,1.5 "
        )
    kept = [steady, other]
    if unsteady:
        kept.insert(0, _placed(next(row for row in rows if row.startswith("7001"))))
    matrix = tmp_path / f"{MATRIX}.fs"
    matrix.write_text("\n".join((header, rule, *kept)) + "\n", encoding="utf-8")
    return matrix


def _plan(workspace, matrix, *, batch: int = 1):
    """Plan the matrix as ``plan --batch N`` does and return the plan."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return plan_grouped_matrix(
            matrix,
            workspace,
            mode="batch",
            batch=batch,
            name=MATRIX,
            recipes={},
            recipe_registry=workflow_registry(),
        )


def _points(workspace, matrix) -> list[tuple[str, str]]:
    """The (sim, point name) of every point of the matrix, in matrix order."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_matrix(
            matrix, workspace, name=MATRIX, recipes={}, recipe_registry=workflow_registry()
        )
    return [(entry.sim_id, entry.run_id.rsplit("/", 1)[1]) for entry in plan.points]


def _alone(tmp_path: Path, *, flow: bool = False):
    """Run every point ALONE, one ``--sims S --points P`` run each; return the workspace."""
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path, flow=flow)
    for sim, tag in _points(workspace, matrix):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            run_matrix(
                matrix,
                workspace,
                name=MATRIX,
                recipes={},
                recipe_registry=workflow_registry(),
                assess=converged,
                executor=_submitting(profile, submit=False),
                sims=[sim],
                points=[tag],
            )
    return workspace


def _job_text(workspace, name: str = "BATCH-7002-7004.txt") -> str:
    return (workspace.root / HOME / name).read_text(encoding="utf-8")


def _verbs(text: str) -> list[str]:
    return [line.split()[0] for line in text.splitlines() if line.strip()]


def test_p0351_steady_fr403_two_steady_polars_assemble_one_job(tmp_path):
    """P0351-BATCH-STEADY (FR-403): two steady polars of two points each are ONE job.

    ``plan --batch 1`` leaves no polar out and plans one job of the four points.
    ``run --batch 1`` records each point SUBMITTED in its own datapoint folder, as
    a point run alone is, and writes one job script: one solve per point, the
    second polar opened after ``NEW_SIMULATION``, each later point of a polar
    after ``REMOVE_INITIALIZATION``, no action registered, no action program
    written, every path absolute.
    """
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    plan = _plan(workspace, matrix)
    assert plan.grouping.left_out == (), plan.grouping.left_out
    (job,) = plan.grouping.jobs
    assert job.sims == ("7002", "7004") and len(job.points) == 4, job
    records = _run(workspace, matrix, executor=_submitting(profile, submit=False))
    assert [r.status for r in records] == [RunStatus.SUBMITTED] * 4
    assert [r.run_id.rsplit("/", 1)[1] for r in records] == [tag for _, tag in POINTS]
    assert [r.submission["job"]["order"] for r in records] == [1, 2, 3, 4]
    assert all(r.submission["working_dir"].startswith("datapoints/DP-") for r in records)
    text = _job_text(workspace)
    verbs = _verbs(text)
    assert verbs.count("OPEN") == 2 and verbs.count("NEW_SIMULATION") == 1, verbs
    assert verbs.count("REMOVE_INITIALIZATION") == 2 and verbs.count("START_SOLVER") == 4
    assert verbs.count("CLOSE_FLIGHTSTREAM") == 1 and verbs[-1] == "CLOSE_FLIGHTSTREAM"
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" not in verbs
    assert not relative_paths(text), relative_paths(text)
    assert list((workspace.root / HOME / "actions").iterdir()) == []


def _blocks(text: str) -> list[list[str]]:
    """Cut a job script into its points' blocks, the job's own log export and close dropped."""
    lines = text.splitlines()
    assert lines[-1] == "CLOSE_FLIGHTSTREAM", lines[-3:]
    lines = lines[:-1]
    if lines[-3:-1] and lines[-3] == "EXPORT_LOG" and lines[-2].endswith(".job-log.txt"):
        lines = lines[:-3]
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line in ("REMOVE_INITIALIZATION", "NEW_SIMULATION") and blocks[-1]:
            blocks.append([])
        blocks[-1].append(line)
    return [_trimmed(block) for block in blocks]


def _trimmed(lines: list[str]) -> list[str]:
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


def _grouped_lines(block: list[str], root: Path, sim: str, tag: str) -> list[str]:
    """A job block read as the point's alone script: its folder and its log name undone."""
    folder = f"<root>/{HOME}sim_{sim}/datapoints/DP-{tag}/"
    text = _neutral("\n".join(block), root).replace(folder, "").replace(HOME, "sims/")
    return [re.sub(r"\.cumulative-log\.txt$", "_log.txt", line) for line in text.splitlines()]


def _alone_lines(workspace, sim: str, tag: str) -> list[str]:
    """The point's alone script, its close dropped."""
    path = workspace.root / "sims" / f"sim_{sim}" / "scripts" / f"{tag}.txt"
    lines = _neutral(path.read_text(encoding="utf-8"), workspace.root).splitlines()
    assert lines[-1] == "CLOSE_FLIGHTSTREAM", lines[-3:]
    return _trimmed(lines[:-1])


@pytest.mark.parametrize("flow", [False, True], ids=["incidences", "flow-sweep"])
def test_p0351_steady_fr403_each_point_restates_the_alone_solver_section(tmp_path, flow):
    """P0351-BATCH-STEADY (FR-403): every block of the job is the point's alone script.

    The control is each point run ALONE (``--sims S --points P``, one script each).
    The job's first point is its alone script whole; the first point of the next
    polar is ``NEW_SIMULATION`` then its alone script whole; a later point of a
    polar is ``REMOVE_INITIALIZATION`` then its alone script from its solver
    section on (``SOLVER_SET_AOA``: the settings, the initialisation, the solve,
    the exports), the geometry, frames and fluid before it being its polar's
    first point's, line for line. A later point of the Reynolds sweep differs in
    its fluid, before that anchor, so it reopens its geometry: ``NEW_SIMULATION``
    then its alone script whole, and the plan says so. Each comparison reads the
    point's folder as its alone script names it and its cumulative log as its
    declared log.
    """
    alone = _alone(tmp_path / "alone", flow=flow)
    workspace, profile, _ = _workspace(tmp_path / "grouped")
    matrix = _matrix(tmp_path / "grouped", flow=flow)
    points = _points(workspace, matrix)
    plan = _plan(workspace, matrix)
    assert plan.grouping.left_out == (), plan.grouping.left_out
    reopened = [line for line in plan.grouping.warnings if "reopens its geometry" in line]
    assert [line.split(":")[0] for line in reopened] == (["POL 7004"] if flow else [])
    _run(workspace, matrix, executor=_submitting(profile, submit=False))
    blocks = _blocks(_job_text(workspace))
    assert len(blocks) == len(points) == 4, [block[:1] for block in blocks]
    seen = []
    for block, (sim, tag) in zip(blocks, points, strict=True):
        mine = _grouped_lines(block, workspace.root, sim, tag)
        theirs = _alone_lines(alone, sim, tag)
        solver = theirs.index(next(line for line in theirs if line.startswith("SOLVER_SET_AOA")))
        if mine[0] == "REMOVE_INITIALIZATION":
            assert mine[2:] == theirs[solver:], (sim, tag)
            assert seen[-1][:solver] == theirs[:solver], (sim, tag)
        elif mine[0] == "NEW_SIMULATION":
            assert mine[2:] == theirs, (sim, tag)
        else:
            assert mine == theirs, (sim, tag)
        seen.append(theirs)
    assert [block[0] for block in blocks[1:]] == TRANSITIONS[flow]


def test_p0351_steady_fr403_a_mixed_matrix_splits_by_kind(tmp_path):
    """P0351-BATCH-STEADY (FR-403): a steady and an unsteady polar never share a job.

    With the unsteady rotor row 7001 before the two steady rows, ``plan --batch 1``
    plans two jobs, one per kind, and says why; the unsteady job registers its
    actions and writes its programs, the steady job neither. The split groups by
    kind beside processor count and build, and a job assembled from both kinds is
    refused by name.
    """
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path, unsteady=True)
    plan = _plan(workspace, matrix)
    assert plan.grouping.left_out == (), plan.grouping.left_out
    assert [job.sims for job in plan.grouping.jobs] == [("7001",), ("7002", "7004")]
    assert any(
        "build, kind (steady or unsteady) and unsteady_solver_actions there are, "
        "and a job holds one of each, so one job per group is planned." in line
        for line in plan.grouping.warnings
    )
    _run(workspace, matrix, executor=_submitting(profile, submit=False))
    rotor = workspace.root / "sims" / "batch" / f"{MATRIX}_b1"
    steady = workspace.root / "sims" / "batch" / f"{MATRIX}_b2"
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" in _verbs(
        (rotor / "BATCH-7001-7001.txt").read_text(encoding="utf-8")
    )
    assert (rotor / "actions" / "pfs_batch_schedule.json").is_file()
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" not in _verbs(
        (steady / "BATCH-7002-7004.txt").read_text(encoding="utf-8")
    )
    assert list((steady / "actions").iterdir()) == []

    def unit(sim: str, order: int, steady_kind: bool) -> PolarUnit:
        return PolarUnit(
            sim_id=sim,
            order=order,
            ncpus=8,
            fs_build=BUILD,
            run_ids=(f"m/sim_{sim}/p0",),
            point_seconds=(60.0,),
            walltime_cell_s=None,
            walltime_cell_text=None,
            best=True,
            margin_s=60.0,
            steady=steady_kind,
        )

    jobs, _ = split_polars([unit("1", 1, False), unit("2", 2, True), unit("3", 3, False)], 1)
    assert [[u.sim_id for u in job.units] for job in jobs] == [["1", "3"], ["2"]]

    def point(sim: str, steady_kind: bool) -> JobPoint:
        return JobPoint(
            run_id=f"m/sim_{sim}/p0",
            sim_id=sim,
            point_name="p0",
            text="START_SOLVER\n",
            datapoint_dir=tmp_path / sim,
            outputs=(),
            action_exports="",
            first_export_step=None,
            stop_text="",
            time_steps=0 if steady_kind else 4,
            steady=steady_kind,
        )

    mixed = [JobPolar("1", (point("1", False),)), JobPolar("2", (point("2", True),))]
    with pytest.raises(CampaignConfigError, match="never both"):
        assemble_job(mixed, kind="batch", version=BUILD, job_log=None, job_dir=tmp_path)


def test_p0351_steady_fr403_what_stays_out_is_named(tmp_path):
    """P0351-BATCH-STEADY (FR-403): steady and quasi-steady rows join; what cannot is named.

    ``steady`` and ``qsteady_rotor`` rows are eligible; a LEGACY row (its own recipe
    builds it) and a steady row asking a warm sweep (``COLD_START`` false) are left
    out with their reasons; a steady point initialising the solver twice (a
    quasi-steady wheel, a wake termination read from a file) is refused for the
    job, because the second initialisation prints the job log's cut marker, and an
    unsteady point is not judged by that rule.
    """
    workspace, _profile, _ = _workspace(tmp_path)
    base = _continuing_case("{FINISH_PENDING}")

    def judged(**variables: str) -> str | None:
        case = base.model_copy(update={"variables": variables})
        return eligibility(case, workspace=workspace, version="26.124")

    assert judged(**{WORKFLOW_KEY: "steady"}) is None
    assert judged(**{WORKFLOW_KEY: "qsteady_rotor"}) is None
    assert judged(**{WORKFLOW_KEY: "steady", "COLD_START": "true"}) is None
    assert "COLD_START false" in str(judged(**{WORKFLOW_KEY: "steady", "COLD_START": "false"}))
    assert "LEGACY" in str(judged())

    def point(text: str, steady_kind: bool) -> JobPoint:
        return JobPoint(
            run_id="m/sim_1/p0",
            sim_id="1",
            point_name="p0",
            text=text,
            datapoint_dir=tmp_path,
            outputs=(),
            action_exports="",
            first_export_step=None,
            stop_text="",
            time_steps=0,
            steady=steady_kind,
        )

    twice = "INITIALIZE_SOLVER\nSYMMETRY NONE\n\nINITIALIZE_SOLVER\nSYMMETRY NONE\n\nSTART_SOLVER\n"
    with pytest.raises(CampaignConfigError, match="initialises the solver 2 times"):
        refuse_a_second_initialization(point(twice, True))
    refuse_a_second_initialization(point(twice, False))
    refuse_a_second_initialization(point("INITIALIZE_SOLVER\n\nSTART_SOLVER\n", True))


# ------------------------------------------------------------------ collect


#: The stand-in solver: it writes every save and export target the script names,
#: the loads table at the incidence last set, and at each EXPORT_LOG the log as it
#: stands: the import echo at each OPEN, the marker at each re-initialisation and
#: refresh, one solve at each START_SOLVER. A relative target is the working
#: folder's. The identity pre-flight's script runs nothing.
STAND_IN = r"""
import pathlib, sys
script = pathlib.Path(sys.argv[1])
if script.name == "preflight.txt":
    sys.exit(0)
here = pathlib.Path(__file__).parent
opened = (here / "opened.txt").read_text(encoding="utf-8")
solve = (here / "solve.txt").read_text(encoding="utf-8")
loads = (here / "loads.txt").read_text(encoding="utf-8")
lines = script.read_text(encoding="utf-8").splitlines()
log, alpha = "", 0.0
for index, line in enumerate(lines):
    words = line.split()
    if not words:
        continue
    verb = words[0]
    if verb == "OPEN":
        log += opened
    elif verb in ("REMOVE_INITIALIZATION", "NEW_SIMULATION"):
        log += "Solution cleared. Initialization removed.\n"
    elif verb == "SOLVER_SET_AOA":
        alpha = float(words[1])
    elif verb == "START_SOLVER":
        log += solve.replace("{alpha}", "%.3f" % alpha)
    if verb in ("SAVEAS", "SAVE_PLOT_TO_FILE") or verb.startswith("EXPORT_"):
        target = pathlib.Path(lines[index + 1].strip())
        if not target.is_absolute():
            target = pathlib.Path.cwd() / target
        if verb == "EXPORT_LOG":
            body = log
        elif verb == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
            body = loads.replace("{alpha}", "%.3f" % alpha)
        else:
            body = target.name
        target.write_bytes(body.encode("utf-8"))
"""


def _stand_in(folder: Path) -> Path:
    """Write the stand-in and the texts it writes: one solve of the recorded steady log."""
    folder.mkdir(parents=True, exist_ok=True)
    recorded = TWO_SOLVES.read_text(encoding="utf-8").splitlines()
    start = [i for i, line in enumerate(recorded) if "being initialized" in line][1]
    end = next(i for i, line in enumerate(recorded) if line.startswith("Solver run time")) + 1
    solve = "\n".join(recorded[start:end]) + "\n"
    solve = re.sub(r"Angle of attack \(Deg\): -?[\d.]+", "Angle of attack (Deg): {alpha}", solve)
    assert MARKER not in solve and "{alpha}" in solve, "the fixture moved"
    (folder / "opened.txt").write_text(
        "Running script file: job\n\n1 bodies, 145 vertices and 272 faces imported.\n\n",
        encoding="utf-8",
    )
    (folder / "solve.txt").write_text(solve, encoding="utf-8")
    loads = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    loads = re.sub(r"(Angle of attack \(Deg\)\s+)[-\d.]+", r"\g<1>{alpha}", loads)
    loads = re.sub(r"(Simulation file:\s+).*", r"\g<1>point.fsm", loads)
    last = re.findall(r"^(\d+)\s", solve, flags=re.MULTILINE)[-1]
    loads = re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{last}", loads)
    (folder / "loads.txt").write_text(loads, encoding="utf-8")
    program = folder / "stand_in.py"
    program.write_text(STAND_IN, encoding="utf-8")
    return program


def _collected(workspace) -> dict[str, dict]:
    """Collect once; return each record as JSON, the workspace root read as one token."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        collect_once(workspace, interval=0.0, sleep=lambda _s: None)
    text = json.dumps([r.model_dump(mode="json") for r in workspace.read_manifest()])
    for spelling in (workspace.root.as_posix(), str(workspace.root).replace("\\", "\\\\")):
        text = text.replace(spelling, "<root>")
    return {record["run_id"]: record for record in json.loads(text)}


#: What a point collected from a job may say differently from the same point
#: submitted alone and collected (FR-366): where it ran, how it was launched, and
#: its script's digest (its inputs are named under the batch while it runs).
NAMED = {
    "submission",
    "executor",
    "argv",
    "cwd",
    "started_at",
    "finished_at",
    "walltime_s",
    "walltime_margin_s",
    "script_sha256",
}


def test_p0351_steady_fr403_collect_completes_a_batched_point_as_alone(tmp_path):
    """P0351-BATCH-STEADY (FR-403): collect completes each steady point as the point alone.

    The steady job runs locally through the stand-in, ``collect`` moves its
    polars home and cuts the job log into each point's own log; each point is
    then judged by the package's own assessor. Polar 7004 sweeps the Reynolds
    number, so its second point reopens its geometry inside its polar and its
    log segment carries its own opening echo, which the cut does not repeat.
    The control is each point submitted alone, run through the same stand-in in
    its datapoint folder and
    collected the same way. Each grouped record equals its control but the named
    fields: the same CONVERGED status, outputs, ``outputs_sha256``, iterations,
    residual, log read and ``wall_time_s``, which is the solver run time of the
    point's sliced log, with that basis in ``submission.job.wall_time_basis``.
    """
    program = _stand_in(tmp_path / "solver")
    alone = _alone(tmp_path / "alone", flow=True)
    for record in alone.read_manifest():
        folder = alone.sim_dir(record.sim_id) / record.submission["working_dir"]
        script = alone.sim_dir(record.sim_id) / record.script_path
        subprocess.run(
            [sys.executable, str(program), str(script)],
            cwd=folder,
            check=True,
            env=os.environ.copy(),
        )
    theirs = _collected(alone)

    workspace, _profile, _ = _workspace(tmp_path / "grouped")
    (workspace.inputs_dir / "hpc" / "h001.toml").unlink()
    matrix = _matrix(tmp_path / "grouped", flow=True)
    _plan(workspace, matrix)

    class Solver(StubSolver):
        def _argv(self, script_path: Path) -> list[str]:
            return [sys.executable, str(program), str(script_path)]

    _run(workspace, matrix, executor=Solver(""), local=True)
    assert (workspace.root / HOME / "BATCH-7002-7004.end.json").is_file()
    mine = _collected(workspace)
    assert sorted(mine) == sorted(theirs)
    for run_id, record in mine.items():
        control = theirs[run_id]
        assert record["status"] == control["status"] == "CONVERGED", (run_id, record["error"])
        differing = sorted(k for k in set(record) | set(control) if record.get(k) != control.get(k))
        assert set(differing) <= NAMED, (run_id, differing)
        assert record["outputs_sha256"] and record["iterations"] is not None, run_id
        assert record["wall_time_s"] == pytest.approx(record["solver_run_time_s"]), run_id
        basis = record["submission"]["job"]["wall_time_basis"]
        assert "sliced log" in basis, basis


def test_p0351_steady_fr403_a_plan_with_no_job_runs_nothing(tmp_path):
    """P0351-BATCH-STEADY (FR-403, FR-365): a receipt that holds no job is refused, unrun.

    Both steady rows state ``COLD_START`` false, so the plan leaves both out and
    its receipt holds no job. ``run --batch 1 --local`` refuses it and the solver
    is started for nothing: the empty receipt was read as no selection until
    0.35.1, and every polar the plan had left out ran in the default mode. The
    control is the same matrix with cold rows, whose job runs once.
    """
    seen = tmp_path / "seen.txt"
    code = (
        "import pathlib, sys; "
        f"p = pathlib.Path({seen.as_posix()!r}); "
        "old = p.read_text() if p.exists() else ''; "
        "p.write_text(old + pathlib.Path(sys.argv[1]).name + chr(10))"
    )
    for warm, folder in ((True, "warm"), (False, "cold")):
        workspace, _profile, _ = _workspace(tmp_path / folder)
        (workspace.inputs_dir / "hpc" / "h001.toml").unlink()
        matrix = _matrix(tmp_path / folder)
        if warm:
            text = matrix.read_text(encoding="utf-8")
            text = text.replace("VELOCITY: 30.0", "VELOCITY: 30.0 / COLD_START: false")
            matrix.write_text(text, encoding="utf-8")
        plan = _plan(workspace, matrix)
        assert len(plan.grouping.jobs) == (0 if warm else 1), plan.grouping
        seen.unlink(missing_ok=True)
        if warm:
            with pytest.raises(MatrixError, match="holds no job"):
                _run(workspace, matrix, executor=StubSolver(code), local=True)
            assert not seen.exists(), seen.read_text(encoding="utf-8")
            assert workspace.read_manifest() == []
        else:
            _run(workspace, matrix, executor=StubSolver(code), local=True)
            assert seen.read_text(encoding="utf-8").split() == [
                "preflight.txt",
                "BATCH-7002-7004.txt",
            ]
