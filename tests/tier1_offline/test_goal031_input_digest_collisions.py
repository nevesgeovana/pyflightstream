"""Tier 1: two different files the solver reads never share one key of ``inputs_sha256``.

The record keys every input the solver reads by its file name. The custom free
stream a row names (G15) is read where it lives, under the workspace's
``inputs/freestreams/``, and hashed under its name when the case is prepared;
the run then writes the data files the script parked for the solver, the
trailing-edge node file ``<geometry stem>.wake_nodes.txt`` (G02) and the
actuator disc's profile copy ``<profile stem>.actuator_profile.txt`` (G06), and
merged their digests into the same mapping by name. A free stream named like
either is a second, different file under one key: the generated file's digest
replaced the field's, so the record could not say which field the solver read,
and ``reconstruct()`` checked the generated file under that key and left the
field unverified.

What is held here, through ``run_matrix`` on a point and on a steady row run as
one job, and through ``run_campaign`` for a case built in Python:

1. such a row is refused before the solver is started, naming the key, the
   file the row declared and the file the run writes, and its record keeps the
   declared file's digest under the key;
2. the same bytes arriving twice under one key are one file's digest and not a
   collision: that run is not refused. The refusal compares digests, never
   names alone;
3. two names equal but for case, ``prop.txt`` and ``PROP.txt``, are one file on
   a case-insensitive file system (Windows), so different bytes under them are
   refused as under one name: by ``helpers.actuator_disc`` parking the second
   profile, and in any case by the run's writer before the solver starts. The
   test asserts the refusal, never an overwrite, so it holds on any file system.

Nothing here runs a solver.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.cases import Campaign, CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases import matrix as matrix_mod
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import CampaignErrors, _write_pending_files, run_campaign
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_g06_actuator_disc import AS_SAVED, REFERENCE_WITH_A_DISC
from tests.tier1_offline.test_g15_custom_freestream import SHEARED
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import (
    RECIPES,
    WRITES_EVERY_EXPORT,
    CountingStub,
    converged,
)
from tests.tier1_offline.test_raw_mesh_conditions import FILE_ROUTE, _library
from tests.tier1_offline.test_run_wake_edge_count import (
    LOG_AROUND,
    MIDPOINTS,
    STUB,
    StubSolver,
)

#: One point, and a steady row of two points, which runs as ONE job over one
#: script in the simulation folder. The steady job sweeps the advance ratio at
#: zero incidence, since a custom free stream is refused beside any other.
PATHS = pytest.mark.parametrize(
    ("condition", "values"),
    [
        ("MACH:0.2, REmi:2.3, ALPHA:sweep", "0.0"),
        ("MACH:0.2, REmi:2.3, ALPHA:0.0, ADVANCE_RATIO:sweep", "0.2,0.4"),
    ],
    ids=["one-point", "a-steady-job"],
)


def _one_row(tmp_path: Path, *, condition: str, values: str, cell: str) -> Path:
    """A steady row on the raw wing ``wing.stl``, on 26.124, the one build of the file route."""
    header = " | ".join(matrix_mod._COLUMNS)
    row = " | ".join(
        {
            "POL": "7001",
            "HIDDEN": "0",
            "RUN": "1",
            "AIRCRAFT": "Wing",
            "DESCRIPTION": "ONE_KEY_ONE_FILE",
            "FLIGHT_CONDITION": condition,
            "SWEEP_VALUES": values,
            "GEOMETRY": "wing.stl",
            "REF": "r003",
            "SET": "s002",
            "PPROC": "p001",
            "SYMMETRY": "NONE",
            "FS_BUILD": "26.124",
            "WORKFLOW": "steady",
            "VAR_NAMES_VALUES": cell,
        }.get(name, "-")
        for name in matrix_mod._COLUMNS
    )
    path = tmp_path / "one_key.fs"
    path.write_text(header + "\n" + "-" * 40 + "\n" + row + "\n", encoding="utf-8")
    return path


def _run(workspace: CampaignWorkspace, matrix: Path, build: str):
    """Run the matrix with a stand-in solver that counts every script it is started on."""
    stub = CountingStub(WRITES_EVERY_EXPORT)
    try:
        run_matrix(
            matrix,
            workspace,
            name="one_key",
            default_fs_version=build,
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=stub,
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    return record, stub


def _assert_refused_before_the_solver(record, stub, *, key: str, declared: Path, sim_dir: Path):
    assert stub.invocations == [], (
        f"the solver was started on {stub.invocations} with two different files under the "
        f"key {key!r} of inputs_sha256: the record kept {record.inputs_sha256.get(key)} "
        f"there, and the declared file {declared} hashes to {file_sha256(declared)}"
    )
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    for needle in (repr(key), str(declared), str(sim_dir), "inputs_sha256"):
        assert needle in (record.error or ""), f"the refusal does not name {needle}: {record.error}"
    assert record.inputs_sha256.get(key) == file_sha256(declared), record.inputs_sha256


@PATHS
def test_a_free_stream_named_like_the_trailing_edge_node_file_is_refused_before_the_solver(
    tmp_path, condition, values
):
    """G15 beside G02: ``FREESTREAM: wing.wake_nodes`` on the file-route wing ``wing.stl``.
    The solver would read two files named ``wing.wake_nodes.txt``, the field and the node
    file the run writes, and one key of the record cannot hold both digests."""
    workspace = _library(tmp_path, FILE_ROUTE)
    field = workspace.inputs_dir / "freestreams" / "wing.wake_nodes.txt"
    field.parent.mkdir(exist_ok=True)
    field.write_text(SHEARED, encoding="utf-8")
    matrix = _one_row(
        tmp_path, condition=condition, values=values, cell="FREESTREAM: wing.wake_nodes"
    )
    record, stub = _run(workspace, matrix, "26.124")
    _assert_refused_before_the_solver(
        record,
        stub,
        key="wing.wake_nodes.txt",
        declared=field.resolve(),
        sim_dir=workspace.sim_dir("7001"),
    )


@PATHS
def test_a_free_stream_named_like_the_disc_profile_copy_is_refused_before_the_solver(
    tmp_path, condition, values
):
    """G15 beside G06: ``FREESTREAM: prop_ct.actuator_profile`` on a row whose disc reads
    ``PROFILE: prop_ct``, whose run-owned copy is ``prop_ct.actuator_profile.txt``."""
    workspace, matrix = _matrix(
        tmp_path,
        condition=condition,
        values=values,
        cell=(
            "FREESTREAM: prop_ct.actuator_profile / ACTUATOR: PROP / ACTUATOR_RPM: 2400 "
            "/ PROFILE: prop_ct"
        ),
    )
    (workspace.inputs_dir / "references" / "r003.toml").write_text(
        REFERENCE_WITH_A_DISC, encoding="utf-8"
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(exist_ok=True)
    (profiles / "prop_ct.txt").write_bytes(AS_SAVED)
    field = workspace.inputs_dir / "freestreams" / "prop_ct.actuator_profile.txt"
    field.write_text(SHEARED, encoding="utf-8")
    record, stub = _run(workspace, matrix, "26.120")
    _assert_refused_before_the_solver(
        record,
        stub,
        key="prop_ct.actuator_profile.txt",
        declared=field.resolve(),
        sim_dir=workspace.sim_dir("3207"),
    )


# --- a case built in Python: the digests decide, never the names alone ----------------


def _node_file_recipe(case, script):
    """A steady point that writes its node file where it runs, under the field's name."""
    script.emit("OPEN", case.geometry)
    helpers.mark_wake_edges(
        script,
        edge_type="STANDARD",
        tolerance=0.0001,
        units="METER",
        node_file=str(Path(script.working_dir) / "wing.wake_nodes.txt"),
        midpoints=MIDPOINTS,
    )
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


