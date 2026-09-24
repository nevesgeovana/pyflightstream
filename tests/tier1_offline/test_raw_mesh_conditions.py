"""Tier 1: a raw mesh's boundary conditions, declared in its sidecar (G02, T06).

A raw mesh (``.obj``, ``.stl``) carries no trailing edge, and without one the
solver makes no wake and still runs and answers. So the sidecar that already
states the mesh's unit and names, ``<stem>.boundaries.toml``, declares how its
trailing edges are marked, in a ``[trailing_edges]`` table:

* ``file = "<points file>"`` is the DEFAULT route: a package-side points file
  (a unit line, then the mid-point of every trailing-edge mesh edge), checked
  against the mesh at plan, converted to the simulation's metres, written as
  the solver's node file and imported by ``IMPORT_WAKE_EDGES_FROM_FILE``. It
  runs on 26.124 only, the one build it was measured on (RPT-061).
* ``detect = "auto"`` or ``detect = { surfaces = [...], sweep_angle = ... }``
  is the second route, and it applies only when written: detection is never
  the silent default.

Beside it, two options apply only when written: ``[wake_termination]``
(automatic, or by surface) and ``[base_regions]`` (automatic). A raw mesh
whose sidecar declares no trailing edge is refused at plan, and a saved
simulation whose sidecar declares any of the three tables is refused, since
its own marking is already in the file.

The fixture is the qa synthetic wing, a rectangular NACA 0012 of chord 1 m and
span 8 m in 16 spanwise panels: its trailing edge is 16 mesh edges whose
mid-points lie at x = 1, z = 0 and y = -3.75 + 0.5 k, the same set the solver
imported from a file and detected by angle on 26.124 (RPT-061, RPT-065).
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases import workflows as workflows_module
from pyflightstream.cases.matrix import MatrixError
from pyflightstream.cases.workflows import (
    WORKFLOW_KEY,
    build_script,
    build_steady_sweep,
    workflow_registry,
)
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.qa.geometry import WingSpec, generate_wing_stl
from pyflightstream.run import (
    Assessment,
    CampaignErrors,
    LocalExecutor,
    PlanStatus,
    SubmittingExecutor,
    run_campaign,
)
from pyflightstream.run.matrix import plan_matrix, run_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import InputArtifactError, RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE as NATIVE_LOG_TABLE
from tests.tier1_offline.test_goal024_profile_log import PROFILE as NATIVE_LOG_PROFILE
from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix
from tests.tier1_offline.test_workflows import FIXTURE_ROTOR

GOLDENS = Path(__file__).parent / "goldens" / "raw_mesh"

#: The sixteen trailing-edge mid-points of the qa wing, by construction.
MIDPOINTS = [(1.0, -3.75 + 0.5 * k, 0.0) for k in range(16)]

#: What the solver logs when it imports all sixteen onto the wing (RPT-061).
_SIXTEEN_ON_WING = "16 trailing edges imported for boundary Wing"

#: One steady row naming the wing, its loads table and its solver log.
ROW = (
    "7001 | TestWing | RAW_MESH | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 | {build} |  0 | 1 | OUTPUTS: {outputs} / VELOCITY: 30.0 / GEOMETRY: {geometry}{tail}"
)
WITH_LOG = "loads_{point}.txt,run_{point}_log.txt"
WITHOUT_LOG = "loads_{point}.txt"

FILE_ROUTE = '[trailing_edges]\nfile = "wing.te.txt"\n'
DETECT_AUTO = '[trailing_edges]\ndetect = "auto"\n'
DETECT_BY_SURFACE_WITH_WAKE_AND_BASE = (
    '[trailing_edges]\ndetect = { surfaces = ["Wing"], sweep_angle = 60 }\n\n'
    '[wake_termination]\ndetect = { surfaces = ["Wing"] }\n\n'
    '[base_regions]\ndetect = "auto"\n'
)
#: The file route with both options: the one that waits for an initialisation
#: and the one that does not.
FILE_ROUTE_WITH_WAKE_AND_BASE = (
    FILE_ROUTE + '\n[wake_termination]\ndetect = "auto"\n\n[base_regions]\ndetect = "auto"\n'
)


def _points_text(points=MIDPOINTS, unit="METER") -> str:
    return unit + "\n" + "".join(f"{x!r},{y!r},{z!r}\n" for x, y, z in points)


def _library(tmp_path, tables, *, build="26.124", points=None, suffix=".stl"):
    """A workspace holding the qa wing, its sidecar with ``tables`` and its points file."""
    workspace = make_library(tmp_path, register_build=(build, Path(sys.executable).as_posix()))
    geometries = workspace.inputs_dir / "geometries"
    mesh = geometries / f"wing{suffix}"
    if suffix == ".stl":
        spec = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=16)
        generate_wing_stl(spec, mesh, name="Wing")
        unit_table = '[import]\nunits = "METER"\n\n'
    else:
        mesh.write_bytes(b"a saved simulation")
        unit_table = ""
    (geometries / "wing.boundaries.toml").write_text(
        'boundaries = ["Wing"]\n\n' + unit_table + tables, encoding="utf-8"
    )
    (geometries / "wing.te.txt").write_text(
        points if points is not None else _points_text(), encoding="utf-8"
    )
    return workspace


def _matrix(tmp_path, build="26.124", outputs=WITH_LOG, geometry="wing.stl", tail=""):
    row = ROW.format(build=build, outputs=outputs, geometry=geometry, tail=tail)
    return write_matrix(tmp_path / "raw_mesh.fs", [row])


def _case(tmp_path, workspace, *, build="26.124", outputs=WITH_LOG, geometry="wing.stl", tail=""):
    """Bind the one row and return its case, at its one point."""
    resolved = resolve_matrix(
        _matrix(tmp_path, build, outputs, geometry, tail),
        workspace,
        name="matrix",
        fs_version=build,
        recipes=RECIPES,
    )
    case = resolved.campaign.sims[0]
    rendered = [name.replace("{point}", "a+00.0") for name in case.outputs]
    return case.model_copy(update={"point": {"alpha": 0.0}, "outputs": rendered})


def _render(case, build="26.124") -> str:
    script = Script(build)
    build_script(case, script)
    return script.render()


def _normalized(text: str, tmp_path: Path) -> str:
    """The render with the machine's folder replaced, in one separator."""
    return (
        text.replace(str(tmp_path), "<WORKDIR>")
        .replace(tmp_path.as_posix(), "<WORKDIR>")
        .replace("\\", "/")
    )


