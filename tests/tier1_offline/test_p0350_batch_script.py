"""The job script of a grouped run, spliced from the per-point scripts (FR-352 to FR-360).

The fixtures under ``fixtures/batch0350/scripts/`` are the scripts the
licensed probes of 2026-10-02 measured on 26.124 (DESIGN-0350 test report):
the per-point scripts pyflightstream 0.34.0 wrote for POL 9811, 9812, 9821
and 9841, and the arm scripts that ran several points in one instance (arm A:
one polar re-initialized; arm D: the advance ratio moved; arm E: a second
polar on another geometry, the actions registered once). Machine paths are
scrubbed to ``<machine path>``; each test names the geometry path it needs.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._batch_script import (
    JobPoint,
    JobPolar,
    assemble_job,
    drop_registrations,
    job_point,
    refuse_unspliceable,
    restate_anchor,
    write_targets,
)
from pyflightstream.cases.workflows._vocabulary import CUMULATIVE_LOG_SUFFIX
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import rotor_case

SCRIPTS = Path(__file__).parent / "fixtures" / "batch0350" / "scripts"
BUILD = "26.124"
ROOT = PurePosixPath("/ws/sims/batch/mtx_b1")
ACTION_HEAD = "SET_NEW_UNSTEADY_SOLVER_ACTION"
#: The commands whose next line is a path (the geometry and every target).
PATH_HEADS = ("OPEN", "SAVEAS", "SAVE_PLOT_TO_FILE", "UNSTEADY_SOLVER_EXPORT_PLOTS")


def relative_paths(text: str) -> list[tuple[int, str]]:
    """Scan every line independently of the emitter's output inventory and command database."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        tokens = re.findall(r'"[^"]*"|\'[^\']*\'|[^\s"\']+', line)
        if PurePosixPath(line).is_absolute() or PureWindowsPath(line).is_absolute():
            tokens = [line]  # Native path-only lines may contain unquoted spaces.
        for word in tokens:
            token = word.strip("\"'")
            pathlike = (
                "/" in token
                or "\\" in token
                or token.lower().endswith((".py", ".txt", ".fsm", ".csv", ".json", ".dat"))
            )
            absolute = PurePosixPath(token).is_absolute() or PureWindowsPath(token).is_absolute()
            if pathlike and (not absolute or ".." in token.replace("\\", "/").split("/")):
                found.append((number, line))
    return found


@pytest.mark.parametrize("kind", ["batch", "polar_sweep"])
@pytest.mark.parametrize("exports", [False, True])
@pytest.mark.parametrize("root", [ROOT, PureWindowsPath("Q:/scratch/job with spaces")])
def test_p0350_script_fr359_all_path_tokens_absolute(kind, exports, root):
    """P0350-BATCH-ABSOLUTE (FR-359): scan BATCH and FULL-POLAR, including action arguments.

    Reproduction: build two unsteady rotor polars with WALLTIME and ordinary
    exports. Without a per-step threshold the old splice leaves exactly the
    counter, clock and stop-file lines relative; with one it also leaves the
    exports action relative. The single-point text stays byte-for-byte intact.
    """
    polars = []
    originals = []
    for sim in ("7101", "7102"):
        case = rotor_case(WALLTIME="4m", EXPORT_UNSTEADY_AFTER_ITER=2 if exports else None)
        case = case.model_copy(update={"sim_id": sim, "outputs": ["point.txt", "point.fsm"]})
        script = Script(BUILD)
        build_script(case, script)
        original = script.render()
        point = job_point(
            case,
            run_id=f"mtx/sim_{sim}/DP-a00",
            text=original,
            datapoint_dir=root / f"sim_{sim}/datapoints/DP-a00",
            version=BUILD,
        )
        polars.append(JobPolar(sim, (point,)))
        originals.append(original)
    job = assemble_job(polars, kind=kind, version=BUILD, job_log=None, job_dir=root)
    assert not relative_paths(job.text), relative_paths(job.text)
    for polar, original in zip(polars, originals, strict=True):
        assert polar.points[0].text == original
    for name in ("pfs_unsteady_actions.py", "pfs_walltime_clock.py", "pfs_walltime_stop.txt"):
        assert str(root / "actions" / name) in job.text
    if exports:
        assert str(root / "actions/pfs_unsteady_exports.txt") in job.text


