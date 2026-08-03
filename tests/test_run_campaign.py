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
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import (
    Assessment,
    CampaignErrors,
    LoadsAssessor,
    LocalExecutor,
    PlanStatus,
    _recipe_digest,
    package_vcs_state,
    plan_campaign,
    reconstruct,
    run_campaign,
)
from pyflightstream.script import helpers
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
        assert use["report"] == "reports/compat/CMP-26120_2026-07-23_pln012.yaml"
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
    assert record.package_commit == commit
    assert record.package_dirty is dirty
    # This suite runs from a tracked work tree, so the pair is knowable here.
    # If that ever stops being true the assertion below says so rather than
    # letting the test pass over two Nones and prove nothing.
    assert commit is not None, (
        "the test suite is not running from a tracked work tree, so this guard "
        "cannot see whether the commit is recorded"
    )
    assert len(commit) == 40
    assert isinstance(dirty, bool)
    assert workspace.read_manifest()[0].package_commit == commit


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
    # The control: with git back, the pair is populated again, so the test
    # above is about the failure path and not about a permanently empty cache.
    assert package_vcs_state()[0] is not None


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