def _run_in_python(tmp_path: Path, field_text: str):
    """Run one point of a Python case declaring ``field_text`` as its custom free stream."""
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    field = tmp_path / "freestreams" / "wing.wake_nodes.txt"
    field.parent.mkdir()
    # Written as the run writes a parked text file, so the same text is the same bytes.
    field.write_text(field_text, encoding="utf-8")
    case = SimCase(
        sim_id="9001",
        aircraft="TestWing",
        velocity=30.0,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="node_file",
        outputs=["loads_{point}.txt"],
        freestream_profile=str(field),
    )
    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp_path / "log_to_write.txt"
    log.write_text(
        LOG_AROUND.format(line="16 trailing edges imported for boundary Wing"),
        encoding="utf-8",
        newline="",
    )
    workspace = CampaignWorkspace(tmp_path / "camp")
    try:
        run_campaign(
            campaign,
            StubSolver(stub, log),
            workspace,
            assess=converged,
            recipes={"node_file": _node_file_recipe},
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    # The stand-in leaves this file where it runs, so its absence says it never started.
    started = any(workspace.sim_dir("9001").rglob("node_file_seen.txt"))
    return record, field, started


def test_a_python_case_whose_field_differs_from_a_generated_file_of_its_name_is_refused(
    tmp_path,
):
    record, field, started = _run_in_python(tmp_path, SHEARED)
    assert not started, "the solver was started with two different files under one key"
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert "'wing.wake_nodes.txt'" in (record.error or "") and str(field) in (record.error or "")
    assert record.inputs_sha256.get("wing.wake_nodes.txt") == file_sha256(field)


def test_the_same_bytes_twice_under_one_key_are_one_file_and_run(tmp_path):
    """The control: a field holding exactly the bytes the run writes under its name is one
    file's digest arriving twice, not two files, and the point runs."""
    record, field, started = _run_in_python(tmp_path, helpers.render_wake_edge_node_file(MIDPOINTS))
    assert started, "the point never reached the solver"
    assert record.status is RunStatus.CONVERGED, (record.status, record.error)
    assert record.inputs_sha256.get("wing.wake_nodes.txt") == file_sha256(field)


# --- one name but for case: one file on a case-insensitive file system ---------------

#: Two loadings of a disc, the second another rotor's: as rendered, so what the run
#: writes is exactly these bytes.
LOADING = "0.1,1.0\n0.5,2.0"
OTHER_LOADING = "0.1,5.0\n0.5,6.0"


def test_two_files_whose_names_differ_only_in_case_are_one_file_and_refused(tmp_path):
    """A Python recipe calling ``actuator_disc(profile_text=...)`` twice, on ``prop.txt`` and
    ``PROP.txt`` with different loadings. On Windows the second write replaces the first, so
    both discs read the second loading while ``inputs_sha256['prop.txt']`` records the first.
    Refused where the second profile is parked, and in any case by the run's writer; the
    same bytes under both names stay accepted, under the keys the script named."""
    work = tmp_path / "DP-point"
    lower, upper = str(work / "prop.txt"), str(work / "PROP.txt")
    disc = {"frame": 2, "axis": "X", "offset": 0.0, "r_tip": 0.5, "r_hub": 0.1, "rpm": 2400.0}
    script = Script("26.124")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    helpers.actuator_disc(script, "PROP", **disc, profile=lower, n_blades=3, profile_text=LOADING)
    before = script.render()

    # The helper parking the second profile sees the first.
    with pytest.raises(CommandArgumentError, match=r"already writes a different file.*case"):
        helpers.actuator_disc(
            script, "FAN", **disc, profile=upper, n_blades=3, profile_text=OTHER_LOADING
        )
    assert script.render() == before, "the refused disc left lines in the script"
    assert script.pending_input_files == {lower: LOADING.encode()}, script.pending_input_files

    # The run's writer refuses them however they were parked (here past the helper), before
    # the solver starts: a declared input and a written file, then two written files.
    field = tmp_path / "freestreams" / "PROP.txt"
    field.parent.mkdir()
    field.write_text(SHEARED, encoding="utf-8")
    case = SimCase(
        sim_id="9002",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="discs",
        outputs=["loads_{point}.txt"],
        freestream_profile=str(field),
    )
    with pytest.raises(CampaignConfigError, match=r"'PROP\.txt', the same name but for case"):
        _write_pending_files(script, work, case=case, recorded={"PROP.txt": file_sha256(field)})
    script._pending_input_files[upper] = OTHER_LOADING.encode()
    with pytest.raises(CampaignConfigError) as refused:
        _write_pending_files(script, work, case=case, recorded={})
    message = str(refused.value)
    for needle in (lower, upper, "'9002'", "inputs_sha256", "the solver was not started"):
        assert needle in message, f"the refusal does not name {needle}: {message}"

    # THE CONTROL: the same bytes under both spellings are one file's content, and run.
    same = Script("26.124")
    same.emit("CREATE_NEW_COORDINATE_SYSTEM")
    for name, path in (("PROP", lower), ("FAN", upper)):
        helpers.actuator_disc(same, name, **disc, profile=path, n_blades=3, profile_text=LOADING)
    digest = _write_pending_files(same, work, case=case, recorded={})
    assert digest == dict.fromkeys(("prop.txt", "PROP.txt"), file_sha256(work / "prop.txt"))


def test_a_node_file_named_like_a_parked_one_but_for_case_is_refused_by_the_helper(tmp_path):
    """``mark_wake_edges`` holds its node file to the rule ``actuator_disc`` holds a
    profile to: a path equal to a parked one but for case is the same file on a
    case-insensitive file system, so different points under it are refused where the
    second file is parked, and the same points under both spellings are accepted."""
    script = Script("26.124")
    common = {"edge_type": "STANDARD", "tolerance": 0.0001, "units": "METER"}
    lower, upper = str(tmp_path / "wing.txt"), str(tmp_path / "WING.txt")
    helpers.mark_wake_edges(script, **common, node_file=lower, midpoints=MIDPOINTS)
    before = script.render()
    moved = [(x + 0.25, y, z) for x, y, z in MIDPOINTS]
    with pytest.raises(CommandArgumentError, match=r"only in case"):
        helpers.mark_wake_edges(script, **common, node_file=upper, midpoints=moved)
    assert script.render() == before, "the refused import left lines in the script"
    helpers.mark_wake_edges(script, **common, node_file=upper, midpoints=MIDPOINTS)


def test_a_declared_log_is_read_whatever_the_case_of_its_name(tmp_path):
    """A log the script names ``RunLog.txt`` and a row collects as ``runlog.txt`` is one
    file on a case-insensitive file system, so its text is read for the refusal lines; a
    collected output named nowhere as a log is not."""
    from pyflightstream.run._wake_edge_verdict import collected_log_texts

    (tmp_path / "runlog.txt").write_text("the log", encoding="utf-8")
    (tmp_path / "loads.txt").write_text("the loads", encoding="utf-8")
    collected = ["runlog.txt", "loads.txt"]
    assert collected_log_texts(tmp_path, collected, declared=["RunLog.txt"]) == ["the log"]
    assert collected_log_texts(tmp_path, collected, declared=[]) == []


def test_two_action_scripts_whose_names_differ_only_in_case_are_refused(tmp_path):
    """``actions/step.txt`` setting the incidence and ``actions/STEP.txt`` exporting the
    loads are one file on a case-insensitive file system: both actions would run the
    export and the incidence command would be lost. The helper refuses the second where
    it is registered, and the run's writer refuses them however they were parked,
    before it writes any file; the same text under both spellings is one file."""
    script = Script("26.124")
    helpers.unsteady_action(
        script,
        name="incidence",
        kind="SCRIPT",
        filename="actions/step.txt",
        action_script="SOLVER_SET_AOA 2.0",
    )
    before = script.render()
    with pytest.raises(CommandArgumentError, match=r"only in case"):
        helpers.unsteady_action(
            script,
            name="loads",
            kind="SCRIPT",
            filename="actions/STEP.txt",
            action_script="EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        )
    assert script.render() == before, "the refused action left lines in the script"

    script._pending_action_scripts["actions/STEP.txt"] = "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    case = SimCase(
        sim_id="9003",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    work = tmp_path / "DP-point"
    with pytest.raises(CampaignConfigError, match=r"case-insensitive"):
        _write_pending_files(script, work, case=case, recorded={})
    assert not work.exists() or not any(work.rglob("*")), "a file was written before the refusal"


def test_the_solvers_own_log_is_read_on_a_job_that_declared_no_log(tmp_path):
    """A job submitted before the declared logs were recorded, whose LEGACY recipe named
    the solver's own ``FlightStreamLog.txt`` through LOG_OUTPUT alone, with no EXPORT_LOG:
    the file is the solver's own log by its name, so it is read for the refusal lines
    whatever was declared, in any case."""
    from pyflightstream.run._wake_edge_verdict import collected_log_texts

    (tmp_path / "flightstreamlog.txt").write_text("the log", encoding="utf-8")
    (tmp_path / "loads.txt").write_text("the loads", encoding="utf-8")
    collected = ["flightstreamlog.txt", "loads.txt"]
    assert collected_log_texts(tmp_path, collected, declared=[]) == ["the log"]


def test_one_file_spelled_through_a_parent_folder_is_one_file(tmp_path):
    """``step.txt`` and ``sub/../STEP.txt`` are one file wherever the path is resolved:
    the helper refuses the second action where it is registered, and the run's writer
    refuses such a pair however it was parked, before it writes any file."""
    script = Script("26.124")
    helpers.unsteady_action(
        script,
        name="incidence",
        kind="SCRIPT",
        filename="actions/step.txt",
        action_script="SOLVER_SET_AOA 2.0",
    )
    with pytest.raises(CommandArgumentError, match=r"one file"):
        helpers.unsteady_action(
            script,
            name="loads",
            kind="SCRIPT",
            filename="actions/sub/../STEP.txt",
            action_script="EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        )
    script._pending_action_scripts["actions/sub/../STEP.txt"] = "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    case = SimCase(
        sim_id="9004",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    work = tmp_path / "DP-point"
    with pytest.raises(CampaignConfigError, match=r"one file"):
        _write_pending_files(script, work, case=case, recorded={})
    assert not work.exists() or not any(work.rglob("*")), "a file was written before the refusal"


def test_a_parked_file_on_a_path_the_run_writes_itself_is_refused(tmp_path):
    """The counter and clock programs, and the state files the run removes, are written
    after the parked files: a data file parked on one of those paths would be replaced or
    deleted after its digest was recorded. Refused before any file is written."""
    from pyflightstream.cases.workflows import UNSTEADY_ACTION_PROGRAM

    script = Script("26.124")
    script._pending_input_files[UNSTEADY_ACTION_PROGRAM.upper()] = b"not the program"
    case = SimCase(
        sim_id="9005",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    work = tmp_path / "DP-point"
    with pytest.raises(CampaignConfigError, match=r"the run writes .* itself"):
        _write_pending_files(script, work, case=case, recorded={})
    assert not work.exists() or not any(work.rglob("*")), "a file was written before the refusal"
