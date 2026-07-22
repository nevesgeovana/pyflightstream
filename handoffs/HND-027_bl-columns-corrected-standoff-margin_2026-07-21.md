# HND-027: BL-column finding corrected, standoff margin delivered (2026-07-21)

## 1. Context

Geovana corrected the HND-024 side finding: SET_SOLVER_VISCOUS_COUPLING
concerns the viscous effect on the integrated loads (CL), not the
probe-export boundary-layer columns, whose model lives in Advanced
Settings. She also asked for the standoff margin (the HND-024
recorded option) to be implemented now.

## 2. The correction, settled empirically (RPT-004 erratum)

Three control runs on the same 1628-probe case (26.120 build 7012026,
identical convergence at iteration 58): defaults,
REYNOLDS_AVERAGED_DRAG_FORCES DISABLE, and that plus
SET_SOLVER_VISCOUS_COUPLING DISABLE plus SET_INVISCID_LOADS ENABLE.
The 37 near-wall probes kept their BL columns in every variant; the
1591 probes away from the wall exported zeros in every variant,
defaults included. Conclusion for this build: the probe-export BL
columns are evaluated at UPDATE_PROBE_POINTS geometrically, for
probes near the wall, regardless of the scripting-side viscous
toggles (the Advanced Settings scripting chapter, SRC-003
pp.344-346, holds no further boundary-layer switch; the manual read
confirmed the chapter's full command list en route). Geovana's
correction stands confirmed for the coupling flag; the practical
consequence inverts the HND-024 advice: the DLV-006 inert-BL
assertion is satisfied by keeping probes off the wall, not by
toggles. RPT-004 carries the erratum and the variant table; the
EXPORT_PROBE_POINTS database note is corrected.

## 3. Standoff margin (delivered)

`apply_geometry_gate(..., standoff=d)` now also discards probes
hugging the surface closer than the margin, for base and
refinement-band candidates alike, with separate accounting
(`base_standoff_culled`, `refined_standoff_culled`, `standoff`) in
the GeometryGateReport; a probe on the wall samples the body's
surface state, not the flow (the RPT-004 zero-velocity leading-edge
node is the motivating case, and the margin also keeps planar grids
clear of the geometric BL-column zone). Standoff without a mesh
refuses didactically. Hand-computed cube test: 12 wall-hugging nodes
culled at margin 0.15, kept count exact.

## 4. State at close

Suite at 274 green. No plan rows opened or closed: the standoff was
the recorded option of PLN-018's note, now delivered; the BL
correction is an erratum inside RPT-004. Parallel M6/FSI session
active in the worktree (aeroelastic command family, RPT-005); its
files stay untouched.

## 5. Single highest-value next action

Unchanged from HND-024, now with the corrected guidance: wire the
planar survey into a case recipe and start the G1-G5 far-field
checks, keeping every survey probe outside the standoff of the wall
rather than relying on solver toggles for BL inertness.
