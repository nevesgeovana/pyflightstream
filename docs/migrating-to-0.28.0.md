# Migrating to 0.28.0

This release adds capabilities a user reaches from the matrix, the command line
and the input files, and refuses a few inputs that were accepted without doing
what they said. Recorded run manifests are read without rewriting them. What
changes for you is listed below, one section per change.

## 1. An unsteady row refuses `COLD_START` (G36)

- `COLD_START` is a key of a steady sweep over the attitude: it clears the
  solution before each point, which otherwise starts from the previous point's
  converged one. Every point of an unsteady or rotor row is its own job and
  starts from no solution, so the key changed nothing there, and the plan now
  refuses an unsteady row that states it, `true` or `false`, naming the key.
  Remove `COLD_START` from such a row. A steady row is unchanged.

## 2. A warning when a plot group takes the rotor table's name (G42)

- A pproc plot group named like the automatic `ROTOR_<ALIAS>` group (for
  example `ROTOR_{family}` in the rotor's own frame) now draws a warning at plan
  and before a run: that rotor's table will not be written, because the run
  keeps your group and the table reads the automatic one in the global frame.
  Nothing else changes. To keep both, rename the group, `SHAFT_{family}` for
  instance.

## 3. `--force-rerun` of one point of a steady job redoes the whole job (G37)

- A steady row runs as one warm job. Naming one of its points to
  `--force-rerun` (by point name or run_id) now runs every point of the job
  again as one job, and a warning lists them; before, it ran the named point
  alone, cold, and the other points lost their record. Naming the job itself
  (`<campaign>/sim_<id>/sweep`) is unchanged. A point added to the row after
  the job ran and recorded on its own (`--resume`) runs again inside the job,
  and its old record is archived with the job's.

## 4. `--force-rerun-all` and `--sims` (G44)

- New: `pyfs-matrix run <matrix> --force-rerun-all` redoes every recorded point,
  and `--sims 2031 2032` narrows it to those simulations. A script that built a
  list of `--force-rerun` flags from `runs.json` can use this instead. Nothing
  that existed changes.

## 5. A run that submits does not post, and a local run's log (G43)

- `pyfs-matrix run` that submits any point to a cluster no longer writes
  products or the sweep table, also when another point of the same run failed;
  it ends with a line naming what was submitted
  and the next command, `pyfs-matrix collect --workspace <root>`, which
  collects and then posts. A script that read `post/` right after a submitting
  run reads it after `collect` instead.
- A local run prints a banner, numbers its points (a steady job its range of
  points) and ends with a table that counts points, not jobs; an
  unsteady point with a step counter prints its progress every 10 steps.
  `--progress-every N` changes the cadence and `--progress-every 0` turns it
  off. The lines go to stderr, as every progress line always has; stdout and
  the records are unchanged.

## 6. An actuator disc from the advance ratio (G20)

- A disc row may state `ADVANCE_RATIO` instead of `ACTUATOR_RPM`; the speed is
  derived with the disc's own diameter. A row that states `ACTUATOR_RPM` is
  unchanged. The refusal of a disc row stating neither now names both keys.
- A steady row that sweeps `ADVANCE_RATIO` for its disc runs one job per point,
  not one warm job, because each point sets its own disc speed.
