## The acoustic signals product

A point whose record lists acoustic signals gets, under
`acoustics/` of its products, the tables below, read from the file the solver's
`EXPORT_ACOUSTIC_SIGNALS` wrote. The export holds, per observer, a block: a line
`Observer: <name>`, a line `Position: x,y,z` (Fortran-style numbers such as
`.00,10.0,.00`), a line `Columns: Observer time (sec), PL (Pa), PT (Pa), PO (Pa)`
and one row per sample (measured on build 26.124, probe A1). The manual pages of
the toolbox (SRC-003 pp.374 and 380) do not define the three pressure columns;
the probe shows `PO = PL + PT` in every row, and the package reads `PO` as the
overall pressure and calls PL the loading part and PT the thickness part, which is
the customary split and not a vendor statement. The unit of the position is not in
the file and is read as metres.

`<n>` is the observer's place in the export, from 01, and `<observer>` its name
made safe for a file name.

- **Pressure against time**, `<point>_<n>_<observer>_pressure.csv`: `TIME_S`,
  `PRESSURE_PA`, the `PO` column.
- **Spectrum**, `<point>_<n>_<observer>_spectrum.csv`, with the columns
  `FREQUENCY_HZ`, `AMPLITUDE_PA` and `LEVEL_DB`: the one-sided amplitude
  spectrum of `PO` over the observer time, the real FFT of the samples as they are
  (no window, mean kept). For `N` samples at the constant step `dt`, the sampling
  rate is `1/dt` and the bin width `1/(N dt)`; bin 0 is `|X0|/N` (the mean), a
  bin below Nyquist is `2|Xk|/N`, the Nyquist bin of an even `N` is `|Xk|/N`, so
  a cosine of amplitude `A` on a bin reads `A`. `LEVEL_DB` is
  `20 log10((A/sqrt(2)) / 20e-6 Pa)`, `NA` for bin 0 and for a zero amplitude. A
  step that is not constant (relative spread above 1e-3) gives no spectrum.
- **OASPL**, `OASPL_DB` of `<point>_acoustics_summary.csv`:
  `20 log10(p_rms / 20e-6 Pa)`, `p_rms` the root mean square of `PO` about its
  mean over the whole record; `NA` for a silent record. The summary has one row
  per observer, with the columns `OBSERVER`, `X_M`, `Y_M`, `Z_M` (the position),
  `SAMPLES`, `TIME_START_S`, `TIME_END_S`, `SAMPLE_RATE_HZ`, `BIN_HZ` (the bin
  width of the spectrum) and `OASPL_DB`; the sampling rate and the bin width are
  `NA` where the step is not constant.
- **Blade-passage harmonics**, `<point>_acoustics_bpf.csv`, with the columns
  `ROTOR`, `OBSERVER`, `HARMONIC`, `FREQUENCY_HZ`, `BIN_HZ`, `AMPLITUDE_PA` and
  `LEVEL_DB`, one row per observer, rotor and harmonic: for each rotor of the
  record with its blade count `B` and speed `rpm`, harmonic `n` (1 to 4) is at
  `n B |rpm| / 60` hertz (the sign of the speed only states the sense of rotation), read at the nearest bin of the observer's spectrum, with
  the bin frequency, the amplitude and the level. `NA` when the record states no
  blades or speed, above the Nyquist frequency, or below one bin width; each `NA`
  has a line in `post.log`.
- **Directivity**, `<point>_acoustics_directivity.csv`, written only when at
  least four observers are coplanar and lie on one circle (each within 1e-3 of the
  radius): per observer the angle about the circle's centre, measured from the
  first observer and increasing toward the second, in `[0, 360)` degrees, the
  radius and the OASPL, as the columns `OBSERVER`, `ANGLE_DEG`, `RADIUS_M` and
  `OASPL_DB`. Fewer than four observers, or any off the circle, is not
  an arc and writes no file.

**The manifest and the skips.** `products.json` registers each of these files
with `kind` `acoustics`, `source` `acoustic_signals` and `observers`, the number
of observers of the export. The export is the file the record lists under
`acoustic_signals`; a record that lists none asks for no acoustics, and nothing
is said. An export the post cannot read is named under `acoustics` in the
post's skips and warned in `post.log`, and the other products are written.

**The section is not a table.** The VTK files of an `ACOUSTIC_SECTION`, in
`<point>_acoustic_section/`, are the solver's own and are recorded and hashed
as outputs of the point ([acoustic signals](../acoustic-emission.md#what-the-run-writes));
the post reads none of them, and no table is derived from them.
