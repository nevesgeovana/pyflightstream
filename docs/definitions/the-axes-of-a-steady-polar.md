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
(`test_g16_the_steady_polar_and_its_super_file_state_the_polar_once_as_pol`,
`test_g16_a_super_file_in_the_fixed_width_format_states_the_polar_once_as_pol`).
A 0.26.0 table carried the polar as `POLAR`, in the place `POL` has now; the
super file's union reads such a table's `POLAR` as `POL`
(`test_g16_a_polar_table_written_before_the_rule_gives_the_union_its_polar_as_pol`).

The loads export states ONE force and ONE moment per surface, in the
geometry's own frame: **x aft, y right, z up**. Every axis column of a steady
polar row is that pair, summed over the group's surfaces and turned.

| columns | axes | how |
|---|---|---|
| `CDB, CYB, CLB, CRB25, CMB25, CNB25` | body: forward, right, down | half a turn about y. `CDB` IS the export's `Cx` and `CLB` its `Cz` |
| `CDS ... CNS` | stability | body axes turned by `-alpha_s` about y |
| `CDW ... CNW` | wind | stability axes turned by `beta_w` about z |

Drag opposes +x and lift opposes +z of each system; the side force keeps its
sign. The moment turns as ONE vector in one length and only then is
normalised: `CR` and `CN` by the span, `CM` by the chord. Under sideslip that
is what moves pitch into roll by the ratio of chord to span.

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

**In a coupled FSI run `CDo` is zero as the solver prints it.** On 26.124
the loads export of a coupled solve prints `CDo` as zero from the first
export of its first coupling pass, where the rigid solve of the same wing
prints the profile drag (RPT-128). So in a coupled run `CD0` reads that zero.

**A drag the solver declined is `NA`.** A boundary on the vorticity
induced-drag list (`SET_VORTICITY_DRAG_BOUNDARIES`) without a defined trailing
edge is not computed, and the export prints its `CDi` as zero (SRC-003 p.202).
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
(`write_recorded_polar`) has no run record and declines nothing. The
fixed-width custom polar carries the same missing value as `nan` in the
column's own width, since its format writes every number `%10.5f`.

**`CLW` is NOT the solver's `CL`.** The `CL` an export prints sits
between 0.10 and 0.25 per cent above the wind-axis lift of the vector printed
beside it on 27 of the 28 lifting recorded exports (lift above 0.05) in
`tests/tier1_offline/fixtures/recorded_total_rows.csv`; one sits at 0.71 per cent.
The cause is not known. The polar states the vector's, so that every column of a row
comes from one source and `CDB`, `CLB` agree with the `Cx`, `Cz` of the
export. See [the steady-polar migration](../migrating-to-0.24.0.md) for the correction to historical `CLS` and `CLW`.

---
