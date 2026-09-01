"""Tier 1: the campaign loop, end-to-end dry run without FlightStream.

A StubSolver replaces the FlightStream argv with a Python one-liner
that mimics the solver behavior needed by each scenario (write the
declared outputs, write the hidden-mode error log, or fail), so the
whole path campaign.toml model, recipe, builder, workspace, executor,
and manifest is exercised for real.
"""

import hashlib
import inspect
import json
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

import pyflightstream.run as run_module
from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.results import (
    DATA_ORIGIN_CODES,
    REDUCTION_CODES,
    REDUCTION_WINDOW_CODES,
)
from pyflightstream.run import (
    Assessment,
    CampaignErrors,
    ExecutorConfigurationError,
    LoadsAssessor,
    LocalExecutor,
    PlanStatus,
    SolverBuild,
    _recipe_digest,
    package_vcs_state,
    plan_campaign,
    reconstruct,
    run_campaign,
)
from pyflightstream.script import helpers
from pyflightstream.versions import resolve as version_resolve
from pyflightstream.workspace import (
    MANIFEST_SCHEMA,
    CampaignWorkspace,
    NamingTemplate,
    RunRecord,
    RunStatus,
    WorkspaceError,
)

FIXTURES = Path(__file__).parent / "fixtures"


class StubSolver(LocalExecutor):
    def __init__(self, code: str):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.code = code

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", self.code, str(script_path)]


# The stub writes the file the script asks the solver to export, so a
# per-point output name (loads_{point}.txt) is honored like the solver
# would honor it.
WRITES_LOADS = (
    "import pathlib, sys; "
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
    "[pathlib.Path(lines[i + 1]).write_text('LOADS') "
    "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']"
)
WRITES_NOTHING = "pass"
CRASHES_WITH_LOG = (
    "import pathlib, sys; "
    "pathlib.Path('FlightStreamLog.txt').write_text('Unknown command SPOILER'); "
    "sys.exit(2)"
)


def steady_recipe(case, script):
    script.emit("OPEN", case.geometry)
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


def broken_recipe(case, script):
    script.emit("SOLVER_SET_AOA", "not-a-number")


def converged(case, execution, sim_dir):
    return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)


def diverged(case, execution, sim_dir):
    return Assessment(status=RunStatus.FAILED_DIVERGED, error="residual grew monotonically")


def make_campaign(tmp_path, *, recipe="steady", alphas=(0.0, 2.0), outputs=("loads_{point}.txt",)):
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=list(alphas)),
        recipe=recipe,
        outputs=list(outputs),
    )
    return Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[case])


def test_dry_run_records_every_point_end_to_end(tmp_path):
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert [record.run_id for record in records] == [
        "camp/sim_9001/a+00.0",
        "camp/sim_9001/a+02.0",
    ]
    assert all(record.status is RunStatus.CONVERGED for record in records)
    assert all(record.fs_version_requested == "26.120" for record in records)
    assert records[0].iterations == 120
    assert records[0].outputs == ["raw/loads_a+00.0.txt"]
    assert records[1].outputs == ["raw/loads_a+02.0.txt"]  # both points survive
    assert "wing.fsm" in records[0].inputs_sha256
    assert not records[0].raw_flag
    # The solver-setup snapshot of the built script rode into the manifest.
    setup = records[0].solver_setup
    assert setup is not None
    assert setup["flags"]["SOLVER_SET_AOA"]["provenance"] == "explicit"
    assert setup["flags"]["SOLVER_MINIMUM_CP"] == {
        "command": "SOLVER_MINIMUM_CP",
        "family": "advanced_settings",
        "provenance": "default",
        "value": -100,
        "emitted": True,
        "evidence": setup["flags"]["SOLVER_MINIMUM_CP"]["evidence"],
    }
    assert "SRC-003 p.221" in setup["flags"]["SOLVER_MINIMUM_CP"]["evidence"]
    reloaded = workspace.read_manifest()
    assert reloaded[0].solver_setup == setup
    sim = tmp_path / "camp" / "sims" / "sim_9001"
    assert (sim / "scripts" / "a+02.0.txt").is_file()
    assert "SOLVER_SET_AOA 2.0" in (sim / "scripts" / "a+02.0.txt").read_text(encoding="utf-8")
    assert "inputs" in (sim / "scripts" / "a+00.0.txt").read_text(encoding="utf-8")
    assert len(workspace.read_manifest()) == 2


def test_recipe_failure_lands_as_failed_script(tmp_path):
    campaign = make_campaign(tmp_path, recipe="broken", alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_SCRIPT") as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"broken": broken_recipe},
        )
    assert caught.value.failures[0].error.startswith("CommandArgumentError")
    assert workspace.read_manifest()[0].status is RunStatus.FAILED_SCRIPT


