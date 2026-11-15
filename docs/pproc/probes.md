## Probe tables

<a id="probes"></a>

`probes/<point>_probes.csv`, and `probes/<point>_probes_history.csv` where a row mixes
fluid-plot probes with default entries. The folder holds probe tables only. Written
for every row that declares `[[probes]]`, of any run type: the last-step table of a
steady point from the probe-points export, or of an unsteady point from its plots
history.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block) |
| `PROBE` | the probe point's number, counted across the entries of the artifact |
| `X`, `Y`, `Z` | the point's coordinates, in the frame `FRAME` names |
| `FRAME` | the frame of the coordinates |
| `STEP` | the solver step the sample is from; `NA` on a steady point |
| the export's columns | the fluid quantities the solver exports at the point (`Mach`, `Cp`, `vx`, `vy`, `vz`, `vtot`) and the boundary-layer columns, in the export's units and order |

The definition of record is [the probes table](../definitions/the-probes-table.md#the-probes-table).
