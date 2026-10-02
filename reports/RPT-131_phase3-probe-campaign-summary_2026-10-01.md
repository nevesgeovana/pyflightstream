# RPT-131 - The PHASE3 probe campaign of 2026-09-28: a summary of the facts the committed reports use (2026-10-01)

A summary receipt, written for FR-343 of pyflightstream 0.34.0. A private
licensed probe campaign on **FlightStream 26.124, build 8172026**, run on
2026-09-28 on the measuring machine, produced a results file, `PHASE3-RESULTS.md`
(seventeen sections, kept outside this repository). Two committed reports take
facts from it: RPT-093 (the Aeroelastic Coupling Toolbox on 26.124, sections 1
to 13 of the file) and RPT-089 (the quasi-steady rotor against the unsteady
rotor, sections 12 and 15 to 17). Until now those facts could not be checked
from the repository. This report states each one beside its date, build and
command, so a reader can repeat the measurement with a licence and compare.

What it does not carry: no geometry, no dimension of one, no research data
(forces, moments and coefficients of the research rotor stay in the private
file and in the two reports above), no project, order or machine identifier,
and no executable digest (NFR-31). Every number below is a count, a ratio or
a percentage, or an error against an imposed displacement. The solver
reported them; this report did not run the solver.

## The facts

| fact | number | date | solver build | command or script step |
|---|---|---|---|---|
| Surface vertices mapped on an OBJ-imported blade when the aeroelastic surface list holds the blade's own boundary ID (2), rotary motion, coupling enabled before the first step | 936 of 936 | 2026-09-28 | 26.124 (8172026) | `ASSIGN_AEROELASTIC_SURFACES 2`, then `START_SOLVER` |
| Surface vertices mapped on the same blade when the list holds surface 1 instead | 0 of 936, no refusal and no warning | 2026-09-28 | 26.124 (8172026) | `ASSIGN_AEROELASTIC_SURFACES 1`, then `START_SOLVER` |
| Nine-step unsteady run, rotary motion, coupling enabled from the start: steps after whose structural call the exported blade stood back at its imported azimuth (0.00 deg), the step before it standing at 10 to 90 deg | 9 of 9 | 2026-09-28 | 26.124 (8172026) | `SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE`, `START_SOLVER`, one `EXPORT_SOLVER_ANALYSIS_TECPLOT` per step |
| Staged start, 36 rigid steps and then the coupling enabled without re-initializing, nine coupled steps: vertices mapped | 0 of 936, with 9 structural calls made | 2026-09-28 | 26.124 (8172026) | `START_SOLVER`, `SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE`, `START_SOLVER` |
| Blade held still, rotation carried by the free stream, steady solver: vertices mapped | 936 of 936 | 2026-09-28 | 26.124 (8172026) | `SET_FREESTREAM ROTATION <frame> <axis> <rpm>`, `EXECUTE_AEROELASTIC_ANALYSIS` |
| Same run, imposed displacement: aeroelastic iterations to converge | 2 of 10 | 2026-09-28 | 26.124 (8172026) | `SET_AEROELASTIC_ITERATIONS 10`, `EXECUTE_AEROELASTIC_ANALYSIS` |
| Same run: largest error of the exported surface against the imposed displacement | 0.1 mm | 2026-09-28 | 26.124 (8172026) | `EXPORT_SOLVER_ANALYSIS_TECPLOT` after `EXECUTE_AEROELASTIC_ANALYSIS` |
| Same run, zero displacement: axial force against the same blade turning rigid in an unsteady run at the same azimuth | 0.35 % apart | 2026-09-28 | 26.124 (8172026) | `SET_FREESTREAM ROTATION <frame> <axis> <rpm>`, `SET_SOLVER_STEADY`, `START_SOLVER` |
| Rotation placed inside the structural displacement: largest residual of the morphed surface against the exact rotated position, at the root, at 90 deg of rotation | 37.1 mm | 2026-09-28 | 26.124 (8172026) | `START_SOLVER` with the structural program returning the rotated displacement, nodes in the reference frame |
| Same run: steps after which the coupled solve diverged | about 5 | 2026-09-28 | 26.124 (8172026) | `START_SOLVER` with the structural program returning the rotated displacement |
| Whole wheel at 5 deg angle of attack, six clockings against the unsteady rotor at 10 deg per step: gap of the quasi-steady axial force to the unsteady one | -8.99 % | 2026-09-28 | 26.124 (8172026) | `SET_FREESTREAM ROTATION <frame> <axis> <rpm>`, `SET_SOLVER_STEADY`, `START_SOLVER` per clocking; `SET_SOLVER_UNSTEADY`, `START_SOLVER` for the unsteady rotor |
| Same wheel: wall time of the six clockings against three unsteady revolutions | 10.8 s against 102.7 s | 2026-09-28 | 26.124 (8172026) | one launch per run, `-hidden -script`, licence checkout included |
| Clockings: largest difference of any of the six components at 6 clockings from the value at 24 clockings | 1.6 % | 2026-09-28 | 26.124 (8172026) | `SET_FREESTREAM ROTATION <frame> <axis> <rpm>`, `START_SOLVER` per clocking, 6 and 24 per 60 deg passage |

## How to read it

The date is the date of the campaign's results file and of every launch in
it. Every row ran on the one build stated, and none was repeated on another
build except where RPT-093 says so for the morph behaviour (build 26.122
showed the same, which is not a row here). The commands are the script
lines of the arm that produced the number, in the form the command database
of this package carries; a placeholder in angle brackets stands for a value
the measuring machine chose and this report does not publish.

A row is a fact of one run, not a property of the solver: where a report
draws a conclusion from several rows, the conclusion is that report's and
the rows are here only so that the numbers it cites resolve.

## Where it is cited

RPT-093 and RPT-089 cite this report in place of the private file, and the
specification cites it at FR-343.
