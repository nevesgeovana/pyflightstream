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