@pytest.mark.parametrize("quote", ["", '"', "'"])
@pytest.mark.parametrize(
    ("command", "name"),
    [
        ("SET_INLET_CUSTOM_PROFILE 1", "pfs_inlet_1_abcd.txt"),
        ("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER", "wing.wake_nodes.txt"),
        ("SET_PROP_ACTUATOR_PROFILE 1 NEWTONS 2", "disc.actuator_profile.txt"),
        ("SET_FREESTREAM CUSTOM UNSTRUCTURED", "converted field.dat"),
        ("SET_FREESTREAM CUSTOM STRUCTURED", "converted_field.txt"),
        ("OPEN", "geometry.fsm"),
        ("IMPORT\nUNITS METER\nFILE_TYPE OBJ\nFILE", "mesh.obj"),
    ],
)
def test_p0350_script_fr359_point_inputs_are_absolute(command, name, quote):
    """P0350-BATCH-ABSOLUTE (FR-359): each emitter's local input follows its datapoint.

    These are the relative input forms of _geometry, _actuator and _freestream;
    FSI and user actions are refused by the grouped planner. The normal run
    already binds geometry and wake/profile paths absolutely; the splice must
    also handle their relative forms without changing the saved point text.
    """
    case = rotor_case()
    script = Script(BUILD)
    build_script(case, script)
    separator = " " if command.endswith("FILE") else "\n"
    text = f"{command}{separator}{quote}{name}{quote}\n\n" + script.render()
    point = job_point(
        case,
        run_id="mtx/sim_7001/DP-a00",
        text=text,
        datapoint_dir=ROOT / "sim_7001/datapoints/DP-a00",
        version=BUILD,
    )
    job = assemble_job(
        [JobPolar(case.sim_id, (point,))],
        kind="batch",
        version=BUILD,
        job_dir=ROOT,
        job_log=None,
    )
    assert not relative_paths(job.text), relative_paths(job.text)
    assert f"{quote}{point.datapoint_dir / name}{quote}" in job.text
    assert point.text == text


def _text(name: str, geometry: str) -> str:
    """A fixture script, its scrubbed geometry path named by the test."""
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    return text.replace("OPEN\n<machine path>", f"OPEN\n{geometry}", 1)


def _point(name: str, *, sim: str, folder: str, geometry: str = "", text: str | None = None):
    """A job point from a fixture, its outputs read off its own targets."""
    body = text if text is not None else _text(name, geometry or f"/ws/sims/sim_{sim}/inputs/g.fsm")
    outputs = tuple(dict.fromkeys(t for t in write_targets(body, BUILD) if not t.startswith("/")))
    return JobPoint(
        run_id=f"mtx/sim_{sim}/{folder}",
        sim_id=sim,
        point_name=folder,
        text=body,
        datapoint_dir=ROOT / f"sim_{sim}" / "datapoints" / folder,
        outputs=outputs,
        action_exports="",
        first_export_step=None,
        stop_text="",
        time_steps=45,
    )


def _normalized(text: str) -> list[str]:
    """The command sequence: comments and blanks dropped, every path and target a role."""
    out: list[str] = []
    previous = ""
    for line in text.splitlines():
        bare = line.strip()
        if not bare or bare.startswith("#"):
            continue
        head = previous.split()[0] if previous.split() else ""
        if head in PATH_HEADS or head.startswith("EXPORT_"):
            out.append("<path>")
        elif head == ACTION_HEAD:
            out.append("<action>")
        else:
            out.append(bare)
        previous = bare
    return out


def _same_polar() -> tuple[JobPoint, JobPoint]:
    """POL 9811 (alpha 0) and POL 9812 (alpha 2), restated as one polar of sim 9811."""
    geometry = "/ws/sims/sim_9811/inputs/30_BLADE.fsm"
    first = _point("p9811.txt", sim="9811", folder="DP-a00", geometry=geometry)
    second = _point("p9812.txt", sim="9811", folder="DP-a20", geometry=geometry)
    return first, second


def test_p0350_script_fr352_a_reinit_splice_equals_arm_a():
    """P0350-BATCH-SAME-POLAR (FR-352): a later point of a polar is arm A's re-initialization.

    The job over {9811 alpha 0, 9812 alpha 2} gives the command sequence of
    the measured ``armA.txt`` once both are normalized. Control: the same
    pair with the rotor speed line touched (so the anchor moves to
    ``SET_MOTION_ROTOR_RPM``, the restating of arm D) must NOT match arm A,
    so the comparison can tell the two cuts apart.
    """
    first, second = _same_polar()
    job = assemble_job(
        [JobPolar("9811", (first, second))], kind="batch", version=BUILD, job_log=None, job_dir=ROOT
    )
    arm_a = _normalized((SCRIPTS / "armA.txt").read_text(encoding="utf-8"))
    assert _normalized(job.text) == arm_a
    assert [block.transition for block in job.blocks] == ["start", "reinit"]
    assert job.blocks[1].anchor == "SET_SOLVER_UNSTEADY"

    moved = second.text.replace(
        "SET_MOTION_ROTOR_RPM 1 473.1723", "SET_MOTION_ROTOR_RPM 1 473.17230"
    )
    mutant = _point("", sim="9811", folder="DP-a20", text=moved)
    assert restate_anchor(first, mutant) == "SET_MOTION_ROTOR_RPM"
    control = assemble_job(
        [JobPolar("9811", (first, mutant))], kind="batch", version=BUILD, job_log=None, job_dir=ROOT
    )
    assert _normalized(control.text) != arm_a


