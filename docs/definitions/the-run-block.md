## The run block

<a id="the-run-block"></a>

Every csv the post writes opens with these columns, in this order, so a reader
holding one file can tell which polar, point and condition each row is of, and
two files of one point join on their first columns. A column that does not
apply to a row is `NA` ([the token for a value that does not
exist](the-token-for-a-value-that-does-not-exist.md)), never absent, so the
schema is the same for every run type. Reduction rows with their own windows
end the block at `WINDOW_REVS` and omit `WINDOW_PASSAGES`, as defined in
[the window of a reduction row](../post-processing-definitions.md#the-window-of-a-reduction-row).
Units and sources are stated once in
`products.json`, not in the csv.

A row is a steady value when `RUN_TYPE` is `steady` and a window average
otherwise.

The columns marked `<id>` are written once per rotor the reference declares,
id ascending, the consecutive `<id>` columns together for each rotor: `RPM0,
J0, MTIP0, MHEL0, RPM1, J1, MTIP1, MHEL1` and `D0, ADISC0, PITCH0, TOE0, D1,
...`. The rotor columns name the rotor by its id with no underscore. A
reference that declares no rotor writes none of them. `<IDENTIFIER>` stands
for one column per name of the row's `IDENTIFIERS` pairs, in the order
written, and for none when the row states none. A name the block already
writes (`POL`, `ALPHA`, `RPM0`) is refused by name, under `skipped` as
`run_block/<POL>#identifiers` and in a warning, and the block and every table
are written without it.

| Column | Unit | Source |
|---|---|---|
| <a id="pol"></a>`POL` | - | the matrix row's polar, as the matrix writes it |
| <a id="point-id"></a>`POINT_ID` | - | 1-based position of the point in its polar's sweep order |
| <a id="point"></a>`POINT` | - | the point name the per-point files carry |
| <a id="identifiers"></a>`<IDENTIFIER>` | as written | the row's `IDENTIFIERS: {NAME:value}` pairs, in the order written |
| <a id="run-type"></a>`RUN_TYPE` | - | `steady`, `unsteady`, `unsteady_rotor` or `qsteady_rotor`: the workflow selected for the row |
| <a id="alpha"></a>`ALPHA` | deg | the row's angle of attack as written |
| <a id="beta"></a>`BETA` | deg | the row's sideslip as written |
| <a id="mach"></a>`MACH` | - | the point's Mach number |
| <a id="re"></a>`RE` | - | the point's Reynolds number, in millions |
| <a id="vinf"></a>`VINF` | m/s | the free-stream speed of the point |
| <a id="vref"></a>`VREF` | m/s | the loads export's reference velocity |
| <a id="rpm-id"></a>`RPM<id>` | rev/min | the speed rotor `<id>` turned at, signed by its hand about its declared axis; `NA` on a row that turns no rotor |
| <a id="j-id"></a>`J<id>` | - | the advance ratio rotor `<id>` ran at, `VINF / (abs(n) D<id>)` with `n` in rev/s |
| <a id="mtip-id"></a>`MTIP<id>` | - | the tip Mach number of rotor `<id>` ([tip and helical Mach numbers](tip-and-helical-mach-numbers.md#tip-and-helical-mach-numbers)) |
| <a id="mhel-id"></a>`MHEL<id>` | - | the helical tip Mach number of rotor `<id>` |
| <a id="j"></a>`J` | - | the advance ratio the row requested; `NA` on a row that states RPM |
| <a id="j-clock"></a>`J_CLOCK` | - | the advance ratio the clock rotor ran at (below) |
| <a id="rpm-clock"></a>`RPM_CLOCK` | rev/min | the clock rotor's speed, with its hand (below) |
| <a id="thrust"></a>`THRUST` | N | the thrust condition the row states (`ACTUATOR_THRUST` of an actuator disc row); `NA` otherwise |
| <a id="alt"></a>`ALT` | m | the altitude of the resolved atmosphere |
| <a id="rho"></a>`RHO` | kg/m^3 | the density of the point |
| <a id="temp"></a>`TEMP` | K | the temperature of the point |
| <a id="mu"></a>`MU` | Pa s | the dynamic viscosity, written in scientific notation as text |
| <a id="sref"></a>`SREF` | m^2 | the reference area |
| <a id="cref"></a>`CREF` | m | the reference chord |
| <a id="bref"></a>`BREF` | m | the reference span |
| <a id="xmom"></a>`XMOM` | m | the moment reference point's x, in the mesh frame |
| <a id="ymom"></a>`YMOM` | m | the moment reference point's y, in the mesh frame |
| <a id="zmom"></a>`ZMOM` | m | the moment reference point's z, in the mesh frame |
| <a id="d-id"></a>`D<id>` | m | the diameter of rotor `<id>` (`diameter_m` of its block) |
| <a id="adisc-id"></a>`ADISC<id>` | m^2 | the disc area of rotor `<id>`, `pi D^2 / 4` |
| <a id="pitch-id"></a>`PITCH<id>` | deg | the pitch of the frame `R<id>` ([the rotor frame](axes-and-signs.md#the-rotor-frame)) |
| <a id="toe-id"></a>`TOE<id>` | deg | the toe of the frame `R<id>` |
| <a id="first-step"></a>`FIRST_STEP` | - | the first step of the averaging window actually used, 1-based; `NA` on a steady row |
| <a id="last-step"></a>`LAST_STEP` | - | the last step of that window, inclusive; `NA` on a steady row |
| <a id="steps"></a>`STEPS` | - | the steps in that window; `NA` on a steady row |
| <a id="window-revs"></a>`WINDOW_REVS` | - | the clock rotor revolutions the window spans; `NA` on a steady row or a row without a clock |
| <a id="window-passages"></a>`WINDOW_PASSAGES` | - | the clock rotor blade passages the window spans; `NA` on a steady row or a row without a clock |

`DESCRIPTION` is not a column: a polar's description is in `products.json`.

<a id="the-clock-rotor"></a>

### `J_CLOCK` and `RPM_CLOCK`, the clock rotor

On an unsteady row with no turning rotor, the optional `J_CLOCK` input supplies
a notional reference clock: `n = V / (J_CLOCK * D)` in rev/s and
`DELTA_TIME = (DELTA_THETA / 360) * J_CLOCK * D / V`.
D is always the row reference's top-level `rotor_diameter_m`, never a rotor
block's `diameter_m` and never selected by `CLOCK_MOTION`; a reference without
`rotor_diameter_m` is refused by name.
`REVOLUTIONS` counts these reference revolutions. `RPM_CLOCK` reports `60 * n`
and the output `J_CLOCK` is the ratio that speed implies against the point's
free stream and this same reference diameter. The notional clock turns no mesh
or rotor frame. Its recorded speed and diameter also define revolution windows.

A row may turn several rotors, each with its own speed and advance ratio; the
per-rotor columns `RPM<id>` and `J<id>` state them all. The **clock rotor** is
the one whose revolutions count the row's time: the rotor `CLOCK_MOTION`
names, or the only rotor the row turns. `RPM_CLOCK` is that rotor's speed in
rev/min, signed by its hand about its declared axis, as the run record kept
it. `J_CLOCK` is the advance ratio that speed implies against the point's own
free stream and the rotor's diameter, `J_CLOCK = VINF / (|n| D)` with `n` in
rev/s; the magnitude of the speed enters, because the hand is the rotor's and
`RPM_CLOCK` carries it.

Both are what the run measured, beside `J`, which is what the row requested:
a row stating `RPM` and sweeping alpha writes `NA` in `J` and the ratio it ran
at in `J_CLOCK`. Either is `NA` where the record does not state the speed, the
reference does not state the diameter, or the row turns several rotors and
names no clock. `WINDOW_REVS` and `WINDOW_PASSAGES` count the clock rotor's
revolutions and blade passages over the averaging window.
For a reduction row with its own window, the row's own average supplies
`WINDOW_REVS`; the point window is never substituted.

<a id="tecplot-and-vtk"></a>

### In a Tecplot or VTK file

A Tecplot file carries the block as one `DATASETAUXDATA <COLUMN>="<value>"`
record per column, in the order above, before the first zone. A legacy VTK
file carries it as one `FIELD FieldData` block on the dataset, one array per
column.
