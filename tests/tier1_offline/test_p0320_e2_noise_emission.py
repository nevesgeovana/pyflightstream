"""Tier 1: the acoustic toolbox emitted by the unsteady run types (0.32.0, work package E2).

GEO-066 2.6 parts 1 to 3, FR-265 to FR-269. A row key switches
``ACOUSTIC_SOURCES`` on in the setup of an unsteady run, before the solver
initialises; observers are declared by the row as named points, imported from a
file of the input library, or as an acoustic section, with the observer time;
``COMPUTE_ACOUSTIC_SIGNALS`` and ``EXPORT_ACOUSTIC_SIGNALS`` close the run, and
the export and the section's files are declared, collected and hashed by the
record. The command order is the one the licensed round-1 probe A1 ran on
26.124 (``reports/compat/CMP-26124_2026-09-30_acoustics.yaml``). Every fixture
is synthetic.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import CampaignConfigError, acoustics, classify_outputs
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    WORKFLOWS,
    build_script,
    workflow_registry,
)
from pyflightstream.run import CampaignErrors
from pyflightstream.run.collect import acoustic_section_outputs, collect_once
from pyflightstream.run.matrix import run_matrix
from pyflightstream.script import Script, helpers
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_collect_stage import _submitted_workspace
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import RECIPES, STUB_BODY, CountingStub, converged
from tests.tier1_offline.test_rotor_by_alias import two_rotor_case
from tests.tier1_offline.test_workflows import rotor_case, steady_case, unsteady_case

OBSERVERS = "MIC1 0.0 10.0 0.0, MIC2 0.0 -10.0 0.5"
TIME = "0.05 0.2 16"
SECTION = (
    "{PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 / AZIMUTH_OBSERVERS:4 / "
    "INNER_RADIUS:5.0 / OUTER_RADIUS:10.0}"
)
#: The form round-1 probe A1 imported on 26.124: a count line, then x,y,z lines.
OBSERVER_FILE = "2\n0.0,-10.0,0.0\n5.0,0.0,10.0\n"


def _lines(case, build: str = "26.124") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def _first(lines: list[str], command: str) -> int:
    return next(i for i, line in enumerate(lines) if line.split(" ", 1)[0] == command)


def _acoustic(make, stem: str = "loads_a+00.0", **variables):
    """A case of ``make`` stating ``variables``, its outputs as the run layer declares them."""
    case = make(**variables)
    outputs = acoustics.with_acoustic_signals([f"{stem}.txt"], case, stem)
    return case.model_copy(update={"outputs": outputs})


# --- P0320-NOISE-SOURCES -------------------------------------------------------


@pytest.mark.parametrize("make", [rotor_case, unsteady_case], ids=["unsteady_rotor", "unsteady"])
@pytest.mark.parametrize("mode", ["ENABLE", "DISABLE"])
def test_p0320_noise_sources_row_key_switches_acoustic_sources_before_initialization(make, mode):
    """P0320-NOISE-SOURCES: the row key reaches the setup of an unsteady run, before
    INITIALIZE_SOLVER, with the value the row states; a row without it emits no
    acoustic command at all."""
    lines = _lines(make(ACOUSTIC_SOURCES=mode))
    assert f"ACOUSTIC_SOURCES {mode}" in lines
    assert lines.index(f"ACOUSTIC_SOURCES {mode}") < _first(lines, "INITIALIZE_SOLVER")
    assert not any(line.startswith(("COMPUTE_ACOUSTIC", "EXPORT_ACOUSTIC")) for line in lines)
    assert not any("ACOUSTIC" in line for line in _lines(make()))


def test_p0320_noise_sources_reach_a_motions_row(tmp_path):
    """P0320-NOISE-SOURCES: a row that names its rotors in MOTIONS builds through its
    own branch, and the sources are switched on there too, before the solver
    initialises."""
    lines = _lines(two_rotor_case(tmp_path, ACOUSTIC_SOURCES="ENABLE"))
    assert lines.index("ACOUSTIC_SOURCES ENABLE") < _first(lines, "INITIALIZE_SOLVER")


def test_p0320_noise_sources_are_registered_on_the_unsteady_run_types_only():
    """P0320-NOISE-SOURCES: the five keys belong to the two unsteady run types, and a
    steady run type does not read them."""
    for name in ("unsteady", "unsteady_rotor"):
        assert set(acoustics.ACOUSTIC_KEYS) <= set(WORKFLOWS[name].keys), name
    for name in ("steady", "qsteady_rotor"):
        assert not set(acoustics.ACOUSTIC_KEYS) & set(WORKFLOWS[name].keys), name


def test_p0320_noise_sources_value_outside_the_command_is_refused():
    """P0320-NOISE-SOURCES: a value the command does not take is refused naming the key."""
    with pytest.raises(CampaignConfigError, match=r"ACOUSTIC_SOURCES: ON; it is ENABLE"):
        _lines(rotor_case(ACOUSTIC_SOURCES="ON"))


# --- P0320-NOISE-OBSERVERS -----------------------------------------------------


def test_p0320_noise_observers_as_points_with_the_observer_time():
    """P0320-NOISE-OBSERVERS: each named point is created by name at its position, the
    observer time follows, both in the setup and in the order probe A1 ran."""
    case = _acoustic(
        rotor_case,
        ACOUSTIC_SOURCES="ENABLE",
        ACOUSTIC_OBSERVERS=OBSERVERS,
        ACOUSTIC_OBSERVER_TIME=TIME,
    )
    lines = _lines(case)
    created = [line for line in lines if line.startswith("CREATE_NEW_ACOUSTIC_OBSERVER")]
    assert [line.split()[1:] for line in created] == [
        ["MIC1", "0.0", "10.0", "0.0"],
        ["MIC2", "0.0", "-10.0", "0.5"],
    ]
    order = [
        lines.index("ACOUSTIC_SOURCES ENABLE"),
        lines.index(created[0]),
        lines.index(created[1]),
        lines.index("SET_ACOUSTIC_OBSERVER_TIME 0.05 0.2 16"),
        _first(lines, "INITIALIZE_SOLVER"),
    ]
    assert order == sorted(order)


def test_p0320_noise_observers_imported_from_the_point_s_copy_of_a_file(tmp_path):
    """P0320-NOISE-OBSERVERS: a file of observers is imported by the solver from the
    point's own copy, in the folder the point runs in, which the run writes byte for
    byte and hashes."""
    source = tmp_path / "ring.csv"
    source.write_text(OBSERVER_FILE, encoding="utf-8")
    case = unsteady_case(
        ACOUSTIC_SOURCES="ENABLE", ACOUSTIC_OBSERVERS_FILE="ring", ACOUSTIC_OBSERVER_TIME=TIME
    ).model_copy(update={"acoustic_observers_file": str(source)})
    outputs = acoustics.with_acoustic_signals(["P.txt"], case, "P")
    assert outputs == ["P.txt", "P_acoustic_signals.txt"]
    case = case.model_copy(update={"outputs": outputs})
    script = Script("26.124")
    script.working_dir = str(tmp_path / "DP-a+00.0")
    build_script(case, script)
    lines = script.render().splitlines()
    copy = str(Path(script.working_dir) / "ring.acoustic_observers.csv")
    assert lines[lines.index("ACOUSTIC_OBSERVERS_IMPORT") + 1] == copy
    assert script.pending_input_files[copy] == source.read_bytes()
    assert lines.index("ACOUSTIC_OBSERVERS_IMPORT") < _first(lines, "INITIALIZE_SOLVER")


def test_p0320_noise_observers_as_an_acoustic_section_after_the_signals():
    """P0320-NOISE-OBSERVERS: the section is created after the signals are computed, in
    the reference coordinate system unless FRAME names a frame the run creates, into the
    point's own folder, which the run creates by writing its note there."""
    case = _acoustic(
        rotor_case,
        ACOUSTIC_SOURCES="ENABLE",
        ACOUSTIC_SECTION=SECTION,
        ACOUSTIC_OBSERVER_TIME=TIME,
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    at = lines.index("CREATE_ACOUSTIC_SECTION")
    assert lines[at + 1 : at + 9] == [
        "FRAME 1",
        "PLANE YZ",
        "OFFSET 0.0",
        "RADIAL_OBSERVERS 2",
        "AZIMUTH_OBSERVERS 4",
        "INNER_RADIUS 5.0",
        "OUTER_RADIUS 10.0",
        "STORAGE_PATH loads_a+00.0_acoustic_section",
    ]
    assert _first(lines, "COMPUTE_ACOUSTIC_SIGNALS") < at
    note = f"loads_a+00.0_acoustic_section/{acoustics.ACOUSTIC_SECTION_NOTE}"
    assert "plane YZ" in str(script.pending_input_files[str(Path(note))])
    # A section alone exports no signals file and declares none.
    assert not any(line.startswith("EXPORT_ACOUSTIC_SIGNALS") for line in lines)
    assert case.outputs == ["loads_a+00.0.txt"]
    in_mrp = _acoustic(
        rotor_case,
        ACOUSTIC_SOURCES="ENABLE",
        ACOUSTIC_OBSERVER_TIME=TIME,
        ACOUSTIC_SECTION=SECTION.replace("{", "{FRAME:ROTOR_SMRP / "),
    )
    framed = _lines(in_mrp)
    assert framed[framed.index("CREATE_ACOUSTIC_SECTION") + 1] != "FRAME 1"


def test_p0320_noise_observers_a_section_is_placed_in_the_frame_it_names():
    """P0320-NOISE-OBSERVERS: FRAME carries the index of the very frame the record
    names among those the run created, not merely some frame other than the
    reference one."""
    case = _acoustic(
        rotor_case,
        ACOUSTIC_SOURCES="ENABLE",
        ACOUSTIC_OBSERVER_TIME=TIME,
        ACOUSTIC_SECTION=SECTION.replace("{", "{FRAME:AFT / "),
    )
    script = Script("26.124")
    script.declare_existing(frames=5)
    helpers.start_solver(script)
    acoustics.emit_acoustic_signals(
        case, script, unsteady=True, frames={"FORE": 2, "AFT": 5}, from_metres=lambda what: 1.0
    )
    lines = script.render().splitlines()
    assert lines[lines.index("CREATE_ACOUSTIC_SECTION") + 1] == "FRAME 5"


@pytest.mark.parametrize(
    ("variables", "words"),
    [
        ({"ACOUSTIC_OBSERVERS": OBSERVERS}, r"no ACOUSTIC_OBSERVER_TIME"),
        ({"ACOUSTIC_OBSERVER_TIME": TIME}, r"declares no observer"),
        ({"ACOUSTIC_OBSERVERS": "MIC1 0 0", "ACOUSTIC_OBSERVER_TIME": TIME}, r"NAME X Y Z"),
        (
            {"ACOUSTIC_OBSERVERS": "M 0 0 0, M 1 1 1", "ACOUSTIC_OBSERVER_TIME": TIME},
            r"naming M more than once",
        ),
        ({"ACOUSTIC_OBSERVERS": OBSERVERS, "ACOUSTIC_OBSERVER_TIME": "0.2 0.1 4"}, r"T1 is above"),
        (
            {
                "ACOUSTIC_SECTION": "{PLANE:QQ / OFFSET:0 / RADIAL_OBSERVERS:1 / "
                "AZIMUTH_OBSERVERS:1 / INNER_RADIUS:0 / OUTER_RADIUS:1}",
                "ACOUSTIC_OBSERVER_TIME": TIME,
            },
            r"cut in one of XY, XZ, YZ",
        ),
        (
            {"ACOUSTIC_SECTION": "{PLANE:YZ}", "ACOUSTIC_OBSERVER_TIME": TIME},
            r"does not state OFFSET",
        ),
        (
            {
                "ACOUSTIC_SECTION": SECTION.replace("{", "{FRAME:NOWHERE / "),
                "ACOUSTIC_OBSERVER_TIME": TIME,
            },
            r"frame 'NOWHERE', which\s+this run does not create",
        ),
        ({"ACOUSTIC_OBSERVERS_FILE": "ring", "ACOUSTIC_OBSERVER_TIME": TIME}, r"no resolved file"),
    ],
)
def test_p0320_noise_observers_a_malformed_declaration_is_refused_naming_the_key(variables, words):
    """P0320-NOISE-OBSERVERS: every declaration not in its form is refused before any
    emission, naming the key and the form it takes."""
    with pytest.raises(CampaignConfigError, match=words):
        _lines(_acoustic(rotor_case, ACOUSTIC_SOURCES="ENABLE", **variables))


def test_p0320_noise_observers_without_sources_are_refused():
    """P0320-NOISE-OBSERVERS: observers with no ACOUSTIC_SOURCES are refused rather than
    defaulted, since a signal computed with no source recorded is zero."""
    with pytest.raises(CampaignConfigError, match=r"states no ACOUSTIC_SOURCES"):
        _lines(_acoustic(rotor_case, ACOUSTIC_OBSERVERS=OBSERVERS, ACOUSTIC_OBSERVER_TIME=TIME))


def test_p0320_noise_observers_file_resolves_at_bind_and_refuses_a_malformed_file(tmp_path):
    """P0320-NOISE-OBSERVERS: the file key names inputs/acoustics/<stem>.csv; a missing
    file, a file not in the solver's form, and the key on a LEGACY row are refused when
    the row binds."""
    folder = tmp_path / "acoustics"
    folder.mkdir()
    (folder / "ring.csv").write_text(OBSERVER_FILE, encoding="utf-8")
    (folder / "short.csv").write_text("3\n0,0,0\n", encoding="utf-8")
    resolved = acoustics.resolve_observers_file(
        tmp_path, {"ACOUSTIC_OBSERVERS_FILE": "ring"}, pol="7", legacy=False
    )
    assert resolved == str((folder / "ring.csv").resolve())
    assert acoustics.resolve_observers_file(tmp_path, {}, pol="7", legacy=False) is None
    with pytest.raises(InputArtifactError, match=r"holds no absent\.csv; it holds ring\.csv"):
        acoustics.resolve_observers_file(
            tmp_path, {"ACOUSTIC_OBSERVERS_FILE": "absent"}, pol="7", legacy=False
        )
    with pytest.raises(InputArtifactError, match=r"states 3 observer\(s\).*holds 1"):
        acoustics.resolve_observers_file(
            tmp_path, {"ACOUSTIC_OBSERVERS_FILE": "short"}, pol="7", legacy=False
        )
    with pytest.raises(InputArtifactError, match=r"writes LEGACY"):
        acoustics.resolve_observers_file(
            tmp_path, {"ACOUSTIC_OBSERVERS_FILE": "ring"}, pol="7", legacy=True
        )


# --- P0320-NOISE-COMPUTE-EXPORT ------------------------------------------------


@pytest.mark.parametrize("make", [rotor_case, unsteady_case], ids=["unsteady_rotor", "unsteady"])
def test_p0320_noise_compute_export_at_the_end_of_the_run(make):
    """P0320-NOISE-COMPUTE-EXPORT: COMPUTE_ACOUSTIC_SIGNALS follows the solve, then
    EXPORT_ACOUSTIC_SIGNALS to the point's declared <point>_acoustic_signals.txt, then
    the section, all before the point's saved simulation and its other exports."""
    case = _acoustic(
        make,
        ACOUSTIC_SOURCES="ENABLE",
        ACOUSTIC_OBSERVERS=OBSERVERS,
        ACOUSTIC_OBSERVER_TIME=TIME,
        ACOUSTIC_SECTION=SECTION,
    )
    assert case.outputs == ["loads_a+00.0.txt", "loads_a+00.0_acoustic_signals.txt"]
    lines = _lines(case)
    export = lines.index("EXPORT_ACOUSTIC_SIGNALS")
    assert lines[export + 1] == "loads_a+00.0_acoustic_signals.txt"
    order = [
        _first(lines, "START_SOLVER"),
        lines.index("COMPUTE_ACOUSTIC_SIGNALS"),
        export,
        lines.index("CREATE_ACOUSTIC_SECTION"),
        _first(lines, "EXPORT_SOLVER_ANALYSIS_SPREADSHEET"),
        _first(lines, "CLOSE_FLIGHTSTREAM"),
    ]
    assert order == sorted(order)
    assert lines.count("COMPUTE_ACOUSTIC_SIGNALS") == 1


def test_p0320_noise_observers_a_malformed_row_is_a_blocked_point_at_pre_flight(tmp_path):
    """P0320-NOISE-OBSERVERS: a matrix row whose observers lack their time window is
    refused by the pre-flight as one blocked point carrying the sentence that names the
    key, before anything executes; naming the point's outputs, which the run layer does
    before building its script, does not raise past the point."""
    cell = (
        "DELTA_TIME:0.001 / TIME_ITERATIONS:8 / LAST_ITERS_AVG:8 / ACOUSTIC_SOURCES:ENABLE / "
        f"ACOUSTIC_OBSERVERS:{OBSERVERS}"
    )
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="0.0",
        workflow="unsteady",
        cell=cell,
    )
    stub = CountingStub(WRITES_THE_ACOUSTIC_EXPORTS)
    with pytest.raises(MatrixError, match=r"(?s)1 blocked.*no ACOUSTIC_OBSERVER_TIME"):
        run_matrix(
            matrix,
            workspace,
            name="noise",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=stub,
        )
    assert stub.invocations == []


