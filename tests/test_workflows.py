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
to SERIALISE against the command database of every build it COVERS,
which is five of the nine registered rather than all nine, because the
rotor motion vocabulary only exists from 26.101 onward. Serialising is
not the same fact as being accepted by a solver, and the
acceptance clause of PFS-2025.06 that asks for one real unsteady case
producing all four outputs needs a licensed seat that was not open.
"""

from __future__ import annotations

import ast
import math
import warnings
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._fsm import (
    MESH_MARKER,
    MeshReadError,
    boundary_labels,
    boundary_names,
)
from pyflightstream.cases import (
    CampaignConfigError,
    ReferenceData,
    SimCase,
    SolverSettings,
    SweepAxis,
    check_recipe,
)
from pyflightstream.cases import matrix as matrix_module
from pyflightstream.cases import workflows as workflows_module
from pyflightstream.cases.matrix import to_campaign
from pyflightstream.cases.workflows import (
    ADVANCE_RATIO_VARIABLE,
    DELTA_THETA_VARIABLE,
    GEOMETRY_VARIABLE,
    PERIODIC_COPIES_VARIABLE,
    REVOLUTIONS_VARIABLE,
    ROTOR_SHEDDING_VARIABLE,
    RPM_SIGN_VARIABLE,
    SIMULATION_SUFFIX,
    SYMMETRY_VARIABLE,
    WORKFLOW_KEY,
    WORKFLOWS,
    ExportWindow,
    ReductionPlan,
    WorkflowConventions,
    WorkflowCoverageError,
    accepted_symmetry,
    build_script,
    covered_builds,
    emit_rotor_motion,
    export_window,
    reduction_plan,
    resolve_workflow,
    rotor_relaxed_trailing_edges,
    rotor_shedding_direction,
    rotor_speed,
    rotor_time_stepping,
    select_workflow,
    workflow_names,
    workflow_registry,
)
from pyflightstream.commands import ArgType, CommandRegistry
from pyflightstream.fsi.driver import revolutions_per_step
from pyflightstream.post.reductions import write_reduction, write_series
from pyflightstream.post.unsteady import (
    blade_passage_average,
    passage_windows,
    read_timestep_series,
)
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    helpers,
)
from pyflightstream.versions import known_versions
from pyflightstream.workspace import WorkspaceError

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "workflow_rotor_matrix.fs"
PAGE = REPO / "docs" / "workspace-and-workflows.md"
SRC = REPO / "src" / "pyflightstream"

#: The FS_SCRIPT code to workflow NAME mapping the fixture expects. No
#: entry is a module:function reference: that is the whole point.
CODES = {"010": "unsteady_rotor", "003": "steady", "020": "unsteady"}


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


def _case_for(name: str) -> SimCase:
    """One case of the shape run type ``name`` accepts.

    Read from `GOLDEN_CASES`, which is the same table the byte-identity
    goldens are rendered from. Sharing that table is the point: a
    selector with its own private mapping could quietly hand two types
    the same shape and restore the coverage gap the parametrization
    above was added to close, and this one cannot, because the goldens
    would have to degenerate with it and they are pinned byte for byte.
    """
    return GOLDEN_CASES[name]["bare"]().model_copy(update={"recipe": name})


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_the_workspace_conventions_are_passed_in_and_never_imported(name):
    """`workspace` sits ABOVE `cases`, so the conventions arrive as data.

    Parametrized over EVERY workflow, which the adversarial pass forced:
    with only the rotor covered, a literal export name restored into the
    steady builder was denied by nothing in this module.

    The case comes from `_case_for` rather than from `rotor_case` under
    a borrowed name: the rotorless type REFUSES a rotor key, on purpose,
    so a shared rotor case would refuse before this test could assert
    anything about conventions.
    """
    case = _case_for(name)
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
        case = _case_for(name)
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
    assert [sim.sim_id for sim in campaign.sims] == ["7001", "7002", "7003"]
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
    assert set(built) == {"rotor/sim_7001", "rotor/sim_7002", "rotor/sim_7003"}
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


def test_the_fixture_is_a_three_row_matrix_that_declares_its_outputs():
    """A degenerate fixture passes every test above for the wrong reason."""
    campaign = fixture_campaign()
    assert len(campaign.sims) == len(WORKFLOWS)
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


# --- PFS-2025.02.02: the case geometry is opened, first -----------------------


def steady_case(**overrides) -> SimCase:
    """One steady case built by hand, for the geometry and symmetry reads."""
    variables: dict[str, str | float | int | bool] = {
        WORKFLOW_KEY: "steady",
        "VELOCITY": "30.0",
    }
    geometry = overrides.pop("geometry", None)
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7002",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        geometry=geometry,
    )


def rendered(case: SimCase, build: str = "26.120") -> str:
    """Build one case and return the whole script text."""
    script = Script(build)
    build_script(case, script)
    return script.render()


def steady_case_full() -> SimCase:
    """A steady case exercising the settings branches ``bare`` leaves out.

    ``bare`` carries one alpha and the default :class:`SolverSettings`,
    so two conditional emissions never fire: the sideslip line (``point``
    has no ``beta``) and the thread-count line (``max_threads`` is None).
    A V and V pass measured that, and it matters because the goldens are
    the release's forward regression detector: a mutation inside the
    ``sideslip is not None`` branch was invisible to the whole
    population.

    THE SECOND OUTPUT IS CARRIED AND NOT REACHED, said plainly because an
    earlier version of this docstring claimed it exercised "any output
    index above zero" and it does not. Both builders call ``_output`` at
    index 0 only, so ``forces_a+02.0.txt`` appears in no golden and
    ``return names[index]`` is an equivalent mutant today. It is kept
    because a case declaring two outputs is a legitimate shape and the
    day a builder exports a second file the golden moves; it buys
    nothing right now.

    Like ``bare`` it names NONE of the three 0.8.1 keys, so it belongs to
    the same claim.
    """
    return steady_case().model_copy(
        update={
            "point": {"alpha": 2.0, "beta": 3.0},
            "outputs": ["loads_a+02.0.txt", "forces_a+02.0.txt"],
            "solver": SolverSettings(iterations=800, convergence=1e-6, max_threads=8),
        }
    )


def rotor_case_full() -> SimCase:
    """A rotor case in the other window form, with the optional cells set.

    ``WINDOW_STEPS`` rather than ``WINDOW_DEGREES``, plus ``ROTOR_ORIGIN``
    and ``MOVING_BOUNDARIES``, which are the rotor branches ``bare`` does
    not reach. Names none of the three 0.8.1 keys.

    EVERY FIELD IS NON-DEGENERATE ON PURPOSE, including the axis and the
    TIME LOOP. Two versions of this case failed that in turn. The first
    left ``ROTOR_AXIS`` at the shared default of ``X``, so all 28 goldens
    carried ``AXIS 1 X`` and a builder that hardcoded ``X`` passed every
    one of them. The second left ``DELTA_TIME`` and ``TIME_ITERATIONS``
    at the shared values, which the only rotor fixture in the repository
    also uses, so nothing anywhere disagreed and hardcoding BOTH survived
    the entire tier 1 suite: every rotor row's time loop was decorative
    and the run reported a machine nobody described.
    A rotor row asking for ``Z`` and spinning about ``X`` converges,
    exports and reports numbers for a machine nobody described, which is
    the failure class this release exists to remove. The origin is
    likewise off-axis in all three components rather than only in ``z``.
    """
    return rotor_case(
        WINDOW_DEGREES=None,
        WINDOW_STEPS="36",
        ROTOR_AXIS="Z",
        ROTOR_ORIGIN="0.1,0.2,0.3",
        MOVING_BOUNDARIES="1,2",
        DELTA_TIME="0.00025",
        TIME_ITERATIONS="1600",
    )


def _golden_fluid():
    """The resolved state the 0.9.0 golden shapes carry.

    Written as literals rather than by calling the resolver, so a golden
    cannot follow a change in the physics: a regression detector that
    recomputes its own expectation detects nothing. These are the values
    the resolver produces for ``MACH:0.20, REmi:5.5`` against a 1.0 m
    reference, and if the resolver stops producing them the goldens move
    and a reader is asked why.
    """
    from pyflightstream.cases import FluidState

    return FluidState(
        velocity_m_per_s=68.0588,
        density_kg_m3=1.44598,
        pressure_pa=119603.0,
        temperature_k=288.15,
        viscosity_pa_s=1.7893e-05,
        sonic_velocity_m_per_s=340.294,
        heat_capacity_ratio=1.4,
        source="solved-from-reynolds",
        reference_length_m=1.0,
    )


def steady_case_resolved() -> SimCase:
    """A steady case carrying BOTH 0.9.0 emissions, for the goldens.

    WHY THIS SHAPE EXISTS, and it is the finding that produced it. A QA
    pass measured that no golden carried a ``REF_`` line or a
    ``FLUID_PROPERTIES`` block, so the two emissions this release adds
    had no byte-exact coverage on any build: they were asserted only by
    line membership, which cannot see ordering, spacing, phase placement
    or duplication.

    That is the SAME hole that hid the original defect. The reference
    resolved, bound onto the case and reached no emitted line for a whole
    release, and the reason nobody noticed is that not one golden carried
    a ``REF_`` line to go missing. Fixing the emission without closing
    the hole would leave the next such defect equally invisible.
    """
    from pyflightstream.cases import ReferenceData

    return steady_case().model_copy(
        update={
            "reference": ReferenceData(area=10.0, length=1.2),
            "fluid": _golden_fluid(),
        }
    )


def rotor_case_resolved() -> SimCase:
    """The same, on the rotor branch, which had even less coverage."""
    from pyflightstream.cases import ReferenceData

    return rotor_case().model_copy(
        update={
            "reference": ReferenceData(area=10.0, length=1.2),
            "fluid": _golden_fluid(),
        }
    )


# --- PFS-2028.01: the case shapes of a run that turns nothing ---------------
#
# THREE DIFFERENT, NON-DEGENERATE CLOCKS, and the arbitrariness is the
# point. Reusing 0.0001 and 720, which `rotor_case` and fixture row 7001
# both carry, would let a builder that hardcoded the clock render every
# golden correctly. That is not hypothetical here: two earlier versions
# of the rotor fixture did exactly that, and the note on
# `rotor_case_full` records both.


def unsteady_case(**overrides) -> SimCase:
    """The bare shape: a free stream, a clock, and nothing turning."""
    variables: dict[str, str | float | int | bool] = {
        WORKFLOW_KEY: "unsteady",
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.00025",
        "TIME_ITERATIONS": "480",
    }
    geometry = overrides.pop("geometry", None)
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7003",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0},
        geometry=geometry,
    )


def unsteady_case_full() -> SimCase:
    """A third clock again, and the optional cells a rotorless row may set."""
    return unsteady_case(
        DELTA_TIME="0.0005",
        TIME_ITERATIONS="240",
        LOG_OUTPUT="2",
        **{"OUTPUTS": "loads_a+00.0.txt, loads_a+00.0_log.txt"},
    ).model_copy(update={"outputs": ["loads_a+00.0.txt", "loads_a+00.0_log.txt"]})


def unsteady_case_resolved() -> SimCase:
    """The 0.9.0 shape: a resolved fluid state beside a fourth clock."""
    return unsteady_case(DELTA_TIME="0.00125", TIME_ITERATIONS="96").model_copy(
        update={
            "reference": steady_case_resolved().reference,
            "condition": steady_case_resolved().condition,
        }
        if hasattr(steady_case_resolved(), "condition")
        else {"reference": steady_case_resolved().reference}
    )


#: The case shapes the byte-identity goldens are rendered from, by
#: workflow. The SINGLE HOME: ``scripts/gen_workflow_goldens.py`` imports
#: this table, so the generator and the guard cannot disagree about what
#: a historical case is.
GOLDEN_CASES = {
    "steady": {
        "bare": steady_case,
        "full": steady_case_full,
        # 0.9.0: carries a reference AND a resolved fluid state, so the
        # two emissions this release adds have byte-exact goldens on
        # every build rather than line-membership assertions only.
        "resolved": steady_case_resolved,
    },
    "unsteady": {
        "bare": unsteady_case,
        "full": unsteady_case_full,
        "resolved": unsteady_case_resolved,
    },
    "unsteady_rotor": {
        "bare": rotor_case,
        "full": rotor_case_full,
        "resolved": rotor_case_resolved,
    },
}

#: The (workflow, build) pairs that are expected to REFUSE rather than
#: render, with the refusal text pinned as the golden.
#:
#: Declared as data because the alternative is a laundering path. The
#: generator writes a refusal golden ONLY for a pair listed here and
#: aborts on any other failure; without that, a defect making a builder
#: raise on every build would be turned into nine committed "expected"
#: refusals by one regeneration, and the suite would pass over it.
#:
#: The one entry is the registered over-approximation: ``covered_builds``
#: reports 25.000 as covered by ``steady`` because that build's database
#: carries every command the workflow always emits, while
#: ``initialize_solver`` refuses that edition's grammar outright. When
#: that is decided either way, this set goes empty in the same commit.
EXPECTED_REFUSALS = {("steady", "25.000"), ("unsteady", "25.000")}

#: Every workflow crossed with every case shape and every build it
#: covers: the population the byte-identity claim was always about.
GOLDEN_RENDERS = [
    (name, label, build)
    for name in sorted(GOLDEN_CASES)
    for label in sorted(GOLDEN_CASES[name])
    for build in covered_builds(WORKFLOWS[name])
]

GOLDEN_WORKFLOWS = Path(__file__).parent / "goldens" / "workflows"


def golden_name(name: str, label: str, build: str) -> str:
    """The committed file name for one rendered pair.

    Double underscores rather than a dot and an at sign. The first
    scheme joined the parts that way and reads as an EMAIL ADDRESS to
    the tier 1 personal-identifier guard, which fired on the receipt
    file that lists these names. It was right to: the shape it protects
    against is a dotted word, an at sign and a dotted domain, which is
    exactly what that scheme produced. Exempting the guard would have
    weakened a check that keeps addresses off a public remote in order
    to keep a file name cosmetic.
    """
    return f"{name}__{label}__{build}.txt"


def render_or_refusal(name: str, label: str, build: str) -> str:
    """Return one workflow's render on one build, or its refusal text.

    Imported by ``scripts/gen_workflow_goldens.py`` rather than copied
    into it. An earlier version duplicated these lines there and
    justified it as "clearer duplicated than imported across the
    tests/scripts boundary", which refuted itself: the generator already
    imports this module for the case builders.

    The ``except`` is narrow on purpose. A builder refusing is behaviour
    worth pinning; a ``TypeError`` from a renamed helper is a broken
    generator, and freezing its message as evidence would hide the break.
    """
    case = GOLDEN_CASES[name][label]()
    # THE PREMISE, ASSERTED RATHER THAN NAMED IN A TITLE. The guard is
    # called "a case naming none of the three keys", and nothing checked
    # that the case names none of them. Both builders come from shared
    # fixtures that forty other cases override, so the default variable
    # dict is a live edit surface: adding `SYMMETRY: NONE` to a default
    # leaves every golden byte-identical, because NONE is what the
    # builder already emits, and the guard's subject silently becomes
    # the opposite of its name. Measured by a QA pass, green.
    declared = {GEOMETRY_VARIABLE, SYMMETRY_VARIABLE, PERIODIC_COPIES_VARIABLE}
    named = declared & set(case.variables)
    assert not named and case.geometry is None, (
        f"the {name} '{label}' case declares {sorted(named) or 'a geometry'}, so this "
        "population is no longer the historical one and the byte-identity claim it "
        "backs is about a different matrix than the one it names"
    )
    try:
        return rendered(case, build)
    except (CampaignConfigError, CommandArgumentError, WorkflowCoverageError) as error:
        return f"REFUSED {type(error).__name__}\n{error}\n"


@pytest.mark.parametrize(("name", "label", "build"), GOLDEN_RENDERS)
def test_a_case_naming_none_of_the_three_keys_renders_its_committed_bytes(name, label, build):
    """THE GUARD BEHIND THE RELEASE'S OWN HEADLINE SAFETY CLAIM.

    0.8.1 says a matrix naming none of ``GEOMETRY``, ``SYMMETRY`` or
    ``PERIODIC_COPIES`` renders byte for byte as it always did, and until
    this case nothing measured it. The claim cited the 23 files in
    ``tests/goldens/`` and the 18 in ``tests/fixtures/``; not one of those
    41 is produced by a workflow builder, so they could not have changed
    whatever the builders did.

    Measured rather than argued: a QA pass inserted one extra
    ``script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")`` into
    ``_build_steady``, which changes the bytes of every geometry-less
    steady render on every build, and the whole tier 1 suite stayed
    GREEN. The nearest existing guard asserts line 0 and ``"OPEN" not in
    lines``, which that mutant satisfies.

    A build a workflow COVERS but cannot BUILD is pinned as its refusal
    text instead of a script. That is not a curiosity: ``covered_builds``
    reports 25.000 as covered by ``steady`` because the database carries
    every command the workflow always emits, while the initialization
    helper refuses that edition outright. Pinning the refusal keeps the
    over-approximation visible and its wording fixed; the CHANGELOG's
    "Known gaps" states it as a shipped limit.

    Regenerate with ``python scripts/gen_workflow_goldens.py`` and read
    the diff: a change here is a change to every script this package
    builds for every user who has not touched their matrix.
    """
    golden = GOLDEN_WORKFLOWS / golden_name(name, label, build)
    assert golden.is_file(), (
        f"no committed render for {name} ({label}) on {build}. A build joins "
        "covered_builds the moment its evidence lands, so this fires on a newly "
        "registered build before anyone notices the population grew: regenerate with "
        "python scripts/gen_workflow_goldens.py and review the new file"
    )
    actual = render_or_refusal(name, label, build)
    # read_bytes and not read_text: universal-newline translation would
    # hide a line-ending rewrite from a comparison whose whole subject is
    # the bytes. The sibling guard in test_script.py asserts the same
    # tree carries no carriage return at all.
    assert actual.encode("utf-8") == golden.read_bytes(), (
        f"the {name} workflow renders different bytes on {build} than the committed "
        "golden. Every matrix that names none of the three 0.8.1 keys just changed "
        "script, which is the property the release promised would hold"
    )
    # THE REFUSAL SET IS ASSERTED, not merely tolerated. Without this, a
    # defect that made a builder raise on every build could be turned
    # into committed "expected" refusals by one regeneration, and every
    # assertion above would still pass: the goldens would match, the
    # population would match, and the tree would record the defect as the
    # intended behaviour.
    refused = actual.startswith("REFUSED")
    assert refused == ((name, build) in EXPECTED_REFUSALS), (
        f"{name} on {build} "
        + ("refuses and is not a declared refusal" if refused else "")
        + ("renders and is declared as a refusal" if not refused else "")
        + f"; EXPECTED_REFUSALS holds {sorted(EXPECTED_REFUSALS)}"
    )


def test_the_render_population_is_not_empty_and_covers_both_workflows():
    """The non-vacuity guard for the parametrization above.

    ``GOLDEN_RENDERS`` is computed from ``covered_builds``, so a defect
    that emptied or narrowed it would silently reduce the case above to
    nothing while every remaining case still passed. A parametrized guard
    over a computed population needs the population asserted.
    """
    assert len(GOLDEN_RENDERS) >= 41, (
        f"the render population shrank to {len(GOLDEN_RENDERS)}; it was 28 when the "
        "goldens were committed and 41 once the 0.9.0 'resolved' shape joined, and "
        "it may only GROW as builds register or shapes are added"
    )
    assert {name for name, _, _ in GOLDEN_RENDERS} == set(WORKFLOWS), (
        "a shipped workflow renders on no build at all, so the byte-identity guard "
        "covers it vacuously"
    )
    assert {label for _, label, _ in GOLDEN_RENDERS} == {"bare", "full", "resolved"}, (
        "a case shape vanished from the table, so the branches it was added to reach "
        "are covered by nothing again"
    )
    # `*.txt` only: the directory also carries `RECEIPT-v0.8.0.md`, the
    # one-time measurement that the same cases rendered identically
    # against the released tag. It is evidence, not a golden, and no test
    # reads it, so it must not join the population it documents.
    committed = {path.name for path in GOLDEN_WORKFLOWS.glob("*.txt")}
    assert committed == {golden_name(*row) for row in GOLDEN_RENDERS}, (
        "the committed goldens and the covered population disagree; a stale golden for "
        "a build no longer covered would sit there asserted by nothing"
    )
    # Every declared refusal names a pair that is actually rendered, so a
    # stale entry cannot sit here excusing a pair that no longer exists.
    assert EXPECTED_REFUSALS <= {(name, build) for name, _, build in GOLDEN_RENDERS}, (
        "EXPECTED_REFUSALS names a (workflow, build) pair outside the rendered "
        "population, so it excuses nothing and hides the next real refusal"
    )


#: A staged simulation path of the shape the campaign loop writes: the
#: case's OWN copy under its sim directory, not the library original.
STAGED = "runs/7002/inputs/rotor_sector.fsm"


def test_the_defect_itself_a_geometry_now_changes_the_script():
    """THE REPRODUCTION. Two cases that differed only in their geometry
    rendered BYTE-IDENTICAL scripts, on both builders: no OPEN, no
    NEW_SIMULATION, no import of any kind. The run layer had already
    staged the file and hashed it into the record, so the manifest named
    a mesh the script never opened and the solver solved whatever it had
    in memory.

    This case is the one that goes red on the shipped 0.8.0 body, and it
    is written as a comparison rather than as an `"OPEN" in text` so it
    keeps failing for the original reason if the emission ever moves.
    """
    without = rendered(steady_case())
    with_geometry = rendered(steady_case(geometry=STAGED))
    assert with_geometry != without, (
        "a case carrying a geometry renders the same script as the same case without "
        "one, so nothing opens the mesh and the solver runs on whatever it has"
    )
    assert STAGED in with_geometry, "the script never names the staged geometry"


@pytest.mark.parametrize(
    ("workflow", "case"),
    [
        ("steady", steady_case(geometry=STAGED)),
        ("unsteady_rotor", rotor_case()),
    ],
)
def test_both_builders_open_the_geometry_before_anything_else(workflow, case):
    """OPEN is the FIRST line, on both run types.

    Not merely present: OPEN replaces the whole simulation state, so a
    coordinate system, a motion or a solver setting emitted before it
    would be discarded by it with nothing said, and the rotor's rotary
    motion would then cite a frame that no longer exists.
    """
    opened = case.model_copy(update={"geometry": STAGED})
    lines = rendered(opened, "26.123").splitlines()
    assert lines[0] == "OPEN", (
        f"the {workflow} workflow emits {lines[0]!r} first; OPEN discards whatever "
        "preceded it, so anything before it is silently thrown away"
    )
    assert lines[1] == STAGED, "OPEN does not name the staged geometry on its value line"


def test_the_path_opened_is_the_one_the_case_carries_at_build_time():
    """The STAGED copy, never the library original.

    ``inputs_sha256`` in the run record is the hash of the staged bytes,
    so opening anything else breaks the pairing between the digest a
    record publishes and the bytes the solver read, and breaks it
    silently. The campaign loop rewrites ``case.geometry`` to the staged
    path before the builder runs; the builder's job is to open what it
    is given and nothing else.
    """
    library = "campaign/inputs/geometries/rotor_sector.fsm"
    text = rendered(steady_case(geometry=STAGED))
    assert STAGED in text
    assert library not in text
    assert rendered(steady_case(geometry=library)) != text, (
        "the builder renders the same script for two different geometry paths, so it "
        "is not opening the path the case carries"
    )


def test_a_case_naming_no_geometry_emits_nothing_new():
    """The byte-unchanged property, which is what makes this a patch.

    Every shipped fixture and every committed golden names no geometry,
    so this is the case that has to be unchanged: not "OPEN is absent"
    but "the first line is the one it always was".
    """
    lines = rendered(steady_case()).splitlines()
    assert lines[0] == "SET_FREESTREAM CONSTANT"
    assert "OPEN" not in lines
    rotor = rendered(rotor_case(), "26.123").splitlines()
    assert rotor[0] == "CREATE_NEW_COORDINATE_SYSTEM"
    assert "OPEN" not in rotor


@pytest.mark.parametrize(
    "geometry",
    ["runs/7002/inputs/blade.stl", "runs/7002/inputs/blade.obj", "runs/7002/inputs/blade"],
)
def test_a_suffix_that_is_not_fsm_is_refused_with_the_documented_route(geometry):
    """A raw mesh is refused rather than imported, and the refusal routes.

    IMPORT's FIRST argument is the length units of the mesh file
    (SRC-003 p.307) and no matrix cell declares them, so importing here
    would mean defaulting a unit: a body of the wrong size, solved,
    exported and reported without a word. That is the class of defect
    this release exists to remove, so the narrowing is deliberate and
    the refusal names the route the user already has.
    """
    script = Script("26.120")
    with pytest.raises(CampaignConfigError) as raised:
        build_script(steady_case(geometry=geometry), script)
    message = str(raised.value)
    assert geometry in message, "the refusal does not name the file that was refused"
    assert SIMULATION_SUFFIX in message, "the refusal does not name the suffix that works"
    assert "units" in message.lower(), "the refusal does not name the physical cause"
    assert "docs/mesh-inputs.md" in message, "the refusal does not name the documented route"
    assert GEOMETRY_VARIABLE in message, (
        "the refusal describes the resolved file and never names the CELL the author "
        "typed, so they read back a path they did not write"
    )
    # `_open_geometry`'s docstring promises the script is left exactly as
    # it was, and that promise was asserted NOWHERE: a QA pass inserted
    # the OPEN emission immediately BEFORE the raise and the suite stayed
    # green. Two sibling refusals in this module already assert the empty
    # render; this is the third.
    assert script.render().strip() == "", (
        "the refusal left lines in the script, so a caller that catches it and keeps "
        "building emits a half-open geometry"
    )


def test_the_documented_route_the_refusal_names_really_exists():
    """The refusal points at a page, so the page has to be there.

    A route named in an error message and deleted from the repository is
    a worse answer than no route at all, and nothing else in the suite
    reads this pair.
    """
    page = REPO / "docs" / "mesh-inputs.md"
    assert page.is_file(), f"{page} is named in a refusal and does not exist"
    body = page.read_text(encoding="utf-8")
    assert ".fsm" in body, "the page the refusal routes to does not mention .fsm at all"
    # THE ANCHOR, and this half is why the guard was widened. The refusal
    # tells the user which sentence to look for, and for one commit it
    # quoted "A workflow opens route 1 only" while the page said "A
    # WORKFLOW TAKES ROUTE 1 ONLY". Both halves were written together and
    # neither was wrong alone; the pair sent a blocked user searching a
    # long page for a string that was not on it. Asserting that the file
    # exists and says ".fsm" could not see it.
    assert workflows_module._MESH_PAGE_ANCHOR in body, (
        f"the refusal tells the user to look on {page.name} under "
        f"{workflows_module._MESH_PAGE_ANCHOR!r}, and that sentence is not on the page"
    )
    refusal = ""
    try:
        rendered(steady_case(geometry="runs/7002/inputs/blade.stl"))
    except CampaignConfigError as error:
        refusal = str(error)
    assert workflows_module._MESH_PAGE_ANCHOR in refusal, (
        "the refusal no longer quotes the anchor this guard pins, so the pair it "
        "protects is no longer the pair that ships"
    )


def test_the_suffix_is_read_case_insensitively():
    """``.FSM`` off a file system that upper-cased it still opens.

    A user staging a file from a case-preserving share meets this and
    nothing about their simulation is different.
    """
    assert rendered(steady_case(geometry="runs/7002/inputs/rotor_sector.FSM"))


def test_open_is_not_declared_in_any_workflow_command_tuple():
    """A sometimes-emitted command must not narrow the derived coverage.

    ``Workflow.commands`` is the input to :func:`covered_builds`, and
    its own docstring states the rule: a command emitted only for some
    cases must not be listed, because listing it narrows the range for
    every run that never reaches it. OPEN is emitted only for a case
    that names a geometry.
    """
    for name, workflow in WORKFLOWS.items():
        assert "OPEN" not in workflow.commands, (
            f"workflow {name!r} declares OPEN, which it emits only for a case naming a "
            "geometry; the coverage range would then exclude builds that can run every "
            "case this workflow actually builds"
        )


def test_open_is_available_on_every_build_the_workflows_cover():
    """The complement of the case above, and the reason it is safe.

    Leaving OPEN out of the tuples costs nothing only while every
    covered build carries the command. Measured against the database
    rather than asserted, so the day a build appears without it this
    goes red instead of the emission failing in a user's session.
    """
    database = CommandRegistry.load()
    for name, workflow in WORKFLOWS.items():
        for build in covered_builds(workflow):
            assert "OPEN" in database.for_version(build), (
                f"build {build} is covered by workflow {name!r} and its command database "
                "carries no OPEN, so a case naming a geometry cannot be built on it"
            )


# --- PFS-2025.02.03: the solver initialization comes off the row -------------


#: What each registered build accepts, WRITTEN DOWN rather than derived.
#:
#: This replaced a helper that walked the database exactly as
#: :func:`accepted_symmetry` does, five identical lines, under a
#: docstring claiming it compared the function against the evidence
#: "and not against a second copy of the same tuple". A second copy is
#: precisely what it was, so any defect the two shared (the wrong
#: argument name, the wrong field) passed. A QA pass measured that and
#: it is the reason this table exists.
#:
#: A table has to be MAINTAINED, and that is the feature: a build whose
#: documented vocabulary changes cannot slip through as a silently
#: re-derived answer, because someone has to come here and say so.
#: ``None`` means the build does not express symmetry through an
#: argument of that name.
EXPECTED_SYMMETRY = {
    "25.000": None,  # spells it SYMMETRY_TYPE, own token set (SRC-749 p.298)
    "25.100": ("NONE", "MIRROR", "PERIODIC"),
    "26.000": ("NONE", "MIRROR", "PERIODIC"),
    "26.100": ("NONE", "MIRROR", "PERIODIC"),
    "26.101": ("NONE", "MIRROR", "PERIODIC"),
    "26.120": ("NONE", "MIRROR", "PERIODIC"),
    "26.121": ("NONE", "MIRROR", "PERIODIC"),
    "26.122": ("NONE", "MIRROR", "PERIODIC"),
    "26.123": ("NONE", "MIRROR", "PERIODIC"),
}


def registry_declaring(values: tuple[str, ...]) -> CommandRegistry:
    """A command database whose INITIALIZE_SOLVER takes other symmetries.

    The only way to prove the accepted set is READ rather than restated:
    a literal list in the module answers the same on every database, and
    this one is deliberately not the shipped vocabulary.
    """
    database = CommandRegistry.load()
    entry = database.commands["INITIALIZE_SOLVER"]
    args = tuple(
        argument.model_copy(update={"values": values}) if argument.name == "symmetry" else argument
        for argument in entry.args
    )
    commands = dict(database.commands)
    commands["INITIALIZE_SOLVER"] = entry.model_copy(update={"args": args})
    return CommandRegistry(commands=commands)


def test_the_accepted_symmetries_come_from_the_database_per_build():
    """Every registered build, against an INDEPENDENT expectation.

    The oracle is :data:`EXPECTED_SYMMETRY`, written down rather than
    re-derived; its own comment carries why. The population is asserted
    too, so a build registered tomorrow fails here until someone states
    what it accepts, instead of being covered by a loop that shrank.
    """
    registered = {build.canonical for build in known_versions()}
    assert registered == set(EXPECTED_SYMMETRY), (
        f"the expectation table and the registered builds disagree: {registered} vs "
        f"{set(EXPECTED_SYMMETRY)}. State what the new build accepts rather than "
        "widening the loop"
    )
    for canonical, expected in sorted(EXPECTED_SYMMETRY.items()):
        assert accepted_symmetry(Script(canonical)) == expected, (
            f"the accepted symmetry set reported for {canonical} is not the one this "
            "build is documented to accept"
        )


def test_the_build_whose_symmetry_argument_is_spelled_differently_reports_none():
    """25.000 spells it SYMMETRY_TYPE, so the read finds no ``symmetry``.

    This is the case a hand-written list cannot pass: a literal
    ``("NONE", "MIRROR", "PERIODIC")`` answers the same for every build
    and would report a vocabulary this edition does not have
    (SRC-749 p.298). ``None`` is what hands the row on to
    ``initialize_solver``, whose refusal names that edition.
    """
    assert accepted_symmetry(Script("25.000")) is None
    assert accepted_symmetry(Script("26.120")) is not None


def test_a_database_declaring_other_symmetries_changes_the_answer():
    """MUTATION-PROOF: the set is read, and a literal cannot pass this.

    The database is the authority, so a build documenting a different
    vocabulary has to be reported with THAT vocabulary, both by the
    reader and inside the refusal a bad cell meets.
    """
    invented = ("NONE", "HALF_MODEL", "SECTOR")
    database = registry_declaring(invented)
    script = Script("26.120", registry=database)
    assert accepted_symmetry(script) == invented

    case = steady_case(SYMMETRY="MIRROR")
    with pytest.raises(CampaignConfigError) as raised:
        build_script(case, Script("26.120", registry=database), registry=database)
    message = str(raised.value)
    assert "HALF_MODEL" in message and "SECTOR" in message, (
        "the refusal does not list the modes THIS database declares, so the accepted "
        "set is a literal kept beside the workflow"
    )
    assert "MIRROR" in message, "the refusal does not name the value the row wrote"


def test_a_build_that_declares_the_argument_without_enumerating_it_refuses_nothing_here():
    """THE SECOND FALSY ANSWER, and the one that had no case at all.

    ``accepted_symmetry`` returns ``None`` when the build does not
    declare a ``symmetry`` argument, and an EMPTY TUPLE when it declares
    one that is not an enumeration: a non-enum argument carries
    ``values = None`` in the command database, which reads back as ``()``.
    The two are different facts and the return value keeps them apart,
    but ``_initialize`` must treat them alike, because neither can judge
    a mode.

    This case exists because getting that wrong is invisible. For one
    round of review the check read ``accepted is not None``, which is
    correct for the absent argument and refuses EVERY mode on this one,
    with a message claiming the build accepts none of them. No test
    reached it: the mutation restoring the truthiness test survived the
    suite, and that survival is what exposed it.

    What must happen instead is nothing at all HERE. The row goes on to
    the command's own validation, which is the only thing that knows
    this build's grammar.
    """
    # A NON-ENUM argument, which is the shape that really produces the
    # empty tuple: `values` is None on it and `values or ()` reads it as
    # `()`. Built here rather than through `registry_declaring`, which
    # keeps the type ENUM and so makes an enumeration with no tokens,
    # a degenerate entry the script validator rejects on its own. That
    # distinction cost this case one revision and is why it is written
    # down: the two look identical through `accepted_symmetry`.
    database = CommandRegistry.load()
    entry = database.commands["INITIALIZE_SOLVER"]
    args = tuple(
        argument.model_copy(update={"type": ArgType.STR, "values": None})
        if argument.name == "symmetry"
        else argument
        for argument in entry.args
    )
    commands = dict(database.commands)
    commands["INITIALIZE_SOLVER"] = entry.model_copy(update={"args": args})
    database = CommandRegistry(commands=commands)

    script = Script("26.120", registry=database)
    assert accepted_symmetry(script) == (), (
        "an argument declared without an enumeration should read back as an empty "
        "tuple, which is the case this guard is about"
    )

    case = steady_case(SYMMETRY="PERIODIC", PERIODIC_COPIES="4")
    text = Script("26.120", registry=database)
    build_script(case, text, registry=database)
    rendered_lines = text.render().splitlines()
    assert "SYMMETRY PERIODIC 4" in rendered_lines, (
        "the row was refused, or its mode was dropped, on a build that declares the "
        "argument without enumerating its tokens; this layer cannot judge a mode there "
        "and must leave the decision to the command"
    )


def test_a_row_declaring_neither_key_emits_symmetry_none_and_no_count():
    """Exactly what every workflow emitted before 0.8.1.

    Both halves matter: NONE is the token, and the absence of a count
    beside it is what says no periodic copies were requested.
    """
    lines = rendered(steady_case()).splitlines()
    assert "SYMMETRY NONE" in lines
    assert not [line for line in lines if line.startswith("SYMMETRY ") and line != "SYMMETRY NONE"]


def test_a_periodic_sector_reaches_the_command_with_its_copy_count():
    """The whole point of the item: the sector can finally say so.

    A four-bladed rotor modelled as one 90 degree sector emits
    ``SYMMETRY PERIODIC 4``. Under the shipped 0.8.0 body no cell could
    express this and the same mesh was initialized under NONE, which
    solves a ONE-BLADED rotor: it converges, it exports, and its thrust
    and torque are not the sector's.
    """
    text = rendered(steady_case(SYMMETRY="PERIODIC", PERIODIC_COPIES="4"))
    assert "SYMMETRY PERIODIC 4" in text.splitlines()
    assert "SYMMETRY NONE" not in text


def test_the_rotor_builder_reads_the_same_two_keys():
    """Both builders, because a sector study is a ROTOR study.

    The unsteady rotor is the run type the periodic rows of the blocked
    study name, so a fix that reached only the steady builder would have
    fixed the case nobody was blocked on.
    """
    case = rotor_case()
    case = case.model_copy(
        update={"variables": {**case.variables, "SYMMETRY": "PERIODIC", "PERIODIC_COPIES": "3"}}
    )
    assert "SYMMETRY PERIODIC 3" in rendered(case, "26.123").splitlines()


def test_the_symmetry_value_is_folded_before_the_domain_is_checked():
    """A cell typed in lower case is the same physical statement."""
    assert "SYMMETRY MIRROR" in rendered(steady_case(SYMMETRY="mirror")).splitlines()


def test_a_symmetry_outside_the_declared_set_is_refused_naming_both():
    """The value written and the modes accepted, and the physical cause."""
    with pytest.raises(CampaignConfigError) as raised:
        rendered(steady_case(SYMMETRY="AXISYMMETRIC"))
    message = str(raised.value)
    assert "'AXISYMMETRIC'" in message, "the refusal does not name the value the row wrote"
    for mode in EXPECTED_SYMMETRY["26.120"]:
        assert mode in message, f"the refusal does not list the accepted mode {mode}"
    assert "one blade" in message, "the refusal does not name the physical consequence"


def test_periodic_without_a_copy_count_is_refused_by_the_cell_it_needs():
    """The command appends the count (SRC-003 p.337), so the row must say."""
    with pytest.raises(CampaignConfigError) as raised:
        rendered(steady_case(SYMMETRY="PERIODIC"))
    message = str(raised.value)
    assert PERIODIC_COPIES_VARIABLE in message
    assert "7002" in message, "the refusal does not name the case"


def test_a_copy_count_without_periodic_is_refused_rather_than_dropped():
    """A count outside a periodic sector means nothing, so it is not ignored.

    Silently dropping it is the shape of this whole release's defect: the
    author asked for something, the script did not carry it, and nothing
    said so.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rendered(steady_case(PERIODIC_COPIES="4"))
    message = str(raised.value)
    assert f"no {SYMMETRY_VARIABLE} at all" in message, (
        "the refusal reports a SYMMETRY value the author never typed"
    )
    with pytest.raises(CampaignConfigError):
        rendered(steady_case(SYMMETRY="MIRROR", PERIODIC_COPIES="4"))


