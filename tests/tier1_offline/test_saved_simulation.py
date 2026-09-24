"""Tier 1: every workflow point leaves its final saved simulation (0.27.0, G11).

The guarantee the workflows page states, held by a test on each of its links:

* every workflow script of every run type, on every build a run type renders
  on, saves the point's ``.fsm`` once, after its last solve and before the
  close, first among the point's exports, and each point of a steady sweep
  saves its own;
* every tier-3 script of a row naming a run type does, rendered through the
  real matrix path with the real post-processing artifacts;
* a pproc artifact cannot switch it off, as it cannot switch the loads off;
* the file reaches ``datapoints/DP-<point>/`` and the run record, with its
  sha256, and a point whose file is not there is recorded
  ``FAILED_INCOMPLETE_OUTPUT``;
* ``pyfs-matrix plan`` names every ``LEGACY`` row whose outputs declare none,
  because its final state is neither collected nor recorded.

A case written in Python that declares its own ``outputs`` exports exactly
those (``test_a_row_declaring_a_loads_table_and_a_log_gets_exactly_those`` in
``test_workflows.py``), so the rows below are built as the matrix path builds
them: the outputs a row naming a run type gets from its pproc artifact.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    EXPORT_KINDS,
    PprocSpec,
    SimCase,
    case_at_point,
    classify_outputs,
)
from pyflightstream.cases.matrix import LEGACY_WORKFLOW, OUTPUTS_VARIABLE, read_matrix
from pyflightstream.cases.workflows import (
    LOG_OUTPUT_VARIABLE,
    WORKFLOWS,
    build_script,
    build_steady_sweep,
    workflow_registry,
)
from pyflightstream.run import CampaignErrors, PlanStatus
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import Script
from pyflightstream.versions import known_versions
from pyflightstream.workspace import CampaignWorkspace, InputArtifactError, RunStatus
from tests.tier1_offline.test_goal023_every_build import NOT_YET_RENDERED
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    REGISTRY_FIXTURE,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
    make_library,
    matrix_recipe,
)
from tests.tier1_offline.test_workflows import GOLDEN_CASES, steady_case

REPO = Path(__file__).resolve().parents[2]
TIER3 = REPO / "tests" / "tier3_licensed"
BUILDS = [version.canonical for version in known_versions()]
#: Every (run type, build) cell that renders. The cells that do not are the
#: declared ones, whose population ``test_goal023_every_build`` measures.
CELLS = [
    (name, build)
    for name in sorted(WORKFLOWS)
    for build in BUILDS
    if (name, build) not in NOT_YET_RENDERED
]
#: The number of tier-3 scripts of rows naming a run type: 57 measured at
#: bff91d6, 70 since the mesh matrix (8) and the GUI matrix (5) of 0.27.0, and
#: 74 since the GUI matrix's custom free-stream rows (4, G15).
#: A floor, so a matrix that gains rows keeps passing and one that loses its
#: goldens does not pass by checking nothing.
TIER3_WORKFLOW_GOLDENS = 74
#: The words the plan warning and the page share with these tests.
UNSAVED = "declare no saved simulation"


def as_a_matrix_row(case: SimCase, name: str, stem: str) -> SimCase:
    """The case as a matrix row naming ``name`` reaches the builder.

    Its outputs are the default set of a pproc artifact, rendered for one
    point the way the run layer renders ``{name}``, and a row naming a run
    type carries neither OUTPUTS nor LOG_OUTPUT: the reader refuses both.
    """
    outputs = PprocSpec().outputs(unsteady=name.startswith("unsteady"))
    return case.model_copy(
        update={
            "outputs": [output.replace("{name}", stem) for output in outputs],
            "variables": {
                key: value
                for key, value in case.variables.items()
                if key not in (OUTPUTS_VARIABLE, LOG_OUTPUT_VARIABLE)
            },
        }
    )


def saves(lines: list[str]) -> list[tuple[int, str]]:
    """Every SAVEAS of a script, as (line index, the name it saves)."""
    return [(index, lines[index + 1]) for index, line in enumerate(lines) if line == "SAVEAS"]


def starts(lines: list[str]) -> list[int]:
    return [index for index, line in enumerate(lines) if line == "START_SOLVER"]


# --------------------------------------------------------------- the scripts --


@pytest.mark.parametrize(("name", "build"), CELLS, ids=[f"{n}-{b}" for n, b in CELLS])
def test_g11_every_workflow_script_saves_its_final_simulation(name, build):
    """One SAVEAS of the point's .fsm, after the last solve and before the close."""
    for label, make in sorted(GOLDEN_CASES[name].items()):
        case = as_a_matrix_row(make(), name, f"P{make().sim_id}-M100AL+000")
        script = Script(build)
        build_script(case, script)
        lines = script.render().splitlines()
        saved = saves(lines)
        wanted = classify_outputs(case.outputs)["simulation"]
        assert [what for _, what in saved] == [wanted], (
            f"{name} {label} on {build} saves {saved}, and the point declares {wanted}"
        )
        (at, _), last = saved[0], starts(lines)[-1]
        assert last < at < lines.index("CLOSE_FLIGHTSTREAM"), (
            f"{name} {label} on {build}: SAVEAS at line {at}, the last START_SOLVER at "
            f"{last}; the save must hold the state the point ended in"
        )


