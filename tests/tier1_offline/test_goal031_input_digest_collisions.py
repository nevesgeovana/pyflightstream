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
    """A log the script names ``RunLog.OUT`` and a row collects as ``runlog.out`` is one
    file on a case-insensitive file system, so its text is read for the refusal lines
    although its suffix is no text suffix; every collected text output is read whatever
    its name, and an output that is neither declared nor text is not."""
    from pyflightstream.run._wake_edge_verdict import collected_log_texts

    (tmp_path / "runlog.out").write_text("the log", encoding="utf-8")
    (tmp_path / "table.csv").write_text("the table", encoding="utf-8")
    (tmp_path / "loads.txt").write_text("the loads", encoding="utf-8")
    collected = ["runlog.out", "table.csv", "loads.txt"]
    assert collected_log_texts(tmp_path, collected, declared=["RunLog.OUT"]) == [
        "the log",
        "the loads",
    ]
    assert collected_log_texts(tmp_path, collected, declared=[]) == ["the loads"]


def test_a_log_a_child_action_exported_is_read_for_the_refusal_lines(tmp_path):
    """A SCRIPT action exports the log each step under a name the main script never
    states, and the solver appends ``_iteration=<step>``: the collected step files carry
    the refusal line and are read, because every collected text output is."""
    from pyflightstream.run._wake_edge_verdict import (
        ACTUATOR_PROFILE_REFUSALS,
        actuator_profile_verdict,
        collected_log_texts,
    )

    refusal = ACTUATOR_PROFILE_REFUSALS[1] + "\nC:/w/prop.txt\n"
    for step in (11, 12):
        (tmp_path / f"step-transcript_iteration={step}.txt").write_text(refusal, encoding="utf-8")
    collected = ["step-transcript_iteration=11.txt", "step-transcript_iteration=12.txt"]
    texts = collected_log_texts(tmp_path, collected, declared=[])
    assert len(texts) == 2, texts
    assert actuator_profile_verdict(*texts) is not None


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
    assert "the log" in collected_log_texts(tmp_path, collected, declared=[])


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


def test_a_parked_file_on_the_main_script_s_path_is_refused(tmp_path):
    """The main script is written and hashed before the parked files: an action parked on
    its path would replace it, so the solver would run other commands than the record's
    ``script_sha256`` names. It is a file the run writes itself, and refused as one."""
    sim_dir = tmp_path / "sims" / "sim_9006"
    main = sim_dir / "scripts" / "P9006-AL+000.txt"
    main.parent.mkdir(parents=True)
    main.write_text("the main script", encoding="utf-8")
    script = Script("26.124")
    script._pending_action_scripts[str(main)] = "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    case = SimCase(
        sim_id="9006",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(
        CampaignConfigError, match=r"the run writes .* itself|other points name the files"
    ):
        _write_pending_files(
            script, sim_dir / "DP-point", case=case, recorded={}, run_writes=(main,)
        )
    assert main.read_text(encoding="utf-8") == "the main script"


