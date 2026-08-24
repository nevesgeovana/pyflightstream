"""Tier 1: the matrix as a first-class run interface (v0.3 decision 3).

resolve_matrix binds the REF/SET/ENTRY/FS_BUILD columns to a synthetic
workspace input library in tmp_path; plan_matrix pre-flights without
executing; run_matrix executes through a StubSolver that mimics the
solver, so the whole path matrix, library, canonical campaign form,
pre-flight, executor, and manifest is exercised without FlightStream.

The three entry points live in TWO modules and this file imports them
from where they are, which is the point rather than an accident of
tidying: `resolve_matrix` binds the matrix to the workspace input
library and so belongs to `pyflightstream.workspace.matrix`, while
`plan_matrix` and `run_matrix` compose the campaign loop and so belong
to `pyflightstream.run.matrix` (OPS-2007.01). Only the reader and the
converter stayed in `pyflightstream.cases.matrix`.
"""

import sys
from pathlib import Path, PurePosixPath

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases.matrix import (
    DEFAULT_VERSION_OPTION,
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
    upgrade_matrix,
)
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import (
    FS_VERSION_FROM_DEFAULT,
    FS_VERSION_FROM_ROW,
    Assessment,
    LocalExecutor,
    PlanStatus,
)
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import helpers
from pyflightstream.versions import resolve
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    RunStatus,
    WorkspaceError,
)
from pyflightstream.workspace import matrix as matrix_module
from pyflightstream.workspace.matrix import GEOMETRY_VARIABLE, resolve_matrix

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
        return [sys.executable, "-c", self.code, str(script_path)]


# Writes whatever the SCRIPT asks it to export, rather than a fixed
# name, which is the only form that can exercise collection: a stub that
# always writes 'loads.txt' passes whatever the case declares. The
# sibling stub in test_run_campaign.py has always done it this way.
WRITES_LOADS = (
    "import pathlib, sys; "
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
    "[pathlib.Path(lines[i + 1]).write_text('LOADS') "
    "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']"
)


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
    # The managed protocol: a recipe exports case.outputs[i], never a
    # literal, so the loop collects exactly the files the case declared.
    # This emitted the literal "loads.txt" until 2026-08-03, which was
    # invisible because to_campaign never declared any outputs and the
    # collection step therefore had nothing to look for.
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


def converged(case, execution, sim_dir):
    return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)


#: Artifact bodies by the THREE-DIGIT TAIL of the code that names them.
#:
#: The fixtures spell their REF, SET and ENTRY codes with a kind letter
#: (``r003``, ``s002``, ``e001``) while a matrix written inline by a test
#: still spells them bare (``003``), and both are legitimate ids: the
#: input library resolves whatever the column says. Keying by the tail is
#: what lets one library cover both, so a fixture that changes its
#: spelling does not silently take the whole module red.
REFERENCE_BODIES = {
    "003": "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n",
    "004": "area_m2 = 12.0\nchord_m = 1.5\nspan_m = 9.0\n",
}
SETUP_BODIES = {
    "002": "iterations = 800\nconvergence = 1e-6\n",
    "003": "iterations = 400\nwake_layers = 4\n",
}
GROUP_BODIES = {"001": 'wing = ["wing_left", "wing_right"]\nbody = [1]\n'}


def fixture_codes(path=FIXTURE):
    """Return the REF, SET and ENTRY codes one fixture actually spells.

    Read from the file rather than written here, so the assertions below
    name the codes the matrix names and cannot drift from it.
    """
    rows = read_matrix(path, active_only=False)
    return {
        "ref": [row.ref_code for row in rows],
        "set": [row.set_code for row in rows],
        "entry": [row.entry_code for row in rows],
    }


def code_for(pol, kind, path=FIXTURE):
    """Return the `kind` code the row with this POL names."""
    for row in read_matrix(path, active_only=False):
        if row.pol == pol:
            return {"ref": row.ref_code, "set": row.set_code, "entry": row.entry_code}[kind]
    raise AssertionError(f"POL {pol} is not in {path}")


def make_library(tmp_path, *, register_build=None):
    """Build a synthetic workspace input library covering the fixtures."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.inputs_dir
    spelled = {"references": set(), "setups": set(), "groups": set()}
    for path in (FIXTURE, REGISTRY_FIXTURE):
        codes = fixture_codes(path)
        spelled["references"] |= set(codes["ref"])
        spelled["setups"] |= set(codes["set"])
        spelled["groups"] |= set(codes["entry"])
    # The body tables are keyed by the bare three-digit code, which is
    # what the codes were before 0.8.0. Every id the library can resolve
    # now DECLARES its kind with a leading letter (PFS-2009.01), so the
    # letter is added here rather than staging both spellings: a bare
    # file is one no id can reach, and leaving it on disk would teach a
    # later reader that the old spelling still resolves. Measured
    # 2026-08-19: it staged six such files, found by the currency guard
    # over this builder rather than by any test of the library itself.
    for tail in REFERENCE_BODIES:
        spelled["references"].add(f"r{tail}")
    for tail in SETUP_BODIES:
        spelled["setups"].add(f"s{tail}")
    for tail in GROUP_BODIES:
        spelled["groups"].add(f"e{tail}")
    for subdir, bodies in (
        ("references", REFERENCE_BODIES),
        ("setups", SETUP_BODIES),
        ("groups", GROUP_BODIES),
    ):
        for code in sorted(spelled[subdir]):
            body = bodies.get(code[-3:])
            if body is not None:
                (inputs / subdir / f"{code}.toml").write_text(body, encoding="utf-8")
    if register_build is not None:
        build_id, exe_path = register_build
        with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
            handle.write(f'"{build_id}" = "{exe_path}"\n')
    return workspace


def register(workspace, build_id, exe_path, version=None):
    """Append one entry to a workspace build registry, in either shape.

    With `version` left out the entry is the bare path string the
    registry has always taken; given one it is the TABLE shape added at
    PFS-2009.05, which is the only way a build declares the FlightStream
    version its scripts are emitted under.
    """
    if version is None:
        entry = f'"{build_id}" = "{exe_path}"\n'
    else:
        entry = f'"{build_id}" = {{ path = "{exe_path}", version = "{version}" }}\n'
    with open(workspace.inputs_dir / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write(entry)
    return workspace


def write_matrix(path, rows):
    """Write an inline matrix in the pre-v0.8.0 shape, then upgrade it.

    HEADER is the fifteen-column layout, which the reader now refuses
    with a didactic pointer at ``upgrade_matrix``. Going through that
    migration rather than hand-writing the WORKFLOW cell keeps these
    rows readable AND exercises the one path a user with an existing
    matrix takes.
    """
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    upgrade_matrix(path, in_place=True)
    return path


# --- resolution: hits ------------------------------------------------------


def test_resolve_matrix_applies_reference_and_setup_to_the_cases(tmp_path):
    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
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
    # The historical codes survive in the variables (lossless), whatever
    # the matrix spells them as.
    assert by_sim["9001"].variables["matrix_ref"] == code_for("9001", "ref")
    assert by_sim["9001"].variables["matrix_set"] == code_for("9001", "set")
    # ENTRY groups come back verbatim for the script and post layers.
    assert resolved.groups[code_for("9001", "entry")].groups == {
        "wing": ["wing_left", "wing_right"],
        "body": [1],
    }
    # The unmapped preset key stays verbatim in the artifact.
    assert resolved.setups[code_for("9001", "set")].settings["wake_layers"] == 4


# --- PFS-2027.02 and .04: the resolver, and where it must sit ------------


def test_the_flight_condition_resolves_against_the_rows_own_reference(tmp_path):
    """The end-to-end path, and the ORDERING it depends on.

    THIS TEST IS THE ORDERING GUARD, and it fails rather than asking.
    In `resolve_matrix` the reference is bound to a LOCAL at the top of
    the per-row loop and reaches the case only through the `model_copy`
    that closes it, so `case.reference` is still None while the loop body
    runs. A resolver moved above that binding would therefore see no
    length at all, and every Reynolds constraint in the matrix would be
    refused -- or, worse, silently resolved against nothing if the
    refusal were ever relaxed. Asserting the length that was USED is what
    detects the move: 1.2 is REF 003's chord, and no other value in this
    fixture is 1.2.
    """
    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    condition = resolved.conditions["9001"]
    assert condition.reference_length_m == 1.2, (
        "the resolver did not see REF 003's chord, which is what happens "
        "when it runs before the reference is bound"
    )
    assert condition.stated == {"MACH": 0.1441, "REmi": 4.38}
    assert condition.density_source == "solved-from-reynolds"
    assert condition.reynolds == pytest.approx(4.38e6)


def test_the_resolved_state_reaches_the_case_fields_it_has(tmp_path):
    """Velocity, Mach and Reynolds land on the case; the rest rides along."""
    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    case = {sim.sim_id: sim for sim in resolved.campaign.sims}["9001"]
    condition = resolved.conditions["9001"]
    assert case.mach == pytest.approx(condition.mach)
    assert case.velocity == pytest.approx(condition.velocity_m_per_s)
    assert case.reynolds == pytest.approx(condition.reynolds)
    # And the condition AS WRITTEN travels on the case too, which is what
    # lets a reader recompute the resolution rather than trust it.
    assert case.flight_condition == {"MACH": 0.1441, "REmi": 4.38}


def test_a_row_stating_no_condition_is_refused_by_the_reader(tmp_path):
    """The mandatoriness RE and MACH had, inherited by what replaced them.

    Written in the CURRENT layout directly rather than through
    `write_matrix`, which goes via the legacy upgrade: the old format
    had RE and MACH as mandatory numeric columns, so a row with no flow
    condition at all is a thing only the new layout can even express.

    IT IS REFUSED, and that is the point of the test. An independent
    review found this accepted silently, which would have been a
    loosening smuggled in by a format change: the case would reach a
    builder with no velocity, no density and no Reynolds number while
    looking exactly like a working row.
    """
    from pyflightstream.cases.matrix import _COLUMNS

    workspace = make_library(tmp_path)
    cells = {name: "" for name in _COLUMNS}
    cells.update(
        {
            "POL": "9101",
            "AIRCRAFT": "TestWing",
            "DESCRIPTION": "NO_CONDITION",
            "FLIGHT_CONDITION": "",
            "SWEEP_TYPE": "AL",
            "SWEEP_VALUES": "0.0",
            "REF": code_for("9001", "ref"),
            "SET": code_for("9001", "set"),
            "ENTRY": code_for("9001", "entry"),
            "FS_SCRIPT": "003",
            "FS_BUILD": "MANUAL",
            "HIDDEN": "0",
            "RUN": "1",
            "WORKFLOW": "LEGACY",
            "VAR_NAMES_VALUES": "OUTPUTS: loads_{point}.txt",
        }
    )
    matrix = tmp_path / "silent.fs"
    header_line = " | ".join(_COLUMNS)
    data_line = " | ".join(cells[name] for name in _COLUMNS)
    matrix.write_text(header_line + "\n" + data_line + "\n", encoding="utf-8")
    with pytest.raises(MatrixError) as caught:
        resolve_matrix(
            matrix,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    message = str(caught.value)
    assert "9101" in message
    assert "FLIGHT_CONDITION" in message
    # It names the columns it replaced, so a user migrating knows why a
    # cell they never had to fill in is suddenly required.
    assert "RE" in message and "MACH" in message
    # And it gives something to copy rather than only a rule.
    assert "MACH:0.20, REmi:5.5" in message


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
    code = code_for("9006", "ref")
    (workspace.inputs_dir / "references" / f"{code}.toml").unlink()
    with pytest.raises(InputArtifactError, match=rf"POL 9006.*inputs/references/{code}\.toml"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )


@pytest.mark.filterwarnings("ignore:setup preset")
def test_missing_setup_and_group_are_didactic_too(tmp_path):
    workspace = make_library(tmp_path)
    setup_code = code_for("9001", "set")
    (workspace.inputs_dir / "setups" / f"{setup_code}.toml").unlink()
    with pytest.raises(InputArtifactError, match=rf"SET column.*inputs/setups/{setup_code}\.toml"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    workspace = make_library(tmp_path / "second")
    group_code = code_for("9001", "entry")
    (workspace.inputs_dir / "groups" / f"{group_code}.toml").unlink()
    entry_miss = rf"ENTRY column.*inputs/groups/{group_code}\.toml"
    with pytest.raises(InputArtifactError, match=entry_miss):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )


def test_manual_build_requires_the_explicit_override(tmp_path):
    workspace = make_library(tmp_path)
    with pytest.raises(MatrixError, match="MANUAL.*fs_exe"):
        resolve_matrix(FIXTURE, workspace, name="matrix", fs_version="26.120", recipes=RECIPES)


def test_unregistered_build_points_at_the_registry_and_the_override(tmp_path):
    workspace = make_library(tmp_path)  # registry template only, no entries
    with pytest.raises(InputArtifactError, match=r"26\.120.*executables\.toml"):
        resolve_matrix(
            REGISTRY_FIXTURE, workspace, name="matrix", fs_version="26.120", recipes=RECIPES
        )


def test_a_build_no_row_can_reach_is_still_refused_by_the_registry(tmp_path):
    """Two builds are no longer refused, and an unregistered one still is.

    The multi-build refusal is gone (PFS-2009.05), so this matrix reaches
    the registry with two ids instead of being stopped above it. The
    remedy the message offers is the one that applies to a cell.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    row = (
        "700{n} | TestWing | MIXED | 3.10 | 0.0890 | AL | 0.0 | 003 | 002 | 001 | 003 "
        "| {build} |  0 | 1 | FSM_FILE:wing_clean"
    )
    matrix = write_matrix(
        tmp_path / "mixed.fs",
        [row.format(n=1, build="26.100"), row.format(n=2, build="26.120")],
    )
    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES)

    message = str(caught.value)
    assert "FS_BUILD column" in message and "'26.100'" in message, message
    assert "campaign default" not in message, (
        f"a build id that a CELL names was reported as the campaign default: {message}"
    )


