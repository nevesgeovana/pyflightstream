!!! requirement "FR-300 A rotor's loading noise from its blade loads, by a compact source model <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-QS-NOISE, section 2.6 part 5 of the 0.32.0 scope, EXPLORATORY by the owner's decision of 2026-09-29 (no threshold, no gate). Evidence: `tests/tier1_offline/test_p0320_f_qsteady_noise.py::test_a_point_force_at_rest_gives_the_exact_dipole_field_fr_300`, `::test_a_steady_force_in_uniform_motion_gives_the_convected_dipole_fr_300`, `::test_an_unloaded_moving_blade_is_silent_the_model_has_no_thickness_term_fr_300`.*

    Need: A quasi-steady rotor solve records no acoustic sources, so a user who wants its tonal noise needs it estimated from the loads the solve does give.

    Requirement: Each blade is replaced by two compact point forces turning with it, its axial force at the axial load's centroid radius and its in-plane force at the torque's centroid radius, each the negative of the load on the blade; the pressure at an observer is the loading term of Farassat's Formulation 1A for a compact source in a medium at rest (F. Farassat, NASA/TM-2007-214853, 2007; K. S. Brentner and F. Farassat, Progress in Aerospace Sciences 39, 2003), near-field terms kept, with no thickness term, so an unloaded moving blade is silent. The model is a library and is not called by the post stage.

    Solution (release 0.32.0): `pyflightstream.post.qsteady_noise`, `PointForce`, `loading_noise`, `RotorMotion`, `BladeLoad`, `rotor_point_forces`, `rotor_loading_noise`.

!!! requirement "FR-301 One blade's load against azimuth from a wheel's clockings <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-QS-NOISE, section 2.6 part 5 of the 0.32.0 scope (route A). Evidence: `tests/tier1_offline/test_p0320_f_qsteady_noise.py::test_a_series_is_recovered_from_its_samples_fr_301`, `::test_a_series_refuses_more_harmonics_than_its_samples_carry_fr_301`, `::test_a_wheel_s_clockings_give_back_the_blade_load_against_azimuth_fr_301`, `::test_the_components_of_one_placed_blade_fr_301`, `::test_a_load_without_a_mean_force_has_no_centroid_fr_301`.*

    Need: A wheel of `B` identical blades solved at `k` clockings gives `B k` samples of one blade's load at known azimuths, from which the load against azimuth is wanted.

    Requirement: From each blade's force and moment about the hub in the fixed frame and its azimuth, the axial, tangential and radial forces are fitted as a Fourier series in azimuth by least squares, with at most `(distinct - 1) // 2` harmonics and a `ProductError` when more are asked; the centroid radii are the mean moments over the mean forces unless stated, refused when a mean force is zero or the radius is not positive.

    Solution (release 0.32.0): `rotating_components`, `fit_azimuthal_series`, `AzimuthalSeries`, `reconstruct_blade_load`, `azimuth_from_moment`.

!!! requirement "FR-302 The observer-time retardation of a subsonic source <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-QS-NOISE, section 2.6 part 5 of the 0.32.0 scope. Evidence: `tests/tier1_offline/test_p0320_f_qsteady_noise.py::test_the_emission_time_of_a_source_at_rest_fr_302`, `::test_the_emission_time_of_a_source_in_uniform_motion_fr_302`, `::test_the_emission_time_of_a_rotating_blade_and_a_moving_observer_fr_302`, `::test_a_supersonic_source_is_refused_fr_302`.*

    Need: Sound heard at an observer time left the source earlier, and a rotating or flying source moves in between.

    Requirement: The emission time of each observer time is the root before it of `|x(t) - y(tau)| = c0 (t - tau)`, for an observer at rest or moving; a source whose speed bound is not below `c0` is refused with a `ProductError`.

    Solution (release 0.32.0): `emission_times`, used by `loading_noise`.

!!! requirement "FR-303 The steady rotor's tonal harmonics in closed form <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-QS-NOISE, section 2.6 part 5 of the 0.32.0 scope. Evidence: `tests/tier1_offline/test_p0320_f_qsteady_noise.py::test_steady_rotor_harmonics_match_the_gutin_closed_form_fr_303`, `::test_a_thrust_alone_is_silent_in_the_plane_of_the_disc_in_the_far_field_fr_303`, `::test_an_observer_moving_with_the_hub_on_the_axis_hears_a_constant_fr_303`.*

    Need: The time-domain model must be held to a case whose tonal amplitude is known before it is compared with any solver output.

    Requirement: The far-field rms amplitude of shaft harmonic `n` of `B` identical blades with a steady load is Gutin's closed form (Gutin 1936, in the form of M. E. Goldstein, Aeroacoustics, 1976, chapter 3; the compact steady limit of D. B. Hanson, AIAA Journal 18, 1980), zero for `n` not a multiple of `B`; the model's harmonics agree with it to 0.5 per cent at a tip Mach of 0.5.

    Solution (release 0.32.0): `gutin_harmonic_rms`.

!!! requirement "FR-304 The comparison measures and the route A report <span class='srs-implemented'>implemented</span>"

    *Origin: P0320-QS-NOISE, section 2.6 part 5 of the 0.32.0 scope, EXPLORATORY (no threshold, no gate). Evidence: `tests/tier1_offline/test_p0320_f_qsteady_noise.py::test_the_comparison_measures_fr_304`, `::test_the_workspace_writer_is_not_wired_and_still_refuses_fr_304`, `::test_rpt099_and_its_sidecar_state_only_nondimensional_values_fr_304`; report `reports/RPT-099_qsteady-noise-route-a-against-round-3_2026-09-30.md`.*

    Need: A predicted pressure record is compared with the solver's acoustic signals of an unsteady run on the same times.

    Requirement: `compare_signals` returns, of the fluctuations about each record's mean, the rms ratio, its level difference in dB, the Pearson correlation and the rms of the difference over the reference's rms, plus the ratio of the means; records of unequal length, of fewer than two samples, or constant are refused. The workspace writer `write_qsteady_noise_report` stays a refusing contract in 0.32.0, and report RPT-099 states only nondimensional values.

    Solution (release 0.32.0): `compare_signals`, `SignalComparison`; RPT-099 and its JSON sidecar.
