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
from pyflightstream.run import SubmittingExecutor
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
from tests.tier3_licensed import fsi_lq1

BUILD = "26.124"
ROOT = PurePosixPath("/ws/sims/batch/mtx_b1")
POST = "SET_AEROELASTIC_POST_PROCESSING_SCRIPT"
#: The matrix name the grouped run fixture of 0.35.0 labels its batch with (``rotor_b1``).
RUN_MATRIX = "rotor"


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
    fsi_lq1.build(root, sys.executable)
    workspace = CampaignWorkspace(root)
    row = (
        "7001 | 1 | 1 | WINGSYN | - | WING_FSI_UNSTEADY | MACH:0.147, REmi:3.42, ALPHA:sweep | "
        f"0.0,2.0 | {fsi_lq1.GEOMETRY}.obj | r340 | s340 | p340 | NONE | - | 8 | - | {BUILD} | "
        "unsteady | DELTA_TIME: 0.01 / TIME_ITERATIONS: 20 / LAST_ITERS_AVG: 10 / FSI: f340\n"
    )
    matrix = root / f"{RUN_MATRIX}.fs"
    matrix.write_text(fsi_lq1._MATRIX_HEADER + row, encoding="utf-8")
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
