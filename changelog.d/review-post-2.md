## Changed

- Small dimensional CSV values retain significant digits where five decimal
  places would lose precision. This covers viscosity, time (including the
  native plots clock), positions, sectional loads, velocities, boundary-layer
  lengths, and dimensional rotor and group columns. Coefficients keep five
  decimal places. Readers must accept scientific notation in physical columns.
- A probe history containing `NA` or blank cells keeps its other values and
  produces a probes table. Previously one such cell could skip the whole table.
- Malformed recorded reduction windows are listed under that reduction's
  `skipped` key instead of aborting the post. Each window must contain two
  bounds, the first and last solver steps.
- Truncated VTK vector blocks raise `IncompleteOutputError`; malformed vector
  rows and non-UTF-8 frames raise `MalformedOutputError`, instead of raw Python
  indexing, conversion or decoding exceptions.
- A failing post keeps its original exception if a log write, log close or
  interrupted-manifest write also fails, including when the log reader sees
  partial JSON from that failed rewrite. The secondary failure is attached
  as an exception note. A log failure after a successful post still raises.
- A rerun whose export now declares zero sections or zero probe points retires
  the previous table under both archive settings. Under `--force-overwrite` it
  removes the old file and records the skipped product.
- Harmonics now require angular coverage as well as distinct sample counts.
  See [the fit definition](definitions/the-per-station-harmonics.md) for the
  180-degree maximum-gap rule, omitted terms and `HarmonicFit.reason`.


- [Migrating to 0.39.0](migrating-to-0.39.0.md)
- [Migrating to 0.38.0](migrating-to-0.38.0.md)
- [Migrating to 0.37.0](migrating-to-0.37.0.md)
- [Migrating to 0.36.0](migrating-to-0.36.0.md)
- [Migrating to 0.35.1](migrating-to-0.35.1.md)
- [Migrating to 0.35.0](migrating-to-0.35.0.md)
- [Migrating to 0.34.0](migrating-to-0.34.0.md)
- [Migrating to 0.33.1](migrating-to-0.33.1.md)
- [Migrating to 0.33.0](migrating-to-0.33.0.md)
- [Migrating to 0.32.0](migrating-to-0.32.0.md)
- [Migrating to 0.31.0](migrating-to-0.31.0.md)
- [Migrating to 0.30.0](migrating-to-0.30.0.md)
- [Migrating to 0.29.0](migrating-to-0.29.0.md)
- [Migrating to 0.28.0](migrating-to-0.28.0.md)
- [Migrating to 0.27.0](migrating-to-0.27.0.md)
- [Migrating to 0.26.0](migrating-to-0.26.0.md)
- [Migrating to 0.25.0](migrating-to-0.25.0.md)
- [Migrating to 0.24.0](migrating-to-0.24.0.md)
- [Migrating to 0.23.0](migrating-to-0.23.0.md)
- [Migrating to 0.22.0](migrating-to-0.22.0.md)
- [Migrating to 0.21.0](migrating-to-0.21.0.md)
- [Migrating to 0.19.0](migrating-to-0.19.0.md)
- [Migrating to 0.18.0](migrating-to-0.18.0.md)
- [Migrating to 0.17.0](migrating-to-0.17.0.md)
- [Migrating to 0.16.0](migrating-to-0.16.0.md)
- [Migrating to 0.15.0](migrating-to-0.15.0.md)
- [Migrating to 0.14.0](migrating-to-0.14.0.md)
- [Migrating to 0.13.0](migrating-to-0.13.0.md)
- [Migrating to 0.11.0](migrating-to-0.11.0.md)
- [Migrating to 0.10.1](migrating-to-0.10.1.md)
- [Migrating to 0.10.0](migrating-to-0.10.0.md)
- [Migrating to 0.8.1](migrating-to-0.8.1.md)
- [Migrating to 0.5.0](migrating-to-0.5.0.md)
