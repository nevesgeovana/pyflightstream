# Migrating to 0.24.0

This release changes NUMBERS that 0.23.0 published, changes the header of almost
every table the post stage writes, and asks one new thing of a matrix row. Read
this before you upgrade a workspace you care about.

**Almost everything below is produced by posting again, with no solver:**

```
pyfs-matrix post --workspace <root>
```

over outputs you already collected, on Windows and on the cluster. What posting
again cannot give you is named where it applies: three things need a NEW run,
because they are about what the script asks the solver to plot or record.

No run record is rewritten by any of this. Where a record and today's matrix
disagree, the products follow the rule stated in each section and the record stays
as it was written.

---

## 1. Numbers that change

Each of these is a number a file of 0.23.0 stated and a file of 0.24.0 states
differently. None needs a solver run unless it says so.

### `ETAW` and the shaft angle, wherever alpha or beta is not zero

The free-stream direction the rotor table projected the force on had the wrong
sign in y and in z. It is `(cos a cos b, -cos a sin b, +sin a)` in the export's
frame, x aft, y right, z up: measured on the recorded exports, whose own drag is
the projection of their own force vector on it. `ETAW` and `shaft_angle_deg`
change on every rotor row with incidence or sideslip. At zero incidence and zero
sideslip nothing moves. `ETAW` equals `ETA` when the shaft lies along the stream.

### `CLS`, `CLW`, `CDB` and `CLB` of every steady polar

Every axis column of a steady polar row is now built from the force
`(Cx, Cy, Cz)` and the moment `(CMx, CMy, CMz)` the export states, turned in one
place. `CDB` IS the export's `Cx` and `CLB` its `Cz`. 0.23.0 took the solver's
`CL` and `CDi + CDo` as stability-axis forces and turned them back.

The `CL` an export prints sits between 0.10 and 0.25 per cent above the wind-axis
lift of the vector printed beside it on 27 of the 28 lifting recorded exports
(lift above 0.05); one sits at 0.71 per cent. The measurements are in
`tests/tier1_offline/fixtures/recorded_total_rows.csv`, and the cause is not
known. **`CLS` and `CLW` fall by the measured gap, zero sideslip included.** On one recorded
point at alpha -2: `CLS` 0.18828 becomes 0.18800, `CLB` 0.18744 becomes 0.18716,
`CDB` 0.02744 becomes 0.02743. `CDS`, `CDW`, `CD0`, `CDI` and the moments at zero
sideslip do not move.

A point under sideslip is no longer refused: it is a row like any other.

### An unsteady point with no `LAST_REVS_AVG` stops publishing its last time step

A run recorded before the window was stated on the row has no `LAST_REVS_AVG` (or
`LAST_ITERS_AVG`) to read. 0.23.0 wrote such a point's group polars from the native
export, which states the **last time step** of the run. 0.24.0 averages it over
the window its run recorded (the run's default, or a retired `WINDOW_*` key of the
row), says so in a warning naming the steps and where they came from, and writes
`P<sim>_<name>_uns_avg.csv`; the per-group polars of that point are no longer
written. State the key on the row and post again to choose the window.

### `AZIMUTH` of a sections table

It was one number for the whole file: the row's clock rotor, turned from zero,
unsigned, on wing rows too. It is where BLADE ONE OF THE ROW'S OWN ROTOR is,
`(blade1.azimuth_deg + sense * STEP * 360 / steps_per_revolution) mod 360`, and
`NA` on a surface no rotor owns. A run made before 0.24.0 did not record which
rows belong to which surface and states `NA`.

### `time_average`, `per_blade` and `phase_locked` follow the MATRIX

If you edited `LAST_REVS_AVG` on a row after the run, 0.23.0 moved the unsteady
polar to the new window and left `time_average`, `per_blade` and `phase_locked` on
the recorded one. One resolver serves all of them now, and posting again moves
every reduction of the point together.

### `MACH`, `VINF` and the air, on a sweep of a flow variable

A sweep over `MACH`, `TASmps`, `dISA` or `ALTFT` wrote every row with the FIRST
point's Mach, velocity and density. Each row now states its own, resolved again
from its matrix row; the post stage warns where that differs from the record. A
sweep over alpha, beta or the advance ratio is unaffected.

### `ALT`