def test_p0320_noise_compute_export_sources_alone_compute_nothing():
    """P0320-NOISE-COMPUTE-EXPORT: a row that switches the sources on and declares no
    observer records them and computes and exports nothing, and declares no file."""
    case = _acoustic(rotor_case, ACOUSTIC_SOURCES="ENABLE")
    assert case.outputs == ["loads_a+00.0.txt"]
    lines = _lines(case)
    assert "ACOUSTIC_SOURCES ENABLE" in lines
    assert "COMPUTE_ACOUSTIC_SIGNALS" not in lines


def test_p0320_noise_compute_export_needs_its_declared_output():
    """P0320-NOISE-COMPUTE-EXPORT: a case built in Python without the export among its
    outputs is refused naming the helper that declares it, never exported to a literal."""
    case = rotor_case(
        ACOUSTIC_SOURCES="ENABLE", ACOUSTIC_OBSERVERS=OBSERVERS, ACOUSTIC_OBSERVER_TIME=TIME
    )
    with pytest.raises(CampaignConfigError, match=r"with_acoustic_signals"):
        _lines(case)


# --- P0320-NOISE-COLLECT -------------------------------------------------------

#: A stub solver that writes every export the script names on the next line, the
#: acoustic export among them, and two VTK files in the folder a section names.
WRITES_THE_ACOUSTIC_EXPORTS = (
    "import pathlib, sys; "
    "from pyflightstream.cases import EXPORT_KINDS; "
    "verbs = {kind[2] for kind in EXPORT_KINDS} | {'EXPORT_ACOUSTIC_SIGNALS'}; "
    "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
    f"[pathlib.Path(lines[i + 1]).write_text({STUB_BODY}) "
    "for i, line in enumerate(lines) "
    "if line.split(' ')[0] in verbs and i + 1 < len(lines)]; "
    "[(pathlib.Path(line[13:]) / f'VTK_output-00{k}.vtk').write_text('VTK') "
    "for line in lines if line.startswith('STORAGE_PATH ') for k in (1, 2)]"
)