# --- the default and the second route ------------------------------------------------


def test_a_raw_mesh_whose_sidecar_declares_no_trailing_edge_is_refused_at_plan(tmp_path):
    """No trailing edge, no wake, and the solver answers anyway: refused, naming the table.

    Matched on the table's name, never on the exception type alone: the
    type is raised for other reasons by the same builder.
    """
    workspace = _library(tmp_path, "")
    case = _case(tmp_path, workspace)
    with pytest.raises(CampaignConfigError, match=r"\[trailing_edges\]") as caught:
        _render(case)
    message = str(caught.value)
    for needle in ("wing.boundaries.toml", 'file = "', 'detect = "auto"', "docs/mesh-inputs.md"):
        assert needle in message, f"the refusal does not name {needle!r}: {message}"
    # THE PAGE'S OWN WORDS: the refusal says which sentence to search for, and
    # a quoted phrase the page does not carry sends a blocked user nowhere.
    anchor = workflows_module._CONDITIONS_PAGE_ANCHOR
    assert anchor in message, message
    page = Path(__file__).resolve().parents[2] / "docs" / "mesh-inputs.md"
    assert anchor in page.read_text(encoding="utf-8"), f"{page.name} does not carry {anchor!r}"


def test_detection_is_emitted_only_when_written(tmp_path):
    """The file route marks by the file alone; the detect route by detection alone.

    A silent default would be the file route ALSO emitting a detection, or
    a table naming neither meaning detection.
    """
    detections = ("AUTO_DETECT_TRAILING_EDGES", "DETECT_TRAILING_EDGES_BY_SURFACE")
    by_file = _render(_case(tmp_path, _library(tmp_path, FILE_ROUTE))).splitlines()
    assert "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER" in by_file, by_file
    assert not [line for line in by_file if line.startswith(detections)], by_file

    other = tmp_path / "detect"
    other.mkdir()
    by_detection = _render(_case(other, _library(other, DETECT_AUTO))).splitlines()
    assert "AUTO_DETECT_TRAILING_EDGES" in by_detection, by_detection
    assert not [line for line in by_detection if line.startswith("IMPORT_WAKE_EDGES")]


@pytest.mark.parametrize(
    ("name", "tables"),
    [
        ("te_file__26.124", FILE_ROUTE),
        ("te_detect_auto__26.124", DETECT_AUTO),
        (
            "te_detect_by_surface_with_wake_and_base__26.124",
            DETECT_BY_SURFACE_WITH_WAKE_AND_BASE,
        ),
        ("te_file_with_wake_and_base__26.124", FILE_ROUTE_WITH_WAKE_AND_BASE),
    ],
    ids=["file", "detect-auto", "detect-by-surface-wake-base", "file-wake-base"],
)
def test_each_raw_mesh_route_renders_its_committed_bytes(tmp_path, name, tables):
    """One golden per route, byte for byte, with the machine's folder as <WORKDIR>."""
    rendered = _normalized(_render(_case(tmp_path, _library(tmp_path, tables))), tmp_path)
    golden = GOLDENS / f"{name}.txt"
    assert golden.is_file(), f"{golden.name} is not committed; run this module with --write"
    assert rendered.encode("utf-8") == golden.read_bytes(), (
        f"the {name} render moved; if the change is intended, run this module with --write "
        "and read the diff"
    )


