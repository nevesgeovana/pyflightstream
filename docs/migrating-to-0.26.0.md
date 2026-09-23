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

Before replacing an empty member list with `"all"`, check the row's reference
for a collision: an existing boundary name or alias takes precedence over the
built-in selection of every family. Search the reference, then inspect matches
under `[aliases]` (including quoted keys):

```text
rg -n 'all|\[aliases\]' inputs/references/r001.toml
```

Also check the geometry inventory for a boundary named `all`. For example,
`all = ["W"]` under `[aliases]` makes `TOTAL = "all"` select only W, while the
retired empty list selected every surface. If `all` is taken, name a unique alias
holding the intended members, such as `WHOLE_AIRCRAFT = ["W", "B"]` in the
reference and `TOTAL = "WHOLE_AIRCRAFT"` in the pproc. Verify those members
against the inventory before posting. Replace integer boundary positions with
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

## The post log and what no longer refuses

Every post writes `post.log` beside `products.json`, and the manifest names it
under `log`. Check this file after posting, including after a clean campaign.
It records warnings and named skips with their point, product, applicable step
and remedy. Rebuilding archives the old log with the old products.

The default now reads native logs and warns about frozen solves and unread
blocks while writing every product it can compute. A failed point's status
alone no longer excludes usable exports. No-data, malformed-export and
unassignable-layout cases still have named skips because the requested table
cannot be computed.

```text
pyfs-matrix post --workspace campaign
pyfs-matrix post --workspace campaign --check-frozen
```

The second form asks to refuse affected averages instead of warning alone.
Both forms write the log. The azimuthal guard now uses the reducer's exact set
of plotted samples, including resolved blade-family aliases and every nonzero
interpolation weight. A terminal log cut before `Iteration` is unread; a
page-less marker immediately followed by the same step's marker is a repeat.