def test_p0320_noise_collect_the_export_and_the_section_are_collected_and_hashed(tmp_path):
    """P0320-NOISE-COLLECT: a matrix row with observers, a file and a section runs
    through the real plan and run path: the signals file is declared, collected into
    the point's folder and hashed; the imported file's copy is hashed as an input; each
    file of the section folder is listed and hashed in the record; none of them is ever
    classified as a surface export."""
    cell = (
        "DELTA_TIME:0.001 / TIME_ITERATIONS:8 / LAST_ITERS_AVG:8 / ACOUSTIC_SOURCES:ENABLE / "
        f"ACOUSTIC_OBSERVERS:{OBSERVERS} / ACOUSTIC_OBSERVERS_FILE:ring / "
        f"ACOUSTIC_OBSERVER_TIME:{TIME} / ACOUSTIC_SECTION:{SECTION}"
    )
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="0.0",
        workflow="unsteady",
        cell=cell,
    )
    (workspace.inputs_dir / "acoustics").mkdir()
    (workspace.inputs_dir / "acoustics" / "ring.csv").write_text(OBSERVER_FILE, "utf-8")
    records = run_matrix(
        matrix,
        workspace,
        name="noise",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_THE_ACOUSTIC_EXPORTS),
    )
    assert [record.status for record in records] == [RunStatus.CONVERGED], [
        record.error for record in records
    ]
    record = records[0]
    signals = [name for name in record.outputs if name.endswith("_acoustic_signals.txt")]
    assert len(signals) == 1, record.outputs
    assert re.fullmatch(
        r"datapoints/DP-(?P<t>[^/]+)/P3207-(?P=t)_acoustic_signals\.txt", signals[0]
    )
    section = sorted(name for name in record.outputs if "_acoustic_section/" in name)
    assert [Path(name).name for name in section] == ["VTK_output-001.vtk", "VTK_output-002.vtk"]
    for name in [*signals, *section]:
        assert record.outputs_sha256[name] == file_sha256(workspace.sim_dir("3207") / name)
    assert any(name.endswith("ring.acoustic_observers.csv") for name in record.inputs_sha256)
    assert not set(classify_outputs(record.outputs).values()) & {*signals, *section}


