# RPT-099 - QS-NOISE route A against the unsteady_rotor acoustic signals of licensed round 3 (2026-09-30)

EXPLORATORY, by the owner's decision of 2026-09-29 ("em aberto, por enquanto
carater exploratorio"): QS-NOISE carries no threshold in dB and no gate, and
0.32.0 does not wait on it. This report compares route A of the 0.32.0 scope
(GEO-066 section 2.6 part 5) with the solver's own acoustic signals, says what
the comparison shows, and says what it does not. No solver ran for it: it reads
files a licensed run already wrote.

Only nondimensional values are stated: Mach numbers, the advance ratio, r/R,
k r, t/T (T one revolution), pressures over the free-stream dynamic pressure
`q`, ratios, correlations and counts. The sidecar
`RPT-099_qsteady-noise-route-a-against-round-3_2026-09-30.json` holds every
number below and the five records as p/q against t/T; the script that wrote it
is `C:/WORK/release-0320/probes/round3/rpt099_route_a.py`, run with this
branch's `src` on `PYTHONPATH`.

## 1. The model (FR-300 to FR-303)

`pyflightstream.post.qsteady_noise`, a library beside the post row, not wired
into the post stage:

- **The source.** Each blade is two compact point forces turning with it: the
  axial force at the centroid radius of the axial load, the in-plane force at
  the centroid radius of the torque. The force on the fluid is the negative of
  the load the solver reports on the blade.
- **The propagation.** The loading term of Farassat's Formulation 1A for a
  compact source in a medium at rest (F. Farassat, NASA/TM-2007-214853, 2007;
  K. S. Brentner and F. Farassat, Progress in Aerospace Sciences 39, 2003,
  section 3), near-field terms kept, every term at the retarded time. No
  thickness term.
- **The retardation.** The emission time is the root before the observer time
  of `|x(t) - y(tau)| = c0 (t - tau)`, by bisection; an observer may move.
- **The load against azimuth.** A least-squares Fourier series in azimuth of
  each force component, from blade samples at known azimuths (a wheel's
  clockings give `B k` samples of one blade), and the centroid radii from the
  mean moments.
- **The closed-form check.** Gutin's far-field harmonic of a steady rotor
  (Gutin 1936, in the form of M. E. Goldstein, Aeroacoustics, 1976, chapter 3;
  the compact steady limit of D. B. Hanson, AIAA Journal 18, 1980).

The tier-1 tests (`tests/tier1_offline/test_p0320_f_qsteady_noise.py`) hold
the model to closed forms before any comparison: the exact dipole field with
its near field, the Prandtl-Glauert convected dipole of a steady force in
uniform motion, the emission time of a source at rest and in uniform motion
(the root of a quadratic), the silence of an unloaded moving blade, the
Gutin harmonics to 0.5 per cent at a tip Mach of 0.5, and the recovery of a
load series from a wheel's clockings. Ten hand-made mutants of the model
(near-field sign, motion term, Doppler power, rate sign, blade spacing, Gutin
tangential term, centroid sign, bisection side, observer motion, azimuth sense)
are each killed by the suite.

## 2. The reference

POL 3201 of licensed round 3 (`C:/WORK/release-0320/probes/round3/`): the
`unsteady_rotor` row of package E2 on FlightStream 26.124, build 8172026,
executable SHA-256
withheld from the public tree per NFR-31. The
synthetic single blade `30_BLADE` (`pyflightstream.qa.geometry.BladeSpec`),
axis X, one blade, one revolution in 24 steps from an impulsive start,
acoustic sources ENABLE; its control POL 3202 is the same row with sources
DISABLE.

| Quantity | Value |
|---|---|
| Tip Mach number | 0.163 |
| Flight Mach number | 0.144 |
| Advance ratio J | 2.77 |
| Observers | five, each at r/R = 5.47 (k r = 0.89 at the shaft frequency, so in the near field) |
| In the disc plane | MIC_P (+Y), MIC_M (-Y), Observer 4 (+Z), Observer 5 (-Z) |
| On the axis, upstream | MIC_UP (-X) |
| Observer window | 16 samples, t/T from 0.24 to 0.92 |

Facts of the reference, read from the signals files: the thickness column
`PT` is zero in every row, `PO` equals `PL` in every row, and every pressure
of the control 3202 is zero. The solver's record is loading noise only, which
is what route A models.

## 3. What route A was fed, and why that is not the whole of route A

Route A proper reconstructs a blade's load against azimuth from the clockings
of a `qsteady_rotor` wheel. Round 3 has no `qsteady_rotor` run of this blade at
this point, so that input does not exist on disk. The comparison therefore
feeds the propagation with the unsteady run's own loads (the per-step force
and moment about the hub of `_plots.txt`. That file's footer reads "Force
Units: Coefficients", but its values are dimensional: the last step's force
and moment equal the point's final coefficients (`.txt` export) times `q` and
the reference area, and times the reference length for the moments, to the
fourth digit):

- **A0, history**: the 24 per-step loads, interpolated in time;
- **A1, quasi-steady**: the last step's load held as a steady load turning
  with the blade, which is what a quasi-steady solve would supply if it equalled
  the unsteady run's last step.

The blade and the point are the same as the reference's, so the propagation
half of route A is compared quantitatively. The reconstruction half (FR-301)
and the quasi-steady approximation of the loads themselves are NOT tested by
this report.