def test_two_builds_resolve_to_two_installations(tmp_path):
    """The item's headline: one matrix, two rows, two solver builds.

    Refused outright until PFS-2009.05, on the ground that a campaign
    binds to exactly one installation. It no longer does: a case names
    its build and the campaign loop takes a builds mapping, so the
    record can say which of the two a point ran on instead of naming the
    campaign's for both.
    """
    workspace = make_library(tmp_path)
    register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
    register(workspace, "26.123", "C:/fs26123/FlightStream.exe", version="26.123")
    row = (
        "700{n} | TestWing | MIXED | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 | 003 "
        "| {build} |  0 | 1 | FSM_FILE:wing_clean / OUTPUTS: loads_{{point}}.txt"
    )
    matrix = write_matrix(
        tmp_path / "two_builds.fs",
        [row.format(n=1, build="26.120"), row.format(n=2, build="26.123")],
    )

    resolved = resolve_matrix(
        matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES
    )

    assert resolved.row_builds == ("26.120", "26.123")
    assert {build: entry.fs_exe for build, entry in resolved.builds.items()} == {
        "26.120": Path("C:/fs26120/FlightStream.exe"),
        "26.123": Path("C:/fs26123/FlightStream.exe"),
    }
    # The bare string declares no version and the table declares one.
    assert resolved.builds["26.120"].fs_version is None
    assert resolved.builds["26.123"].fs_version == "26.123"
    # Every active row names a build, so no row runs on the campaign's
    # own installation and it is the first row's rather than the
    # default's; either way it is an executable this matrix really uses.
    assert resolved.fs_exe == Path("C:/fs26120/FlightStream.exe")


@pytest.mark.filterwarnings("ignore:setup preset")
def test_bad_setup_value_is_refused_didactically(tmp_path):
    workspace = make_library(tmp_path)
    broken = f"{code_for('9002', 'set')}.toml"
    (workspace.inputs_dir / "setups" / broken).write_text('iterations = "many"\n', encoding="utf-8")
    with pytest.raises(InputArtifactError, match="does not fit the case solver settings"):
        resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
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
        default_fs_version="26.120",
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
        default_fs_version="26.120",
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
        default_fs_version="26.120",
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
            default_fs_version="26.120",
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


# --- the matrix path never collected anything ------------------------------
#
# Found by running the author's own research campaign on 2026-08-03, not by
# a review: `to_campaign` never set `outputs`, so every matrix-driven case
# carried the empty default and the collection step had nothing to look for.
# A thirty-minute unsteady run completed, the solver wrote all eight files
# into the run folder, and the point was recorded FAILED_INCOMPLETE_OUTPUT
# with "collected: nothing".
#
# It stayed invisible because the end-to-end test above passed a stub
# assessor that returns CONVERGED without reading a file, the fixture recipe
# exported a literal instead of `case.outputs[0]`, and the stub solver wrote
# a fixed name. All three are fixed above; these pin the behaviour.


def test_a_matrix_row_declaring_no_outputs_is_refused_before_the_solver():
    """A refusal costs nothing; the silent empty list cost half an hour."""
    import re
    import tempfile

    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    stripped = re.sub(r"\s*/\s*OUTPUTS:[^|\n]*", "", text)
    assert stripped != text, "the fixture no longer declares OUTPUTS to strip"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "no_outputs.fs"
        path.write_text(stripped, encoding="utf-8")
        with pytest.raises(MatrixError, match="declares no outputs"):
            to_campaign(path, name="m", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES)


def test_a_legacy_matrix_still_converts_and_says_what_to_add():
    """FR-10 and FR-11, which the refusal above closed for a whole day.

    `_declared_outputs` raised from `to_campaign`, and `convert_matrix`
    calls `to_campaign`, so `pyfs-matrix convert` refused every matrix
    written before the OUTPUTS variable existed. That is every matrix
    the author already owns, and conversion is the ONE path off the
    legacy format: FR-10 scopes "forever" to the external format and
    FR-11 calls conversion lossless, and neither moved.

    Conversion spends no solver time, so it carries what the row
    declares, including nothing, and warns naming the rows. The
    refusal belongs on the paths that are about to start a solver, and
    the test above still pins it there.
    """
    import re
    import tempfile

    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    stripped = re.sub(r"\s*/\s*OUTPUTS:[^|\n]*", "", text)
    assert stripped != text, "the fixture no longer declares OUTPUTS to strip"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "legacy.fs"
        path.write_text(stripped, encoding="utf-8")
        with pytest.warns(UserWarning, match="declare no outputs"):
            rendered = convert_matrix(
                path, name="m", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
            )
    assert "[[sim]]" in rendered, "the legacy matrix did not convert at all"
    assert "outputs = " not in rendered, (
        "the conversion invented outputs the matrix never declared, which is the "
        "opposite failure: FR-11 calls it lossless in both directions"
    )


def test_a_declared_row_reaches_the_case_and_survives_conversion():
    """The control, and the FR-11 half: what the row declares must arrive
    on the case AND survive the campaign.toml round trip."""
    campaign = to_campaign(
        REGISTRY_FIXTURE, name="m", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    assert campaign.sims[0].outputs == ["loads_{point}.txt"]
    text = convert_matrix(
        REGISTRY_FIXTURE, name="m", fs_version="26.120", fs_exe="C:/fs.exe", recipes=RECIPES
    )
    assert "outputs = " in text


def test_the_end_to_end_run_actually_collects_the_declared_file(tmp_path):
    """The gap that hid all of this: the run above asserted CONVERGED from a
    stub assessor that never opened a file. This asserts the COLLECTION."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    records = run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="collect",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        executor=StubSolver(WRITES_LOADS),
        recipe_registry={"steady": matrix_recipe},
    )
    for record in records:
        assert record.outputs, f"{record.run_id} collected nothing"
        assert record.outputs_sha256, f"{record.run_id} recorded no output hashes"
        collected = workspace.sim_dir(record.sim_id) / record.outputs[0]
        assert collected.is_file(), collected


def test_the_row_decides_the_window_when_the_caller_does_not(tmp_path, monkeypatch):
    """The HIDDEN column existed, the row said 0 (show the window), and
    run_matrix used its own parameter, so the run went headless against
    the matrix's explicit instruction.

    This test USED to pass an explicit executor and then assert the
    signature default, which meant the derivation it is named for never
    executed: the QA pass measured lines 840-843 of matrix.py as
    uncovered and showed that replacing the whole derivation with
    `hidden = True` kept it green. The `Recording` class and the `seen`
    dict it carried were never read, which is worse than absent, because
    the file reads as though the run were observed.

    It now leaves `executor` unset, which is the only path that reaches
    the derivation, and records what LocalExecutor was actually
    constructed with.
    """
    import pyflightstream.run.matrix as matrix_module

    rows = read_matrix(REGISTRY_FIXTURE)
    assert not all(row.hidden for row in rows), (
        "the fixture must carry a row asking for a visible window, or this "
        "test cannot tell the row from the default"
    )

    seen: dict[str, object] = {}

    class Recording(StubSolver):
        def __init__(self, fs_exe, hidden=True, **kwargs):
            seen["hidden"] = hidden
            super().__init__(WRITES_LOADS)

    # `pyflightstream.run.matrix`, not `pyflightstream.run`: since the
    # hoist (OPS-2007.01) the entry point imports LocalExecutor at MODULE
    # level, so the name it resolves is the one bound in its own module
    # and patching the source package would silently miss. Patching the
    # wrong one is not a false pass here, because the real executor then
    # refuses the synthetic path and the test errors loudly.
    monkeypatch.setattr(matrix_module, "LocalExecutor", Recording)
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="window",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        recipe_registry={"steady": matrix_recipe},
    )
    assert seen.get("hidden") is False, (
        f"the matrix has a row asking for a visible window and the executor was "
        f"built with hidden={seen.get('hidden')!r}. The row decides when the "
        "caller does not, which is what the HIDDEN column is for"
    )

    import inspect

    assert inspect.signature(run_matrix).parameters["hidden"].default is None, (
        "hidden must default to None, meaning the row decides"
    )


def _recording_executor(monkeypatch, seen):
    """Patch the executor the matrix builds and record its hidden argument."""
    import pyflightstream.run.matrix as matrix_module

    class Recording(StubSolver):
        def __init__(self, fs_exe, hidden=True, **kwargs):
            seen["hidden"] = hidden
            super().__init__(WRITES_LOADS)

    # `pyflightstream.run.matrix`, not `pyflightstream.run`: since the
    # hoist (OPS-2007.01) the entry point imports LocalExecutor at MODULE
    # level, so the name it resolves is the one bound in its own module.
    monkeypatch.setattr(matrix_module, "LocalExecutor", Recording)


def test_a_matrix_whose_rows_all_ask_for_hidden_runs_hidden(tmp_path, monkeypatch):
    """The other direction of the derivation, which the repair left open.

    Its sibling above asserts ``hidden is False`` for a matrix carrying a
    visible row, and that assertion alone is satisfied by ``hidden =
    False`` written unconditionally: a mutation to exactly that was
    measured green across the whole suite. A derivation needs both of its
    answers pinned or it is not pinned at all.
    """
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    all_hidden = text.replace("|    0   |", "|    1   |")
    assert all_hidden != text, "the fixture no longer carries a row asking for a window"
    matrix = tmp_path / "all_hidden.fs"
    matrix.write_text(all_hidden, encoding="utf-8")
    rows = read_matrix(matrix)
    assert all(row.hidden for row in rows), "this fixture must ask for hidden everywhere"

    seen: dict[str, object] = {}
    _recording_executor(monkeypatch, seen)
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    run_matrix(
        matrix,
        workspace,
        name="allhidden",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        recipe_registry={"steady": matrix_recipe},
    )
    assert seen.get("hidden") is True, (
        f"every row asks for a hidden window and the executor was built with "
        f"hidden={seen.get('hidden')!r}"
    )


def test_one_visible_row_makes_the_campaign_visible_wherever_it_sits(tmp_path, monkeypatch):
    """The reduction is over every row, not over the first one.

    Third case because two were not enough. The fixture's visible row is
    its FIRST, so ``all(row.hidden for row in rows)`` and
    ``rows[0].hidden`` give the same answer for it and the same answer
    for the all-hidden variant: that mutant survives both of the tests
    above. Swapping the two columns separates them, and this is the only
    assertion that does.
    """
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    swapped = text.replace("|    0   |", "|    @   |").replace("|    1   |", "|    0   |")
    swapped = swapped.replace("|    @   |", "|    1   |")
    assert swapped != text, "the fixture no longer carries one of each HIDDEN value"
    matrix = tmp_path / "visible_second.fs"
    matrix.write_text(swapped, encoding="utf-8")
    rows = read_matrix(matrix)
    assert rows[0].hidden and not all(row.hidden for row in rows), (
        "this fixture exists to make the first row disagree with the reduction"
    )

    seen: dict[str, object] = {}
    _recording_executor(monkeypatch, seen)
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    run_matrix(
        matrix,
        workspace,
        name="visiblesecond",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        recipe_registry={"steady": matrix_recipe},
    )
    assert seen.get("hidden") is False, (
        "a later row asks for a visible window, so the campaign is visible; the "
        f"executor was built with hidden={seen.get('hidden')!r}"
    )


def test_an_explicit_hidden_argument_overrules_the_column(tmp_path, monkeypatch):
    """The caller-wins half, which had no test at all.

    Both the changelog and the derivation's own comment promise that an
    explicit True or False beats the column. Nothing exercised it: no
    ``run_matrix`` call in the suite passed ``hidden=``, so mutating the
    ``if hidden is None:`` guard to ``if True:`` left the suite green and
    silently took the promise away.
    """
    seen: dict[str, object] = {}
    _recording_executor(monkeypatch, seen)
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    # The fixture carries a row asking for a visible window, so the
    # column would derive False. The caller says True.
    run_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="callerwins",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        recipe_registry={"steady": matrix_recipe},
        hidden=True,
    )
    assert seen.get("hidden") is True, (
        "an explicit hidden=True must beat a column that derives False; the "
        f"executor was built with hidden={seen.get('hidden')!r}"
    )


def test_an_explicit_hidden_false_also_overrules_the_column(tmp_path, monkeypatch):
    """The other direction of caller-wins, on a matrix that derives True.

    Its sibling above passes True over a column deriving False, so a
    mutation hardcoding True satisfies it. The promise is symmetric and
    so is the pinning: this passes False over a matrix whose every row
    asks to be hidden.
    """
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    all_hidden = text.replace("|    0   |", "|    1   |")
    assert all_hidden != text, "the fixture no longer carries a row asking for a window"
    matrix = tmp_path / "all_hidden_override.fs"
    matrix.write_text(all_hidden, encoding="utf-8")

    seen: dict[str, object] = {}
    _recording_executor(monkeypatch, seen)
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    run_matrix(
        matrix,
        workspace,
        name="callerwinsfalse",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        recipe_registry={"steady": matrix_recipe},
        hidden=False,
    )
    assert seen.get("hidden") is False, (
        "an explicit hidden=False must beat a column that derives True; the "
        f"executor was built with hidden={seen.get('hidden')!r}"
    )


def test_the_override_says_which_rows_it_overrules(tmp_path):
    """The explicit fs_exe override is the only way to run MANUAL, so it has
    to win. It used to win SILENTLY over a row naming a real build: measured
    on the author's campaign, a row saying FS_BUILD 26.121 ran on the 26.120
    executable and was recorded as having requested 26.120, with nothing
    said. Overruling an explicit request is a decision the caller is
    entitled to hear."""
    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.strip() and not line.startswith("-")]
    assert len(rows) >= 3, "the fixture needs a header and two distinct rows"
    header, keep, second = rows[0], rows[1], rows[2]
    manual = second.replace("| 26.120   |", "| MANUAL   |", 1)
    assert manual != second, "the fixture's second row no longer names build 26.120"
    mixed = tmp_path / "mixed.fs"
    mixed.write_text("\n".join([header, keep, manual]) + "\n", encoding="utf-8")

    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    with pytest.warns(UserWarning, match="overruling the FS_BUILD"):
        resolve_matrix(
            mixed,
            workspace,
            name="m",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/elsewhere/FlightStream.exe",
        )


def test_no_warning_when_the_override_overrules_nothing(tmp_path):
    """The control: with every row MANUAL the override overrules no explicit
    request, and a warning there would train the reader to ignore it."""
    import warnings as _warnings

    text = REGISTRY_FIXTURE.read_text(encoding="utf-8")
    all_manual = text.replace("| 26.120   |", "| MANUAL   |")
    path = tmp_path / "all_manual.fs"
    path.write_text(all_manual, encoding="utf-8")

    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    with _warnings.catch_warnings():
        _warnings.simplefilter("error", UserWarning)
        resolve_matrix(
            path,
            workspace,
            name="m",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/elsewhere/FlightStream.exe",
        )


# --- the version argument is a DEFAULT, and its name says so ---------------


def test_the_matrix_entry_points_call_the_version_argument_a_default():
    """PFS-2009.08.01: the rename is the load-bearing half.

    A parameter called ``fs_version`` sitting beside a per-row FS_BUILD
    column reads as an OVERRIDE of that column, and nobody reads a
    docstring to check a name they think they understand. The argument
    answers only for rows that name no build, so it is a default.
    """
    import inspect

    for entry in (plan_matrix, run_matrix):
        parameters = inspect.signature(entry).parameters
        assert "default_fs_version" in parameters, (
            f"{entry.__name__}() still calls the argument fs_version alone, which "
            "reads as an override of the FS_BUILD column rather than as the "
            "fallback for rows that name no build"
        )


def test_the_default_version_reaches_the_plan_under_its_new_name(tmp_path):
    """The behaviour half: the new keyword is not just accepted, it is used."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    plan = plan_matrix(
        REGISTRY_FIXTURE,
        workspace,
        name="matrix",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry={"steady": matrix_recipe},
        write_plan=False,
    )
    assert plan.fs_version == "26.120"
    assert [point.status for point in plan.points] == [PlanStatus.READY] * 4


