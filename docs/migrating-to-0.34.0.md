# Migrating to 0.34.0

Keep a copy of the workspace and install the release in a separate Python
environment before running existing matrices. Planning and post-processing can
check most changes without starting FlightStream. The package's dependencies
and extras are the ones [0.33.0](migrating-to-0.33.0.md) declared, and 0.33.1
changed nothing a reader acts on beyond the extras it named.

Three changes can alter a result or a byte you already have, and the page
puts them first, in the order of their reach: every text file the package
writes now ends its lines with LF, an actuator disc with `rpm_sign = 1` now
swirls its wake the way a rotor of `rpm_sign = 1` turns, and a rotor row that
states no wake termination now keeps four rotor radii of wake. The sections
after them are the renamed guides, the code that moved without moving a public
path, the new thin-blade command, the run selection and the message of a second
run, a fixed family of five switches, a registered solver build, an
actuator-disc profile command, and the face count of a mesh in the inventory
and in the last column of two products.

## Every text file has LF line ends

From 0.34.0 every text file the package writes ends its lines with LF on every
platform (NFR-32): the products, `products.json`, the post log and its JSON,
the run records, the plans, the logs, the emitted solver scripts and the files
the solver reads, and the counter and clock programs the solver runs. Up to
0.33.1 a file written on Windows ended its lines with CRLF wherever the writer
stated no line end, and with LF on Linux, so the same campaign wrote different
bytes on the two. There is no switch that restores CRLF.

What a reader must allow:

- A reader that split lines on CRLF now reads LF. Split with
  `str.splitlines()` or open the file in text mode, which reads either.
- A byte-exact comparison against a file 0.33.1 wrote on Windows removes the CR
  before each LF first; the only difference between the two files is those
  bytes, except for the two programs below.
- A digest of a file written by 0.33.1 on Windows differs from the digest of
  the same file written by 0.34.0, for that reason alone. The embedded counter
  and clock solver programs now state the LF line end in their own text, so
  their text and their recorded sha256 change as well.
- The products snapshot of the release judges line ends on both platforms.

Every write goes through one private module, `pyflightstream._textio`, and a
tier-1 guard refuses a text write outside it. The receipt script
`scripts/lf_products_check.py` posts the recorded campaigns and counts the
files holding a CR byte, and RPT-140 is the census of the writers that gave
CRLF on 0.33.1. None of them is a setting.

## An actuator disc swirls the way its rotor turns

An actuator disc whose reference block states `rpm_sign = 1` now swirls its
wake the way a rotor of `rpm_sign = 1` turns (FR-331), as the block's
docstring always said. The script hands `SET_PROP_ACTUATOR_RPM` minus the
block's sign times the row's speed, where 0.33.0 handed plus: on 26.124 a disc
handed plus turns against the rotor of the same sign, the sense summarised in
RPT-137. Every emitted `SET_PROP_ACTUATOR_RPM` line therefore carries the
opposite sign of the line 0.33.0 wrote for the same row, and nothing else in
the script changes; `scripts/check_parity.py` names the difference under
FR-331.

What a script of yours must allow:

- A study that set `rpm_sign = -1` on a disc to make it swirl with its rotor
  sets `rpm_sign = 1` from 0.34.0, the rotor's own hand.
- A study that kept `rpm_sign = 1` and read its disc wake as the rotor's now
  gets the swirl the rotor gives.
- A disc result recorded by 0.33.0 or earlier keeps the sense it was run with:
  its run record holds the script it ran.
- The sense is measured on 26.124 only; on another build the same rule is
  applied and unmeasured.

`pyfs-matrix plan` also warns, and never refuses, on a row whose disc has
`wake_type = "RELAXED"` and names a loading `PROFILE`, naming the row, the disc
and RPT-137: on 26.124 a RELAXED disc ignored a custom profile and carried
about half of the thrust asked. The plan's statuses and the file it writes are
what they would be without the warning (FR-332).

## A rotor row keeps four radii of wake unless it says otherwise

From 0.34.0 the script of an `unsteady_rotor` row whose setup and row state
none of `wake_termination_length`, `wake_termination_steps` and
`wake_termination_revolutions` carries one `SET_WAKE_TERMINATION_TIME_STEPS`
line: the default length L = 4 rotor radii, converted into steps from the
free-stream speed, the rotor speed and the step angle (FR-321). 0.33.0 wrote no
termination there, and the solver kept the whole wake. The default is a
recommendation, kept for its computational cost, and it is permanent: a row
that wants the 0.33.0 script states its termination. `scripts/check_parity.py`
names the changed line under FR-321, and only rotor rows that state no
termination differ.

