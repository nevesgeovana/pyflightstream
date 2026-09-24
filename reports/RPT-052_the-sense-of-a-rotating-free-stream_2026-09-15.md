# RPT-052: the sense of a rotating free stream (2026-09-15)

**WHAT THIS SETTLES.** From 0.21.0 a matrix row states one body rate --
`roll_rate`, `pitch_rate`, `yaw_rate` -- in deg/s and in flight-mechanics
signs, and the script writes `SET_FREESTREAM ROTATION <frame> <axis> <rev/min>`
about the moment reference point instead of `SET_FREESTREAM CONSTANT` (FR-105).
The package emits the rate AS WRITTEN. **What the solver does with a positive
angular velocity about a frame axis is stated by no edition of the manual**,
and this report is the measurement that decides whether the emitted sign means
what a flight-mechanics rate means.

**THE VERDICT: it does.** A positive `pitch_rate` produces the flow field of a
NOSE-UP rotation on FlightStream 26.124, so
`cases.workflows.FREESTREAM_ROTATION_SIGN` stays `+1`.

## The question a fixture cannot answer

A fixture can assert that the command is written, with the frame the reference
declares and the rate converted to rev/min. It cannot say which way the flow
then turns: that is a property of the solver, and the manual's page on
`SET_FREESTREAM` (SRC-003 p.322) gives the arguments and not the sense.

The consequence of getting it wrong is silent. A row asking for a pull-up would
be solved as a push-over: every coefficient plausible, every residual clean, and
the damping term of the wrong sign.

## What was run

One workspace, three points, ONE THING MOVED between them: the rate.

    workspace   GeoverseResearch/tools/fts_workspace/pfs0210-probe-rotation
    geometry    30_WB.fsm, the wing-body of pfs0160, READ and never written
    build       FlightStream 26.124
    row         MACH:0.2, REmi:11.7716754, ALPHA:sweep, BETA:0.0, pitch_rate:<rate>
    points      alpha 2 deg, pitch_rate 0.0, 4.0 and 40.0 deg/s
    reference   SREF 50.0, CREF 2.526, BREF 20.0, MRP at x = 9.152 m
    axes        [body_axes] roll = X, pitch = Y, yaw = Z

**WHAT DIFFERS BETWEEN THE TWO SCRIPTS THAT RAN**, taken from the files
themselves and not from a rendering made beside them. 102 lines each and
EIGHTEEN differing lines:

```
-SET_FREESTREAM CONSTANT
+SET_FREESTREAM ROTATION 2 Y 0.6666666666666666
```

and SIXTEEN lines of two kinds. Fourteen are export names, seven names each
written on both sides, which follow from the point name because 0.21.0 names
every file of a point by it (`P4101-...Q+000` against `P4102-...Q+040`). The
other two are the line naming the simulation's own input mesh,
`sims/sim_4101/inputs/30_WB.fsm` against `sims/sim_4102/inputs/30_WB.fsm`,
which follows from the SIMULATION ID and not from the point name. **Those two
files are byte-identical**, sha256 `3a5f174c...`, recorded per simulation in the
evidence: the path differs and the geometry does not. ONE PHYSICAL LINE
DIFFERS; the rest is naming, and it could not be otherwise on a release whose
names carry the rate.

The same eighteen lines of the same three kinds separate the baseline from the
40 deg/s point, `sim_4101` against `sim_4103`, and that diff is committed
beside this one. It is the pair that carries the verdict: the 4 deg/s
increment is 0.6% of the base and could be argued with, and the 40 deg/s one is
4.7%.

The report's first writing said "102 lines each, ONE differing line", which was
a diff of two cases rendered offline with their output templates unrendered:
not the scripts whose digests the evidence records. The V&V lens of 2026-09-16
caught it and, on the closing round, caught what the fix still claimed.
**THE CONTROL IS RECORDED, NOT CHECKABLE FROM THIS REPOSITORY ALONE.** The two
scripts are not committed (they carry this machine's absolute paths and live in
the probe workspace), so a reader here has the diff as this session transcribed
it. What the record does buy is real and is the reason it is here: each side
carries its script's sha256, so anyone holding the workspace can recompute both
digests and the diff and find them or not find them, and a later edit to either
script breaks the digest rather than the prose.

Frame 2 is the `MRP` coordinate system the builder creates at the reference's
moment point; `Y` is the axis `[body_axes]` gives the pitch rate; 0.6667 rev/min
is 4 deg/s.

All three points converged.

## What came back

Group 1 is the airframe, group 2 the wing alone, group 3 the body alone, as
`p001` defines them. Body axes, moments about the MRP at the quarter-chord
reference.

| pitch_rate | CL (airframe) | dCL | CM25 (airframe) | dCM25 | dCL wing | dCL body |
|---|---|---|---|---|---|---|
| 0 deg/s | 0.24116 | -- | -0.02467 | -- | -- | -- |
| 4 deg/s | 0.24349 | +0.00233 | -0.02481 | -0.00014 | +0.00262 | -0.00029 |
| 40 deg/s | 0.26383 | +0.02267 | -0.02583 | -0.00116 | +0.02569 | -0.00302 |