def test_the_file_route_writes_the_checked_points_in_metres_in_the_folder_the_script_runs_in(
    tmp_path,
):
    """The node file is parked for the run: the count, the placeholder, then the points.

    It is named inside the folder the run gives the script (G02), by absolute
    path, as the geometry is, and never beside the staged geometry: a staged
    geometry is a link into the input library that every simulation on the
    same mesh shares. With no folder given, the bare file name.
    """
    points = [(1000.0 * x, 1000.0 * y, 1000.0 * z) for x, y, z in MIDPOINTS]
    workspace = _library(tmp_path, FILE_ROUTE, points=_points_text(points, "MILLIMETER"))
    case = _case(tmp_path, workspace)
    folder = tmp_path / "camp" / "sims" / "sim_7001" / "datapoints" / "DP-point"
    script = Script("26.124")
    script.working_dir = str(folder)
    build_script(case, script)
    lines = script.render().splitlines()
    at = lines.index("IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER")
    assert Path(lines[at + 1]) == folder / "wing.wake_nodes.txt", lines[at + 1]
    parked = script.pending_input_files[lines[at + 1]].splitlines()
    assert parked[:3] == ["16", "0,0,0", "1.0,-3.75,0.0"], parked
    assert script.wake_edge_points == 16

    bare = Script("26.124")
    build_script(case, bare)
    rendered = bare.render().splitlines()
    assert rendered[rendered.index(lines[at]) + 1] == "wing.wake_nodes.txt", rendered


@pytest.mark.parametrize(
    ("build", "needles"),
    [("26.123", ("RPT-061", "26.124")), ("26.121", ("26.121", "does not carry"))],
    ids=["unmeasured-build", "build-without-the-command"],
)
def test_the_file_route_is_refused_on_a_build_it_was_not_measured_on(tmp_path, build, needles):
    """The import line was run on 26.124 only; no other build is emitted a form for it."""
    workspace = _library(tmp_path, FILE_ROUTE, build=build)
    case = _case(tmp_path, workspace, build=build)
    with pytest.raises(CommandNotInVersionError) as caught:
        _render(case, build)
    for needle in needles:
        assert needle in str(caught.value), caught.value


def test_a_file_route_row_that_exports_no_solver_log_is_refused_at_plan(tmp_path):
    """The count check reads the solver log, and the solver writes one of its own only on an
    abnormal end: a file-route row with no log among its outputs could never pass it."""
    workspace = _library(tmp_path, FILE_ROUTE)
    case = _case(tmp_path, workspace, outputs=WITHOUT_LOG)
    with pytest.raises(CampaignConfigError, match=r"_log\.txt") as caught:
        _render(case)
    assert "trailing" in str(caught.value) and "count" in str(caught.value), caught.value


# --- the refusals of the tables -------------------------------------------------------


@pytest.mark.parametrize(
    ("tables", "needles"),
    [
        (FILE_ROUTE + 'detect = "auto"\n', ("both file and detect", "one of")),
        ("[trailing_edges]\n", ("neither file nor detect", "one of")),
        (FILE_ROUTE + "angle = 30\n", ("angle",)),
        ('[trailing_edges]\ndetect = "yes"\n', ("'yes'", "auto")),
        (DETECT_AUTO + "tolerance = 0.001\n", ("tolerance", "detect")),
        ("[trailing_edges]\ndetect = { surfaces = [] }\n", ("surfaces",)),
        (FILE_ROUTE + "tolerance = 0\n", ("tolerance",)),
        (FILE_ROUTE + '\n[wake_termination]\ndetect = "all"\n', ("wake_termination", "'all'")),
        (
            FILE_ROUTE + '\n[base_regions]\ndetect = { surfaces = ["Wing"] }\n',
            ("base_regions", "auto"),
        ),
    ],
    ids=[
        "file-and-detect",
        "neither",
        "a-key-it-does-not-read",
        "a-detect-word",
        "a-tolerance-detection-does-not-read",
        "no-surface",
        "a-zero-tolerance",
        "a-wake-termination-word",
        "base-regions-by-surface",
    ],
)
def test_a_table_that_does_not_hold_its_shape_is_refused_at_binding(tmp_path, tables, needles):
    """Each table is read at binding, so a malformed one is refused with the row, by name."""
    workspace = _library(tmp_path, tables)
    with pytest.raises(InputArtifactError) as caught:
        _case(tmp_path, workspace)
    message = str(caught.value)
    assert "POL 7001" in message and "wing.boundaries.toml" in message, message
    for needle in needles:
        assert needle in message, f"the refusal does not name {needle!r}: {message}"


def test_a_points_file_that_misses_the_mesh_is_refused_at_binding_naming_the_line(tmp_path):
    """Point 3 moved 0.2 mm aft marks nothing, silently; it is refused before any seat."""
    moved = list(MIDPOINTS)
    moved[2] = (1.0002, moved[2][1], 0.0)
    workspace = _library(tmp_path, FILE_ROUTE, points=_points_text(moved))
    with pytest.raises(InputArtifactError) as caught:
        _case(tmp_path, workspace)
    message = str(caught.value)
    for needle in ("POL 7001", "wing.te.txt", "point 3 of 16", "file line 4", "0.0002"):
        assert needle in message, f"the refusal does not name {needle!r}: {message}"


