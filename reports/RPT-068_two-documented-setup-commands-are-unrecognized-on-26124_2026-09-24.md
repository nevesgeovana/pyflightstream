# RPT-068: two documented setup commands are unrecognized on 26.124 (2026-09-24)

**Date:** 2026-09-24
**Found by:** a licensed probe of the 0.27.0 work, run before item G14 was built
**Status:** REGISTERED for 0.27.0 (G14: both setup keys are refused on 26.124 at plan, naming this report, and the 26.124 rows record the build's answer)
**Affects:** `SET_VORTICITY_LIFT_MODEL`, which the command database records as documented on every build and never run, and `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION`, documented only by the 25.000 to 26.000 editions

## What this settles

Item G14 gives two solver commands a setup key each, so a run can state them
instead of passing them as raw script lines. Neither command had ever run on any
build. **On FlightStream 26.124 both are answered exactly as a name no build
documents is answered: "Unrecognized command", and the script stops there.** The
26.124 manual documents the first of the two, so the page and the build disagree
here. A setup key that emitted either command on 26.124 would stop the run at
that line.

## What was run

FlightStream 26.124, four short runs with no solve, launched one at a time,
detached, with no solver alive before the first. Every run opens a copy of the
half wing-body of RPT-052 (the blank line after the path), prints a sentinel,
runs ONE block, prints a second sentinel, exports its log and closes. The
control runs nothing between the sentinels. The positive control runs a name no
edition documents, so the run shows what an unknown command looks like on this
build.

    instrument  whether the script reaches the second sentinel and exports its
                log, and the solver's own log (FlightStreamLog.txt), which the
                build writes when a script ends abnormally
    build       FlightStream 26.124 (build 8172026, executable sha256 68e64e66...)

## What came back

| run | the one block | second sentinel | log exported | the solver's own log |
|---|---|---|---|---|
| control | nothing | reached | yes | no error |
| positive control | `PYFS_NO_SUCH_COMMAND 1` | not reached | no | `Unrecognized command` |
| vorticity lift | `SET_VORTICITY_LIFT_MODEL ENABLE` | not reached | no | `Unrecognized command` |
| viscous coupling | `SET_UNSTEADY_VISCOUS_COUPLING_ITERATION 5` | not reached | no | `Unrecognized command` |

Each stopped run's log carries the same two lines as the positive control's: a
syntax error naming the line and "Unrecognized command", then a scripting error
at that line. The return code is 0 in all four, so only the log tells a stopped
script from a finished one.

## What it means for the package

- The two G14 keys are built, and each is validated against the command
  database for the row's build. The 26.124 rows record the build's answer, so
  a row on 26.124 stating either key is refused at plan, naming this report,
  instead of stopping mid-run. On the builds whose editions document a command,
  the key emits it, and that is documented, not verified.
- The command database's note on the vorticity lift model names the
  Kutta-Joukowski lift forces as another route to the same quantity; whether
  that route gives on 26.124 what this command was meant to give is not
  measured here.

## What this does NOT establish

- **Whether the builds before 26.124 answer either command.** Only 26.124 was
  run.
- **Whether the vorticity lift model moved under another name** in 26.124. The
  build answered the documented name only.
- **Whether a script that initialises first answers differently.** The block
  ran after `OPEN`, before any initialisation. There, the build treats both
  names as it treats the positive control's; another place in a script was
  not tried.

## Evidence

`reports/probes/RPT-068_2026-09-24_evidence.yaml`: per run, the block, whether
the second sentinel was reached and the log exported, the solver's error lines
with the machine-local path cut, and the script's digest; the four checks as
booleans. The solver outputs stayed on the measuring machine (invariant 5).
