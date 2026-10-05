## What every product states

**The first column of every table is the polar, and no line precedes the
header**. Every table the post writes under `post/<matrix>/`,
the additional post's under `additional/<pid>/` included, and the campaign
sweep table beside them open with `POL`, named as the run matrix names its
polar column, holding in each row the POL of the point that row comes from
(`test_g16_every_table_the_post_writes_opens_with_the_polar_of_its_rows`). A
table whose rows mix polars, the campaign sweep, carries each row's own. What a
table states about all its rows is a column too, never a line before the
header: the rotor table's rotor is its `ROTOR` column, right after `POL`. `POL`
is the only column that states the polar: a steady polar table and its super
file written by 0.26.0 opened with it as `POLAR`, and no table the post writes
carries `POLAR` (`test_g16_every_table_the_post_writes_opens_with_the_polar_of_its_rows`).
Every other column keeps its name and its order after them. The solver's own
files under `datapoints/DP-<point>/` are never rewritten, and the fixed-width
custom polar (`.dat`) keeps the title lines its format specifies; a super file
written in the fixed-width `legacy_polar` format opens with `POL` too.

**No cell holds a comma or a double quote, and no cell is quoted**, so a reader that splits each line on `,`, as `numpy.genfromtxt` does,
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
[default warning policy](what-the-package-does-not-judge.md#the-post-log-and-the-default-warning-rule-since-0260).

The steady polar already carries `ALPHA`, `BETA`, `MACH` and `RE` among its
twenty-four, so it states the rest of the block beside them. The plots table
`probes/<point>_plots.csv` states NO condition, on purpose: after `POL` it is the
export's own header, and the reductions read every column after `POL` back as a
plotted quantity.

**The settings table opens with `POL` and the run id, and its other columns are codes.**
`settings/<matrix>_settings.csv` (FR-419) is the solver settings of every recorded point as one
numeric table, written by default and switched off by `[products] settings_codebook = false`. It
opens with `POL` and `RUN_ID`, the key of its row, and then holds the WIDE form of the
[settings codebook](../settings-codebook.md): `codebook_version`, `run_index`, and `f<id>_value` and
`f<id>_prov` for every flag, each a number or `NA`; the legend of the codes is the codebook beside
it, `settings/<matrix>_settings.codebook.json`. A point whose record holds no solver-setup snapshot
has no row, and `post.log` names it in one INFO line; it is not a recorded skip. With no snapshot
anywhere neither file is written. The table spans the whole matrix, so a post limited to some simulations
does not rebuild it. Both files are listed with kind `settings_codebook`.

---
