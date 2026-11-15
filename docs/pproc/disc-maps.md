## Disc maps

<a id="disc-maps"></a>

`reductions/<point>_disc_<ROTOR>_<QUANTITY>.csv`, one per rotor and sectional load
quantity of an unsteady-rotor point or a quasi-steady wheel: every blade at every
sampled azimuth, mapped over the disc.

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block) |
| `ROTOR_ID`, `ROTOR` | the declared id and the alias of the rotor |
| `QUANTITY` | the sectional load mapped |
| `SAMPLE`, `BLADE` | the sample (a clocking, or a step of the last revolution) and the blade |
| `AZIMUTH_DEG` | where the blade is, in degrees |
| `STATION_R_M`, `R_OVER_R` | the station's radius in m and as a fraction of the rotor radius |
| `VALUE` | the value of the quantity at that blade, station and azimuth, in its unit |

A rotor with no blade at a stated azimuth is named under
`reductions/<point>_disc_` in the post's skips and warned. The definition of record is
[the disc maps](../definitions/the-disc-maps.md#the-disc-maps).
