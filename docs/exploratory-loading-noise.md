# Exploratory loading-noise products

Add this table to a quasi-steady wheel's pproc, then run ordinary workspace post:

```toml
[noise]
exploratory = true
observers_m = [[10.0, 2.0, 2.0]]
hub_velocity_m_s = [0.0, 0.0, 0.0]
sound_speed_m_s = 340.0
samples_per_revolution = 360
```

FR-2115 permits these exploratory post products only when explicitly requested.
The opt-in is required. The current reconstruction supports a wheel about +X,
with azimuth zero along +Z. It combines the recorded per-blade forces and hub
moments at the wheel's clockings, fits their azimuthal variation, and applies
the compact loading term of Formulation 1A for one revolution. The output
`noise/<point>_observer_<index>.csv` contains time in seconds and pressure in Pa.
The manifest labels it `exploratory, not validated` and states that thickness
noise is absent. It is not a prediction validated against a licensed solver run.
The post stage also writes `noise_report.json` beside `products.json`, indexing
the loading signals, their source runs and observer positions from that manifest.

All positions and velocities are in the medium-rest frame. State hub velocity
explicitly; `observer_velocity_m_s` defaults to zero. Optional `orders` limits
the harmonic fit. Optional positive `axial_radius_m` and `inplane_radius_m`
override the load centroids when the corresponding mean force cannot determine
them. Incomplete blade loads, unsupported axes and non-subsonic source motion
are refused with a named skipped product.

## Harmonics and reference comparisons

Every requested observer signal also gets `<point>_observer_<index>_harmonics.csv`.
Its shaft harmonics are `m * blades`, for `m = 1..gutin_orders` (default 4).
`RMS_PA` comes from the discrete Fourier transform of the written revolution;
`GUTIN_RMS_PA` uses each blade's mean axial and tangential force and the same
loading radii used by the reconstruction. `RATIO` is measured RMS divided by
Gutin RMS, or `NA` for a zero denominator. Increase `samples_per_revolution` if
the requested harmonics reach Nyquist; the table is otherwise a named skip.
The sample clocks and acoustic values retain floating-point precision in CSV.

Gutin assumes a hub at rest in the medium. A nonzero `hub_velocity_m_s` leaves
the RMS column available, writes `NA` in the Gutin columns and records the reason
in both the manifest and `post.log`. No new validation claim is implied.

Within `[noise]`, optional `reference = ["measurements/observer.csv"]` lists one
workspace-relative file or empty string per observer. Each CSV needs `time_s`
and `pressure_pa` in seconds and Pa; the uppercase native acoustics headers are
also accepted. The native `acoustics/<stem>_<NN>_<slug>_pressure.csv` is suitable.
An ambiguous or unsupported column name is refused rather than guessed.
Paths must remain inside the workspace.

The comparison file contains `rms_ratio`, `level_difference_db`, `correlation`,
`normalized_rms_difference` and `mean_ratio`, after periodic linear resampling of
the reference's last complete revolution onto prediction times. A shorter record
is a named skip. Correlation depends on the two clocks' origins: no automatic
phase alignment is performed. Both signals must have nonconstant fluctuations.

## Dedicated command

```text
pyfs-matrix noise matrix --sims 6001 --workspace study --overwrite
```

This uses the same partial post as `post --sims`: every product of the selected
simulations is rebuilt. Other simulations remain as the previous post left them.
Existing products require `--overwrite`. A selected matrix pproc must declare
`[noise]`. The command lists the noise files, the largest finite Gutin ratio in
each observer's harmonic table, and every noise skip. `noise_report.json`
indexes signals, harmonics, comparisons and skips, including an all-skipped run.
The recorded synthetic wheel test `test_p0440_noise_command_posts_selected_simulations`
executes this command without launching a solver.
