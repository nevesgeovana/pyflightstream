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

from pyflightstream.cases.matrix import (
    DEFAULT_VERSION_OPTION,
    MatrixError,
    convert_matrix,
    read_matrix,
    to_campaign,
    upgrade_matrix,
)
from pyflightstream.run import Assessment, LocalExecutor, PlanStatus
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import helpers
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
        resolve_matrix(matrix, workspace, name="matrix", fs_version="26.120", recipes=RECIPES)


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