def test_solver_failure_lands_as_failed_execution_with_the_log(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_EXECUTION"):
        run_campaign(
            campaign,
            StubSolver(CRASHES_WITH_LOG),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.FAILED_EXECUTION
    assert "Unknown command SPOILER" in record.error


def test_missing_declared_output_lands_as_incomplete(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_INCOMPLETE_OUTPUT"):
        run_campaign(
            campaign,
            StubSolver(WRITES_NOTHING),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    assert workspace.read_manifest()[0].status is RunStatus.FAILED_INCOMPLETE_OUTPUT


def test_unresolvable_recipe_fails_every_point_loudly(tmp_path):
    campaign = make_campaign(tmp_path, recipe="no.such.module:build")
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="2 campaign point"):
        run_campaign(campaign, StubSolver(WRITES_LOADS), workspace, assess=converged)
    records = workspace.read_manifest()
    assert len(records) == 2
    assert all(record.status is RunStatus.FAILED_SCRIPT for record in records)
    assert "cannot be imported" in records[0].error


def copies_fixture_as(fixture: str, target: str) -> str:
    source = FIXTURES / fixture
    return (
        f"import pathlib; pathlib.Path({target!r})"
        f".write_text(pathlib.Path(r'{source}').read_text())"
    )


def test_loads_assessor_closes_the_convergence_judgment_end_to_end(tmp_path):
    # No loads file is named: the assessor reads the case's first
    # declared output as the loop rendered it for this point, which is
    # the only form that works for a sweep (the name carries the point).
    #
    # The requested alpha is 2.0 because the steady fixture PRINTS 2.000,
    # and REV010-001 is exactly the rule that those two must agree. This
    # test requested 0.0 against that same fixture until 2026-08-03 and
    # asserted CONVERGED, so the defect the review reproduced with a
    # custom solver was already sitting in this repository's own
    # end-to-end test: a converged result for one flight condition
    # accepted as the evidence of another.
    campaign = make_campaign(tmp_path, alphas=(2.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(copies_fixture_as("loads_steady_26.120.txt", "loads_a+02.0.txt")),
        workspace,
        assess=LoadsAssessor(requested_version=campaign.fs_version),
        recipes={"steady": steady_recipe},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED
    assert record.iterations == 312
    assert record.fs_version_reported == "26.1"
    assert record.fs_build == "7012026"
    # The binding is persisted, not just acted on: alpha and velocity were
    # compared, both agreed, and the manifest says so.
    bound = {entry["axis"]: entry for entry in record.conditions}
    assert bound["alpha"]["requested"] == 2.0
    assert bound["alpha"]["reported"] == 2.0
    assert bound["velocity"]["reported"] == 30.0
    assert all(entry["within"] for entry in record.conditions)


def make_raw(tmp_path, fixture: str, name: str = "loads.txt", text: str | None = None):
    raw = tmp_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    content = text if text is not None else (FIXTURES / fixture).read_text(encoding="utf-8")
    (raw / name).write_text(content, encoding="utf-8")
    return tmp_path


def test_loads_assessor_judgments_per_evidence(tmp_path):
    steady = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    assessor = LoadsAssessor("loads.txt")

    converged = assessor(None, None, make_raw(tmp_path / "a", "loads_steady_26.120.txt"))
    assert converged.status is RunStatus.CONVERGED

    limited = assessor(
        None,
        None,
        make_raw(tmp_path / "b", "", text=steady.replace("312", "500")),
    )
    assert limited.status is RunStatus.COMPLETED_MAX_ITER

    diverged = assessor(
        None,
        None,
        make_raw(tmp_path / "c", "", text=steady.replace("+0.0089000,", "NaN,")),
    )
    assert diverged.status is RunStatus.FAILED_DIVERGED
    assert "CDi" in diverged.error

    truncated = assessor(None, None, make_raw(tmp_path / "d", "loads_truncated_26.120.txt"))
    assert truncated.status is RunStatus.FAILED_INCOMPLETE_OUTPUT

    unsteady_no_log = assessor(None, None, make_raw(tmp_path / "e", "loads_unsteady_26.120.txt"))
    assert unsteady_no_log.status is RunStatus.COMPLETED_MAX_ITER


def test_loads_assessor_uses_the_log_residuals_when_declared(tmp_path):
    sim_dir = make_raw(tmp_path, "loads_unsteady_26.120.txt")
    make_raw(tmp_path, "log_residuals_26.120.txt", name="log.txt")
    assessment = LoadsAssessor("loads.txt", log_file="log.txt")(None, None, sim_dir)
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.iterations == 1575
    assert assessment.residual == pytest.approx(9.6e-8)


def test_diverged_assessment_is_a_failure(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="FAILED_DIVERGED"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=diverged,
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert record.error == "residual grew monotonically"


# --- resume: growing a sweep and re-running into the same root --------------


def test_resume_skips_recorded_points_and_runs_only_the_new_ones(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        make_campaign(tmp_path, alphas=(0.0, 2.0)),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    grown = make_campaign(tmp_path, alphas=(0.0, 2.0, 4.0))
    records = run_campaign(
        grown,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        resume=True,
    )
    assert [record.run_id for record in records] == ["camp/sim_9001/a+04.0"]
    assert len(workspace.read_manifest()) == 3


def test_rerun_without_resume_raises_before_executing_anything(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    with pytest.raises(WorkspaceError, match="resume=True"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    assert len(workspace.read_manifest()) == 1  # nothing re-recorded


def test_resume_honors_a_synthetic_manifest_record(tmp_path):
    # The manifest is the identity authority: a record appended outside
    # the loop (for example a run migrated from another machine) is
    # enough for resume to consider the point done.
    campaign = make_campaign(tmp_path, alphas=(0.0, 2.0))
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_9001/a+00.0",
            sim_id="9001",
            point={"alpha": 0.0},
            fs_version_requested="26.120",
            package_version="0.0.0-synthetic",
            script_sha256="0" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
        )
    )
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        resume=True,
    )
    assert [record.run_id for record in records] == ["camp/sim_9001/a+02.0"]


# --- naming template wiring: output names only, identity untouched ----------


def outputs_recipe(case, script):
    script.emit("OPEN", case.geometry)
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script, vorticity_drag_boundaries="all", aoa=case.point["alpha"], velocity=case.velocity
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


def test_naming_template_names_scripts_and_rendered_outputs(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(2.0,), outputs=("loads_{point}.txt",))
    workspace = CampaignWorkspace(
        tmp_path / "camp",
        naming=NamingTemplate(point_name="{campaign}_{sim}_a{alpha}"),
    )
    writes_rendered = "import pathlib; pathlib.Path('loads_a+02.0.txt').write_text('LOADS')"
    records = run_campaign(
        campaign,
        StubSolver(writes_rendered),
        workspace,
        assess=converged,
        recipes={"steady": outputs_recipe},
    )
    record = records[0]
    # Identity is untouched by the template: same run_id scheme as ever.
    assert record.run_id == "camp/sim_9001/a+02.0"
    assert record.outputs == ["raw/loads_a+02.0.txt"]
    sim = tmp_path / "camp" / "sims" / "sim_9001"
    script_text = (sim / "scripts" / "camp_9001_a2.txt").read_text(encoding="utf-8")
    assert "loads_a+02.0.txt" in script_text  # the recipe saw the rendered name
    assert (sim / "raw" / "loads_a+02.0.txt").is_file()


# --- plan_campaign: pre-flight without execution ----------------------------


def test_plan_catches_a_broken_recipe_before_any_execution(tmp_path):
    campaign = make_campaign(tmp_path, recipe="broken")
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"broken": broken_recipe})
    assert [entry.status for entry in plan.points] == [PlanStatus.BLOCKED, PlanStatus.BLOCKED]
    assert "CommandArgumentError" in plan.points[0].error
    # Nothing executed, nothing recorded, no script written.
    assert workspace.read_manifest() == []
    scripts = tmp_path / "camp" / "sims" / "sim_9001" / "scripts"
    assert list(scripts.iterdir()) == []
    assert "2 blocked" in plan.summary()


def test_plan_catches_a_missing_geometry_before_any_execution(tmp_path):
    campaign = make_campaign(tmp_path)
    campaign.sims[0].geometry = str(tmp_path / "never_created.fsm")
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    assert all(entry.status is PlanStatus.BLOCKED for entry in plan.points)
    assert "does not exist" in plan.points[0].error
    assert workspace.read_manifest() == []


def test_plan_marks_ready_and_already_recorded_points(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        make_campaign(tmp_path, alphas=(0.0,)),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    grown = make_campaign(tmp_path, alphas=(0.0, 2.0))
    plan = plan_campaign(grown, workspace, recipes={"steady": steady_recipe})
    by_run_id = {entry.run_id: entry for entry in plan.points}
    assert by_run_id["camp/sim_9001/a+00.0"].status is PlanStatus.ALREADY_RECORDED
    assert by_run_id["camp/sim_9001/a+02.0"].status is PlanStatus.READY
    assert by_run_id["camp/sim_9001/a+02.0"].script_name == "a+02.0.txt"
    # The plan summary lands next to the manifest, as a report only.
    assert plan.plan_file == workspace.root / "plan.json"
    payload = json.loads(plan.plan_file.read_text(encoding="utf-8"))
    assert payload["campaign"] == "camp"
    assert {point["status"] for point in payload["points"]} == {"READY", "ALREADY_RECORDED"}


# --- per-point output names: no point may overwrite another's evidence ------


@pytest.mark.parametrize(
    ("outputs", "blocked"),
    [
        (("loads.txt",), True),  # constant: both points write the same file
        (("loads_{point}.txt",), False),
        (("loads_{alpha}.txt",), False),  # any template that distinguishes them
        (("loads_{mach}.txt",), True),  # renders per case, not per point
        (("loads_{point}.txt", "log.txt"), True),  # one colliding name is enough
    ],
)
def test_output_names_that_two_points_would_share_block_the_case(tmp_path, outputs, blocked):
    campaign = make_campaign(tmp_path, alphas=(0.0, 2.0), outputs=outputs)
    campaign.sims[0].mach = 0.2
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    statuses = {point.status for point in plan.points}
    if blocked:
        assert statuses == {PlanStatus.BLOCKED}
        assert "overwrite the first" in plan.points[0].error
    else:
        assert PlanStatus.BLOCKED not in statuses


def test_a_single_point_case_may_name_its_output_constantly(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,), outputs=("loads.txt",))
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    assert [point.status for point in plan.points] == [PlanStatus.READY]


@pytest.mark.parametrize(
    ("alphas", "outputs", "blocked"),
    [
        # The three inputs PLN-20260802-1904 measured passing the plan and
        # dying at collection. Each cost a licensed solver seat to learn a
        # fact the library already had.
        ((0.0,), ("loads.txt", "loads.txt"), True),
        ((0.0,), ("a/loads.txt", "b/loads.txt"), True),
        ((0.0, 2.0), ("a/loads.txt", "b/loads.txt"), True),
        # Controls, so the widening is not just "refuse more". A
        # directory part is legitimate; it simply does not make two names
        # differ, because collection drops it.
        ((0.0,), ("out/loads.txt", "log.txt"), False),
        ((0.0, 2.0), ("out/loads_{point}.txt", "log_{point}.txt"), False),
    ],
)
def test_a_collision_knowable_at_plan_time_is_refused_there(tmp_path, alphas, outputs, blocked):
    """PLN-20260802-1904: the plan and the collection now key the same way.

    ``collect_outputs`` refuses duplicates within one produced set AND a
    name already in ``raw/``, both on the BASE name. The plan-time check
    anticipated only the second, and on the DECLARED string. So a
    collision fully knowable before anything ran was reported only after
    the solver had run, which contradicts two published promises: the
    case model says such a case is blocked before it runs, and the
    changelog says every collision is refused before anything moves.
    """
    campaign = make_campaign(tmp_path, alphas=alphas, outputs=outputs)
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    statuses = {point.status for point in plan.points}
    if blocked:
        assert statuses == {PlanStatus.BLOCKED}
        assert "overwrite the first" in plan.points[0].error
    else:
        assert PlanStatus.BLOCKED not in statuses


@pytest.mark.parametrize(
    ("alphas", "outputs"),
    [
        ((0.0,), ("loads.txt", "loads.txt")),
        ((0.0,), ("a/loads.txt", "b/loads.txt")),
        ((0.0, 2.0), ("loads.txt",)),
    ],
)
def test_the_run_path_refuses_the_collision_without_starting_the_solver(tmp_path, alphas, outputs):
    """The half the plan-time test cannot reach, and the half that costs money.

    `_output_collision` has TWO call sites: `_plan_case_error`, which
    `plan_campaign` reaches, and `_prepare_case`, which `run_campaign`
    reaches. Every earlier test went through the first, so the QA pass
    disabled the SECOND and the whole suite stayed byte-identically
    green. A user calling `run_campaign` directly, which the README
    teaches and `run_matrix` does, would have gone back to learning
    about the collision at collection time, after the solver had run.
    That is the licensed seat this fix exists to save, and nothing was
    watching the path that spends it.

    The load-bearing assertion is that no script OF THIS CAMPAIGN was
    executed. Asserting only that the run failed would pass on a
    campaign that ran the solver and then refused, which is the defect
    rather than the fix.

    It is scoped to the workspace rather than written as
    ``started == []`` because the solver-identity pre-flight legitimately
    invokes the executable once, from a temporary directory, before any
    case is prepared. Worth recording while it is in view: that pre-flight
    therefore runs BEFORE this refusal, so a collision knowable from the
    campaign file alone still costs one solver start. That is the
    pre-flight's own design and not this guard's business, but a reader
    of this test should not conclude that nothing at all was launched.
    """

    class RecordingSolver(StubSolver):
        def __init__(self):
            super().__init__(WRITES_LOADS)
            self.started: list[str] = []

        def _argv(self, script_path: Path) -> list[str]:
            self.started.append(str(script_path))
            return super()._argv(script_path)

    campaign = make_campaign(tmp_path, alphas=alphas, outputs=outputs)
    workspace = CampaignWorkspace(tmp_path / "camp")
    executor = RecordingSolver()

    with pytest.raises(CampaignErrors):
        run_campaign(
            campaign,
            executor,
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )

    from_this_campaign = [path for path in executor.started if str(workspace.root) in path]
    assert from_this_campaign == [], (
        f"the solver was started on {from_this_campaign}, a script of a campaign whose "
        "output names collide, so the refusal happened after the run rather than "
        "before it. The collision is knowable from the campaign alone; spending a "
        "licensed solver seat to discover it is the defect PLN-20260802-1904 closed"
    )
    records = workspace.read_manifest()
    assert records, "the refusal recorded no point at all, so the manifest hides the failure"
    for record in records:
        assert record.status.startswith("FAILED")
        assert "overwrite the first" in (record.error or "")


def test_the_plan_and_the_collection_agree_on_the_collected_name():
    """One rule, two boundaries, and the boundaries must not re-derive it.

    The defect was not that either side was wrong on its own: each was
    right about its own question. It was that they answered the same
    question differently, so the cheap boundary passed what the
    expensive one refused. This asserts they share the function.
    """
    from pyflightstream.run import collection_name as from_run
    from pyflightstream.workspace import collection_name as from_workspace

    assert from_run is from_workspace
    assert from_workspace("loads.txt") == "loads.txt"
    assert from_workspace("a/loads.txt") == "loads.txt"
    assert from_workspace("a\\loads.txt") == "loads.txt"
    assert from_workspace("a/b/loads.txt") == "loads.txt"
    assert from_workspace(Path("a") / "loads.txt") == "loads.txt"


def test_a_registered_callable_meets_the_same_protocol_check(tmp_path):
    # The registry path skips resolve_recipe, so without its own check a
    # loose builder would fail per point with a bare TypeError instead.
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": lambda workdir: None})
    assert {point.status for point in plan.points} == {PlanStatus.BLOCKED}
    assert "does not satisfy the ScriptRecipe protocol" in plan.points[0].error


def test_the_assessor_says_what_it_could_not_read(tmp_path):
    # A converted matrix declares no outputs, so the default assessor
    # has nothing to judge; it must say so as a point status, not raise.
    campaign = make_campaign(tmp_path, alphas=(0.0,), outputs=())
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=LoadsAssessor(),
            recipes={"steady": lambda case, script: script.emit("OPEN", case.geometry)},
        )
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "no single collected output reads as a loads table" in record.error


def test_the_assessor_says_which_named_file_is_missing(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=LoadsAssessor("not_exported.txt"),
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert "no collected output named 'not_exported.txt'" in record.error
    assert "loads_a+00.0.txt" in record.error  # what was collected


# PYFS-004, the REV-002 blocker reproduced at ecc212e. The review published
# five steps and they are all asserted below in one test, in its order, so
# the reproduction and the guard are the same artifact.
#
# The defect was an ORDERING one: run_campaign called _prepare_case (which
# calls stage_inputs, a copy) once per case at :555, and only then tested
# `run_id in recorded` per point at :560. So a resume with nothing left to
# run still re-staged: the executor was called 0 times and returned [],
# which looks like a correct no-op, while the staged input was silently
# replaced OLD -> NEW and the manifest kept OLD's sha256. The manifest
# stopped describing the bytes on disk, and no output said so.
#
# The fix decides what is pending BEFORE preparing anything, and it decides
# it at the CASE level, because that is the level staging works at.


def test_a_resume_with_nothing_pending_does_not_restage(tmp_path):
    """The review's five published steps, in order."""
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    geometry = Path(campaign.sims[0].geometry)

    # 1. first run records both points and the manifest hashes OLD
    first = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert len(first) == 2
    staged = workspace.sim_dir("9001") / "inputs" / geometry.name
    assert staged.read_bytes() == b"geometry"
    recorded_hash = first[0].inputs_sha256[geometry.name]

    # the input changes underneath, which is the whole scenario
    geometry.write_bytes(b"geometry NEW")

    # 2. resume returns nothing and the executor is never called
    calls = []

    class CountingSolver(StubSolver):
        def _argv(self, script_path):
            calls.append(script_path)
            return super()._argv(script_path)

    resumed = run_campaign(
        campaign,
        CountingSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        resume=True,
    )
    assert resumed == []
    assert calls == []

    # 3, 4 and 5: the staged copy is UNTOUCHED, so the manifest still
    # describes it. This is the assertion that failed before the fix.
    assert staged.read_bytes() == b"geometry", (
        "the staged input was replaced by a resume that ran nothing"
    )
    manifest = {record.run_id: record for record in workspace.read_manifest()}
    still = manifest[first[0].run_id].inputs_sha256[geometry.name]
    assert still == recorded_hash
    from pyflightstream.workspace import _sha256

    assert _sha256(staged) == still, "the manifest hash no longer matches the file on disk"


def test_a_partial_resume_refuses_when_the_input_changed(tmp_path):
    """The half the review did not reach, and it is the same defect.

    With one point recorded and one pending, staging is legitimate: the
    pending point needs its inputs. But re-staging CHANGED content retires
    the evidence behind the recorded point, leaving one manifest describing
    two different input sets. Refusing is the only answer that keeps
    inputs_sha256 a fact about the run.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    geometry = Path(campaign.sims[0].geometry)
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )

    # add a second point, so the case is partially recorded, and change the input
    campaign.sims[0].sweep = SweepAxis(type="alpha", values=[0.0, 2.0])
    geometry.write_bytes(b"geometry NEW")

    with pytest.raises(WorkspaceError, match="has changed since"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
            resume=True,
        )
    # and the refusal happened BEFORE staging: the old copy survives
    staged = workspace.sim_dir("9001") / "inputs" / geometry.name
    assert staged.read_bytes() == b"geometry"


def test_a_partial_resume_runs_the_new_point_when_the_input_is_unchanged(tmp_path):
    """The control: the refusal above must not have cost resume its purpose."""
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )

    campaign.sims[0].sweep = SweepAxis(type="alpha", values=[0.0, 2.0])
    resumed = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        resume=True,
    )
    assert len(resumed) == 1, "only the new point should run"
    assert [record.run_id for record in workspace.read_manifest()] == [
        "camp/sim_9001/a+00.0",
        "camp/sim_9001/a+02.0",
    ]


def test_a_rerun_without_resume_still_refuses_before_anything_executes(tmp_path):
    """The pre-existing contract, re-asserted because the fix moved the check.

    The docstring always promised the refusal came "before anything
    executes". It now also comes before anything is STAGED, which is what
    the promise had to mean to be worth anything.
    """
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    geometry = Path(campaign.sims[0].geometry)
    geometry.write_bytes(b"geometry NEW")

    with pytest.raises(WorkspaceError, match="already in the manifest"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    staged = workspace.sim_dir("9001") / "inputs" / geometry.name
    assert staged.read_bytes() == b"geometry"


# PYFS-007, the REV-002 blocker reproduced at ecc212e. The review's evidence
# was the real 26.120 residual log with one character changed in the last
# PRESSURE residual, and its four measured rows are the four cases below.
#
# The defect was `max(velocity, pressure)` followed by a NaN test on the
# RESULT. Every comparison against NaN is False, so Python's max returns its
# first argument: max(9.6e-8, nan) is 9.6e-08. A NaN in the second column was
# swallowed, the test below never fired, and the point was published
# CONVERGED carrying a residual that is not the residual that decided it.
# Infinity was the same class in a different disguise: inf <= limit is False,
# so an infinite residual read as COMPLETED_MAX_ITER, which asserts the
# solver merely ran out of iterations.
#
# The fix judges every component BEFORE combining them. Reducing a set of
# numbers cannot be trusted to preserve the invalidity of one of them.

LAST_VELOCITY = "+9.6000000E-8"
LAST_PRESSURE = "+2.6200000E-8"


def _log_with(replacement: str, column: str) -> str:
    """The real fixture with one final-row residual replaced."""
    text = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("1575"):
            lines[index] = line.replace(column, replacement.ljust(len(column)))
            break
    else:  # pragma: no cover - the fixture changed
        raise AssertionError("the final iteration row is no longer 1575")
    return "".join(lines)


def _assess_log(tmp_path, text):
    make_raw(tmp_path, "loads_unsteady_26.120.txt")
    make_raw(tmp_path, "", name="log.txt", text=text)
    return LoadsAssessor("loads.txt", log_file="log.txt")(None, None, tmp_path)


def test_a_nan_in_the_pressure_column_is_not_swallowed(tmp_path):
    """Row 2 of the review's table, and the one that was wrong.

    Measured before the fix: status=CONVERGED, iterations=1575,
    residual=9.6e-08, which is the VELOCITY residual reported as though it
    had decided a judgment the NaN should have prevented.
    """
    assessment = _assess_log(tmp_path, _log_with("NaN", LAST_PRESSURE))
    assert assessment.status is RunStatus.FAILED_DIVERGED
    assert assessment.iterations == 1575
    assert "pressure" in assessment.error
    # and it must not report the other column's value as "the" residual
    assert assessment.residual is None


def test_a_nan_in_the_velocity_column_is_still_caught(tmp_path):
    """Row 4, and it is EVIDENCE rather than the control it was labelled.

    The label was wrong and the QA re-run pass measured it. The pre-fix body
    did reach FAILED_DIVERGED here, because max(nan, 2.62e-8) is nan and the
    old post-hoc NaN test fired. But the old message read "final residuals
    are NaN", so the assertion below on "velocity" fails against it, which
    makes this case fail on the mutant like the other two.

    The group's only true control is test_the_pristine_log_is_still_converged.
    Recorded rather than quietly relabelled, because a reader who trusts the
    labels believes this group has a control it does not have, and the next
    edit could delete the real evidence as redundant.
    """
    assessment = _assess_log(tmp_path, _log_with("NaN", LAST_VELOCITY))
    assert assessment.status is RunStatus.FAILED_DIVERGED
    assert "velocity" in assessment.error


def test_an_infinite_residual_is_divergence_and_not_an_iteration_limit(tmp_path):
    """Row 3: measured COMPLETED_MAX_ITER with residual=inf before the fix.

    COMPLETED_MAX_ITER is a claim that the solver ran to its iteration cap
    with a finite residual it simply did not reduce far enough. An infinite
    residual is a different event and must not borrow that status.
    """
    assessment = _assess_log(tmp_path, _log_with("Inf", LAST_PRESSURE))
    assert assessment.status is RunStatus.FAILED_DIVERGED
    assert "pressure" in assessment.error


def test_the_pristine_log_is_still_converged(tmp_path):
    """Row 1, the control.

    Without this the three above are satisfied by an assessor that calls
    everything diverged.
    """
    assessment = _assess_log(
        tmp_path, (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8")
    )
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.iterations == 1575
    assert assessment.residual == pytest.approx(9.6e-8)


# --- FR-48: a waived broken command reaches the manifest --------------------


def waived_altitude_recipe(case, script):
    """steady_recipe plus the one command 26.120 records broken."""
    script.emit("OPEN", case.geometry)
    helpers.free_stream(script)
    script.allow_broken(
        "AIR_ALTITUDE",
        reason="reproducing a run made before the units defect was found",
    )
    helpers.atmosphere(script, altitude=1000.0)
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


def refused_altitude_recipe(case, script):
    """The same recipe without the waiver: the campaign must not run it."""
    script.emit("OPEN", case.geometry)
    helpers.atmosphere(script, altitude=1000.0)


def test_a_waived_broken_command_rides_into_the_manifest(tmp_path):
    """The half of PYFS-002 that outlives the session.

    Refusing at build time protects the run being built. This protects
    every reader afterwards: the numbers in this campaign came from a
    solver told to fly at an altitude the manual's command does not
    deliver on this build, and the manifest is the only place that can
    still say so once the script is one file among hundreds.
    """
    campaign = make_campaign(tmp_path, recipe="waived")
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"waived": waived_altitude_recipe},
    )
    assert all(record.status is RunStatus.CONVERGED for record in records)
    for record in records:
        (use,) = record.broken_commands
        assert use["command"] == "AIR_ALTITUDE"
        assert use["version"] == "26.120"
        assert use["report"] == "reports/compat/CMP-26120_2026-08-08_full.yaml"
        assert use["reason"].startswith("reproducing a run")
    # It survives the round trip through runs.json, which is the point.
    assert workspace.read_manifest()[0].broken_commands == records[0].broken_commands
    # The control: the ordinary recipe records nothing, so an empty list
    # keeps meaning "this run leaned on nothing broken".
    plain_root = tmp_path / "plain"
    plain_root.mkdir()
    plain = make_campaign(plain_root)
    plain_workspace = CampaignWorkspace(plain_root / "camp")
    plain_records = run_campaign(
        plain,
        StubSolver(WRITES_LOADS),
        plain_workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert plain_records[0].broken_commands == []


def test_an_unwaived_broken_command_fails_the_point_before_the_solver(tmp_path):
    """A recipe that emits it without a waiver never reaches the solver.

    FAILED_SCRIPT, not a converged point with wrong numbers, which is
    what this campaign produced before FR-48.
    """
    campaign = make_campaign(tmp_path, recipe="refused")
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors) as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"refused": refused_altitude_recipe},
        )
    records = workspace.read_manifest()
    assert len(records) == 2
    assert all(record.status is RunStatus.FAILED_SCRIPT for record in records)
    assert all("AIR_ALTITUDE" in record.error for record in records)
    assert all("BrokenCommandError" in record.error for record in records)
    # Nothing was waived, so nothing is recorded as waived: the refusal
    # and the record are separate mechanisms and must not stand in for
    # each other.
    assert all(record.broken_commands == [] for record in records)
    assert len(caught.value.failures) == 2


# --- PYFS-008: forced iterations disable the threshold the count judgment ---
# --- infers from. The field was parsed and never read.                    ---

_FORCED_OFF = "Force solver to run all iterations           F"
_FORCED_ON = "Force solver to run all iterations           T"


def _steady_text() -> str:
    text = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    assert _FORCED_OFF in text, (
        "the steady fixture no longer prints the forced-iterations line as this "
        "guard expects, so every assertion below would be testing the wrong file"
    )
    return text


def test_an_early_stop_under_forced_iterations_is_not_converged(tmp_path):
    """The finding, as its own assertion.

    312 of 500 requested, with the solver told to run all of them. The
    threshold that an early stop is supposed to evidence was switched off, so
    whatever ended the loop, it was not convergence. Before this, the point
    was published CONVERGED and was byte for byte indistinguishable in the
    manifest from a run that genuinely met the threshold at 312.
    """
    forced = _steady_text().replace(_FORCED_OFF, _FORCED_ON)
    assessment = LoadsAssessor("loads.txt")(
        None, None, make_raw(tmp_path / "forced", "", text=forced)
    )
    assert assessment.status is not RunStatus.CONVERGED
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert assessment.iterations == 312
    assert "312 of 500" in assessment.error
    assert "forced iterations" in assessment.error


def test_the_count_judgment_still_stands_when_iterations_are_not_forced(tmp_path):
    """The control, and the reason the fix is narrow.

    Same file, same counts, one character different. Without it, a mutation
    that failed every early stop would leave the test above green while
    every converged run in every campaign turned into a failure.
    """
    assessment = LoadsAssessor("loads.txt")(
        None, None, make_raw(tmp_path / "unforced", "", text=_steady_text())
    )
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.iterations == 312


def test_a_completed_forced_run_is_still_completed_max_iter(tmp_path):
    """Forced iterations that reach the budget are not a failure.

    The loop ran its prescribed course; nothing about that is wrong, and
    nothing about it is convergence either. This is the second control: the
    refusal is about the loop ending EARLY, not about forcing.
    """
    text = _steady_text().replace(_FORCED_OFF, _FORCED_ON).replace("312", "500")
    assessment = LoadsAssessor("loads.txt")(None, None, make_raw(tmp_path / "full", "", text=text))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER
    assert assessment.iterations == 500


def test_an_unprinted_forced_flag_leaves_the_count_judgment_alone(tmp_path):
    """None is not False, and the difference decides a run.

    A footer that does not print the line tells us nothing about the
    threshold, so the count judgment stands. Reading None as "forced" would
    fail every steady run parsed from a version whose footer omits it.
    """
    text = "\n".join(
        line for line in _steady_text().splitlines() if "Force solver to run all" not in line
    )
    assessment = LoadsAssessor("loads.txt")(
        None, None, make_raw(tmp_path / "silent", "", text=text + "\n")
    )
    assert assessment.status is RunStatus.CONVERGED


def test_a_declared_log_decides_on_residuals_whatever_the_forced_flag_says(tmp_path):
    """Forced iterations change what an early stop MEANS, not what a residual is.

    With a log the judgment reads the residual directly, so there is no
    inference for the forced flag to invalidate, and narrowing the fix to the
    no-log branch is deliberate rather than an oversight.
    """
    unsteady = (FIXTURES / "loads_unsteady_26.120.txt").read_text(encoding="utf-8")
    sim_dir = make_raw(tmp_path / "logged", "", text=unsteady.replace(_FORCED_OFF, _FORCED_ON))
    make_raw(tmp_path / "logged", "log_residuals_26.120.txt", name="log.txt")
    assessment = LoadsAssessor("loads.txt", log_file="log.txt")(None, None, sim_dir)
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.residual == pytest.approx(9.6e-8)


# --- PYFS-006: whose file is this, and can it be overwritten? --------------


def test_a_file_that_was_already_there_is_not_collected_as_this_point(tmp_path):
    """The finding, and the reason it is worse than it sounds.

    The solver writes nothing at all in this test. Before the fix the point
    was published CONVERGED, its manifest record named `raw/loads_a+00.0.txt`
    as its evidence, and that file held whatever had been sitting in the
    folder. Nothing distinguished the record from a real one.

    Every point of a case shares one simulation folder, and collection asks
    only whether the declared output EXISTS.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    sim_dir = workspace.create_sim("9001")
    (sim_dir / "loads_a+00.0.txt").write_text("LEFT BEHIND BY SOMETHING ELSE", encoding="utf-8")

    with pytest.raises(CampaignErrors):
        run_campaign(
            campaign,
            StubSolver(WRITES_NOTHING),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "already exist" in record.error
    assert "loads_a+00.0.txt" in record.error
    assert record.outputs == []
    # The leftover is left exactly where it was: a refusal moves nothing.
    assert (sim_dir / "loads_a+00.0.txt").read_text(encoding="utf-8") == (
        "LEFT BEHIND BY SOMETHING ELSE"
    )
    # And the script is still recorded, so the refused point says what it
    # would have run rather than nothing.
    assert record.script_sha256


def test_an_ordinary_point_is_unaffected_by_the_stale_output_check(tmp_path):
    """The control: the folder is empty, so nothing is refused.

    Without it, a mutation refusing every point would leave the test above
    green while no campaign could run at all.
    """
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert all(record.status is RunStatus.CONVERGED for record in records)
    assert records[0].outputs == ["raw/loads_a+00.0.txt"]


def test_the_manifest_records_a_hash_per_collected_output(tmp_path):
    """A record that names evidence should say which bytes it named.

    Inputs have carried a hash since the first manifest; outputs carried a
    NAME and nothing else, so a file edited, truncated or replaced after the
    run still matched its record.
    """
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    for record in records:
        assert sorted(record.outputs_sha256) == sorted(record.outputs)
        for name, digest in record.outputs_sha256.items():
            path = workspace.sim_dir(record.sim_id) / name
            assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    # It survives the round trip through runs.json.
    assert workspace.read_manifest()[0].outputs_sha256 == records[0].outputs_sha256
    # And it detects the edit it exists to detect.
    edited = workspace.sim_dir("9001") / records[0].outputs[0]
    edited.write_text("TAMPERED", encoding="utf-8")
    assert (
        hashlib.sha256(edited.read_bytes()).hexdigest()
        != workspace.read_manifest()[0].outputs_sha256[records[0].outputs[0]]
    )


# --- PYFS-017, the manifest half: which code actually ran ------------------


def _package_is_tracked() -> bool:
    """True when the imported package sits in a tracked git work tree.

    An editable install does; a wheel installed into site-packages does
    not, and `package_vcs_state` documents `(None, None)` for that case.
    Two tests below asserted the editable reading unconditionally, so
    they failed against an installed wheel: found by dry-running the
    release workflow's test-artifact job locally before tagging, which
    is the only configuration in which that job runs (2026-08-03).
    """
    import subprocess

    import pyflightstream

    package_dir = Path(pyflightstream.__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "__init__.py"],
            cwd=package_dir,
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def test_the_manifest_records_the_package_commit_and_dirty_state(tmp_path):
    """`package_version` cannot tell two commits of one tag apart.

    Measured by the review at 28 commits and 85 files past `v0.3.0`, every
    identity still reporting `0.3.0`. A campaign run from a development tree
    was indistinguishable, in its own manifest, from one run against the
    release.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    commit, dirty = package_vcs_state()
    record = records[0]
    # The invariant that holds either way: the record says exactly what
    # package_vcs_state said, and never something else.
    assert record.package_commit == commit
    assert record.package_dirty is dirty
    assert workspace.read_manifest()[0].package_commit == commit

    if _package_is_tracked():
        assert commit is not None and len(commit) == 40
        assert isinstance(dirty, bool)
    else:
        # An INSTALLED wheel has no repository to ask, which is the
        # documented (None, None). Asserted rather than skipped, because
        # this is precisely the configuration the release workflow's
        # test-artifact job runs in, and a skip there would leave the
        # release leg proving nothing about the field.
        assert (commit, dirty) == (None, None)


def test_the_vcs_pair_is_none_together_and_never_guesses(tmp_path, monkeypatch):
    """None means "not knowable", never "clean".

    A wheel install has no repository to ask. Reporting a clean tree there
    would be a confident wrong answer, and the pair is what a later reader
    uses to decide whether a run is reproducible at all.
    """
    package_vcs_state.cache_clear()
    monkeypatch.setattr(
        "pyflightstream.run.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no git here")),
    )
    try:
        assert package_vcs_state() == (None, None)
    finally:
        monkeypatch.undo()
        package_vcs_state.cache_clear()
    # The control: with git back, the cache is not permanently empty, so the
    # test above is about the failure path rather than about a dead cache.
    # What "populated" means depends on where the package came from, and both
    # readings are the documented behaviour.
    if _package_is_tracked():
        assert package_vcs_state()[0] is not None
    else:
        assert package_vcs_state() == (None, None)


# --- PYFS-015: the record plus the staged inputs must reproduce the run ----


@pytest.mark.requirement("NFR-07")
def test_a_recorded_run_reconstructs_from_the_manifest_alone(tmp_path):
    """The round trip the finding asks for.

    RunRecord had 17 fields and none of them was the command line, the
    working directory, the effective timeout, the executable, the recipe's
    identity, or the script path. NFR-07 promised the record plus the staged
    inputs reproduce the run, and "reproduce" meant re-deriving all of that
    from executor code that may have changed since.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    record = records[0]
    assert record.manifest_schema == MANIFEST_SCHEMA
    assert record.argv and record.argv[0] == sys.executable
    assert record.cwd == str(workspace.sim_dir("9001"))
    assert record.recipe == "steady"
    assert (
        record.recipe_sha256
        == hashlib.sha256(inspect.getsource(steady_recipe).encode("utf-8")).hexdigest()
    )
    assert record.script_path == "scripts/a+00.0.txt"
    assert record.fs_exe == sys.executable
    assert record.fs_exe_sha256

    # The round trip: read the manifest back from disk and rebuild.
    reloaded = workspace.read_manifest()[0]
    rebuilt = reconstruct(reloaded, workspace=workspace)
    assert rebuilt.argv == tuple(record.argv)
    assert rebuilt.cwd == record.cwd
    assert rebuilt.timeout_s == record.timeout_s
    assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET" in rebuilt.script_text
    assert rebuilt.faithful, rebuilt.verified
    # Everything the record hashed is checked, not just the script.
    assert "scripts/a+00.0.txt" in rebuilt.verified
    assert "inputs/wing.fsm" in rebuilt.verified
    assert "raw/loads_a+00.0.txt" in rebuilt.verified


def test_reconstruction_says_so_when_an_artifact_changed(tmp_path):
    """`faithful` is the point: a changed file must not pass unnoticed.

    Without this the helper would hand back an invocation and a script that
    look authoritative while the evidence beside them had moved.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    record = workspace.read_manifest()[0]
    assert reconstruct(record, workspace=workspace).faithful

    edited = workspace.sim_dir("9001") / record.outputs[0]
    edited.write_text("TAMPERED", encoding="utf-8")
    rebuilt = reconstruct(record, workspace=workspace)
    assert not rebuilt.faithful
    assert rebuilt.verified[record.outputs[0]] == "differs"
    # Only the edited artifact is reported changed.
    assert rebuilt.verified[record.script_path] == "match"

    # Each artifact class is checked SEPARATELY, and this half is here
    # because a mutation proved it was not: replacing the script's own
    # hash check with True left every assertion above green, since they
    # only ever tampered with an output. A per-class guard needs a
    # per-class witness.
    script = workspace.sim_dir("9001") / record.script_path
    script.write_text("STOP\n", encoding="utf-8")
    after_script = reconstruct(record, workspace=workspace)
    assert after_script.verified[record.script_path] == "differs"

    staged = workspace.sim_dir("9001") / "inputs" / "wing.fsm"
    staged.write_bytes(b"REPLACED")
    after_input = reconstruct(record, workspace=workspace)
    assert after_input.verified["inputs/wing.fsm"] == "differs"

    # And a DELETED artifact is "missing", not "differs": nothing changed,
    # the evidence is gone, and the two have different answers (somebody
    # edited a result, against restore it from archive/).
    (workspace.sim_dir("9001") / record.outputs[0]).unlink()
    after_delete = reconstruct(record, workspace=workspace)
    assert after_delete.verified[record.outputs[0]] == "missing"
    assert not after_delete.faithful


def test_reconstruction_refuses_an_unknown_manifest_schema(tmp_path):
    """Guessing which fields exist would rebuild a run that never happened."""
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    record = workspace.read_manifest()[0]
    future = record.model_copy(update={"manifest_schema": "pyfs-manifest/99"})
    with pytest.raises(WorkspaceError, match="manifest schema"):
        reconstruct(future, workspace=workspace)
    # The control: the known schema still reconstructs, so the refusal is
    # about the value and not about the check being unconditional.
    assert reconstruct(record, workspace=workspace).faithful


def test_reconstruction_refuses_a_record_whose_script_is_gone(tmp_path):
    """An archived or cleaned sim cannot be reconstructed, and says so."""
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    record = workspace.read_manifest()[0]
    (workspace.sim_dir("9001") / record.script_path).unlink()
    with pytest.raises(WorkspaceError, match="is not at"):
        reconstruct(record, workspace=workspace)


def test_a_recipe_without_retrievable_source_records_no_hash(tmp_path):
    """None is honest where a lambda or a REPL function has no source.

    The alternative is hashing the repr, which changes with the memory
    address and would make two identical runs look different.
    """
    assert _recipe_digest(None) is None
    assert _recipe_digest(steady_recipe) is not None
    assert _recipe_digest(len) is None  # C-implemented, no source


def test_a_run_can_be_reconstructed_by_its_run_id(tmp_path):
    """The manifest names runs by id, so the helper should accept one.

    Reaching a run by list position, which is what the first version
    forced, is the raw-index-instead-of-label shape: `run_id` is this
    layer's named entity and it is what a reader of the manifest has.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    rebuilt = reconstruct("camp/sim_9001/a+00.0", workspace=workspace)
    assert rebuilt.faithful
    with pytest.raises(WorkspaceError, match=r"no run 'camp/sim_9001/a\+99.9'"):
        reconstruct("camp/sim_9001/a+99.9", workspace=workspace)


def test_the_plan_reports_a_waived_command_before_any_solver_time(tmp_path):
    """The pre-flight already knows, and used to say nothing.

    `_plan_point` builds the same script in dry run, so the waiver is
    determined at plan time; a waived point nonetheless planned READY,
    indistinguishable from a clean one, and the operator learned of the
    dependency only from the manifest, after the solver ran.
    """
    campaign = make_campaign(tmp_path, recipe="waived", alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(
        campaign, workspace, recipes={"waived": waived_altitude_recipe}, write_plan=False
    )
    point = plan.points[0]
    assert point.status is PlanStatus.READY
    assert point.broken_commands == ("AIR_ALTITUDE",)
    assert point.raw is False
    assert "waive a command recorded broken: AIR_ALTITUDE" in plan.summary()


def test_an_ordinary_plan_reports_no_waiver(tmp_path):
    """The control: the line appears only when there is something to say."""
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe}, write_plan=False)
    assert plan.points[0].broken_commands == ()
    assert "waive a command" not in plan.summary()
    assert "escape hatch" not in plan.summary()


# --- REV010-002: an unrecognized solver mode was a SUCCESSFUL status -------
#
# The review's reproduction: replacing the solver mode with "Warp" produced
# COMPLETED_MAX_ITER with no error. The classifier test in test_results.py
# proves the vocabulary; this proves the STATUS, which is the half that
# reached the manifest.


def _with_solver_mode(text: str, mode: str) -> str:
    """Rewrite the printed solver mode, keeping the file's own layout."""
    line = next(row for row in text.splitlines() if row.strip().startswith("Solver mode:"))
    printed = line.split()[-1]
    rewritten = text.replace(line, line.replace(printed, mode))
    # The rewrite must change the text exactly when the mode differs. A bare
    # "it changed" assertion fails the control below, where the fixture
    # already prints the mode being asked for; a missing assertion would let
    # a mutant that silently rewrote nothing pass as a refusal.
    assert (rewritten != text) == (printed != mode), mode
    return rewritten


@pytest.mark.parametrize("mode", ["Warp", "transient", "Stead"])
def test_an_unknown_solver_mode_is_not_a_successful_terminal_state(tmp_path, mode):
    steady = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    assessment = LoadsAssessor("loads.txt")(
        None,
        None,
        make_raw(tmp_path / mode, "", text=_with_solver_mode(steady, mode)),
    )
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert mode in assessment.error
    assert "not one this package knows" in assessment.error


def test_both_known_modes_are_still_judged(tmp_path):
    """The control. Without it the parametrized refusal above would pass on
    an assessor that refuses every mode, including the two real ones."""
    steady = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    for mode, expected in (
        ("Steady", RunStatus.CONVERGED),
        ("Unsteady", RunStatus.COMPLETED_MAX_ITER),
    ):
        assessment = LoadsAssessor("loads.txt")(
            None,
            None,
            make_raw(tmp_path / f"ok_{mode}", "", text=_with_solver_mode(steady, mode)),
        )
        assert assessment.status is expected, mode
        assert assessment.error is None, mode


# --- REV010-001: a result for a different flight condition ----------------
#
# The review's reproduction, reproduced here without its custom solver: a
# campaign point requests alpha=0 and the collected export prints alpha=2.
# Before this, the assessor took `case` and never read it, so the point was
# recorded CONVERGED and the contradiction lived only in a table helper the
# manifest never consults.


def test_an_export_from_another_operating_point_is_not_converged(tmp_path):
    steady = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")  # prints 2.000 deg
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=["loads.txt"],
    )
    case.point = {"alpha": 0.0}
    assessment = LoadsAssessor("loads.txt")(
        case, None, make_raw(tmp_path / "wrong", "", text=steady)
    )
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "different operating point" in assessment.error
    assert "alpha requested +0.0000 deg" in assessment.error
    # The decision is persisted with the numbers behind it.
    alpha = next(entry for entry in assessment.conditions if entry["axis"] == "alpha")
    assert alpha["requested"] == 0.0 and alpha["reported"] == 2.0
    assert alpha["within"] is False


def test_the_same_export_is_converged_for_the_point_it_belongs_to(tmp_path):
    """The control. Without it the refusal above would pass on an assessor
    that refused every export, which is the mutant that matters here."""
    steady = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[2.0]),
        recipe="steady",
        outputs=["loads.txt"],
    )
    case.point = {"alpha": 2.0}
    assessment = LoadsAssessor("loads.txt")(
        case, None, make_raw(tmp_path / "right", "", text=steady)
    )
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.error is None
    assert all(entry["within"] for entry in assessment.conditions)


def test_a_wrong_point_export_never_reaches_the_manifest_as_converged(tmp_path):
    """End to end, because the finding is about what the MANIFEST records.

    The stub writes the 2.000 deg fixture under the name the loop renders
    for the 0.0 deg point, which is exactly the overwrite the error text
    warns about.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="different operating point"):
        run_campaign(
            campaign,
            StubSolver(copies_fixture_as("loads_steady_26.120.txt", "loads_a+00.0.txt")),
            workspace,
            assess=LoadsAssessor(requested_version=campaign.fs_version),
            recipes={"steady": steady_recipe},
        )
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    alpha = next(entry for entry in record.conditions if entry["axis"] == "alpha")
    assert alpha["requested"] == 0.0 and alpha["reported"] == 2.0


# --- REV010-014: appending a run rewrote the runs before it ---------------
#
# read_manifest validated every row through RunRecord, whose
# manifest_schema defaulted to the CURRENT schema, and append_record
# re-serialized that validated list back to disk. So reading a historical
# manifest stamped it, and writing one new run PERSISTED the stamp: a row
# that never carried the field came back asserting the current layout,
# with more than twenty other fields defaulted into it.


def _legacy_row() -> dict:
    """A minimal historical row: no manifest_schema, no later fields."""
    return {
        "run_id": "camp/sim_0001/a+00.0",
        "sim_id": "0001",
        "point": {"alpha": 0.0},
        "fs_version_requested": "26.120",
        "package_version": "0.1.0",
        "script_sha256": "abc",
        "raw_flag": False,
        "status": "CONVERGED",
    }


def _workspace_with_legacy_row(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.manifest_path.write_text(json.dumps([_legacy_row()], indent=2), encoding="utf-8")
    return workspace


def test_a_legacy_row_does_not_claim_the_current_schema(tmp_path):
    workspace = _workspace_with_legacy_row(tmp_path)
    (record,) = workspace.read_manifest()
    assert record.manifest_schema is None, (
        "absent must not read as the current schema: the row never said that"
    )


def test_reading_a_manifest_does_not_change_it(tmp_path):
    workspace = _workspace_with_legacy_row(tmp_path)
    before = workspace.manifest_path.read_bytes()
    workspace.read_manifest()
    assert workspace.manifest_path.read_bytes() == before


def test_appending_a_run_leaves_the_older_row_exactly_as_written(tmp_path):
    """The review's reproduction. Appending rewrote the old row with the
    current schema and twenty-odd defaulted fields."""
    workspace = _workspace_with_legacy_row(tmp_path)
    new = RunRecord(
        run_id="camp/sim_0001/a+02.0",
        sim_id="0001",
        point={"alpha": 2.0},
        fs_version_requested="26.120",
        package_version="0.4.0",
        script_sha256="def",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        manifest_schema=MANIFEST_SCHEMA,
    )
    workspace.append_record(new)

    rows = workspace.read_raw_manifest()
    assert len(rows) == 2
    assert rows[0] == _legacy_row(), "the historical row was edited by an append"
    assert "manifest_schema" not in rows[0]
    # And the new row does carry it, so this is not simply "nothing is stamped".
    assert rows[1]["manifest_schema"] == MANIFEST_SCHEMA


def test_a_new_run_records_its_schema(tmp_path):
    """The control for the pair above: new rows must still be stamped, or
    'old rows are not rewritten' would be satisfied by never writing it."""
    campaign = make_campaign(tmp_path, alphas=(2.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert workspace.read_raw_manifest()[0]["manifest_schema"] == MANIFEST_SCHEMA


def test_reconstruction_refuses_a_row_that_predates_the_schema_field(tmp_path):
    """Refusing beats reconstructing fields the row does not have. This
    branch was unreachable while the default made every legacy row claim
    the current layout."""
    workspace = _workspace_with_legacy_row(tmp_path)
    with pytest.raises(WorkspaceError, match="carries no manifest schema"):
        reconstruct("camp/sim_0001/a+00.0", workspace=workspace)


# --- a campaign whose cases run on two solver builds --------------------


def _two_build_campaign(tmp_path, *, second_recipe="steady"):
    """A campaign of two cases, the second sent to a different build."""
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")

    def case(sim_id, fs_build, recipe):
        return SimCase(
            sim_id=sim_id,
            aircraft="TestWing",
            velocity=30.0,
            geometry=str(geometry),
            sweep=SweepAxis(type="alpha", values=[0.0]),
            recipe=recipe,
            outputs=["loads_{point}.txt"],
            fs_build=fs_build,
        )

    return Campaign(
        name="camp",
        fs_version="26.120",
        fs_exe=sys.executable,
        sims=[case("9001", None, "steady"), case("9002", "second", second_recipe)],
    )


def _second_build(tmp_path):
    """A SolverBuild whose executable is a real file with its own bytes.

    A distinct file rather than a second reference to ``sys.executable``,
    because the whole assertion is that ``fs_exe_sha256`` differs per
    build: two names for one file hash the same, and a record that still
    wrote the campaign's executable would pass.
    """
    other_exe = tmp_path / "FlightStream26121.exe"
    other_exe.write_bytes(b"a different installation")
    return other_exe, SolverBuild(
        fs_exe=other_exe,
        fs_version="26.121",
        executor=StubSolver(WRITES_LOADS),
    )


def _record_identity_checks(monkeypatch, seen):
    """Record every pre-flight the loop fires, still running the real one."""
    real_check = run_module.check_solver_identity

    def recording(executor, version, workdir, **kwargs):
        seen.append((version.canonical, id(executor)))
        return real_check(executor, version, workdir, **kwargs)

    monkeypatch.setattr(run_module, "check_solver_identity", recording)


def test_a_case_records_the_build_it_actually_ran_on(tmp_path):
    """PFS-2009.05: the manifest stops naming one executable for every point.

    A campaign declares ONE fs_version and ONE fs_exe, and `_execute_point`
    wrote `str(campaign.fs_exe)` and `_file_digest(campaign.fs_exe)` into
    every record regardless. So a study across two solver builds could not
    be stated at all: the run matrix refused a second FS_BUILD value
    outright, and the reason it HAD to was that recording one would have
    published a falsehood about which installation produced each point.

    THE FALSIFYING MEASUREMENT, which is the whole content of this test:
    with those two lines restored to `campaign.fs_exe`, the two records
    below carry the same executable and the same digest, and this fails on
    the assertion rather than on a missing name.
    """
    campaign = _two_build_campaign(tmp_path)
    other_exe, second = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={"second": second},
    )
    by_sim = {record.sim_id: record for record in records}
    assert set(by_sim) == {"9001", "9002"}

    assert by_sim["9001"].fs_exe == str(sys.executable)
    assert by_sim["9002"].fs_exe == str(other_exe), (
        "the case declaring fs_build='second' was recorded against the "
        "campaign's executable, so the manifest names an installation the "
        "point never ran on"
    )
    assert by_sim["9001"].fs_exe_sha256 != by_sim["9002"].fs_exe_sha256, (
        "both points hashed to the same executable; a per-build record that "
        "does not move the DIGEST records the same evidence under two names"
    )
    assert by_sim["9002"].fs_exe_sha256 == hashlib.sha256(other_exe.read_bytes()).hexdigest()

    # And the version, which is what the script was emitted under.
    assert by_sim["9001"].fs_version_requested == "26.120"
    assert by_sim["9002"].fs_version_requested == "26.121", (
        "the second build's points are recorded against the campaign's "
        "version, so a reader cannot tell which command database produced "
        "the script"
    )


#: A command the database documents on 26.121 and NOT on 26.120, so a
#: script emitting it says which version it was built against. Measured
#: rather than assumed: the pair is asserted in the test below, so the day
#: a 26.120 row is written for it the test fails as an unusable probe
#: instead of passing vacuously.
_ONLY_ON_26121 = "SET_WAKE_DECAY_CONSTANT"


def wake_decay_recipe(case, script):
    """The steady recipe plus one command only the newer build documents."""
    script.emit("OPEN", case.geometry)
    helpers.free_stream(script)
    script.emit(_ONLY_ON_26121, 0.05)
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


def test_the_second_builds_script_is_emitted_under_its_own_version(tmp_path):
    """The other half: the SCRIPT, not only the record that describes it.

    A record naming 26.121 beside a script built against the campaign's
    26.120 is worse than either alone, because the manifest then documents
    a run that never happened that way.

    Measured through the COMMAND DATABASE rather than through the script
    text, and the difference matters: the rendered script carries no
    version header at all, so an assertion reading "26.121 appears in the
    file" is unsatisfiable and would have to be weakened into something
    that proves nothing. What the version actually controls is which
    commands may be emitted, so the second case emits one the newer build
    documents and the older one does not. Under the campaign's version the
    builder refuses it and the point lands FAILED_SCRIPT; under its own
    build's version it converges.
    """
    from pyflightstream.commands import CommandRegistry

    registry = CommandRegistry.load()
    assert _ONLY_ON_26121 in registry.for_version("26.121"), (
        f"{_ONLY_ON_26121} is no longer documented on 26.121, so this test "
        "cannot tell the two versions apart; pick another command whose rows "
        "differ between the two builds"
    )
    assert _ONLY_ON_26121 not in registry.for_version("26.120"), (
        f"{_ONLY_ON_26121} is now documented on 26.120 too, so emitting it "
        "proves nothing about which version the script was built against"
    )

    campaign = _two_build_campaign(tmp_path, second_recipe="wake_decay")
    _, second = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    recipes = {"steady": steady_recipe, "wake_decay": wake_decay_recipe}
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes=recipes,
        builds={"second": second},
    )
    by_sim = {record.sim_id: record for record in records}
    assert by_sim["9002"].status is RunStatus.CONVERGED, (
        f"the second case emits {_ONLY_ON_26121}, which its own build "
        f"documents, and it was refused: {by_sim['9002'].error}. The script "
        "was built against the campaign's version rather than the build's."
    )
    assert by_sim["9002"].script_path is not None
    text = (workspace.sim_dir("9002") / by_sim["9002"].script_path).read_text(encoding="utf-8")
    assert _ONLY_ON_26121 in text

    # THE CONTROL, and without it the assertion above is satisfied by a
    # database that documents the command everywhere. Same campaign, same
    # recipe, a build declaring the OLDER version: the point must be
    # refused, which is what proves the version is read from the build.
    control_workspace = CampaignWorkspace(tmp_path / "control")
    with pytest.raises(CampaignErrors) as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            control_workspace,
            assess=converged,
            recipes=recipes,
            builds={
                "second": SolverBuild(
                    fs_exe=second.fs_exe, fs_version="26.120", executor=second.executor
                )
            },
        )
    refused = {record.sim_id: record for record in caught.value.failures}["9002"]
    assert refused.status is RunStatus.FAILED_SCRIPT
    assert _ONLY_ON_26121 in (refused.error or "")


def test_a_case_naming_an_unsupplied_build_is_refused_before_anything_runs(tmp_path):
    """The fallback that would make the whole feature a lie, refused.

    Falling back to `campaign.fs_exe` for a case naming a build the caller
    did not supply is exactly the record this item exists to stop: the
    point runs on one installation and the manifest names another. Refused
    BEFORE staging and before the manifest is touched, so the campaign
    root is left as it was found.
    """
    campaign = _two_build_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(ExecutorConfigurationError) as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    message = str(caught.value)
    assert "9002" in message and "second" in message, (
        "the refusal must name the case and the build it asked for"
    )
    assert "SolverBuild" in message, "the refusal must name what to pass instead"
    # Nothing was recorded, including for the FIRST case, which needs no
    # build at all: a configuration mistake is not a partial run.
    assert workspace.read_manifest() == []


def test_the_pre_flight_asks_each_build_once_on_its_own_executor(tmp_path, monkeypatch):
    """One identity check per installation, and on the right executable.

    The pre-flight answers "which build is installed at THIS executable",
    so a second executable is a second unanswered question and a single
    check would leave it unasked. The executor identity is asserted too:
    a loop that asked both versions while passing the campaign's executor
    every time would satisfy a version-only count while confirming one
    installation twice and reporting it as two.
    """
    campaign = _two_build_campaign(tmp_path)
    _, second = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    default_executor = StubSolver(WRITES_LOADS)

    seen: list[tuple[str, int]] = []
    _record_identity_checks(monkeypatch, seen)
    run_campaign(
        campaign,
        default_executor,
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={"second": second},
    )
    assert sorted(version for version, _ in seen) == ["26.120", "26.121"], (
        f"the pre-flight was asked {seen}; each distinct build is confirmed "
        "exactly once, and a build nothing asks about is an installation "
        "nothing checked"
    )
    asked = dict(seen)
    assert asked["26.120"] == id(default_executor)
    assert asked["26.121"] == id(second.executor), (
        "the second build's pre-flight ran on the campaign's executor, so it "
        "confirmed the wrong installation and reported it as the right one"
    )


def test_a_single_build_campaign_records_exactly_what_it_recorded_before(tmp_path, monkeypatch):
    """The regression half, and the one that matters most.

    Every campaign written before v0.8.0 names no build at all, so the
    per-build path must be invisible to it: same executable, same digest,
    same version, and ONE pre-flight rather than one per case. Pinned on a
    campaign of TWO cases, because a one-case campaign cannot tell "once
    per campaign" from "once per case", and the loop now keys the
    pre-flight on the build rather than on a single flag.
    """
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    cases = [
        SimCase(
            sim_id=sim_id,
            aircraft="TestWing",
            velocity=30.0,
            geometry=str(geometry),
            sweep=SweepAxis(type="alpha", values=[0.0]),
            recipe="steady",
            outputs=["loads_{point}.txt"],
        )
        for sim_id in ("9001", "9002")
    ]
    campaign = Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=cases)
    workspace = CampaignWorkspace(tmp_path / "camp")

    seen: list[tuple[str, int]] = []
    _record_identity_checks(monkeypatch, seen)
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert [record.sim_id for record in records] == ["9001", "9002"]
    assert {record.fs_exe for record in records} == {str(sys.executable)}
    assert len({record.fs_exe_sha256 for record in records}) == 1
    assert {record.fs_version_requested for record in records} == {"26.120"}
    assert [version for version, _ in seen] == ["26.120"], (
        f"a campaign naming no build asked the pre-flight {seen}; it spent one "
        "process before v0.8.0 and must spend one now"
    )


def test_the_plan_validates_each_case_against_its_own_build(tmp_path):
    """Pre-flight is where a per-build campaign earns the check.

    A case sent to a build whose database does not carry a command it
    emits has to block HERE, before the first point of the FIRST build
    spends solver time. That is the whole promise of the pre-flight and
    it is the one a per-build campaign can lose silently: threading the
    build into the RUN and leaving the plan on the campaign's version
    passes a campaign the loop then refuses, after the solver has run.

    Both directions, because one alone is satisfied by a constant: the
    same case blocks under the older build and is READY under the newer.
    """
    campaign = _two_build_campaign(tmp_path, second_recipe="wake_decay")
    recipes = {"steady": steady_recipe, "wake_decay": wake_decay_recipe}

    def plan_for(version, root):
        return plan_campaign(
            campaign,
            CampaignWorkspace(tmp_path / root),
            recipes=recipes,
            write_plan=False,
            builds={
                "second": SolverBuild(
                    fs_exe=Path(sys.executable),
                    fs_version=version,
                    executor=StubSolver(WRITES_LOADS),
                )
            },
        )

    older = {point.sim_id: point for point in plan_for("26.120", "older").points}
    assert older["9001"].status is PlanStatus.READY
    assert older["9002"].status is PlanStatus.BLOCKED, (
        "the second case was validated against the campaign's version rather "
        "than its own build's, so a command that build does not document "
        "would have been discovered only after the solver ran"
    )
    assert _ONLY_ON_26121 in (older["9002"].error or "")

    newer = {point.sim_id: point for point in plan_for("26.121", "newer").points}
    assert newer["9001"].status is PlanStatus.READY
    assert newer["9002"].status is PlanStatus.READY, (
        f"the second case blocks on its own build, which documents "
        f"{_ONLY_ON_26121}: {newer['9002'].error}"
    )


def test_the_plan_refuses_a_case_naming_an_unsupplied_build(tmp_path):
    """The pre-flight cannot pass a configuration the run will reject.

    Otherwise the promise that a green plan means the campaign is runnable
    is false for exactly the campaigns this feature adds, and it is false
    in the direction that costs solver time.
    """
    campaign = _two_build_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(ExecutorConfigurationError, match="second"):
        plan_campaign(campaign, workspace, recipes={"steady": steady_recipe}, write_plan=False)


# --- which supplied velocity wins (OPS-2009.01.04) --------------------------


class _PrintedConditions:
    """The three fields ``bind_conditions`` reads, without a parsed export.

    ``bind_conditions`` is duck typed on purpose (its own docstring says
    so), so the precedence is measured without a loads fixture and
    without asserting anything about the parser.
    """

    def __init__(self, *, alpha, velocity):
        self.angle_of_attack_deg = alpha
        self.sideslip_deg = None
        self.freestream_velocity_m_s = velocity


def _velocity_check(case, *, printed_velocity):
    """Bind one case against an export printing ``printed_velocity``."""
    binding = run_module._bind_case_conditions(
        case, _PrintedConditions(alpha=0.0, velocity=printed_velocity)
    )
    return {check.axis: check for check in binding.checks}["velocity"]


def _velocity_case(**overrides):
    fields = dict(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=["loads_{point}.txt"],
        point={"alpha": 0.0},
    )
    fields.update(overrides)
    return SimCase(**fields)


def test_the_point_velocity_wins_over_the_case_velocity():
    """The precedence, pinned where a refactor can reverse it in silence.

    The point is the value of THIS point and the case attribute is the
    case default, so the point wins. ``setdefault`` is what says that,
    and a plain assignment reads identically at the call site while
    recording a request the campaign never made: the binding would claim
    30 m/s was asked for when 12 was.
    """
    case = _velocity_case(point={"alpha": 0.0, "velocity": 12.0})
    check = _velocity_check(case, printed_velocity=12.0)
    assert check.requested == 12.0, (
        "the case attribute overwrote the point's own velocity, so the recorded "
        "request is not the request"
    )
    assert check.within


def test_the_case_velocity_fills_in_when_the_point_supplies_none():
    """The other direction, without which the test above passes on a constant."""
    check = _velocity_check(_velocity_case(), printed_velocity=30.0)
    assert check.requested == 30.0
    assert check.within


def test_a_case_supplying_no_velocity_at_all_requests_none():
    """Absent is not zero: nothing was asked, so nothing is compared."""
    binding = run_module._bind_case_conditions(
        _velocity_case(velocity=None), _PrintedConditions(alpha=0.0, velocity=30.0)
    )
    assert [check.axis for check in binding.checks] == ["alpha"]


def test_no_sweep_can_supply_a_velocity_so_the_point_branch_is_off_the_campaign_path():
    """The finding, measured rather than described (OPS-2009.01.04).

    The precedence above is REAL but UNREACHABLE through a campaign
    today: no sweep axis emits a velocity, so ``case.point`` carries one
    only when a caller puts it there, which is what the two tests above
    do. Pinned as a measurement so that the day a velocity sweep is added
    this fails and a reader learns the precedence has become
    campaign-reachable, instead of the branch quietly counting as
    covered.
    """
    axes = set()
    for sweep in (
        SweepAxis(type="alpha", values=[0.0]),
        SweepAxis(type="beta", values=[0.0]),
        SweepAxis(type="advance_ratio", values=[1.0]),
        SweepAxis(type="alpha_beta", values=[(0.0, 0.0)]),
    ):
        for point in sweep.points():
            axes |= set(point)
    assert "velocity" not in axes, (
        "a sweep can now emit a velocity, so the point-versus-case precedence is "
        "reachable from a campaign file; the two tests above stop being the only "
        "place it is exercised"
    )


# --- the pre-flight refuses before a licensed run begins (PFS-2009.09) ------


def _identity_stub(build):
    """A stub solver that reports ``build`` when asked for its identity.

    Writes the declared outputs like every other stub here, and answers
    the pre-flight's EXPORT_LOG with a log naming one build number, which
    is what ``check_solver_identity`` reads.
    """
    return (
        "import pathlib, sys; "
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_text('LOADS') "
        "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']; "
        f"[pathlib.Path(lines[i + 1]).write_text('FlightStream build #{build}') "
        "for i, line in enumerate(lines) if line == 'EXPORT_LOG']"
    )


class _CountingSolver(StubSolver):
    """A stub that records every script it is handed."""

    def __init__(self, code):
        super().__init__(code)
        self.scripts: list[str] = []

    def _argv(self, script_path: Path):
        self.scripts.append(Path(script_path).name)
        return super()._argv(script_path)


def _registered_build(version):
    from pyflightstream.versions import resolve as resolve_version

    return resolve_version(version).build


def test_a_row_whose_build_fails_identity_stops_the_campaign_before_any_point_runs(tmp_path):
    """PFS-2009.09.02: the refusal comes before the first licensed run.

    The pre-flight is per build and it fired at the first point OF THAT
    BUILD, so a campaign whose SECOND build is misconfigured ran every
    point of the first one and refused afterwards. Those seats are
    already gone when the message arrives, which is the whole thing a
    pre-flight exists to prevent.

    THE FALSIFYING MEASUREMENT is the manifest: with the check left at
    the per-case seam, the first case executes and records before the
    second build is ever asked, so ``read_manifest()`` holds one record
    and this fails on the assertion rather than on a missing name.
    """
    campaign = _two_build_campaign(tmp_path)
    other_exe, _ = _second_build(tmp_path)
    good = _CountingSolver(_identity_stub(_registered_build("26.120")))
    bad = _CountingSolver(_identity_stub("8092026"))
    second = SolverBuild(fs_exe=other_exe, fs_version="26.121", executor=bad)
    workspace = CampaignWorkspace(tmp_path / "camp")

    with pytest.raises(ExecutorConfigurationError) as caught:
        run_campaign(
            campaign,
            good,
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
            builds={"second": second},
        )

    assert workspace.read_manifest() == [], (
        "points of the healthy build were executed and recorded before the "
        "second build's identity was ever asked, so the licensed seats this "
        "refusal exists to save were already spent when it arrived"
    )
    assert good.scripts == ["preflight.txt"], (
        f"the campaign's own executor ran {good.scripts}; nothing but the "
        "identity pre-flight may run before every build has answered"
    )
    message = str(caught.value)
    assert "second" in message, "the refusal does not name the build that failed"
    assert "9002" in message, (
        "the refusal does not name the row that asked for the failing build, so "
        "the user has a wall rather than something actionable"
    )
    assert "8092026" in message and "26.121" in message


def test_a_healthy_second_build_still_runs_every_point(tmp_path):
    """The control: the refusal above must not be reachable by refusing all."""
    campaign = _two_build_campaign(tmp_path)
    other_exe, _ = _second_build(tmp_path)
    good = _CountingSolver(_identity_stub(_registered_build("26.120")))
    also_good = _CountingSolver(_identity_stub(_registered_build("26.121")))
    second = SolverBuild(fs_exe=other_exe, fs_version="26.121", executor=also_good)
    workspace = CampaignWorkspace(tmp_path / "camp")

    records = run_campaign(
        campaign,
        good,
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={"second": second},
    )
    assert [record.sim_id for record in records] == ["9001", "9002"]
    assert [record.status for record in records] == [RunStatus.CONVERGED] * 2


def test_a_resume_with_nothing_pending_still_launches_no_solver_process(tmp_path):
    """The invariant the earlier refusal must not trade away.

    Moving the identity check ahead of the loop is the obvious way to
    close the double spend and it breaks this: a fully recorded campaign
    re-run with resume=True has nothing to do and must spend NOTHING. The
    check therefore stays at the pending seam and only widens to cover
    every build that still has work.
    """
    campaign = _two_build_campaign(tmp_path)
    other_exe, _ = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        _CountingSolver(_identity_stub(_registered_build("26.120"))),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={
            "second": SolverBuild(
                fs_exe=other_exe,
                fs_version="26.121",
                executor=_CountingSolver(_identity_stub(_registered_build("26.121"))),
            )
        },
    )

    fresh = _CountingSolver(_identity_stub(_registered_build("26.120")))
    fresh_second = _CountingSolver(_identity_stub("8092026"))
    records = run_campaign(
        campaign,
        fresh,
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={
            "second": SolverBuild(fs_exe=other_exe, fs_version="26.121", executor=fresh_second)
        },
        resume=True,
    )
    assert records == []
    assert fresh.scripts == [] and fresh_second.scripts == [], (
        f"a resume with nothing pending launched {fresh.scripts + fresh_second.scripts}; "
        "a campaign with nothing left to run must spend no solver process, and a "
        "build whose points are all recorded is not even asked its identity"
    )


def _many_rows_per_build(tmp_path, *, per_build=3):
    """A campaign of ``per_build`` cases on each of two builds."""
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    cases = []
    for index in range(per_build):
        for prefix, build in (("90", None), ("91", "second")):
            cases.append(
                SimCase(
                    sim_id=f"{prefix}{index:02d}",
                    aircraft="TestWing",
                    velocity=30.0,
                    geometry=str(geometry),
                    sweep=SweepAxis(type="alpha", values=[0.0]),
                    recipe="steady",
                    outputs=["loads_{point}.txt"],
                    fs_build=build,
                )
            )
    return Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=cases)


def test_the_pre_flight_checks_each_build_once_whatever_the_row_count(tmp_path, monkeypatch):
    """PFS-2009.09.01: N identity checks for N builds, not one per row.

    Grouping is what turns a per-row cost into a per-build cost while
    keeping per-row coverage, and a one-case-per-build campaign cannot
    tell the two apart: three cases per build is the smallest shape that
    can.
    """
    campaign = _many_rows_per_build(tmp_path)
    _, second = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")

    seen: list[tuple[str, int]] = []
    _record_identity_checks(monkeypatch, seen)
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={"second": second},
    )
    assert len(campaign.sims) == 6
    assert sorted(version for version, _ in seen) == ["26.120", "26.121"], (
        f"six rows across two builds asked the pre-flight {len(seen)} times ({seen}); "
        "the cost is per BUILD, because the question is which build is installed "
        "at an executable and a row does not change the answer"
    )


def test_the_plan_reports_the_build_grouping_before_anything_runs(tmp_path):
    """The grouping is an artefact the operator wants BEFORE the campaign.

    How many solver installations a study actually spans is usually a
    surprise, and the pre-flight is the one place it can be learned for
    free: ``plan_campaign`` spends no solver process at all.
    """
    campaign = _many_rows_per_build(tmp_path, per_build=2)
    _, second = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(
        campaign,
        workspace,
        recipes={"steady": steady_recipe},
        builds={"second": second},
    )

    groups = getattr(plan, "build_groups", None)
    assert groups == {"": ["9000", "9001"], "second": ["9100", "9101"]}, (
        "the plan cannot say which cases run on which installation, so the one "
        "free chance to report the grouping is not taken"
    )
    text = plan.summary()
    assert "2 solver installation" in text, (
        f"the plan summary does not report the grouping:\n{text}"
    )
    assert "second" in text and "9100" in text
    payload = json.loads(plan.plan_file.read_text(encoding="utf-8"))
    assert payload["build_groups"] == {"": ["9000", "9001"], "second": ["9100", "9101"]}


def test_a_single_installation_campaign_still_reports_its_one_group(tmp_path):
    """The ordinary campaign, which is every campaign written before v0.8.0."""
    campaign = make_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    assert getattr(plan, "build_groups", None) == {"": ["9001"]}
    assert "1 solver installation" in plan.summary()


# --- PFS-2009.08.02: the record says where each row's build came from -------
#
# `fs_exe` and `fs_version_requested` say WHICH build a point ran on and
# have since PYFS-015. Neither says whether that build was chosen FOR THE
# ROW or inherited from the campaign default, and with two sources for one
# fact a reader of a finished run cannot tell them apart.


@pytest.mark.requirement("NFR-07")
def test_the_record_says_whether_the_build_came_from_the_row_or_the_default(tmp_path):
    """Both values, in one campaign, so neither is a constant that happens to fit."""
    campaign = _two_build_campaign(tmp_path)
    other_exe, second = _second_build(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        builds={"second": second},
    )
    by_sim = {record.sim_id: record for record in records}
    assert set(by_sim) == {"9001", "9002"}, (
        "the campaign that carries both answers did not run both cases, so a "
        "single-valued field would satisfy the assertions below"
    )
    assert by_sim["9001"].fs_version_source == run_module.FS_VERSION_FROM_DEFAULT
    assert by_sim["9002"].fs_version_source == run_module.FS_VERSION_FROM_ROW
    # THE REPRODUCTION HALF: what the record says about the source has to
    # agree with the executable it names, or the new field is decoration.
    assert by_sim["9001"].fs_exe == sys.executable
    assert by_sim["9002"].fs_exe == str(other_exe)
    assert by_sim["9002"].fs_version_requested == "26.121"
    assert by_sim["9001"].fs_version_requested == "26.120"
    # And it survives the manifest, which is where a later reader meets it.
    stored = {record.sim_id: record for record in workspace.read_manifest()}
    assert stored["9002"].fs_version_source == run_module.FS_VERSION_FROM_ROW
    assert stored["9001"].fs_version_source == run_module.FS_VERSION_FROM_DEFAULT


def test_a_failed_point_still_says_where_its_build_came_from(tmp_path):
    """The base dict, not the success path: a failure is a record too."""
    campaign = make_campaign(tmp_path, recipe="broken", alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors) as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"broken": broken_recipe},
        )
    (failure,) = caught.value.failures
    assert failure.status is RunStatus.FAILED_SCRIPT
    assert failure.fs_version_source == run_module.FS_VERSION_FROM_DEFAULT


def test_a_row_written_before_the_build_source_existed_reads_as_unrecorded(tmp_path):
    """None is a third state and is not `campaign_default`."""
    workspace = _workspace_with_legacy_row(tmp_path)
    (record,) = workspace.read_manifest()
    assert record.fs_version_source is None, (
        "a row that predates the field must not claim the build was inherited; "
        "absent and campaign_default are different facts about the evidence"
    )


# --- OPS-2009.01.13: the record carries the requested free-stream velocity ---
#
# Two places compare requested conditions against the conditions the solver
# printed back, and only one of them could see the velocity axis, so the
# two could reach opposite verdicts about one run.


@pytest.mark.requirement("FR-18")
def test_the_record_carries_the_velocity_the_case_requested(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    assert campaign.sims[0].velocity == 30.0, (
        "the fixture stopped declaring a velocity, so this test would pass on a "
        "field that is always None"
    )
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert records[0].velocity_requested_m_s == 30.0
    (stored,) = workspace.read_manifest()
    assert stored.velocity_requested_m_s == 30.0


def test_a_failed_point_still_records_the_velocity_it_requested(tmp_path):
    """The four early returns build their record from the base dict alone."""
    campaign = make_campaign(tmp_path, recipe="broken", alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors) as caught:
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"broken": broken_recipe},
        )
    (failure,) = caught.value.failures
    assert failure.status is RunStatus.FAILED_SCRIPT
    assert failure.velocity_requested_m_s == 30.0, (
        "the failed point is exactly the one a reader compares against a "
        "neighbour, and it lost the axis"
    )


def test_a_case_that_requested_no_velocity_records_none_and_never_zero(tmp_path):
    """Not requested and requested-as-zero are different claims."""
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=["loads_{point}.txt"],
    )
    assert case.velocity is None
    campaign = Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    (stored,) = workspace.read_manifest()
    assert stored.velocity_requested_m_s is None, (
        "a case that asked for no velocity must record None; zero would be a "
        "request a loads export could be judged to contradict"
    )


# --- PFS-2012.03: a waiver record keeps its origin --------------------------


def test_a_row_under_the_previous_manifest_stamp_still_reconstructs(tmp_path):
    """The bump must not strand every manifest written before it.

    Nothing in this package migrates a manifest, so a reader that refused
    every older stamp would make the bump equivalent to deleting them.
    """
    assert "pyfs-manifest/1" in run_module.KNOWN_MANIFEST_SCHEMAS
    assert MANIFEST_SCHEMA != "pyfs-manifest/1", (
        "this test is about reading the PREVIOUS stamp; the constant did not move"
    )
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    rows = workspace.read_raw_manifest()
    assert len(rows) == 1
    rows[0]["manifest_schema"] = "pyfs-manifest/1"
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    rebuilt = reconstruct(rows[0]["run_id"], workspace=workspace)
    assert rebuilt.argv and rebuilt.script_text

    # THE CONTROL: a stamp outside the known set still denies, so this is
    # not "reconstruction stopped checking".
    rows[0]["manifest_schema"] = "pyfs-manifest/99"
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with pytest.raises(WorkspaceError, match="pyfs-manifest/99"):
        reconstruct(rows[0]["run_id"], workspace=workspace)


# --- PFS-2014.03: the sweep leaves its csv unasked ---------------------------
#
# Half one of the item shipped in the tabular layer: every row of a sweep
# table says whether its numbers are a raw integration or a reduction and
# over what window, and `sweep_table(require_loads=False)` exists so a
# campaign whose every point failed still yields a frame. What these
# cases pin is the half that was missing: NOBODY ASKS. Only
# `pyfs-matrix run` wrote a table, so a campaign driven from Python left
# its numbers inside the manifest and the raw exports and a colleague
# opening the workspace found no table at all.


def writes_fixture_per_sim(steady_fixture: str, unsteady_fixture: str) -> str:
    """Stub solver writing a different fixture for sim_9001 and sim_9002.

    The declared export name carries the point, so the stub reads the
    target out of the built script exactly as WRITES_LOADS does; what it
    adds is that the two simulations of one campaign export DIFFERENT
    solver modes, which is the mixed table the acceptance is about.
    """
    steady = FIXTURES / steady_fixture
    unsteady = FIXTURES / unsteady_fixture
    return (
        "import pathlib, sys; "
        "script = pathlib.Path(sys.argv[1]); "
        f"fixture = r'{steady}' if 'sim_9001' in script.as_posix() else r'{unsteady}'; "
        "text = pathlib.Path(fixture).read_text(); "
        "lines = script.read_text().splitlines(); "
        "[pathlib.Path(lines[i + 1]).write_text(text) "
        "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']"
    )


def mixed_campaign(tmp_path):
    """One campaign with a steady point and an unsteady point.

    The requested conditions are the ones the two fixtures PRINT (alpha
    2 deg at 30 m/s, and alpha 0 deg at 49.036 m/s): the tabular reader
    refuses an export whose printed operating point contradicts the
    record, so a campaign that means to be read has to ask for what its
    evidence shows.
    """
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    steady = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[2.0]),
        recipe="steady",
        outputs=["loads_{point}.txt"],
    )
    unsteady = SimCase(
        sim_id="9002",
        aircraft="TestProp",
        velocity=49.036,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=["loads_{point}.txt"],
    )
    return Campaign(
        name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[steady, unsteady]
    )


def sweep_csv(tmp_path):
    """Where the campaign is expected to have left its table."""
    return tmp_path / "camp" / "post" / run_module.SWEEP_TABLE_NAME


def test_a_completed_sweep_leaves_its_csv_beside_its_runs_unasked(tmp_path):
    """Nobody names a path, and the table is there afterwards.

    The call below passes no target, no writer and no post-processing
    step: the acceptance is that the file exists all the same, under the
    campaign's own post/ folder, with one line per point carrying the
    integrated forces.
    """
    campaign = mixed_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(writes_fixture_per_sim("loads_steady_26.120.txt", "loads_unsteady_26.120.txt")),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert len(records) == 2

    target = sweep_csv(tmp_path)
    assert target.is_file(), (
        f"a completed campaign left no {run_module.SWEEP_TABLE_NAME} under post/; the "
        "numbers exist only inside the manifest and the raw exports, which is the "
        "state PFS-2014.03 exists to end"
    )
    table = pd.read_csv(target)
    assert list(table["run_id"]) == ["camp/sim_9001/a+02.0", "camp/sim_9002/a+00.0"], (
        "the table must carry one line per point, in manifest order"
    )
    # The integrated forces, read back off the two fixtures' Total rows.
    assert table["CL"].tolist() == pytest.approx([0.4308, 0.00166])
    assert table["CDi"].tolist() == pytest.approx([0.0089, -0.009075])


def test_every_line_says_which_of_the_two_produced_its_numbers(tmp_path):
    """No row is ambiguous about raw integration versus reduction.

    The steady point's coefficients are a direct integration over
    nothing; the unsteady point's are the solver's own time average, and
    the spreadsheet prints no window for it, which the row SAYS rather
    than leaving blank. Both land under the same coefficient column
    names in one file, so a reader without these three columns compares
    them and reads a method difference as physics.
    """
    campaign = mixed_campaign(tmp_path)
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        campaign,
        StubSolver(writes_fixture_per_sim("loads_steady_26.120.txt", "loads_unsteady_26.120.txt")),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    table = pd.read_csv(sweep_csv(tmp_path))
    steady, unsteady = table.iloc[0], table.iloc[1]
    assert (steady["data_origin"], steady["reduction"], steady["reduction_window"]) == (
        "raw",
        "none",
        "not_applicable",
    )
    assert (unsteady["data_origin"], unsteady["reduction"], unsteady["reduction_window"]) == (
        "raw",
        "time_average",
        "not_printed",
    ), (
        "an unsteady line must carry the reduction and say the export printed no "
        "window; blank would read as 'averaged over nothing'"
    )
    # Vocabulary, not spelling: every cell is a published token, so a
    # future value cannot arrive as free text this file cannot be read by.
    for column, published in (
        ("data_origin", DATA_ORIGIN_CODES),
        ("reduction", REDUCTION_CODES),
        ("reduction_window", REDUCTION_WINDOW_CODES),
    ):
        assert set(table[column]) <= set(published), (
            f"the {column} column of the written table holds a token outside {sorted(published)}"
        )


def test_a_campaign_whose_every_point_failed_still_leaves_its_table(tmp_path):
    """The write happens BEFORE the raise, or the file is lost.

    CampaignErrors is raised by a campaign that RAN and had failing
    points, and those points are recorded. The same defect was found one
    layer up in `pyfs-matrix run`, where the writer sat under an except
    arm that returned first, so a sweep with one failed point left no
    table at all.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0, 2.0))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.raises(CampaignErrors, match="2 campaign point"):
        run_campaign(
            campaign,
            StubSolver(WRITES_NOTHING),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    table = pd.read_csv(sweep_csv(tmp_path))
    assert list(table["run_id"]) == ["camp/sim_9001/a+00.0", "camp/sim_9001/a+02.0"]
    assert set(table["status"]) == {"FAILED_INCOMPLETE_OUTPUT"}
    # Nothing was measured, so nothing is claimed about a reduction.
    assert set(table["reduction"]) == {"unknown"}
    assert set(table["reduction_window"]) == {"unknown"}
    assert "CL" not in table.columns


def test_a_sweep_whose_exports_do_not_read_as_loads_still_leaves_its_rows(tmp_path):
    """What ``require_loads=False`` actually buys, measured.

    Written after a mutant SURVIVED. Flipping the keyword back to True
    changed nothing in the all-points-failed case above, and the reason
    is worth keeping: the tabular layer only refuses when there ARE
    successful runs and none of them yields coefficients, so a campaign
    with no successful run never reaches that refusal. The condition the
    keyword really covers is this one, points recorded as successful
    whose exports the reader cannot parse, and it is the common shape of
    a mis-declared export name. The identity rows are what tell the
    operator which point to look at, so raising there would withhold the
    evidence exactly when it is needed.
    """
    campaign = make_campaign(tmp_path, alphas=(0.0, 2.0))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.warns(PyflightstreamWarning, match="none of the 2 successful runs"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),  # writes a file that is not a loads spreadsheet
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    table = pd.read_csv(sweep_csv(tmp_path))
    assert list(table["run_id"]) == ["camp/sim_9001/a+00.0", "camp/sim_9001/a+02.0"]
    assert set(table["status"]) == {"CONVERGED"}
    assert "CL" not in table.columns


def test_a_campaign_that_recorded_nothing_leaves_no_table_and_no_warning(tmp_path):
    """An empty manifest has no table to leave and nothing to complain about.

    The resume path can schedule no work at all; warning there would put
    a complaint on every re-run that found its work already done, and
    writing there would mean a file with no rows.
    """
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    campaign = Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[])
    workspace = CampaignWorkspace(tmp_path / "camp")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert (
            run_campaign(
                campaign,
                StubSolver(WRITES_LOADS),
                workspace,
                assess=converged,
                recipes={"steady": steady_recipe},
            )
            == []
        )
    assert not sweep_csv(tmp_path).exists()


