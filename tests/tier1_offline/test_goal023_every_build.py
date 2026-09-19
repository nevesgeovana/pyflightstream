"""Tier 1: every matrix workflow on every registered build (GOAL-023, 0.20.0, FR-101).

One seam decides how an unsteady row is marched on a build: with the solver's
per-step actions where the row asks for what only they give and the build
documents them, and as a SINGLE MARCH otherwise, which is one solver start over
every time step with the plots declared before it and the exports after. A row
that asks, on a build without actions, for something only actions give is
refused before any line is emitted, naming the build, the feature and the
remedy. The strategy is recorded in the plan and in the run record.

The test names carry ``goal023_<arm>`` so the goal's checker can select them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    MARCH_ACTIONS,
    MARCH_SINGLE,
    WORKFLOW_KEY,
    WORKFLOWS,
    BuildCapabilities,
    BuildCapabilityError,
    WorkflowCoverageError,
    build_script,
    march_strategy,
    reduction_windows,
    workflow_registry,
)
from pyflightstream.commands import CommandRegistry
from pyflightstream.run import plan_campaign, run_campaign
from pyflightstream.script import CommandArgumentError, Script
from pyflightstream.versions import known_versions
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_run_campaign import StubSolver, converged
from tests.tier1_offline.test_workflows import (
    GOLDEN_CASES,
    GOLDEN_WORKFLOWS,
    golden_name,
    rendered,
    rotor_case,
    unsteady_case,
)

BUILDS = [version.canonical for version in known_versions()]
#: The builds whose database documents the per-step action command, derived
#: rather than listed, so a build that gains it moves between the two sets.
WITH_ACTIONS = [
    b for b in BUILDS if "SET_NEW_UNSTEADY_SOLVER_ACTION" in CommandRegistry.load().for_version(b)
]
WITHOUT_ACTIONS = [b for b in BUILDS if b not in WITH_ACTIONS]


def _commands(text: str) -> list[str]:
    """The command token of every line that starts one, in order."""
    return [
        line.split()[0]
        for line in text.splitlines()
        if line
        and not line.startswith((" ", "#"))
        and line.split()[0].isupper()
        and "_" in line.split()[0]
    ]


# ------------------------------------------------------------ capabilities --


def test_goal023_single_march_the_capabilities_are_derived_from_the_database():
    """Measured over every build, never a list: the action command decides it."""
    registry = CommandRegistry.load()
    for build in BUILDS:
        view = registry.for_version(build)
        capabilities = BuildCapabilities.of(view)
        assert capabilities.build == build
        assert capabilities.unsteady_actions is ("SET_NEW_UNSTEADY_SOLVER_ACTION" in view), build
    assert "26.123" in WITH_ACTIONS and "26.124" in WITH_ACTIONS
    assert "26.120" in WITHOUT_ACTIONS and "25.000" in WITHOUT_ACTIONS


# ------------------------------------------------------------- single march --


@pytest.mark.parametrize("build", [b for b in WITHOUT_ACTIONS if b != "25.000"])
def test_goal023_single_march_an_unsteady_row_marches_once_on_a_build_without_actions(build):
    """No action is registered and the solver starts once over every step the row states."""
    script = Script(build)
    build_script(unsteady_case(), script)
    text = script.render()
    commands = _commands(text)
    assert script.march_strategy == MARCH_SINGLE
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" not in commands
    assert commands.count("START_SOLVER") == 1, commands
    assert "TIME_ITERATIONS 480" in text.split("START_SOLVER", 1)[0], (
        "the one start does not march every step"
    )
    assert commands.index("SET_SOLVER_UNSTEADY") < commands.index("START_SOLVER")


def test_goal023_single_march_the_rotor_script_without_actions_is_in_the_legacy_order():
    """The tier-3 rotor row on 26.120, as the whole pipeline renders it (its golden is pinned).

    The plots are declared before the one solver start, and the plots table,
    every other export and the log come after it: the legacy scripts' order.
    """
    goldens = Path(__file__).resolve().parents[1] / "tier3_licensed" / "goldens" / "matriz_builds"
    text = next(goldens.glob("P7001-*.txt")).read_text(encoding="utf-8")
    commands = _commands(text)
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" not in commands
    assert commands.count("START_SOLVER") == 1
    start = commands.index("START_SOLVER")
    plots = [i for i, name in enumerate(commands) if name.startswith("UNSTEADY_SOLVER_NEW_")]
    assert plots and max(plots) < start, "a plot was declared after the solver started"
    assert commands.index("UNSTEADY_SOLVER_EXPORT_PLOTS") > start
    assert commands.index("EXPORT_LOG") > start


def test_goal023_single_march_the_reductions_of_a_single_march_come_from_the_row_clock():
    """The time average, phase-locked and per-blade windows need no action record."""
    windows = reduction_windows(rotor_case())
    assert windows is not None
    for name in ("time_average", "phase_locked", "per_blade"):
        assert "windows" in windows[name], (name, windows[name])


@pytest.mark.parametrize("build", WITH_ACTIONS)
def test_goal023_single_march_a_row_asking_for_nothing_actions_give_marches_once_where_they_exist(
    build,
):
    """On a build WITH actions, a row that asks for none of them is the same single march."""
    case = unsteady_case()
    script = Script(build)
    build_script(case, script)
    assert script.march_strategy == MARCH_SINGLE
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" not in _commands(script.render())


def test_goal023_single_march_a_row_asking_for_actions_where_they_exist_uses_them():
    case = unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="2")
    script = Script("26.123")
    build_script(case, script)
    assert script.march_strategy == MARCH_ACTIONS
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION" in _commands(script.render())


def test_goal023_single_march_a_steady_row_has_no_march_strategy():
    script = Script("26.123")
    build_script(GOLDEN_CASES["steady"]["bare"](), script)
    assert script.march_strategy is None


# ------------------------------------------------------------ told, not hidden --


FEATURES = [
    ({"WALLTIME": "1h"}, "WALLTIME", "RESTART: {ADDITIONAL_ITERS=n}"),
    ({"EXPORT_UNSTEADY_AFTER_ITER": "2"}, "EXPORT_UNSTEADY_AFTER_ITER", "plots table"),
    ({"EXPORT_UNSTEADY_AFTER_REV": "1"}, "EXPORT_UNSTEADY_AFTER_REV", "plots table"),
    ({"RESTART": "{FINISH_PENDING}"}, "FINISH_PENDING", "ADDITIONAL_ITERS"),
    ({"RESTART": "{ADDITIONAL_REVS=1}"}, "ADDITIONAL_REVS", "ADDITIONAL_ITERS"),
]


@pytest.mark.parametrize(("cells", "feature", "remedy"), FEATURES)
def test_goal023_told_not_hidden_an_actions_feature_on_a_build_without_them_is_refused_by_name(
    cells, feature, remedy
):
    """Refused before the first line, naming the build, the feature and what to write."""
    case = rotor_case(**cells) if "REV" in feature else unsteady_case(**cells)
    script = Script("26.120")
    with pytest.raises(BuildCapabilityError) as refused:
        build_script(case, script)
    message = str(refused.value)
    assert "26.120" in message, message
    assert feature in message, message
    assert remedy in message, message
    assert "26.123" in message, "the refusal does not name a build that has the feature"
    assert script.render().strip() == "", "a line was emitted before the refusal"


def test_goal023_told_not_hidden_march_strategy_refuses_without_building():
    """The seam is callable on its own, so the plan can ask it."""
    registry = CommandRegistry.load()
    with pytest.raises(BuildCapabilityError):
        march_strategy(
            unsteady_case(WALLTIME="10m"),
            capabilities=BuildCapabilities.of(registry.for_version("25.100")),
        )
    assert (
        march_strategy(unsteady_case(), capabilities=BuildCapabilities.for_build("25.100"))
        == MARCH_SINGLE
    )
    assert BuildCapabilities.for_build("26.124") == BuildCapabilities.of(
        registry.for_version("26.124")
    )


def test_goal023_told_not_hidden_the_refusal_names_the_cell_to_change_and_each_threshold():
    """Api lens L2 and L3: FS_BUILD is named, and each threshold's remedy names its own key."""
    case = unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="2", EXPORT_UNSTEADY_AFTER_REV="1")
    with pytest.raises(BuildCapabilityError) as refused:
        build_script(case, Script("26.120"))
    message = str(refused.value)
    assert "Set FS_BUILD to a build that documents them" in message, message
    assert (
        "remove EXPORT_UNSTEADY_AFTER_ITER" in message
        and "remove EXPORT_UNSTEADY_AFTER_REV" in message
    )
    assert "Once they are removed, the row runs on 26.120 as a single march" in message


