# RPT-141 - Several unsteady points, and several polars, in one FlightStream 26.124 instance (2026-10-02)

The licensed evidence behind the batched-run requirements of the 0.35.0 scope: **FR-352,
FR-353, FR-354, FR-359, FR-360, FR-361 and FR-378**, and the 611 s note of **FR-358**. Three
licensed tests ran on **FlightStream 26.124, build 8172026**, executable SHA-256 withheld
from the public tree per NFR-31, driven by pyflightstream 0.34.0 (the package wrote the
fresh-instance scripts and records; the multi-point scripts are those scripts cut and joined,
because the 0.34.0 emitter writes one point per script). One solver instance at a time,
hidden, never beside a test suite, far field 5 layers stated in the setup of every point.
Every run ended with exit status 0 except the one deliberate hang of section 5, which the
harness stopped. The tests ran on 2026-10-02.

Only nondimensional values are stated, plus counts, iteration numbers, megabytes and seconds.
The geometries are the two synthetic tier-3 geometries, `30_BLADE.fsm` (a periodic blade, six
copies, 293 solver faces) and `40_PUSHER.fsm` (a body with a base and a two-blade pusher
rotor, 1138 solver faces). The point numbers (POL 9811, 9812, 9821, 9841) belong to
synthetic cases.

## 1. The questions

The cluster profile starts one FlightStream instance per job and the queue is the scarce
resource, so one job should hold its CPUs and run many points in that one instance. That is
safe only if what one point leaves behind does not reach the next. Three questions:

- **Test 1.** After an unsteady point, does `REMOVE_INITIALIZATION` followed by
  `INITIALIZE_SOLVER` give a second unsteady point equal to the same point in a fresh
  instance, also when the second point changes the advance ratio J (new rotor speed, new
  time step)?
- **Test 2.** After a polar, does `NEW_SIMULATION`, then `OPEN`, then a polar with other
  flags give the same results as that polar in a fresh instance? What survives?
- **Test 3.** The same refresh, but the `OPEN` reads a different mesh (`30_BLADE.fsm` then
  `40_PUSHER.fsm`). Does anything of the first geometry reach the second result?

Two side questions are answered on the way: where a save and an export land, and what a
save into a folder that does not exist does.

## 2. The cases

| test | polar 1 | polar 2 |
|---|---|---|
| 1 | `30_BLADE`, unsteady_rotor, J 1.7, alpha 0, 10 degrees a step, 1.25 revolutions = 45 steps (POL 9811) | the same, alpha 2 (POL 9812); and a variant at J 1.9 after J 1.5 |
| 2 | point 9811 above | another setup (incompressible instead of Prandtl-Glauert, wake-on-wake off, additional wake relaxation on, convergence 1e-4 in 200 iterations, 4 threads instead of 8), another post-processing set (16 plot columns instead of 23), another sweep variable: advance ratio 1.5 then 1.9, 36 steps each (POL 9821); seven settings that polar 1 states are left unstated in polar 2, so they can reach it only by surviving the reset |
| 3 | `30_BLADE`, point 9811 | `40_PUSHER`, unsteady_rotor, Mach 0.1, 15 degrees a step, 1 revolution = 24 steps, alpha 0 then 4 (POL 9841), 37 plot columns |

The 1.25-revolution length of Test 1 is deliberate: point 1 ends with the wheel 30 degrees
off its periodic position, so a blade azimuth carried into point 2 would show as a phase
shift. The two geometries of Test 3 differ in boundary count (1 against 3), symmetry
(periodic with six copies against none), coordinate frames, motion boundary, post-processing
set and reference, so every state that could leak differs between the two.

## 3. The arms

Every multi-point script is built from the text of the scripts pyflightstream 0.34.0 wrote
for the fresh runs; the only edits are export names, the geometry path, and the dropped
re-registration of the unsteady actions where the arm says so.

