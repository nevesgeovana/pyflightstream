# RPT-007: PLN-020 soft-blade pilot and the mesh-morphing investigation (2026-07-21)

Continuation of the WP7 line (RPT-006) on FlightStream 26.120 build
7012026: the beta(r) rotor-frame embedding landed (commit 5e47df6),
the soft-blade coupled pilot ran, and an anomaly in its response led
to a controlled investigation whose conclusion reinterprets part of
the pilot evidence. All runs on the licensed machine, generic
synthetic blade and wing only.

## 1. Soft-blade pilot (stiffness scale 1)

Same vehicle as RPT-006 with EI 1e5 N m2, GJ 2e3 N m2, 90 steps
(2.5 revolutions), `time_increment_s` configured (the RPT-006 dt
remedy: phase boundaries landed exactly at 18/36 steps). Config hash
`6d44efec...`; convergence log committed as
`reports/fsi/PILOT-26120_2026-07-21_soft_convergence.csv`.

* Structural response: tip elastic twist -1.029 deg (nose down,
  monotonic root to tip), tip flap +4.86 mm toward the suction side,
  inner iteration at 3 solves per call. Both directions match the
  physical expectation (cambered section's nose-down quarter-chord
  moment plus propeller moment; thrust-side bending), corroborating
  the projection signs of `project_rotor_frame_loads` (RPT-006
  finding 3): the export moment column is positive nose-down.
* Phase machine in-solver, complete: phases 1/2/3/4 executed
  17/18/37/18 calls; convergence declared at revolution 2 (tip twist
  change 0.0002 deg under the 0.05 deg tolerance); phase 4 ran
  unrelaxed (lambda 1) recording all 18 steps of the final half
  revolution. This closes RPT-006 finding 4 (phase 4 previously
  unexercised in-solver).
* Frozen replay of the final deformation (max 4.24 mm): reproduces
  the coupled solution to 5e-6 or better on CL, CDi, CDo, CMy over a
  full 90-step replay, held rows written verbatim on every call.

## 2. The anomaly

At matched run length (90-step near-rigid baseline, scale 1000), the
soft run's metrics differ from near-rigid by at most 6.2e-6 in CDi -
a 1 deg tip twist and 5 mm flap changing thrust by 0.014 percent.
Per-section sectional loads differ by at most 0.18 percent. A 1 deg
pitch change on this operating point should move local loading by
percent-to-tens-of-percent levels: the aerodynamics were not seeing
the deformation.

## 3. Controlled elimination on the rotor case

Frozen 6-step probes holding an unmistakable deformation (0.10 m tip
flap plus 5 deg nose-down twist), all against a rigid 6-step
reference (max per-section normal-density shift, integrated CDi):

| Probe | Variation | Result |
|---|---|---|
| norbf | as the pilot (no AEROELASTIC_RBF_TYPE) | 0.09 percent, CDi unchanged |
| wendland | AEROELASTIC_RBF_TYPE WENDLAND_C2 | identical to norbf |
| iter2 | SET_AEROELASTIC_ITERATIONS 2 (12 calls for 6 steps) | 0.24 percent, unchanged |
| preinit | aeroelastic block before INITIALIZE_SOLVER | identical |
| decimal | FSIDisp in plain decimals (no exponents), batch-file executable | identical |
| garbage | non-numeric FSIDisp | FlightStream crashes (0xC0000005) |

The garbage crash proves FSIDisp is read and parsed every step (and
records a solver robustness note: a malformed displacement file is an
access violation, not an error message). The command grammars were
re-verified letter by letter against SRC-003 pp.375-376.

## 4. The motionless control: morphing works

A static full-span NACA 0012 wing (no motion definition), 6-step
unsteady solve at 5 deg, the same aeroelastic block, structural nodes
on the mid-chord span line, and a batch executable holding FSIDisp
fixed:

| Metric | Flat FSIDisp | Bent (0.4 m tip bend) | Delta |
|---|---|---|---|
| CL | +0.4803 | +0.8577 | +0.3774 |
| CDi | +0.0096 | +0.0339 | +0.0243 |
| CMy | -0.1246 | -0.3328 | -0.2082 |

The identical command sequence and file formats deform the mesh and
move the loads decisively when the boundary has no motion.

## 5. Conclusion and consequences

On 26.120 build 7012026, the FSIDisp deformation is not applied to
boundaries attached to a rotary motion definition: the coupling loop
runs end to end (per-step loads export, executable call, displacement
file read), but the solid-body morphing documented at SRC-003 p.273
is silently dropped for the rotating boundary. The 26.1 release notes
(SRC-215) list the scriptable toolbox and the five RBF morphing
algorithms with no such limitation, so this is recorded as a
candidate solver defect for the vendor.

* Two-way rotor FSI is blocked in this build. The RPT-006 near-rigid
  acceptance stands mechanically (54/54 coupled calls, counters,
  files), but its "recovers the rigid baseline" outcome must be read
  as trivially insensitive: with morphing dropped, any stiffness
  recovers the rigid baseline. The wing control proves the
  pyflightstream side of the interface (commands, formats, node
  layout, displacement writer) is correct end to end.
* The soft pilot's structural response is the one-way (rigid-blade
  loads) response: valid as a structural result and as the projection
  sign corroboration, not as coupled aeroelasticity.
* PLN-020 is implementation-complete and solver-blocked for the
  rotor two-way validation; the motionless path (static aeroelastic
  wing) is available for a genuine two-way pilot in the meantime.

## 6. Side findings

* SET_SIGNIFICANT_DIGITS does not reach the sectional loads export:
  at 8 (the manual's maximum, SRC-003 p.284) the header still prints
  dt with three decimals and the rows keep four mantissa digits. The
  `FsiConfig.time_increment_s` remedy of RPT-006 is the correct and
  sufficient fix (validated in the soft pilot: phases at exactly
  18/36).
* The 26.1 release notes record a fixed unit-conversion bug in this
  very export (Pound-force versus Newtons), consistent with the
  RPT-006 per-span-density reading of the file being a quirk-prone
  area.

## Pending

* Vendor-facing question on the motion-plus-morphing defect
  (author's call; the probe pair rigid/norbf/wendland versus the wing
  control is the reproducible evidence package).
* PLN-019 sweep unchanged; the family notes in
  `aeroelastic_coupling.yaml` now carry this finding.
* Optional interim two-way pilot on the static wing (no solver
  defect in the way); the rotor near-rigid Tier 3 regression stays
  meaningful as a loop-mechanics regression.
