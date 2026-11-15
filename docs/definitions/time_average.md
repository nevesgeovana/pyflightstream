## `time_average`

The window average of a point is the row of that point in the polar files. The
`time_average` table is no longer written: for every family it is its row in
[`FAM-ACOEF`](../pproc/fam-acoef.md), [`FAM-DIM`](../pproc/fam-dim.md) and, inside a
rotor, [`FAM-RCOEF`](../pproc/fam-rcoef.md); for every group it is the row of the
[group files](../pproc/group-files.md).

**One window per point.** Not one per rotor, because a point has one history. The
window is the one the row states ([the averaging
window](the-averaging-window.md#the-averaging-window)), and the first and last step
it used, the steps and the revolutions and blade passages it spans are in the
[run block](the-run-block.md#the-run-block) of every file of the point:
`FIRST_STEP`, `LAST_STEP`, `STEPS`, `WINDOW_REVS` and `WINDOW_PASSAGES`.

An unsteady point is a window average and a steady point is a steady value: the
run block says which, by `RUN_TYPE`, and the files carry the same names.
