## The per-station harmonics

!!! note "Current behaviour"
    The 0P, 1P and 2P content of every blade station's load around the
    disc, from the sections the post already wrote.

`sections/<point>_harmonics.csv`, one per rotor point that has samples at
several azimuths. For each rotor, each blade station and each sectional load
quantity of the sections export, the least-squares fit

    load(psi) = H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)

over every sample of that station, `psi` being the sample's blade azimuth in
degrees.

**It is read from the WRITTEN sections.** The samples are the rows a user
holds, read back, and `psi` is the table's own `AZIMUTH`: no azimuth is
computed again. Which rows:

- a `qsteady_rotor` WHEEL point: every blade at every clocking of
  `sections/<point>_sections.csv` (`CLOCKING`), whose `AZIMUTH` is each
  block's own blade at its clocking
  ([The quasi-steady rotor](the-quasi-steady-rotor.md#the-quasi-steady-rotor)). The wheel's premise is
  identical blades, so blade `n` at clocking `i` is one more azimuth of the
  same station: a wheel of `N` blades at `k` clockings gives `N k` samples,
  `N k` distinct azimuths `360 / (N k)` apart. A sector point has one azimuth
  and no file.
- an `unsteady_rotor` point: every blade at every step of the LAST COMPLETE
  REVOLUTION of that rotor in `series/<point>_sections_series.csv`, the
  per-step sectional exports. Revolution `m` is steps
  `first + (m - 1) N` to `first + m N - 1`, counted from the series' first
  stamped step as [`per_revolution`](per_revolution.md#per_revolution) counts from its first
  row, with `N` the rotor's own `steps_per_revolution` from the run record
  rounded to a whole step; the steps after the last complete revolution are
  not read. The series states each block's OWN blade's azimuth
  (blade `n` of the rotor's `B` at blade one's plus `(n - 1) 360 / B`, the
  blades placed ahead of blade one whatever the sense of rotation, as the
  per-blade table places them,
  `pyflightstream.post.axes.placed_blade_azimuth_deg`), and the fit reads it
  as stated. See [the harmonics migration](../migrating-to-0.31.0.md) for older series.

A sample is a BLOCK of one blade: the consecutive rows of one clocking or
step whose `FAMILY` names families of one blade of the rotor, blade `n` being
the `n`-th entry of its `families_blades` (expanded through the aliases). A
block of several blades, or of a family no blade names, is not a sample.

**The stations.** Station `j` is the `j`-th row of every blade block of the
rotor, at the radius `STATION_R_M = |Offset|` of the first sample, read as the
radius of a distribution cut along the blade from the hub, as the validity
columns read it. Every sample must hold its station within `1e-6` of the
first sample's largest radius: a station where one does not is left out and
named in `products.json` `skipped` under
`sections/<point>_harmonics.csv#rotor=<ALIAS>#station=<j>`, and a rotor whose
blocks hold different numbers of stations, or which has no block of one blade
at a stated azimuth, under `...#rotor=<ALIAS>`; each is a WARNING line in
`post.log` too, and the other stations are written.

**The quantities.** Every numeric load column of the export after the
condition: `Fx`, `Fz` and `Moment` of today's sectional loads export, each in
the export's own axes and units (N/m, N m/m). The station's place (`Offset`,
`Chord`, `X_QC`, `Z_QC`) and the columns the post adds (`CLOCKING`, `K_1P`,
the validity and the integrated strips) are not fitted. A harmonic of an
in-plane quantity describes the blade's load only where the export's axes
turn with the blade, as they do for a distribution cut in the blade's own
frame.

**The columns.** `POL`, the condition (`CONTEXT_COLUMNS`, the sections
table's own values), then

| column | what it is |
|---|---|
| `ROTOR` | the rotor's alias |
| `QUANTITY` | the export's column fitted |
| `STATION_R_M` | the station's radius, m |
| `R_OVER_R` | `STATION_R_M` over half the rotor block's `diameter_m`: the wheel's record's, and on an unsteady point the reference's the row names today; `NA` where no reference can be asked |
| `SAMPLES` | the samples fitted |
| `DISTINCT_AZIMUTHS` | how many distinct azimuths they hold, two within `1e-6` deg (360 and 0 included) being one |
| `H0` | the mean, 0P |
| `H1_AMP`, `H1_PHASE_DEG` | `A1` and `PHI1` |
| `H2_AMP`, `H2_PHASE_DEG` | `A2` and `PHI2` |
| `RESIDUAL_RMS` | the root mean square of the samples less the fit made |

Amplitudes carry the quantity's unit. One row per rotor, quantity and
station, in that order.

**The phase convention.** `PHI_k` is in degrees in `[0, 360)`, in the
convention of the table's `AZIMUTH` (so on a left-hand rotor too): the `kP`
term peaks where `k psi = PHI_k`. The 1P term peaks at the azimuth `PHI1`;
the 2P term at the two azimuths `PHI2 / 2` and `PHI2 / 2 + 180`. The fit is
`H0 + a_k cos(k psi) + b_k sin(k psi)` by `numpy.linalg.lstsq`, with
`A_k = sqrt(a_k^2 + b_k^2)` and `PHI_k = atan2(b_k, a_k)`.

**Too few azimuths is `NA`, said once.** A fit up to `kP` has `2k + 1`
unknowns, so 1P needs 3 distinct azimuths and 2P needs 5. A station with
fewer carries `NA` in that harmonic's amplitude and phase, and the fit is made
without it (`H0` alone below 3); `post.log` carries ONE WARNING line per rotor
and harmonic that is `NA` anywhere, naming how many rows and the fewest
azimuths:

```
WARNING point=<point> product=sections/<point>_harmonics.csv: rotor 'PROP': the 2P harmonic is NA in 9 row(s), whose stations hold as few as 4 distinct azimuth(s); a 2P fit needs 5
```

A wheel of 2 blades at 2 clockings (4 azimuths) has a 1P fit and no 2P. Nothing
blocks: the table is written.

**Not written, and said.** An unsteady rotor whose record states no
`steps_per_revolution`, or whose series holds no complete revolution, is named
under `sections/<point>_harmonics.csv#rotor=<ALIAS>`; where no station of any
rotor could be fitted the file is not written and `products.json` names it.
An unsteady rotor point that cuts sections (its record states a sections
layout) and has no sections series (its row exported no per-step sectional
loads, or the series was not written), no export window, or no rotor its
record states is named under `sections/<point>_harmonics.csv`, with
a WARNING line in `post.log`.

**The manifest.** `products.json` registers the file with `kind`
`harmonics`, `source` `wheel clockings` or `unsteady last revolution`,
`samples` (the blade samples fitted, all rotors) and `samples_by_rotor`; a
wheel's entry adds `clockings`, an unsteady point's `revolution` (the first
and last step fitted, per rotor) and `steps_per_revolution`.

---
