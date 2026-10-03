# One row, one actuator disc or one custom free stream

The row keys that replace the uniform free stream: an actuator disc and a custom free stream imported from a file.

## One row, one actuator disc

A row may carry an actuator disc, the solver's linearized
propeller slipstream (FR-109). The disc's GEOMETRY belongs to the
configuration, so it is a block of the row's reference, beside the rotors and
the frames; its LOADING belongs to the condition, so the row states it:

```toml
[[frames]]
name = "HUB"
origin = [1.0, 0.0, 0.0]

[PROP]
kind = "actuator"
frame = "HUB"          # the frame the disc's axis belongs to
axis = "X"             # X, Y or Z of that frame
offset_m = 0.0         # along the axis, from the frame's origin
tip_radius_m = 0.5
hub_radius_m = 0.1     # 0 <= hub < tip
rpm_sign = 1           # +1 the right-hand rule about axis, swirling as a rotor of +1 turns
blades = 3             # needed by a row stating PROFILE
swirl = 0.8            # optional: the fraction of the swirl velocity kept downstream
profile_units = "NEWTONS"   # the force unit a profile file is written in
```

```text
ACTUATOR: PROP / ACTUATOR_RPM: 2400 / ACTUATOR_THRUST: 120
ACTUATOR: PROP / ACTUATOR_RPM: 2400 / PROFILE: prop_ct
```

`ACTUATOR` names the block; `ACTUATOR_RPM` is the speed in rev/min, a
magnitude whose hand is the block's `rpm_sign`; and the row states exactly one
loading: `ACTUATOR_THRUST`, the net thrust in N (the ELLIPTICAL model, thrust
given in NEWTONS as the manual recommends), or `PROFILE`, the stem of a file of
the workspace's `inputs/profiles/` (the CUSTOM model). ONE DISC PER ROW. A
reference declaring a disc changes nothing on a row that names none.

**THE PROFILE FILE** holds the radial distribution, one station per line: two
numbers separated by one comma, `r,F`, the radial station (normalised or
dimensional, as you write it; the package does not convert it) and the force
there, per blade, in the block's `profile_units`. No header line and no count
line:

```text
0.2,0.0
0.6,127.3
1.0,0.0
```

`pyfs-workspace profile` writes this file for you, from a POL's
written sections or as the uniform or the Betz-Prandtl shape, scaled to a
thrust or a CT, as `inputs/profiles/<stem>.csv` with its provenance record:
see [actuator-disc profiles](actuator-profiles.md).

Save it as any editor saves it. The solver is never handed your file: the run
writes its own copy, `<stem>.actuator_profile.txt`, in the folder the point
runs in (a steady row of several points: its simulation folder), and the
script names the copy. The copy holds your rows with the blank lines and the
spaces around the numbers removed, joined by a newline, and NO final newline,
because 26.124 reads every line of the file as a point: measured on 26.124
(RPT-070), eleven rows ending in a newline were read as twelve points, logged
as unreadable and refused in a dialog that holds the solver until a person
closes it, while the same eleven rows without the final newline were read,
radii and forces. The copy's sha256 joins the record's `inputs_sha256`, and
your file is never written. A `PROFILE` is resolved when the row is planned,
and a stem the folder does not hold is refused naming what it does hold. A
file the solver would misread is refused then too, naming the file and the
line: a header or a count first (each read as one point more, which set every
value to zero), a row that is not two numbers separated by one comma, a number
that is not finite, or fewer than two rows. A case written in Python sets
`SimCase.actuator_profile` to the file's absolute path and is held to the same
form when its script is built.

The script creates the disc after every frame exists and before the solver is
initialised: `CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL|CUSTOM <name>`,
`SET_ACTUATOR_AXIS`, `SET_ACTUATOR_RADIUS`, `SET_PROP_ACTUATOR_RPM`, then
`SET_PROP_ACTUATOR_THRUST` or `SET_PROP_ACTUATOR_PROFILE` (the run's copy of the
profile on the next line), `SET_PROP_ACTUATOR_SWIRL` when the block states a swirl, and
`ENABLE_ACTUATOR`. Each way to get the row wrong is refused before a line is
written, naming the key: a block the reference does not declare (listing the
ones it does), a speed missing or not above zero, both loadings or neither, a
`PROFILE` on a block stating no `blades`, a loading key without `ACTUATOR`, and
a frame the run did not create. The block itself is refused when its name is
not one word, when it shares its name with a rotor, an alias or a frame, and
when it forgets `kind = "actuator"`.

