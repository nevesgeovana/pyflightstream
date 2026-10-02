# RPT-142 - The batched-run rehearsal of the 0.35.0 dev wheel on FlightStream 26.124 (2026-10-02)

The licensed rehearsal of the batched cluster runs of pyflightstream 0.35.0 (`--batch` and
`--polar-sweep`), run on the development wheel before any cluster test, on **FlightStream
26.124, build 8172026**, executable SHA-256 withheld from the public tree per NFR-31, local
executor, one solver instance per job, hidden, far field 5 layers stated in every setup. It
is the licensed counterpart of the measurements of RPT-141: there a hand-cut script
showed that one instance can hold several points and polars; here the package emits the job
script, runs it, collects it and posts it. Run window: 2026-10-02T17:03 to 17:18 local, in
four launches, never beside a test suite or a second solver.

Only nondimensional values are stated, plus counts, iteration numbers, megabytes and
seconds. The geometries are the two synthetic tier-3 geometries, `30_BLADE.fsm` and
`40_PUSHER.fsm`. The point numbers (POL 9901, 9902, 9911, 9912, 9931) belong to synthetic
cases.

## 1. The question

Does a job that holds several points and polars in one instance, planned with
`plan --batch 1` or `--polar-sweep` and run with `run ... --local`, leave each point exactly
as the same point run alone leaves it (FR-351, FR-352, FR-353, FR-354), and do the pieces the
job adds (the per-point clock start FR-355, the batch folders, the collect and the log
slicing) work on the real solver?

## 2. The case

Polar A: `30_BLADE`, unsteady_rotor, advance ratio 1.7, 10 degrees a step, 1.25 revolutions
= 45 steps, alpha 0 and 2. Polar B: `40_PUSHER`, unsteady_rotor, Mach 0.1, 15 degrees a
step, 1 revolution = 24 steps, alpha 0 and 4. Each is the case of RPT-141 (Tests 1 and 3).
The twins for comparison are the package's own fresh-instance runs of those points, one
instance each: polar A alpha 0 and 2 (iteration 826 and 1085 at the last step) and polar B
alpha 0 and 4 (735 and 733).

## 3. The arms

| arm | matrix | commands (role form) | wheel |
|---|---|---|---|
| R1 | POL 9901 (polar A) and 9902 (polar B), 8 CPUs each, a job walltime of 30 minutes | `plan <matrix> --batch 1`; `run <matrix> --batch 1 --local`; `collect`; `post` | the first dev wheel |
| R2 | POL 9911 (polar A) and 9912 (polar B), a setup with a clock margin of 30 s, a job walltime of 68 s so the deadline is 38 s after the first step, per-step exports from step 20 on polar A and from step 10 on polar B | the same four, then a re-plan and a re-run of what the clock left | the tree with the R1 fixes |
| R3 | POL 9931, polar B alone | `plan <matrix> --polar-sweep`; `run <matrix> --polar-sweep --local`; `collect` | the same tree |

One job holds the four points of R1 and R2 (a batch of one). R3 is the polar sweep: one job
for the one polar. The package tree of each launch is recorded: R1 ran at `455ccb71` with
no file changed; R2 at `56fa0bac` with no file changed; the second pass of R2 and R3 ran on
the fixed tree with 3 and 1 uncommitted working-tree files recorded, the fixes of section 5
among them. Every launch ended with exit status 0 except the first pass of R2, where the
clock stopped the job (section 4).

## 4. Measurements

### R1: the four points, one instance (FR-351 to FR-354, FR-366, FR-368, FR-374, FR-375, FR-376)

The job ran the two polars in order inside one solver instance: the instance's unsteady-step
counter reads **138 = 45 + 45 + 24 + 24**, and the per-point clock files read 45, 45, 24 and
24 steps, each point's own. The launcher recorded a peak working set of 196.6 MB, a lowest
free memory of 2.16 GB and 65.2 s for the whole command file (plan, run, collect, post).
The points lived in the batch's own folder while the job ran, and `collect` moved them to
their simulation folders.

| point | comparison with the point run alone | result |
|---|---|---|
| polar A alpha 0 | plots 1035 cells, CL, CDi and CM of every step, iteration count of every step, last iteration 826 | identical |
| polar A alpha 2 | plots 1035 cells, 45 steps, last iteration 1085 | identical |
| polar B alpha 0 | plots 888 cells, 24 steps, last iteration 735 | identical |
| polar B alpha 4 | plots 888 cells, 24 steps, last iteration 733 | identical |

**R1: 4 of 4 points identical.** The log of each point was read from its own slice of the
instance's cumulative log (45 and 24 step lines each, never the whole), which is the
slicing of FR-368 working on the real log.

The saved simulations were compared block by block, 16 blocks against 16 in every pair and
the same size to the byte in each pair, and are not part of the count. The blocks that
differ are in known classes only: a line holding the interpreter path in the saved actions
(the twin ran under another interpreter), line 31 of the GRAPHICS block (a window geometry
that changes after an instance's first save), value 25 of the WAKE strands (the unused slot
after the last step), one denormal in the WRAPPER block, and run-to-run rounding of unprinted
digits in the SOLVER block (about 1e-14 relative). The classes are those of RPT-141.

The solver's own memory report grows within the instance: polar A 161.8 MB at point 1 and
169.7 MB at point 2, polar B 198.1 MB at point 1 and 205.5 MB at point 2, about 7 to 8 MB
for the second point of each polar. Four points do not measure growth over many.

### R2: the clock start and the walltime (FR-355, FR-370, FR-371)

The setup states a clock margin of 30 s and the matrix a walltime of 68 s, so the job
deadline is 38 s after the clock's first step. Per-step exports were asked from step 20 on
polar A and from step 10 on polar B. The first pass ran four points in one job:

