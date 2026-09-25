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

## 7. A template of every input file (G47)

- New: `inputs/input_template.md`, written by `pyfs-workspace init`, `pyfs-matrix
  plan` and `pyfs-matrix post` at the root of `inputs/`, beside the folders whose
  files it shows. One section per kind of input file you write (the matrix, the
  setup, the pproc, the reference, the named points, the geometry sidecars, the
  trailing-edge points file, the provenance record, the actuator profile and the
  probe survey of `profiles/`, the free stream, the HPC profile and the build
  registry), each with a complete example to copy to the path its title names.
  `inputs/pproc/INPUTS.md` stays where it is, and the template links it. A
  workspace made before this release gains the page at its next `plan` or
  `post`; nothing else in it changes, and a file of your own under that name
  would be rewritten, as `INPUTS.md` is.
- Three files the page's examples showed were not read as documented now are:
  a reference whose `[rotor]` states `hub_radius_m` was refused as an actuator
  disc with no kind; a pproc stating the top-level `vtk_variables` was refused
  as an old-shape groups file; and a steady row whose pproc draws a probe
  rectangle or circle failed to plan, its `NEW_PROBE_POINT` lines missing the
  `VOLUME` type. All three are read, and plan, as written.

## 8. The custom free stream: the UNSTRUCTURED form, and a warning (G18)

- A `FREESTREAM` naming a `.dat` (the UNSTRUCTURED form) now has a measured
  run behind it (RPT-077); nothing a row writes changes.
- New: the plan warns when the field's grid does not reach the whole body,
  naming both extents. Beyond its grid the solver does not extend the field.
  A run is not refused; widen the grid if the whole body should see the field.
- A row whose field carries an incidence reads its body forces Cx, Cy and Cz:
  its CL and CDi are printed in the axes of the zero angle the row states.

## 9. An OBJ's surface names are read from its groups (G30)

- An `.obj` a row names no longer needs its `boundaries` written by hand. When
  it has no `<stem>.boundaries.toml`, `pyfs-matrix plan` (and `run`) writes one
  beside it holding the list, one name per `o` or `g` group that holds a face,
  in the order of the file, and says so on stderr. Add the `[import]` units and
  `[trailing_edges]` beneath the list, as before; the plan that wrote it blocks
  the row on the missing unit until you do. `pyfs-matrix inventory <file>.obj`
  writes the same file.
- A sidecar you already have is kept as it is and never rewritten, and
  `pyfs-matrix inventory` refuses an `.obj`'s existing sidecar, `--overwrite` or
  not. If its `boundaries` differ from the file's groups, in a name or in the
  order, the run still cites your list, and the plan now warns naming both
  lists: check which one is right before the next run.
- An `.obj` that mixes `o` and `g`, opens one group name twice, writes a face
  before its first group, or has a group statement naming no group or several
  words, and has no sidecar, is refused at plan naming the line; write its
  `boundaries` by hand, as before. An `.stl` is unchanged.

## 10. The solver's plots on an unsteady row (G26)

- An unsteady row now saves `<point>_plot_residuals.txt` and
  `<point>_plot_loads.txt` by default, once, at the end of the march. A script
  that counted the files of an unsteady point finds two more; `plot_residuals =
  false` and `plot_loads = false` under `[exports]` turn them off.
  `plot_residuals = true` on an unsteady row, refused before, is accepted.
  `plot_sections_cp = true` on an unsteady row is still refused.

## 11. The boundary-layer profile is refused on 26.124 (G24)

- A row writing `EXPORT_BL_VELOCITY_PROFILE` raw on 26.124 is refused at plan: the
  command holds an unattended script (RPT-075). Nothing else changes; the VTK
  surface export carries the boundary-layer thicknesses.

## 12. Steady probes in a frame are placed where the frame stands

- A steady row whose pproc declares probe lines, rectangles or circles in a frame
  other than the reference (MRP, or a frame the reference declares) now samples
  them where that frame stands: the points are carried into the reference frame
  by the frame's origin and axes. Before, they were emitted at the frame's own
  coordinates, which is right only for a frame at the reference origin. A steady
  run of such a row samples different points than before; the probe table names
  the same declared positions. Unsteady rows are unchanged.
- The custom free stream's coverage warning (G18) now says, for a row that moves
  the body (ROTATE, TRANSLATE, rotor MOTIONS or an import operation), that the
  coverage was not checked, instead of comparing the body where its file holds it.

## 13. The Tecplot surface is written from the VTK (G45)

- The script no longer asks the solver for the Tecplot: it exports the surface
  as VTK and the package writes `<point>.dat` from it, at the same name and in
  the same folder, per step too. A script or a Tecplot layout that reads the
  `.dat` finds it where it was, and reads a different file:
  - **The values are per cell, not per node.** The zone is still one FEPolygon
    zone of the same nodes and polygons, and every variable but `X`, `Y`, `Z` is
    now cell-centred, the value the solver computed on each panel. A layout that
    contoured nodal values contours cell values; a script that indexed a
    variable by node must index it by polygon.
  - **The names are the VTK's.** `Cp` is now `Cp_reference`, beside a new
    `Cp_freestream`; `CF` is `skin_friction_coeff.`; `Mach Number` is
    `Mach_Number`; `BL Thickness`, `BL streamline length`, `Transition marker`
    and `Separation marker` take underscores. Seven variables are new, among
    them `Normalized_Vorticity` and `Boundary_Index`.
  - **`Singularity_strength` is gone**: the VTK does not carry it, so no
    translation can.
  - The nodes and the velocity components are in the reference frame, as the
    solver's Tecplot was.
- `<point>.vtk` now sits beside every `<point>.dat` and is listed among the
  point's outputs, since the `.dat` is written from it and names it.
  `[exports] vtk = true` gives that same file, not a second export.
- A row whose loads frame the script does not place, or whose pproc's
  `vtk_variables` names one or two of `VX`, `VY`, `VZ` while its loads frame
  moves, is refused at plan, naming the frame; name all three components or
  none. A continuation of a run recorded before 0.28.0 is refused before the
  solver starts unless its pproc sets `tecplot = false`, since that run recorded
  no placement of its loads frame.
- A `.dat` a run wrote before 0.28.0 is the solver's own and stays so.

## 9. `[time_averaging]` now works (G25)

- A pproc carrying `[time_averaging]` was refused at plan on every build, because
  the solver's own averaging command hangs 26.124. It now plans and runs: the
  row exports its surface at every time step of the window, and `pyfs-matrix
  post` writes `post/<matrix>/surfaces/<point>_time_average.dat` (and a `.vtk`
  beside it with `[exports] vtk = true`), the average of those steps, cell by
  cell, in the reference frame. Remove nothing to use it; keep `tecplot` on
  under `[exports]`, the default.
- The per-step exports are the ones `EXPORT_UNSTEADY_AFTER_ITER: <first step of
  the window>` would give, so a row stating no threshold now leaves one VTK, one
  Tecplot, one loads table and the sections of every step of its window in its
  datapoint folder, and their series tables under `series/`. A row whose own
  threshold starts after the window is refused, naming both steps; lower the
  threshold to the window's first step.
- The build must carry the unsteady solver action (26.122 on). A steady row and
  an additional pproc still refuse the table.
- A run recorded before 0.28.0 is read as it was.