@pytest.mark.parametrize("count", ["0", "-2"])
def test_fewer_than_one_copy_is_not_a_sector(count):
    """A sector stands for at least one copy of itself."""
    with pytest.raises(CampaignConfigError) as raised:
        rendered(steady_case(SYMMETRY="PERIODIC", PERIODIC_COPIES=count))
    assert PERIODIC_COPIES_VARIABLE in str(raised.value)


def test_a_fractional_copy_count_is_refused_by_the_key_and_not_by_the_command():
    """Matrix variables arrive as text; the conversion is refused here."""
    with pytest.raises(CampaignConfigError) as raised:
        rendered(steady_case(SYMMETRY="PERIODIC", PERIODIC_COPIES="2.5"))
    message = str(raised.value)
    assert PERIODIC_COPIES_VARIABLE in message
    assert "fractional" in message


def test_the_build_this_helper_cannot_express_keeps_its_own_refusal():
    """25.000 raises the HELPER's message, not a symmetry one.

    Wrapping the ``initialize_solver`` call re-labelled that refusal as
    a symmetry problem on a row that had said nothing about symmetry,
    which reads as a defect in the row rather than in the build. It was
    measured on this build before the wrap was removed, so the case is
    kept: every refusal this module owns is decided BEFORE the helper
    runs, and the helper's own message survives untouched.
    """
    with pytest.raises(CommandArgumentError) as raised:
        rendered(steady_case(), "25.000")
    message = str(raised.value)
    assert "25.000" in message
    assert "SYMMETRY_TYPE" in message
    assert SYMMETRY_VARIABLE not in message.replace("SYMMETRY_TYPE", "")


