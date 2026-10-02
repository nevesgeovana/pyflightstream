"""The probe specification catalog, one entry per database command.

Pipeline role: encodes how each FlightStream command is probed (what
minimal session state it needs, how it is emitted with distinctive
values, and which observable effect proves it acted). Instruments and
tokens are pinned from real 26.120 runs (reports/compat, HND-011
recon): the settings sheet header of EXPORT_PROBE_POINTS reflects the
solver settings even before initialization; OUTPUT_SETTINGS_AND_STATUS
dumps the fluid state always and the solver state once initialized;
object names (coordinate systems, actuators) survive as readable text
in a SAVEAS file, while numeric fields do not; OPEN, INITIALIZE_SOLVER
and START_SOLVER print distinctive log messages.

Assertion strictness follows the evidence rules: strict assertions
(absence is ``broken``) only where the instrument is recon-proven to
expose the state; everywhere else the assertion returns None and the
command lands ``unprobed``, because a probe may never guess. Three
commands carry no specification yet, each needing an input-file fixture:
SET_PROP_ACTUATOR_PROFILE, whose file form 26.124 reads was measured by a
licensed probe outside this catalog (RPT-070), and the two FSI commands,
whose input-file format awaits a manual pass.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from pyflightstream.qa.geometry import WingSpec, generate_wing_stl, wing_triangles
from pyflightstream.qa.probes import (
    ProbeArtifacts,
    Requires,
    dump_gained,
    emit_solver_setup,
    file_effect,
    fsm_changed,
    fsm_gained,
    printed_line,
    region_printed,
)
from pyflightstream.results import imported_trailing_edges
from pyflightstream.script import Script
from pyflightstream.script.helpers import initialize_solver, render_wake_edge_node_file

#: The catalog exports its catalog and nothing else. Without this, every
#: non-underscore definition here is public the moment the wheel ships,
#: which would make three effect-assertion helpers of this module part
#: of the supported surface by accident (the rule is stated in
#: tests/tier1_offline/test_exceptions_catalog.py: an absent __all__ means the module
#: declares none, and then every top-level name is public).
__all__ = ["PROBE_SPECS"]

# The shared instruments and the registry are in _spec_kit; the second
# part of the catalog is imported last, so it registers after this one.
from pyflightstream.qa._spec_kit import (  # noqa: E402
    _NESTED_NAME,
    PROBE_SPECS,
    _emit,
    _named_frame,
    _read,
    _saveas,
    _seq,
    _sheet,
    _spec,
    _unobservable,
    fsm_grep,
    region_printed_lax,
    sheet_matches,
)

# --- script controls (SRC-003 p.281), the pilot family -----------------


def _run_script_target(script: Script, workdir: Path) -> None:
    # The nested file is fixed probe support data (a single PRINT), not
    # emitted through a builder: it must exist on disk before the run.
    nested = workdir / _NESTED_NAME
    nested.write_text(
        "# nested script for the RUN_SCRIPT probe\nPRINT PYFS_EFFECT_NESTED\n",
        encoding="utf-8",
    )
    script.emit("RUN_SCRIPT", nested)


_spec(
    command="PRINT",
    build_target=_emit("PRINT", "PYFS_EFFECT_PRINT"),
    assert_effect=region_printed("PYFS_EFFECT_PRINT"),
    effect_note="the probe message PYFS_EFFECT_PRINT appears as a log line of its own",
)
_spec(
    command="STOP",
    build_target=_emit("STOP"),
    expects_halt=True,
    effect_note="script processing halts at STOP",
    timeout_s=60.0,
)
_spec(
    command="RUN_SCRIPT",
    build_target=_run_script_target,
    assert_effect=lambda artifacts: printed_line(artifacts.target_region(), "PYFS_EFFECT_NESTED"),
    effect_note=(
        "the nested script's message PYFS_EFFECT_NESTED appears in the log, so the "
        "called script really ran"
    ),
)


# --- file io (SRC-003 pp.282-283) --------------------------------------


def _open_reopen_target(script: Script, workdir: Path) -> None:
    script.emit("OPEN", workdir / "reopen.fsm")


def _new_sim_effect(artifacts: ProbeArtifacts) -> bool | None:
    saved = artifacts.workdir / "after_new.fsm"
    if not saved.is_file():
        return None
    return saved.stat().st_size < 100_000


_spec(
    command="OPEN",
    build_target=_open_reopen_target,
    prelude=lambda script, workdir: script.emit("SAVEAS", workdir / "reopen.fsm"),
    assert_effect=region_printed("Simulation file opened"),
    effect_note=(
        "the log confirms 'Simulation file opened' for a file the probe saved just before"
    ),
)
_spec(
    command="SAVEAS",
    build_target=lambda script, workdir: script.emit("SAVEAS", workdir / "saveas_target.fsm"),
    assert_effect=file_effect("saveas_target.fsm"),
    effect_note="the simulation file the command names exists and is not empty",
)
_spec(
    command="NEW_SIMULATION",
    build_target=_emit("NEW_SIMULATION"),
    requires=Requires.SIM,
    epilogue=lambda script, workdir: script.emit("SAVEAS", workdir / "after_new.fsm"),
    assert_effect=_new_sim_effect,
    effect_note=(
        "after NEW_SIMULATION on an opened 582 kB simulation, the session saved by the "
        "epilogue is below 100 kB (the geometry is gone)"
    ),
)
_spec(
    command="CLOSE_FLIGHTSTREAM",
    build_target=_emit("CLOSE_FLIGHTSTREAM"),
    expects_halt=True,
    effect_note="script processing ends at CLOSE_FLIGHTSTREAM and the solver exits",
    timeout_s=60.0,
)
_spec(
    command="EXPORT_LOG",
    build_target=lambda script, workdir: script.emit("EXPORT_LOG", workdir / "target_log.txt"),
    assert_effect=file_effect("target_log.txt"),
    effect_note="the log file the command names exists and is not empty",
)
_spec(
    command="OUTPUT_SETTINGS_AND_STATUS",
    build_target=lambda script, workdir: script.emit(
        "OUTPUT_SETTINGS_AND_STATUS", workdir / "target_dump.txt"
    ),
    assert_effect=file_effect("target_dump.txt"),
    effect_note="the settings file the command names exists and is not empty",
)


# --- simulation controls (SRC-003 p.328) -------------------------------


def _units_epilogue(script: Script, workdir: Path) -> None:
    emit_solver_setup(script)
    initialize_solver(script)
    script.emit("OUTPUT_SETTINGS_AND_STATUS", workdir / "dump_epilogue.txt")


def _units_effect(artifacts: ProbeArtifacts) -> bool | None:
    dump = _read(artifacts.workdir, "dump_epilogue.txt")
    if dump is None:
        return None
    return True if ",cm" in dump else None


_spec(
    command="SET_SIMULATION_LENGTH_UNITS",
    build_target=_emit("SET_SIMULATION_LENGTH_UNITS", "CENTIMETER"),
    requires=Requires.SIM,
    epilogue=_units_epilogue,
    assert_effect=_units_effect,
    effect_note="the initialized settings dump reports lengths in cm",
)


# --- coordinate systems (SRC-003 pp.329-331) ---------------------------

_spec(
    command="CREATE_NEW_COORDINATE_SYSTEM",
    build_target=_emit("CREATE_NEW_COORDINATE_SYSTEM"),
    epilogue=_seq(_named_frame("PYFS_CREATED_FRAME"), _saveas),
    assert_effect=fsm_grep("PYFS_CREATED_FRAME"),
    effect_note=(
        "the epilogue names the created frame and the name is readable in the saved "
        "simulation file (via EDIT_COORDINATE_SYSTEM, whose own probe disambiguates)"
    ),
)


_CREATE_FRAME_PRELUDE = _emit("CREATE_NEW_COORDINATE_SYSTEM")

_spec(
    command="EDIT_COORDINATE_SYSTEM",
    build_target=lambda script, workdir: script.emit(
        "EDIT_COORDINATE_SYSTEM",
        frame=2,
        name="PYFS_EDITED_FRAME",
        origin_x=0.1,
        origin_y=0.0,
        origin_z=0.0,
        vector_x_x=1.0,
        vector_x_y=0.0,
        vector_x_z=0.0,
        vector_y_x=0.0,
        vector_y_y=1.0,
        vector_y_z=0.0,
        vector_z_x=0.0,
        vector_z_y=0.0,
        vector_z_z=1.0,
    ),
    prelude=_CREATE_FRAME_PRELUDE,
    epilogue=_saveas,
    assert_effect=fsm_grep("PYFS_EDITED_FRAME"),
    effect_note="the frame name set by the command is readable in the saved simulation file",
)
_spec(
    command="SET_COORDINATE_SYSTEM_ORIGIN",
    build_target=_emit("SET_COORDINATE_SYSTEM_ORIGIN", 2, 0.5511, 0.1, 0.2, "METER"),
    prelude=_CREATE_FRAME_PRELUDE,
    save_state=True,
    assert_effect=fsm_gained("0.5511", "0.1", "0.2"),
    effect_note=("the saved simulation carries the distinctive frame origin"),
)
_spec(
    command="SET_COORDINATE_SYSTEM_AXIS",
    build_target=_emit("SET_COORDINATE_SYSTEM_AXIS", 2, "X", 0.28, 0.96, 0.0, "FALSE"),
    prelude=_CREATE_FRAME_PRELUDE,
    save_state=True,
    assert_effect=fsm_gained("0.28", "0.96"),
    effect_note=(
        "the saved simulation carries the axis direction 0.28, 0.96, which is stored "
        "unchanged because it is already a unit vector. THE SOLVER NORMALISES THE "
        "DIRECTION WHATEVER THE NORMALIZE FLAG SAYS: this probe first passed "
        "0.61234, 0.79012 with the flag FALSE and the file stored that vector divided "
        "by its magnitude, to all seventeen digits (RPT-020). A unit vector is used "
        "so the value asserted is the value passed"
    ),
)


# --- boundary conditions (SRC-003 pp.319-328) --------------------------

_spec(
    command="AUTO_DETECT_TRAILING_EDGES",
    build_target=_emit("AUTO_DETECT_TRAILING_EDGES"),
    requires=Requires.SIM,
    assert_effect=region_printed_lax("trailing edge"),
    effect_note=(
        "a line of the target region naming trailing edges, which detection prints as "
        "N trailing edges marked on surface <name>; INITIALIZE_SOLVER alone marks no "
        "trailing edge and prints no such line, measured on 26.124 (RPT-065). A silent "
        "region is unprobed: the saved-state reader of RPT-065, the instrument that "
        "separates what detection and initialisation mark, is not this probe's "
        "assertion yet"
    ),
)
_spec(
    command="SET_TRAILING_EDGE_TYPE",
    build_target=_emit("SET_TRAILING_EDGE_TYPE", 1, "RELAXED"),
    requires=Requires.SIM,
    prelude=_emit("AUTO_DETECT_TRAILING_EDGES"),
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the trailing-edge type"),
)
_spec(
    command="DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
    build_target=_emit("DISABLE_WAKE_NODES_ON_TRAILING_EDGE", 1),
    requires=Requires.SIM,
    prelude=_emit("AUTO_DETECT_TRAILING_EDGES"),
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the wake-node state"),
)
_spec(
    command="AUTO_DETECT_WAKE_TERMINATION_NODES",
    build_target=_emit("AUTO_DETECT_WAKE_TERMINATION_NODES"),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    save_state=True,
    effect_note=(
        "the saved simulation does not move on the probe geometry (RPT-020); a "
        "clean synthetic wing may simply have no wake termination nodes to find, "
        "so this needs a geometry that does"
    ),
)

#: The wing the wake-edge import probe marks: the qa wing at the tier-3 10_WING
#: resolution, 16 spanwise panels, so its trailing edge is 16 mesh edges along
#: x = 1, z = 0, one every half metre of span. Named Wing, which is the boundary
#: the solver's import line names.
_WAKE_EDGE_WING = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=16)
_WAKE_EDGE_STL = "wake_wing.stl"
_WAKE_EDGE_NODES = "wake_wing.wake_nodes.txt"


def _wing_trailing_edge_midpoints(spec: WingSpec) -> list[tuple[float, float, float]]:
    """Return the mid-points of a qa wing's trailing-edge mesh edges, from its triangles.

    The trailing-edge vertices are those at the chord's aft end, one pair per
    spanwise station (the contour's two ends, a rounding apart in z); each
    trailing-edge edge joins two consecutive stations, so its mid-point is the
    mean of theirs.
    """
    vertices = wing_triangles(spec).reshape(-1, 3)
    aft = vertices[vertices[:, 0] == vertices[:, 0].max()]
    stations = sorted({float(y) for y in aft[:, 1]})
    points = []
    for near, far in zip(stations[:-1], stations[1:], strict=True):
        pair = aft[(aft[:, 1] == near) | (aft[:, 1] == far)]
        # Rounded to 1e-12 m, far inside the import's tolerance, so the two
        # contour ends' z of order 1e-17 average to the 0.0 they stand for.
        points.append(
            (
                round(float(pair[:, 0].mean()), 12),
                round((near + far) / 2.0, 12),
                round(float(pair[:, 2].mean()), 12),
            )
        )
    return points


def _wake_edge_wing_prelude(script: Script, workdir: Path) -> None:
    """Import the qa wing as boundary Wing into a new simulation, in metres."""
    stl = generate_wing_stl(_WAKE_EDGE_WING, workdir / _WAKE_EDGE_STL, name="Wing")
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", stl, clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")


def _wake_edge_import_target(script: Script, workdir: Path) -> None:
    """Write the node file of the wing's 16 mid-points and emit the 26.124 import.

    The line is the one ``helpers.mark_wake_edges`` emits: the type, the
    tolerance, the simulation's unit as the third token, and the node file's
    path on the next line (RPT-061); the file is the count, the placeholder
    triple and the mid-points. Emitted through the database grammar, so a
    build whose grammar has no third token refuses to build the probe and
    the command lands unprobed there.
    """
    nodes = workdir / _WAKE_EDGE_NODES
    nodes.write_text(
        render_wake_edge_node_file(_wing_trailing_edge_midpoints(_WAKE_EDGE_WING)),
        encoding="utf-8",
    )
    script.emit("IMPORT_WAKE_EDGES_FROM_FILE", "STANDARD", 0.0001, "METER", nodes)


def _import_lines(artifacts: ProbeArtifacts) -> list[dict[str, int]]:
    """Every import line of the target region, each as ``{boundary: count}``, in order.

    Read by the parser the run reads the count with, one line at a time, so two
    lines on one boundary stay two entries. The judge and the reading both call
    this, so the lines a report records are the lines the verdict was made on.
    """
    lines = artifacts.target_region().splitlines()
    return [found for found in map(imported_trailing_edges, lines) if found]


def _imported_exactly(boundary: str, count: int) -> Callable[[ProbeArtifacts], bool]:
    """Effect: the target region logs exactly one import, ``count`` edges on ``boundary``.

    Strict. Every import line of the region (``N trailing edges imported for
    boundary <name>``, RPT-061) is read with its count and its boundary
    (:func:`_import_lines`), and the whole list is compared with the one import
    the probe wrote. A substring of the line would verify 116 edges, 16 on a
    boundary named ``Winglet``, or a second import beside the first; silence is
    a file that marked nothing.
    """

    def check(artifacts: ProbeArtifacts) -> bool:
        return _import_lines(artifacts) == [{boundary: count}]

    return check


def _import_lines_read(artifacts: ProbeArtifacts) -> str:
    """Return the reading the report records: the import lines the judge compared, as JSON."""
    return "import lines " + json.dumps(_import_lines(artifacts))


_spec(
    command="IMPORT_WAKE_EDGES_FROM_FILE",
    build_target=_wake_edge_import_target,
    prelude=_wake_edge_wing_prelude,
    save_state=True,
    assert_effect=_imported_exactly("Wing", _WAKE_EDGE_WING.n_span),
    observe=_import_lines_read,
    effect_note=(
        "the solver logs one import line, 16 trailing edges imported for boundary Wing, "
        "one per trailing-edge mesh edge of the wing, and no other; it prints the line "
        "only when the import marks something (RPT-061)"
    ),
)
_spec(
    command="SET_FREESTREAM",
    build_target=_emit("SET_FREESTREAM", "CONSTANT"),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    save_state=True,
    effect_note=(
        "the saved simulation does not move (RPT-020). The reading is that CONSTANT "
        "is the state the simulation was already in, which would make the call a "
        "no-op rather than a failure; no page has been found stating the default, so "
        "the entry carries no default_ref and this stays a hypothesis. The CUSTOM and "
        "ROTATION forms await fixtures"
    ),
)
_spec(
    command="FLUID_PROPERTIES",
    build_target=_emit(
        "FLUID_PROPERTIES",
        density=1.179,
        pressure=98765.4,
        temperature=291.55,
        viscosity=0.0000185,
        specific_heat_ratio=1.31,
    ),
    dump_state=True,
    assert_effect=dump_gained("Density,1.179", strict=True),
    effect_note="the settings dump reports the distinctive density 1.179 kg/m^3",
)
_spec(
    command="AIR_ALTITUDE",
    build_target=_emit("AIR_ALTITUDE", 5000.0, "METERS"),
    dump_state=True,
    assert_effect=dump_gained("Density,.736", strict=True),
    # The asserted effect ALONE. This note is stamped verbatim into
    # every report of every build, so a cross-build failure narrative
    # here becomes a sentence the report asserts about builds where it
    # is false: the 26.122 run recorded this command `verified` beside
    # the words "the METERS units argument reads ignored", which the
    # same line's `effect: true` contradicts. Where the defect is real
    # it belongs in the entry's own note in `boundary_conditions.yaml`,
    # which carries it and cites the runs (`PLN-20260810-2000`).
    effect_note=("the settings dump reports the 5000 m standard-atmosphere density (0.736 kg/m^3)"),
)


# --- runtime settings (SRC-003 pp.339-343) -----------------------------


def _sheet_setter(
    command: str,
    value: object,
    pattern: str,
    note: str,
    strict: bool = True,
) -> None:
    _spec(
        command=command,
        build_target=_emit(command, value),
        requires=Requires.SIM,
        epilogue=_sheet,
        assert_effect=sheet_matches(pattern, strict=strict),
        effect_note=note,
    )


_sheet_setter(
    "SOLVER_SET_AOA",
    7.253,
    r"Angle of attack \(Deg\)\s+7\.253",
    "the settings sheet reports the distinctive angle of attack 7.253 deg",
)
_sheet_setter(
    "SOLVER_SET_SIDESLIP",
    3.414,
    r"Side-slip angle \(Deg\)\s+3\.414",
    "the settings sheet reports the distinctive side-slip 3.414 deg",
)
_sheet_setter(
    "SOLVER_SET_VELOCITY",
    51.617,
    r"Freestream velocity \(m/s\)\s+51\.617",
    "the settings sheet reports the distinctive free-stream velocity 51.617 m/s",
)
_sheet_setter(
    "SOLVER_SET_ITERATIONS",
    123,
    r"Requested solver iterations\s+123\b",
    "the settings sheet reports the distinctive iteration count 123",
)
_sheet_setter(
    "SOLVER_SET_CONVERGENCE",
    0.000271828,
    r"Solver convergence limit\s+2\.718E-04",
    "the settings sheet reports the distinctive convergence limit 2.718E-04",
)
_sheet_setter(
    "SOLVER_SET_FORCED_ITERATIONS",
    "ENABLE",
    r"Force solver to run all iterations\s+T\b",
    "the settings sheet reports forced iterations as T",
)
_sheet_setter(
    "SOLVER_SET_REF_VELOCITY",
    47.513,
    r"Reference velocity \(m/s\)\s+47\.513",
    "the settings sheet reports the distinctive reference velocity 47.513 m/s",
)
_sheet_setter(
    "SOLVER_SET_REF_AREA",
    2.727,
    r"Reference area \(m\^2\)\s+2\.727",
    "the settings sheet reports the distinctive reference area 2.727 m^2",
)
_sheet_setter(
    "SOLVER_SET_REF_LENGTH",
    3.131,
    r"Reference length \(m\)\s+3\.131",
    "the settings sheet reports the distinctive reference length 3.131 m",
)
_spec(
    command="SOLVER_SET_MACH_NUMBER",
    build_target=_emit("SOLVER_SET_MACH_NUMBER", 0.213),
    requires=Requires.SOLVER,
    dump_state=True,
    assert_effect=dump_gained("Mach Number,.213", strict=True),
    effect_note="the initialized settings dump reports the distinctive Mach number .213",
)
_spec(
    command="SOLVER_SET_REF_MACH_NUMBER",
    build_target=_emit("SOLVER_SET_REF_MACH_NUMBER", 0.157),
    requires=Requires.SOLVER,
    dump_state=True,
    assert_effect=dump_gained("Reference Mach,.157", strict=True),
    effect_note="the initialized settings dump reports the distinctive reference Mach .157",
)
_spec(
    command="SET_MAX_PARALLEL_THREADS",
    build_target=_emit("SET_MAX_PARALLEL_THREADS", 3),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the thread count"),
)


# --- advanced settings (SRC-003 pp.344-345) ----------------------------

_spec(
    command="SET_SOLVER_CONVERGENCE_ITERATIONS",
    build_target=_emit("SET_SOLVER_CONVERGENCE_ITERATIONS", 37),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_gained("37"),
    effect_note=(
        "the saved simulation carries the distinctive convergence window 37. The value "
        "is 37 rather than the 7 this probe used before instruments reached it: a "
        "single digit matches somewhere in any simulation file"
    ),
)
_spec(
    command="SOLVER_MINIMUM_CP",
    build_target=_emit("SOLVER_MINIMUM_CP", -4.5),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_gained("-4.5"),
    effect_note=("the saved simulation carries the distinctive minimum-Cp floor"),
)


# --- solver settings (SRC-003 pp.339-343) ------------------------------

_spec(
    command="SET_SOLVER_STEADY",
    build_target=_emit("SET_SOLVER_STEADY"),
    requires=Requires.SIM,
    prelude=_emit("SET_SOLVER_UNSTEADY", time_iterations=3, delta_time=0.0123),
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Solver mode:\s+Steady", strict=True),
    effect_note="the settings sheet reports Steady after the prelude set the unsteady mode",
)
_spec(
    command="SET_SOLVER_UNSTEADY",
    build_target=_emit("SET_SOLVER_UNSTEADY", time_iterations=7, delta_time=0.0123),
    requires=Requires.SIM,
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Time increment \(sec\)\s+\.012", strict=True),
    effect_note="the settings sheet reports the distinctive time increment .012 s",
)
_spec(
    command="SET_BOUNDARY_LAYER_TYPE",
    build_target=_emit("SET_BOUNDARY_LAYER_TYPE", "TURBULENT"),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the boundary-layer model choice"),
)
_spec(
    command="SET_SOLVER_VISCOUS_COUPLING",
    build_target=_emit("SET_SOLVER_VISCOUS_COUPLING", "ENABLE"),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the viscous-coupling choice"),
)
_spec(
    command="SET_VISCOUS_EXCLUDED_BOUNDARIES",
    build_target=_emit("SET_VISCOUS_EXCLUDED_BOUNDARIES", 1, [1]),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the viscous exclusion list"),
)


# --- solver initialization (SRC-003 p.337) -----------------------------


def _initialize_target(script: Script, workdir: Path) -> None:
    initialize_solver(script)


_spec(
    command="INITIALIZE_SOLVER",
    build_target=_initialize_target,
    requires=Requires.SIM,
    prelude=lambda script, workdir: emit_solver_setup(script),
    assert_effect=region_printed("Solver initialized"),
    effect_note="the log reports 'Solver initialized' with the mesh statistics",
)
_spec(
    command="SOLVER_PROXIMAL_BOUNDARIES",
    build_target=_emit("SOLVER_PROXIMAL_BOUNDARIES", 1, [1]),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the proximal-boundary marking"),
)
_spec(
    command="REMOVE_INITIALIZATION",
    build_target=_emit("REMOVE_INITIALIZATION"),
    requires=Requires.SOLVER,
    dump_state=True,
    assert_effect=dump_gained("Not initialized", strict=True),
    effect_note=("the settings dump flips from the initialized solver state to 'Not initialized'"),
)
_spec(
    command="START_SOLVER",
    build_target=_emit("START_SOLVER"),
    requires=Requires.SOLVER,
    assert_effect=region_printed("Solver run time"),
    effect_note="the log carries the iteration table and 'Solver run time'",
)
_spec(
    command="CLEAR_SOLUTION",
    build_target=_emit("CLEAR_SOLUTION"),
    requires=Requires.SOLUTION,
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Current solver iteration number:\s+0\b", strict=False),
    effect_note="the settings sheet reports the solver iteration counter back at 0",
)


# --- solver analysis (SRC-003 pp.350-351) ------------------------------


def _inviscid_effect(artifacts: ProbeArtifacts) -> bool | None:
    loads = _read(artifacts.workdir, "loads_inviscid.txt")
    if loads is None:
        return None
    for line in loads.splitlines():
        fields = line.strip().split(",")
        if len(fields) == 10 and fields[0] == "B":
            try:
                return abs(float(fields[6])) < 1e-6
            except ValueError:
                return None
    return None


_spec(
    command="SET_VORTICITY_DRAG_BOUNDARIES",
    build_target=_emit("SET_VORTICITY_DRAG_BOUNDARIES", 1, [1]),
    requires=Requires.SOLUTION,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the vorticity-drag list"),
)
_spec(
    command="DELETE_VORTICITY_DRAG_BOUNDARIES",
    build_target=_emit("DELETE_VORTICITY_DRAG_BOUNDARIES"),
    requires=Requires.SOLUTION,
    prelude=_emit("SET_VORTICITY_DRAG_BOUNDARIES", 1, [1]),
    assert_effect=_unobservable,
    effect_note="the vorticity-drag boundary list is not exposed by any instrument yet",
)
# THE LOADS FRAME AND THE MOMENTS MODEL ARE PROBED BEFORE THE SOLVE, where the
# package emits them since 0.27.0 (B05): both are init-phase commands on the
# evidence of RPT-064, where set after START_SOLVER the frame reached the final
# export and none of the step exports written during the march. The SOLVER tier
# ends at INITIALIZE_SOLVER, so the target lands where a workflow puts it, and
# the frame's epilogue starts the solver BEFORE the sheet: the sheet then says
# whether the frame survived the solve, which is what the step exports rest on,
# rather than only whether the line was accepted.
_spec(
    command="SET_SOLVER_ANALYSIS_LOADS_FRAME",
    build_target=_emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", 2),
    requires=Requires.SOLVER,
    early_prelude=_named_frame("PYFS_FRAME_NAME"),
    epilogue=_seq(_emit("START_SOLVER"), _sheet),
    assert_effect=sheet_matches(r"Coordinate frame for analysis:\s+PYFS_FRAME_NAME", strict=True),
    effect_note=(
        "the settings sheet exported after the solve reports the analysis frame set "
        "before it, by its probe-given name PYFS_FRAME_NAME"
    ),
)
_spec(
    command="SET_ANALYSIS_MOMENTS_MODEL",
    build_target=_emit("SET_ANALYSIS_MOMENTS_MODEL", "VORTICITY"),
    requires=Requires.SOLVER,
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the moments-model choice"),
)
_spec(
    command="SET_ANALYSIS_SYMMETRY_LOADS",
    build_target=_emit("SET_ANALYSIS_SYMMETRY_LOADS", "ENABLE"),
    requires=Requires.SOLVER,
    assert_effect=_unobservable,
    effect_note=(
        "the symmetry-loads toggle is not exposed by any instrument yet; probed "
        "pre-solve since the 2026-07-21 phase correction (the in-solve monitors "
        "consume it)"
    ),
)
_spec(
    command="SET_LOADS_AND_MOMENTS_UNITS",
    build_target=_emit("SET_LOADS_AND_MOMENTS_UNITS", "NEWTONS"),
    requires=Requires.SOLUTION,
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Force Units:\s+(?i:newtons)", strict=False),
    effect_note="the settings sheet footer reports the force units as Newtons",
)
_spec(
    command="SET_SOLVER_ANALYSIS_BOUNDARIES",
    build_target=_emit("SET_SOLVER_ANALYSIS_BOUNDARIES", 1, [1]),
    requires=Requires.SOLUTION,
    assert_effect=_unobservable,
    save_state=True,
    effect_note=(
        "the saved simulation does not move (RPT-020); every boundary appears to be "
        "selected already, so setting all of them changes nothing to observe"
    ),
)
_spec(
    command="SET_INVISCID_LOADS",
    build_target=_emit("SET_INVISCID_LOADS", "ENABLE"),
    requires=Requires.SOLUTION,
    epilogue=lambda script, workdir: script.emit(
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET", workdir / "loads_inviscid.txt"
    ),
    assert_effect=_inviscid_effect,
    effect_note=(
        "the loads exported after enabling inviscid-only report CDo exactly zero "
        "(the viscous default on this run is nonzero)"
    ),
)


# --- solver export (SRC-003 pp.352-354) --------------------------------


def _export_spec(command: str, filename: str, *extra: object, note: str | None = None) -> None:
    _spec(
        command=command,
        build_target=lambda script, workdir: script.emit(command, workdir / filename, *extra),
        requires=Requires.SOLUTION,
        assert_effect=file_effect(filename),
        effect_note=note or "the export file the command names exists and is not empty",
    )


_export_spec("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads_target.txt")
_export_spec("EXPORT_SOLVER_ANALYSIS_TECPLOT", "solution.dat")
_export_spec("EXPORT_SOLVER_ANALYSIS_VTK", "solution.vtk", -1)
_export_spec("EXPORT_SOLVER_ANALYSIS_CSV", "solution.csv", "CP-FREESTREAM", "PASCALS", 1, -1)
_export_spec("EXPORT_SOLVER_ANALYSIS_PLOAD_BDF", "loads.bdf", -1)
_export_spec("EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS", "forces.txt", -1)


def _vtk_variables_effect(artifacts: ProbeArtifacts) -> bool | None:
    vtk = _read(artifacts.workdir, "variables.vtk")
    if vtk is None:
        return None
    return True if "CP_REFERENCE" in vtk else None


_spec(
    command="SET_VTK_EXPORT_VARIABLES",
    build_target=_emit("SET_VTK_EXPORT_VARIABLES", 2, "DISABLE", ["X", "CP_REFERENCE"]),
    requires=Requires.SOLUTION,
    epilogue=lambda script, workdir: script.emit(
        "EXPORT_SOLVER_ANALYSIS_VTK", workdir / "variables.vtk", -1
    ),
    assert_effect=_vtk_variables_effect,
    effect_note="the VTK exported afterwards carries the selected CP_REFERENCE variable",
)


# --- unsteady plots (SRC-003 pp.347-348), one coupled specification --------
#
# WRITTEN FROM A MEASUREMENT, NOT FROM THE MANUAL (PFS-2015.02.01). The
# three commands are coupled: a plot is defined in the setup phase, the
# solver runs unsteady, and the export writes one file carrying every
# defined plot as a column, named for the plot. The tier-3 workspace
# measured that coupling on 2026-09-08 through the `unsteady_rotor` and
# `unsteady` run types (rows 1011, 1020, 5005, 7001 and 7002 of
# tests/tier3_licensed): the run record names `<point>_plots.txt`, the
# file exists, its header carries `Solver mode: Unsteady` and a column per
# plot the run type defined. The specifications below reproduce that
# shape at probe scale: SIM tier (OPEN only), then the steady setup with
# SET_SOLVER_UNSTEADY over it, the plot definition BEFORE INITIALIZE_SOLVER
# (a definition after it was not measured and is not assumed), and the
# export after START_SOLVER as the epilogue whose file is the effect.

_PLOTS_FILE = "plots_probe.txt"


def _unsteady_setup(script: Script, workdir: Path) -> None:
    """Emit the tiers' steady setup with the unsteady mode over it.

    Init phase, so it follows the plot definitions, which are setup phase.
    """
    emit_solver_setup(script)
    script.emit("SET_SOLVER_UNSTEADY", time_iterations=3, delta_time=0.0123)


def _force_plot(script: Script, workdir: Path) -> None:
    script.emit(
        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        frame=1,
        units="COEFFICIENTS",
        parameter="CL",
        name="CL_PYFS_PLOT",
        boundaries=-1,
    )


def _fluid_plot(script: Script, workdir: Path) -> None:
    script.emit(
        "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
        frame=1,
        parameter="VELOCITY",
        name="VELOCITY_PYFS_PLOT",
        vertex="0.0 0.0 1.0",
    )


def _solve_and_export_plots(script: Script, workdir: Path) -> None:
    _unsteady_setup(script, workdir)
    initialize_solver(script)
    script.emit("START_SOLVER")
    script.emit("UNSTEADY_SOLVER_EXPORT_PLOTS", workdir / _PLOTS_FILE)


def _plots_file_names(plot: str) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: the exported plots file carries a column named for the plot."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        text = _read(artifacts.workdir, _PLOTS_FILE)
        if text is None:
            return None
        return True if plot in text else False

    return check


_spec(
    command="UNSTEADY_SOLVER_NEW_FORCE_PLOT",
    build_target=_force_plot,
    requires=Requires.SIM,
    epilogue=_solve_and_export_plots,
    assert_effect=_plots_file_names("CL_PYFS_PLOT"),
    effect_note="the plots file exported after the unsteady solve carries the CL plot by name",
    timeout_s=240.0,
)
_spec(
    command="UNSTEADY_SOLVER_NEW_FLUID_PLOT",
    build_target=_fluid_plot,
    requires=Requires.SIM,
    epilogue=_solve_and_export_plots,
    assert_effect=_plots_file_names("VELOCITY_PYFS_PLOT"),
    effect_note="the plots file exported after the unsteady solve carries the fluid plot by name",
    timeout_s=240.0,
)
_spec(
    command="UNSTEADY_SOLVER_EXPORT_PLOTS",
    build_target=lambda script, workdir: script.emit(
        "UNSTEADY_SOLVER_EXPORT_PLOTS", workdir / _PLOTS_FILE
    ),
    requires=Requires.SIM,
    prelude=_seq(
        _force_plot,
        _unsteady_setup,
        lambda script, workdir: initialize_solver(script),
        _emit("START_SOLVER"),
    ),
    assert_effect=file_effect(_PLOTS_FILE),
    effect_note="the plots file the command names exists and is not empty after an unsteady solve",
    timeout_s=240.0,
)


import pyflightstream.qa._spec_catalog_b as _spec_catalog_b  # noqa: E402,F401
import pyflightstream.qa._spec_ccs_mesh as _spec_ccs_mesh  # noqa: E402,F401
import pyflightstream.qa._spec_ccs_noise as _spec_ccs_noise  # noqa: E402,F401
import pyflightstream.qa._spec_t1 as _spec_t1  # noqa: E402,F401
