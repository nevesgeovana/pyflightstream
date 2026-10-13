## Changed

- Small dimensional CSV values retain significant digits where five decimal
  places would lose precision. This covers viscosity, time (including the
  native plots clock), positions, sectional loads, velocities, boundary-layer
  lengths, and dimensional rotor and group columns. Coefficients keep five
  decimal places. Readers must accept scientific notation in physical columns. (no requirement: PFS-2105.041 fix)
- A probe history containing `NA` or blank cells keeps its other values and
  produces a probes table. Previously one such cell could skip the whole table. (no requirement: PFS-2105.016 fix)
- Malformed recorded reduction windows are listed under that reduction's
  `skipped` key instead of aborting the post. Each window must contain two
  bounds, the first and last solver steps. (no requirement: PFS-2095.016 fix)
- Truncated VTK vector blocks raise `IncompleteOutputError`; malformed vector
  rows and non-UTF-8 frames raise `MalformedOutputError`, instead of raw Python
  indexing, conversion or decoding exceptions. (no requirement: PFS-2095.020 fix)
- A failing post keeps its original exception if a log write, log close or
  interrupted-manifest write also fails, including when the log reader sees
  partial JSON from that failed rewrite. The secondary failure is attached
  as an exception note. A log failure after a successful post still raises. (no requirement: PFS-2086.002 fix)
- A rerun whose export now declares zero sections or zero probe points retires
  the previous table under both archive settings. Under `--force-overwrite` it
  removes the old file and records the skipped product. (no requirement: PFS-2100.004 fix)
- Harmonics now require angular coverage as well as distinct sample counts.
  See [the fit definition](definitions/the-per-station-harmonics.md) for the
  180-degree maximum-gap rule, omitted terms and `HarmonicFit.reason`. (no requirement: PFS-2086.007 fix)
