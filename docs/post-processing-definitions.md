# Post-processing definitions

**This page is the definition of record for every post-processing product this
package writes.** It exists because the definitions kept being re-explained in
conversation and re-derived from code, and a definition derived from code makes
the code its own specification. Where this page and the code disagree, **this
page is right and the code is a defect**.

Every definition below states the requirement a product is built to. None of
them was inferred from an implementation.

!!! note "For whoever maintains this package"
    Read this page before changing any reduction, any averaging window, or any
    product's column set. A reduction whose meaning you reconstructed from
    `workflows.py` is a reduction you are about to get subtly wrong: three of
    the definitions below were implemented as a declared field with no caller,
    which reads exactly like a finished feature.

## Contents

- [The vocabulary](#the-vocabulary)
- [What every product states](#what-every-product-states)
- [The axes of a steady polar](#the-axes-of-a-steady-polar)
- [The sections table, and which row is which](#the-sections-table-and-which-row-is-which)
- [The probes table](#the-probes-table)
- [`time_average`](#time_average)
- [`per_blade`](#per_blade)
- [`phase_locked`](#phase_locked)
- [The averaging window](#the-averaging-window)
- [Native surface flow exports](#native-surface-flow-exports)
- [The unsteady POLAR](#the-unsteady-polar)
- [Rotor coefficients](#rotor-coefficients)
- [What the package does NOT judge](#what-the-package-does-not-judge)
- [The token for a value that does not exist](#the-token-for-a-value-that-does-not-exist)

---

## The vocabulary

| term | meaning |
|---|---|
| **revolution** | one full turn of a rotor, `60 / rpm` seconds, `60 / (rpm * dt)` solver steps |
| **blade passage** | one revolution divided by the blade count |
| **azimuthal position** | where a blade is in its turn, 0 to 360 degrees |
| **window** | an inclusive, 1-based range of solver steps that a reduction averages over |
| **SMRP** | a rotor's own static moment reference point, `<ALIAS>_SMRP` |
| **MRP** | the global moment reference point of the aircraft |
| **alias** | the name of a rotor, and of the integration group built from its families |

---

## What every product states

Every table the post stage composes states the condition it is a table OF, in
one block, in this order:

<!-- condition-columns: ALPHA, BETA, MACH, RE, VINF, VREF, ALT, RHO, TEMP, MU, J, J_CLOCK, RPM_CLOCK, SREF, CREF, BREF -->

| column | unit | what it is |
|---|---|---|
| `ALPHA`, `BETA` | deg | the angles the solver REPORTS it ran at, as the row wrote them |
| `MACH` | - | the Mach number of THAT point |
| `RE` | millions | the Reynolds number the solver reports |
| `VINF` | m/s | the free-stream velocity the solver reports |
| `VREF` | m/s | the solver's REFERENCE velocity, which is what it normalises a coefficient by |
| `ALT` | ft | the altitude the row states; `NA` where it states none |
| `RHO` | kg/m3 | the air density the run resolved for that point |
| `TEMP` | K | the air temperature the run resolved for that point |
| `MU` | Pa s | the dynamic viscosity, written in scientific notation |
| `J` | - | the advance ratio the row REQUESTED; `NA` on a row that turns no rotor, and on one that states its speed as `RPM` |
| `J_CLOCK` | - | the advance ratio the CLOCK rotor RAN at, `V / (n D)` from this point's free stream, the speed the record kept and the rotor's diameter; `NA` where the record or the reference does not say |
| `RPM_CLOCK` | rev/min | the speed the CLOCK rotor turned at, with its hand; the CLOCK rotor is the one `CLOCK_MOTION` names, or the only rotor the row turns. A row turning several and naming none has no clock, and both columns are `NA` rather than taking one rotor's number for another's |
| `SREF`, `CREF`, `BREF` | m2, m, m | the reference area, chord and span |

**Why the block is this long.** A coefficient is a force divided by
`1/2 rho V^2 S`. A file that states the coefficient and the area, and neither the
density nor the velocity it was divided by, is a number nobody can take back to a
force or compare with another campaign. `ALT` does not stand in for the density:
a row may pin the density directly, and then the altitude says nothing about it.

**Which velocity normalised what.** The solver normalises by `VREF`. The steady
polar's twenty-four coefficients are the solver's own, so they are by `VREF`. The
plots table, every reduction of it and the unsteady polar are rescaled to the
free stream by `(VREF / VINF)^2`, so they are by `VINF`. The rotor table takes
the export back to Newtons with `VREF`, which undoes the solver's own division,
and its coefficients are by `rho n^2 D^4` and carry no velocity at all. With both
velocities in the row, a reader can tell which one a number used; the post stage
also WARNS, naming the point, when the two differ.

**`SREF` and `CREF` are checked against the export.** The solver divides by the
area and the length of the project file it opened, and the loads export prints
both. The package sets neither: it states the reference artifact's. Where the
two differ by more than the export's printed precision, post warns and writes
every computable product by default; `check_frozen=True` refuses the simulation's
products and `products.json` names both numbers. A table stating one area beside
coefficients divided by another differs by a constant factor, so receiving a
table does not establish agreement. See the single
[default warning policy](#the-post-log-and-the-default-warning-rule-since-0260).

The steady polar already carries `ALPHA`, `BETA`, `MACH` and `RE` among its
twenty-four, so it states the rest of the block beside them. The plots table
`probes/<point>_plots.csv` states NO condition, on purpose: it is the export's own
header, and the reductions read every column of it back as a plotted quantity.

---

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

**`CLW` is NOT the solver's `CL`.** The `CL` an export prints sits
between 0.10 and 0.25 per cent above the wind-axis lift of the vector printed
beside it on 27 of the 28 lifting recorded exports (lift above 0.05) in
`tests/tier1_offline/fixtures/recorded_total_rows.csv`; one sits at 0.71 per cent.
The cause is not known. The polar states the vector's, so that every column of a row
comes from one source and `CDB`, `CLB` agree with the `Cx`, `Cz` of the
export. A table written before 0.24.0 used the solver's `CL`, so its `CLS`
and `CLW` are higher by that much.

---

## The sections table, and which row is which

`sections/<point>_sections.csv` is ONE export of the solver holding EVERY
distribution the pproc declares, the wing in `XZ` and each blade in its own
frame, one after another with no marker between them. Each row leads with:

| column | what it is |
|---|---|
| `STEP` | on an unsteady point, the run's last TIME STEP, from the run record: the export is written when the march ends, and its own header counts the solver's inner iterations, not steps ([RPT-053](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-053_what-an-unsteady-export-states-and-when_2026-09-19.md)). On a steady point, the solver iteration the export states. One name across every table |
| `FAMILY` | the geometry families of the row's distribution, joined by `+` |
| `PLANE` | the cutting plane of that distribution |
| `ROTOR` | the rotor whose blades those families are; `NA` for a surface no rotor owns |
| `AZIMUTH` | where BLADE ONE OF THAT ROTOR is at `STEP`, in degrees, wrapped to one turn; `NA` without a rotor |

`AZIMUTH = (blade1.azimuth_deg + sense * STEP * 360 / steps_per_revolution) mod 360`,
with the datum, the sense of rotation (the sign of the rotor's speed) and the
steps per revolution all taken from THAT rotor. Two rotors at two speeds have
two azimuths at one step, and a wing has none.

The run records which distribution is which, because the script states
surfaces by index and nothing at post can name them. A run recorded before
0.24.0 states `NA` in all four, and so does a record whose blocks do not add
up to the rows the export holds: a row given its neighbour's family is worse
than a row given none.

**It is one instant.** On an unsteady point this table is the distribution at
`STEP`, not an average over the window, and its `products.json` entry says
`"kind": "instant"`. The history is `series/<point>_sections_series.csv`,
which carries the same identity on every row.

### Per-distribution sectional loads and Cp (0.25.0)

For every point, post also writes one file per `[[sections.distributions]]`
entry for each export:

- `sections/<point>_sloads_<name>.csv`, from the sectional loads export;
- `sections/<point>_cp_<name>.csv`, from `EXPORT_ALL_SURFACE_SECTIONS`.

`<name>` preserves the entry's `families` word (including an alias such as
`blades`); a list joins its words with `-`, for example `Blade1-Blade2`.
Filename-invalid characters become `_`, and trailing spaces and dots are
removed. Names that collide after sanitization, including differences only in
case, receive `_<k>`, the entry's 1-based pproc position. If that creates another
collision, the same position suffix is applied again until names are unique.
All planes and expanded blade/rotor blocks of one entry share its one file.

With `EXPORT_UNSTEADY_AFTER_REV` or `EXPORT_UNSTEADY_AFTER_ITER`, each file holds
**every available stamped step**, in ascending order. Without per-step exports,
it holds the end-of-run export, with `STEP` interpreted as in the existing
sections table above. The existing end-of-run table and combined
`series/<point>_sections_series.csv` remain available.

Rows lead with `STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH`, then the shared
condition block, then the export's columns. Sectional loads retain
`Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment`. Cp carries `SECTION`, the export's
1-based cross-section index, followed by its twenty printed columns:
`Section_direction_value, X, Y, Z, nx, ny, nz, L, Cp, Mach, vx, vy, vz, vtot,
Cp_ref, Theta, CF, Delta*, Delta, H`. There is one row per step, section and
chordwise station, in the export's station order. Unknown time or identity
values read `NA`.

The recorded `sections_layout` assigns sections to blocks. New records also
retain each block's pproc entry position and original `families` selection;
editing the pproc cannot reassign those recorded blocks. For a 0.24.0 layout,
the recorded pproc must match each block unambiguously by families, plane,
frame and count. An ambiguous match is a named skip. Without a recorded layout,
**no split file is written**: `products.json` names the layout requirement.
A layout whose counts disagree with an export is likewise refused for that
export kind, rather than assigning rows to guessed distributions.

Each manifest entry states `distribution` (1-based), `families` (the original
alias/selection), and `steps_tabled`. A pproc entry with no recorded blocks
gets a named skip rather than a guessed share of another entry's rows.
Missing exports and missing stamped steps
are named skips. A section without chordwise stations contributes no Cp rows;
a distribution with no stations at a step is named as a skip. A malformed
export skips that kind's split files; the other kind remains available.

#### Integrated sectional loads (since 0.26.0)

Set `integrate = true` beside `families`, `planes` and `count` in the desired
`[[sections.distributions]]` entry. The default is `false`. Omitted or false,
the sectional CSV is byte-for-byte the seven export columns and existing
context written by 0.25.1, with no additional column. This is a post-processing
choice in the pproc, so it also applies when posting existing recorded exports.
The current entry must match each recorded block uniquely by families, plane,
frame and count; reordering entries cannot move an integration request to
another block. Recorded entry positions still own the split files. An ambiguous
or missing match warns by point, file and block and records an `#integration`
skip, keeping the file's original columns. All blocks in one file must request
integration for that file to gain integrated columns.

The effective matrix pproc supplies integration requests only; legacy ownership
still resolves through the recorded pproc. Section selectors, including `each`,
use the same expansion as the export builder, resolving current aliases through
the live reference to the recorded boundary families, including rotor names and
aliases of rotor names. An expanded emission's family set must equal the recorded
block's set. Ownership of a legacy layout (a name and a grouping for raw
files, no number added) resolves the recorded pproc's selectors over the
recorded cuts, the only evidence there is, a family stem and a numbered name
included. Integration is never matched that way, whoever asks, because the
post cannot tell a recorded specification from a current one (two
resolutions of one artifact id compare equal after an edit, and a recorded
entry may have emitted nothing): a selector is knowable only by exact
recorded boundary names, by aliases and by the live reference's rotor
definitions, whose members count even when they have no sectional block;
`RunRecord` carries no complete geometry inventory, layout silence never
proves a family absent, and any other word (a family stem, an unrecorded
name, a whole-geometry selector) leaves membership uncertain, establishes no
integration match and keeps the raw columns with a named skip. `each` and
`each_blade` still identify one known family per block without claiming a
complete inventory.
In a common frame, `["Wing", "Tail"]` describes one combined block,
so it cannot integrate separate recorded Wing and Tail blocks; both keep their
raw columns with a named warning. Where no rotor definition reaches the match
(a legacy layout, or a reference without rotors), the recorded frame names
carry the builder's grouping, because they name the rotor: `<alias>_RMRP`,
`<alias>_SMRP` with its `_ORIGINAL` twin (one emission turned, one group), and
`<alias>_RMRP<n>` for one blade; a frame either specification in hand cites
literally (a user's own `X_RMRP`) names no rotor whatever it is called, unless
a recorded frame no specification cites literally establishes the same rotor
(the rotor's `ROTOR_RMRP` cited by an entry over its hub stays the rotor's
while `ROTOR_RMRP1` is recorded); even then a literally cited frame can hold
any family, so it never supplies a sibling's missing family and a block
recorded in it is that literal entry's, never an expanding entry's; uncertain
membership keeps the raw columns. A block of any other kind than the entry's
frame expands per, a common frame included, is not that entry's emission and
cannot stand as a sibling of one. On an expanding frame (`LOCAL_AXIS`, `RMRP`,
`SMRP`) a recorded block is an entry's emission when it is exactly the selected
families recorded in its group, every other selected family is recorded in a
sibling group of the same kind (another rotor, another blade) or, for a
`LOCAL_AXIS` entry, in its own rotor's frame (the hub and spinner the builder
leaves out of a cut), and a per-blade block is one blade; two blocks recorded in
one group came from two entries and a combined entry owns neither, and a
selected family recorded only in a common frame leaves the block unmatched. If the effective pproc cannot be
resolved, complete recorded layouts and available stamped exports still supply
their histories. Integration and products needing that specification are named
skips in `products.json` and `post.log`.

```toml
[[sections.distributions]]
families = "blades"
frame = "LOCAL_AXIS"
planes = ["XZ"]
count = 50
integrate = true
```

The same `sections/<point>_sloads_<name>.csv` gains these columns, in this order
immediately after `Moment`:

| column | token in `_tokens.py` | unit | definition |
|---|---|---|---|
| `Strip_length` | `STRIP_LENGTH` | m | positive length of this station's strip |
| `Fx_int` | `FX_INT` | N | `Fx * Strip_length` |
| `Fz_int` | `FZ_INT` | N | `Fz * Strip_length` |
| `My_int` | `MY_INT` | N m | `Moment * Strip_length`, about this station's quarter chord |

**Strip rule.** For strictly monotonic exported offsets `s[0] ... s[n-1]`,
the interior boundaries are `(s[i-1] + s[i]) / 2`. The outer boundaries are
`s[0]` and `s[n-1]`. Endpoint lengths are half their one adjacent interval;
each interior length is half the distance between its two neighboring stations.
Thus the strips tile exactly the first-to-last station interval with no gap,
overlap or extrapolation to a geometric root or tip. Decreasing offsets retain
their order and use positive lengths. The nominal `count` spacing is never
used. Each recorded block (one plane, frame and family selection) is integrated
independently at each exported STEP, including blocks sharing a distribution
file. Original rows, axes, STEP and AZIMUTH are preserved. These are instants,
with no temporal average or revolution envelope.

**Moment-point decision, 2026-09-23.** `My_int` reports the integral of the
export's `Moment` about the local quarter chord `(X_QC, Z_QC)`. SRC-751,
the registered 26.123 manual, p.253 (Sectional Load Distributions), explicitly
identifies Xqc and Zqc as the 25% chord coordinates used for the CM reference.
Its pp.370-371 document computing and exporting the same sectional loads.
The recorded export
`tests/tier1_offline/fixtures/fsi/FS_SurfaceSection_Loads_call0002.txt` carries
`Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment`; its Newtons/Newton-Meter footer
states the computation units. The line-density interpretation is supported
by the force-integral comparison in RPT-006. Multiplying the moment density
by the strip length preserves that moment point and the export's sign and
section-plane axes. For an XZ cut in a blade's own frame this is its My.
For another cut plane it retains the export's plane-normal moment component
under the same column name. No transfer to an elastic axis, hub or global MRP
is applied. A sum of these local moments is not a moment about one common point.

**Integration never blocks post.** A block with fewer than two stations,
non-monotonic or repeated Offset, or a non-finite sectional value cannot be
integrated. Overflow in the integration is handled the same way. Post writes
the entire distribution file with its original columns, omitting all four
added columns, even when other blocks or steps in that file are valid. A
`PyflightstreamWarning` names the point, output file, source step/block and
reason. Other distribution files and Cp products continue normally.

---

## The probes table

The run type selects the source of `probes/<point>_probes.csv` for every
`[[probes]]` declaration, including drawn shapes and cited `points_file`
profiles.

- **Unsteady:** each point and requested parameter is sampled by a fluid plot.
  One table combines all available probe histories, with one row per point and
  solver step. The positions and frame come from the run's recorded probe
  positions; the samples come from the plots history. A probe-points instant
  export never supplies this table.
- **Steady:** both declaration forms use standard probe points, and the table
  contains the probe-points export. `STEP` is `NA`.

An unsteady run recorded with 0.24.0 or earlier sampled cited profiles only at
the final instant. Those probes have no recorded history: posting again skips
them, names the profile and reason in `products.json`, and keeps the available
drawn-probe histories. A new run is needed to obtain the cited profiles' history.

Where the artifact's entries ask for DIFFERENT parameters, the table carries a
column for every requested parameter, and a point that was not sampled for one
carries `NA` there. A point keeps the samples it has; no entry loses its history
because a neighbour asked for something else.

For an unsteady run, a cited profile is a count followed by `X,Y,Z,TYPE` CSV
rows, with type 0 or 1. Both types supply fixed vertices to fluid plots; the
entry's frame, scale and parameters apply to those vertices. Invalid counts,
coordinates or types are refused before solving. Steady imports retain their
existing solver import behavior.

---

## `time_average`

One average of the whole point over one window. It is what a POLAR row of an
unsteady point is built from.

**One window per point.** Not one per rotor, because a point has one history.

---

## `per_blade`

!!! note "The code since 0.24.0"
    0.23.0 wrote the ONE shared window below and ONE ROW for it, the time
    average's shape under the per-blade name. Since 0.24.0
    `probes/<point>_per_blade_<ALIAS>.csv` is one row per blade with its start
    and end azimuth, as defined here.

The per-blade table averages each blade over the LAST part of the run, the
row's averaging window. The blades sit at different azimuths, and that is not a
reason for different windows: a column states where each blade starts and ends.

**ONE window per rotor, shared by every blade of that rotor.** One row per blade,
and each row carries
the **start and end azimuth of that blade** over that one shared window.

**Why one window and not one per blade.** Averaging each blade over its own
passage puts each blade in a different part of the history, so any difference
between two blades mixes a real azimuthal difference with a difference in WHEN
each was sampled -- and nothing in the file says which is which. With one window,
the azimuth columns carry the difference explicitly and the reader can see it.

**The window comes from `LAST_REVS_AVG` or `LAST_ITERS_AVG` on the matrix row.**
On a multi-rotor run, each blade follows its own rotor's clock:
`LAST_REVS_AVG` counts that rotor's own revolutions. Rotors turning at different
rates can therefore have different step windows for the same requested number
of revolutions. Every blade of one rotor shares that rotor's window;
`LAST_ITERS_AVG` uses the stated step count.

Averaging from step one mixes the transient with the answer.

**The rows.** Each row leads with `REDUCTION`, `ROTOR`, `BLADE`, `FAMILY`, the
window (`FIRST_STEP`, `LAST_STEP`, `STEPS`), `AZIMUTH_START`, `AZIMUTH_END`,
then the condition block and the moment point.

- **A blade's columns are the plots named for its family.** A plot is
  `<parameter>_<group>` and a group cut per blade is named for the blade's
  family, so blade one's are `CL_MRP_Blade1`, `FX_LOCAL_Blade1`. The row carries
  them with the family removed, `CL_MRP`, `FX_LOCAL`, so two blades line up
  under one heading. A pproc gets them with `families = "each"` or
  `frame = "LOCAL_AXIS"` over the rotor.
- **The azimuths are where that blade IS at the window's first and last step**,
  by the formula of the sections table: blade one's datum, plus the blade's
  position times `360 / blades`, plus the rotor's sense times the step times
  `360 / steps_per_revolution`, wrapped. `blades` is the ROTOR's count, so a
  periodic sector carrying two blades of four spaces them a quarter turn apart.
  Without the rotor's clock they read `NA`; the averages are written all the same.
- **Which families are a rotor's blades** is the `families_blades` of its block
  in the reference artifact; a run made since 0.24.0 also records them. A row
  that states its rotor with flat keys and cites no block has no per-blade
  table, and `products.json` says why.

---

## `phase_locked`

!!! note "The code since 0.24.0, where the pproc declares `[phase_locked]`"
    0.23.0 wrote the averaging window cut into consecutive blade passages, one
    row per passage, under this name. Since 0.24.0 a pproc that declares the
    `[phase_locked]` table gets the table defined here. **A pproc that does not
    declare it still gets the passage series**, so a workspace that never asked
    for the table reads the file it has always read.

It looks at the SAME azimuthal position over several revolutions and returns
the mean against azimuthal position.

**It is an average ACROSS revolutions at a FIXED azimuth.** It is not a series
of consecutive passages, and that distinction is the whole content of this
section.

The operation, step by step:

1. Take the last `last_revolutions_avg` revolutions.
2. For **each azimuthal position**, average the samples at that position across
   those revolutions. With three revolutions, every azimuthal position has
   **three datapoints** entering its mean.
3. Write the result **tabulated by azimuthal position, 0 to 360**.
4. Do this **for each blade on its own, about that rotor's `SMRP`**.
5. Then do it **for each alias, about the global `MRP`**.
6. Put all of it in **one file**, with columns suffixed
   `_{alias or blade_name}_{SMRP or MRP}`.

**The row of this product is an azimuthal position.** Not a passage, not a
revolution, not a blade.

**How the file carries it.** `probes/<point>_phase_locked[_<ALIAS>].csv` leads
with `REDUCTION`, `ROTOR`, `AZIMUTH`, `STEP`, `REVOLUTIONS`, the steps the
revolutions span (`FIRST_STEP`, `LAST_STEP`, `STEPS`), the condition block and
the moment point, then the plotted columns under the names the export prints.

- **The rows are the azimuthal positions of the rotor's LAST revolution**, one
  per solver step of it, sorted from 0 towards 360. `AZIMUTH` is where BLADE ONE
  is, by the formula of [the sections table](#the-sections-table-and-which-row-is-which),
  and `STEP` is the step of the last revolution that azimuth falls on.
- **A blade's column is tabulated by THAT blade's azimuth.** A column ending in
  a blade family of the rotor is sampled where that blade, which sits its
  position times `360 / blades` after blade one, is at the row's azimuth, so two
  blades line up azimuth for azimuth. Every other column, a rotor's total or the
  aircraft's, is tabulated by blade one's azimuth.
- **The suffix is the plot's own.** A plot is `<parameter>_<group>` and the pproc
  names the group, so `_{alias or blade_name}_{SMRP or MRP}` is what a group
  named `PUSHER_SMRP` or cut per blade prints; the package renames nothing.
- **`REVOLUTIONS` is how many samples entered the mean**, `last_revolutions_avg`
  exactly when that is a whole number.
- **Between two steps the history is read linearly.** One revolution earlier is
  a whole number of steps earlier only when `steps_per_revolution` is whole, and
  a blade's offset only when it divides by the blade count. Where both hold,
  every sample is a row of the history and nothing is interpolated.
- **Without blade one's datum or the rotor's signed speed no azimuth can be
  stated**, and the table is a named skip: declare the rotor in the reference
  and have the row cite it. A depth under one revolution is a named skip too.

### When it is generated

!!! note "The code since 0.24.0"
    0.23.0 refused the `[phase_locked]` table by name. Since 0.24.0 it binds, and
    `pyfs-matrix post` reads it again from the pproc as it stands, so the gate
    and the depth can be edited with no solver re-run.

The pproc states the minimum TOTAL revolutions and the revolutions each
azimuthal mean takes; the table is generated when the matrix specification
reaches that minimum.

```toml
[phase_locked]
min_revolutions      = 4.0   # the minimum TOTAL revolutions, for it to exist
last_revolutions_avg = 2.0   # how many revolutions enter each azimuthal mean
```

- The criterion is `min_revolutions`, and **equal or greater generates it**.
- What is compared against it is **what the matrix specification states** -- the
  revolutions the ROW turns -- and not the length of the exported window.
- `last_revolutions_avg` may not exceed `min_revolutions`: a reduction may not
  average over more history than it required in order to exist.

### A short run is SKIPPED, never REFUSED

A run that turns fewer revolutions than the minimum loses **this reduction and
nothing else**. Its POLAR, its per-blade table and every other product are
written as usual. Taking a product away from a campaign that already ran is
never the answer to a threshold not being met.

**A pproc that says nothing about `phase_locked` gets one as it always did.**
Absent is not zero: nothing gates it, and it is the passage series it has
always been.

---

## Probe parameters

On a **steady** run, a `[[probes]]` entry's `parameters` list only enables
the entry when nonempty (an empty list disables it). It does **not** select or
filter the exported variables: the solver's probe-points export carries its
fixed set. `pyfs-matrix plan` warns for each steady entry with a nonempty list,
naming its entry number and frame. On an **unsteady** run, `parameters` selects
the fluid-plot variables sampled by the entry.

---

## The averaging window

The window is stated in iterations or in last revolutions, ON THE MATRIX ROW,
and a row of an unsteady run type must state it.

| column | run type | required | unit |
|---|---|---|---|
| `LAST_REVS_AVG` | `unsteady_rotor` | **yes** | last revolutions, **accepts a float** |
| `LAST_ITERS_AVG` | `unsteady` | yes | last iterations |

**The key is written in UPPER CASE, exactly as the table spells it**, like every
other key of a matrix row. `VAR_NAMES_VALUES` keys are matched on the exact
spelling: a lower-case `last_revs_avg` on a workflow row is refused as a key of
no run type, and where that check does not run it is not read at all, so the
window it meant to state is not applied.

**It lives in the MATRIX, not in the pproc**, because it converses directly with
the temporal setup: `DELTA_TIME`, `TIME_ITERATIONS` and `RPM` are all on the same
row. Putting it in the pproc would separate the window from the quantities that
define it.

`WINDOW_STEPS` and `WINDOW_REVOLUTIONS` are **retired** -- they were the same idea
under another name in another place, and two spellings of one idea are how two
published numbers come to disagree.

Since 0.26.0, `WINDOW_STEPS`, `WINDOW_REVOLUTIONS` and `WINDOW_DEGREES`
are refused at plan time. Write `LAST_ITERS_AVG` for steps or `LAST_REVS_AVG`
for revolutions; divide degrees by 360. A new unsteady plan requires one of
these current keys. Older records retain the window the run was given, with
a warning naming the steps when no current averaging key was recorded.

---

## Native surface flow exports

Tecplot (`.dat`), VTK (`.vtk`) and FEM CSV (`.csv`) are native solver surface
exports. VTK and CSV are **off by default**. The pproc can request them and
select VTK variables by their command-database names:

```toml
vtk_variables = ["X", "Y", "Z", "CP_FREESTREAM"] # top-level; optional

[exports]
vtk = true
csv = true

[time_averaging]
last_revs = 1.5 # OR last_iters = 54; exactly one, positive
```

Without `vtk_variables`, VTK uses the command's all-variables form. Both forms
exclude the wake. CSV exports `CP-FREESTREAM`, `PASCALS`, all surfaces, in the
solver reference frame (frame 1 on builds whose grammar includes it). Unknown
VTK variables and commands unavailable on the selected build are refused at
plan. Both formats also join the per-step `EXPORT_UNSTEADY_AFTER_REV` or
`EXPORT_UNSTEADY_AFTER_ITER` exports.

**Time-averaged surfaces cannot be produced on the builds measured so far.**
On 2026-09-19, licensed C01 measured that `SOLVER_TIME_AVERAGING` hangs
FlightStream 26.124 in the position the package emits it: no outputs were
written before the termination at 240.5 seconds. Without that command, the
script wrote all seven outputs and its final log export, exiting successfully
in 133.0 seconds. Both runs left a receipt under `reports/pfs0250/`.

The package refuses a pproc carrying `[time_averaging]` at plan time, naming
the build and the measurement, rather than sending the hanging command to the
solver. Remove the table to obtain Tecplot, VTK and CSV surfaces as **instants**,
including the requested per-step exports. This does not change the matrix
window used to average the plots history.

The key remains available only on a build whose command-database status is
`verified`; manual documentation alone (from 26.122) is insufficient. On such
a build it emits `SOLVER_TIME_AVERAGING ENABLE first last` in INIT for these
three native surface formats on an unsteady run. Without the table no
averaging command is emitted. Changing the surface window requires a new run.

The bounds are inclusive, 1-based, ending at the run's last time step.
`last_iters` is a count of steps; `last_revs` uses the same rotor clock and
rounding as `LAST_REVS_AVG` (with `DELTA_THETA`, steps per revolution is
`360 / DELTA_THETA`). A window longer than the run is clipped at step 1.
SRC-750 p.353 says "unsteady time iteration"; interpreting that as time steps
rather than inner iterations remains **UNVERIFIED**: the C01 hang prevented
measurement of the bounds. The export header's inner-iteration counter is
never used for this conversion.

The run records the emitted window. Surface entries in `products.json` and
PROV-JSON carry `kind: average` and `window`, including iteration bounds,
the declared count and, for revolutions, the clock. Re-posting reads that
recorded request, even if the pproc has changed. Per-step entries end their
window at the export's step until the requested end is reached; a stopped run
also ends its native export window at the recorded stop step. Exports before
the averaging start are named skips. Without the table, surface entries carry
`kind: instant`. The native files retain the solver's own format.

---

## The unsteady POLAR

- The POLAR of an unsteady point is the **plots history, time-averaged** over the
  window, and it does **not** read the native coefficient export.
- **Its columns are the plot variables under the names the export prints them.**
  It does not carry the steady polar's fixed 24 coefficient columns.
- The flight-condition and reference-length columns are still added, because
  those come from the workspace and not from the export.

- **The file is `polars/P<sim>_<name>_uns_avg.csv`**, one per simulation and one
  row per point. Every file under `post/` comes from a sweep, so the name says
  what the file IS, the average of the unsteady history, and carries the `P`
  every per-point product carries. It was `<sim>_<name>_unsteady.csv` in 0.23.0.
- **Each row opens with `FIRST_STEP`, `LAST_STEP`, `STEPS`**, the window THAT
  point was averaged over, so the file says on its own that it is an average and
  over what. The condition block follows, then `XMOM`, `YMOM`, `ZMOM`, because
  the plots carry moments and a moment states nothing without its point.
- **The super file's content is ADDED to this table**, after the plot columns:
  the matrix row's cells, the record's scalars, each rotor's speed, the solver
  flags. The super file is what the polar does not have; for an unsteady point it
  is not a second file.
- **The axis coefficients follow the plot columns**, the eighteen of the steady
  polar under its own names, in the order `CDW .. CNW25`, `CDS .. CNS25`,
  `CDB .. CNB25`, each suffixed with its plot group's WHOLE name
  (`CLW_MRP_TOTAL`), one group or several. Their source is
  the plots of the GLOBAL `MRP` frame: the six components `FX, FY, FZ, MX, MY,
  MZ` of a plot group the pproc declares with `frame = "MRP"`, in Newtons and
  Newton metres, averaged over the row's window like every other column, divided
  by `1/2 RHO VINF^2 SREF` (and by `CREF` for the moments) of THAT row, and
  turned as [the axes of a steady polar](#the-axes-of-a-steady-polar) are. A
  rotor's own frame is never the source: its axes are not the geometry's. A
  second global-frame group adds its own eighteen and renames none.
- **A pproc that plots those six for no global-frame group gets one added by
  the run**, `MRP_TOTAL`, over every boundary, where the run has an `MRP` frame.
  A pproc that already plots them is left as it is, to the byte. A run made
  before 0.24.0 without such plots has no axes block, and `products.json` says
  so under `polars/<file>#axes`; the block is never a column of `NA`.

**Why the native export is not the source.** It states the **last time step
only**, which on an oscillating rotor is one instant of a cycle. It still ships,
as a health check.

**Why the columns are not renamed.** Nothing in this package knows which plot
label carries which coefficient, and a label invented by the package does not
fail loudly -- it writes `NA` down a whole column.

**The `[names]` dictionary (0.24.0).** A downstream tool may read other names, so
the pproc may state a dictionary, from a plot column AS THE EXPORT PRINTS IT to
the name the reader wants:

```toml
[names]
CL_MRP_TOTAL = "CL_TOTAL"
FX_HUB_PUSHER = "FX_PUSHER"
```

- It renames columns of the unsteady polar and of the averaged reductions
  (`time_average`, and the passage series). The plots table
  `probes/<point>_plots.csv` stays as the export prints it, because it is the
  source the others are read from; the per-blade and azimuthal tables carry
  columns that are no longer the export's own names and are not renamed.
- Undeclared, every name passes through exactly as printed.
- The axes and the `[equations]` read the export's names; the dictionary is
  applied last, to the heading alone.
- **The whole dictionary applies or none of it does.** An entry naming a column
  no plot of the point prints, or giving a column a name the table ALREADY
  carries, leaves every column under the export's name and is said in
  `products.json` (`polars/<file>#names`, `probes/<point>#names`) and as a
  warning. It never becomes a column of `NA`.
- **`CL` is taken.** The unsteady polar carries the native export's last-step
  `CL`, `CDi`, `CDo`, `Cx` and the rest in its setup content, as a health
  check, so a plot column cannot be renamed to one of those; `CL_TOTAL` can.
- Two entries giving one name, or a name that is not one word, are refused when
  the pproc is read.

---

## Rotor coefficients

`J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW`, one table per rotor, every column suffixed
with the rotor's alias. They make physical sense for **one** rotor and not for
several summed: the diameters and speeds that normalise them are different
numbers.

### Where an unsteady point's numbers come from

A steady point's row is built from the loads export. **An unsteady point's row
is the average of the PLOTS history over the row's window**, the same window the
unsteady polar and the reductions use, because the loads export of an unsteady
run states the last time step, one instant of a cycle.

- **The history is the rotor's own six components in the global `MRP` frame**,
  `FX, FY, FZ, MX, MY, MZ` in Newtons, over the rotor's own families, general
  and blades. It is found through the pproc: a `[[plots.groups]]` entry with
  `frame = "MRP"` whose families are exactly the rotor's, whatever it is
  called. Where the pproc plots none, the run adds one itself, `ROTOR_<ALIAS>`.
- **A group in a rotor's own frame is never the source.** Its force is stated in
  axes that turn with the rotor and its moment is already about the hub. A
  group that merely shares the alias's name over other families is not one either.
- **A row that states a window never holds an instant.** A point whose history
  does not cover the window, or holds no such columns, is LEFT OUT of the table
  and named in `products.json`, as the unsteady polar beside it does. The
  table's manifest entry states `source` and `window`.

Until 0.24.0 the history was looked for under `FX_<alias>`, a name no run
printed, so every unsteady rotor table silently held the last time step.

### `ETAW`

It is an efficiency, with the rotor's force vector turned to wind axes in
place of the thrust.

1. Take the full force vector in the rotor frame, `[Fx, Fy, Fz]_rotor`.
2. Carry it to the airframe body frame by the **transpose** of the
   rotor-to-body rotation.
3. Carry it to wind axes by the **AIAA** rotation, with **alpha and beta**.
4. Take the **X** component: `Fx_W`.
5. `ETAW = J * CTW / CP`, where `CTW = Fx_W / (rho n^2 D^4)` -- the wind-axis
   force nondimensionalised exactly as the thrust is, entering the same
   efficiency where `CT` enters. It stays **dimensionless**.

**It reduces to `ETA` when the shaft lies along the stream**, which is what makes
the column readable beside `ETA`. A caller that states no wind-axis force gets
`NA`, never the old cosine: publishing the superseded number under the corrected
name would leave a reader unable to tell which of the two they hold.

**It is two rotations on a vector, never the cosine of a scalar angle.** A cosine
discards the components that are not along the axis, which is exactly what the
rotation chain preserves.

### A static point

Every rotor coefficient reads `NA` on a static point except `J`, which is a real
`0.00000`. The export states coefficients normalised by the run's own dynamic
pressure; at `V = 0` that pressure is zero and the rotor's real thrust has been
divided away before the package sees it. **No rotor coefficient is recoverable
from a static point whatever the package does**, which is also why a hover figure
of merit cannot be offered: it needs a force the run does not state.

---

## What the package does NOT judge

The package checks whether the **numerical iterations within the last time
step** converged. It also rejects a frozen solve: at least two consecutive time
steps whose inner iterations after the first all print exactly zero velocity
residual and whose last inner iteration prints both residuals exactly zero.

A frozen solve is recorded as `FAILED_DIVERGED`, naming the first frozen step
and the count.

### The post log and the default warning rule (since 0.26.0)

**Nothing in the post blocks by default.** Every `write_campaign_products` run
creates `post.log` beside `products.json`, under `post/<matrix stem>/` or
`post/products/` when no matrix is named. The manifest names it under `log`.
A clean campaign writes the log too. Its header states the package version,
workspace, matrix stem, local time with UTC offset, and `check_frozen` choice.
Each WARNING names the point and product, the step where one applies, and what
would settle the issue. Every named manifest skip and every
`PyflightstreamWarning` emitted during the stage is recorded there. A rebuild
archives the previous log with the same timestamp as its products. An
interrupted post keeps its header and the warnings collected before it stopped.
Warning capture is process-wide, so concurrent posts in threads can put a warning
in another campaign's log; post one campaign per process until `reports/RPT-058`
is resolved.

A frozen solve, an unread native-log block, a reference mismatch, or a failed
point's status is a
reason to warn, not to withhold a computable product. Histories, instants and
averages remain available. A log that cannot be opened never ends the post.
A failed point fails alone: shared metadata comes from records that carry each
field, preferring successful records, and a record with none is a named run skip
without suppressing healthy points' products.
An empty or header-only unsteady log has no residual evidence: it warns by
default and refuses affected averages with `check_frozen=True`; a steady log
does not need unsteady residual pages.
No-data and malformed-export cases still cannot supply numbers; missing frame,
clock or layout facts cannot assign them to a requested product. These
impossibilities are named skips in both the manifest and the post log.
Superseded runs and inapplicable products retain their named explanations too.
Existing-output protection still requires an explicit rebuild request.

**`--check-frozen` means REFUSE INSTEAD OF WARN.** It opts into the earlier
refusals for affected averages and reference mismatches; the warning is still
written to `post.log`.
An excluded failed status is named under `runs/<run_id>` with the status and
flag; rebuilding retires its previous products according to the archive choice.
Averages wholly before a proven freeze keep their products. A freeze affects
all steps from its first frozen step onward. An unread block affects only the
samples that use it. Raw histories and explicitly instant products stay
available. The provenance document still digests every recorded output,
including the native log, and records an inaccessible file from its run record.

### The reducer states the plotted steps it reads

The reducer in `post/unsteady.py` reports its set of plotted steps through
`read_steps`, on the same code path that computes the average. The guard asks
for that set using the same resolved rotor families as the writer. It performs
no sample arithmetic, does not enumerate the declared interval, and does not
invent offsets from blades whose columns the history does not contain.

The azimuthal phase-locked average samples each azimuth of the final revolution
across the requested revolutions. Each interpolation reports its plotted
bracketing steps; an exact plotted moment reports that step alone. The guard
checks set membership for unread steps, not every step between the extremes.
A sparse history can reach far outside the declared window while reading none
of the intervening unplotted steps. Ordinary passage and time averages report
the whole plotted steps they actually take.

**Every nonzero interpolation weight counts, without a cutoff.** This keeps
the verdict true of the arithmetic: a tiny weight can still multiply a large
value. At 2.0000000001 steps per revolution the sample at 59.99999999995 reads
step 59 with weight about 5e-11; that step is included. The reducer's existing
clock tolerances select moments; they do not round their interpolation support.

Measured examples with dense plotted histories:

| History and plan | Plotted steps read |
|---|---|
| Totals only, two declared blades, three steps per revolution, window [59,61] | {59,60,61} |
| Totals only, 3.6 steps per revolution, four revolutions ending at 20 | {6,7,...,20} |
| Family alias expanding to two plotted blades, three steps per revolution, window [59,61] | {58,59,60,61} |

### Unread residual blocks and repeated markers

A residual page stopped before its closing separator is unread. Since 0.26.0,
a terminal marker block with no residual page is unread too, but only when the
log has already printed at least one residual page in an unsteady marker block.
A log whose markers never carry pages is not classified as cut. With earlier
pages present, a cut after `Iterat`, before the `Iteration` anchor finishes,
is unread (RPT-055). A page-less
marker followed immediately by another marker for the same step is a repeat
associated with per-step export actions; it is skipped without resetting the
residual evidence. It is not a terminal cut.

A frozen step immediately beside an unread step is reported unread too, in
either order, because the two consecutive steps might establish a freeze. A
log can prove a freeze and carry unread steps; both facts are kept and logged.
With `check_frozen=True`, either can refuse an affected average.

The per-blade table states one window over its passages. In opt-in refusal
mode, a refused passage between two kept ones refuses the whole table, because
joining the survivors would bridge the unread data. Losing passages only from
an end keeps a shorter contiguous product. In default warning mode all
computable passages remain in the product and the affected ones are logged.

It does **not** judge whether the time history has settled. There is no settle
tolerance, no convergence criterion over the history, and no point is failed for
one. **That judgement is the user's, made afterwards from the history.**

This is stated here rather than left out, because "the package does not check
this" is exactly the kind of thing a reader assumes the other way round.

---

## The token for a value that does not exist

Every product writes **`NA`**. Not a zero, and not a blank.

- **Not a zero**, because zero is a value a row can genuinely have -- an advance
  ratio at rest is exactly zero and is a measurement -- so a zero written for
  "no value" is a number a reader would believe.
- **Not a blank**, because a blank is indistinguishable from a value that went
  missing, from a column that never applied, and from a writer that stopped
  halfway.

The token lives in one place, `pyflightstream._tokens.NOT_APPLICABLE`, below
every layer. **Readers still accept `-`**, which is what files written before
0.23.0 carry.
