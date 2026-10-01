"""The probe catalog, second part: probe points to the sweeper toolbox.

Pipeline role: the entries of ``PROBE_SPECS`` for probe points,
streamlines, sections, actuators, motions and the sweeper, registered
when ``pyflightstream.qa.specs`` imports this module. The shared
instruments are in ``pyflightstream.qa._spec_kit``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pyflightstream.qa.probes import (
    ProbeArtifacts,
    Requires,
    file_effect,
    fsm_changed,
    fsm_gained,
)
from pyflightstream.script import Script

#: The catalog exports its catalog and nothing else. Without this, every
#: non-underscore definition here is public the moment the wheel ships,
#: which would make three effect-assertion helpers of this module part
#: of the supported surface by accident (the rule is stated in
#: tests/tier1_offline/test_exceptions_catalog.py: an absent __all__ means the module

__all__: list[str] = []

from pyflightstream.qa._spec_kit import (  # noqa: E402
    _emit,
    _file_lax,
    _log_printed,
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
    effect_note="the probe export may refresh; the stored points do not move",
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
        include_symmetry="DISABLE",
        surfaces=-1,
    ),
    requires=Requires.SOLVER,
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
    save_state=True,
    assert_effect=fsm_gained("0.6622"),
    effect_note=("the saved simulation carries the distinctive axis offset 0.6622"),
)
_spec(
    command="SET_ACTUATOR_RADIUS",
    build_target=_emit("SET_ACTUATOR_RADIUS", 1, 1.234, 0.321),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    save_state=True,
    assert_effect=fsm_gained("1.234", "0.321"),
    effect_note=("the saved simulation carries both distinctive radii, 1.234 tip and 0.321 hub"),
)
_spec(
    command="SET_PROP_ACTUATOR_RPM",
    build_target=_emit("SET_PROP_ACTUATOR_RPM", 1, 3456.7),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    save_state=True,
    assert_effect=fsm_gained("3456.7"),
    effect_note=("the saved simulation carries the distinctive rpm 3456.7"),
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
    save_state=True,
    assert_effect=fsm_gained("0.777"),
    effect_note=("the saved simulation carries the distinctive swirl fraction 0.777"),
)
_spec(
    command="ENABLE_ACTUATOR",
    build_target=_emit("ENABLE_ACTUATOR", 1),
    requires=Requires.SIM,
    prelude=_ACTUATOR_PRELUDE,
    assert_effect=_unobservable,
    save_state=True,
    effect_note=(
        "the saved simulation does not move when an actuator is enabled (RPT-020); "
        "an actuator appears to be enabled already when created, so the state "
        "instrument cannot separate the two"
    ),
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

#: One setter of this family cannot be probed on a rotary motion.
#: Measured on 26.122: SET_MOTION_START_TIME against the shared rotary
#: prelude aborts the script with the solver's own refusal, "Start time
#: cannot be set for rotary motion", and the harness recorded the
#: command BROKEN. That would have added a fourth MEASURED broken
#: beside three inherited ones; it would not have created the refusal,
#: which the inheritance already carries. And the command is not
#: measured to WORK: the corrected probe records it running with its
#: effect unobservable on all four builds. The refusal is about the
#: motion type, so the probe creates the type that accepts it
#: (RPT-026).
_SIXDOF_PRELUDE = _emit("CREATE_NEW_MOTION", "6DOF")


def _motion_setter(
    command: str,
    *args: object,
    note: str,
    prelude: Callable[[Script, Path], None] | None = None,
) -> None:
    _spec(
        command=command,
        build_target=_emit(command, *args),
        requires=Requires.SIM,
        prelude=_MOTION_PRELUDE if prelude is None else prelude,
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
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=("the saved simulation carries the motion frame binding"),
)
_motion_setter(
    "SET_MOTION_START_TIME",
    1,
    0.05,
    note="the motion start time is stored in binary form; no instrument yet",
    prelude=_SIXDOF_PRELUDE,
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
_spec(
    command="SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION",
    build_target=_emit("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION", 1, "DISABLE", 1),
    requires=Requires.SIM,
    prelude=_seq(
        _MOTION_PRELUDE, _emit("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION", 1, "ENABLE", 1)
    ),
    save_state=True,
    assert_effect=fsm_changed(),
    effect_note=(
        "DISABLE after ENABLE changes the saved simulation, which stores the key "
        "(the one-line difference of the 0.32.0 round 1, RPT-096)"
    ),
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
    effect_note="the sweeper clear-solution toggle is not exposed by any instrument yet",
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
