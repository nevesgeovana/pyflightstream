## The axes of a steady polar

The polar's filename uses the first record that contributes a row: its recorded
point name when the contributing points do not vary, or its recorded sweep name when
they do. Skipped records never supply that name. A rebuild writes the current
numbers under the contributors' name and retires any previous table of that
simulation that is no longer produced, naming the old file in `products.json`
and `post.log`. Retirement follows the rebuild's archive policy.

A point whose loads export selects no surface of a polar group contributes no
row to that group's table. Its skip is recorded under the table's key with a
`#<point>` suffix, and `post.log` names the point, group and the alias or export
evidence needed to settle it. Conditions, superfile rows and run provenance use
the same contributing points. An unassignable analysis frame is a named run
skip for that point's polar row; it cannot suppress another point's products.
The unsteady polar follows the same naming rule using only points whose plots
history actually contributes an averaged row, rather than every readable load.

A steady polar row opens with `POL`, the polar, then `DESCRIPTION`, `GROUP`,
the reference block `SREF, CREF, BREF, XMOM, YMOM, ZMOM`, the condition the
twenty-four do not carry, and the twenty-four. Its super file opens with the
same columns, in the fixed-width `legacy_polar` format too
A historical table may carry the polar as `POLAR`, in the place `POL` has now; the
super file's union reads such a table's `POLAR` as `POL`

The loads export states ONE force and ONE moment per surface, in the
geometry's own frame: **x aft, y right, z up**. Every axis column of a steady
polar row is that pair, summed over the group's surfaces and turned.
An absent analysis frame is refused because its rotation cannot be established.
The Python `polar_row` call requires measured force and moment vectors.
Omitting `beta_deg` currently warns and uses zero; supply sideslip explicitly
because it becomes required at the next breaking window.

| columns | axes | how |
|---|---|---|
| `CDB, CYB, CLB, CRB25, CMB25, CNB25` | body: forward, right, down | half a turn about y. `CDB` IS the export's `Cx` and `CLB` its `Cz` |
| `CDS... CNS` | stability | body axes turned by `-alpha_s` about y |
| `CDW... CNW` | wind | stability axes turned by `beta_w` about z |

Drag opposes +x and lift opposes +z of each system; the side force keeps its
sign. The moment turns as ONE vector in one length and only then is
normalised: `CR` and `CN` by the span, `CM` by the chord. Under sideslip that
is what moves pitch into roll by the ratio of chord to span. The one length is
the reference chord: the export states all three of its moment coefficients,
`CMx`, `CMy` and `CMz`, normalised by the reference chord (measured on 26.124
and 26.125, where changing the reference length alone halved all three; the
solver takes no span), and the roll and yaw columns are rescaled from the chord
to the span.

**The angles that turn the axes are read off the velocity the solver flies.**
The solver turns sideslip about the body z axis first and incidence second,
so it flies `V (cos a cos b, cos a sin b, sin a)`, and
`alpha_s = atan2(w, u)`, `beta_w = asin(v / V)`. They equal the written
`ALPHA` and `BETA` whenever either is zero and differ at second order
otherwise: at `ALPHA 4, BETA 2` they are 4.0024 and 1.9951 degrees. The
`ALPHA` and `BETA` columns stay what the row wrote.

**`CDW` is the drag the solver integrates.** The wind-axis drag of the
export's own vector equals its `CDi + CDo`, which the recorded exports
confirm to their printed precision, under sideslip too. `CD0` and `CDI` are
those two integrals as the solver states them.

<a id="the-drag-split-of-26125"></a>

