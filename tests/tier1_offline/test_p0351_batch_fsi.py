"""FR-407: a coupled (FSI) row joins a grouped job (0.35.1, P0351-BATCH-FSI).

Until 0.35.1 the grouped plan left a coupled polar out ("a coupled run is not
grouped in this release"). The coupling loop of the fixed wing on ``unsteady``
(FSI-G) runs INSIDE the solver instance: ``SET_AEROELASTIC_COUPLING_IN_UNSTEADY
ENABLE`` couples once per time step, the solver runs the post-processing script
and then the structural program it was given (``fsi_callback.py``) in the
working directory it was given, and the program keeps its state in that folder
(``cases/fsi_workspace.py``, ``_stage_and_emit``). No Python runs between two
solver passes outside the instance, so the loop does not keep a coupled point
out of a job. What a job must do instead:

* enter every coupled point by ``NEW_SIMULATION`` and its whole text, even
  after a point of its own polar: ``REMOVE_INITIALIZATION`` keeps the model
  loaded (DESIGN-0350 arms A and D), and with it the mesh an earlier point's
  coupling morphed; the whole text reopens the pristine geometry;
* run a copy of the point's post-processing script whose targets are absolute
  in the point's folder, because the job's process does not run in it;
* switch the coupling off for a point without it that follows a coupled one;
* cut a coupled point's log from its own segment, which opens the model.

The steady merge admits the steady fixture at eligibility. Synthetic cases.
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.cases.workflows._batch_actions import is_absolute_target
from pyflightstream.cases.workflows._batch_script import (
    JOB_POST_SCRIPT,
    SOLVER_BLOCK,
    JobPolar,
    assemble_job,
    couples,
    job_point,
    refuse_unspliceable,
    write_targets,
)
from pyflightstream.results.log import point_log_text, split_job_log
from pyflightstream.run import LoadsAssessor, SubmittingExecutor
from pyflightstream.run._batch_plan import eligibility
from pyflightstream.run._batch_run import run_grouped_matrix
from pyflightstream.run.collect import collect_once
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace._batches import GroupingReceipt
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case, unsteady_wing_case
from tests.tier1_offline.test_p0350_batch_collect import (
    A2,
    TAGS,
    _converged,
    _job,
    _make_link,
    _no_sleep,
    _record,
    _write_point,
)
from tests.tier1_offline.test_p0350_batch_run import PROFILE, RECORDS_ARGV
from tests.tier1_offline.test_p0350_batch_run import _job as _run_job
from tests.tier1_offline.test_p0350_batch_script import relative_paths
from tests.tier1_offline.test_workflows import unsteady_case

BUILD = "26.124"
ROOT = PurePosixPath("/ws/sims/batch/mtx_b1")
POST = "SET_AEROELASTIC_POST_PROCESSING_SCRIPT"
#: The matrix name the grouped run fixture of 0.35.0 labels its batch with (``rotor_b1``).
RUN_MATRIX = "rotor"


# Synthetic inputs from tests.tier3_licensed.fsi_lq1, defined inline for tier 1.
NACA = "4412"
CHORD_M, SEMI_SPAN_M, N_CHORD, N_SPAN = 1.0, 4.0, 25, 20


_SETUP = """# s340: steady preset of LQ1 (0.34.0, RPT-128), the s110 of RPT-092;
# far field at five layers.
boundary_layer_type = "TURBULENT"
viscous_coupling = false
convergence = 1e-5
max_parallel_threads = 8
NITER = 500
set_solver_model = "SUBSONIC_PRANDTL_GLAUERT"
proximity_avoidance = "DISABLE"
stabilization = "ENABLE"
stabilization_strength = 1.0
induced_wake_velocity = true
farfield_layers = 5
significant_digits = 7
convergence_iterations = 20
solver_minimum_cp = -100

