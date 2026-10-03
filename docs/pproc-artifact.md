# The post-processing artifact and its products

What the post-processing artifact of a row holds, the products it derives, and archiving a completed simulation. The definition of every reduction is in [the post-processing definitions](post-processing-definitions.md).

## What the post-processing artifact holds

`PPROC` names `inputs/pproc/p<id>.toml`, the post-processing artifact
(PFS-2029.07). It carries twelve optional tables; a file holding `[groups]`
alone is valid. `[volume_section]` has [its own paragraph below](#a-volume-section).
`[names]` renames the unsteady polar's plot columns to the names a
downstream tool reads, the whole dictionary or none of it, and is defined on
[the definition of record](post-processing-definitions.md); the other three,
`[phase_locked]`, `[equations]` and `[glossary]`, are described under [the three tables that reduce and derive](#the-three-tables-that-reduce-and-derive).

Omitted export kinds follow the run type's defaults; they are not all enabled.
See [Native surface flow exports](post-processing-definitions.md#native-surface-flow-exports)
for the VTK, CSV and force-distribution opt-in rule, [The solver's own plots](post-processing-definitions.md#the-solvers-own-plots)
for the residual, load and section Cp plots a steady point saves, and
[The probes table](post-processing-definitions.md#the-probes-table)
for the unsteady plots source, whose defaults omit the probe-points export.

```toml
base_regions = ["Base"]        # the boundaries that become base regions; [] = off
singularity_strength = true    # the Tecplot surface carries the nodal strength (off by default)

[groups]                       # group NAME -> ONE alias, written as a string (0.24.0)
TOTAL = "all"                  # every family the geometry carries
AIRFRAME = "airframe"          # an alias of the row's reference, under its [aliases]
ROTOR = "Blade"                # a family is every member of it: Blade1, Blade2, ...

[exports]                      # override the defaults for this run type
tecplot = false                # disable Tecplot; loads and simulation cannot be off
vtk = true                     # opt in to VTK surface export
csv = true                     # opt in to CSV surface export
force_distributions = true     # opt in to the per-panel force distribution, at run end
plot_loads = false             # a steady point saves the solver's plots; switch one off

[sections]                     # NEW_SURFACE_SECTION_DISTRIBUTION per entry and plane
count = 50
plot_direction = 1
include_symmetry = false
[[sections.distributions]]
families = ["W"]
frame = "MRP"
planes = ["XZ"]
[[sections.distributions]]
families = "LIFT"              # the rotor; LOCAL_AXIS makes it one per blade
frame = "LOCAL_AXIS"           # the FRAME says how the entry expands
planes = ["XY"]

[plots]                        # UNSTEADY_SOLVER_NEW_FORCE_PLOT per group and parameter
parameters = ["CL", "CDI", "CDO", "CD", "FX", "FY", "FZ", "MX", "MY", "MZ"]
[[plots.groups]]
name = "MRP_TOTAL"             # the plot is named {parameter}_{group}: CL_MRP_TOTAL
frame = "MRP"
families = "all"
[[plots.groups]]
name = "MRP_{family}"          # one group per family the geometry carries
frame = "MRP"
families = "each"
[[plots.groups]]
name = "{family}_SMRP"         # one group per rotor, in ITS OWN frame: FZ_LIFT_SMRP
frame = "SMRP"
families = "LIFT"

[[probes]]                     # UNSTEADY_SOLVER_NEW_FLUID_PLOT per vertex and parameter
frame = "LIFT_SMRP"            # a rotor frame: one probe set per rotor it reaches
parameters = ["MACH", "VELOCITY", "VX", "VY", "VZ", "STATIC_PRESSURE_RATIO"]
points = 25
scale = "rotor_radius"         # or "m"; the radius is THAT rotor's, not the configuration's
[[probes.lines]]
start = [-2.0, -1.0, 0.0]
end = [-2.0, 1.0, 0.0]

[products]                     # the post-processed CSV tables the campaign writes
polars = true                  # one polar table per group, per point
sections = true                # one table per point from its sectional loads export
plots = true                   # one table per unsteady point from its plots export
custom_polar_format = false    # beside each polar table, the text file the reference tooling opens

[phase_locked]                 # OPTIONAL: the phase-locked table becomes one row per azimuth
min_revolutions = 4.0          # generated when the row turns AT LEAST this many revolutions
last_revolutions_avg = 2.0     # how many of the last revolutions enter each azimuth's mean

[equations.T_AXIAL]            # a derived column of the unsteady polar: T_AXIAL_LIFT
expression = "-FZ"             # FZ about LIFT in SMRP is the plotted column FZ_LIFT_SMRP
meshes_alias = "LIFT"          # an ALIAS, never a family list
frame = "SMRP"
[equations.CT_FLIGHT]          # an equation may name another; the order is worked out
expression = "T_AXIAL / (0.5 * RHO * VINF**2 * SREF)"
meshes_alias = "LIFT"

[glossary]                     # what YOUR symbols mean; listed in inputs/pproc/VARIABLES.md
T_AXIAL = "N. Axial force of the lifters in their own frame, sign flipped"
CT_FLIGHT = "-. T_AXIAL over the free-stream dynamic pressure and SREF"
```

Three things carry the artifact across configurations. A `families` entry
is a list of family names, a bare word (an alias the row's reference
declares, read first, above; else a family name), or one of TWO SELECTORS:
`all` (every boundary, the command's own `-1` form) and `each` (one entry
per family the geometry carries, the name carrying `{family}`). A family
the geometry does not carry is left out, which is how one artifact serves
a wing-body and an isolated rotor, and an entry that resolves to nothing
is skipped; pass `--ignore-missing-families false` to `pyfs-matrix plan`
or `run` to have a name no boundary answers refused instead. The skip is
never silent for a section distribution or a force plot group (FR-320; a plot group is emitted on unsteady rows only): the plan
prints one warning per pproc artifact and per family that an entry declares
and the geometry of some row does not carry, naming the entry and every row
that lacks it, and every such row still plans READY. A numbered name counts
by itself: `Blade2` is missing on a sector whose mesh carries `Blade1` alone,
and a misspelled `Bladee2` beside `Blade1` is named the same way. A row that
carries every family is named in no warning. The word
is read: `true`, `yes` and `1` mean yes, `false`, `no` and `0` mean no, and
anything else is refused naming the flag and the word rather than quietly
meaning yes.

The choice reaches each case as the row variable
`IGNORE_MISSING_FAMILIES`, which is what a refusal quotes back at you and
what `pyflightstream.cases.workflows.IGNORE_MISSING_FAMILIES_VARIABLE`
spells for a Python caller:

<!-- skip: next -->
```python
from pyflightstream.cases.workflows import IGNORE_MISSING_FAMILIES_VARIABLE

case = case.model_copy(
    update={"variables": {**case.variables, IGNORE_MISSING_FAMILIES_VARIABLE: "false"}}
)
```

**A MATRIX CELL MAY NOT WRITE IT.** The reader refuses a row that states the
key and points you at the flag, because whether a family the mesh lacks is a
skip or a refusal is a property of the RUN and not of the row: the same row
is planned across a wing and a rotor, which is the whole reason the skip
exists. At the default nothing at all is written onto a case, so every
recorded run keeps its identity and every emitted script its bytes.

### The three tables that reduce and derive

**`[phase_locked]`** is optional, and it does two things. It GATES the
phase-locked reduction: the table is generated when the matrix row turns at
least `min_revolutions`, counted over the whole run of THAT rotor
(`TIME_ITERATIONS` over its steps per revolution) and never over the exported
window, and equal generates it. A run that turned less loses this one table,
named under `skipped` in `products.json` with both numbers; its polar, its
per-blade table and every other product are written as usual. And it sets the
SHAPE: with the table, `probes/<point>_phase_locked[_<ALIAS>].csv` is one row
per azimuthal position, the mean of the samples at that azimuth across the
last `last_revolutions_avg` revolutions, as
[the definition of record](post-processing-definitions.md#phase_locked) states
it. `last_revolutions_avg` may not exceed `min_revolutions`. Without the table
the file is the series of blade passages it has always been. The table is read
again by `pyfs-matrix post`, so adding, editing or removing it needs no new
run.

**`[equations]`** adds derived columns to the unsteady polar,
`polars/P<sim>_<name>_uns_avg.csv`, after the axis coefficients and before the
setup of the row, each named `<NAME>_<alias>`. An expression is arithmetic
over the columns that row already holds: numbers, names, `+ - * / **`, unary
minus, parentheses and `abs, sqrt, sin, cos, tan, radians, degrees, min, max`.
It is parsed and walked, never executed, and a construct outside that list is
refused when the artifact is read. A symbol `S` of an equation about alias `A`
in frame `F` is, first match wins: another equation named `S`; the column
`S_A_F`, then `S_F_A`, where a frame is stated; `S_A`; the column `S` exactly
as the file spells it. Above, `FZ` reads `FZ_LIFT_SMRP` and `RHO` reads `RHO`.
A symbol none of them answers refuses the WHOLE block: the polar is written
without derived columns, `products.json` says why under
`polars/<file>#equations` naming the equation, the symbol, the spellings tried
and the columns there are, and the stage warns. It is never a column of `NA`.
A chain that loops is refused when the artifact is read, naming its members.

**`[glossary]`** is one line per symbol of yours. It reaches the generated
guides: `pyfs-workspace init`, `pyfs-matrix plan` and `pyfs-matrix post` write
`VARIABLES.md` and `WRITING-EQUATIONS.md` into `inputs/pproc/`, the first
listing every column the products state with its unit and definition and,
beside them, the glossary of every pproc artifact in the folder, the second
saying how to write an equation. Both are generated from the code and are
rewritten only when their content would change; no other file of the folder
is touched.

The selectors are `all` and `each`.
`each_blade` went because the FRAME says how an entry expands now, so
`frame = "LOCAL_AXIS"` is what one distribution per blade is written as.
`airframe` and `blades` went because they are the two that decide what a
BLADE IS, from `blade_pattern`, a regular expression over the family name,
`^Blade\d+$` unless the file says otherwise: a mesh whose blades are
spelled another way gets an airframe with blades in it and nothing says
so. Declare the set in the reference's `[aliases]` table and cite it by
name, and a study that named its own surfaces cannot be guessed wrong.
All three are REFUSED, not warned about, and the refusal names what to
write instead; an alias of the same name is read FIRST, so a reference
that already declares `airframe` is untouched and keeps its own meaning.
The refusal arrives when the ROW is built, at `plan`, because whether
`airframe` is an alias or the retired selector is a question about the
reference the row cites. A `frame` is
cited by NAME: `MRP`, the moment frame the reference artifact creates;
`SMRP` and `RMRP`, a rotor's hub frame and its turning frame, and
`LOCAL_AXIS`, one frame per blade (0.15.0, and see the next paragraph for
what those three do to the entry); `<ALIAS>_SMRP`, `<ALIAS>_RMRP` and
`<ALIAS>_RMRP<k>`, the same frames named for ONE rotor, which is how an
entry says which rotor it is about on a row that turns nine; a frame the
row's REFERENCE declares in its `[[frames]]` table, by the name written
there (`LIFTERS_MRP`, `PUSHER_TIP`); and `BLADE_AXIS` on the flat rotor
row. The retired names, `PROP_MRP`, `PROP_MRP<k>` and
`RotorAxis<k>`, do NOT resolve: they went with the package-level rotor
frame, and an entry citing one is refused naming the shape to write.

**THE FRAME DECIDES HOW THE ENTRY EXPANDS**, which is why there is no
`expand` key and why `each_blade` retired. An entry in `MRP` or a declared
frame is ONE over the families it names. One in `SMRP` or `RMRP` is one
per ROTOR those families reach, each in that rotor's own frame. One in
`LOCAL_AXIS` is one per BLADE, plus one for the rotor's `families_general`,
which have no local axis and ride the rotor's. Six lines of a `[plots]`
table are twenty-seven emissions on a nine-rotor aircraft. A name that
would collide carries `{family}`, and the reader refuses a name without it
where the entry emits more than once.

TWO WAYS AN ENTRY CAN FAIL TO LAND, and they are deliberately different.
An entry whose families reach no rotor the REFERENCE declares is REFUSED
at plan time, naming the rotors and the aliases it could have named,
because that is a writing error and cannot come right on another mesh. An
entry whose rotors the reference does declare, but whose frames THIS RUN
did not place, is LEFT OUT with a warning, exactly as an entry whose
families the geometry lacks is: a steady row places no rotor frames and a
lifters-only row places none of the pusher's, and one artifact serves all
three rows.

!!! warning "A rotor's frames are named from its alias"

    A motion record that names a rotor block of the reference
    instantiates `<ALIAS>_SMRP` at the hub, `<ALIAS>_RMRP` turning with
    the motion, and `<ALIAS>_RMRP<k>` per blade of that block's
    `families_blades`, turning with blade k (FR-62). Nine rotors
    instantiate nine sets rather than colliding on one radical, so a
    post-processing entry can say WHICH rotor it is about:
    `frame = "PUSHER_RMRP"`.

    A row that ROTATES that alias also gets `<ALIAS>_SMRP_ORIGINAL`, a
    copy of the hub frame as it stood before the first rotation, which
    nothing turns (FR-71). It is created once per alias, so a row that
    turns one alias twice keeps the state before the FIRST rotation.

    **AND YOU DO NOT HAVE TO CITE IT.** An entry naming a hub frame that
    this row rotated is written in BOTH: once in `<ALIAS>_SMRP`, where the
    rotation left it, and once in `<ALIAS>_SMRP_ORIGINAL`, where it
    started. The plot names differ by the same suffix, so the two tables
    sit beside each other. That is the rule of 2026-09-10: an
    entry says which ROTOR it is about, and the row's rotation decides how
    many readings of it there are, exactly as the frame decides how many
    emissions an entry stands for. A rotor this row did not turn has no
    original frame and nothing doubles. `<ALIAS>_RMRP` and
    `<ALIAS>_RMRP<k>` never double: they turn WITH the motion at every step
    of an unsteady run, so there is no single frame they turned from.

    `PROP_MRP<k>` and `RotorAxis<k>` are refused for an entry written
    against 0.14.0, and a record that names no alias still emits them, so
    a workspace may migrate its rows before its post-processing. The
    custom frames come from the REFERENCE now, not the preset, and a
    family of `families_general` gets no frame of its own: its local frame
    IS the rotor's, which is what makes the spinner ride the hub.

An entry that resolves to nothing is skipped, unless this run asked for the
refusal (see `--ignore-missing-families` above); an entry WRITTEN as nothing
is refused, at `pyfs-matrix plan`, naming the file, the key as the file
spells it, and what the empty list feeds (PFS-2005.02, "an empty boundary
list is refused wherever the solver would read it as disable everything"),
except where the selection has an explicit meaning. A pproc group uses one
alias string:

```toml
[groups]
TOTAL = "all"
```

When no boundary or reference alias is named `all`, this selects EVERY FAMILY
of the geometry: the polar sums every surface row, and a motion using this
selection moves every boundary. Check for that collision before migrating;
see [the 0.26.0 migration check](migrating-to-0.26.0.md#6-a-pproc-group-names-one-alias).
A group value resolves first as a boundary name, then a reference alias from
`[aliases]`, then a family label without its trailing number. Thus `"airframe"`
selects the reference alias's members, while `"Blade"` can select `Blade1`
through `Blade6`. Members absent from the geometry are left out.

Historical syntax, retired at 0.26.0: `TOTAL = []` selected every family in the retired list syntax, and nonempty member lists and integer positions were also accepted.
Current editable inputs refuse all group lists; use one alias string and name
boundary members in the reference instead. `families = []` in a
`[[plots.groups]]` or a `[[sections.distributions]]` entry is refused,
naming `UNSTEADY_SOLVER_NEW_FORCE_PLOT` or
`NEW_SURFACE_SECTION_DISTRIBUTION`: the entry exists to emit over the
families it names, and over none it would emit nothing while reading as
though it had. `base_regions` is the other selection whose empty list has
a documented meaning, the autodetect off, which is its default. The table
the readers consult is `pyflightstream.workspace.inputs.ENTITY_SELECTIONS`,
one row per key with the verdict and its reason.

`base_regions` is a TOP-LEVEL key, so it goes above the first table
header, as the example above places it: TOML puts a key written under
`[groups]` INTO that table, where it is a group named base_regions. The top-level key is recognised separately from retired groups files (PFS-2005.04); `base_regions = []` there is the documented off switch and
plans READY, and `base_regions = ["Base"]` reaches the script as one
`DETECT_BASE_REGIONS_BY_SURFACE` per boundary of the family. It names the
boundaries that BECOME the base regions, as the row's `BASE_REGIONS` does:
the body's own boundary marks nothing (RPT-066).

**A GROUP IS NAMED, and the product file carries the name.** An
artifact

```toml
[groups]
PUSHER = "Blade1"
"wing" = "Wing"
```

is accepted, and its polar tables are
`polars/P0001-M150AL+000BE+000J+sweep_PUSHER.csv` and `..._wing.csv`. A group
keyed by a NUMBER, as the example at the top of this section keys its four,
still binds, and its files keep the numbered suffix: `"1"` writes `..._g01.csv`.
That suffix survives only for a pproc that still numbers its groups, so the
products of a workspace with numbered groups and the ones written beside them
stay one convention. [Migrating to 0.23.0](migrating-to-0.23.0.md) has the
command that renames products already written.

**A GROUP IS ONE ALIAS, written as a string.** The key names the
product file and the value names what is summed:

```toml
[groups]
PUSHER   = "PUSHER"      # a rotor of the reference: that rotor's own families
AIRFRAME = "airframe"    # an alias of the reference's [aliases] table
TOTAL    = "all"         # every family, if no boundary or alias takes this name
```

so a steady polar per alias is one line, and its table is `..._PUSHER.csv`. A
group that names a rotor, under any key, is that rotor's families; a rotor the
artifact does not name still gets its group made for it. The alias resolves
through the reference AS IT STANDS when `pyfs-matrix post` runs, so renaming or
extending an alias needs no re-run. **A group whose alias selects no surface of
any loads export of the simulation writes no table**: it is named under
`skipped` in `products.json` with the surfaces the export does carry, instead of writing a table of zeros.

Every list form is refused with the line to write instead:
`PUSHER = ["Blade1"]` becomes `PUSHER = "Blade1"`. Several members become
one alias declared in the reference, which the group names. For an empty list,
follow the collision check linked above before choosing `"all"`; if the name is
taken, declare a unique alias holding the intended members. Replace integer
positions with boundary names in the reference's alias.

**THE ONE NAME REFUSED** at `pyfs-matrix plan` is a name shaped like the
numbered suffix itself, `g01` and its kin: a file named after it could not be
told from the form it supersedes, and the rename of existing products needs
that difference. The refusal names the row, the artifact and the key. See [the named-group migration](migrating-to-0.23.0.md) for older numbered products (PFS-2032.03). An artifact whose groups are not
for polar tables says so with `products.polars = false` and is not checked.

The `[exports]` table decides the row's export set (FR-51): a workflow row
declares no `OUTPUTS` of its own any more, every export is named for the
point with the study's suffixes (`.fsm`, `.txt`, `.dat`, `_cp.txt`,
`_sloads.txt`, `_probes.txt`, `_plots.txt`, `_log.txt`), and a workflow row
that still carries `OUTPUTS` is refused naming this table. A
steady point also saves the solver's residual and load plots
(`_plot_residuals.txt`, `_plot_loads.txt`) and, where the artifact declares
sections, its section Cp plot (`_plot_cp_sections.txt`); each is switched off
with `false` (`plot_residuals`, `plot_loads`, `plot_sections_cp`). Unsteady
rows save residual/load plots once after the march, and 0.29.0 also supports
the final section Cp plot when section distributions exist. A missing declared
plot fails the point `FAILED_INCOMPLETE_OUTPUT` like any declared export. `force_distributions = true` opts a row of any run
type into `_force_distributions.txt`, the per-panel force distribution of every
surface, saved once at the end of the run. The loads table
and the saved simulation cannot be switched off: `loads = false` and `simulation = false` are refused naming the file. A setup artifact
that names one of these tables is refused pointing here: a setup carries
solver settings only (PFS-2029.16). The run record names the pproc id each
point was run for. The volume section's file (`_vsec.vtk` or `_vsec.dat`) is
not an `[exports]` kind: `[volume_section]` declares it, and `[exports]`
naming `volume_section_vtk` or `volume_section_tecplot` is refused.

The top-level key `singularity_strength` decides whether the
Tecplot surface carries the nodal `Singularity_strength`. The VTK the surface
is written from does not hold it, so carrying it costs a second, native Tecplot
export per point and per exported step (`<point>_native_tecplot.dat`). It is off
by default: the point exports the VTK alone, its `.dat` carries every VTK
variable and states `Singularity_strength` as not carried, and the point is
complete without the native file it was never asked to write.
`singularity_strength = true` exports the native file and carries the strength,
as 0.29.0 did for every surface. The value is a TOML boolean; `"true"` or `1` is
refused. `pyfs-matrix plan` says on each row that declares a Tecplot surface
whether its strength is carried. See
[surface translation](surface-translation.md).

<a id="a-volume-section-steady-rows"></a>

### A volume section

The pproc declares one flow-field plane. The workspace samples
it through probes or unsteady fluid plots, then post writes VTK or Tecplot
velocity point fields. It does not create native volume sections. For example:

```toml
[volume_section]
shape = "rectangle"                 # or "circle"
frame = "REFERENCE"                 # frame containing the plane
plane = "YZ"                        # XY, XZ or YZ of that frame
offset_m = 0.5                      # remaining positive frame axis, in meters
corners_m = [-1.0, -1.0, 1.0, 1.0]  # u0, v0, u1, v1 in the selected plane
points = [25, 25]                   # samples along each rectangular axis
refinement_layers = 1               # each extra layer bisects grid intervals
format = "vtk"                     # or "tecplot"
```

A circle states `radii_m = [r1, r2]` with `0 <= r1 < r2` and
`points = [radial, azimuthal]` instead of `corners_m`. Rectangle counts
must be at least two; a circle needs at least two radial and three azimuthal
samples. A zero-radius center occurs once. Shape-specific keys are refused on
the other shape. All authored lengths are meters in the declared frame; its
placement and any motion must be known before a derived REFERENCE field can
be written. Use a frame created by the reference or workflow, not a GUI name
whose placement the run did not record.

Steady rows retain the native probe sample; unsteady and rotor rows retain the
actual fluid-plot STEPs and write each as a separate field. The result is a
vertex cloud, not a volume mesh or a reconstruction of unsampled flow. Native
export conventions are build- and unit-specific; see [sampled fields](sampled-fields.md)
for the evidence and named refusals. Changing the plane after a run does not
invent samples at the new positions.

Product filenames, units, source and provenance are defined once in
[the volume-section definition](post-processing-definitions.md#a-volume-section).
That page also retains the native 0.27.x/0.28.x contract for historical records.
A saved FSM's existing native sections do not index the new probe grid. Direct
native/custom section commands remain available under their command evidence,
but callers must establish any indices inherited from the FSM themselves.

## What the products are

The meaning of a `[[probes]]` entry's `parameters` list depends on the run type;
see [Probe parameters](post-processing-definitions.md#probe-parameters) for the
definition and the steady-plan warning.

The `[products]` table names three kinds of CSV table, every one a header
line and one row per record, so a spreadsheet or a dataframe opens it with
nothing else; every table the post writes opens with `POL`, the
polar each row comes from. A POLAR table per group of `[groups]`, under `polars/` and
named by the same convention as the point's script with the swept
variable's field written `<code>+sweep`
(`polars/P0001-M150RE438AL+000BE+000J+sweep_PUSHER.csv` for a group named
`PUSHER`, and `..._g01.csv` for a group still keyed `"1"`; FR-85 and FR-88): one
row per point of the polar with the
reference block (`SREF`, `CREF`, `BREF`, the moment point), the advance
ratio of the row in `J` (`NA` where the run recorded none) and twenty-four
coefficients, `ALPHA`, `BETA`, `MACH`, `RE` (Reynolds in millions), the body
axes (`CDB`, `CYB`, `CLB`, `CRB25`, `CMB25`, `CNB25`), the stability axes
(`CDS` to `CNS25`), the wind axes (`CDW` to `CNW25`), and `CD0` and `CDI`,
every value at five decimals. A SECTIONS table per point,
`sections/<point>_sections.csv`: the solver `STEP` it was sampled at, WHICH
distribution each row belongs to (`FAMILY`, `PLANE`, `ROTOR`) and where blade
one of that rotor was (`AZIMUTH`), then the point's condition and the seven columns
of its sectional loads export, in the export's units; a run that defined no
distribution leaves an export declaring zero sections and gets no table. The
FLOW-FIELD SAMPLES of a point under `probes/`, whatever the run type was
(FR-87): `probes/<point>_plots.csv`, the unsteady plots export re-tabled
with its coefficient columns brought from the solver's reference
velocity to the free stream, and `probes/<point>_probes.csv`, the probe
table of a row of any kind. That table opens with `POL` and then the same six
columns whichever run type filled it (FR-91), `PROBE, X, Y, Z, FRAME, STEP`, and
then carries its own export's fluid quantities in their own names and
units: a steady row brings Mach, Cp, the velocity components and the
boundary-layer columns; an unsteady row brings the parameters its probe
entry asked for, one row per point and solver step. `STEP` carries `NA` on a
steady row, which has one step.

The `X`, `Y`, `Z` and `FRAME` columns are why this table exists. An
unsteady plots export numbers its probe columns, one per parameter the
row's own probe entry declares, `MACH7, VELOCITY7,
STATIC_PRESSURE_RATIO7` on a row asking for three, and it never says
where point 7 is, so its samples could not be placed at all. A steady
export does state its coordinates, and the frame it names is the
ANALYSIS frame rather than the one the probe entry laid its points out
in, so it could not be placed either without knowing the artifact.

The package records the vertex, the coordinates and the entry's frame
while it emits each point, writes them to
`sims/<sim>/profiles/<sim>_probe_points.csv`, and joins them here. That
file is the package's own record: it replaces only a file carrying its own
header, so a points file of your own that happened to carry the same name is
named in a refusal rather than replaced. When a run record names no such file, its `FRAME` cells read `NA` and its steady
coordinates still come from the export; the table is written either way.
`STEP` carries `NA` on a steady row, which has one step.

**THERE IS ONE TOKEN AND NO BLANK.** Every spine cell the
package cannot fill reads `NA`: the step of a steady row, and the position
or frame of a run that recorded none. See [the missing-value migration](migrating-to-0.23.0.md) for historical files using `-` or blank cells. A probe export this release cannot
read is a recorded skip naming the file and costs the simulation none of
its other products.

And the REDUCTIONS of the plots table, one file per applicable reduction
beside it (PFS-2015.04), over the window the row states;
[the reductions of an unsteady point](workflow-unsteady.md#the-reductions-of-an-unsteady-point)
walks them. The arithmetic behind the polar table is the
reference and was checked column by column against the tables the owning seat
recorded: FlightStream's `CL`, `CDi + CDo` and `Cy` are the stability-axis
coefficients, the body axes follow by turning them through the angle of
attack, the wind axes by turning the stability axes through the sideslip,
and the rolling and yawing moments are `CMx` and `CMz` scaled from the chord
to the span, with the reference sign.

The run writes these after collection, under `post/<matrix stem>/`, the
folder named after the matrix file (`post/matriz/` for `matriz.fs`), and
`products.json` beside them names every file with the run ids it derives
from and the pproc artifact; a campaign resumed with new points rewrites
them, since they derive from the manifest. A simulation whose product is
refused by design, one whose export was normalised by another reference
area than the products would state for one, is listed under
`skipped` in that file with the reason, and the others are written
(PFS-2031.16); the key is always there, empty when nothing was refused. A
windowed unsteady point also gets its per-step series under `series/`,
described with the export threshold below (the stamped files as a series). To rebuild them by hand, with no solver and no executable
configured:

```text
pyfs-matrix post matriz.fs --workspace .            # archives what is there, then writes
pyfs-matrix post --workspace .                      # every matrix the manifest names
pyfs-matrix post --workspace . --strict             # exit 3 if any product was skipped
pyfs-matrix post --workspace . --force-overwrite    # destroys instead, and asks first
```

**A REBUILD REFUSES NOTHING.** The first form MOVES whatever is
there into `archive/<day and hour>/` beside it and writes the new product in
its place, so nothing is lost and nothing is in your way. `--overwrite` is
gone: the flag that keeps no copy is `--force-overwrite`, it asks for a
confirmation, and a non-interactive session answers no. One stamp per rebuild,
so everything one rebuild replaced sits in one folder.

A skip is a success by default, since everything producible was produced;
`--strict` is for a wrapper that must tell a partial rebuild from a whole
one, and it changes the exit code alone, after every product is written.

### The super file in fixed-width text

`[products] superfile_format = "legacy_polar"` on the pproc artifact writes the
super file as fixed-width text, every field right-aligned in sixteen characters
and no commas, for a tool that splits on position. `csv` is the default and what
every existing workspace keeps. THE COLUMNS AND THE VALUES ARE THE SAME in both:
it is a second rendering of one table, never a second product. An unsteady simulation has no super file of
its own, its content rides in `P<sim>_<name>_uns_avg.csv`, so the key has nothing
to format there.

### Custom polar format

The existing tooling opens a fixed-width text polar file, not a
CSV, and `[products] custom_polar_format = true` on the pproc artifact
writes that file beside every polar table the stage writes, under the polar
table's own stem with the suffix `.dat`
(`P0001-M150AL+000BE+000J+sweep_g01.dat` beside `..._g01.csv`), the same rows
a second time (PFS-2014.01.01). Off by default. **The format carries the group
as a two-digit NUMBER on its fourth line.** A numbered group states its number;
a NAMED group states its position in the `[groups]` table, counted from one,
and the file's name carries the alias. In 0.23.0 a named group stopped the
products stage here. The shape, read off a recorded file and pinned by the committed
fixture `tests/tier1_offline/fixtures/custom_polar_format_sample.dat` (every
value in it synthetic), is nine header lines and then one line per point:

```text
FlightStream - STEADY_polar_AL_sweep_MACH_REmi_pins_from_the_setup
100110
Tue Sep 08 23:41:07  2026
007 01
      MNOM      SREF      CREF      BREF      XMOM      YMOM      ZMOM
       0.1       8.0       1.0       8.0      0.25       0.0       0.0
013
024
     ALPHA      BETA      MACH        RE       CDB       CYB       CLB  ...
  -2.00000   0.00000   0.10000   2.30000   0.00398   0.00000  -0.16424  ...
```

The title carries the row's description; line 2 is the polar and a
two-digit Mach code (`1001` at Mach 0.10 is `100110`);
line 3 the write time; `007 01` the number of reference columns and the
group; then the reference names and values, the row and column counts,
the twenty-four column names of the polar table in its order, and every
number at `%10.5f`. The docstring of
`pyflightstream.post.write_custom_polar_format` is the specification, line
by line, and `read_custom_polar_format` reads the file back (the retired prefix and key are refused); the tier-1 test
feeds the fixture's rows through the writer and requires the fixture's
bytes, and writes, reads and writes again what the stage produced,
requiring equal bytes (PFS-2014.01.02).

### A run's provenance, in an interchange format

Beside the tables, the stage writes one provenance document per recorded
run, every status, as W3C PROV in its PROV-JSON serialization
(PFS-2012.08.01): `post/<matrix stem>/provenance/<run id>.prov.json`, the
run id's separators replaced by underscores (`camp/sim_3207/a-02.0` is
`provenance/camp_sim_3207_a-02.0.prov.json`), and `products.json` names
each under `provenance` keyed by run id. The run record already carried
every fact; the document is the shape another tool reads without reading
this page. Its entities are every staged input, the script and every
collected output, each with its sha256 under `pyfs:sha256` (an output's
computed from the file when it is still there, `pyfs:sha256_from` says
`file` or `record`); its one activity is the solver run, with
`prov:startTime` and `prov:endTime` as the executor read its clock,
the wall time, the status and the executor's argv; its agents are the
package at its version and commit and the solver build at its executable
identity. The activity `used` the inputs and the script, every output
`wasGeneratedBy` it, and it `wasAssociatedWith` both agents:

```text
"activity": {
 "pyfs:run/camp/sim_3207/a-02.0": {
  "prov:type": "pyfs:SolverRun",
  "prov:startTime": "2026-09-08T21:41:07+00:00",
  "prov:endTime": "2026-09-08T21:41:19+00:00",
  "pyfs:status": "CONVERGED", "pyfs:wall_time_s": 12.5,
  "pyfs:executor": "LocalExecutor",
  "pyfs:argv": ["C:/builds/26120/FlightStream.exe", "-hidden", "-script", "run.fs"]
 }
}
```

The document is written with the standard library alone and read back in
the suite by a reader of a few lines that checks every relation names a
node the document declares; a PROV tool reads it as any PROV-JSON.

## Archiving a completed simulation

See [Archive and restore](restore-and-rebuild.md#archive-and-restore) for the workspace record definitions and recovery routes.

**To redo ONE point whose row was wrong, do not archive the simulation.**
`pyfs-matrix run --force-rerun <point>` archives that point's
record and its collected outputs and runs it again, keeping everything else
where it is; the section below is for retiring a whole simulation. Archiving
the simulation to redo one point takes the row's other points with it.

Every point of a row keeps its outputs in its OWN folder beneath the
simulation folder, and a point runs in that folder too (a
steady row of several points is one job and runs in the simulation folder).
A run refuses to collect onto a name already in that point's folder, or to
start a point whose declared output is already sitting in the folder it
runs in before the solver has written it, rather than attribute somebody
else's file to the new point.
Those refusals say to archive the simulation, and this is the command they
mean:

```text
pyfs-workspace archive . 8001        # sims/sim_8001/ becomes archive/sim_8001.zip
```

It zips the simulation's staged inputs, scripts and raw outputs into
one file under `archive/`, then removes the folder, so the row can be
re-run into a clean one while its evidence stays and the manifest keeps
its records. The products already under `post/` are untouched, and a
later `pyfs-matrix post` reads the exports from the simulation folder,
which is now in the zip: rebuild the products first, archive after.