def _run_the_section_row(root: Path, executor, leftover: str | None = None):
    """Run one unsteady matrix row declaring a section, in a workspace under ``root``,
    after writing ``leftover`` (a name relative to the simulation folder) when given."""
    cell = (
        "DELTA_TIME:0.001 / TIME_ITERATIONS:8 / LAST_ITERS_AVG:8 / ACOUSTIC_SOURCES:ENABLE / "
        f"ACOUSTIC_OBSERVER_TIME:{TIME} / ACOUSTIC_SECTION:{SECTION}"
    )
    root.mkdir()
    workspace, matrix = _matrix(
        root,
        condition="MACH:0.2, REmi:2.3, ALPHA:sweep",
        values="0.0",
        workflow="unsteady",
        cell=cell,
    )
    if leftover is not None:
        stale = workspace.sim_dir("3207") / leftover
        stale.parent.mkdir(parents=True)
        stale.write_text("an earlier run's VTK", encoding="utf-8")
    return run_matrix(
        matrix,
        workspace,
        name="noise",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=executor,
    )


def test_p0320_noise_collect_refuses_a_section_file_left_before_the_run(tmp_path):
    """P0320-NOISE-COLLECT: a file already in the point's section folder before the
    solver runs is refused as a leftover, never listed and hashed as this run's
    evidence (the rule declared outputs are held to, PYFS-006): the section's files
    are listed after the run, so a leftover would be indistinguishable from a file
    the solver wrote."""
    # A first workspace names the folder the section writes into ...
    first = _run_the_section_row(tmp_path / "first", CountingStub(WRITES_THE_ACOUSTIC_EXPORTS))
    assert first[0].status is RunStatus.CONVERGED, first[0].error
    written = [name for name in first[0].outputs if "_acoustic_section/" in name]
    assert written, first[0].outputs
    leftover = str(PurePosixPath(written[0]).parent / "VTK_output-009.vtk")
    # ... and a second finds a file there before its run, as an aborted run leaves one.
    stub = CountingStub(WRITES_THE_ACOUSTIC_EXPORTS)
    with pytest.raises(CampaignErrors) as refused:
        _run_the_section_row(tmp_path / "second", stub, leftover)
    [record] = refused.value.records
    assert leftover not in record.outputs
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, record.status
    assert "VTK_output-009.vtk" in str(record.error)
    assert "before it ran" in str(record.error)
    assert stub.invocations == []