BUILD_ROWS = [
    ("plain", {}),
    ("threshold", {"EXPORT_UNSTEADY_AFTER_ITER": "2"}),
    ("clock", {"WALLTIME": "1h"}),
]


@pytest.mark.parametrize("build", WITH_ACTIONS)
@pytest.mark.parametrize(("label", "cells"), BUILD_ROWS)
def test_goal023_told_not_hidden_the_label_is_what_the_script_registers(build, label, cells):
    """Qa lens 3: the recorded strategy and the emitted actions agree on every row shape."""
    script = Script(build)
    build_script(unsteady_case(**cells), script)
    emitted = "SET_NEW_UNSTEADY_SOLVER_ACTION" in _commands(script.render())
    assert (script.march_strategy == MARCH_ACTIONS) is emitted, (label, script.march_strategy)


def test_goal023_told_not_hidden_a_label_that_disagrees_with_the_script_is_refused(monkeypatch):
    """Architect lens F1: build_script holds the label and the script together."""
    from pyflightstream.cases import workflows

    monkeypatch.setattr(workflows, "march_strategy", lambda case, **_: MARCH_ACTIONS)
    with pytest.raises(workflows.WorkflowCoverageError, match="internal defect"):
        build_script(unsteady_case(), Script("26.123"))
    # The other direction (qa lens, round two): a single march whose script
    # registers actions is refused too.
    monkeypatch.setattr(workflows, "march_strategy", lambda case, **_: MARCH_SINGLE)
    with pytest.raises(workflows.WorkflowCoverageError, match="internal defect"):
        build_script(unsteady_case(EXPORT_UNSTEADY_AFTER_ITER="2"), Script("26.123"))