def test_the_table_is_rebuilt_from_the_whole_manifest_on_a_resume(tmp_path):
    """One file describes the campaign, not the call that wrote it.

    This is why the name says campaign and why overwriting is right: the
    content is derived from an append-only manifest, so a rewrite can
    only add points. A per-call file would leave fragments nobody can
    join, and refusing the overwrite would freeze the table at the first
    call.
    """
    workspace = CampaignWorkspace(tmp_path / "camp")
    run_campaign(
        make_campaign(tmp_path, alphas=(0.0,)),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
    )
    assert list(pd.read_csv(sweep_csv(tmp_path))["run_id"]) == ["camp/sim_9001/a+00.0"]
    run_campaign(
        make_campaign(tmp_path, alphas=(0.0, 2.0)),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        resume=True,
    )
    assert list(pd.read_csv(sweep_csv(tmp_path))["run_id"]) == [
        "camp/sim_9001/a+00.0",
        "camp/sim_9001/a+02.0",
    ], "the rewritten table dropped the point an earlier call recorded"


def test_a_failed_write_costs_the_campaign_nothing_but_says_so(tmp_path):
    """A real OSError from the write, and the records still come back.

    post/ is occupied by a FILE, so creating the folder fails the way a
    read-only tree or a full disk would. The campaign's own outcome is
    what the operator paid solver time for; a csv that could not be
    written must not take it away, and must not be silent either.
    """
    (tmp_path / "camp").mkdir()
    (tmp_path / "camp" / "post").write_text("not a folder", encoding="utf-8")
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.warns(PyflightstreamWarning, match="sweep table was NOT written"):
        records = run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
        )
    assert [record.run_id for record in records] == ["camp/sim_9001/a+00.0"]
    assert len(workspace.read_manifest()) == 1


