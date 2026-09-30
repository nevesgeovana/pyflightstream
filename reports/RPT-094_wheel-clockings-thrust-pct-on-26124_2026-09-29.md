# RPT-094 - The 0.31 G1 wheel: sections at every clocking, the XY cut read, THRUST_PCT and the rotor table as the mean, on 26.124 (2026-09-29)

A short licensed confirmation of the 0.31 wheel (item **G1**) of the
`qsteady_rotor` workflow: a whole wheel at an angle of attack, three
clockings, no FSI, run through the package's own path (`pyfs-matrix plan`,
`pyfs-matrix run`, the post that `run` performs) on **FlightStream 26.124,
build 8172026**, executable SHA-256
withheld from the public tree per NFR-31
(`fs_exe_sha256` in `runs.json`, measured from the executable that ran). One
solver instance, hidden, far field 5 layers.

Only nondimensional values of the propeller and its run are stated here:
Mach and Reynolds numbers, the advance ratio, r/R, coefficients, ratios,
fractions, counts and times. The run's rotor speed, free-stream speed and
density, and every force and moment in newtons, are not published; the run
id's last token, which states the rotor speed, is written `RPM<n>`.

Two trees appear here and are kept apart:

- **The run and its first post**: the package tree of `feat/0-31` at
  `8d0c8827` (`package_commit` in `runs.json`, `package_dirty: false`).
- **The re-post that gives THRUST_PCT and TORQUE_PCT**: the tree of this
  branch at `f64d888c`, which reads an XY cut for the thrust and torque shares
  (the commit whose message records the measurement of section 3). The re-post
  ran the post only, on a plain file copy of the workspace; no solver ran. On
  `8d0c8827` the two shares were `null` in the point's validity file, because
  that tree did not read an XY cut.

## 1. What was run

A six-blade research propeller (its geometry is not published): six blades,
one OBJ group each, no spinner, no nacelle, no symmetry, trailing edges from
the mesh's points file, shaft along X through the origin. POL 9311, workflow
`qsteady_rotor`, case WHEEL, `PASSAGE_POSITIONS: 3`, Mach 0.1441, Re 4.38
million on the reference chord, **AoA 5 deg**, beta 0, advance ratio J
1.70001 (the rotor table's `J_ROTOR`), steady solver, sections at 30 stations
over blade one.

| run id | status | iterations per clocking | final residual | wall time |
|---|---|---|---|---|
| `pfs0310-l1-ws/sim_9311/M144RE438AL+050BE+000RPM<n>` | **CONVERGED** | 61 | 1.4377e-06 | 9.1 s |

The record read the solver log (`log_file_used`
`P9311-M144RE438AL+050BE+000RPM<n>_log.txt`) and carries one verdict per
clocking (`clocking_verdicts` in `runs.json`):

| clocking index | blade one azimuth (deg) | status | iterations | residual |
|---|---|---|---|---|
| 1 (solved first) | 20 | CONVERGED | 61 | 1.3420e-06 |
| 2 (solved second) | 40 | CONVERGED | 61 | 1.4377e-06 |
| 0 (solved last, back at the datum) | 0 | CONVERGED | 61 | 1.2296e-06 |

**The delete and re-create cycle ran.** The emitted script
(`sims/sim_9311/scripts/P9311-...txt`) rotates the six blades 20 deg about X,
re-initialises the solver, creates the section distribution over blade one
(`NEW_SURFACE_SECTION_DISTRIBUTION`, `PLANE XY`, `NUM_SECTIONS 30`, in the
frame of the rotated pose, `FRAME 4`) and solves and exports clocking 20 deg;
then `DELETE_ALL_SURFACE_SECTIONS`, a further 20 deg rotation, a new
distribution (`FRAME 5`) and the solve and exports of clocking 40 deg; then
`DELETE_ALL_SURFACE_SECTIONS` again, a rotation back by 40 deg, a new
distribution (`FRAME 3`) and the solve and exports of clocking 0, the point's
own exports. So the command ran twice and the distribution was created three
times. `DELETE_ALL_SURFACE_SECTIONS` is documented in the command database and
had not been run before. That it took effect is read from the exports: the
sectional-loads export of each clocking (`_qs01_sloads.txt`,
`_qs02_sloads.txt`, `_sloads.txt`) has the same length, 67 lines, and the
sections table holds 30 stations per clocking, not 60 or 90 accumulating; and
all three solves converged (above). The solver's own log carries no line for
the command, so the evidence is the exports, not a log message.

## 2. The sections table

`post/l1_g1/sections/P9311-M144RE438AL+050BE+000RPM<n>_sections.csv` holds
**90 rows: clockings 0, 1 and 2, at azimuths 0, 20 and 40 deg, 30 stations at
every clocking**, one family (`Blade1`), plane XY, step 61. The stations are
**the same at every clocking** (the 30 `Offset` values of clocking 0 equal
those of clockings 1 and 2 exactly; the spacing between neighbouring stations
is uniform to 3 %). With R the rotor radius, the **first cut is at r/R
0.2371 and the last at r/R 0.9843**. The blade itself runs from r/R 0.224 to
0.997 (the extent RPT-091 measured on the same mesh, divided by R), so both
end cuts are inside the blade span and no cut is empty.

## 3. The XY cut, measured

The distribution is an XY cut in the rotor's hub frame, whose x axis is the
shaft. What an XY cut's `Fx` and `Fz` columns mean was the open question the
0.31 thrust-axis item carried; this run answers it (recorded in the message of
`f64d888c`, recomputed here from the files). The strip integral of a column
over blade one's stations (trapezoid rule over the `Offset` values of the
sections table, per clocking) is compared with the blade's own load in the
run's loads exports (`post/l1_g1/polars/P9311-ROTOR_qs_positions.csv`,
columns `FX_Blade1`, `FY_Blade1`, `FZ_Blade1`, `MX_Blade1`), which the solver
integrates over the whole blade in the loads frame. Each ratio is the strip
integral divided by the blade's own load:

| clocking | integral of Fx / blade force along the shaft | integral of Fz / blade in-plane force, the magnitude of (FY, FZ) | integral of Fz x Offset / blade moment about the shaft |
|---|---|---|---|
| 0 | 0.9807 | 0.9851 | -0.9821 |
| 1 | 0.9803 | 0.9846 | -0.9820 |
| 2 | 0.9799 | 0.9842 | -0.9819 |

So an XY cut states **`Fx` along the frame's x (the shaft) and `Fz` along its
y, the station at `Offset` along z**: the three strip integrals match the
blade's force along the shaft, its in-plane force and its moment about the
shaft to **about 2 per cent** (0.980 to 0.985), at every clocking; the moment
has the opposite sign, as `r x F` gives. The 1.5 to 2 per cent that the
strips do not hold may be the ends of the blade outside the first and last
cut (the cuts stop at r/R 0.2371 and 0.9843 and the trapezoid rule adds
nothing outside them); this run does not separate it from the other
candidates (the strip rule, the cut's own discretisation). At clocking 0
the blade's in-plane force is almost wholly along y (`FZ_Blade1` is 0.024 of
the in-plane magnitude); at 20 and 40 deg it turns with the blade (`FZ_Blade1`
0.365 and 0.662 of it), and the `Fz` column of the rotated cut follows it,
which is why the comparison uses the magnitude of the in-plane force.

## 4. THRUST_PCT and TORQUE_PCT (from the re-post on `f64d888c`)

