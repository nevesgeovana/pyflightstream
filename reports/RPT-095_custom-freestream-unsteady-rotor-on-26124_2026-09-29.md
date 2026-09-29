# RPT-095 - The 0.31 G6: a custom free stream on unsteady_rotor, confirmed on 26.124 (2026-09-29)

A short licensed confirmation of the 0.31 item **G6**: an `unsteady_rotor`
row that states `FREESTREAM` (a custom free-stream field) builds, runs and
is read by the solver, through the package's own path (`pyfs-matrix plan`,
`pyfs-matrix run`, the post that `run` performs) on **FlightStream 26.124,
build 8172026**, executable SHA-256
`68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65`
(`fs_exe_sha256` in `runs.json`). The package is the tree of `feat/0-31` at
`8d0c8827` (`package_commit`, `package_dirty: false`). One solver instance at
a time, hidden, far field 5 layers. The run records and the post are those of
the session's workspace of 2026-09-29; a second post of the same files on this
branch (`f64d888c`, no solver) listed the same 22 products and the same six
skips.

Only nondimensional values of the propeller and its run are stated here:
Mach and Reynolds numbers, the advance ratio, coefficients, ratios, counts
and times. The run's rotor speed, free-stream speed and density, its time
step, and every force and moment in newtons, are not published.

## 1. What was run

A six-blade research propeller (its geometry is not published), shaft along X,
Mach 0.1441, Re 4.38 million, alpha 0, beta 0, advance ratio 1.70001.
Workflow `unsteady_rotor`, `DELTA_THETA` 10 deg per step, `REVOLUTIONS` 1,
`LAST_REVS_AVG` 0.5, `CLOCK_MOTION` ROTOR. The script sets 36 time
iterations (one revolution) and 500 solver iterations per step at most.

| POL | row | field | status | iterations | final residual | wall time |
|---|---|---|---|---|---|---|
| 9321 | `FREESTREAM: fs_l1uniform` | `SET_FREESTREAM CUSTOM STRUCTURED` | **CONVERGED** | 1048 | 2.152e-07 | 51.0 s |
| 9322 | none (the control) | `SET_FREESTREAM CONSTANT` | **CONVERGED** | 1048 | 2.170e-07 | 49.2 s |

The two scripts differ in nothing but the file paths and run names and the
free-stream lines (`diff` of `sims/sim_9321/scripts` and `sim_9322/scripts`:
`SET_FREESTREAM CUSTOM STRUCTURED` and the file's path against
`SET_FREESTREAM CONSTANT`). Both points ran on the same executable, the same
row otherwise, and both converged in about 50 s, 1048 iterations each.

**The field of 9321** (`inputs/freestreams/fs_l1uniform.txt`) is a uniform
STRUCTURED field of **13 x 13 points** (the header line `13 13` and 169 point
lines): every point states the velocity (V, 0, 0), V the row's free-stream
speed, along the shaft, on one plane. It is uniform on purpose: the control 9322
states the same speed as a constant, so a solver that reads the field must give
the control's result.

## 2. The field is read on unsteady_rotor

The solver's own log of 9321 states it: "Freestream velocity custom profile
imported from this location:" followed by the field's path (line 23 of
`P9321-M144RE438AL+000BE+000_log.txt`); the log of 9322 has no such line.

The rotor table rows (`post/l1_g6/polars/P9321-ROTOR_rotor.csv` and
`P9322-ROTOR_rotor.csv`), each the time average over the last half revolution
(steps 19 to 36, 18 steps):

| POL | CT_ROTOR | CQ_ROTOR | CP_ROTOR | ETA_ROTOR | CN_ROTOR | CS_ROTOR |
|---|---|---|---|---|---|---|
| 9321 (field) | -0.28985 | -0.09016 | -0.56646 | 0.86988 | -0.00002 | -0.00001 |
| 9322 (control) | -0.28984 | -0.09015 | -0.56645 | 0.86987 | -0.00002 | -0.00002 |

The rows **agree to the last printed digit**: CT, CQ, CP and ETA of the field
run are one unit of the fifth decimal above the control's in magnitude (about
3e-5 relative, and the same in every one of the four, a sign of one common
cause rather than four). They are not equal to every printed digit, and this
report does not say they are. The averaged loads say the same
(`P9321_M144RE438AL+000BE+000_uns_avg.csv` and its 9322 twin): the field
run's `FX_ROTOR_ROTOR` is 1.0000299 of the control's (3.0e-5 relative), and
its `MX_ROTOR_ROTOR` 1.0000239 of it (2.4e-5). Both
runs' rotor table also states MTIP 0.26630, MHEL 0.30278 and J 1.70001. So a
custom free stream that equals the constant is read on `unsteady_rotor`: the
row builds (the 26.124 script accepted the command inside an unsteady
script), the solver states that it imported the file, and the result is the
control's to the fifth decimal.

## 3. The skips both points share

Each point has 11 products in `post/l1_g6/products.json` (22 in all: the
datapoint's Tecplot and VTK, the three sections tables, the plots,
time-average, phase-locked and per-revolution probe tables, the rotor table
and the unsteady average), and skipped the same three products each. Every
skip is named in `products.json` and in `post.log` with its reason:

| product (per point) | why it is skipped |
|---|---|
| `probes/<point>_phase_locked.csv` | the case names its rotors, so each reduces over its own blade passage and there is no single passage of the row; the per-rotor file `_phase_locked_ROTOR.csv` is written |
| `probes/<point>_per_blade.csv` | the same reason; the per-rotor `_per_blade_ROTOR.csv` is the one that would stand for it |
| `probes/<point>_per_blade_ROTOR.csv` | the plots table holds no column of a blade family of the rotor (blades one to six), so there is no blade to give a row to; a blade's plots are the ones named for its family, declared with a plot group whose `families` is `each` or whose frame is `LOCAL_AXIS`, and that takes a new run |

The three are the same for the control, so they are the row's shape (a named
rotor, the plots the pproc artifact declares), not something the free stream
changes. One product this row could have written is absent without a skip:
the per-station harmonic product (`sections/<point>_harmonics.csv`). The
harmonics of an `unsteady_rotor` point are fitted over the last complete
revolution of the sections series, and no sections series was written for
these points (no `series/` folder in the post; their `sections` tables hold
the one final step, 36). The post's code writes nothing for a point without a
series and states no skip for it. The unsteady harmonics are therefore **not confirmed by
this run**.

## 4. What this does not establish

- One uniform field; a field that varies in space is not exercised. That
  the solver reads the field's values, and not only the file, is not shown
  by this run: a field equal to the constant gives the control's result
  whether its values are read or not. A field with a gradient would separate
  the two.
- The 3e-5 relative difference between the field run and the control was not
  attributed (iteration-level noise of the unsteady solve is one candidate;
  this run did not test it).
- One revolution at 10 deg steps, the last half averaged: the row's cheapest
  form, not a converged unsteady study (RPT-089 has the time-step study).
- The unsteady harmonic product (section 3).

Numbers and their files are in the sidecar
`RPT-095_custom-freestream-unsteady-rotor-on-26124_2026-09-29.json`.