def test_an_unforeseen_write_error_does_not_swallow_the_campaign_failures(tmp_path, monkeypatch):
    """The except clause is total ON PURPOSE, and this is why.

    A RuntimeError out of the writer is exactly the class a narrow
    except would let through, and letting it through would replace
    CampaignErrors, the one object naming which points failed, with a
    report about a csv.
    """

    def explodes(frame, path, **kwargs):
        raise RuntimeError("the writer broke in a way nobody predicted")

    monkeypatch.setattr(run_module, "write_table", explodes)
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    with pytest.warns(PyflightstreamWarning, match="RuntimeError"):
        with pytest.raises(CampaignErrors, match="1 campaign point"):
            run_campaign(
                campaign,
                StubSolver(WRITES_NOTHING),
                workspace,
                assess=converged,
                recipes={"steady": steady_recipe},
            )
    assert workspace.read_manifest()[0].status is RunStatus.FAILED_INCOMPLETE_OUTPUT


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ({"return_code": 1, "timed_out": False}, "return code 1"),
        ({"return_code": None, "timed_out": True}, "timeout"),
    ],
)
def test_the_preflight_names_its_own_failure_rather_than_blaming_the_solver(
    tmp_path, monkeypatch, outcome, expected
):
    """A DISCARDED RESULT MADE THREE CAUSES READ AS ONE.

    The pre-flight warns rather than refuses when it cannot read a build
    number, which is deliberate. What was wrong is the diagnosis: the
    run's own result was thrown away, so a solver that failed to start
    and one killed by the timeout produced the same sentence as a solver
    that ran perfectly and printed nothing, and that sentence said the
    build number could not be read FROM THE SOLVER.

    It is the same misattribution as the unresolved log path one line
    further on, with the difference that here the cause was knowable and
    discarded. The timeout case is one the operator can act on.
    """

    class FailingSolver:
        def run_script(self, script_path, working_dir, timeout_s=None):
            return run_module.ExecutionResult(
                wall_time_s=0.1, log_text=None, stdout="", stderr="", **outcome
            )

    monkeypatch.chdir(tmp_path)
    with pytest.warns(run_module.VersionMismatchWarning) as caught:
        run_module.check_solver_identity(
            FailingSolver(), version_resolve("26.120"), tmp_path / "pre"
        )
    message = str(caught[0].message)
    assert expected in message, (
        f"the warning does not name the real cause; it says {message!r}, which reads "
        "as a solver that ran and printed nothing"
    )
    assert "could not read a build number from the solver" not in message, (
        "the warning blames the solver for a run that failed or was killed before it "
        "could print anything"
    )


