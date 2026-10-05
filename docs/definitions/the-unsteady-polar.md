## The unsteady POLAR

- The POLAR of an unsteady point is the **plots history, time-averaged** over the
  window, and it does **not** read the native coefficient export.
- **Its columns are the plot variables under the names the export prints them.**
  It does not carry the steady polar's fixed 24 coefficient columns.
- The source plots table normalizes coefficient plots to the free stream by
  `(Vref / Vinf)^2`, including `CDP_*` and `CDV_*` on 26.125. Their names stay
  distinct from `CDI_*` and `CDO_*`; dimensional forces and moments are unchanged.
- The flight-condition and reference-length columns are still added, because
  those come from the workspace and not from the export.

- **The file is `polars/P<sim>_<name>_uns_avg.csv`**, one per simulation and one
  row per point. Every file under `post/` comes from a sweep, so the name says
  what the file IS, the average of the unsteady history, and carries the `P`
  every per-point product carries. It was `<sim>_<name>_unsteady.csv` in 0.23.0.
- **Each row opens with `POL`, then `FIRST_STEP`, `LAST_STEP`, `STEPS`**, the
  window THAT point was averaged over, so the file says on its own that it is an
  average and over what. The condition block follows, then `XMOM`, `YMOM`, `ZMOM`,
  because the plots carry moments and a moment states nothing without its point.
- **The super file's content is ADDED to this table**, after the plot columns:
  the matrix row's cells, the record's scalars, each rotor's speed and diameter
  (`RPM_<alias>` and, right after it, `DIAMETER_<alias>`), the solver
  flags. The super file is what the polar does not have; for an unsteady point it
  is not a second file. Its `POL` cell is the row's first column and is not
  written a second time.
- **The last column is `MESH_FACES`**, after the super file's
  content: the face count of the point's geometry as its inventory states it,
  or `NA` ([the mesh face count](the-mesh-face-count-since-0340.md#the-mesh-face-count-since-0340)).
- **The axis coefficients follow the plot columns**, the eighteen of the steady
  polar under its own names, in the order `CDW .. CNW25`, `CDS .. CNS25`,
  `CDB .. CNB25`, each suffixed with its plot group's WHOLE name
  (`CLW_MRP_TOTAL`), one group or several. Their source is
  the plots of the GLOBAL `MRP` frame: the six components `FX, FY, FZ, MX, MY,
  MZ` of a plot group the pproc declares with `frame = "MRP"`, in Newtons and
  Newton metres, averaged over the row's window like every other column, divided
  by `1/2 RHO VINF^2 SREF` (and by `CREF` for the moments) of THAT row, and
  turned as [the axes of a steady polar](the-axes-of-a-steady-polar.md#the-axes-of-a-steady-polar) are. A
  rotor's own frame is never the source: its axes are not the geometry's. A
  second global-frame group adds its own eighteen and renames none.
- **A pproc that plots those six for no global-frame group gets one added by
  the run**, `MRP_TOTAL`, over every boundary, where the run has an `MRP` frame.
  A pproc that already plots them is left as it is, to the byte. A recorded run without such plots has no axes block, and `products.json` says
  so under `polars/<file>#axes`; the block is never a column of `NA`.

**Why the native export is not the source.** It states the **last time step
only**, which on an oscillating rotor is one instant of a cycle. It still ships,
as a health check.

**Why the columns are not renamed.** Nothing in this package knows which plot
label carries which coefficient, and a label invented by the package does not
fail loudly -- it writes `NA` down a whole column.

**The `[names]` dictionary (0.24.0).** A downstream tool may read other names, so
the pproc may state a dictionary, from a plot column AS THE EXPORT PRINTS IT to
the name the reader wants:

```toml
[names]
CL_MRP_TOTAL = "CL_TOTAL"
FX_HUB_PUSHER = "FX_PUSHER"
```

- It renames columns of the unsteady polar and of the averaged reductions
  (`time_average`, and the passage series). The plots table
  `probes/<point>_plots.csv` stays as the export prints it, because it is the
  source the others are read from; the per-blade and azimuthal tables carry
  columns that are no longer the export's own names and are not renamed.
- Undeclared, every name passes through exactly as printed.
- The axes and the `[equations]` read the export's names; the dictionary is
  applied last, to the heading alone.
- **The whole dictionary applies or none of it does.** An entry naming a column
  no plot of the point prints, or giving a column a name the table ALREADY
  carries, leaves every column under the export's name and is said in
  `products.json` (`polars/<file>#names`, `probes/<point>#names`) and as a
  warning. It never becomes a column of `NA`.
- **`CL` is taken.** The unsteady polar carries the native export's last-step
  `CL`, `CDi`, `CDo`, `Cx` and the rest in its setup content, as a health
  check, so a plot column cannot be renamed to one of those; `CL_TOTAL` can.
- Two entries giving one name, or a name that is not one word, are refused when
  the pproc is read.

---
