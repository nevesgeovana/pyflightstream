## The averaged surface

<a id="averaged-surface"></a>

With `[time_averaging]` in the pproc, `surfaces/<stem>_time_average.dat` (Tecplot,
always) and `surfaces/<stem>_time_average.vtk` (with `[exports] vtk`): one surface per
point, averaged panel by panel over the window, each step weighing the same. The
coordinates are the nodes of the window's last step. The per-step surface exports stay
in the simulation folder.

Both files carry the [run block](../definitions/the-run-block.md#the-run-block) of the
point: in the Tecplot file as one `DATASETAUXDATA <COLUMN>="<value>"` record per column,
in the block's order, before the average's own records (`AVERAGE_OF`, `WINDOW`,
`STATISTIC`, `COORDINATES`, `TRANSLATION`, `SOURCE_FRAME`, `NODAL_VARIABLES`,
`NOT_CARRIED`); in the VTK file as dataset field data, one array per column, a double
array for a number (`nan` where it has none) and a string array for a text column. A
name both state keeps the block's value.

The variables, frames and the not-carried list are in
[native surface flow exports](../definitions/native-surface-flow-exports.md#native-surface-flow-exports).
