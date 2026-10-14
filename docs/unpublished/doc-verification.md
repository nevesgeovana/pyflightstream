# Documentation verification provenance

The published pages state user-facing behavior. This unpublished page keeps the public requirement, report and test locators used to verify those statements. The fixtures and examples are still checked on the published pages.

## docs/sixdof-motion.md

The initial angular-velocity input is in rad/s on 26.124 and 26.125, and the
trajectory rates p, q, r are in rad/s while phi, theta, psi are in degrees:
[RPT-169, 6DOF initial angular velocity input unit](../../reports/RPT-169_6dof-initial-rate-unit_2026-10-13.md).
This replaces the earlier inference from the rotary-motion command's unit.
The probe does not settle the remaining trajectory column units.

## docs/definitions/the-additional-post.md

    `pyfs-matrix post <matrix> --additional-pproc`, with no solve (`test_g12_the_extraction_lands_in_additional_and_is_hashed`,
    `test_g12_the_additional_script_never_solves_and_never_saves`). This section
    ([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md)):
    (`test_g12_a_row_on_another_build_is_refused_naming_rpt062`). The field off the
    (`test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062`,
    `test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused`).
    (`test_g12_an_unsteady_extractions_sections_table_is_the_last_instant`), and
    (`test_g12_an_unsteady_extraction_is_one_instant_in_the_post_log`). The plots
    (`test_g12_additional_products_are_marked_with_the_pproc`):
    (RPT-062). The table keeps every row: the layout the extraction records is the
    (`test_g12_the_additional_sections_table_holds_the_run_rows_then_the_additional_ones`).
    (`test_g12_a_frame_turned_since_the_run_under_the_same_name_is_skipped`,
    `test_g12_a_frame_moved_after_it_was_placed_differs_by_the_move`), since a
    (`test_g12_an_older_record_is_held_to_the_boundaries_its_geometry_hash_recovers`),
    (`test_g12_an_older_record_whose_boundaries_no_hash_recovers_is_skipped_naming_why`):
    (`test_g12_an_extraction_of_another_state_of_the_point_is_stale`). A saved
    (`test_g12_an_extraction_whose_saved_simulation_left_the_disk_is_stale`). A
    (`test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product`). The
    (`test_g12_an_extraction_whose_file_changed_is_extracted_again`).

