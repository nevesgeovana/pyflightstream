# RPT-098 - pyflightstream 0.32 round 3 on FlightStream 26.124: the acoustic chain, the wake stabilisation and the surface removal (2026-09-30)

The report of licensed round 3 of pyflightstream 0.32.0 (GOAL-037), packages E2
(noise emission) and H (G4 and G9). Nine rows in two matrices ran through the
**package route** (`pyfs-matrix plan`, then `pyfs-matrix run --local`) on
**FlightStream 26.124, build 8172026**, executable SHA-256
withheld from the public tree per NFR-31, serially,
with far field 5 layers in every setup. Round 1 (RPT-096) proved the acoustic
commands, `DELETE_SURFACES` and the wake stabilisation `DISABLE` one script at
a time; this round proves the package's own emission, collection and hashing of
them on an `unsteady_rotor` row. No solver was run to write this report: it
reads the round's records, saved simulations and the checkers' verdicts
(`verdicts_e2*.json`, `verdicts_h.json`).

(no requirement: licensed report RPT-098, not a capability)

Only nondimensional values are stated. The geometry is the library's tier-3
single blade and twin-blade meshes; the round states no length, speed or rotor
speed of either, and the scripts that hold them stay in the round's folder.

## 1. The acoustic chain on unsteady_rotor (package E2, POL 3201 to 3203)

The rows are `unsteady_rotor` rows, one revolution marched in 24 steps.

| POL | what it moves | record | what was read |
|---|---|---|---|
| 3201 | the whole chain: `ACOUSTIC_SOURCES ENABLE`, three named observers, an observer file of two, the observer time window, a section | CONVERGED | one signals file, five observer blocks, 16 rows each, nonzero pressures in 160 of 240 values; 16 section files; 27 of 27 outputs hash as recorded |
| 3202 | the control: 3201 with `ACOUSTIC_SOURCES DISABLE`, the one token changed | CONVERGED | the same file layout, every one of the 240 pressure values zero |
| 3203 | a section alone: compute, no export, in the rotor's hub frame | CONVERGED | no signals file declared or written; 16 section files listed and hashed, 26 of 26 outputs hash as recorded |

What the two full rows show:

- The package emits `COMPUTE_ACOUSTIC_SIGNALS` and `EXPORT_ACOUSTIC_SIGNALS` after the solver start and before the save, and the export is collected and hashed as the run's output. The sources, the observers and the time window are set after the motion and before the unsteady solver is initialised, and the solver accepted that order.
- The five observer blocks are the three named ones first (`MIC_P`, `MIC_M`, `MIC_UP`) and the two imported from the point's own copy of the observer file (read back as `Observer 4` and `Observer 5`); the copy is hashed among the run's inputs.
- The time column runs from 0.05 to 0.190625 in 16 rows per observer.
- The sources flag is read by the solver through the package's route as it was on a script: sources off, every pressure zero; sources on, 160 of 240 values nonzero. The control is exact zero, so the nonzero values of 3201 are the sources'.
- The section writes 16 files per run, each with a 24 point grid for the 2 radial by 8 azimuthal request, listed in the record's outputs with their hashes. In 3203 the section sits in the rotor's hub frame and needs no signals export before it.

## 2. G4: the wake stabilisation, DISABLE, ENABLE and absent (package H, POL 3304 to 3306)

Three `unsteady_rotor` rows on the same setup and blade count differ in one
setup key.

| POL | the key | the line the package emits | record |
|---|---|---|---|
| 3304 | DISABLE | `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION 1 DISABLE 2` | CONVERGED |
| 3305 | ENABLE | `SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION 1 ENABLE 2` | CONVERGED |
| 3306 | absent | no such line | CONVERGED |

The saved simulations of the DISABLE and ENABLE rows differ in bytes (482 of
3394 lines differ, the two files having the same line count), which reads the
key as stored. The absent-key save equals neither: it is not byte equal to the
DISABLE save (the two files are the same size) nor to the ENABLE save. So the
three cases are three states of the file, and the package's DISABLE is not the
same as writing nothing. What the differing lines are, and whether the
difference between DISABLE and absent is a stored setting or a stamp of the
save, were not read.

## 3. G9: surface removal and the renumbered inventory (package H, POL 3301 to 3303)

The mesh is the twin-blade library mesh with four boundaries, `Body`, `Base`,
`Blade1` and `Blade2`.

| POL | what it moves | what was read | record |
|---|---|---|---|
| 3301 | `delete_surfaces = ["Blade1"]` on a rotor row moving `Blade2` | `DELETE_SURFACES 3` right after the open, before anything cites a surface; the saved inventory is Body, Base, Blade2; the row's `SET_MOTION_BOUNDARIES` cites index 3 | COMPLETED_MAX_ITER |
| 3302 | the same row without the key | no `DELETE_SURFACES`; `SET_MOTION_BOUNDARIES` cites index 4 | CONVERGED |
| 3303 | the family form, `delete_surfaces = ["Blade"]` | `DELETE_SURFACES 4` then `DELETE_SURFACES 3` (a family goes from its last member); the saved inventory is Body, Base | CONVERGED |

The inventory after the removal is **Body, Base, Blade2 with the moving
boundary at index 3**: `Blade2` moved from index 4 to index 3, the package's
motion command follows it, and the same row without the key still cites 4.

POL 3301's status `COMPLETED_MAX_ITER` is the short march reaching its
iteration limit, and it is **not a G9 defect**: the round's checker expected a
finished-and-converged status for every row and read this one as the only
failed expectation of its whole run (every other H expectation and all of E2's
held), while every G9 expectation of the row (the script line, the citation
index, the saved inventory) held. The row
saved its simulation.

## What this round does not establish

- **An acoustic chain on a solved real propeller.** The rows are library meshes marched for one revolution; the pressures say nothing about a real case.
- **Any amplitude, level or spectrum.** Only that sources off is zero and sources on is not, and that the layout is as the package promises.
- **The relation of the observer time window to the solver's time.** The window was chosen by the row and the round ties no observer row to a solver step.
- **What the section's 16 files hold per time step**, beyond the point count of the grid.
- **What the differing lines of the G4 saves are**, and whether the DISABLE and the absent-key saves differ by a setting or by a stamp.
- **The effect of the wake stabilisation on any solution.** The round compares saved files, not loads or wakes.
- **G9 on any other mesh**, or a removal that would leave the moving boundary with no index.
- **A promotion of any command to `verified`.** The round ran no `pyfs-qa probe`.

Numbers and files are in the sidecar
`RPT-098_acoustic-chain-wake-and-surface-removal-round-3-on-26124_2026-09-30.json`;
the round's own files are `C:/WORK/release-0320/probes/round3/` (`README.md`,
`verdicts_e2.json`, `verdicts_h.json`, `sims/`, `logs/`).