def test_goal023_told_not_hidden_the_record_refuses_a_strategy_outside_the_closed_set():
    """Api lens M2: the run record takes the two marches and None, nothing else."""
    from pydantic import ValidationError

    from pyflightstream.workspace import RunRecord

    minimal = {
        "run_id": "camp/sim_1/a+00.0",
        "sim_id": "1",
        "fs_version_requested": "26.120",
        "package_version": "0.20.0",
        "script_sha256": "0" * 64,
        "raw_flag": False,
        "status": "CONVERGED",
    }
    assert RunRecord.model_fields["march_strategy"].default is None
    with pytest.raises(ValidationError):
        RunRecord.model_validate({**minimal, "march_strategy": "single-march"})
    assert RunRecord.model_validate({**minimal, "march_strategy": MARCH_SINGLE}).march_strategy == (
        MARCH_SINGLE
    )


def _campaign(build: str, **variables) -> Campaign:
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_{point}.txt"],
        variables={
            WORKFLOW_KEY: "unsteady",
            "VELOCITY": "30.0",
            "DELTA_TIME": "0.01",
            "TIME_ITERATIONS": "4",
            # The whole run, which is the window a rotorless row with none
            # was given before 0.24.0 made the key mandatory.
            "LAST_ITERS_AVG": "4",
            **variables,
        },
    )
    return Campaign(name="camp", fs_version=build, fs_exe=sys.executable, sims=[case])