## docs/flight-conditions.md

    is both (FR-69, FR-70):
    (`test_goal024_freestream_rotation_a_pitch_rate_turns_the_free_stream`). The
    (`test_goal024_freestream_rotation_a_rate_sweeps_like_any_other_variable`).
    (`test_goal024_freestream_rotation_a_reference_declaring_no_axes_is_refused_by_name`),
    not write (`test_goal024_freestream_rotation_two_non_zero_rates_are_refused_by_name`,
    `test_goal024_freestream_rotation_a_case_authored_in_python_is_refused_too`).
    (`test_goal024_freestream_rotation_every_rate_zero_writes_constant`,
    `test_goal024_freestream_rotation_a_row_with_no_rate_at_all_writes_constant`).
    `test_goal024_freestream_rotation_each_rate_turns_in_the_flight_mechanics_sense`,
    `test_goal024_freestream_rotation_each_rate_takes_its_own_axis`). The sign per
    (`test_goal024_freestream_rotation_the_sign_per_rate_is_the_export_to_body_turn`).
    (`test_the_emitted_rotation_is_the_one_the_probe_recorded_producing_that_rate`
    | `roll_rate` | right wing down | `ROTATION <frame> X -6.667` | the meshed left wing loses lift (-0.0998 in its lift coefficient) and the rolling moment opposes the roll: the damping of a positive roll rate | T11, RPT-060 |
    | `pitch_rate` | nose up | `ROTATION <frame> Y 6.667` | the airframe gains lift (+0.0227) and the pitching moment turns nose down (-0.0012): the damping of a positive pitch rate | RPT-052 |
    | `yaw_rate` | nose right | `ROTATION <frame> Z -6.667` | the meshed left wing, now advancing, gains lift (+0.0089): the response of a positive yaw rate | T11, RPT-060 |
    right for pitch (RPT-052) and reversed for roll and yaw (T11, RPT-060), so the
    (`test_goal024_freestream_rotation_a_permuted_axis_turns_with_its_rates_sign`);

## docs/srs/data-model.md

    2026-09-09 (PFS-2003.03): one entry listed the letters and the digits
    `tests/tier1_offline/test_command_db_grammar.py` pins every member of
    as that digit (PFS-2003.04).
    evidence. The harness now has the outcome (RPT-026), recognised from
    RAN_MISSING_LOG (FR-413), a run whose outputs are all present
    `runs.json` holding it; and MAX_ITER_REACHED (FR-434), a steady point that
          30_WB/         the recommended form (PFS-2032.04): the geometry file,

## docs/storage-and-sync.md

    without an archive by default (FR-397). With `post --archive`, `collect --archive`

## docs/workflow-additional-post.md

    (`test_g12_a_row_stating_additional_pproc_plans_ready`), no builder reads the
    (`test_g12_the_key_changes_no_byte_of_the_run_script`), and the run record
    never carries it (`test_g12_the_run_record_never_carries_the_key`). Afterwards,
    own ([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md)):
    (`test_g12_a_copy_that_does_not_hash_as_recorded_fails_and_launches_nothing`),
    (`test_g12_the_extraction_lands_in_additional_and_is_hashed`). The script opens
    created (`test_g12_the_distributions_cite_the_frames_the_run_created`), updates
    (`test_g12_the_additional_script_renders_its_committed_bytes`). It never
    (`test_g12_the_additional_script_never_solves_and_never_saves`). The copy is
    (`test_g12_an_original_that_changes_during_the_extraction_fails_it`).
    (`test_g12_the_extraction_lands_in_additional_and_is_hashed`). `runs.json` is
    (`test_g12_the_original_run_record_and_manifest_are_untouched`). The post then
    (`test_g12_additional_products_are_marked_with_the_pproc`); the
      `test_g12_a_row_without_the_key_is_skipped_naming_why`);
      `test_g12_a_point_whose_saved_simulation_is_absent_is_skipped_naming_the_path`);
      `test_g12_a_point_whose_saved_simulation_does_not_match_its_record_is_skipped_naming_both_hashes`);
      `test_g12_an_extracted_point_is_not_extracted_twice`); an extraction whose
      (`test_g12_an_extraction_whose_file_changed_is_extracted_again`);
      (`BUILD_CHANGED`, `test_g12_a_point_whose_build_changed_is_skipped`): a saved
      `test_g12_a_run_that_averaged_its_surface_in_time_is_skipped`): whether a
      `test_g12_a_row_whose_frames_changed_since_the_run_is_skipped`,
      `test_g12_a_point_whose_boundaries_moved_since_the_run_is_skipped`): a
      (`test_g12_a_frame_turned_since_the_run_under_the_same_name_is_skipped`).
      (`test_g12_an_older_record_is_held_to_the_boundaries_its_geometry_hash_recovers`);
      (`test_g12_an_older_record_whose_boundaries_no_hash_recovers_is_skipped_naming_why`);
      `test_g12_a_point_still_in_a_queue_is_skipped`), a continuation replaced it
      `test_g12_a_run_a_continuation_replaced_is_skipped_and_the_continuation_extracted`),
      `test_g12_a_point_whose_row_is_no_longer_active_is_skipped`).
    (`test_g12_an_additional_pproc_the_library_lacks_is_refused_at_plan_naming_the_key`).
    ([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md),
    `test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062`), and the
    (`test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused`).
    (`test_g12_the_key_on_a_legacy_row_is_refused`). And a row on a build other
    than 26.124, the one build RPT-062 measured
    (`test_g12_a_row_on_another_build_is_refused_naming_rpt062`).
    run holds its LAST instant (RPT-062), so what the extraction gives there is that
    rows (`test_g12_plan_warns_that_an_unsteady_rows_additional_post_is_one_instant`),
    (`test_g12_an_unsteady_point_is_one_instant_and_says_so`).
    read from its rows (`test_g12_the_additional_post_needs_the_matrix`), and takes
    (`test_g12_a_flag_of_the_additional_post_without_it_is_refused`). It prints
    (`test_g12_the_cli_post_additional_pproc_prints_each_point_and_exits`).
    (`test_g12_the_cli_exits_2_on_a_failed_extraction_and_counts_under_strict_a_skip_that_asks`).
    (`test_submitted_extraction_waits_then_collects_without_mutating_original`). Repeating the request while it is pending
    (`test_submitted_extraction_waits_then_collects_without_mutating_original`).
    (`test_an_additional_post_planned_for_a_submission_exports_no_log`). The
    (`test_an_additional_post_under_local_exports_no_log_on_such_a_machine`,
    `test_an_additional_post_writes_the_printed_output_as_its_log`).
    (`test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product`).