def test_the_former_spelling_still_works_and_says_it_is_the_former_one(tmp_path):
    """Callers of these two entry points exist outside this package.

    The command line keeps ``--fs-version`` by the author's decision of
    2026-08-03, which unified the flag across every CLI here, so only the
    PYTHON keyword moves and the old one keeps working until a release
    removes it.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    with pytest.warns(DeprecationWarning, match="default_fs_version"):
        plan = plan_matrix(
            REGISTRY_FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            recipe_registry={"steady": matrix_recipe},
            write_plan=False,
        )
    assert plan.fs_version == "26.120"


def test_naming_the_version_neither_way_is_refused_didactically(tmp_path):
    """Omitting it used to be a bare TypeError from the call machinery."""
    workspace = make_library(tmp_path)
    with pytest.raises(MatrixError, match="default_fs_version"):
        plan_matrix(REGISTRY_FIXTURE, workspace, name="matrix", recipes=RECIPES)


def test_the_two_spellings_agreeing_is_accepted_with_the_notice(tmp_path):
    """The arm between the other two: both names, one value.

    Left untested it would be counted as covered by the disagreement
    case, which takes the other branch and never reaches it.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    with pytest.warns(DeprecationWarning, match="default_fs_version"):
        plan = plan_matrix(
            REGISTRY_FIXTURE,
            workspace,
            name="matrix",
            default_fs_version="26.120",
            fs_version="26.120",
            recipes=RECIPES,
            recipe_registry={"steady": matrix_recipe},
            write_plan=False,
        )
    assert plan.fs_version == "26.120"


def test_the_two_spellings_disagreeing_is_refused_rather_than_resolved(tmp_path):
    """Two names for one argument, given two values, is not a thing to guess at."""
    workspace = make_library(tmp_path)
    with pytest.raises(MatrixError, match="two names for one argument"):
        plan_matrix(
            REGISTRY_FIXTURE,
            workspace,
            name="matrix",
            default_fs_version="26.120",
            fs_version="26.121",
            recipes=RECIPES,
        )


# --- PFS-2009.08.03: refused above the binding, with and without fs_exe -----
#
# `_resolve_build` returns Path(override) BEFORE it ever builds the set of
# FS_BUILD values, so a check placed at that set is skipped exactly when
# the explicit override is passed. The acceptance says "with and without
# fs_exe", which is why this refusal sits above the binding step instead.

PFS20090803_ROWS = (
    "9001 | TestWing | ROW_ONE | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 |          | 0 | 1 | OUTPUTS: loads_{point}.txt",
    "9002 | TestWing | ROW_TWO | 3.10 | 0.0890 | AL | 2.0 | r003 | s002 | e001 "
    "| 003 |   26.120 | 0 | 1 | OUTPUTS: loads_{point}.txt",
    "9003 | TestWing | ROW_OFF | 3.10 | 0.0890 | AL | 4.0 | r003 | s002 | e001 "
    "| 003 |          | 0 | 0 | OUTPUTS: loads_{point}.txt",
)


def _pfs20090803_matrix(tmp_path):
    """One silent active row, one active row naming a build, one row off."""
    path = write_matrix(tmp_path / "pfs20090803_run.fs", list(PFS20090803_ROWS))
    everything = read_matrix(path, active_only=False)
    assert [row.row_number for row in everything] == [1, 2, 3]
    assert [row.fs_build for row in everything] == ["", "26.120", ""], (
        "the fixture must hold exactly one silent ACTIVE row, one active row "
        "naming a build, and one silent row that is switched off"
    )
    assert [row.run for row in everything] == [1, 1, 0]
    return path


def _never_bound(monkeypatch):
    """Make the binding step explode, so reaching it is a visible failure."""
    import pyflightstream.run.matrix as run_matrix_module

    def exploding(*args, **kwargs):
        raise AssertionError(
            "resolve_matrix was reached: the matrix was bound, a Campaign was "
            "built and the executable was resolved before the refusal fired"
        )

    monkeypatch.setattr(run_matrix_module, "resolve_matrix", exploding)


@pytest.mark.parametrize("fs_exe", [None, "C:/fs/FlightStream.exe"])
@pytest.mark.parametrize("entry", ["plan", "run"])
def test_a_silent_row_with_a_blank_default_is_refused_before_anything_binds(
    tmp_path, monkeypatch, entry, fs_exe
):
    path = _pfs20090803_matrix(tmp_path)
    workspace = make_library(tmp_path)
    _never_bound(monkeypatch)
    call = plan_matrix if entry == "plan" else run_matrix
    extra = {} if entry == "plan" else {"assess": converged}

    with pytest.raises(MatrixError) as caught:
        call(
            path,
            workspace,
            name="camp",
            recipes=RECIPES,
            default_fs_version="   ",
            fs_exe=fs_exe,
            **extra,
        )
    message = str(caught.value)
    assert "row 1 (POL 9001)" in message, (
        f"the silent active row must be named by number and POL: {message}"
    )
    assert "9002" not in message, f"the row that names a build is not silent: {message}"
    assert "9003" not in message, (
        f"an inactive row runs nothing, so its empty cell asks nothing: {message}"
    )
    assert DEFAULT_VERSION_OPTION in message
    assert "not registered" not in message
    # Nothing was executed and nothing was planned.
    assert workspace.read_manifest() == []
    assert not (workspace.root / "plan.json").exists()


@pytest.mark.parametrize("entry", ["plan", "run"])
def test_a_blank_default_is_refused_by_the_option_and_never_by_the_registry(
    tmp_path, monkeypatch, entry
):
    """No row is silent, so the default answers for nothing; still refused."""
    path = write_matrix(
        tmp_path / "pfs20090803_named.fs",
        [
            "9001 | TestWing | ROW_ONE | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
            "| 003 |   26.120 | 0 | 1 | OUTPUTS: loads_{point}.txt",
        ],
    )
    assert all(row.fs_build for row in read_matrix(path)), (
        "this arm needs a matrix in which no active row is silent"
    )
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FlightStream.exe"))
    _never_bound(monkeypatch)
    call = plan_matrix if entry == "plan" else run_matrix
    extra = {} if entry == "plan" else {"assess": converged}

    with pytest.raises(MatrixError) as caught:
        call(path, workspace, name="camp", recipes=RECIPES, default_fs_version="", **extra)
    message = str(caught.value)
    assert DEFAULT_VERSION_OPTION in message
    assert "Known versions" not in message and "not registered" not in message, (
        f"the version registry answered a question about a missing option: {message}"
    )
    assert "POL" not in message, f"no row is silent, so none may be named: {message}"


