## The disc maps

!!! note "Current behaviour"
    The sectional load by radius and azimuth over the disc, from the
    sections the post already wrote.

`sections/<point>_disc_<ROTOR>_<QUANTITY>.csv`, one per rotor and sectional
load quantity (`Fx`, `Fz`, `Moment` on today's export) of a rotor point that
has sections. Where the harmonics fit a load's content around the disc, the
disc map is the load itself, sample by sample, so it can be drawn as a polar
map in the tool of the user's choice. No figure is drawn: the table is the
product.

**It is read from the WRITTEN sections**, as the harmonics are, and `AZIMUTH_DEG`
is the table's own or placed by `pyflightstream.post.axes`: no azimuth is computed again here. The samples are the same:

- a `qsteady_rotor` WHEEL point: every blade at every clocking of
  `sections/<point>_sections.csv`, `SAMPLE` being the `CLOCKING`;
- an `unsteady_rotor` point: every blade at every step of the last complete
  revolution of that rotor in `series/<point>_sections_series.csv`, `SAMPLE`
  being the `STEP`.

**The rows.** One row is one blade station at one sample: `POL` and the
condition columns of every table of the post, then

| Column | Meaning |
|---|---|
| `ROTOR`, `QUANTITY` | the rotor's alias and the sectional load column the file maps |
| `SAMPLE` | the clocking of a wheel, the step of an unsteady point |
| `BLADE` | which blade of the rotor, from 1, in the order of its `BLADE_FAMILIES` |
| `AZIMUTH_DEG` | where THAT blade is at that sample, in `[0, 360)`: the table's own azimuth of the block (a table that states blade one's is placed by `pyflightstream.post.axes`) |
| `STATION_R_M` | the station's radius, `|Offset|`, in metres |
| `R_OVER_R` | the radius over the rotor's radius (half its diameter), or `NA` where the diameter is not known |
| `VALUE` | the sectional load of that station at that sample, as the export states it |

Rows run by `AZIMUTH_DEG`, then `STATION_R_M`, so the file reads as a polar
grid. A wheel of `N` blades at `k` clockings holds `N k` azimuths and one row
per station at each; a value the export does not state is `NA`.

**What is not mapped.** A rotor with no block that is one of its blades at a
stated azimuth has no file, and is named under
`sections/<point>_disc_#rotor=<ALIAS>` in the post's skips and warned in
`post.log`; so is a rotor of an unsteady point with no complete revolution,
and a point with no readable table, sections series or export window (named
under `sections/<point>_disc_`). The other products are written.

**The manifest.** `products.json` registers each file with `kind` `disc_map`,
`source` `wheel clockings` or `unsteady last revolution`, `samples` (the blade
samples of that rotor), `rotor` and `quantity`; a wheel's entry adds
`clockings`, an unsteady point's `revolution` and `steps_per_revolution`.

---