def test_goal023_told_not_hidden_the_plan_records_the_strategy_and_blocks_by_name(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    recipes = {"unsteady": workflow_registry()["unsteady"]}
    plan = plan_campaign(_campaign("26.120"), workspace, recipes=recipes, write_plan=False)
    assert plan.points[0].march_strategy == MARCH_SINGLE, plan.points[0]
    blocked = plan_campaign(
        _campaign("26.120", WALLTIME="1h"),
        CampaignWorkspace(tmp_path / "camp2"),
        recipes=recipes,
        write_plan=False,
    )
    assert blocked.points[0].status.name == "BLOCKED"
    assert "WALLTIME" in (blocked.points[0].error or "") and "26.120" in (
        blocked.points[0].error or ""
    )


def test_goal023_told_not_hidden_the_run_record_carries_the_strategy(tmp_path):
    from tests.tier1_offline.test_run_campaign import WRITES_LOADS

    workspace = CampaignWorkspace(tmp_path / "camp")
    records = run_campaign(
        _campaign("26.120"),
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"unsteady": workflow_registry()["unsteady"]},
    )
    assert records[0].status in (RunStatus.CONVERGED, RunStatus.FAILED_INCOMPLETE_OUTPUT), records[
        0
    ].error
    assert records[0].march_strategy == MARCH_SINGLE
    assert workspace.read_manifest()[0].march_strategy == MARCH_SINGLE


# ---------------------------------------------------------------- transparent --


@pytest.mark.parametrize("name", ["unsteady", "steady"])
def test_goal023_transparent_one_row_plans_on_every_build_with_only_the_build_changed(
    name, tmp_path
):
    """The same case, the same cells, every build: no key is added to make it run."""
    case = GOLDEN_CASES[name]["bare"]()
    for build in BUILDS:
        if (name, build) in NOT_YET_RENDERED:
            continue
        script = Script(build)
        build_script(case, script)
        assert script.render().strip(), build


# ------------------------------------------------------------ support matrix --


#: The cells of the support matrix that do not render yet, each with the reason
#: that is true today. EXACT: a cell that starts rendering must leave this table
#: in the same commit, and a cell that stops rendering must be added with its
#: reason, or the population test below fails.
#:
#: OWNER: the 25.000 edition's INITIALIZE_SOLVER takes five settings no later
#: edition exposes and no edition gives a default for (load frame, proximity
#: avoidance, stabilization, its strength, fast multipole; SRC-749 p.303), so
#: choosing them is a numerical decision that is the owner's (GOAL-023 arm 4).
#: 26.100 LEFT THIS TABLE at 0.20.1: it has no scripted rotor mark (RPT-049),
#: and the owner decided its rotor is written as a Euclidean motion without
#: the mark, the speed in rev/min (RPT-051).
NOT_YET_RENDERED = {
    ("steady", "25.000"): "OWNER",
    ("unsteady", "25.000"): "OWNER",
    ("unsteady_rotor", "25.000"): "OWNER",
}

#: How each declared cell refuses, and the words that say why (qa lens 5): a
#: refusal of another kind that merely names the build does not pass.
REFUSED_BY = {
    ("steady", "25.000"): (CommandArgumentError, "INITIALIZE_SOLVER grammar"),
    ("unsteady", "25.000"): (CommandArgumentError, "INITIALIZE_SOLVER grammar"),
    ("unsteady_rotor", "25.000"): (WorkflowCoverageError, "no CREATE_NEW_MOTION"),
}


@pytest.mark.parametrize("build", BUILDS)
@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_goal023_support_matrix_every_run_type_renders_on_every_build(name, build):
    """Every workflow and every case shape renders on every registered build.

    A render succeeding is the whole claim about commands: Script.emit refuses
    a command the build's database does not carry, so a script that renders
    carries only commands that build documents. A declared cell must REFUSE,
    by name, before it writes a line.
    """
    for label, make in sorted(GOLDEN_CASES[name].items()):
        if (name, build) in NOT_YET_RENDERED:
            kind, cause = REFUSED_BY[(name, build)]
            script = Script(build)
            with pytest.raises(kind) as refused:
                build_script(make(), script)
            assert build in str(refused.value), f"{name} {label} on {build}: {refused.value}"
            assert cause in str(refused.value), f"{name} {label} on {build}: {refused.value}"
            continue
        text = rendered(make(), build)
        assert text.strip(), f"{name} {label} rendered nothing on {build}"