def test_a_given_default_still_binds_a_matrix_with_a_silent_row(tmp_path):
    """The control, and it must run the real binding rather than a stub."""
    path = _pfs20090803_matrix(tmp_path)
    workspace = make_library(tmp_path)
    plan = plan_matrix(
        path,
        workspace,
        name="camp",
        recipes=RECIPES,
        default_fs_version="26.120",
        fs_exe="C:/fs/FlightStream.exe",
        recipe_registry={"steady": matrix_recipe},
        write_plan=False,
    )
    assert {entry.sim_id for entry in plan.points} == {"9001", "9002"}
    assert not plan.blocked, plan.summary()


# --- PFS-2009.08.02: the record says WHERE its build came from --------------
#
# A record has always named the installation twice, in `fs_exe` and in
# `fs_version_requested`, and could not say whether the point's own row
# chose it or whether it inherited the campaign default. The campaign
# layer learned to record that (`fs_version_source`) from
# `SimCase.fs_build`; the matrix converter never set that field, so every
# matrix-driven point was recorded as having inherited the default even
# when its FS_BUILD cell named the build outright.
#
# The two facts these tests hold apart:
#   * WHICH build ran -> fs_exe, fs_exe_sha256, fs_version_requested
#   * WHO CHOSE it    -> fs_version_source

SILENT_ROW = (
    "9101 | TestWing | SILENT_ROW | 3.10 | 0.0890 | AL | 0.0,2.0 | r003 | s002 | e001 "
    "| 003 |          | 1 | 1 | OUTPUTS: loads_{point}.txt"
)
NAMED_ROW = (
    "9102 | TestWing | NAMED_ROW | 3.10 | 0.0890 | BE | -3.0,3.0 | r003 | s002 | e001 "
    "| 003 |   26.120 | 1 | 1 | OUTPUTS: loads_{point}.txt"
)


def real_executable(tmp_path):
    """A file that really exists, so fs_exe_sha256 is a real digest.

    The other fixtures register a path that is not there, which is fine
    for selection but records ``fs_exe_sha256`` as None, and a
    reproduction test that cannot compare a digest is not testing
    reproduction.
    """
    exe = tmp_path / "fs26120" / "FlightStream.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"not really a solver, but a real file with a real digest")
    return exe


def run_for_records(path, workspace, **extra):
    """Run one matrix through the stub solver and return its records."""
    return run_matrix(
        path,
        workspace,
        name="prov",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        executor=StubSolver(WRITES_LOADS),
        recipe_registry={"steady": matrix_recipe},
        **extra,
    )


@pytest.mark.filterwarnings("ignore:none of the")
def test_a_row_naming_its_build_is_recorded_as_having_chosen_it(tmp_path):
    """The FS_BUILD cell named the installation, so the row chose it."""
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    records = run_for_records(REGISTRY_FIXTURE, workspace)

    assert records, "the run recorded nothing to judge"
    for record in records:
        assert record.fs_version_source == FS_VERSION_FROM_ROW, (
            f"{record.run_id} inherited the campaign default in the manifest, but its "
            "row's FS_BUILD cell names 26.120: the record cannot tell a build chosen "
            "FOR THE ROW from one it fell back to"
        )
        assert Path(record.fs_exe) == exe


@pytest.mark.filterwarnings("ignore:none of the")
def test_a_silent_row_falls_back_to_the_default_and_the_record_says_so(tmp_path):
    """The other source, and the fallback the refusal text always promised.

    An empty FS_BUILD cell used to be carried into the build set
    verbatim, so this matrix asked the workspace registry for the build
    id '' and was refused as unregistered, however good the default was.
    """
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    path = write_matrix(tmp_path / "silent_only.fs", [SILENT_ROW])
    assert [row.fs_build for row in read_matrix(path)] == [""], (
        "this arm needs a matrix whose only active row names no build"
    )

    records = run_for_records(path, workspace)

    assert records, "the run recorded nothing to judge"
    for record in records:
        assert record.fs_version_source == FS_VERSION_FROM_DEFAULT
        assert Path(record.fs_exe) == exe, (
            "the campaign default did not answer for the row that names no build"
        )


@pytest.mark.filterwarnings("ignore:none of the")
def test_one_matrix_records_both_sources_row_by_row(tmp_path):
    """The case the per-row shape exists for: one silent row, one named.

    A single flag per RUN would report one of these two rows wrongly,
    and both run on the same installation, so nothing else in the record
    could tell them apart.
    """
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    path = write_matrix(tmp_path / "both_sources.fs", [SILENT_ROW, NAMED_ROW])

    records = run_for_records(path, workspace)

    sources = {record.sim_id: record.fs_version_source for record in records}
    assert sources == {"9101": FS_VERSION_FROM_DEFAULT, "9102": FS_VERSION_FROM_ROW}
    assert {Path(record.fs_exe) for record in records} == {exe}, (
        "both rows run on one installation; only the SOURCE differs"
    )
    # And the manifest on disk says it, not just the returned objects.
    stored = {record.sim_id: record.fs_version_source for record in workspace.read_manifest()}
    assert stored == sources


@pytest.mark.filterwarnings("ignore:none of the")
def test_the_explicit_override_is_recorded_as_the_campaign_not_the_row(tmp_path):
    """The override overrules the column, and the record must agree.

    The warning ``_resolve_build`` raises says these rows will be
    recorded against the campaign's declared version and not the build
    they asked for. Recording them as row-chosen would contradict the
    package's own warning.
    """
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", "C:/unused/FlightStream.exe"))
    with pytest.warns(UserWarning, match="overruling the FS_BUILD value"):
        records = run_for_records(REGISTRY_FIXTURE, workspace, fs_exe=exe)

    assert records
    for record in records:
        assert record.fs_version_source == FS_VERSION_FROM_DEFAULT
        assert Path(record.fs_exe) == exe


@pytest.mark.filterwarnings("ignore:none of the")
def test_the_record_alone_resolves_to_the_same_build(tmp_path):
    """The reproduction clause: no matrix, no registry, just the record.

    A reader who has only the manifest must reach the same installation
    and the same version the run used. The three fields that carry it
    are ``fs_exe`` (which binary), ``fs_exe_sha256`` (still that
    binary), and ``fs_version_requested`` (which command database the
    script was built against).
    """
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    path = write_matrix(tmp_path / "reproduce.fs", [SILENT_ROW, NAMED_ROW])
    run_for_records(path, workspace)

    expected = (exe, resolve("26.120").canonical)
    manifest = workspace.read_manifest()
    assert manifest, "nothing was recorded to reproduce"
    for record in manifest:
        reproduced = (Path(record.fs_exe), resolve(record.fs_version_requested).canonical)
        assert reproduced == expected, (
            f"{record.run_id} cannot be reproduced from its own record: it names "
            f"{reproduced} where the run used {expected}"
        )
        assert record.fs_exe_sha256 == file_sha256(exe), (
            "the recorded digest does not identify the binary that ran, so a reader "
            "cannot tell whether the same installation is still there"
        )


def test_resolve_matrix_reports_which_rows_named_their_own_build(tmp_path):
    """The one fact only the binding step knows, and where it is stated.

    By the time a record is written both sources have become the same
    executable, so the provenance has to be captured here or not at all.
    """
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    path = write_matrix(tmp_path / "row_builds.fs", [SILENT_ROW, NAMED_ROW])

    resolved = resolve_matrix(path, workspace, name="prov", fs_version="26.120", recipes=RECIPES)

    assert resolved.row_builds == (None, "26.120")
    assert len(resolved.row_builds) == len(resolved.campaign.sims), (
        "row_builds is read positionally against campaign.sims; a length mismatch "
        "would attribute one row's build to another row"
    )
    assert resolved.fs_exe == exe


def test_an_override_leaves_no_row_claiming_it_chose_the_build(tmp_path):
    """Every entry None under the override, and that is a statement."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/unused/FlightStream.exe"))
    path = write_matrix(tmp_path / "override_rows.fs", [SILENT_ROW, NAMED_ROW])

    with pytest.warns(UserWarning, match="overruling the FS_BUILD value"):
        resolved = resolve_matrix(
            path,
            workspace,
            name="prov",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/elsewhere/FlightStream.exe",
        )

    assert resolved.row_builds == (None, None)


def test_the_override_warning_never_lists_a_row_that_named_nothing(tmp_path):
    """A silent row is not overruled: it asked for nothing.

    It used to be listed anyway, as an empty id in the middle of the
    sentence, between the words value(s) and the comma.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/unused/FlightStream.exe"))
    path = write_matrix(tmp_path / "override_warning.fs", [SILENT_ROW, NAMED_ROW])

    with pytest.warns(UserWarning, match="overruling the FS_BUILD value") as caught:
        resolve_matrix(
            path,
            workspace,
            name="prov",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/elsewhere/FlightStream.exe",
        )

    message = str(caught[0].message)
    assert "value(s) 26.120 that" in message, (
        f"the overruled list is not exactly the rows that named a build: {message}"
    )


def test_a_silent_row_and_a_named_row_reach_two_installations(tmp_path):
    """A silent row and a named row that disagree are two installations.

    They were REFUSED for it until PFS-2009.05, which is the refusal this
    item removes: the campaign's own installation answers for the silent
    row and the named row runs on the one its cell names, so the campaign
    default and a second build coexist in one file.
    """
    workspace = make_library(tmp_path)
    register(workspace, "26.101", "C:/fs26101/FlightStream.exe")
    register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
    # The NAMED row FIRST, deliberately. With the silent row first, the
    # campaign's own build and the first row's build are the same string,
    # and every wrong rule for choosing between them gives the right
    # answer.
    path = write_matrix(tmp_path / "two_installations.fs", [NAMED_ROW, SILENT_ROW])

    resolved = resolve_matrix(path, workspace, name="prov", fs_version="26.101", recipes=RECIPES)

    assert resolved.row_builds == ("26.120", None)
    # The campaign's own executable is the DEFAULT's here, because a row
    # names no build and that is the row it answers for.
    assert resolved.fs_exe == Path("C:/fs26101/FlightStream.exe")
    assert set(resolved.builds) == {"26.120"}, (
        "only a build a ROW names belongs in the mapping; the campaign default "
        "answers through campaign.fs_exe"
    )
    assert resolved.builds["26.120"].fs_exe == Path("C:/fs26120/FlightStream.exe")


def test_an_unregistered_default_is_refused_as_the_default_and_not_as_a_cell(tmp_path):
    """The remedies differ, so the message must say which id this is.

    Editing an FS_BUILD cell does nothing for a build id that arrived
    from the campaign default, and the cell in question is empty.
    """
    workspace = make_library(tmp_path)  # registry template only, no entries
    path = write_matrix(tmp_path / "unregistered_default.fs", [SILENT_ROW])

    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(path, workspace, name="prov", fs_version="26.120", recipes=RECIPES)

    message = str(caught.value)
    assert "campaign default version '26.120'" in message, message
    assert "row 1 (POL 9101)" in message, message
    assert "executables.toml" in message