def test_p0320_noise_collect_a_submitted_point_names_its_section_files(tmp_path):
    """P0320-NOISE-COLLECT: a submitted point collected by pyfs-matrix collect (run/collect.py)
    names each file its section wrote in the record's outputs, the run's own note
    left out, exactly as the local path does; the signals file is a declared output
    and is waited for like any other."""
    template, _ = _submitted_workspace(tmp_path / "template")
    submitted = template.read_manifest()[0]
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    point = workspace.sim_dir("9001") / "datapoints" / "DP-AL+000"
    section = point / "P_acoustic_section"
    section.mkdir(parents=True)
    workspace.append_record(
        submitted.model_copy(
            update={
                "submission": {
                    **(submitted.submission or {}),
                    "working_dir": "datapoints/DP-AL+000",
                    "declared_outputs": ["P.txt", "P_acoustic_signals.txt"],
                }
            }
        )
    )
    (point / "P.txt").write_text("numbers", encoding="utf-8")
    (point / "P_acoustic_signals.txt").write_text("Observer: MIC1", encoding="utf-8")
    for name in ("VTK_output-001.vtk", "VTK_output-002.vtk", acoustics.ACOUSTIC_SECTION_NOTE):
        (section / name).write_text("VTK", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=lambda _seconds: None)
    [outcome] = report.collected
    assert outcome.record is not None
    outputs = outcome.record.outputs
    assert "datapoints/DP-AL+000/P_acoustic_signals.txt" in outputs
    assert [name for name in outputs if "_acoustic_section/" in name] == [
        "datapoints/DP-AL+000/P_acoustic_section/VTK_output-001.vtk",
        "datapoints/DP-AL+000/P_acoustic_section/VTK_output-002.vtk",
    ]


