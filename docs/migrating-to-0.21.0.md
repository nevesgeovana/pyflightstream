# Migrating to 0.21.0

0.21.0 renames every point. A workspace planned, submitted or run under
0.20.x keeps working, but only after one command has renamed it, and this
page is the step-by-step: what changed, what you run, and what each of the
other new switches asks of a file you already have.

Nothing here is optional reading for a cluster user: the names, the
`WALLTIME` unit and the profile's `[log]` table all refuse by name rather
than guessing, so a file that is not updated stops with a message instead
of running something you did not ask for.

## 1. The names

**What you had.** A point was `a+00.0_b+00.0_j+00.8`: the tag ended the
`run_id`, named the datapoint folder `DP-a+00.0_b+00.0_j+00.8`, and the
files beside it were named another way,
`POLAR-3207_M20AL+000BE+000J+080.txt`. The tag wrote one decimal per axis,
so J 0.80 and J 0.84 were one folder, and neither scheme carried the
Reynolds number, the altitude, or anything else the row declared.

**What you have now.** One name, written by the row's `FLIGHT_CONDITION`
cell: every variable it declares, in the order it declares them.

    FLIGHT_CONDITION: MACH:0.144, REmi:4.38, ALPHA:0, BETA:0, ADVANCE_RATIO:sweep
    the point at J 0.80  ->  M144RE438AL+000BE+000J+080

That one name ends the `run_id`, names the folder `DP-<name>`, and is the
stem of every file of the point, `P<sim>-<name>`:

    sims/sim_3207/datapoints/DP-M144RE438AL+000BE+000J+080/
        P3207-M144RE438AL+000BE+000J+080.txt
        P3207-M144RE438AL+000BE+000J+080_cp.txt
        P3207-M144RE438AL+000BE+000J+080_log.txt

The superfile is the same name with `SUPER-` and the swept field written
`<code>+sweep`: `SUPER-3207-M144RE438AL+000BE+000J+sweep_g01.csv`.

