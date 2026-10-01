---
report: RPT-132
exploratory: true
requirement: FR-337
---

# RPT-132 - The sign of QS-NOISE route A against the unsteady acoustic reference (2026-10-01)

EXPLORATORY (FR-337). This report sets no threshold, and no check, gate or
plan status reads it; the noise product of FR-300 is unchanged by it. It
studies the sign disagreement RPT-099 found between route A of QS-NOISE and the
solver's own acoustic record of licensed round 3 (RPT-098). No solver ran for
it: it reads files the licensed round already wrote (POL 3201 of round 3, the
`unsteady_rotor` row with its acoustic sources on) and the committed sidecar of
RPT-099.

Only nondimensional values are stated: the tip and flight Mach numbers, r/R,
k r, angles, ratios and correlations. The sidecar
`RPT-132_qsnoise-route-a-sign_2026-10-01.json` holds every number below. The
script that wrote it, `rpt132_sign.py`, reads every dimensional value from the
round's own files and states none; it stays with the round's local files
(`<local probe folder>/round3/`), as the script of RPT-099 does, and runs with
this branch's `src` on `PYTHONPATH`.

## 1. The question

RPT-099 fed the propagation half of route A (`pyflightstream.post.qsteady_noise`)
with the unsteady run's own blade loads and found, at all five observers, a
record that matches the reference in level and in shape and is its negative:
correlation -0.87 to -0.98 in the disc plane, and an on-axis upstream mean of
the opposite sign. It did not say which term of the model disagrees, nor
whether the cause is a sign, a rotation sense, a time origin or a frame. This
report asks:

1. What sign convention does each side use?
2. Which term flips: the whole loading term, one of its brackets, one of the
   two compact sources, or no term at all (a frame, a sense or an origin)?

## 2. The two conventions

**Route A (the model).** The loading term of Farassat's Formulation 1A for a
compact source, three brackets taken at the emission time: the far bracket
(`Ldot_r / (c0 r (1 - M_r)^2)`), the near bracket
(`(L_r - L_M) / (r^2 (1 - M_r)^2)`) and the motion bracket (the term in
`Mdot_r` and `M_r - M^2`). `L` is the force the surface exerts ON THE FLUID, the
negative of the load the solver reports on the blade; `rhat` points from the
source to the observer; the pressure is the overpressure `p - p0`. The tier-1
test `test_a_point_force_at_rest_gives_the_exact_dipole_field_fr_300` pins this:
a force on the fluid pointing at the observer raises the observer's pressure.
Each blade is two compact sources: its axial force at the axial centroid and
its in-plane force at the torque centroid.

**The load the model is fed.** The per-step force and moment of the run's
`_plots.txt`. Its sign is physical on two counts: the axial load on the blade
points along -X, upstream (the thrust of a propeller flying into a free stream
that moves along +X), and the tangential load opposes the rotation (an absorbed
torque). The input does not carry the flip.

**The reference (the solver).** The `PL` column of the acoustic signals file
(`PO` equals `PL` and `PT` is zero in every row of this run, RPT-099). The
toolbox's manual pages (SRC-003 pp.374 and 380) do not define `PL`, `PT` and
`PO`, nor the sign of either the pressure or the load they use. The vendor
states no convention, so the reference's convention is what this report
measures.

## 3. What was tested

**The source.** The A1 variant of RPT-099: the last step's load held as a
steady load turning with the blade, the azimuth at the start inferred from the
moments (80.7 deg), observers carried with the hub through the medium. Each of
the two sources is split into its three brackets, six pressures per observer;
their sum equals the package's `rotor_loading_noise` to a relative 1e-12 at
every observer, which the script asserts.

**The reference, larger than RPT-099's.** Besides the five observers, the run
wrote an acoustic section in the disc plane (RPT-098 listed its 16 files and
did not read them): 24 points per file on three rings, r/R 2.73, 4.10 and 5.47,
at seven distinct azimuths 51.4 deg apart (the eighth repeats the first), so
21 distinct points. A fact measured here for the first time: the section's
file k holds observer time k. The outer ring's point at azimuth 0 is MIC_P's
point, and its value equals MIC_P's sample k in all 16 files to the last digit
written (largest relative difference 0). The in-plane test therefore has 25
records (four observers and 21 section points) at three values of k r (0.45,
0.67 and 0.89), and MIC_UP on the axis upstream hears the axial source alone.

**The hypotheses.** Each changes one thing of the model and is scored against
the reference by the pooled in-plane normalised rms difference (each record
about its own mean; 0 is a perfect match, 1 is no better than silence) and by
the ratio of MIC_UP's mean, model over reference (+1 is the right sign and
size).

| | Hypothesis | In-plane rms difference | In-plane correlations | MIC_UP mean ratio |
|---|---|---|---|---|
| H0 | the model as it is | 2.02 | -0.98 to -0.85 | -1.73 |
| H1 | every term negated (the load on the body, or `p0 - p`) | 0.366 | 0.85 to 0.98 | +1.73 |
| H2 | the axial source alone negated | 2.04 | -0.98 to -0.85 | +1.79 |
| H3 | the in-plane source alone negated | 0.373 | 0.85 to 0.98 | -1.79 |
| H4 | the far bracket alone negated | 1.64 | -0.68 to 0.59 | -2.25 |
| H5 | the near and motion brackets alone negated | 1.23 | -0.59 to 0.68 | +2.25 |
| H6 | the observers inverted through the hub | 0.610 | 0.65 to 0.98 | +1.79 |
| H7 | the rotation sense reversed | 1.61 | -0.97 to 0.83 | -1.73 |
| H8 | the azimuth origin moved by half a turn | 0.610 | 0.65 to 0.98 | -1.73 |
| H9 | the rotation sense reversed and every term negated | 1.31 | -0.83 to 0.97 | +1.73 |

