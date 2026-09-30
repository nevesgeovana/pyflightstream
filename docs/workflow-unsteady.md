# The unsteady workflow

The `unsteady` run type: a body that does not move, solved in the time domain, and the reductions of an unsteady point.

`unsteady` is one point of a body that does not move, solved in the
time domain: a uniform free stream, a physical time loop the row states
directly, one solve, one loads export. It exists because a study often
needs the unsteady answer for a shape with no rotor in it, and because a
powered and an unpowered configuration are only comparable when they are
solved on the SAME discretisation.

**Its clock is `DELTA_TIME` and `TIME_ITERATIONS`, and the azimuthal pair
is refused on it.** `DELTA_THETA` and `REVOLUTIONS` are not a clock: they
become one by dividing by a rotor speed, and a run that turns nothing has
none. The refusal says so and does not offer you a rotor speed, because a
speed stated to satisfy it would set the physical time step of a run that
emits no motion. A row carrying `RPM`, `ADVANCE_RATIO`, `RPM_SIGN`,
`ROTOR_AXIS`, `ROTOR_ORIGIN` or `MOVING_BOUNDARIES` is refused for the
same reason: nothing would read them, and the run would be recorded as
though they had been honoured.

**And one refusal reaches an `unsteady` row without its author touching
the row at all.** A solver preset stating a wake termination in
REVOLUTIONS is refused on this run type, because a run that turns
nothing has no revolution for the setting to be counted in. The run
does have a time loop, so the setting is not meaningless in principle;
it is unstateable in revolutions, and this package records no
steps-spelled preset key for it. Drop the key from the preset the row
names, or give that row a preset of its own. A steady row meets a
different refusal for a different reason, and a rotor row meets none.

**`LOG_OUTPUT` applies here too**, and for the same reason it applies to
a rotor run: an unsteady time loop always reaches its prescribed end, so
the iteration counter judges nothing and the run would be recorded
`COMPLETED_MAX_ITER` whatever the solver did. Name the log among the
row's outputs and the residuals decide instead.

## The reductions of an unsteady point

An unsteady point's plots table is its raw time history, one row per solver
time step. The stage writes its reductions beside it, one file per
reduction, each named in `products.json` with the reduction and the window
it used (PFS-2015.04); raw is the plots table itself and is written once,
never a second time under another name. Which reductions apply is the run
type's, and the window is the one the row states:

| file | run type | window |
|---|---|---|
| `probes/<point>_time_average.csv` | `unsteady_rotor` and `unsteady` | the AVERAGING WINDOW the row states, `LAST_REVS_AVG` on a rotor row and `LAST_ITERS_AVG` on a rotorless one, ending at the run's last step; without any (a record made before 0.24.0, since a new plan of such a row is refused), a rotor row's last revolution (from `DELTA_THETA` and `REVOLUTIONS`, or `RPM` and `DELTA_TIME`), and a rotorless row's whole run (`DELTA_TIME` and `TIME_ITERATIONS`). One row |
| `probes/<point>_phase_locked_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | WITH a `[phase_locked]` table in the pproc: the last `last_revolutions_avg` revolutions OF THAT ROTOR, one row per azimuthal position, each value the mean across those revolutions at that azimuth. WITHOUT it: the time-average window cut into blade passages OF THAT ROTOR, one of its revolutions over its own blade count, a trailing partial passage dropped; one row per passage |
| `probes/<point>_per_blade_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | ONE window shared by every blade: the row's `LAST_REVS_AVG`, counted in THAT ROTOR's revolutions and ending at the run's last step, and without the key that rotor's last complete revolution; ONE ROW PER BLADE since 0.24.0, each with its `BLADE`, its `FAMILY` and its `AZIMUTH_START` and `AZIMUTH_END` over that window |
| `probes/<point>_per_revolution_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors (since 0.31.0) | ONE ROW PER COMPLETE REVOLUTION of that rotor, cut on ITS OWN steps per revolution from the written plots table: the mean of every plotted column and, from the second revolution on, each column's drift from the previous revolution in per cent. A trailing partial revolution is excluded and named under `skipped`. The pproc's optional `[per_revolution]` table declares `drift_limit_pct` (positive, default 1): when the LAST revolution's drift of a force or moment column exceeds it, `post.log` carries a WARNING and nothing is blocked. [Definition of record](post-processing-definitions.md#per_revolution) |
| `sections/<point>_harmonics.csv` | `unsteady_rotor` with per-step sectional exports, and a `qsteady_rotor` wheel (since 0.31.0) | THE LAST COMPLETE REVOLUTION of each rotor, on its own steps per revolution, from the written sections series; on a wheel every blade at every clocking of the sections table. Per rotor, blade station and sectional load quantity, the least-squares `H0`, 1P and 2P amplitude and phase over the samples' blade azimuths; a harmonic short of distinct azimuths (1P needs 3, 2P 5) is `NA` and said once in `post.log`. [Definition of record](post-processing-definitions.md#the-per-station-harmonics) |
| `probes/<point>_phase_locked.csv` | `unsteady_rotor`, a row naming no rotor by alias | WITH a `[phase_locked]` table: the last `last_revolutions_avg` revolutions, one row per azimuthal position. WITHOUT it: the time-average window cut into blade passages, one revolution over `BLADES` steps each, a trailing partial passage dropped; one row per passage |
| no per-blade table | `unsteady_rotor`, a row naming no rotor by alias | No reference block identifies the blade families; `products.json` says why the table is skipped |
| `surfaces/<point>_time_average.dat` (and `.vtk` with `[exports] vtk`) | `unsteady_rotor` and `unsteady`, WITH a `[time_averaging]` table in the pproc (since 0.28.0) | the table's `last_iters` or `last_revs`, ending at the run's last step: the surface exported at every step of it, averaged panel by panel by the package ([the definition](post-processing-definitions.md#native-surface-flow-exports)) |

**`per_blade` IS ONE ROW PER BLADE OVER ONE SHARED WINDOW (0.24.0).** Until
0.23.0 it cut the last revolution into one window per blade, which put each blade
in a different stretch of the history; 0.23.0 wrote one window and ONE row. Since
0.24.0 every blade is averaged over the same window and has its own row, with its
start and end azimuth in columns, as [the definition of
record](post-processing-definitions.md#per_blade) asks. The azimuthal form of
`phase_locked` that page defines is written where the pproc declares
`[phase_locked]`.

**The window is required.** Since 0.24.0 `pyfs-matrix plan` refuses a new
unsteady row that states NO window key. Since 0.26.0, `WINDOW_STEPS`,
`WINDOW_REVOLUTIONS` and `WINDOW_DEGREES` are refused; replace them with
`LAST_REVS_AVG` or `LAST_ITERS_AVG`, dividing degrees by 360. The reductions and
unsteady polar of a record without the current keys use the window the run was
given, with a warning naming the steps.

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

**SINCE 0.15.0 A ROW THAT NAMES ITS ROTORS REDUCES PER ROTOR** (FR-68), and
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

<!-- skip: next -->
```python
from pyflightstream.cases.workflows import PER_ROTOR_REDUCTIONS, ROTORS_KEY

# Reading a run record's reductions without hard-coding either name.
per_rotor = record.reductions.get(ROTORS_KEY, {})
for alias, block in per_rotor.items():
    for reduction in PER_ROTOR_REDUCTIONS:
        entry = block[reduction]
        # -> {'windows': [[448, 515], ...], 'period_steps': 68, ...}
        #    or {'skipped': '<the reason this rotor has none>'}
```

A worked example: a row naming rotor `PROP` of eight steps, four steps per
revolution, two blades, stating `LAST_REVS_AVG: 1.5`, which is six steps. Its
reference declares a `[PROP]` block with `kind = "rotor"` and
`families_blades = ["Blade1", "Blade2"]`, alongside its hub, axis, diameter and
blade-one datum. Its pproc requests blade plots, for example:

```toml
[plots]
parameters = ["FX", "FY", "FZ", "MX", "MY", "MZ"]

[[plots.groups]]
name = "MRP_{family}"
frame = "MRP"
families = "each"
```

The run must export those blade columns; adding the declaration afterwards
requires a new run. With no `[phase_locked]` table, the reductions of
`AL-020_plots.csv` land as

```text
probes/AL-020_plots.csv           raw, one row per step
probes/AL-020_time_average.csv    one row, steps 3 to 8
probes/AL-020_phase_locked_PROP.csv  three rows, steps 3 to 4, 5 to 6, 7 to 8
probes/AL-020_per_blade_PROP.csv     two rows, one per blade, steps 3 to 8
```

each reduction file leading with its window and the flight condition, and then
the plots table's own columns; the exact header of each is on [the definition of
record](post-processing-definitions.md), which is the one place it is kept. And
`products.json` names each:

```text
"probes/AL-020_per_blade_PROP.csv": {
 "sim_id": "7001", "pproc": "p001", "runs": ["camp/sim_7001/AL-020"],
 "reduction": "per_blade", "rotor": "PROP", "windows": [[3, 8]],
 "window_from": "the averaging window the row states, 6 steps, shared by every blade",
 "period_steps": 2
}
```

A record written before 0.23.0 keeps the windows it recorded, so its
`per_blade` entry may still list one window per blade.