def test_p0350_script_fr352_the_anchor_follows_the_first_difference():
    """P0350-BATCH-SAME-POLAR (FR-352): the anchor is the nearest one at the first difference.

    The 9821 pair (J 1.5, J 1.9: a new speed and a new time step) splices at
    ``SET_MOTION_ROTOR_RPM``, arm D's cut, and the job equals arm D's
    sequence; the 9811/9812 pair (alpha only) at ``SET_SOLVER_UNSTEADY``.
    """
    geometry = "/ws/sims/sim_9821/inputs/30_BLADE.fsm"
    low = _point("p9821_j150.txt", sim="9821", folder="DP-j150", geometry=geometry)
    high = _point("p9821_j190.txt", sim="9821", folder="DP-j190", geometry=geometry)
    assert restate_anchor(low, high) == "SET_MOTION_ROTOR_RPM"
    job = assemble_job(
        [JobPolar("9821", (low, high))],
        kind="polar_sweep",
        version=BUILD,
        job_log=None,
        job_dir=ROOT,
    )
    assert _normalized(job.text) == _normalized((SCRIPTS / "armD.txt").read_text(encoding="utf-8"))
    assert restate_anchor(*_same_polar()) == "SET_SOLVER_UNSTEADY"


def test_p0350_script_fr353_fr354_a_refresh_equals_arm_e():
    """P0350-BATCH-NEW-POLAR (FR-353), P0350-BATCH-ACTIONS-ONCE (FR-354): arm E's refresh.

    Polars {30_BLADE: 9811} and {40_PUSHER: 9841 alpha 0, alpha 4} give arm
    E's sequence: ``NEW_SIMULATION``, the second polar's ``OPEN`` of its
    pristine staged geometry, and no registration after the first point.
    Control: the same job with the second polar's registrations kept (arm C's
    doubling) must NOT match arm E.
    """
    blade = _point(
        "p9811.txt", sim="9811", folder="DP-a00", geometry="/ws/sims/sim_9811/inputs/30_BLADE.fsm"
    )
    pusher = "/ws/sims/sim_9841/inputs/40_PUSHER.fsm"
    low = _point("p9841_a000.txt", sim="9841", folder="DP-a00", geometry=pusher)
    high = _point("p9841_a040.txt", sim="9841", folder="DP-a40", geometry=pusher)
    job = assemble_job(
        [JobPolar("9811", (blade,)), JobPolar("9841", (low, high))],
        kind="batch",
        version=BUILD,
        job_log=None,
        job_dir=ROOT,
    )
    arm_e = _normalized((SCRIPTS / "armE.txt").read_text(encoding="utf-8"))
    assert _normalized(job.text) == arm_e
    assert [block.transition for block in job.blocks] == ["start", "refresh", "reinit"]
    lines = job.text.splitlines()
    refresh = job.blocks[1]
    assert lines[refresh.first_line - 1] == "NEW_SIMULATION"
    opened = [lines[i + 1] for i, line in enumerate(lines) if line == "OPEN"]
    assert opened == ["/ws/sims/sim_9811/inputs/30_BLADE.fsm", pusher]
    heads = [i + 1 for i, line in enumerate(lines) if line.startswith(ACTION_HEAD)]
    assert heads and max(heads) <= job.blocks[0].last_line

    own = [line for line in low.text.splitlines() if line.startswith(ACTION_HEAD)]
    doubled = job.text.replace("INITIALIZE_SOLVER", "\n".join([*own, "INITIALIZE_SOLVER"]), 2)
    assert _normalized(doubled) != arm_e


def test_p0350_script_fr352_unspliceable_prefix_refused_by_line():
    """P0350-BATCH-SAME-POLAR (FR-352): a difference before the anchor is refused by line.

    A point whose fluid density differs is refused, naming that line. Control:
    a point whose only pre-anchor difference is its own datapoint folder in a
    node-file path is accepted.
    """
    first, second = _same_polar()
    dense = second.text.replace("DENSITY 0.798989896950572", "DENSITY 1.225")
    line = dense.splitlines().index("DENSITY 1.225") + 1
    with pytest.raises(CampaignConfigError, match=rf"line {line} .*DENSITY 1\.225"):
        refuse_unspliceable(first, _point("", sim="9811", folder="DP-a20", text=dense))

    def parked(point: JobPoint) -> JobPoint:
        text = point.text.replace(
            "SET_SIGNIFICANT_DIGITS 7", f"SET_SIGNIFICANT_DIGITS 7\n{point.datapoint_dir}/nodes.txt"
        )
        return _point("", sim="9811", folder=point.point_name, text=text)

    refuse_unspliceable(parked(first), parked(second))
    assert restate_anchor(parked(first), parked(second)) == "SET_SOLVER_UNSTEADY"