A sections table said `ALT 0.00000` on a row flown at altitude, because it read
the export's header line, which the campaign never sets; a rotor table said `NA`.
Both state the altitude the row states, and `NA` where it states none.

### `Time-step` leaves the reductions

A reduction is an average over a window, and the mean of a step counter measures
nothing. The `Time-step` and `Time (sec)` columns are gone from every
`_time_average` and per-rotor reduction; the window is `FIRST_STEP`, `LAST_STEP`,
`STEPS`. **If you read those files by column POSITION, every position moved.**

### A zero that was not a measurement

A polar group whose alias no longer selects any surface, a group stated as integer
positions, and a rotor whose families select nothing each wrote a row of zeros.
Each is now a named skip in `products.json`. A `[groups]` entry is ONE alias,
written as a string; the list form still binds and warns.

### A point accepted by mistake is a failure now

On the collected (cluster) path: a run forced to its iteration limit whose export
was written before the end, WITH a solver log saying so, was recorded as
converged; and a point whose exported velocity is not the requested one was not
assessed at all. Both are recorded as failures and leave the products. The log is
read for completeness and no longer overrides it.

### A continued point is in its tables once

A run that reached its iteration limit and was then continued with `RESTART` put
the point in its polar and in the sweep table twice, both rows carrying the
continuation's numbers. The run that was continued is left out and named under
`skipped`. This reads the `continues` field a continuation records since 0.24.0; a
chain recorded before it is unchanged.

### `SREF` and `CREF` are checked against the export

The package sets neither; the solver divides by the area and the length of the
project file it opened, and prints both. Where they differ from the reference the
products would state, beyond the three decimals the export prints, the
simulation gets NO product and both numbers are named. A workspace whose artifact
and project agree is unaffected; one that is refused was publishing coefficients
wrong by a constant factor.

### The rotor table of an unsteady point is the window average

**Every rotor table of an unsteady point held the last time step**, because its
average was looked for under a column name no run printed. It now holds the
average over the row's window, found through the pproc: the plot group in the
global `MRP` frame whose families are exactly the rotor's general and blade
families. On a recorded licensed rotor point the two differ by 43 per cent:
-410.75 N at the last step against -287.82 N over the row's window
(`reports/RPT-053`).

**This one needs a NEW run for most workspaces.** A pproc that plots `FX, FY, FZ,
MX, MY, MZ` for such a group already gets the average by posting again. Any other
gets, from a new run, the group the run now adds itself, `ROTOR_<ALIAS>`. A
campaign run before 0.24.0 without such plots gets NO rotor table for its unsteady
points, with the reason in `products.json`: a row that states a window never holds
an instant. A group over the blades alone is not the rotor's history when the
rotor also owns a spinner, and a group in the rotor's own frame is never the
source.

### A periodic sector: no number changes for symmetry

A row that solves one periodic sector (`SYMMETRY PERIODIC <copies>`) with the
symmetry loads enabled gets, from the solver, the forces of the WHOLE rotor:
the export's blade row already carries every copy. The package counts the
copies ONCE, by reading that row, and never multiplies again. Nothing about
this changes in 0.24.0; it is stated here because the rotor table of such a
row was suspected of a symmetry factor, and the factor was the last time step
against the window average of the section above, not the copies.