**The response is monotone and of the same order in the rate**: ten times the
rate gives 9.7 times the lift increment and 8.3 times the moment increment.
The lift ratio is well resolved; THE MOMENT RATIO IS NOT, because the 4 deg/s
moment increment is one printed digit at the five-decimal resolution of the
table (-0.00014, so +/-3.6 per cent from the rounding alone). What the two
rates establish is that the solver is reading the command rather than being
perturbed by it, and that is why the second rate was run: at 4 deg/s the moment
increment is 0.6% of the base and could be argued with; at 40 deg/s it is 4.7%
and cannot.

## Why that is a nose-up rate

**The moment opposes the rotation.** A lifting surface rotating about a point
near its own quarter chord sees an increased local angle of attack behind the
centre of rotation and a decreased one ahead of it, so the increment of
pitching moment OPPOSES the rotation: pitch damping, `Cm_q < 0`. The measured
increment is NEGATIVE (nose-down) for a positive emitted rate, so the emitted
rotation is the one a nose-up rate produces. Had the solver read the positive
value as nose-down, the damping would have been nose-UP and `dCM25` positive.

**The lift moves the way it must.** The wing, whose centroid is behind the MRP,
GAINS lift (+0.0257 at 40 deg/s) while the body, most of which is ahead of it,
LOSES lift (-0.0030). Aft up, forward down, which is the same nose-up rotation
read a second way.

## The drag at the larger rate

At 40 deg/s two of the three groups came back with a NEGATIVE drag
coefficient: the airframe at -0.00002 and the wing at -0.00237, against
+0.00524 and +0.00267 at zero rate. It is recorded here because the verdict
leans on that point and a reader should see it rather than find it in the
evidence file.

**It is not read as a verdict either way.** A panel method with no viscous
model computes the force from the pressure distribution alone, so a rotating
inflow that tilts the local flow forward over part of the surface can produce a
negative pressure drag; the wing's own induced drag is also small here
(CL 0.26 on a span of 20 m). Whether -0.0024 on the wing is that effect or an
artefact of the rotating free stream at a rate no aircraft flies is a question
for the domain seat, and the sign verdict does not rest on the drag: it rests
on the moment and on which surfaces gained lift.

## What this does NOT establish

- **The other two rates are not measured.** Roll and yaw are emitted by the
  same code with the same sign against the axis the reference declares, and
  nothing here ran one. A row that rolls or yaws rests on this measurement plus
  the argument that one axis is not special, which is an argument and not a run.
- **The magnitude is not calibrated against theory.** No `Cm_q` was computed
  from a strip model and compared; the measurement is of the SENSE, and the
  linearity is evidence that the command is read, not that the value is right.
- **One build.** 26.124. No other build was asked, and the command's grammar is
  identical across the editions that document it.
- **One geometry, one incidence.** The argument above is about where the
  surfaces sit relative to the moment point, which is a property of this
  configuration; a configuration whose lifting surfaces sit entirely ahead of
  its moment point would show the opposite lift increments and the same
  moment sign, and the moment is the half the verdict rests on.
- **The geometric half is not checkable from anything committed.** "The wing's
  centroid is behind the MRP" and "most of the body is ahead of it" are read
  from the mesh, and the mesh never enters this repository. A reader without it
  has the moment argument and not the lift one.
- **It presumes the mesh's own orientation matches its declared axes.** The
  reference states `[body_axes] pitch = Y`, and nothing here measures that the
  geometry is built nose along +X with +Z up. A mesh built another way with the
  same declaration would turn the free stream about the wrong axis and this
  probe would not have noticed.
- **The drag is not explained**, only recorded: see the section above.


---

## Amended 2026-09-24: roll and yaw were run, and the argument failed (G13)

Nothing above is changed; the verdict for pitch stands. The first bullet of "What this
does NOT establish" said a row that rolls or yaws rested on this measurement "plus the
argument that one axis is not special, which is an argument and not a run". The run is
the licensed probe T11 of the 0.27.0 work, on FlightStream 26.124 (build 8172026), seven
converged solves on this report's mesh, reported in
`reports/RPT-060_roll-and-yaw-rates-are-emitted-reversed_2026-09-23.md` with its
evidence at `reports/probes/RPT-060_2026-09-23_evidence.yaml`. **The argument was
wrong.** The solver does turn the free stream as a right-hand rotation about each frame
axis, as this report found for y. But the body axes (forward, right, down) are the
geometry's frame (x aft, y right, z up) turned half a turn about y, so p = -omega_x and
r = -omega_z while q = +omega_y. One sign of +1 was right for the axis this report ran
and reversed for the other two.

- **Results already produced.** A row of 0.21.0 to 0.26.0 stating `roll_rate` or
  `yaw_rate` was solved at the opposite rate: its coefficients are those of -p or -r.
  That is measured on 26.124 and on this configuration's axes; on another build the same
  line was emitted and its response is unmeasured. A row stating `pitch_rate` is
  unaffected.
- **The constant this report named**, `cases.workflows.FREESTREAM_ROTATION_SIGN`, is a
  sign per body axis since 0.27.0 (G13): -1 for roll, +1 for pitch, -1 for yaw, the
  diagonal of the export-to-body turn in `post/axes.py`. A row stating `pitch_rate`
  writes what it wrote before.