def test_p0350_script_fr359_fr360_every_target_absolute_in_its_folder():
    """P0350-BATCH-ABSOLUTE (FR-359, FR-360): every target absolute, in its point's folder.

    Every target of an assembled job is absolute and under its own point's
    datapoint folder; each declared output appears exactly once; a point's
    ``EXPORT_LOG`` target ends in the cumulative suffix. Control: a point
    whose declared outputs leave one name out keeps it relative, and
    ``assemble_job`` refuses the job.
    """
    first, second = _same_polar()
    job = assemble_job(
        [JobPolar("9811", (first, second))], kind="batch", version=BUILD, job_log=None, job_dir=ROOT
    )
    assert job.targets == write_targets(job.text, BUILD)
    for point in (first, second):
        mine = [t for t in job.targets if t.startswith(f"{point.datapoint_dir}/")]
        for name in point.outputs:
            if name.endswith("_log.txt"):
                stem = name.removesuffix("_log.txt")
                assert mine.count(f"{point.datapoint_dir}/{stem}{CUMULATIVE_LOG_SUFFIX}") == 1
            else:
                assert mine.count(f"{point.datapoint_dir}/{name}") == 1, name
        assert len(mine) == len(point.outputs)
    assert sum(len(p.outputs) for p in (first, second)) == len(job.targets)

    short = replace(second, outputs=second.outputs[1:])
    with pytest.raises(CampaignConfigError, match="relative"):
        assemble_job(
            [JobPolar("9811", (first, short))],
            kind="batch",
            version=BUILD,
            job_log=None,
            job_dir=ROOT,
        )


def _without_log(point: JobPoint) -> JobPoint:
    """The point as the cluster writes it with ``export_log = false``: no EXPORT_LOG."""
    text = re.sub(r"EXPORT_LOG\n[^\n]*\n", "", point.text)
    return _point("", sim=point.sim_id, folder=point.point_name, text=text)


def test_p0350_script_fr357_job_end():
    """The job ends with its own log when its points export theirs, else with the close alone."""
    first, second = _same_polar()
    log = ROOT / "BATCH-9811-9811.job-log.txt"
    job = assemble_job(
        [JobPolar("9811", (first, second))], kind="batch", version=BUILD, job_log=log, job_dir=ROOT
    )
    assert job.text.endswith(f"EXPORT_LOG\n{log}\n\nCLOSE_FLIGHTSTREAM\n")
    assert job.text.count("CLOSE_FLIGHTSTREAM") == 1

    quiet = [_without_log(first), _without_log(second)]
    bare = assemble_job(
        [JobPolar("9811", tuple(quiet))], kind="batch", version=BUILD, job_log=log, job_dir=ROOT
    )
    assert "EXPORT_LOG" not in bare.text
    assert bare.text.rstrip("\n").splitlines()[-1] == "CLOSE_FLIGHTSTREAM"


def test_p0350_script_drop_registrations_and_job_point():
    """P0350-BATCH-POINT-SCRIPTS (FR-356): the job is built from the per-point builder output.

    The registrations go with their argument lines; a job point reads its
    case and the script its builder wrote.
    """
    text = _text("p9812.txt", "/ws/g.fsm")
    dropped = drop_registrations(text)
    assert ACTION_HEAD not in dropped
    assert '"actions/' not in dropped and "actions/pfs_walltime_stop.txt" not in dropped
    assert len(text.splitlines()) - len(dropped.splitlines()) == 9

    case = rotor_case()
    script = Script(BUILD)
    from pyflightstream.cases.workflows import build_script

    build_script(case, script)
    folder = PurePosixPath("/ws/sims/sim_7001/datapoints/DP-x")
    point = job_point(
        case, run_id="mtx/sim_7001/DP-x", text=script.render(), datapoint_dir=folder, version=BUILD
    )
    assert point.point_name == "DP-x" and point.sim_id == "7001"
    assert point.time_steps == 720
    assert point.first_export_step is None and point.action_exports == ""
    assert point.outputs == ("loads_a+00.0.txt",)
    assert point.stop_text.rstrip("\n").endswith("CLOSE_FLIGHTSTREAM")
