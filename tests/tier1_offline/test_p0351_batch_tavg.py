"""FR-402: a polar asking ``[time_averaging]`` joins a grouped job (0.35.1, P0351-BATCH-TAVG).

0.35.0 left every such polar out of ``plan --batch`` and ``plan --polar-sweep``. The grouped
job already carries what a time-averaged point needs, through the per-point re-pointing of
FR-355 (the owner's design of 2026-10-02): at a point's first step the job's counter makes
that point current from the job's schedule, counts its steps from 1 again, and writes the
point's own per-step exports, every name absolute in the point's own datapoint folder, from
the point's own first export step (the window's first step, G25). These tests take two
time-averaging rotor polars of two points each through the real plan, the real run and the
real collect and post, once grouped and once alone, and compare what each point leaves.

No solver runs. :func:`emulate` plays the solver from the script it is handed, in the
behaviour measured on 26.124 in the dev-wheel rehearsal of 2026-10-02 (arm R2,
``EXPORT_UNSTEADY_AFTER_ITER`` 20 and 10 on a grouped job of four points): every registered
action runs after each time step, in registration order; a SCRIPT action's exports are
written stamped ``<stem>_iteration=<step><suffix>``; and that step is the step of the
simulation now marching, which starts again at 1 after ``REMOVE_INITIALIZATION`` and after
``NEW_SIMULATION`` (point 2 of polar A stamped 20 to 45, not 65 to 90; point 1 of polar B
stamped 10 and 11 at job count 100 and 101).
"""

from __future__ import annotations

import ast
import json
import runpy
import shlex
import warnings
import zlib
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.post.products import write_campaign_products
from pyflightstream.results.log import RESTART_MARKER
from pyflightstream.run import SubmittingExecutor
from pyflightstream.run._batch_plan import plan_grouped_matrix
from pyflightstream.run._batch_run import run_grouped_matrix
from pyflightstream.run.collect import collect_once
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_g25_surface_time_average import _step_body
from tests.tier1_offline.test_g45_tecplot_from_vtk import _write_solver_vtk
from tests.tier1_offline.test_goal021_inputs_absolute import BUILD, _rotor_row, _workspace
from tests.tier1_offline.test_matrix_run import HPC_PROFILE, converged

