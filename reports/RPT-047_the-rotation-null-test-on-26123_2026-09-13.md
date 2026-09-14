# RPT-047: the rotation null test, on 26.123 (2026-09-13)

**WHAT THIS SETTLES.** PFS-2034.05 asked for a licensed round that judges the
mesh-rotation machinery of `ROTATE` on real solver output rather than on the
script it emits. The node's own acceptance had stood open since 2026-09-10
with the arm printing ASKED and never PROVED, because nobody had said what
the round would COMPARE against: a rotated propeller has no reference to be
right or wrong against, so any number it produced would have been read rather
than judged.

The design this round rests on is a NULL TEST, and it is what makes the round
judgeable: take a full wheel, turn the whole isolated propeller, and give the
flow the opposite angle of attack so that it is still uniform on the propeller.
Turning the model by an angle and turning the freestream by the same angle does
not change the physical problem; it changes the frame it is written in. So the
answer is known exactly, in advance, with no band to agree on first.

**THE VERDICT: it holds, across 209 comparisons of four kinds.** The worst
disagreement is stated PER POPULATION rather than as one number, because the
four are measured against different bands and in different units, and a single
worst gap quoted over all 209 would attribute one population's figure to the
rest: 3.3e-06 over the 3 wind-axis coefficients, 5.6e-06 over the 6 body-axis
force and moment components, 2.03e-05 over the 140 per-step series
comparisons, and one unit in the last printed digit over the 60 sectional
comparisons.

## The command, and it is in the tree

```
python -m tests.tier3_licensed.rotation_null
```

It reads the products of `tests/tier3_licensed/matriz_rotate.fs`, which are
written by a licensed run and are NOT committed (`.gitignore:116` excludes
`tests/tier3_licensed/post/`). That is why this report exists: the products
are machine-local and the report is the durable evidence. The matrix, the
reference `r007.toml`, the post-processing artifact `p006.toml`, the three
plan-time goldens and the measurement module are all committed, so the round
is reproducible on any seat with the build.

The run that produced the numbers below:

```
python -m pyflightstream.run.cli run matriz_rotate.fs --workspace . \
    --fs-version 26.123 --fs-exe <the 26.123 executable>
```

## The three rows, and why there are three for a test that compares two

| POL | mesh | angle of attack | what it is |
|---|---|---|---|
| 9001 | unturned | 0 | the control: the wheel square to a uniform axial flow |
| 9002 | +6 deg about `HUB-Y` | +6 | the DERANGEMENT: flow and mesh turned the same way |
| 9003 | +6 deg about `HUB-Y` | -6 | the null pair: the opposite angle, as the owner said |

The third row is the reason this is a measurement. A check that has only ever
been shown to accept is not a check, and this estate has shipped both halves
of that mistake already: a guard whose every pairing passed and a guard whose
only evidence was that it could refuse. Row 9002 meets the propeller at
twelve degrees of incidence and must fail everything row 9003 passes.

**AND THE SIGN WAS NOT KNOWN WHEN THE ROWS WERE WRITTEN.** "The opposite
angle of attack" is unambiguous physics and the solver's own convention
decides which arithmetic sign that is. Rather than pick one and report a pass
that was half luck, both were run. The rows answer it: with the mesh turned
`+6` about the hub frame's Y axis, `SOLVER_SET_AOA -6.0` is what restores the
uniform flow.

## The geometry, and that it really is a full wheel

`40_PUSHER.fsm`, whose `Blade1` boundary is built by
`tests.tier3_licensed.recipes.two_blade_rotor`: two blades 180 degrees apart,
both meshed. The whole azimuth is present and nothing is a periodic copy,
which is what the owner's "full wheel" asks for. `Body` and `Base` are the
spinner it turns on. It is a SYNTHETIC geometry generated from public shape
laws; nothing of the owner's work went into it.

Two choices in `r007.toml` exist to keep the null test about the rotation and
nothing else, and both are stated because either one, made carelessly, would
have produced a false finding:

- **The moment point is the hub**, `(4.5, 0, 0)`, the point the rotation turns
  about. A moment reference off the rotation centre moves relative to the
  model when the model turns, so the forces would have been invariant and the
  moments would not, and the report would have blamed the rotation machinery
  for the choice of where moments were taken.
