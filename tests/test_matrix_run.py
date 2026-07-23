"""Tier 1: the matrix as a first-class run interface (v0.3 decision 3).

resolve_matrix binds the REF/SET/ENTRY/FS_BUILD columns to a synthetic
workspace input library in tmp_path; plan_matrix pre-flights without
executing; run_matrix executes through a StubSolver that mimics the
solver, so the whole path matrix, library, canonical campaign form,
pre-flight, executor, and manifest is exercised without FlightStream.
"""

import sys
from pathlib import Path

import pytest

from pyflightstream.cases.matrix import (
    MatrixError,
    plan_matrix,
    resolve_matrix,
    run_matrix,
)
from pyflightstream.run import Assessment, LocalExecutor, PlanStatus
from pyflightstream.script import helpers
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    RunStatus,
    WorkspaceError,
)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "matrix.fs"
REGISTRY_FIXTURE = FIXTURES / "matrix_registry.fs"
# Codes map to registry names; the callables land in recipe_registry.
RECIPES = {"003": "steady", "004": "steady"}

HEADER = (
    "POL | AIRCRAFT | DESCRIPTION | RE | MACH | SWEEP_TYPE | SWEEP_VALUES | REF | SET "
    "| ENTRY | FS_SCRIPT | FS_BUILD | HIDDEN | RUN | VAR_NAMES_VALUES"
)


class StubSolver(LocalExecutor):
    def __init__(self, code: str):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.code = code

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", self.code]


WRITES_LOADS = "import pathlib; pathlib.Path('loads.txt').write_text('LOADS')"


def matrix_recipe(case, script):
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        aoa=case.point.get("alpha", 0.0),
        velocity=30.0,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads.txt")
    script.emit("CLOSE_FLIGHTSTREAM")


def converged(case, execution, sim_dir):
    return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)