def test_the_identity_preflight_exports_its_log_to_an_absolute_path(tmp_path, monkeypatch):
    """THE FIFTH SOLVER BOUNDARY, and the one whose failure is a false PASS.

    `check_solver_identity` emits `EXPORT_LOG <path>` into script text and
    runs the solver with its working directory set to `workdir`. Spelled
    relatively, the solver writes the log one level too deep, this
    function finds none, reads no build number, and WARNS instead of
    raising: a campaign aimed at the wrong FlightStream build proceeds,
    and the warning blames the solver.

    That is the difference between this boundary and the other four. The
    campaign ones fail loudly with a missing file; this one fails by
    downgrading a refusal into a warning about somebody else.

    Its only in-package caller passes `tempfile.mkdtemp()` and every
    existing case passes `tmp_path`, both absolute, so the arm is
    unvisited rather than covered and is exercised here on its own terms.
    """
    emitted: dict[str, str] = {}

    class LogSpy:
        def run_script(self, script_path, working_dir, timeout_s=None):
            emitted["script"] = Path(script_path).read_text(encoding="utf-8")
            return run_module.ExecutionResult(
                return_code=0,
                wall_time_s=0.1,
                timed_out=False,
                log_text=None,
                stdout="",
                stderr="",
            )

    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_module.check_solver_identity(LogSpy(), version_resolve("26.120"), Path("pre"))

    lines = emitted["script"].splitlines()
    exported = lines[lines.index("EXPORT_LOG") + 1]
    assert Path(exported).is_absolute(), (
        f"the pre-flight exports its log to {exported!r}, which the solver resolves "
        "from its own directory; the log lands where nothing reads it, the build "
        "number is never read, and a wrong installation is warned about instead of "
        "being refused"
    )
    assert Path(exported).parent == (tmp_path / "pre").resolve()