**A SAVED SIMULATION THAT ALREADY CARRIES AN ACTUATOR IS REFUSED**, naming the
actuators it carries. `CREATE_NEW_ACTUATOR` appends to the actuators the opened
file holds, and every command after it cites the disc by that index, so on
such a file the row's axis, radius, speed and loading would configure the
saved actuator; numbering the new disc after it would leave two discs where the
row states one. Open a simulation saved without an actuator, or name no
`ACTUATOR` on the row and the saved one stays as it was saved. The package
reads the file's actuators from its physics block, walked by the block's own
counts on the shape every save read so far holds (the two carrying a disc are
the 26.124 saves of the tier-3 disc rows, one actuator each), and a block out of
that shape is refused as unreadable rather than taken to hold none. A point's
final save carries the disc its row created, so it is not a geometry for
another disc row. A raw mesh is imported into a new simulation and carries
none.

**THE METRES ARE WRITTEN IN THE SIMULATION'S LENGTH UNIT.** `SET_ACTUATOR_AXIS`
and `SET_ACTUATOR_RADIUS` carry no unit, and the solver reads their lengths in
the simulation's unit, so the script converts `offset_m`, `tip_radius_m` and
`hub_radius_m` (and a volume section's lengths the same way) into:

* the unit the script set itself after the open: the metres a raw mesh is set
  to after its import, or a unit a setup line states, as the row's
  `RAW: {COMMAND: SET_SIMULATION_LENGTH_UNITS MILLIMETER / BEFORE: setup}`
  does, which turns a 0.5 m radius into `500.0`;
* on a saved simulation the script set no unit on, the unit the file was saved
  in. The package reads it from the head of the file's global block, and it
  reads one head only: the one every save read so far carries, the saves known
  to be in metres among them, which it takes as metres. A file opening
  otherwise is refused at `pyfs-matrix plan`, naming the keys, because
  whether a save in another unit writes another head has not been measured.
  Stating the unit the file was saved in with that setup line makes it known,
  and the lengths are converted into it.

A case that opens nothing, or a placeholder file with no global block, has no
unit to read, and its lengths are written as stated.

WHAT HAS RUN WHERE, from the command database. `CREATE_NEW_ACTUATOR` is
verified on 26.100 and 26.120 to 26.124; `SET_ACTUATOR_AXIS`,
`SET_ACTUATOR_RADIUS`, `SET_PROP_ACTUATOR_RPM` and `SET_PROP_ACTUATOR_SWIRL`
are verified on 26.121 to 26.124, each by a probe reading the saved simulation.
`SET_PROP_ACTUATOR_THRUST` and `ENABLE_ACTUATOR` ran without abort or logged
error in the probes of 26.120 to 26.124, and their effect has never been
observed, so they are documented only: a run can converge with the disc's
thrust not applied and nothing here would say so. `SET_PROP_ACTUATOR_PROFILE`
ran on 26.124 under a licensed probe (RPT-070), which measured the file form
above by reading the saved simulation, with no solve; it stays documented
there, since what a profile the solver read does to the loads has not been
observed, and every other build of the range is documented only. The profile
route is refused on 25.000 and 25.100, whose editions print the command without
a blade count.

A PROFILE THE SOLVER COULD NOT USE FAILS THE POINT. When the solver cannot use
the file, it logs `Failed to find`, `Failed to read`, `No data found in` or
`Failed to load custom radial thrust profile file: <path>` and runs on to the
end with the disc acting on a loading that is not the file's: the loads
converge and nothing else in the outputs says so. A point whose solver log
carries one of those lines is recorded `FAILED_SCRIPT` whichever assessor
judged it, on a local run and at `pyfs-matrix collect`, and its `error` quotes
the line and names the file. The line is read from the solver log, so a row
whose outputs name no log is not held to it.

NOT MEASURED: the disc on an unsteady row; the disc on a rotor row, where a
flat row with no blade frames turns every frame with its motion
(`SET_MOTION_MOVING_FRAMES 1 -1`), the disc's frame included; the disc under
mirror symmetry; the loads of a disc whose profile the solver read; and the
profile file on any build but 26.124. A continuation reopens the saved
simulation, which carries the disc, and emits it again nowhere; a disc added
to a row after its run stopped does not reach the continuation and is not yet
refused there. A row may state `ADVANCE_RATIO` (G20) instead of
`ACTUATOR_RPM`, and the disc turns at n = V / (J D) with its own diameter (twice
its `tip_radius_m`); a steady row that sweeps the advance ratio runs one job per
point, so each point sets its own speed. A row stating neither is refused
naming both.

### What the disc was measured to do on 26.124

A research study of the disc on 26.124 (build 8172026), summarised in
[RPT-137](https://github.com/nevesgeovana/pyflightstream/blob/main/reports/RPT-137_actuator-disc-measured-behaviour-on-26124_2026-10-01.md),
measured four things a reader would not assume. They are stated here with the
case they were measured on; on another build they are unmeasured.

**THE HAND.** A disc whose block states `rpm_sign = 1` swirls its
wake the way a rotor of `rpm_sign = 1` turns (FR-331): `+1` is a positive
rotation about the block's `axis` by the right-hand rule, as for a rotor block.
The script hands `SET_PROP_ACTUATOR_RPM` minus the block's sign times the
row's speed, because a disc handed plus swirled against a rotor of the same
`rpm_sign` on 26.124 and a disc handed minus swirled with it (RPT-137). The
[migration record](migrating-to-0.34.0.md#an-actuator-disc-swirls-the-way-its-rotor-turns)
explains how to update a study that used the older sign convention.

**THE SWIRL IS ONE GLOBAL FACTOR.** The block's `swirl` is one global factor,
0 to 1, applied to the swirl the solver computes for the disc from its thrust
and speed; it is not a radial distribution. `SET_PROP_ACTUATOR_SWIRL` takes one
number and no command imposes a swirl profile, so a disc cannot be given the
radial swirl of a bladed rotor (RPT-137).

**ELLIPTICAL PLACED 0.62 OF THE THRUST ASKED IN THE WAKE.** On the one case
RPT-137 summarises (26.124), a disc loaded by `ACTUATOR_THRUST` (the ELLIPTICAL
model) carried 0.62 of the thrust asked as axial momentum flux four radii
downstream, at the thrust asked and at twice it alike, where the CUSTOM
profiles carried 0.95 to 1.04 of it. This is a measured value, not a
guaranteed one: the solver's elliptical definition is not readable from the
manual, and a study that needs the thrust in the wake loads the disc by a
profile.

**RELAXED IGNORED A CUSTOM PROFILE.** On the same case (RPT-137), a disc whose
block states `wake_type = "RELAXED"` gave the same wake for every loading
profile and for the ELLIPTICAL model, and carried about half of the thrust
asked as axial momentum flux four radii downstream. This is a measured value,
not a guaranteed one. The plan warns on a row whose RELAXED disc names a
`PROFILE`, naming the row, the disc and RPT-137, and never refuses it (FR-332);
a RIGID disc reads the profile.

## One row, one custom free stream

A row may replace the uniform free stream with a velocity field
read from a file (G15), the GUI's custom free stream, imported under the free
stream's profile. The field varies within the YZ plane of the GLOBAL frame,
which is how the solver reads it. The row names the file by its stem:

```text
FREESTREAM: shear
```

`FREESTREAM` names a file of the workspace's `inputs/freestreams/`, a folder
`pyfs-workspace init` creates, and the extension is the form, as the solver's
manual ties them:

- `shear.txt` is the STRUCTURED form: a first line `Npts Mpts`, two positive
  integers, then Npts x Mpts rows `x y z vx vy vz`, the rows of the first
  index outer and those of the second inner;
- `shear.dat` is the UNSTRUCTURED form: one row `x y z vx vy vz` per vertex,
  and no header.

```text
3 3
0.0 -8.0 -4.0 20.0 0.0 0.0
0.0 -8.0  0.0 30.0 0.0 0.0
0.0 -8.0  4.0 40.0 0.0 0.0
0.0  0.0 -4.0 20.0 0.0 0.0
0.0  0.0  0.0 30.0 0.0 0.0
0.0  0.0  4.0 40.0 0.0 0.0
0.0  8.0 -4.0 20.0 0.0 0.0
0.0  8.0  0.0 30.0 0.0 0.0
0.0  8.0  4.0 40.0 0.0 0.0
```

That file is a field of 30 m/s along x at z = 0, sheared by 2.5 m/s per metre
of z, over 16 m of span and 8 m of height. THE FILE IS IN METRES AND METRES PER
SECOND, IN THE GLOBAL FRAME, as the simulation is: nothing is converted, and
the rows are written to the solver as they are, which is how 26.124 reads them
(the licensed probe T14, RPT-071, below).

THE FIELD IS THE FLOW'S DIRECTION. On 26.124 `SOLVER_SET_AOA` does not turn a
custom field (T14), so a row stating one states `ALPHA` and `BETA` as 0, or
neither, and writes the incidence it wants into the field's `vy` and `vz`
components. A non-zero angle of attack or sideslip beside the key, fixed or
swept, is refused at plan, a sweep at every point, the one at zero too
(`test_g15_a_field_beside_an_angle_of_attack_or_a_sideslip_is_refused`,
`test_g15_a_field_beside_an_angle_in_the_flight_condition_blocks_every_point_at_plan`):
run, such a row would solve near zero incidence and report the angle it names.
The sideslip was not measured; it is the same mechanism and is refused for the
same reason.

The script writes `SET_FREESTREAM CUSTOM STRUCTURED`, or `UNSTRUCTURED`, and
the file's absolute path on the next line, in place of
`SET_FREESTREAM CONSTANT`, on every run type and once for a whole steady sweep
(`test_g15_a_row_naming_a_freestream_writes_custom_in_place_of_constant`,
`test_g15_a_dat_file_is_the_unstructured_form`,
`test_g15_a_steady_sweep_writes_its_field_once_with_the_setup`). Nothing else
of the script moves, so the row's `FLIGHT_CONDITION` still writes
`SOLVER_SET_AOA 0.0`, `SOLVER_SET_SIDESLIP 0.0` and `SOLVER_SET_VELOCITY`
(`test_g15_the_script_differs_from_its_control_in_the_free_stream_lines_alone`).
The file is resolved when the row is planned, to the absolute path the script
names; it is read where it lives, never copied beside the mesh, and its sha256
joins the record's `inputs_sha256`
(`test_g15_a_row_resolves_inputs_freestreams_at_plan_and_the_record_hashes_it`).
A case written in Python states the file's absolute path in
`SimCase.freestream_profile` (`test_g15_a_case_built_in_python_states_the_file_alone`).

The file is read against its form when each point is built, which the plan
does, so a file not in it is refused before any seat, naming the file, the
line and what the form asks: a header that is not two positive integers, a row
count other than Npts x Mpts, a row that is not six finite numbers, rows whose
x differ (the field lies in one YZ plane, so every row states the x of that
plane) and rows stating a single y or a single z
(`test_g15_a_file_not_in_the_manuals_form_is_refused_naming_the_file_and_the_line`,
`test_g15_a_file_not_in_the_form_blocks_the_point_at_plan`). A blank line is
read past. Refused at plan as well: a stem the folder does not hold, naming
what it holds, and a stem written with its extension; a stem the folder holds
as both a `.txt` and a `.dat`; the key on a `LEGACY` row, whose recipe writes
its own free stream; and the key beside a non-zero or swept body rate, since a
rate writes `SET_FREESTREAM ROTATION` and a run has one `SET_FREESTREAM`
(`test_g15_a_stem_the_folder_does_not_hold_is_refused_at_plan_naming_what_it_holds`,
`test_g15_a_stem_carried_by_both_forms_is_refused_at_plan_naming_the_folder`,
`test_g15_the_key_on_a_legacy_row_is_refused_at_plan`,
`test_g15_a_field_beside_a_body_rate_is_refused`). A rate written as 0 is
straight flight and sits beside it.

WHAT HAS RUN WHERE. `SET_FREESTREAM` is documented on every build, and its
CUSTOM STRUCTURED form ran on 26.124 under the licensed probe T14 (RPT-071),
steady rows of `tests/tier3_licensed/matriz_gui.fs` on the 12_WING_PHY wing at
30 m/s, five far-field layers (the loads table prints four decimals):

| row | free stream | angle of attack | CL | CDi | CDo |
|---|---|---|---|---|---|
| 5013 | CONSTANT | 0 deg | 0.0023 | 0.0000 | 0.0066 |
| 5012 | the uniform field, vx = 30 m/s | 0 deg | 0.0023 | 0.0000 | 0.0066 |
| 5014 | the field sheared in z, vx = 30 + 2.5 z m/s | 0 deg | 0.0045 | 0.0000 | 0.0066 |
| 5010 | CONSTANT | 4 deg | 0.3385 | 0.0049 | 0.0071 |
| 5011 | the uniform field, vx = 30 m/s | 4 deg | 0.0021 | 0.0002 | 0.0065 |

The uniform field loads as the constant free stream it equals, to the digits
printed, with both divided by the same stated reference velocity, so the field's
speed is read in m/s (the grid's coordinates, which a uniform field cannot
show, were not probed on their own); the sheared field moves the lift; and at
4 deg, the one angle run, the field loads near its own 0 deg self and far from
the constant free stream at 4 deg, although the angle still moves the result a
little (CL 0.0021 against 0.0023, CDi 0.0002 against 0.0000). That is the
refusal above.
Row 5011 is retired from the matrix, since the plan refuses it now; its run is
the report's evidence. `tests/tier3_licensed/test_freestream.py` holds 5012 to
5014 to what they measured. Every other build is documented only, and the
ROTATION form ran on 26.124 under RPT-052.

The rest of the field (G18) was run on 26.124 under the
licensed probe T16 (RPT-077), each variant against a control of the same
batch:

- **The UNSTRUCTURED form runs**: the uniform rows as a `.dat` load as the
  STRUCTURED file and the constant free stream do.
- **The grid should cover the body.** Beyond its grid the solver neither
  extends a field linearly nor holds its edge station; what it applies there is
  closest to the constant free stream the script states. So the part of a body
  outside the grid is not loaded by the field, and THE PLAN WARNS, naming the
  field's y and z extent and the body's
  (`test_g18_a_field_that_does_not_cover_the_body_is_warned_at_plan`). It warns
  rather than refuses, because a field meant as a local gust may cover only part
  of the body on purpose. The body is read from a saved simulation's mesh or an
  OBJ, in its `[import]` unit converted to metres as `IMPORT` converts it
  (RPT-069); an STL is not read, and then nothing is said. A row that MOVES the body (ROTATE, TRANSLATE, rotor MOTIONS
  or an import operation) is told the coverage was not checked, and why, because
  the body's file does not say where the row places it
  (`test_g18_a_row_that_moves_the_body_is_told_its_coverage_was_not_checked`).
- **Incidence written into the field loads the body as that incidence**: a
  field of 30 m/s tilted 4 deg in z, at `ALPHA: 0`, gives the body forces of the
  constant free stream at 4 deg (Cz 0.3381 against 0.3378, Cx -0.0124 against
  -0.0116, CMy -0.0858 in both). **The loads export prints CL and CDi in the axes
  of the angle the row states**, zero, not of the flow: that row prints CL 0.3382
  and CDi -0.0195, the 4 deg lift and drag turned onto the 0 deg axes. Read the
  body forces Cx, Cy and Cz of such a row, or turn CL and CDi by the field's
  incidence.
- **A saved simulation carries its custom field**: reopened with no
  `SET_FREESTREAM` line, the sheared field's saved file solves the sheared
  field. The package writes `SET_FREESTREAM` on every row it builds from a mesh
  or a saved file, and that line overrides the field the file carries, so a
  CONSTANT row opening such a file solves the constant free stream. A
  continuation (`RESTART`) reopens the saved simulation and writes no free
  stream, so it continues the field the stopped run read, as measured; it
  continues only a run whose record hashes the same field under the file's name:
  a stopped run that read no field, or the file with other bytes, is refused at
  plan and at run, and the angle is judged beside the field as on a run from the
  mesh.

NOT MEASURED: the unit of the grid's coordinates; angles other than 4 deg over
a uniform field (and the small residue that angle leaves); the sideslip beside
a field; a custom field on an unsteady or a rotor row; the solver's rule beyond
the grid to the digit. A field whose file name is the name of a file the run
writes for the solver, the trailing-edge node file or the disc's profile copy,
is refused before the solver starts, because the record keys each input by its
name.