[flight_condition]
MUPas = 1.789e-5
ASMPS = 340.29
TK = 288.15
PPA = 101325
"""


_REFERENCE = """# r340: the closed right half of the synthetic NACA 4412 wing (public shape law),
# chord 1 m, semi-span 4 m, root at y = 0; moment point on the quarter chord, the
# FSI-G pitch axis and the origin of the MRP frame the sections are cut in.
area_m2 = 4.0
chord_m = 1.0
span_m = 4.0

[moment_point]
x_m = 0.25
y_m = 0.0
z_m = 0.0
"""


_PPROC = """# p340: the fixed wing: one spanwise distribution normal to Y in MRP
# (the FSI-G route's).
[groups]
TOTAL = "all"

[sections]
count = 20
include_symmetry = false

[[sections.distributions]]
families = ["Wing"]
frame = "MRP"
planes = ["XZ"]

[products]
polars = true
sections = true
"""


_MATRIX_HEADER = (
    "POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION | "
    "SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | "
    "WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n" + "-" * 96 + "\n"
)


def _section_contour() -> list[list[float]]:
    """The NACA 4412 contour as the FSI input takes it: (toward the LE, toward suction) [m]."""
    from pyflightstream.qa.geometry import naca4_contour

    contour = naca4_contour(NACA, N_CHORD)[:-1] * CHORD_M
    return [[round(0.25 * CHORD_M - x, 9), round(z, 9)] for x, z in contour]


def _wing_obj() -> tuple[str, int]:
    """The closed half wing as OBJ text (one group), and its vertex count."""
    from pyflightstream.qa.geometry import WingSpec, wing_triangles

    spec = WingSpec(naca=NACA, chord_m=CHORD_M, span_m=SEMI_SPAN_M, n_chord=N_CHORD, n_span=N_SPAN)
    triangles = wing_triangles(spec, translation_m=(0.0, SEMI_SPAN_M / 2.0, 0.0))
    index: dict[tuple[float, float, float], int] = {}
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for triangle in triangles:
        ids = []
        for point in triangle:
            # Adding 0.0 turns a negative zero into zero and leaves every other value.
            key = (
                round(float(point[0]), 9) + 0.0,
                round(float(point[1]), 9) + 0.0,
                round(float(point[2]), 9) + 0.0,
            )
            if key not in index:
                index[key] = len(vertices) + 1
                vertices.append(key)
            ids.append(index[key])
        if len(set(ids)) == 3:
            faces.append((ids[0], ids[1], ids[2]))
    lines = [
        f"# closed right half of the synthetic NACA {NACA} wing (public shape law), "
        f"chord {CHORD_M:g} m, semi-span {SEMI_SPAN_M:g} m; metres",
        "o Wing",
        *(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices),
        *(f"f {a} {b} {c}" for a, b, c in faces),
    ]
    return "\n".join(lines) + "\n", len(vertices)


def _trailing_edge_points() -> str:
    """One trailing-edge point per spanwise panel, at mid-panel, in metres."""
    rows = ["METER"]
    for k in range(N_SPAN):
        y = SEMI_SPAN_M * (k + 0.5) / N_SPAN
        rows.append(f"{CHORD_M:.9f},{y:.9f},{0.0:.9f}")
    return "\n".join(rows) + "\n"


def _fsi_input() -> str:
    """f340: the f011 of RPT-092 with the NACA 4412 contour at every station."""
    stations = [0.5 * k for k in range(9)]
    contour = json.dumps(_section_contour())
    sections = ",\n  ".join(contour for _ in stations)
    return (
        f"# f340: the closed right half of the synthetic NACA {NACA} wing as SOLID Ti-6Al-4V\n"
        "# (grade 5, annealed), clamped at the root, under its aerodynamic loads and its own\n"
        "# weight (FSI-G). Sections: the contour of the mesh, toward the leading edge and\n"
        "# toward the suction side, about the quarter chord (the pitch axis).\n"
        'mode = "calculated"\nmaterial = "ti-6al-4v-grade5-annealed"\n\n'
        "[config]\nblade_count = 1\nomega_rad_per_s = 0.0\n\n"
        "[config.wing]\nself_weight = true\ngravity_m_per_s2 = [0.0, 0.0, -9.80665]\n"
        'span_axis = "+Y"\norigin_m = [0.25, 0.0, 0.0]\n\n'
        f"[sections]\nstation_radii_m = {json.dumps(stations)}\n"
        f"chord_m = {json.dumps([CHORD_M] * len(stations))}\n"
        f"geometric_pitch_deg = {json.dumps([0.0] * len(stations))}\n"
        f'geometry_source = "Synthetic NACA {NACA} (public shape law, '
        'pyflightstream.qa.geometry), chord 1 m, metres"\n'
        "torsion_grid_cells = 64\n"
        f"sections_m = [\n  {sections}\n]\n"
    )


def _build_coupled_inputs(root: Path) -> None:
    """Stage the synthetic coupled wing inputs used by this offline submitting test."""
    inputs = root / "inputs"
    geometry = inputs / "geometries" / "coupled_wing"
    geometry.mkdir(parents=True, exist_ok=True)
    obj, _ = _wing_obj()
    (geometry / "coupled_wing.obj").write_text(obj, encoding="utf-8")
    (geometry / "coupled_wing.boundaries.toml").write_text(
        'boundaries = ["Wing"]\n[import]\nunits = "METER"\n'
        '[trailing_edges]\nfile = "coupled_wing.te.txt"\n[wake_termination]\ndetect = "auto"\n',
        encoding="utf-8",
    )
    (geometry / "coupled_wing.te.txt").write_text(_trailing_edge_points(), encoding="utf-8")
    for folder, name, body in (
        ("setups", "s340.toml", _SETUP),
        ("references", "r340.toml", _REFERENCE),
        ("pproc", "p340.toml", _PPROC),
        ("fsi", "f340.toml", _fsi_input()),
        ("", "executables.toml", f'"{BUILD}" = "{Path(sys.executable).as_posix()}"\n'),
    ):
        (inputs / folder).mkdir(parents=True, exist_ok=True)
        (inputs / folder / name).write_text(body, encoding="utf-8")


def _point(case, sim: str, tag: str):
    """One job point of ``case``, with the post-processing script its run stages."""
    case = case.model_copy(update={"sim_id": sim})
    script = Script(BUILD)
    build_script(case, script)
    staged = script.pending_input_files.get("fsi_post.txt", "")
    return job_point(
        case,
        run_id=f"mtx/sim_{sim}/DP-{tag}",
        text=script.render(),
        datapoint_dir=ROOT / f"sim_{sim}" / "datapoints" / f"DP-{tag}",
        version=BUILD,
        post_script=staged if isinstance(staged, str) else staged.decode("utf-8"),
    )


def _block(job, number: int) -> list[str]:
    block = job.blocks[number]
    return job.text.splitlines()[block.first_line - 1 : block.last_line]


def _after(lines: list[str], head: str) -> str:
    return lines[next(i for i, line in enumerate(lines) if line.split()[:1] == [head]) + 1]


def test_p0351_fsi_fr407_a_coupled_unsteady_row_joins(tmp_path):
    """P0351-BATCH-FSI (FR-407): ``eligibility`` lets an unsteady coupled row join.

    The steady merge also admits the same fixture's steady coupled row at eligibility.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    coupled = unsteady_wing_case(tmp_path)
    assert coupled.fsi is not None
    assert eligibility(coupled, workspace=workspace, version=BUILD) is None
    steady = steady_wing_case(tmp_path)
    assert eligibility(steady, workspace=workspace, version=BUILD) is None


