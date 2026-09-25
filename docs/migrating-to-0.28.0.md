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
  (`<campaign>/sim_<id>/sweep`) is unchanged.

## 4. `--force-rerun-all` and `--sims` (G44)

- New: `pyfs-matrix run <matrix> --force-rerun-all` redoes every recorded point,
  and `--sims 2031 2032` narrows it to those simulations. A script that built a
  list of `--force-rerun` flags from `runs.json` can use this instead. Nothing
  that existed changes.
