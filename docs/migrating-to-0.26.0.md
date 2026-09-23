# Migrating to 0.26.0

This development cycle removes six forms whose compatibility period ended at
0.26.0. Update Python calls and editable matrix and pproc inputs as below.
Recorded run manifests are read without rewriting them.

## 1. Section samples use `step=`

Replace `write_sections_table(path, text, mach=0.1, iteration=144)` with:

```text
write_sections_table(path, text, mach=0.1, step=144)
```

`iteration=` is absent from the signature and raises TypeError, including when
its value is `None` or it appears beside `step=`. The solver's stamped export
filenames still use `_iteration=N`; those names do not change.

## 2. Campaign assessment uses `LoadsAssessor`

The standalone `assess_unsteady_from_plots` function has been deleted from
`pyflightstream.run`; importing it raises ImportError. For campaign assessment:

```python
from pyflightstream.run import LoadsAssessor
```

`LoadsAssessor` judges native loads and solver residuals. It does not replace a
history-settling analysis: choose and apply that analysis separately to the
recorded history. There is no replacement fractional-drift helper in `run`.

## 3. `WINDOW_STEPS` becomes `LAST_ITERS_AVG`

Replace `WINDOW_STEPS: 100` in the matrix row with `LAST_ITERS_AVG: 100`.
The count is unchanged. This is the averaging key of a rotorless unsteady row
and can also state a rotor row's window in iterations.

## 4. `WINDOW_REVOLUTIONS` becomes `LAST_REVS_AVG`

Replace `WINDOW_REVOLUTIONS: 1.5` with `LAST_REVS_AVG: 1.5` on an
`unsteady_rotor` row. The count is unchanged and each rotor uses its own clock.

## 5. `WINDOW_DEGREES` becomes `LAST_REVS_AVG`

Divide degrees by 360: `WINDOW_DEGREES: 90` becomes `LAST_REVS_AVG: 0.25`.
Every `WINDOW_*` key is refused at plan time, even beside its replacement.
State only one of `LAST_REVS_AVG` and `LAST_ITERS_AVG`. The `_uns_avg` product
naming and windows stored in recorded manifests remain unchanged.

## 6. A pproc group names one alias

Replace `PUSHER = ["PUSHER"]` under `[groups]` with `PUSHER = "PUSHER"`.
For several members, declare their alias in the reference:

```toml
[aliases]
AIRFRAME = ["W", "B"]
```

Then point the pproc group at it:

```toml
[groups]
AIRFRAME = "AIRFRAME"
TOTAL = "all"
```

An empty member list becomes `"all"`. Replace integer boundary positions with
boundary names in the reference's alias. Every list form is refused with the
one-alias line to write instead.

## Older recorded manifests stay readable

`broken_commands` is silently read as `waived_commands` for as long as manifests
carrying it exist. Since 0.26.0 this is plain compatibility with no countdown.
New records write `waived_commands`; a record containing both keys is refused.
Do not rewrite a recorded manifest to update this spelling.

## Integrated sectional loads

To receive forces and moments per strip as well as the exported line densities,
add `integrate = true` to the desired `[[sections.distributions]]` pproc entry.
The default is false, retaining the previous CSV bytes and columns. Re-posting
existing exports can enable this option without another solver run.

The same sectional file appends `Strip_length` (m), `Fx_int` and `Fz_int` (N),
and `My_int` (N m) after `Moment`. Strip boundaries are the midpoints between
exported stations, with half intervals at the ends. Integration is separate
for each recorded block and STEP; it preserves the section axes and azimuth.
`My_int` remains about each station's quarter chord, as specified by SRC-751
p.253, with no transfer to the hub or elastic axis and no revolution envelope.

An invalid block leaves the entire file in its original form and emits a
`PyflightstreamWarning` naming the point, file and reason; post continues.
See [Integrated sectional loads](post-processing-definitions.md#integrated-sectional-loads-since-0260)
for the column definitions, moment-point evidence and exact strip rule.
