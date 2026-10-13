# RPT-170 - Far-field probe field against the solver's own wake, 26.124 and 26.125 (2026-10-13)

## Scope and verdicts

Planning nodes PFS-2081.94 (the FR-38 balances of an isolated propeller do not close) and PFS-2081.95 (Trefftz C
on 26.124 carries about half the crossflow energy Trefftz A implies on a wing). Both read probe points exported by
the solver behind the body. The question of this report: does the exported probe velocity field hold the
circulation the solver's own wake carries, checked by Stokes' theorem, which no post-processing choice can move?

| Case | Build | Probe field against the wake | What the package does (0.40.0) |
|---|---|---|---|
| Wing, Trefftz C plane at 0.25 BREF | 26.124 | holds 0.79 of the root circulation the loads shed; its own lift is 0.74 CL | C row written with its own `CL_T`, WARNING (FR-453 R9) |
| Wing, Trefftz C plane at 0.25 BREF | 26.125 | holds 1.05 of it; its own lift is 1.05 CL | C row written, no flag; C and A agree to 2.2 percent in `CDI_T` |
| Six-blade wheel, quasi-steady, survey lattice | 26.124 and 26.125, identical to four digits | at x/R 0.5, 1.0 and 1.5 the swirl vanishes inside the radius where the solver's own tip lines cross | ledgers written; FR-38 R8 states the measured limit |

The post-processing integrals are not the cause in either case: they integrate the exported samples faithfully
(below). The cause is the exported field itself.

## What was read

