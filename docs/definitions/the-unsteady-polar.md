## The unsteady POLAR

This page moved. An unsteady point is a row of the same polar files as a steady point, and its
values are the average of the plots history over the row's window: the families in
[FAM-DIM](../pproc/fam-dim.md), [FAM-ACOEF](../pproc/fam-acoef.md) and
[FAM-RCOEF](../pproc/fam-rcoef.md), the groups in [group files](../pproc/group-files.md#group-files).
The 0.57.0 file `polars/P<sim>_<name>_uns_avg.csv` is retired in 0.58.0, see
[the polar files by family and by group](../upgrading.md#polar-files-by-family-and-by-group). The
averaging window is on [the averaging window](the-averaging-window.md).

<a id="the-merged-polar"></a>

### The merged polar

`[products] merged_polar = true` writes `polars/P<sim>_<name>_merge.csv` beside the polar, for
a reader that wants one flat table.

- **Its rows are the polar's rows, in the polar's order,** and the polar's columns come first
  with their values unchanged.
- **A rotor row joins a polar row by the run both came from,** never by a flight condition: a
  simulation that sweeps `ALPHA` at one `J` holds several rows of that `J`.
- **Each rotor table adds the columns the polar does not hold,** including `J_<alias>`, after
  `ROTOR`, which names the rotors that have a row on that row, joined by `+`. A row with no
  row of a rotor reads `NA` in that rotor's columns and is named under `skipped`.
- **`[products.rotate_columns]` adds an angle of the row's `ROTATE`,** last, in degrees: each
  column name takes `"<alias>:<AXIS>"`, matched on the record's `ALIAS` and `AXIS` exactly, and
  two records of one alias and axis add up, as the rotations do. A simulation with no matrix row
  states nothing either way, so the column reads `NA` and is named under `skipped`. Without
  `merged_polar = true` the table writes nothing and is named there. A rotation the row does not state is not turned, so
  its angle is 0, and the column is named under `skipped`. A column the table already holds is
  left as it is and named there too.
- **A rotor table whose rows do not each name one run is not joined:** its columns read `NA`
  and the table is named under `skipped`.
- **A simulation with no unsteady polar writes no merged polar,** and says so under `skipped`.

**Why the native export is not the source.** It states the **last time step
only**, which on an oscillating rotor is one instant of a cycle. It still ships,
as a health check.

**Why the columns are not renamed.** Nothing in this package knows which plot
label carries which coefficient, and a label invented by the package does not
fail loudly -- it writes `NA` down a whole column.

**The `[names]` dictionary.** A downstream tool may read other names, so
the pproc may state a dictionary, from a plot column AS THE EXPORT PRINTS IT to
the name the reader wants:

```toml
[names]
CL_MRP_TOTAL = "CL_TOTAL"
FX_HUB_PUSHER = "FX_PUSHER"
```

- It renames the plotted columns of the reduction tables under `reductions/`
  (`phase_locked` and `per_revolution`). The plots table
  `time_history/<point>_plots.csv` stays as the export prints it, because it is the
  source the others are read from; the columns of the family and group files under
  `polars/` are fixed by [the output catalogue](../pproc/index.md) and are not renamed.
- Undeclared, every name passes through exactly as printed.
- The axes and the `[equations]` read the export's names; the dictionary is
  applied last, to the heading alone.
- **The whole dictionary applies or none of it does.** An entry naming a column
  no plot of the point prints, or giving a column a name the table ALREADY
  carries, leaves every column under the export's name and is said in
  `products.json` (`reductions/<file>#names`, `probes/<point>#names`) and as a
  warning. It never becomes a column of `NA`.
- **`CL` is taken.** The unsteady polar carries the native export's last-step
  `CL`, `CDi`, `CDo`, `Cx` and the rest in its setup content, as a health
  check, so a plot column cannot be renamed to one of those; `CL_TOTAL` can.
- Two entries giving one name, or a name that is not one word, are refused when
  the pproc is read.

---