def test_p0351_fsi_fr407_every_coupled_point_reopens_its_model(tmp_path):
    """P0351-BATCH-FSI (FR-407): coupled points refresh, run their own post copy, in their folder.

    A coupled polar of two points, then a polar without coupling. The second coupled point enters
    by ``NEW_SIMULATION`` (not a re-initialization); its structural nodes, working directory and
    structural program are its own folder, and its post-processing script line names the job's
    copy, whose every target is absolute in its own folder. The point without coupling switches
    the coupling off before its solver block. A splice difference before the restate anchor does
    not refuse a coupled point, and a coupled point whose staged post was not read refuses the
    job.
    """
    first = _point(unsteady_wing_case(tmp_path), "7001", "a")
    later = _point(unsteady_wing_case(tmp_path), "7001", "b")
    plain = _point(unsteady_case(), "7002", "a")
    assert couples(first) and couples(later) and not couples(plain)
    job = assemble_job(
        [JobPolar("7001", (first, later)), JobPolar("7002", (plain,))],
        kind="batch",
        version=BUILD,
        job_log=None,
        job_dir=ROOT,
    )
    assert [b.transition for b in job.blocks] == ["start", "refresh", "refresh"]
    assert [name for name, _ in job.files] == [
        JOB_POST_SCRIPT.format(order=1),
        JOB_POST_SCRIPT.format(order=2),
    ]
    for number, point in ((0, first), (1, later)):
        lines = _block(job, number)
        folder = str(point.datapoint_dir)
        assert _after(lines, "SET_AEROELASTIC_WORKING_DIRECTORY") == folder
        assert _after(lines, "IMPORT_AEROELASTIC_STRUCTURAL_NODES").startswith(folder)
        program = _after(lines, "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND")
        assert program.endswith(f'"{point.datapoint_dir / "fsi_callback.py"}"'), program
        name, body = job.files[number]
        assert _after(lines, POST) == str(ROOT / name)
        targets = write_targets(body, BUILD)
        assert targets and all(is_absolute_target(t) and t.startswith(folder) for t in targets)
    off = [line for line in _block(job, 2) if line.strip()]
    heads = [line.split()[0] for line in off]
    at = off.index("SET_AEROELASTIC_COUPLING_IN_UNSTEADY DISABLE")
    assert heads[at + 1] == SOLVER_BLOCK
    assert POST not in heads
    assert not relative_paths(job.text), relative_paths(job.text)
    moved = later.text.replace(
        "NEW_SIMULATION", "NEW_SIMULATION\n# a difference before any anchor", 1
    )
    refuse_unspliceable(first, replace(later, text=moved))
    unread = replace(later, post_script="")
    with pytest.raises(CampaignConfigError, match="post-processing script"):
        assemble_job(
            [JobPolar("7001", (first, unread))],
            kind="batch",
            version=BUILD,
            job_log=None,
            job_dir=ROOT,
        )