Recorded runs, no new solve. Wing: an aspect-ratio-8 half wing mirrored (BREF 20 m, SREF 50 m), Mach 0.2,
alpha 4 deg, 160 section stations, the release default plane (+/-0.75 by +/-0.5 BREF at 0.01 BREF, 15,251 probes),
the same mesh and setup on both builds (wake refinement 1000 percent of the average mesh size, a wake grid of depth
9 on both, read in each probe export's header and log). Wheel: six blades, `qsteady_rotor`, J = 1.8, the release
default survey lattice (stations x/R -2, -0.2, 0.2, 0.5, 1, 1.5, 2; 40 rings; 72 azimuths), the solver's default wake
end (`WAKE_TERMINATION_X DEFAULT`, logged "Trefftz plane location" at x/R 2.08).

One licensed process (26.124, hidden, about two seconds): the wheel's saved simulation opened and its VTK exported
with the wake switched on (`OPEN`, `SET_VTK_EXPORT_VARIABLES -1 ENABLE`, `EXPORT_SOLVER_ANALYSIS_VTK`), no solve, to
read the wake lines the probes were computed with.

## The wing: circulation round the half wake

The circulation of the crossflow round a rectangle in the plane enclosing the right half wake (from just right of
the symmetry plane to y, all of the plane's height) equals the circulation the half wing sheds, which is the root
circulation of its loading (Stokes; a sheet's strength is the derivative of the bound circulation).

| Quantity | 26.124 | 26.125 |
|---|---|---|
| root circulation of the loading (Trefftz A, innermost station), m^2/s | 76.1 | 72.7 |
| circulation of the probe field, rectangle to y = 12 m, m^2/s | 59.6 | 76.2 |
| same, rectangle to y = 14 m | 60.4 | 76.2 |
| ratio probe / loading | 0.79 | 1.05 |
| lift of the plane's own vorticity, rho V sum y xi dS, over the solver's CL | 0.739 | 1.051 |
| same on the larger plane (+/-1 by +/-0.75 BREF at 0.025 BREF) | 0.771 | 1.047 |
| Trefftz B calibration factor (lift of the raw wake values to the near field) | 1.494 | 0.954 |
| crossflow energy C over A (`CDI_T`) | 0.50 | 0.978 |

On 26.124 the probe velocities carry 0.74 to 0.79 of the circulation and, the energy going as its square, about
half the crossflow energy; the solver's raw wake values are low by a similar factor (B's factor 1.494). On 26.125
both are within 5 percent. The plane's extent is not the cause (the larger plane moves the ratio from 0.739 to
0.771), nor the post quadrature (an independent sum of v^2 + w^2 over the 15,251 samples times rho/2 and the cell
area gives the post's `CDI_T` to three digits). An earlier refinement study of another wing on 26.124 recorded
the C span efficiency falling from 2.55 on the coarsest to 1.01 on the finest of five meshes, which is the sign of a
probe field whose induced velocity depends on the wake's resolution on that build.

## The wheel: the swirl the wake lines imply

Behind the blades only the wake lines cross a plane x, so the azimuthal mean of the swirl at radius r is the sum of
the strengths of the lines crossing inside r over 2 pi r (Stokes), up to the export's undocumented scale k (the same
k at every station). The 156 wake lines all reach x/R 2.08; the six tip lines stand at r/R 0.95 to 0.99 at every
station. Swirl, m/s, probe azimuthal mean against the lines (the lines' column in the export's scale, sign opposite
to the package's azimuth convention):

| x/R | r/R 0.316 | r/R 0.474 | r/R 0.637 | r/R 0.796 | r/R 0.938 |
|---|---|---|---|---|---|
| 0.2 | -5.90 / 4.25 | -7.48 / 6.97 | -5.79 / 6.93 | -3.96 / 6.29 | -1.55 / 3.52 |
| 0.5 | -6.88 / 5.90 | -5.51 / 6.97 | -3.16 / 7.28 | -0.90 / 6.24 | 0.01 / 3.20 |
| 1.0 | -6.63 / 5.90 | -0.28 / 7.25 | 0.01 / 7.28 | 0.01 / 6.19 | 0.00 / 2.86 |
| 1.5 | -7.38 / 5.90 | -4.36 / 7.53 | -1.25 / 7.28 | -0.01 / 6.13 | 0.01 / 2.87 |
| 2.0 | -5.83 / 5.90 | -7.57 / 6.97 | -6.73 / 7.28 | -4.63 / 6.19 | -2.03 / 2.53 |

The lines imply the same swirl profile at every station from 0.5 to 2.0, and the probes follow it at x/R 0.2 and
2.0 (k close to 1). At 0.5, 1.0 and 1.5 the probes' swirl vanishes outside r/R 0.86, 0.47 and 0.8 while the tip
lines still cross at about 0.97: the exported velocities there do not hold the circulation of the solver's own
wake. The axial balance follows the swirl: `FX_N` over the near-field thrust is 0.79, 0.35, 0.05, 0.20 and 0.86 at
x/R 0.2 to 2.0, and the torque flux the same ratios.

What the balance itself is checked against, on the same samples: the mass flow is constant to 6e-4 at every station
(coverage 1); the upstream station x/R -0.2 closes to -5.9 N (-0.3 percent of the thrust); downstream the flux is
carried by the pressure term (1433 of 1444 N at x/R 0.2, 1509 of 1559 N at 2.0), and the exported pressure is the
rotating-frame Bernoulli value of the exported velocity (ring r/R 0.555: rho Omega r v_theta = 204 Pa against the
exported p - p_inf 204 Pa at x/R 0.2, and 226 Pa against 228 Pa at x/R 2). Reversing the frame speed in the conversion sends the torque to -1.99e6 N m, so the
sense used is the one the field was solved in.

## Conclusion per build

- **26.124**: on the wing the probe field holds 0.74 to 0.79 of the shed circulation at this mesh; Trefftz C there is
  not the loads' induced drag. On the wheel see below.
- **26.125**: on the wing the probe field holds the shed circulation to 5 percent and C agrees with A (2.2 percent
  in `CDI_T`). On the wheel the same as 26.124, to four digits.
- **Both builds, quasi-steady wheel**: the exported probe velocities between x/R 0.5 and 1.5 violate Stokes' theorem
  against the solver's own wake lines; no momentum balance of that field can close. The FR-38 balances measure the
  exported field; their departure from the near-field thrust and torque on such a row is a property of the solver's
  probe field, stated in FR-38 R8.

What the package does: every Trefftz C row of a wing states `CL_T`, the lift of the plane's own streamwise vorticity,
and post writes a WARNING where it departs from the solver's CL by more than 10 percent (FR-453 R9); the C row and
its numbers are still written. The ledgers are written as measured, with the limit stated (FR-38 R8). Not settled:
which solver setting, if any, makes the 26.124 probe field converge at a given mesh, and why the wheel's probe field
departs at mid-stations; both are solver questions for the vendor.