#: The verbs that write a point's files, the save apart: what "first among its
#: exports" is measured against.
EXPORT_VERBS = frozenset(verb for _kind, _suffix, verb, _ in EXPORT_KINDS) - {"SAVEAS"}


@pytest.mark.parametrize(("name", "build"), CELLS, ids=[f"{n}-{b}" for n, b in CELLS])
def test_g11_the_save_comes_first_among_the_points_exports(name, build):
    """D07: the page says the save comes "first among its exports"; every export follows it."""
    for label, make in sorted(GOLDEN_CASES[name].items()):
        case = as_a_matrix_row(make(), name, f"P{make().sim_id}-M100AL+000")
        script = Script(build)
        build_script(case, script)
        lines = script.render().splitlines()
        ((at, _),) = saves(lines)
        last = starts(lines)[-1]
        exports = [
            index for index in range(last, len(lines)) if lines[index].split(" ")[0] in EXPORT_VERBS
        ]
        assert exports, f"{name} {label} on {build} exports nothing after its last solve"
        assert at < exports[0], (
            f"{name} {label} on {build}: {lines[exports[0]]} at line {exports[0]} comes "
            f"before the SAVEAS at line {at}"
        )


@pytest.mark.parametrize("build", [b for n, b in CELLS if n == "steady"])
def test_g11_every_point_of_a_steady_sweep_saves_its_own(build):
    """A steady row is one job since 0.17.0, and each of its points saves its own."""
    angles = (0, 2, 4)
    cases = [
        case_at_point(
            as_a_matrix_row(steady_case(), "steady", f"P7002-M100AL+{10 * angle:03d}"),
            {"alpha": float(angle)},
        )
        for angle in angles
    ]
    script = Script(build)
    build_steady_sweep(cases, script)
    lines = script.render().splitlines()
    saved = saves(lines)
    assert [what for _, what in saved] == [
        classify_outputs(case.outputs)["simulation"] for case in cases
    ], f"on {build} the sweep saves {saved}"
    solves = starts(lines)
    assert len(solves) == len(angles), solves
    bounds = [*solves[1:], lines.index("CLOSE_FLIGHTSTREAM")]
    for (at, what), solve, following in zip(saved, solves, bounds, strict=True):
        assert solve < at < following, (
            f"on {build} {what} is saved at line {at}, outside its point's solve "
            f"({solve}) and the next ({following})"
        )


def test_g11_every_workflow_golden_of_the_tier3_matrices_saves_its_point():
    """The real matrix path, over the real pproc artifacts of the tier-3 library.

    A LEGACY row's recipe decides what it saves, so its goldens are left out
    and nothing is asserted about them.
    """
    legacy = {
        (matrix.stem, row.pol)
        for matrix in TIER3.glob("*.fs")
        for row in read_matrix(matrix, active_only=False)
        if row.workflow == LEGACY_WORKFLOW
    }
    checked = 0
    for golden in sorted((TIER3 / "goldens").glob("*/*.txt")):
        if (golden.parent.name, golden.stem.split("-")[0][1:]) in legacy:
            continue
        lines = golden.read_text(encoding="utf-8").splitlines()
        saved = saves(lines)
        assert [what for _, what in saved] == [f"{golden.stem}.fsm"], (
            f"{golden.parent.name}/{golden.name} saves {saved}"
        )
        assert starts(lines)[-1] < saved[0][0] < lines.index("CLOSE_FLIGHTSTREAM"), (
            f"{golden.parent.name}/{golden.name}: the save is not the last state"
        )
        checked += 1
    assert checked >= TIER3_WORKFLOW_GOLDENS, (
        f"{checked} tier-3 workflow goldens were checked and {TIER3_WORKFLOW_GOLDENS} "
        "were measured; a golden was lost or a row became LEGACY"
    )


# ------------------------------------------------------------- the artifact --