The blade's azimuth is inferred from the in-plane moment (the moment of the
axial force), step by step: 15.0 to 15.2 deg per step, positive about +X,
scatter about a uniform rotation 0.6 deg. The axial load on the blade points
-X (upstream thrust, as the `BladeSpec` convention states for a positive
rotation) and the tangential load opposes the rotation. Over the revolution the
axial load falls 6.2 per cent and the tangential 11.8 per cent (the starting
transient of one revolution); at the last step axial over in-plane is 0.52,
and the centroids sit at r/R 0.56 to 0.58 (axial) and 0.44 to 0.47 (in-plane).

## 4. What the comparison shows

Every measure is of the fluctuation about each record's own mean, over the 16
samples. Observer carried with the hub through the medium (the "tunnel" frame
of the JSON); holding the rotor at rest instead moves every in-plane level
below by at most 0.08 dB and every in-plane correlation by at most 0.01 (A0 at
MIC_UP by 1.0 dB and 0.04).

| Observer | A1 level vs reference (dB) | A1 correlation | A0 level (dB) | A0 correlation |
|---|---|---|---|---|
| MIC_P | +0.63 | -0.87 | +0.69 | -0.88 |
| MIC_M | -1.43 | -0.94 | -1.28 | -0.94 |
| Observer 4 | +1.05 | -0.92 | +1.28 | -0.93 |
| Observer 5 | +1.62 | -0.98 | +1.85 | -0.98 |
| MIC_UP | the steady model is constant here | | +19.0 | -0.93 |

1. **In the disc plane the level agrees within 1.9 dB and the shape agrees,
   with the opposite sign.** At the four in-plane observers route A's rms is
   0.85 to 1.24 times the reference's, and its record correlates with the
   reference at -0.87 to -0.98. Negated, the rms of the difference is 0.31 to
   0.53 of the reference's rms. In the disc plane the axial force radiates
   almost nothing, so these four observers test the in-plane (torque) force.

2. **On the axis upstream the reference is steady, as the steady model says,
   and again of the opposite sign.** MIC_UP's reference is almost constant:
   its fluctuation is 0.27 per cent of its mean and 0.1 per cent of MIC_P's
   fluctuation. A steady thrust turning on the axis radiates a constant there,
   and A1 is constant to rounding. The mean is +1.71e-5 q in the
   reference and -2.96e-5 q in A1 (ratio -1.73). This observer tests the
   thrust alone, and its sign depends on no azimuth and no time origin.

3. **A0's history is too unsteady on the axis.** Fed the per-step loads, the
   model puts the starting transient's drift into MIC_UP, 19 dB above the
   reference's fluctuation there. The reference does not show the transient
   that the loads export shows, at least not at the level the compact model
   gives it. In the plane A0 and A1 differ by 0.25 dB at most.

**The sign.** The model's sign is the textbook one and is pinned by the
tier-1 exact dipole test: a force on the fluid pointing at the observer raises
the observer's pressure, so upstream of a rotor that thrusts upstream the
steady near field is below ambient. The reference is above ambient there, and
anti-correlated in the plane: at all five observers it is the negative of the
model. The data are consistent with the solver's `PL` being computed from the
load ON THE BODY (or with the opposite sign convention for the pressure);
they do not decide it. A one-thing probe would: a non-rotating lifting wing
with one observer above and one below, whose suction side is known.

## 5. What this does not show

- It does not test the quasi-steady approximation of the loads, nor the
  reconstruction from a wheel's clockings: route A's own input was not run
  (section 3).
- No tonal level per harmonic: 16 samples over 0.68 of a revolution resolve no
  harmonic of the shaft, so the comparison is of time records, not spectra,
  and no Hanson or Gutin harmonic of the solver's record is read.
- One blade, one point, a low tip Mach number (0.163), five observers at one
  distance in the near field. Nothing about blade counts above one, thickness
  noise, or the far field.
- The factor 1.73 between the model's and the reference's on-axis means is
  unexplained. The compact source cannot be the reason at r/R 5.47 on the axis,
  where every point of the disc is nearly equidistant from the observer.
- The azimuth at the start inferred from the moments is 80.7 deg, where the
  `BladeSpec` convention puts the blade (along +Z) at 90 deg: 0.6 of a step,
  not resolved. It moves no correlation above by more than a few hundredths
  against the sign.
- One revolution from an impulsive start is shorter than the manual's advice
  of two for a rotor (SRC-751 p.210); the reference is a starting record.

## 6. Route B: not possible on this solver, so round 4 is not prepared

Route B would start a short unsteady run from the quasi-steady (steady)
solution, to record acoustic sources. The manual and the command database say
it cannot be done:

- the solver mode cannot be changed after the solver is initialised; it must
  first be uninitialised (SRC-751 p.197);
- uninitialising releases the solver's memory allocations and the boundary
  assignments (SRC-751 p.199, paraphrased), and on 26.124 a repeated `INITIALIZE_SOLVER`
  logs that the solution was cleared (RPT-069, T07, in the notes of
  `AUTO_DETECT_WAKE_TERMINATION_NODES` in `commands/boundary_conditions.yaml`);
- `SET_SOLVER_STEADY` and `SET_SOLVER_UNSTEADY` are both of the init phase in
  the command database, so the package's ordering check refuses them after
  `INITIALIZE_SOLVER`.

A solve continues from the existing solution only within one mode
(SRC-751 p.198, paraphrased), and a repeated unsteady run continues the previous block
(SRC-751 p.210): an unsteady run can be extended, but a steady solution cannot
seed it. No scripts were written under `probes/round4/`. The run that would
complete route A is instead a `qsteady_rotor` wheel of the same blade at the
same point, at several clockings, which supplies the input of section 3; it is
not prepared here.