def make_library(tmp_path, *, register_build=None):
    """Build a synthetic workspace input library covering the fixtures."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.inputs_dir
    reference = "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n"
    (inputs / "references" / "003.toml").write_text(reference, encoding="utf-8")
    (inputs / "references" / "004.toml").write_text(
        "area_m2 = 12.0\nchord_m = 1.5\nspan_m = 9.0\n", encoding="utf-8"
    )
    (inputs / "setups" / "002.toml").write_text(
        "iterations = 800\nconvergence = 1e-6\n", encoding="utf-8"
    )
    (inputs / "setups" / "003.toml").write_text(
        "iterations = 400\nwake_layers = 4\n", encoding="utf-8"
    )
    (inputs / "groups" / "001.toml").write_text(
        'wing = ["wing_left", "wing_right"]\nbody = [1]\n', encoding="utf-8"
    )
    if register_build is not None:
        build_id, exe_path = register_build
        with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
            handle.write(f'"{build_id}" = "{exe_path}"\n')
    return workspace


def write_matrix(path, rows):
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


# --- resolution: hits ------------------------------------------------------


def test_resolve_matrix_applies_reference_and_setup_to_the_cases(tmp_path):
    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.12",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    campaign = resolved.campaign
    assert campaign.fs_exe == str(Path("C:/fs/FlightStream.exe"))
    by_sim = {sim.sim_id: sim for sim in campaign.sims}
    # POL 9001: REF 003 and SET 003.
    assert by_sim["9001"].reference.area == 10.0
    assert by_sim["9001"].reference.length == 1.2
    assert by_sim["9001"].solver.iterations == 400
    # POL 9002: SET 002 maps both runtime keys.
    assert by_sim["9002"].solver.iterations == 800
    assert by_sim["9002"].solver.convergence == 1e-6
    # POL 9006: the distinct REF 004.
    assert by_sim["9006"].reference.area == 12.0
    # The historical codes survive in the variables (lossless).
    assert by_sim["9001"].variables["matrix_ref"] == "003"
    assert by_sim["9001"].variables["matrix_set"] == "003"
    # ENTRY groups come back verbatim for the script and post layers.
    assert resolved.groups["001"].groups == {"wing": ["wing_left", "wing_right"], "body": [1]}
    # The unmapped preset key stays verbatim in the artifact.
    assert resolved.setups["003"].settings["wake_layers"] == 4


def test_registry_build_resolves_the_executable(tmp_path):
    exe = "C:/fs26120/FlightStream.exe"
    workspace = make_library(tmp_path, register_build=("26.120", exe))
    resolved = resolve_matrix(
        REGISTRY_FIXTURE, workspace, name="matrix", fs_version="26.120", recipes=RECIPES
    )
    assert resolved.fs_exe == Path(exe)
    assert resolved.campaign.fs_exe == str(Path(exe))


# --- resolution: misses, all didactic --------------------------------------


@pytest.mark.filterwarnings("ignore:setup preset")
def test_missing_reference_names_the_row_the_id_and_the_folder(tmp_path):
    workspace = make_library(tmp_path)
    (workspace.inputs_dir / "references" / "004.toml").unlink()
    with pytest.raises(InputArtifactError, match=r"POL 9006.*inputs/references/004\.toml"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.12",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )


@pytest.mark.filterwarnings("ignore:setup preset")
def test_missing_setup_and_group_are_didactic_too(tmp_path):
    workspace = make_library(tmp_path)
    (workspace.inputs_dir / "setups" / "003.toml").unlink()
    with pytest.raises(InputArtifactError, match=r"SET column.*inputs/setups/003\.toml"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.12",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    workspace = make_library(tmp_path / "second")
    (workspace.inputs_dir / "groups" / "001.toml").unlink()
    with pytest.raises(InputArtifactError, match=r"ENTRY column.*inputs/groups/001\.toml"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.12",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )


def test_manual_build_requires_the_explicit_override(tmp_path):
    workspace = make_library(tmp_path)
    with pytest.raises(MatrixError, match="MANUAL.*fs_exe"):
        resolve_matrix(FIXTURE, workspace, name="matrix", fs_version="26.12", recipes=RECIPES)


def test_unregistered_build_points_at_the_registry_and_the_override(tmp_path):
    workspace = make_library(tmp_path)  # registry template only, no entries
    with pytest.raises(InputArtifactError, match=r"26\.120.*executables\.toml"):
        resolve_matrix(
            REGISTRY_FIXTURE, workspace, name="matrix", fs_version="26.120", recipes=RECIPES
        )


def test_mixed_builds_are_refused(tmp_path):
    workspace = make_library(tmp_path)
    row = (
        "700{n} | TestWing | MIXED | 3.10 | 0.0890 | AL | 0.0 | 003 | 002 | 001 | 003 "
        "| {build} |  0 | 1 | FSM_FILE:wing_clean"
    )
    matrix = write_matrix(
        tmp_path / "mixed.fs",
        [row.format(n=1, build="26.100"), row.format(n=2, build="26.120")],
    )
    with pytest.raises(MatrixError, match="2 FS_BUILD values"):
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.12", recipes=RECIPES)


@pytest.mark.filterwarnings("ignore:setup preset")
def test_bad_setup_value_is_refused_didactically(tmp_path):
    workspace = make_library(tmp_path)
    (workspace.inputs_dir / "setups" / "002.toml").write_text(
        'iterations = "many"\n', encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="does not fit the case solver settings"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.12",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )


# --- plan_matrix: pre-flight without execution ------------------------------


def test_plan_matrix_preflights_every_point_without_executing(tmp_path):
    exe = "C:/fs26120/FlightStream.exe"
    workspace = make_library(tmp_path, register_build=("26.120", exe))
    plan = plan_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="matrix",
        fs_version="26.120",
        recipes=RECIPES,
        recipe_registry={"steady": matrix_recipe},
    )
    assert [entry.status for entry in plan.points] == [PlanStatus.READY] * 4
    assert workspace.read_manifest() == []
    assert plan.plan_file == workspace.root / "plan.json"
    assert plan.plan_file.is_file()


# --- run_matrix: the one-call entry -----------------------------------------


def test_run_matrix_executes_and_records_every_point(tmp_path):
    exe = "C:/fs26120/FlightStream.exe"
    workspace = make_library(tmp_path, register_build=("26.120", exe))
    seen = []

    def spying_recipe(case, script):
        seen.append(case)
        matrix_recipe(case, script)

    records = run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="matrix",
        fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        executor=StubSolver(WRITES_LOADS),
        recipe_registry={"steady": spying_recipe},
    )
    assert [record.run_id for record in records] == [
        "matrix/sim_8001/a+00.0",
        "matrix/sim_8001/a+02.0",
        "matrix/sim_8002/b-03.0",
        "matrix/sim_8002/b+03.0",
    ]
    assert all(record.status is RunStatus.CONVERGED for record in records)
    assert len(workspace.read_manifest()) == 4
    # The recipes saw the resolved artifacts applied to their cases.
    assert seen[0].reference.area == 10.0
    assert seen[0].solver.iterations == 800


def test_run_matrix_honors_resume_and_refuses_a_silent_rerun(tmp_path):
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    keywords = dict(
        name="matrix",
        fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        recipe_registry={"steady": matrix_recipe},
    )
    run_matrix(REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), **keywords)
    resumed = run_matrix(
        REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), resume=True, **keywords
    )
    assert resumed == []
    assert len(workspace.read_manifest()) == 4
    with pytest.raises(WorkspaceError, match="resume=True"):
        run_matrix(REGISTRY_FIXTURE, workspace, executor=StubSolver(WRITES_LOADS), **keywords)


def test_run_matrix_refuses_a_blocked_preflight_before_any_execution(tmp_path):
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    with pytest.raises(MatrixError, match="nothing was\\s+executed"):
        run_matrix(
            REGISTRY_FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes={"003": "no.such.module:build"},
            assess=converged,
            executor=StubSolver(WRITES_LOADS),
        )
    assert workspace.read_manifest() == []


def test_matrix_without_active_rows_is_refused(tmp_path):
    workspace = make_library(tmp_path)
    matrix = write_matrix(
        tmp_path / "parked.fs",
        [
            "7001 | TestWing | PARKED | 3.10 | 0.0890 | AL | 0.0 | 003 | 002 | 001 "
            "| 003 | 26.120 |  0 | 0 | FSM_FILE:wing_clean"
        ],
    )
    with pytest.raises(MatrixError, match="no active rows"):
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES)