The conversion is `n = ceil(L R Omega / (V_ax dtheta))`, with R half the
largest diameter of the rotors the row turns (the rotor block's `diameter_m`,
else the reference's `rotor_diameter_m`), Omega the rotor speed, dtheta the
step angle and
V_ax the axial convection speed of the wake; rounding is upward, so the wake
kept is never shorter than L. The run record of the point names the L asked,
the V_ax used with the rule that gave it (`free_stream`, `induced_velocity` or
`revolution_cap`) and the steps emitted, and the plan states the same values
for each rotor point. Which speed V_ax should be in forward flight is settled
by the licensed long-wake run reported in RPT-130; read it before relying on
the default for a study whose wake length matters.

What a matrix must allow:

- One key states the termination. A row that states two of the three keys,
  from its setup, its preset or its `VAR_NAMES_VALUES` cell, in any
  combination, is refused at plan naming each key, its value and where it comes
  from (FR-322). The refusal of 0.33.0 for a preset stating revolutions beside
  steps is this rule now.
- A rotor row at zero free-stream speed that states no termination is refused
  at plan until it states `wake_termination_thrust_n`, which convects the
  length at the momentum-theory induced velocity where that exceeds the
  free-stream speed, or `wake_termination_revolutions_cap`, which bounds the
  converted steps (FR-323). The two keys bound a length only and are refused
  beside a step or revolution count.
- The setup key `wake_termination_x_m` places the solver's wake end plane: the
  `WAKE_TERMINATION_X` argument of `INITIALIZE_SOLVER`, `DEFAULT` or an X in
  metres in the simulation's frame. A setup that does not state it writes
  `DEFAULT`, as 0.33.0 did; a number with a unit, a distance in radii, a
  non-finite number, an empty value and any other word are refused (FR-324).
- The plan warns, and never refuses, on every rotor point whose wake may not
  reach its length: too few revolutions for the length, a step or revolution
  count that keeps less than four radii, a stated end plane before the length,
  and the solver's `DEFAULT` plane, whose position the plan cannot know (FR-325).
  The same holds for a blades-only wheel.

No golden render and no tier-3 matrix of the package is refused by the hover
rule: the parity run of `v0.33.1` against the integrated tree renders all 194
scripts. The plan file `plan.json` gains one key per point, `wake_termination`,
with the three recorded values for a rotor point and empty for any other. A
result recorded by 0.33.0 or earlier keeps the script it ran in its run
record.

## The guides are renumbered

The PDF guides are numbered from 01 and the cheatsheet is guide 04 (FR-329).
No old name resolves, so a link, a bookmark or a script that names a guide by
its file name is updated by this map, each guide with the number it had in
0.33 (the file names were `pyfts-guide-<number>-<name>.pdf`, the name being
the one of the right column):

| Number in 0.33 | From 0.34.0 |
| --- | --- |
| 00 | `pyfts-guide-01-fts-overview.pdf` (overview) |
| 01 | `pyfts-guide-02-workspaces.pdf` (workspaces) |
| 02 | `pyfts-guide-03-gui-to-pyfs.pdf` (GUI to pyfs) |
| none, `pyfts-cheatsheet-pyfs-matrix.pdf` | `pyfts-guide-04-cheatsheet.pdf` (cheatsheet, new as a numbered guide) |
| 03 | `pyfts-guide-05-references.pdf` (references) |
| 04 | `pyfts-guide-06-solver-setup.pdf` (solver setup) |
| 05 | `pyfts-guide-07-pproc-definitions.pdf` (post-processing definitions) |
| 06 | `pyfts-guide-08-fsi.pdf` (FSI) |
| 07 | `pyfts-guide-09-python-environment-offline.pdf` (Python environment for offline machines) |

The cheatsheet is now one document of ten pages (FR-328): page 1 holds every
subcommand and option of `pyfs-matrix`, page 2 every other console tool, and
pages 3 to 10 the eight stages of the campaign workflow, one page each. The
two cheatsheet PDFs of the development branch are one. The list of guides is on
[the guides page](guides.md).

## Code moved, and no public path did

Four modules were cut again in 0.34.0, under the architecture guards of 0.33.0
(AD-16, AD-17 and AD-18), and the rule of 0.33.0 holds: every public name keeps
its dotted path, every console command and option keeps its spelling and help
text, and no emitted script or product byte changes because of the cut.

- The models of `pyflightstream.cases` live in six public modules,
  `cases.pproc`, `cases.reference_blocks`, `cases.settings`, `cases.mesh`,
  `cases.naming` and `cases.selection`. Every name keeps its
  `pyflightstream.cases` path, where it is the same object, and the root's
  `__all__` is unchanged in content and order.
- `pyflightstream.script.helpers.solver_settings` is the facade over
  per-family emitters in a private module; its 61 parameters, their order and
  defaults, every emitted line and every refusal are those of 0.33.0 (but see
  the five switches below, which were a defect of the old emitter). Every
  import path of 0.33.0 keeps working.
- The parser of `pyfs-matrix` is built by one function per family of
  subcommands, and the printing of `plan` and of the storage commands moved to
  a private module of `run`; the generated command-line reference is the same.
- The probe catalog `pyflightstream.qa.specs` is cut into modules with
  `PROBE_SPECS` keeping its name, its path and its order. It gained probe
  specifications for the acoustic, CCS wing, CCS fuselage and CCS revolve
  chapters (FR-333 to FR-335, FR-342).

`scripts/check_parity.py` compares the release with `v0.33.1` for the public
names and signatures, the commands and options, the emitted scripts and the
products, and names the differences this page lists.

## A thin blade can be derived from a blade mesh

`pyfs-matrix degenerate GEOMETRY --kind thin-blade --root-offset LENGTH`,
beside `inventory`, derives the thin blade of a blade mesh, a saved simulation
or an OBJ, and writes `<stem>_thin_blade.obj` with its boundary inventory
`<stem>_thin_blade.boundaries.toml` beside the source (FR-330). `thin-blade`
is the one kind and the default of `--kind`; the root offset is required, and
the blade's root is moved outward along the span by it so that it does not
cross the spinner. `--overwrite` rewrites an existing output.

`--boundary NAME` names the one boundary, an OBJ's group, that is the blade
when the file also holds a spinner, a nacelle or other bodies; the output is
then written as `<stem>_<NAME>_thin_blade.obj`. The command never modifies the
source. A refusal exits with status 2, names the file and the reason and
writes nothing: a mesh it cannot read, a file holding more than one boundary
without `--boundary`, an OBJ whose sidecar states a CAD or CCS conversion, a
blade whose root cannot be told from its tip, a section that is open, and a
blade whose two sides it cannot separate. The thin blade lies in the blade's
frame, so the inventory states the length unit of the source and, for an OBJ,
the mesh operations of its sidecar in order.

## Planning and running a selection, and the command that continues a run

`pyfs-matrix plan` and `pyfs-matrix run` take `--sims SIM [SIM ...]` and
`--points POINT [POINT ...]` (FR-326): one simulation, or one simulation and
some of its points by the point name the plan prints, is planned and run
without editing the matrix. The matrix file is not written, every point not
selected is neither planned, staged nor run and keeps its record, and an id or
a point the matrix does not carry is refused before anything runs, naming it
and the ones that exist. `--points` is accepted only with `--sims`.

What changes for a script of yours: `pyfs-matrix run --sims 2031 2032` without
`--force-rerun-all` was refused in 0.33.0 and runs those two simulations from
0.34.0, so a script that relied on the refusal sees a run. Add
`--force-rerun-all` to redo recorded points, as before, which keeps its 0.33.0
meaning; `--points` beside `--force-rerun-all` is refused. A selected point that
is already recorded follows the rules of 0.33.0 (refused, `--resume`,
`--force-rerun`). Use `plan --sims` to rehearse the same selection. The
selection is also a pair of arguments of the library functions `plan_matrix`
and `run_matrix`, `sims` and `points`.

A second `pyfs-matrix run` of a matrix with recorded points, without
`--resume`, is still refused with exit status 2 and runs nothing, and now
prints the command that continues it (FR-327): the command as it was invoked
with `--resume` added, quoted for the shell it was typed in, with the count of
recorded points and of the points that would run. The run never asks a
question, since it may be detached. The library refusal is still a
`WorkspaceError`, which now carries the counts as `recorded` and `would_run`.
The options are described in [Run the matrix](workflow-run-matrix.md).

## Five switches that asked DISABLE now get DISABLE

`solver_settings` resolves `valarezo_criterion`, `wake_relaxation`,
`wake_streamwise_agglomeration`, `adverse_gradient_boundary_layer` and
`vortex_ring_normalization` as it resolves its other switches (FR-349). A row
that asked DISABLE, the word or false, for one of them now gets DISABLE in its
script, where 0.33.0 wrote ENABLE and its setup record held the word; a value
in neither vocabulary is refused before anything is emitted, and the setup
snapshot records a boolean instead of the string. A row that asked ENABLE, or
nothing, renders as before, and no recorded campaign or golden render asked
any of the five. To keep the old behaviour of a row, ask ENABLE.

## A sampled field of build 8242026 is written without a warning

Build 8242026 of FlightStream 26.124 is registered (FR-153, RPT-136), by the
author decision of 2026-10-01 and not by a measurement: it has the rows build
8172026 has, the unsteady fluid plot and steady probe velocity conventions and
the rotation timing in metres and millimetres, each stating "owner decision of
2026-10-01, not measured" in its evidence. A field of that build is therefore
written with no warning, and its `products.json` entry carries neither
`velocity_convention` nor `rotation_timing`. The rows of build 8172026 and the
warning for every other build are unchanged, and no run measured 8242026. The
recipe that measures a convention is on
[Sampled fields](sampled-fields.md); it names the frames `ROTOR_SMRP` and
`ROTOR_RMRP1`, and says that a ring of four blades repeats every 90 degrees, so
one blade pins the whole rotation shift.

## A profile for an actuator disc can be generated

`pyfs-workspace profile SHAPE` writes `inputs/profiles/<stem>.csv` and its
provenance record `<stem>.provenance.json`, so that a matrix row uses the
profile by its stem (`PROFILE: <stem>`), as a sampled field is used (FR-347).
The shape is `sections` (a POL's written sections: the sectional loads table
the post recorded, found by `--pol` or named, `-Fx` at the stations by
default), `uni` (thrust growing with the radius) or `bp` (Betz-Prandtl, at an
advance ratio `--advance-ratio`); the profile is scaled to a thrust
(`--thrust`) or a thrust coefficient (`--ct` with `--rho` and `--rpm`), never
both. A station of `sections` whose thrust is negative is set to zero and
counted, as the measured method did. The command previews by default and
writes only with `--apply`, and replaces an existing file only with
`--overwrite`. The elliptical disc is native to the solver and needs no file.
The written file is an input of the next matrix; nothing already in a
workspace changes, and the post does not change. Measured on
26.124 and summarised in RPT-137, a custom profile delivers 0.95 to 1.04 of the
thrust asked on a RIGID wake, the ELLIPTICAL model places 0.62, and a RELAXED
wake ignores the profile (the plan warning above).

## The inventory records the number of faces

The inventory of a geometry, `<stem>.boundaries.toml`, records `mesh_faces`,
its number of faces, with `boundary_faces`, the count of each boundary where
the reader gives it, and `mesh_sha256`, the sha256 of the file counted
(FR-348). The super file, and the unsteady polar
(`polars/P<sim>_<name>_uns_avg.csv`), end with a new column `MESH_FACES`,
taken from the inventory whenever the field exists for the row's geometry, and
`NA` otherwise: the post never counts a face. Where the inventory was counted
from other bytes than the sha256 the run recorded for the file, `post.log`
warns, naming both, and the count is still carried. A reader of these files
that counts their columns sees one more, including the fixed-width
`legacy_polar` form of the super file, which gains one more 16-wide field. An
inventory written by an earlier release has no field and gives `NA`; for a
saved simulation, `pyfs-matrix inventory <geometry> --overwrite` takes it
again with the count.

## The coupled-run convergence log gains a column

The FSI convergence log `fsi_convergence_log.csv` ends with a new column,
`tip_flap_signed_m`: the tip flap deflection in metres with the sign the
displacement file `FSIDisp.txt` carries, positive toward the suction side
(FR-339). `tip_flap_m` stays the magnitude. A script that reads the log by
column name reads a 0.34.0 log unchanged; one that counts the columns of a row
sees fourteen instead of thirteen. A coupled run whose log 0.33.0 started is
refused when 0.34.0 resumes it, before the call writes anything, naming the
log: move the log aside to resume under 0.34.0, which then starts a new log, or
resume the run under 0.33.0. FSI on `unsteady_rotor` is still refused on this
release, as on 0.33.1; see [the FSI workspace](fsi-workspace.md).