def test_binding_a_matrix_directly_refuses_a_blank_default_before_the_registry(tmp_path):
    """PFS-2009.08.03 for the caller who binds without planning or running.

    ``plan_matrix`` and ``run_matrix`` refuse above this function, and a
    caller who calls ``resolve_matrix`` itself reaches neither of them.
    Without the same refusal here the silent row falls back to a blank
    default, and the first thing that notices is the executable registry,
    which reports a missing build id rather than a missing option.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/unused/FlightStream.exe"))
    path = write_matrix(tmp_path / "blank_default.fs", [SILENT_ROW])

    with pytest.raises(MatrixError) as caught:
        resolve_matrix(path, workspace, name="prov", fs_version="   ", recipes=RECIPES)

    message = str(caught.value)
    assert "row 1 (POL 9101)" in message, message
    assert DEFAULT_VERSION_OPTION in message
    assert "executables.toml" not in message, (
        f"the executable registry answered a question about a missing option: {message}"
    )


def count_identity_probes(monkeypatch):
    """Count the identity pre-flights a run spends, without running any.

    Each one launches the solver, so this is a licensed-seat cost and not
    a stylistic one; the campaign loop asks once per installation that
    still has work, keyed by the case's ``fs_build``.
    """
    import pyflightstream.run as run_module

    calls = []

    def counting(executor, version, workdir):
        calls.append(version)

    monkeypatch.setattr(run_module, "check_solver_identity", counting)
    return calls


@pytest.mark.filterwarnings("ignore:none of the")
def test_a_matrix_on_one_installation_is_asked_which_build_it_is_once(tmp_path, monkeypatch):
    """Carrying the provenance must not multiply the pre-flight.

    Every active row names the same build, so there is one installation
    and one question to ask it. A row-keyed build mapping that also left
    the campaign answering for someone would ask twice, and each ask is
    a solver launch.
    """
    calls = count_identity_probes(monkeypatch)
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))

    run_for_records(REGISTRY_FIXTURE, workspace)

    assert len(calls) == 1, f"one installation was asked {len(calls)} times: {calls}"


@pytest.mark.filterwarnings("ignore:none of the")
def test_a_mixed_matrix_asks_its_one_installation_once_per_source(tmp_path, monkeypatch):
    """The measured cost of per-row provenance, stated rather than hidden.

    A matrix mixing a silent row with a row naming the same build reaches
    ONE executable under TWO keys, because the campaign loop groups by
    ``fs_build`` and the silent rows sit under the campaign's own key. It
    therefore launches the solver twice to ask one installation the same
    question.

    It is not a regression: before this item a mixed matrix did not run
    at all, being refused for naming two FS_BUILD values, one of which
    was the empty string. The structural fix is to group by the resolved
    EXECUTABLE rather than by the key, which lives in
    ``pyflightstream.run._check_scheduled_builds``. If this number drops
    to 1, that fix landed: lower it here rather than deleting the test.
    """
    calls = count_identity_probes(monkeypatch)
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))
    path = write_matrix(tmp_path / "probe_cost.fs", [SILENT_ROW, NAMED_ROW])

    run_for_records(path, workspace)

    assert len(calls) == 2, (
        f"the mixed matrix spent {len(calls)} identity probe(s) on one installation; "
        "2 is the measured cost of keying the pre-flight by fs_build"
    )
    assert set(calls) == {resolve("26.120")}, (
        "both probes must ask about the campaign default version: a build id is a "
        "registry key and never a declaration of which command database a build has"
    )


# --- PFS-2009.05: the run matrix lives in the workspace layer ---------------
#
# The item removed the refusal that a matrix's active rows must agree on a
# single FS_BUILD value. What replaces it is not a relaxation: each row
# runs on the installation its own cell names, and the record says which
# one it was, so nothing is recorded against an executable it never used.
#
# The version a row's script is emitted under is a DECLARATION, never an
# inference from a build id or an executable path, and the place the
# caller makes it is the executable registry: the file where they already
# say what a build id means on this machine.

SECOND_BUILD_ROW = (
    "9103 | TestWing | SECOND_BUILD | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 |   26.123 | 1 | 1 | OUTPUTS: loads_{point}.txt"
)


def two_real_executables(tmp_path):
    """Two files that really exist, with DIFFERENT bytes.

    Different bytes deliberately: the acceptance names ``fs_exe_sha256``
    beside ``fs_exe``, and two installations with identical content would
    hash the same, so a record naming the wrong one would still pass a
    digest comparison.
    """
    first = tmp_path / "fs26120" / "FlightStream.exe"
    second = tmp_path / "fs26123" / "FlightStream.exe"
    for path, body in ((first, b"build 26.120"), (second, b"a different build, 26.123")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    assert file_sha256(first) != file_sha256(second)
    return first, second


@pytest.mark.filterwarnings("ignore:none of the")
def test_each_row_is_recorded_against_the_installation_it_asked_for(tmp_path):
    """The acceptance, end to end: two builds, one run, two records.

    Every clause of it is here. Each record names in ``fs_exe`` and
    ``fs_exe_sha256`` the executable its OWN row asked for rather than
    the campaign's, and ``fs_version_requested`` is the version that
    build's registry entry declares.
    """
    first, second = two_real_executables(tmp_path)
    workspace = make_library(tmp_path)
    register(workspace, "26.120", first.as_posix())
    register(workspace, "26.123", second.as_posix(), version="26.123")
    path = write_matrix(tmp_path / "per_row_build.fs", [NAMED_ROW, SECOND_BUILD_ROW])

    records = run_for_records(path, workspace)

    by_sim = {record.sim_id: record for record in records}
    assert set(by_sim) == {"9102", "9103"}, f"both rows must run: {sorted(by_sim)}"
    assert Path(by_sim["9102"].fs_exe) == first
    assert Path(by_sim["9103"].fs_exe) == second, (
        "the row naming 26.123 was recorded against the campaign's executable, which "
        "is the falsehood the single-build refusal used to prevent by refusing"
    )
    assert by_sim["9102"].fs_exe_sha256 == file_sha256(first)
    assert by_sim["9103"].fs_exe_sha256 == file_sha256(second)
    assert by_sim["9102"].fs_version_requested == "26.120"
    assert by_sim["9103"].fs_version_requested == "26.123", (
        "the second build declares version 26.123 in the registry and its row's "
        "script was emitted under the campaign default instead"
    )
    assert by_sim["9102"].fs_version_source == FS_VERSION_FROM_ROW
    assert by_sim["9103"].fs_version_source == FS_VERSION_FROM_ROW
    # And the manifest on disk says it, not only the returned objects.
    stored = {record.sim_id: Path(record.fs_exe) for record in workspace.read_manifest()}
    assert stored == {"9102": first, "9103": second}


@pytest.mark.filterwarnings("ignore:none of the")
def test_the_script_of_a_row_is_emitted_under_its_own_builds_version(tmp_path):
    """The version reaches the SCRIPT, not only the record field.

    A record naming a version whose command database the script was
    never built against would be evidence of nothing, so this asserts
    the version the emitter saw rather than the string in the manifest.
    """
    first, second = two_real_executables(tmp_path)
    workspace = make_library(tmp_path)
    register(workspace, "26.120", first.as_posix())
    register(workspace, "26.123", second.as_posix(), version="26.123")
    path = write_matrix(tmp_path / "script_version.fs", [NAMED_ROW, SECOND_BUILD_ROW])

    seen = {}

    def version_spying_recipe(case, script):
        seen[case.sim_id] = str(script.version)
        matrix_recipe(case, script)

    run_matrix(
        path,
        workspace,
        name="prov",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        executor=StubSolver(WRITES_LOADS),
        recipe_registry={"steady": version_spying_recipe},
    )

    assert seen == {"9102": "26.120", "9103": "26.123"}


@pytest.mark.filterwarnings("ignore:none of the")
def test_a_build_that_declares_no_version_falls_back_to_the_campaign_default(tmp_path):
    """The bare path string keeps meaning exactly what it meant.

    Both builds are registered as bare strings here, so neither declares
    a version, and both rows are emitted under the campaign default even
    though they run on two different installations. That is the half of
    the design which keeps every registry written before this item
    working unaltered.
    """
    first, second = two_real_executables(tmp_path)
    workspace = make_library(tmp_path)
    register(workspace, "26.120", first.as_posix())
    register(workspace, "26.123", second.as_posix())
    path = write_matrix(tmp_path / "no_declared_version.fs", [NAMED_ROW, SECOND_BUILD_ROW])

    records = run_for_records(path, workspace)

    by_sim = {record.sim_id: record for record in records}
    assert {record.fs_version_requested for record in records} == {"26.120"}, (
        "a build declaring no version must fall back to the campaign default, and "
        "its build id must NOT be read as a version"
    )
    # The installation still differs: only the version fell back.
    assert Path(by_sim["9103"].fs_exe) == second


@pytest.mark.filterwarnings("ignore:none of the")
def test_a_single_build_matrix_records_exactly_what_it_recorded_before(tmp_path):
    """The last acceptance clause, as a regression rather than a claim.

    One build, registered in the shape every registry before this item
    used. The four fields a record carries about its installation must
    be what they were: the registered executable, its digest, the
    campaign default version, and the row as the source.
    """
    exe = real_executable(tmp_path)
    workspace = make_library(tmp_path, register_build=("26.120", exe.as_posix()))

    records = run_for_records(REGISTRY_FIXTURE, workspace)

    assert records, "the run recorded nothing to judge"
    for record in records:
        assert Path(record.fs_exe) == exe
        assert record.fs_exe_sha256 == file_sha256(exe)
        assert record.fs_version_requested == "26.120"
        assert record.fs_version_source == FS_VERSION_FROM_ROW


def test_one_executor_is_built_per_installation(tmp_path, monkeypatch):
    """An executor is bound to an executable, so two builds need two.

    And no more than two: the campaign's own executor answers for its
    own executable, so a build resolving to it must not construct a
    second one. Each construction is an object bound to a process this
    run will launch, and a duplicate would be a second identity
    pre-flight of one installation.
    """
    import pyflightstream.run.matrix as matrix_module

    first, second = two_real_executables(tmp_path)
    built = []

    class Recording(StubSolver):
        def __init__(self, fs_exe, hidden=True, **kwargs):
            built.append(Path(fs_exe))
            super().__init__(WRITES_LOADS)

    monkeypatch.setattr(matrix_module, "LocalExecutor", Recording)
    workspace = make_library(tmp_path)
    register(workspace, "26.120", first.as_posix())
    register(workspace, "26.123", second.as_posix(), version="26.123")
    path = write_matrix(tmp_path / "executors.fs", [NAMED_ROW, SECOND_BUILD_ROW])

    with pytest.warns(UserWarning, match="none of the"):
        run_matrix(
            path,
            workspace,
            name="prov",
            default_fs_version="26.120",
            recipes=RECIPES,
            assess=converged,
            recipe_registry={"steady": matrix_recipe},
        )

    assert built == [first, second], (
        f"one executor per distinct executable, in first-appearance order: {built}"
    )


@pytest.mark.filterwarnings("ignore:none of the")
def test_an_executor_the_caller_supplied_answers_for_every_build(tmp_path, monkeypatch):
    """A caller who hands in an executor has bound the whole run to it.

    Building a LocalExecutor beside it for the second build would send
    some rows to a process the caller never asked for, which is a worse
    failure than the two-build refusal this item removed.
    """
    import pyflightstream.run.matrix as matrix_module

    def refuse(*args, **kwargs):
        raise AssertionError("a LocalExecutor was built although the caller supplied one")

    monkeypatch.setattr(matrix_module, "LocalExecutor", refuse)
    first, second = two_real_executables(tmp_path)
    workspace = make_library(tmp_path)
    register(workspace, "26.120", first.as_posix())
    register(workspace, "26.123", second.as_posix(), version="26.123")
    path = write_matrix(tmp_path / "supplied_executor.fs", [NAMED_ROW, SECOND_BUILD_ROW])

    records = run_for_records(path, workspace)

    assert {record.sim_id for record in records} == {"9102", "9103"}
    assert {Path(record.fs_exe) for record in records} == {first, second}


def test_a_bound_matrix_carrying_half_the_pair_is_refused(tmp_path):
    """row_builds and builds are filled together, or the run cannot start.

    Only a hand-built ResolvedMatrix can carry one without the other,
    and the alternative to refusing is falling back to the campaign's
    executable, which records a point against an installation it never
    ran on.
    """
    import dataclasses

    from pyflightstream.run.matrix import _bind_row_builds

    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    path = write_matrix(tmp_path / "half_pair.fs", [NAMED_ROW])
    resolved = resolve_matrix(path, workspace, name="prov", fs_version="26.120", recipes=RECIPES)
    assert resolved.builds, "the fixture must carry the entry this test then removes"

    stripped = dataclasses.replace(resolved, builds={})
    with pytest.raises(MatrixError, match="row_builds and carries no entry"):
        _bind_row_builds(stripped, "26.120", StubSolver(WRITES_LOADS), lambda exe: None)


def test_the_reader_holds_no_import_inside_a_function_body():
    """The item's first clause, over the module the hoist emptied.

    ``cases/matrix.py`` deferred five imports to call time, each of them
    reaching a layer above it, which recorded the dependency while
    hiding it from every module-level reader. The layer guard in
    ``tests/test_conventions.py`` owns the rule for the whole package;
    this asserts the item's own subject, so a re-deferral in that one
    file fails beside the tests of what the hoist was for.
    """
    import ast

    import pyflightstream.cases.matrix as reader

    tree = ast.parse(Path(reader.__file__).read_text(encoding="utf-8"))
    functions = [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    offenders = [
        f"{outer.name}() at line {node.lineno}"
        for outer in functions
        for node in ast.walk(outer)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert not offenders, "cases/matrix.py imports inside a function body: " + ", ".join(offenders)
    # Non-vacuity: a walk that found no function would report green.
    assert len(functions) >= 10, (
        f"the walk found {len(functions)} function(s) in {reader.__file__}; the module "
        "has many more, so a smaller number means the walk is broken"
    )


MANUAL_ROW = (
    "9104 | TestWing | MANUAL_ROW | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 |   MANUAL | 1 | 1 | OUTPUTS: loads_{point}.txt"
)


def test_a_default_that_no_row_falls_back_to_need_not_be_registered(tmp_path):
    """A registry entry nothing runs on is not a precondition of a run.

    Every active row names its own build here, so the campaign default
    answers for nobody. Resolving it anyway would make an unrelated
    registry entry, and on the default executor an unrelated FILE ON
    DISK, a precondition of a run that never touches either.
    """
    workspace = make_library(tmp_path)
    register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
    register(workspace, "26.123", "C:/fs26123/FlightStream.exe", version="26.123")
    path = write_matrix(tmp_path / "unused_default.fs", [NAMED_ROW, SECOND_BUILD_ROW])

    resolved = resolve_matrix(path, workspace, name="prov", fs_version="26.101", recipes=RECIPES)

    assert resolved.fs_exe == Path("C:/fs26120/FlightStream.exe"), (
        "26.101 is registered as a VERSION and not as a build of this workspace, and "
        "no row falls back to it; the campaign's own executable is the first row's"
    )
    assert set(resolved.builds) == {"26.120", "26.123"}


def test_an_unregistered_build_a_cell_names_is_not_reported_as_the_default(tmp_path):
    """The two remedies stay apart when both kinds of id are in one file.

    A silent row makes the campaign default a live build id, so the
    condition "some row named none" is true while the id that failed to
    resolve came from a CELL. Reading the first as evidence of the
    second sends the reader to edit a default that is fine.
    """
    workspace = make_library(tmp_path)
    register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
    unregistered = NAMED_ROW.replace("26.120", "26.121")
    path = write_matrix(tmp_path / "cell_not_default.fs", [SILENT_ROW, unregistered])

    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(path, workspace, name="prov", fs_version="26.120", recipes=RECIPES)

    message = str(caught.value)
    assert "FS_BUILD column" in message and "'26.121'" in message, message
    assert "campaign default" not in message, (
        f"a build id a CELL names was reported as the campaign default: {message}"
    )


def test_the_refusal_names_the_build_the_file_names_first(tmp_path):
    """MUTANT: `dict.fromkeys(effective)` reduced to `sorted(set(effective))`.

    The comment at that site states the intent outright: the registry is
    read in the order the FILE names the builds, so a refusal names the
    first one a reader would look at rather than the alphabetically
    smallest. A QA pass on 2026-08-20 measured that nothing observed it:
    the mutant survived all 433 cases of this module, because every other
    multi-build case happens to name its builds in alphabetical order.

    So this case names them in REVERSE alphabetical order and asserts
    which one the message reaches for. Both are unregistered, so either
    could legitimately be refused; what is pinned is WHICH, and that is
    the whole content of the design choice.
    """
    workspace = make_library(tmp_path)
    register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
    first = NAMED_ROW.replace("26.120", "26.123")
    second = NAMED_ROW.replace("26.120", "26.121")
    path = write_matrix(tmp_path / "reverse_order.fs", [first, second])

    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(path, workspace, name="prov", fs_version="26.120", recipes=RECIPES)

    message = str(caught.value)
    assert "'26.123'" in message, (
        "the refusal did not name the build the FILE names first; under "
        "alphabetical ordering it would name 26.121, which is the row a reader "
        f"looks at second. Message: {message}"
    )


def test_a_manual_row_beside_a_registered_one_still_needs_the_override(tmp_path):
    """MANUAL is refused wherever it sits, not only in the first row.

    The refusal used to be asked of the ONE build a single-build matrix
    collapsed to. With several builds it has to be asked of each, or a
    MANUAL cell in the second row reaches the registry and is refused as
    an unregistered build id, which names the wrong remedy.
    """
    workspace = make_library(tmp_path)
    register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
    path = write_matrix(tmp_path / "manual_second.fs", [NAMED_ROW, MANUAL_ROW])

    with pytest.raises(MatrixError, match="MANUAL.*fs_exe"):
        resolve_matrix(path, workspace, name="prov", fs_version="26.120", recipes=RECIPES)


# --- PFS-2025.02.01: a row names its geometry through the input library ------


#: One active row, with its VAR_NAMES_VALUES cell left open to the case.
#: The codes are the lettered ids `make_library` stages (PFS-2009.01).
GEOMETRY_ROW = (
    "7001 | TestWing | GEOMETRY_ROW | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 | 26.120 |  0 | 1 | OUTPUTS: loads_{{point}}.txt{tail}"
)


def stage_geometry(workspace, name, body=b"fake simulation"):
    """Put one file in the workspace geometry library and return its path."""
    path = workspace.inputs_dir / "geometries" / name
    path.write_bytes(body)
    return path


def geometry_matrix(tmp_path, tail, stem="geometry.fs"):
    """Write a one-row matrix whose variables cell carries `tail`."""
    return write_matrix(tmp_path / stem, [GEOMETRY_ROW.format(tail=tail)])


def resolve_geometry_row(tmp_path, workspace, tail, stem="geometry.fs"):
    """Resolve a one-row matrix and return its single case."""
    matrix = geometry_matrix(tmp_path, tail, stem)
    resolved = resolve_matrix(
        matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES
    )
    return resolved.campaign.sims[0]


def test_a_row_naming_a_geometry_resolves_it_against_the_input_library(tmp_path):
    """THE DEFECT, at the layer that had no way to say it.

    ``resolve_matrix`` never assigned ``SimCase.geometry`` and the word
    "geometr" did not occur in this module, so a run matrix could not
    name a geometry AT ALL. The run layer had always done its half:
    ``_prepare_case`` stages the file, hashes it into the record, and
    rewrites the field to the staged copy before a builder is called.
    The value was prepared and read by nobody.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    staged = stage_geometry(workspace, "wing_clean.fsm")
    case = resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_clean")
    assert case.geometry is not None, "the row named a geometry and the case carries none"
    assert Path(case.geometry) == staged