def test_a_row_that_does_declare_a_symmetry_on_that_build_still_gets_the_helpers_refusal():
    """THE BRANCH THE CASE ABOVE CANNOT REACH, and it was unproven.

    The sibling above builds a case with NO ``SYMMETRY`` key, so
    ``symmetry is None`` and the whole accepted-modes block is skipped.
    No case anywhere declared a symmetry on 25.000, which left
    ``accepted is not None and ...`` carrying a fact nothing measured: a
    QA pass deleted the ``accepted is not None`` half and the entire tier
    1 suite stayed green.

    What the missing half decides: 25.000 spells the argument
    ``SYMMETRY_TYPE``, so :func:`accepted_symmetry` answers ``None``, and
    the row must go on to meet the BUILD's refusal. Without the guard it
    would meet a refusal from this module reading "FlightStream 25.000
    initializes under " with an empty list, blaming the row for the
    build's grammar and naming no accepted mode at all.
    """
    with pytest.raises(CommandArgumentError) as raised:
        rendered(steady_case(SYMMETRY="PERIODIC", PERIODIC_COPIES="4"), "25.000")
    message = str(raised.value)
    assert "SYMMETRY_TYPE" in message, "the build's own refusal was replaced by ours"
    assert "initializes under" not in message, (
        "the row was refused for declaring a mode this build does not accept, but the "
        "build declares no accepted set at all: the refusal names an empty list"
    )