@pytest.mark.parametrize("table", [FILE_ROUTE, DETECT_AUTO, '[base_regions]\ndetect = "auto"\n'])
def test_a_saved_simulation_whose_sidecar_marks_edges_is_refused(tmp_path, table):
    """A .fsm carries its own marking; a second pass from the sidecar would mark twice."""
    workspace = _library(tmp_path, table, suffix=".fsm")
    case = _case(tmp_path, workspace, geometry="wing.fsm")
    with pytest.raises(CampaignConfigError) as caught:
        _render(case)
    name = table.split("]")[0].lstrip("[")
    assert f"[{name}]" in str(caught.value) and "wing.fsm" in str(caught.value), caught.value


def test_a_surface_the_sidecar_does_not_name_is_refused_listing_the_names(tmp_path):
    """Detection by surface cites the sidecar's names exactly, never by position."""
    workspace = _library(tmp_path, '[trailing_edges]\ndetect = { surfaces = ["Wng"] }\n')
    with pytest.raises(CampaignConfigError) as caught:
        _render(_case(tmp_path, workspace))
    assert "'Wng'" in str(caught.value) and "'Wing'" in str(caught.value), caught.value


def test_the_file_route_beside_an_operation_that_moves_the_body_is_refused(tmp_path):
    """The points name edges of the file as written; a scale would carry them away."""
    scale = '\n[[import.operations]]\nop = "scale"\nfactors = [2.0, 2.0, 2.0]\n'
    workspace = _library(tmp_path, FILE_ROUTE + scale)
    with pytest.raises(CampaignConfigError) as caught:
        _render(_case(tmp_path, workspace))
    message = str(caught.value)
    assert "operation 1 (scale)" in message and "wing.te.txt" in message, message


def test_the_two_options_emit_their_detection_only_when_written(tmp_path):
    """No option written, no option emitted; each written one emits its command."""
    bare = _render(_case(tmp_path, _library(tmp_path, DETECT_AUTO)))
    assert "WAKE_TERMINATION_NODES" not in bare and "BASE_REGIONS" not in bare, bare
    other = tmp_path / "options"
    other.mkdir()
    tables = DETECT_AUTO + '\n[wake_termination]\ndetect = "auto"\n'
    lines = _render(_case(other, _library(other, tables))).splitlines()
    detected = lines.index("AUTO_DETECT_TRAILING_EDGES")
    assert lines[detected + 1] == "AUTO_DETECT_WAKE_TERMINATION_NODES", lines


# --- the wake termination of the file route waits for an initialisation (T07) -----------


def _initialization_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Each ``INITIALIZE_SOLVER`` of a render: its line and its lines up to the blank one."""
    return [
        (at, lines[at : lines.index("", at)])
        for at, line in enumerate(lines)
        if line == "INITIALIZE_SOLVER"
    ]


def _assert_detected_between_two_initializations(lines: list[str], marks: list[str]) -> None:
    """The T07 order: import, first initialisation, detection, the same initialisation again."""
    blocks = _initialization_blocks(lines)
    assert len(blocks) == 2, (
        f"the file route initialises the solver {len(blocks)} time(s); it must initialise, "
        "detect the wake-termination nodes and initialise again, because before an "
        "initialisation the detection finds nothing on edges imported from a file"
    )
    (first_at, first), (second_at, second) = blocks
    assert first == second, (
        f"the first initialisation {first} is not the final one {second}; the second clears "
        "the first, so the first must be the same setting and nothing of its own"
    )
    between = [line for line in lines[first_at + len(first) : second_at] if line]
    assert between == marks, (
        f"between the two initialisations the script carries {between}, and the "
        f"wake-termination detection {marks} is the one thing that belongs there"
    )
    before = [line for line in lines[:first_at] if "WAKE_TERMINATION_NODES" in line]
    assert not before, f"a detection before the first initialisation marks nothing: {before}"
    imported = [at for at, line in enumerate(lines) if line.startswith("IMPORT_WAKE_EDGES")]
    assert imported and imported[0] < first_at, "the edges are imported before any initialisation"
    started = [at for at, line in enumerate(lines) if line == "START_SOLVER"]
    assert started and started[0] > second_at, (
        "the solver starts before the second initialisation, so it solves without the "
        "wake-termination nodes the detection marked"
    )


@pytest.mark.parametrize(
    ("detect", "marks"),
    [
        ('"auto"', ["AUTO_DETECT_WAKE_TERMINATION_NODES"]),
        ('{ surfaces = ["Wing"] }', ["DETECT_WAKE_TERMINATION_NODES_BY_SURFACE 1"]),
    ],
    ids=["auto", "by-surface"],
)
def test_the_file_route_detects_its_wake_termination_between_two_initializations(
    tmp_path, detect, marks
):
    """G02, T07 on 26.124. Run right after an import from a file, the termination
    detection marks nothing; run after the initialisation it marks the node, which
    the solver, initialised without it, does not use until it initialises again (the
    log reports the trailing-edge groups only during an initialisation, the inferred
    reason). So the file route initialises, detects, and initialises again with the
    same settings, then starts the solver."""
    tables = FILE_ROUTE + f"\n[wake_termination]\ndetect = {detect}\n"
    lines = _render(_case(tmp_path, _library(tmp_path, tables))).splitlines()
    _assert_detected_between_two_initializations(lines, marks)


@pytest.mark.parametrize(
    "tables",
    [DETECT_AUTO + '\n[wake_termination]\ndetect = "auto"\n', FILE_ROUTE],
    ids=["detection-route-with-wake-termination", "file-route-without-wake-termination"],
)
def test_a_script_with_nothing_waiting_for_an_initialization_initializes_once(tmp_path, tables):
    """The detection route marks the ends with the edges it detects, before the
    initialisation, and a file route with no ``[wake_termination]`` has nothing to
    detect: each initialises once, as before (the goldens pin the bytes)."""
    lines = _render(_case(tmp_path, _library(tmp_path, tables))).splitlines()
    assert lines.count("INITIALIZE_SOLVER") == 1, lines
    marks = [at for at, line in enumerate(lines) if "WAKE_TERMINATION_NODES" in line]
    assert all(at < lines.index("INITIALIZE_SOLVER") for at in marks), lines


def _unsteady(case, run_type: str):
    """The raw-mesh case as a row of an unsteady run type, the steady row's own keys dropped."""
    variables = {k: v for k, v in case.variables.items() if k not in ("OUTPUTS", "RECIPE")}
    variables[WORKFLOW_KEY] = run_type
    if run_type == "unsteady":
        variables.update(DELTA_TIME="0.01", TIME_ITERATIONS="12", LAST_ITERS_AVG="6")
        return case.model_copy(update={"recipe": run_type, "variables": variables})
    variables.update(
        RPM="1200",
        ROTOR_AXIS="X",
        BLADES="1",
        DELTA_TIME="0.0001",
        TIME_ITERATIONS="720",
        LAST_REVS_AVG="0.25",
    )
    rotor = FIXTURE_ROTOR.model_copy(update={"families_blades": ["Wing"]})
    return case.model_copy(
        update={"recipe": run_type, "variables": variables, "rotors": {rotor.alias: rotor}}
    )


