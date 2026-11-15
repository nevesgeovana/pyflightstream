## Harmonics: per-station 0P, 1P and 2P

<a id="harmonics"></a>

`reductions/<point>_harmonics.csv`, one per rotor point that has samples at several
blade azimuths: an unsteady-rotor point with per-step sectional exports (the last
complete revolution) and a quasi-steady wheel (every blade at every clocking).

| Columns | Content |
| --- | --- |
| the run block | [the run block](../definitions/the-run-block.md#the-run-block) |
| `ROTOR_ID`, `ROTOR` | the declared id and the alias of the rotor |
| `QUANTITY` | the sectional load: `Fx`, `Fz` or `Moment` |
| `STATION_R_M`, `R_OVER_R` | the station's radius in m and as a fraction of the rotor radius |
| `SAMPLES`, `DISTINCT_AZIMUTHS` | the blade samples fitted and the distinct azimuths among them |
| `H0` | the mean of the quantity at the station, in the quantity's unit |
| `H1_AMP`, `H1_PHASE_DEG`, `H2_AMP`, `H2_PHASE_DEG` | the 1P and 2P amplitudes (the quantity's unit) and phases (degrees) of the least-squares fit |
| `RESIDUAL_RMS` | the root mean square of the fit's residual, in the quantity's unit |

A harmonic short of distinct azimuths (1P needs 3, 2P needs 5) is `NA` and said once in
`post.log`. The definition of record is
[the per-station harmonics](../definitions/the-per-station-harmonics.md#the-per-station-harmonics).