def test_the_build_that_spells_it_differently_answers_none_rather_than_empty():
    """``None`` and ``()`` are two different facts and must not share a value.

    ``None`` means this build does not express symmetry through an
    argument named ``symmetry``; an empty tuple would mean it declares
    the argument and enumerates nothing. No build asks the second
    question today, which is exactly why the sentinel was worth
    separating before one does: with both spelled ``()`` the docstring
    was true only by a property of the database that nothing asserts,
    and ``accepted_symmetry(script) == ()`` reads at a call site as "no
    mode is accepted", the inverse of what it meant.
    """
    assert accepted_symmetry(Script("25.000")) is None
    accepted = accepted_symmetry(Script("26.120"))
    assert accepted is not None and "PERIODIC" in accepted


# --- PFS-2025.02.04: the reference artifact reaches the emitted script -------


def _reference_case(reference):
    """A minimal steady case, with and without a reference."""
    from pyflightstream.cases import SimCase, SweepAxis

    return SimCase(
        sim_id="P1",
        aircraft="W",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        point={"alpha": 0.0},
        reference=reference,
        velocity=30.0,
        outputs=["loads.txt"],
        variables={"WORKFLOW": "steady"},
    )


def _rendered(reference):
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script

    script = Script("26.123")
    build_script(_reference_case(reference), script)
    return script.render().splitlines()


def test_a_case_carrying_a_reference_emits_its_area_and_length():
    """PFS-2025.02.04, and until 0.9.0 it emitted neither.

    Measured before this landed: not one of the 29 committed workflow
    goldens carried a REF_ line, so a campaign declared its areas and
    lengths and the coefficients came out against whatever the solver
    defaulted to, with nothing said.
    """
    from pyflightstream.cases import ReferenceData

    lines = _rendered(ReferenceData(area=10.0, length=1.2))
    assert "SOLVER_SET_REF_AREA 10.0" in lines
    assert "SOLVER_SET_REF_LENGTH 1.2" in lines


def test_a_case_carrying_no_reference_emits_neither_and_nothing_else_moves():
    """The byte-identity clause, which is what protects every old fixture."""
    from pyflightstream.cases import ReferenceData

    with_reference = _rendered(ReferenceData(area=10.0, length=1.2))
    without = _rendered(None)
    assert [line for line in without if "REF" in line] == []
    # Everything that is not the two new lines is unchanged, so a case
    # that names no reference renders exactly what it always rendered.
    assert [line for line in with_reference if "REF" not in line] == without


def test_the_reference_values_are_emitted_in_the_units_the_artifact_carries():
    """No conversion here, deliberately.

    The artifact documents its own units (area in square metres, length
    in metres). Converting at the emitter would put a second opinion
    about units in the one place that cannot see that documentation.
    """
    from pyflightstream.cases import ReferenceData

    lines = _rendered(ReferenceData(area=3.25, length=0.75))
    assert "SOLVER_SET_REF_AREA 3.25" in lines
    assert "SOLVER_SET_REF_LENGTH 0.75" in lines


# --- PFS-2025.02.05 / PFS-2027.05: the resolved state reaches the script -----


def _fluid_case(fluid):
    from pyflightstream.cases import ReferenceData, SimCase, SweepAxis

    return SimCase(
        sim_id="P1",
        aircraft="W",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        point={"alpha": 0.0},
        velocity=30.0,
        reference=ReferenceData(area=10.0, length=1.2),
        fluid=fluid,
        outputs=["loads.txt"],
        variables={"WORKFLOW": "steady"},
    )