| arm | what it is |
|---|---|
| fresh | the package's own runs, `pyfs-matrix plan` then `pyfs-matrix run --local`, one instance per point; the comparator for every other arm |
| A (Test 1) | point 1 whole, then `REMOVE_INITIALIZATION`, then point 2 restated from `SET_SOLVER_UNSTEADY` on (clock, flight condition, every solver setting, `INITIALIZE_SOLVER`, `START_SOLVER`, exports). The open, the frames, the force plots, the fluid properties, the motion and the actions are not repeated |
| B2 (Test 1) | point 2 exactly as the package wrote it, launched directly: the control that the package launch and a direct launch agree |
| D (Test 1b, 2) | polar 2 alone in a fresh instance (J 1.5, `REMOVE_INITIALIZATION`, J 1.9 restated from `SET_MOTION_ROTOR_RPM` on) |
| C (Test 2) | one instance: polar 1, `NEW_SIMULATION`, `OPEN`, then exactly arm D's polar 2 |
| AF (folders) | arm A as a batch: point 1 saved and exported to a folder by relative paths, point 2 to another by absolute paths, a bare-name export after each save, and a final deliberate save into a folder that does not exist |
| reopen | `OPEN` of each saved `.fsm` and its exports, then `NEW_SIMULATION` and `OPEN` of the other; no solve |
| F (Test 3) | control, one fresh instance: polar 2 on `40_PUSHER` alone (point 1 registers the three actions, `REMOVE_INITIALIZATION`, point 2) |
| E (Test 3) | one instance: polar 1 on `30_BLADE` (the one registration of the instance), `NEW_SIMULATION`, `OPEN` of `40_PUSHER`, then exactly F's polar 2 with its action registrations removed. A text difference of E's polar 2 against F's shows only those removed lines |
| G (Test 3) | a saved `.fsm` that carries actions: one instance with no action registered, `OPEN` of a copy of F's saved file, solve, `NEW_SIMULATION`, `OPEN` the same file, solve |

