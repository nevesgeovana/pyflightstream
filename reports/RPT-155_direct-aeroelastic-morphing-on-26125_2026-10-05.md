# RPT-155 - Direct aeroelastic morphing on build 10052026 (2026-10-05)

FlightStream 26.125, build 10052026; far field 5. This report transcribes retained runs and comparisons; it does not rerun the solver. Evidence is cited by file name relative to the run folder.

## Purpose

Record the S6 evidence for FR-341: whether direct aeroelastic mesh morphing can be scripted and verified on build 26.125 for quasi-steady sector and unsteady rotor routes.

## Method

The same ten arms as RPT-154 ran on build 26.125: Q0-Q4, a quasi-steady sector using a research propeller blade, and U0-U4, an unsteady rotor using the same generic blade description. All arms used far field 5. The direct arms Q3, Q4, U3 and U4 used `SET_DIRECT_AEROELASTIC_MESH_MORPHING`; Q4 and U4 selected RIGID, while Q3 and U3 selected DEFLECTED. Q1 and U1 represent current wiring; Q2 and U2 are mapped-route controls. The written displacement field was checked against the resulting surface over two cycles where applicable. Sources: `DESIGN.md` dated 2026-10-05 section, `judge.log`, and logs and retained comparisons under `runs/` and `diffs/`.

## Results

The direct-morphing command was recognized on build 26.125. Q4 RIGID moved the surface by the written field and passed the exact two-cycle check; maximum error was 5e-16 m. Q3 DEFLECTED produced the right geometry to 5e-12 m, but its exact two-cycle check did not close.

On the unsteady rotor, U4 RIGID wrote a nodes file that followed rotation, with node azimuth changing from -10 to -90 degrees over nine steps. The deformed surface nevertheless stayed at the import azimuth. U3 DEFLECTED left nodes at azimuth 0 and produced a surface with up to 1.2 cm error.

The mapped control U2 applied the deflection at the import azimuth, reproducing the RPT-093 behavior on build 26.125. U1, representing today's wiring, left the blade undeformed. Q1 and Q2 behaved as recorded for the corresponding controls in RPT-154: Q1 deflected the surface; Q2 applied the mapped written field, while its exact two-cycle check did not close.

Route C is implementable on the quasi-steady sector with RIGID on build 26.125. The measured unsteady rotor route is not supported. The owner's decision on 2026-10-05 is to implement the sector only.

## Limits

One build and one case were measured. Q4 demonstrates the RIGID quasi-steady sector behavior for this case; it does not establish DEFLECTED exact-cycle closure. The unsteady tests show the measured node and surface behavior for these arms and do not establish a supported direct unsteady workflow. The direct file exchange and behavior beyond the measured commands, frames, and cycles remain uncharacterized.