def _fluid_rendered(fluid, build="26.123"):
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script

    script = Script(build)
    build_script(_fluid_case(fluid), script)
    return script.render().splitlines()


def _resolved_state():
    from pyflightstream.cases import FluidState

    return FluidState(
        velocity_m_per_s=68.0588,
        density_kg_m3=1.44598,
        pressure_pa=119603.0,
        temperature_k=288.15,
        viscosity_pa_s=1.7893e-05,
        sonic_velocity_m_per_s=340.294,
        source="solved-from-reynolds",
    )


def test_a_resolved_flight_condition_emits_the_five_fluid_properties():
    """PFS-2027.05: what was solved is what the script says.

    Emitted as explicit properties rather than as an altitude, and the
    choice is forced rather than preferred: AIR_ALTITUDE has no argument
    for an ISA deviation, and a density solved to meet a Reynolds number
    is not an atmosphere point at all.
    """
    lines = _fluid_rendered(_resolved_state())
    assert "FLUID_PROPERTIES" in lines
    assert "DENSITY 1.44598" in lines
    assert "PRESSURE 119603.0" in lines
    assert "TEMPERATURE 288.15" in lines
    assert "VISCOSITY 1.7893e-05" in lines


def test_a_case_with_no_resolved_state_emits_no_fluid_block():
    """The clause that protects every case written before 0.9.0."""
    assert "FLUID_PROPERTIES" not in _fluid_rendered(None)


@pytest.mark.parametrize(
    ("build", "present", "absent"),
    [
        ("26.123", "SPECIFIC_HEAT_RATIO 1.4", "SONIC_VELOCITY"),
        ("26.000", "SONIC_VELOCITY 340.294", "SPECIFIC_HEAT_RATIO"),
    ],
)
def test_the_fifth_property_follows_the_build(build, present, absent):
    """One state, two editions, and the emitter refuses the wrong one.

    The solver editions state one physical fact two ways: the three
    pre-26.100 builds take a sonic velocity and the later ones take the
    specific-heat ratio. The case carries both and the builder ASKS
    which this build takes, so one case renders on either side of that
    boundary instead of failing on one of them.
    """
    lines = _fluid_rendered(_resolved_state(), build)
    assert present in lines
    assert not any(line.startswith(absent) for line in lines)


def test_the_rotor_builder_emits_the_fluid_state_too():
    """BOTH builders, not just the one that had a test.

    A QA pass measured that deleting `_fluid(case, script)` from the
    unsteady-rotor builder left 136 tests passing, because only the
    steady branch was covered. The rotor is the workflow whose own
    fixture was rewritten in this change to carry a flight condition,
    and rotor Reynolds is the case the reference-length coupling prices
    at the ratio of the two lengths, so it is the branch least safe to leave
    untested.
    """
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script

    case = rotor_case().model_copy(update={"fluid": _resolved_state()})
    script = Script("26.123")
    build_script(case, script)
    lines = script.render().splitlines()
    assert "FLUID_PROPERTIES" in lines, "the rotor builder emitted no fluid state"
    assert "DENSITY 1.44598" in lines
    assert "TEMPERATURE 288.15" in lines


def test_the_rotor_builder_emits_nothing_when_there_is_no_fluid_state():
    """And the absence clause on the same branch."""
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script

    script = Script("26.123")
    build_script(rotor_case(), script)
    assert "FLUID_PROPERTIES" not in script.render().splitlines()


# --- the rotor speed as a ratio, and the clock as an angle -------------------
#
# The two derivations that were inputs until this release. A propeller
# study is designed in an advance ratio and an azimuthal step; the
# rev/min and the seconds are what those work out to at the run's own
# velocity, so the matrix now takes the decisions and derives the rest.


def ratio_case(**overrides) -> SimCase:
    """A rotor case stating its speed as a ratio, with a diameter to divide by."""
    variables: dict[str, object] = {"RPM": None, ADVANCE_RATIO_VARIABLE: "1.7"}
    variables.update(overrides)
    case = rotor_case(**variables)
    return case.model_copy(
        update={
            "reference": ReferenceData(area=50.0, length=2.526, propeller_diameter=3.6576),
            "velocity": 49.036363674559425,
        }
    )


def test_an_advance_ratio_resolves_the_rotor_speed_the_study_was_designed_at():
    """J = V/(nD) inverted, against the campaign's own measured numbers.

    The values are the SMIL2 B45 point: 49.0364 m/s through a 3.6576 m
    diameter at J = 1.7 is 473.17 rev/min, which is the rotor speed that
    campaign's proven runs used and typed by hand into every row.
    """
    speed = rotor_speed(ratio_case())
    assert speed.stated_form == "advance_ratio"
    assert speed.rpm == pytest.approx(473.17782, abs=5e-5)
    assert speed.advance_ratio == 1.7
    assert speed.diameter_m == 3.6576


def test_an_explicit_rpm_is_carried_through_unconverted():
    """The form that was the only one keeps working, verbatim."""
    speed = rotor_speed(rotor_case())
    assert speed.stated_form == "rpm"
    assert speed.rpm == 1200.0
    assert speed.advance_ratio is None and speed.diameter_m is None


def test_the_sign_is_applied_to_a_derived_speed_and_never_invented():
    """A ratio is a magnitude, so the hand of the rotation is its own key."""
    assert rotor_speed(ratio_case()).rpm > 0.0
    assert rotor_speed(ratio_case(**{RPM_SIGN_VARIABLE: "-1"})).rpm < 0.0
    assert rotor_speed(ratio_case(**{RPM_SIGN_VARIABLE: "-1"})).rpm == pytest.approx(
        -rotor_speed(ratio_case()).rpm
    )


def test_a_sign_beside_an_explicit_rpm_is_refused_as_a_second_opinion():
    """A rev/min value carries its own sign; a second one can only disagree."""
    with pytest.raises(CampaignConfigError) as raised:
        rotor_speed(rotor_case(**{RPM_SIGN_VARIABLE: "-1"}))
    message = str(raised.value)
    # RPM_SIGN_VARIABLE == "RPM_SIGN", so `"RPM" in message` is entailed
    # by the first conjunct and checked nothing. The second key is named
    # by the phrase that can only come from the rev/min branch.
    assert RPM_SIGN_VARIABLE in message
    assert "carries its own sign" in message


def test_a_ratio_with_no_diameter_on_the_reference_is_refused_naming_the_field():
    """The refusal has to name the artifact field, or the author cannot act."""
    case = ratio_case().model_copy(update={"reference": ReferenceData(area=50.0, length=2.526)})
    with pytest.raises(CampaignConfigError) as raised:
        rotor_speed(case)
    message = str(raised.value)
    assert "propeller_diameter_m" in message, (
        f"the refusal must name the field to add to the reference artifact; got {message!r}"
    )


def test_stating_the_speed_in_both_forms_is_refused_naming_both():
    """The rev/min are what the ratio works out to; a second form disagrees."""
    with pytest.raises(CampaignConfigError) as raised:
        rotor_speed(ratio_case(RPM="1200"))
    message = str(raised.value)
    assert ADVANCE_RATIO_VARIABLE in message and "1200" in message


def test_stating_no_rotor_speed_at_all_is_refused_offering_both_forms():
    """And the refusal names the two ways to close it."""
    with pytest.raises(CampaignConfigError) as raised:
        rotor_speed(rotor_case(RPM=None))
    message = str(raised.value)
    assert ADVANCE_RATIO_VARIABLE in message and "RPM" in message


def test_the_azimuthal_step_and_the_revolutions_set_the_whole_clock():
    """10 deg per step for 1.5 revolutions at 473.17 rev/min is 54 x 0.00352 s.

    Those are the numbers the SMIL2 campaign typed into its rows as
    constants; here they are the CONSEQUENCE of the two decisions
    behind them.
    """
    stepping = rotor_time_stepping(
        ratio_case(
            DELTA_TIME=None,
            TIME_ITERATIONS=None,
            **{DELTA_THETA_VARIABLE: "10.0", REVOLUTIONS_VARIABLE: "1.5"},
        )
    )
    assert stepping.stated_form == "angular"
    assert stepping.time_iterations == 54
    assert stepping.steps_per_revolution == pytest.approx(36.0)
    # 10 / (6 * 473.1786) s, and the legacy row typed 0.00352, which is
    # that value rounded to three figures. The rounding is the reason to
    # derive rather than type: 54 steps of 0.00352 s cover 1.4990
    # revolutions and not the 1.5 the campaign documented.
    assert stepping.delta_time_s == pytest.approx(0.0035222840, abs=5e-10)
    # A DURATION ASSERTION AGAINST THE ROTOR SPEED WAS REPLACED HERE, and
    # the replacement is the point: `delta_time * steps` is identically
    # `revolutions * 60 / rpm` given the two formulas the function uses,
    # so it restated the implementation's own algebra and could not fail
    # for any accepted input. The literal below is independent of it.
    assert stepping.delta_time_s * stepping.time_iterations == pytest.approx(0.19020334, abs=5e-9)


def test_the_explicit_clock_is_carried_through_unconverted():
    """The pair that was the only form keeps working, verbatim."""
    stepping = rotor_time_stepping(rotor_case())
    assert stepping.stated_form == "explicit"
    assert stepping.delta_time_s == 1e-4
    assert stepping.time_iterations == 720


def test_revolutions_that_are_not_a_whole_number_of_steps_are_refused():
    """A run ending part way through a step ends at an azimuth nobody chose."""
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(
            ratio_case(
                DELTA_TIME=None,
                TIME_ITERATIONS=None,
                **{DELTA_THETA_VARIABLE: "7.0", REVOLUTIONS_VARIABLE: "1.5"},
            )
        )
    message = str(raised.value)
    # "7" ALONE FREE-RIDES on the derived 77.1429, so deleting the theta
    # interpolation left the assertion passing. "7.0" is the value the
    # author typed and is the one that pins it.
    assert "7.0" in message and "1.5" in message, (
        f"the refusal must print both numbers the author chose; got {message!r}"
    )


