"""FR-405: a polar whose setup states ``unsteady_solver_actions`` joins a grouped job (0.35.1).

Until 0.35.0 the grouped plan left such a polar out ("a user action cannot be withdrawn
between polars"). The measurements behind the rule of 0.35.1 (RPT-141, Test 2): an action
registered on the instance survives ``REMOVE_INITIALIZATION`` and ``NEW_SIMULATION``, a
second registration runs it twice a step, and the command database documents no command
that withdraws one (``SET_NEW_UNSTEADY_SOLVER_ACTION`` is the only action command of
``commands/unsteady_solver.yaml``). So a job holds polars stating ONE set of user actions,
registered once, before the package's own actions, exactly as a point run alone registers
them (FR-319), and its lines are kept as the setup wrote them.

Marker: P0351-BATCH-USER-ACTIONS (FR-405). Synthetic data only; no solver runs.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path, PurePosixPath

import pytest

from pyflightstream.cases import CampaignConfigError, SolverSettings
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.cases.workflows._batch_script import (
    JobPolar,
    assemble_job,
    job_point,
)
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run._batch_plan import eligibility, plan_grouped_matrix
from pyflightstream.run._batch_split import PolarUnit, split_polars
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import Script
from tests.tier1_offline.test_matrix_run import converged
from tests.tier1_offline.test_p0350_batch_plan import _fixture
from tests.tier1_offline.test_p0350_batch_run import (
    MATRIX,
    NAMED_FIELDS,
    _matrix,
    _neutral,
    _normalised,
    _plan,
    _run,
    _submitting,
    _workspace,
)
from tests.tier1_offline.test_workflows import rotor_case

BUILD = "26.124"
ROOT = PurePosixPath("/ws/sims/batch/mtx_b1")
ACTION_HEAD = "SET_NEW_UNSTEADY_SOLVER_ACTION"
#: Two user actions: a shell line with relative words, and a script by an absolute file.
ACTIONS = (
    {"type": "COMMAND_LINE", "name": "user_marker", "filename": 'python marker.py --out "a b.txt"'},
    {"type": "SCRIPT", "name": "user_probe", "filename": "/abs/probe actions/probe.txt"},
)
#: The registration order of a point run alone: the setup's first, then the package's.
ALONE_ORDER = [
    "user_marker",
    "user_probe",
    "pfs_unsteady_counter",
    "pfs_walltime_clock",
    "pfs_walltime_stop",
]
#: The setup body a matrix row names to state the two actions.
ACTIONS_TOML = """
[[unsteady_solver_actions]]
type = "COMMAND_LINE"
name = "user_marker"
filename = "python marker.py"
"""


def _case(sim: str, actions=ACTIONS):
    """A rotor case with a wall clock and ordinary outputs, its setup stating ``actions``."""
    case = rotor_case(WALLTIME="4m")
    return case.model_copy(
        update={
            "sim_id": sim,
            "outputs": ["point.txt", "point.fsm"],
            "solver": SolverSettings(unsteady_solver_actions=list(actions) or None),
        }
    )


def _point(sim: str, folder: str, actions=ACTIONS):
    """One job point of a polar, its script written as the point run alone writes it."""
    case = _case(sim, actions)
    script = Script(BUILD)
    build_script(case, script)
    return job_point(
        case,
        run_id=f"mtx/sim_{sim}/{folder}",
        text=script.render(),
        datapoint_dir=ROOT / f"sim_{sim}" / "datapoints" / folder,
        version=BUILD,
    )


def _registrations(text: str) -> list[tuple[int, str, str]]:
    """Each registration of a text: its 1-based line, its name and the line after it."""
    lines = text.splitlines()
    return [
        (number, line.split()[2], lines[number])
        for number, line in enumerate(lines, 1)
        if line.startswith(ACTION_HEAD)
    ]


def test_p0351_user_actions_fr405_registered_once_in_the_alone_order_and_as_written():
    """P0351-BATCH-USER-ACTIONS (FR-405): the job registers the setup's actions once, as alone.

    A batch of two polars stating the same two actions: one polar of two points (a
    re-initialization) and one of one point (a refresh). The job's registrations are the
    alone script's, name for name and in its order (the setup's before the package's); each
    user action's argument line is the alone line byte for byte (the shell line keeps its
    relative words); and nothing is registered after the first point, so no action runs
    twice a step. On 0.35.0 the splice dropped the user lines and kept only the package's.
    """
    first, second = _point("7101", "DP-a00"), _point("7101", "DP-a20")
    other = _point("7102", "DP-a00")
    alone = _registrations(first.text)
    assert [name for _, name, _ in alone] == ALONE_ORDER
    job = assemble_job(
        [JobPolar("7101", (first, second)), JobPolar("7102", (other,))],
        kind="batch",
        version=BUILD,
        job_log=None,
        job_dir=ROOT,
    )
    assert [block.transition for block in job.blocks] == ["start", "reinit", "refresh"]
    spliced = _registrations(job.text)
    assert [name for _, name, _ in spliced] == ALONE_ORDER
    by_name = {name: argument for _, name, argument in alone}
    for _, name, argument in spliced:
        if name.startswith("user_"):
            assert argument == by_name[name]
    assert max(number for number, _, _ in spliced) <= job.blocks[0].last_line
    assert job.text.count('python marker.py --out "a b.txt"') == 1


@pytest.mark.parametrize("kind", ["batch", "polar_sweep"])
def test_p0351_user_actions_fr405_a_job_of_one_set_only(kind):
    """P0351-BATCH-USER-ACTIONS (FR-405): polars stating different actions never share a job.

    The assembler refuses a job mixing a polar with actions and one without, naming FR-405,
    because an action survives NEW_SIMULATION and cannot be withdrawn. Control: the same
    two polars both without actions assemble, and register no user action.
    """
    stated, bare = _point("7101", "DP-a00"), _point("7102", "DP-a00", actions=())
    with pytest.raises(CampaignConfigError, match="FR-405"):
        assemble_job(
            [JobPolar("7101", (stated,)), JobPolar("7102", (bare,))],
            kind=kind,
            version=BUILD,
            job_log=None,
            job_dir=ROOT,
        )
    control = assemble_job(
        [JobPolar("7102", (bare,)), JobPolar("7103", (_point("7103", "DP-a00", actions=()),))],
        kind=kind,
        version=BUILD,
        job_log=None,
        job_dir=ROOT,
    )
    assert [name for _, name, _ in _registrations(control.text)] == ALONE_ORDER[2:]


def _unit(sim: str, order: int, actions: tuple[tuple[str, str, str], ...]) -> PolarUnit:
    return PolarUnit(
        sim_id=sim,
        order=order,
        ncpus=8,
        fs_build=BUILD,
        run_ids=(f"m/sim_{sim}/p0",),
        point_seconds=(600.0,),
        walltime_cell_s=None,
        walltime_cell_text=None,
        best=True,
        margin_s=60.0,
        actions=actions,
    )


def test_p0351_user_actions_fr405_the_split_groups_by_action_set():
    """P0351-BATCH-USER-ACTIONS (FR-405): the split keeps one action set per job.

    Four polars in matrix order: none, set A, set A, set B. ``--batch 1`` plans one job per
    set, the two polars of set A together, and warns that the groups outnumber the jobs.
    """
    one = (("COMMAND_LINE", "a", "python a.py"),)
    two = (("COMMAND_LINE", "b", "python b.py"),)
    units = [
        _unit("2001", 1, ()),
        _unit("2002", 2, one),
        _unit("2003", 3, one),
        _unit("2004", 4, two),
    ]
    jobs, notes = split_polars(units, 1)
    assert [tuple(u.sim_id for u in job.units) for job in jobs] == [
        ("2001",),
        ("2002", "2003"),
        ("2004",),
    ]
    assert any("unsteady_solver_actions" in note and "one job per group" in note for note in notes)


def test_p0351_user_actions_fr405_eligibility_takes_them_and_names_a_relative_script():
    """P0351-BATCH-USER-ACTIONS (FR-405): a polar stating actions is eligible.

    The exception is a SCRIPT action named by a relative file, which a point run alone reads
    in its own datapoint folder (its working directory) and one registration in one instance
    can name only once; it is left out by name. Control: the same row with no action.
    """
    assert eligibility(_case("7101"), workspace=None, version=BUILD) is None
    relative = ({"type": "SCRIPT", "name": "user_probe", "filename": "probe.txt"},)
    reason = str(eligibility(_case("7101", relative), workspace=None, version=BUILD))
    assert "SCRIPT" in reason and "relative file" in reason
    assert eligibility(_case("7101", ()), workspace=None, version=BUILD) is None


def test_p0351_user_actions_fr405_the_plan_groups_them_and_warns_of_the_folder(tmp_path):
    """P0351-BATCH-USER-ACTIONS (FR-405): ``plan --batch 1`` groups the polars by action set.

    Three polars: 7001 states no action, 7002 and 7003 name a setup stating one. Nothing is
    left out; 7001 has its job and 7002 with 7003 share the other; the receipt warns that the
    actions run from the job's folder. On 0.35.0 the two were left out.
    """
    workspace, matrix = _fixture(tmp_path, walltimes=("1h", "1h", "1h"), sweep="0.0")
    body = (workspace.inputs_dir / "setups" / "s002.toml").read_text(encoding="utf-8")
    (workspace.inputs_dir / "setups" / "s004.toml").write_text(body + ACTIONS_TOML, "utf-8")
    header, rule, *rows = matrix.read_text(encoding="utf-8").splitlines()
    rows = [row if row.startswith("7001") else row.replace("| s002 ", "| s004 ") for row in rows]
    assert sum("| s004 " in row for row in rows) == 2
    matrix.write_text("\n".join([header, rule, *rows]) + "\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_grouped_matrix(
            matrix,
            workspace,
            mode="batch",
            batch=1,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
        )
    assert plan.grouping.left_out == ()
    assert [job.sims for job in plan.grouping.jobs] == [("7001",), ("7002", "7003")]
    named = [note for note in plan.grouping.warnings if "user_marker" in note]
    assert len(named) == 1 and "POL 7002, 7003" in named[0] and "job's folder" in named[0]


def _with_actions(workspace) -> None:
    """Make the setup both polars of the run fixture name state the user action."""
    setup = workspace.inputs_dir / "setups" / "s002.toml"
    setup.write_text(setup.read_text(encoding="utf-8") + ACTIONS_TOML, encoding="utf-8")


def _job_text(root: Path, mode: str) -> str:
    """The one job script a grouped run of the fixture wrote."""
    name = "BATCH-7001-7003.txt" if mode == "batch" else "FULL-POLAR.txt"
    folder = root / "sims" / ("batch" if mode == "batch" else "sim_7001")
    (path,) = folder.rglob(name)
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("mode", ["batch", "polar_sweep"])
def test_p0351_user_actions_fr405_records_equal_the_points_run_alone(tmp_path, mode):
    """P0351-BATCH-USER-ACTIONS (FR-405): each record is the point run alone, bar the named fields.

    Both polars of the run fixture name a setup stating one COMMAND_LINE action. The grouped
    records equal the records of the same points run alone except the fields FR-366 names,
    each point's own script is the alone script byte for byte, and the job registers the
    action once, its line as the setup wrote it, before the package's counter.
    """
    alone_ws, alone_profile, _ = _workspace(tmp_path / "alone")
    _with_actions(alone_ws)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        alone = run_matrix(
            _matrix(tmp_path / "alone"),
            alone_ws,
            name=MATRIX,
            recipes={},
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=_submitting(alone_profile, submit=False),
        )
    workspace, profile, _ = _workspace(tmp_path / "grouped")
    _with_actions(workspace)
    matrix = _matrix(tmp_path / "grouped")
    batch = 1 if mode == "batch" else None
    _plan(workspace, matrix, mode=mode, batch=batch)
    grouped = _run(
        workspace, matrix, mode=mode, batch=batch, executor=_submitting(profile, submit=False)
    )
    one, other = _normalised(alone, alone_ws.root), _normalised(grouped, workspace.root)
    assert [r["run_id"] for r in one] == [r["run_id"] for r in other] and len(one) == 3
    named = set(NAMED_FIELDS) | {"script_sha256"}
    home = f"sims/batch/{MATRIX}_b1/" if mode == "batch" else "sims/"
    for a, b, record in zip(one, other, grouped, strict=True):
        assert sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k) and k not in named) == []
        sim = f"sim_{record.sim_id}"
        mine = (workspace.root / home / sim / record.script_path).read_text(encoding="utf-8")
        theirs = (alone_ws.root / "sims" / sim / record.script_path).read_text(encoding="utf-8")
        assert "python marker.py" in theirs
        assert _neutral(mine, workspace.root).replace(home, "sims/") == _neutral(
            theirs, alone_ws.root
        )
    names = [name for _, name, _ in _registrations(_job_text(workspace.root, mode))]
    assert names[:2] == ["user_marker", "pfs_unsteady_counter"]
    assert names.count("user_marker") == 1
    assert "\npython marker.py\n" in _job_text(workspace.root, mode)
    assert json.dumps(other).count("user_marker") == json.dumps(one).count("user_marker")