## docs/workflow-qsteady-rotor.md

    26.124 (RPT-089): **`PASSAGE_POSITIONS: 2` converges thrust and torque to
    six, and the torque 7.1 % and 5.75 % above (RPT-089 section 3). A finer unsteady step
    builds have since run on 26.124: a sector coupled with FSI (RPT-090) and a
    (RPT-091).
    (`test_a_missing_log_strands_no_other_output_of_a_local_point`,
    `test_collection_files_every_output_that_exists_and_names_only_the_missing`). A missing file does not prevent collection of the outputs that exist. The collection method raises `MissingOutputsError`, a
    (`test_g11_every_workflow_script_saves_its_final_simulation`,
    `test_g11_the_save_comes_first_among_the_points_exports`), and the file is
    (`test_g11_the_saved_simulation_is_collected_and_hashed`), and a point whose
    (`test_g11_a_point_whose_saved_simulation_is_missing_is_recorded_incomplete`).
    (`test_g11_every_point_of_a_steady_sweep_saves_its_own`), for `unsteady` and
    (`test_g11_every_workflow_script_saves_its_final_simulation`,
    `test_g11_the_saved_simulation_is_collected_and_hashed`); 25.000 renders
    is (`test_g11_a_pproc_cannot_switch_the_saved_simulation_off`). A `LEGACY`
    (`test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan`). A
    (`test_a_row_declaring_a_loads_table_and_a_log_gets_exactly_those`). This
    [RPT-137](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md)

