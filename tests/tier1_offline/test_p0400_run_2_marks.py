"""Tier 1, 0.40.0 lane run-2: the steady job, its descriptor, its marks and its cost.

Every fixture is synthetic.
"""

from __future__ import annotations

from pyflightstream.run.records import mark_converged
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_mark_failed import _record, _workspace


def test_p0400_a_local_log_named_without_the_suffix_is_written_from_the_output(tmp_path):
    """P0400-LOCAL-LOG-NAME (PFS-2103.030): the declared log is found by _declared_logs.

    On an export_log = false machine with --local, the log is written from the
    solver's captured output; a case naming it ``solver_<point>.out`` (its
    LOG_OUTPUT) was not found by the ``_log.txt`` suffix, neither written nor
    excused.
    """
    from tests.tier1_offline.test_goal031_local_run_log import _file_route_point
    from tests.tier1_offline.test_run_wake_edge_count import LOG_AROUND

    printed = LOG_AROUND.format(line="16 trailing edges imported for boundary Wing")
    record = _file_route_point(
        tmp_path,
        prints=printed,
        outputs=["loads_{point}.txt", "solver_{point}.out"],
        variables={"LOG_OUTPUT": "2"},
    )
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert any(name.endswith(".out") for name in record.outputs), record.outputs


def test_p0400_steady_job_descriptor_names_the_sweep(tmp_path):
    """P0400-JOB-DESCRIPTOR (PFS-2094.039): a steady job's descriptor names the sweep.

    The first point's case was bound for the row's clock and processors, and
    its point name went into the descriptor as the job's.
    """
    from pathlib import Path

    from tests.tier1_offline.test_goal021_swept_row import _run, _submitting
    from tests.tier1_offline.test_matrix_run import HPC_PROFILE, RECIPES, _steady_sweep_matrix

    workspace, matrix = _steady_sweep_matrix(tmp_path)
    text = "\n".join(
        line.replace('"FTS{sim}"', '"FTS{sim}_{point}"')
        for line in HPC_PROFILE.splitlines()
        if not line.startswith(("walltime ", "ncpus "))
    )
    records = _run(
        workspace,
        matrix,
        _submitting(workspace, build="26.120", text=text + "\n"),
        name="warm",
        recipes=RECIPES,
        default_fs_version="26.120",
    )
    (job,) = records
    descriptor = Path(job.submission["descriptor"]).read_text(encoding="utf-8")
    assert f"FTS5001_{job.point_name}" in descriptor, descriptor


def test_p0400_mark_converged_judges_a_job_point_by_its_own_loads(tmp_path):
    """P0400-MARK-CONVERGED-OWN-LOADS (PFS-2103.029): a job point that collected nothing is refused.

    The check fell back to the job row's outputs, every other point's files,
    and accepted the point on the first point's loads export.
    """
    workspace = _workspace(tmp_path)
    sim = workspace.sim_dir("5001")
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "P5001-AL+000.txt").write_text("loads", encoding="utf-8")
    ran = [
        {"tag": "AL+000", "status": "CONVERGED", "outputs": ["P5001-AL+000.txt"]},
        {"tag": "AL+005", "status": "FAILED_INCOMPLETE_OUTPUT"},
    ]
    job = _record("5001", "camp/sim_5001/sweep", RunStatus.FAILED_INCOMPLETE_OUTPUT)
    workspace.append_record(
        job.model_copy(update={"points_ran": ran, "outputs": ["P5001-AL+000.txt"]})
    )
    entry = mark_converged(workspace.root, ["5001"], reason="read by hand", points=["AL+005"])
    assert entry["marked"] == []
    assert "loads export is not on disk" in entry["refused"]["camp/sim_5001/AL+005"]


def test_p0400_cost_table_procs_is_the_row_s_ncpus(tmp_path):
    """P0400-COST-PROCS (PFS-2094.038): the procs column reads the row's NCPUS first.

    The script's SET_MAX_PARALLEL_THREADS comes from row_ncpus, and the
    table showed the setup's max_threads beside it.
    """
    from pyflightstream.run import estimate_point_cost
    from tests.tier1_offline.test_plan_cost import saved_simulation, steady_case

    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    case = steady_case(geometry, max_threads=8)
    case = case.model_copy(update={"variables": {**case.variables, "NCPUS": "48"}})
    assert estimate_point_cost(case, run_id="run/a", recorded=[]).processors == 48


def test_p0400_cost_prices_a_steady_job_record_per_point(tmp_path):
    """P0400-COST-JOB (PFS-2094.015): a steady job's wall time is shared by its points.

    One record of ten points in 1000 s priced one steady point at 1000 s,
    ten times its share.
    """
    from pyflightstream.run import estimate_point_cost
    from tests.tier1_offline.test_plan_cost import recorded, saved_simulation, steady_case

    geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
    job = {**recorded("run/sweep", 1000.0), "points_ran": [{"tag": f"p{i}"} for i in range(10)]}
    cost = estimate_point_cost(steady_case(geometry), run_id="run/a", recorded=[job])
    assert cost.seconds == 100.0


def test_p0400_cost_offers_no_time_for_an_unsteady_point_of_unknown_steps(tmp_path):
    """P0400-COST-UNKNOWN-STEPS (PFS-2094.016): no step count, no expected time.

    The point was priced at one time step, the per-step rate shown as its
    expected time.
    """
    from pyflightstream.run import estimate_point_cost
    from tests.tier1_offline.test_plan_cost import recorded, rotor_case, saved_simulation

    rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
    case = rotor_case(rotor)
    variables = {k: v for k, v in case.variables.items() if k != "REVOLUTIONS"}
    case = case.model_copy(update={"variables": variables})
    history = [recorded("run/u1", 360.0, "unsteady_rotor")]
    cost = estimate_point_cost(case, run_id="run/b", recorded=history, steps_by_run={"run/u1": 36})
    assert cost.time_iterations is None
    assert cost.seconds is None
    assert "step count is unknown" in cost.basis