- **The frame `HUB` is owned by no rotor.** Rotating by an alias turns the
  frames that alias owns (FR-71), so an axis frame belonging to `PUSHER`
  would have turned between the row's first rotation record and its second,
  and the two records would not have been about the same line. `HUB` is
  nobody's, so the model turns rigidly.

The row turns the model in two records because no single alias owns all of
it: `{ANGLE: 6 / AXIS: HUB-Y / ALIAS: PUSHER}` turns the blades and the
rotor's own frames with them, and `{ANGLE: 6 / AXIS: HUB-Y / ALIAS: airframe}`
turns the spinner. The emitted script confirms both about frame 3, the
unturned `HUB`, and is committed as the plan-time golden.

## What was checked, and why each check can fail differently

| # | what | the rule | why it is not enough alone |
|---|---|---|---|
| 1 | `CL`, `CDi`, `CDo` at `MRP` | IDENTICAL: they are defined against the freestream, which turned with the model | a propeller at zero incidence is symmetric about its axis, so this passes even if the model turned the wrong way |
| 2 | `Cx`, `Cy`, `Cz`, `CMx`, `CMy`, `CMz` at `MRP` | the control's vector ROTATED by exactly +6 deg about Y | this is the check with a direction in it; it is asserted as a rotation, never as a magnitude, because a magnitude survives the wrong rotation too |
| 3 | the per-step loads series, paired by STEP | both rules again, step by step and surface by surface | a time average can agree while its steps do not, which is what an azimuthal phase error looks like |
| 4 | the sectional loads at `LOCAL_AXIS` | IDENTICAL outright: that frame turned with the alias that owns it | the finest grid this workspace exports, and the one a rotation that moved the blades and left their axes behind would fail |

## What it found

The whole of what the measurement prints, unabridged:

```
The rotation null test of PFS-2034.05. The mesh of rows 9002 and 9003 is turned +6.0 degrees about the hub frame's Y axis; row 9001 turns nothing.
Bands: 5e-04 absolute on the coefficients, set from the control's own lateral residual; on the sectional loads, one unit in the 4 significant digits that export actually prints.

--- row 9002, angle of attack +6.0 degrees ---
POLAR-9002_M10AL+060BE+000 against POLAR-9001_M10AL+000BE+000
  DIFFERS  wind-axis coefficients at MRP, invariant: 3 comparison(s), worst gap 1.718e-01
           CL (wind axes, invariant): expected -0.000008, got +0.171842, gap 1.718e-01
           CDi (wind axes, invariant): expected -0.755404, got -0.741440, gap 1.396e-02
           CDo (wind axes, invariant): expected +0.012809, got +0.013457, gap 6.482e-04
  DIFFERS  body-axis force and moment at MRP, rotated: 6 comparison(s), worst gap 2.547e-02
           Cx (body axes, rotated): expected -0.738528, got -0.741852, gap 3.324e-03
           Cz (body axes, rotated): expected +0.077613, got +0.093799, gap 1.619e-02
           Cy (body axes, on the axis of rotation): expected +0.000197, got -0.009232, gap 9.430e-03
           CMx (body axes, rotated): expected -0.213896, got -0.214489, gap 5.930e-04
           ... and 1 more
  DIFFERS  per-step loads series: 140 comparison(s), worst gap 3.037e-01
           step 6 Blade1 CL: expected +0.000010, got +0.164130, gap 1.641e-01
           step 6 Blade1 CDi: expected -0.788120, got -0.773150, gap 1.497e-02
           step 6 Blade1 Cx: expected -0.773876, got -0.776200, gap 2.324e-03
           step 6 Blade1 Cz: expected +0.081348, got +0.082360, gap 1.012e-03
           ... and 87 more
  DIFFERS  sectional loads, in the blade's own frame: 60 comparison(s), worst gap 1.680e+02
           station 1 Fx: expected -526.500000, got -520.400000, gap 6.100e+00
           station 1 Fz: expected +48.180000, got +50.730000, gap 2.550e+00
           station 1 Moment: expected +630.300000, got +623.200000, gap 7.100e+00
           station 2 Fx: expected -1153.000000, got -1147.000000, gap 6.000e+00
           ... and 53 more

--- row 9003, angle of attack -6.0 degrees ---
POLAR-9003_M10AL-060BE+000 against POLAR-9001_M10AL+000BE+000
  AGREES   wind-axis coefficients at MRP, invariant: 3 comparison(s), worst gap 3.300e-06
  AGREES   body-axis force and moment at MRP, rotated: 6 comparison(s), worst gap 5.600e-06
  AGREES   per-step loads series: 140 comparison(s), worst gap 2.032e-05
  AGREES   sectional loads, in the blade's own frame: 60 comparison(s), worst gap 1.000e+00

THE NULL TEST HOLDS, on exactly one of the two rows: 9003 (alpha -6.0). The other turned the flow the same way as the mesh and met it at twice the angle, and it DIFFERS on every one of the four checks, which is what makes this a measurement rather than a check that accepts whatever it is given.
```

