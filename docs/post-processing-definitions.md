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
    `cases/workflows/` is a reduction you are about to get subtly wrong: three of
    the definitions below were implemented as a declared field with no caller,
    which reads exactly like a finished feature.

## Contents

- [Warnings and recorded diagnostics](#warnings-and-recorded-diagnostics)
- [The vocabulary](#the-vocabulary)
- [What every product states](#what-every-product-states)
- [The axes of a steady polar](#the-axes-of-a-steady-polar)
- [The sections table, and which row is which](#the-sections-table-and-which-row-is-which)
- [The probes table](#the-probes-table)
- [The reductions of an unsteady point](#the-reductions-of-an-unsteady-point)
- [`time_average`](#time_average)
- [`per_blade`](#per_blade)
- [`phase_locked`](#phase_locked)
- [`per_revolution`](#per_revolution)
- [The per-station harmonics](#the-per-station-harmonics)
- [The disc maps](#the-disc-maps)
- [The averaging window](#the-averaging-window)
- [Native surface flow exports](#native-surface-flow-exports)
- [The solver's own plots](#the-solvers-own-plots)
- [The boundary-layer profile is not produced](#the-boundary-layer-profile-is-not-produced)
- [A volume section](#a-volume-section)
- [The additional post](#the-additional-post)
- [The unsteady POLAR](#the-unsteady-polar)
- [The mesh face count](#the-mesh-face-count-since-0340)
- [Rotor coefficients](#rotor-coefficients)
- [Tip and helical Mach numbers](#tip-and-helical-mach-numbers)
- [What the package does NOT judge](#what-the-package-does-not-judge)
- [The token for a value that does not exist](#the-token-for-a-value-that-does-not-exist)
- [Quasi-steady wheel corrections](#quasi-steady-wheel-corrections)
- [The installed-frame copy of a product table](#the-installed-frame-copy-of-a-product-table)
- [The inflow tools' products](#the-inflow-tools-products)
- [The quasi-steady rotor](#the-quasi-steady-rotor)
- [The acoustic signals product](#the-acoustic-signals-product)
- [The post of other records](#the-post-of-other-records-since-0320)
- [Posting and collecting some simulations](#posting-and-collecting-some-simulations-since-0330)

---

## Warnings and recorded diagnostics

Postprocessing warnings are quiet in command-line runs by default. This applies
to every warning category; errors, progress and the final command status remain
visible. Pass `--pproc-warnings` to `pyfs-matrix run`, `post` or `collect` to
show concise category counts and the detailed log location on stderr.

Every postprocessing stage records all its warnings and skipped products in
`post.log` and `post.log.json`, including category, severity, point, product,
message and any stated remedy. Python callers retain ordinary warning-filter
behavior. Terminal presentation does not change product values or CSV bytes.

`pyfs-matrix post <matrix> --workspace <root> --diagnostics` prints a complete
Markdown report of the saved logs. It reports their timestamps and package
versions and states explicitly when no saved log exists. It does not rerun
postprocessing or write products, guides, manifests or archives. A malformed log
is an error, not a clean diagnostic result. Capture stdout to save the report;
the CLI outcome signature stays on stderr.

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

**The first column of every table is the polar, and no line precedes the
header** (since 0.27.0). Every table the post writes under `post/<matrix>/`,
the additional post's under `additional/<pid>/` included, and the campaign
sweep table beside them open with `POL`, named as the run matrix names its
polar column, holding in each row the POL of the point that row comes from
(`test_g16_every_table_the_post_writes_opens_with_the_polar_of_its_rows`). A
table whose rows mix polars, the campaign sweep, carries each row's own. What a
table states about all its rows is a column too, never a line before the
header: the rotor table's rotor is its `ROTOR` column, right after `POL`. `POL`
is the only column that states the polar: a steady polar table and its super
file written by 0.26.0 opened with it as `POLAR`, and no table the post writes
carries `POLAR` since 0.27.0
(`test_g16_every_table_the_post_writes_opens_with_the_polar_of_its_rows`).
Every other column keeps its name and its order after them. The solver's own
files under `datapoints/DP-<point>/` are never rewritten, and the fixed-width
custom polar (`.dat`) keeps the title lines its format specifies; a super file
written in the fixed-width `legacy_polar` format opens with `POL` too.

**No cell holds a comma or a double quote, and no cell is quoted** (since
0.27.0), so a reader that splits each line on `,`, as `numpy.genfromtxt` does,
reads the header and every row to the same count. A text cell that would hold a
comma writes `;` in its place: a list the super content echoes from the matrix
row reads `-2.0;0.0` under `SWEEP_VALUES` and `MACH:0.2; REmi:2.3; ALPHA:sweep`
under `FLIGHT_CONDITION`. A double quote is written as a single one, and a line
break as a space
(`test_g16_the_echoed_matrix_cells_write_their_lists_with_semicolons`).

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
| `J` | - | the advance ratio the row REQUESTED; `NA` on a row that turns no rotor, and on one that states its speed as `RPM` (in the two quasi-steady tables it is the ratio the rotor ran at where the row requested none, below) |
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
`probes/<point>_plots.csv` states NO condition, on purpose: after `POL` it is the
export's own header, and the reductions read every column after `POL` back as a
plotted quantity.

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
export. A table written before 0.24.0 used the solver's `CL`, so its `CLS`
and `CLW` are higher by that much.

---

## The sections table, and which row is which

`sections/<point>_sections.csv` is ONE export of the solver holding EVERY
distribution the pproc declares, the wing in `XZ` and each blade in its own
frame, one after another with no marker between them. Each row leads with:

| column | what it is |
|---|---|
| `POL` | the polar of the point, as the matrix names it (since 0.27.0) |
| `STEP` | on an unsteady point, the run's last TIME STEP, from the run record: the export is written when the march ends, and its own header counts the solver's inner iterations, not steps ([RPT-053](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-053_what-an-unsteady-export-states-and-when_2026-09-19.md)). On a steady point, the solver iteration the export states. One name across every table |
| `FAMILY` | the geometry families of the row's distribution, joined by `+` |
| `PLANE` | the cutting plane of that distribution |
| `ROTOR` | the rotor whose blades those families are; `NA` for a surface no rotor owns |
| `AZIMUTH` | where the block's blade is at `STEP`, in degrees, wrapped to one turn: the block's OWN blade when it cuts the families of one blade of its rotor, else where BLADE ONE OF THAT ROTOR is; `NA` without a rotor |

`AZIMUTH = (blade1.azimuth_deg + sense * STEP * 360 / steps_per_revolution) mod 360`,
with the datum, the sense of rotation (the sign of the rotor's speed) and the
steps per revolution all taken from THAT rotor. Two rotors at two speeds have
two azimuths at one step, and a wing has none. A block that cuts the
families of ONE blade of its rotor (the rotor's `families_blades`, blade `n`
from 1, expanded through the aliases) states THAT blade's azimuth, `AZIMUTH`
above placed `(n - 1) 360 / B` ahead (0.31.0,
`pyflightstream.post.axes.placed_blade_azimuth_deg`, the one home), whatever
the sense of rotation: the sense turns the clock, not the blades' places on
the disc. So the four blade blocks of a four-blade rotor read four azimuths a
quarter turn apart, in the sections table and in the sections series alike.
A block over several blades, over the rotor's general families, or of a rotor
whose record states no blade grouping keeps blade one's azimuth. The sections of a quasi-steady
WHEEL point hold every clocking, and there a block of one blade states where
THAT blade is at its clocking ([The quasi-steady rotor](#the-quasi-steady-rotor)).

The run records which distribution is which, because the script states
surfaces by index and nothing at post can name them. A run recorded before
0.24.0 states `NA` in all four, and so does a record whose blocks do not add
up to the rows the export holds: a row given its neighbour's family is worse
than a row given none.

**It is one instant.** On an unsteady point this table is the distribution at
`STEP`, not an average over the window, and its `products.json` entry says
`"kind": "instant"`. The history is `series/<point>_sections_series.csv`,
which carries the same identity on every row.

The sections table of an additional post holds the run's rows first and the
additional pproc's after them; [The additional post](#the-additional-post) says
how each is named.

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
On a quasi-steady WHEEL point each file holds every clocking, with a
`CLOCKING` column after the export's own columns and the azimuth of each
block's blade at that clocking, as the sections table does
([The quasi-steady rotor](#the-quasi-steady-rotor)).

With `EXPORT_UNSTEADY_AFTER_REV` or `EXPORT_UNSTEADY_AFTER_ITER`, each file holds
**every available stamped step**, in ascending order. Without per-step exports,
it holds the end-of-run export, with `STEP` interpreted as in the existing
sections table above. The existing end-of-run table and combined
`series/<point>_sections_series.csv` remain available.

Rows lead with `POL, STEP, time_s, FAMILY, PLANE, ROTOR, AZIMUTH`, then the
shared condition block, then the export's columns. Sectional loads retain
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
frame and count. Since 0.27.0 that match reads the geometry's boundary names
where they are known, for a block recorded in a common frame (see *The
geometry's names* under the integrated loads below): a block whose only
possible emitter is an entry citing a word nothing resolves, such as a rotor's
name with no rotor definition in hand, is that entry's, and the split file is
named after it. In a frame spelt like a rotor's, where the names settle
nothing because this match holds no rotor definition, where the names leave
no single owner, where two boundaries carry one name, or where no file carries
the recorded hash, the recorded cuts decide as before and the rows are kept. An
ambiguous match is a named skip. Since 0.29.0, a missing recorded layout can
be recovered in memory from the exact hash-verified saved script, the recorded
geometry's boundary order, and a uniquely matching recorded pproc. Only explicit
append-only distribution commands with known frame identities qualify. The
manifest and original exports remain unchanged. A changed or missing script,
ambiguous selection, section deletion, unknown frame, or continuation without its
predecessor layout retains the named refusal in `products.json`.
A layout whose counts disagree with an export is likewise refused for that
export kind, rather than assigning rows to guessed distributions.

**The empty layout is a layout (since 0.27.0).** A run whose script adds or
removes no surface section records `sections_layout = []`, which is every
steady point of a pproc declaring no distribution: its sections exports state
`Number of Surface Sections: 0`. With no distribution declared and none
created there is nothing to split and nothing is named as skipped
(`test_a_steady_row_that_created_no_distribution_is_not_refused_a_split`); a
declared entry the geometry left out gets its named skip as above
(`test_an_entry_the_geometry_leaves_out_is_named_as_such_not_as_a_missing_layout`).
A continuation records the layout of the run it continues, whose saved
simulation it reopens
(`test_a_continuation_records_the_layout_of_the_run_it_continues`). A record written before 0.27.0 with no layout at all is given the
empty one when its recorded script is on disk, its bytes hash as the record's
`script_sha256` says, and it carries none of `NEW_SURFACE_SECTION_DISTRIBUTION`,
`CREATE_NEW_SURFACE_SECTION`, `DELETE_SURFACE_SECTION` and
`DELETE_ALL_SURFACE_SECTIONS`; that is read off the script and needs no new
run (`test_an_old_record_takes_the_empty_layout_its_script_proves`). A record
whose script creates a section or no longer hashes as recorded, and a
continuation recorded before 0.27.0, are not given it, and their split stays
refused (`test_an_old_record_whose_script_creates_a_distribution_keeps_the_refusal`,
`test_an_old_record_whose_script_no_longer_hashes_keeps_the_refusal`,
`test_an_old_continuation_keeps_the_refusal`).

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
the sectional CSV holds the seven export columns and the context written by
0.25.1, behind the `POL` column every table opens with since 0.27.0, with no
additional column. This is a post-processing
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
block's set.

**The geometry's names (since 0.27.0).** Each run records `inventory`, the
geometry's boundary names in the solver's order as the script read them at
`OPEN`. A record written before 0.27.0 carries none, and the post reads them
from the mesh block of the geometry file whose sha256 the record carries in
`inputs_sha256`: the simulation's own staged copy first, then the library's
file of that name. The hash, never the name, says the file is the one that
ran, and it is computed from the file each time its names are read, before
and after the read, never remembered: a geometry changed or deleted since the
run recovers nothing, nor does one changed while its names are read, and the
`<stem>.boundaries.toml` sidecar is not read for it, because nothing hashed
it. The names settle a selection ONLY for a block recorded in a common frame,
or where the live reference's rotor definitions are in hand (integration
alone ever has them). A block recorded in a frame spelt like a rotor's
(`<alias>_RMRP`, `<alias>_RMRP<n>`, `<alias>_SMRP`, `<alias>_SMRP_ORIGINAL`)
may be an expanding entry's emission, and the builder resolved that entry
against the reference's rotor families, never over the names alone:
`Blade1` on `RMRP` asks for the rotor owning Blade1, and `Blade` for every
rotor with a Blade family. With no rotor definition in hand such a block is
matched as without the names, below, as in 0.26.0. No block records which
entry emitted it, so a user's own frame spelt like a rotor's (`X_RMRP`) is
read that way too, and two entries on it stay refused by name. A run that
turned a rotor is matched as without the names in any frame unless the
rotor definitions are in hand, because the builder reads a word naming a
rotor as that rotor's families before any stem: a rotor `Prop` beside
boundaries Prop1 and Prop2 is not the stem `Prop`. Where the
names are read, a selection is read by the export builder's own expansion
over them, for integration and for the ownership of a legacy layout alike:
a family stem, a numbered name, `all` and the aliases resolve as they
did at export, and an `all` block (recorded as an empty family list) is the
whole inventory. So `families = "Blade"` integrates a recorded Blade1 and
Blade2 block where the geometry carries no third blade and no boundary named
`Blade`, and is refused, by name, where it carries either. Names that give
one name to two boundaries settle nothing: the builder leaves that name out
of its labels, so the rest no longer say what `all` or a stem selected, and
the record is read as one without the names. A word that
resolves to nothing over the names and that no alias or rotor definition in
hand names (a rotor's name with no rotor definition) leaves its entry a
possible owner of every block of its frame kind, plane and count, so the
integration match is refused by name; for the ownership of a legacy layout
that same entry owns a block by elimination, when every other entry either
did not emit it by the builder's reading or could not have. An entry citing
a frame whose `_ORIGINAL` twin the run holds emits into both frames, so over
the names it stays a possible owner of a block on the twin beside the entry
citing the twin, and the integration match there is refused by name.

**Without the names** (a run that opened no geometry declaring them, an
older record whose geometry is gone or changed, or names that give one name
to two boundaries), ownership of a legacy layout
(a name and a grouping for raw files, no number added) resolves the recorded
pproc's selectors over the recorded cuts, the only evidence there is, a
family stem and a numbered name included. Integration is never matched that
way, whoever asks, because the post cannot tell a recorded specification
from a current one (two resolutions of one artifact id compare equal after an
edit, and a recorded entry may have emitted nothing): a selector is knowable
only by exact recorded boundary names, by aliases and by the live reference's
rotor definitions, whose members count even when they have no sectional
block; without the geometry's names layout silence never proves a family
absent, and any other word (a family stem, an unrecorded name, a
whole-geometry selector) leaves membership uncertain, establishes no
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

Each row opens with `POL`, then `PROBE`, `X`, `Y`, `Z`, `FRAME`, `STEP` and the
condition block, then the export's own columns (steady) or the sampled
parameters (unsteady).

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

## The reductions of an unsteady point

An unsteady point's plots table is its raw time history, one row per solver
time step. The stage writes its reductions beside it, one file per
reduction, each named in `products.json` with the reduction and the window
it used (PFS-2015.04); raw is the plots table itself and is written once,
never a second time under another name. Which reductions apply is the run
type's, and the window is the one the row states ([the averaging
window](#the-averaging-window)). Each reduction is defined in its own section
below: [`time_average`](#time_average), [`per_blade`](#per_blade),
[`phase_locked`](#phase_locked), [`per_revolution`](#per_revolution) and [the
per-station harmonics](#the-per-station-harmonics).

| file | run type | window |
|---|---|---|
| `probes/<point>_time_average.csv` | `unsteady_rotor` and `unsteady` | the AVERAGING WINDOW the row states, `LAST_REVS_AVG` on a rotor row and `LAST_ITERS_AVG` on a rotorless one, ending at the run's last step; without any (a record made before 0.24.0, since a new plan of such a row is refused), a rotor row's last revolution (from `DELTA_THETA` and `REVOLUTIONS`, or `RPM` and `DELTA_TIME`), and a rotorless row's whole run (`DELTA_TIME` and `TIME_ITERATIONS`). One row |
| `probes/<point>_phase_locked_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | WITH a `[phase_locked]` table in the pproc: the last `last_revolutions_avg` revolutions OF THAT ROTOR, one row per azimuthal position, each value the mean across those revolutions at that azimuth. WITHOUT it: the time-average window cut into blade passages OF THAT ROTOR, one of its revolutions over its own blade count, a trailing partial passage dropped; one row per passage |
| `probes/<point>_per_blade_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors | ONE window shared by every blade: the row's `LAST_REVS_AVG`, counted in THAT ROTOR's revolutions and ending at the run's last step, and without the key that rotor's last complete revolution; ONE ROW PER BLADE since 0.24.0, each with its `BLADE`, its `FAMILY` and its `AZIMUTH_START` and `AZIMUTH_END` over that window |
| `probes/<point>_per_revolution_<ALIAS>.csv` | `unsteady_rotor`, a row naming its rotors (since 0.31.0) | ONE ROW PER COMPLETE REVOLUTION of that rotor, cut on ITS OWN steps per revolution from the written plots table: the mean of every plotted column and, from the second revolution on, each column's drift from the previous revolution in per cent. A trailing partial revolution is excluded and named under `skipped`. The pproc's optional `[per_revolution]` table declares `drift_limit_pct` (positive, default 1): when the LAST revolution's change of a force or moment column exceeds it in per cent of the largest previous mean of the same kind in its group (an in-plane force against the thrust, an in-plane moment against the torque), `post.log` carries a WARNING and nothing is blocked. [Definition of record](#per_revolution) |
| `sections/<point>_harmonics.csv` | `unsteady_rotor` with per-step sectional exports, and a `qsteady_rotor` wheel (since 0.31.0) | THE LAST COMPLETE REVOLUTION of each rotor, on its own steps per revolution, from the written sections series; on a wheel every blade at every clocking of the sections table. Per rotor, blade station and sectional load quantity, the least-squares `H0`, 1P and 2P amplitude and phase over the samples' blade azimuths; a harmonic short of distinct azimuths (1P needs 3, 2P 5) is `NA` and said once in `post.log`. [Definition of record](#the-per-station-harmonics) |
| `probes/<point>_phase_locked.csv` | `unsteady_rotor`, a row naming no rotor by alias | WITH a `[phase_locked]` table: the last `last_revolutions_avg` revolutions, one row per azimuthal position. WITHOUT it: the time-average window cut into blade passages, one revolution over `BLADES` steps each, a trailing partial passage dropped; one row per passage |
| no per-blade table | `unsteady_rotor`, a row naming no rotor by alias | No reference block identifies the blade families; `products.json` says why the table is skipped |
| `surfaces/<point>_time_average.dat` (and `.vtk` with `[exports] vtk`) | `unsteady_rotor` and `unsteady`, WITH a `[time_averaging]` table in the pproc (since 0.28.0) | the table's `last_iters` or `last_revs`, ending at the run's last step: the surface exported at every step of it, averaged panel by panel by the package ([the definition](#native-surface-flow-exports)) |

**`per_blade` IS ONE ROW PER BLADE OVER ONE SHARED WINDOW (0.24.0).** Until
0.23.0 it cut the last revolution into one window per blade, which put each blade
in a different stretch of the history; 0.23.0 wrote one window and ONE row. Since
0.24.0 every blade is averaged over the same window and has its own row, with its
start and end azimuth in columns, as [its definition](#per_blade) asks. The azimuthal form of
`phase_locked` that page defines is written where the pproc declares
`[phase_locked]`.

Every window is counted in solver steps, inclusive, 1-based, and row `k` of
the plots table is step `k`; the table's own time column is averaged like
any other column and is not read as the clock. The average is the one
implementation of blade-passage averaging the package holds
(`pyflightstream.post.blade_passage_average`), applied once per window, and
it is taken over the WRITTEN plots table, so a reduction can be recomputed
from the file beside it. The windows travel on the run record: `pyfs-matrix
run` resolves them off the row when it writes the record (`reductions` in
`runs.json`), and `pyfs-matrix post` reads them from there, with one
exception: the averaging window is resolved again from the matrix as `post`
reads it (`LAST_REVS_AVG` or `LAST_ITERS_AVG`), against the clock the record
already carries, so the key can be edited and `post` re-run with no solver.
Where the matrix names no key, the window the run recorded stands. A reduction the
row cannot window is listed under `skipped` with the reason, keyed by the
file it would have been: a rotor row that names NO rotor by alias and
states no `BLADES` skips the two passage reductions; a plots table shorter
than the window skips every reduction over it; a record written before this
field existed skips the time average naming the record. Not applicable is
not skipped: a rotorless point lists no per-blade file anywhere.

**SINCE 0.15.0 A ROW THAT NAMES ITS ROTORS REDUCES PER ROTOR** (FR-68), and
it needs no `BLADES` of its own: each rotor's blade count is the one its
rotor block declares, and each rotor's blade passage is ITS OWN
revolution, `60 / (rev per minute * the solver step)`, divided by its
blades. A transition row turning four lifters at 2200 rev/min and a pusher
at 900 reduces the two over passages of different lengths in one run, which
one file per reduction cannot hold, so the files name the rotor and the
flat `<point>_per_blade.csv` is listed under `skipped` with a reason naming
the files written instead. The windows live on the run record under
`rotors` (`pyflightstream.cases.workflows.ROTORS_KEY`), alias to that
rotor's block, and each written file's manifest entry carries a `rotor`
field, so the rotor is readable without taking a file name apart. The two
reductions that are per rotor are named by
`pyflightstream.cases.workflows.PER_ROTOR_REDUCTIONS`; the time average is
not among them, because it is one window of the whole point whatever turns
in it. A rotor whose motion cannot be resolved is a SKIP under its own name
rather than an absence, so a rotor never simply vanishes from the products.

---

## `time_average`

One average of the whole point over one window. It is what a POLAR row of an
unsteady point is built from.

**One window per point.** Not one per rotor, because a point has one history.

`probes/<point>_time_average.csv` opens with `POL`, `REDUCTION`, `ROTOR`,
`WINDOW`, `FIRST_STEP`, `LAST_STEP`, `STEPS`, then the condition block and the
moment point, then the plotted columns averaged over the window. The passage
series a pproc without `[phase_locked]` gets under the phase-locked name has the
same columns.

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

**The rows.** Each row leads with `POL`, `REDUCTION`, `ROTOR`, `BLADE`, `FAMILY`, the
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
with `POL`, `REDUCTION`, `ROTOR`, `AZIMUTH`, `STEP`, `REVOLUTIONS`, the steps the
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

## `per_revolution`

!!! note "New in 0.31.0"
    The one product that answers "has the rotor's load settled from one
    revolution to the next?" from the history the post already wrote.

One row per COMPLETE revolution of one rotor, each column of the plots table
averaged over that revolution, and from the second revolution on how far that
mean moved from the previous revolution's.

**It is read from the WRITTEN plots table.** `probes/<point>_plots.csv` is read
back by `plots_table_series`, as every reduction is, and the raw export is not
read again: a reduction is of the file a user holds and can be recomputed from
it.

**Which files.** A point of an `unsteady_rotor` row that names its rotors gets
`probes/<point>_per_revolution_<ALIAS>.csv`, one per rotor, each cut on THAT
rotor's own `steps_per_revolution` from the run record's reductions plan (a
rotor turning at another speed has another revolution). A row that states its
clock flat and names no rotor by alias gets `probes/<point>_per_revolution.csv`,
its `ROTOR` `NA`. A steady point and a plain unsteady one have no revolution and
no file. The product is registered in `products.json` like the other
reductions, with `reduction` = `per_revolution`, its `windows` (one per
revolution) and its `rotor`.

**How the history is cut.** Revolution `k` is rows `(k-1) * N + 1` to `k * N` of
the table, counted from its first row, where `N` is the rotor's steps per
revolution rounded to a whole solver step, as the phase-locked reduction does.
A history that starts at step 1 cuts at steps 1 to `N`, `N+1` to `2N` and so
on. Each mean is the package's one average over that window, the one the time
average takes.

**A partial last revolution is EXCLUDED, and said.** The steps after the last
complete revolution are not averaged: their mean would be the mean of another
length of history under the same name. `products.json` states it under
`skipped`, keyed `probes/<point>_per_revolution_<ALIAS>.csv#partial`, and the
post log carries a WARNING line naming the point, the file, the complete
revolutions and the steps left over. A table with not one complete revolution
writes no file and says why under `skipped`, and a rotor whose record states no
steps per revolution (its speed or the solver time step was not resolved) is
named the same way.

**The columns.** `POL`, `REDUCTION` (`per_revolution`), `ROTOR`, `REVOLUTION`
(counted from one), `FIRST_STEP`, `LAST_STEP`, `STEPS` (the revolution's length),
the condition and reference block, `XMOM`, `YMOM`, `ZMOM`, then the mean of every
plotted column under the name the plots table carries (or the pproc's `[names]`
entry for it), then `<column>_DRIFT_PCT` for each of them. The plots table's
clock is not a plotted column and is not averaged.

**The drift** of a column at revolution `k >= 2` is

    (mean_k - mean_(k-1)) / |mean_(k-1)| * 100

in per cent: positive where the mean rose, whatever the sign of the quantity. It
is `NA` on the first revolution, and `NA` where the previous mean is exactly
zero, which has no relative change. `NA` is the package's one token for a value
that does not exist.

**The declared threshold.** The pproc may declare

```toml
[per_revolution]
drift_limit_pct = 1.0
```

`drift_limit_pct` is positive (zero and negative values are refused) and
defaults to 1 per cent where the table or the key is absent.

**The warning judges a load against its SCALE, not against itself** (since
0.33.0). A force or moment column is a plotted column whose parameter (the text
before the first underscore) is one of `FX`, `FY`, `FZ`, `MX`, `MY`, `MZ` or the
force coefficients `CL`, `CDI`, `CDO`, `CD`; the text after it is the column's
group. Its KIND is a force (`FX`, `FY`, `FZ`), a moment (`MX`, `MY`, `MZ`) or a
force coefficient (`CL`, `CDI`, `CDO`, `CD`), and the columns of one kind and
one group are the components of one load of one body in one frame. The SCALE of
a column at the last revolution `n` is the largest magnitude among the means at
revolution `n - 1` of the columns of its kind and group, so an in-plane force is
judged against the thrust and an in-plane moment against the torque. The column
warns when

    |mean_n - mean_(n-1)| > drift_limit_pct / 100 * scale

For the column that IS the largest of its group this is its drift in the table
exceeding the limit. A near-zero component (an in-plane force of a rotor in
uniform inflow) has a large relative drift that is noise and is not warned
about unless its change is large against the load it is a component of. A group
whose means at `n - 1` are all zero or not numbers, and a column whose own means
are not numbers, give no warning.

The WARNING line in `post.log` names the point, the rotor, the column, its
change in per cent of the scale, the scale and the column that sets it, the
change itself and the limit:

```
WARNING point=<point> product=probes/<point>_per_revolution_<ALIAS>.csv: rotor '<ALIAS>' column FX_MRP_TOTAL drifts +4.7619 per cent of its scale 10.5 (the magnitude of FX_MRP_TOTAL, the largest force mean of its group in the earlier revolution; a change of +0.5) between revolution 2 and revolution 3, over the drift limit of 1 per cent ([per_revolution] drift_limit_pct): the last revolution is still moving
```

The `<column>_DRIFT_PCT` columns of the table keep the relative drift defined
above; only the warning reads the scale. A probe or any other plotted column has
a drift and no warning. **The warning never blocks**: the table is written whether
or not the limit is exceeded, as nothing in the post blocks by default. Only a
history with at least two complete revolutions can drift. The table is read again
by `pyfs-matrix post`, so declaring or editing the limit needs no new run.

A frozen solve is judged like every other average: the default warns, and the
explicit refusal mode skips the table naming the reason.

---

## The per-station harmonics

!!! note "New in 0.31.0"
    The 0P, 1P and 2P content of every blade station's load around the
    disc, from the sections the post already wrote.

`sections/<point>_harmonics.csv`, one per rotor point that has samples at
several azimuths. For each rotor, each blade station and each sectional load
quantity of the sections export, the least-squares fit

    load(psi) = H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)

over every sample of that station, `psi` being the sample's blade azimuth in
degrees.

**It is read from the WRITTEN sections.** The samples are the rows a user
holds, read back, and `psi` is the table's own `AZIMUTH`: no azimuth is
computed again. Which rows:

- a `qsteady_rotor` WHEEL point: every blade at every clocking of
  `sections/<point>_sections.csv` (`CLOCKING`), whose `AZIMUTH` is each
  block's own blade at its clocking
  ([The quasi-steady rotor](#the-quasi-steady-rotor)). The wheel's premise is
  identical blades, so blade `n` at clocking `i` is one more azimuth of the
  same station: a wheel of `N` blades at `k` clockings gives `N k` samples,
  `N k` distinct azimuths `360 / (N k)` apart. A sector point has one azimuth
  and no file.
- an `unsteady_rotor` point: every blade at every step of the LAST COMPLETE
  REVOLUTION of that rotor in `series/<point>_sections_series.csv`, the
  per-step sectional exports. Revolution `m` is steps
  `first + (m - 1) N` to `first + m N - 1`, counted from the series' first
  stamped step as [`per_revolution`](#per_revolution) counts from its first
  row, with `N` the rotor's own `steps_per_revolution` from the run record
  rounded to a whole step; the steps after the last complete revolution are
  not read. Since 0.31.0 the series states each block's OWN blade's azimuth
  (blade `n` of the rotor's `B` at blade one's plus `(n - 1) 360 / B`, the
  blades placed ahead of blade one whatever the sense of rotation, as the
  per-blade table places them,
  `pyflightstream.post.axes.placed_blade_azimuth_deg`), and the fit reads it
  as stated; a series written before 0.31.0 stated blade one's on every block.

A sample is a BLOCK of one blade: the consecutive rows of one clocking or
step whose `FAMILY` names families of one blade of the rotor, blade `n` being
the `n`-th entry of its `families_blades` (expanded through the aliases). A
block of several blades, or of a family no blade names, is not a sample.

**The stations.** Station `j` is the `j`-th row of every blade block of the
rotor, at the radius `STATION_R_M = |Offset|` of the first sample, read as the
radius of a distribution cut along the blade from the hub, as the validity
columns read it. Every sample must hold its station within `1e-6` of the
first sample's largest radius: a station where one does not is left out and
named in `products.json` `skipped` under
`sections/<point>_harmonics.csv#rotor=<ALIAS>#station=<j>`, and a rotor whose
blocks hold different numbers of stations, or which has no block of one blade
at a stated azimuth, under `...#rotor=<ALIAS>`; each is a WARNING line in
`post.log` too, and the other stations are written.

**The quantities.** Every numeric load column of the export after the
condition: `Fx`, `Fz` and `Moment` of today's sectional loads export, each in
the export's own axes and units (N/m, N m/m). The station's place (`Offset`,
`Chord`, `X_QC`, `Z_QC`) and the columns the post adds (`CLOCKING`, `K_1P`,
the validity and the integrated strips) are not fitted. A harmonic of an
in-plane quantity describes the blade's load only where the export's axes
turn with the blade, as they do for a distribution cut in the blade's own
frame.

**The columns.** `POL`, the condition (`CONTEXT_COLUMNS`, the sections
table's own values), then

| column | what it is |
|---|---|
| `ROTOR` | the rotor's alias |
| `QUANTITY` | the export's column fitted |
| `STATION_R_M` | the station's radius, m |
| `R_OVER_R` | `STATION_R_M` over half the rotor block's `diameter_m`: the wheel's record's, and on an unsteady point the reference's the row names today; `NA` where no reference can be asked |
| `SAMPLES` | the samples fitted |
| `DISTINCT_AZIMUTHS` | how many distinct azimuths they hold, two within `1e-6` deg (360 and 0 included) being one |
| `H0` | the mean, 0P |
| `H1_AMP`, `H1_PHASE_DEG` | `A1` and `PHI1` |
| `H2_AMP`, `H2_PHASE_DEG` | `A2` and `PHI2` |
| `RESIDUAL_RMS` | the root mean square of the samples less the fit made |

Amplitudes carry the quantity's unit. One row per rotor, quantity and
station, in that order.

**The phase convention.** `PHI_k` is in degrees in `[0, 360)`, in the
convention of the table's `AZIMUTH` (so on a left-hand rotor too): the `kP`
term peaks where `k psi = PHI_k`. The 1P term peaks at the azimuth `PHI1`;
the 2P term at the two azimuths `PHI2 / 2` and `PHI2 / 2 + 180`. The fit is
`H0 + a_k cos(k psi) + b_k sin(k psi)` by `numpy.linalg.lstsq`, with
`A_k = sqrt(a_k^2 + b_k^2)` and `PHI_k = atan2(b_k, a_k)`.

**Too few azimuths is `NA`, said once.** A fit up to `kP` has `2k + 1`
unknowns, so 1P needs 3 distinct azimuths and 2P needs 5. A station with
fewer carries `NA` in that harmonic's amplitude and phase, and the fit is made
without it (`H0` alone below 3); `post.log` carries ONE WARNING line per rotor
and harmonic that is `NA` anywhere, naming how many rows and the fewest
azimuths:

```
WARNING point=<point> product=sections/<point>_harmonics.csv: rotor 'PROP': the 2P harmonic is NA in 9 row(s), whose stations hold as few as 4 distinct azimuth(s); a 2P fit needs 5
```

A wheel of 2 blades at 2 clockings (4 azimuths) has a 1P fit and no 2P. Nothing
blocks: the table is written.

**Not written, and said.** An unsteady rotor whose record states no
`steps_per_revolution`, or whose series holds no complete revolution, is named
under `sections/<point>_harmonics.csv#rotor=<ALIAS>`; where no station of any
rotor could be fitted the file is not written and `products.json` names it.
An unsteady rotor point that cuts sections (its record states a sections
layout) and has no sections series (its row exported no per-step sectional
loads, or the series was not written), no export window, or no rotor its
record states is named under `sections/<point>_harmonics.csv`, with
a WARNING line in `post.log`.

**The manifest.** `products.json` registers the file with `kind`
`harmonics`, `source` `wheel clockings` or `unsteady last revolution`,
`samples` (the blade samples fitted, all rotors) and `samples_by_rotor`; a
wheel's entry adds `clockings`, an unsteady point's `revolution` (the first
and last step fitted, per rotor) and `steps_per_revolution`.

---

## The disc maps

!!! note "New in 0.32.0"
    The sectional load by radius and azimuth over the disc, from the
    sections the post already wrote.

`sections/<point>_disc_<ROTOR>_<QUANTITY>.csv`, one per rotor and sectional
load quantity (`Fx`, `Fz`, `Moment` on today's export) of a rotor point that
has sections. Where the harmonics fit a load's content around the disc, the
disc map is the load itself, sample by sample, so it can be drawn as a polar
map in the tool of the user's choice. No figure is drawn: the table is the
product.

**It is read from the WRITTEN sections**, as the harmonics are, and `AZIMUTH_DEG`
is the table's own or placed by `pyflightstream.post.axes`: no azimuth is computed again here. The samples are the same:

- a `qsteady_rotor` WHEEL point: every blade at every clocking of
  `sections/<point>_sections.csv`, `SAMPLE` being the `CLOCKING`;
- an `unsteady_rotor` point: every blade at every step of the last complete
  revolution of that rotor in `series/<point>_sections_series.csv`, `SAMPLE`
  being the `STEP`.

**The rows.** One row is one blade station at one sample: `POL` and the
condition columns of every table of the post, then

| Column | Meaning |
|---|---|
| `ROTOR`, `QUANTITY` | the rotor's alias and the sectional load column the file maps |
| `SAMPLE` | the clocking of a wheel, the step of an unsteady point |
| `BLADE` | which blade of the rotor, from 1, in the order of its `BLADE_FAMILIES` |
| `AZIMUTH_DEG` | where THAT blade is at that sample, in `[0, 360)`: the table's own azimuth of the block (a table that states blade one's is placed by `pyflightstream.post.axes`) |
| `STATION_R_M` | the station's radius, `|Offset|`, in metres |
| `R_OVER_R` | the radius over the rotor's radius (half its diameter), or `NA` where the diameter is not known |
| `VALUE` | the sectional load of that station at that sample, as the export states it |

Rows run by `AZIMUTH_DEG`, then `STATION_R_M`, so the file reads as a polar
grid. A wheel of `N` blades at `k` clockings holds `N k` azimuths and one row
per station at each; a value the export does not state is `NA`.

**What is not mapped.** A rotor with no block that is one of its blades at a
stated azimuth has no file, and is named under
`sections/<point>_disc_#rotor=<ALIAS>` in the post's skips and warned in
`post.log`; so is a rotor of an unsteady point with no complete revolution,
and a point with no readable table, sections series or export window (named
under `sections/<point>_disc_`). The other products are written.

**The manifest.** `products.json` registers each file with `kind` `disc_map`,
`source` `wheel clockings` or `unsteady last revolution`, `samples` (the blade
samples of that rotor), `rotor` and `quantity`; a wheel's entry adds
`clockings`, an unsteady point's `revolution` and `steps_per_revolution`.

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

**A continued point is averaged over the last steps of its WHOLE march**
(since 0.33.0, FR-96). A continuation (`RESTART`) records the row's clock, so
its window as recorded ends at the last step of the run it continues; the post
moves every window of the point, keeping its length, to end at the last step
of the march, so `LAST_REVS_AVG: 1` averages the last revolution the solver
turned, in the continuation. The plots table of such a point is the history of
the whole march: the post reads the plots export of each run of the chain from
the archive the next run moved it into (`datapoints/DP-<point>/archive/<stamp>/`)
and joins them by step number. An export whose first step follows the
history's last is appended; one that starts inside the history and repeats its
rows there restates the march and is taken from where it starts; one that
starts again at step 1 with rows of its own is numbered on from the history's
last step, its time with it. No step is repeated or missing at a seam, and
`post.log` says how the history was joined and the step the window ends at. A
history that cannot be found or joined is said there, naming the file, and the
table then holds the continuation's own export, as it states its steps. Which
of these the solver writes is not yet read on a licensed run, so each is read.
A point that continues nothing is averaged exactly as before.

---

## Native surface flow exports

VTK (`.vtk`) and FEM CSV (`.csv`) are native solver surface exports; the
Tecplot (`.dat`) is written by the package from the VTK since 0.28.0
([below](#the-tecplot-surface-is-written-from-the-vtk-since-0280)). Since 0.29.0,
new Tecplot requests also retain the native nodal-strength source described in
[the 0.29 amendment](#native-nodal-strength-in-0290). VTK and CSV
are **off by default**. The pproc can request them and select VTK variables by
their command-database names:

```toml
vtk_variables = ["X", "Y", "Z", "CP_FREESTREAM"] # top-level; optional

[exports]
vtk = true
csv = true

[time_averaging]
last_revs = 1.5 # OR last_iters = 54; exactly one, positive
```

**The force distribution is off by default too** (since 0.27.0).
`force_distributions = true` under `[exports]` saves
`<point>_force_distributions.txt` on every run type: the pressure and viscous
force coefficients of every surface panel, by boundary, which
`pyflightstream.results.parse_force_distributions` reads. It is exported once,
at the end of the run, with every surface (`SURFACES -1`): an unsteady row does
not add it to its per-step exports, and its wall-clock rescue does write it.
The file grows with the mesh, which is why it is asked for rather than given.
An export taken before the solver has iterated can hold no panel.

Without `vtk_variables`, VTK uses the command's all-variables form. Both forms
exclude the wake. CSV exports `CP-FREESTREAM`, `PASCALS`, all surfaces, in the
solver reference frame (frame 1 on builds whose grammar includes it). Unknown
VTK variables and commands unavailable on the selected build are refused at
plan. Both formats also join the per-step `EXPORT_UNSTEADY_AFTER_REV` or
`EXPORT_UNSTEADY_AFTER_ITER` exports.

### The Tecplot surface is written from the VTK (since 0.28.0)

**Historical 0.28.x contract.** The following description applies to records
without the native-source declaration. New 0.29.0 records follow
[the amendment below](#native-nodal-strength-in-0290); historical outputs keep
the meaning their recorded release gave them.

**A 0.28.x campaign point does not request native Tecplot.** Where `[exports]`
keeps `tecplot` (the default), the script exports the surface as VTK
(`EXPORT_SOLVER_ANALYSIS_VTK`, every surface) and the package writes the `.dat`
from it, at the name the solver's own Tecplot had, in the point's
`datapoints/DP-<point>/`, before the point's outputs are collected. The run
hashes it with them, so every reader downstream finds it where it was. **One VTK
export per point feeds both**: where the pproc also asks `[exports] vtk`, the
user's VTK is that very file. Where it does not, the VTK is exported under the
Tecplot's own name with `.vtk`, kept beside it and listed among the point's
outputs, because the `.dat` names it. Without `vtk_variables` it is the
all-variables form, `SET_VTK_EXPORT_VARIABLES -1 DISABLE`, which writes no
`<name>_wakes.vtk` (RPT-074).

| | the solver's own Tecplot, to 0.27.x | the package's 0.28.x contract |
|---|---|---|
| zone | one FEPolygon zone, BLOCK packing | the same |
| nodes | `X`, `Y`, `Z`, in the reference frame | the same nodes, in the reference frame; under mirror or periodic symmetry, followed by the images of the surface (below) |
| values | per NODE, by a cell-to-node rule of the solver's | per CELL, `VARLOCATION` cell-centred: exactly the value the solver computed on each panel, nothing interpolated |
| variables | sixteen, `Singularity_strength` among them | every variable the VTK carries, under the VTK's names: nineteen in the all-variables form |
| faces | each polygon's edges, the polygon on the left, none on the right | the same |

- **The frame.** The solver writes the VTK in the ANALYSIS LOADS FRAME, the frame
  `SET_SOLVER_ANALYSIS_LOADS_FRAME` names: a point `p` is written
  `p' = R (p - o)`, `R`'s rows the frame's axes in the reference frame and `o`
  its origin (RPT-074). The package undoes it with the loads frame the script
  itself set, as the script placed it: it emitted the frames and the
  loads-frame command, so it knows `R` and `o`. A loads frame the script did not
  place (one an opened project carries, or one a command moved in a way the
  package does not follow) is refused at plan, naming the frame.
- **The velocity components are written back the way the solver wrote them, as
  a point is, origin included.** On RPT-074's recorded files the norm of `Vx`,
  `Vy`, `Vz` equals the panel's own `Velocity` to 7e-15 at the median only once
  the frame's origin is put back, `v = R^T v' + o`, on 6867 of 7167 panels of
  both the plain and the turned frame; turned back as a vector alone it misses
  by 9.0 m/s at the median, the origin's 9.152 m read as a speed. So the
  components are undone exactly as the nodes are. Every other value is a scalar
  and is written as the VTK holds it. A `vtk_variables` naming some of `VX`,
  `VY`, `VZ` and not all three is refused at plan where the loads frame is not
  the reference frame, since each component was written from all three.
- **A row under symmetry carries its images.** Under mirror symmetry the VTK,
  and so the `.dat`, holds the modelled surface followed by its mirror image in
  `y`; under periodic symmetry, the modelled blade followed by its copies turned
  about the rotor's axis, one per other blade. The solver's own Tecplot held the
  modelled surface alone. The first block of nodes and polygons is that surface,
  node for node: the 99 Tecplot files of the tier-3 points on 26.124 against the
  solver's own of the same solves are equal on 86, and on the 13 mirrored or
  periodic ones the first block is equal to 3e-17 m and the rest are the images
  (RPT-080). A reader that sums over every panel of such a `.dat` sums the whole
  body, not the half or the one blade the solver's file held.
- **`Singularity_strength` is not carried.** It is the panel strength the
  solver's Tecplot prints, and the VTK does not hold it. The VTK adds seven the
  solver's Tecplot did not carry: `Normalized_Vorticity`, `Cp_freestream`, the
  momentum and displacement thicknesses and the shape factor of the boundary
  layer, `Static_pressure_ratio` and `Boundary_Index`.
- **The names are the VTK's.** Where the solver's Tecplot printed `CF`, `Cp`,
  `Mach Number`, `BL Thickness`, the `.dat` carries `skin_friction_coeff.`,
  `Cp_reference` (and `Cp_freestream` beside it), `Mach_Number`, `BL_Thickness`,
  and so on; nothing is renamed, because which of the two pressure coefficients
  the solver's `Cp` was is not identified (RPT-074). With `vtk_variables` a
  subset, the `.dat` carries that subset.
- **Cell values against nodal ones.** A translated file is not the solver's
  Tecplot to the digit: that one holds nodal values, this one the cell values
  they were averaged from. On RPT-074's solve, each cell value against the mean
  of the solver's nodal values at that polygon's nodes differs by a median of
  0.0025 in `Cp` (1.66 at most) and 3.3e-6 in `CF`.
- **What the file states about itself.** Its `DATASETAUXDATA` records name its
  VTK (`SOURCE_VTK`) and that file's sha256 (`SOURCE_VTK_SHA256`), say it is a
  translation, cell-centred, in the reference frame (`TRANSLATION`), name the
  frame undone (`SOURCE_FRAME`) and say `Singularity_strength` is not carried
  (`NOT_CARRIED`). Its `products.json` entry states the same as
  `translated_from`, `source_sha256`, `location` (`cell-centred`), `frame`
  (`reference`) and `not_carried`; the PROV document attributes it to the
  package and derives it from the VTK. The run record's `surface_translations`
  states each translation, its frame and the files written, and why one could
  not be; a Tecplot the run could not write is a named skip,
  `tecplot/<run id>`.
- **Per step, the same route.** `EXPORT_UNSTEADY_AFTER_ITER` and
  `EXPORT_UNSTEADY_AFTER_REV` export the step's VTK, and the run writes each
  `<name>_iteration=<step>.dat` from the `<name>_iteration=<step>.vtk` beside it.
  The wall clock's rescue exports the VTK too, and its `.dat` is written the same
  way.
- **The additional post** writes its Tecplot the same way, in the run's loads
  frame as the run's own script placed it. **A continuation's** loads frame is
  the saved simulation's, and the run takes its placement from the run it
  continues; one recorded before 0.28.0 states none, and such a continuation is
  refused at plan, before anything is archived, unless its pproc sets
  `tecplot = false`.
- **What keeps its own route.** The volume section's Tecplot
  (`[volume_section] format = "tecplot"`, `EXPORT_VOLUME_SECTION_TECPLOT`), the
  probe files of `pyflightstream.post.writers` and a hand-written script's
  `helpers.export_results(tecplot=...)` are what they were. Only the campaign's
  surface export, `[exports] tecplot`, is written from the VTK.
- **A record written before 0.28.0** keeps the solver's Tecplot and the meaning
  its release gave it: nothing reads it again.

### Native nodal strength in 0.29.0

A new workspace Tecplot surface request retains both its VTK source and a
native auxiliary `*_native_tecplot.dat`, including each requested STEP. The
package-written product keeps the VTK's physical cell fields and adds the
native source's actual nodal `Singularity_strength` after a unique coordinate
bijection and complete polygon-topology match. It does not derive strength
from Cp, interpolate cell Cp to nodes, or treat equal counts as equal geometry.

Both source hashes, the complete recorded loads frame, output hash and matching
evidence accompany the mixed nodal/cell association. Each STEP uses its own
source; missing or ambiguous evidence is named rather than filled from the
final export. Historical records without that declaration keep the 0.28.x
VTK-only contract and its explicit missing-strength statement. See
[surface translation](surface-translation.md) for the exact source/association
and recovery contract.

### The strength is asked for (since 0.30.0)

**The native export is made only where the row's pproc sets
`singularity_strength = true`.** The key is off by default. Off, the point
exports no `*_native_tecplot.dat`, at the end of the run or at any step; its
translation record names no native source; the `.dat` follows the 0.28.x
contract above, every VTK variable cell-centred with `Singularity_strength` in
`NOT_CARRIED` and `not_carried`; and the point is not
`FAILED_INCOMPLETE_OUTPUT` for a native file it was never asked to write. The
time-averaged surface below averages the VTK variables and states the strength
not carried. On, every point and step is exported, matched and recorded exactly
as in 0.29.0. `pyfs-matrix plan` states per row declaring a Tecplot surface
whether the strength is carried.

### The time-averaged surface is the package's (since 0.28.0)

**`[time_averaging]` makes the run export the surface at every step of its
window, and the post averages those exports.** `SOLVER_TIME_AVERAGING` is never
emitted: on 2026-09-19 licensed C01 measured it hanging FlightStream 26.124 in
the position the package emitted it (no output was written before the
termination at 240.5 seconds; receipts under `reports/pfs0250/`), and 26.123
stops at it (RPT-079). The table is `last_iters` or `last_revs`, exactly one,
positive, as before.

- **The window.** Inclusive, 1-based time steps ending at the run's last time
  step: `last_iters` is a count of steps; `last_revs` uses the rotor clock and
  the rounding of `LAST_REVS_AVG` (with `DELTA_THETA`, steps per revolution is
  `360 / DELTA_THETA`). A window longer than the run is clipped at step 1. The
  steps are the time steps the per-step counter counts and the solver stamps on
  each export as `_iteration=<step>` (RPT-041); the export header's
  inner-iteration counter is never read for them.
- **How the steps are exported.** Through the per-step export machinery of
  [the sections](#per-distribution-sectional-loads-and-cp-0250): a row stating no
  `EXPORT_UNSTEADY_AFTER_ITER` or `EXPORT_UNSTEADY_AFTER_REV` exports as one
  stating `EXPORT_UNSTEADY_AFTER_ITER: <the window's first step>` would, every
  per-step kind of its outputs from that step to the end, the surface's VTK among
  them. A row stating a threshold at or before the window's first step keeps it;
  one after it is refused at plan, naming both steps, since the steps before it
  would never be exported. The build must carry the unsteady solver action
  (`SET_NEW_UNSTEADY_SOLVER_ACTION`, 26.122 on); the point must export its
  Tecplot, which the average is written as. A steady row, and an additional
  pproc, refuse the table.
- **What is averaged.** The same PANEL, the VTK's cell index, across the steps of
  the window, each step's values first written back in the reference frame as
  its Tecplot is (the velocity components undone as a point is, above). Every
  step weighs the same, and nothing is interpolated. The average is
  `blade_passage_average`, the package's one averaging routine, with the panels
  as its samples and the steps as its frames. Every physical cell field the VTK
  carries is averaged, `skin_friction_coeff.` (CF) included. In 0.29.0, available native
  nodal strength is averaged separately from the cell fields using every
  selected STEP's matched source. Coordinate fields retain the last selected
  STEP; they are never averaged into a different geometry.
- **What the solver's own average says about it.** On 26.122, where the solver
  runs `SOLVER_TIME_AVERAGING`, its final surface equals, to 1e-13, the uniform
  mean of the same run's per-step instants over the same inclusive time steps,
  for `Cp`, `Vx` and `Velocity`: the package's average matches the solver's to
  machine precision for the flow variables (RPT-079). The solver keeps CF at its
  last instant; the package averages CF as it averages every other variable.
- **Refused, or skipped, by name; never partial.** Steps that do not share one
  topology (the node count, the polygon count and the nodes around every
  polygon) refuse the average, naming the step: a panel cannot be followed
  across them. A step of the window that was not exported (a run stopped by its
  wall clock before the window ended, a continuation, whose step counter starts
  again) skips the average, naming the missing steps: an average of the steps
  that were would not be the window's. Both are named skips in `products.json`
  and `post.log`. A window that reaches a frozen part of the solve is warned
  about, as every other average is, and under `--check-frozen` it is refused
  before anything is written: no file, no entry, the reason under its name.
- **Where its nodes are.** The averaged file's nodes are those of the window's
  LAST step: on a turning rotor the nodes move from step to step, and their mean
  would be a surface nobody flew.
- **The product.** `surfaces/<point>_time_average.dat` under the matrix's
  products, written by the writer of every Tecplot (one FEPolygon zone, every
  VTK value per panel, cell-centred, in the reference frame, plus real nodal
  strength for 0.29.0 records declaring that source), and
  `surfaces/<point>_time_average.vtk` beside it where the pproc asks
  `[exports] vtk`. Its `DATASETAUXDATA` records say what it is an average of
  (`AVERAGE_OF`, `WINDOW`, `COORDINATES`, `TRANSLATION`, `SOURCE_FRAME` and
  either the actual native-source evidence or the historical `NOT_CARRIED`). Its `products.json` entry carries `kind: average`, the
  recorded `window`, the `steps` averaged, `inputs` (each per-step VTK read and
  its sha256), `averaged_by: pyflightstream`, `weighting: uniform`,
  `coordinates_step`, and `location`, `frame` and `not_carried` as every
  translated Tecplot does. The frozen-solve rule of every average applies: a
  freeze inside the window warns, and `check_frozen` refuses.
- **Native comparison limits in 0.29.0.** Native fields can retain a final
  instant even where the package computes their temporal mean. Those statistics
  are not equivalent. The measured WALLTIME discrepancy retains a named
  surface-average refusal; see [unsteady products](unsteady-postprocessing.md)
  for the observed build, STEP coverage and accepted limits.
- **The instants stay.** Every per-step VTK and the Tecplot written from it stay
  on disk and in `products.json` as `kind: instant`, and so do the end of the
  run's surface exports.
- **The run records the window**, as `surface_average_window`, and the post reads
  that record, never a pproc edited since; a continuation keeps the window of
  the run it continues. Changing the window of a recorded run needs a new run,
  since the steps before the window's first were not exported.
- **A record written before 0.28.0** that carries the solver's window
  (`surface_time_averaging`, `verification: UNVERIFIED`) keeps the meaning its
  release gave it: its native surface exports are `kind: average` over that
  window, per-step entries end their window at the export's step, and exports
  before the window's start are named skips.

---

## The solver's own plots

Since 0.27.0 a steady point, and since 0.28.0 an unsteady one (the first two),
saves the plots the solver draws of its own solve, next to its exports, one
text file each:

| `[exports]` key | The plot | File | Default |
|---|---|---|---|
| `plot_residuals` | the residual history | `<point>_plot_residuals.txt` | on |
| `plot_loads` | the load history | `<point>_plot_loads.txt` | on |
| `plot_sections_cp` | the Cp of every surface section | `<point>_plot_cp_sections.txt` | on where `[[sections.distributions]]` declares sections |

Each is switched off with `false` under `[exports]`. `plot_sections_cp = true`
in an artifact that declares no sections is refused, because the plot would
show no section.

The script chooses each plot with `SET_PLOT_TYPE` (`RESIDUALS`, `LOADS`,
`SECTIONS_CP`) and saves it with `SAVE_PLOT_TO_FILE`, the file on the line
after the command, after every other export of the point and before its log.
Both commands are `verified` on 26.124 (RPT-067) and documented, never run,
on every other build.

**What a file holds.** The plotted SERIES as text, not an image: the run header
the loads export prints, the column names, one row per point of the plot and
the units footer. The residual and the load histories have one row per solver
iteration (residuals of velocity and pressure; lift, induced drag from
vorticity and pitching moment). The section Cp has one x/Cp column pair per
section.

**A plot is a display of the solve, never a source of a coefficient.** The
files are collected into `datapoints/DP-<point>/` and hashed in the run record
like every export of the point, and nothing in this package reads a number
from them. On 26.124 the last plotted lift equals the exported CL, the plotted
induced drag is close to the exported CDi without equalling it, and the
plotted pitching moment is not the exported CMy at all (-0.897 against
-0.0247). Every coefficient on this page comes from the loads export.

**An unsteady point saves the residual and the load plots too** (since 0.28.0,
G26), on by default as on a steady point, ONCE, after the march and before its
log, and again in the wall clock's rescue, which is the end of the run; never
inside the per-step exports, which would save the same growing file at every
step. After an unsteady solve on 26.124 each file holds the series of the
whole march, one row per INNER iteration (857 rows over 12 time steps), and the
last plotted lift is the exported CL (RPT-076). A history per time step is the
unsteady force plot, `<point>_plots.txt` through `[plots]`, as before. **The
section Cp plot joins supported unsteady rows in 0.29.0**: it is saved once
after the march when the pproc declares section distributions, never by each
per-STEP action. The earlier steady-only refusal applies to prior releases.
A plot is not a sectional-load table; see [unsteady plots and averages](unsteady-postprocessing.md)
for the measured final-export control and history-coverage limits.

## The boundary-layer profile is not produced

The solver can export the boundary-layer velocity profile through the wall at
one surface point (`EXPORT_BL_VELOCITY_PROFILE`). It holds an unattended script:
on 26.122 it opens a modal window that waits for a person (RPT-027), and on
26.124 the script stopped at it and the run was lost at its timeout (RPT-075).
The command remains `broken` on 26.124: a row writing it raw is refused at
plan, naming the report. Since 0.29.0, the separate typed request
`products.boundary_layer_velocity_profile = true` is also refused before
execution while positive unattended-profile evidence is absent.
The boundary-layer quantities of the surface come from the VTK export instead
(thickness, momentum and displacement thickness, shape factor; RPT-074).
The independent `products.boundary_layer_integrals` request writes these actual
cell quantities at configured section cuts; it never substitutes them for a
velocity profile. See [boundary-layer products](boundary-layer-products.md).

**Run as a campaign writes it.** A point saves each plot to its own name,
relative to its working directory, as every export of the point does; a run
of that exact block on 26.124, two saves in a row, left both files in the
working directory (RPT-067, its addendum).

## A volume section

Since 0.29.0, `[volume_section]` declares one sampled flow plane through
probes on steady rows and fluid-plot histories on unsteady/rotor rows. The
package writes a velocity **vertex cloud**, without interpolated surface
panels or invented volume cells. This is the approved workspace route; it
uses no native volume-section index.

| Field | Definition |
|---|---|
| Files | `post/<matrix>/fields/<point>_vsec.vtk` or `.dat`; unsteady products add `_step_<STEP>` before the extension. Each has a provenance JSON companion. |
| Plane | Rectangle `corners_m` or annular `radii_m`, in the declared `frame` and `plane`, with `offset_m` on the remaining positive axis. Authored lengths are meters. |
| Samples | Rectangle `points` gives the two axis counts (25 by 25 when omitted); each extra `refinement_layers` bisects intervals. A circle states radial/azimuthal counts and samples its zero-radius center once. |
| Source | The written probe CSV, derived from the native steady probe export or the actual unsteady fluid-plot STEPs. No missing STEP is synthesized. |
| Physical meaning | Positions in REFERENCE coordinates and meters; absolute REFERENCE velocity components in m/s. Export-kind, unit, executable and motion evidence must support the conversion. |
| Time | One instantaneous steady sample set, or a separate field for each actual unsteady STEP; never an implied time average. |
| Provenance | Source hash, recorded sample identities/positions, declared and resolved frames, units, actual STEP where present, native convention evidence and recorded solver setup. Unknown setup values remain unknown. |

A saved FSM may already contain native sections: the new sampling grid does
not use those sections as its addressing basis. The direct native/custom API
still does not discover their indices. Its caller must establish the actual
native section inventory, as explained in [sampled fields](sampled-fields.md).
A new grid or a missing history cannot be reconstructed merely by posting old
results. See [the workspace example](pproc-artifact.md#a-volume-section)
for input syntax and the measured-domain restrictions.

### Historical native volume exports, 0.27.x and 0.28.x

The following contract is retained for old run records only. It is not the
implementation of a new 0.29.0 workspace `[volume_section]` request.

A volume section is ONE flow-field plane through the solution, declared by the
pproc's `[volume_section]` table (since 0.27.0) and cut by every point of a
**steady** row after its solve. It is a native solver export, like the surface
files above, and the package writes no product from it:

| field | definition |
|---|---|
| file | `{name}_vsec.vtk` (`format = "vtk"`, `EXPORT_VOLUME_SECTION_VTK`) or `{name}_vsec.dat` (`format = "tecplot"`, `EXPORT_VOLUME_SECTION_TECPLOT`), in the point's `datapoints/DP-<point>/`, hashed in its record |
| plane | a rectangle between two diagonal corners (`corners_m`), or an annulus between two radii (`radii_m`), in the `plane` of the named `frame`, `offset_m` along its normal; every length in metres, written in the simulation's length unit, and a saved simulation whose unit the package cannot read is refused at plan ([the workflows page](workflow-row-flow-inputs.md#one-row-one-actuator-disc)) |
| instant | the converged state of THAT point: the section is created after the point's `START_SOLVER`, its flow computed by `UPDATE_ALL_VOLUME_SECTIONS` before the export, and a later point of a sweep deletes the previous section before creating its own, so each file is its own point's plane; a section exported with no update held every cell at 0.0 in the licensed run of 2026-09-24 (RPT-070), and with the update the rerun's 96 cell values of each point are all non-zero and differ between its two points (RPT-070) |
| which section | the pproc's own: the export and the delete cite the index the pproc's section takes in the solver's list, counting every section the script cuts, a raw line's included, so a section a raw line cut before it never fills the pproc's file; a raw line deleting the pproc's section leaves the file nothing to export, and the row is refused when its script is built |

The `_vsec` infix is what tells the file from a surface export of the same
extension, in a run recorded by 0.27.0 or later. **A run recorded before 0.27.0
keeps the meaning its release gave the name**: its `P_vsec.vtk` or
`P_vsec.dat` was a surface VTK or Tecplot export, and the post keeps it one, a
native-surface entry of `products.json` with its instant or average metadata in
PROV-JSON, because upgrading the reader does not rewrite what a record says.
The post reads every recorded output by the kinds the record's
`package_version` knew. There is one section per pproc; an unsteady row naming a pproc that
declares one is refused, because its step exports run before a section cut
after the march exists. The commands are verified on 26.120 to 26.124 one at a
time; the delete-then-create sequence of a sweep is not measured.

## Durable execution activity

Run, solver/submission, translation, post, collection and continuation stages append
timestamped records to logs/activity.log and logs/activity.log.jsonl beside the
workspace. The text log retains progress; JSONL records include final outcome
counts and exception details. Native scheduler stdout remains native when
EXPORT_LOG is disabled. Recorded diagnostics do not enter these stages or mutate
the logs. A standalone local executor keeps its activity log under its working
directory. Progress goes to stderr; JSON and CSV stdout remain data only.

On the console of a command, a warning of the package's own categories prints
as `[warning] <message>`, without the path of the installed file, its line
number or the echoed source line. Since 0.31.0 a warning longer than 90
columns is wrapped, its continuation lines indented under its text, and every
warning is followed by a blank line; the words are unchanged. The first
`[<stage>] started:` line prints the
workspace root absolute and later lines print paths under it relative to it.
The `[continuation] started` and `finished` lines, said for every point whether
or not it continues a run, print only with `--verbose` since 0.31.0.
A forced re-run says one line per simulation, for example
`[warning] force_rerun: the collected outputs of 10 point(s) of sim_4016 were archived (sims/sim_4016/datapoints/DP-*/archive/<stamp>)`,
and writes each point's move, with its absolute path, to `logs/activity.log`.
Pass `--verbose` to `pyfs-matrix plan`, `run`, `post` or `collect` to print
Python's full warning format and one line per point again. A Python caller keeps
Python's standard warnings and absolute paths. Every command ends with the
signature box on stderr; `--help` and `--version` end with one short line.

## The additional post

A scheduler submission is recorded as SUBMITTED, with no completed outputs.
Collection requires stable exports and unchanged source/script hashes before
recording EXTRACTED. Native scheduler logs remain native when EXPORT_LOG is
disabled; scheduler acceptance text is never presented as a solver log.

A row that names a second pproc, `ADDITIONAL_PPROC: p<id>`, has that pproc
extracted from each recorded point's final saved simulation by
`pyfs-matrix post <matrix> --additional-pproc`, with no solve (since 0.27.0,
`test_g12_the_extraction_lands_in_additional_and_is_hashed`,
`test_g12_the_additional_script_never_solves_and_never_saves`). This section
defines what comes back and what the products of it are.

**What a reopened saved simulation gives back.** Measured by the licensed probe
T09 on 26.124, on two saved points (a steady half wing-body and an unsteady
pusher rotor) reopened from a copy with no solve, against the run's own exports
([RPT-062](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-062_what-a-reopened-simulation-gives-back_2026-09-23.md)):

| export | reopened, with no solve |
|---|---|
| total loads | identical |
| surface solution | identical bytes |
| surface sections, a distribution created after reopening included | identical |
| sectional loads | identical once computed after reopening, and zero until then: the file stores the sections and not their loads, so the extraction computes them every time |
| plots history of an unsteady point | identical |
| probe points, off the body | NOT identical: updated or created after reopening, they differ from the run's, by up to 4 percent in speed and 0.094 in Cp |

The saved file of the unsteady point is its last instant. Only 26.124 was
measured, so a row on another build stating the key is refused at plan
(`test_g12_a_row_on_another_build_is_refused_naming_rpt062`). The field off the
body (probe points and a volume section), the plots of a march and a surface
averaged in time are refused in an additional pproc for the same reason:
nothing measured says a reopened file gives them back
(`test_g12_an_additional_pproc_with_probes_is_refused_naming_rpt062`,
`test_g12_an_additional_pproc_that_asks_what_a_reopened_file_cannot_give_is_refused`).

**One instant on an unsteady point.** The saved simulation of an unsteady run
is its LAST instant, so every table of an unsteady extraction is one instant
and not the run's history: the sections table's `STEP` is the run's last time
step and its entry says `"kind": "instant"`
(`test_g12_an_unsteady_extractions_sections_table_is_the_last_instant`), and
the post log says it once per extraction
(`test_g12_an_unsteady_extraction_is_one_instant_in_the_post_log`). The plots
history the extraction exports is the run's own, so the plots tables and the
reductions over it are the run's history read under the additional pproc.

**The products.** Written by the post under `post/<matrix>/additional/<pid>/`,
beside the run's own and never over them, by the builders the run's products
use: the additional pproc's group polars on a steady point, one sections table
per point, and on an unsteady point the plots tables and their reductions.
Each table opens with `POL`, the polar of the point the extraction was taken
from, like every table of the run's own.
Every entry of `products.json` for them carries
(`test_g12_additional_products_are_marked_with_the_pproc`):

| key | meaning |
|---|---|
| `pproc` | the ADDITIONAL pproc id, not the one the row ran with |
| `additional` | always `true`, written `"additional": true`; a reader that takes every entry as a product of a run filters on it |
| `extraction` | the extractions the file holds, each `<point run id>/additional/<pid>` |
| `derives_from` | the points those extractions were taken from |

and no `runs`, which names run ids everywhere else in the index. The surface
exports and the plots history of an extraction are indexed as the solver wrote
them, in the point's `datapoints/DP-<point>/additional/<pid>/`, with the same
marks.

**Which rows the sections table holds.** A reopened sections export carries the
distributions the run created FIRST and the additional pproc's after them
(RPT-062). The table keeps every row: the layout the extraction records is the
run's own blocks followed by the new ones, numbered on after the run's and
marked with the pproc, so `FAMILY` and `PLANE` say which row is which, and the
extraction's `leading_sections` counts the run's rows at the head
(`test_g12_the_additional_sections_table_holds_the_run_rows_then_the_additional_ones`).
A layout whose counts do not add up to the export states `NA`, as on the run's
own table.

**Which frames and boundaries it cites.** The extraction cites the frames and
the boundaries the saved simulation holds, which are the run's. A frame is the
run's only while the row creates it today exactly as the run's recorded script
did, in every line a script defines or moves a frame with: its index and name,
its origin and three axes, and every later turn, move, copy or deletion. A
point whose row creates a frame differing in any of them, a frame turned under
its old name and place included, is skipped `SCRIPT_DRIFT` naming the line
(`test_g12_a_frame_turned_since_the_run_under_the_same_name_is_skipped`,
`test_g12_a_frame_moved_after_it_was_placed_differs_by_the_move`), since a
distribution cited in it would be cut in the frame the file holds and not the
one the pproc means. The boundaries are the run's and never today's file's:
the names the run's record states or, on a record written before 0.27.0, the
names read by the geometry's hash as the post's own tables read them (*The
geometry's names*, above). A point whose row declares the boundaries in another order today is
skipped `SCRIPT_DRIFT` naming both orders
(`test_g12_an_older_record_is_held_to_the_boundaries_its_geometry_hash_recovers`),
and so is one whose names nothing on disk recovers while the geometry declares
names today
(`test_g12_an_older_record_whose_boundaries_no_hash_recovers_is_skipped_naming_why`):
an index read off today's file would cut whichever surface holds that index in
the saved one, under the name the pproc asked for.

**When an extraction stops counting.** Only a CURRENT extraction has products:
its point is a record the post admits, the point's saved simulation still
hashes as the one the extraction opened, in the point's record and as the file
on disk, and every file the extraction wrote is on disk and hashes as recorded
(`test_g12_an_extraction_of_another_state_of_the_point_is_stale`). A saved
simulation deleted or replaced under a record nobody rewrote leaves every
extraction of it stale, named by the path
(`test_g12_an_extraction_whose_saved_simulation_left_the_disk_is_stale`). A
point that ran again, by a forced rerun or a continuation, archives its folder
with the extraction in it; the old extraction is then stale, the post skips it under
`additional/<pid>/runs/<extraction id>` and never under the run's own key, so
no product of the run is retired for it, and a previous additional product
nothing current supplies is archived like a refused table. The next
`--additional-pproc` extracts the point again
(`test_g12_a_stale_extraction_is_skipped_and_retires_no_main_product`). The
extraction pass reuses an extraction by the same test of its files, so one
whose file was changed or truncated since is extracted again by the next
`--additional-pproc` rather than called already extracted, and its products
come back
(`test_g12_an_extraction_whose_file_changed_is_extracted_again`).

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
- **Each row opens with `POL`, then `FIRST_STEP`, `LAST_STEP`, `STEPS`**, the
  window THAT point was averaged over, so the file says on its own that it is an
  average and over what. The condition block follows, then `XMOM`, `YMOM`, `ZMOM`,
  because the plots carry moments and a moment states nothing without its point.
- **The super file's content is ADDED to this table**, after the plot columns:
  the matrix row's cells, the record's scalars, each rotor's speed, the solver
  flags. The super file is what the polar does not have; for an unsteady point it
  is not a second file. Its `POL` cell is the row's first column and is not
  written a second time.
- **The last column is `MESH_FACES`** (since 0.34.0), after the super file's
  content: the face count of the point's geometry as its inventory states it,
  or `NA` ([the mesh face count](#the-mesh-face-count-since-0340)).
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

## The mesh face count (since 0.34.0)

- **`MESH_FACES` is the last column of every super file and of every unsteady
  polar** (`polars/P<sim>_<name>_uns_avg.csv`), after every column 0.33 wrote,
  so a reader that takes those columns by position keeps each of them. It holds
  the face count of the geometry the row's run opened.
- **It comes from the boundary inventory, and the post never counts a face.**
  `pyfs-matrix inventory <geometry>`, and the plan for an OBJ that has no
  inventory, write into `<stem>.boundaries.toml`, when they take the inventory,
  `mesh_faces`, the face count of a saved simulation's mesh block or of an OBJ;
  `boundary_faces`, the count of each boundary in the order of `boundaries`,
  where the reader gives it (a saved simulation whose faces are all triangles
  and whose block names each face's boundary, and an OBJ, one count per group
  that holds a face); and `mesh_sha256`, the sha256 of the file counted.
- **A row carries the count whenever the inventory states it for that row's
  geometry**, the library's inventory read first and then the simulation's
  staged copy. Otherwise the cell is `NA`: a row whose point has no run record,
  and an inventory without `mesh_faces` (every inventory taken before 0.34.0).
- **Where the inventory's `mesh_sha256` is not the sha256 the run recorded** for
  the file, because the geometry was replaced, edited or cleaned (`--clean`)
  between the inventory and the run, the count is still carried and `post.log`
  warns, naming the inventory, both sha256 and the run. The warning never
  blocks the post; take the inventory again if the geometry changed.
- **Taking the count again.** For a saved simulation, `pyfs-matrix inventory
  <geometry> --overwrite` rewrites its inventory with the count. The package
  never rewrites an OBJ's inventory, because it may carry tables written by
  hand: move it aside, take the inventory again, and copy those tables beneath
  the new list.

---

## Rotor coefficients

`J`, `CT`, `CQ`, `CP`, `ETA`, `ETAW`, and since 0.31.0 the in-plane `CN`, `CS`,
`CMN`, `CMS`, one table per rotor, every column suffixed with the rotor's alias. They make physical sense for **one** rotor and not for
several summed: the diameters and speeds that normalise them are different
numbers.

The table is `polars/P<sim>-<alias>_rotor.csv`. It opens with `POL` and
`ROTOR`, the rotor's alias, on every row, then the condition block,
`RPM_<alias>`, `DIAMETER_<alias>` and the six, `J_<alias>` to `ETAW_<alias>`,
then, since 0.30.0, `MTIP_<alias>` and `MHEL_<alias>`
([Tip and helical Mach numbers](#tip-and-helical-mach-numbers)), and then, last
since 0.31.0, `CN_<alias>`, `CS_<alias>`, `CMN_<alias>` and `CMS_<alias>`
([The in-plane coefficients](#the-in-plane-coefficients)). The column contract
grows at its end only, so every earlier column keeps its position.
Its first line is its header: from 0.23.0 to 0.26.x the alias stood alone on
the first line, before the header, so a loaded table knew its rotor, and no CSV
reader took the file as written. The column keeps that promise.

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

### The in-plane coefficients

Since 0.31.0 the table states the rotor's force and moment square to its
axis, in the rotor's own axes `(T, S, N)`:

- `T` is the rotor's axis as the reference declares it, the direction in
  which its thrust is counted positive (the same axis `CT` projects on).
- `N`, the normal, is the part of the reference frame's up direction (`+z`
  of the loads frame: x aft, y right, z up) square to `T`, normalised.
- `S`, the side axis, completes the right-handed set: `S = N x T`, so
  `T x S = N`.

For a level rotor whose axis points forward (`-x`), `N` is `+z` and `S` is
`-y`, the right of a viewer upstream of the rotor looking downstream at it;
the force components are then `N = +FZ` and `S = -FY`, and the moments
`MN = +MZ` and `MS = -MY`. `N`, `S`, `MN` and `MS` are taken from the same
rotor force and the same moment about the HUB that `CT` and `CQ` are taken
from (`M_hub = M_mrp + (r_mrp - r_hub) x F`), and normalised as they are,
with that row's density, the magnitude of its rotor speed and the rotor's
diameter:

```text
CN  = N  / (rho n^2 D^4)
CS  = S  / (rho n^2 D^4)
CMN = MN / (rho n^2 D^5)
CMS = MS / (rho n^2 D^5)
```

- The axes turn with the rotor: a tilted axis tilts `N` with it, and `N`
  stays in the vertical plane that holds the axis.
- The sense of rotation does not enter them: none is a power.
- **An axis along the up direction has no normal and no side axis.** The four
  read `NA` on every row, and the post says so once for the table, in its log.
  They also read `NA` wherever `CT` does (a static point, a loads frame that
  is not the geometry's), because they come from the same force.
- On an unsteady point they are the window's average, as every other column
  of the row is. On a quasi-steady wheel they are of the mean loads over its
  clockings, as every other column of the row is (since 0.31.0), and on a
  sector solved without symmetry loads they are the modelled sector's, not
  the whole rotor's.

### A static point

Every rotor coefficient reads `NA` on a static point except `J`, which is a real
`0.00000`. The export states coefficients normalised by the run's own dynamic
pressure; at `V = 0` that pressure is zero and the rotor's real thrust has been
divided away before the package sees it. **No rotor coefficient is recoverable
from a static point whatever the package does**, which is also why a hover figure
of merit cannot be offered: it needs a force the run does not state.

## Tip and helical Mach numbers

Since 0.30.0, every point of three row types states how fast the blade tip
moves against the speed of sound: an `unsteady_rotor` row, for each rotor it
turns; a `steady` row that states `RPM`, for its rotor; and a row of any run
type that names an actuator disc (`ACTUATOR`), for each disc:

```text
Omega = 2 pi RPM / 60                  rad/s
M_tip = Omega R / a
M_hel = sqrt(V^2 + (Omega R)^2) / a
```

- `RPM` is the speed the run turns, in rev/min, the unit of every rotor speed
  the package resolves: a rotor's `RPM` stated, or derived from
  `ADVANCE_RATIO`; a disc's `ACTUATOR_RPM`, or the speed its advance ratio
  works out to against the disc's own diameter, as its script emits it.
  Its sign is the rotor's hand and is not read: both numbers are of a speed.
  On a build whose rotor motion is written without a unit mark (26.100, report
  RPT-051) the package writes the rev/min it resolved, and the unit that build
  reads there is not measured; the numbers are of the speed the row states.
- `R` is a rotor's half diameter: the `diameter_m` of its rotor block in the
  reference, else the reference's `rotor_diameter_m`. A rotor with neither has
  no known radius, and its two numbers are not computed: the plan and the run
  record say so naming the row, and nothing is guessed. A disc's `R` is its
  block's `tip_radius_m`, which a disc block cannot omit; a row naming a disc
  its reference does not declare gets the same named note.
- `V` is the free-stream speed and `a` the speed of sound of the point's own
  resolved flight condition, the same resolution that sets the Mach number the
  run flies (a pinned `ASMPS` included). On a static rig, a row stating `RPM`
  and `ADVANCE_RATIO` and no velocity, `V` is the velocity the package derives,
  `J (RPM / 60) D` of the clock rotor. At `V = 0`, `M_hel = M_tip`.
- `M_tip` is the tangential speed of the tip alone; `M_hel` composes it with
  the free stream, the speed at which the tip meets the air in a helix. Both
  are dimensionless and geometric: `V` is the free-stream speed alone, not
  corrected for the rotor's own induced velocity, which near hover and at low
  advance ratio adds to the speed the tip actually sees.

Where they appear:

- `pyfs-matrix plan` prints both per rotor and per disc per point, and
  `plan.json` carries them per point under `rotor_mach`, keyed by the rotor's
  alias or the disc's name, with `kind` (`rotor` or `actuator`) and the speed,
  the diameter, `V` and `a` they were taken at. **The plan warns when
  `M_hel >= 1`** on any point, naming each point, its rotor or disc and its
  `M_hel`: at 1 or more the tip is sonic or supersonic. It is a warning and
  never a refusal.
- The run record (`runs.json`) carries the same block under `rotor_mach`;
  the key is absent on a record with no such point. A steady row runs its
  points as one job, so its job record keys the blocks one level up by the
  point's name, and each point read out of the job carries its own.
- The rotor table carries `MTIP_<alias>` and `MHEL_<alias>` after its six
  coefficients (and before the four in-plane ones of 0.31.0), taken at that
  row's speed and `DIAMETER_<alias>` and at the point's resolved condition. A
  point whose condition does not resolve reads `NA` in both and keeps its row.
  A disc has no rotor table, and a steady row's record states no rotor speed
  for the table to read, so for those two the numbers are in the plan,
  `plan.json` and the run record. A `qsteady_rotor` point is the exception
  among steady rows: its rotor table reads the row's speed from the point's
  quasi-steady record (below).

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
Each WARNING is one line, `WARNING point=<point> product=<product>: <message>`,
under the point and product the warning itself names (a point may hold
spaces, as a campaign's name may; a product never does); a warning that names
none is the stage's own and reads `point=campaign product=stage`. The message
names the step where one applies and what would settle the issue. A named skip
and an interrupted post state their remedy apart from the message, at the end
of the line after `Remedy:`. Every named manifest skip and every warning the
package emits during the post is recorded there. A rebuild
archives the previous log with the same timestamp as its products. An
interrupted post keeps its header and the warnings collected before it stopped.
Each post collects the package's warnings in its own campaign-local sink, held
per thread (a `ContextVar`), so two posts in two threads of one process each log
only their own, and one post's silenced sweep table silences no other post.
After the log is written, the post re-emits its warnings to its caller's warning
filters, outside every sink. A warning raised during a post by code outside the
package is not logged. A thread the post itself started would not inherit the
sink; the post starts none (`reports/RPT-058`, closed in 0.27.0).

`post.log.json` beside it (since 0.27.0) carries the same records for a
program. It holds the header, as `version`, `workspace`, `matrix`, `time` and
`check_frozen` with the values the text header prints (`matrix` is `null` where
the text says `None`), and `records`, one per WARNING line in the same order,
each with `point`, `product`, `message` and `remedy`. `remedy` is `null` when
the warning states what would settle it inside its message rather than apart
from it, which every warning the package raises does; a named skip and an
interrupted post carry theirs. Both files are written from one list of records,
on a clean, a failed and an interrupted post alike, so they cannot disagree.
The manifest names the file under `log_json`, and a rebuild archives it with
the log.

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

## Sampled velocity fields and reusable inflow

The public `post.write_probe_field` writes finite REFERENCE-frame samples in meters and m/s. VTK uses one vertex per sample; Tecplot uses one single-point ordered zone per sample, so neither format invents edges or surface cells. Each sidecar records the solver setup, source hash, coordinate and velocity units, sample count and variable meanings. The optional six-column `x y z vx vy vz` inflow file is an UNSTRUCTURED global YZ-plane profile; it must have distinct, non-collinear sample positions at one x. The writer refuses unsupported frames and incomplete or non-finite arrays before writing. It never interpolates samples or installs the profile automatically.

Example: `write_probe_field(stem, points_m, velocity_m_s, source=csv_path, provenance=record, formats=("vtk", "tecplot"), reusable_inflow=True)`. Tecplot zone dimensions and nodal POINT packing follow the [official data format guide](https://tecplot.azureedge.net/products/360/2024r1m1/360-data-format.html).

A workspace opts in per `[[probes]]` entry with `frame = "REFERENCE"`, `field_formats = ["vtk", "tecplot"]` and optionally `reusable_inflow = true`. These requests automatically sample VX, VY and VZ. The emitted sample IDs and native-to-meter factor are recorded with the run. Post writes `fields/<point>_field_<entry>[_step_<step>]` from complete probe tables; every actual transient step remains separate. Missing components or recorded sample IDs produce a named post warning and no interpolated replacement.

## The installed-frame copy of a product table

`pyflightstream.post.inflow_tools.to_installed_frame(table)` (since 0.32.0) writes `<table>_installed.csv` beside a product table stated in the ISOLATED frame, the same numbers in the INSTALLED frame, which is the isolated one mirrored through `y = 0`. It never overwrites; the isolated table is the record and this is a second table beside it, unless `out=` names another place for it, and `flip=` names further columns to negate. Applying it to its own output returns the input. A rotor table may open with one alias line that holds no comma; it is kept as it stands.

Blade and family names do not change. Blade `k` of the image wheel, at `+(k - 1) 60` degrees on a six-blade wheel, is blade `k` of the installed wheel, at `-(k - 1) 60`, so a table keeps its row order and its names. The mirror changes sign or maps a column as this table says (a column name is matched case-insensitively at its start, then `_`, a digit or the end of the name; the code reads the same list, `FLIPPED_COLUMNS` and `AZIMUTH_COLUMNS`, and a test holds the two equal):

| column | treatment | why |
|---|---|---|
| `FY` | flip | the force along the mirrored axis |
| `MX` | flip | a moment about an axis in the mirror plane |
| `MZ` | flip | a moment about an axis in the mirror plane |
| `CY[A-Z]*` | flip | the side-force coefficients |
| `CR[A-Z]*` | flip | the roll coefficients, a moment about x |
| `CN[BSW]\d*` | flip | the yaw coefficients of the body, stability and wind axes |
| `CMX` | flip | the coefficient of `MX` |
| `CMZ` | flip | the coefficient of `MZ` |
| `TORQUE` | flip | the sense of rotation reverses in the mirror |
| `RPM` | flip | the signed speed follows the sense of rotation |
| `BETA` | flip | the sideslip angle |
| `CS` | flip | the side-force coefficient |
| `CMN` | flip | the yawing-moment coefficient |
| `AZIMUTH` | azimuth | `psi -> -psi mod 360` |
| `AZIMUTH_START` | azimuth | `psi -> -psi mod 360` |
| `AZIMUTH_END` | azimuth | `psi -> -psi mod 360` |
| `azimuth_deg` | azimuth | `psi -> -psi mod 360` |
| `FX` | keep | along the axis the mirror leaves |
| `MY` | keep | a moment about the normal of the mirror plane |
| `CT` | keep | the thrust coefficient |

The sectional `Fx`, `Fz` and `Moment` are NOT negated by default: the orientation of the section axes is not settled, and negating them on a guess would write a wrong number that looks like a right one. The `flip=` argument names them once it is. Any other column is copied as written.

## The inflow tools' products

Three products of the quasi-steady inflow (since 0.32.0). Each states its units and refuses what it cannot state.

**The fluctuation report.** `pyfs-workspace field time-mean --fluctuation` writes `<stem>.fluctuation.csv` beside the mean, and `--fluctuation-only --last K` writes it alone. For each probe of the last `K` per-step fields it gives the time mean's companion, the POPULATION standard deviation (divided by `K`, not `K - 1`) of each velocity component, `std_vx`, `std_vy`, `std_vz`, and `std_mag = sqrt(std_vx^2 + std_vy^2 + std_vz^2)`, in m/s, with the probe's `x, y, z`, values to nine significant figures. The steps must be consecutive integers holding the same probes (within 1e-6 m), and a single steady field has no fluctuation and is refused. The provenance record names the file and its sha256.

**The interior fill.** `pyfs-workspace field fill-interior --r-body R` (default `0.38` m) gives every probe with `r < R`, `r` the distance from the x axis, the velocity of the probe at `r >= R` with the smallest radius on the same azimuth ray (`atan2(z, y)` within 1e-3 rad). It changes no position, states how many probes it replaced, and refuses a probe with no partner on its ray. A preview by default; `--apply` writes with the provenance of the other field operations.

**The blade-view harmonics.** `pyflightstream.post.inflow_tools.blade_view_harmonics` reads a custom inflow as one blade meets it, in the blade frame with rotation. At radius `r` the blade, at `psi = 0` along `+Z` and `psi` positive in the sense of rotation about `+X`, meets `V_a = v.x` and `V_t = Omega r - v.e_t(psi)`; `phi = atan2(V_a, V_t)` and `dalpha(psi) = -(phi - mean phi)` (the pitch cancels and a power-off field has no self-induction). The variance share of each harmonic `n >= 1` of `dalpha` is reported for `n = 1..8`, `n95` is the smallest `n` whose cumulative share reaches 95 per cent (the plan's `inflow_fft` counting, a harmonic under 0.001 degree of amplitude not counted), `k_1P = Omega c / (2 mean V_rel)` with the mean relative speed of the revolution and `k_eff = n95 k_1P`, and `PASSAGE_POSITIONS` is suggested as `ceil(n_max / N + 1)` for `N` blades. `dalpha_rms_deg` and `dalpha_half_ptp_deg` are in degrees. The rotor axis must be `X` because the profile is a YZ plane. `inflow_harmonics_map` repeats it over advance ratios `J = V / (n D)` of one fixed field, `J` moving the rotor speed and `V` staying, and `write_inflow_harmonics` writes `inflow_harmonics.csv` (`J, r_over_R, c_over_R, dalpha_rms_deg, dalpha_half_ptp_deg, n95, k_1P, k_eff, share_n1 .. share_n8`) and `inflow_harmonics_J.csv` (`J, r_over_R, n95, k_1P, k_eff, dalpha_rms_deg`).

## The quasi-steady rotor

A `qsteady_rotor` point is steady, and every product a steady point writes
(the polar, the rotor table, the sections, the probes) is written for it as
for any steady point: the instant of its own solve, which on a wheel is
clocking 0, except that a wheel's sections hold every clocking and a wheel's
row of the rotor table is the mean of its clockings (both since 0.31.0,
below). The rotor table's speed, `RPM_<alias>`, is the row's, the speed
the free stream turns at, read from the point's quasi-steady record
(`<point>_qsteady.json`), as an unsteady rotor's is read from its plan. Where the row states `ADVANCE_RATIO`, the speed is n = V / (J D) with D the rotor block's own `diameter_m`, never the reference's top-level `rotor_diameter_m`. A
sector's table is its one solve's export as it stands, with no factor for
the periodic copies (the export carries the whole rotor where the row enables
symmetry loads and the sector alone where it does not).

**The rotor table of a wheel is the mean of its clockings** (since 0.31.0;
until 0.30.0 it was clocking 0 alone). The rotor's force and its moment about
the hub are averaged over the `k` clockings, each clocking's own loads export
as the point's record names it: every surface's six components, each taken
from its export's reference velocity to the point's, averaged over the
clockings by the same average the average table takes, and then the rotor's
statics as for any steady point. Because the sum over the rotor's surfaces
and the transfer of the moment to the hub are linear, that is the mean of the
rotor's force and moment, and `CT`, `CQ`, `CP`, `ETA`, `ETAW`, `CN`, `CS`,
`CMN` and `CMS` are then computed from those mean loads:

```text
F_mean = (1/k) sum_i F_i        M_hub,mean = (1/k) sum_i M_hub,i
ETA    = J CT(F_mean) / CP(M_hub,mean)     never (1/k) sum_i ETA_i
```

The table's `products.json` entry says `"source": "mean of k clockings"`
with `k` written out, and `"clockings": k` (a mapping of run to `k` where the
points of one table differ). A wheel point one of whose clocking exports is
missing, unreadable, without a reference velocity, in another analysis frame
or listing other surfaces is not a row of the table and is named under its
key in `products.json` `skipped`; the mean of the other clockings is never
written in its place. A sector is one solve and its row is that solve, as
before.

Two products are the run type's own, and a wheel point's sections
gain its clockings and its validity.

- **The clockings table**, `polars/P<sim>-<ALIAS>_qs_positions.csv`: one row
  per point and clocking, the shape of the unsteady rotor's phase-locked table
  (one row per azimuth). `REDUCTION` is `qsteady_position`; `AZIMUTH` is where
  blade one is at that clocking, `(blade1.azimuth_deg + sense * theta_i) mod 360`
  with `sense` the sign of the rotor's speed, by the one rule the sections
  table's `AZIMUTH` follows (`pyflightstream.post.axes.clocked_blade_azimuth_deg`),
  so the two agree for either hand (until 0.31.0 this added `theta_i`
  unsigned, and a left-hand wheel's two tables disagreed); `POSITION` is `i`
  and `POSITIONS` is `k`. Each value is an
  INSTANT, the steady solve at that clocking.
- **The average table**, `polars/P<sim>-<ALIAS>_qs_avg.csv`: one row per
  point, `REDUCTION` `qsteady_average`, the mean over its clockings of every
  loads column. It is the quasi-steady counterpart of the unsteady time
  average, and it is an AVERAGE over clockings, never over time.

In both tables `J_CLOCK` and `RPM_CLOCK` state what the rotor ran at, from the
speed of the point's own record, the diameter of the rotor's block and the
point's free stream (`V / (n D)`, the one formula of the rotor table), and `J`
states the same number where the row requested no advance ratio. A point with
a speed and a free stream is never `NA` in them; what the row requested is kept
as written, and a point whose free stream or diameter is not stated stays `NA`.

Both carry `CONTEXT_COLUMNS`, the moment point, the validity columns below
(the average table then the rotor state of a wheel point, below, since 0.31.0)
and then, for the rotor (`_<ALIAS>`) and for each blade (`_<family>`),
`FX FY FZ` (N) and `MX MY MZ` (N m, about the rotor's HUB), in the loads
frame's axes, and `THRUST` and `TORQUE`, the components along the shaft, each
taken from the loads export of that clocking at its reference velocity and
the point's density, by the rotor table's own statics. A point whose record
or one of whose clocking exports is missing is not a row, and
`products.json` names it under the file.

**The validity columns**, on both tables and on the sections of a wheel
point: `K_1P_MIN`, `K_1P_MAX`, `K_1P_MEAN` (span weighted),
`SPAN_PCT_K_GT_0_05`, `SPAN_PCT_K_GT_0_1`, `THRUST_PCT_K_GT_0_1`,
`TORQUE_PCT_K_GT_0_1` and `K_1P_SOURCE`, with
`k = Omega c / (2 sqrt(V^2 + (Omega r)^2))` per station. The `1P` is counted
on the blade, once per revolution of that blade: the frequency at which one
blade meets an inflow that varies once around the disc, never the
blade-passing frequency a fixed surface near the rotor feels, nor what a
balance summing every blade reads. Where the point has
a sectional loads export (`K_1P_SOURCE` `sections`), `c` is the export's
`Chord` and `r` the absolute `Offset` of the rows the record's layout gives to
the rotor, read as the radius of a distribution cut along the blade from the
hub; the summary is taken over the rotor's first blade present, so a wheel's
blades do not count one station several times. Each station stands for a
strip, half-way to its neighbours. The two shares are the strips above 0.1
over all strips, of the thrust and of the torque per unit span, both taken
along the rotor's axis (since 0.31.0). The export states `Fx` and `Fz` in the
axes of the frame the distribution was cut in, which the run's sections layout
names for each block; for a cut in that frame's XZ plane the station's force
is `F = Fx e_x + Fz e_z` and the station sits at `r = Offset e_y`, for a cut
in its XY plane `F = Fx e_x + Fz e_y` and `r = Offset e_z`, and with
`a` the rotor's axis (the record's `axis_vector`, in the sense its thrust is
counted positive) stated in the same frame's axes:

```text
thrust per unit span  t = F . a
torque per unit span  q = (r x F) . a
THRUST_PCT_K_GT_0_1 = 100 sum_{k > 0.1} t w / sum t w
TORQUE_PCT_K_GT_0_1 = 100 sum_{k > 0.1} q w / sum q w
```

with `w` each station's strip, so the torque comes from the in-plane
(tangential) component of the force only. In a frame of the rotor
(`<ALIAS>_SMRP`, `<ALIAS>_RMRP`, a blade's `<ALIAS>_RMRP<k>`, and each
clocking's copy of one) `a` is the frame's shaft axis, the rotor's letter or
`z` for a shaft stated as a vector, because every such frame is the hub frame
turned about the shaft; in `MRP`, whose axes are the geometry's, `a` is
`axis_vector` itself. Until 0.31.0 the export's `Fx` was read as the thrust
and `Fz |Offset|` as the torque, which holds only in a frame whose x axis is
the shaft. The reading of an XZ cut rests on the FSI pilot records (RPT-005,
RPT-006); the reading of an XY cut was measured on the 0.31.0 short licensed
confirmation of a clocked wheel, where the strip integrals of `Fx`, `Fz` and
`Fz Offset` over blade one matched the blade's force along the shaft, its
in-plane force and its moment about the shaft to about 2 per cent. **A share
is `NA`**, and the post says why in a WARNING line of `post.log` naming the
point, where a block was cut in a frame whose axes the post does not know (one
a setup creates), in the YZ plane (not measured), or in a block the layout does
not name; where a station of the blade the shares are taken over states its
`Fx`, `Fz` or `Offset` as `NA` or as nothing readable (the line names the
station; a gap is never read as a zero load); where the total is zero; and where
stations of opposite sign put the share outside 0 to 100 per cent, the total
then having no sign a share of it could be read against. Where the point has
no such export the values are the plan's, the chord read off the mesh
(`K_1P_SOURCE` `mesh`), and the two shares are `NA`.

**The rotor state of a wheel point** (since 0.31.0), the quantities the
wheel's correction routes read: six columns after the validity columns in
`_qs_avg.csv`, and the same six under `rotor_state` in the point's validity
file (`null` where not known). With `T` the rotor's thrust along its axis,
the mean over the clockings of `THRUST_<ALIAS>` (the thrust of the rotor
table's mean loads), `rho` the point's density, `V` its free-stream speed,
`n = |rpm| / 60` and `Omega = 2 pi n` the rotor's speed, `D` its diameter,
`R = D / 2`, `A = pi R^2`, and `alpha_p` the angle between the rotor's axis
(in the sense its thrust is counted positive) and the direction of flight,
the direction the free stream comes from (`alpha_p = 0` in axial flight along
the thrust, 90 degrees edgewise):

| column | definition |
|---|---|
| `CT_ROTOR` | `T / (rho A (Omega R)^2)`, the rotor convention |
| `CT_PROPELLER` | `T / (rho n^2 D^4)`, the propeller convention, `pi^3 / 4` times `CT_ROTOR` |
| `MU_ROTOR` | `V sin(alpha_p) / (Omega R)`, the advance ratio in the disc plane |
| `LAMBDA_C` | `V cos(alpha_p) / (Omega R)`, the free stream through the disc against the thrust |
| `LAMBDA_I` | the momentum-theory induced inflow, the root of Glauert's relation below |
| `CHI_DEG` | `atan2(MU_ROTOR, LAMBDA_C + LAMBDA_I)` in degrees, the wake skew angle |

```text
LAMBDA_I = CT_ROTOR / (2 sqrt(MU_ROTOR^2 + (LAMBDA_C + LAMBDA_I)^2))
```

`LAMBDA_I` is solved by Newton's method from the hover value
`sign(CT_ROTOR) sqrt(|CT_ROTOR| / 2)` until a step is no larger than 1e-10, in
at most 100 steps (`pyflightstream.cases.qsteady.glauert_induced_inflow`). A
relation that does not converge (momentum theory does not describe a rotor
descending into its own wake) leaves `LAMBDA_I` and `CHI_DEG` `NA`, and the
post says so in a WARNING line of `post.log` naming the point and the average
table; `NA` everywhere a thrust is not known at every clocking, or the point
states no density or speed. `MU_ROTOR`, not `MU`: `MU` is the air's viscosity
in every table's condition block. A sector's row reads `NA` in all six.

**The sections of a wheel point** (0.31.0) hold EVERY clocking: the wheel
exports its section distributions at each clocking, created again in that
clocking's pose in frames turned with the wheel (see the workspace page), and
`sections/<point>_sections.csv` holds clocking 0's rows, then clocking 1's,
up to clocking `k - 1`'s, each block in the order the run recorded it. After
the export's own columns come:

| column | what it is |
|---|---|
| `CLOCKING` | `i`, the clocking the row was cut at; 0 is the point's own solve |
| `K_1P` | the reduced frequency of the row's station (`NA` on a row no rotor owns) |
| the validity columns | the point's, one value down the table |

and on every row `ROTOR` is the wheel's rotor for a block of its families,
and `AZIMUTH` states where the block's blade is at that clocking,

`AZIMUTH = (blade1.azimuth_deg + (n - 1) * 360 / N + sense * i * (360 / N) / k) mod 360`

for a block of ONE blade, blade `n` of the rotor's `N` (its place in
`families_blades`), with `sense` the sign of the rotor's speed: blade `n`
sits `(n - 1) / N` of a turn from blade one, as the blade frames are placed,
and clocking `i` turns the wheel by `theta_i` in the sense of rotation, as the
surfaces are turned. A block of several families of the rotor states blade
one's, which is what `AZIMUTH` means in every other sections table; a block
no rotor owns reads `NA`. The rule has one home,
`pyflightstream.post.axes.clocked_blade_azimuth_deg`.

Every clocking is cut at the same stations (each distribution is created in
its frame turned with the blades, so the blade spans one interval along every
clocking's normal): the post compares each clocking's blocks, planes and
`Offset` with clocking 0's, to a thousandth of the largest offset, and a
clocking that differs is tabled as exported and warned in `post.log`. A
clocking whose export the point's record does not name (a wheel run before
0.31.0 exported its sections at clocking 0 only), or which is not on disk, is
not in the table, and `products.json` names it under the table's key with
`#clocking=<i>`; the other clockings are written.

The validity summary is taken over clocking 0's rows, the point's own solve,
so a clocking's stations are not counted `k` times; `K_1P` is stated on every
row.

**The super file** row of a wheel point carries the validity columns after
every other key of the row, the sections' values where the point has them,
else the plan's; `NA` in the rows of every other point.

**The per-point validity file**, `<point>_qsteady_validity.json`, is written by
the post into the wheel point's datapoint folder, beside the run's
`<point>_qsteady.json`: every value of the validity columns (the thrust and
torque shares included, `null` where not known), `K_1P_SOURCE`, the rotor state (`rotor_state`, since 0.31.0), and the
plan's record as the run kept it. The run's record is a hashed input of the
run and is never rewritten; this file is the post's and every post rewrites
it. `products.json` names each point's file under the clockings and average
tables' entries (`validity_files`, relative to the products folder).

The steady polar table and the rotor table of a quasi-steady point do not
carry the validity columns: their columns are a fixed contract a reader's
scripts index, and no line precedes a CSV header, so a reader of those two
finds the point's values in its super-file row and in its validity file.

**A point whose quasi-steady record cannot be read** (missing, not JSON, of a
schema other than the one the package writes, or holding a key it does not
write) keeps every product that does not need the record, and loses, each by
name in `products.json` `skipped` and as a WARNING line in `post.log`, the ones
that do: its row of the rotor table (the speed is the record's), its rows of the
clockings and average tables, and, where it has a sections table, that
table's `K_1P` column and validity columns. The reason given is the record's
own refusal, naming the file. The post never stops on it.

---

## Quasi-steady wheel corrections

!!! note "New in 0.31.0, and NOT VALIDATED"
    The machine that applies a correction to a `qsteady_rotor` wheel's
    products at post, beside the raw ones. Every route is off by default and
    none is validated; the choice of a route and of its numbers is research's.
    The user's page is [Quasi-steady wheel corrections](qsteady-corrections.md).

**What asks for it.** The pproc's `[qsteady_correction]` table: `route`
(`none`, the default; `table`, route 4; `sector_offset`, route 2), `file` (the
id of `inputs/calibrations/<id>.toml`, required by a route) and `diagnostic`
(`none`, the default, or `theodorsen`). Route 1 (the Theodorsen and Sears lift
deficiency) is refused as a route and offered as the diagnostic only; route 3
(`dynamic_inflow`, `skewed_wake`, `pitt_peters`, `coleman`) is refused, its
double counting with the solver's own wake being unmeasured. It applies to the
WHEEL points of a simulation and to nothing else; a simulation of quasi-steady
points none of which is a wheel is named under `skipped`
(`qsteady_correction#sim=<sim>`).

**It is read from the WRITTEN products**, after the post has written them, and
never writes over one: each corrected product is a new file,
`<name>_corrected.csv`, beside its raw file, and the raw file is byte for byte
what a post with no route writes.

**The calibration and its grid.** Each row of the file names a component, its
place on the axes `J` (the rotor table's `J_<ALIAS>` of the point), `ALPHA`
(the point's, deg) and `K_1P` (the station's for a sectional component, the
point's `K_1P_MEAN` for a rotor component), and the coefficients `OFFSET_0P`,
`GAIN_0P`, `GAIN_1P` and `PHASE_1P_DEG`. The rows of one component form a
tensor grid over the axes whose values vary; an axis with one value is
constant and constrains nothing. The coefficients are interpolated
multilinearly inside the grid; a point outside it on a varying axis, or stating
no value on one, is NEVER extrapolated: its corrected cells are `NA`, named in
`skipped` (`<corrected file>#point=<point>#component=<C>` for a rotor table or
an average table, `<corrected harmonics>#component=<C>` for a station) and in a
WARNING line of `post.log`. A file the post cannot read corrects nothing,
named under `calibrations/<id>.toml#sim=<sim>`.

**The corrected products**, for a component the calibration names:

| file | the change |
|---|---|
| `polars/P<sim>-<ALIAS>_rotor_corrected.csv` | `CT_<ALIAS>`, `CQ_<ALIAS>`, `CN_<ALIAS>`, `CS_<ALIAS>`, `CMN_<ALIAS>`, `CMS_<ALIAS>`: `q' = GAIN_0P q + OFFSET_0P`; `CP`, `ETA` and `ETAW` `NA` where `CT` or `CQ` is corrected |
| `polars/P<sim>-<ALIAS>_qs_avg_corrected.csv` | `THRUST_<ALIAS>`, `TORQUE_<ALIAS>`, `FX_<ALIAS>` .. `MZ_<ALIAS>`, `CT_PROPELLER` (by `CT`), `CT_ROTOR`: the same; `CT_ROTOR`, `CT_PROPELLER`, `LAMBDA_I` and `CHI_DEG` `NA` where the thrust is corrected and they are not |
| `sections/<point>_harmonics_corrected.csv` | per station: `H0' = GAIN_0P H0 + OFFSET_0P`, `H1_AMP' = GAIN_1P H1_AMP`, `H1_PHASE_DEG' = H1_PHASE_DEG + PHASE_1P_DEG` in `[0, 360)`; `H2_AMP`, `H2_PHASE_DEG` and `RESIDUAL_RMS` unchanged |
| `sections/<point>_sections_corrected.csv` | each row, blade `n` at clocking `i` at its `AZIMUTH` `psi`: `load' = load + (H0' - H0) + [A1' cos(psi - PHI1') - A1 cos(psi - PHI1)]` with the station's fit as the harmonic product wrote it; `Fx_int`, `Fz_int`, `My_int` `NA` where their load is corrected |

A station whose 1P harmonic is `NA` is corrected in its 0P term only, and the
entry says how many cells. A column no component names is carried raw.

**Every corrected file** ends with `CORRECTION_ROUTE` and `CALIBRATION_SHA256`
on every row. Its `products.json` entry: `kind` `corrected`, `raw`, `route`,
`calibration` (the file, relative to the workspace), `calibration_sha256`,
`cells` (each point, component and, for a section component, station, with the
grid values bracketing it on each varying axis and the one value of each
constant axis), `derived_na`, `validation` `not validated`, a `note`, and
`source_run_id` (and `wheel_run_id`) for route 2. A route 2 file's
`source_run_id` that is not a run of `runs.json` is a WARNING line and the file
is applied as it stands.

**The diagnostic**, `sections/<point>_theodorsen.csv`, for a wheel point with a
harmonic product: `POL`, the condition (the harmonic product's), then `ROTOR`,
`QUANTITY`, `STATION_R_M`, `R_OVER_R`, `K_1P` (the station's, from the
sections), `C_ABS` and `C_PHASE_DEG` of `C(k) = H1(k) / (H1(k) + i H0(k))`,
`Hn = Jn - i Yn`, `S_ABS` and `S_PHASE_DEG` of
`S(k) = (J0(k) - i J1(k)) C(k) + i J1(k)` (the gust referred to mid-chord),
phases in degrees in `[-180, 180]`, `C(0) = S(0) = 1`, then the measured
`H1_AMP` and `H1_PHASE_DEG`. Entry: `kind` `theodorsen`, `source` (the harmonic
product), `diagnostic`, `validation`. It corrects nothing.

## The acoustic signals product

A point whose record lists acoustic signals (since 0.32.0) gets, under
`acoustics/` of its products, the tables below, read from the file the solver's
`EXPORT_ACOUSTIC_SIGNALS` wrote. The export holds, per observer, a block: a line
`Observer: <name>`, a line `Position: x,y,z` (Fortran-style numbers such as
`.00,10.0,.00`), a line `Columns: Observer time (sec), PL (Pa), PT (Pa), PO (Pa)`
and one row per sample (measured on build 26.124, probe A1). The manual pages of
the toolbox (SRC-003 pp.374 and 380) do not define the three pressure columns;
the probe shows `PO = PL + PT` in every row, and the package reads `PO` as the
overall pressure and calls PL the loading part and PT the thickness part, which is
the customary split and not a vendor statement. The unit of the position is not in
the file and is read as metres.

`<n>` is the observer's place in the export, from 01, and `<observer>` its name
made safe for a file name.

- **Pressure against time**, `<point>_<n>_<observer>_pressure.csv`: `TIME_S`,
  `PRESSURE_PA`, the `PO` column.
- **Spectrum**, `<point>_<n>_<observer>_spectrum.csv`, with the columns
  `FREQUENCY_HZ`, `AMPLITUDE_PA` and `LEVEL_DB`: the one-sided amplitude
  spectrum of `PO` over the observer time, the real FFT of the samples as they are
  (no window, mean kept). For `N` samples at the constant step `dt`, the sampling
  rate is `1/dt` and the bin width `1/(N dt)`; bin 0 is `|X0|/N` (the mean), a
  bin below Nyquist is `2|Xk|/N`, the Nyquist bin of an even `N` is `|Xk|/N`, so
  a cosine of amplitude `A` on a bin reads `A`. `LEVEL_DB` is
  `20 log10((A/sqrt(2)) / 20e-6 Pa)`, `NA` for bin 0 and for a zero amplitude. A
  step that is not constant (relative spread above 1e-3) gives no spectrum.
- **OASPL**, `OASPL_DB` of `<point>_acoustics_summary.csv`:
  `20 log10(p_rms / 20e-6 Pa)`, `p_rms` the root mean square of `PO` about its
  mean over the whole record; `NA` for a silent record. The summary has one row
  per observer, with the columns `OBSERVER`, `X_M`, `Y_M`, `Z_M` (the position),
  `SAMPLES`, `TIME_START_S`, `TIME_END_S`, `SAMPLE_RATE_HZ`, `BIN_HZ` (the bin
  width of the spectrum) and `OASPL_DB`; the sampling rate and the bin width are
  `NA` where the step is not constant.
- **Blade-passage harmonics**, `<point>_acoustics_bpf.csv`, with the columns
  `ROTOR`, `OBSERVER`, `HARMONIC`, `FREQUENCY_HZ`, `BIN_HZ`, `AMPLITUDE_PA` and
  `LEVEL_DB`, one row per observer, rotor and harmonic: for each rotor of the
  record with its blade count `B` and speed `rpm`, harmonic `n` (1 to 4) is at
  `n B |rpm| / 60` hertz (the sign of the speed only states the sense of rotation), read at the nearest bin of the observer's spectrum, with
  the bin frequency, the amplitude and the level. `NA` when the record states no
  blades or speed, above the Nyquist frequency, or below one bin width; each `NA`
  has a line in `post.log`.
- **Directivity**, `<point>_acoustics_directivity.csv`, written only when at
  least four observers are coplanar and lie on one circle (each within 1e-3 of the
  radius): per observer the angle about the circle's centre, measured from the
  first observer and increasing toward the second, in `[0, 360)` degrees, the
  radius and the OASPL, as the columns `OBSERVER`, `ANGLE_DEG`, `RADIUS_M` and
  `OASPL_DB`. Fewer than four observers, or any off the circle, is not
  an arc and writes no file.

**The manifest and the skips.** `products.json` registers each of these files
with `kind` `acoustics`, `source` `acoustic_signals` and `observers`, the number
of observers of the export. The export is the file the record lists under
`acoustic_signals`; a record that lists none asks for no acoustics, and nothing
is said. An export the post cannot read is named under `acoustics` in the
post's skips and warned in `post.log`, and the other products are written.

**The section is not a table.** The VTK files of an `ACOUSTIC_SECTION`, in
`<point>_acoustic_section/`, are the solver's own and are recorded and hashed
as outputs of the point ([acoustic signals](acoustic-emission.md#what-the-run-writes));
the post reads none of them, and no table is derived from them.

## The post of other records (since 0.32.0)

The products of `pyfs-matrix post` are rebuilt from `runs.json` by default.
Two options post other records, and their products stand apart from the
default ones so the two can be compared; the columns inside are the default
post's. The file names of `--runs NAME` are the default post's too; those of
`--from-sims` carry the point names and the sweep token the records were
assembled with (below), since the naming a run outside the package used is
not recorded anywhere to be repeated.

| command | the records | the products folder |
|---|---|---|
| `pyfs-matrix post <matrix>` | `runs.json` | `post/<matrix>/` |
| `pyfs-matrix post <matrix> --runs NAME` | the manifest `NAME` in the workspace root | `post/<matrix>@<NAME without .json>/` |
| `pyfs-matrix post <matrix> --from-sims` | assembled in memory from `sims/` | `post/<matrix>@sims/` |

An apart folder holds its own `products.json`, `post.log`, `archive/` and its
own measurement reports under `reports/`; nothing under `post/<matrix>/` or the
workspace's `reports/` is written by it. `pyfs-matrix collect --runs NAME`
completes the submitted records of `NAME` and posts them apart the same way.

**What `--from-sims` assembles, and what it refuses.** Each loads export under
`sims/sim_<POL>/` of a row of the matrix is one point (outside the `archive`,
`scripts` and `inputs` folders), and the files beside it named its stem plus
the suffix of another export kind (`<stem>.dat`, `<stem>_plots.txt`,
`<stem>_log.txt` and the rest) are its other exports; a file whose name only
begins with the stem is another point's. The record takes:

- the point: the value of the row's sweep at the angles the export reports;
- the flight condition: the row's, the swept value in place, resolved with the
  setup's pins, while the export's reported velocity, angles and Reynolds
  number still win in every product row, as they do for a recorded run;
- the reference block and the aliases: the row's reference;
- the averaging window: the row's `LAST_REVS_AVG` or `LAST_ITERS_AVG`, cut over
  the steps of the point's plots export, with `--steps-per-revolution N` for a
  window in revolutions;
- the point's name: its `DP-<name>` folder's, else the export's stem; the
  sweep token in the file names is `<code>+sweep`, for example
  `P6001-AL+sweep_g02.csv`;
- the status: the collect's assessment of the exports, so a steady point with
  no log export reads `FAILED_INCOMPLETE_OUTPUT` and is posted with a warning.

What cannot be recovered is refused by name and that point or row is left out,
printed and written into `post.log`: a reference that does not resolve, a
condition that does not resolve, an export whose angles are no value of the
sweep (or a row sweeping anything but an angle over more than one value), two
exports at one point, a time history with no window in the row, and a window in
revolutions with no `--steps-per-revolution`. Such a record carries no rotor
block, so the rotor tables and the per-rotor reductions of its point are named
skips. No manifest is written.

## Posting and collecting some simulations (since 0.33.0)

`pyfs-matrix post <matrix> --sims 2006,2007` rebuilds only those simulations'
products of the matrix, in place. The ids are written as `delete-sims` takes
them: comma separated, or in brackets (`[2006,2007]`). Each named simulation's
files are archived into their folder's `archive/<stamp>/` and rewritten as a
whole post writes them; every other simulation's files keep their bytes, and
`products.json` keeps their entries, their skips and their provenance as they
were, while the named simulations' entries and skips are replaced. Without a
matrix, each matrix holding a named simulation is posted, limited to the ones
it holds. A named simulation with no record of the matrix is refused by name
before anything is written.

A product built from several simulations is never written from some of them:

| product | under `--sims` |
|---|---|
| the super files (`polars/SUPER-*`), whose columns are the union over every simulation of the matrix | left as the last whole post wrote them, the named simulations' included |
| `reports/superfile-<release>.json`, the measurement of the super files | left as it was |
| `reports/sections-<release>.json`, the sections measurement | rebuilt from every recorded simulation of the matrix, as a whole post rebuilds it, unless another simulation's folder is compacted or deleted; then left as it was |
| the provenance documents | written for the named simulations only, under the name a whole post gives them |

Each product left is named with its reason under `partial.not_rebuilt` in
`products.json`, beside `partial.sims`, and in one WARNING line of `post.log`.
`pyfs-matrix post <matrix>` without `--sims` is the whole post and rebuilds
them. `campaign_sweep.csv` is written by the run, not by the post.

`pyfs-matrix collect --sims 2006,2007` sweeps only the SUBMITTED records of
those simulations, and of their additional extractions; every other record is
left untouched and is not counted as outstanding, so `--watch` stops once the
named simulations are collected. The post that follows (unless `--no-post`) is
limited to the same simulations. An id no record carries is refused before
anything is swept. In Python the keyword is `sims` of
`write_campaign_products`, `collect_once` and `collect_and_post` (FR-307).

`pyfs-matrix collect --discard-walltime` marks each latest WALLTIME_REACHED
record in that scope FAILED_MARKED after the sweep, before post, including
records from an earlier collect. Under `--watch` it does this after every
pass. It keeps the previous status in `marked.from` and records
`discarded_by: "collect --discard-walltime"`. Outputs stay on disk. A grouped
plan takes the point again from the start automatically, and its run archives
the old record and outputs; a default-mode plan needs `--force-rerun`.
Without the option collect behaves as before (FR-400).