The code and the digits of each variable are in
[How a point is named](workspace-and-workflows.md#how-a-point-is-named).
Read that table before you rename, because the names it gives are the ones
your folders will carry.

## 2. Rename the workspace you already have

    pyfs-matrix rename --workspace <campaign root>

It reads the matrix and the manifest, works out the new name of every
record from its row and its recorded point, and then renames the datapoint
folders, the scripts and the collected files, rewrites the manifest, and
rewrites `plan.json` in place so it matches without needing your recipes or a
solver version. It prints every change; running it a second time changes
nothing.

**Your products are rebuilt, not moved.** The tables under `post/` keep their
0.20.x names until you rebuild them, so run `pyfs-matrix post --workspace
<root>` after the rename: the polars, the superfiles and the series tables are
then written under the new names. **THE 0.20.x-NAMED TABLES ARE LEFT WHERE THEY
ARE, and deleting them is yours.** The post stage archives a product it is
about to OVERWRITE, and a table under the old name is at a different path, so
nothing overwrites it and nothing archives it. Until you remove them your
`post/` folder holds both conventions.

**Before it touches anything** it refuses, by name, a record it cannot map:
one whose simulation has no row in the matrix, one whose recorded flow
state differs from the row's (the matrix changed since the run), and two
records whose new names would collide. Fix what it names and run it again.

**Collect your queued jobs first.** A submitted job writes into the folder
its descriptor named, so a workspace with a `SUBMITTED` record whose folder
would move is refused: run `pyfs-matrix collect` until nothing is
outstanding, then rename. A submitted point written by 0.20.x collects into
the folder it ran in, so this order works on a workspace that has never been
renamed.

**If you tried this under 0.21.0 and it failed**, the collecting sweep refused
those records and wrote them back as `FAILED_INCOMPLETE_OUTPUT`, which also
cleared the `SUBMITTED` state. Restore `runs.json` from a backup if you have
one; if you do not, the outputs are untouched on disk and the records have to
be set back to `SUBMITTED` by hand before collecting again. 0.21.1 fixes the
cause.

**What is not renamed.** Nothing outside the workspace: your matrix file,
your inputs library and your own notes keep their names. Nothing under `post/`
either: the products are REBUILT under the new names by `pyfs-matrix post`,
which is the step after this one. The manifest is archived before it is
rewritten.

**If you pass `--point-name`, read this twice.** The placeholders moved with
the names: `{point}` is now the point name and `{polar}` is `P<sim>-<name>`. A
template of your own still renders, so this is the one change in the release
that reaches you WITHOUT a message -- your files simply come out under different
names. Check your template before the first run.

**If you do not rename**, the post-processing stages refuse a record written
before 0.21.0 and say so, naming this command. `collect` does not refuse it:
since 0.21.1 it collects such a record IN PLACE, under the datapoint folder the
record's own submission block names. Neither of them guesses a name for it, and
`pyfs-matrix rename` is still what names it.

## 3. `WALLTIME` now carries its unit

The column takes the unit with the number:

    WALLTIME: 240m        four hours, written in minutes
    WALLTIME: 4h          the same four hours

A bare `240` is refused by name: it read as seconds in one place and as
minutes in another, and a walltime that means two things is a job that
either dies early or holds a node for a day.

The descriptor your scheduler receives carries the value **as you wrote
it**, so a profile whose template writes `#SBATCH --time={walltime}` gets
`4h` when you wrote `4h`. If your scheduler wants it another way, the HPC
profile's `walltime_arithmetic` says which; the default is `wall`, the
value as written.

## 4. The HPC profile's `[log]` table

Some clusters abort at `EXPORT_LOG` and write their own log beside the run
instead. The profile now says so, rather than the package assuming one
shape of machine:

    [log]
    export_log = false
    native_log = "FTS{sim}.l*"

- `export_log = false` leaves `EXPORT_LOG` out of the script.
- `native_log` names the file the scheduler writes; `collect` copies it to
  the standard log name, so everything downstream reads one file.
- `export_log = false` with no `native_log` is refused: that combination
  asks for a run with no log at all.
- Several files matching `native_log` are refused, because the copy would
  otherwise pick one of them silently.
- **The profile's keys are now a CLOSED set**, at the top level and inside
  `[log]`. A key outside it is refused by name rather than ignored, so a
  profile that carried a `notes =` line, or that spelled `native_log` wrongly,
  stops at the refusal instead of reaching `EXPORT_LOG` on the cluster and
  aborting the job there. If your profile carries anything of your own, move
  it out before you run.

A profile that says nothing keeps 0.20.x behaviour: the script exports the
log itself.

## 5. `--accept-unregistered-build`

`plan` and `run` take `--accept-unregistered-build`. Without it, a
workstation build other than the one registered for the version a row names
is refused, and the refusal now names the flag. With it the run proceeds,
warns, and every record says the flag was used and carries the build the
solver printed; `plan.json` records it too.

Use it when you know your installation is compatible and the package does
not know it. The compatibility is then yours to judge.

## 6. Sweeping, RPM and a rotating free stream

These add to what a row may write; they take nothing away.

- **Any `FLIGHT_CONDITION` variable sweeps**, not only `ALPHA`, `BETA` and
  `ADVANCE_RATIO`. Write `sweep` against the key and list the values in
  `SWEEP_VALUES` as before. Each point carries its own value and its own
  name.
- **`RPM` may be stated in `FLIGHT_CONDITION`** and swept. A `MOTIONS`
  record naming a speed still wins over it. `RPM` with `ADVANCE_RATIO` and
  a velocity (`MACH` or `TASmps`) is refused, because the three over-state
  the point; `RPM` with `ADVANCE_RATIO` and no velocity computes the
  velocity, V = J x (RPM/60) x D, with D the diameter of the rotor the
  `CLOCK_MOTION` names. A row naming no such rotor is refused by name.
- **A rotating free stream**: one of `roll_rate`, `pitch_rate`, `yaw_rate`
  in deg/s, in the flight-mechanics sign convention, about the moment
  reference point of the row's `REF`, which declares the model's axis
  orientation. The script then writes `SET_FREESTREAM ROTATION` instead of
  `CONSTANT`. Two non-zero rates in one row are refused by name; so is a
  rate with a `REF` that declares no axes. All-zero rates write `CONSTANT`,
  as before.

## 7. The order to do it in

1. Read the code table, so you know what your points will be called.
2. `pyfs-matrix collect` until nothing is outstanding.
3. `pyfs-matrix rename --workspace <root>`, and read what it printed.
4. `pyfs-matrix post --workspace <root>`, to rebuild the products under the
   new names.
5. Put the unit on every `WALLTIME` cell.
6. If your cluster writes its own log, add `[log]` to its profile.
7. Run as before.
