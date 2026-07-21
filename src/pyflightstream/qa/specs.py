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
commands carry no specification yet: SET_PROP_ACTUATOR_PROFILE and the
two FSI commands need input-file fixtures whose format awaits a manual
pass.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from pyflightstream.qa.probes import (
    ProbeArtifacts,
    ProbeSpec,
    Requires,
    dump_gained,
    emit_solver_setup,
    file_effect,
    printed_line,
    region_printed,
)
from pyflightstream.script import Script
from pyflightstream.script.helpers import initialize_solver

_NESTED_NAME = "nested_probe.txt"
_SHEET = "sheet.txt"


# --- shared instruments -------------------------------------------------


def _sheet(script: Script, workdir: Path) -> None:
    """Export the settings sheet, the universal state instrument."""
    script.emit("EXPORT_PROBE_POINTS", workdir / _SHEET)


def _saveas(script: Script, workdir: Path) -> None:
    """Save the simulation for the name-greppability instrument."""
    script.emit("SAVEAS", workdir / "saved.fsm")


def _seq(*parts: Callable[[Script, Path], None]) -> Callable[[Script, Path], None]:
    """Chain build callables into one."""

    def build(script: Script, workdir: Path) -> None:
        for part in parts:
            part(script, workdir)

    return build


def _read(workdir: Path, name: str) -> str | None:
    path = workdir / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")


def sheet_matches(pattern: str, strict: bool = True) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: the settings sheet matches ``pattern`` (regex).

    Strict only for labels the recon proved the sheet exposes; a
    missing sheet always returns None (the instrument, not the target,
    failed).
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        sheet = _read(artifacts.workdir, _SHEET)
        if sheet is None:
            return None
        if re.search(pattern, sheet):
            return True
        return False if strict else None

    return check


def fsm_grep(token: str, expect: bool = True) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: a readable name is present (or absent) in the saved file.

    Object names survive as text in a SAVEAS file (recon-proven);
    numeric fields do not. A missing saved file returns None.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / "saved.fsm"
        if not path.is_file():
            return None
        present = token.encode("ascii") in path.read_bytes()
        return present is expect

    return check


def _unobservable(artifacts: ProbeArtifacts) -> None:
    """Effect placeholder: the state is not observable yet (unprobed)."""
    return None


def region_printed_lax(marker: str) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: a log message in the target region, None when silent."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        return True if printed_line(artifacts.target_region(), marker) else None

    return check


def _log_printed(marker: str) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: a message in the log exported after the epilogue.

    None when that log never appeared (the epilogue aborted, so the
    instrument, not the target, failed).
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        final = artifacts.log_final()
        if final is None:
            return None
        return printed_line(final, marker)

    return check