# --- the log the verdict was read from, and the manifest that carries it -----
#
# BOTH FIXES BELOW SHIPPED WITH NO TEST, and a round-three mutation pass
# found that reverting either left the whole run suite green. The field
# exists to tell a residual verdict from an iteration-count one; a fix
# nothing evaluates cannot keep that apart a second time.


def test_the_assessment_records_which_log_decided_the_verdict(tmp_path):
    """The residual half: the file is named, so the claim is checkable."""
    sim_dir = make_raw(tmp_path, "loads_unsteady_26.120.txt")
    make_raw(tmp_path, "log_residuals_26.120.txt", name="log.txt")
    assessment = LoadsAssessor("loads.txt", log_file="log.txt")(None, None, sim_dir)
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.log_file_used == "log.txt"


def test_an_assessment_with_no_log_records_none_rather_than_a_name(tmp_path):
    """The other half, and the one that makes the field mean anything.

    An unsteady point with no log is COMPLETED_MAX_ITER whatever the
    solver did. Without this assertion the field could be populated
    unconditionally and still read as evidence.
    """
    sim_dir = make_raw(tmp_path, "loads_unsteady_26.120.txt")
    assessment = LoadsAssessor("loads.txt")(None, None, sim_dir)
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER
    assert assessment.log_file_used is None