@pytest.mark.parametrize(
    "stated,missing",
    [
        ({DELTA_THETA_VARIABLE: "10.0"}, REVOLUTIONS_VARIABLE),
        ({REVOLUTIONS_VARIABLE: "1.5"}, DELTA_THETA_VARIABLE),
    ],
)
def test_half_an_angular_clock_is_refused_naming_the_missing_key(stated, missing):
    """Neither of the two implies the other, so half a pair is not a clock.

    ASSERTED ON THE PHRASE AND NOT ON MEMBERSHIP. Both refusals name both
    keys, so `missing in message` was true in either branch for either
    input: the parametrize was one test run twice, and an implementation
    with the two lists swapped passed it.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(ratio_case(DELTA_TIME=None, TIME_ITERATIONS=None, **stated))
    message = str(raised.value)
    stated_key = next(iter(stated))
    assert f"and not {missing}" in message, (
        f"the refusal must say which key is MISSING, not merely mention both; got {message!r}"
    )
    assert message.index(stated_key) < message.index(f"and not {missing}"), (
        "the stated key must be named before the missing one, or the message reads backwards"
    )


def test_stating_the_clock_in_both_forms_is_refused_naming_both():
    """The seconds are what the angle works out to; a second form disagrees."""
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(
            ratio_case(**{DELTA_THETA_VARIABLE: "10.0", REVOLUTIONS_VARIABLE: "1.5"})
        )
    message = str(raised.value)
    assert DELTA_THETA_VARIABLE in message and "DELTA_TIME" in message


def test_the_builder_emits_the_derived_clock_and_the_derived_speed():
    """End to end: a row stating only J and an azimuthal step renders a run."""
    case = ratio_case(
        DELTA_TIME=None,
        TIME_ITERATIONS=None,
        WINDOW_DEGREES=None,
        **{
            DELTA_THETA_VARIABLE: "10.0",
            REVOLUTIONS_VARIABLE: "1.5",
            "WINDOW_REVOLUTIONS": "1.0",
        },
    )
    script = Script("26.123")
    build_script(case, script, conventions=WorkflowConventions(outputs=("loads.txt",)))
    lines = script.render().splitlines()
    assert "TIME_ITERATIONS 54" in lines
    assert any(line.startswith("DELTA_TIME 0.00352") for line in lines), (
        f"expected the derived time step; got {[x for x in lines if 'DELTA_TIME' in x]}"
    )
    assert any(line.startswith("SET_MOTION_ROTOR_RPM 1 473.177") for line in lines), (
        f"expected the derived rotor speed; got {[x for x in lines if 'RPM' in x]}"
    )


def test_a_row_written_in_the_derived_numbers_renders_what_it_always_rendered():
    """The compatibility claim, asserted rather than promised."""
    script = Script("26.123")
    build_script(rotor_case(), script, conventions=WorkflowConventions(outputs=("loads.txt",)))
    lines = script.render().splitlines()
    assert "TIME_ITERATIONS 720" in lines
    assert "DELTA_TIME 0.0001" in lines
    assert "SET_MOTION_ROTOR_RPM 1 1200.0" in lines


# --- the solver log, and the verdict it makes possible -----------------------


def test_a_row_naming_no_log_exports_none():
    """The compatibility half: every workflow script before this emitted none."""
    script = Script("26.123")
    build_script(rotor_case(), script, conventions=WorkflowConventions(outputs=("loads.txt",)))
    assert "EXPORT_LOG" not in script.render()


def test_the_named_output_is_the_one_exported_as_the_log():
    """1-based, and it survives rendering because rendering preserves order."""
    script = Script("26.123")
    build_script(
        rotor_case(LOG_OUTPUT="2"),
        script,
        conventions=WorkflowConventions(outputs=("loads_a+00.0.txt", "log_a+00.0.txt")),
    )
    lines = script.render().splitlines()
    assert "EXPORT_LOG" in lines
    assert lines[lines.index("EXPORT_LOG") + 1] == "log_a+00.0.txt", (
        "the log must be the RENDERED name of the declared output, never a literal"
    )


def test_a_log_position_the_row_does_not_declare_is_refused_naming_both():
    """The refusal has to print what the row declared, or it cannot be acted on."""
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            rotor_case(LOG_OUTPUT="3"),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt", "log.txt")),
        )
    message = str(raised.value)
    assert "3" in message and "2" in message


def test_a_log_named_by_file_name_is_refused_saying_why_a_name_cannot_work():
    """The mistake that cost a pre-flight; the message has to prevent the retry."""
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            rotor_case(LOG_OUTPUT="loads_{point}_log.txt"),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt", "log.txt")),
        )
    message = str(raised.value)
    assert "rendered" in message.lower(), (
        f"the refusal must say WHY a name cannot be used here; got {message!r}"
    )


def _angular(**over):
    """A ratio case on the angular clock, which is what the conversion needs."""
    keys = {DELTA_THETA_VARIABLE: "10.0", REVOLUTIONS_VARIABLE: "1.5"}
    keys.update(over)
    return ratio_case(DELTA_TIME=None, TIME_ITERATIONS=None, **keys)


# --- the refusals the first round shipped untested ---------------------------
#
# A QA lens measured ten new refusal branches with no test at all. A
# refusal nothing exercises is a refusal nobody has read, and this
# package's whole didactic claim rests on what a refusal says.


@pytest.mark.parametrize(
    "key,value",
    [
        (ADVANCE_RATIO_VARIABLE, "nan"),
        (ADVANCE_RATIO_VARIABLE, "inf"),
        (DELTA_THETA_VARIABLE, "nan"),
        (REVOLUTIONS_VARIABLE, "inf"),
    ],
)
def test_a_non_finite_cell_is_refused_by_case_and_key(key, value):
    """Every comparison against NaN is false, so a bound alone does not stop it.

    Before this, `DELTA_THETA: nan` reached `int(round(...))` and died
    with a bare ValueError naming neither the case nor the key, and
    `ADVANCE_RATIO: nan` resolved a NaN rotor speed that reached the
    command layer.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(_angular(**{key: value}))
    message = str(raised.value)
    assert "finite" in message and key in message and "7001" in message


