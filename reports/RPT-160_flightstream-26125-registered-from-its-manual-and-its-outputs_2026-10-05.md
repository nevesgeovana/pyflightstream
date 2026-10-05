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

## 4. The probe campaign

The campaign of the same day ran every probe specification with a 26.125 row,
175, on two solvers at a time, far field 5 before every initialisation, and
wrote `reports/compat/CMP-26125_2026-10-05_probe-campaign.yaml`; its identity
report, `reports/compat/CMP-26125_2026-10-05_identity.yaml`, prints the build
and release recorded above. The first pass recorded 138 verified and 7 broken.
Five of the seven were the probe's own lines: four wrote the form of 26.124
where SRC-753 adds DIRECTION, or SPACE and AXIS, and one wrote the revolve
export in the six-placeholder form of its page heading where the page's sample
prints the revolve loft's form. Re-probed the same day in the printed forms,
the morphing surface, the flap cove and the revolve export ran and showed their
effect, and the two relaxed trailing edges ran with no abort and no observable
effect; the committed report carries the re-probed lines and names both
passes. The 26.125 rows of the four make DIRECTION, SPACE and AXIS required,
the line without them having aborted, and the revolve export's row states the
sample's form.

Two stay broken on the documented form: `CREATE_FREE_SURFACE_TFI_MESH` on a
session holding the probe blade raises a modal error naming a perimeter curve
with no virtual curves, which stops an unattended script, and
`NEW_OFF_BODY_STREAMLINE` ends the solver with an access violation, as on
26.124. No run type writes either, and the emitter refuses both on 26.125,
naming the evidence.

Final: 141 verified, 2 broken, 236 unprobed, and the database promoted from the
report. With the minimal workflow's commands verified, 26.125 is
`operational`. The four commands SRC-753 stops printing have no 26.125 row and
were not asked.

## Addendum, 2026-10-05: two exports of the campaign, read line by line

Section 3 measured the loads export; two readers of 0.37.0 also rest on two
other exports of the campaign of section 4, and this addendum quotes them. Both
files were written by 26.125 (build 10052026) in the first shard of that
campaign, each by one probe of `reports/compat/CMP-26125_2026-10-05_probe-campaign.md`,
on the package's own synthetic test blade (`30_BLADE.fsm` of the tier-3
inputs), steady, 30 m/s, five iterations, far field 5. The files stayed on the
measuring machine; each is named here by its sha256 and its lines are quoted
as the solver wrote them, without their CRLF line ends.

### The sweep spreadsheet (W3-1)

Written by the probe of `SWEEPER_EXPORT_SPREADSHEET` (one custom angle of
attack, 2.0 degrees, swept and exported), file `sweep.txt`, 36 lines, sha256
`53b0da3610e4c939976257428354ab558ff91b98db2c65007a53ec5642d3fff1`. Its title
line 5 reads `Aerodynamic loads (Sweep)`, its header line 28 and its one data
row, line 30, read:

```text
     AOA (deg), Beta (deg), Velocity (m/sec), Cx, Cy, Cz, CL, CDp, CDv, CMx, CMy, CMz
     +2.0000,+.0000,+30.0000,+.1487,-.1829,-.0034,-.0086,+.1473,+.0012,+.1919,+.1738,+.0038,
```

The two drag columns are printed `CDp` and `CDv`, where the recorded 26.123
sweep spreadsheet (RPT-037) prints `CDi` and `CDo`; the other ten names and their order
are the same. This is one export of one sweep with one point; no other 26.125
sweep spreadsheet was read, and no 26.124 sweep spreadsheet was read in this
campaign.