def _file_lax(name: str, minimum_bytes: int = 1) -> Callable[[ProbeArtifacts], bool | None]:
    """Effect: an epilogue-produced file has content, None when absent.

    Lax because the file is written by a support command, not by the
    target: absence may mean the instrument broke, never proof of a
    target no-op.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        if path.is_file() and path.stat().st_size >= minimum_bytes:
            return True
        return None

    return check


def _emit(command: str, *args: object, **kwargs: object) -> Callable[[Script, Path], None]:
    """Make a build callable that emits one fixed command."""

    def build(script: Script, workdir: Path) -> None:
        script.emit(command, *args, **kwargs)

    return build


def _named_frame(name: str) -> Callable[[Script, Path], None]:
    """Create local frame 2 and give it a greppable name."""

    def build(script: Script, workdir: Path) -> None:
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")
        script.emit(
            "EDIT_COORDINATE_SYSTEM",
            frame=2,
            name=name,
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
        )

    return build


PROBE_SPECS: dict[str, ProbeSpec] = {}


def _spec(**kwargs: object) -> None:
    spec = ProbeSpec(**kwargs)
    PROBE_SPECS[spec.command] = spec


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
    assert_effect=_unobservable,
    effect_note="frame origins are stored in binary form; no instrument observes them yet",
)
_spec(
    command="SET_COORDINATE_SYSTEM_AXIS",
    build_target=_emit("SET_COORDINATE_SYSTEM_AXIS", 2, "X", 1.0, 0.0, 0.0, "TRUE"),
    prelude=_CREATE_FRAME_PRELUDE,
    assert_effect=_unobservable,
    effect_note="frame axes are stored in binary form; no instrument observes them yet",
)


# --- boundary conditions (SRC-003 pp.319-328) --------------------------

_spec(
    command="AUTO_DETECT_TRAILING_EDGES",
    build_target=_emit("AUTO_DETECT_TRAILING_EDGES"),
    requires=Requires.SIM,
    assert_effect=region_printed_lax("trailing edge"),
    effect_note=(
        "the command runs silently and INITIALIZE_SOLVER detects edges on its own; no "
        "instrument separates the two yet"
    ),
)
_spec(
    command="SET_TRAILING_EDGE_TYPE",
    build_target=_emit("SET_TRAILING_EDGE_TYPE", 1, "RELAXED"),
    requires=Requires.SIM,
    prelude=_emit("AUTO_DETECT_TRAILING_EDGES"),
    assert_effect=_unobservable,
    effect_note="trailing-edge types are not exposed by any instrument yet",
)
_spec(
    command="DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
    build_target=_emit("DISABLE_WAKE_NODES_ON_TRAILING_EDGE", 1),
    requires=Requires.SIM,
    prelude=_emit("AUTO_DETECT_TRAILING_EDGES"),
    assert_effect=_unobservable,
    effect_note="wake-node states are not exposed by any instrument yet",
)
_spec(
    command="AUTO_DETECT_WAKE_TERMINATION_NODES",
    build_target=_emit("AUTO_DETECT_WAKE_TERMINATION_NODES"),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note="wake termination nodes are not exposed by any instrument yet",
)
_spec(
    command="SET_FREESTREAM",
    build_target=_emit("SET_FREESTREAM", "CONSTANT"),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note=(
        "the CONSTANT form is the solver default and leaves no observable trace; the "
        "ROTATION and CUSTOM forms await dedicated fixtures"
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
    effect_note=(
        "the settings dump reports the 5000 m standard-atmosphere density "
        "(0.736 kg/m^3); the first full sweep observed 1.056 kg/m^3 instead, which is "
        "the 5000 ft standard state, so the METERS units argument reads ignored"
    ),
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
    assert_effect=_unobservable,
    effect_note="the thread count is not exposed by any instrument yet",
)


# --- advanced settings (SRC-003 pp.344-345) ----------------------------

_spec(
    command="SET_SOLVER_CONVERGENCE_ITERATIONS",
    build_target=_emit("SET_SOLVER_CONVERGENCE_ITERATIONS", 7),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note="the convergence-iterations window is not exposed by any instrument yet",
)
_spec(
    command="SOLVER_MINIMUM_CP",
    build_target=_emit("SOLVER_MINIMUM_CP", -4.5),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note="the minimum-Cp floor is not exposed by any instrument yet",
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
    assert_effect=_unobservable,
    effect_note="the boundary-layer model choice is not exposed by any instrument yet",
)
_spec(
    command="SET_SOLVER_VISCOUS_COUPLING",
    build_target=_emit("SET_SOLVER_VISCOUS_COUPLING", "ENABLE"),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note="the viscous-coupling toggle is not exposed by any instrument yet",
)
_spec(
    command="SET_VISCOUS_EXCLUDED_BOUNDARIES",
    build_target=_emit("SET_VISCOUS_EXCLUDED_BOUNDARIES", 1, [1]),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note="viscous exclusions are not exposed by any instrument yet",
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
    assert_effect=_unobservable,
    effect_note="proximal-boundary marking is not exposed by any instrument yet",
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
    assert_effect=_unobservable,
    effect_note="the vorticity-drag boundary list is not exposed by any instrument yet",
)
_spec(
    command="DELETE_VORTICITY_DRAG_BOUNDARIES",
    build_target=_emit("DELETE_VORTICITY_DRAG_BOUNDARIES"),
    requires=Requires.SOLUTION,
    prelude=_emit("SET_VORTICITY_DRAG_BOUNDARIES", 1, [1]),
    assert_effect=_unobservable,
    effect_note="the vorticity-drag boundary list is not exposed by any instrument yet",
)
_spec(
    command="SET_SOLVER_ANALYSIS_LOADS_FRAME",
    build_target=_emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", 2),
    requires=Requires.SOLUTION,
    early_prelude=_named_frame("PYFS_FRAME_NAME"),
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Coordinate frame for analysis:\s+PYFS_FRAME_NAME", strict=True),
    effect_note=(
        "the settings sheet reports the analysis frame by its probe-given name PYFS_FRAME_NAME"
    ),
)
_spec(
    command="SET_ANALYSIS_MOMENTS_MODEL",
    build_target=_emit("SET_ANALYSIS_MOMENTS_MODEL", "VORTICITY"),
    requires=Requires.SOLUTION,
    assert_effect=_unobservable,
    effect_note="the moments-model choice is not exposed by any instrument yet",
)
_spec(
    command="SET_ANALYSIS_SYMMETRY_LOADS",
    build_target=_emit("SET_ANALYSIS_SYMMETRY_LOADS", "ENABLE"),
    requires=Requires.SOLUTION,
    assert_effect=_unobservable,
    effect_note="the symmetry-loads toggle is not exposed by any instrument yet",
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
    effect_note=(
        "the analysis boundary selection is indistinguishable on a single-boundary "
        "geometry; needs a multi-boundary fixture"
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


# --- probe points (SRC-003 pp.362-363) ---------------------------------

_spec(
    command="NEW_PROBE_POINT",
    build_target=_emit("NEW_PROBE_POINT", "VOLUME", 1.2345, 2.3456, 3.4567),
    requires=Requires.SOLUTION,
    epilogue=_sheet,
    assert_effect=sheet_matches(r"0\.1234E\+01", strict=True),
    effect_note="the probe export lists the distinctive point coordinate 0.1234E+01",
)
_spec(
    command="NEW_PROBE_LINE",
    build_target=_emit("NEW_PROBE_LINE", 3, 0.9876, 0.0, 0.1, 1.1111, 0.0, 0.1),
    requires=Requires.SOLUTION,
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Number of Probe Points:\s+3\b", strict=True),
    effect_note="the probe export counts exactly the 3 requested line points",
)


def _probe_import_target(script: Script, workdir: Path) -> None:
    # Lattice format per the curated helper evidence (SRC-003
    # pp.362-363): first line the count, then X,Y,Z,TYPE rows.
    lattice = workdir / "lattice.csv"
    lattice.write_text("2\n0.8765,0.1,0.2,1\n0.7654,0.3,0.4,1\n", encoding="utf-8")
    script.emit("PROBE_POINTS_IMPORT", "METER", 1, lattice)


_spec(
    command="PROBE_POINTS_IMPORT",
    build_target=_probe_import_target,
    requires=Requires.SOLUTION,
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Number of Probe Points:\s+2\b", strict=True),
    effect_note="the probe export counts exactly the 2 imported lattice points",
)
_spec(
    command="UPDATE_PROBE_POINTS",
    build_target=_emit("UPDATE_PROBE_POINTS"),
    requires=Requires.SOLUTION,
    prelude=_emit("NEW_PROBE_POINT", "VOLUME", 1.2345, 2.3456, 3.4567),
    assert_effect=_unobservable,
    effect_note=(
        "the probe export may refresh values on its own, so it cannot discriminate "
        "UPDATE_PROBE_POINTS; needs a dedicated instrument"
    ),
)
_spec(
    command="EXPORT_PROBE_POINTS",
    build_target=lambda script, workdir: script.emit("EXPORT_PROBE_POINTS", workdir / "probes.txt"),
    requires=Requires.SOLUTION,
    prelude=_emit("NEW_PROBE_POINT", "VOLUME", 1.2345, 2.3456, 3.4567),
    assert_effect=file_effect("probes.txt"),
    effect_note="the probe export file the command names exists and is not empty",
)
_spec(
    command="DELETE_PROBE_POINTS",
    build_target=_emit("DELETE_PROBE_POINTS"),
    requires=Requires.SOLUTION,
    prelude=_emit("NEW_PROBE_POINT", "VOLUME", 1.2345, 2.3456, 3.4567),
    epilogue=_sheet,
    assert_effect=sheet_matches(r"Number of Probe Points:\s+0\b", strict=True),
    effect_note="the probe export counts 0 points after the prelude created one",
)


# --- streamlines (SRC-003 pp.360-361) ----------------------------------


def _streamline_epilogue(script: Script, workdir: Path) -> None:
    script.emit("GENERATE_ALL_OFF_BODY_STREAMLINES")
    script.emit("EXPORT_ALL_OFF_BODY_STREAMLINES", workdir / "streamlines.txt")


_spec(
    command="NEW_OFF_BODY_STREAMLINE",
    build_target=_emit(
        "NEW_OFF_BODY_STREAMLINE",
        position_x=0.5,
        position_y=0.3,
        position_z=0.2,
        upstream="DISABLE",
    ),
    requires=Requires.SOLUTION,
    epilogue=_streamline_epilogue,
    assert_effect=_file_lax("streamlines.txt", minimum_bytes=200),
    effect_note=(
        "the streamline export written after generation carries data for the seeded streamline"
    ),
)
_spec(
    command="NEW_STREAMLINE_DISTRIBUTION",
    build_target=_emit(
        "NEW_STREAMLINE_DISTRIBUTION",
        position_1_x=0.4,
        position_1_y=0.2,
        position_1_z=0.1,
        position_2_x=0.6,
        position_2_y=0.4,
        position_2_z=0.1,
        subdivisions=4,
    ),
    requires=Requires.SOLUTION,
    epilogue=_streamline_epilogue,
    assert_effect=_file_lax("streamlines.txt", minimum_bytes=200),
    effect_note=(
        "the streamline export written after generation carries data for the seeded distribution"
    ),
)
# The seeding prelude of the two commands below uses the distribution
# form: the first full sweep showed the single-streamline form aborts
# the script (its own probe records that), so it cannot serve as a
# support instrument.
_SEED_STREAMLINES = _emit(
    "NEW_STREAMLINE_DISTRIBUTION",
    position_1_x=0.4,
    position_1_y=0.2,
    position_1_z=0.1,
    position_2_x=0.6,
    position_2_y=0.4,
    position_2_z=0.1,
    subdivisions=4,
)

_spec(
    command="GENERATE_ALL_OFF_BODY_STREAMLINES",
    build_target=_emit("GENERATE_ALL_OFF_BODY_STREAMLINES"),
    requires=Requires.SOLUTION,
    prelude=_SEED_STREAMLINES,
    epilogue=lambda script, workdir: script.emit(
        "EXPORT_ALL_OFF_BODY_STREAMLINES", workdir / "streamlines.txt"
    ),
    assert_effect=_file_lax("streamlines.txt", minimum_bytes=200),
    effect_note="the streamline export written afterwards carries generated data",
)
_spec(
    command="EXPORT_ALL_OFF_BODY_STREAMLINES",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_ALL_OFF_BODY_STREAMLINES", workdir / "streamlines.txt"
    ),
    requires=Requires.SOLUTION,
    prelude=_seq(_SEED_STREAMLINES, _emit("GENERATE_ALL_OFF_BODY_STREAMLINES")),
    assert_effect=file_effect("streamlines.txt"),
    effect_note="the streamline export file the command names exists and is not empty",
)


# --- surface sections (SRC-003 pp.357-359) -----------------------------

_CREATE_SECTION = _emit("CREATE_NEW_SURFACE_SECTION", 1, "XZ", 0.05, "1", "DISABLE", -1)

_spec(
    command="CREATE_NEW_SURFACE_SECTION",
    build_target=_CREATE_SECTION,
    requires=Requires.SOLUTION,
    epilogue=lambda script, workdir: script.emit(
        "EXPORT_ALL_SURFACE_SECTIONS", workdir / "sections.txt"
    ),
    assert_effect=_file_lax("sections.txt", minimum_bytes=100),
    effect_note="the all-sections export written afterwards carries the created section",
)
_spec(
    command="NEW_SURFACE_SECTION_DISTRIBUTION",
    build_target=_emit(
        "NEW_SURFACE_SECTION_DISTRIBUTION",
        frame=1,
        plane="XZ",
        num_sections=3,
        plot_direction="1",
        surfaces=-1,
    ),
    requires=Requires.SOLUTION,
    epilogue=lambda script, workdir: script.emit(
        "EXPORT_ALL_SURFACE_SECTIONS", workdir / "sections.txt"
    ),
    assert_effect=_file_lax("sections.txt", minimum_bytes=100),
    effect_note="the all-sections export written afterwards carries the distribution",
)
_spec(
    command="COMPUTE_SURFACE_SECTIONAL_LOADS",
    build_target=_emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "COEFFICIENTS"),
    requires=Requires.SOLUTION,
    prelude=_CREATE_SECTION,
    epilogue=lambda script, workdir: script.emit(
        "EXPORT_SURFACE_SECTIONAL_LOADS", workdir / "sectional_loads.txt"
    ),
    assert_effect=_file_lax("sectional_loads.txt", minimum_bytes=100),
    effect_note="the sectional-loads export written afterwards carries computed loads",
)
_spec(
    command="EXPORT_SURFACE_SECTIONAL_LOADS",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_SURFACE_SECTIONAL_LOADS", workdir / "sectional_loads.txt"
    ),
    requires=Requires.SOLUTION,
    prelude=_seq(_CREATE_SECTION, _emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "COEFFICIENTS")),
    assert_effect=file_effect("sectional_loads.txt"),
    effect_note="the sectional-loads file the command names exists and is not empty",
)
_spec(
    command="UPDATE_ALL_SURFACE_SECTIONS",
    build_target=_emit("UPDATE_ALL_SURFACE_SECTIONS"),
    requires=Requires.SOLUTION,
    prelude=_CREATE_SECTION,
    assert_effect=_unobservable,
    effect_note=(
        "the sections export may refresh on its own, so it cannot discriminate the "
        "update command; needs a dedicated instrument"
    ),
)
_spec(
    command="EXPORT_ALL_SURFACE_SECTIONS",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_ALL_SURFACE_SECTIONS", workdir / "sections.txt"
    ),
    requires=Requires.SOLUTION,
    prelude=_CREATE_SECTION,
    assert_effect=file_effect("sections.txt"),
    effect_note="the all-sections file the command names exists and is not empty",
)
_spec(
    command="DELETE_SURFACE_SECTION",
    build_target=_emit("DELETE_SURFACE_SECTION", 1),
    requires=Requires.SOLUTION,
    prelude=_CREATE_SECTION,
    assert_effect=_unobservable,
    effect_note=(
        "the surviving-section listing format is not pinned yet, so deletion is not "
        "discriminated; needs a dedicated instrument"
    ),
)


# --- volume sections (SRC-003 pp.355-356) ------------------------------

_CREATE_RECT_VSECTION = _emit(
    "CREATE_NEW_RECTANGLE_VOLUME_SECTION",
    1,
    "XZ",
    0.0,
    1,
    -1.0,
    -1.0,
    1.0,
    1.0,
    "NONE",
    0.1,
    1,
    1.2,
)


def _vsection_export_epilogue(script: Script, workdir: Path) -> None:
    script.emit("EXPORT_VOLUME_SECTION_VTK", 1, workdir / "vsection.vtk")


def _delete_vsection_effect(artifacts: ProbeArtifacts) -> bool:
    return not (artifacts.workdir / "vsection.vtk").is_file()


_spec(
    command="CREATE_NEW_RECTANGLE_VOLUME_SECTION",
    build_target=_CREATE_RECT_VSECTION,
    requires=Requires.SOLUTION,
    epilogue=_vsection_export_epilogue,
    assert_effect=_file_lax("vsection.vtk", minimum_bytes=100),
    effect_note="exporting volume section 1 afterwards succeeds, so the section exists",
)
_spec(
    command="CREATE_NEW_CIRCLE_VOLUME_SECTION",
    build_target=_emit(
        "CREATE_NEW_CIRCLE_VOLUME_SECTION",
        1,
        "XZ",
        0.0,
        10,
        10,
        0.2,
        1.0,
        "NONE",
        0.1,
        1,
        1.2,
    ),
    requires=Requires.SOLUTION,
    epilogue=_vsection_export_epilogue,
    assert_effect=_file_lax("vsection.vtk", minimum_bytes=100),
    effect_note="exporting volume section 1 afterwards succeeds, so the section exists",
)
_spec(
    command="UPDATE_ALL_VOLUME_SECTIONS",
    build_target=_emit("UPDATE_ALL_VOLUME_SECTIONS"),
    requires=Requires.SOLUTION,
    prelude=_CREATE_RECT_VSECTION,
    assert_effect=_unobservable,
    effect_note=(
        "the section export may refresh on its own, so it cannot discriminate the "
        "update command; needs a dedicated instrument"
    ),
)
_spec(
    command="EXPORT_VOLUME_SECTION_VTK",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_VOLUME_SECTION_VTK", 1, workdir / "vsection.vtk"
    ),
    requires=Requires.SOLUTION,
    prelude=_CREATE_RECT_VSECTION,
    assert_effect=file_effect("vsection.vtk"),
    effect_note="the VTK file the command names exists and is not empty",
)
_spec(
    command="EXPORT_VOLUME_SECTION_TECPLOT",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_VOLUME_SECTION_TECPLOT", 1, workdir / "vsection.dat"
    ),
    requires=Requires.SOLUTION,
    prelude=_CREATE_RECT_VSECTION,
    assert_effect=file_effect("vsection.dat"),
    effect_note="the Tecplot file the command names exists and is not empty",
)
_spec(
    command="DELETE_VOLUME_SECTION",
    build_target=_emit("DELETE_VOLUME_SECTION", 1),
    requires=Requires.SOLUTION,
    prelude=_CREATE_RECT_VSECTION,
    epilogue=_vsection_export_epilogue,
    assert_effect=_delete_vsection_effect,
    effect_note=(
        "exporting the deleted section 1 afterwards produces no file (the export "
        "command's own probe rules out an export failure)"
    ),
)


# --- actuators (SRC-003 pp.323-324) ------------------------------------

_ACTUATOR_PRELUDE = _seq(
    _emit("CREATE_NEW_COORDINATE_SYSTEM"),
    _emit("CREATE_NEW_ACTUATOR", "PROPELLER", subtype="ELLIPTICAL", name="PYFS_ACT_BASE"),
)

_spec(
    command="CREATE_NEW_ACTUATOR",
    build_target=_emit(
        "CREATE_NEW_ACTUATOR", "PROPELLER", subtype="ELLIPTICAL", name="PYFS_ACT_CREATED"
    ),
    requires=Requires.SIM,
    epilogue=_saveas,
    assert_effect=fsm_grep("PYFS_ACT_CREATED"),
    effect_note="the actuator name is readable in the saved simulation file",
)
_spec(
    command="SET_ACTUATOR_NAME",
    build_target=_emit("SET_ACTUATOR_NAME", 1, "PYFS_ACT_RENAMED"),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    epilogue=_saveas,
    assert_effect=fsm_grep("PYFS_ACT_RENAMED"),
    effect_note="the new actuator name is readable in the saved simulation file",
)
_spec(
    command="SET_ACTUATOR_AXIS",
    build_target=_emit("SET_ACTUATOR_AXIS", 1, 2, "X", 0.6622),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    effect_note="actuator axis fields are stored in binary form; no instrument yet",
)
_spec(
    command="SET_ACTUATOR_RADIUS",
    build_target=_emit("SET_ACTUATOR_RADIUS", 1, 1.234, 0.321),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    effect_note="actuator radii are stored in binary form; no instrument yet",
)
_spec(
    command="SET_PROP_ACTUATOR_RPM",
    build_target=_emit("SET_PROP_ACTUATOR_RPM", 1, 3456.7),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    effect_note="the actuator rpm is stored in binary form; no instrument yet",
)
_spec(
    command="SET_PROP_ACTUATOR_THRUST",
    build_target=_emit("SET_PROP_ACTUATOR_THRUST", 1, 45.678, "NEWTONS"),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    effect_note="the actuator thrust is stored in binary form; no instrument yet",
)
_spec(
    command="SET_PROP_ACTUATOR_SWIRL",
    build_target=_emit("SET_PROP_ACTUATOR_SWIRL", 1, 0.777),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    effect_note="the swirl fraction is stored in binary form; no instrument yet",
)
_spec(
    command="ENABLE_ACTUATOR",
    build_target=_emit("ENABLE_ACTUATOR", 1),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    effect_note="the enable flag is stored in binary form; no instrument yet",
)
_spec(
    command="DELETE_ACTUATOR",
    build_target=_emit("DELETE_ACTUATOR", 1),
    requires=Requires.SIM,
    prelude=_seq(
        _emit("CREATE_NEW_COORDINATE_SYSTEM"),
        _emit("CREATE_NEW_ACTUATOR", "PROPELLER", subtype="ELLIPTICAL", name="PYFS_ACT_DOOMED"),
    ),
    epilogue=_saveas,
    assert_effect=fsm_grep("PYFS_ACT_DOOMED", expect=False),
    effect_note=("the deleted actuator's name is no longer readable in the saved simulation file"),
)


# --- motion definitions (SRC-003 pp.332-336) ---------------------------

_MOTION_PRELUDE = _emit("CREATE_NEW_MOTION", "ROTARY")


def _motion_setter(command: str, *args: object, note: str) -> None:
    _spec(
        command=command,
        build_target=_emit(command, *args),
        requires=Requires.SIM,
        prelude=_MOTION_PRELUDE,
        assert_effect=_unobservable,
        effect_note=note,
    )


_spec(
    command="CREATE_NEW_MOTION",
    build_target=_emit("CREATE_NEW_MOTION", "ROTARY"),
    requires=Requires.SIM,
    assert_effect=_unobservable,
    effect_note=(
        "motions are unnamed and stored in binary form (recon-checked); no instrument "
        "observes them yet"
    ),
)
_motion_setter(
    "SET_MOTION_BOUNDARIES",
    1,
    -1,
    note="motion boundary lists are stored in binary form; no instrument yet",
)
_motion_setter(
    "SET_MOTION_MOVING_FRAMES",
    1,
    -1,
    note="motion frame lists are stored in binary form; no instrument yet",
)


def _motion_frame_prelude(script: Script, workdir: Path) -> None:
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit("CREATE_NEW_MOTION", "ROTARY")


_spec(
    command="SET_MOTION_COORDINATE_SYSTEM",
    build_target=_emit("SET_MOTION_COORDINATE_SYSTEM", 1, 2),
    requires=Requires.SIM,
    prelude=_motion_frame_prelude,
    assert_effect=_unobservable,
    effect_note="the motion frame binding is stored in binary form; no instrument yet",
)
_motion_setter(
    "SET_MOTION_START_TIME",
    1,
    0.05,
    note="the motion start time is stored in binary form; no instrument yet",
)
_motion_setter(
    "SET_MOTION_ROTOR_AXIS",
    1,
    "X",
    note="the rotor axis is stored in binary form; no instrument yet",
)
_motion_setter(
    "SET_MOTION_ROTOR_RPM",
    1,
    4567.8,
    note="the rotor rpm is stored in binary form; no instrument yet",
)
_motion_setter(
    "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION",
    1,
    "ENABLE",
    6,
    note="the wake-stabilization state is stored in binary form; no instrument yet",
)
_motion_setter(
    "DELETE_MOTION",
    1,
    note="motions are unnamed in the saved file, so deletion is not discriminated yet",
)


# --- sweeper toolbox (SRC-003 p.406) -----------------------------------

_SWEEP_AOA_PRELUDE = _emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", [2.0])


def _sweep_pair_effect(artifacts: ProbeArtifacts) -> bool | None:
    sweep = _read(artifacts.workdir, "sweep.txt")
    if sweep is None:
        return None
    return True if ("2.000" in sweep and "4.000" in sweep) else None


def _sweep_epilogue(script: Script, workdir: Path) -> None:
    script.emit("SWEEPER_START")
    script.emit("SWEEPER_EXPORT_SPREADSHEET", workdir / "sweep.txt")


def _postrun_target(script: Script, workdir: Path) -> None:
    postrun = workdir / "postrun.txt"
    postrun.write_text("PRINT PYFS_POSTRUN\n", encoding="utf-8")
    script.emit("SWEEPER_POST_RUN_SCRIPT", "ENABLE", postrun)


_spec(
    command="SWEEPER_SET_AOA_SWEEP",
    build_target=_emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", [2.0, 4.0]),
    requires=Requires.SOLVER,
    epilogue=_sweep_epilogue,
    assert_effect=_sweep_pair_effect,
    effect_note="the sweep spreadsheet carries both requested angles 2.000 and 4.000",
    timeout_s=240.0,
)
_spec(
    command="SWEEPER_SET_BETA_SWEEP",
    build_target=_emit("SWEEPER_SET_BETA_SWEEP", "CUSTOM", [1.5, 3.5]),
    requires=Requires.SOLVER,
    epilogue=_sweep_epilogue,
    assert_effect=lambda artifacts: (
        True
        if (sweep := _read(artifacts.workdir, "sweep.txt")) is not None
        and "1.500" in sweep
        and "3.500" in sweep
        else None
    ),
    effect_note="the sweep spreadsheet carries both requested side-slips 1.500 and 3.500",
    timeout_s=240.0,
)
_spec(
    command="SWEEPER_SET_VELOCITY_SWEEP",
    build_target=_emit("SWEEPER_SET_VELOCITY_SWEEP", "DISABLE"),
    requires=Requires.SOLVER,
    assert_effect=_unobservable,
    effect_note=(
        "only the DISABLE form is probed (the CUSTOM velocity list file format awaits "
        "a manual pass); the disabled state leaves no observable trace"
    ),
)
_spec(
    command="SWEEPER_POST_RUN_SCRIPT",
    build_target=_postrun_target,
    requires=Requires.SOLVER,
    prelude=_SWEEP_AOA_PRELUDE,
    epilogue=lambda script, workdir: script.emit("SWEEPER_START"),
    assert_effect=_log_printed("PYFS_POSTRUN"),
    effect_note=("the post-run script's message PYFS_POSTRUN appears in the log after the sweep"),
    timeout_s=240.0,
)
_spec(
    command="SWEEPER_CLEAR_SOLUTION",
    build_target=_emit("SWEEPER_CLEAR_SOLUTION", "ENABLE"),
    requires=Requires.SOLVER,
    assert_effect=_unobservable,
    effect_note="the sweeper clear-solution toggle leaves no observable trace yet",
)
_spec(
    command="SWEEPER_REF_VELOCITY_SAME",
    build_target=_emit("SWEEPER_REF_VELOCITY_SAME", "ENABLE"),
    requires=Requires.SOLVER,
    assert_effect=_unobservable,
    effect_note="the sweeper reference-velocity toggle leaves no observable trace yet",
)
_spec(
    command="SWEEPER_START",
    build_target=_emit("SWEEPER_START"),
    requires=Requires.SOLVER,
    prelude=_SWEEP_AOA_PRELUDE,
    assert_effect=region_printed_lax("Solver run time"),
    effect_note="the sweep run prints the solver iteration table and run time",
    timeout_s=240.0,
)
_spec(
    command="SWEEPER_EXPORT_SPREADSHEET",
    build_target=lambda script, workdir: script.emit(
        "SWEEPER_EXPORT_SPREADSHEET", workdir / "sweep.txt"
    ),
    requires=Requires.SOLVER,
    prelude=_seq(_SWEEP_AOA_PRELUDE, _emit("SWEEPER_START")),
    assert_effect=file_effect("sweep.txt"),
    effect_note="the sweep spreadsheet the command names exists and is not empty",
    timeout_s=240.0,
)
