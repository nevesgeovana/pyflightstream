## The reductions of an unsteady point

An unsteady point's plots table is its raw time history, one row per solver
time step. The stage writes its reductions beside it, one file per
reduction, each named in `products.json` with the reduction and the window
it used (PFS-2015.04); raw is the plots table itself and is written once,
never a second time under another name. Which reductions apply is the run
type's, and the window is the one the row states ([the averaging
window](the-averaging-window.md#the-averaging-window)). Each reduction has its own definition: [`time_average`](time_average.md#time_average), [`per_blade`](per_blade.md#per_blade),
[`phase_locked`](phase_locked.md#phase_locked), [`per_revolution`](per_revolution.md#per_revolution) and [the
per-station harmonics](the-per-station-harmonics.md#the-per-station-harmonics).

| file | run type | window |
|---|---|---|
| `probes/<point>_time_average.csv` | `unsteady_rotor` and `unsteady` | the AVERAGING WINDOW the row states, `LAST_REVS_AVG` on a rotor row and `LAST_ITERS_AVG` on a rotorless one, ending at the run's last step; without any (a historical record, since a new plan of such a row is refused), a rotor row's last revolution (from `DELTA_THETA` and `REVOLUTIONS`, or `RPM` and `DELTA_TIME`), and a rotorless row's whole run (`DELTA_TIME` and `TIME_ITERATIONS`). One row |
| `probes/<point>_phase_locked_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | WITH a `[phase_locked]` table in the pproc: the last `last_revolutions_avg` revolutions OF THAT ROTOR, one row per azimuthal position, each value the mean across those revolutions at that azimuth. WITHOUT it: the time-average window cut into blade passages OF THAT ROTOR, one of its revolutions over its own blade count, a trailing partial passage dropped; one row per passage |
| `probes/<point>_per_blade_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | ONE window shared by every blade: the row's `LAST_REVS_AVG`, counted in THAT ROTOR's revolutions and ending at the run's last step, and without the key that rotor's last complete revolution; ONE ROW PER BLADE, each with its `BLADE`, its `FAMILY` and its `AZIMUTH_START` and `AZIMUTH_END` over that window |
| `probes/<point>_per_revolution_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | ONE ROW PER COMPLETE REVOLUTION of that rotor, cut on ITS OWN steps per revolution from the written plots table: the mean of every plotted column and, from the second revolution on, each column's drift from the previous revolution in per cent. A trailing partial revolution is excluded and named under `skipped`. The pproc's optional `[per_revolution]` table declares `drift_limit_pct` (positive, default 1): when the LAST revolution's change of a force or moment column exceeds it in per cent of the largest previous mean of the same kind in its group (an in-plane force against the thrust, an in-plane moment against the torque), `post.log` carries a WARNING and nothing is blocked. [Definition of record](per_revolution.md#per_revolution) |
| `sections/<point>_harmonics.csv` | `unsteady_rotor` with per-step sectional exports, and a `qsteady_rotor` wheel | THE LAST COMPLETE REVOLUTION of each rotor, on its own steps per revolution, from the written sections series; on a wheel every blade at every clocking of the sections table. Per rotor, blade station and sectional load quantity, the least-squares `H0`, 1P and 2P amplitude and phase over the samples' blade azimuths; a harmonic short of distinct azimuths (1P needs 3, 2P 5) is `NA` and said once in `post.log`. [Definition of record](the-per-station-harmonics.md#the-per-station-harmonics) |
| `probes/<point>_phase_locked.csv` | `unsteady_rotor`, a row naming no rotor by alias | WITH a `[phase_locked]` table: the last `last_revolutions_avg` revolutions, one row per azimuthal position. WITHOUT it: the time-average window cut into blade passages, one revolution over `BLADES` steps each, a trailing partial passage dropped; one row per passage |
| no per-blade table | `unsteady_rotor`, a row naming no rotor by alias | No reference block identifies the blade families; `products.json` says why the table is skipped |
| `surfaces/<point>_time_average.dat` (and `.vtk` with `[exports] vtk`) | `unsteady_rotor` and `unsteady`, WITH a `[time_averaging]` table in the pproc | the table's `last_iters` or `last_revs`, ending at the run's last step: the surface exported at every step of it, averaged panel by panel by the package ([the definition](native-surface-flow-exports.md#native-surface-flow-exports)) |

**`per_blade` IS ONE ROW PER BLADE OVER ONE SHARED WINDOW.** Every blade is averaged over the same window and has its own row, with its
start and end azimuth in columns, as [its definition](per_blade.md#per_blade) asks. The azimuthal form of
`phase_locked` that page defines is written where the pproc declares
`[phase_locked]`.

Every window is counted in solver steps, inclusive, 1-based, and row `k` of
the plots table is step `k`; the table's own time column is averaged like
any other column and is not read as the clock. The average is the one
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
field existed skips the time average naming the record. Not applicable is
not skipped: a rotorless point lists no per-blade file anywhere.

**A ROW THAT NAMES ITS ROTORS REDUCES PER ROTOR** (FR-68), and
it needs no `BLADES` of its own: each rotor's blade count is the one its
rotor block declares, and each rotor's blade passage is ITS OWN
revolution, `60 / (rev per minute * the solver step)`, divided by its
blades. A transition row turning four lifters at 2200 rev/min and a pusher
at 900 reduces the two over passages of different lengths in one run, which
one file per reduction cannot hold, so the files name the rotor and the
flat `<point>_per_blade.csv` is listed under `skipped` with a reason naming
the files written instead. The windows live on the run record under
`rotors` (`pyflightstream.cases.workflows.ROTORS_KEY`), alias to that
rotor's block, and each written file's manifest entry carries a `rotor`
field, so the rotor is readable without taking a file name apart. The two
reductions that are per rotor are named by
`pyflightstream.cases.workflows.PER_ROTOR_REDUCTIONS`; the time average is
not among them, because it is one window of the whole point whatever turns
in it. A rotor whose motion cannot be resolved is a SKIP under its own name
rather than an absence, so a rotor never simply vanishes from the products.

---
