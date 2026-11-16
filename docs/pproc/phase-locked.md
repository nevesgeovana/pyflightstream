## phase_locked: the reduction by azimuth or passage

<a id="phase-locked"></a>

`reductions/<point>_phase_locked_<ALIAS>.csv` (one per rotor the row names), or
`reductions/<point>_phase_locked.csv` for a row that names no rotor by alias. Written
for an unsteady-rotor point, once per point.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block); `FIRST_STEP`, `LAST_STEP`, `STEPS` and `WINDOW_REVS` describe the row's own average; `WINDOW_PASSAGES` is omitted |
| `REDUCTION` | `phase_locked` |
| `ROTOR_ID`, `ROTOR` | the declared id and the alias of the rotor; `NA` for a row that names none |
| `AZIMUTH`, `STEP`, `REVOLUTIONS` | with a `[phase_locked]` table, the azimuth the row is the mean at, the step of that mean and the revolutions it averages; without one, one row per blade passage |
| the plots | the plotted columns averaged over the row's window, in the plots history's units |

The definition of record, the windows and the sense of the azimuth are on
[`phase_locked`](../definitions/phase_locked.md#phase_locked), one of [the reductions of
an unsteady point](../post-processing-definitions.md#the-reductions-of-an-unsteady-point).
Its columns, units and frames are stated in [`products.json`](products-json.md).
