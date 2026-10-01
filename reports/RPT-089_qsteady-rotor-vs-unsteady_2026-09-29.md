# RPT-089 - The quasi-steady rotor against the unsteady rotor, measured (2026-09-29, amended 2026-10-01)

Amended 2026-10-01: the facts taken from the private campaign's results file are summarised, with their number, date, build and command, in RPT-131; no measurement of this report changed.

A summary of licensed runs on **FlightStream 26.124, build #8172026**, made on
this machine on 2026-09-28 and 2026-09-29 to decide how the `qsteady_rotor`
run type of 0.30.0 solves a rotor and how many clockings of its wheel it
needs. The geometry is a six-blade research propeller: one blade mesh copied
six times about the shaft by rotating its vertices in steps of 60 deg, one
body per blade, no spinner and no nacelle, no symmetry, trailing edges by the
solver's detection. Its geometry is not published; this report states only
the numbers it produced (the private results file they come from is summarised in RPT-131). Every run was one launch, serial, far field 5 layers.

## 1. The rotating free stream stands for the turning blade (steady)

One blade held still, the rotation carried by the free stream
(`SET_FREESTREAM ROTATION <frame> <axis> <rpm>`, the rotor's own hub frame,
axis and signed speed, 473.17 rev/min) and the steady solver, against the same
blade turning in an unsteady run after one revolution at the same azimuth:

| quantity | steady, rotating free stream | unsteady, turning blade | difference |
|---|---|---|---|
| axial force Fx (N) | -404.78 | -403.38 | 0.35 % |
| in-plane force Fy (N) | +363.12 | +372.47 | 2.5 % |

The axial coefficient agrees with the unsteady production run of the same
blade to 0.55 %. The sense of the free stream's rotation that reproduces the
turning blade is the motion's own: the same frame, the same axis, the same
signed rate. The steady run reports no viscous drag where the unsteady one
reports 5.09 N; that difference is not decided by these runs.

## 2. The whole wheel at an angle of attack: clockings against the unsteady rotor

The six-blade wheel at 5 deg angle of attack, 49.04 m/s, loads frame at the
origin. U: the unsteady rotor, all six blades turning, 10 deg per step, three
revolutions (108 steps), the last revolution averaged. Q: the blades held
still, the rotating free stream, one steady solve per clocking at 0, 10, 20,
30, 40 and 50 deg (six clockings of the 60 deg passage), averaged.

| component | U, last revolution | Q, mean of 6 clockings | (Q - U) / abs(U) | U ripple | Q spread |
|---|---|---|---|---|---|
| Fx (N) | -2022.76 | -2204.64 | -8.99 % | 11.6 | 10.6 |
| Fy (N) | +55.36 | -27.09 | opposite sign | 1.4 | 10.8 |
| Fz (N) | +320.52 | +257.75 | -19.6 % | 1.6 | 8.5 |
| Mx (N m) | -2274.67 | -2433.44 | -6.98 % | 10.7 | 7.5 |
| My (N m) | -54.83 | +44.68 | opposite sign | 1.6 | 13.2 |
| Mz (N m) | -410.73 | -345.45 | +15.9 % | 1.7 | 11.1 |

In coefficients (rho 0.6326 kg/m3, n 7.886 rev/s, D 3.648 m), U gives CT
0.2903 and CP 0.5623, Q gives CT 0.3164 (+9.0 %) and CP 0.6015 (+7.0 %). The
single blade's once-per-revolution load (counted on the blade: the blade
meets the non-uniform inflow once in each of its revolutions, not the
blade-passing excitation a fixed surface near the rotor feels, nor what a
balance summing every blade reads) has the same shape and amplitude in
both (about 650 N per blade in the in-plane force) and differs in phase and
level on the downgoing half of the disc, which is where the small in-plane
totals differ.

Wall time, one launch each, licence checkout included: U 102.7 s for three
revolutions; Q 10.8 s for all six clockings, about ten times less.

## 3. The control at zero angle of attack: the axial gap is the wake

The same wheel and setup at 0 deg, the unsteady rotor run to three and to six
revolutions:

| component | U, 3 rev (last) | U, 6 rev (last) | Q, 6 clockings | Q vs U3 | Q vs U6 |
|---|---|---|---|---|---|
| Fx (N) | -1993.71 | -2025.10 | -2177.54 | -9.22 % | -7.53 % |
| Mx (N m) | -2253.93 | -2282.82 | -2414.05 | -7.10 % | -5.75 % |

