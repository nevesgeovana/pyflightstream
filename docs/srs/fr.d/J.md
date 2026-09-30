!!! requirement "FR-280 A static rig row with MOTIONS is not refused for stating its speed twice <span class='srs-implemented'>implemented</span>"

    *Origin: D-RIG, moved from 0.33 by the owner's "pode entrar" (GEO-066,
    package J). Evidence: `tests/tier1_offline/test_p0320_rigor.py`
    (`test_p0320_d_rig_a_static_rig_with_motions_is_not_refused_for_a_double_speed`).*

    **Need.** A rotor rig turns at a fixed speed and sweeps the advance ratio,
    which then means the free stream, V = J x (RPM/60) x D.

    **Requirement.** A row that states `RPM` and a swept `ADVANCE_RATIO` and
    no velocity in its cell, with `MOTIONS`, is planned at every point and its
    rotor Mach numbers are resolved; the plan does not read the velocity it
    derived at the point as a stated one and refuse the row for stating its
    rotor speed twice.

    **Solution** (release 0.32.0). The static-rig test of `rotor_speed` asks
    what the cell declared (`condition_order`), not what the point resolved.
    Trace: `test_p0320_d_rig_a_static_rig_with_motions_is_not_refused_for_a_double_speed`.

!!! requirement "FR-281 One native match tolerance, with the printed-precision slack <span class='srs-implemented'>implemented</span>"

    *Origin: 0.29.1-tol, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_tol_0291_one_function_gives_the_printed_precision_slack`,
    `test_p0320_tol_0291_a_full_precision_native_adds_no_slack`.*

    **Need.** A native nodal export printed at limited digits and a VTK written
    at single precision differ, for a part far from the origin, by more than
    four single-precision epsilons of the coordinates.

    **Requirement.** One function, `native_match_tolerance`, beside
    `attach_native_strength`, gives the per-axis tolerance the match takes by
    default. Told the significant digits the native was printed at
    (`native_printed_digits`), it adds half a unit of the last digit and half
    a single-precision spacing of the coordinate magnitude. Told nothing, it is
    the rule it always was, and a native printed at full precision adds
    nothing.

    **Solution** (release 0.32.0). `results/native_surface.py`. Trace: the two
    tests above.

!!! requirement "FR-282 The time-averaged native strength uses that tolerance <span class='srs-implemented'>implemented</span>"

    *Origin: 0.29.1-avg, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_avg_0291_the_time_average_matches_a_far_native_with_that_tolerance`.*

    **Need.** The time average of a surface matched each step's native
    strength with a tolerance of its own.

    **Requirement.** `average_surface_exports` resolves the tolerance of each
    step's native from `native_match_tolerance` and the digits that native was
    printed at, and records it in the step's matching evidence.

    **Solution** (release 0.32.0). `post/surfaces.py`. Trace: the test above.

!!! requirement "FR-283 DEFAULT_DRIFT_LIMIT_PCT is public in cases <span class='srs-implemented'>implemented</span>"

    *Origin: ARCH2-S2, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_arch2_s2_the_default_drift_limit_is_public_in_cases`.*

    **Need.** The default drift limit is read by the post stage and belongs to
    the case model.

    **Requirement.** `DEFAULT_DRIFT_LIMIT_PCT` is in `pyflightstream.cases.__all__`
    and is the default of `PerRevolutionSpec.drift_limit_pct`.

    **Solution** (release 0.32.0). `cases/__init__.py`. Trace: the test above.

!!! requirement "FR-284 The clocking 0 filter of the NA shares is tested <span class='srs-implemented'>implemented</span>"

    *Origin: QA2-2, moved from 0.33 (GEO-066, package J). Evidence:
    `test_p0320_qa2_2_the_na_shares_read_clocking_zero_rows_only`.*

    **Need.** The thrust and torque shares above k = 0.1 read the point's own
    solve, clocking 0, of a table that holds every clocking; nothing pinned it.

    **Requirement.** With rows of another clocking that carry other forces and
    an unread force, the shares are those of clocking 0's rows alone and no
    note is written.

    **Solution** (release 0.32.0). A test of the 0.31.0 filter
    (`add_reduced_frequency_to_sections`); a mutant that removes the filter
    fails it. Trace: the test above.

!!! requirement "FR-285 A quasi-steady point's products state J <span class='srs-implemented'>implemented</span>"

    *Origin: QS-J, the owner's post-release defect class "ADVANCE_RATIO not
    NA", found by the X1 rehearsal: 17 rows of `_qs_avg.csv` and
    `_qs_positions.csv` of the recorded wheel workspace read `NA` in `J` and
    `J_CLOCK`. Evidence: `test_p0320_qs_j_a_wheel_point_states_its_j_from_its_own_speed_and_diameter`,
    `test_p0320_qs_j_a_requested_j_is_kept_and_a_missing_free_stream_stays_na`.*

    **Need.** A quasi-steady point turns its rotor at the speed of its record,
    and the rotor's block gives its diameter.

    **Requirement.** `J_CLOCK`, `RPM_CLOCK` and, where the row requested none,
    `J` state the rotor's own advance ratio `V / (n D)` in both quasi-steady
    tables, by the one formula of the rotor table (`rotor_advance_ratio`).
    What the row requested is kept, and a point without a free stream or a
    diameter stays `NA`. Re-posting a copy of the recorded workspace gives all
    17 rows a finite `J`.

    **Solution** (release 0.32.0). `post/_tables.py` (`rotor_advance_ratio`,
    shared with `J_CLOCK` of the other tables), `post/qsteady.py`. Trace: the
    two tests above.
