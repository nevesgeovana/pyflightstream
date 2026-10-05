# RPT-160 - FlightStream 26.125 registered from its manual and its outputs (2026-10-05)

The record of how **FR-423** registers FlightStream 26.125: what its manual
documents against the 26.124 manual, what the solver prints about itself, and
how its exports differ in form from 26.124's. No probe of the command database
ran to write it; the probe campaign that verifies the 26.125 statuses is owed
and its command is in the release kit.

## 1. The package

The 26.125 package differs from the 26.124 package in two files: the
executable and the user manual. The release notes, the EULA, the three
libraries and the sample script are byte-identical to 26.124's (sha256 of each
compared), so the release notes document none of what follows.

## 2. The manual, SRC-753

SRC-753 is 425 pages against 417 for SRC-752 (the 26.124 edition), its
scripting reference at pp.288-390 and its Script Index at pp.391-397, and it
carries the vendor's new product name. Read by the package's own reader over
both editions (`pyfs-manual surface`, `pyfs-manual register --fs-version
26.125`):

| Count | Commands |
|---|---|
| documented by SRC-752 | 371 |
| documented by SRC-753 | 380 |
| described identically, rows written by the register tool | 330 |
| described differently, rows written from a reading | 37 |
| documented first by SRC-753 | 13 |
| no longer printed, answering absent | 4 |

The thirteen new commands: `ASSIGN_SELECTED_CURVES_TO_CCS_WING`,
`ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE`, `ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY`,
`SET_CCS_TE_BLEND_LENGTH`, `CREATE_FREE_SURFACE_TFI_MESH`,
`FREE_SURFACE_EXPORT_TYPE`, `DELETE_FREE_SURFACE`, `ENABLE_SOLVER_TIME_AVERAGING`,
`DISABLE_SOLVER_TIME_AVERAGING`, `RESET_SOLVER_SWEEPER`,
`STABILITY_TOOLBOX_ANGLE_INCREMENT`, `SET_DIRECT_AEROELASTIC_MESH_MORPHING` and
`SET_AEROELASTIC_CONVERGENCE_THRESHOLD`. Twelve are entered with this
registration; `SET_DIRECT_AEROELASTIC_MESH_MORPHING` is entered by item S6 of the
release (FR-341), which ran it on 26.124 (RPT-154). SRC-752 does not print that
command: its text was searched page by page and the name is on no page.

The four no longer printed: `AUTO_DETECT_BASE_REGIONS`,
`AUTO_DETECT_TRAILING_EDGES`, `AUTO_DETECT_WAKE_TERMINATION_NODES` and
`SOLVER_TIME_AVERAGING`. In their place SRC-753 documents the every-boundary
form (-1) of the three `DETECT_*_BY_SURFACE` commands and the
`ENABLE_SOLVER_TIME_AVERAGING` and `DISABLE_SOLVER_TIME_AVERAGING` pair.

Of the 37 read differently, the grammar moves in 23 and each states it as an
argument override of its 26.125 row: the third argument of
`CREATE_AIRFOIL_SEPARATION` (the leading-edge type replaces the Valarezo
toggle), the edge-type token of `IMPORT_WAKE_EDGES_FROM_FILE` (the third token
26.124 was measured to require, RPT-061, now named: 1 for edge mid-points, 2
for corner nodes), the direction of the two relaxed trailing-edge CCS
commands, SPACE and AXIS on the flap cove and the morphing surface, the six
colour-map commands written on one line, the CDP and CDV tokens of the force
plot and the stability coefficient, and token lists that grow (ROUNDED_BLEND,
GENERIC, two NASTRAN file types, three thermal VTK variables, the -1 forms).
The other fourteen differ in layout spacing, a corrected sample or a parameter
table that names an argument the signature already had; the note of each row
says which.

Outside the scripting reference the loads chapter renames the two drag
columns (SRC-753 pp.227 and 229 against SRC-752 pp.225 and 227): CDi (induced
drag) becomes CDp (pressure drag) and CDo (skin friction drag) becomes CDv
(viscous and separation drag).

## 3. What the solver prints

Measured on six recorded points of a 26.124 campaign re-run on the 26.125
executable from their recorded scripts, one solver at a time, far field 5,
each export compared with the 26.124 export of the same point. The identity
lines and the measured forms are committed in
`reports/probes/RPT-160_2026-10-05_evidence.yaml`.

- The log names the build `Simcenter Flightstream 2612, build #10052026`, and
  every loads export closes with `Software : Simcenter Flightstream version
  2612, build #10052026` and a Company line naming Siemens. 26.124 printed
  release 26.1 at build 8172026 and named Altair. The product name, the
  release token (2612, with no dot) and the build number all change form, so
  the registry records build 10052026 and the printed release 2612.
- Every export title line that read `FlightStream <kind>` reads
  `Simcenter Flightstream <kind>`: probe points, surface sectional loads,
  surface sections and plots.
- The loads table header reads `CDp, CDv` where 26.124 read `CDi, CDo`. On the
  steady point the pressure-drag column equals 26.124's induced-drag column to
  the printed digit on every surface row, and the viscous column is larger
  than the skin-friction column by about a fifth of the total.
- The recorded unsteady scripts ask `UNSTEADY_SOLVER_NEW_FORCE_PLOT` for the
  parameters CDI and CDO, the tokens SRC-753 p.359 no longer lists (it lists CDP
  and CDV). 26.125 ran them: on an unsteady point the last value of the CDI plot
  equals the pressure-drag total of the loads export to the printed digit, and
  the CDO plot the viscous total. The 26.125 row of the command therefore accepts
  the four tokens, the two the page prints and the two the run measured.

## 4. What remains for a run

Every 26.125 status is `documented`. The probe campaign of the release kit
runs every probe specification of the catalog on 26.125, writes
`reports/compat/CMP-26125_<date>_*.yaml`, and its identity step must print the
build and release recorded here. Whether the build still answers the four
commands its manual stopped printing is asked by no probe, since a command
with no row is not probed.
