"""Tier 1: the workspace workflow, from a run type to a complete script.

Pipeline role: quality gate on PFS-2025.02, .05, .06, .08, .10 and .18.

A WORKFLOW is a run TYPE that builds the whole script by itself. It
resolves by TABLE LOOKUP inside :mod:`pyflightstream.cases.workflows`
and never through ``importlib``, which is exactly what separates it
from a recipe: a user cannot supply one, so a user who writes no Python
at all still gets a validated script.

The reproduction a reader should start from, and the shortest call that
exercises the whole item:

>>> from pyflightstream.cases.matrix import to_campaign
>>> from pyflightstream.cases.workflows import build_script
>>> from pyflightstream.script import Script
>>> campaign = to_campaign(                      # doctest: +SKIP
...     "workflow_rotor_matrix.fs",
...     name="rotor",
...     fs_version="26.120",
...     fs_exe="C:/fs.exe",
...     recipes={"010": "unsteady_rotor", "003": "steady"},
... )
>>> build_script(campaign.sims[0], Script("26.120"))   # doctest: +SKIP

WHAT THIS MODULE DELIBERATELY DOES NOT TEST, said here so a reader does
not take silence for coverage: no solver runs. The rotor path is proven
to SERIALISE against the command database of every registered build,
which is not the same fact as being accepted by a solver, and the
acceptance clause of PFS-2025.06 that asks for one real unsteady case
producing all four outputs needs a licensed seat that was not open.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis, check_recipe
from pyflightstream.cases import matrix as matrix_module
from pyflightstream.cases.matrix import to_campaign
from pyflightstream.cases.workflows import (
    ROTOR_SHEDDING_VARIABLE,
    WORKFLOW_KEY,
    WORKFLOWS,
    ExportWindow,
    ReductionPlan,
    WorkflowConventions,
    WorkflowCoverageError,
    build_script,
    covered_builds,
    emit_rotor_motion,
    export_window,
    reduction_plan,
    resolve_workflow,
    rotor_relaxed_trailing_edges,
    rotor_shedding_direction,
    select_workflow,
    workflow_names,
    workflow_registry,
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.fsi.driver import revolutions_per_step
from pyflightstream.post.reductions import write_reduction, write_series
from pyflightstream.post.unsteady import (
    blade_passage_average,
    passage_windows,
    read_timestep_series,
)
from pyflightstream.script import Script, helpers
from pyflightstream.versions import known_versions
from pyflightstream.workspace import WorkspaceError

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "workflow_rotor_matrix.fs"
PAGE = REPO / "docs" / "workspace-and-workflows.md"
SRC = REPO / "src" / "pyflightstream"

#: The FS_SCRIPT code to workflow NAME mapping the fixture expects. No
#: entry is a module:function reference: that is the whole point.
CODES = {"010": "unsteady_rotor", "003": "steady"}


def fixture_campaign(fs_version: str = "26.120"):
    """The committed fixture, converted with no Python recipe anywhere."""
    return to_campaign(
        FIXTURE,
        name="rotor",
        fs_version=fs_version,
        fs_exe="C:/fs.exe",
        recipes=CODES,
    )


def rotor_case(**overrides) -> SimCase:
    """One rotor case built by hand, for the per-variable refusals."""
    variables: dict[str, str | float | int | bool] = {
        WORKFLOW_KEY: "unsteady_rotor",
        "VELOCITY": "30.0",
        "RPM": "1200",
        "ROTOR_AXIS": "X",
        "BLADES": "4",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "WINDOW_DEGREES": "90",
    }
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
    )


def test_the_reader_and_the_registry_agree_on_the_types():
    """Every registered workflow is a WORKFLOW cell the reader accepts.

    The reader READS this registry rather than keeping a list of its
    own (`cases.matrix.workflow_types`), so this can only go red if the
    direction is reversed back into a second list.
    """
    accepted = matrix_module.workflow_types()
    assert set(workflow_names()) <= set(accepted), (
        "a registered workflow is not an accepted WORKFLOW cell value, so a matrix "
        "naming it is refused by the reader before the registry is ever consulted"
    )
    assert accepted[0] == matrix_module.LEGACY_WORKFLOW, (
        "LEGACY is not the first accepted value, so a row that wants the established "
        "behaviour is no longer the first thing the refusal offers"
    )


# --- PFS-2025.02: the entity, and the table it lives in ----------------------


def test_a_case_naming_a_workflow_and_no_recipe_produces_a_complete_script():
    """The acceptance's first half: a run TYPE, and no user function."""
    case = fixture_campaign().sims[0].model_copy(update={"point": {"alpha": 0.0}})
    script = Script("26.120")
    build_script(case, script)
    text = script.render()
    assert text.splitlines()[0] == "CREATE_NEW_COORDINATE_SYSTEM", (
        "the workflow did not build the script from its first line; a workflow that "
        f"emits only a tail is not a complete script. Got:\n{text[:200]}"
    )
    for expected in (
        "CREATE_NEW_MOTION ROTARY",
        "SET_MOTION_ROTOR_AXIS",
        "SET_MOTION_ROTOR_RPM",
        "SET_SOLVER_UNSTEADY",
        "INITIALIZE_SOLVER",
        "START_SOLVER",
        "CLOSE_FLIGHTSTREAM",
    ):
        assert expected in text, f"the built script never emits {expected}"
    # The name is still `loads_{point}.txt` here, unrendered: the naming
    # template lives in the WORKSPACE, one layer above, and the campaign
    # loop renders it for the point before the builder runs. What this
    # asserts is that the workflow exported the name the case DECLARES
    # rather than a literal of its own, which is the property that keeps
    # two points of one case from overwriting each other.
    assert "loads_{point}.txt" in text, (
        "the workflow exported a literal rather than the name the case declared"
    )