def _steady_job(case, *, cold: bool) -> Script:
    points = [
        case.model_copy(
            update={
                "point": {"alpha": alpha},
                "outputs": [name.replace("a+00.0", f"a{alpha:+05.1f}") for name in case.outputs],
            }
        )
        for alpha in (0.0, 2.0)
    ]
    script = Script("26.124")
    build_steady_sweep(points, script, cold=cold)
    return script


@pytest.mark.parametrize(
    "run_type",
    ["steady", "steady-job-warm", "steady-job-cold", "unsteady", "unsteady_rotor"],
)
def test_every_run_type_on_the_file_route_detects_between_two_initializations(tmp_path, run_type):
    """G02, T07: every run type that imports a raw mesh takes the same order, a steady
    row of several points (one job, warm or cold) included; its points begin after
    the second initialisation, so each solves with the node marked."""
    tables = FILE_ROUTE + '\n[wake_termination]\ndetect = "auto"\n'
    case = _case(tmp_path, _library(tmp_path, tables))
    if run_type.startswith("steady-job"):
        script = _steady_job(case, cold=run_type.endswith("cold"))
    else:
        script = Script("26.124")
        build_script(case if run_type == "steady" else _unsteady(case, run_type), script)
    _assert_detected_between_two_initializations(
        script.render().splitlines(), ["AUTO_DETECT_WAKE_TERMINATION_NODES"]
    )


def test_a_continuation_of_a_file_route_row_marks_nothing_and_initializes_once(tmp_path):
    """A continuation reopens the simulation the stopped run saved, which carries the
    edges and the node that run marked, so it imports nothing and detects nothing."""
    tables = FILE_ROUTE + '\n[wake_termination]\ndetect = "auto"\n'
    case = _unsteady(_case(tmp_path, _library(tmp_path, tables)), "unsteady")
    case.variables.update(
        RESTART="{FINISH_PENDING}", RESTART_FROM="stopped.fsm", RESTART_ITERATIONS="6"
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    assert lines[:3] == ["OPEN", "stopped.fsm", "LOAD_SOLVER_INITIALIZATION ENABLE"], lines[:3]
    marking = [line for line in lines if "IMPORT" in line or "WAKE_TERMINATION_NODES" in line]
    assert not marking, lines
    assert lines.count("INITIALIZE_SOLVER") == 1, lines


def test_base_regions_declared_by_the_sidecar_and_by_the_row_is_refused(tmp_path):
    """The sidecar's detection marks every base; the row's key would mark one again."""
    tables = DETECT_AUTO + '\n[base_regions]\ndetect = "auto"\n'
    workspace = _library(tmp_path, tables)
    case = _case(tmp_path, workspace, tail=" / BASE_REGIONS: Wing")
    with pytest.raises(CampaignConfigError) as caught:
        _render(case)
    assert "[base_regions]" in str(caught.value) and "BASE_REGIONS" in str(caught.value)


# --- the whole path: the row, the node file, the import and the solver's count ---------

#: The stand-in for the solver: it reads the node file the import line names
#: (proof it existed when the solver started), writes the exports the script
#: asks for, and writes the log it is handed where EXPORT_LOG asks.
STUB = """
import pathlib, sys
lines = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
log = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
for index, line in enumerate(lines):
    if line.startswith("IMPORT_WAKE_EDGES_FROM_FILE"):
        node = pathlib.Path(lines[index + 1]).read_text(encoding="utf-8")
        pathlib.Path("node_file_seen.txt").write_text(node, encoding="utf-8")
    if line == "EXPORT_SOLVER_ANALYSIS_SPREADSHEET":
        pathlib.Path(lines[index + 1]).write_text("LOADS", encoding="utf-8")
    if line == "EXPORT_LOG":
        pathlib.Path(lines[index + 1]).write_text(log, encoding="utf-8")
"""


class _Solver(LocalExecutor):
    def __init__(self, stub: Path, log: Path):
        super().__init__(fs_exe=sys.executable, hidden=True)
        self.stub, self.log = stub, log

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, str(self.stub), str(script_path), str(self.log)]