def _coupled_workspace(tmp_path: Path, *, coupled: bool):
    """The A2 batch of ``test_p0350_batch_collect``, its points' records coupled or not."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    staged = tmp_path / "staged"
    staged.mkdir()
    job_dir = workspace.root / str(_job("batch", 1)["dir"])
    sim = job_dir / "sim_2006"
    (sim / "scripts").mkdir(parents=True)
    for order, tag in enumerate(TAGS, start=1):
        (sim / "scripts" / f"P2006-{tag}.txt").write_bytes(b"script\n")
        _write_point(sim / "datapoints" / f"DP-{tag}", tag, order)
        record = _record(tag, job=_job("batch", order))
        if coupled:
            inputs = {**record.inputs_sha256, f"datapoints/DP-{tag}/fsi-provenance.json": "f" * 64}
            record = record.model_copy(update={"inputs_sha256": inputs})
        workspace.append_record(record)
    _make_link(staged, sim / "inputs")
    (job_dir / str(_job("batch", 1)["script"])).write_bytes(b"job script\n")
    (job_dir / "BATCH-2006-2006.end.json").write_bytes(b'{"returncode": 0}\n')
    return workspace


@pytest.mark.parametrize("coupled", [True, False], ids=["coupled", "control"])
def test_p0351_fsi_fr407_a_coupled_point_s_log_is_its_own_segment(tmp_path, coupled):
    """P0351-BATCH-FSI (FR-407): collect cuts a coupled later point's log from its own segment.

    A coupled point reopened its model, so its segment carries what a point run alone prints
    before its initialisation, and the polar's preamble is not put in front of it a second
    time. Control: the same records without the FSI provenance take the polar's preamble.
    """
    workspace = _coupled_workspace(tmp_path, coupled=coupled)
    collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=_converged)
    log = workspace.sim_dir("2006") / "datapoints" / "DP-AL+020" / "P2006-AL+020_log.txt"
    segments = split_job_log(A2)
    start = segments[1] if coupled else segments[0]
    assert log.read_text(encoding="utf-8") == point_log_text(A2, segments[1], polar_start=start)
    assert point_log_text(A2, segments[1], polar_start=segments[1]) != point_log_text(
        A2, segments[1], polar_start=segments[0]
    )


def test_p0351_fsi_fr407_a_grouped_run_writes_each_post_copy(tmp_path):
    """P0351-BATCH-FSI (FR-407): run --batch writes each coupled point's post copy in actions/.

    The synthetic half wing of LQ1 (public NACA shape law), coupled on ``unsteady`` with two
    points in one batch, through the real submitting executor (submit off): both points are
    SUBMITTED, the job folder holds ``actions/pfs_fsi_post_001.txt`` and ``_002.txt``, each the
    post the point staged in its own folder with every target in that folder, and the job script
    names each copy and enters the second point by ``NEW_SIMULATION``.
    """
    root = tmp_path / "camp"
    CampaignWorkspace.init(root)
    _build_coupled_inputs(root)
    workspace = CampaignWorkspace(root)
    row = (
        "7001 | 1 | 1 | WINGSYN | - | WING_FSI_UNSTEADY | MACH:0.147, REmi:3.42, ALPHA:sweep | "
        f"0.0,2.0 | coupled_wing.obj | r340 | s340 | p340 | NONE | - | 8 | - | {BUILD} | "
        "unsteady | DELTA_TIME: 0.01 / TIME_ITERATIONS: 20 / LAST_ITERS_AVG: 10 / FSI: f340\n"
    )
    matrix = root / f"{RUN_MATRIX}.fs"
    matrix.write_text(_MATRIX_HEADER + row, encoding="utf-8")
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-c", RECORDS_ARGV, (tmp_path / "argv.json").as_posix()]
    words = ", ".join(f"'{Path(w).as_posix() if w == sys.executable else w}'" for w in command)
    profile.write_text(PROFILE.format(command=words), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plan = plan_matrix(
            matrix, workspace, name=RUN_MATRIX, recipes={}, recipe_registry=workflow_registry()
        )
        assert not plan.blocked
        job = replace(_run_job("batch", ["7001"], [p.run_id for p in plan.points]), fs_build=BUILD)
        receipt = GroupingReceipt(
            schema="pyfs-grouping/1",
            mode="batch",
            requested=1,
            selection={"sims": None, "points": None},
            jobs=(job,),
            left_out=(),
            total_estimate_s=60.0,
            longest_estimate_s=60.0,
            max_walltime_s=None,
            warnings=(),
        )
        plan_file = workspace.plan_dir(RUN_MATRIX) / "plan.json"
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
        payload["grouping"] = receipt.to_json()
        plan_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        executor = SubmittingExecutor(
            read_hpc_profile(profile), values={"fs_build": BUILD}, submit=False
        )
        records = run_grouped_matrix(
            matrix,
            workspace,
            mode="batch",
            batch=1,
            name=RUN_MATRIX,
            recipes={},
            recipe_registry=workflow_registry(),
            assess=None,
            executor=executor,
            local=False,
        )
    assert [r.status for r in records] == [RunStatus.SUBMITTED] * 2, [r.error for r in records]
    job_dir = root / job.dir
    script = (job_dir / PurePosixPath(job.script).name).read_text(encoding="utf-8")
    for order, record in enumerate(records, start=1):
        copy = job_dir / JOB_POST_SCRIPT.format(order=order)
        folder = job_dir / "sim_7001" / str(record.submission["working_dir"])
        staged = (folder / "fsi_post.txt").read_text(encoding="utf-8")
        body = copy.read_text(encoding="utf-8")
        targets = write_targets(body, BUILD)
        assert targets == tuple(str(folder / name) for name in write_targets(staged, BUILD))
        assert script.count(f"{POST}\n{copy}\n") == 1, copy
    assert script.count("REMOVE_INITIALIZATION") == 0
    assert not relative_paths(script), relative_paths(script)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Solver mode: Unsteady", "1 bodies, 3 vertices and 1 faces imported."),
        ("Solving unsteady time-step iteration (3/3)...", "Symmetry is disabled."),
    ],
    ids=["only-before", "only-after"],
)
def test_p0351_fsi_fr407_one_initialization_condition_still_splits(before, after):
    """P0351-BATCH-FSI (FR-407): one setup-reset condition alone is a point boundary."""
    text = f"{before}\nSolution cleared. Initialization removed.\n{after}\n"
    segments = split_job_log(text)
    assert len(segments) == 2
    assert [(s.first_line, s.last_line, s.complete) for s in segments] == [
        (0, 0, True),
        (2, 2, False),
    ]


def _fsi_native_log(iteration: int, residual: float) -> str:
    """Synthetic double initialization followed by one complete unsteady solve."""
    return (
        "1 bodies, 3 vertices and 1 faces imported.\n"
        "Symmetry is disabled.\nSolver initialized in 0.1 seconds\n"
        "Solver mode: Unsteady\n\n"
        "Solution cleared. Initialization removed.\x00\n\n"
        "Symmetry is disabled.\nSolver initialized in 0.2 seconds\n"
        "Solver mode: Unsteady\n"
        "Solving unsteady time-step iteration (3/3)...\n"
        "----------------------------------------\n"
        "Iteration Res. Vel. Res. Pres.\n"
        "----------------------------------------\n"
        f"{iteration} {residual} {residual / 2}\n"
        "----------------------------------------\n"
        "Unsteady solver run time: 0.1 minutes\n"
    )


def _fsi_loads(iteration: int) -> str:
    """Synthetic unsteady loads with the native report's required fields."""
    return f"""Aerodynamic loads
Simulation file:                            synthetic.fsm
Angle of attack (Deg)                       0.000
Side-slip angle (Deg)                       0.000
Freestream velocity (m/s)                   12.000
Requested solver iterations                 500
Solver convergence limit                     1.000E-05
Force solver to run all iterations           F
Time increment (sec)                        0.01
Solver model:                               Subsonic (Prandtl-Glauert)
Solver mode:                                Unsteady
Reference velocity (m/s)                    12.000
Reference length (m)                        1.000
Reference area (m^2)                        1.000
Coordinate frame for analysis:              MRP
Current solver iteration number:            {iteration}
----------------------------------------------------------------------------------------------------
Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz
----------------------------------------------------------------------------------------------------
Panel,0,0,1,1,0.01,0.01,0,0,0
Total,0,0,1,1,0.01,0.01,0,0,0
----------------------------------------------------------------------------------------------------
Force Units: Coefficients
Moment Units: Coefficients
Software : Flightstream version 26.1, build #8172026
"""


