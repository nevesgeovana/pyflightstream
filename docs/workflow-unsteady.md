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

**The per-step exports of the end of the run** are stated on this run type in
time steps: `EXPORT_UNSTEADY_AFTER_ITER: <step>` begins them at a step, and
`EXPORT_UNSTEADY_LAST_ITER: <steps>` covers the last `<steps>` steps of the run
(first exported step `TIME_ITERATIONS - <steps> + 1`), at most one of the two
per row (FR-415). The revolutions forms are refused here, having no rotor clock;
the refusal names the iterations form. See [the last revolutions or the last
steps of a run](workflow-unsteady-rotor.md#the-last-revolutions-or-the-last-steps-of-a-run).

**`LOG_OUTPUT` applies here too**, and for the same reason it applies to
a rotor run: an unsteady time loop always reaches its prescribed end, so
the iteration counter judges nothing and the run would be recorded
`COMPLETED_MAX_ITER` whatever the solver did. Name the log among the
row's outputs and the residuals decide instead.

## Probes: unsteady or normal

A pproc `[[probes]]` entry on this run type is an UNSTEADY probe unless it
states `kind = "normal"` (0.37.0): one fluid plot per point and parameter,
whose history the solver writes at every time step. A NORMAL probe is a probe
point created after the time march, updated and exported once, so the probes
table and any sampled field or reusable inflow hold the run's last time step.
Use it when only the end of the run is needed. Every entry of one row is of one
kind. The script of a normal entry, after the march:

```text
START_SOLVER
NEW_PROBE_LINE ... / NEW_PROBE_POINT VOLUME ... / PROBE_POINTS_IMPORT ...
UPDATE_ALL_SURFACE_SECTIONS
COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS
UPDATE_PROBE_POINTS
SAVEAS ...
EXPORT_PROBE_POINTS <point>_probes.txt
```

With a per-step export window, the normal probes are also exported at every
step of the window: the exports script of the first exporting step creates them,
and every step of the window runs

```text
UPDATE_PROBE_POINTS
EXPORT_PROBE_POINTS
<point>_probes.txt
```

beside the other per-step exports, stamped `<point>_probes_iteration=<step>.txt`.
See [the probe kind](pproc-artifact.md#the-probe-kind-of-an-unsteady-row).

## The reductions of an unsteady point

An unsteady point's plots table is its raw time history, one row per solver
time step, and the post writes its reductions beside it, one file per
reduction, each named in `products.json` with the reduction and the window it
used. Which reductions a point gets, what each file holds, the window each is
taken over and how a row naming its rotors reduces per rotor are defined in
one place, [the reductions of an unsteady
point](post-processing-definitions.md#the-reductions-of-an-unsteady-point) on
the definition of record; the window itself is [the averaging
window](post-processing-definitions.md#the-averaging-window). This page shows
them on a worked example.

The windows travel on the run record (`reductions` in `runs.json`), and a row
naming its rotors carries one block per rotor under `rotors`. Reading them
without hard-coding either name:

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

A historical record keeps the windows it recorded, so its
`per_blade` entry may still list one window per blade.