The in-plane components are near zero in both, as they should be (U within
0.3, Q within 4 N or N m, the clocking noise of the steady solution). The
axial gap is the same at 0 deg as at 5 deg, so it is not caused by the angle:
it is the steady wake against the time-accurate one, and the unsteady run is
still moving towards the steady answer. Revolution by revolution the
unsteady thrust is -2159.86 N (revolution 1, the start-up), then -1983.38,
-1993.71, -2004.01, -2014.46 and -2025.10 N (revolution 6): about 10 N, 0.5 %,
more each revolution and not yet levelled at revolution 6. A linear
extrapolation would reach the steady answer in about 15 more revolutions; that
extrapolation is not a measurement. The in-plane differences at 5 deg are
therefore attributed to the unsteadiness the angle creates (the phase and the
level of the once-per-revolution blade load), an inference from the two
controls.

## 4. How many clockings: the convergence study

The wheel at 5 deg, k uniform clockings in one 60 deg passage,
`theta_i = i x 60 / k`, for k = 1, 2, 3, 6, 12 and 24 (k = 1, 2, 3 and 6 are
subsets of the six of section 2; 12 and 24 were run for this study):

| k | Fx (N) | Fy (N) | Fz (N) | Mx (N m) | My (N m) | Mz (N m) | largest change from the previous k |
|---|---|---|---|---|---|---|---|
| 1 | -2210.56 | -23.37 | 258.84 | -2437.94 | 40.43 | -347.98 | - |
| 2 | -2206.12 | -23.81 | 257.17 | -2434.21 | 40.64 | -346.05 | 1.89 % (Fy) |
| 3 | -2207.84 | -27.53 | 260.58 | -2435.92 | 45.97 | -348.87 | 15.65 % (Fy) |
| 6 | -2204.64 | -27.09 | 257.75 | -2433.44 | 44.68 | -345.45 | 2.80 % (My) |
| 12 | -2203.95 | -27.46 | 258.21 | -2432.96 | 45.16 | -345.95 | 1.38 % (Fy) |
| 24 | -2203.82 | -27.57 | 258.23 | -2432.82 | 45.27 | -345.95 | 0.41 % (Fy) |

- Thrust and torque (Fx, Mx), and the larger in-plane Fz and Mz, are converged
  to better than 0.2 % from k = 2.
- The small in-plane Fy and My, tens of N set against a clocking noise of
  about 13 N, need more: at k = 6 all six components are within 1.6 % of the
  k = 24 values (Fx within 0.04 %), and they change by less than 0.5 % only
  from k = 12 to k = 24.
- More clockings do not close the in-plane difference with the unsteady rotor
  of section 2: at every k, Fy stays near -27.5 N against +55.4 N, and Fz and
  Mz keep their -19 % and +16 % gaps.
- The wall time grows linearly, about 1.7 s per clocking: k = 6 is about ten
  times cheaper than three unsteady revolutions, k = 24 still 2.4 times.

## 5. The unsteady rotor's time step: a finer step moves it towards the steady answer

Sections 2 and 3 ran the unsteady rotor at 10 deg per step. The same wheel was
run again at 5 deg and at 2.5 deg per step, with only the step (`DELTA_TIME`)
and the step count (`TIME_ITERATIONS`) changed and the wake settings
identical. Six revolutions at 2.5 deg were not run: estimated at about 56 min
from the growth measured at 10 deg, they exceeded the time allowed per run.
Three revolutions at 2.5 deg were run instead, the same 432 steps as six
revolutions at 5 deg.

At 0 deg angle of attack, per revolution, against the quasi-steady wheel
(Q, six clockings: Fx -2177.54 N, Mx -2414.05 N m); the gap here is
(U - Q) / abs(Q), the unsteady value's distance below the steady one:

| revolution | Fx 10 deg | Fx 5 deg | Fx 2.5 deg | Mx 10 deg | Mx 5 deg | Mx 2.5 deg |
|---|---|---|---|---|---|---|
| 1 | -2159.86 | -2106.45 | -2087.42 | -2418.04 | -2364.38 | -2344.50 |
| 2 | -1983.38 | -2015.51 | -2052.15 | -2244.40 | -2278.71 | -2314.50 |
| 3 | -1993.71 (8.44 %) | -2034.90 (6.55 %) | -2089.88 (4.03 %) | -2253.93 (6.63 %) | -2296.68 (4.86 %) | -2349.45 (2.68 %) |
| 4 | -2004.01 | -2054.23 | | -2263.43 | -2314.58 | |
| 5 | -2014.46 | -2073.53 | | -2273.04 | -2332.37 | |
| 6 | -2025.10 (7.00 %) | -2092.71 (3.90 %) | | -2282.82 (5.44 %) | -2349.99 (2.65 %) | |

The in-plane components stay within 0.2 N or N m of zero in every run at 0 deg.

- A finer step raises the mean thrust at every revolution: at revolution 3 the
  Fx gap is 8.4 % at 10 deg, 6.6 % at 5 deg and 4.0 % at 2.5 deg (Mx 6.6, 4.9
  and 2.7 %); at revolution 6 it is 7.0 % at 10 deg and 3.9 % at 5 deg.
