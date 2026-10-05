# RPT-154 - Direct aeroelastic morphing not recognised by build 8172026 (2026-10-05)

FlightStream 26.124, build 8172026; far field 5. This report transcribes retained runs and comparisons; it does not rerun the solver. Evidence is cited by file name relative to the run folder.

## Purpose

Record the S6 evidence for FR-341, item S6, currently on hold: whether direct aeroelastic mesh morphing can be scripted and verified on this build for quasi-steady sector and unsteady rotor routes.

## Method

The 26.124 user manual documents `SET_DIRECT_AEROELASTIC_MESH_MORPHING <frame> RIGID|DEFLECTED` on its aeroelastic coupling toolbox page. The experiment compared Q0-Q4 quasi-steady sector arms and U0-U4 unsteady rotor arms. The case was a research propeller blade with private geometry, 936 vertices, at advance ratio J = 1.7. All arms used far field 5.

The direct arms Q3, Q4, U3 and U4 replaced structural-node import with the documented direct-mode command. Q1 was the current quasi-steady sector route; Q2 used mapped structural displacements. U1 was the current unsteady rotor wiring; U2 used mapped displacements. Q0 and U0 were rigid controls. Sources are `DESIGN.md`, `judge.log`, logs under `runs/`, and the retained comparisons under `diffs/`.

## Results

Build 8172026 reported each direct-mode script line as an unrecognised command in all four direct arms. The run logs contain the refusals, and no direct-arm structural calls or direct-mode output followed. Thus neither direct route ran far enough to measure morphing.

The control routes did run. Q1 moved the surface 3.5 mm relative to its rigid control. In Q2, the mapped route applied the written displacement field: each measured cycle was within 0.6 mm of its written field. The retained judge notes that an exact two-cycle truncation check did not pass, so Q2 is evidence for the mapped control response, not a claim of exact two-cycle reproduction.

On the unsteady rotor, U1 left the blade undeformed. U2 applied the mapped deflection at the import azimuth, reproducing the defect recorded in RPT-093. These controls confirm that the arms exercised the current and mapped routes while leaving the direct command failure as the blocker.

Route C cannot be implemented or verified on build 8172026. The item remains on hold pending a build that carries the command; that build has been requested from the vendor.

## Limits

One build and one case were measured. The file format expected by direct mode is unknown. Because the direct command was refused, this experiment provides no evidence about its file exchange, displacement semantics, or behavior after a supported build becomes available.

## Addendum (2026-10-05): the 26.124 manual does not document the command

The Method's first sentence says the 26.124 user manual documents `SET_DIRECT_AEROELASTIC_MESH_MORPHING` on its aeroelastic coupling toolbox page. It does not. The 26.124 package's PDF manual (SRC-752, 417 pages) was searched page by page, and its compiled help was extracted and searched file by file: neither prints the command name. Its aeroelastic coupling toolbox page (SRC-752 p.382) documents the structural-node commands only. The command form the arms used, `SET_DIRECT_AEROELASTIC_MESH_MORPHING <frame> RIGID|DEFLECTED`, is first printed by the 26.125 edition (SRC-753 p.388), which is what the command database's 26.125 registration records. The measured result above is unchanged: build 8172026 refused the command in all four direct arms.