def test_a_case_naming_both_a_workflow_and_a_recipe_is_refused_naming_both():
    """The acceptance's second half, and the message names BOTH values."""
    case = rotor_case().model_copy(update={"recipe": "my_study.recipes:build"})
    with pytest.raises(CampaignConfigError) as raised:
        select_workflow(case)
    message = str(raised.value)
    assert "unsteady_rotor" in message and "my_study.recipes:build" in message, (
        "the refusal must print BOTH values, so the author can see which one to delete; "
        f"got {message!r}"
    )
    assert "7001" in message, "the refusal does not name the case it refused"


def test_two_registered_workflows_that_disagree_are_refused_naming_both():
    """The other shape of the same conflict, and it is not the same test.

    The WORKFLOW cell and the FS_SCRIPT mapping can BOTH name a
    registered type. Agreement is one statement said twice; disagreement
    is two builders, and a naive `recipe in WORKFLOWS` check treats the
    second as harmless.
    """
    case = rotor_case().model_copy(update={"recipe": "steady"})
    with pytest.raises(CampaignConfigError) as raised:
        select_workflow(case)
    assert "unsteady_rotor" in str(raised.value) and "steady" in str(raised.value)


def test_the_same_type_named_twice_is_not_a_conflict():
    """The fixture's own shape: the WORKFLOW cell and the code agree."""
    assert select_workflow(rotor_case()) == "unsteady_rotor"


def test_a_case_naming_neither_a_workflow_nor_a_recipe_is_refused():
    """A case that names no builder at all is refused, naming the table."""
    case = rotor_case(**{WORKFLOW_KEY: None}).model_copy(update={"recipe": "  "})
    with pytest.raises(CampaignConfigError) as raised:
        select_workflow(case)
    message = str(raised.value)
    assert "unsteady_rotor" in message and "steady" in message, (
        "a case naming neither must be told what the known types ARE, or the refusal "
        f"leaves the author guessing; got {message!r}"
    )
    # The adversarial pass found this assertion missing and the test green
    # with the refusal DELETED: a case naming neither then fell through to
    # the recipe-without-a-workflow refusal, which lists the same types and
    # is a different diagnosis of a different problem.
    assert "names neither a workflow nor a recipe" in message, (
        "the refusal does not say that NEITHER was named; a case with no builder at "
        f"all and a case with a recipe are two different problems. Got {message!r}"
    )


def test_a_legacy_row_still_reaches_its_own_recipe():
    """Every matrix written before the column keeps running as it ran."""
    case = rotor_case(**{WORKFLOW_KEY: matrix_module.LEGACY_WORKFLOW})
    case = case.model_copy(update={"recipe": "my_study.recipes:build"})
    with pytest.raises(CampaignConfigError) as raised:
        select_workflow(case)
    assert "my_study.recipes:build" in str(raised.value)
    assert "names a workflow AND a recipe" not in str(raised.value), (
        "a LEGACY cell means NO workflow, so pairing it with a recipe is the normal "
        "case and must never be reported as a conflict"
    )


