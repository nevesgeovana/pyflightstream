## The plots history

<a id="time-history"></a>

`time_history/<point>_plots.csv`, one row per solver time step, written for an unsteady
or unsteady-rotor point when `[products] plots` is on. It is the raw history the
reductions and the window averages of the polar files are taken over; none of them
replaces it.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block), in its order; the window columns state the window the point's averages use |
| `Time-step` | the solver step of the row, the clock of the table |
| the plots | one column per plotted quantity, named `<PARAMETER>_<FRAME>_<GROUP>` as the plot group names it (`FX_MRP_TOTAL`), or as the pproc's `[names]` dictionary renames it |

Forces are in N and moments in N m, in the frame the plot group declares. The
coefficient columns (`CL_`, `CDI_`, `CDO_`, `CDP_`, `CDV_`, `CD_`) are brought from the
solver's reference velocity to the free stream by `(VREF / VINF)^2`; where the free
stream is zero they read `NA`, and the log says why.

The table is read back by every reduction, so a reduction can be recomputed from the
file beside it. Its units and frames are stated for every column in
[`products.json`](products-json.md).

Probe tables are not in this folder: `probes/` holds probe tables only.
