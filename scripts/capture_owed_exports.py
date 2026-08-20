"""Capture one observed file per OWED export command, in ONE licensed run.

    python scripts/capture_owed_exports.py --exe <path> --out <dir> [--dry]

WHY THIS EXISTS. `PFS-2014.02` asks that every export in the default set
have a parser and a tabular conversion. Seven entries of
`results.EXPORT_CONVERSIONS` are classified `EXPORT_OWED`, and six of
them give the same reason: "no observed export captured". A parser for a
format nobody has observed is a guess, and this repository does not ship
guesses. So the blocking artefact is not code, it is FILES, and the
licensed run sheet's own rule applies: produce the artefacts early,
because the code can be written while the solver is busy and the file
cannot be written after the licence is gone.

THE GEOMETRY IS SYNTHETIC AND THAT IS THE POINT. It is the NACA 0012
wing this package generates for its own physics cases, written by
`qa.geometry.generate_wing_stl`. A capture made on the author's research
geometry could never be committed as a test fixture (invariant 5), which
would leave every parser written against it untestable in tier 1. A
generated wing has no such problem: the bytes are ours.

THE BUILD IS 26.120 AND NOT THE NEWEST. 26.123 is registered with
`inherits_base: false`, so a command with no 26.123 row of its own is
REFUSED rather than resolved from the base release, and two of the seven
(`EXPORT_SOLVER_ANALYSIS_CSV`, `EXPORT_BL_VELOCITY_PROFILE`) carry no
such row. Several of the seven are already `verified` on 26.120, meaning
a probe has seen them work there. Capturing on the build that documents
all seven is what makes one run enough.

ONE RUN, NOT SEVEN. The run sheet forbids spending the same run twice.
Every export is emitted into a single solved case, and the preconditions
each one needs are emitted with it rather than being discovered by a
second checkout.

WHAT IT DOES NOT DO. It does not promote a status, write a compat report
or edit the command database: an observed export is evidence for a
PARSER, and a status moves only through the sanctioned probe path
(invariant 3). It writes files and a manifest of what it saw.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from pyflightstream.qa.geometry import generate_wing_stl  # noqa: E402
from pyflightstream.qa.physics import PHY01_WING  # noqa: E402
from pyflightstream.run import LocalExecutor  # noqa: E402
from pyflightstream.script import Script, helpers  # noqa: E402

#: The seven, each with the precondition it needs before it will write
#: anything. An export that silently writes nothing is the failure mode
#: that wastes the seat, so the preconditions are emitted rather than
#: assumed.
OWED = (
    "EXPORT_SOLVER_ANALYSIS_CSV",
    "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS",
    "EXPORT_SURFACE_SECTIONS",
    "EXPORT_ALL_SURFACE_SECTIONS",
    "SWEEPER_EXPORT_SPREADSHEET",
)

VERSION = "26.120"

#: `EXPORT_BL_VELOCITY_PROFILE` is NOT in the list above, and its absence
#: is the run's first finding rather than an oversight. The emitter
#: refused it against 26.120: its only recorded evidence is 26.122 and
#: 26.123. It needs its own capture on one of those, which is a second
#: run answering a DIFFERENT question rather than the same run spent
#: twice. `EXPORT_SOLVER_ANALYSIS_CSV`, meanwhile, carries no 26.123 row
#: at all, so no single build captures both.
SECOND_RUN_OWED = (
    "EXPORT_BL_VELOCITY_PROFILE",
    "EXPORT_ALL_OFF_BODY_STREAMLINES",
)


def build_script(stl: Path, out: Path) -> Script:
    """Build the one script that solves once and exports seven ways.

    Parameters
    ----------
    stl : Path
        The generated wing, already written.
    out : Path
        Directory the exports land in.

    Returns
    -------
    Script
        The script, rendered by the caller.
    """
    # THE PRELUDE IS THE PHYSICS HARNESS'S, command for command, rather
    # than one written here. Two names were invented on the first attempt
    # and the emitter refused both against the database, which is the
    # guard doing its job: SET_AOA and SET_VELOCITY do not exist,
    # SOLVER_SET_AOA and SOLVER_SET_VELOCITY do.
    script = Script(version=VERSION)
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT", "METER", "STL", str(stl), clear=True)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SET_FREESTREAM", "CONSTANT")
    script.emit("SOLVER_SET_AOA", 4.0)
    script.emit("SOLVER_SET_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_VELOCITY", 30.0)
    script.emit("SOLVER_SET_REF_AREA", PHY01_WING.area_m2)
    script.emit("SOLVER_SET_REF_LENGTH", PHY01_WING.chord_m)
    script.emit("SOLVER_SET_ITERATIONS", 120)
    script.emit("SOLVER_SET_CONVERGENCE", 1.0e-4)
    script.emit("START_SOLVER")
    script.emit("SET_LOADS_AND_MOMENTS_UNITS", "COEFFICIENTS")

    # THE PRECONDITIONS, emitted rather than assumed. An export whose
    # subject does not exist writes nothing and the seat is spent on a
    # file that never appears. A surface section must be CREATED before
    # it can be exported, and a streamline must be seeded and generated.
    script.emit("CREATE_NEW_SURFACE_SECTION", 1, "XZ", 0.0, "1", "DISABLE", -1)
    # THE STREAMLINE SEED IS NOT EMITTED and its export rides with it.
    # `NEW_OFF_BODY_STREAMLINE` is recorded BROKEN on this build by a
    # committed probe report: script processing aborts at the command,
    # and the solver accepts the line, so the run would return numbers
    # nothing marks as wrong. The emitter refused it, which is the third
    # time in building this one script that the database stopped a seat
    # from being spent on a file that would never appear.

    # The spreadsheet is the one already-parsed export, captured beside
    # the others so the seven can be read against a file whose meaning is
    # known.
    helpers.export_results(script, spreadsheet=str(out / "control_spreadsheet.txt"))

    emitted: list[str] = []
    for command in OWED:
        target = out / f"{command.lower()}.txt"
        try:
            if command == "EXPORT_SOLVER_ANALYSIS_CSV":
                # Five arguments the database names and the first attempt
                # omitted: the emitter refused it rather than letting the
                # solver decide what a one-argument call meant.
                script.emit(command, str(target), "CP-FREESTREAM", "PASCALS", 1, -1)
            elif command == "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS":
                script.emit(command, str(target), -1)
            elif command == "EXPORT_SURFACE_SECTIONS":
                # An INDEX, not a path: it exports one created section,
                # and the file name is the solver's to choose.
                script.emit(command, 1)
            else:
                script.emit(command, str(target))
            emitted.append(command)
        except Exception as refused:  # noqa: BLE001 - the refusal is the finding
            print(f"  REFUSED at build time: {command}: {refused}")
    script.emit("EXPORT_LOG", str(out / "run_log.txt"))
    print(f"  emitted {len(emitted)} of {len(OWED)} owed exports")
    return script


def main() -> int:
    """Render the capture script, run it, and report what each export produced."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stl = generate_wing_stl(PHY01_WING, out / "wing.stl")
    print(f"geometry: {stl} ({stl.stat().st_size} bytes, generated, not private)")

    script = build_script(stl, out)
    text = script.render()
    script_path = out / "capture.fsm"
    script_path.write_text(text, encoding="utf-8")
    print(f"script:   {script_path} ({len(text.splitlines())} lines)")

    if args.dry:
        print("DRY: the script is rendered and nothing was run.")
        return 0

    executor = LocalExecutor(Path(args.exe))
    result = executor.run_script(script_path, out, timeout_s=900.0)
    print(f"solver exit: {result.return_code}, wall {result.wall_time_s:.1f}s")

    seen = {}
    for command in OWED:
        target = out / f"{command.lower()}.txt"
        seen[command] = target.stat().st_size if target.exists() else None
        state = "no file" if seen[command] is None else f"{seen[command]} bytes"
        print(f"  {command:44} {state}")

    (out / "capture_manifest.json").write_text(
        json.dumps(
            {
                "build": VERSION,
                "executable": str(args.exe),
                "geometry": "generated NACA 0012, qa.geometry.generate_wing_stl",
                "returncode": result.return_code,
                "produced": seen,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    produced = sum(1 for value in seen.values() if value)
    print(f"\n{produced} of {len(OWED)} owed exports produced a file.")
    return 0 if produced else 1


if __name__ == "__main__":
    raise SystemExit(main())
