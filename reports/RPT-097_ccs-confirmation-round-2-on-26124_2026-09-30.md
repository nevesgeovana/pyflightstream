# RPT-097 - pyflightstream 0.32 CCS confirmation, round 2 on FlightStream 26.124 (2026-09-30)

The report of licensed round 2 of pyflightstream 0.32.0 (GOAL-037), package C
(CCS). Seven items, each its own matrix row, ran one after the other through
the **package route** (`pyfs-matrix plan`, then `pyfs-matrix run --local`) on
**FlightStream 26.124, build 8172026**, executable SHA-256
withheld from the public tree per NFR-31. Round 1
(RPT-096) proved the CCS commands one script at a time; this round asks whether
the package's own emission of them works when a user runs a row. Every row is a
steady solve at an angle of attack of 4 degrees and a Mach number of 0.1, 150
iterations at most, far field 5 layers (setup `s001`), on generic shapes built
from public shape laws (the round-1 inputs, byte for byte). No solver was run
to write this report: it reads the round's records, logs and saved simulations.

(no requirement: licensed report RPT-097, not a capability)

Only nondimensional values are stated. The scripts hold the geometry's
dimensions and stay in the round's folder.

## 1. How an item is read

An item is **confirmed** when the run record's status is a finished one
(`CONVERGED` or `COMPLETED_MAX_ITER`), the log holds no error line, a
simulation was saved, and the boundaries the package's boundary reader lists in
the final saved simulation are the ones the sidecar names. The two comparisons
(the control surface against the plain wing, the two shedding directions
against each other) are byte and line comparisons of two final saved
simulations. An item that leaves no saved simulation is **not confirmed**.

## 2. One row per item

| item | POL | what it moves | record status | boundaries in the saved simulation | verdict |
|---|---|---|---|---|---|
| CCS1-WING | 3201 | the wing loft through a whole row, with `CCS_WING_MESH_SUBDIVISIONS CHORD 30` | CONVERGED | PYFS_WING | **confirmed** |
| CCS1-FUSELAGE | 3202 | the fuselage loft | CONVERGED | PYFS_FUS | **confirmed** |
| CCS1-REVOLUTION | 3203 | the body of revolution | CONVERGED | PYFS_REV | **confirmed** |
| CCS2-PARAMETRIC | 3204 | CCS1-WING plus one control surface in the ten-argument PARAMETRIC form | CONVERGED | PYFS_WING, PYFS_AIL, PYFS_AIL_side | **confirmed**; the saved simulation differs from CCS1-WING's |
| CCS2-REAL | 3205 | the same control surface with REAL spanwise limits | FAILED_EXECUTION | none: no saved simulation | **not confirmed** |
| G35-AXIAL | 3206 | `kind = "file"` (`CCS_IMPORT`), `CCS_SHEDDING: AXIAL` | CONVERGED | PYFS_CCS_FUS | **confirmed** |
| G35-AZIMUTH | 3207 | the same with `CCS_SHEDDING: AZIMUTH` | COMPLETED_MAX_ITER | PYFS_CCS_FUS | **confirmed**; the two saves differ |

The rows differ from the round-1 probes in one thing only: the script is the
one the package emits.

## 3. What each group read

### 3.1 The three lofts (CCS1)

The wing, the fuselage and the body of revolution were each lofted by the
package's curve route from the generic CCS file, solved, and saved. Each final
saved simulation lists exactly the boundary its sidecar names, and no log holds
an error line. This is the package route working on 26.124 for the three loft
kinds, where round 1 had proved the commands alone.

### 3.2 The control surface (CCS2)

The control surface in the **PARAMETRIC** form, the ten-argument line that
states SPACE and AXIS, is **confirmed**: the run completed, the log holds no
error line, and the saved simulation lists three boundaries, the wing, the
control surface and a side boundary of it (`PYFS_AIL_side`), where the plain
wing lists one. The saved simulation differs from CCS1-WING's: the plain
wing's save has 1431 lines and the save with the control surface 1744 (the
order the round's read script compares them in), and the two files are not
byte equal.

The same control surface with **REAL** spanwise limits ended
**FAILED_EXECUTION**: the record holds no saved simulation, and the log holds
no error line that names a cause. The two rows differ only in the spanwise
limits' space (and the numbers that state them), so the round shows the REAL
form fails here and the PARAMETRIC form does not; it does not say why. The
package now refuses the REAL form when the row is planned, on every build,
naming this report and the PARAMETRIC form to use (FR-295 to FR-299). The
command database keeps `NEW_CCS_WING_CONTROL_SURFACE` at `documented` on 26.124
with a note of this reading: promotion to `verified` needs a `pyfs-qa probe`
run, which this round was not.

### 3.3 The shedding direction (G35)

`kind = "file"` imports the whole CCS file by `CCS_IMPORT`, with every
`Relaxed_TE` line restated in the row's direction. Both directions ran, saved,
and list one boundary, `PYFS_CCS_FUS`. The two saved simulations differ: the
axial one is 4740 lines and the azimuth one 5026, and 4413 lines differ
between them. The two saves are solved simulations of different lengths and
the AZIMUTH run ended at its iteration limit (`COMPLETED_MAX_ITER`, the
round's cap and not a defect), so the difference mixes whatever the direction
digit does to the geometry with the two solutions. **The two saves differ**,
and that is all this round shows: the direction digit's own effect is not
separated from the solution, and round 1 recorded five differing lines without line numbers, so the two rounds are not
compared line by line. What is confirmed is that both directions are accepted and run
through the package route.

## 4. The verdict, item by item

**Confirmed:** the CCS wing loft (CCS1-WING), the fuselage loft
(CCS1-FUSELAGE), the body of revolution (CCS1-REVOLUTION), the control surface
in the PARAMETRIC form (CCS2-PARAMETRIC), and the G35 axial and azimuth files
(the two saves differ).

**Not confirmed:** the control surface in the REAL form (CCS2-REAL).

## What this round does not establish

- **Why the REAL form failed.** The record's status and the missing saved simulation are all that was read; the log names no cause, and whether any REAL argument set is accepted is not known.
- **What the control surface does to the flow or the loads.** The round confirms the saved simulation has the added boundaries and differs from the plain wing's; it compares no coefficient.
- **What the differing lines of the G35 saves are**, or that the geometry differs in the way the digit's meaning in the manual implies: the two saves were compared as text.
- **Any other build.** Only 26.124 ran; the REAL refusal on the other builds rests on their not having been measured.
- **Convergence of any row as a physical result.** The rows are generic shapes solved to exercise the route; the round says nothing about a real aircraft.
- **A promotion of any command to `verified`.** The round ran no `pyfs-qa probe`.

Numbers and files are in the sidecar
`RPT-097_ccs-confirmation-round-2-on-26124_2026-09-30.json`; the round's own
files are `<local probe folder>/round2/ccs/` (`README.md`,
`verdicts_ccs.json`, `ws/` with the records and logs).