def test_p0320_noise_collect_the_acoustic_files_are_never_classified_as_an_export():
    """P0320-NOISE-COLLECT: the signals file ends in .txt like the loads table and a
    section's files end in .vtk like the surface export, and the classifier claims
    neither: listed first, the signals file does not take the loads table's place,
    and a section VTK is not the point's surface."""
    signals = "datapoints/DP-a/P_acoustic_signals.txt"
    section = "datapoints/DP-a/P_acoustic_section/VTK_output-001.vtk"
    names = [signals, section, "datapoints/DP-a/P.txt"]
    claimed = classify_outputs(names, package_version="0.32.0")
    assert claimed.get("loads") == "datapoints/DP-a/P.txt"
    assert not {signals, section} & set(claimed.values()), claimed


def test_p0320_noise_collect_lists_the_section_files_beside_the_collected_outputs(tmp_path):
    """P0320-NOISE-COLLECT: the collect's listing finds each section folder in the
    datapoint folders the collected outputs sit in, every file but the run's own note,
    sorted, and adds nothing where no section wrote."""
    point = tmp_path / "datapoints" / "DP-a+00.0"
    folder = point / "P1_acoustic_section"
    folder.mkdir(parents=True)
    for name in ("VTK_output-002.vtk", "VTK_output-001.vtk", acoustics.ACOUSTIC_SECTION_NOTE):
        (folder / name).write_text("x", encoding="utf-8")
    collected = ["datapoints/DP-a+00.0/P1.txt"]
    assert acoustic_section_outputs(tmp_path, collected) == [
        *collected,
        "datapoints/DP-a+00.0/P1_acoustic_section/VTK_output-001.vtk",
        "datapoints/DP-a+00.0/P1_acoustic_section/VTK_output-002.vtk",
    ]
    assert acoustic_section_outputs(tmp_path / "other", collected) == collected


