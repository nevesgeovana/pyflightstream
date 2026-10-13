## Added
- `farfield.plane_lift`: the Kutta-Joukowski lift of the streamwise vorticity a Trefftz C plane holds. The C row of a wing states it as `CL_T`, and post warns where it departs from the solver's CL by more than 10 percent: the probe field then does not hold the circulation the loads shed (FR-453 R9, PFS-2081.95, RPT-171).
- Every row of `farfield/<group>_trefftz.csv`, `farfield/<group>_ledgers.csv` and `sections/<point>_trefftz_<family>.csv` ends with `STATUS`, the point's solver termination status as `campaign_sweep.csv` writes it (FR-456 R10, PFS-2081.97).
- The run record carries `farfield_layout`, the far-field plane and lattice each point laid or reused (a steady job keys it by point name), and `plan.json` states it under the row's `farfield` `probes` (FR-455 R4, PFS-2081.58).
## Changed
- Planning resolves the far-field plane and lattice once, by frame and by the exact laid-out points: a declared `[[probes]]` shape identical after layout is reused (a key stated at its default is the same geometry), and a `[farfield]` table stating no geometry reuses the one declared lattice or rectangle that qualifies (FR-455 R2, PFS-2081.56).
- Post matches every exported far-field position to the recorded layout, each set exactly once, and integrates with the recorded grid; a set it cannot match is a named skip. A record without a layout is matched to the table as it stands, by shape for the plane and a frame's lattice (PFS-2081.58).
- Trefftz A warns, naming the families and both lifts, where the traced families' lift departs from the solver's CL by more than 5 percent (FR-451 R13, PFS-2081.96).
- The far-field comparison columns `CDI_NEAR_PRESSURE` and `CDI_NEAR_VORTICITY` read the first column of the printed drag split, `CDp` on 26.125 (PFS-2081.98).
## Fixed
- Far-field post took a frame's lattice as the last points of the export and the plane by its point count, so a reused frame lattice followed by another probe entry, or a plane changed to another grid of the same count, was integrated with the wrong samples or the wrong area (PFS-2081.58).
- The far-field products of a `qsteady_rotor` point were skipped ("states no speed in the point's record"): the hub speed is read from the row's own quasi-steady record, as every other product reads it, signed once by the rotor's hand (FR-453 R8, PFS-2081.93).
- `CDI_NEAR_PRESSURE` and `CDI_NEAR_VORTICITY` were `NA` on every 26.125 point (PFS-2081.98).
## Migration
- The three far-field files gain a last column, `STATUS`.
- The C row's `CL_T` was `NA`; it is now the plane's own lift, and its `E_T` is still formed with the solver's CL.
- `post.farfield_fields.far_samples(samples, layout, *, per_m)` takes a `FarLayout` (`recorded_layout`, `derived_layout`) in place of `lattice_m`, `plane_count` and `lattice_tail`.
- FR-38 R8 states the measured limit of the balances on a quasi-steady wheel, whose exported probe field does not hold its own wake's circulation at mid stations on 26.124 and 26.125 (RPT-171).
