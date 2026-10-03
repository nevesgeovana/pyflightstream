## `per_revolution`

!!! note "Current behaviour"
    The one product that answers "has the rotor's load settled from one
    revolution to the next?" from the history the post already wrote.

One row per COMPLETE revolution of one rotor, each column of the plots table
averaged over that revolution, and from the second revolution on how far that
mean moved from the previous revolution's.

**It is read from the WRITTEN plots table.** `probes/<point>_plots.csv` is read
back by `plots_table_series`, as every reduction is, and the raw export is not
read again: a reduction is of the file a user holds and can be recomputed from
it.

**Which files.** A point of an `unsteady_rotor` row that names its rotors gets
`probes/<point>_per_revolution_<ALIAS>.csv`, one per rotor, each cut on THAT
rotor's own `steps_per_revolution` from the run record's reductions plan (a
rotor turning at another speed has another revolution). A row that states its
clock flat and names no rotor by alias gets `probes/<point>_per_revolution.csv`,
its `ROTOR` `NA`. A steady point and a plain unsteady one have no revolution and
no file. The product is registered in `products.json` like the other
reductions, with `reduction` = `per_revolution`, its `windows` (one per
revolution) and its `rotor`.

**How the history is cut.** Revolution `k` is rows `(k-1) * N + 1` to `k * N` of
the table, counted from its first row, where `N` is the rotor's steps per
revolution rounded to a whole solver step, as the phase-locked reduction does.
A history that starts at step 1 cuts at steps 1 to `N`, `N+1` to `2N` and so
on. Each mean is the package's one average over that window, the one the time
average takes.

**A partial last revolution is EXCLUDED, and said.** The steps after the last
complete revolution are not averaged: their mean would be the mean of another
length of history under the same name. `products.json` states it under
`skipped`, keyed `probes/<point>_per_revolution_<ALIAS>.csv#partial`, and the
post log carries a WARNING line naming the point, the file, the complete
revolutions and the steps left over. A table with not one complete revolution
writes no file and says why under `skipped`, and a rotor whose record states no
steps per revolution (its speed or the solver time step was not resolved) is
named the same way.

**The columns.** `POL`, `REDUCTION` (`per_revolution`), `ROTOR`, `REVOLUTION`
(counted from one), `FIRST_STEP`, `LAST_STEP`, `STEPS` (the revolution's length),
the condition and reference block, `XMOM`, `YMOM`, `ZMOM`, then the mean of every
plotted column under the name the plots table carries (or the pproc's `[names]`
entry for it), then `<column>_DRIFT_PCT` for each of them. The plots table's
clock is not a plotted column and is not averaged.

**The drift** of a column at revolution `k >= 2` is

    (mean_k - mean_(k-1)) / |mean_(k-1)| * 100

in per cent: positive where the mean rose, whatever the sign of the quantity. It
is `NA` on the first revolution, and `NA` where the previous mean is exactly
zero, which has no relative change. `NA` is the package's one token for a value
that does not exist.

**The declared threshold.** The pproc may declare

```toml
[per_revolution]
drift_limit_pct = 1.0
```

`drift_limit_pct` is positive (zero and negative values are refused) and
defaults to 1 per cent where the table or the key is absent.

**The warning judges a load against its SCALE, not against itself**. A force or moment column is a plotted column whose parameter (the text
before the first underscore) is one of `FX`, `FY`, `FZ`, `MX`, `MY`, `MZ` or the
force coefficients `CL`, `CDI`, `CDO`, `CD`; the text after it is the column's
group. Its KIND is a force (`FX`, `FY`, `FZ`), a moment (`MX`, `MY`, `MZ`) or a
force coefficient (`CL`, `CDI`, `CDO`, `CD`), and the columns of one kind and
one group are the components of one load of one body in one frame. The SCALE of
a column at the last revolution `n` is the largest magnitude among the means at
revolution `n - 1` of the columns of its kind and group, so an in-plane force is
judged against the thrust and an in-plane moment against the torque. The column
warns when

    |mean_n - mean_(n-1)| > drift_limit_pct / 100 * scale

For the column that IS the largest of its group this is its drift in the table
exceeding the limit. A near-zero component (an in-plane force of a rotor in
uniform inflow) has a large relative drift that is noise and is not warned
about unless its change is large against the load it is a component of. A group
whose means at `n - 1` are all zero or not numbers, and a column whose own means
are not numbers, give no warning.

The WARNING line in `post.log` names the point, the rotor, the column, its
change in per cent of the scale, the scale and the column that sets it, the
change itself and the limit:

```
WARNING point=<point> product=probes/<point>_per_revolution_<ALIAS>.csv: rotor '<ALIAS>' column FX_MRP_TOTAL drifts +4.7619 per cent of its scale 10.5 (the magnitude of FX_MRP_TOTAL, the largest force mean of its group in the earlier revolution; a change of +0.5) between revolution 2 and revolution 3, over the drift limit of 1 per cent ([per_revolution] drift_limit_pct): the last revolution is still moving
```

The `<column>_DRIFT_PCT` columns of the table keep the relative drift defined
above; only the warning reads the scale. A probe or any other plotted column has
a drift and no warning. **The warning never blocks**: the table is written whether
or not the limit is exceeded, as nothing in the post blocks by default. Only a
history with at least two complete revolutions can drift. The table is read again
by `pyfs-matrix post`, so declaring or editing the limit needs no new run.

A frozen solve is judged like every other average: the default warns, and the
explicit refusal mode skips the table naming the reason.

---
