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
from pathlib import Path

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
from pyflightstream.workspace.matrix import resolve_matrix

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
