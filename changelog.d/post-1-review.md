# Post-processing corrections for 0.40.0

- migration: PFS-2100.003, PFS-2100.012, PFS-2100.011 and PFS-2100.013 correct diagnostic commands, product names, geometry remedies and CSV line numbers.
- migration: PFS-2105.005, PFS-2105.006 and PFS-2105.030 change rotor warnings, omit averages that cannot become coefficients and preserve the simulation Mach when a record has none.
- migration: PFS-2105.007, PFS-2105.008 and PFS-2105.011 key acoustic skips per point, end harmonics at available history and label unwindowed unsteady group polars as instant, including exports identified by solver mode.
- migration: PFS-2095.044 and PFS-2095.018 raise ProductError for named legacy groups and malformed custom-polar numeric input.
- migration: PFS-2105.032 preserves acoustic floating-point precision. Rebuild acoustic tables to recover small amplitudes and exact time samples.
- migration: PFS-2105.033 invalidates derived rotor and average columns when their source components are corrected.
- migration: PFS-2105.012 bounds custom-polar numeric fields to preserve separation; long values may use reduced precision.
- migration: PFS-2089.007 renames the inflow result to InflowStationHarmonics. The old inflow_tools.StationHarmonics import warns and remains available until 1.0.0. The loads-harmonics class keeps its name.
- migration: PFS-2105.014 mirrors YMOM and every *_PHASE_DEG column. Rebuild installed-frame copies from their source tables.
- migration: PFS-2105.037 refuses negative-X blade-view axes; use positive X with signed omega.
- migration: PFS-2088.014 uses one clock reader for reductions and probes and refuses a nonmonotonic native field clock.
- migration: PFS-2105.015 writes NA for plots coefficients at nonpositive freestream velocity and explains why.
- migration: PFS-2085.021 warns about the unmeasured declined-drag interpretation of 26.125 exports.
- migration: PFS-2096.021 and PFS-2096.022 check all destinations before writing probe fields or a surface-average pair.
- migration: PFS-2096.019 and PFS-2096.020 write manifests atomically and reject an unknown matrix before creating its products folder.
- migration: PFS-2105.035 measures geometry-frame section radii and torque arms from the hub. Harmonic radius columns become NA, with a warning, where the recorded frame and hub cannot place the station.
- migration: PFS-2105.036 refuses clockings without positive reference velocity instead of substituting freestream velocity.
- migration: PFS-2105.017 fixes ETAW's orientation across incidence zero; PFS-2105.018 writes NA for attitude-dependent quantities when ALPHA or BETA is missing; PFS-2105.040 names frame refusals and static rows.
- migration: PFS-2100.014 suppresses builder-only warnings during section matching; PFS-2105.039 excludes stamped files outside the recorded window and names them in skipped.
- migration: PFS-2089.001 makes native file lists relative to the products folder, matching product keys. Resolve these paths from the folder containing products.json.
- migration: PFS-2105.038 lists only steps with emitted rows in steps_tabled.
- migration: PFS-2105.019 keeps fill sentinels out of wide values. PFS-2105.042 adds f<id>_kind to distinguish enumeration codes from list lengths. Codebook version 1 retains its existing code meanings.
- migration: PFS-2105.021 records expected and emitted section counts as lists retaining block multiplicity.
- migration: PFS-2095.045 rejects reversed surface-average windows with ProductError.
- migration: PFS-2081.40 extends the integrated tip strips by half a spacing beyond the end stations; rebuild Strip_length, Fx_int, Fz_int and My_int products.
- migration: PFS-2098.004 exposes cases.TEMPLATE_SETTINGS_LEFT_OUT and workspace.missing_log_warning as public contracts for the post layer.

The licensed 26.125 declined-surface probe still requires registration by its owner. No licensed solver was run during this review.
