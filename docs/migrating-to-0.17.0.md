# Migrating to 0.17.0

> Frozen record: not edited after its release.

## Historical context: srs - functional-requirements

BOTH SHAPES ARE PRE-SCANS FROM 0.17.0, and this paragraph used to say
they were not. The second was asked of each destination immediately
before that file was moved, so a call whose third output landed on a
held name refused with the first two already collected: sources gone,
destinations written, no manifest record, and a recovery to do by
hand. The sentence stated it as a property rather than a defect,
because no record is destroyed either way, and said outright that
making it a pre-scan too was an acceptance decision. That decision was
taken on the GEO-039 triage. The whole destination set is now resolved
before the first move, and the refusal names every held file rather
than the first one it meets.

## Historical row-key changes

- v0.17.0: `COLD_START`, whether a steady row clears the solver between the points of its sweep. Warm is the default and this is the opt-out (FR-95); and `RESTART`, how to continue a run the wall clock stopped, which v0.17.0 PARSED and refused to run (FR-96)
- v0.17.0: **FOUR NAMES LEFT THIS CELL AND BECAME COLUMNS**: `GEOMETRY`, `SYMMETRY`, `SYMMETRY_LOADS` and `NCPUS`, which lived here or in the setup and now have a column each, beside the two that are new in both homes, `CONFIGURATION` and `WALLTIME` (FR-93). A row that states one of the six in BOTH homes is refused naming both. The rows above still show the cell spelling because that is what a file written before 0.17.0 carries, and `pyfs-matrix upgrade` moves them
