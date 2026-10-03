## `per_blade`

!!! note "The output file"
    `probes/<point>_per_blade_<ALIAS>.csv` is one row per blade with its start
    and end azimuth, as defined here. See [the migration record](../migrating-to-0.24.0.md)
    for the shape of historical files.

The per-blade table averages each blade over the LAST part of the run, the
row's averaging window. The blades sit at different azimuths, and that is not a
reason for different windows: a column states where each blade starts and ends.

**ONE window per rotor, shared by every blade of that rotor.** One row per blade,
and each row carries
the **start and end azimuth of that blade** over that one shared window.

**Why one window and not one per blade.** Averaging each blade over its own
passage puts each blade in a different part of the history, so any difference
between two blades mixes a real azimuthal difference with a difference in WHEN
each was sampled -- and nothing in the file says which is which. With one window,
the azimuth columns carry the difference explicitly and the reader can see it.

**The window comes from `LAST_REVS_AVG` or `LAST_ITERS_AVG` on the matrix row.**
On a multi-rotor run, each blade follows its own rotor's clock:
`LAST_REVS_AVG` counts that rotor's own revolutions. Rotors turning at different
rates can therefore have different step windows for the same requested number
of revolutions. Every blade of one rotor shares that rotor's window;
`LAST_ITERS_AVG` uses the stated step count.

Averaging from step one mixes the transient with the answer.

**The rows.** Each row leads with `POL`, `REDUCTION`, `ROTOR`, `BLADE`, `FAMILY`, the
window (`FIRST_STEP`, `LAST_STEP`, `STEPS`), `AZIMUTH_START`, `AZIMUTH_END`,
then the condition block and the moment point.

- **A blade's columns are the plots named for its family.** A plot is
  `<parameter>_<group>` and a group cut per blade is named for the blade's
  family, so blade one's are `CL_MRP_Blade1`, `FX_LOCAL_Blade1`. The row carries
  them with the family removed, `CL_MRP`, `FX_LOCAL`, so two blades line up
  under one heading. A pproc gets them with `families = "each"` or
  `frame = "LOCAL_AXIS"` over the rotor.
- **The azimuths are where that blade IS at the window's first and last step**,
  by the formula of the sections table: blade one's datum, plus the blade's
  position times `360 / blades`, plus the rotor's sense times the step times
  `360 / steps_per_revolution`, wrapped. `blades` is the ROTOR's count, so a
  periodic sector carrying two blades of four spaces them a quarter turn apart.
  Without the rotor's clock they read `NA`; the averages are written all the same.
- **Which families are a rotor's blades** is the `families_blades` of its block
  in the reference artifact; the run also records them. A row
  that states its rotor with flat keys and cites no block has no per-blade
  table, and `products.json` says why.

---
