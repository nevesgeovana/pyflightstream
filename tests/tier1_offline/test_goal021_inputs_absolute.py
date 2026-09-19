"""PFS-2010.01.02, the assumption it rests on: a point's script names its inputs absolutely.

A submitted point of a swept row is to run in its own datapoint folder,
``sims/sim_<id>/datapoints/DP-<tag>/``, one level below the simulation folder
every point runs in today. ``sims/<sim>/inputs`` is a link AT THE SIMULATION
LEVEL. So the move is safe only if every file the solver READS is named by an
absolute path: a path relative to the simulation folder resolves against the
solver's working directory, and the moment that directory is one level deeper
the job opens nothing, inside a queue nobody is watching.

WHAT IS AND IS NOT AN INPUT. The exports a point writes and the action files it
registers are named relative to the working directory ON PURPOSE: they are
written into that directory and follow it. What must not follow it is a file
that already exists before the solver starts: the geometry it opens, a probe
survey it imports, the saved simulation a continuation reopens.

Every test drives ``run_matrix`` through a submitting executor that writes its
descriptor and calls no scheduler, and reads the SCRIPT that was written,
because the script is what the job runs.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import SubmittingExecutor
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_matrix_run import (
    FIXTURES,
    HPC_PROFILE,
    converged,
    make_library,
    stage_geometry,
)

BUILD = "26.123"

#: The verbs whose file argument the solver READS, and how many lines below
#: the verb that argument sits. `PROBE_POINTS_IMPORT` is `param_lines`: the
#: name, then UNITS, FRAME and the path.
READS = {"OPEN": 1, "PROBE_POINTS_IMPORT": 3}


def _rotor_row(tmp_path, *, sweep="0.0,2.0,4.0", extra=""):
    header, rule, row, *_ = (
        (FIXTURES / "workflow_rotor_matrix.fs").read_text(encoding="utf-8").splitlines()
    )
    for before, after in (
        ("| 0.0            |", f"| {sweep:<14} |"),
        ("| -        | r003", "| wing_clean.fsm | r003"),
        ("| -     | -        | 26.120", f"| 8     | 1h       | {BUILD}"),
        ("WINDOW_DEGREES: 90", "WINDOW_DEGREES: 90" + extra),
    ):
        assert before in row, (before, row)
        row = row.replace(before, after)
    matrix = tmp_path / "rotor.fs"
    matrix.write_text("\n".join((header, rule, row)) + "\n", encoding="utf-8")
    return matrix


def _workspace(tmp_path):
    workspace = make_library(tmp_path, register_build=(BUILD, "C:/fs/FS.exe"))
    stage_geometry(workspace, "wing_clean.fsm")
    return workspace


def _run(workspace, matrix, *, name="rotor"):
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(HPC_PROFILE, encoding="utf-8")
    executor = SubmittingExecutor(
        read_hpc_profile(profile), values={"fs_build": BUILD}, submit=False
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        try:
            run_matrix(
                matrix,
                workspace,
                name=name,
                recipes={},
                recipe_registry=workflow_registry(),
                assess=converged,
                executor=executor,
            )
        except Exception:  # noqa: BLE001 -- the subject is the script, written either way
            pass


class NothingMeasuredError(Exception):
    """The fixture did not reach the path it claims to measure.

    DELIBERATELY NOT AN AssertionError. While the two inputs were measured
    relative, their tests were xfails accepting AssertionError alone, and this
    kept a probe that measured nothing from passing for the known defect. The
    inputs are absolute since 0.18.1 and the xfails are gone; the distinction
    stays, because a failure that means "nothing was measured" should never
    read as the path assertion failing.
    """


def _read_paths(script: Path) -> list[tuple[str, str]]:
    lines = script.read_text(encoding="utf-8").splitlines()
    found = []
    for index, line in enumerate(lines):
        offset = READS.get(line.split(" ")[0])
        if offset is not None and index + offset < len(lines):
            found.append((line.split(" ")[0], lines[index + offset].strip().strip('"')))
    return found


def _point_scripts(workspace) -> list[Path]:
    scripts = sorted((workspace.sim_dir("7001") / "scripts").glob("*.txt"))
    if not scripts:
        raise NothingMeasuredError("no point script was written, so nothing was measured")
    return scripts


def _relative(workspace) -> list[str]:
    offenders = []
    for script in _point_scripts(workspace):
        read = _read_paths(script)
        if not read:
            raise NothingMeasuredError(
                f"{script.name} names no file it reads, so nothing was measured"
            )
        offenders += [
            f"{script.name}: {verb} {path}" for verb, path in read if not Path(path).is_absolute()
        ]
    return offenders


def test_goal021_inputs_absolute_the_geometry_a_point_opens(tmp_path):
    """The geometry is opened through the link, by an absolute path."""
    workspace = _workspace(tmp_path)
    _run(workspace, _rotor_row(tmp_path))
    opened = [
        path
        for script in _point_scripts(workspace)
        for verb, path in _read_paths(script)
        if verb == "OPEN"
    ]
    if not opened:
        raise NothingMeasuredError("no OPEN was emitted, so nothing was measured")
    assert _relative(workspace) == [], _relative(workspace)


def test_goal021_inputs_absolute_a_probe_survey_the_user_cited(tmp_path):
    """FR-80: a `[[probes]]` entry citing a points file leaves no relative path in a script.

    SINCE 0.25.0 (F01) THIS ROTOR ROW READS THE SURVEY ITSELF, at plan, and
    samples each point through a fluid plot; it imports nothing, so no path to
    the survey reaches the script at all. The import by absolute path is held on
    a steady row by test_workflows.py.
    """
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n\n'
        "[[probes]]\n"
        'frame = "MRP"\n'
        'parameters = ["VELOCITY"]\n'
        'points_file = "disk_survey.txt"\n',
        encoding="utf-8",
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    # The import file format of the manual (SRC-003 p.362): the count, then
    # X,Y,Z,TYPE. The one-line placeholder this held was never read before F01.
    (profiles / "disk_survey.txt").write_text("1\n0.0,0.0,0.0,1\n", encoding="utf-8")
    _run(workspace, _rotor_row(tmp_path))
    text = "\n".join(s.read_text(encoding="utf-8") for s in _point_scripts(workspace))
    if "UNSTEADY_SOLVER_NEW_FLUID_PLOT" not in text:
        raise NothingMeasuredError(
            "no fluid plot was emitted, so the cited survey was not measured"
        )
    assert "PROBE_POINTS_IMPORT" not in text, "an unsteady row imports no survey (F01)"
    assert _relative(workspace) == [], _relative(workspace)


def test_goal021_inputs_absolute_the_saved_simulation_a_continuation_reopens(tmp_path):
    """FR-96: RESTART reopens the stopped run's saved simulation by an absolute path."""
    workspace = _workspace(tmp_path)
    saved = workspace.sim_dir("7001") / "datapoints" / "DP-V0300RE120AL+000"
    saved.mkdir(parents=True, exist_ok=True)
    (saved / "V0300RE120AL+000.fsm").write_text("a stopped march", encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="rotor/sim_7001/V0300RE120AL+000",
            sim_id="7001",
            point={"alpha": 0.0},
            status=RunStatus.WALLTIME_REACHED,
            matrix_stem="rotor",
            fs_version_requested=BUILD,
            package_version="0.18.0",
            script_sha256="c" * 64,
            raw_flag=False,
            outputs=["datapoints/DP-V0300RE120AL+000/V0300RE120AL+000.fsm"],
            export_window={"time_iterations": 720},
            stopped_at={"step": 250},
        )
    )
    # UNDER THE CAMPAIGN THAT RECORDED THE STOPPED POINT, which is the case
    # 0.18.0 could not run: the row was refused as a fork (GOAL-021, the
    # owner's call of 2026-09-14).
    _run(
        workspace,
        _rotor_row(tmp_path, sweep="0.0", extra=" / RESTART: {FINISH_PENDING}"),
    )
    opened = [
        path
        for script in _point_scripts(workspace)
        for verb, path in _read_paths(script)
        if verb == "OPEN" and path.endswith(".fsm") and "V0300RE120AL+000" in path
    ]
    if not opened:
        raise NothingMeasuredError(
            "no script reopened the saved simulation, so the continuation was not measured: "
            + ", ".join(s.name for s in _point_scripts(workspace))
        )
    assert _relative(workspace) == [], _relative(workspace)


def test_goal021_inputs_absolute_a_survey_the_profiles_folder_does_not_hold_is_refused(tmp_path):
    """FR-80 promised this refusal at plan time, and nothing performed it until 0.18.1."""
    import pytest

    from pyflightstream.exceptions import InputArtifactError

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n\n'
        "[[probes]]\n"
        'frame = "MRP"\n'
        'parameters = ["VELOCITY"]\n'
        'points_file = "missing_survey.txt"\n',
        encoding="utf-8",
    )
    profiles = workspace.inputs_dir / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "disk_survey.txt").write_text("0.0 0.0 0.0\n", encoding="utf-8")
    from pyflightstream.workspace.matrix import resolve_matrix

    with pytest.raises(InputArtifactError) as raised:
        resolve_matrix(_rotor_row(tmp_path), workspace, name="rotor", fs_version=BUILD, recipes={})
    message = str(raised.value)
    assert message.count("'missing_survey.txt'") == 1, message
    assert message.count("it holds disk_survey.txt") == 1, message