#: The two polars: 7001 at alpha 0 and 2, 7002 at alpha 4 and 6 (distinct point names).
SWEEPS = {"7001": "0.0,2.0", "7002": "4.0,6.0"}
#: Forty steps of 18 degrees.
CLOCK = ("DELTA_TIME: 0.0001 / TIME_ITERATIONS: 720", "DELTA_TIME: 0.0025 / TIME_ITERATIONS: 40")
#: The last four steps of forty are averaged.
WINDOW = [37, 40]
PPROC = "[time_averaging]\nlast_iters = 4\n"
#: The frame the synthetic surfaces are written in: the loads frame the records state.
FRAME = {"frame": 2, "origin": [0.0, 0.0, 0.0], "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}
#: The commands whose next line is the file they write.
WRITES = ("SAVEAS", "SAVE_PLOT_TO_FILE", "UNSTEADY_SOLVER_EXPORT_PLOTS")
ACTION = "SET_NEW_UNSTEADY_SOLVER_ACTION"
#: The verbs after which the solver's log starts a new point (FR-368, MEASURED).
RESTARTS = ("REMOVE_INITIALIZATION", "NEW_SIMULATION")


def _writes(head: str) -> bool:
    return head in WRITES or head.startswith("EXPORT_")


def _content(path: Path, step: int | None) -> None:
    """Write one export: a surface whose values depend on its point and step, or a tag."""
    key = f"{path.parent.parent.parent.name}/{path.stem}"
    if path.suffix == ".vtk":
        points, polygons, values = _step_body(step or WINDOW[1])
        scale = 1.0 + (zlib.crc32(key.encode()) % 97) / 10.0
        scaled = {name: np.asarray(v) * scale for name, v in values.items()}
        scaled["Boundary_Index"] = values["Boundary_Index"]
        _write_solver_vtk(path, points, polygons, scaled, FRAME)
    else:
        path.write_text(f"{key} {step}\n", encoding="utf-8")


def _export(lines: list[str], cwd: Path, step: int | None, log: list[str]) -> None:
    """Write every target of an export text, stamped with ``step`` when an action runs it."""
    for index, line in enumerate(lines[:-1]):
        words = line.split()
        if not words or not _writes(words[0]):
            continue
        path = cwd / lines[index + 1].strip()
        if step is not None:
            path = path.with_name(f"{path.stem}_iteration={step}{path.suffix}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if words[0] == "EXPORT_LOG":
            path.write_text("".join(f"{line}\n" for line in log), encoding="utf-8")
        else:
            _content(path, step)


def _program(path: Path) -> None:
    """Run one action program as the solver does, as its own main, and require a clean exit."""
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as stop:
        assert stop.code in (0, None), (path, stop.code)


def _march(actions: list[tuple[str, Path]], steps: int, cwd: Path, log: list[str]) -> None:
    """One START_SOLVER: every action after every step, the step from 1 (measured, R2)."""
    log.append("Following geometry is being initialized")
    for step in range(1, steps + 1):
        log.append(f"Solving unsteady time-step iteration ( {step} / {steps} )")
        for kind, path in actions:
            if kind == "COMMAND_LINE":
                _program(path)
            elif path.is_file():
                _export(path.read_text(encoding="utf-8").splitlines(), cwd, step, log)


def emulate(script: Path, cwd: Path) -> None:
    """Play the solver on ``script`` run from ``cwd``, as measured on 26.124 (module docstring)."""
    lines = script.read_text(encoding="utf-8").splitlines()
    actions: list[tuple[str, Path]] = []
    log: list[str] = []
    steps = 0
    for index, line in enumerate(lines):
        words = line.split()
        head = words[0] if words else ""
        if head == ACTION:
            target = shlex.split(lines[index + 1], posix=False)[-1].strip('"')
            actions.append((words[1], cwd / target))
        elif head == "TIME_ITERATIONS":
            steps = int(words[1])
        elif head == "START_SOLVER":
            _march(actions, steps, cwd, log)
        elif head in RESTARTS:
            log.append(RESTART_MARKER)
        elif _writes(head):
            _export(lines[index : index + 2], cwd, None, log)


def _matrix(tmp_path: Path) -> tuple[CampaignWorkspace, Path]:
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(PPROC, encoding="utf-8")
    matrix = _rotor_row(tmp_path)
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    row = row.replace(*CLOCK)
    rows = [
        row.replace("7001", sim, 1).replace("0.0,2.0,4.0", sweep) for sim, sweep in SWEEPS.items()
    ]
    matrix.write_text("\n".join([header, rule, *rows]) + "\n", encoding="utf-8")
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(HPC_PROFILE, encoding="utf-8")
    return workspace, matrix


def _executor(workspace: CampaignWorkspace) -> SubmittingExecutor:
    profile = read_hpc_profile(workspace.inputs_dir / "hpc" / "h001.toml")
    return SubmittingExecutor(profile, values={"fs_build": BUILD}, submit=False)


def _keywords() -> dict[str, object]:
    return {"name": "rotor", "recipes": {}, "recipe_registry": workflow_registry()}


def _grouped(tmp_path: Path, mode: str):
    """Plan and run the two polars grouped; return the workspace and the grouping receipt."""
    workspace, matrix = _matrix(tmp_path)
    batch = 1 if mode == "batch" else None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_grouped_matrix(matrix, workspace, mode=mode, batch=batch, **_keywords())
        assert plan.grouping.left_out == (), plan.grouping.left_out
        run_grouped_matrix(
            matrix,
            workspace,
            mode=mode,
            batch=batch,
            assess=converged,
            executor=_executor(workspace),
            **_keywords(),
        )
    return workspace, plan.grouping


def _alone(tmp_path: Path) -> CampaignWorkspace:
    """Run the same points in the default mode, each played alone from its own folder."""
    workspace, matrix = _matrix(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        run_matrix(
            matrix, workspace, executor=_executor(workspace), assess=converged, **_keywords()
        )
    for record in workspace.read_manifest():
        sim = workspace.sim_dir(record.sim_id)
        emulate(sim / str(record.script_path), sim / str(record.submission["working_dir"]))
    return workspace


def _played(workspace: CampaignWorkspace, grouping) -> None:
    """Play every job of a grouped run from its own folder, then write its local end record."""
    for job in grouping.jobs:
        script = workspace.root / job.script
        emulate(script, script.parent)
        (script.parent / f"{script.stem}.end.json").write_text('{"returncode": 0}\n')


def _collected_and_posted(workspace: CampaignWorkspace) -> dict[str, dict]:
    def judged(_record, _sim_dir):
        return RunStatus.CONVERGED, None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        collect_once(workspace, interval=0.0, sleep=lambda _s: None, assessor=judged)
        assert {r.status for r in workspace.read_manifest()} == {RunStatus.CONVERGED}
        write_campaign_products(workspace, overwrite=True, matrix_stem="rotor")
    manifest = workspace.products_dir("rotor") / "products.json"
    products = json.loads(manifest.read_text(encoding="utf-8"))["products"]
    return {name: entry for name, entry in products.items() if entry.get("kind") == "average"}


def _stamped(workspace: CampaignWorkspace) -> dict[str, list[str]]:
    """Every stamped file of each point's home folder, by point folder."""
    found: dict[str, list[str]] = {}
    for sim in SWEEPS:
        for folder in sorted((workspace.sim_dir(sim) / "datapoints").iterdir()):
            names = sorted(p.name for p in folder.iterdir() if "_iteration=" in p.name)
            found[f"sim_{sim}/{folder.name}"] = names
    return found


def _alone_program(folder: Path) -> dict[str, object]:
    """The constants of the counter program a point run alone is given, read off its file."""
    tree = ast.parse((folder / "actions" / "pfs_unsteady_actions.py").read_text(encoding="utf-8"))
    return {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ("EXPORTS", "THRESHOLD", "TIME_ITERATIONS")
    }


@pytest.mark.parametrize("mode", ["batch", "polar_sweep"])
def test_p0351_tavg_fr402_time_averaging_polars_are_grouped(tmp_path, mode):
    """P0351-BATCH-TAVG (FR-402): both time-averaging polars join the grouped plan, none left out.

    Red on 0.35.0: both polars are left out with "its post-processing asks
    [time_averaging]", and no job is planned.
    """
    workspace, matrix = _matrix(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_grouped_matrix(
            matrix,
            workspace,
            mode=mode,
            batch=1 if mode == "batch" else None,
            **_keywords(),
        )
    assert plan.grouping.left_out == (), "FR-402: a time-averaging polar joins"
    sims = [sim for job in plan.grouping.jobs for sim in job.sims]
    assert sims == ["7001", "7002"], sims
    assert sum(len(job.points) for job in plan.grouping.jobs) == 4


@pytest.mark.requirement("FR-355")
@pytest.mark.parametrize("mode", ["batch", "polar_sweep"])
def test_p0351_tavg_fr402_each_point_exports_into_its_own_folder_from_its_window(tmp_path, mode):
    """P0351-BATCH-TAVG (FR-402): the schedule re-points each point's per-step exports.

    Line by line: each point's exports in the job's schedule are the EXPORTS of the counter
    program the same point is given to run alone, every name line made absolute in the
    point's own datapoint folder and every other line unchanged; its first export step is the
    alone THRESHOLD, the first step of the window its record carries; and its steps are its own
    (the job counts every point from 1). The job registers the exports action once.
    """
    workspace, grouping = _grouped(tmp_path, mode)
    records = {r.run_id: r for r in workspace.read_manifest()}
    assert len(records) == 4
    for job in grouping.jobs:
        job_dir = (workspace.root / job.script).parent
        text = (workspace.root / job.script).read_text(encoding="utf-8")
        assert text.count(f"{ACTION} SCRIPT pfs_unsteady_exports") == 1
        schedule = json.loads((job_dir / "actions/pfs_batch_schedule.json").read_text("utf-8"))
        assert [p["run_id"] for p in schedule["points"]] == list(job.points)
        for entry in schedule["points"]:
            record = records[entry["run_id"]]
            folder = Path(entry["datapoint_dir"])
            assert folder.name == Path(record.submission["working_dir"]).name
            alone = _alone_program(folder)
            names = set(record.submission["declared_outputs"])
            expected = [
                str(folder / line) if line in names else line
                for line in str(alone["EXPORTS"]).split("\n")
            ]
            assert entry["exports"].split("\n") == expected, entry["run_id"]
            assert entry["first_export_step"] == alone["THRESHOLD"] == WINDOW[0]
            assert record.surface_average_window["iterations"] == WINDOW
            assert entry["time_steps"] == alone["TIME_ITERATIONS"] == WINDOW[1]
        assert schedule["total_steps"] == WINDOW[1] * len(job.points)


@pytest.mark.parametrize("mode", ["batch", "polar_sweep"])
def test_p0351_tavg_fr402_grouped_points_leave_what_alone_points_leave(tmp_path, mode):
    """P0351-BATCH-TAVG (FR-402): stamped exports and the averaged surface equal a point alone.

    After the grouped job is played and collected, each point's home datapoint folder holds
    exactly the stamped per-step files the same point run alone holds (the window's four
    steps, the alone names, no file of another point), and the post writes each point's
    time-averaged surface byte for byte as it does for the point run alone, its steps the
    window and its inputs the point's own stamped VTK files.
    """
    grouped, grouping = _grouped(tmp_path / "grouped", mode)
    _played(grouped, grouping)
    alone = _alone(tmp_path / "alone")
    averages = _collected_and_posted(grouped)
    assert averages == _collected_and_posted(alone)
    stamped = _stamped(grouped)
    assert stamped == _stamped(alone)
    for folder, names in stamped.items():
        stem = folder.rsplit("DP-", 1)[1]
        steps = sorted({int(n.split("_iteration=")[1].split(".")[0]) for n in names})
        assert steps == list(range(WINDOW[0], WINDOW[1] + 1)), folder
        assert all(name.startswith(stem) for name in names), folder
    assert len(averages) == 4
    for name, entry in averages.items():
        assert entry["steps"] == list(range(WINDOW[0], WINDOW[1] + 1)), name
        stem = Path(name).name.removesuffix("_time_average.dat")
        assert all(Path(key).name.startswith(f"{stem}_iteration=") for key in entry["inputs"])
        products = grouped.products_dir("rotor")
        assert (products / name).read_bytes() == (alone.products_dir("rotor") / name).read_bytes()