@pytest.mark.parametrize("ratio", ["-1.7", "0"])
def test_an_advance_ratio_of_zero_or_less_is_refused_pointing_at_the_sign_key(ratio):
    """A ratio is a magnitude; a negative one is a hand, and has its own key.

    Zero is included because it is the boundary the condition is written
    at, and the first version exercised only the negative side.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_speed(ratio_case(**{ADVANCE_RATIO_VARIABLE: ratio}))
    assert RPM_SIGN_VARIABLE in str(raised.value)


def test_a_ratio_on_a_stopped_aircraft_is_refused_naming_the_inversion():
    """n = V / (J D) is a stopped rotor at V = 0."""
    case = ratio_case().model_copy(update={"velocity": 0.0})
    with pytest.raises(CampaignConfigError) as raised:
        rotor_speed(case)
    # NOT `n = V / (J D)`, which the first repair used: that phrase occurs
    # in three of this function's refusals, so a fixture drifting to a
    # neighbouring branch would still pass while reporting on a branch it
    # no longer reaches. That is how the round-two defect was born.
    assert "needs a moving aircraft" in str(raised.value)


def test_stating_no_clock_at_all_is_refused_offering_both_forms():
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(ratio_case(DELTA_TIME=None, TIME_ITERATIONS=None))
    message = str(raised.value)
    assert DELTA_THETA_VARIABLE in message and "DELTA_TIME" in message


@pytest.mark.parametrize(
    "stated,missing",
    [({"DELTA_TIME": "0.001"}, "TIME_ITERATIONS"), ({"TIME_ITERATIONS": "720"}, "DELTA_TIME")],
)
def test_half_an_explicit_clock_is_refused_naming_the_missing_key(stated, missing):
    """The commit claimed this without qualification; only the angular pair had a test."""
    # BUILT AS A DICT, because `ratio_case(DELTA_TIME=None, **stated)`
    # passes DELTA_TIME twice and dies in the call rather than in the
    # code under test.
    keys = {"DELTA_TIME": None, "TIME_ITERATIONS": None}
    keys.update(stated)
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(ratio_case(**keys))
    assert f"and not {missing}" in str(raised.value)


@pytest.mark.parametrize("theta", ["0", "-10", "361"])
def test_an_azimuthal_step_outside_one_revolution_is_refused(theta):
    """A step of a whole turn resolves nothing inside one turn.

    BUILT ON A COMPLETE PAIR, and asserted on a phrase only this branch
    produces. The first version stated DELTA_THETA and left REVOLUTIONS
    out, so the half-a-pair refusal fired one branch earlier; that
    refusal also names DELTA_THETA, so a `match` on the key name passed
    while the range check never ran. All three parameters were one test
    asserting an unrelated message.
    """
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(_angular(**{DELTA_THETA_VARIABLE: theta}))
    assert "resolves nothing inside one turn" in str(raised.value)


def test_a_run_of_no_revolutions_is_refused():
    """The mirror image of the same mistake, fixed the same way."""
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(_angular(**{REVOLUTIONS_VARIABLE: "0"}))
    assert "positive number of revolutions" in str(raised.value)


def test_an_angular_clock_on_a_rotor_that_does_not_turn_is_refused():
    """A degree of rotation has no duration at zero rev/min.

    Reached through the RPM form, because the ratio form cannot express
    a stopped rotor: n = V / (J D) is zero only at zero velocity, which
    is refused earlier and for its own reason.
    """
    case = _angular()
    kept = {k: v for k, v in case.variables.items() if k != ADVANCE_RATIO_VARIABLE}
    kept["RPM"] = "0"
    with pytest.raises(CampaignConfigError) as raised:
        rotor_time_stepping(case.model_copy(update={"variables": kept}))
    assert "rotor speed of zero" in str(raised.value)


# --- the wake termination, the one preset field needing a conversion ---------


def test_the_preset_wake_termination_converts_from_revolutions_to_steps():
    """Minus one revolution at 36 steps per revolution is minus 36 steps.

    This is the ONLY new solver-preset field whose emitter takes a
    different unit from the one the preset states, and the round that
    added it had no test that rendered it into a script at all.
    """
    case = _angular().model_copy(
        update={"solver": SolverSettings(wake_termination_revolutions=-1.0)}
    )
    script = Script("26.123")
    build_script(case, script, conventions=WorkflowConventions(outputs=("loads.txt",)))
    assert "SET_WAKE_TERMINATION_TIME_STEPS -36" in script.render().splitlines()


def test_a_wake_termination_with_no_rotor_speed_is_refused():
    """A revolution has no length in steps without one.

    CALLED DIRECTLY, and that is a statement about the guard rather than
    a shortcut. The rotor builder resolves the rotor speed before the
    clock, so a case with no speed is refused there and this arm is
    unreachable through it; the arm is what stops the conversion being
    attempted if that order ever changes. The first version of this test
    went through the builder, met the no-rotor-speed refusal, carried a
    bare `raises` with no match, and never executed the line its own
    docstring describes.
    """
    case = rotor_case(RPM=None, DELTA_TIME="0.001", TIME_ITERATIONS="100").model_copy(
        update={"solver": SolverSettings(wake_termination_revolutions=-1.0)}
    )
    stepping = rotor_time_stepping(case)
    assert stepping.rpm is None, "the clock must carry no speed for this arm to exist"
    with pytest.raises(CampaignConfigError) as raised:
        workflows_module._wake_termination(case, stepping)
    assert "has no length in time steps here" in str(raised.value)


# --- the records, whose shape is decided here even though nothing reads it ---


def test_the_rotor_speed_record_carries_every_input_it_consumed():
    """A record claiming a derived number without its divisors is unreadable."""
    record = rotor_speed(ratio_case()).record()
    assert record["form"] == "advance_ratio"
    assert record["stated"] == 1.7
    assert record["diameter_m"] == 3.6576
    assert record["velocity_m_per_s"] == pytest.approx(49.036363674559425)
    # AN INDEPENDENT LITERAL, not `60 * V / (J D)` restated. The formula
    # would pin the plumbing and not the number, which is one of the five
    # failure modes this file repaired two sections up.
    assert record["rpm"] == pytest.approx(473.17782, abs=5e-5)


def test_the_time_stepping_record_carries_the_rotor_speed_it_ran_against():
    """steps_per_revolution is computed FROM rpm, so a record needs both."""
    record = rotor_time_stepping(_angular()).record()
    assert record["form"] == "angular"
    assert record["delta_theta_deg"] == 10.0
    assert record["revolutions"] == 1.5
    assert record["time_iterations"] == 54
    assert record["steps_per_revolution"] == pytest.approx(36.0)
    assert record["rpm"] is not None, (
        "the divisor of steps_per_revolution must be in the record beside it"
    )


# --- the log position, and the export it must not overwrite ------------------


def test_the_log_may_not_claim_the_position_the_spreadsheet_exports_to():
    """LOG_OUTPUT: 1 wrote the solver log over the loads table.

    The run completed and the assessor then sent the author to look for
    a truncated export rather than at the cell they typed. Position 1 is
    also the likeliest typo of someone who has just read "counted from 1".
    """
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            rotor_case(LOG_OUTPUT="1"),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt", "log.txt")),
        )
    message = str(raised.value)
    assert "loads.txt" in message and "already exports" in message


def test_a_decimal_log_position_is_not_told_why_a_name_cannot_work():
    """2.0 is not a name, and answering the name question answers nothing asked."""
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            rotor_case(LOG_OUTPUT="2.0"),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt", "log.txt")),
        )
    message = str(raised.value)
    assert "decimal point" in message
    assert "rendered" not in message.lower()


# --- the round-two findings, each with the probe it shipped without ----------


def test_a_steady_row_refuses_a_wake_termination_it_cannot_emit():
    """It used to resolve, validate, reach no line, and say nothing.

    THIS TEST WAS DESCRIBED AND NOT WRITTEN in the round that added the
    refusal, and a review lens found the refusal shipped with no probe.
    The only wake-termination test there exercised the rotor branch,
    which is a different function.
    """
    case = steady_case().model_copy(
        update={"solver": SolverSettings(wake_termination_revolutions=-1.0)}
    )
    with pytest.raises(CampaignConfigError) as raised:
        build_script(case, Script("26.123"), conventions=WorkflowConventions(outputs=("l.txt",)))
    message = str(raised.value)
    assert "STEADY" in message and "revolutions" in message


def test_a_rotor_row_is_not_caught_by_the_steady_refusal():
    """The other half of the same claim: it must not fire where it can convert."""
    case = _angular().model_copy(
        update={"solver": SolverSettings(wake_termination_revolutions=-1.0)}
    )
    script = Script("26.123")
    build_script(case, script, conventions=WorkflowConventions(outputs=("loads.txt",)))
    assert "SET_WAKE_TERMINATION_TIME_STEPS -36" in script.render().splitlines()


@pytest.mark.parametrize("origin", ["nan,0,0", "0,inf,0", "0,0,-inf"])
def test_a_non_finite_rotor_origin_is_refused(origin):
    """The one numeric cell that does not pass through _required_float.

    It parses three values out of one string with a bare float(), so
    float("nan") succeeded and a NaN coordinate became the origin of the
    frame the whole rotary motion turns about.
    """
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            _angular(ROTOR_ORIGIN=origin),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt",)),
        )
    message = str(raised.value)
    assert "finite" in message and "ROTOR_ORIGIN" in message


def test_a_speed_resolved_from_another_case_is_refused():
    """A handed speed also skips every refusal rotor_speed makes.

    Without the identity check, a row stating both ADVANCE_RATIO and RPM
    builds a clean script when a caller supplies a speed, because the
    refusal for that contradiction lives inside the resolver the caller
    just bypassed.
    """
    mine = ratio_case()
    theirs = rotor_speed(ratio_case().model_copy(update={"sim_id": "9999"}))
    with pytest.raises(CampaignConfigError) as raised:
        emit_rotor_motion(mine, Script("26.123"), frame=1, speed=theirs)
    message = str(raised.value)
    assert "9999" in message and "7001" in message


def test_a_speed_from_this_case_is_accepted():
    """The acceptance half, so the refusal is not satisfied by a constant."""
    script = Script("26.123")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    case = ratio_case()
    emit_rotor_motion(case, script, frame=2, speed=rotor_speed(case))
    assert any("SET_MOTION_ROTOR_RPM" in line for line in script.render().splitlines())


@pytest.mark.parametrize(
    "value,expected,forbidden",
    [
        ("2.0", "decimal point", "rendered"),
        ("log_{point}.txt", "RENDERED", "decimal point"),
        ("nan", "not a whole number", "decimal point"),
        ("inf", "not a whole number", "decimal point"),
        ("1e3", "not a whole number", "decimal point"),
    ],
)
def test_a_log_position_that_is_not_a_number_gets_the_right_reason(value, expected, forbidden):
    """float-parseability was wider than the message it selected.

    `nan`, `inf` and `1e3` all parse as floats, so their authors were
    told the value takes no decimal point, about characters containing
    no decimal point.
    """
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            rotor_case(LOG_OUTPUT=value),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt", "log.txt")),
        )
    message = str(raised.value)
    assert expected in message
    assert forbidden not in message


@pytest.mark.parametrize(
    "origin,expected",
    [
        ("0,0", "comma separated"),
        ("0,0,0,0", "comma separated"),
        ("x,0,0", "not three numbers"),
    ],
)
def test_a_rotor_origin_that_is_not_three_numbers_is_refused(origin, expected):
    """The two refusals beside the one this round added, left untested.

    The finiteness check went in eight lines below these and neither was
    covered, so a didactic refusal a blocked author reads had no probe.

    ASSERTED ON `comma separated` AND NOT ON `three coordinates`: the
    latter occurs in TWO of this function's three refusals, so the count
    cases passed against the finiteness branch's wording as well. That
    is the round-two defect inside the round written to close it, and a
    mutant swapping the two message bodies survived.
    """
    with pytest.raises(CampaignConfigError) as raised:
        build_script(
            _angular(ROTOR_ORIGIN=origin),
            Script("26.123"),
            conventions=WorkflowConventions(outputs=("loads.txt",)),
        )
    message = str(raised.value)
    assert expected in message and "ROTOR_ORIGIN" in message


# --- PFS-2028.00: a row names the mesh family, not the solver's positions ----
#
# THE DEFECT, in one sentence. A rotor row cited its moving boundaries by
# POSITION in one geometry's boundary order. Those positions are right for
# the file they were written against and mean different surfaces in any file
# that orders them differently, and nothing said so: the run completed,
# exported, and reported loads for a rotor whose moving set was wrong.
#
# WHY THESE TESTS ARE HERE AND NOT IN tests/test_script_entities.py. That
# module is FR-30b's old evidence and the requirement is TRUE there: the
# script layer has always resolved a declared label. It could not fail on
# this defect, because nothing in src/ ever declared an inventory, so the
# label half of "either an index or a label" was unreachable from a matrix
# row. A requirement whose evidence answers a narrower question than the
# claim is the defect class this repository has now paid for three times.


def _saved_simulation(path: Path, names: Sequence[str]) -> Path:
    """Write the smallest saved simulation carrying a mesh block.

    Built from the format's own shape rather than copied from a campaign
    geometry, for two reasons: those files are 1 to 9 MB, and some of
    them are derivatives that may not be distributed. What is reproduced
    here is exactly what the reader reads, including the two junk lines
    between the marker and the count and the head numbers STARTING AT 2,
    which is what seven of the eight real geometries do and what makes a
    reader that mistook the head number for the index wrong here.
    """
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    # `newline=""` because the CRLF here is DATA, not formatting. Without
    # it the platform translates each "\n" again and the file gains a
    # blank line between every record, which the reader then reports as a
    # count line that is not a number. The real geometries are CRLF, so
    # this writes the bytes they carry rather than the bytes this
    # platform would have chosen.
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


def _rotor_row(geometry: Path, cell: str, sim_id: str = "8001") -> SimCase:
    """A rotor case in the shape a matrix row converts to."""
    return rotor_case(MOVING_BOUNDARIES=cell).model_copy(
        update={"sim_id": sim_id, "geometry": str(geometry)}
    )


def _moving_payload(text: str) -> str:
    """The continuation line under SET_MOTION_BOUNDARIES."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("SET_MOTION_BOUNDARIES"):
            return lines[index + 1]
    raise AssertionError(f"no SET_MOTION_BOUNDARIES in:\n{text}")


@pytest.mark.requirement("FR-30b")
def test_a_rotor_row_naming_a_boundary_family_moves_those_surfaces(tmp_path):
    """FR-30b at the surface a user writes, which is a matrix row.

    Four clauses, and the order is the point. Clause one fails FIRST on
    today's code, on a plain equality about the inventory, so the test
    fails for the RIGHT reason: not because a name is unknown, but
    because the package never declared the inventory the name lives in.
    Written the naive way, this test would have failed with "no mesh
    boundary labels are registered yet", which is the same evidence
    dressed up as the user's mistake.
    """
    sector = _saved_simulation(tmp_path / "sector.fsm", ["Blade1", "S", "N"])
    script = Script("26.123")
    build_script(_rotor_row(sector, "Blade,S"), script)

    # 1. THE PACKAGE DECLARED THE INVENTORY. This is the clause that
    #    fails on 0.10.0, before any name is resolved.
    assert script.num_boundaries == 3, (
        "the package did not declare the opened geometry's boundary inventory, so a "
        "row naming a family has nothing to resolve against and FR-30b's label half "
        "is unreachable from a matrix row"
    )
    assert script.entities.labels("boundaries") == {"Blade1": 1, "S": 2, "N": 3}

    # 2. The family resolved to the positions those names hold HERE.
    assert _moving_payload(script.render()) == "1,2"


@pytest.mark.requirement("FR-30b")
def test_one_family_cell_follows_the_geometry_instead_of_a_fixed_position(tmp_path):
    """The clause that FALSIFIES the defect rather than restating it.

    The same cell, against two files that order the same names
    differently, must emit different indices. A row of positions cannot
    have this property, and a test that only checked one file would pass
    against a mapping hard-coded to that file.
    """
    sector = _saved_simulation(tmp_path / "sector.fsm", ["Blade1", "S", "N"])
    wheel = _saved_simulation(
        tmp_path / "wheel.fsm",
        ["Blade1", "S", "N", "Blade2", "Blade3", "Blade4", "Blade5", "Blade6"],
    )

    rendered = {}
    for name, geometry in (("sector", sector), ("wheel", wheel)):
        script = Script("26.123")
        build_script(_rotor_row(geometry, "Blade,S"), script)
        rendered[name] = _moving_payload(script.render())

    assert rendered["sector"] == "1,2"
    assert rendered["wheel"] == "1,2,4,5,6,7,8", (
        "the family did not follow the file's own order, so one cell does not mean "
        "the rotating surfaces of whatever geometry the row opens"
    )
    assert rendered["sector"] != rendered["wheel"], (
        "one cell emitted the same positions against two different boundary orders, "
        "which is the defect this release closes wearing a name"
    )

    # AND THE DEFECT ITSELF, measured beside it: the positional cell is
    # blind to the file. This is the assertion that makes the pair above
    # evidence rather than a description.
    positional = {}
    for name, geometry in (("sector", sector), ("wheel", wheel)):
        script = Script("26.123")
        with pytest.warns(PyflightstreamWarning, match="POSITION"):
            build_script(_rotor_row(geometry, "1,2"), script)
        positional[name] = _moving_payload(script.render())
    assert positional["sector"] == positional["wheel"] == "1,2", (
        "the positional cell stopped being blind to the geometry, so the comparison "
        "above no longer demonstrates anything"
    )


def test_an_exact_boundary_label_is_not_read_as_its_family(tmp_path):
    """`Blade1` means one blade, and `Blade` means all of them.

    Exact before family is load-bearing: `Blade1` is both a label and a
    member of family `blade`, so a family match tried first would turn a
    row citing ONE blade into a row citing six, silently.
    """
    wheel = _saved_simulation(
        tmp_path / "wheel.fsm",
        ["Blade1", "S", "N", "Blade2", "Blade3", "Blade4", "Blade5", "Blade6"],
    )
    script = Script("26.123")
    build_script(_rotor_row(wheel, "Blade1,S"), script)
    assert _moving_payload(script.render()) == "1,2", (
        "an exact boundary label expanded as if it were a family name"
    )