def test_g11_a_pproc_cannot_switch_the_saved_simulation_off(tmp_path):
    """Refused through the file, as ``loads = false`` is; another kind stays selectable."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    pproc = workspace.inputs_dir / "pproc"
    (pproc / "p020.toml").write_text("[exports]\nsimulation = false\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="saved simulation cannot be deselected"):
        workspace.resolve_pproc("p020")
    # The control: the refusal is of this one kind, not of the table.
    (pproc / "p021.toml").write_text("[exports]\ntecplot = false\n", encoding="utf-8")
    outputs = workspace.resolve_pproc("p021").outputs(unsteady=True)
    assert "{name}.fsm" in outputs and "{name}.dat" not in outputs, outputs


# ---------------------------------------------------------------- the record --


@pytest.mark.parametrize(
    ("workflow", "cell", "values", "points"),
    [
        ("steady", "", "-2.0,0.0", 2),
        ("unsteady", "DELTA_TIME: 0.001 / TIME_ITERATIONS: 20 / LAST_ITERS_AVG: 20", "0.0", 1),
    ],
    ids=["steady", "unsteady"],
)
def test_g11_the_saved_simulation_is_collected_and_hashed(tmp_path, workflow, cell, values, points):
    """The .fsm lands in its point's folder and the record hashes the file on disk."""
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values=values,
        workflow=workflow,
        cell=cell,
    )
    records = run_matrix(
        matrix,
        workspace,
        name="saved",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert records, "the row ran no point"
    saved = []
    for record in records:
        assert record.status is RunStatus.CONVERGED, record.error
        for name in record.outputs:
            if not str(name).endswith(".fsm"):
                continue
            assert re.fullmatch(r"datapoints/DP-(?P<tag>[^/]+)/P3207-(?P=tag)\.fsm", name), name
            on_disk = workspace.sim_dir("3207") / name
            assert record.outputs_sha256[name] == file_sha256(on_disk), name
            saved.append(name)
    assert len(saved) == points, f"{points} points and the records name {saved}"


def test_g11_a_point_whose_saved_simulation_is_missing_is_recorded_incomplete(tmp_path):
    """D07: a solver that writes every export but the .fsm leaves an incomplete point."""
    saves_nothing = WRITES_EVERY_EXPORT.replace(
        "verbs = {kind[2] for kind in EXPORT_KINDS}; ",
        "verbs = {kind[2] for kind in EXPORT_KINDS} - {'SAVEAS'}; ",
    )
    assert saves_nothing != WRITES_EVERY_EXPORT, "the stub no longer reads as expected"
    workspace, matrix = _matrix(tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="0.0")
    with pytest.raises(CampaignErrors, match="FAILED_INCOMPLETE_OUTPUT"):
        run_matrix(
            matrix,
            workspace,
            name="unsaved",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=CountingStub(saves_nothing),
        )
    (record,) = workspace.read_manifest()
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, (record.status, record.error)
    assert ".fsm" in str(record.error), record.error


# ------------------------------------------------------------------ the plan --


def test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan(tmp_path):
    """Both LEGACY rows declare a loads table only; the plan says so and blocks nothing."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    said = rf"POL 8001, 8002: LEGACY row\(s\) that {UNSAVED}"
    with pytest.warns(PyflightstreamWarning, match=said):
        plan = plan_matrix(
            REGISTRY_FIXTURE,
            workspace,
            name="matrix",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry={"steady": matrix_recipe},
            write_plan=False,
        )
    assert [point.status for point in plan.points] == [PlanStatus.READY] * 4


def test_g11_a_legacy_row_declaring_its_fsm_and_a_workflow_row_are_not_warned(tmp_path):
    """The controls: a LEGACY row that declares its .fsm, and a row naming a run type."""
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    declared = text.replace(
        "OUTPUTS: loads_{point}.txt", "OUTPUTS: loads_{point}.txt, sim_{point}.fsm"
    )
    assert declared.count("sim_{point}.fsm") == 2, "the fixture no longer reads as expected"
    legacy = tmp_path / "legacy" / "declared.fs"
    legacy.parent.mkdir()
    legacy.write_text(declared, encoding="utf-8")
    library = make_library(tmp_path / "legacy", register_build=("26.120", "C:/fs/FS.exe"))
    workspace, steady = _matrix(
        tmp_path / "workflow", condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="0.0"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        first = plan_matrix(
            legacy,
            library,
            name="matrix",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry={"steady": matrix_recipe},
            write_plan=False,
        )
        second = plan_matrix(
            steady,
            workspace,
            name="named",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
    assert [point.status for point in first.points] == [PlanStatus.READY] * 4
    assert [point.status for point in second.points] == [PlanStatus.READY]
    warned = [str(warning.message) for warning in caught if UNSAVED in str(warning.message)]
    assert warned == [], warned


# ------------------------------------------------------------------ the page --


def test_g11_the_workflows_page_states_the_guarantee_and_names_its_tests():
    """The page states the path and the refusal, and cites tests that are on disk."""
    text = " ".join(
        (REPO / "docs" / "workspace-and-workflows.md").read_text(encoding="utf-8").split()
    )
    assert "datapoints/DP-<point>/P<POL>-<point>.fsm" in text
    assert "`[exports] simulation = false` is refused" in text
    assert "`pyfs-matrix plan` warns naming every `LEGACY` row" in text
    for name in (
        "test_g11_every_workflow_script_saves_its_final_simulation",
        "test_g11_the_saved_simulation_is_collected_and_hashed",
    ):
        assert f"`{name}`" in text, name
        assert name in globals(), f"the page cites {name}, which is not in this module"