## 4. What was found

1. **The rotation sense agrees, without the model.** On the outer ring the
   first azimuthal harmonic of the reference's in-plane pattern turns at
   0.994 times the shaft rate, in the same sense as the model's (1.000). A
   reversed sense (H7, H9) is excluded.

2. **The whole loading term flips, not one bracket.** The phase of the first
   shaft harmonic, reference against the negated model (H1), is -20.5, -20.3
   and -21.2 deg on the three rings (k r 0.45, 0.67 and 0.89): the same at
   every radius. The near and far brackets stand in a ratio that grows with
   k r, so a flip of one bracket leaves a phase that drifts with radius:
   negating the far bracket alone leaves 111, 91 and 75 deg, the near and
   motion brackets alone -69, -89 and -105 deg, a drift of 37 deg that the
   reference does not show. The least-squares gains of the far and near
   brackets are -1.00 and -0.90 (the motion bracket held at +1; -1.03 and
   -0.91 held at -1): both negative and both of unit size.

3. **Both sources flip.** In the plane the axial force radiates little, so
   negating the in-plane source alone (H3, 0.373) fits as well as negating
   everything (H1, 0.366). MIC_UP decides: it hears the axial source alone,
   and H3 leaves its mean with the wrong sign (-1.79) where H1 gives the right
   one. The axial and the in-plane sources both carry the flip.

4. **It is a sign, not a frame or an origin.** Inverting the observers through
   the hub also negates a compact dipole, but it fits the plane worse even at
   its own best azimuth shift (0.443, at 26.5 deg, against 0.227 for H1 at
   its best, finding 5). Moving the azimuth origin by half a turn (H8)
   negates the plane's harmonic but leaves the on-axis mean, which depends on
   no azimuth and no time, with the wrong sign.

5. **After the negation, what remains is a lag of one time step.** Scanned at
   0.5 deg, the azimuth shift that best fits the negated model is +15.0 deg,
   1.00 step of the 24-step revolution; the in-plane rms difference falls from
   0.366 to 0.227 and a single gain reads -0.93. The reference places the blade
   one step further on than the loads export does. This is what a loads row k
   that belongs to the time (k - 1) of a step, or an acoustic time origin one
   step earlier, would give; this report does not decide which. With the shift
   the azimuth at the start is 95.7 deg, where the `BladeSpec` convention puts
   the blade at 90 deg (the nominal 90 deg fits at 0.252).

6. **The sizes.** At the best shift the in-plane source's gain is -0.92 and the
   axial source's -0.61; the per-point first-harmonic amplitude ratios,
   reference over model, are 0.80 to 1.09. The factor 1.73 between the on-axis
   means (RPT-099) is the axial source's alone: the reference's axial loading
   noise is about 0.6 of the model's, its in-plane loading noise about 0.9.

**The answer to the two questions.** The model's convention is the textbook
one, pinned by its tier-1 test. The solver's record is the negative of it in
every term that can be measured here: both sources, the near and the far
brackets together, at every radius, with the rotation sense, the frame and the
time origin (to one step) agreeing. That is what a `PL` computed from the load
ON THE BODY (the force the fluid exerts on the blade), or a `PL` reported as
`p0 - p`, would give. It is a convention of the reference, one sign for the
whole loading term, and not a defect of one term of route A.

## 5. What this does not decide

- **Which of the two conventions.** A load on the body and a pressure counted
  as `p0 - p` give the same `PL` in every record, so no `PL` record separates
  them. The thickness column would: thickness noise does not depend on the
  load, so a `PT` of the textbook sign beside a negated `PL` puts the flip in
  the load, and a negated `PT` puts it in the pressure. `PT` is zero in every
  row of round 3, and why is not known. This needs a licensed run whose record
  carries a nonzero `PT`; it is not prepared here. The non-rotating wing probe
  that RPT-099 proposes would confirm the negation free of any azimuth or time
  origin, but it cannot separate the two conventions either.
- **The motion bracket's sign.** In the plane its rms is 0.046 of the near
  bracket's (the far bracket's is 0.52). Left free, its gain reads +3.8 and
  the residual falls to 0.037; held at +1 the residual is 0.129, held at -1 it
  is 0.208. A component of that shape about four times the bracket's size,
  with the sign of the unnegated model, is in the reference; whether it is the
  solver's motion term, an effect of a distributed source the compact model
  lacks, or the starting transient is not decided.
- **The side of the one-step lag**: the loads export's step index, or the
  acoustic time origin.
- **The axial factor** of about 0.6 against about 0.9 in the plane, which
  RPT-099 already left unexplained; a compact source cannot be the reason on
  the axis.
- **Route A proper.** As in RPT-099, the source is the unsteady run's last
  step held steady (A1): the reconstruction from a `qsteady_rotor` wheel's
  clockings (FR-301) and the quasi-steady approximation of the loads are not
  tested. One blade, one point, a tip Mach number of 0.163, k r up to 0.89 (the
  near field), one revolution from an impulsive start.
- **Any change to the product.** The study suggests no change to FR-300:
  route A's convention is the textbook one. A comparison with this solver's
  record negates its `PL` and allows for the one-step lag; that is a reading
  of this report, not a rule of the package.