The individual numbers behind the first line, from
`post/matriz_rotate/campaign_sweep.csv`, because a worst gap is a summary and
the invariance is worth seeing whole:

| | 9001, the control | 9003, turned and flown back | what was expected |
|---|---|---|---|
| `CL` | -8.2e-06 | -4.9e-06 | identical; both are zero |
| `CDi` | -0.7554040 | -0.7554031 | identical |
| `CDo` | +0.0128086 | +0.0128086 | identical, to every digit printed |
| `Cx` | -0.7425955 | -0.7385271 | -0.7385285, the control rotated |
| `Cz` | -9.4e-06 | +0.0776161 | +0.0776130, the control rotated |
| `CMx` | -0.2150290 | -0.2138956 | -0.2138958, the control rotated |
| `CMz` | -0.0004286 | +0.0220505 | +0.0220504, the control rotated |
| iterations | 514 | 514 | not asserted, and they match |
| residual | 8.7756e-06 | 8.7752e-06 | not asserted, and they match |

The solver took the same number of iterations to the same residual on the two
rows, which nothing here asserts and which is the strongest single sign that
it was handed the same problem twice.

## The bands, and where each came from

**On the coefficients, 5e-4 absolute.** Set from the MEASURED residual of the
control's own lateral force: `Cy` is +1.972e-4 where an exactly axisymmetric
answer would be zero, because half a revolution of a two-blade rotor does not
average the azimuth away exactly. A null test asserted tighter than the noise
of the thing it measures reports the discretisation as a defect. The worst
gap actually observed, 5.6e-6, is ninety times inside it.

**On the sectional loads, one unit in the last significant digit.** That
export prints FOUR significant digits: of the 140 numbers in the control's
file the longest mantissa is four digits and the rest are four with trailing
zeros. The setup preset `s002` states `significant_digits = 7`, so the
sectional-loads export does not carry the setup's setting; that is recorded
here as a measurement and is not a defect this round chased.

**A CORRECTION THIS ROUND MADE TO ITSELF**, written down rather than fixed
quietly, because the first answer was wrong in the direction that looks
careful. The first writing of the section comparison divided every column by
the largest `Fz` in the file and judged the result against the coefficient
band. That compares a MOMENT in newton metres against a scale in newtons:
station 10's moment had to agree eight times tighter than the force beside
it, and it was duly reported as the one disagreement in the whole test. It
was not one. `Fx` and `Fz` at that station are identical to the last digit
printed, and the moment reads -2093 against -2092, which is one unit in the
fourth significant digit and the finest difference that file can express. A
band that is dimensionally incoherent is not a strict band; it is a band
measuring the wrong thing, and it produced a finding against the subject that
belonged against the instrument.

## What this does NOT say

It does not say the rotation is correct at every angle, about every axis, for
every alias. It says that at +6 degrees about a hub frame's Y axis, applied
to a full wheel in two records covering every boundary of the mesh, the
solver was handed the same physical problem as the unturned control and
answered it identically to five or more significant digits across 209
comparisons of four different kinds.

It does not judge the propeller. No thrust, torque or efficiency figure here
is compared against anything outside this round, and none should be: the
geometry is synthetic and its loads mean nothing beyond this test.

It does not settle whether `SOLVER_SET_AOA` and `ROTATE` share a sign
convention in general. It settles it for a rotation about Y, which is the
axis an angle of attack is about, and that is the case the node asked for.