def test_the_submission_descriptor_is_a_file_the_run_writes_itself(tmp_path):
    """A submitting executor writes its descriptor into the point's folder when it
    submits, after the parked files; the descriptor's path is reserved like the main
    script's, and an executor with no profile reserves nothing."""
    from types import SimpleNamespace

    from pyflightstream.run import _descriptor_of

    submitting = SimpleNamespace(profile=SimpleNamespace(descriptor_name="job.sh"))
    assert _descriptor_of(submitting, tmp_path) == [tmp_path / "job.sh"]
    assert _descriptor_of(object(), tmp_path) == []
    script = Script("26.124")
    script._pending_input_files["JOB.SH"] = b"not the descriptor"
    case = SimCase(
        sim_id="9007",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(CampaignConfigError, match=r"the run writes .* itself"):
        _write_pending_files(
            script,
            tmp_path,
            case=case,
            recorded={},
            run_writes=_descriptor_of(submitting, tmp_path),
        )


@pytest.mark.parametrize("values", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_both_run_paths_reserve_the_script_they_wrote(tmp_path, monkeypatch, values):
    """The point path and the steady job path hand the writer the main script they
    wrote and hashed, so a file parked on it is refused on either path; a call site
    that stops passing it would leave the check above unreached."""
    import pyflightstream.run as run_module
    from tests.tier1_offline.test_g06_actuator_disc import _run_a_profile_row

    seen = []
    real = run_module._write_pending_files

    def spy(*args, **kwargs):
        seen.append(tuple(Path(p).as_posix() for p in kwargs.get("run_writes", ())))
        return real(*args, **kwargs)

    monkeypatch.setattr(run_module, "_write_pending_files", spy)
    record, _profile, _line = _run_a_profile_row(tmp_path, values=values, refused=False)
    assert seen, "the writer was not called"
    assert any(p.endswith(record.script_path) for p in seen[0]), (seen, record.script_path)


@pytest.mark.parametrize("kind", ["action", "data"])
def test_a_file_parked_on_a_hashed_input_is_refused_before_it_is_written(tmp_path, kind):
    """A recipe parks a file on the path of the staged geometry, which the record already
    hashed and which may be the geometry library itself through the inputs junction: the
    writer refuses before a byte is written, so the input keeps its bytes; the same bytes
    parked there are one file and accepted."""
    geometry = tmp_path / "sims" / "sim_9008" / "inputs" / "wing.obj"
    geometry.parent.mkdir(parents=True)
    geometry.write_bytes(b"v 0 0 0\n")
    script = Script("26.124")
    if kind == "action":
        script._pending_action_scripts[str(geometry)] = "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    else:
        script._pending_input_files[str(geometry)] = b"not the geometry"
    case = SimCase(
        sim_id="9008",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    recorded = {"wing.obj": file_sha256(geometry)}
    with pytest.raises(CampaignConfigError, match=r"already hashed|folder the point runs in"):
        _write_pending_files(script, tmp_path / "DP-point", case=case, recorded=recorded)
    assert geometry.read_bytes() == b"v 0 0 0\n", "the input was overwritten before the refusal"

    same = Script("26.124")
    same._pending_action_scripts[str(geometry)] = "v 0 0 0\n"
    _write_pending_files(same, tmp_path / "DP-point", case=case, recorded=recorded)
    assert geometry.read_bytes() == b"v 0 0 0\n"


@pytest.mark.parametrize("refused", [True, False], ids=["refused", "control"])
def test_collection_reads_the_solvers_own_log_where_the_job_ran(tmp_path, refused):
    """A submitted point that declared its loads only: the solver still wrote its own
    ``FlightStreamLog.txt`` in the folder the job ran in, and a refusal line there
    overrides a CONVERGED assessment on collection."""
    from pyflightstream.run._wake_edge_verdict import ACTUATOR_PROFILE_REFUSALS
    from pyflightstream.run.collect import _log_verdicts
    from pyflightstream.workspace import RunRecord

    sim_dir = tmp_path / "sims" / "sim_9009"
    work = sim_dir / "datapoints" / "DP-AL+000"
    work.mkdir(parents=True)
    (work / "loads.txt").write_text("the loads", encoding="utf-8")
    line = ACTUATOR_PROFILE_REFUSALS[1] if refused else "Solver finished"
    (work / "FlightStreamLog.txt").write_text(line + "\nC:/w/prop.txt\n", encoding="utf-8")
    record = RunRecord.model_construct(
        run_id="camp/sim_9009/AL+000",
        sim_id="9009",
        submission={},
        script_path=None,
        cwd=str(work),
    )
    status, verdict = _log_verdicts(
        record, sim_dir, ["datapoints/DP-AL+000/loads.txt"], None, RunStatus.CONVERGED, None
    )
    if refused:
        assert status is RunStatus.FAILED_SCRIPT, (status, verdict)
    else:
        assert status is RunStatus.CONVERGED, (status, verdict)


def test_a_parked_file_equal_to_a_hashed_input_leaves_it_untouched(tmp_path):
    """The same bytes parked on a hashed input are the same file, and the writer leaves
    the input as it is: an action script is written in text mode, and on Windows a
    rewrite would turn the input's LF into CRLF under the digest the record keeps."""
    geometry = tmp_path / "sims" / "sim_9010" / "inputs" / "wing.obj"
    geometry.parent.mkdir(parents=True)
    geometry.write_bytes(b"v 0 0 0\nv 1 0 0\n")
    script = Script("26.124")
    script._pending_action_scripts[str(geometry)] = "v 0 0 0\nv 1 0 0\n"
    case = SimCase(
        sim_id="9010",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    recorded = {"wing.obj": file_sha256(geometry)}
    _write_pending_files(script, tmp_path / "DP-point", case=case, recorded=recorded)
    assert geometry.read_bytes() == b"v 0 0 0\nv 1 0 0\n"
    assert file_sha256(geometry) == recorded["wing.obj"]


def test_a_data_file_the_run_writes_is_the_points_own(tmp_path):
    """Two submitted points whose recipe parks one shared absolute profile with its own
    loading each: the second submission rewrote the file the first job had not read
    yet, under the first record's digest. A data file the run writes and hashes is the
    point's own and is written in the folder the point runs in; one parked anywhere
    else is refused before anything is written."""
    shared = tmp_path / "shared" / "prop.txt"
    script = Script("26.124")
    script._pending_input_files[str(shared)] = b"0.5,1.0\n1.0,0.0"
    case = SimCase(
        sim_id="9011",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="discs",
        outputs=["loads_{point}.txt"],
    )
    work = tmp_path / "sims" / "sim_9011" / "datapoints" / "DP-AL+000"
    with pytest.raises(CampaignConfigError, match=r"folder the point runs in"):
        _write_pending_files(script, work, case=case, recorded={})
    assert not shared.exists(), "the shared file was written before the refusal"

    inside = Script("26.124")
    inside._pending_input_files["prop.txt"] = b"0.5,1.0\n1.0,0.0"
    assert set(_write_pending_files(inside, work, case=case, recorded={})) == {"prop.txt"}


def test_collection_reads_the_solvers_log_in_a_moved_workspace(tmp_path):
    """A workspace moved after submission: the record's cwd names the old place, and the
    solver's own log sits in the datapoint folder the submission names relative to the
    simulation; collection reads it there."""
    from pyflightstream.run._wake_edge_verdict import ACTUATOR_PROFILE_REFUSALS
    from pyflightstream.run.collect import _log_verdicts
    from pyflightstream.workspace import RunRecord

    sim_dir = tmp_path / "moved" / "sims" / "sim_9012"
    work = sim_dir / "datapoints" / "DP-AL+000"
    work.mkdir(parents=True)
    (work / "loads.txt").write_text("the loads", encoding="utf-8")
    (work / "FlightStreamLog.txt").write_text(
        ACTUATOR_PROFILE_REFUSALS[1] + "\nC:/w/prop.txt\n", encoding="utf-8"
    )
    record = RunRecord.model_construct(
        run_id="camp/sim_9012/AL+000",
        sim_id="9012",
        script_path=None,
        submission={"working_dir": "datapoints/DP-AL+000"},
        cwd=str(tmp_path / "where-it-was" / "sims" / "sim_9012" / "datapoints" / "DP-AL+000"),
    )
    status, verdict = _log_verdicts(
        record, sim_dir, ["datapoints/DP-AL+000/loads.txt"], None, RunStatus.CONVERGED, None
    )
    assert status is RunStatus.FAILED_SCRIPT, (status, verdict)


def test_a_descriptor_named_like_a_program_the_run_writes_is_refused(tmp_path):
    """A machine profile whose descriptor name is the wall-clock program's path: the
    descriptor, written at submission, would replace the program the record hashed.
    The run's own files are checked against one another before anything is written."""
    from types import SimpleNamespace

    from pyflightstream.cases.workflows import WALLTIME_CLOCK_PROGRAM
    from pyflightstream.run import _descriptor_of

    submitting = SimpleNamespace(profile=SimpleNamespace(descriptor_name=WALLTIME_CLOCK_PROGRAM))
    case = SimCase(
        sim_id="9013",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(CampaignConfigError, match=r"descriptor|writes .* itself"):
        _write_pending_files(
            Script("26.124"),
            tmp_path,
            case=case,
            recorded={},
            run_writes=_descriptor_of(submitting, tmp_path),
        )


def test_two_run_written_files_on_one_path_are_refused_whatever_their_spelling(tmp_path):
    """A machine profile whose descriptor name is the steady job's main script: the two
    files the run writes are one path spelled the same way, and the descriptor would
    replace the script the record hashed. Refused before anything is written."""
    main = tmp_path / "scripts" / "P9014-AL+sweep.txt"
    case = SimCase(
        sim_id="9014",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(CampaignConfigError, match=r"written by the run for two things"):
        _write_pending_files(
            Script("26.124"), tmp_path, case=case, recorded={}, run_writes=(main, main)
        )


def test_a_collected_output_of_any_text_kind_is_read_for_the_refusal_lines(tmp_path):
    """A child action exports the log each step as ``step.out``, which the solver files as
    ``step_iteration=11.out``: every collected output that is not a binary kind is read
    for the four sentences, streamed, whatever its suffix; a binary kind is not read."""
    from pyflightstream.run._wake_edge_verdict import (
        ACTUATOR_PROFILE_REFUSALS,
        actuator_profile_verdict,
        collected_log_texts,
    )

    refusal = ACTUATOR_PROFILE_REFUSALS[1] + "\nC:/w/prop.txt\n"
    (tmp_path / "step_iteration=11.out").write_text("line\n" + refusal, encoding="utf-8")
    (tmp_path / "point.fsm").write_text(refusal, encoding="utf-8")
    texts = collected_log_texts(tmp_path, ["step_iteration=11.out"], declared=[])
    assert actuator_profile_verdict(*texts) is not None, texts
    assert collected_log_texts(tmp_path, ["point.fsm"], declared=[]) == []


def test_windows_name_aliases_are_one_file_or_refused(tmp_path):
    """``prop.txt.`` is ``prop.txt`` on Windows, which drops a trailing dot or space;
    ``PROP~1.TXT`` has an 8.3 short name's form and ``prop.txt:x`` names a stream. The
    helpers see the first as the parked file, and the writer refuses every such name
    before anything is written."""
    from pyflightstream._digest import aliased_name_fault, one_file_key

    assert one_file_key(tmp_path / "prop.txt") == one_file_key(tmp_path / "PROP.txt.")
    assert one_file_key(tmp_path / "prop.txt") == one_file_key(tmp_path / "prop.txt ")
    assert one_file_key(tmp_path / "prop.txt") != one_file_key(tmp_path / "prop.txt.bak")
    for name in ("prop.txt.", "prop.txt ", "PROP~1.TXT", "prop.txt:x"):
        assert aliased_name_fault(name), name
    assert aliased_name_fault("prop.txt") is None

    disc = {"frame": 2, "axis": "X", "offset": 0.0, "r_tip": 0.5, "r_hub": 0.1, "rpm": 2400.0}
    script = Script("26.124")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    helpers.actuator_disc(
        script,
        "PROP",
        **disc,
        profile=str(tmp_path / "prop.txt"),
        n_blades=3,
        profile_text=LOADING,
    )
    with pytest.raises(CommandArgumentError, match=r"already writes a different file"):
        helpers.actuator_disc(
            script,
            "FAN",
            **disc,
            profile=str(tmp_path / "prop.txt."),
            n_blades=3,
            profile_text=OTHER_LOADING,
        )

    case = SimCase(
        sim_id="9015",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="discs",
        outputs=["loads_{point}.txt"],
    )
    for name in ("prop.txt.", "PROP~1.TXT"):
        parked = Script("26.124")
        parked._pending_input_files[name] = b"0.5,1.0\n1.0,0.0"
        with pytest.raises(CampaignConfigError, match=r"Name it plainly"):
            _write_pending_files(parked, tmp_path / "DP-point", case=case, recorded={})
    assert not (tmp_path / "DP-point").exists() or not any((tmp_path / "DP-point").rglob("*"))


def test_a_descriptor_name_windows_reads_as_an_alias_is_refused(tmp_path):
    """A machine profile's descriptor named ``actions/pfs_walltime_clock.py::$DATA`` is
    the clock program's own data stream on Windows; the caller's files pass the same
    alias check as a parked one."""
    from types import SimpleNamespace

    from pyflightstream.run import _descriptor_of

    submitting = SimpleNamespace(
        profile=SimpleNamespace(descriptor_name="actions/pfs_walltime_clock.py::$DATA")
    )
    case = SimCase(
        sim_id="9016",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(CampaignConfigError, match=r"Name it plainly"):
        _write_pending_files(
            Script("26.124"),
            tmp_path,
            case=case,
            recorded={},
            run_writes=_descriptor_of(submitting, tmp_path),
        )


def test_a_data_file_parked_through_a_link_leading_outside_the_point_is_refused(tmp_path):
    """A junction (or a symbolic link) inside the point's folder that leads to a folder
    several points share: the file parked through it is outside the point, and refused."""
    shared = tmp_path / "shared"
    shared.mkdir()
    work = tmp_path / "sims" / "sim_9017" / "datapoints" / "DP-AL+000"
    work.mkdir(parents=True)
    link = work / "shared"
    try:
        import _winapi

        _winapi.CreateJunction(str(shared), str(link))
    except (ImportError, OSError):
        try:
            link.symlink_to(shared, target_is_directory=True)
        except OSError:
            pytest.skip("this machine can make neither a junction nor a symbolic link")
    script = Script("26.124")
    script._pending_input_files["shared/prop.txt"] = b"0.5,1.0\n1.0,0.0"
    case = SimCase(
        sim_id="9017",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="discs",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(CampaignConfigError, match=r"folder the point runs in"):
        _write_pending_files(script, work, case=case, recorded={})
    assert not (shared / "prop.txt").exists(), "the shared file was written before the refusal"


@pytest.mark.parametrize("where", ["scripts", "another-point"])
def test_nothing_parked_lands_where_other_points_records_point(tmp_path, where):
    """Point B's recipe parks an action on point A's hashed main script, or in A's
    datapoint folder, in the same campaign invocation: A is queued and has not read
    them yet. Refused before anything is written; a path under the simulation's own
    folder that is neither, where the tier-3 re-read probe parks its action, is not."""
    sim = tmp_path / "camp" / "sims" / "sim_9018"
    main_a = sim / "scripts" / "P9018-AL+000.txt"
    main_a.parent.mkdir(parents=True)
    main_a.write_text("A's script", encoding="utf-8")
    work_b = sim / "datapoints" / "DP-AL+020"
    work_b.mkdir(parents=True)
    target = main_a if where == "scripts" else sim / "datapoints" / "DP-AL+000" / "step.txt"
    script = Script("26.124")
    script._pending_action_scripts[str(target)] = "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"
    case = SimCase(
        sim_id="9018",
        aircraft="TestWing",
        velocity=30.0,
        sweep=SweepAxis(type="alpha", values=[2.0]),
        recipe="actions",
        outputs=["loads_{point}.txt"],
    )
    with pytest.raises(CampaignConfigError, match=r"other points name the files"):
        _write_pending_files(script, work_b, case=case, recorded={})
    assert main_a.read_text(encoding="utf-8") == "A's script"

    probe = Script("26.124")
    probe._pending_action_scripts[str(sim / "actions" / "reread.txt")] = "EXPORT_LOG"
    _write_pending_files(probe, work_b, case=case, recorded={})
    assert (sim / "actions" / "reread.txt").is_file()