Measured on a licensed periodic sector of six copies: the rotor's own history
reports a force along the shaft and nothing across it (the two cross
components are zero to the export's precision), and the rotor table of that
point equals the window mean of that history. How such a sector compares with
a full wheel solved separately is a question about the two geometries, not
about the package, and the licensed comparison is in `reports/pfs0240/`.

---

## 2. One new thing a matrix row must say

An unsteady row states its averaging window, or `pyfs-matrix plan` refuses it
naming the key: `LAST_REVS_AVG` on a row that turns a rotor, `LAST_ITERS_AVG` on
one that does not. A row with a deprecated `WINDOW_STEPS`, `WINDOW_REVOLUTIONS`
or `WINDOW_DEGREES` key still plans with a warning until 0.26.0; only a row with
NO window key is refused. Add the current key to the `VAR_NAMES_VALUES` cell:

```
... / DELTA_THETA: 5 / REVOLUTIONS: 2.0 / LAST_REVS_AVG: 0.5
```

`LAST_REVS_AVG: 1` is what a rotor row with no key was given before, and
`LAST_ITERS_AVG` equal to `TIME_ITERATIONS` is the whole run. Records you already
hold post without it, with the warning of section 1.

---

## 3. Headers that change

Read your files BY COLUMN NAME. Every table below gained or lost columns.

| table | what changed |
|---|---|
| every product | the condition block gains `VREF`, `RHO`, `TEMP`, `MU`: `ALPHA, BETA, MACH, RE, VINF, VREF, ALT, RHO, TEMP, MU, J, SREF, CREF, BREF` |
| unsteady polar | renamed `P<sim>_<name>_uns_avg.csv` (was `<sim>_<name>_unsteady.csv`; the old file is archived). Opens with `FIRST_STEP, LAST_STEP, STEPS`; gains `XMOM, YMOM, ZMOM`, the eighteen axis coefficients under the steady polar's names, each suffixed with its plot group's whole name (`CLW_MRP_TOTAL`, `CMW25_MRP_TOTAL`), any `[equations]` columns, and the super file's content |
| sections | `ITERATION` is `STEP`; gains `FAMILY, PLANE, ROTOR` before `AZIMUTH` |
| series | `step` is `STEP`; the condition block; `PROBE` in the probes series; the sections series leads with `STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH` |
| reductions | gain `ROTOR` and `XMOM, YMOM, ZMOM`; lose `Time-step` and `Time (sec)` |
| per-blade | ONE ROW PER BLADE: `REDUCTION, ROTOR, BLADE, FAMILY, FIRST_STEP, LAST_STEP, STEPS, AZIMUTH_START, AZIMUTH_END`, then the blade's own columns with its family removed (`CL_MRP_Blade1` becomes `CL_MRP`). It was one row of the total's average |
| rotor table | gains `RPM_<alias>` and `DIAMETER_<alias>`; `J_<alias>` is on the free stream |

The plots table `probes/<point>_plots.csv` stays exactly as the export prints it,
on purpose: every other unsteady product is read from it.

`products.json` says more: `complete` and, on a rebuild that died, `interrupted`;
`kind: instant` on a sections table; `source` and `window` on an unsteady polar and
on a rotor table; and entries ending in `#axes`, `#equations` or `#names` where a
BLOCK of a file that was written could not be. `pyfs-matrix post --strict` counts
those as skips.

---

## 4. What needs a new run

- **The unsteady rotor table**, unless your pproc already plots the rotor's six
  components over its own families in the `MRP` frame (section 1).
- **The axis coefficients of an unsteady polar**, unless your pproc already plots
  the six for a group in the `MRP` frame. A new run adds the group `MRP_TOTAL`.
- **`FAMILY`, `PLANE`, `ROTOR` and `AZIMUTH` of a sections table**, which the run
  records since 0.24.0, and the blade families a per-blade table reads when it is
  posted without its matrix.

A new run's SCRIPT differs from 0.23.0's by those added plots and by nothing else:
six `UNSTEADY_SOLVER_NEW_FORCE_PLOT` commands for `MRP_TOTAL` where the pproc plots
none in the global frame, and six per rotor the row turns.

---

## 5. New in the pproc, all optional

`[phase_locked]`, `[equations]` and `[glossary]`, which 0.23.0 refused by name,
bind now, and so does `[names]`. A pproc that declares none of them is read
exactly as before. `[products] superfile_format = "legacy_polar"` is accepted
again. Two generated guides appear in `inputs/pproc/`, `VARIABLES.md` and
`WRITING-EQUATIONS.md`; commit them or ignore them.

An `[equations]` symbol reads `<symbol>_<alias>` before the exact column. A
`[names]` entry may not give a column the name `CL`: the unsteady polar already
carries the native export's last-step `CL`.

---

## 6. Removed and deprecated

- Removed, none had a caller: `post.unsteady.converged_window`,
  `post.products.group_product_name`, `post.superfile.declared_sweep`,
  `post.superfile.SUPER_PREFIX`. `write_sections_table` no longer takes
  `step_deg=`.
- Deprecated, removed in 0.26.0: a `[groups]` entry written as a list of members.
  Write ONE alias as a string.
- `broken_commands` in a record: its removal moved from 0.24.0 to 0.26.0 in this
  release, because recorded workspaces still carry it. The 0.26 development
  cycle briefly carried a later deadline for it and for the other compatibility
  promises above; no release stated it, and 0.26.0 remains the deadline.
