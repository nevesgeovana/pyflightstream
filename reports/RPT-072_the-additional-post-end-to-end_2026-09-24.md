# RPT-072: the additional post end to end on 26.124 (2026-09-24)

**Date:** 2026-09-24
**Found by:** the licensed test T10 of the 0.27.0 work
**Status:** CLOSED in 0.27.0 (G12: `pyfs-matrix post --additional-pproc` reopens each point's final saved simulation and extracts what a new pproc asks, with no new solve)

## What this settles

G12 lets a finished campaign ask for products its pproc did not: a row states
`ADDITIONAL_PPROC: <pproc>`, and `pyfs-matrix post --additional-pproc` reopens
the point's saved simulation, extracts, exports and closes, without solving
again. T10 runs it on the licensed workspace of T07 and checks what the
definition of record promises: the right points extract, the others are skipped
with their reason, nothing of the original run moves, and a second pass extracts
nothing.

## What was run

FlightStream 26.124 (build 8172026), detached, no solver alive before, on the
eight recorded points of `matriz_mesh.fs`. Three rows state `ADDITIONAL_PPROC:
p009` (one XZ distribution of 12 sections on the wing, a group, the VTK export):
4101 (steady), 4102 (steady, raw mesh) and 4105 (unsteady). 4102's saved
simulation was deleted on purpose before the pass. `runs.json` and every output
of the eight points were hashed before it.

## What came back

- 4101 and 4105 extracted into `datapoints/DP-<point>/additional/p009/`: the
  loads table, the Tecplot and VTK exports, the Cp and sectional-loads tables,
  the log, and for the unsteady point the plots; no reopened copy of the saved
  file. 4102 was skipped `NO_SAVED_SIMULATION`, naming where the file should be;
  the five rows without the key were skipped `NO_KEY`.
- Each extraction's loads table equals its run's, digit for digit (4101: CL
  0.3293351, CDi 0.0288962; 4105: CL 0.1794990, CDi 0.0193077). Each extraction
  script opens the saved file and carries no `START_SOLVER`.
- The sectional-loads table carries the 12 new sections (4101) and, for the
  unsteady point, the run's rows and the new ones.
- `additional.json` holds one EXTRACTED record per point, whose saved-simulation
  hash equals the run record's before and after the extraction.
- `runs.json` and all 70 original outputs hash as before the pass (the deleted
  file aside).
- The products are written under `post/matriz_mesh/additional/p009/`, and
  `post.log.json` records the unsteady point's one-instant extraction.
- A second pass extracted nothing: 4101 and 4105 `ALREADY_EXTRACTED`, 4102
  still `NO_SAVED_SIMULATION`, no solver launched (2.7 s).

**Verdict: VERIFIED.** The additional post extracts from the saved simulation
without solving, skips what it cannot extract with its reason, leaves the run's
record and outputs untouched, and does not repeat itself.
