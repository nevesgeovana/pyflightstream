## Added

- EXPLORATORY, no threshold and no gate: `pyflightstream.post.qsteady_noise` models a rotor's loading noise from its blade loads, each blade two compact point forces propagated by the loading term of Farassat's Formulation 1A with its near field, with no thickness term; a library, not wired into the post stage (FR-300).
- The load of one blade against azimuth is fitted as a Fourier series from blade samples at known azimuths, the clockings of a quasi-steady wheel, with the centroid radii from the mean moments (`reconstruct_blade_load`, `fit_azimuthal_series`, `rotating_components`) (FR-301).
- The observer-time retardation of a subsonic source, for an observer at rest or moving with the hub (`emission_times`) (FR-302).
- Gutin's closed-form far-field harmonic of a steady rotor, which the time-domain model is tested against (`gutin_harmonic_rms`) (FR-303).
- The measures that compare a predicted pressure record with a reference, and report RPT-099, route A against the unsteady_rotor acoustic signals of licensed round 3 (`compare_signals`) (FR-304).