def test_the_id_is_a_stem_and_the_library_extension_is_whatever_was_staged(tmp_path):
    """The id is the file name STEM, never a path and never a suffix.

    Resolution is delegated to ``workspace.resolve_geometry``, which
    registers a staged file under any extension. Which suffixes a
    WORKFLOW will open is a different question, decided one layer up in
    ``cases.workflows``: a library holding a raw mesh is legitimate, and
    a row pointing a workflow at one is what is refused.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    staged = stage_geometry(workspace, "raw_blade.stl")
    case = resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: raw_blade")
    assert Path(case.geometry) == staged


def test_the_stem_the_row_wrote_survives_in_the_case_variables(tmp_path):
    """The conversion stays lossless (FR-11): the cell is still readable.

    The resolved PATH lands on the field and the ID stays in the
    variables, so a record can still say which library artifact the row
    asked for and not only which file it got.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    case = resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_clean")
    assert case.variables[GEOMETRY_VARIABLE] == "wing_clean"


def test_a_row_naming_no_geometry_leaves_the_field_absent(tmp_path):
    """The property that makes this shippable as a patch.

    Measured on the SHIPPED fixtures rather than on an inline row: every
    matrix written before this release resolves exactly as it did, which
    means every case of them carries no geometry and every builder emits
    the bytes it always emitted.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    assert resolved.campaign.sims, "the fixture resolved to no cases, so this proves nothing"
    assert all(case.geometry is None for case in resolved.campaign.sims)
    assert not any(GEOMETRY_VARIABLE in case.variables for case in resolved.campaign.sims), (
        "the shipped fixture already names a geometry, so the case above is not measuring "
        "a matrix written before this release"
    )


def test_a_geometry_cell_that_strips_to_empty_names_nothing(tmp_path):
    """Blank and absent are the same silence, as they are for FS_BUILD.

    A row whose cell is empty NAMES NO GEOMETRY, so it resolves exactly
    as a row that never wrote the key. Refusing it instead would change
    how a pre-existing matrix resolves, which is the one thing a patch
    release may not do.

    THE PROPERTY IS COMPOSED OF TWO HALVES and both are asserted, in the
    order the value travels. The reader strips every VAR_NAMES_VALUES
    value as it parses the cell, and the binder treats the empty string
    as no geometry; a strip in the binder as well would be a second
    guard that no input can reach, which is exactly what a mutation
    found there (it deleted the strip and the whole suite stayed green).
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    matrix = geometry_matrix(tmp_path, " / GEOMETRY:   ")
    row = read_matrix(matrix)[0]
    assert row.variables[GEOMETRY_VARIABLE] == "", (
        "the reader no longer strips a variable value, so the binder is now the only "
        "thing between a whitespace cell and the input library and it does not strip"
    )
    assert resolve_geometry_row(tmp_path, workspace, " / GEOMETRY:   ").geometry is None


def test_a_geometry_the_library_cannot_resolve_is_refused_naming_the_row(tmp_path):
    """The row, its POL, the stem written, and what would have resolved.

    The sibling REF, SET and ENTRY refusals all name the row's POL, and
    this one has to as well: a campaign has as many rows as it has
    points, and "no geometry artifact with id 'wing_v3'" sends the
    author to grep their own matrix.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    stage_geometry(workspace, "wing_flapped.fsm")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_v3")
    message = str(caught.value)
    assert "POL 7001" in message, "the refusal does not name the row"
    assert GEOMETRY_VARIABLE in message, "the refusal does not name the variable"
    assert "'wing_v3'" in message, "the refusal does not name the stem that was written"
    assert "wing_clean" in message and "wing_flapped" in message, (
        "the refusal does not list the geometries that WOULD have resolved"
    )


def test_the_geometry_refusal_carries_its_structured_attributes(tmp_path):
    """A caller offering the user a choice does not parse the sentence.

    ``InputArtifactError`` carries ``kind``, ``artifact_id`` and
    ``available`` for exactly that, and re-raising with the row is where
    those get dropped.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_v3")
    assert caught.value.kind == "geometry"
    assert caught.value.artifact_id == "wing_v3"
    assert caught.value.available == ("wing_clean",)


def test_the_geometry_refusal_is_the_catalogued_exception_and_not_a_bare_raise(tmp_path):
    """No standard-library error out of a public name (FR-39).

    ``InputArtifactError`` is what a user catches for every other
    library miss, so a geometry miss must be catchable the same way. The
    ``RuntimeError`` half is asserted because that is the base a caller
    who has not imported the package name still catches.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_v3")
    assert isinstance(caught.value, RuntimeError)
    assert not isinstance(caught.value, (KeyError, FileNotFoundError, ValueError))


def test_an_id_that_could_not_be_a_file_name_is_refused_by_the_library(tmp_path):
    """A PATH in the cell is refused, and it is refused ONCE.

    Resolution is not reimplemented here: ``resolve_geometry`` already
    holds the id rule, the not-found listing and the ambiguity check, so
    a second resolver in this module would be a second answer to "which
    file is this id". The path form is what proves the library's own
    ``_check_id`` is the thing being reached.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: inputs\\geometries\\wing.fsm")
    message = str(caught.value)
    assert "POL 7001" in message, "the row is lost when the library refuses the id's shape"
    assert "never a path" in message, "the library's own id rule is not what refused this"