**On 26.125 the drag split is `CDV` and `CDP`.** The loads export of
26.125 prints its drag split as `CDp, CDv`, pressure drag and viscous and
separation drag (FSM-26.125 pp.227, 229), in the places where every earlier build
printed `CDi, CDo`, induced and skin friction drag (FSM-26.124 pp.225, 227). The
polar carries each pair under its own names and never reads one as the other:
a 26.125 point writes `CDV` where an earlier point writes `CD0`, the sum of the
group's `CDv`, and `CDP` where it writes `CDI`, the sum of its `CDp`. A table
whose points all ran on one build carries that build's pair in the last two
columns, so a table of 26.124 points is written exactly as before. A table
holding points of both builds carries `CD0, CDI, CDV, CDP`, each row `NA`
under the pair its export did not print. On either build the group's total
drag is the sum of the two columns, which both manuals state of their own pair
(FSM-26.124 p.227, FSM-26.125 p.229). The fixed-width custom polar names its last
columns the same way, and its count line counts them. The parsed loads report
and the loads series keep the column names the export printed. The solver's
sweeper spreadsheet also keeps its printed `CDp, CDv` pair on 26.125 and
`CDi, CDo` on earlier builds; tabulation preserves all twelve columns.

**In a coupled FSI run `CDo` is zero as the solver prints it.** On 26.124
the loads export of a coupled solve prints `CDo` as zero from the first
export of its first coupling pass, where the rigid solve of the same wing
prints the profile drag. So in a coupled run `CD0` reads that zero.

**A drag the solver declined is `NA`.** A boundary on the vorticity
induced-drag list (`SET_VORTICITY_DRAG_BOUNDARIES`) without a defined trailing
edge is not computed, and the export prints its `CDi` as zero (FSM-26.120 p.202).
So a surface is DECLINED at a point when that point's run record puts it on
the list AND its printed `CDi` is exactly zero. The list decides, not the zero:
a surface left off it is integrated by surface pressure and can print a real
zero, which is summed as one. `"all"` is every surface, and boundary `i` of an
index list is the table's `i`-th surface row; a list holding anything the table
cannot place is read as every surface. A group holding a declined surface
writes `NA` in `CDI` and in every axis column the x force reaches at that
point's angles, because the export's `Cx` is short by the same drag. Those
are `CDB`, `CDS` and `CDW` always, `CLS` and `CLW` at a non-zero angle of
attack, and `CYW` under sideslip. The moments, `CYB`, `CLB`, `CYS` and `CD0`
keep their numbers. The solver's own Total row and the parsed per-surface `CDi`
keep the number the export printed, and `post.log` names the declined surfaces
of each point. The rule reads the printed digits, so a trailing-edged surface
whose induced drag rounds to zero is declined too. `SET_SIGNIFICANT_DIGITS`
narrows that band. A polar rebuilt from point folders alone
(`write_recorded_polar`) has no run record and declines nothing. The rule
reads `CDi` only, so a 26.125 point declines nothing in the sums. On 26.125 a
declined surface prints `CDp` exactly 0, as earlier builds print `CDi` 0
So `post.log` warns, once per point, for every surface the
record puts on the list whose 26.125 `CDp` is exactly 0, naming the surface and
the build. Build 26.124 cannot discriminate: its sphere prints `CDi` 0 both on
and off the list. The
fixed-width custom polar carries the same missing value as `nan` in the
column's own width, since its format writes every number `%10.5f`.