- It also changes the drift, which roughly doubles each time the step is
  halved: Fx gains 10.4 N per revolution from revolution 2 to 6 at 10 deg,
  19.3 N at 5 deg, and 37.7 N from revolution 2 to 3 at 2.5 deg (one interval
  only). No step had levelled off by its last revolution, so neither the step
  nor the revolution count is converged, and both move the unsteady rotor
  towards the quasi-steady one.
- The start-up dip after revolution 1 is shallower with a finer step
  (revolution 2: -1983, -2016 and -2052 N).

At 5 deg angle of attack, 5 deg per step, six revolutions, against the
quasi-steady wheel at k = 24 (section 4) and the 10 deg unsteady run of
section 2:

| component | Q (k = 24) | U 10 deg, rev 3 | U 5 deg, rev 3 | U 5 deg, rev 6 | U 5 deg rev 6 against Q |
|---|---|---|---|---|---|
| Fx (N) | -2203.82 | -2022.76 | -2062.81 | -2123.73 | 3.6 % below |
| Fy (N) | -27.57 | +55.36 | +42.07 | +41.66 | opposite sign |
| Fz (N) | +258.23 | +320.52 | +287.82 | +288.34 | 11.7 % above |
| Mx (N m) | -2432.82 | -2274.67 | -2317.23 | -2373.38 | 2.4 % below |
| My (N m) | +45.27 | -54.83 | -35.89 | -35.25 | opposite sign |
| Mz (N m) | -345.95 | -410.73 | -372.15 | -374.32 | 8.2 % larger in magnitude |

- The in-plane disagreement shrinks with the finer step: at revolution 3, Fz
  goes from 24.1 % above Q at 10 deg to 11.5 % at 5 deg, and Mz from 18.7 %
  to 7.6 % above Q in magnitude; Fy goes from +55.4 to +42.1 N and My from
  -54.8 to -35.9 N m.
- Unlike Fx and Mx, the in-plane loads are nearly flat from revolution 2 to 6
  at 5 deg (Fy 42.2 to 41.7 N, Fz 287.6 to 288.3 N): they follow the step,
  not the length of the wake.
- The signs of Fy and My do not change: the unsteady rotor stays near
  Fy +42 N and My -35 N m, against the quasi-steady -27.6 N and +45.3 N m.

Wall time, one launch each, licence checkout included:

| run | angle of attack | revolutions (steps) | wall time (s) |
|---|---|---|---|
| unsteady, 10 deg per step | 0 | 3 (108) / 6 (216) | 101.9 / 236.5 |
| unsteady, 5 deg per step | 0 | 6 (432) | 780.4 |
| unsteady, 2.5 deg per step | 0 | 3 (432) | 1457.8 |
| unsteady, 10 deg per step | 5 | 3 (108) | 102.7 |
| unsteady, 5 deg per step | 5 | 6 (432) | 1105.4 |
| quasi-steady wheel, k = 6 / k = 24 | 5 | - | 11 / 42 |

At a fixed step the cost grows faster than the step count (at 10 deg, 2.3
times from three to six revolutions). The finer unsteady reference costs 780
to 1458 s against 11 to 42 s for the quasi-steady wheel.

## What the package takes from this

- `qsteady_rotor` solves the blades held still in `SET_FREESTREAM ROTATION` at
  the rotor's hub frame, shaft and signed speed (section 1).
- A wheel in an inflow that varies around the disc is solved at
  `PASSAGE_POSITIONS` = k clockings inside one passage and averaged; the
  guidance is k = 2 for thrust and torque and 6 or more for the in-plane
  loads (section 4).
- Its in-plane loads at an angle are quasi-steady estimates (sections 2 and
  3), and its thrust and torque sit about 7 to 9 % above an unsteady rotor
  averaged after three to six revolutions at 10 deg per step, a gap the
  unsteady run was still closing at about 0.5 % per revolution (section 3)
  and one a finer unsteady step narrows, to about 4 % at 5 deg per step and
  six revolutions (section 5).
- The unsteady rotor's own guidance: a mean thrust taken from few
  revolutions, or at a coarse time step, sits below the developed wake's; a
  finer step raises it too, not only more revolutions (section 5).

## What this does not establish

- The package's own `qsteady_rotor` scripts have not run on a licensed solver
  at this writing: these runs were hand-built scripts of the same commands.
  In particular the clocking of the wheel inside one launch by
  `ROTATE_SURFACE` and a second `INITIALIZE_SOLVER` is not measured (the runs
  above clocked the wheel from a new simulation per clocking), and neither is
  a custom inflow file with the rotation added by the package, against the
  rotating free stream.
- Where the unsteady rotor's thrust levels off; the extrapolation of
  section 3 is not a measurement.
- A time step at which the unsteady rotor is converged: no step run here
  (10, 5 and 2.5 deg) had levelled off by its last revolution, and six
  revolutions at 2.5 deg were not run (section 5).
- Any geometry but this six-blade propeller.