def test_the_log_that_decided_the_verdict_reaches_the_run_record(tmp_path):
    """It was populated on the Assessment and dropped at the RunRecord.

    THROUGH THE CAMPAIGN LOOP, not by constructing a RunRecord. The
    first version of this test built the record directly, which proves
    the field is declared and says nothing about the line that carries
    it across; deleting that line is exactly the regression this exists
    to catch, and a direct construction survives it.
    """

    def assessed_from_a_log(case, execution, sim_dir):
        return Assessment(
            status=RunStatus.CONVERGED,
            iterations=120,
            residual=3.2e-6,
            log_file_used="log_a+00.0.txt",
        )

    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=assessed_from_a_log,
        recipes={"steady": steady_recipe},
    )
    assert records[0].log_file_used == "log_a+00.0.txt", (
        "the log the verdict was read from did not survive the RunRecord boundary"
    )
    written = json.loads((tmp_path / "camp" / "runs.json").read_text(encoding="utf-8"))
    rows = written["runs"] if isinstance(written, dict) else written
    assert rows[0]["log_file_used"] == "log_a+00.0.txt", (
        "the manifest on disk, which is the reader the field names, does not carry it"
    )


def test_the_forced_iteration_refusal_does_not_tell_users_to_name_the_log(tmp_path):
    """Auto-detection made that advice wrong and nothing was checking it.

    The message is a didactic surface: it is what a blocked user acts on,
    and it was still instructing them to pass `log_file` when exporting
    the log is now enough.
    """
    text = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    text = text.replace(
        "Force solver to run all iterations           F",
        "Force solver to run all iterations           T",
    )
    sim_dir = make_raw(tmp_path, "loads_steady_26.120.txt", text=text)
    assessment = LoadsAssessor("loads.txt")(None, None, sim_dir)
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    message = assessment.error or ""
    assert "found by content" in message, (
        f"the refusal must say the log is found by content, not that it has to be "
        f"named; got {message!r}"
    )
    assert "name it to LoadsAssessor" not in message


def test_the_auto_detected_log_is_recorded_under_the_name_it_was_found_by(tmp_path):
    """The branch the reworded refusal calls the normal path, untested.

    TWO THINGS THIS PINS THAT THE NAMED-FILE TEST CANNOT. It takes the
    auto-detect route, where a mutant returning None for exactly that
    route survived the whole suite. And the collected log is called
    something no argument could have supplied, so an implementation
    echoing the configured name back instead of the resolved file fails
    here; with a fixture named `log.txt` and `log_file="log.txt"` the two
    are indistinguishable.
    """
    sim_dir = make_raw(tmp_path, "loads_unsteady_26.120.txt")
    make_raw(tmp_path, "log_residuals_26.120.txt", name="whatever_the_solver_wrote.txt")
    assessment = LoadsAssessor()(None, None, sim_dir)
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.log_file_used == "whatever_the_solver_wrote.txt"