## docs/workflow-run-matrix.md

    rather than an import step (FR-10, FR-35). Each row names a point of
    three identifiers that reach into the input library; `PPROC` names the post-processing artifact (PFS-2029.07). `FS_BUILD` names the FlightStream
    is still mapped by that option (PFS-2031.11). A `LEGACY` row's recipe also
    (`test_g11_a_legacy_row_without_a_saved_simulation_is_warned_at_plan`). `HIDDEN` and
      every stem-only cell of an older matrix with `.fsm` (PFS-2029.09). What the name buys is that the cell
        half's is the row's `SYMMETRY_LOADS` column (FR-66), emitted as
    rule that keeps them apart is one folder per matrix (PFS-2031.04): `plan`
    `post/<stem>/campaign_sweep.csv` ONCE (FR-90: the two names were the same
    golden by `tests/tier1_offline/test_tier3_offline.py`. They are not
    `run --resume` skips it (`test_the_plan_reports_a_recorded_jobs_points_as_recorded`).
    (`test_two_new_angles_of_a_recorded_job_are_recorded_one_each`); the plan

## docs/workspace-and-workflows.md

    `test_the_committed_matrix_drives_the_workflow_with_no_python_recipe` in
    `tests/tier1_offline/test_workflows.py`, which builds every row of it and asserts that
    `tests/tier1_offline/test_docs_example_currency.py` holds the two together, so this
      that rotor's own block (FR-68). The solver model is the setup preset's
      axis, no re-parameterisation, no trim extraction. FR-20 carries that

## docs/actuator-profiles.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-070: the volume section and the actuator disc on 26.124, and a profile file the solver would not read (2026-09-24)](../../reports/RPT-070_the-gui-rows-volume-section-and-actuator-disc_2026-09-24.md)
- [RPT-137 - The actuator disc on FlightStream 26.124: the swirl sense, the swirl factor, the thrust ELLIPTICAL and RELAXED put in the wake, and the quasi-steady probe frame (2026-10-01)](../../reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md)

## docs/boundary-conditions.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-021: four chapter questions asked of the solver](../../reports/RPT-021_chapter-questions-measured_2026-08-08.md)
- [RPT-066: base regions mark the base boundary, and wake termination is unobserved (2026-09-24)](../../reports/RPT-066_base-regions-mark-the-base-boundary-and-wake-termination-is-unobserved_2026-09-24.md)
- [RPT-081 - Typed boundary and base-region operations (2026-09-27, editorial amendment 2026-09-28)](../../reports/RPT-081_typed-boundary-and-base-region-operations_2026-09-27.md)

## docs/boundary-layer-products.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-027: the boundary layer across a proximity gap, 26.122 against 26.123 (2026-08-17, amended 2026-08-17)](../../reports/RPT-027_boundary-layer-across-a-proximity-gap_2026-08-17.md)
- [RPT-075: the boundary-layer profile export still holds an unattended script on 26.124 (2026-09-25)](../../reports/RPT-075_the-boundary-layer-profile-still-holds-the-script-on-26124_2026-09-25.md)

## docs/ccs-geometry.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-097 - pyflightstream 0.32 CCS confirmation, round 2 on FlightStream 26.124 (2026-09-30)](../../reports/RPT-097_ccs-confirmation-round-2-on-26124_2026-09-30.md)

## docs/definitions/a-volume-section.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-070: the volume section and the actuator disc on 26.124, and a profile file the solver would not read (2026-09-24)](../../reports/RPT-070_the-gui-rows-volume-section-and-actuator-disc_2026-09-24.md)

## docs/definitions/native-surface-flow-exports.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-041: a SCRIPT action re-reads its file on every time step, measured on 26.123 (2026-09-08)](../../reports/RPT-041_script-action-reread-on-26123_2026-09-08.md)
- [RPT-074: the VTK surface export carries more than the Tecplot, per cell, in the loads frame (2026-09-25)](../../reports/RPT-074_the-vtk-export-is-written-in-the-loads-frame-per-cell_2026-09-25.md)
- [RPT-079: the solver's time averaging counts time steps, on the one build that runs it (2026-09-25)](../../reports/RPT-079_the-solver-averages-the-surface-over-time-steps-on-26122_2026-09-25.md)
- [RPT-080: every changed tier-3 row on 26.124 against the 0.27.0 run (2026-09-25)](../../reports/RPT-080_every-changed-tier3-row-on-26124-against-0270s-run_2026-09-25.md)

## docs/definitions/the-axes-of-a-steady-polar.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-128: CDo and the XZ moment of a coupled cambered wing on 26.124](../../reports/RPT-128_cdo-and-the-xz-moment-of-a-coupled-cambered-wing-on-26124_2026-10-02.md)

## docs/definitions/the-boundary-layer-profile-is-not-produced.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-027: the boundary layer across a proximity gap, 26.122 against 26.123 (2026-08-17, amended 2026-08-17)](../../reports/RPT-027_boundary-layer-across-a-proximity-gap_2026-08-17.md)
- [RPT-067: the plot commands write the plotted series as text (2026-09-24)](../../reports/RPT-067_the-plot-commands-write-the-plotted-series-as-text_2026-09-24.md)
- [RPT-074: the VTK surface export carries more than the Tecplot, per cell, in the loads frame (2026-09-25)](../../reports/RPT-074_the-vtk-export-is-written-in-the-loads-frame-per-cell_2026-09-25.md)
- [RPT-075: the boundary-layer profile export still holds an unattended script on 26.124 (2026-09-25)](../../reports/RPT-075_the-boundary-layer-profile-still-holds-the-script-on-26124_2026-09-25.md)

## docs/definitions/the-quasi-steady-rotor.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-005: WP1 FSI dry run on FlightStream 26.120 (2026-07-21)](../../reports/RPT-005_fsi-dry-run_2026-07-21.md)
- [RPT-006: WP7 near-rigid coupled pilot on FlightStream 26.120 (2026-07-21)](../../reports/RPT-006_wp7-nearrigid-pilot_2026-07-21.md)

## docs/definitions/the-sections-table-and-which-row-is-which.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-006: WP7 near-rigid coupled pilot on FlightStream 26.120 (2026-07-21)](../../reports/RPT-006_wp7-nearrigid-pilot_2026-07-21.md)
- [RPT-053: what an unsteady export states, and at which step (2026-09-19)](../../reports/RPT-053_what-an-unsteady-export-states-and-when_2026-09-19.md)

## docs/definitions/the-solvers-own-plots.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-067: the plot commands write the plotted series as text (2026-09-24)](../../reports/RPT-067_the-plot-commands-write-the-plotted-series-as-text_2026-09-24.md)
- [RPT-076: the solver saves its residual and load plots after an unsteady solve too (2026-09-25)](../../reports/RPT-076_the-solver-s-plots-after-an-unsteady-solve_2026-09-25.md)

## docs/definitions/tip-and-helical-mach-numbers.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-051: a rotor on 26.100 without the rotor mark (2026-09-15)](../../reports/RPT-051_a-rotor-on-26100-without-the-rotor-mark_2026-09-15.md)

## docs/definitions/what-the-package-does-not-judge.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-055: a residual block whose `Iteration` anchor is cut carries nothing to refuse](../../reports/RPT-055_partial-residual-anchor_2026-09-22.md)
- [RPT-058: post log captures warnings process-wide](../../reports/RPT-058_post-log-captures-warnings-process-wide_2026-09-23.md)

## docs/fsi-workspace.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-025: the rotor morphing defect across three builds (2026-08-11)](../../reports/RPT-025_rotor-morphing-across-three-builds_2026-08-11.md)
- [RPT-092 - Fixed-wing FSI with the wing's own weight, confirmed on 26.124 (2026-09-29)](../../reports/RPT-092_fixed-wing-fsi-on-26124_2026-09-29.md)
- [RPT-128: CDo and the XZ moment of a coupled cambered wing on 26.124](../../reports/RPT-128_cdo-and-the-xz-moment-of-a-coupled-cambered-wing-on-26124_2026-10-02.md)
- [RPT-154 - Direct aeroelastic morphing not recognised by build 8172026 (2026-10-05)](../../reports/RPT-154_direct-aeroelastic-morphing-not-recognised-by-build-8172026_2026-10-05.md)
- [RPT-155 - Direct aeroelastic morphing on build 10052026 (2026-10-05)](../../reports/RPT-155_direct-aeroelastic-morphing-on-26125_2026-10-05.md)

## docs/geometry-units-and-starts.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-070: the volume section and the actuator disc on 26.124, and a profile file the solver would not read (2026-09-24)](../../reports/RPT-070_the-gui-rows-volume-section-and-actuator-disc_2026-09-24.md)

## docs/mesh/how-to.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-078: an OBJ is imported one boundary per group, in the order of the file (2026-09-25)](../../reports/RPT-078_an-obj-is-imported-in-the-order-of-its-groups_2026-09-25.md)

## docs/mesh/reference.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-048: what a per-surface translation does to shared vertices, on 26.123 (2026-09-14)](../../reports/RPT-048_what-a-per-surface-translation-does-to-shared-vertices_2026-09-14.md)
- [RPT-061: where the wake-edge import reads its nodes (2026-09-23)](../../reports/RPT-061_where-the-wake-edge-import-reads-its-nodes_2026-09-23.md)
- [RPT-065: what detection and initialisation mark (2026-09-24)](../../reports/RPT-065_what-detection-and-initialisation-mark_2026-09-24.md)
- [RPT-066: base regions mark the base boundary, and wake termination is unobserved (2026-09-24)](../../reports/RPT-066_base-regions-mark-the-base-boundary-and-wake-termination-is-unobserved_2026-09-24.md)
- [RPT-069: three routes to one body, and the node the file route lost at the blade's root (2026-09-24)](../../reports/RPT-069_three-routes-to-one-body-and-the-file-routes-root-node_2026-09-24.md)
- [RPT-078: an OBJ is imported one boundary per group, in the order of the file (2026-09-25)](../../reports/RPT-078_an-obj-is-imported-in-the-order-of-its-groups_2026-09-25.md)
- [RPT-162 - Isolated propeller comparison of refined mesh levels on 26.124 (2026-10-06)](../../reports/RPT-162_isolated-propeller-refine-levels-on-26124_2026-10-06.md)

## docs/pproc-artifact.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-066: base regions mark the base boundary, and wake termination is unobserved (2026-09-24)](../../reports/RPT-066_base-regions-mark-the-base-boundary-and-wake-termination-is-unobserved_2026-09-24.md)

## docs/sampled-fields.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-083 - Probe frames and temporal export limits (2026-09-27, editorial amendment 2026-09-28)](../../reports/RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md)
- [RPT-136 - Build 8242026 of FlightStream 26.124 is registered by decision, not by measurement (2026-10-01)](../../reports/RPT-136_fr153-build-8242026_2026-10-01.md)
- [RPT-137 - The actuator disc on FlightStream 26.124: the swirl sense, the swirl factor, the thrust ELLIPTICAL and RELAXED put in the wake, and the quasi-steady probe frame (2026-10-01)](../../reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md)

## docs/srs/scope.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-008: mesher and flow-visualization integration license research (v0.3 line)](../../reports/RPT-008_integrations-license-research_2026-07-22.md)

## docs/surface-translation.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-074: the VTK surface export carries more than the Tecplot, per cell, in the loads frame (2026-09-25)](../../reports/RPT-074_the-vtk-export-is-written-in-the-loads-frame-per-cell_2026-09-25.md)
- [RPT-087 - A periodic row's native Tecplot is read one zone per copy (2026-09-28)](../../reports/RPT-087_periodic-native-tecplot-one-zone-per-copy_2026-09-28.md)

## docs/unsteady-postprocessing.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-083 - Probe frames and temporal export limits (2026-09-27, editorial amendment 2026-09-28)](../../reports/RPT-083_probe-frames-and-temporal-export-limits_2026-09-27.md)

## docs/workflow-builds-and-hpc.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-049: a rotor on the builds before the rotary motion (2026-09-15)](../../reports/RPT-049_a-rotor-on-the-builds-before-the-rotary-motion_2026-09-15.md)
- [RPT-051: a rotor on 26.100 without the rotor mark (2026-09-15)](../../reports/RPT-051_a-rotor-on-26100-without-the-rotor-mark_2026-09-15.md)

## docs/workflow-input-library.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-018: the flow-separation family across four builds, and a delete command the February edition documents under a name the solver does not answer to](../../reports/RPT-018_separation-family-across-builds_2026-08-05.md)
- [RPT-064: a loads frame set before the solve reaches every step export (2026-09-24)](../../reports/RPT-064_a-loads-frame-set-before-the-solve-reaches-every-step_2026-09-24.md)
- [RPT-068: two documented setup commands are unrecognized on 26.124 (2026-09-24)](../../reports/RPT-068_two-documented-setup-commands-are-unrecognized-on-26124_2026-09-24.md)
- [RPT-106: setup-key audit of the solver chapters (2026-09-30)](../../reports/RPT-106_setup-key-audit_2026-09-30.md)

## docs/workflow-plan-and-cost.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-148 - Licensed batched versus alone comparisons for 0.35.1 (2026-10-03)](../../reports/RPT-148_licensed-batched-versus-alone-0351_2026-10-03.md)

## docs/workflow-row-flow-inputs.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-052: the sense of a rotating free stream (2026-09-15)](../../reports/RPT-052_the-sense-of-a-rotating-free-stream_2026-09-15.md)
- [RPT-069: three routes to one body, and the node the file route lost at the blade's root (2026-09-24)](../../reports/RPT-069_three-routes-to-one-body-and-the-file-routes-root-node_2026-09-24.md)
- [RPT-070: the volume section and the actuator disc on 26.124, and a profile file the solver would not read (2026-09-24)](../../reports/RPT-070_the-gui-rows-volume-section-and-actuator-disc_2026-09-24.md)
- [RPT-071: a custom free stream sets the flow's direction, and the angle of attack does not turn it (2026-09-24)](../../reports/RPT-071_a-custom-free-stream-sets-the-flow-direction_2026-09-24.md)
- [RPT-077: what RPT-071 left open about the custom free stream (2026-09-25)](../../reports/RPT-077_what-was-left-of-the-custom-free-stream_2026-09-25.md)
- [RPT-137 - The actuator disc on FlightStream 26.124: the swirl sense, the swirl factor, the thrust ELLIPTICAL and RELAXED put in the wake, and the quasi-steady probe frame (2026-10-01)](../../reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md)

## docs/workflow-row-geometry-motion.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-048: what a per-surface translation does to shared vertices, on 26.123 (2026-09-14)](../../reports/RPT-048_what-a-per-surface-translation-does-to-shared-vertices_2026-09-14.md)

## docs/workflow-unsteady-rotor.md

Report locators carried by this page at v0.39.0, retained here after the
publication cleanup. Each report retains its own build and measurement limits.

- [RPT-041: a SCRIPT action re-reads its file on every time step, measured on 26.123 (2026-09-08)](../../reports/RPT-041_script-action-reread-on-26123_2026-09-08.md)
- [RPT-044: a boundary renamed in the solver before the save reaches every export by its new name (2026-09-09)](../../reports/RPT-044_a-renamed-boundary-reaches-the-export-by-its-new-name_2026-09-09.md)
- [RPT-064: a loads frame set before the solve reaches every step export (2026-09-24)](../../reports/RPT-064_a-loads-frame-set-before-the-solve-reaches-every-step_2026-09-24.md)
- [RPT-066: base regions mark the base boundary, and wake termination is unobserved (2026-09-24)](../../reports/RPT-066_base-regions-mark-the-base-boundary-and-wake-termination-is-unobserved_2026-09-24.md)
- [RPT-089 - The quasi-steady rotor against the unsteady rotor, measured (2026-09-29, amended 2026-10-01)](../../reports/RPT-089_qsteady-rotor-vs-unsteady_2026-09-29.md)
