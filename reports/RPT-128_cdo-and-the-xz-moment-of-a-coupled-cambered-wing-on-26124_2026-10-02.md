---
report: RPT-128
requirements: FR-338, FR-340
cdo_cause: solver
capped_one_pass: true
xz_moment_verdict: confirmed
xz_moment_ratio: 1.00825
xz_force_ratio: 0.99033
---

# RPT-128 - Why CDo reads zero in a coupled FSI run, and the XZ cut moment on a cambered wing, on FlightStream 26.124 (2026-10-02)

The licensed measurement **FR-338** and **FR-340** owe (each "Evidence owed", "the licensed
run ... reported in RPT-128"), run after the 0.34.0 release. Three points of the FSI workflow
ran on **FlightStream 26.124, build 8172026**, executable SHA-256 withheld from the public tree
per NFR-31, one solver instance at a time, hidden, far field 5 layers stated in the setup of
every point (`SOLVER_SET_FARFIELD_LAYERS 5` in each emitted script). The scripts are the ones
pyflightstream 0.34.0 emits (package tree at `d09978f1`, no file changed), through the
package route (`pyfs-matrix plan`, then `run`), with two probe additions made in the probe's own
process by the committed kit `tests/tier3_licensed/fsi_lq1.py`: a loads spreadsheet exported at
the head of the coupled points' aeroelastic post, and, on one point, the coupling capped at one
iteration. The run window: 2026-10-02T17:19:13-03:00 to 2026-10-02T17:20:53-03:00.

Only nondimensional values are stated: force and moment coefficients of the loads spreadsheet's
Total row, and ratios. The geometry is a synthetic half wing generated from a public shape law
(the NACA 4412 section, aspect ratio 4 on the half span, 25 chordwise and 20 spanwise panels),
the wing of RPT-092 with a cambered section.

## 1. The questions

FR-338, as the requirement states it: "a short licensed probe on 26.124 states why `CDo` reads
zero in the coupled FSI exports, and the package fixes it where the cause is its own ordering."
R1: "RPT-128 states the probe, the cause it separates and the evidence."

FR-340, as the requirement states it: "a short licensed run on a cambered profile confirms or
refutes the magnitude of the XZ cut moment the package reads, and the result is a committed
report." R2, fixed before the run: "The magnitude is confirmed when the moment ratio lies at least
as close to 1 as the force ratio of the same run does, and refuted otherwise."

## 2. The case and the points

| point | what it is | coupling | the probe's additions |
|---|---|---|---|
| 9341 | the rigid wing, alpha 5, the steady setup of RPT-092 | none | none: the package's script |
| 9342 | the same wing coupled (the fixed-wing route, a solid titanium wing under its loads and its weight) | up to 50 iterations, as the package emits | a loads spreadsheet at the head of the aeroelastic post |
| 9343 | 9342 with the coupling capped at ONE iteration, so its post runs once, before the only structural call | 1 | the same head export, and the cap |

Fixed before the run (the kit's docstring and its analysis): the cause is `solver` when the
capped point's head export reads `CDo` 0, `package_order` when that head export is non-zero and
the capped point's own export reads 0, and `undetermined` otherwise; the rigid point's `CDo` must
be non-zero (the control that can say "different"). That the capped post ran once is measured:
its convergence log holds one row, and the sectional loads export left on disk carries the solver
iteration that row records. The XZ verdict is judged on the rigid point (no deformation; RPT-092's
44 percent was its rigid row); the coupled point's ratios are reported and decide nothing.

The instrument's control: the same analysis over RPT-092's recorded points reproduces that
report's ratios on the symmetric section (moment 0.43689, force 0.98444).

## 3. Measurements

Each launch exited with status 0 and named build #8172026 in its logs. Every point converged:
9341 in 64 solver iterations; 9342 in 505 solver iterations over 22 coupling iterations, of the
50 allowed; 9343 in 64 solver iterations over its one coupling iteration.

| export | `CDo` |
|---|---|
| 9341, own export (rigid) | 0.0098384 |
| 9342, own export (the last pass) | 0.0 |
| 9342, head export of the last pass | 0.0 (after the updates of every earlier pass; decides nothing) |
| 9343, head export (its one pass, before any update of the post) | 0.0 |
| 9343, own export (the same pass, after the post's updates) | 0.0 |

The capped point's post ran once: its convergence log holds 1 row, which records solver
iteration 64, and the sectional loads export left on disk states "Current solver iteration
number: 64", as do its head export and its own loads spreadsheet.

**How the one-pass reading was read twice.** The kit's first analysis of this run printed
`capped point ran its post once: False` and so `cdo_cause: undetermined`. The cause was the
kit's check, not the run: it looked for exactly one file named `FS_SurfaceSection_Loads.txt`
anywhere under the point's folder, and the package keeps a copy of each structural call's input
under the point's `fsi_archive/call_0001/` folder. That copy is a different file (it names the
simulation `Default.fsm` and its sectional rows differ from the point's own export), not a second
pass of the post, but it made the count two, so the check could never pass on a point that keeps
its archive. The kit now counts the point's own files and leaves out the `fsi_archive/` folder by
name, nothing else; a tier-1 test
(`tests/tier1_offline/test_fsi_lq1_one_pass.py`) holds a synthetic point with one own export and
one archive copy, which the check accepts, and the same point with a second own export, which it
still refuses; the test fails on the kit as it was. The same analysis was then run again over the
same recorded files, with no new solve, and printed the one-pass line above and `cdo_cause:
solver`. Nothing else in its output changed.

| point | summed cut moments over the solver's moment | summed cut forces over the solver's lift | verdict by R2 |
|---|---|---|---|
| 9341 rigid (judged) | 1.00825 | 0.99033 | confirmed |
| 9342 coupled (reported) | 1.00791 | 0.99045 | confirmed |

## 4. Verdict

- FR-338: the zero is the solver's. In the coupled solve, the loads spreadsheet the solver
  exports at the head of the post's one pass, before the post updates the sections, the loads
  or the probe points and before any structural call, already reads `CDo` 0, where the rigid
  solve of the same wing reads 0.0098384. The package's order of operations does not produce
  it. `cdo_cause: solver`.
- FR-340: the magnitude of the XZ cut moment is confirmed on the cambered wing: the summed cut
  moments are 1.00825 of the solver's moment about the same line, at least as close to 1 as the
  summed cut forces to the lift (0.99033). `xz_moment_verdict: confirmed`.

What follows: the FSI page states that `CDo` reads zero in a coupled run, and why, citing this
report (FR-338 R3), and the definitions page states the same measured zero and that `CD0` reads
it, citing this report (R4);
nothing emitted changes. The XZ reading stays, and the FSI page's XZ reading cites this report
(FR-340 R3). The tier-1 tests `tests/tier1_offline/test_p0340_fsi_rpt128.py` read this front
matter and the five recorded loads exports above, each with its control.

## 5. What this does not show

- One section (a 4 percent camber), one angle of attack, one material, one build; the rotor
  routes of FSI are not concerned.
- Why the solver prints `CDo` 0 in a coupled solve is not measured: this run separates the
  solver from the package's order, not the solver's own reason.
- The XZ ratios read the cuts the package takes in its own frame on the quarter chord; another
  moment point or another cut count is not measured.