def test_a_workflow_resolves_by_table_lookup_and_never_by_import():
    """The separation from a recipe, measured on the CARRIER.

    A reference that would import cleanly through ``resolve_recipe`` is
    refused here, and the module itself is asserted to contain no import
    machinery, so the property is a fact about the code rather than a
    sentence in a docstring.
    """
    with pytest.raises(CampaignConfigError) as raised:
        resolve_workflow("pyflightstream.script.helpers:free_stream")
    assert "unsteady_rotor" in str(raised.value)

    tree = ast.parse((SRC / "cases" / "workflows.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not {"importlib", "import_module", "__import__"} & imported, (
        "cases/workflows.py reaches for the import machinery; a workflow that can be "
        "imported by reference is a recipe with a different name"
    )


def test_every_workflow_in_the_table_satisfies_the_recipe_protocol():
    """The registry entries are callables the campaign loop can call."""
    registry = workflow_registry()
    assert set(registry) == set(WORKFLOWS), (
        "the registry and the table disagree, so a name the table knows would not "
        "resolve at run time"
    )
    assert len(registry) >= 2, "the workflow table is empty; this guard would pass for nothing"
    for name, entry in registry.items():
        check_recipe(name, entry)


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_the_workspace_conventions_are_passed_in_and_never_imported(name):
    """`workspace` sits ABOVE `cases`, so the conventions arrive as data.

    Parametrized over EVERY workflow, which the adversarial pass forced:
    with only the rotor covered, a literal export name restored into the
    steady builder was denied by nothing in this module.
    """
    case = rotor_case(**{WORKFLOW_KEY: name}).model_copy(update={"recipe": name})
    script = Script("26.120")
    build_script(
        case,
        script,
        conventions=WorkflowConventions(outputs=("chosen_by_the_run_layer.txt",)),
    )
    assert "chosen_by_the_run_layer.txt" in script.render(), (
        f"the {name!r} workflow ignored the conventions it was handed and used a name "
        "of its own, so the run layer cannot name anything"
    )


def test_cases_workflows_imports_nothing_above_its_own_layer():
    """The layer rule, at the one module this work adds.

    `tests/test_conventions.py` holds the whole tree to it; this is the
    same rule asserted where the item can see it, because a new module
    at the `cases` layer is exactly where an upward reach is tempting.
    """
    tree = ast.parse((SRC / "cases" / "workflows.py").read_text(encoding="utf-8"))
    above = {"post", "qa", "run", "workspace", "fsi"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pyflightstream"):
            parts = (node.module or "").split(".")
            assert len(parts) < 2 or parts[1] not in above, (
                f"cases/workflows.py imports {node.module}, which sits at or above the "
                "run layer; deferring it to a function body would not change its "
                "direction either"
            )


# --- PFS-2025.18: the build is an input, and an uncovered one is refused -----


def test_the_rotor_coverage_is_derived_from_the_database_and_not_declared():
    """Every covered build carries every command the workflow emits.

    Derived rather than listed: a build registered tomorrow joins the
    range the moment its evidence lands, and a command whose status
    moves narrows it in the same commit.
    """
    registry = CommandRegistry.load()
    rotor = resolve_workflow("unsteady_rotor")
    assert rotor.commands, "the workflow declares no commands, so coverage means nothing"
    covered = covered_builds(rotor)
    assert covered, "no build covers the rotor workflow; the derivation is broken"
    order = [build.canonical for build in known_versions()]
    for canonical in order:
        view = registry.for_version(canonical)
        complete = all(name in view for name in rotor.commands)
        assert (canonical in covered) is complete, (
            f"{canonical} is reported {'covered' if canonical in covered else 'uncovered'} "
            "while its command database says otherwise"
        )
    assert list(covered) == [name for name in order if name in covered], (
        "coverage does not come back in release order, which is the only ordering "
        "authority (commands/_meta.yaml)"
    )


def test_a_build_outside_the_range_is_refused_before_any_emission():
    """The acceptance verbatim: the build, the range, and the command."""
    script = Script("26.100")
    with pytest.raises(WorkflowCoverageError) as raised:
        build_script(rotor_case(), script)
    message = str(raised.value)
    assert "26.100" in message, "the refusal does not name the build it got"
    assert "26.101" in message and "26.123" in message, (
        f"the refusal does not name the range it covers; got {message!r}"
    )
    assert "SET_MOTION_ROTOR_AXIS" in message and "SET_MOTION_ROTOR_RPM" in message, (
        "the refusal does not name the command that forced the range, so the reader "
        f"cannot tell whether a newer build would help; got {message!r}"
    )
    assert script.render().strip() == "", (
        "the workflow emitted before it refused; the acceptance says BEFORE any solver "
        "process starts, and a script half-built is a script somebody runs"
    )


def test_the_refusal_names_the_earlier_vocabulary_only_where_the_build_has_it():
    """A checkable truth on the builds it appears on, not a general claim."""
    with pytest.raises(WorkflowCoverageError) as early:
        build_script(rotor_case(), Script("26.100"))
    assert "SET_MOTION_IS_ROTOR" in str(early.value), (
        "26.100 carries the earlier rotor vocabulary and the refusal never mentions it, "
        "so the reader is not told why a rotor is expressible there and not this way"
    )


def test_a_build_inside_the_range_emits():
    """The other half of the same acceptance sentence."""
    covered = covered_builds(resolve_workflow("unsteady_rotor"))
    assert len(covered) >= 2, "too few covered builds for this guard to mean anything"
    for build in covered:
        script = Script(build)
        build_script(rotor_case(), script)
        assert "SET_MOTION_ROTOR_RPM" in script.render(), (
            f"{build} is reported covered and the workflow emitted no rotor speed on it"
        )


def test_the_steady_workflow_covers_every_registered_build():
    """Coverage is per workflow, not per package."""
    covered = covered_builds(resolve_workflow("steady"))
    assert set(covered) == {build.canonical for build in known_versions()}


def test_the_coverage_refusal_keeps_its_standard_library_base():
    """Catalogued class, package base first, RuntimeError second."""
    assert issubclass(WorkflowCoverageError, PyflightstreamError)
    assert issubclass(WorkflowCoverageError, RuntimeError), (
        "the refusal is about the ENVIRONMENT the script would run in rather than "
        "about an argument, so RuntimeError is the base a caller is entitled to catch"
    )
    assert WorkflowCoverageError.__mro__[1] is PyflightstreamError, (
        "the package base must be the FIRST base, or `except PyflightstreamError` misses it"
    )


def test_the_coverage_refusal_offers_no_override_route():
    """The escape exists one level up, and is a RECORDED waiver."""
    import inspect

    from pyflightstream.cases import workflows

    signature = inspect.signature(workflows.require_coverage)
    assert set(signature.parameters) == {"workflow", "version", "registry"}, (
        "require_coverage grew a parameter; an allow-anyway route here would be a way "
        f"past the guard that leaves no record. Got {list(signature.parameters)}"
    )


def test_no_workflow_declares_a_command_the_database_does_not_know():
    """A typo in the command tuple would silently empty the range."""
    known = set(CommandRegistry.load().commands)
    for name, workflow in WORKFLOWS.items():
        unknown = sorted(set(workflow.commands) - known)
        assert not unknown, (
            f"workflow {name!r} declares {unknown}, which the command database does not "
            "carry at all; coverage would be empty on every build and the cause would "
            "read as a vendor problem"
        )


def test_every_command_a_workflow_declares_is_one_it_really_emits():
    """The tuple is the coverage input, so a stale entry narrows the range.

    Measured against the script the builder actually renders on a
    covered build, rather than against the list itself.
    """
    for name in WORKFLOWS:
        case = rotor_case(**{WORKFLOW_KEY: name}).model_copy(update={"recipe": name})
        script = Script("26.123")
        build_script(case, script)
        emitted = {
            line.split()[0]
            for line in script.render().splitlines()
            if line[:1].isalpha() and line.split()[0].isupper()
        }
        absent = sorted(set(WORKFLOWS[name].commands) - emitted)
        assert not absent, (
            f"workflow {name!r} declares {absent} and its builder never emits them; a "
            "command listed but not emitted narrows the covered range for runs that "
            "would have been fine"
        )


# --- PFS-2025.05: the motion comes off the row -------------------------------


def test_the_rotor_step_emits_the_whole_motion_from_the_row():
    """Motion, its ROTARY type, its coordinate system, its axis, its RPM."""
    script = Script("26.120")
    index = helpers.coordinate_frame(
        script, name="rotor", origin=(0, 0, 0), x_axis=(1, 0, 0), y_axis=(0, 1, 0), label="rotor"
    )
    assert index == 2
    emit_rotor_motion(rotor_case(), script, frame="rotor")
    emitted = [
        line
        for line in script.render().splitlines()
        if line.startswith(("CREATE_NEW_MOTION", "SET_MOTION"))
    ]
    assert emitted == [
        "CREATE_NEW_MOTION ROTARY",
        "SET_MOTION_BOUNDARIES 1 -1",
        "SET_MOTION_MOVING_FRAMES 1 -1",
        "SET_MOTION_COORDINATE_SYSTEM 1 2",
        "SET_MOTION_ROTOR_AXIS 1 X",
        "SET_MOTION_ROTOR_RPM 1 1200.0",
    ], f"the motion block is not what the row says; got {emitted}"


@pytest.mark.parametrize("key", ["RPM", "ROTOR_AXIS"])
def test_a_row_missing_one_value_is_refused_naming_the_pol_and_the_key(key):
    """The acceptance's second half, one key at a time."""
    script = Script("26.120")
    with pytest.raises(CampaignConfigError) as raised:
        emit_rotor_motion(rotor_case(**{key: None}), script, frame=2)
    message = str(raised.value)
    assert "7001" in message, "the refusal does not name the row (the POL is the sim_id)"
    assert key in message, f"the refusal does not name the key it is missing; got {message!r}"
    assert script.render().strip() == "", "the step emitted before it refused"


def test_an_unparsable_rotor_speed_is_refused_as_a_number_and_not_by_the_command():
    """Matrix variables are STRINGS, so the conversion is ours, here.

    Without it the emitter refuses "twelve hundred" naming only
    SET_MOTION_ROTOR_RPM, which sends the author to the command
    reference instead of to the cell they typed.
    """
    script = Script("26.120")
    with pytest.raises(CampaignConfigError) as raised:
        emit_rotor_motion(rotor_case(RPM="twelve hundred"), script, frame=2)
    message = str(raised.value)
    assert "twelve hundred" in message and "RPM" in message and "7001" in message
    assert "rev/min" in message, (
        "the refusal does not state the physical quantity or its unit, which the house "
        f"rule requires of an error message; got {message!r}"
    )


def test_the_moving_boundaries_come_from_the_row_when_it_names_them():
    """A row that names its moving boundaries gets exactly those."""
    script = Script("26.120")
    script.declare_existing(boundaries=6)
    helpers.coordinate_frame(
        script, name="rotor", origin=(0, 0, 0), x_axis=(1, 0, 0), y_axis=(0, 1, 0), label="rotor"
    )
    emit_rotor_motion(rotor_case(MOVING_BOUNDARIES="2,3"), script, frame="rotor")
    text = script.render()
    assert "SET_MOTION_BOUNDARIES 1 2" in text, f"got:\n{text}"
    assert "SET_MOTION_BOUNDARIES 1 2\n2,3" in text, (
        f"the boundaries the row named did not reach the motion; got:\n{text}"
    )


def test_an_empty_moving_boundaries_cell_is_refused_rather_than_read_as_all():
    """`MOVING_BOUNDARIES: ,` is a typo, not a request to move everything."""
    script = Script("26.120")
    with pytest.raises(CampaignConfigError) as raised:
        emit_rotor_motion(rotor_case(MOVING_BOUNDARIES=" , "), script, frame=2)
    assert "MOVING_BOUNDARIES" in str(raised.value)


# --- PFS-2025.08: the degrees-backwards window -------------------------------

#: 1200 rev/min is 20 rev/s; one revolution is 0.05 s; at 1e-4 s per
#: step that is 500 steps, so 360 deg, 1 rev and 500 steps are one span.
RPM = 1200.0
DT = 1e-4
STEPS_PER_REV = 500


def test_the_three_window_forms_produce_the_same_span():
    """Degrees, steps and revolutions are one window said three ways."""
    common = dict(rpm=RPM, delta_time_s=DT, time_iterations=720)
    by_degrees = export_window(degrees=360.0, **common)
    by_steps = export_window(steps=STEPS_PER_REV, **common)
    by_revolutions = export_window(revolutions=1.0, **common)
    assert by_degrees.steps == by_steps.steps == by_revolutions.steps == STEPS_PER_REV


def test_the_record_carries_the_stated_form_and_the_derived_one():
    """A later reader must see which was written and which computed."""
    window = export_window(degrees=90.0, rpm=RPM, delta_time_s=DT, time_iterations=720)
    record = window.record()
    assert record["form"] == "degrees"
    assert record["stated"] == 90.0
    assert record["steps"] == 125
    assert record["degrees"] == pytest.approx(90.0)
    assert record["revolutions"] == pytest.approx(0.25)
    assert window.stated_form == "degrees" and window.stated_value == 90.0


def test_a_window_longer_than_the_run_is_refused_naming_both_numbers():
    """The acceptance verbatim: BOTH numbers in the message."""
    with pytest.raises(CampaignConfigError) as raised:
        export_window(revolutions=3.0, rpm=RPM, delta_time_s=DT, time_iterations=720)
    message = str(raised.value)
    assert "1500" in message and "720" in message, (
        "the refusal must print the derived step count AND the run length, or the "
        f"author cannot tell which to change; got {message!r}"
    )


@pytest.mark.parametrize("form", ["degrees", "revolutions"])
def test_an_angular_window_without_a_rotor_speed_is_refused_naming_the_cause(form):
    """A degree of rotation has no duration until the rotor speed is known."""
    with pytest.raises(CampaignConfigError) as raised:
        export_window(**{form: 90.0}, delta_time_s=DT, time_iterations=720)
    message = str(raised.value)
    assert "rev/min" in message or "rotor speed" in message, (
        f"the refusal does not name the physical cause; got {message!r}"
    )


@pytest.mark.parametrize("form", ["degrees", "revolutions"])
def test_an_angular_window_without_a_time_step_is_refused_naming_the_cause(form):
    with pytest.raises(CampaignConfigError) as raised:
        export_window(**{form: 90.0}, rpm=RPM, time_iterations=720)
    assert "time step" in str(raised.value)


def test_a_window_stated_in_steps_needs_neither_rotor_speed_nor_time_step():
    """Steps are already the solver's own unit, so nothing converts."""
    window = export_window(steps=100, time_iterations=720)
    assert window.steps == 100
    assert window.record()["degrees"] is None, (
        "a step window with no rotor speed cannot state its own degrees, and inventing "
        "one is worse than reporting none"
    )


@pytest.mark.parametrize("kwargs", [{"degrees": 90.0, "steps": 100}, {}])
def test_exactly_one_window_form_is_taken(kwargs):
    """Two forms cannot be checked against each other; none says nothing."""
    with pytest.raises(CampaignConfigError):
        export_window(rpm=RPM, delta_time_s=DT, time_iterations=720, **kwargs)


def test_the_window_is_counted_backwards_from_the_end_of_the_run():
    """Her rule: the last blade passage, not the first."""
    window = export_window(degrees=90.0, rpm=RPM, delta_time_s=DT, time_iterations=720)
    assert window.window_steps() == (596, 720)


def test_a_window_that_rounds_to_nothing_is_refused_rather_than_returned():
    """A zero-step window is a window nobody notices is empty."""
    with pytest.raises(CampaignConfigError):
        export_window(degrees=0.1, rpm=RPM, delta_time_s=DT, time_iterations=720)


def test_the_conversion_agrees_with_the_coupled_driver_that_owns_the_other_copy():
    """Duplicated on purpose; pinned so the two can never disagree.

    `fsi.driver.revolutions_per_step` cannot be imported by the core:
    `fsi.beam` pulls `pyflightstream.extras` and the extras-isolation
    guard keeps the core off optional-extra paths. So the arithmetic is
    written twice and this test is what makes that safe.
    """
    omega = RPM * 2.0 * math.pi / 60.0
    per_step = revolutions_per_step(omega, DT)
    window = export_window(revolutions=1.0, rpm=RPM, delta_time_s=DT, time_iterations=720)
    assert window.steps == pytest.approx(round(1.0 / per_step)), (
        "the window's revolutions-to-steps conversion disagrees with the coupled "
        "driver's, so one of the two published phase schedules is wrong"
    )
    assert window.steps_per_revolution == pytest.approx(1.0 / per_step)


def test_the_window_comes_off_the_row():
    """The whole point: nobody types this twice."""
    window = ExportWindow.from_case(rotor_case())
    assert window.stated_form == "degrees" and window.stated_value == 90.0
    assert window.steps == 125


def test_a_row_stating_two_window_forms_is_refused():
    with pytest.raises(CampaignConfigError):
        ExportWindow.from_case(rotor_case(WINDOW_STEPS="200"))


# --- PFS-2025.06: four reductions, one window --------------------------------


def test_the_reduction_plan_names_four_artefacts_with_the_raw_series_first():
    """The fourth is what makes the other three safe."""
    plan = reduction_plan(rotor_case())
    assert isinstance(plan, ReductionPlan)
    assert plan.artefacts[0] == plan.series_file, (
        "the raw series is not first; it ships BESIDE every reduction and is never "
        "replaced by one, which is her standing qualification on this capability"
    )
    assert len(plan.artefacts) == 4 and len(set(plan.artefacts)) == 4, (
        f"four distinct artefacts are owed; got {plan.artefacts}"
    )


def test_the_averaging_window_is_the_export_window():
    """The lane default, pinned so nobody adds a second window later."""
    assert reduction_plan(rotor_case()).window == ExportWindow.from_case(rotor_case()), (
        "the averaging window and the export window have drifted apart; two windows a "
        "user must keep consistent is a defect generator"
    )


def test_one_blade_passage_is_one_revolution_divided_by_the_blade_count():
    plan = reduction_plan(rotor_case())
    assert plan.revolution_steps == STEPS_PER_REV
    assert plan.period_steps == STEPS_PER_REV // 4
    windows = plan.blade_windows()
    assert len(windows) == 4
    assert windows[-1][1] == 720, "the per-blade split does not end at the end of the run"
    assert windows[0][0] == 720 - STEPS_PER_REV + 1
    # strict=False on purpose: this is a sliding pair over one list, so
    # the second argument is one shorter by construction.
    for earlier, later in zip(windows, windows[1:], strict=False):
        assert later[0] == earlier[1] + 1, "the per-blade windows are not contiguous"


def test_a_row_with_no_blade_count_cannot_ask_for_a_per_blade_split():
    with pytest.raises(CampaignConfigError) as raised:
        reduction_plan(rotor_case(BLADES=None))
    assert "BLADES" in str(raised.value)


def _write_frame(path: Path, step: int, value: float) -> Path:
    """One Tecplot ASCII point zone, two samples, one scalar field."""
    path.write_text(
        'TITLE = "frame"\n'
        'VARIABLES = "X" "Y" "Z" "cp"\n'
        f'ZONE T="t" SOLUTIONTIME={step * DT:.8f}\n'
        f"0.0 0.0 0.0 {value}\n"
        f"1.0 0.0 0.0 {value * 2.0}\n",
        encoding="utf-8",
    )
    return path


def _series(tmp_path: Path, frequency: int = 25):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    frames = [
        _write_frame(frames_dir / f"frame_{index:03d}.dat", index * frequency, float(index))
        for index in range(1, 720 // frequency + 1)
    ]
    return read_timestep_series(frames, order="given", frequency=frequency)


def test_the_four_reductions_compose_out_of_the_post_layer(tmp_path):
    """COMPOSE, never re-implement: the average is PFS-2015.01's one.

    This is the path PFS-2025.06 asks for, executed end to end on
    synthetic frames. What it cannot do is run a solver, and it cannot
    be driven from `run` either: `post` sits ABOVE `run` and `cases` in
    the layer order, so the composition belongs to a post-layer caller
    and the plan is what the case can hand it.
    """
    plan = reduction_plan(rotor_case())
    series = _series(tmp_path)
    assert series.n_frames == 28

    out = tmp_path / "reduced"
    out.mkdir()

    # 1. the raw series, FIRST and unconditionally.
    series_file = write_series(out / plan.series_file, series)
    assert series_file.is_file()

    # 2. the time average, over the export window.
    time_average = blade_passage_average(series, window=plan.window_steps())
    written = [write_reduction(out / plan.artefacts[1], time_average, series_file=series_file)]

    # 3. the phase-locked average: the SAME average, once per passage.
    locked = [
        blade_passage_average(series, window=window)
        for window in passage_windows(series, period_steps=plan.period_steps)
    ]
    assert locked, "no complete passage fell inside the series"
    written.append(write_reduction(out / plan.artefacts[2], locked[-1], series_file=series_file))

    # 4. the per-blade split, one window per blade of the last revolution.
    per_blade = [blade_passage_average(series, window=window) for window in plan.blade_windows()]
    assert len(per_blade) == 4
    written.append(write_reduction(out / plan.artefacts[3], per_blade[0], series_file=series_file))

    assert all(path.is_file() for path in written)
    assert len({series_file, *written}) == 4, "the four artefacts are not four files"
    assert series_file.read_text(encoding="utf-8").splitlines()[0].startswith("step")


def test_the_per_blade_windows_do_not_all_average_the_same_frames(tmp_path):
    """A split that returns four copies of one number is not a split."""
    plan = reduction_plan(rotor_case())
    series = _series(tmp_path)
    means = [
        float(blade_passage_average(series, window=window).fields["cp"][0])
        for window in plan.blade_windows()
    ]
    assert len(set(means)) == 4, (
        f"the four blade windows produced {len(set(means))} distinct averages; a "
        "per-blade split that cannot tell the blades apart hides exactly what it is for"
    )


def test_a_reduction_cannot_be_written_over_the_series_it_came_from(tmp_path):
    """Her file rule, exercised through the plan's own names."""
    plan = reduction_plan(rotor_case())
    series = _series(tmp_path)
    series_file = write_series(tmp_path / plan.series_file, series)
    average = blade_passage_average(series, window=plan.window_steps())
    with pytest.raises(WorkspaceError):
        write_reduction(series_file, average, series_file=series_file, overwrite=True)


def test_nothing_under_src_imports_the_sister_library():
    """The acceptance's last clause, as a walk rather than as a claim."""
    offenders = []
    walked = 0
    for module in sorted(SRC.rglob("*.py")):
        walked += 1
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            if any(name.split(".")[0] == "itaca" for name in names):
                offenders.append(f"{module.relative_to(SRC).as_posix()}:{node.lineno}")
    assert walked >= 40, (
        f"the walk reached only {walked} modules; a walk that found nothing reports "
        "green for the wrong reason"
    )
    assert not offenders, f"these modules import the sister library: {offenders}"


# --- PFS-2025.10: the example IS the test ------------------------------------


def test_the_committed_matrix_drives_the_workflow_with_no_python_recipe():
    """The migrated form: a matrix, a workflow name, and nothing else.

    This is the test the documentation page lifts. Its subject is that
    every one of the fixture's rows builds a complete script with no
    module:function reference anywhere in the call.
    """
    campaign = fixture_campaign()
    assert [sim.sim_id for sim in campaign.sims] == ["7001", "7002"]
    assert not any(":" in sim.recipe for sim in campaign.sims), (
        "a fixture row still names a module:function reference, so the example does "
        "not show what it claims to show"
    )
    built = {}
    for sim in campaign.sims:
        for point in sim.sweep.points():
            script = Script("26.120")
            build_script(sim.model_copy(update={"point": point}), script)
            built[f"rotor/sim_{sim.sim_id}"] = script.render()
    assert set(built) == {"rotor/sim_7001", "rotor/sim_7002"}
    assert "SET_SOLVER_UNSTEADY" in built["rotor/sim_7001"]
    assert "SET_SOLVER_UNSTEADY" not in built["rotor/sim_7002"], (
        "the steady workflow emitted the unsteady time loop, so the two run types are "
        "not distinguished at all"
    )


def test_the_page_carries_the_fixture_byte_for_byte_and_cites_this_module():
    """The lift, guarded from this side.

    `tests/test_docs_example_currency.py` holds the page's FIRST example
    to its fixture. This module owns the second, so the same mechanism
    is applied to it here rather than left to a review.
    """
    text = PAGE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "tests/test_workflows.py" in text, (
        "the page does not name the module its workflow example is lifted from"
    )
    assert "test_the_committed_matrix_drives_the_workflow_with_no_python_recipe" in text, (
        "the page does not cite the executed test, which is what makes the example rot-proof"
    )
    fixture = FIXTURE.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    assert fixture in text, (
        "the matrix on the page is not the fixture this module runs, so a reader "
        "copying it is copying something nothing executes"
    )


def test_the_page_no_longer_says_there_is_no_workflow_object():
    """NFR-11: the page this work invalidates moves in the same session."""
    text = PAGE.read_text(encoding="utf-8").lower()
    assert "there is no workflow object" not in text, (
        "the page still states that no workflow object exists, which this module's "
        "first import contradicts"
    )
    assert "there is no unsteady or rotor workflow" not in text


def test_the_workflow_table_is_documented_where_a_user_would_look():
    """A capability no page mentions satisfies currency and helps nobody."""
    text = PAGE.read_text(encoding="utf-8")
    for name in WORKFLOWS:
        assert name in text, f"workflow {name!r} ships and the page a newcomer reads never names it"


# --- non-vacuity of the fixtures this module rests on ------------------------


def test_the_fixture_is_a_two_row_matrix_that_declares_its_outputs():
    """A degenerate fixture passes every test above for the wrong reason."""
    campaign = fixture_campaign()
    assert len(campaign.sims) == 2
    for sim in campaign.sims:
        assert sim.outputs, f"row {sim.sim_id} declares no outputs"
        assert sim.variables.get(WORKFLOW_KEY), f"row {sim.sim_id} names no workflow"
    assert np.isclose(campaign.sims[0].reynolds, 1.2e6)
    assert {sim.variables[WORKFLOW_KEY] for sim in campaign.sims} == set(WORKFLOWS), (
        "the fixture does not exercise every registered workflow, so a broken builder "
        "could ship green"
    )


# --- PFS-2026.06: the azimuthal shedding option, reachable from the row ------
#
# The direction a relaxed trailing edge sheds its wake in is a field of
# the COMPONENT specification and not a scripting argument, so no
# workflow emits it. The clause this section answers is that the option
# is REACHABLE from the workflow that emits rotor cases: a rotor row
# states it, `emit_rotor_motion` refuses a row that states it wrongly,
# and `rotor_relaxed_trailing_edges` applies it to the specifications a
# component definition carries.

#: The two shapes a component definition carries, in canonical spelling.
FOUR_FIELD_EDGE = "0.5;0.1;0.9;1"
AZIMUTH_EDGE = "0.5;0.1;0.9;1;1"
AXIAL_EDGE = "0.5;0.1;0.9;1;0"


def test_the_azimuthal_option_is_reachable_from_the_rotor_row():
    """The acceptance clause, at its shortest.

    A rotor row writes one cell and the specifications its component
    definition carries come back shedding azimuthally. Nothing is
    emitted, because no command takes the field; what the workflow layer
    owns is turning the row into the text.
    """
    case = rotor_case(ROTOR_SHEDDING="AZIMUTH")
    assert rotor_shedding_direction(case) == "AZIMUTH"
    assert rotor_relaxed_trailing_edges(case, [FOUR_FIELD_EDGE]) == [AZIMUTH_EDGE]


@pytest.mark.parametrize("cell", ["AZIMUTH", "azimuth", "1", " Azimuth "])
def test_the_row_may_spell_the_direction_either_way(cell):
    """A matrix cell is text, and the manual's own spelling is an integer.

    Both are accepted so an author copying the field value out of a
    component definition and an author writing the word get the same
    run.
    """
    assert rotor_shedding_direction(rotor_case(ROTOR_SHEDDING=cell)) == "AZIMUTH"


def test_a_row_that_asks_for_nothing_leaves_every_specification_as_written():
    """Clause two, at the workflow layer.

    Absent is not AXIAL: a row that says nothing about shedding must not
    silently widen a four-field specification, because the component
    file it came from may be read by a build that has four fields.
    """
    case = rotor_case()
    assert rotor_shedding_direction(case) is None
    assert rotor_relaxed_trailing_edges(case, [FOUR_FIELD_EDGE, AXIAL_EDGE]) == [
        FOUR_FIELD_EDGE,
        AXIAL_EDGE,
    ]


def test_the_axial_direction_asked_for_reaches_a_specification_that_states_another():
    """A row CAN turn the azimuthal option back off, on a stated one."""
    case = rotor_case(ROTOR_SHEDDING="AXIAL")
    assert rotor_relaxed_trailing_edges(case, [AZIMUTH_EDGE, FOUR_FIELD_EDGE]) == [
        AXIAL_EDGE,
        FOUR_FIELD_EDGE,
    ]


def test_a_direction_the_row_invents_is_refused_naming_the_cell_and_both():
    """Clause three, at the layer where a matrix author reads it.

    This module's rule: a matrix value is refused by the cell the author
    typed, not by the command. The message therefore names the case, the
    key, the value written and both accepted directions.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_shedding_direction(rotor_case(ROTOR_SHEDDING="diagonal"))
    message = str(raised.value)
    assert "7001" in message, "the refusal does not name the row (the POL is the sim_id)"
    assert "ROTOR_SHEDDING" in message, "the refusal does not name the key"
    assert "'diagonal'" in message, "the refusal does not name the value the row wrote"
    for accepted in ("AXIAL", "AZIMUTH", "0", "1"):
        assert accepted in message, f"the refusal does not name {accepted!r}; got {message!r}"


def test_the_rotor_emitter_refuses_that_row_before_it_emits_anything():
    """The option is reachable FROM THE EMITTER, which is what makes it a guard.

    `emit_rotor_motion` cannot emit the direction, and reads it anyway:
    a row declaring ROTOR_SHEDDING: diagonal that built a perfectly good
    script would be told nothing at all, and the author would discover
    the typo by getting the wrong wake. The refusal lands before the
    first emission, like every other read in that function.
    """
    script = Script("26.120")
    with pytest.raises(CampaignConfigError) as raised:
        emit_rotor_motion(rotor_case(ROTOR_SHEDDING="diagonal"), script, frame=2)
    assert "ROTOR_SHEDDING" in str(raised.value)
    assert script.render().strip() == "", "the step emitted before it refused"


def test_a_rotor_row_asking_for_the_azimuth_direction_still_builds_its_script():
    """And the script gains NOTHING, because no command carries the field.

    The complement of the refusal above: a well-formed direction changes
    the specifications a component definition carries and changes no
    line of the script, so a build that reads four fields runs this case
    exactly as it always did.
    """
    plain = Script("26.120")
    build_script(rotor_case(), plain)
    shedding = Script("26.120")
    build_script(rotor_case(ROTOR_SHEDDING="AZIMUTH"), shedding)
    assert shedding.render() == plain.render(), (
        "the shedding direction reached the script; it is a component-file field and "
        "no registered build takes it as a scripting argument"
    )


def test_a_specification_the_package_cannot_read_names_which_one_of_how_many():
    """A component definition carries several, so 'unreadable' is not enough."""
    case = rotor_case(ROTOR_SHEDDING="AZIMUTH")
    with pytest.raises(CampaignConfigError) as raised:
        rotor_relaxed_trailing_edges(case, [FOUR_FIELD_EDGE, "0.5;0.1;0.9", AZIMUTH_EDGE])
    message = str(raised.value)
    assert "7001" in message
    assert "number 2 of 3" in message, (
        f"the refusal does not say which specification of how many; got {message!r}"
    )


def test_the_direction_the_row_names_is_the_vocabulary_the_helper_defines():
    """Non-vacuity: the two layers cannot drift into different vocabularies.

    Every test above names its values as literals, so the workflow layer
    could grow a third direction and they would all still pass.
    """
    assert set(helpers.RELAXED_SHEDDING_DIRECTIONS) == {"AXIAL", "AZIMUTH"}
    assert ROTOR_SHEDDING_VARIABLE == "ROTOR_SHEDDING"
    for token in helpers.RELAXED_SHEDDING_DIRECTIONS:
        assert rotor_shedding_direction(rotor_case(ROTOR_SHEDDING=token)) == token


def test_one_specification_passed_without_its_list_is_refused_by_shape():
    """Found by the adversarial pass: a bare string is a sequence.

    `rotor_relaxed_trailing_edges(case, "0.5;0.1;0.9;1")` iterated the
    text one character at a time and refused "number 1 of 13", which
    names the wrong thing entirely. The remedy is stated: put it in a
    list.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_relaxed_trailing_edges(rotor_case(), FOUR_FIELD_EDGE)
    message = str(raised.value)
    assert "one character at a time" in message
    assert repr(FOUR_FIELD_EDGE) in message


def test_something_that_cannot_be_iterated_is_refused_and_not_left_to_len():
    """No bare standard-library error out of a public name (FR-39).

    The second half of the same adversarial finding: the signature says
    sequence and `len()` on anything else leaves a raw TypeError.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_relaxed_trailing_edges(rotor_case(), 4)
    assert "cannot be iterated" in str(raised.value)


def test_a_generator_of_specifications_is_read_rather_than_refused():
    """The lazy form works, which is why `len` had to go.

    A caller filtering a component definition hands in a generator; it
    has no length, and the count in the unreadable-specification message
    is what needed one.
    """
    case = rotor_case(ROTOR_SHEDDING="AZIMUTH")
    produced = (edge for edge in [FOUR_FIELD_EDGE, AXIAL_EDGE])
    assert rotor_relaxed_trailing_edges(case, produced) == [AZIMUTH_EDGE, AZIMUTH_EDGE]


def test_the_specification_restater_refuses_a_bad_row_rather_than_defaulting():
    """MUTANT N1, found by an adversarial pass on 2026-08-20.

    `rotor_relaxed_trailing_edges` reads the row's direction through
    `rotor_shedding_direction`, and that refusal is asserted at the
    reader. It was NOT asserted here, so wrapping this call in
    `try: ... except CampaignConfigError: direction = None` left the
    whole module green: a row that typed the direction wrong would have
    had its specifications restated at the DEFAULT direction, silently,
    and the axial default is exactly the value a rotor author asking for
    azimuth would not notice.

    The complement is asserted too, because a case that only proves a
    raise proves nothing about the path it guards: a well-formed row
    still restates.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_relaxed_trailing_edges(rotor_case(ROTOR_SHEDDING="diagonal"), [FOUR_FIELD_EDGE])
    message = str(raised.value)
    assert "ROTOR_SHEDDING" in message, "the refusal does not name the key"
    assert "'diagonal'" in message, "the refusal does not name the value the row wrote"

    good = rotor_relaxed_trailing_edges(rotor_case(ROTOR_SHEDDING="AZIMUTH"), [FOUR_FIELD_EDGE])
    assert good == [AZIMUTH_EDGE], (
        "the well-formed row stopped restating, so the case above would pass on a "
        "function that refuses everything"
    )