The re-post (`pyflightstream.run.cli post l1_g1.fs --workspace .`, with
`PYTHONPATH` at this branch's `src/`) wrote 11 products, complete, no skip
(`post/l1_g1/products.json`, `"skipped": {}`), and the point's validity file
(`P9311-..._qsteady_validity.json` in the datapoint folder) now reads:

| value | from the sections (re-post, f64d888c) | run's own post (8d0c8827) | from the mesh (plan) |
|---|---|---|---|
| K_1P_MIN | 0.0345 | 0.0345 | 0.0421 |
| K_1P_MAX | 0.1306 | 0.1306 | 0.1315 |
| K_1P_MEAN | 0.0895 | 0.0895 | 0.0898 |
| SPAN_PCT_K_GT_0_05 | 91.40 % | 91.40 % | 97.37 % |
| SPAN_PCT_K_GT_0_1 | 32.77 % | 32.77 % | 28.95 % |
| **THRUST_PCT_K_GT_0_1** | **11.73 %** | null (XY not read) | not computed at plan |
| **TORQUE_PCT_K_GT_0_1** | **10.26 %** | null (XY not read) | not computed at plan |

The thrust and torque shares are the part of the blade's thrust and torque
carried by the stations where the 1P reduced frequency exceeds 0.1, read from
the XY cut's `Fx` (along the shaft) and `Fz x Offset` (about it) as section 3
measured. The values are in the point's `_qs_avg.csv` and `_qs_positions.csv`
rows (`THRUST_PCT_K_GT_0_1` 11.73155, `TORQUE_PCT_K_GT_0_1` 10.25995) and in
the sections table's columns of the same names.

## 5. The rotor table as the mean of the three clockings

`post/l1_g1/polars/P9311-ROTOR_rotor.csv` is written, and `products.json`
gives its source as **"mean of 3 clockings"** (`"clockings": 3`). The row:

| J_ROTOR | CT_ROTOR | CQ_ROTOR | CP_ROTOR | ETA_ROTOR | ETAW_ROTOR | CN_ROTOR | CS_ROTOR | CMN_ROTOR | CMS_ROTOR |
|---|---|---|---|---|---|---|---|---|---|
| 1.70001 | -0.32683 | -0.09897 | -0.62187 | 0.89345 | 0.88089 | 0.03846 | -0.00397 | -0.01425 | 0.00182 |

(CT and CQ negative by the shaft sense of the loads frame; ETAW the wind-axis
efficiency, which at 5 deg differs from ETA; CN, CS, CMN and CMS the rotor's
in-plane coefficients, new in 0.31; the row's `RPM_ROTOR` is not reported
here.) The mean is the mean: the three clockings' `FX_ROTOR` in
`_qs_positions.csv` are 1.00173, 0.99984 and 0.99843 of the `FX_ROTOR` of
`_qs_avg.csv`, and their mean is that value to the printed digit (a ratio of
1.00000); likewise `MX_ROTOR` and `FZ_ROTOR`.
The two-clocking row of RPT-091 (same point, clockings 0 and 30 deg) read CT
-0.32740; the three-clocking row reads -0.32683, 0.2 % from it.

The `_qs_avg.csv` row also carries the wheel's rotor state (`CT_PROPELLER`
-0.32683, `MU_ROTOR` 0.04716, `LAMBDA_C` -0.53907, `LAMBDA_I` -0.03650,
`CHI_DEG` 175.316), the same in the validity file's `rotor_state`.

## 6. The harmonic product

`post/l1_g1/sections/P9311-M144RE438AL+050BE+000RPM<n>_harmonics.csv` is
written and registered in `products.json` (`kind` `harmonics`, `source` "wheel
clockings", `samples` 3, `clockings` 3): 90 rows, three quantities (`Fx`,
`Fz`, `Moment`) at each of the 30 stations. Every row has `SAMPLES` 3 and
`DISTINCT_AZIMUTHS` 3 (blade one at 0, 20 and 40 deg). With three distinct
azimuths per station the once-per-revolution fit (needs 3) is written: `H0`,
`H1_AMP` and `H1_PHASE_DEG` are numbers in all 90 rows, with a residual of
0 (three samples, three unknowns; the fit is exact and says nothing about its
own error). The twice-per-revolution fit needs 5, so **`H2_AMP` and
`H2_PHASE_DEG` are `NA` in all 90 rows, as designed**. The first station
(`Fx`, r/R 0.2371) reads `H1_AMP` 0.4775 of the magnitude of its `H0`
(which is negative) and `H1_PHASE_DEG` 319.44.

## 7. What this does not establish

- Three clockings at 0, 20 and 40 deg cover one 60 deg blade passage, not a
  revolution; the 1P harmonic is an exact fit of three samples and the 2P is
  not reported. RPT-089's "What the package takes from this" section gives
  the guidance of 6 or more clockings for the in-plane loads, from its
  section 4 convergence study.
- The 2 per cent between the strip integrals and the blade loads is not
  attributed to a cause by any run.
- One point, one angle of attack; no comparison with an unsteady rotor is
  made here (RPT-089's).
- The run used `8d0c8827`; the two shares come from the post of `f64d888c`
  on the same run files. A run on `f64d888c` itself was not made, and the
  solver-facing script does not differ between the two trees (`f64d888c`
  changes the post only).

Numbers and their files are in the sidecar
`RPT-094_wheel-clockings-thrust-pct-on-26124_2026-09-29.json`.