Commands, in role form (one solver at a time; the working directory of the solver process is
the arm's folder):

```
pyfs-matrix plan <matrix> --workspace <ws>          # one plan per matrix
pyfs-matrix run <matrix> --workspace <ws> --local   # the fresh runs, one instance per point
<solver executable> -hidden -script <arm script>    # each arm, in the arm's own folder
<comparison script> reinit | reset | folders | meshchange   # writes the comparison files
```

The launcher measured free memory before each launch, refused to start while a solver or a
test run was alive, sampled free memory and the solver's working set every 0.5 s, killed
only the instance it started if free memory fell under 0.5 GB or a timeout passed, and
recorded the outcome. Free memory before the launches ranged from 3.26 to 4.29 GB, its lowest
sample while running was 2.87 GB, and the peak working set was 173 MB in Tests 1 and 2 and
194 to 198 MB in Test 3.

## 4. The comparison, and its controls

Per point the comparison reads three things: CL, CDi and CM of the last iteration of every
step as printed (eight significant digits) with the iteration count of every step and the
global iteration number at the last step; every cell of the plots export; and the saved
simulation, block by block. A cell is compared as text, so "identical" means the same
printed digits.

Each verdict was given its controls, and each control can say "different":

- **Fresh against fresh.** The package's launch against a direct launch of the same script
  (B2): identical at every step. The package's fresh runs against the direct fresh runs of
  Tests 2 and 3 (D, F): identical.
- **Two different points.** Alpha 0 against alpha 2: first difference at step 1, 990 of 1035
  plot cells differ. Test 2, J 1.5 against J 1.9: first difference at step 1. Test 3, alpha 0
  against alpha 4 on the pusher: first difference at step 1, 792 of 888 cells differ; the
  pusher against the blade: first difference at step 1, iteration 735 against 567.
- **The log columns that read as asterisks.** With the default five significant digits CL and
  CM print as a row of asterisks in both arms of Test 2, so that comparison of log columns
  compares asterisks. The plots export (forces and moments in newtons) and CDi carry the
  verdict there.

## 5. Measurements

### Test 1: `REMOVE_INITIALIZATION` then `INITIALIZE_SOLVER` (FR-352)

| comparison | result |
|---|---|
| control: package fresh point 2 against direct fresh point 2 | identical at every step, iteration 1085 against 1085 |
| arm A point 1 against fresh point 1 | identical at every step, iteration 826 against 826 |
| **arm A point 2 (after the removal) against fresh point 2** | **45 steps against 45, every CL, CDi, CM string identical, worst relative difference 0, same iteration count per step, iteration 1085 against 1085, plots 0 of 1035 cells differ** |
| discrimination: arm A point 1 against fresh point 2 | differs from step 1, 990 of 1035 cells |
| J change: arm D point 2 (J 1.9 after J 1.5, removal, restated from the rotor speed on) against the package's fresh J 1.9 | identical at every step |

At the switch the log prints "Solution cleared. Initialization removed.", rebuilds the wake
grid (7 deep, 5888 cells) as a fresh start does, restarts the step counter at "(1/45)" and the
solver iteration numbering at 1, and reports "Solver initialized" in .08 seconds, the time a
fresh start reports.

**Reset by the re-initialization:** the wake, the solution, the step counter and the
iteration numbering, the plot histories (45 rows, not 90), and the blade azimuth.
**Kept:** the loaded geometry (no open between the points), the coordinate frames and the
force-plot definitions (the same 23 columns, not created again), the motion, every setting
not restated (a significant-digits setting stated only in point 1 still prints eight digits
in point 2), and the unsteady-solver actions. The action counter reads 90 = 45 + 45 and the
log shows two runtime commands a step in both points.

**Not measured:** the removal with the motion, the boundaries or the geometry changed between
points; a steady point after an unsteady one; a body case in this test; a cluster build.

### Test 2: `NEW_SIMULATION`, then `OPEN`, then a polar with other flags (FR-353, FR-354)

| comparison | result |
|---|---|
| arm C polar 1 against fresh point 1 | identical at every step |
| **arm C polar 2, J 1.5, against arm D (fresh instance)** | **identical at every step, iteration 1242 against 1242** |
| **arm C polar 2, J 1.9, against arm D** | **identical at every step, iteration 1221 against 1221** |
| plots, both points, arm C against arm D | 0 of 576 cells differ, and against the package's fresh runs 0 of 576 each |
| discrimination: arm C J 1.5 against the package's fresh J 1.9 | first difference at step 1 |

`NEW_SIMULATION` prints "Solution cleared. Initialization removed." and nothing more, and
the next `OPEN` prints the saved-in and opened-in build line and the geometry. It
**removed** polar 1's force plots (polar 2 exports 16 columns, as in the fresh instance, not
16 plus 23), polar 1's significant-digits setting (polar 2 prints at the default in both
arms), and every other numeric state: the seven settings polar 2 leaves unstated took their
defaults and the results match the fresh instance.

It **did not remove the unsteady-solver actions.** Polar 2's script registered its three
actions again and from then on each fired twice a step: four "Executed runtime command"
lines a step against two in arm D, and the counter reads 189 = 45 + 2 x (36 + 36), where arm D
reads 72. No result changed, but polar 2 took .33 to .34 minutes against .20 in arm D (about
70 per cent more wall time on this case) and the package's step counter counts double. This
is the measurement behind FR-354: register the actions once per instance.

**The geometry.** The geometry stays loaded across `REMOVE_INITIALIZATION` and is dropped by
`NEW_SIMULATION`, so the next polar must `OPEN` again.

### Test 3: a batch that changes mesh (FR-353, FR-378)

| comparison | result |
|---|---|
| arm E polar 1 on the blade against the package's fresh run | identical at every step, iteration 826 against 826 |
| **arm E polar 2 point 1 on the pusher (after `NEW_SIMULATION` and `OPEN` of the pusher) against arm F point 1** | **every printed string identical, iteration count per step identical, iteration 735 against 735** |
| **arm E polar 2 point 2 against arm F point 2** | **identical at every step, iteration 733 against 733** |
| plots, E against F, both points | 0 of 888 cells differ, and against the package's fresh runs 0 of 888 each |
| controls: F against the package's fresh runs, both points | identical at every step |
| the geometry echo (boundary names, vertex, face and wake-strand counts, trailing edges, Trefftz plane), the actions fired per step, the size of each saved `.fsm` | identical to the byte count |