def test_a_stem_two_staged_files_share_is_refused_rather_than_chosen(tmp_path):
    """Which of two files an ambiguous id means is not a guess.

    The library owns this refusal too, and the row has to survive it:
    the author fixes a matrix cell or a staged file name, and both are
    findable only from the POL.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    stage_geometry(workspace, "wing_clean.stl")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_clean")
    message = str(caught.value)
    assert "POL 7001" in message
    assert "wing_clean.fsm" in message and "wing_clean.stl" in message


@pytest.mark.parametrize("staged_first", [True, False])
def test_a_cell_naming_the_file_name_is_told_the_id_is_the_stem(tmp_path, staged_first):
    """THE REFUSAL MUST NOT PRESCRIBE A DOUBLED EXTENSION.

    The id rule permits a dot, so ``GEOMETRY: wing_clean.fsm`` (what
    anyone who has just staged a file writes) passes the id check and
    misses in the library. The first wording told that user to stage
    ``inputs/geometries/wing_clean.fsm.fsm``: satisfiable, and the wrong
    action, because their file was already staged correctly and the CELL
    was what needed fixing.

    BOTH ORDERS ARE COVERED and that is the point of the parametrization.
    A first fix keyed the diagnosis on the stem already being staged,
    which serves only someone who staged before writing the cell; the
    commoner order is the other one, and it still received the doubled
    extension. The suffix in the WRITTEN id is what diagnoses this, and
    it is diagnosable with nothing else true.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    if staged_first:
        stage_geometry(workspace, "wing_clean.fsm")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_clean.fsm")
    message = str(caught.value)
    assert "wing_clean.fsm.fsm" not in message, (
        "the refusal prescribes a doubled extension, which is the defect this case "
        "exists to prevent"
    )
    assert f"{GEOMETRY_VARIABLE}: wing_clean" in message, (
        "the refusal does not show the cell the user should have written"
    )
    assert "STEM" in message, "the refusal does not name the rule that was broken"


@pytest.mark.parametrize("stem", ["wing_clean", "wing.v2"])
def test_an_ambiguous_stem_is_diagnosed_before_its_dot_is_mistaken_for_a_suffix(tmp_path, stem):
    """A DOTTED STEM IS A LEGITIMATE ID, and it shadowed the arm above it.

    ``wing.v2.fsm`` and ``wing.v2.stl`` is one mesh in two formats under
    a version-numbered stem, and the cell ``GEOMETRY: wing.v2`` is
    correct. The library refuses it for AMBIGUITY, and for one round the
    suffix arm was tested first: ``PurePath('wing.v2').suffix`` is
    ``'.v2'``, so that user was told to write ``GEOMETRY: wing`` and
    stage a third file, three sentences before the chained library text
    said their id matched two files and one should be removed.

    An ambiguity refusal proves the written id IS the shared stem, so it
    has to be diagnosed first. The dot-free case is kept beside it
    because it is the one the first version of this guard covered, and
    losing it would trade one blind spot for another.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, f"{stem}.fsm")
    stage_geometry(workspace, f"{stem}.stl")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, f" / GEOMETRY: {stem}")
    message = str(caught.value)
    assert f"{stem}.fsm" in message and f"{stem}.stl" in message
    assert "rename or remove" in message, "the refusal does not carry the real remedy"
    assert "STEM and not the file name" not in message, (
        "an ambiguous id was diagnosed as a file name, so the user is told to shorten "
        "a cell that is already correct"
    )
    assert "stage" not in message.split("A row that names no")[0].lower(), (
        "the refusal tells a user whose file is staged twice to stage it"
    )


def test_a_cell_holding_a_path_is_told_the_id_is_a_stem(tmp_path, monkeypatch):
    """A path-shaped cell must not be told to create a file with separators in its name.

    ``_check_id`` refuses the SHAPE, and its refusal carries the same
    structured attributes as a miss into an empty library, so without an
    arm of its own the general remedy fired: "stage a file whose name is
    '...rotor' plus its extension". That file cannot be created, a
    subdirectory would not resolve either, and the chained library
    sentence says "never a path" immediately afterwards.

    THE SEPARATOR IS A BACKSLASH, and it is the only one that reaches
    here. A forward slash is the ``VAR_NAMES_VALUES`` cell's own
    separator between KEY:VALUE entries, so a matrix carrying one is
    refused by the reader before this function is called at all. A
    backslash is what a Windows user pastes from an explorer window, and
    it travels through the cell untouched, which is why the arm names
    both separators itself rather than asking ``PurePath``: on a POSIX
    runner ``PurePosixPath`` does not treat it as one.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    pasted = "inputs\\geometries\\rotor"
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, f" / GEOMETRY: {pasted}")
    message = str(caught.value)
    assert f"{GEOMETRY_VARIABLE}: rotor" in message, (
        "the refusal does not show the cell the user should have written"
    )
    assert f"whose name is '{pasted}'" not in message, (
        "the refusal prescribes a file name containing path separators, which cannot "
        "be created and which the library's own sentence contradicts"
    )
    # THE STEM MUST NOT BE PLATFORM-DEPENDENT, and this assertion is the
    # whole reason the arm computes it with an explicit POSIX rule. A
    # shared `PurePath(...).stem` is `PureWindowsPath` on this machine
    # and `PurePosixPath` on the runner, and the second does not split a
    # backslash: the remedy became the user's own input, echoed back
    # inside a sentence saying "never a path", on the one platform CI
    # runs and this machine does not.
    assert pasted not in message.split("which the workspace")[1].split(". ")[0], (
        "the refusal quotes the path back as the cell to write, which is the input "
        "that was just refused; the stem was computed with the platform's own "
        "separator rule rather than with both"
    )

    # THE OTHER PLATFORM, SIMULATED, because this one cannot see the
    # defect. On Windows `PurePath` is `PureWindowsPath` and splits a
    # backslash, so the assertions above pass whether the arm uses the
    # explicit POSIX rule or the platform default. On the runner
    # `PurePath` is `PurePosixPath`, which does NOT, and the remedy
    # became the user's own input. Substituting the class is what makes
    # that reachable from here rather than only from a red CI leg.
    monkeypatch.setattr(matrix_module, "PurePath", PurePosixPath)
    with pytest.raises(InputArtifactError) as posix:
        resolve_geometry_row(tmp_path, workspace, f" / GEOMETRY: {pasted}", stem="p.fs")
    posix_message = str(posix.value)
    assert f"{GEOMETRY_VARIABLE}: rotor" in posix_message, (
        "under the POSIX path rule the refusal no longer names the stem, so the arm "
        "is relying on this machine's separator handling and the runner sees the "
        "input echoed back at it"
    )


def test_a_dotted_id_that_misses_is_not_told_to_truncate_its_version_tag(tmp_path):
    """A DOT IS LEGAL INSIDE AN ID, so a suffix does not prove a file name.

    The library holds ``blade.v3`` and the row says ``GEOMETRY: blade.v2``,
    a version typo. Read as a file name, that id's stem is ``blade``, and
    the suffix arm used to say so: it told the author to truncate a
    correct version tag and to stage a third file, while the chained
    listing named ``blade.v3`` as the id that would have resolved.

    Nothing here can tell a version-tagged stem from a file name, so the
    refusal gives BOTH readings rather than guessing one. The arm that
    does commit to the file-name reading fires only when the library
    corroborates it, which is the sibling case above.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "blade.v3.fsm")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: blade.v2")
    message = str(caught.value)
    assert "blade.v3" in message, "the refusal does not name the id that would resolve"
    assert f"{GEOMETRY_VARIABLE}: blade'" not in message, (
        "the refusal tells the author to truncate a version tag, and the id it points "
        "at does not resolve either"
    )
    assert "reads two ways" in message, "the refusal commits to one reading it cannot prove"


def test_an_id_refused_for_its_shape_is_told_to_fix_the_cell_not_to_stage_a_file(tmp_path):
    """No file of that name can resolve, so staging one is the wrong action.

    ``_check_id`` refuses on shape, and its refusal carries the same
    structured attributes as a miss into an empty library. Without an arm
    of its own, a cell like ``_wing`` was told to stage ``_wing`` plus an
    extension; the author does that and meets the identical refusal,
    because the leading character rule is what they broke.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: _wing")
    message = str(caught.value)
    assert "stage a file whose name is" not in message, (
        "the refusal tells the author to stage a file that cannot resolve under any "
        "extension, because the id's SHAPE is what was refused"
    )
    assert "beginning with a letter or a digit" in message, (
        "the refusal does not state the rule that was broken"
    )


def test_no_refusal_offers_dropping_the_key_as_a_way_out(tmp_path):
    """The compatibility sentence must not read as a third option.

    Every geometry refusal used to end "A row that names no GEOMETRY at
    all opens no file and is unaffected". True, and in a refusal it reads
    as a remedy: taking it produces a workflow with no OPEN, which is
    PFS-2025.02.01 exactly, a script that runs against whatever the
    solver had in memory and reports numbers with nothing said. A blocked
    engineer under time pressure is the reader who takes the option that
    makes the error go away.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: absent_stem")
    message = str(caught.value)
    assert "is unaffected" not in message, (
        "the refusal offers naming no geometry as a way out, which is the defect this "
        "release exists to remove"
    )


def test_an_ambiguous_stem_is_not_told_to_stage_the_file_it_staged_twice(tmp_path):
    """The third arm, which the two-arm version answered wrongly.

    With ``wing_clean.fsm`` and ``wing_clean.stl`` both staged and the
    cell written correctly as the stem, the library refuses for
    AMBIGUITY. The general arm told that user to stage the file and to
    write the cell they had already written, while the real remedy,
    renaming or removing one of the two, was only in the chained
    sentence.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    stage_geometry(workspace, "wing_clean.stl")
    with pytest.raises(InputArtifactError) as caught:
        resolve_geometry_row(tmp_path, workspace, " / GEOMETRY: wing_clean")
    message = str(caught.value)
    assert "wing_clean.fsm" in message and "wing_clean.stl" in message
    assert "stage a file whose name is" not in message, (
        "the refusal tells a user whose file is staged twice to stage it, and to write "
        "the cell they already wrote"
    )
    assert "rename or remove" in message, "the refusal does not carry the real remedy"


