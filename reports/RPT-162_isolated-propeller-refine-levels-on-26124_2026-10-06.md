# RPT-162 - Isolated propeller comparison of refined mesh levels on 26.124 (2026-10-06)

FlightStream 26.124, build 8172026, far-field layers 5. The isolated propeller comparison of FR-424 (PFS-2079.07, GOAL-045 arm PR): one native mesh level of a six-blade propeller against the levels `pyfs-matrix refine` wrote from it at factors 1, 0.5 and 2, every level run with the same run type, setup, reference and post-processing. The acceptance is the owner's and is not stated here.

## Purpose

Show, on the licensed solver, that a level refined at factor 1 reproduces the native level, and how the rotor coefficients move along the refine sequence 0.5, 1, 2. Only one native level of the propeller exists, so the native-against-refined comparison is made at factor 1 and the sequence measures the mesh sensitivity of the refined family.

## Method

The geometry is a research propeller of six blades without spinner; its shape is withheld. Every blade is a grid family (a tube with zipper caps at both ends), so every level was resampled as a grid (FR-424 R6) and written in the native face order (R7). The levels were made with the 0.38.0 development tree (`pyfs-matrix refine MESH 1`, `0.5`, `2`, default output folder) and audited against the native mesh (FR-426); the factor-1 level's vertex and face lines equal the native file's, line for line. Run type `qsteady_rotor`, wheel, alpha 0, advance ratio 1.70 at the clock speed, Mach 0.1441, the same setup (far-field layers 5), reference and post for every row. The rotor table `P38NN-ROTOR_rotor.csv` of each point gives `CT_ROTOR`, `CP_ROTOR` and `ETA_ROTOR`. Every run converged.

| Level | Run id | Faces | Faces per blade |
|---|---|---:|---:|
| native | `ws/sim_3801/M144RE438AL+000BE+000RPM00473` | 5616 | 936 |
| R1 (factor 1) | `ws/sim_3802/M144RE438AL+000BE+000RPM00473` | 5616 | 936 |
| R0p5 (factor 0.5) | `ws/sim_3803/M144RE438AL+000BE+000RPM00473` | 1404 | 234 |
| R2 (factor 2) | `ws/sim_3804/M144RE438AL+000BE+000RPM00473` | 22032 | 3672 |

## Results

Relative change against the native level, `(level - native) / abs(native)`:

| Level | CT | CP | Efficiency |
|---|---:|---:|---:|
| R1 | +0.00% | +0.00% | +0.00% |
| R0p5 | -7.56% | -4.70% | -3.00% |
| R2 | +1.19% | +5.40% | -3.99% |

The factor-1 level reproduces the native level in every printed digit of the three coefficients, which is what the identical files predict. Along the sequence 0.5, 1, 2 the thrust coefficient converges: the change from 1 to 2 is about a sixth of the change from 0.5 to 1, an observed order near 2.7. The power coefficient does not converge on these three levels: it grows by a similar amount at each doubling (+4.9% from 0.5 to 1, +5.4% from 1 to 2), so the efficiency falls at both ends of the sequence. The audit of the 0.5 level warned that its size growth across neighbouring faces exceeds the native level's, which coarsening a clustered grid produces.

## Limits

One operating point, one propeller, one run type (quasi-steady); the power coefficient's trend needs a finer level, or a native level made at a different size in the pre-processor, to be read as convergence or as a property of the refined family. Absolute coefficients are kept in the private record of the release.
