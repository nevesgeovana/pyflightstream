"""Tier 1: the campaign loop, end-to-end dry run without FlightStream.

A StubSolver replaces the FlightStream argv with a Python one-liner
that mimics the solver behavior needed by each scenario (write the
declared outputs, write the hidden-mode error log, or fail), so the
whole path campaign.toml model, recipe, builder, workspace, executor,
and manifest is exercised for real.
"""

import json
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import (
    Assessment,
    CampaignErrors,
    LoadsAssessor,
    LocalExecutor,
    PlanStatus,
    plan_campaign,
    run_campaign,
)
from pyflightstream.script import helpers
from pyflightstream.workspace import (
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
    return Campaign(name="camp", fs_version="26.12", fs_exe=sys.executable, sims=[case])


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
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        campaign,
        StubSolver(copies_fixture_as("loads_steady_26.120.txt", "loads_a+00.0.txt")),
        workspace,
        assess=LoadsAssessor(requested_version=campaign.fs_version),
        recipes={"steady": steady_recipe},
    )
    record = records[0]
    assert record.status is RunStatus.CONVERGED
    assert record.iterations == 312
    assert record.fs_version_reported == "26.1"
    assert record.fs_build == "7012026"


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
        assert "would write the output" in plan.points[0].error
    else:
        assert PlanStatus.BLOCKED not in statuses


def test_a_single_point_case_may_name_its_output_constantly(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,), outputs=("loads.txt",))
    workspace = CampaignWorkspace(tmp_path / "camp")
    plan = plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    assert [point.status for point in plan.points] == [PlanStatus.READY]


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
