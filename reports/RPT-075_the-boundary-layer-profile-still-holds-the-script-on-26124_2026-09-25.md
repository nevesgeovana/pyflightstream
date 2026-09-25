# RPT-075: the boundary-layer profile export still holds an unattended script on 26.124 (2026-09-25)

**Date:** 2026-09-25
**Found by:** the licensed probe T20 of the 0.28.0 work
**Status:** OPEN until G24 (0.28.0: the command refused at plan on every build that documents it, naming this report)
**Affects:** `EXPORT_BL_VELOCITY_PROFILE`, documented from 26.122 and measured interactive on 26.122 (RPT-027)

## What this settles

The boundary-layer velocity profile at a point of the surface is a solver
command, `EXPORT_BL_VELOCITY_PROFILE <frame> <x> <y> <z>` with the file on the
next line. On 26.122 it opened a modal window with a plot and a Done button and
held the script until a person dismissed it (RPT-027). 0.28.0 would build it into
the pproc only if 26.124 runs it unattended. **It does not: on 26.124 the script
stops at the command and the point is never finished.**

## What was run

FlightStream 26.124 (build 8172026), the control point of RPT-060 (30_WB, alpha
2 deg, `SOLVER_SET_FARFIELD_LAYERS 5`), in the same detached batch as its control,
with no solver alive before it. The variant adds ONE command just before the log
export: `EXPORT_BL_VELOCITY_PROFILE 1` at a node of the control's own Tecplot
surface on the upper wing (the highest node between 35 and 45 % of the half-span,
in the reference frame 1), with its file on the next line. The run was given 120 s,
about twelve times the control's wall time (9.4 s).

## What came back

- **The run timed out at 120.06 s** and was killed; no solver process was left
  alive after it.
- **Every export before the command was written** (the loads, the Tecplot, the
  sections, the sectional loads, the probes), with the control's loads to the
  print; **the profile file and the log export after it were not.**
- The command left no line in any file the run wrote.

## What it means for the package

- **The command cannot be part of an unattended run on 26.124**, as on 26.122:
  a campaign that reached it would hold a seat until a person dismissed a window
  nobody sees under `-hidden`.
- **0.28.0 does not build `[[boundary_layer]]`**, and a raw
  `EXPORT_BL_VELOCITY_PROFILE` line is refused at plan on every build that
  documents the command, naming this report and RPT-027; the viscous drag and the
  boundary-layer variables of the VTK surface (RPT-074: thickness, momentum and
  displacement thickness, shape factor) are the unattended instruments.

## What this does not settle

- Whether a later build runs it unattended; the refusal is by build and a new
  build is probed before it is lifted.
- What the profile file holds.

## Evidence

The script the solver received and the result record are kept machine-local with
the probe driver `p28_driver.py` (variant S_BL); the GOAL-032 ledger's T20 receipt
names every path, the executable's sha256 and the batch's preflight.

**Verdict: REFUTED**: `EXPORT_BL_VELOCITY_PROFILE` does not run unattended on
26.124; the script stops at it and the run is lost at its timeout, as on 26.122.