**`CLW` is NOT the solver's `CL`.** The `CL` an export prints sits
between 0.10 and 0.25 per cent above the wind-axis lift of the vector printed
beside it on 27 of the 28 lifting recorded exports (lift above 0.05) in
`tests/tier1_offline/fixtures/recorded_total_rows.csv`; one sits at 0.71 per cent.
The cause is not known. The polar states the vector's, so that every column of a row
comes from one source and `CDB`, `CLB` agree with the `Cx`, `Cz` of the
export. See [the steady-polar migration](../upgrading.md#older-layouts) for the correction to historical `CLS` and `CLW`.

<a id="the-trimmed-polar"></a>

### The trimmed polar

**The trimmed polar is the polar's row at zero pitching moment, interpolated
inside the sampled angles and never extrapolated.** A pproc with `[products]
trimmed_polar = true` (off by default) writes, beside every polar table,
`<polar stem>_trim.csv`: the polar's own columns and one row.

1. Read the rows that state a finite `ALPHA` and a finite `CMB25`, ordered by
   `ALPHA`. Fewer than two such rows is refused.
2. Find where `CMB25` crosses zero: a row whose `CMB25` is exactly zero is the
   trim as written; otherwise two neighbouring rows whose `CMB25` changes sign
   bracket it.
3. Interpolate every numeric column linearly between the two rows at the
   fraction `m0 / (m0 - m1)` of the way, `m0` and `m1` their `CMB25`, and write
   `CMB25` as `0.0`. A cell that both rows state alike is kept as written (`POL`,
   `GROUP` and a condition the sweep holds); a text cell that differs, and a
   numeric cell either row lacks, read `NA`.

A polar whose sampled `CMB25` never changes sign does not bracket the trim, and
one that crosses zero more than once has more than one trim; both are refused,
nothing is chosen or extrapolated. The post names the refusal under `skipped`,
keyed by the trim file it would have been, and the polar itself stays written.
`products.json` lists the trimmed polar with its polar's entry and `trimmed`,
the moment and the angle it was read on. `pyflightstream.post.write_trimmed_polar`
writes the same file from any polar table; it refuses a file already there
unless `overwrite=True`.

<a id="the-refinement-study-uncertainty"></a>

### The refinement-study uncertainty

**A `[refinement]` table declares a three-level study, and the post writes the
numerical uncertainty of every coefficient of every point from it, by the grid
convergence index.** `levels` names the three simulations, finest first: one
polar solved on three discretisations, three mesh levels or three time steps.
`spacings` states each level's representative size, finest first, positive and
increasing; omitted, each is read from the level's polar as
`h = MESH_FACES^(-1/2)`, which a polar stating no single `MESH_FACES` cannot
give. `safety_factor`, `Fs`, is 1.25 by default and at least 1.

For one coefficient of one point, with `f1, f2, f3` its values finest first and
`h1, h2, h3` the sizes:

```text
e21 = f2 - f1        e32 = f3 - f2
r21 = h2 / h1        r32 = h3 / h2
p   = [ ln(e32 / e21) + ln((r21^p - 1) / (r32^p - 1)) ] / ln(r21)
f_ext    = f1 - e21 / (r21^p - 1)
U_NUM    = Fs |e21| / (r21^p - 1)
GCI_FINE = U_NUM / |f1|
```

The observed order `p` is solved by fixed point from `ln(e32 / e21) / ln(r21)`,
and the second term vanishes where the two ratios are equal. Three equal values
give no order (`NA`), `f1` as the extrapolated value and a zero band. A change
that alternates in sign or is zero (oscillatory or stalled convergence), an
order that is not positive (the values move apart as the levels are refined)
and an order that does not settle give no estimate: the coefficient's row
reads `NA` in the four estimate columns and the reason in `NOTE`. `GCI_FINE`
is `NA` where `f1` is zero.

The table is `polars/GCI-P<finest>_g<group>.csv`, one per group the three
levels' polars share. A row is one point and one coefficient, the points paired
row by row in the polars' order: `POL` (the finest level's), `GROUP`, `ALPHA`,
`BETA`, `COEFFICIENT`, `F1`, `F2`, `F3`, `H1`, `H2`, `H3`, `ORDER`,
`EXTRAPOLATED`, `GCI_FINE`, `U_NUM` and `NOTE`, for every coefficient of the
steady polar after `ALPHA`, `BETA`, `MACH` and `RE` that all three polars carry.
A study one of whose levels has no polar among this post's products, one whose
spacings cannot be read, and one whose polars hold
a different number of points or other angles at one row, is named under
`skipped` and writes no table. `products.json` lists the table with kind
`refinement_study`, its `levels`, its `spacings` and the `polars` it read.
`pyflightstream.post.polar.grid_convergence` computes one estimate.

---