- **The clock start is reset at each point (FR-355: YES).** Each point's clock file holds its
  own start time and its own step count: 45 and 45 on polar A, started 17 s apart, then
  polar B point 1. The per-step exports of polar A run from its own step 20 to 45
  (`..._iteration=20` to `45`) in each point, and those of polar B from its own step 10, in
  the point where the counter of the instance had already passed 90. A clock that ran across
  the instance would have started polar A point 2's exports at step 65 of the job.
- **The deadline fired where designed.** It fired at **polar B point 1, own step 11**, 38.4
  s after the clock's first step: that point's record reads `WALLTIME_REACHED`, 11 steps, the
  instance's counter reads 101 = 45 + 45 + 11, the wall-clock action wrote the stop text and
  saved the point's outputs as they stood, with the step stamp in the names (the files for
  steps 10 and 11).
- **Polar B point 2 was not started**, and the job named it so (outstanding, not failed).

The second pass re-planned the same matrix. The plan then listed 1 point ready and 3 already
recorded (the two converged points of polar A and the stopped point 1 of polar B), the
not-started point was batched alone and run, and it **converged identical** to the point run
alone: plots 888 of 888 cells, 24 steps, last iteration 733, a counter of 24 in its own
job. The comparison counts 3 of 4 points identical, and the fourth is the stopped point,
reported as different for what it is: 11 steps, a plots table of 10 rows against 24, and a
log of 11 step lines against 24. It stopped at the deadline, as designed. Polar A's two
points compare identical (1035 of 1035 cells, last iterations 826 and 1085).

Block by block, the saved simulations of R2 show the same classes as R1, and the SOLVER block of polar A's
files holds 724 lines against the twin's 721; that 3-line difference was not traced here.

### R3: the polar sweep (FR-375, FR-376)

`run <matrix> --polar-sweep --local` on polar B alone ran one job with the two points of the
polar: both **identical** to the points run alone, plots 888 of 888 cells each, 24 steps,
last iterations 735 and 733: **2 of 2**. `collect` completed both (10 outputs each, recorded
`CONVERGED`) and `post` followed. The launcher recorded 33.8 s for the whole command file.

## 5. The three defects the rehearsal found, and their fixes

R1 ran on the first dev wheel; R2 and R3 ran on the fixed tree.

1. **`collect` refused a batch's plan.** After R1's solver run finished, `collect` marked
   all four points FAILED, "the grouped job could not be prepared": the plan leaves each
   simulation's inputs folder empty, and `collect` read a real, empty folder where the batch
   holds a link to the shared inputs. The solver run itself was intact. Fixed in `56fa0bac`
   (the empty inputs folder the plan leaves is adopted); the collect, repeated after the fix,
   completed all four points (10 outputs each, `CONVERGED`) and R1's 4 of 4 above reads those.
   The first post of the command file also stopped on a command-line misuse (`--local` is
   refused by `post` without `--additional-pproc`), which was a mistake of the command file,
   not a defect.
2. **A point the clock stopped carried its step stamp.** The outputs of a point stopped by
   the deadline are named `<name>_iteration=<step>` (the stamp the per-step exports use),
   so the first `collect` of the second pass found "9 of 9 declared outputs not there yet"
   and left the point outstanding. `collect` now adopts the stamped outputs of a clock-stopped
   point as that point's outputs; the repeated collect completed it (10 outputs).
3. **Not-started points were read as recorded.** The plan of the second pass counted the
   points the clock never started among the recorded ones, so it would have left them
   forever. They are now read as outstanding, which is why the second pass listed exactly one
   point ready.

## 6. Verdict and the requirements it supports

| requirement | what the rehearsal shows |
|---|---|
| FR-351 | `run --batch 1 --local` ran the jobs the plan listed and nothing else |
| FR-352, FR-353, FR-354 | within a polar the removal and the initialization, between the polars the refresh, the actions registered once (counter 138 = 45 + 45 + 24 + 24): all four points identical to the points run alone, 1035 and 888 of 888 cells, every iteration count |
| FR-355 | the clock start resets at each point: **YES**; per-step exports from each point's own step 20 and 10, not the job's |
| FR-366, FR-374 | each point is recorded as a point run alone is; the batch's points lived in the batch folder while the job ran and `collect` moved them to the simulation folders |
| FR-367, FR-368 | `collect` completed a job's points (after the fix of section 5), and each point's log was read from its own slice of the cumulative log |
| FR-370, FR-371 | one wall clock for the job; the point the deadline reached is `WALLTIME_REACHED` at its own step 11, the point not started is named, and the step counter of each point is its own (45, 45, 11, 24) |
| FR-375, FR-376 | `--local` combines with `--batch` and `--polar-sweep`, and the run is the solver only (R3: 2 of 2 identical) |

Requirements of the range FR-351 to FR-376 not named here (FR-356, FR-357, FR-358, FR-361 to
FR-365, FR-369, FR-372, FR-373) were not exercised by these runs: no point failed without
stopping the instance, no node-local storage was used, and no queue was involved.

## 7. What this does not show

- One build, two synthetic geometries, unsteady_rotor points on a local executor. No cluster,
  no queue, no node-local storage, and so no measure of the saving the batch exists for.
- A batch of one (`--batch 1`) and one polar sweep. A split into several jobs, and the choice
  of `BEST` as the walltime, were not run (the matrix with `BEST` was refused by 0.34, and
  the rehearsal ran with a stated walltime).
- Four points per job and two polars: growth of memory or of the step counter over many is
  not measured.
- The deadline was reached once, at one point; the exports of a clock-stopped point and
  the second pass are measured for that one case. A point that fails without stopping the
  instance is not exercised.
- The saved simulations are compared by block, not by hash, and are not part of the count of
  identical points.
