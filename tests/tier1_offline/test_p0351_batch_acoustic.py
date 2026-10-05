"""FR-406: an acoustic row joins a grouped job (0.35.1, P0351-BATCH-ACOUSTIC).

Until 0.35.1 the grouped plan left an acoustic polar out ("its section folder
in one instance is not measured"). A point inside a job must leave what the
same point run alone leaves, and two things of an acoustic point are not its
own text once an earlier point ran in the same instance: the observers, model
objects that outlive ``REMOVE_INITIALIZATION`` (DESIGN-0350 arms A and D: the
model objects stay loaded), and the ``ACOUSTIC_SOURCES`` switch, which a later
point of a polar never restates because it sits before the restate anchor.
So every point after the job's first restates its acoustic setup just before
its ``SET_SOLVER_UNSTEADY``, after ``DELETE_ALL_ACOUSTIC_OBSERVERS``, and a
point without acoustics after one with them switches the sources off.

The acoustic outputs move with the point like every other output: the signals
export is a declared output and the section's ``STORAGE_PATH`` is a path
argument, both absolute in the point's own datapoint folder (FR-359); the run
writes each point's section note into its own folder, which collect lists.
Synthetic cases only; no solver runs.
"""

from __future__ import annotations

import warnings
from pathlib import PurePosixPath

import pytest

from pyflightstream.cases import acoustics
from pyflightstream.cases.workflows import WORKFLOW_KEY, build_script
from pyflightstream.cases.workflows._batch_script import (
    SOLVER_BLOCK,
    JobPolar,
    assemble_job,
    job_point,
)
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run._batch_plan import eligibility
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
from tests.support_helpers import grouped_plan_fixture as _plan_fixture
from tests.tier1_offline.test_p0350_batch_plan import _plan as _grouped_plan
from tests.tier1_offline.test_p0350_batch_run import (
    _matrix,
    _run,
    _submitting,
    _workspace,
)
from tests.tier1_offline.test_p0350_batch_script import relative_paths
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case

BUILD = "26.124"
ROOT = PurePosixPath("/ws/sims/batch/mtx_b1")
OBSERVERS = "MIC1 0.0 10.0 0.0, MIC2 0.0 -10.0 0.5"
TIME = "0.05 0.2 16"
SECTION = (
    "{PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 / AZIMUTH_OBSERVERS:4 / "
    "INNER_RADIUS:5.0 / OUTER_RADIUS:10.0}"
)
ACOUSTIC = {
    "ACOUSTIC_SOURCES": "ENABLE",
    "ACOUSTIC_OBSERVERS": OBSERVERS,
    "ACOUSTIC_OBSERVER_TIME": TIME,
    "ACOUSTIC_SECTION": SECTION,
}
#: The matrix cell form of the same keys, appended to a row's VAR_NAMES_VALUES.
CELL = "".join(f" / {key}: {value}" for key, value in ACOUSTIC.items())
#: The acoustic setup commands these cases emit (no observer file).
SETUP = (
    "ACOUSTIC_SOURCES",
    "CREATE_NEW_ACOUSTIC_OBSERVER",
    "SET_ACOUSTIC_OBSERVER_TIME",
)


def _point(case, sim: str, tag: str):
    """One job point of ``case``, its outputs declared as the run layer declares them."""
    stem = f"loads_{tag}"
    outputs = acoustics.with_acoustic_signals([f"{stem}.txt"], case, stem)
    case = case.model_copy(update={"sim_id": sim, "outputs": outputs})
    script = Script(BUILD)
    build_script(case, script)
    return job_point(
        case,
        run_id=f"mtx/sim_{sim}/DP-{tag}",
        text=script.render(),
        datapoint_dir=ROOT / f"sim_{sim}" / "datapoints" / f"DP-{tag}",
        version=BUILD,
    )


def _block(job, number: int) -> list[str]:
    """The lines of the job's ``number``-th point (0-based), as the job runs them."""
    block = job.blocks[number]
    return job.text.splitlines()[block.first_line - 1 : block.last_line]


def _heads(lines: list[str]) -> list[str]:
    return [line.split()[0] for line in lines if line.split()]