**Gone after the refresh** (read in the log echo and in the saved files): the first mesh and
its boundaries (the echo shows the pusher's three boundaries, 1054 vertices, 1138 faces, and
none of the blade's one boundary, 262 vertices, periodic symmetry); the first geometry's
frames, motion and force plots (the saved file names only the pusher's four frames and 36
force plots, and none of the blade's 22); the wake and the solution (a fresh 3340-cell wake,
the counter restarts at "(1/24)"). Had the blade's motion survived, the pusher's motion would
have been numbered 2 and the loads would have changed; they are bit-identical.

**Kept after the refresh, none of which changes a load:**

1. *The unsteady actions* (wanted). Registered once, in polar 1, they ran once a step on
   both geometries: two runtime commands a step in every run, the counter reads 93 = 45 +
   24 + 24 against 48 in the fresh control. Nothing doubled, and the pusher points took .14
   minutes against .15 in the control. The counter and the wall clock run across the whole
   instance (the clock file reads 93 steps and 31.3 s from the blade's first step), so each
   point's own step and clock start still need a reset at the start of a point.
2. *A graphics value in the saved file.* Line 31 of the GRAPHICS block reads `125,35` in the
   first simulation an instance saves and `200,50` in every later save, across every arm of
   the three tests. It is a display setting.
3. *Stale bytes in one unused wake slot.* The WAKE block holds 25 values per strand for a
   24-step run, and every WAKE difference sits in value 25, the slot after the last step: 57
   differing numbers in E2 against F2, 49 in F2 against the package's fresh run, 49 in G2
   against G1. In a first point the slot holds zero or a denormal, in a later one another
   run's leftovers. The fresh-against-fresh pairs show the same class, so it is not a carry
   over from the first geometry.

Run-to-run rounding of unprinted digits (10 to 34 numbers at about 1e-14 relative in the
SOLVER block) and one denormal in the WRAPPER block appear in the fresh-against-fresh control
too. **A saved `.fsm` is not byte-reproducible**, fresh against fresh included; a check on
saved simulations compares blocks and values, never hashes (FR-378).

The solver's reported memory after a refresh is a little higher than in a fresh instance:
193.8 MB against 185.8 MB for point 1 (+8.0) and 202.4 MB against 198.1 MB for point 2 (+4.2).
Two polars do not measure growth over many.

**Arm G, a `.fsm` that carries saved actions.** A saved simulation stores the instance's
actions in its SOLVER block (a count line, then each action's name and command). The pristine
tier-3 geometries carry none. In arm G, which registered nothing, `OPEN` of the saved file
fired the counter and the clock at every step (24 counts, two commands a step), so **`OPEN`
loads the saved actions**; a second `OPEN` of the same file after `NEW_SIMULATION` ran them
as three, not six. Whether `OPEN` replaces the list or merges it by name cannot be told from
runs whose names and commands were identical. A solved `.fsm` is also not the pristine
geometry: arm G's first run matches F's point 1 in iteration count at every step and in the
final iteration (735), but its values differ from step 5 on (worst relative difference 5.7e-2
on a CL of order 1e-5), because the file also brought its 36 force plots, its loads frame
and its base regions. These two findings are the measurement behind FR-378: a batch opens
the pristine input geometry, and the plan refuses a file whose action count line is not zero.

### Where a save and an export land, and the missing folder (FR-359, FR-360, FR-361, FR-358)

- **Per-point folders hold their own files.** With per-point names and per-point folders
  every point's files sat beside the others and nothing was overwritten (all nine export
  files of each point present in its own folder). Against the fresh runs, each point is
  identical at every step with 0 of 1035 plot cells different. A repeated name was not
  tested.
- **A saved point reopens as itself.** Reopening the first point's file with no solve
  exports angle of attack 0 and solver iteration 826 and the full 45-step history, equal to
  the export written at the end of the point; the second reports angle of attack 2 and
  iteration 1085.
- **Relative and absolute paths both work, and a relative path resolves against the solver
  process's working directory.** It does not resolve against the folder of the last save (a
  bare-name export after a save into a folder landed in the working directory, not in that
  folder), nor against the folder of the geometry that `OPEN` read, nor after
  `NEW_SIMULATION`. A save does not move the export base. The process working directory
  stayed fixed for the whole job in every arm, and must (FR-359: absolute paths).
- **The target folder must exist before the save.** A save into a folder that did not exist
  raised a modal dialog, "error saving simulation to file", under `-hidden`, after every
  export of both points had been written. The dialog blocked the hidden instance with no
  exit; the harness stopped it at **611 s**, exit -1. The solver does not create the folder.
  The probe was deliberate and was the arm's last command, so every earlier save had
  already succeeded, which isolates the cause. The launcher kills a run at a timeout since
  then. This is the measurement behind FR-361 (create the folders before the launch, check
  every save target) and the 611 s note of FR-358 (the working directory of a batch is
  fixed and its folders are made before the instance starts).
- **The exported log is cumulative.** Each log export writes the whole instance log so far:
  2834 lines with one unsteady run, 6162 with two, and 10936 in Test 2's third export with
  three runs. Anything reading a point's log cuts it at that point's start, the
  "Solving unsteady time-step iteration (1/N)" line or the "Solution cleared. Initialization
  removed." line before it. The clearing command for the log is documented and was not run
  on 26.124.

### Time

| arm | wall clock | solver run time from the log |
|---|---|---|
| fresh instance, one 45-step point | 15.91 s | .24 min |
| two points in one instance (arm A) | 30.22 s | .23 and .24 min |
| polar 2 alone (arm D) | 25.46 s | .20 and .20 min |
| polar 1, reset, polar 2 (arm C) | 55.88 s | polar 2 slower, see the actions |
| a launch with no solve (two opens and exports) | 1.67 s | n/a |

On this machine a fresh launch costs about 2 s more than a re-initialization for this small
mesh. The saving that matters on a cluster, the queue wait and the licence checkout per job,
cannot be measured here. The log prints run time to 0.01 min, so the overhead figures are
good to about 1 s.

## 6. Verdict and the requirements it supports

| requirement | what these runs show |
|---|---|
| FR-352 | the removal then the initialization between two points of a polar gives a point bit-identical to a fresh instance, also when J changes; geometry, frames, force plots and motion stay loaded; licensed confirmation given (Test 1, 1b) |
| FR-353 | `NEW_SIMULATION` then `OPEN` is a clean slate for every state that reaches a result, across other flags (Test 2) and across a mesh change (Test 3); the instance is refreshed, not closed |
| FR-354 | the actions survive both the removal and the refresh, and registering them again doubles them (counter 189 against 72); registered once they ran once a step across a mesh change (counter 93) |
| FR-359 | relative and absolute save and export paths both work; a relative path resolves against the process working directory, which must not move |
| FR-360 | each point saved its `.fsm` and exports into its own folder and no point overwrote another; a saved point reopens as itself |
| FR-361 | a save into a missing folder hangs a hidden instance (stopped at 611 s); the folders must exist before the launch |
| FR-378 | `OPEN` loads saved actions; a solved `.fsm` is not the pristine geometry; saved simulations are compared by block, never by hash |
| FR-358 (611 s note) | the hang above is the measured cost of a save target that does not exist |

The per-point reset of the step counter and the wall clock at the start of a point is the
requirement the counters of Tests 1 to 3 motivate (90, 189, 93 across points); its licensed
confirmation is RPT-142.

## 7. What this does not show

- One build, two synthetic geometries, unsteady and unsteady_rotor points only. A steady
  polar after an unsteady one, or the reverse, is not measured.
- The removal with the motion, the boundaries or the geometry changed between points of one
  polar is not measured (only the advance ratio changed).
- Memory growth over many refreshes, and the number of polars one instance can hold, are not
  measured; two polars were run.
- An `OPEN` of a file whose saved actions have names or commands different from the
  surviving ones (replace against merge), and whether a re-registered action with the file's
  name collapses, are not measured.
- A repeated export name over an existing file was not tested.
- No cluster build and no queue were involved; the time saving on a cluster is not measured.
- One arm launch attempt (arm D, from a combined loop) produced no record and no process and
  its cause was not determined; it was relaunched through the same launcher and is the
  record used.