def test_goal023_support_matrix_the_euclidean_rotor_is_decided_once():
    """Architect lens F2: coverage and the helper read one predicate, over every build."""
    from pyflightstream.cases.workflows import _carried
    from pyflightstream.script import rotor_vocabulary as vocabulary

    registry = CommandRegistry.load()
    for build in BUILDS:
        view = registry.for_version(build)
        euclidean = vocabulary.euclidean_rotor(view)
        unmarked = vocabulary.unmarked_euclidean_rotor(view)
        assert not (euclidean and unmarked), build
        for name in vocabulary.ROTARY_ROTOR_COMMANDS:
            assert _carried(view, name) is (name in view or euclidean or unmarked), (build, name)
    # A build carrying the rotary speed AND the whole Euclidean rotor is not
    # Euclidean, and coverage follows the predicate rather than deciding by
    # itself; no registered build is that shape, so it is built here (qa lens,
    # round two).
    both = {"SET_MOTION_ROTOR_RPM", *vocabulary.EUCLIDEAN_ROTOR_COMMANDS}
    assert vocabulary.euclidean_rotor(both) is False
    assert _carried(both, "SET_MOTION_ROTOR_AXIS") is False
    euclidean_only = set(vocabulary.EUCLIDEAN_ROTOR_COMMANDS)
    assert vocabulary.euclidean_rotor(euclidean_only) is True
    assert vocabulary.unmarked_euclidean_rotor(euclidean_only) is False
    assert _carried(euclidean_only, "SET_MOTION_ROTOR_AXIS") is True
    # The angular velocity alone is the unmarked rotor; with the rotary speed
    # beside it, it is neither.
    velocity_only = set(vocabulary.UNMARKED_EUCLIDEAN_ROTOR_COMMANDS)
    assert vocabulary.unmarked_euclidean_rotor(velocity_only) is True
    assert vocabulary.euclidean_rotor(velocity_only) is False
    assert _carried(velocity_only, "SET_MOTION_ROTOR_RPM") is True
    velocity_and_rpm = {"SET_MOTION_ROTOR_RPM", *velocity_only}
    assert vocabulary.unmarked_euclidean_rotor(velocity_and_rpm) is False
    assert _carried(velocity_and_rpm, "SET_MOTION_ROTOR_AXIS") is False
    # QA-2: the unmarked predicate decides the vocabulary, never whether the
    # build runs a rotor, so a build with the angular velocity and no
    # CREATE_NEW_MOTION is still refused on the motion, as 25.000 is.
    from pyflightstream.cases.workflows import _missing_commands, resolve_workflow
    from pyflightstream.versions import resolve

    packaged = CommandRegistry.load()
    without_motion = CommandRegistry(
        commands={
            name: entry
            for name, entry in packaged.commands.items()
            if name not in ("CREATE_NEW_MOTION", "SET_MOTION_IS_ROTOR")
        }
    )
    shape = without_motion.for_version("26.000")
    assert vocabulary.unmarked_euclidean_rotor(shape) is True
    assert _missing_commands(
        resolve_workflow("unsteady_rotor"), resolve("26.000"), without_motion
    ) == ("CREATE_NEW_MOTION",)
    mark_only = {"SET_MOTION_IS_ROTOR"}
    assert not vocabulary.euclidean_rotor(mark_only)
    assert not vocabulary.unmarked_euclidean_rotor(mark_only)
    assert _carried(mark_only, "SET_MOTION_ROTOR_AXIS") is False
    # 25.000 carries the whole Euclidean rotor and not CREATE_NEW_MOTION, so the
    # predicate holds there and coverage still refuses the build on the motion.
    assert [b for b in BUILDS if vocabulary.euclidean_rotor(registry.for_version(b))] == [
        "25.000",
        "25.100",
        "26.000",
    ]
    assert [b for b in BUILDS if vocabulary.unmarked_euclidean_rotor(registry.for_version(b))] == [
        "26.100"
    ]