# --- P0320-NOISE-ORDER ---------------------------------------------------------


def test_p0320_noise_order_sources_after_initialization_are_refused():
    """P0320-NOISE-ORDER: the acoustic setup emitted into a script that already
    initialised the solver is refused, since sources switched on after the
    initialisation record nothing."""
    script = Script("26.124")
    helpers.initialize_solver(script)
    with pytest.raises(CampaignConfigError, match=r"would follow INITIALIZE_SOLVER"):
        acoustics.emit_acoustic_setup(
            rotor_case(ACOUSTIC_SOURCES="ENABLE"), script, from_metres=lambda what: 1.0
        )


def test_p0320_noise_order_compute_and_export_on_a_steady_run_are_refused():
    """P0320-NOISE-ORDER: computing or exporting the signals on a steady run, or before
    the solver started, is refused: there is no unsteady solution to read."""
    case = _acoustic(
        rotor_case,
        ACOUSTIC_SOURCES="ENABLE",
        ACOUSTIC_OBSERVERS=OBSERVERS,
        ACOUSTIC_OBSERVER_TIME=TIME,
    )
    script = Script("26.124")
    with pytest.raises(CampaignConfigError, match=r"the run is steady"):
        acoustics.emit_acoustic_signals(
            case, script, unsteady=False, frames=None, from_metres=lambda what: 1.0
        )
    with pytest.raises(CampaignConfigError, match=r"the solver has not been started"):
        acoustics.emit_acoustic_signals(
            case, script, unsteady=True, frames=None, from_metres=lambda what: 1.0
        )


def test_p0320_noise_order_a_steady_row_stating_the_keys_is_refused():
    """P0320-NOISE-ORDER: a steady row stating an acoustic key is refused by the row-key
    guard, naming the unsteady run types that read it."""
    with pytest.raises(CampaignConfigError, match=r"ACOUSTIC_SOURCES \(a key of unsteady"):
        _lines(steady_case(ACOUSTIC_SOURCES="ENABLE"))


def test_p0320_noise_order_a_continuation_with_acoustic_keys_is_refused():
    """P0320-NOISE-ORDER: a continuation of a stopped march is refused when the row asks
    for acoustic signals, since whether the recorded sources survive the save is not
    measured."""
    case = unsteady_case(
        RESTART="{FINISH_PENDING}",
        ACOUSTIC_SOURCES="ENABLE",
        **{RESTART_FROM_VARIABLE: "saved/point.fsm", RESTART_ITERATIONS_VARIABLE: "10"},
    )
    with pytest.raises(CampaignConfigError, match=r"continues a stopped run"):
        _lines(case)
