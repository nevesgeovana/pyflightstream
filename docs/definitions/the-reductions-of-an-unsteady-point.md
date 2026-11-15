## The reductions of an unsteady point

Custom recipes that name no registered workflow record no reduction windows.
Registered workflows select reductions from their run type, including when only
the workflow cell supplies that type; conflicting declarations are refused.

For animation-frame reductions, `write_reduction` writes
`field,probe,mean,first_step,last_step,n_frames`. The final three columns
record the first and last source steps actually used and the number of
frames averaged. For example, source steps 2, 4, 6 and 8 reduced over the
declared window 3 through 7 record `first_step=4`, `last_step=6` and
`n_frames=2`. The time series remains beside the reduction. A manually
constructed `FrameAverage` without source bounds leaves those bounds blank.

An unsteady point's plots table is its raw time history, one row per solver
time step. The stage writes its reductions beside it, one file per
reduction, each named in `products.json` with the reduction and the window
it used; raw is the plots table itself and is written once,
never a second time under another name. Which reductions apply is the run
type's, and the window is the one the row states ([the averaging
window](the-averaging-window.md#the-averaging-window)). The reductions are written to
`reductions/`, the history to `time_history/`. Each reduction has its own definition:
[`phase_locked`](phase_locked.md#phase_locked), [`per_revolution`](per_revolution.md#per_revolution) and [the
per-station harmonics](the-per-station-harmonics.md#the-per-station-harmonics). The
window average of every family and group is its row in the polar files
([`time_average`](time_average.md#time_average) and [`per_blade`](per_blade.md#per_blade)
are no longer written).

| file | run type | window |
|---|---|---|
| `reductions/<point>_phase_locked_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | WITH a `[phase_locked]` table in the pproc: the last `last_revolutions_avg` revolutions OF THAT ROTOR, one row per azimuthal position, each value the mean across those revolutions at that azimuth. WITHOUT it: the time-average window cut into blade passages OF THAT ROTOR, one of its revolutions over its own blade count, a trailing partial passage dropped; one row per passage |
| `reductions/<point>_per_revolution_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | ONE ROW PER COMPLETE REVOLUTION of that rotor, cut on ITS OWN steps per revolution from the written plots table: the mean of every plotted column and, from the second revolution on, each column's drift from the previous revolution in per cent. A trailing partial revolution is excluded and named under `skipped`. The pproc's optional `[per_revolution]` table declares `drift_limit_pct` (positive, default 1): when the LAST revolution's change of a force or moment column exceeds it in per cent of the largest previous mean of the same kind in its group (an in-plane force against the thrust, an in-plane moment against the torque), `post.log` carries a WARNING and nothing is blocked. [Definition of record](per_revolution.md#per_revolution) |
| `reductions/<point>_harmonics.csv` | `unsteady_rotor` with per-step sectional exports, and a `qsteady_rotor` wheel | THE LAST COMPLETE REVOLUTION of each rotor, on its own steps per revolution, from the written sections series; on a wheel every blade at every clocking of the sections table. Per rotor, blade station and sectional load quantity, the least-squares `H0`, 1P and 2P amplitude and phase over the samples' blade azimuths; a harmonic short of distinct azimuths (1P needs 3, 2P 5) is `NA` and said once in `post.log`. [Definition of record](the-per-station-harmonics.md#the-per-station-harmonics) |
| `reductions/<point>_phase_locked.csv` | `unsteady_rotor`, a row naming no rotor by alias | WITH a `[phase_locked]` table: the last `last_revolutions_avg` revolutions, one row per azimuthal position. WITHOUT it: the time-average window cut into blade passages, one revolution over `BLADES` steps each, a trailing partial passage dropped; one row per passage |
| `surfaces/<point>_time_average.dat` (and `.vtk` with `[exports] vtk`) | `unsteady_rotor` and `unsteady`, WITH a `[time_averaging]` table in the pproc | the table's `last_iters` or `last_revs`, ending at the run's last step: the surface exported at every step of it, averaged panel by panel by the package ([the definition](native-surface-flow-exports.md#native-surface-flow-exports)) |

Every window is counted in solver steps, inclusive, 1-based. The clock is the
plots table's own `Time-step` column where it states one as a strictly
increasing column of whole numbers, so a table whose clock does not begin at
one is windowed on the steps it states; otherwise (no such column, a cell that
is not a finite whole number, or a repeated or decreasing step) row `k` of the
table is step `k` for the whole table, never a mix of the two. The table's time
column is not averaged. The average is the one
implementation of blade-passage averaging the package holds
(`pyflightstream.post.blade_passage_average`), applied once per window, and
it is taken over the WRITTEN plots table, so a reduction can be recomputed
from the file beside it. The windows travel on the run record: `pyfs-matrix
run` resolves them off the row when it writes the record (`reductions` in
`runs.json`), and `pyfs-matrix post` reads them from there, with one
exception: the averaging window is resolved again from the matrix as `post`
reads it (`LAST_REVS_AVG` or `LAST_ITERS_AVG`), against the clock the record
already carries, so the key can be edited and `post` re-run with no solver.
Where the matrix names no key, the window the run recorded stands. A reduction the
row cannot window is listed under `skipped` with the reason, keyed by the
file it would have been: a rotor row that names NO rotor by alias and
states no `BLADES` skips the two passage reductions; a plots table shorter
than the window skips every reduction over it; a record written before this
field existed skips them naming the record. Not applicable is
not skipped.

**A ROW THAT NAMES ITS ROTORS REDUCES PER ROTOR**, and
it needs no `BLADES` of its own: each rotor's blade count is the one its
rotor block declares, and each rotor's blade passage is ITS OWN
revolution, `60 / (rev per minute * the solver step)`, divided by its
blades. A transition row turning four lifters at 2200 rev/min and a pusher
at 900 reduces the two over passages of different lengths in one run, which
one file per reduction cannot hold, so the files name the rotor. The windows live on the run record under
`rotors` (`pyflightstream.cases.workflows.ROTORS_KEY`), alias to that
rotor's block, and each written file's manifest entry carries a `rotor`
field, so the rotor is readable without taking a file name apart. The two
reductions that are per rotor are named by
`pyflightstream.cases.workflows.PER_ROTOR_REDUCTIONS`. A rotor whose motion cannot be resolved is a SKIP under its own name
rather than an absence, so a rotor never simply vanishes from the products.

---