def _own_setup(point) -> list[str]:
    """The acoustic setup lines a point run alone states, in its own order."""
    return [
        line for line in point.text.splitlines() if line.split()[:1] and line.split()[0] in SETUP
    ]


def test_p0351_acoustic_fr406_an_acoustic_row_joins_a_grouped_job(tmp_path):
    """P0351-BATCH-ACOUSTIC (FR-406): the plan groups an acoustic polar instead of leaving it out.

    ``eligibility`` answers None for an unsteady case stating every acoustic key, and the
    grouped plan of a matrix whose two rotor polars state them puts both into its jobs with
    nothing left out. The steady merge also admits the same fixture's steady row.
    """
    workspace, matrix = _plan_fixture(tmp_path, walltimes=("1h", "1h"), sweep="0.0,2.0")
    text = matrix.read_text(encoding="utf-8").splitlines()
    matrix.write_text(
        "\n".join([*text[:2], *(row + CELL for row in text[2:])]) + "\n", encoding="utf-8"
    )
    plan = _grouped_plan(workspace, matrix, batch=1)
    assert plan.grouping.left_out == (), plan.grouping.left_out
    assert [job.sims for job in plan.grouping.jobs] == [("7001",), ("7002",)]
    assert [len(job.points) for job in plan.grouping.jobs] == [2, 2]
    case = unsteady_case(**ACOUSTIC)
    assert eligibility(case, workspace=workspace, version=BUILD) is None
    steady = case.model_copy(update={"variables": {**case.variables, WORKFLOW_KEY: "steady"}})
    assert eligibility(steady, workspace=workspace, version=BUILD) is None


def test_p0351_acoustic_polars_run_alone_in_their_jobs(tmp_path):
    """P0351-BATCH-ACOUSTIC (FR-406): --batch 1 keeps each acoustic polar alone, points together."""
    workspace, matrix = _plan_fixture(tmp_path, walltimes=("1h", "1h", "1h"), sweep="0.0,2.0")
    header, rule, *rows = matrix.read_text(encoding="utf-8").splitlines()
    matrix.write_text(
        "\n".join([header, rule, rows[0] + CELL, rows[1], rows[2] + CELL]) + "\n",
        encoding="utf-8",
    )
    plan = _grouped_plan(workspace, matrix, batch=1)
    assert plan.grouping.left_out == ()
    assert [job.sims for job in plan.grouping.jobs] == [("7001",), ("7002",), ("7003",)]
    assert [len(job.points) for job in plan.grouping.jobs] == [2, 2, 2]