@pytest.mark.parametrize("code", ["003", "r 003", "inputs/references/r003"])
def test_a_reference_code_refusal_never_prescribes_a_file_that_cannot_resolve(tmp_path, code):
    """THE SIBLING PATH, which had one arm where geometry now has five.

    Every REF, SET and ENTRY refusal used to end "put the artifact at
    inputs/references/<code>.toml", whatever was wrong with the code. The
    sharpest case is the one v0.8.0 created: a bare pre-v0.8.0 code like
    ``003`` was told to create ``003.toml`` while the library's own
    sentence, chained immediately after, said the file must be
    ``r003.toml`` and named the migration that renames it. The author
    creates the file and meets the identical refusal.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    matrix = write_matrix(
        tmp_path / "refcode.fs",
        [GEOMETRY_ROW.format(tail="").replace("| r003 |", f"| {code} |")],
    )
    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES)
    message = str(caught.value)
    assert "POL 7001" in message, "the refusal does not name the row"
    if code == "003":
        assert "leading letter since v0.8.0" in message, (
            "a pre-v0.8.0 code is told to create a file that cannot resolve, with no "
            "mention of the migration the library's own sentence names"
        )
    else:
        assert f"inputs/references/{code}.toml" not in message, (
            "the refusal prescribes a file whose name cannot be a valid id, so "
            "creating it changes nothing"
        )


def test_a_reference_refusal_carries_the_structured_attributes_its_class_promises(tmp_path):
    """A caller offering the user a choice must not be handed an empty one.

    ``InputArtifactError`` documents ``available`` as populated on a
    not-found refusal so callers do not parse the sentence. The geometry
    resolver carries all three across; the code resolver dropped them, so
    a genuine miss with real candidates arrived indistinguishable from an
    empty library.
    """
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs/FS.exe"))
    matrix = write_matrix(
        tmp_path / "refmiss.fs",
        [GEOMETRY_ROW.format(tail="").replace("| r003 |", "| r999 |")],
    )
    with pytest.raises(InputArtifactError) as caught:
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES)
    assert caught.value.artifact_id == "r999", "the row-level refusal dropped the id"
    assert caught.value.available, (
        "the row-level refusal reports no available ids, so a caller cannot offer the "
        "author the codes that would have resolved"
    )


def test_a_raw_mesh_row_is_refused_by_the_pre_flight_before_anything_is_staged(tmp_path):
    """THE OTHER HALF OF THE .stl SIBLING ABOVE, which stops at resolution.

    ``test_the_id_is_a_stem_and_the_library_extension_is_whatever_was_staged``
    stages a ``.stl``, asserts it lands on ``case.geometry``, and stops
    there, which reads as "a .stl row works". It does not: the library
    resolves any extension and the WORKFLOW opens one. With only those
    two cases the suite points in two directions and nothing joins them.

    What is asserted here is the composed behaviour and the commit
    message's own claim about it, that this capability's limits "refuse
    early and name themselves": the refusal arrives from the PRE-FLIGHT,
    so no seat is spent, no simulation folder is created and no bytes are
    copied. That last part is the difference between a refusal and a
    mess to clean up.
    """
    workspace = make_library(tmp_path, register_build=("26.120", Path(sys.executable).as_posix()))
    stage_geometry(workspace, "raw_blade.stl")
    matrix = geometry_matrix(tmp_path, " / VELOCITY: 30.0 / GEOMETRY: raw_blade")

    with pytest.raises(MatrixError) as caught:
        run_matrix(
            matrix,
            workspace,
            name="matrix",
            default_fs_version="26.120",
            recipes=RECIPES,
            assess=converged,
            executor=StubSolver(WRITES_LOADS),
            recipe_registry=workflow_registry(),
        )
    message = str(caught.value)
    assert "docs/mesh-inputs.md" in message, "the composed refusal lost the documented route"
    assert ".fsm" in message, "the composed refusal does not name the suffix that works"
    # MEASURED, and it corrects the assertion this case was first written
    # with. The simulation folder DOES exist: the pre-flight creates the
    # empty skeleton before it validates. That is not the property worth
    # asserting, and demanding its absence would have failed a campaign
    # that behaved correctly. What must be true is that nothing was
    # COPIED, WRITTEN or RECORDED, since those are the three things a
    # refusal arriving too late would leave behind.
    sim_dir = workspace.sim_dir("7001")
    assert not list((sim_dir / "inputs").iterdir()), (
        "the refused row staged its geometry anyway, so bytes were copied for a point "
        "that was never going to run"
    )
    assert not list((sim_dir / "scripts").iterdir()), "a script was written for a refused row"
    assert workspace.read_manifest() == [], "a refused row reached the manifest"


def test_the_whole_chain_the_row_the_staged_copy_and_the_opened_path(tmp_path):
    """END TO END, and the one case that proves the three items compose.

    A row names a geometry, the workspace resolves it, the campaign loop
    STAGES it into the case's own inputs directory and hashes those
    bytes into the record, and the workflow opens THE STAGED COPY. That
    last pairing is the load-bearing one: opening the library original
    instead would leave ``inputs_sha256`` naming bytes the solver never
    read, and would leave it silently.
    """
    workspace = make_library(tmp_path, register_build=("26.120", Path(sys.executable).as_posix()))
    library = stage_geometry(workspace, "wing_clean.fsm")
    matrix = geometry_matrix(
        tmp_path,
        " / VELOCITY: 30.0 / GEOMETRY: wing_clean / SYMMETRY: PERIODIC / PERIODIC_COPIES: 4",
    )
    records = run_matrix(
        matrix,
        workspace,
        name="matrix",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        executor=StubSolver(WRITES_LOADS),
        recipe_registry=workflow_registry(),
    )
    assert [record.status for record in records] == [RunStatus.CONVERGED]

    sim_dir = workspace.sim_dir("7001")
    staged = sim_dir / "inputs" / "wing_clean.fsm"
    assert staged.is_file(), "the campaign loop did not stage the geometry the row named"
    assert staged != library, "the staged copy IS the library file, so the pairing is untested"
    assert records[0].inputs_sha256 == {"wing_clean.fsm": file_sha256(library)}

    # THE SCRIPT THE SOLVER RAN, read off disk rather than spied on in
    # flight: the pre-flight builds a script of its own for validation,
    # before anything is staged, and asserting on whichever render a spy
    # saw first measures that one instead.
    executed = (sim_dir / records[0].script_path).read_text(encoding="utf-8")
    lines = executed.splitlines()
    assert lines[0] == "OPEN", "the executed script does not open the geometry first"
    # STRICT equality, not resolved-equality. Widening this was an
    # unforced weakening made in the commit that is about path SPELLING:
    # two paths that resolve alike but are spelled differently are
    # exactly the defect that commit fixes, and this is the case that
    # would otherwise see it. The relative-root sibling below is where
    # resolving is the requirement, and it says so.
    assert Path(lines[1]) == staged, (
        "the executed script opens a path other than the staged copy the record hashed, "
        "so the digest and the bytes the solver read are not the same file"
    )
    assert "SYMMETRY PERIODIC 4" in lines, "the row's symmetry did not reach the command"


def test_a_campaign_runs_under_the_relative_root_the_cli_defaults_to(tmp_path, monkeypatch):
    """THE ASSERTION EVERY SIBLING ABOVE IS UNABLE TO MAKE, and the reason is the fixture.

    Every guard of this module builds its workspace on ``tmp_path``,
    which is ABSOLUTE, so a path spelled from the caller's directory and
    one spelled from the solver's are the same string and no case can
    tell them apart. The SHIPPED DEFAULT is the other one: ``pyfs-matrix
    run`` and ``plan`` default ``--workspace`` to ``"."`` (``run/cli.py``)
    and hand it to ``CampaignWorkspace`` as written.

    Two things then cross into the solver's process, which runs with its
    working directory set to the simulation folder: the script's path in
    the argv, and the geometry path the script itself names. Spelled from
    a relative root, both were re-resolved from ``sims/sim_7001`` and
    landed one level too deep. This was measured, not reasoned: before
    the fix this case died with

        FileNotFoundError: 'camp/sims/sim_7001/scripts/a+00.0.txt'

    on a script that was sitting right there, and it would have done so
    for EVERY row of every matrix, with or without a geometry.

    The fix is at the root rather than at the two boundaries, so this
    case asserts the OUTCOME (a campaign completes and the opened file is
    where the solver looks) rather than the remedy: the day a third thing
    is handed to the solver it is covered without a new assertion.
    """
    workspace = make_library(tmp_path, register_build=("26.120", Path(sys.executable).as_posix()))
    stage_geometry(workspace, "wing_clean.fsm")
    matrix = geometry_matrix(tmp_path, " / VELOCITY: 30.0 / GEOMETRY: wing_clean")

    monkeypatch.chdir(tmp_path)
    argument = Path("camp")
    assert not argument.is_absolute(), "the fixture is absolute, so it proves nothing"
    relative = CampaignWorkspace(argument)
    assert relative.root.is_absolute(), "the workspace did not resolve the root it was given"

    records = run_matrix(
        matrix,
        relative,
        name="matrix",
        default_fs_version="26.120",
        recipes=RECIPES,
        assess=converged,
        executor=StubSolver(WRITES_LOADS),
        recipe_registry=workflow_registry(),
    )
    assert [record.status for record in records] == [RunStatus.CONVERGED], (
        f"the campaign did not complete under a relative root: {records[0].error}"
    )

    sim_dir = relative.sim_dir("7001")
    executed = (sim_dir / records[0].script_path).read_text(encoding="utf-8")
    opened = Path(executed.splitlines()[1])
    # `sim_dir / opened` IS the solver's resolution rule: an absolute
    # emitted path wins the join and stands on its own, a relative one is
    # taken from the execution directory. So this single expression asks
    # exactly what the solver asks, and it is why the case does not
    # simply assert `opened.is_absolute()`: absoluteness is today's
    # remedy, resolving from sim_dir is the requirement.
    assert (sim_dir / opened).is_file(), (
        f"the script opens {opened}, which does not exist from the solver's own "
        f"directory {sim_dir}: the open resolves against the execution directory"
    )
    assert (sim_dir / opened).resolve() == (sim_dir / "inputs" / "wing_clean.fsm").resolve()


def test_the_resolved_fluid_state_lands_on_the_case(tmp_path):
    """The WIRE between the two halves, which nothing asserted.

    A QA pass measured that `update["fluid"] = FluidState(...)` in
    resolve_matrix could be DELETED with 371 tests green: the resolver
    was tested, the builder was tested against a hand-built FluidState,
    and the line joining them was tested by nothing. The commit is named
    for the resolved state reaching the script, so this is the clause
    the whole change exists for.

    If it stops being true the campaign solves at the solver's default
    air while the row, the run record and ResolvedMatrix.conditions all
    say otherwise, which is the silent-wrong-answer shape this milestone
    was built to remove.
    """
    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    case = {sim.sim_id: sim for sim in resolved.campaign.sims}["9001"]
    condition = resolved.conditions["9001"]

    assert case.fluid is not None, "the resolved state never reached the case"
    assert case.fluid.density_kg_m3 == pytest.approx(condition.density_kg_m3)
    assert case.fluid.pressure_pa == pytest.approx(condition.pressure_pa)
    assert case.fluid.temperature_k == pytest.approx(condition.temperature_k)
    assert case.fluid.viscosity_pa_s == pytest.approx(condition.viscosity_pa_s)
    assert case.fluid.sonic_velocity_m_per_s == pytest.approx(
        condition.sonic_velocity_m_per_s
    )
    assert case.fluid.velocity_m_per_s == pytest.approx(condition.velocity_m_per_s)
    # The branch marker travels too: it is what stops a later reader
    # taking a solved density for an altitude.
    assert case.fluid.source == condition.density_source
    assert case.fluid.reference_length_m == condition.reference_length_m
    # And the ratio is the floor's, not a second literal.
    from pyflightstream._atmosphere import ISA

    assert case.fluid.heat_capacity_ratio == ISA.heat_capacity_ratio


def test_a_case_from_resolve_matrix_renders_its_fluid_state(tmp_path):
    """End to end: matrix row, resolver, case, emitted script.

    The other half of the same gap. Asserting the field lands is not
    the same as asserting a builder emits it, and the two were tested
    in disconnected halves.
    """
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script

    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    case = {sim.sim_id: sim for sim in resolved.campaign.sims}["9001"]
    condition = resolved.conditions["9001"]

    script = Script("26.123")
    steady = case.model_copy(
        update={"variables": {**case.variables, "WORKFLOW": "steady"}}
    )
    build_script(steady, script)
    lines = script.render().splitlines()

    assert "FLUID_PROPERTIES" in lines, "a resolved case emitted no fluid state"
    assert f"DENSITY {condition.density_kg_m3}" in lines
    assert f"TEMPERATURE {condition.temperature_k}" in lines
    # The reference reached it too, which is the other half of the
    # commit's own sentence.
    assert any(line.startswith("SOLVER_SET_REF_AREA") for line in lines)
    assert any(line.startswith("SOLVER_SET_REF_LENGTH") for line in lines)


def test_the_run_record_carries_the_condition_and_the_resolved_state(tmp_path):
    """PFS-2027.05's first clause, which nothing implemented until now.

    The acceptance sentence is that the run record carries the condition
    string AS WRITTEN, every resolved quantity and the reference length,
    so a reader can RECOMPUTE the resolution rather than trust it. Four
    places in this repository said it did. A round-two technical-writer
    pass measured that the run layer held no such field at all: the
    branch marker lived on the resolved matrix and on the case, neither
    of which is the artifact that outlives the session.

    The density_source field is the load-bearing one. A density solved
    to meet a Reynolds number is deliberately not a point in any
    atmosphere, so a record without it gives a later reader no way to
    tell a wind-tunnel state from an altitude.
    """
    from pyflightstream.workspace import RunRecord

    for field in (
        "flight_condition",
        "density_kg_m3",
        "temperature_k",
        "viscosity_pa_s",
        "density_source",
        "reference_length_m",
    ):
        assert field in RunRecord.model_fields, (
            f"the run record carries no {field}, so the resolution it records "
            "cannot be recomputed by a reader"
        )

    workspace = make_library(tmp_path)
    with pytest.warns(UserWarning, match="wake_layers"):
        resolved = resolve_matrix(
            FIXTURE,
            workspace,
            name="matrix",
            fs_version="26.120",
            recipes=RECIPES,
            fs_exe="C:/fs/FlightStream.exe",
        )
    case = {sim.sim_id: sim for sim in resolved.campaign.sims}["9001"]
    condition = resolved.conditions["9001"]

    # THE NUMBER THE UPGRADE WARNING RESTS ON. Both the changelog and the
    # flight-condition page tell a user their results will move and quote
    # this density; until this assertion it was anchored by nothing.
    assert condition.density_kg_m3 == pytest.approx(1.3319, rel=1e-4)
    assert condition.density_kg_m3 / 1.225 == pytest.approx(1.087, rel=1e-3)

    # And the record's own fields are populated from that same state.
    assert case.fluid is not None
    assert case.fluid.density_kg_m3 == pytest.approx(condition.density_kg_m3)
    assert case.fluid.source == "solved-from-reynolds"
    assert case.flight_condition == {"MACH": 0.1441, "REmi": 4.38}
