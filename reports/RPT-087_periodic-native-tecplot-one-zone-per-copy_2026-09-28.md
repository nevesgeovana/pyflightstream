# RPT-087 - A periodic row's native Tecplot is read one zone per copy (2026-09-28)

A re-measurement on **FlightStream 26.124, build #8172026** (read from the
run banner of a six-copy periodic probe row's own log: `FlightStream version
26.1, build #8172026`), using the real native Tecplot export and its matching
VTK export of that row. It establishes that a row under `SYMMETRY PERIODIC`
writes its native Tecplot export as one complete file per periodic copy, and
that the 0.30.0 reader (`read_native_tecplot_zones`,
`attach_native_strength_by_copy`, `translate_vtk_surface`, all in
`pyflightstream.results`) reads that shape end to end, matches each zone to
its VTK copy, and refuses a wrong zone count, while the 0.29.0-era reader
refused the file outright.

## Why it was run

Commit `105bc274` ("fix: a periodic row's native Tecplot is read one zone per
copy (P1)", branch `fix/0-30-robust`) states: a row under `SYMMETRY PERIODIC`
writes its native Tecplot as one complete file per periodic copy (`TITLE`,
`VARIABLES`, `ZONE`, payload, each), six zones of 5961 nodes for a six-copy
sector, zone k equal to the k-th block of the VTK to 1e-13 m; the copies share
378 seam positions, so one whole-disc match is ambiguous; the 0.29.0 reader
refused the file as "trailing data or multiple zones". This report
re-measures every one of those figures against a real native Tecplot / VTK
pair from a six-copy periodic probe row on this machine.

## Source

A six-copy periodic probe row (`SYMMETRY PERIODIC 6` in its own emitted
script), run locally on this machine on 2026-09-28, FlightStream 26.124 build
#8172026. Its native Tecplot export, matching VTK export and log are read
directly; their SHA-256 hashes are recorded in the JSON sidecar. The run sets
a custom analysis loads frame (frame index 2), placed at the origin with
identity axes (the script's own `EDIT_COORDINATE_SYSTEM` block for that
frame), which is the identity transform to the reference frame the native
reader expects; the VTK was carried through `surface_in_reference` with that
frame regardless, for traceability.

## Method

Commands (from `pfs0300-robust`, `PYTHONPATH=src`, the project's own
interpreter, branch tip `e481753e` with `105bc274` as an ancestor):

```
python -c "from pyflightstream.results.native_surface import read_native_tecplot_zones, attach_native_strength_by_copy; ..."
python -c "from pyflightstream.results.surface import translate_vtk_surface; ..."
python -m pytest tests/tier1_offline/test_periodic_native_zones.py -v
```

`read_native_tecplot_zones(native, zones=6)` reads the six zones directly;
`attach_native_strength_by_copy` joins each zone to its VTK copy and reports
its own matched-node count and coordinate tolerance; the direct
`|zone k points - VTK block k points|` was also computed independently of
that function, per copy; coincident (seam) node positions were counted by
rounding every zone's points to 1e-9 m and counting positions shared by more
than one node. `translate_vtk_surface` was run end to end with
`periodic_copies=6`, `5` and `None`, against the real VTK and native files.
The reader as it stood one commit before the fix (`105bc274~1`, checked out
in an isolated worktree, removed afterward) was run against the same real
native Tecplot file via its single-zone entry point,
`read_native_tecplot_surface`.

## Result

| Claim (commit `105bc274`) | Measured |
| --- | --- |
| Six zones, one per copy | **6 zones read** (`read_native_tecplot_zones(..., zones=6)`) |
| 5961 nodes per zone | **5961 nodes in every one of the 6 zones** (5840 elements each) |
| Zone k equals the k-th VTK block to 1e-13 m | **Matched.** Direct per-copy max `|zone k - VTK block k|`: 4.63e-15, 8.29e-14, 9.42e-14, 4.58e-15, 4.08e-15, 3.85e-15 m; overall max **9.42e-14 m**, under the claimed 1e-13 m. (`attach_native_strength_by_copy`'s own auto-picked matching tolerance was 7.34e-06 m per axis, a matching threshold, not the achieved residual; reported for completeness.) |
| 378 shared seam positions | **378 distinct coincident XYZ positions** (764 node instances at those positions) across the six zones, at 1e-9 m rounding |
| 0.29.0 reader refuses with "trailing data or multiple zones" | **Reproduced exactly**: `read_native_tecplot_surface` at `105bc274~1`, run against this same real file, raised `MalformedOutputError: Native Tecplot has trailing data or multiple zones` |
| `zones=6` translates; a wrong count is refused naming both | **Reproduced.** `translate_vtk_surface(..., periodic_copies=6)` succeeded (`matched_nodes: 35766`, the auxdata marker line reads "native values of 6 zones, zone k joined to the k-th periodic copy of the VTK..."); `periodic_copies=5` and `periodic_copies=None` (defaulting to 1) were both refused, each naming the 6 zones actually present against the count expected |
| Build | **26.124, build #8172026**, read from the row's own log banner |

Every figure in the commit is reproduced exactly or bettered (the coordinate
match is measured tighter than the 1e-13 m ceiling the commit states, not
merely "within" it by an unmeasured margin).

## Independent confirmation via the package's own tests

The shipped tier-1 test module for this fix was also run unmodified, against
its own reconstructed fixture (not the real file above, which the shipped
test does not carry): 8 of 8 passed
(`tests/tier1_offline/test_periodic_native_zones.py`), including the
copy-by-copy join against a VTK and the seam-ambiguity control. This confirms
the reader's logic is exercised the same way in both the shipped fixture and
the real file measured here.

## What is not established

- This probe row is a local, standalone run, not part of any tracked,
  versioned research campaign; it was produced specifically to exercise this
  path. No claim is made here about how representative its geometry or flow
  point are of other periodic-symmetry configurations.
- The auto-picked coordinate tolerance `attach_native_strength_by_copy`
  computed (7.34e-06 m) was not independently derived in this report; it is
  read from the function's own returned record, not recomputed by a separate
  method.