def test_p0351_acoustic_fr406_each_point_restates_its_own_setup():
    """P0351-BATCH-ACOUSTIC (FR-406): each later point states its observers once, sources first.

    The job holds a rotor polar of three points (the second restated from ``SET_SOLVER_UNSTEADY``,
    the third from ``SET_MOTION_ROTOR_RPM``, whose restated text already carries the setup), a
    second acoustic polar, then a polar without acoustics. The first point is its own text. Every
    later acoustic point has ``DELETE_ALL_ACOUSTIC_OBSERVERS`` then exactly its own setup lines
    right before its solver block, so each observer is created once per point and its sources are
    switched before its ``INITIALIZE_SOLVER``; the point without acoustics switches them off. Its
    signals export and its section folder are absolute in its own folder.
    """
    first = _point(rotor_case(**ACOUSTIC), "7101", "a")
    by_step = _point(rotor_case(**ACOUSTIC, TIME_ITERATIONS="760"), "7101", "b")
    by_speed = _point(rotor_case(**ACOUSTIC, RPM="1300"), "7101", "c")
    second = _point(rotor_case(**ACOUSTIC), "7102", "a")
    plain = _point(rotor_case(), "7103", "a")
    job = assemble_job(
        [
            JobPolar("7101", (first, by_step, by_speed)),
            JobPolar("7102", (second,)),
            JobPolar("7103", (plain,)),
        ],
        kind="batch",
        version=BUILD,
        job_log=None,
        job_dir=ROOT,
    )
    assert [(b.transition, b.anchor) for b in job.blocks] == [
        ("start", None),
        ("reinit", "SET_SOLVER_UNSTEADY"),
        ("reinit", "SET_MOTION_ROTOR_RPM"),
        ("refresh", None),
        ("refresh", None),
    ]
    assert "DELETE_ALL_ACOUSTIC_OBSERVERS" not in _heads(_block(job, 0))
    for number, point in ((1, by_step), (2, by_speed), (3, second)):
        lines = [line for line in _block(job, number) if line.strip()]
        heads = _heads(lines)
        setup = _own_setup(point)
        at = heads.index("DELETE_ALL_ACOUSTIC_OBSERVERS")
        assert heads.count("DELETE_ALL_ACOUSTIC_OBSERVERS") == 1, point.run_id
        assert lines[at + 1 : at + 1 + len(setup)] == setup, point.run_id
        assert heads[at + 1 + len(setup)] == SOLVER_BLOCK, point.run_id
        assert heads.count("CREATE_NEW_ACOUSTIC_OBSERVER") == 2, point.run_id
        assert heads.index("ACOUSTIC_SOURCES") < heads.index("INITIALIZE_SOLVER"), point.run_id
        folder = str(point.datapoint_dir)
        signals = lines[heads.index("EXPORT_ACOUSTIC_SIGNALS") + 1]
        storage = next(line for line in lines if line.startswith("STORAGE_PATH "))
        assert signals.startswith(folder) and storage.split(" ", 1)[1].startswith(folder)
    off = [line for line in _block(job, 4) if line.strip()]
    assert off[_heads(off).index("DELETE_ALL_ACOUSTIC_OBSERVERS") + 1] == "ACOUSTIC_SOURCES DISABLE"
    assert "CREATE_NEW_ACOUSTIC_OBSERVER" not in _heads(off)
    assert not relative_paths(job.text), relative_paths(job.text)


@pytest.mark.requirement("FR-359")
def test_p0351_acoustic_fr406_a_grouped_run_places_each_section_in_its_point(tmp_path):
    """P0351-BATCH-ACOUSTIC (FR-406): run --batch writes each point's section note in its folder.

    Two rotor polars stating every acoustic key, run in separate jobs through the real submitting
    executor (submit off): every point is SUBMITTED, every point's datapoint folder under the batch
    holds its own section folder with the run's note, and the job script names each of those
    folders and each point's signals export once, with the observers deleted before each later
    point's setup.
    """
    workspace, profile, _ = _workspace(tmp_path)
    matrix = _matrix(tmp_path)
    rows = matrix.read_text(encoding="utf-8").splitlines()
    matrix.write_text(
        "\n".join([*rows[:2], *(row + CELL for row in rows[2:])]) + "\n", encoding="utf-8"
    )
    _grouped_plan(workspace, matrix, batch=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        records = _run(workspace, matrix, executor=_submitting(profile, submit=False))
    assert [r.status for r in records] == [RunStatus.SUBMITTED] * 3
    batch_dir = workspace.root / "sims" / "batch"
    scripts = sorted(batch_dir.glob("*/BATCH-*.txt"))
    assert [path.name for path in scripts] == ["BATCH-7001-7001.txt", "BATCH-7003-7003.txt"]
    script = "\n".join(path.read_text(encoding="utf-8") for path in scripts)
    notes = sorted(batch_dir.rglob(acoustics.ACOUSTIC_SECTION_NOTE))
    assert len(notes) == 3, notes
    for note in notes:
        folder = note.parent
        assert folder.name.endswith(acoustics.ACOUSTIC_SECTION_SUFFIX)
        assert script.count(f"STORAGE_PATH {folder}") == 1, folder
        signals = folder.parent / folder.name.replace(
            acoustics.ACOUSTIC_SECTION_SUFFIX, acoustics.ACOUSTIC_SIGNALS_SUFFIX
        )
        assert script.count(str(signals)) == 1, signals
    assert script.count("DELETE_ALL_ACOUSTIC_OBSERVERS") == 1
    assert not relative_paths(script), relative_paths(script)