def test_goal023_support_matrix_a_blade_count_refusal_names_the_builds_that_take_one():
    """Api lens M1: the remedy is derived from the database, not written as a range."""
    from pyflightstream.script import CommandArgumentError, helpers

    registry = CommandRegistry.load()
    takes_count = [
        b
        for b in BUILDS
        if "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION" in registry.for_version(b)
        and "num_blades"
        in {
            a.name for a in registry.for_version(b)["SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"].args
        }
    ]
    assert takes_count and "26.100" not in takes_count
    script = Script("26.000")
    script.declare_existing(frames=2)
    with pytest.raises(CommandArgumentError) as refused:
        helpers.rotary_motion(script, frame=2, axis="X", rpm=1200.0, wake_stabilization_blades=4)
    assert (
        f"build the script for one that takes the count (Script(version=...)): "
        f"{', '.join(takes_count)}." in str(refused.value)
    )


def test_goal023_support_matrix_the_blade_count_remedy_reads_the_scripts_own_database():
    """Architect lens, round two: a script built on another database is told about that database."""
    from pyflightstream.script import CommandArgumentError, helpers

    packaged = CommandRegistry.load()
    stabilization = "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"
    without = CommandRegistry(
        commands={name: entry for name, entry in packaged.commands.items() if name != stabilization}
    )
    script = Script("26.000", registry=without)
    script.declare_existing(frames=2)
    with pytest.raises(
        CommandArgumentError, match=r"\(Script\(version=\.\.\.\)\): no registered build\."
    ):
        helpers.rotary_motion(script, frame=2, axis="X", rpm=1200.0, wake_stabilization_blades=4)


def test_goal023_support_matrix_the_rotor_mark_is_removed_on_26100_and_carried_before_it():
    """RPT-049: the 26.100 solver ends a script at SET_MOTION_IS_ROTOR; 25.100 and 26.000 run it."""
    assert "SET_MOTION_IS_ROTOR" not in Script("26.100")._view
    for build in ("25.100", "26.000"):
        assert "SET_MOTION_IS_ROTOR" in Script(build)._view, build


@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        ({"axis": "1"}, "by letter"),
        ({"axis": "X", "wake_stabilization_blades": 4}, "blade count"),
    ],
)
@pytest.mark.parametrize("build", ["26.000", "26.100"])
def test_goal023_support_matrix_a_euclidean_rotor_refuses_what_its_vocabulary_cannot_state(
    arguments, said, build
):
    """An axis by index and a blade count have no Euclidean spelling, marked or not."""
    from pyflightstream.script import CommandArgumentError, helpers

    script = Script(build)
    script.declare_existing(frames=2)
    with pytest.raises(CommandArgumentError, match=said) as refused:
        helpers.rotary_motion(script, frame=2, rpm=1200.0, **arguments)
    assert build in str(refused.value)
    assert script.render().strip() == "", "the motion was emitted before the refusal"


def test_goal023_support_matrix_the_cells_that_do_not_render_are_exactly_the_declared_ones():
    """The table above is the population, measured rather than trusted."""
    failing = set()
    for name in WORKFLOWS:
        for build in BUILDS:
            try:
                rendered(GOLDEN_CASES[name]["bare"](), build)
            except Exception:  # noqa: BLE001 -- any refusal is a cell that does not render
                failing.add((name, build))
    assert failing == set(NOT_YET_RENDERED), (
        f"rendering now fails on {sorted(failing - set(NOT_YET_RENDERED))} and succeeds on "
        f"{sorted(set(NOT_YET_RENDERED) - failing)}; move the table with the code"
    )


# -------------------------------------------------------- unchanged on 26.123 --


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_goal023_unchanged_on_26123_every_golden_of_26123_renders_byte_for_byte(name):
    for label, make in sorted(GOLDEN_CASES[name].items()):
        golden = GOLDEN_WORKFLOWS / golden_name(name, label, "26.123")
        assert rendered(make(), "26.123") == golden.read_text(encoding="utf-8"), golden.name


# --------------------------------------------------------------- intake 26.124 --


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_goal023_intake_26124_renders_what_26123_renders(name):
    """Its manual is the 26.123 manual, so every workflow renders the same bytes."""
    for label, make in sorted(GOLDEN_CASES[name].items()):
        assert rendered(make(), "26.124") == rendered(make(), "26.123"), f"{name} {label}"
