# RPT-070: the volume section and the actuator disc on 26.124, and a profile file the solver would not read (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed rows of `matriz_gui.fs` of the 0.27.0 work (G05, G06)
**Status:** CLOSED in 0.27.0 (G05: the section is updated before its export; G06: a disc stated by its net thrust runs, and a point whose profile file the solver could not read fails)
**Affects:** `CREATE_NEW_RECTANGLE_VOLUME_SECTION`, `UPDATE_ALL_VOLUME_SECTIONS`, `EXPORT_VOLUME_SECTION_VTK`, `CREATE_NEW_ACTUATOR`, `SET_PROP_ACTUATOR_THRUST`, `SET_PROP_ACTUATOR_PROFILE`, on 26.124

## What this settles

0.27.0 reaches two GUI steps from a matrix row: a volume section declared in the
pproc and exported by every steady point (G05), and an actuator disc declared in
the reference and named by a row (G06), loaded by its net thrust or by a radial
profile file. Four rows on one wing (`12_WING_PHY.fsm`, 30 m/s, far field 5)
answer whether each reaches the solve and comes back.

## What was run

FlightStream 26.124 (build 8172026), one detached run at a time, no solver alive
before each.

| row | what it states |
|---|---|
| 5007 | a YZ volume section at x = 2.5 m, a steady sweep of alpha 0 and 4 run as one job |
| 5008 | the disc by its net thrust, 120 N at 2400 rev/min |
| 5009 | the disc by a radial profile file |
| 5010 | the control: the disc declared in the reference, named by no row |

## What came back

- **The volume section was exported empty.** Both points of 5007 wrote a
  `_vsec.vtk` of 25 points and 16 cells whose every cell value was 0.0, byte for
  byte the same at 0 and 4 deg. The section is cut after the solve and was
  exported without being computed: the manual computes a section's flow with
  "Update all", `UPDATE_ALL_VOLUME_SECTIONS`. With that command after the cut
  and before the export (the G05 fix), the row was run again: every one of the
  96 cell values of each point is non-zero and the two points differ.
- **The disc by its net thrust reaches the solve.** 5008 against its control
  5010: CDi -0.0221 against +0.0049, CL 0.3451 against 0.3385; its saved
  simulation names the disc `PROP`, the control's does not.
- **The profile file was not read.** The first run of `SET_PROP_ACTUATOR_PROFILE`
  on any build put up a modal dialog, "Invalid file format. Please check file for
  consistency.", that held the solver until a person dismissed it, and its log
  says "Failed to read custom radial thrust profile file: <path>". The point then
  ran to the end with the disc acting on a loading that is not the file's (CDi
  -0.0208, near the net-thrust row) and was recorded as converged. **A point whose
  log carries one of the solver's four "custom radial thrust profile file" lines
  is now FAILED_SCRIPT** (G06), on the point path, the steady job and collect. The
  format the build reads is not settled by this run: the file had two columns,
  `r,F`, as the manual prints, and no header line.

## A saved simulation's length unit

The G06 disc and the G05 section state their lengths in metres, and a saved
simulation keeps the unit it was saved in. Two saves of one metre file, one
after `SET_SIMULATION_LENGTH_UNITS MILLIMETER`, carry different heads in their
`$GLOBAL_START$` block: `1.0` and `5` in metres, `1.0E-03` and `2` in
millimetres. So the head records the unit; 0.27.0 reads the metre head and
refuses any other at plan, naming the keys, rather than read a millimetre file
as metres.

## What this does not settle

- The profile format 26.124 accepts, and the modal dialog that holds an
  unattended run on an unreadable file.
- The circle form of the volume section, and the Tecplot export.

**Verdict: PARTIAL.** The volume section and the disc by its net thrust run and
come back on 26.124 (the section after the update fix); the disc by a profile
file does not read the file, and 0.27.0 now fails such a point instead of
recording it converged.
