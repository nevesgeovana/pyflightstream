"""Capture one small, committable example of every export in the DEFAULT set.

    python scripts/capture_export_corpus.py --exe <path> --out <dir> [--dry]
    python scripts/capture_export_corpus.py --exe <path> --out <dir> --sweeper

WHY THIS EXISTS, and why it is not `capture_owed_exports.py` next to it.
`PFS-2014.02` asks that every export in the default set have a parser and a
tabular conversion, and a parser for a format nobody has observed is a guess.
The blocking artefact was therefore FILES rather than code. Two runs before
this one produced files and neither produced a FIXTURE:

* the 2026-08-17 run captured twelve formats on 26.123 and left them under
  `_private/`, where tier 1 cannot reach them. It was a real capture and its
  outputs are still the reference this script was checked against; what it
  lacked was a committable size. Its wing carries 25 chordwise and 40 spanwise
  panels, so its force distribution is 508 KiB and its CSV 215 KiB, and a
  fixture tree does not take half a megabyte per format.
* the 2026-08-20 run (`scripts/capture_owed_exports.py`, `RPT-036b`) captured
  two formats and found two database defects. That script stays as the record
  of those findings; it is not superseded and it is not this.

THE MESH IS DELIBERATELY COARSE and it is the whole design of this file. The
same wing at 6 by 6 panels produces the same FORMAT in a few kilobytes: a
parser is pinned by the shape of a table, its header, its terminator and its
column names, none of which vary with panel count. Physics is not the point
here and no coefficient from this run is evidence of anything; the QA
references answer for accuracy, and they run their own converged meshes.

THE GEOMETRY IS SYNTHETIC AND THAT IS ALSO THE POINT. It is the NACA 0012 wing
this package generates for its own physics cases. A capture made on the
author's research geometry could never be committed (invariant 5), which would
leave every parser written against it untestable in tier 1.

WHAT IT DOES NOT DO. It does not promote a status, write a compat report or
edit the command database: an observed export is evidence for a PARSER, and a
status moves only through the sanctioned probe path (invariant 3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from pyflightstream.qa.geometry import WingSpec, generate_wing_stl  # noqa: E402
from pyflightstream.run import LocalExecutor  # noqa: E402
from pyflightstream.script import Script  # noqa: E402

#: The build every export below is documented or verified on. 26.123 rather
#: than the newest-that-inherits, because `EXPORT_BL_VELOCITY_PROFILE` has
#: rows on 26.122 and 26.123 ALONE: the 2026-08-20 run tried it against 26.120
#: and the emitter refused it by version, which is why that format was still
#: owed after a run that captured two others.
VERSION = "26.123"

#: The build the run actually emits under. It is a module-level name rather
#: than a parameter threaded through both builders because the emitter reads it
#: at `Script(version=...)` in two places, and `--version` rebinds it: a second
#: build is a legitimate use of this script, since one owed format
#: (`EXPORT_BL_VELOCITY_PROFILE`) has rows on 26.122 and 26.123 alone, and if it
#: refuses to write on one of them the other is the next question rather than
#: the end of the road.
_version = VERSION

#: Coarse on purpose. The default `WingSpec` is 25 by 40, which is the mesh a
#: physics reference wants and roughly thirty times the file this one needs.
COARSE = WingSpec(n_chord=6, n_span=6)

#: Spanwise station of the surface section, in meters, measured from the root.
#: NOT zero, and the offset is the whole reason this is a named constant: the
#: spanwise panel boundaries of this mesh sit at multiples of
#: ``span_m / n_span`` (8/6, so 0, +-1.333, +-2.667, +-4), and a section plane
#: laid on one of them cuts no edges and writes a table with no rows.
SECTION_OFFSET_M = 0.5

#: Where the boundary-layer probe is placed, in meters: chordwise, spanwise,
#: and just above the upper surface. The spanwise value avoids the panel
#: boundary at y = 0 for the same reason ``SECTION_OFFSET_M`` does; whether
#: that is what the export needs is not yet known, and the run below is what
#: asks.
BL_PROBE_M = (0.5, 0.5, 0.06)


def build_capture(stl: Path, out: Path) -> tuple[Script, dict[str, str]]:
    """Emit one solve and every default-set export that rides on it.

    Parameters
    ----------
    stl : Path
        The generated wing, already written.
    out : Path
        Directory the exports land in.

    Returns
    -------
    tuple of Script and dict of str to str
        The script, and the file name each command was asked to write, so
        the caller can report what appeared and what did not.
    """
    produced: dict[str, str] = {}
    script = Script(version=_version)
    script.comment("PFS-2014.02: the default export set on a coarse wing, 26.123")
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", str(stl), clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SET_SIGNIFICANT_DIGITS", 7)
    script.emit("SET_FREESTREAM", "CONSTANT")

    # THE SOLVER BLOCK IS THE 2026-08-17 RUN'S, command for command. It is
    # the sequence that returned 0 on this build with this geometry, and
    # re-deriving it would spend a licensed seat re-discovering it.
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="SUBSONIC_PRANDTL_GLAUERT",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
        symmetry_copies=1,
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_VELOCITY", 30.0)
    script.emit("SOLVER_SET_AOA", 4.0)
    script.emit("SOLVER_SET_SIDESLIP", 0.0)
    script.emit("SOLVER_SET_ITERATIONS", 300)
    script.emit("SOLVER_SET_CONVERGENCE", 1.0e-5)
    script.emit("SOLVER_SET_REF_AREA", COARSE.area_m2)
    script.emit("SOLVER_SET_REF_LENGTH", COARSE.chord_m)
    script.emit("SET_MAX_PARALLEL_THREADS", 8)
    # The boundary layer is switched on because ONE export depends on it:
    # `EXPORT_BL_VELOCITY_PROFILE` has nothing to write without a viscous
    # solution, and an export that writes nothing is a spent seat.
    script.emit("SET_BOUNDARY_LAYER_TYPE", "TURBULENT")
    script.emit("SET_SOLVER_VISCOUS_COUPLING", "ENABLE")
    script.emit("START_SOLVER")

    # EVERY DEFINITION HERE IS PHASE `analysis` and every export below is
    # phase `export`, so the script is grouped rather than interleaved. The
    # emitter refuses any other order.
    script.emit("SET_ANALYSIS_MOMENTS_MODEL", "PRESSURE")
    script.emit("NEW_PROBE_POINT", "VOLUME", 2.0, 0.0, 0.3)
    script.emit("NEW_PROBE_POINT", "VOLUME", 3.0, 0.0, 0.3)
    script.emit(
        "NEW_STREAMLINE_DISTRIBUTION",
        position_1_x=2.0,
        position_1_y=-1.0,
        position_1_z=0.3,
        position_2_x=2.0,
        position_2_y=1.0,
        position_2_z=0.3,
        # Three rather than the reference run's five: the streamline file's
        # size is set by this number and not by the mesh, so the coarse wing
        # would not have shrunk it on its own.
        subdivisions=3,
    )
    script.emit("GENERATE_ALL_OFF_BODY_STREAMLINES")
    # THE SECTION PLANE IS OFF THE PANEL BOUNDARY ON PURPOSE, and the first
    # run of this script is why it is written down. A coarse wing puts its
    # spanwise panel boundaries at multiples of span/n_span, so y = 0 sits
    # exactly ON one, and the section came back `Edges=0`: a file with the
    # right header, the right terminator and no rows. That is a DEGENERATE
    # FIXTURE, the worst kind, because a parser written against it passes
    # while never having read a row. `SECTION_OFFSET_M` is between two
    # boundaries for every mesh this script uses.
    script.emit("CREATE_NEW_SURFACE_SECTION", 1, "XZ", SECTION_OFFSET_M, "1", "DISABLE", -1)
    script.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "COEFFICIENTS")

    def export(command: str, name: str, *args: object, **kwargs: object) -> None:
        produced[command] = name
        script.emit(command, *args, **kwargs)

    export("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads.txt", str(out / "loads.txt"))
    export(
        "EXPORT_SOLVER_ANALYSIS_CSV",
        "loads.csv",
        str(out / "loads.csv"),
        "CP-FREESTREAM",
        "PASCALS",
        1,
        -1,
    )
    export(
        "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS",
        "forces.txt",
        str(out / "forces.txt"),
        -1,
    )
    export("EXPORT_PROBE_POINTS", "probes.txt", str(out / "probes.txt"))
    export(
        "EXPORT_ALL_OFF_BODY_STREAMLINES",
        "streamlines.txt",
        str(out / "streamlines.txt"),
    )
    export("EXPORT_SURFACE_SECTIONAL_LOADS", "sectional.txt", str(out / "sectional.txt"))
    export("EXPORT_ALL_SURFACE_SECTIONS", "sections.txt", str(out / "sections.txt"))
    # `EXPORT_SURFACE_SECTIONS` (the single-section export) is NOT emitted
    # here and its absence is a finding rather than an omission. RPT-036b
    # observed the solver consuming the FOLLOWING LINE as its filename: the
    # entry declares `index: int` alone and the real layout carries a path on
    # its own line, so emitting it mid-script destroys the next command. The
    # 26.120 capture of that format is already committed; correcting the entry
    # needs the manual page and a probe report, not this run.

    # THE LOG IS EXPORTED BEFORE THE LAST EXPORT, not after, which is the
    # opposite of the obvious order and is what the first run taught. Every
    # command after a hang is never reached, so a log emitted last is the one
    # artefact you do not get from a run that hangs, and it is the one that
    # would have said where it stopped.
    script.emit("EXPORT_LOG", str(out / "log.txt"))

    # THE BOUNDARY-LAYER PROFILE IS EMITTED LAST AND UNDER PROTEST. It is
    # the one format no run has observed, and the reason is INTERACTIVITY
    # rather than a solver defect: `reports/RPT-027` measured on 26.122
    # that the command opens a modal window with a plot and a Done button,
    # and script processing stops there until a person dismisses it, under
    # `-hidden` with both streams redirected. Every unattended run of this
    # script since has reproduced that, on 26.123 as well.
    #
    # So it is placed after everything else, and the placement is the whole
    # mitigation: `--timeout` bounds the WHOLE RUN, not this command alone,
    # and putting this last is what makes that bound cheap, because
    # everything else is already written by the time it blocks. This comment
    # named a `--bl-timeout` that does not exist and claimed it bounded the
    # wait rather than the run, which is the inverse of what the real flag
    # does; an operator following it would have got `unrecognized arguments`
    # and then believed a bound they did not have.
    #
    # The arguments are the reference frame and a point near the upper surface.
    # The probe's spanwise station is off the panel boundary, on the same
    # reasoning as the section plane; whether that was the cause of the hang is
    # what this run asks and it is NOT assumed here. The filename is a path on
    # its OWN LINE, which the entry declares.
    export(
        "EXPORT_BL_VELOCITY_PROFILE",
        "bl_profile.txt",
        1,
        *BL_PROBE_M,
        str(out / "bl_profile.txt"),
    )
    script.emit("CLOSE_FLIGHTSTREAM")
    return script, produced


def build_sweeper(stl: Path, out: Path) -> tuple[Script, dict[str, str]]:
    """Emit a three-point angle sweep and its spreadsheet.

    A SEPARATE RUN, not another export appended to the one above, and the
    reason is the failure mode rather than tidiness: the sweeper re-solves the
    case once per point, so a sweeper that fails or runs long aborts a script
    that still had every other export ahead of it. Two runs cost a second
    start-up; one run costs the whole capture.

    Parameters
    ----------
    stl : Path
        The generated wing, already written.
    out : Path
        Directory the spreadsheet lands in.

    Returns
    -------
    tuple of Script and dict of str to str
        The script and the one file it asks for.
    """
    produced: dict[str, str] = {}
    script = Script(version=_version)
    script.comment("PFS-2014.02: the sweeper spreadsheet on a coarse wing, 26.123")
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", str(stl), clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SET_FREESTREAM", "CONSTANT")
    # Three angles, which is the smallest sweep whose spreadsheet still has
    # more than one row and therefore still shows a reader where the rows end.
    #
    # CUSTOM with the list inline, and the mode is not a guess: the entry's
    # note records that UNIFORM takes exactly three numbers read as
    # start/stop/INCREMENT, that CUSTOM takes either the list inline or the
    # path of a file holding it, and that NOTHING in the emitter enforces the
    # pairing. A first draft passed "ENABLE", which is not one of the three,
    # and the emitter refused it against the declared values with the page
    # citation. Passing the list inline under CUSTOM is the one form whose
    # meaning the note settles without relying on the unenforced pairing.
    script.emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", [0.0, 2.0, 4.0])
    script.emit(
        "INITIALIZE_SOLVER",
        solver_model="SUBSONIC_PRANDTL_GLAUERT",
        surfaces=-1,
        wake_termination_x="DEFAULT",
        symmetry="NONE",
        symmetry_copies=1,
        wall_collision_avoidance="DISABLE",
    )
    script.emit("SOLVER_SET_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_VELOCITY", 30.0)
    script.emit("SOLVER_SET_ITERATIONS", 200)
    script.emit("SOLVER_SET_CONVERGENCE", 1.0e-5)
    script.emit("SOLVER_SET_REF_AREA", COARSE.area_m2)
    script.emit("SOLVER_SET_REF_LENGTH", COARSE.chord_m)
    script.emit("SET_MAX_PARALLEL_THREADS", 8)
    script.emit("SWEEPER_START")
    produced["SWEEPER_EXPORT_SPREADSHEET"] = "sweep.txt"
    script.emit("SWEEPER_EXPORT_SPREADSHEET", str(out / "sweep.txt"))
    script.emit("EXPORT_LOG", str(out / "sweep_log.txt"))
    script.emit("CLOSE_FLIGHTSTREAM")
    return script, produced


def main() -> int:
    """Render, optionally run, and report what each export produced."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument(
        "--sweeper",
        action="store_true",
        help="run the sweeper script instead of the main capture",
    )
    # `--fs-version`, NOT `--version`, and the reason is written down at
    # `utils/cli.py`: every tool of this package spells the FlightStream
    # version that way (pyfs-qa, pyfs-matrix, pyfs-manual), and `--version`
    # is what a reader expects to print the PACKAGE's own version. This
    # script was the only place in the tree where `--version` named a
    # solver build, which is the quiet direction of that confusion: the
    # spelling that means "print and exit" everywhere else silently
    # retargeted a licensed run here.
    parser.add_argument(
        "--fs-version",
        dest="fs_version",
        default=VERSION,
        help=(
            "the build to emit under (default 26.123). A command with no row on "
            "the named build is REFUSED by the emitter rather than resolved, "
            "which is the guard rather than an obstacle."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help=(
            "seconds before the solver is killed. Deliberately minutes rather "
            "than the half hour a solve might want: this mesh solves in two "
            "seconds, so anything past a minute is a hang, and the one command "
            "here that has hung is emitted last."
        ),
    )
    args = parser.parse_args()

    global _version
    _version = args.fs_version
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stl = generate_wing_stl(COARSE, out / "wing.stl")
    print(f"geometry: {stl} ({stl.stat().st_size} bytes, generated, not private)")
    print(f"mesh:     {COARSE.n_chord} chordwise by {COARSE.n_span} spanwise")

    builder = build_sweeper if args.sweeper else build_capture
    script, produced = builder(stl, out)
    text = script.render()
    name = "sweeper.fsm" if args.sweeper else "capture.fsm"
    script_path = out / name
    script_path.write_text(text, encoding="utf-8")
    print(f"script:   {script_path} ({len(text.splitlines())} lines)")

    if args.dry:
        print("DRY: the script is rendered and nothing was run.")
        return 0

    executor = LocalExecutor(Path(args.exe))
    result = executor.run_script(script_path, out, timeout_s=args.timeout)
    print(
        f"solver exit: {result.return_code}, wall {result.wall_time_s:.1f}s"
        + (f", TIMED OUT after {args.timeout:.0f}s" if result.timed_out else "")
    )

    seen: dict[str, int | None] = {}
    for command, file_name in produced.items():
        target = out / file_name
        seen[command] = target.stat().st_size if target.is_file() else None
        state = "NO FILE" if seen[command] is None else f"{seen[command]} bytes"
        print(f"  {command:44} {state}")

    manifest = out / ("sweeper_manifest.json" if args.sweeper else "capture_manifest.json")
    manifest.write_text(
        json.dumps(
            {
                "build": _version,
                "mesh": {"n_chord": COARSE.n_chord, "n_span": COARSE.n_span},
                "geometry": "generated NACA 0012, qa.geometry.generate_wing_stl",
                "returncode": result.return_code,
                "timed_out": result.timed_out,
                "timeout_s": args.timeout,
                "produced": seen,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    got = sum(1 for value in seen.values() if value)
    print(f"\n{got} of {len(produced)} exports produced a file.")
    return 0 if got else 1


if __name__ == "__main__":
    raise SystemExit(main())