def test_a_row_naming_a_surface_the_geometry_lacks_is_refused_naming_what_it_has(tmp_path):
    """An unknown name is refused, and the refusal is didactic."""
    sector = _saved_simulation(tmp_path / "sector.fsm", ["Blade1", "S", "N"])
    script = Script("26.123")
    with pytest.raises(ScriptReferenceError) as raised:
        build_script(_rotor_row(sector, "Blade,Nacelle"), script)
    message = str(raised.value)
    assert "Nacelle" in message
    assert "Blade1" in message and "'S'" in message, (
        "the refusal does not list the labels the geometry actually carries, so it "
        "tells the user they are wrong without telling them what is right"
    )
    assert "no mesh boundary labels are registered yet" not in message, (
        "the refusal took the undeclared-inventory branch, which means the package "
        "did not declare the inventory and this test is passing for the wrong reason"
    )


def test_a_positional_row_still_works_and_says_what_the_positions_are(tmp_path):
    """Non-vacuity, and the patch's own promise.

    An index keeps working, because sixteen committed goldens carry this
    line and a patch may not change an input a correct matrix already
    uses. What it gains is a warning that names the surfaces those
    positions actually select in THIS file, which is a migration
    instruction rather than a scold, and which only a package that read
    the file can write.
    """
    wheel = _saved_simulation(
        tmp_path / "wheel.fsm",
        ["Blade1", "S", "N", "Blade2", "Blade3", "Blade4", "Blade5", "Blade6"],
    )
    script = Script("26.123")
    with pytest.warns(PyflightstreamWarning) as caught:
        build_script(_rotor_row(wheel, "1,2,4,5,6,7,8"), script)
    assert _moving_payload(script.render()) == "1,2,4,5,6,7,8", (
        "a row of positions stopped emitting what it emitted before this release, "
        "which is a change to an input a correct matrix already uses"
    )
    message = str(caught[0].message)
    assert "1 is Blade1" in message and "4 is Blade2" in message, (
        "the warning does not say which surfaces the positions select, so it tells "
        "the user to change something without telling them to what"
    )


def test_a_geometry_with_no_mesh_block_leaves_the_inventory_exactly_as_it_was(tmp_path):
    """The compatibility floor, asserted rather than assumed.

    FR-30c licenses an undeclared inventory as permissive, and the suite
    stages placeholder geometries deliberately. A placeholder must not
    start refusing, and a positional row against one must not warn,
    because the package cannot say what those positions name.
    """
    placeholder = tmp_path / "placeholder.fsm"
    placeholder.write_bytes(b"fake simulation")
    script = Script("26.123")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        build_script(_rotor_row(placeholder, "1,2"), script)
    assert script.num_boundaries is None, (
        "a file carrying no mesh block declared an inventory, so the reader invented "
        "boundaries the geometry does not describe"
    )
    assert _moving_payload(script.render()) == "1,2"


def test_a_mesh_block_that_opens_and_breaks_is_reported_and_never_guessed(tmp_path):
    """A malformed block must not produce a half-read map.

    It warns and leaves the inventory undeclared, which is the state the
    run was in before this release. It does NOT refuse: a patch may not
    stop a campaign that ran yesterday over a file the solver itself
    accepts.
    """
    broken = tmp_path / "broken.fsm"
    broken.write_text(
        "\r\n".join([MESH_MARKER, "9999", "99", "3", "2, T, T, F", "Blade1", ".5,.5,.5"]) + "\r\n",
        encoding="utf-8",
        newline="",
    )
    script = Script("26.123")
    with pytest.warns(PyflightstreamWarning, match="ends after"):
        build_script(_rotor_row(broken, "1,2"), script)
    assert script.num_boundaries is None


def test_a_boundary_named_as_a_number_is_refused_by_the_reader(tmp_path):
    """A name that is a bare number reopens the door being closed.

    It could not be told apart from a POSITION in a cell, so the reader
    refuses the file rather than admitting an ambiguity through the one
    door this release exists to shut.
    """
    numeric = _saved_simulation(tmp_path / "numeric.fsm", ["Blade1", "5", "N"])
    with pytest.raises(MeshReadError, match="cannot be told apart"):
        boundary_names(numeric)


def test_two_boundaries_sharing_a_name_lose_it_rather_than_one_of_them(tmp_path):
    """A duplicate must not silently drop a boundary.

    A dict comprehension would keep the later position and lose the
    earlier boundary without a word, capping the declared inventory below
    the file's true count and turning a correct position into a refusal.
    The name goes, both boundaries stay citable by position, and the
    declared total still equals the file's own count.
    """
    twinned = _saved_simulation(tmp_path / "twinned.fsm", ["Blade", "S", "Blade"])
    labels, ambiguous = boundary_labels(boundary_names(twinned))
    assert labels == {"S": 2}
    assert ambiguous == ("Blade",)

    script = Script("26.123")
    with pytest.warns(PyflightstreamWarning) as caught:
        build_script(_rotor_row(twinned, "1,3"), script)
    said = [str(warning.message) for warning in caught]
    assert any("more than once" in message for message in said), said
    # AND THE POSITIONAL WARNING MUST NOT LIE ABOUT THEM. Positions 1 and
    # 3 ARE boundaries; they simply have no unique name. Reporting them as
    # "no boundary in this geometry" would be a false statement about the
    # user's own mesh, inside the message telling them to trust names.
    assert not any("1 is no boundary" in message for message in said), said
    assert script.num_boundaries == 3, (
        "the declared inventory is smaller than the file's boundary count, so a "
        "correct position would now be refused as out of range"
    )
    assert _moving_payload(script.render()) == "1,3"


# --- PFS-2028.01: the acceptance of a run type that turns nothing ------------


def _time_loop(text: str) -> str:
    """The emitted time loop, WITH ITS CONTINUATION LINES.

    The command's own line carries no numbers; the step and the count
    follow it as keyword lines. Returning the first line alone made the
    first version of this test compare two identical strings while
    asserting they differed, which is the same failure mode the test
    exists to catch, one level up.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("SET_SOLVER_UNSTEADY"):
            return "\n".join(lines[index : index + 3])
    raise AssertionError(f"no SET_SOLVER_UNSTEADY in:\n{text}")


def test_the_third_run_type_is_registered_and_covers_every_build():
    """PFS-2028.01: the exercise's third shape can be named by a row.

    The coverage is DERIVED from the command database rather than
    declared, and it comes out wider than the rotor type's because this
    run emits neither motion command. That is the measurable reason the
    type is separate rather than the rotor one with its motion switched
    off: folding them would refuse a rotorless run on three builds for
    commands it never emits.
    """
    assert workflow_names() == ("steady", "unsteady", "unsteady_rotor")
    assert len(covered_builds(WORKFLOWS["unsteady"])) == len(known_versions())
    assert len(covered_builds(WORKFLOWS["unsteady_rotor"])) < len(known_versions())


def test_the_rows_own_clock_reaches_the_emitted_time_loop():
    """The clause a hardcoded clock fails.

    Two different rows must produce two different time loops. A builder
    that emitted a fixed step and count would satisfy any single-row
    assertion, and this repository has shipped that defect twice: the
    note on `rotor_case_full` records both.
    """
    rendered = {}
    for label, case in (("bare", unsteady_case()), ("full", unsteady_case_full())):
        script = Script("26.123")
        build_script(case, script)
        rendered[label] = _time_loop(script.render())
    assert rendered["bare"] != rendered["full"], (
        "two rows stating different clocks emitted the same time loop, so the clock is "
        "not coming off the row"
    )
    assert "480" in rendered["bare"] and "0.00025" in rendered["bare"], rendered["bare"]
    assert "240" in rendered["full"] and "0.0005" in rendered["full"], rendered["full"]


def test_the_rotorless_type_emits_no_motion_and_no_frame():
    """The whole difference from the rotor type, asserted rather than assumed."""
    script = Script("26.123")
    build_script(unsteady_case(), script)
    text = script.render()
    assert "SET_SOLVER_UNSTEADY" in text
    for absent in (
        "CREATE_NEW_MOTION",
        "SET_MOTION_BOUNDARIES",
        "SET_MOTION_ROTOR_RPM",
        "CREATE_NEW_COORDINATE_SYSTEM",
    ):
        assert absent not in text, f"a run that turns nothing emitted {absent}"


@pytest.mark.parametrize(
    "key,value",
    [
        ("RPM", "1200"),
        ("ADVANCE_RATIO", "1.7"),
        ("RPM_SIGN", "-1"),
        ("ROTOR_AXIS", "X"),
        ("ROTOR_ORIGIN", "0,0,0"),
        ("MOVING_BOUNDARIES", "1,2"),
    ],
)
def test_a_rotor_key_on_a_rotorless_row_is_refused_naming_it(key, value):
    """A key that reaches no line is refused, not dropped.

    The steady type tolerates these today, silently, and that is a
    latent instance of this same defect rather than a precedent: this
    package already refuses a preset key that validates and reaches no
    emitted line, calling it the same wrong answer with a longer path.
    """
    script = Script("26.123")
    with pytest.raises(CampaignConfigError) as raised:
        build_script(unsteady_case(**{key: value}), script)
    message = str(raised.value)
    assert key in message
    assert "7003" in message
    assert script.render().strip() == "", "the refusal landed after something was emitted"


def test_the_angular_clock_is_refused_and_the_refusal_offers_no_rotor_speed():
    """The open question, settled and guarded.

    The refusal must NOT tell the author to state a rotor speed. The
    rotor resolver's message does exactly that, and an author who obeys
    it gets a run that builds: the step becomes theta over six times the
    speed, so a run emitting no motion takes its physical clock from a
    number nothing turns at.
    """
    script = Script("26.123")
    with pytest.raises(CampaignConfigError) as raised:
        build_script(unsteady_case(DELTA_THETA="10.0", REVOLUTIONS="2.0"), script)
    message = str(raised.value)
    assert "DELTA_THETA" in message and "REVOLUTIONS" in message
    assert "RPM" not in message and "ADVANCE_RATIO" not in message, (
        "the refusal offers a rotor speed to a run that turns nothing, which is the "
        "advice that manufactures a clock from a number nothing uses"
    )
    assert "DELTA_TIME" in message and "TIME_ITERATIONS" in message


@pytest.mark.parametrize("stated", ["DELTA_TIME", "TIME_ITERATIONS"])
def test_half_a_clock_is_refused_naming_the_missing_half(stated):
    """A step with no count has no length, and a count with no step no duration."""
    absent = "TIME_ITERATIONS" if stated == "DELTA_TIME" else "DELTA_TIME"
    script = Script("26.123")
    with pytest.raises(CampaignConfigError) as raised:
        build_script(unsteady_case(**{absent: None}), script)
    assert absent in str(raised.value)


def test_a_wake_termination_in_revolutions_is_refused_without_the_wrong_reason():
    """The third sibling guard, and why the two that exist were not enough.

    Both existing guards give this run type false advice: the rotor one
    tells the author to state a rotor speed, and the steady one says the
    run has no time loop, which is untrue of this type. A refusal that
    misdescribes the run it refuses teaches the reader the wrong thing
    about their own row.
    """
    case = unsteady_case()
    case = case.model_copy(
        update={"solver": case.solver.model_copy(update={"wake_termination_revolutions": 3.0})}
    )
    script = Script("26.123")
    with pytest.raises(CampaignConfigError) as raised:
        build_script(case, script)
    message = str(raised.value)
    assert "revolution" in message
    assert "no time loop" not in message, (
        "the refusal claims this run type has no time loop, and it has one"
    )
    assert "RPM" not in message and "ADVANCE_RATIO" not in message, (
        "the refusal offers a rotor speed to a run that turns nothing"
    )