def _fsi_assessment_workspace(tmp_path: Path, kind: str, ended: bool):
    """Stage synthetic coupled points and assess the same outputs individually."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(workspace.root)
    job = _job(kind, 1)
    job_dir = workspace.root / str(job["dir"])
    sim = job_dir / "sim_2006" if kind == "batch" else job_dir
    (sim / "scripts").mkdir(parents=True)
    cumulative = ""
    alone = []
    for order, tag in enumerate(TAGS, 1):
        stem = f"P2006-{tag}"
        iteration, residual = 10 + order, order * 2e-7
        native = _fsi_native_log(iteration, residual)
        cumulative += ("Solution cleared. Initialization removed.\n" if order > 1 else "") + native
        folder = sim / "datapoints" / f"DP-{tag}"
        folder.mkdir(parents=True)
        files = {
            f"{stem}.txt": _fsi_loads(iteration),
            f"{stem}_log.txt": native,
            f"{stem}_plot_residuals.txt": f"Iteration,Residual\n{iteration},{residual}\n",
            "fsi_convergence_log.csv": (
                "step,time_s,tip_z\n1,0.01,0.001\n2,0.02,0.002\n3,0.03,0.003\n"
            ),
            "fsi-provenance.json": json.dumps(
                {"schema": "synthetic-fsi", "source": "synthetic.obj"}
            ),
        }
        alone_sim = tmp_path / f"alone_{order}"
        outputs = alone_sim / "outputs"
        outputs.mkdir(parents=True)
        for name, body in files.items():
            (outputs / name).write_text(body, encoding="utf-8")
            if name != f"{stem}_log.txt":
                (folder / name).write_text(body, encoding="utf-8")
        (folder / f"{stem}.cumulative-log.txt").write_text(cumulative, encoding="utf-8")
        (sim / "scripts" / f"{stem}.txt").write_text("synthetic script\n", encoding="utf-8")
        record = _record(tag, job=_job(kind, order)).model_copy(
            update={"inputs_sha256": {"fsi-provenance.json": "a" * 64}}
        )
        workspace.append_record(record)
        alone.append(LoadsAssessor()(None, None, alone_sim))
    (job_dir / str(job["script"])).write_text("synthetic job\n", encoding="utf-8")
    if ended:
        (job_dir / f"{Path(str(job['script'])).stem}.end.json").write_text(
            json.dumps({"returncode": 0}), encoding="utf-8"
        )
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert len(report.collected) == 2, report.lines()
    return workspace.read_manifest(), alone


@pytest.mark.parametrize("kind", ["batch", "polar_sweep"])
@pytest.mark.parametrize("ended", [False, True])
def test_p0351_fsi_fr407_grouped_assessment_matches_alone(tmp_path, kind, ended):
    """P0351-BATCH-FSI (FR-407): setup resets retain the first point's residual evidence."""
    records, alone = _fsi_assessment_workspace(tmp_path, kind, ended)
    expected = alone[0]
    assert expected.status is RunStatus.CONVERGED, expected.error
    assert expected.time_steps == 3
    assert expected.residual == 2e-7
    record = records[0]
    assert record.status is expected.status, record.error
    assert (record.iterations, record.time_steps, record.residual) == (
        expected.iterations,
        expected.time_steps,
        expected.residual,
    )


@pytest.mark.parametrize("kind", ["batch", "polar_sweep"])
@pytest.mark.parametrize("ended", [False, True])
def test_p0351_fsi_fr407_grouped_does_not_use_previous_points_log(tmp_path, kind, ended):
    """P0351-BATCH-FSI (FR-407): the next point avoids false FAILED_INCOMPLETE_OUTPUT."""
    records, alone = _fsi_assessment_workspace(tmp_path, kind, ended)
    expected = alone[1]
    assert expected.status is RunStatus.CONVERGED, expected.error
    assert expected.iterations == 12
    assert expected.residual == 4e-7
    record = records[1]
    assert record.status is expected.status, record.error
    assert (record.iterations, record.time_steps, record.residual) == (
        expected.iterations,
        expected.time_steps,
        expected.residual,
    )
