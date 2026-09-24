# RPT-070: the volume section and the actuator disc on 26.124, and a profile file the solver would not read (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed rows of `matriz_gui.fs` of the 0.27.0 work (G05, G06)
**Status:** CLOSED in 0.27.0 (G05: the section is updated before its export; G06: a disc runs by its net thrust or by a profile file, which the run writes in the form 26.124 reads, and a point whose profile the solver could not read fails)
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
- **The profile file, and the form 26.124 reads.** The first run of
  `SET_PROP_ACTUATOR_PROFILE` on any build put up a modal dialog, "Invalid file
  format. Please check file for consistency.", that held the solver until a
  person dismissed it, and its log says "Failed to read custom radial thrust
  profile file: <path>"; the point was recorded converged. Eight one-thing probes
  (the setup up to the disc, saved, no solve, a watcher closing the dialog)
  settled why: the file's rows `r,F` are right, and **a final newline is read as
  one more, empty point** (the saved disc holds 12 points for 11 rows) which the
  build refuses. A count line or a header line first is read as a point too and
  zeros every value; CRLF, spaces, tabs or a dimensional radius change nothing.
  **The same rows with no final newline are read whole**: 11 points saved, no
  dialog, no refusal. 0.27.0 therefore writes the run's own copy of the profile
  in that form, where the point runs, and names it in the script; a header or a
  count line in the user's file is refused at plan; and a point whose log still
  carries one of the solver's four "custom radial thrust profile file" lines is
  FAILED_SCRIPT (G06). Row 5009 was run again on the copy: no dialog, no refusal
  line, the saved disc holds the 11 points, and its loads equal the first run's
  (CDi -0.0208, CL 0.3439), which had read the 11 points before refusing the
  empty twelfth.

## A saved simulation's length unit

The G06 disc and the G05 section state their lengths in metres, and a saved
simulation keeps the unit it was saved in. Two saves of one metre file, one
after `SET_SIMULATION_LENGTH_UNITS MILLIMETER`, carry different heads in their
`$GLOBAL_START$` block: `1.0` and `5` in metres, `1.0E-03` and `2` in
millimetres. So the head records the unit; 0.27.0 reads the metre head and
refuses any other at plan, naming the keys, rather than read a millimetre file
as metres.

## What this does not settle

- The modal dialog that holds an unattended run on a file the build cannot read
  (the package's copy avoids it; nothing watches for it).
- A profile file with CRLF line ends and no final newline.
- The circle form of the volume section, and the Tecplot export.

**Verdict: VERIFIED.** The volume section (after the update fix), the disc by its
net thrust and the disc by a profile file (in the form measured here, which the
package now writes) run and come back on 26.124.
