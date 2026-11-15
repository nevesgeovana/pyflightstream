## per_revolution: one row per complete revolution

<a id="per-revolution"></a>

`reductions/<point>_per_revolution_<ALIAS>.csv`, one per rotor the row turns (or
`reductions/<point>_per_revolution.csv` for a flat clock). Written for an
unsteady-rotor point. The history is cut into complete revolutions of the rotor's own
steps per revolution; a trailing partial revolution is not averaged and is named in
`products.json`.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block); the window columns are those of the revolution the row is |
| `REDUCTION` | `per_revolution` |
| `ROTOR_ID`, `ROTOR` | the declared id and the alias of the rotor |
| `REVOLUTION` | the revolution, from 1 |
| the plots | the mean of every plotted column over the revolution |
| `<plot>_DRIFT_PCT` | from the second revolution, each column's change from the previous revolution, in per cent |

The drift limit `[per_revolution] drift_limit_pct` (default 1) warns in `post.log`
when the last revolution is still moving, and blocks nothing. The definition of record
is [`per_revolution`](../definitions/per_revolution.md#per_revolution), one of [the
reductions of an unsteady point](../post-processing-definitions.md#the-reductions-of-an-unsteady-point).