def _converged_reading_the_exported_log(case, execution, sim_dir):
    """The assessor's verdict, naming the exported log as the one it read."""
    log = next(Path(name).name for name in case.outputs if name.endswith("_log.txt"))
    return Assessment(
        status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6, log_file_used=log
    )


@pytest.mark.parametrize(
    ("imported", "status"),
    [(16, RunStatus.CONVERGED), (15, RunStatus.FAILED_SCRIPT)],
    ids=["every-point-imported", "one-point-dropped"],
)
def test_a_file_route_row_runs_end_to_end_and_is_held_to_the_solver_count(
    tmp_path, imported, status
):
    """Through run_matrix: the node file is written before the solver, the import is
    emitted, and the solver's logged count against the 16 points written decides."""
    workspace = _library(tmp_path, FILE_ROUTE)
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp_path / "log_to_write.txt"
    log.write_text(f"{imported} trailing edges imported for boundary Wing\n", encoding="utf-8")
    try:
        run_matrix(
            _matrix(tmp_path),
            workspace,
            name="matrix",
            default_fs_version="26.124",
            recipes=RECIPES,
            assess=_converged_reading_the_exported_log,
            executor=_Solver(stub, log),
            recipe_registry=workflow_registry(),
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    assert record.status is status, (record.status, record.error)
    if status is RunStatus.FAILED_SCRIPT:
        assert "16" in record.error and "15" in record.error, record.error
    # The stand-in writes where it runs, the point's own folder since 0.27.0.
    sim_dir = workspace.sim_dir("7001") / "datapoints" / f"DP-{record.point_name}"
    seen = (sim_dir / "node_file_seen.txt").read_text(encoding="utf-8").splitlines()
    assert seen[:3] == ["16", "0,0,0", "1.0,-3.75,0.0"] and len(seen) == 18, seen
    assert "wing.wake_nodes.txt" in record.inputs_sha256


def _residual_log(line: str) -> str:
    """A recorded solver log with ``line`` printed before its residual table.

    The residual table is the recorded 26.120 one; its identity line is put as
    26.124 prints it (CMP-26124_2026-09-24), because the run's identity pre-flight
    reads the log the stand-in writes and refuses a build other than the row's.
    """
    fixture = Path(__file__).parent / "fixtures" / "log_residuals_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    anchor = "script.txt\n"
    assert anchor in text and "build #7012026" in text, "the fixture moved"
    text = text.replace("build #7012026", "build #8172026", 1)
    return text.replace(anchor, f"{anchor}\n{line}\n", 1)


@pytest.mark.parametrize(
    ("imported", "status"),
    [(16, RunStatus.CONVERGED), (15, RunStatus.FAILED_SCRIPT)],
    ids=["every-point-imported", "one-point-dropped"],
)
def test_a_file_route_row_judged_by_an_assessor_that_names_no_log_reads_the_exported_one(
    tmp_path, imported, status
):
    """A caller's assessor answers with a status and need not say which file it read.
    The count is then read from the log the package's own assessor would find among
    the collected outputs, so 16 of 16 keeps the verdict and 15 is FAILED_SCRIPT;
    neither is the FAILED_INCOMPLETE_OUTPUT of a log that was collected and unread."""
    workspace = _library(tmp_path, FILE_ROUTE)
    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp_path / "log_to_write.txt"
    line = f"{imported} trailing edges imported for boundary Wing"
    log.write_text(_residual_log(line), encoding="utf-8")

    def names_no_log(case, execution, sim_dir):
        return Assessment(status=RunStatus.CONVERGED, iterations=120, residual=3.2e-6)

    try:
        run_matrix(
            _matrix(tmp_path),
            workspace,
            name="matrix",
            default_fs_version="26.124",
            recipes=RECIPES,
            assess=names_no_log,
            executor=_Solver(stub, log),
            recipe_registry=workflow_registry(),
        )
    except CampaignErrors:
        pass  # a failed point is recorded in the manifest, which is what is read
    (record,) = workspace.read_manifest()
    assert record.status is status, (record.status, record.error)
    if status is RunStatus.FAILED_SCRIPT:
        assert "16" in record.error and "15" in record.error, record.error


class _Launches(_Solver):
    """The stand-in, counting every script it is asked to run."""

    def __init__(self, stub: Path, log: Path):
        super().__init__(stub, log)
        self.launched: list[Path] = []

    def _argv(self, script_path: Path) -> list[str]:
        self.launched.append(script_path)
        return super()._argv(script_path)


def _plan(tmp_path, workspace, **matrix):
    return plan_matrix(
        _matrix(tmp_path, **matrix),
        workspace,
        name="matrix",
        default_fs_version="26.124",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        write_plan=False,
    )


def test_a_file_route_row_that_turns_its_log_export_off_is_refused_before_any_launch(tmp_path):
    """EXPORT_LOG: false in the row leaves the declared log with nothing to write it.
    The script then exports no log, the count the run is held to cannot be read, and
    the point would be FAILED_INCOMPLETE_OUTPUT after the seat. The plan reads the
    script it built, refuses the point, and run_matrix, whose pre-flight is that
    plan, launches nothing and records nothing."""
    workspace = _library(tmp_path, FILE_ROUTE)
    (blocked,) = _plan(tmp_path, workspace, tail=" / EXPORT_LOG: false").blocked
    for needle in ("EXPORT_LOG", "trailing", "native_log"):
        assert needle in blocked.error, f"the refusal does not name {needle!r}: {blocked.error}"

    stub = tmp_path / "stub_solver.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp_path / "log_to_write.txt"
    log.write_text(_residual_log(_SIXTEEN_ON_WING), encoding="utf-8")
    solver = _Launches(stub, log)
    with pytest.raises(MatrixError, match="nothing was executed"):
        run_matrix(
            _matrix(tmp_path, tail=" / EXPORT_LOG: false"),
            workspace,
            name="matrix",
            default_fs_version="26.124",
            recipes=RECIPES,
            assess=_converged_reading_the_exported_log,
            executor=solver,
            recipe_registry=workflow_registry(),
        )
    assert solver.launched == []
    assert not workspace.manifest_path.is_file() or workspace.read_manifest() == []


def test_a_file_route_row_that_exports_its_log_plans(tmp_path):
    """The control: the same row without the switch plans READY."""
    workspace = _library(tmp_path, FILE_ROUTE)
    plan = _plan(tmp_path, workspace)
    assert [point.status for point in plan.points] == [PlanStatus.READY], plan.summary()


def test_a_file_route_row_is_submitted_where_the_machine_writes_its_own_log(tmp_path):
    """The machine's profile turns EXPORT_LOG off and names the log its scheduler
    writes, which collect copies to the declared name, where the count is read. That
    is a log the run reads, so the file-route row is submitted, holding its 16 points,
    and its script carries no EXPORT_LOG."""
    workspace = _library(tmp_path, FILE_ROUTE)
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(NATIVE_LOG_PROFILE + NATIVE_LOG_TABLE, encoding="utf-8")
    executor = SubmittingExecutor(read_hpc_profile(profile), values={}, submit=False)
    (record,) = run_matrix(
        _matrix(tmp_path),
        workspace,
        name="matrix",
        default_fs_version="26.124",
        recipes=RECIPES,
        assess=_converged_reading_the_exported_log,
        executor=executor,
        recipe_registry=workflow_registry(),
    )
    assert record.status is RunStatus.SUBMITTED, (record.status, record.error)
    assert record.submission["wake_edge_points"] == 16, record.submission
    script = workspace.sim_dir("7001") / record.script_path
    assert "EXPORT_LOG" not in script.read_text(encoding="utf-8").splitlines()


# --- the node file is the run's own, never a file of the input library (G02) ----------


def _submitting(workspace) -> SubmittingExecutor:
    """An executor of a machine whose scheduler writes the log, that submits nothing.

    Each job is written and left as if queued, which is the window in which a
    later submission could replace a file the queued job has yet to read.
    """
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(NATIVE_LOG_PROFILE + NATIVE_LOG_TABLE, encoding="utf-8")
    return SubmittingExecutor(read_hpc_profile(profile), values={}, submit=False)


def _named_node_file(workspace, record) -> Path:
    """The node file a record's script names, on the line after its import line."""
    script = workspace.sim_dir(record.sim_id) / record.script_path
    lines = script.read_text(encoding="utf-8").splitlines()
    (at,) = [i for i, line in enumerate(lines) if line.startswith("IMPORT_WAKE_EDGES_FROM_FILE")]
    return Path(lines[at + 1])


def _points_in(node_file: Path) -> list[tuple[float, ...]]:
    """The mid-points a node file holds, after its count and its placeholder line."""
    rows = node_file.read_text(encoding="utf-8").splitlines()[2:]
    return [tuple(float(value) for value in row.split(",")) for row in rows]


def _real(path: Path) -> Path:
    """Where ``path`` is on disk, through every link and junction on the way."""
    return Path(os.path.realpath(path))


@pytest.mark.parametrize("sweep", ["0.0", "0.0,2.0"], ids=["one-point", "a-steady-job"])
def test_two_queued_cases_on_one_mesh_each_keep_the_edges_they_declared(tmp_path, sweep):
    """G02. Two cases on one mesh, each stating half the span in Python, are
    submitted and left queued: one point each, or one steady job of two points
    each. Staging links each simulation's inputs to the library folder of the
    mesh, so a node file named beside the staged geometry is ONE file for both,
    and the second submission replaced the first's selection before its job
    read it, with the same count, so the count check could not tell. Each job's
    script must name a file of its own run folder holding its own points, and
    each record must hash the bytes its job reads."""
    workspace = _library(tmp_path, FILE_ROUTE)
    matrix = write_matrix(
        tmp_path / "raw_mesh.fs",
        [
            ROW.format(build="26.124", outputs=WITH_LOG, geometry="wing.stl", tail="").replace(
                "| AL | 0.0 |", f"| AL | {sweep} |"
            )
        ],
    )
    resolved = resolve_matrix(
        matrix, workspace, name="matrix", fs_version="26.124", recipes=RECIPES
    )
    (case,) = resolved.campaign.sims
    marking = case.raw_mesh_conditions.trailing_edges
    halves = {
        "7001": tuple(point for point in MIDPOINTS if point[1] < 0),
        "7002": tuple(point for point in MIDPOINTS if point[1] > 0),
    }
    cases = []
    for sim_id, points in halves.items():
        stated = marking.model_copy(update={"points_m": points})
        conditions = case.raw_mesh_conditions.model_copy(update={"trailing_edges": stated})
        cases.append(case.model_copy(update={"sim_id": sim_id, "raw_mesh_conditions": conditions}))
    library = _real(workspace.inputs_dir / "geometries")
    held_before = sorted(path.name for path in library.iterdir())
    records = run_campaign(
        resolved.campaign.model_copy(update={"sims": cases}),
        _submitting(workspace),
        workspace,
        assess=_converged_reading_the_exported_log,
        recipes=workflow_registry(),
        quiet=True,
    )
    assert sorted(record.sim_id for record in records) == ["7001", "7002"], records
    for record in records:
        assert record.status is RunStatus.SUBMITTED, (record.status, record.error)
        named = _named_node_file(workspace, record)
        held = _points_in(named)
        assert held == list(halves[record.sim_id]), (
            f"sim {record.sim_id}'s job names {named}, which holds the points of y from "
            f"{held[0][1]} to {held[-1][1]}, and the case declared y from "
            f"{halves[record.sim_id][0][1]} to {halves[record.sim_id][-1][1]}"
        )
        assert _real(named).is_relative_to(_real(workspace.sim_dir(record.sim_id))), (
            f"sim {record.sim_id}'s node file {named} is on disk at {_real(named)}, "
            "outside its own simulation folder"
        )
        assert not _real(named).is_relative_to(library), _real(named)
        digest = hashlib.sha256(named.read_bytes()).hexdigest()
        assert record.inputs_sha256[named.name] == digest, record.inputs_sha256
    held_after = sorted(path.name for path in library.iterdir())
    assert held_after == held_before, f"a run wrote into the input library: {held_after}"


def test_a_points_file_named_like_the_node_file_is_left_as_its_author_wrote_it(tmp_path):
    """G02. The sidecar may name its points file ``wing.wake_nodes.txt``, the name
    the run gives its node file. The points file is the author's, with its unit
    line, and a run writes nothing into the library that holds it."""
    table = '[trailing_edges]\nfile = "wing.wake_nodes.txt"\n'
    workspace = _library(tmp_path, table)
    authored = workspace.inputs_dir / "geometries" / "wing.wake_nodes.txt"
    authored.write_text(_points_text(), encoding="utf-8")
    before = authored.read_bytes()
    (record,) = run_matrix(
        _matrix(tmp_path),
        workspace,
        name="matrix",
        default_fs_version="26.124",
        recipes=RECIPES,
        assess=_converged_reading_the_exported_log,
        executor=_submitting(workspace),
        recipe_registry=workflow_registry(),
    )
    assert record.status is RunStatus.SUBMITTED, (record.status, record.error)
    assert authored.read_bytes() == before, (
        "the run wrote over the author's points file: it now starts "
        f"{authored.read_text(encoding='utf-8').splitlines()[:2]}"
    )
    assert _points_in(_named_node_file(workspace, record)) == MIDPOINTS


if __name__ == "__main__":  # pragma: no cover - the golden writer, run by hand
    import tempfile

    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: python -m tests.tier1_offline.test_raw_mesh_conditions --write")
    GOLDENS.mkdir(parents=True, exist_ok=True)
    for golden, body in (
        ("te_file__26.124", FILE_ROUTE),
        ("te_detect_auto__26.124", DETECT_AUTO),
        ("te_detect_by_surface_with_wake_and_base__26.124", DETECT_BY_SURFACE_WITH_WAKE_AND_BASE),
        ("te_file_with_wake_and_base__26.124", FILE_ROUTE_WITH_WAKE_AND_BASE),
    ):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            text = _normalized(_render(_case(root, _library(root, body))), root)
        (GOLDENS / f"{golden}.txt").write_bytes(text.encode("utf-8"))
        print(f"wrote {golden}.txt")
