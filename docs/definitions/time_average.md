## `time_average`

One average of the whole point over one window. It is what a POLAR row of an
unsteady point is built from.

**One window per point.** Not one per rotor, because a point has one history.

`probes/<point>_time_average.csv` opens with `POL`, `REDUCTION`, `ROTOR`,
`WINDOW`, `FIRST_STEP`, `LAST_STEP`, `STEPS`, then the condition block and the
moment point, then the plotted columns averaged over the window. The passage
series a pproc without `[phase_locked]` gets under the phase-locked name has the
same columns.

---
